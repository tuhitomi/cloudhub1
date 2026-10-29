# Kiểm thử của đợt nhập TV1

CI chỉ kiểm phần đã có: ownership, cú pháp Python/JS, JSON, tám locale, placeholder và bốn suite Node: i18n, cockpit, shell-view, template-view. `scripts/check_leader_handoff.py` không import driver AWS, không gọi AWS và không sửa kết quả đã lưu trong repository.

Các test còn lại được giữ nguyên mã nhưng chưa chạy độc lập: catalog-view cần quota-view (TV3); create-flow cần create-journal (TV4); create-view cần product-view (TV3); frontend cần portal/auth/quota/notifications; workspace-view cần lifecycle (TV4); content-guard cần content_routing backend (TV2); test_readiness/test_failed_source cần service/store/catalog/router và các driver khác. Chỉ chạy toàn bộ sau khi các owner đưa đủ dependency và kiểm lại kết quả.

`team/handoff-validation.json` ghi thời điểm chạy local thực tế ngày nhập mã. Không chuyển kết quả 531 Python/229 frontend của snapshot đầy đủ cũ thành kết quả của repo chỉ có TV1. Không có vòng AWS hoặc phép đo hiệu năng mới; website đang chạy không bị thay đổi.
