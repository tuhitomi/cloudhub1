# TV1 — Đào Quang Thái

Giao diện và trải nghiệm trình duyệt.

Kiến trúc phụ trách: M1; D01.

## Công việc

| Mã | Kế hoạch trong báo cáo | Đầu ra |
|---|---|---|
| KH01 | 1–2Hoàn thành | Xây dựng khung giao diện, điều hướng, danh mục và các màn hình tài khoản; kết quả là luồng đăng ký, xác minh, đăng nhập và đăng xuất trên web. |
| KH02 | 3–4Hoàn thành | Xây dựng form chọn mẫu, profile, Region, thời hạn và chính sách; hiển thị tư vấn, dự toán và xác nhận trước khi gửi lệnh tạo. |
| KH03 | 5–6Hoàn thành | Xây dựng dashboard, chi tiết môi trường, tiến trình operation và danh sách bản sao; tích hợp gia hạn, kết thúc, sao lưu, khôi phục và thao tác tệp. |
| KH04 | 6–7Hoàn thành | Tích hợp màn hình publish, rollback, đổi ứng dụng, quản trị và thông báo; bổ sung locale, giao diện sáng tối và hiển thị lỗi theo hợp đồng API. |
| KH17 | 8–9Kế hoạch | Kiểm thử đầu cuối trên trình duyệt: tạo, gia hạn, backup/restore, tệp và publish; kiểm reload, quote hết hạn, lỗi mạng, locale và màn hình quản trị. |
| KH21 | 9–10Kế hoạch | Sửa các lỗi giao diện còn lại, thống nhất hướng dẫn sử dụng và thông báo; chạy lại kịch bản trình diễn bằng tài khoản người dùng và quản trị. |

## File phụ trách

Owner chịu trách nhiệm tích hợp và review. File chưa có trên nhánh hiện tại cần được bổ sung trước khi chạy luồng liên quan; không coi danh sách này là kết quả kiểm thử.

| File | Công việc |
|---|---|
| `frontend/admin-directory-view.js` | KH04 |
| `frontend/announcements.js` | KH04 |
| `frontend/app.js` | KH04 |
| `frontend/appearance.js` | KH04 |
| `frontend/architecture.js` | KH02 |
| `frontend/auth.js` | KH01 |
| `frontend/catalog-text.js` | KH02 |
| `frontend/catalog-view.js` | KH02 |
| `frontend/cockpit.js` | KH03 |
| `frontend/config.example.js` | KH01 |
| `frontend/create-flow.js` | KH02 |
| `frontend/create-journal.js` | KH03 |
| `frontend/create-view.js` | KH02 |
| `frontend/error-text.js` | KH04 |
| `frontend/i18n.js` | KH04 |
| `frontend/index.html` | KH01 |
| `frontend/lifecycle.js` | KH03 |
| `frontend/locale-en.js` | KH04 |
| `frontend/locale-source.js` | KH04 |
| `frontend/locales/de.json` | KH04 |
| `frontend/locales/en.json` | KH04 |
| `frontend/locales/es.json` | KH04 |
| `frontend/locales/fr.json` | KH04 |
| `frontend/locales/ja.json` | KH04 |
| `frontend/locales/ko.json` | KH04 |
| `frontend/locales/vi.json` | KH04 |
| `frontend/locales/zh-Hans.json` | KH04 |
| `frontend/maintenance-banner.js` | KH04 |
| `frontend/maintenance-page.js` | KH04 |
| `frontend/maintenance.css` | KH04 |
| `frontend/maintenance.html` | KH04 |
| `frontend/notifications.js` | KH04 |
| `frontend/pages-preview.js` | KH01 |
| `frontend/portal.js` | KH03 |
| `frontend/presentation-data.js` | KH03 |
| `frontend/product-view.js` | KH02 |
| `frontend/public-preview.js` | KH02 |
| `frontend/quota-view.js` | KH02 |
| `frontend/recommendations.js` | KH02 |
| `frontend/redesign.css` | KH01 |
| `frontend/session.js` | KH01 |
| `frontend/shell-view.js` | KH03 |
| `frontend/style.css` | KH01 |
| `frontend/template-view.js` | KH04 |
| `frontend/test-data-view.js` | KH04 |
| `frontend/uploads.js` | KH04 |
| `frontend/workspace-ui.js` | KH03 |
| `frontend/workspace-view.js` | KH03 |
| `frontend/workspace.css` | KH03 |
| `package-lock.json` | KH01 |
| `package.json` | KH01 |
| `scripts/configure_frontend.py` | KH01 |
| `scripts/public_assets.py` | KH01 |
| `scripts/ui_fixture.py` | KH01 |
| `scripts/validate_locales.py` | KH04 |
| `tests/admin-directory-view.test.mjs` | KH17 |
| `tests/announcements.test.mjs` | KH17 |
| `tests/auth.test.mjs` | KH17 |
| `tests/catalog-view.test.mjs` | KH17 |
| `tests/cockpit.test.mjs` | KH17 |
| `tests/create-flow.test.mjs` | KH17 |
| `tests/create-view.test.mjs` | KH17 |
| `tests/frontend.test.mjs` | KH17 |
| `tests/guest-experience.test.mjs` | KH17 |
| `tests/i18n.test.mjs` | KH17 |
| `tests/lifecycle.test.mjs` | KH17 |
| `tests/notifications.test.mjs` | KH17 |
| `tests/presentation-data.test.mjs` | KH17 |
| `tests/product-view.test.mjs` | KH17 |
| `tests/recommendations.test.mjs` | KH17 |
| `tests/session.test.mjs` | KH17 |
| `tests/shell-view.test.mjs` | KH17 |
| `tests/template-view.test.mjs` | KH17 |
| `tests/test-data-view.test.mjs` | KH17 |
| `tests/uploads.test.mjs` | KH17 |
| `tests/wallets.test.mjs` | KH17 |
| `tests/workspace-view.test.mjs` | KH17 |
