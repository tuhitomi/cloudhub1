# TV2 — Ngô Quang Dũng

API, xác thực, metadata, quota, dự toán, quote, ví và ledger.

Kiến trúc phụ trách: M2–M4; D02–D05, D14.

## Công việc

| Mã | Kế hoạch trong báo cáo | Đầu ra |
|---|---|---|
| KH05 | 1–2Hoàn thành | Xây dựng hợp đồng HTTP, tích hợp JWT Cognito và kiểm owner/admin tại backend; kết quả là API tài khoản và cơ chế phân quyền đối tượng. |
| KH06 | 3–4Hoàn thành | Xây dựng metadata, version, khóa, quota và Idempotency-Key; tiếp nhận lệnh bằng giao dịch có điều kiện và trả operation để theo dõi. |
| KH07 | 5–6Hoàn thành | Xây dựng estimator, quote, reservation, ví và ledger; kiểm ngân sách cá nhân và nền tảng, giá theo Region và số liệu chi phí tùy chọn. |
| KH08 | 6–7Hoàn thành | Tích hợp capability, tư vấn và API thao tác tệp, bản ghi, xuất bản, ứng dụng; kết quả là hợp đồng API thống nhất với frontend và worker. |
| KH18 | 8–9Kế hoạch | Kiểm thử API và giao dịch đồng thời: owner chéo, replay, quote dùng lại, thiếu giá, vượt quota/ngân sách và xung đột version; sửa lỗi nghiệp vụ phát hiện được. |
| KH22 | 9–10Kế hoạch | Chốt OpenAPI và cấu trúc lỗi; rà soát cấu hình giá, quota, ví và dữ liệu trả về; sửa lỗi API, kiểm tra hồi quy và hướng dẫn cấu hình backend. |

## File phụ trách

Owner chịu trách nhiệm tích hợp và review. File chưa có trên nhánh hiện tại cần được bổ sung trước khi chạy luồng liên quan; không coi danh sách này là kết quả kiểm thử.

| File | Công việc |
|---|---|
| `backend/cloudhub/__init__.py` | KH05 |
| `backend/cloudhub/access.py` | KH05 |
| `backend/cloudhub/accounts.py` | KH05 |
| `backend/cloudhub/actual_cost.py` | KH07 |
| `backend/cloudhub/api.py` | KH05 |
| `backend/cloudhub/applications.py` | KH08 |
| `backend/cloudhub/benchmark-scenarios.json` | KH08 |
| `backend/cloudhub/benchmarks.py` | KH08 |
| `backend/cloudhub/catalog.py` | KH08 |
| `backend/cloudhub/cost.py` | KH07 |
| `backend/cloudhub/errors.py` | KH05 |
| `backend/cloudhub/ledger.py` | KH07 |
| `backend/cloudhub/public_catalog.py` | KH08 |
| `backend/cloudhub/quotes.py` | KH07 |
| `backend/cloudhub/recommendations.py` | KH08 |
| `backend/cloudhub/regions.py` | KH08 |
| `backend/cloudhub/registration.py` | KH05 |
| `backend/cloudhub/releases.py` | KH08 |
| `backend/cloudhub/s3_files.py` | KH08 |
| `backend/cloudhub/service.py` | KH06 |
| `backend/cloudhub/store.py` | KH06 |
| `backend/cloudhub/template_view.py` | KH08 |
| `backend/cloudhub/ui_context.py` | KH08 |
| `backend/cloudhub/uploads.py` | KH08 |
| `backend/cloudhub/viewer_prices.py` | KH07 |
| `backend/cloudhub/wallet.py` | KH07 |
| `backend/cloudhub/workload_cost.py` | KH07 |
| `backend/cloudhub/workloads.py` | KH07 |
| `config/application-releases.example.json` | KH08 |
| `config/cloudfront-viewer-prices.review.json` | KH07 |
| `config/prices.example.json` | KH07 |
| `config/recommendation-policy.example.json` | KH08 |
| `docs/openapi.json` | KH22 |
| `docs/pricing-and-capacity.md` | KH07 |
| `docs/security.md` | KH05 |
| `docs/template-view.md` | KH08 |
| `scripts/access_token.py` | KH05 |
| `scripts/admin_directory_openapi.py` | KH08 |
| `scripts/announcement_openapi.py` | KH08 |
| `scripts/benchmark_evidence.py` | KH08 |
| `scripts/cloudfront_viewer_prices.py` | KH07 |
| `scripts/cognito_messages.py` | KH05 |
| `scripts/generate_benchmark_scenarios.py` | KH08 |
| `scripts/generate_openapi.py` | KH08 |
| `scripts/lifecycle_openapi.py` | KH08 |
| `scripts/migrate_account_wallets.py` | KH07 |
| `scripts/migrate_forecast_ledger.py` | KH07 |
| `scripts/migrate_regions.py` | KH08 |
| `scripts/notification_openapi.py` | KH08 |
| `scripts/portal_openapi.py` | KH08 |
| `scripts/product_completion_openapi.py` | KH08 |
| `scripts/product_experience_openapi.py` | KH08 |
| `scripts/public_catalog_openapi.py` | KH08 |
| `scripts/recommendation_openapi.py` | KH08 |
| `scripts/refresh_prices.py` | KH07 |
| `scripts/region_i18n_openapi.py` | KH08 |
| `scripts/template_view_openapi.py` | KH08 |
| `scripts/test_visibility_openapi.py` | KH08 |
| `scripts/wallet_openapi.py` | KH08 |
| `tests/fixtures/recommendation-contract.json` | KH18 |
| `tests/test_applications.py` | KH18 |
| `tests/test_cognito_messages.py` | KH18 |
| `tests/test_configuration_choices.py` | KH18 |
| `tests/test_direct_uploads.py` | KH18 |
| `tests/test_domain.py` | KH18 |
| `tests/test_forecast_ledger.py` | KH18 |
| `tests/test_lifecycle_api.py` | KH18 |
| `tests/test_product_ux.py` | KH18 |
| `tests/test_public_catalog.py` | KH18 |
| `tests/test_quotes_continuous.py` | KH18 |
| `tests/test_recommendation_release.py` | KH18 |
| `tests/test_recommendations.py` | KH18 |
| `tests/test_region_shards.py` | KH18 |
| `tests/test_regions.py` | KH18 |
| `tests/test_registration.py` | KH18 |
| `tests/test_review_fixes.py` | KH18 |
| `tests/test_template_view.py` | KH18 |
| `tests/test_termination_review.py` | KH18 |
| `tests/test_wallet_migration.py` | KH18 |
| `tests/test_wallets.py` | KH18 |
| `tests/test_website_releases.py` | KH18 |
