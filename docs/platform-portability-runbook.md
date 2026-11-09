# Chuẩn bị nền tảng tại Region khác

Đây là di chuyển **control plane CloudHub**, khác việc chọn Region cho một môi trường T01–T09. Công cụ hiện có tạo packet offline; packet không triển khai hoặc tự cấp ngân sách/quyền. Có thể dùng thời gian bảo trì, không bắt buộc giữ dịch vụ hoạt động liên tục khi chuyển.

## Chuẩn bị offline

Tạo file cấu hình local riêng từ `config/platform-target.example.json`, chọn một trong ba Region được hỗ trợ và điền AMI, VPC/subnet/AZ, phiên bản RDS, image ECR digest và giá riêng của Region đích. Không dùng ID/ARN từ Region nguồn một cách máy móc. Đầu vào chưa hoàn tất được ghi thành blocker.

```sh
python scripts/prepare_platform_target.py --config config/platform-target.local.json --out outputs/target-packet --draft
```

Packet gồm mã, SAM/ASL, cấu hình review và manifest. `--draft` không cho phép apply. Không đưa proof/gate đã mở ở tài khoản cũ vào tài khoản hoặc Region mới mà chưa có kiểm chứng tương ứng.

## Chuyển trong thời gian bảo trì

1. Chủ dự án duyệt account/Region, quyền, tài nguyên, dự toán và cách thu hồi. Đọc lại inventory, ledger/reservation, operations và AWS Billing/credits theo quyền; không dùng số dư báo cáo cũ.
2. Admin công bố bảo trì, chặn nhận lệnh ghi mới theo quy trình vận hành và xử lý các operation/schedule đang chạy. Giữ worker tương thích với dữ liệu hiện có.
3. Dựng nền tảng đích từ packet đã review. IAM, network, backups và AMI/image phải thuộc đúng Region. Chỉ mở phần đã nghiệm thu.
4. Migration DynamoDB/S3 và danh tính Cognito theo kế hoạch riêng có snapshot, checksum, khóa ghi và đối soát. Cognito User Pool không tự chuyển tài khoản/mật khẩu sang Region khác. Không đặt lại ledger hoặc cấp lại ví để vượt gate.
5. Tái sử dụng domain/hosted zone/CloudFront đang được bảo vệ. Chứng chỉ CloudFront ở us-east-1; API certificate và Regional custom domain ở Region API đích. Cập nhật origin, OAC policy, API mapping/DNS và config frontend có kiểm soát; không tạo distribution trùng alias hoặc đổi URL công khai cho người dùng.
6. Kiểm đúng domain, HTTPS/CORS/JWT, đăng nhập, owner/quota/quote, tác vụ và dữ liệu khôi phục. Đối chiếu code/asset SHA và cấu hình thực; stack UPDATE_COMPLETE chưa đủ.
7. Mở nhận lệnh, theo dõi và chỉ thu hồi nền tảng nguồn khi đủ điều kiện. Giữ tài nguyên/bản sao dùng chung đúng chính sách, ghi rõ phần còn tính phí.

## Quay lại và giới hạn

Quay lại cần xét dữ liệu mới, lệnh đã nhận, schema ledger, session/danh tính và upload/publication chưa xác định kết quả ở đích. Đổi DNS ngược chỉ là một bước. Không đưa worker cũ không tương thích vào dữ liệu mới, reset DynamoDB hoặc xóa môi trường người dùng để quay lại mã.

Repo public không chứa snapshot migration, cấu hình production, nguồn DNS đang dùng hay bằng chứng đã chuyển toàn nền tảng. Quyền trên repository không phải quyền AWS. Không tự di chuyển môi trường khách hàng trong bài cấu hình nền tảng này.
