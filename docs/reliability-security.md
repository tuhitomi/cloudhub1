# Độ tin cậy, bảo mật và kiểm soát chi phí

Bốn cơ chế bổ sung cho control plane. Mỗi cơ chế làm một việc riêng và đều tắt được bằng tham số. Phần đo hiệu năng và CDN nằm ở [performance.md](performance.md).

| Cơ chế | Mặc định | Chi phí ước tính | Tệp |
|---|---|---|---|
| Khóa chi tiêu theo AWS Budgets | Tắt (`MonthlyBudgetUsd=0`) | Budgets: 2 budget đầu miễn phí; Lambda/SNS không đáng kể | `backend/cloudhub/spend_guard.py`, `scripts/resilience_infra.py` |
| AWS X-Ray cho Lambda và Step Functions | Bật | Free tier 100.000 trace/tháng | `scripts/resilience_infra.py` |
| AWS WAF cho Cognito (REGIONAL) | Tắt (`IdentityWafEnabled=false`) | ≈ 5 USD/web ACL + 1 USD/rule/tháng + 0,6 USD/triệu request | `scripts/resilience_infra.py` |
| AWS WAF cho CloudFront (us-east-1) | Không gắn (`FrontendWebAclArn` rỗng) | ≈ 9 USD/tháng + request | `scripts/edge_waf.py`, `infra/hosting/edge-waf.example.json` |
| Change set qua GitHub OIDC | Chạy tay | Không | `.github/workflows/changeset.yml`, `infra/ci/github-changeset-role.json` |

## 1. Khóa chi tiêu (spend guard)

Ví và ngân sách nền tảng của CloudHub giới hạn chi phí **dự toán**. Spend guard phản ứng với chi phí **thực tế** trên hóa đơn AWS.

```
AWS Budgets (ACTUAL, tháng) ──SNS──► Lambda spend-guard ──► DynamoDB  G#SPEND_GUARD {frozen:true}
                                         │                         ▲
                                         └─► AlertTopic (email)    │ đọc ConsistentRead
                                                                   │
API create / restore ─► Service.quota(increase>0) ─────────────────┤
Gia hạn tay / tự động / resume ─► Lifecycle._charge ───────────────┘
```

- Budget `<stack>-monthly` gửi ba ngưỡng tới cùng một topic: ACTUAL 80% (chỉ cảnh báo), FORECASTED 100% (chỉ cảnh báo) và ACTUAL `SpendGuardThresholdPercent` (mặc định 100%, khóa).
- Lambda chỉ khóa khi nhận thông báo loại ACTUAL, đúng tên budget và đạt ngưỡng. IAM của Lambda chỉ cho đọc/ghi đúng một khóa `G#SPEND_GUARD` (điều kiện `dynamodb:LeadingKeys`).
- Khi đang khóa, tạo, khôi phục, gia hạn (tay và tự động) và mở lại môi trường đã tạm dừng trả `409 SPEND_GUARD_ACTIVE`. Gia hạn tự động bị chặn thì chạy chính sách kết thúc người dùng đã xác nhận (PAUSE hoặc BACKUP_RETIRE) và gửi thông báo `RENEWAL_BLOCKED`.
- Kết thúc, sao lưu, xuất dữ liệu, xóa bản sao và retry sao lưu bắt buộc khi thu hồi **không** bị chặn, để không làm kẹt tài nguyên đang tính phí.
- Khóa không tự mở, vì Budgets không gửi sự kiện "đã xuống dưới ngưỡng" và dữ liệu chi phí có độ trễ. Quản trị viên xem `GET /admin/spend-guard` và mở bằng `POST /admin/spend-guard {"frozen": false, "reason": "..."}`. Lý do bắt buộc 10–500 ký tự; 20 thay đổi gần nhất được lưu.

Bật: đặt `MonthlyBudgetUsd` (ví dụ `50`) khi tạo change set. `AlertEmail` hiện có sẽ nhận email lúc khóa.

## 2. Truy vết với AWS X-Ray

Mọi `AWS::Serverless::Function` có `Tracing: Active`, và state machine vòng đời có `Tracing.Enabled`. Quyền `xray:PutTraceSegments` được thêm tường minh vào từng role. Trên X-Ray console, một operation hiện thành chuỗi: Lambda API → DynamoDB → Step Functions → Lambda worker → CloudFormation/EC2/RDS (AWS SDK). Nhờ vậy thấy được bước nào chiếm thời gian. HTTP API không hỗ trợ X-Ray, nên trace bắt đầu từ Lambda.

Dashboard `<stack>-operations` có thêm widget số execution Step Functions bắt đầu, thành công, thất bại và timeout.

## 3. AWS WAF

**Cognito (REGIONAL, cùng stack):** `IdentityWafEnabled=true` tạo web ACL gắn vào user pool, gồm danh sách IP xấu của AWS (`AmazonIpReputationList`) và giới hạn 100 request/5 phút mỗi IP cho các API đăng ký, đăng nhập, quên mật khẩu, nhằm chống spam tạo tài khoản và dò mật khẩu.

**CloudFront (CLOUDFRONT scope):** WAF cho CloudFront bắt buộc tạo ở `us-east-1`, nên nằm trong template riêng:

```sh
python scripts/edge_waf.py
aws cloudformation deploy --region us-east-1 --stack-name cloudhub-edge-waf \
  --template-file infra/hosting/edge-waf.example.json
```

Lấy output `WebAclArn` và truyền vào tham số `FrontendWebAclArn` của stack edge (`configure_edge`). Để trống thì gỡ web ACL. Rule gồm `AmazonIpReputationList`, `KnownBadInputsRuleSet`, `CommonRuleSet` và giới hạn 2.000 request/5 phút mỗi IP. Nên theo dõi metric `BlockedRequests` vài ngày trước khi coi là ổn định, vì `CommonRuleSet` có thể chặn nhầm request hợp lệ.

HTTP API không gắn được WAF trực tiếp. API vẫn được bảo vệ bằng JWT, throttling stage (xem performance.md) và kiểm owner tại backend.

## 4. Đề xuất change set qua GitHub OIDC

Workflow `Propose AWS change set` chỉ chạy tay (`workflow_dispatch`), chỉ trên `main`, trong GitHub environment `aws-changeset`. Các bước:

1. Chạy toàn bộ `check_product_release.py`.
2. Kiểm `infra/control-plane.json` khớp với output của generator.
3. Nhận credentials tạm qua OIDC; không lưu access key trong GitHub.
4. `cloudformation package` rồi `deploy --no-execute-changeset`.
5. Ghi bảng tài nguyên Add/Modify/Remove/Replacement vào job summary.

Role `infra/ci/github-changeset-role.json` chỉ tin token của đúng repo và environment `aws-changeset`. Role được tạo, xem và xóa change set của một stack, nhưng **bị Deny** `ExecuteChangeSet`, `UpdateStack`, `CreateStack`, `DeleteStack` và `iam:PassRole`. Người có quyền vẫn phải tự đọc rồi thực thi change set.

Thiết lập một lần:

```sh
python scripts/ci_deploy_role.py
aws cloudformation deploy --stack-name cloudhub-github-changeset \
  --template-file infra/ci/github-changeset-role.json --capabilities CAPABILITY_IAM \
  --parameter-overrides ArtifactBucket=<bucket> StackName=<control-plane-stack>
```

Sau đó trên GitHub: tạo environment `aws-changeset` (nên bật *Required reviewers*), đặt biến `AWS_CHANGESET_ROLE_ARN`, `CLOUDHUB_ARTIFACT_BUCKET` và tùy chọn `AWS_REGION`.

## Kiểm thử

`python -m unittest tests/test_resilience.py` gồm 18 ca: đọc thông báo Budgets, khóa idempotent và chỉ gửi email một lần, bỏ qua forecast/ngưỡng thấp/budget khác, mở khóa bắt buộc có lý do; tạo, gia hạn tay bị chặn còn gia hạn tự động chuyển sang chính sách kết thúc; điều kiện IAM `LeadingKeys`; X-Ray trên mọi function; WAF; role CI không thể execute; workflow chạy tay, chỉ trên main và không dùng khóa.

Chưa kiểm trên AWS: email Budgets thật (cần chờ chi phí thực vượt ngưỡng hoặc đặt ngưỡng thấp trên tài khoản thử), metric WAF và trace X-Ray sau khi deploy.
