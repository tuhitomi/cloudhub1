# Vận hành production: đo tải, khôi phục dữ liệu, giám sát SLO và bảo mật

Thực hiện ngày 12/11/2026 trên tài khoản production (Singapore, stack điều khiển `cloudhub-pages-live`). Không thay đổi stack điều khiển; mọi thứ mới nằm trong stack riêng hoặc là cấu hình của tài nguyên không thuộc stack đó.

## 1. CDN gần người dùng (stack `cloudhub-shared-edge`)

Change set: `PriceClass_100 → PriceClass_200` và cache policy `FrontendEdgeCachePolicy` (TTL 60–300 s, gzip/brotli) cho asset và `index.html`; `config.js` vẫn không cache. `Modify FrontendDistribution` (không thay thế) + `Add` một cache policy.

| Trang chủ, 20 lượt tuần tự từ Việt Nam | Trước | Sau |
|---|---|---|
| Edge | HIO52 (Oregon) | SGN50 (TP.HCM) |
| TCP connect p50 | ~280 ms | 145 ms |
| Kích thước | 33.358 B, không nén | 7.431 B, brotli |
| Cache | Miss mọi lần | Hit (Age tăng dần) |
| p50 / p95 | 1.322 / 2.812 ms | **531 / 1.326 ms** |

## 2. Thử tải 20 người dùng đồng thời

`loadtest`: 20 người dùng ảo, giữ kết nối như trình duyệt, nghỉ 0,5 s giữa các request, 120 s, trộn 40 % `/public/catalog`, 30 % `/ui-context`, 30 % trang chủ. Tổng 3.499 request, 28,9 request/s.

| Điểm cuối | Thành công | p50 | p95 | p99 |
|---|---|---|---|---|
| Trang chủ (CloudFront) | 1.133/1.133 | 93 ms | 589 ms | 1.020 ms |
| `GET /ui-context` | 1.025/1.026 (1 × 503) | 112 ms | 472 ms | 1.030 ms |
| `GET /public/catalog` | **609/1.340 (731 × 429)** | 185 ms | 1.021 ms | 2.795 ms |

**Phát hiện**

1. **`GET /public/catalog` bị throttle ở mức 5 request/s, burst 10** (route setting của stage `$default`). Đây là giới hạn chung cho mọi khách, mà mỗi lượt mở trang chủ đều gọi catalog, nên khoảng 5 khách/giây đã gặp 429.
2. **Lambda concurrency của cả tài khoản chỉ là 10** (`AccountLimit.ConcurrentExecutions`), mức mặc định của tài khoản mới (bình thường là 1.000). Bốn function dùng chung 10 suất; khi đầy, API trả 503.

**Khắc phục đề xuất**

- Gửi yêu cầu tăng quota Lambda concurrent executions qua Service Quotas (miễn phí; AWS thường duyệt khi tài khoản đã xác minh xong).
- Đưa `/public/catalog` qua cache: mã của PR #2 đã có cache 60 s trong Lambda và `Cache-Control: public, max-age=60`. Cách triệt để hơn là route `/public/catalog` qua CloudFront với TTL 60 s, khi đó API chỉ nhận tối đa khoảng 1 request/phút cho mỗi POP. Sau đó nâng throttle của route lên 25–50 request/s qua quy trình phát hành của stack điều khiển.

## 3. Diễn tập khôi phục dữ liệu (DynamoDB PITR)

Bảng metadata: 2.970 item, 4,5 MB, on-demand, đã mã hóa, PITR đã bật (35 ngày).

| Bước | Kết quả |
|---|---|
| Lệnh restore (latest restorable time) sang bảng mới | 21:07:04 |
| Điểm khôi phục | 21:02:06, nên **RPO ≈ 5 phút** (độ trễ của PITR) |
| Bảng mới ACTIVE, kèm GSI `by_owner` | **RTO = 255 s** |
| Đối chiếu `pk` + `version` | **2.970/2.970 khớp**, 0 khác biệt |
| Dọn dẹp | Xóa bảng diễn tập |

Sau diễn tập: bật **Deletion Protection** cho bảng production (trước đó đang tắt). Bảng không do stack quản lý trực tiếp (được truyền vào qua tham số `Table`), nên không gây drift.

RTO trên chỉ tính phần dữ liệu. Để chuyển ứng dụng sang bảng mới còn cần cập nhật tham số `Table` của stack điều khiển (một change set).

## 4. Giám sát và SLO

**`cloudhub-observability`** (Singapore, `infra/observability/regional.json`):

- Dashboard `cloudhub-observability-slo`: tỷ lệ khả dụng 30 ngày và error budget còn lại; request, 4xx, 5xx; latency p50/p95/p99 và integration latency; Lambda concurrency so với quota tài khoản, throttle, duration, error theo function; DynamoDB RCU/WCU/throttle; Step Functions started/succeeded/failed/time; CloudFront request và error rate.
- **SLO:** 99,5 % request API không lỗi 5xx trong 30 ngày, tức error budget 0,5 %.
- **Burn-rate alarm** đa cửa sổ (Google SRE workbook): 1 giờ > 14,4 (tiêu 2 % budget/giờ) và 6 giờ > 6. Composite alarm `slo-page` gom hai alarm này với alarm concurrency > 80 % quota.
- Alarm riêng cho latency p95 > 2 s, Lambda throttle, DynamoDB throttle, workflow thất bại. Tất cả gửi về `AlertTopic` hiện có.

**`cloudhub-healthchecks`** (us-east-1, `infra/observability/global-checks.json`):

- Route 53 health check HTTPS 30 giây/lần cho `https://cloudhub1.me/` và `https://api.cloudhub1.me/ui-context`, từ Singapore, Tokyo, N. Virginia và Ireland. Tất cả đang `200 OK`. Mỗi Region phân giải ra edge CloudFront khác nhau (ví dụ 13.35.163.x ở Singapore, 3.162.140.x ở Ireland), cho thấy CDN đang phục vụ theo vị trí địa lý.
- Alarm khi check fail (2/3 phút) và khi CloudFront 5xx > 1 %. Topic `GlobalAlerts` gửi email; người nhận cần bấm xác nhận đăng ký trong email AWS.

Chi phí ước tính: 2 health check HTTPS khoảng 3,5 USD/tháng; khoảng 12 alarm 1,2 USD/tháng; dashboard 3 USD/tháng (3 dashboard đầu miễn phí).

## 5. Bảo mật tài khoản

Hiện trạng: root đã có MFA và không có access key. Chưa có IAM user, password policy, CloudTrail trail, AWS Config hay Access Analyzer. GuardDuty và Security Hub trả `SubscriptionRequiredException` vì tài khoản đang được AWS xác minh.

Đã triển khai stack `cloudhub-security-baseline` ngày 13/11/2026 từ `infra/security/baseline.json` (`scripts/security_baseline_infra.py`). Trail `IsLogging=true`, `IsMultiRegionTrail=true`, `LogFileValidationEnabled=true`; Access Analyzer `ACTIVE`; 5 alarm CIS gửi về `AlertTopic`. Stack gồm:

- CloudTrail ghi mọi Region, có xác thực tính toàn vẹn log. Bucket S3 mã hóa, chặn public, chỉ cho TLS, versioning, xóa sau 1 năm.
- Log đẩy vào CloudWatch Logs (lưu 90 ngày), kèm alarm theo CIS 4.1–4.5: dùng root, đăng nhập console không MFA, gọi API trái phép, sửa IAM policy, sửa CloudTrail.
- IAM Access Analyzer phạm vi tài khoản.

Lệnh đã dùng để triển khai (cần quyền tạo IAM role và CloudTrail):

```sh
aws cloudformation deploy --region ap-southeast-1 --stack-name cloudhub-security-baseline \
  --template-file infra/security/baseline.json --capabilities CAPABILITY_IAM \
  --parameter-overrides AlertTopicArn=<AlertTopic ARN>
```

Việc nên làm thêm: tạo người dùng IAM Identity Center thay cho root; đặt password policy; bật GuardDuty và Security Hub (AWS Foundational Security Best Practices) khi tài khoản xác minh xong.

## Tái hiện

```sh
python scripts/observability_infra.py      # infra/observability/*.json
python scripts/security_baseline_infra.py  # infra/security/baseline.json
```
