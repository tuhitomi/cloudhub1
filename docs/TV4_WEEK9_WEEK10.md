# TV4 tuần 9 và tuần 10

Ngày kiểm tra 04/11/2026, Asia/Bangkok UTC+07. Đây là kết quả tích hợp mã và kiểm thử; không xác nhận một đợt triển khai hoặc nghiệm thu AWS mới.

## Phần đã thực hiện

| Hạng mục | Thay đổi | Bằng chứng và giới hạn |
|---|---|---|
| KH13–KH16 | Bổ sung các module TV4 còn thiếu: worker/router/runtime, lifecycle/Scheduler, backup/retention, quản trị và thông báo; giữ nguyên mã và bốn tài liệu do thành viên khác bổ sung | File theo owner TV4; commit mới nối tiếp main, không thay lịch sử của bạn Thái |
| KH20 | Nhánh Worker.fail kiểm lại owner/Region của operation, môi trường và recovery point trước khi sửa metadata hoặc resume nguồn | Ba ca sai scope thất bại trước sửa; sau sửa đều từ chối và giữ nguyên dữ liệu; test_tv4_failure_paths.py |
| KH20 | Hồi quy callback cũ, generation, dispatch lỗi, idempotency, schedule_pending và backup lỗi giữ nguồn | tv4-week9-results.json: 140 test local với support fixture, không gọi AWS |
| KH24 | Tool kiểm dependency, manifest gắn nguồn/test, từ chối kết quả cũ hoặc path không an toàn | test_tv4_release_tools.py; fixture PASS không tạo ready_for_native_review |
| KH24 | Packet yêu cầu mục tiêu account/Region/stack được duyệt; bỏ target production mặc định | prepare_product_0_8_packet.py; chưa tạo/upload packet AWS |
| KH24 | Runbook vận hành, demo, quay lại; CI kiểm release-tool và công bố blocker tích hợp | OPERATIONS_RUNBOOK.md, DEMO_RUNBOOK.md, workflow Local validation |

## Kiểm tra và phạm vi

- Trước sửa: runner TV4 chạy 140 ca, có đúng 3 failure về owner/Region ở nhánh lỗi; không có lỗi hạ tầng test hoặc network attempt.
- Sau sửa tuần 9: 140/140 ca đạt trên LOCAL_SUPPORT_FIXTURE. Có các file API/driver hỗ trợ được sao chép vào thư mục tạm riêng, không commit code của owner khác.
- Cuối tuần 10: kết quả mới nhất trong tv4-week10-results.json; gồm hồi quy trên fixture và các test release-tool. Các hash file hỗ trợ và file TV4 được lưu để đối chiếu; không thay bằng chứng fixture thành AWS.
- Checkout public trực tiếp: các test release-tool và frontend chạy được. Hồi quy TV4 đầy đủ báo BLOCKED_MISSING_DEPENDENCIES khi chưa có API/driver/helper; danh sách thiếu được lưu trong manifest.
- Không chạy AWS, đo tải, đọc Billing/credits hoặc tạo môi trường trong lượt này. Không xác nhận IAM/region gate hoặc chỉ tiêu p95 mới.

## Điều kiện còn chặn

1. TV2/TV3 đưa các module API, store, catalog, estimator, driver và helper test còn thiếu vào repo; chạy lại không dùng --support-source.
2. Review native inventory, operation đang chạy, quota/ledger/giá, Billing/credits và ngân sách hiện tại trước vòng AWS; không dùng số dư trong báo cáo cũ.
3. Review IAM/change set/migration và mục tiêu phát hành, rồi nghiệm thu từng tổ hợp mẫu/profile/Region bằng dữ liệu thật; không mở gate từ một local PASS.
4. Sau native acceptance mới chốt phát hành AWS và các chỉ tiêu đọc API/nhận ID/kích hoạt hết hạn/quét dự phòng. Vì vậy KH20/KH24 có phần code và local review đã thực hiện, nhưng chưa đóng nghiệm thu tích hợp/AWS toàn bộ.

## Tương thích và quay lại

Worker giữ operation ID, generation và schema ledger hiện có. Guard mới làm fail callback sai scope thay vì sửa record/nguồn của người khác. Không migration dữ liệu hoặc thay runtime SSM/gate trong lượt này.

Manifest ghi nguồn working tree và base commit cùng SHA từng file; không phải bản deploy AWS. Chỉ rollback về worker tương thích schema/operation hiện hành sau khi kiểm tác vụ đang chạy, không bỏ guard hoặc reset ledger. Xem runbook để xử lý schedule_pending và nguồn được giữ sau backup lỗi.

## Chốt kiểm tra local

- 149/149 ca thuộc runner TV4 đạt trên LOCAL_SUPPORT_FIXTURE, không bỏ qua ca nào; 196 file hỗ trợ có hash riêng và không đưa vào commit TV4.
- 546/546 test Python của bản nguồn tích hợp tạm đạt; đây là hồi quy rộng hơn cho guard worker dùng chung, gồm các test TV4, không cộng hai con số thành tổng mới. Chỉ cho phép hai kết nối HTTP loopback của fixture tải file; SDK và network bên ngoài bị khóa.
- Chín test release-tool chạy được trực tiếp trên checkout public; 25 test frontend vẫn đạt, đủ tám locale.
- Fingerprint nguồn chuẩn LF giữ manifest ổn định sau Git chuẩn hóa CRLF/LF; checksum dữ liệu người dùng và ZIP vẫn dựa trên byte thật.
- Runner trực tiếp trên repo báo thiếu 53 dependency, chạy 0 test và không PASS. Manifest còn thiếu các nguồn phát hành khác nên ready_for_native_review=false, aws_deployed=false.
- Khôi phục bộ lọc .gitignore cho cấu hình live, giá review riêng, evidence và output; bốn tài liệu kế hoạch do bạn Thái đưa lên được giữ nguyên nội dung. Đã đăng ký owner để checker không lỗi vì file mới chưa được phân công.

Kết quả chi tiết: tv4-week9-results.json, tv4-week10-results.json, tv4-regression-results.json, tv4-native-prerequisites.json và tv4-release-manifest.json.
