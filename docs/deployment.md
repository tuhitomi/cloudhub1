# Triển khai và cấu hình

Repo này không gắn secrets GitHub/AWS và CI chỉ kiểm local. Không chạy script apply/migration/lifecycle bằng tài khoản production khi chưa có cấu hình, kiểm ngân sách và quyền cho đúng tài nguyên.

1. Tạo môi trường Python/Node và chạy các kiểm tra ở README.
2. Tạo file cấu hình local từ `config/deployment.example.json`, `prices.example.json`, `hosting.example.json` hoặc `platform-target.example.json`. Điền account/Region/network/image/domain/giá đã được operator kiểm; không đưa bí mật vào Git.
3. Chạy generator offline như `scripts/generate_infra.py`, `generate_network.py`, `generate_openapi.py`. Với nền tảng đã tồn tại, đọc native template đầy đủ, đối chiếu tài nguyên và chuẩn bị change set chọn lọc; không thay wholesale bằng template mẫu.
4. Đọc danh tính, quota, ledger, inventory và Billing/credits hiện tại. Dự toán nội bộ không phải hóa đơn hay cam kết về số dư AWS.
5. Review IAM/action/resource/condition, tài nguyên sẽ tạo, giới hạn thử và cách dọn; triển khai trong phạm vi được duyệt. Không bật gate chỉ vì unit test đạt.
6. Chờ dịch vụ sẵn sàng, đối chiếu artifact SHA/cấu hình/HTTPS/JWT và dữ liệu thực, rồi mới mở đúng tổ hợp đã nghiệm thu.

Tên miền: dùng Route 53/ACM/CloudFront và Regional custom API theo module hosting hiện có. ACM frontend ở us-east-1, API certificate ở Region API. Không mua domain hoặc sửa nameserver từ ví dụ. Khi chuyển Region phải có kế hoạch danh tính, dữ liệu, tác vụ đang chạy, DNS và quay lại; đổi DNS ngược không phải rollback dữ liệu hoàn chỉnh.

Quay lại mã phải giữ schema ledger, operation ID/generation, upload/publication chưa rõ kết quả và worker tương thích. Không reset DynamoDB, tự hoàn ledger hoặc xóa môi trường người dùng để rollback. Chi tiết triển khai production và snapshot riêng nằm ở repo private của chủ dự án.
