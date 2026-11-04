# Xem CloudFormation template

Trong Môi trường → Chi tiết → Xem CloudFormation template, frontend gọi GET `/environments/{environment_id}/template` khi người dùng bấm. API kiểm JWT/tài khoản/email/owner, lấy Region từ metadata rồi kiểm ARN và tag của stack trước `GetTemplate(Original)`.

Nội dung hiển thị theo allowlist, chỉ đọc; bootstrap, code, môi trường, bí mật, default tham số, metadata/outputs và trường chưa duyệt bị ẩn. Bản lọc không deploy được, không phải live inventory hay drift/health check. Không dựng lại builder để giả template thực tế nếu stack chưa có/đã xóa. Phản hồi no-store; không nhận stack/Region override từ trình duyệt.

Backend `template_view.py`, frontend `template-view.js`, extension IaC/OpenAPI và các test cùng tên là các điểm tích hợp. Bản nguồn có bộ lọc thử trên đủ chín builder; minh chứng đọc AWS thực trước handoff chỉ ở một stack T05 Tokyo có sẵn, không phải chín vòng mới. Không đưa raw template hoặc nội dung đăng nhập lên Git.
