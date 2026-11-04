# Bảo vệ quyền và dữ liệu

Cognito quản lý mật khẩu; backend không tin owner/role/quota do browser tự khai. JWT không thay kiểm quyền sở hữu. Admin phải được kiểm lại qua pool được cấu hình. Quote/ledger/quota/operation dùng conditional transaction và fencing; không tắt các kiểm tra khi thử UI.

Template view, upload, recovery point, operation và môi trường phải kiểm owner riêng. S3 private/OAC, staging grant có hạn/checksum/size/type, đường publish immutable và namespace guard được giữ. Country header chỉ tin tuyến đã kiểm soát; lựa chọn ngôn ngữ không đổi Region hoặc USD.

Repo public không kèm khóa/token/password/private key, cookie, origin protection header, profile/account export, production config hay native snapshot. Cấu hình mẫu dùng giá trị giả hoặc REQUIRED. Mọi quyền chạy AWS và ngân sách phải được cấp riêng, không kế thừa từ việc xem được mã nguồn.
