# Phân công CloudHub — T01–T09

Ngày chốt: 13/10/2026. T10/A19 được loại khỏi phạm vi hiện tại theo yêu cầu người dùng. Mỗi dòng dưới đây có đúng một người chịu trách nhiệm; không dùng nhãn “cả nhóm” cho đầu việc.

## Tổng giờ và giới hạn

| Người | Công việc | Dự phòng riêng | Tổng dự toán | Mẫu AWS |
|---|---:|---:|---:|---|
| TV1 | 190 | 20 | 210 | T01, T08 — EC2, EBS, EFS |
| TV2 | 190 | 20 | 210 | T02, T05, T07 — S3, CloudFront, EC2, Cognito |
| TV3 | 190 | 20 | 210 | T03, T09 — EC2, RDS, API Gateway, Lambda, DynamoDB |
| TV4 | 190 | 20 | 210 | T04, T06 — ALB, ASG, ECS, Scheduler, Step Functions |

**Đây là phân bổ giờ kế hoạch gốc, không phải giờ đã làm hoặc giờ còn lại.** Các nhiệm vụ có mã hiện có cần được đọc, kiểm tra, sửa phần thiếu và tự giải thích/demo; không mặc định viết lại từ đầu.

Báo cáo gốc: 800 giờ công việc + 80 dự phòng = 880. Loại A19/T10 (40 giờ) khỏi phạm vi hiện tại: 760 + 80 = 840. Giữ nguyên giờ từng mục còn lại; các mục lớn chỉ tách giờ cho người chịu trách nhiệm.

**Chưa khớp khung ban đầu 500 + 60 = 560 giờ:** chênh 280 giờ, tương đương 70 giờ/người so với trần 140 giờ/người trong 10 tuần. Không sửa giờ gốc trên giấy để tuyên bố khả thi. Cần ghi effort đã dùng/còn lại, xác định phần tái sử dụng và cắt phạm vi hoặc điều chỉnh lịch được chấp nhận trước khi coi đây là kế hoạch thực hiện 10 tuần.

## Cách nhận và bàn giao đầu việc

- Mỗi người tự làm IaC/quyền/SDK, triển khai, truy cập/ghi dữ liệu, backup/restore/checksum/cleanup và hướng dẫn của các mẫu được giao.
- Đơn vị giờ là giờ người. Ví dụ A22.1=20 giờ cho TV1; không nhân thêm số người và không tính trùng với A22.2–A22.4. Kiểm thử module thuộc nhiệm vụ xây module; A22 là kiểm thử tích hợp riêng.
- Dùng nhánh `team/tv1`, `team/tv2`, `team/tv3`, `team/tv4` khi các thành viên bắt đầu làm; tài liệu này không tự tạo nhánh/PR hoặc nhận đã phân quyền GitHub.
- File/helper dùng lại có một owner tích hợp ở danh sách dưới; người làm mẫu phụ thuộc gửi diff/API contract cho owner đó. Không đồng thời sửa cùng file. T05 dùng helper Linux của TV1; T04 dùng helper RDS của TV3.
- Một người chịu trách nhiệm đầu ra, người khác review không đồng nghĩa chia đôi giờ hoặc bỏ trách nhiệm. Cặp review: TV1↔TV2, TV3↔TV4; review được ghi vào quỹ công việc/dự phòng của chính người thực hiện.
- AWS: trước thay đổi tài nguyên phải có config/dự toán/cách thu hồi và phạm vi tài khoản/region/ngân sách đã duyệt. Tái sử dụng minh chứng T01–T09 hiện có; local mock không thay AWS thật, không chạy lại vòng đời có phí chỉ để hoàn thiện bảng phân công.

## TV1 — T01, T08 — EC2, EBS, EFS

| Mã | Giờ | Nhiệm vụ | Sản phẩm phải bàn giao |
|---|---:|---|---|
| A01 | 16 | Yêu cầu, luồng người dùng và tiêu chí nghiệm thu | Checklist F00–F08, luồng chọn nhu cầu → dự toán → tạo → quản lý; tiêu chí từng T01–T09 và các trạng thái lỗi. |
| A02 | 20 | Repository và CI | Cấu hình kiểm tra Python/JS/schema/IaC, hướng dẫn nhánh và PR; kiểm tra nguồn không chứa credentials hoặc binary. |
| A05 | 48 | Frontend và luồng quản lý | Danh mục, luồng tạo bốn bước, tổng quan/chi tiết/tác vụ, gia hạn/đổi chế độ/kết thúc, backup/restore và UI quản trị; trạng thái loading/empty/error, responsive/focus. |
| A10 | 32 | T01 — Máy Linux: EC2/EBS | IaC/driver, IAM, SSH, ghi dữ liệu /data, snapshot/restore, pause/resume, thu hồi và kiểm kê; kiểm thử và hướng dẫn T01. |
| A18 | 40 | T08 — Ổ đĩa dùng chung: EC2/EFS | IaC/driver, mount target/security group, đọc/ghi từ hai máy, backup/restore/checksum, gỡ phụ thuộc và cleanup; kiểm thử và hướng dẫn T08. |
| A22.1 | 20 | Kiểm thử tích hợp UI và luồng sử dụng | Ca tạo → theo dõi → truy cập → backup → restore → kết thúc; lỗi mạng/gửi lặp/giữ form, thiếu dữ liệu và ảnh desktop/mobile; kết quả local/AWS tách riêng. |
| A23.1 | 8 | Đo trải nghiệm giao diện | Đo bố cục 360/390/768/1440, focus/reduced motion, phản hồi form và khả năng đọc tiền/trạng thái; ghi lỗi và sửa. |
| A24.1 | 6 | Bàn giao giao diện và hướng dẫn người dùng | Hướng dẫn sử dụng, luồng demo frontend, T01/T08 và minh chứng UI; checklist nghiệm thu sản phẩm. |
| A25.1 | 20 | Quỹ dự phòng của người phụ trách | 20 giờ giữ lại cho học dịch vụ/sửa lỗi/tích hợp thuộc các đầu việc đã giao; chỉ ghi giờ dùng khi thực tế phát sinh. |

**Phạm vi file/điểm tích hợp:**

- `frontend/` trừ `auth.js`: UI/interaction/integration; contract auth do TV2 cung cấp.
- `backend/cloudhub/templates.py`, `aws_driver.py`, `efs_template.py`, `efs_driver.py`, `efs_records.py`: helper Linux và T08.
- `.github/workflows/ci.yml` và bộ kiểm thử frontend/UX.

## TV2 — T02, T05, T07 — S3, CloudFront, EC2, Cognito

| Mã | Giờ | Nhiệm vụ | Sản phẩm phải bàn giao |
|---|---:|---|---|
| A03 | 32 | Hạ tầng nền và quyền triển khai | CloudFormation control plane/network, IAM và role theo phạm vi; cấu hình tài khoản/region, kiểm tra quota, cấu hình host S3/CloudFront. |
| A04 | 32 | Cognito và xác thực/phân quyền | Đăng ký, xác thực email, đăng nhập/refresh/reset; mặc định user và quota do admin đặt; kiểm quyền chủ sở hữu tại API. |
| A11 | 24 | T02 — Website tĩnh: S3/CloudFront | IaC/driver, HTTPS, upload/read file, backup/restore/checksum, thu hồi và kiểm kê; kiểm thử và hướng dẫn T02. |
| A14 | 20 | T05 — Website trên máy chủ: EC2/web server | Cấu hình web và nội dung /data trên helper Linux, truy cập, backup/restore, pause/resume/cleanup; kiểm thử và hướng dẫn T05. |
| A15 | 24 | T07 — Kho file và chia sẻ: S3 | Upload/download file riêng tư, liên kết có hạn, backup/restore/checksum/cleanup; kiểm thử quyền và hướng dẫn T07. |
| A20 | 36 | CloudWatch/SNS và backend quản trị | Chỉ số/log/cảnh báo, thông báo sắp hết hạn, quản trị user/quota/signup-defaults, toàn bộ môi trường và thu hồi admin; kiểm thử role và cấu hình nhận cảnh báo. |
| A22.2 | 16 | Kiểm thử xác thực và quyền quản trị | Email trùng, mã sai/hết hạn/gửi lại, sai mật khẩu/reset; user chưa verified, owner chéo, role/admin và quota mặc định không tự nâng. |
| A24.2 | 6 | Bàn giao triển khai và quản trị | Hướng dẫn cấu hình AWS/Cognito/IAM/CI và frontend hosting, T02/T05/T07, đăng ký cảnh báo và quản trị tài khoản. |
| A25.2 | 20 | Quỹ dự phòng của người phụ trách | 20 giờ giữ lại cho học dịch vụ/sửa lỗi/tích hợp thuộc các đầu việc đã giao; chỉ ghi giờ dùng khi thực tế phát sinh. |

**Phạm vi file/điểm tích hợp:**

- `frontend/auth.js`; `backend/cloudhub/accounts.py`, `registration.py`, `access.py`, `portal.py`, `portal_api.py`: auth/admin.
- `backend/cloudhub/s3_template.py`, `s3_driver.py`, `s3_files.py`: T02/T07; cấu hình web T05 dùng helper Linux do TV1 quản lý.
- `scripts/generate_infra.py`, `generate_network.py`, `configure_frontend.py`, `build_pages_live.py`: hạ tầng/host; `infra/control-plane.json`, `network.json` là đầu ra sinh.

## TV3 — T03, T09 — EC2, RDS, API Gateway, Lambda, DynamoDB

| Mã | Giờ | Nhiệm vụ | Sản phẩm phải bàn giao |
|---|---:|---|---|
| A06 | 32 | DynamoDB, API và trạng thái bền vững | API môi trường/tác vụ/bản sao; dữ liệu, khóa, conditional update, giao dịch quota, idempotency và kiểm tra quyền sở hữu; OpenAPI và lỗi thống nhất. |
| A07 | 40 | Điều phối tạo/khôi phục | Hợp đồng driver, router/worker, HTTP 202 + operation_id; workflow tạo stack/chờ/readiness/rollback/restore, lưu trạng thái và xử lý retry. |
| A09 | 36 | Dự toán và hạn mức | Đơn giá/giả định, kỳ tham chiếu/kỳ đầu/gia hạn/giữ dữ liệu; budget cộng dồn và quota, chi phí ghi nhận có phạm vi/độ trễ; không bảo đảm hóa đơn. |
| A12 | 40 | T03 — Web và cơ sở dữ liệu: EC2/RDS | IaC/driver, Secrets Manager, đọc/ghi PostgreSQL, snapshot/restore và kiểm dữ liệu, thu hồi và kiểm kê; kiểm thử và hướng dẫn T03. |
| A17 | 32 | T09 — API serverless: API Gateway/Lambda/DynamoDB | IaC/driver, gọi API có Cognito, đọc/ghi dữ liệu, backup/restore và quyền chủ sở hữu, cleanup; kiểm thử và hướng dẫn T09. |
| A22.3 | 4 | Kiểm thử tích hợp API/workflow | Kiểm contract HTTP 202, operation_id, lỗi chuẩn, phản hồi retry/idempotency và giao dịch quota trong bộ kiểm thử hiện có; kiểm riêng T03/T09. |
| A24.3 | 6 | Bàn giao API/dữ liệu/dự toán | OpenAPI, hợp đồng driver/dữ liệu, hướng dẫn API/T03/T09, bảng đơn giá/giả định và giới hạn phép đo. |
| A25.3 | 20 | Quỹ dự phòng của người phụ trách | 20 giờ giữ lại cho học dịch vụ/sửa lỗi/tích hợp thuộc các đầu việc đã giao; chỉ ghi giờ dùng khi thực tế phát sinh. |

**Phạm vi file/điểm tích hợp:**

- `backend/cloudhub/api.py`, `service.py`, `store.py`, `errors.py`, `catalog.py`: API, dữ liệu, quota và danh mục.
- `worker.py`, `runtime.py`, `driver_router.py`, `stack_driver.py`, `cf_common.py`: giao diện điều phối/adapter; gọi module lifecycle của TV4.
- `cost.py`, `actual_cost.py`, `rds_template.py`, `rds_driver.py`, `rds_app.py`, `data_template.py`, `data_driver.py`, `data_api_app.py`.
- `scripts/generate_openapi.py`, `docs/openapi.json`, cấu hình prices.example và hợp đồng API/driver.

## TV4 — T04, T06 — ALB, ASG, ECS, Scheduler, Step Functions

| Mã | Giờ | Nhiệm vụ | Sản phẩm phải bàn giao |
|---|---:|---|---|
| A08 | 40 | Chế độ vận hành và xử lý đến hạn | Scheduler/Step Functions cho AUTO_RENEW/AUTO_OFF; ledger cộng dồn, deadline/revision, lịch cũ, đổi chế độ sát hạn, đồng bộ lịch lỗi, pause/resume và giữ nguồn khi backup lỗi. |
| A13 | 40 | T04 — Web chịu tải: ALB/ASG | Cấu hình ALB/ASG, health check/giới hạn scale, tích hợp web/RDS của T03, vòng đời dữ liệu/restore/cleanup; kiểm thử và hướng dẫn T04. |
| A16 | 36 | T06 — Docker: ECS Fargate | IaC/driver, image ECR đã duyệt và digest, readiness, dữ liệu bền vững S3, backup/restore/cleanup; kiểm thử và hướng dẫn T06. |
| A21 | 48 | Kiểm kê và hạn lưu dữ liệu | Audit deleted/retained/residual/unknown/billable, bảo vệ tài nguyên dùng chung, retry thu hồi, retention, xóa/export backup và khóa đồng thời. |
| A22.4 | 8 | Kiểm thử lỗi vòng đời và bảo vệ nguồn | Gia hạn sát hạn/lịch cũ, đồng bộ Scheduler lỗi, backup lỗi giữ nguồn, retry có giới hạn và cleanup còn sót; kiểm riêng T04/T06. |
| A23.2 | 12 | Đo tải và thời gian xử lý | Harness và số đo API/tác vụ, kích hoạt deadline/quét dự phòng, kiểm ASG. Bám concurrency demo hiện hành 10; không xin tăng quota hoặc tuyên bố SLA chưa đo. |
| A24.4 | 6 | Bàn giao vận hành và thu hồi | Runbook Scheduler/workflow/backup/restore/retention/audit, T04/T06, danh sách tài nguyên billable và cách xử lý lỗi. |
| A25.4 | 20 | Quỹ dự phòng của người phụ trách | 20 giờ giữ lại cho học dịch vụ/sửa lỗi/tích hợp thuộc các đầu việc đã giao; chỉ ghi giờ dùng khi thực tế phát sinh. |

**Phạm vi file/điểm tích hợp:**

- `backend/cloudhub/lifecycle.py`, `lifecycle_scheduler.py`, `operating_policy.py`, `archive.py`, `backup_export.py`: vận hành/retention/audit.
- `ecs_template.py`, `ecs_driver.py`, `container_app.py`: T06; phần ALB/ASG T04 gửi diff riêng cho TV3 tích hợp trong helper RDS.
- `infra/lifecycle.asl.json`, bộ kiểm thử lifecycle/fault/audit và harness đo tải/deadline.

## Đối chiếu báo cáo

A01–A18, A20–A24 đều có owner. A22 tách 20+16+4+8=48; A23 tách 8+12=20; A24 tách 6+6+6+6=24; A25 giữ 20 giờ dự phòng riêng cho từng người, tổng 80. A19/T10 có trạng thái ngoài phạm vi, không chuyển 40 giờ đó sang một việc khác.

Nguồn gốc `config/report-items.json` và `docs/report-traceability.md` giữ nguyên. Bảng này là phương án phân công mới theo yêu cầu chia cân bằng và mỗi người thực hành AWS, không sửa hồi tố báo cáo gốc hoặc ghi nhận nghiệm thu.

Máy đọc: [config/team-allocation.json](../config/team-allocation.json).
