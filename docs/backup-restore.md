# Dữ liệu, bản sao và kết thúc

| Mẫu | Phạm vi dữ liệu chính |
|---|---|
| T01/T05 | EBS /data, không gồm root/RAM hoặc dữ liệu ngoài phạm vi đăng ký |
| T02/T07 | Nội dung S3 được quản lý và manifest/checksum theo gói |
| T03/T04 | RDS PostgreSQL và dữ liệu ứng dụng được khai báo; không tự bảo vệ toàn root EC2/log |
| T06 | S3 đã đăng ký làm dữ liệu bền vững, không gồm filesystem tạm container/RAM/image |
| T08 | Dữ liệu EFS trong phạm vi bộ xử lý |
| T09 | Dữ liệu DynamoDB do môi trường quản lý |

Khôi phục tạo môi trường mới, đi qua quote/quota/owner và kiểm đúng Region/config. Stack/snapshot sẵn sàng không đồng nghĩa dữ liệu đã xác minh; cần đọc lại/checksum. Sao lưu bắt buộc lỗi phải giữ nguồn và báo lỗi, không tiếp tục xóa.

Thu hồi phân biệt deleted/retained/residual/unknown/billable và thời điểm/phạm vi kiểm kê. Ẩn môi trường test không xóa tài nguyên hoặc lịch sử chi phí. Bản sao/log/đĩa giữ lại có thể tiếp tục tính phí. Các thao tác quản trị và kiểm thử lỗi chỉ trên fixture hoặc nguồn đã được cho phép.
