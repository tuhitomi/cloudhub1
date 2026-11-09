# CloudHub

CloudHub giúp người chưa biết AWS chọn hạ tầng theo nhu cầu, xem dự toán trước khi xác nhận và quản lý môi trường, dữ liệu và bản sao. Người dùng CloudHub không cần cung cấp AWS access key.

Website: [cloudhub1.me](https://cloudhub1.me/).

## Phạm vi

| Mẫu | Nhu cầu |
|---|---|
| T01 | Máy Linux |
| T02 | Website tĩnh |
| T03 | Web và cơ sở dữ liệu PostgreSQL |
| T04 | Web cân bằng tải |
| T05 | Website trên máy chủ |
| T06 | Ứng dụng Docker |
| T07 | Kho file và chia sẻ |
| T08 | Ổ đĩa dùng chung |
| T09 | API serverless |

Mẫu, profile, Region và tính năng chỉ được mở theo capability do backend cung cấp. Tự động gia hạn là lựa chọn chủ động; thời gian xem dự toán không tự trở thành lịch tắt. T10 và Local Zones nằm ngoài phạm vi.

## Cấu trúc

```text
frontend/        Giao diện JavaScript, CSS và bản dịch
backend/         API, dữ liệu, nghiệp vụ và bộ xử lý AWS
infra/           CloudFormation và workflow
scripts/         Kiểm tra, cấu hình và công cụ triển khai
tests/           Kiểm thử Python và frontend
config/          Cấu hình mẫu
docs/            Hướng dẫn và kết quả kiểm tra
team/            Trách nhiệm thành viên và kế hoạch
```

Mã frontend, API, xác thực, workflow và driver của bốn thành viên đã được gộp vào `main`. Bộ kiểm thử chạy trực tiếp từ checkout này, không cần bổ sung mã nguồn bên ngoài. Để sử dụng với AWS vẫn cần cấu hình riêng, hạ tầng, giá và quyền đã được operator kiểm; kết quả tích hợp nguồn không xác nhận phiên bản đang phục vụ trên website.

## Kiểm tra nhanh

Yêu cầu Python 3.13 và Node.js 22 trở lên:

```sh
npm ci --ignore-scripts
python -m pip install -r requirements-dev.txt
python scripts/check_team_ownership.py
python scripts/check_local.py
python scripts/check_tv4.py --out tv4-checks.private.json
python scripts/check_product_release.py --out main-checks.private.json
```

Các lệnh này kiểm ownership, cú pháp, bản dịch, toàn bộ test Python/frontend, OpenAPI và các cấu hình IaC trong release checker. Runner đầy đủ dùng thông tin AWS giả và chặn transport bên ngoài; chỉ cho phép HTTP loopback của fixture. File `*.private.json` được Git bỏ qua. Phạm vi và kết quả thực tế nằm trong [hướng dẫn kiểm thử](docs/testing.md) và [báo cáo chốt main](docs/MAIN_INTEGRATION_STATUS.md).

## Nhóm thực hiện

| Thành viên | Trách nhiệm |
|---|---|
| [TV1 — Đào Quang Thái](team/TV1.md) | Frontend và trải nghiệm trình duyệt |
| [TV2 — Ngô Quang Dũng](team/TV2.md) | API, xác thực, metadata, dự toán, quota và ledger |
| [TV3 — Nguyễn Hải Dương](team/TV3.md) | IaC, mạng, IAM và driver T01–T09 |
| [TV4 — Hoàng Đường Anh Tú](team/TV4.md) | Nhóm trưởng; workflow, vòng đời, bảo vệ dữ liệu, quản trị và phát hành |

Phân công theo báo cáo v2. Owner là người theo dõi triển khai, tích hợp và review thành phần; lịch sử commit không tự thay thế bằng chứng kiểm thử hoặc giờ làm.

## Tài liệu

- [Kiến trúc](docs/architecture.md).
- [Phát triển và mở PR](docs/DEVELOPMENT.md).
- [Phân công theo file](team/FILE_OWNERSHIP.md), [kế hoạch](team/MILESTONES.md).
- [Kiểm thử](docs/testing.md), [nguồn và kết quả kiểm tra trước đây](docs/source-record.json).

Cấu hình thật, credentials, dữ liệu tài khoản và bằng chứng vận hành riêng không đưa vào repo. Mọi lần tạo tài nguyên AWS cần xác nhận đúng account, Region, quyền, dự toán và cách thu hồi; việc xem được mã không tự cấp quyền triển khai.

## Công việc TV4 tuần 9 và 10

Vòng đời, Scheduler, worker, quản trị/thông báo và các công cụ TV4 đã được tích hợp vào nhánh này. Xem [kết quả và blocker](docs/TV4_WEEK9_WEEK10.md), [runbook vận hành](docs/OPERATIONS_RUNBOOK.md) và [kịch bản demo](docs/DEMO_RUNBOOK.md).

Các blocker thiếu module ở lần kiểm 04/11 đã được gỡ sau khi TV2/TV3/TV1 tích hợp. CI hiện bắt buộc chạy hồi quy trực tiếp từ repo và toàn bộ release checker; thiếu module hoặc test bị bỏ qua làm kiểm tra thất bại. Kết quả fixture ngày 04/11 vẫn giữ nguyên như bằng chứng lịch sử, kết quả mới nằm trong [main-integration-results.json](docs/main-integration-results.json).

Phân công hiện tại là báo cáo v2, KH01–KH24 và `team/file-ownership.json`. Bốn tài liệu kế hoạch cũ đã được thành viên loại bỏ bằng commit revert; không còn được tính là module chờ tích hợp. Không mở T10 hoặc thay đổi capability trong lần chốt nguồn này.
