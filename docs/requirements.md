# Phạm vi và tiêu chí của phần TV1

CloudHub phục vụ người chưa biết AWS: chọn nhu cầu → mẫu/Region/cấu hình được backend cho phép → xem dự toán → xác nhận → nhận operation ID → theo dõi → truy cập → sao lưu/khôi phục → kết thúc và kiểm kê.

Danh mục T01–T09; không T10 hoặc Local Zones. Tự động gia hạn phải opt-in. Continuous chỉ được cung cấp khi backend/gate có bằng chứng. Region không tự thay khi đổi ngôn ngữ; tiền tệ giữ USD. Quốc gia từ nguồn tin cậy chỉ giúp chọn ngôn ngữ, lựa chọn đã lưu được ưu tiên, tiếng Anh fallback.

TV1 nhận catalog/workspace, wizard bốn bước, trạng thái tác vụ và màn hình dữ liệu; Linux T01/EBS /data; T08 với hai máy dùng EFS. Dự toán/quote/quota/ownership và thao tác dài phải do backend thực thi. File/helper của người khác phải tích hợp đúng hợp đồng, không thay bằng thành công giả.

Nghiệm thu cần kiểm quyền sở hữu, giá/quote thay đổi, request cũ/gửi lại, lịch cũ, backup lỗi giữ nguồn, đúng phạm vi thu hồi và dữ liệu restore thật. Unit/DOM không chứng minh AWS, sức tải hoặc đủ chín vòng đời. Đợt nhập TV1 chưa chạy lại các vòng AWS đó.
