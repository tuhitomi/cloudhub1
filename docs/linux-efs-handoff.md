# Bàn giao nguồn T01 và T08

T01: `templates.py` dựng EC2 + EBS gp3 mã hóa, thẻ môi trường/owner/managed; dữ liệu trong /data. Restore không format lại đĩa đã có snapshot. `aws_driver.py` chứa SDK/state/readiness/backup/cleanup; phụ thuộc catalog, error và các helper của API/runtime.

T08: `efs_template.py`, `efs_driver.py`, `efs_records.py` mô tả EFS, mount/security group, hai máy đọc/ghi và kiểm dữ liệu. Chưa có toàn bộ driver nền trong bản repo TV1 nên không thể coi các file này là một CLI triển khai độc lập.

Sau tích hợp: kiểm account/Region/quota/budget, tag owner, SSH/mount, ghi dữ liệu và SHA; backup; thu hồi đúng nguồn; inventory phần giữ/còn sót; restore sang môi trường mới và đọc lại từ nguồn đích; dọn đúng tài nguyên thử. Không dùng snapshot/stack READY làm bằng chứng dữ liệu đã khôi phục. Không format đĩa nguồn khi chưa rõ nguồn dữ liệu.

Đây là hướng dẫn tiếp quản, không phải log AWS mới hoặc kết quả kiểm thử đã chạy trong đợt nhập mã.
