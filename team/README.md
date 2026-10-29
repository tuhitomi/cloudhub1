# Làm việc trong nhóm

Nhóm trưởng là TV4 — Hoàng Đường Anh Tú. Phân công chi tiết ở TV1.md–TV4.md và FILE_OWNERSHIP.md, theo trách nhiệm của báo cáo v2.

1. Clone main mới nhất vào thư mục riêng; tạo nhánh `team/tv1`, `team/tv2`, `team/tv3` hoặc `team/tv4` cho công việc của mình.
2. Giữ cấu trúc thư mục chuẩn. Review những file đã có; chỉ commit thay đổi thật của phần được giao. Không xóa rồi thêm lại nội dung giống nhau.
3. Chạy kiểm tra phù hợp và ghi rõ phần còn thiếu dependency. Tách unit/mock, browser và AWS; kết quả từ loại này không thay cho loại khác.
4. Mở PR vào main, nêu hành vi, file liên quan, kết quả test và rủi ro dữ liệu/chi phí nếu có. Nhờ owner review khi thay đổi helper dùng chung.
5. Đồng bộ main sau khi đã lưu công việc của mình. Không force push vào main hoặc ghi đè công việc của người khác.

Tên/GitHub chỉ được điền khi đã xác nhận. `members.json` dùng null cho handle chưa rõ; CODEOWNERS và quyền collaborator không tự phát sinh từ bảng owner.

Khi thực hành AWS, dùng quyền đúng nhiệm vụ, không chia sẻ root/access key. Nêu rõ tài nguyên, dữ liệu được bảo vệ, cách đọc lại sau khôi phục và phần có thể còn phát sinh phí. Các giờ trong báo cáo là kế hoạch, không phải nhật ký thực tế.
