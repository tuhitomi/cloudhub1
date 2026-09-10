# CloudHub — phần bàn giao của nhóm trưởng TV1

CloudHub giúp người chưa biết AWS chọn hạ tầng, xem dự toán, xác nhận và quản lý môi trường. Danh mục T01–T09; người dùng không nhập AWS access key. Website hiện có: https://cloudhub1.me/.

**Repo này đang được các thành viên đưa mã lên từng phần. Hiện chỉ nhập phần TV1. Đây chưa phải bản clone đầy đủ có thể chạy frontend/backend từ đầu đến cuối.** Repo triển khai private và website AWS đang chạy không bị thay đổi bởi các commit này.

## Lịch nhập mã và trách nhiệm

Mã có sẵn được chia thành 8 đợt theo giai đoạn kế hoạch, với ngày tác giả 10/09–29/10/2026 theo yêu cầu chủ dự án. Mã được nhập thực tế ngày 29/10/2026, UTC+07. Theo yêu cầu ngày 30/10/2026, cả AuthorDate và CommitDate được đặt theo tám mốc giai đoạn 10/09–29/10; chúng không phải thời điểm Git thực sự tạo các commit. Đây không phải bằng chứng mã được viết, test hoặc triển khai AWS ở những ngày AuthorDate đó. Xem [lịch và giới hạn](team/WEEKLY_IMPORT.md).

| Người | Phạm vi nhận bàn giao | Phần AWS thực hành |
|---|---|---|
| TV1 / nhóm trưởng | Workspace/UI, catalog, wizard, i18n, Linux và EFS | T01/T08: EC2, EBS, EFS, SSH, snapshot/restore |
| TV2 | Xác thực, hosting, file, quản trị, Region | T02/T05/T07, Cognito, S3, CloudFront, IAM |
| TV3 | API, dữ liệu, quote, chi phí, tư vấn | T03/T09, RDS, Lambda, DynamoDB |
| TV4 | Vòng đời, Scheduler/workflow, thu hồi và Docker | T04/T06, ALB/ASG, ECS, Step Functions |

Chỉ TV1 được nhập trong đợt này; ba người còn lại tự commit phần được giao. [Bảng file](team/FILE_OWNERSHIP.md) và `team/file-ownership.json` mô tả cả phần còn chờ, không khẳng định mọi file đã có. Trách nhiệm tiếp quản không phải chứng nhận tác giả lịch sử, số giờ làm hoặc quyền AWS.

## Kiểm tra phần đã có

Python 3.13 và Node.js 22 trở lên:

```sh
npm ci --ignore-scripts
python scripts/check_team_ownership.py
python scripts/check_leader_handoff.py
```

Các lệnh trên chỉ kiểm nguồn và các test frontend đủ dependency trong phần TV1. Các test tích hợp chờ mã TV2–TV4 được liệt kê riêng; không coi là PASS và không được thay bằng mock rồi công bố AWS đã đạt. Xem [kết quả thực tế](team/handoff-validation.json) và [kiểm thử](docs/testing.md).

## Tích hợp tiếp theo

Giữ đường dẫn chuẩn; không đặt mã vào thư mục cá nhân. Mỗi thành viên clone `https://github.com/tuhitomi/cloudhub1.git`, tạo nhánh riêng từ main hiện tại, đưa đúng file vào và mở PR. Chưa tạo sẵn các nhánh `team/tv2`–`team/tv4` hoặc gắn GitHub handle chưa được xác định cho từng vai trò.

Frontend còn cần các module xác thực, lifecycle, dữ liệu, quota, upload và tư vấn từ người phụ trách. Linux/EFS còn cần catalog, lỗi, runtime, store, driver dùng chung và cấu hình triển khai. `frontend/config.example.js` chỉ là mẫu; không có credential hay cấu hình production. `scripts/ui_fixture.py` chờ API/service/store, chưa chạy độc lập ở bản bàn giao này.

Các gate, Region, quote/quota, owner checks, lịch và bảo vệ dữ liệu thuộc bản triển khai hiện có; đưa mã vào Git không tự mở tính năng, tạo tài nguyên hoặc cấp quyền AWS. Mã nguồn chưa đủ không được dùng để thay stack đang chạy. Không có T10/Local Zones/thanh toán trong phạm vi hiện tại.
