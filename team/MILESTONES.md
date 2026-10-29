# Kế hoạch phát triển

Mốc công việc theo Bảng 3.3 của báo cáo v2. Dùng kết quả test và minh chứng tương ứng để xác nhận đầu ra; bảng kế hoạch không tự chứng minh nghiệm thu AWS.

| Tuần | Đầu ra dự kiến |
|---|---|
| 1 | Thống nhất phạm vi, kiến trúc M1–M8/D01–D14, hợp đồng API/driver và phân công; khởi tạo cấu trúc frontend, backend và IaC. |
| 2 | Hoàn thành khung giao diện, tài khoản, phân quyền và hạ tầng chung; có khung operation và workflow để tích hợp. |
| 3 | Xây dựng metadata, admission, form cấu hình và nhóm driver EC2/RDS; triển khai các nhánh điều phối tạo môi trường. |
| 4 | Ghép luồng chọn mẫu → xác nhận → nhận operation; bổ sung gia hạn, xử lý đến hạn và các mẫu có EC2/RDS. |
| 5 | Bổ sung dự toán, ví, ledger, dashboard và nhóm Fargate/EFS; phát triển các bước sao lưu và khôi phục. |
| 6 | Tích hợp S3/serverless, truyền tệp, checksum, bản sao và thu hồi; hoàn thiện các thao tác nâng cao trong phạm vi. |
| 7 | Ghép các phân hệ, quản trị, thông báo và CI; hoàn thành mốc xây dựng để chuyển sang kiểm thử và hoàn thiện. |
| 8 | Thực hiện KH17–KH20: kiểm API, giao diện, vòng đời và chín mẫu; lập danh sách lỗi kèm operation, cấu hình và kết quả quan sát. |
| 9 | Sửa lỗi tích hợp và kiểm thử lại; đối chiếu dữ liệu sau restore, nguồn giữ lại khi lỗi, lịch và tài nguyên; bắt đầu chốt tài liệu và cấu hình. |
| 10 | Hoàn tất KH21–KH24: hồi quy chung, xử lý lỗi ảnh hưởng nghiệm thu, chốt phiên bản repo, hướng dẫn và kịch bản trình diễn để bàn giao. |
