# Giá, tư vấn và sức tải

Giá được thu thập/review theo phiên bản từ AWS Price List, lưu trong cấu hình runtime/SSM hiện có; không gọi Billing để suy ra giá cho mỗi form. Đơn giá origin theo Region; CloudFront theo nhóm edge và PriceClass đang dùng. File giá CloudFront công khai là dữ liệu tham khảo có phiên bản, không phải phê duyệt chi tiêu hoặc giá thời gian thực.

Thiếu giá giữ tổng chưa xác định và subtotal phần đã biết; không biến null thành 0. Quote backend ràng buộc owner/action/template/Region/config/workload/policy/giá/expiry. Chọn phương án tư vấn chỉ điền form, không tự tạo và không tự xác nhận giá mới. Gửi lại lệnh đã nhận phải giữ idempotency key.

Ví cá nhân và ngân sách chung là tín dụng dự toán nội bộ, không phải tiền mặt, AWS credits hoặc hóa đơn. Giữ lịch sử ledger khi xóa môi trường; không coi thu hồi là hoàn mọi chi phí đã phát sinh.

Nhu cầu quy đổi (RPS, lượt xem, lượt truyền, IOPS) khác sức tải đã đo. Không có benchmark ứng dụng phù hợp thì capacity là null. Fixture không được xuất bản thành proof production. Benchmark cần app/image/scenario/config/Region/dataset, tải thực đạt, độ trễ/lỗi/throughput, thời điểm và nguồn chứng cứ. Không dùng p95 API quản lý làm sức tải T01–T09.
