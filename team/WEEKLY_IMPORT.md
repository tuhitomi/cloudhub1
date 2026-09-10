# Lịch nhập mã TV1

Đây là **nhập lại mã đã có**, thực hiện ngày 29/10/2026 (Asia/Bangkok, UTC+07). Theo yêu cầu ngày 30/10/2026, cả AuthorDate và CommitDate được đặt theo tám mốc chủ dự án chọn để lịch repository thể hiện các giai đoạn; khoảng cách giữa các mốc không cố định bảy ngày. Các timestamp này là mốc giai đoạn, không phải thời điểm Git thực sự tạo commit. Lần nhập nguồn diễn ra ngày 29/10/2026; lần viết lại metadata diễn ra ngày 30/10/2026. Các mốc không khẳng định tác giả đã thực hiện công việc, chạy test hoặc triển khai AWS vào những tuần đó. Chỉ TV1 được đưa mã lên trong đợt này; các thành viên khác tự commit phần của mình.

| Giai đoạn | AuthorDate và CommitDate yêu cầu | Nhóm nội dung nhập |
|---|---|---|
| 1 | 2026-09-10 | Scope, architecture and responsibility handoff |
| 2 | 2026-09-18 | Repository tooling and Linux EC2/EBS source |
| 3 | 2026-09-23 | Catalog presentation, appearance and eight locales |
| 4 | 2026-10-02 | Creation wizard and management integration source |
| 5 | 2026-10-09 | Workspace dashboard and service cockpit source |
| 6 | 2026-10-14 | Maintenance presentation and read-only template UI |
| 7 | 2026-10-24 | EFS shared-storage template and driver source |
| 8 | 2026-10-29 | Scoped local tests, CI and integration handoff |

Thứ tự dựa trên đầu việc kế hoạch: A01 yêu cầu; A02 repository/CI; A05 frontend; A10 Linux (tuần 2); A18 EFS (tuần 7); phần bắt đầu A22.1/A23.1 ở tuần 8. Mã frontend được chia theo thành phần hiện tại; không có snapshot lịch sử từng tuần để khẳng định đó là mã thực có vào ngày AuthorDate. Không nhập công việc A24 tuần 9 hoặc nhận đủ giờ kế hoạch.

Ngày tác giả không thay thế log AWS, PR/review hay nhật ký công việc. Các file hiện tại vẫn có chức năng đã phát triển sau những mốc kế hoạch; không cắt sửa để dựng một lịch sử triển khai giả.

Repo ở trạng thái tích hợp từng phần: CI chỉ kiểm các dependency đã có và công bố test đang chờ. Không có triển khai AWS hoặc thay đổi website từ đợt Git này. Tài liệu `FILE_OWNERSHIP.md` liệt kê cả file còn chờ TV2–TV4, không phải danh sách mọi file đã hiện diện.
