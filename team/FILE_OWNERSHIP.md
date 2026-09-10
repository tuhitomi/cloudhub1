# Phân công tới từng file

Bảng này gồm danh mục nguồn đầy đủ và phần còn chờ các thành viên tự đưa lên. Hiện chỉ phần TV1 đã được nhập. Owner là trách nhiệm tiếp quản/review, không phải chứng nhận tác giả hoặc giờ công.

| File | Owner | Trạng thái trong đợt TV1 | Trách nhiệm |
|---|---|---|---|
| `.gitattributes` | TV1 | Có trong đợt nhập TV1 | Repository, dependencies và CI |
| `.github/CODEOWNERS.example` | TV1 | Có trong đợt nhập TV1 | Điều phối repository và bảng phân công |
| `.github/workflows/ci.yml` | TV1 | Có trong đợt nhập TV1 | Repository, dependencies và CI |
| `.gitignore` | TV1 | Có trong đợt nhập TV1 | Repository, dependencies và CI |
| `README.md` | TV1 | Có trong đợt nhập TV1 | Điều phối repository và bảng phân công |
| `backend/cloudhub/__init__.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/access.py` | TV2 | Chờ owner tự commit | Auth/admin, file/hosting, Region và quyền đọc stack |
| `backend/cloudhub/accounts.py` | TV2 | Chờ owner tự commit | Auth/admin, file/hosting, Region và quyền đọc stack |
| `backend/cloudhub/actual_cost.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/admin_directory.py` | TV2 | Chờ owner tự commit | Auth/admin, file/hosting, Region và quyền đọc stack |
| `backend/cloudhub/announcements.py` | TV2 | Chờ owner tự commit | Auth/admin, file/hosting, Region và quyền đọc stack |
| `backend/cloudhub/api.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/application_driver.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/applications.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/archive.py` | TV4 | Chờ owner tự commit | Vận hành/thu hồi/Docker; module cũ không thuộc danh mục hoạt động |
| `backend/cloudhub/aws_driver.py` | TV1 | Có trong đợt nhập TV1 | Linux/EC2/EBS và EFS T01/T08 |
| `backend/cloudhub/backup_export.py` | TV4 | Chờ owner tự commit | Vận hành/thu hồi/Docker; module cũ không thuộc danh mục hoạt động |
| `backend/cloudhub/benchmark-scenarios.json` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/benchmark_agent.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/benchmarks.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/catalog.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/cf_common.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/container_app.py` | TV4 | Chờ owner tự commit | Vận hành/thu hồi/Docker; module cũ không thuộc danh mục hoạt động |
| `backend/cloudhub/content_app.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/content_routing.py` | TV2 | Chờ owner tự commit | Auth/admin, file/hosting, Region và quyền đọc stack |
| `backend/cloudhub/cost.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/data_api_app.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/data_driver.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/data_template.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/driver_router.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/ecs_driver.py` | TV4 | Chờ owner tự commit | Vận hành/thu hồi/Docker; module cũ không thuộc danh mục hoạt động |
| `backend/cloudhub/ecs_template.py` | TV4 | Chờ owner tự commit | Vận hành/thu hồi/Docker; module cũ không thuộc danh mục hoạt động |
| `backend/cloudhub/efs_driver.py` | TV1 | Có trong đợt nhập TV1 | Linux/EC2/EBS và EFS T01/T08 |
| `backend/cloudhub/efs_records.py` | TV1 | Có trong đợt nhập TV1 | Linux/EC2/EBS và EFS T01/T08 |
| `backend/cloudhub/efs_template.py` | TV1 | Có trong đợt nhập TV1 | Linux/EC2/EBS và EFS T01/T08 |
| `backend/cloudhub/errors.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/ledger.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/lifecycle.py` | TV4 | Chờ owner tự commit | Vận hành/thu hồi/Docker; module cũ không thuộc danh mục hoạt động |
| `backend/cloudhub/lifecycle_scheduler.py` | TV4 | Chờ owner tự commit | Vận hành/thu hồi/Docker; module cũ không thuộc danh mục hoạt động |
| `backend/cloudhub/notification_email.py` | TV2 | Chờ owner tự commit | Auth/admin, file/hosting, Region và quyền đọc stack |
| `backend/cloudhub/notifications.py` | TV2 | Chờ owner tự commit | Auth/admin, file/hosting, Region và quyền đọc stack |
| `backend/cloudhub/operating_policy.py` | TV4 | Chờ owner tự commit | Vận hành/thu hồi/Docker; module cũ không thuộc danh mục hoạt động |
| `backend/cloudhub/portal.py` | TV2 | Chờ owner tự commit | Auth/admin, file/hosting, Region và quyền đọc stack |
| `backend/cloudhub/portal_api.py` | TV2 | Chờ owner tự commit | Auth/admin, file/hosting, Region và quyền đọc stack |
| `backend/cloudhub/public_catalog.py` | TV2 | Chờ owner tự commit | Auth/admin, file/hosting, Region và quyền đọc stack |
| `backend/cloudhub/quotes.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/rds_app.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/rds_driver.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/rds_template.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/recommendations.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/recovery_actions.py` | TV4 | Chờ owner tự commit | Vận hành/thu hồi/Docker; module cũ không thuộc danh mục hoạt động |
| `backend/cloudhub/redshift_driver.py` | TV4 | Chờ owner tự commit | Vận hành/thu hồi/Docker; module cũ không thuộc danh mục hoạt động |
| `backend/cloudhub/redshift_template.py` | TV4 | Chờ owner tự commit | Vận hành/thu hồi/Docker; module cũ không thuộc danh mục hoạt động |
| `backend/cloudhub/regions.py` | TV2 | Chờ owner tự commit | Auth/admin, file/hosting, Region và quyền đọc stack |
| `backend/cloudhub/registration.py` | TV2 | Chờ owner tự commit | Auth/admin, file/hosting, Region và quyền đọc stack |
| `backend/cloudhub/releases.py` | TV2 | Chờ owner tự commit | Auth/admin, file/hosting, Region và quyền đọc stack |
| `backend/cloudhub/runtime.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/s3_driver.py` | TV2 | Chờ owner tự commit | Auth/admin, file/hosting, Region và quyền đọc stack |
| `backend/cloudhub/s3_files.py` | TV2 | Chờ owner tự commit | Auth/admin, file/hosting, Region và quyền đọc stack |
| `backend/cloudhub/s3_template.py` | TV2 | Chờ owner tự commit | Auth/admin, file/hosting, Region và quyền đọc stack |
| `backend/cloudhub/service.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/stack_driver.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/store.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/template_view.py` | TV2 | Chờ owner tự commit | Auth/admin, file/hosting, Region và quyền đọc stack |
| `backend/cloudhub/templates.py` | TV1 | Có trong đợt nhập TV1 | Linux/EC2/EBS và EFS T01/T08 |
| `backend/cloudhub/test_visibility.py` | TV2 | Chờ owner tự commit | Auth/admin, file/hosting, Region và quyền đọc stack |
| `backend/cloudhub/ui_context.py` | TV2 | Chờ owner tự commit | Auth/admin, file/hosting, Region và quyền đọc stack |
| `backend/cloudhub/uploads.py` | TV2 | Chờ owner tự commit | Auth/admin, file/hosting, Region và quyền đọc stack |
| `backend/cloudhub/viewer_prices.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/wallet.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/worker.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/workload_cost.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/cloudhub/workloads.py` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `backend/requirements.txt` | TV3 | Chờ owner tự commit | API, dữ liệu, workflow adapter, quote/ledger, tư vấn và ứng dụng T03/T09 |
| `benchmarks/http.js` | TV4 | Chờ owner tự commit | Công cụ đo tải và kiểm giới hạn |
| `config/application-releases.example.json` | TV3 | Chờ owner tự commit | Cấu hình giá, ứng dụng và tư vấn |
| `config/cloudfront-viewer-prices.review.json` | TV3 | Chờ owner tự commit | Cấu hình giá, ứng dụng và tư vấn |
| `config/deployment.example.json` | TV2 | Chờ owner tự commit | Cấu hình triển khai/hosting/Region mẫu |
| `config/hosting.example.json` | TV2 | Chờ owner tự commit | Cấu hình triển khai/hosting/Region mẫu |
| `config/hosting.readiness.example.json` | TV2 | Chờ owner tự commit | Cấu hình triển khai/hosting/Region mẫu |
| `config/platform-target.example.json` | TV2 | Chờ owner tự commit | Cấu hình triển khai/hosting/Region mẫu |
| `config/prices.example.json` | TV3 | Chờ owner tự commit | Cấu hình giá, ứng dụng và tư vấn |
| `config/product-release.example.json` | TV2 | Chờ owner tự commit | Cấu hình triển khai/hosting/Region mẫu |
| `config/recommendation-policy.example.json` | TV3 | Chờ owner tự commit | Cấu hình giá, ứng dụng và tư vấn |
| `config/regions.example.json` | TV2 | Chờ owner tự commit | Cấu hình triển khai/hosting/Region mẫu |
| `docs/architecture.md` | TV1 | Có trong đợt nhập TV1 | Tài liệu tích hợp và kiểm thử |
| `docs/backup-restore.md` | TV4 | Chờ owner tự commit | Tài liệu bảo vệ dữ liệu và thu hồi |
| `docs/deployment.md` | TV2 | Chờ owner tự commit | Tài liệu triển khai và an toàn AWS |
| `docs/local-check-results.json` | TV3 | Chờ owner tự commit | Tài liệu sản phẩm, API, giá và giới hạn |
| `docs/openapi.json` | TV3 | Chờ owner tự commit | Tài liệu sản phẩm, API, giá và giới hạn |
| `docs/platform-portability-runbook.md` | TV2 | Chờ owner tự commit | Runbook chuyển nền tảng, Region, hosting và IAM |
| `docs/pricing-and-capacity.md` | TV3 | Chờ owner tự commit | Tài liệu sản phẩm, API, giá và giới hạn |
| `docs/product-scope.md` | TV3 | Chờ owner tự commit | Tài liệu sản phẩm, API, giá và giới hạn |
| `docs/security.md` | TV2 | Chờ owner tự commit | Tài liệu triển khai và an toàn AWS |
| `docs/template-view.md` | TV2 | Chờ owner tự commit | Tài liệu triển khai và an toàn AWS |
| `docs/testing.md` | TV1 | Có trong đợt nhập TV1 | Tài liệu tích hợp và kiểm thử |
| `frontend/admin-directory-view.js` | TV2 | Chờ owner tự commit | UI tích hợp auth, hosting, quản trị hoặc S3 |
| `frontend/announcements.js` | TV2 | Chờ owner tự commit | UI tích hợp auth, hosting, quản trị hoặc S3 |
| `frontend/app.js` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/appearance.js` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/architecture.js` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/auth.js` | TV2 | Chờ owner tự commit | UI tích hợp auth, hosting, quản trị hoặc S3 |
| `frontend/catalog-text.js` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/catalog-view.js` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/cockpit.js` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/config.example.js` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/create-flow.js` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/create-journal.js` | TV4 | Chờ owner tự commit | UI trạng thái, vòng đời và idempotency |
| `frontend/create-view.js` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/error-text.js` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/i18n.js` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/index.html` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/lifecycle.js` | TV4 | Chờ owner tự commit | UI trạng thái, vòng đời và idempotency |
| `frontend/locale-en.js` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/locale-source.js` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/locales/de.json` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/locales/en.json` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/locales/es.json` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/locales/fr.json` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/locales/ja.json` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/locales/ko.json` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/locales/vi.json` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/locales/zh-Hans.json` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/maintenance-banner.js` | TV2 | Chờ owner tự commit | UI tích hợp auth, hosting, quản trị hoặc S3 |
| `frontend/maintenance-page.js` | TV2 | Chờ owner tự commit | UI tích hợp auth, hosting, quản trị hoặc S3 |
| `frontend/maintenance.css` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/maintenance.html` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/notifications.js` | TV2 | Chờ owner tự commit | UI tích hợp auth, hosting, quản trị hoặc S3 |
| `frontend/pages-preview.js` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/portal.js` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/presentation-data.js` | TV4 | Chờ owner tự commit | UI trạng thái, vòng đời và idempotency |
| `frontend/product-view.js` | TV3 | Chờ owner tự commit | UI tích hợp dự toán, dữ liệu và tư vấn |
| `frontend/public-preview.js` | TV2 | Chờ owner tự commit | UI tích hợp auth, hosting, quản trị hoặc S3 |
| `frontend/quota-view.js` | TV3 | Chờ owner tự commit | UI tích hợp dự toán, dữ liệu và tư vấn |
| `frontend/recommendations.js` | TV3 | Chờ owner tự commit | UI tích hợp dự toán, dữ liệu và tư vấn |
| `frontend/redesign.css` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/session.js` | TV2 | Chờ owner tự commit | UI tích hợp auth, hosting, quản trị hoặc S3 |
| `frontend/shell-view.js` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/style.css` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/template-view.js` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/test-data-view.js` | TV2 | Chờ owner tự commit | UI tích hợp auth, hosting, quản trị hoặc S3 |
| `frontend/uploads.js` | TV2 | Chờ owner tự commit | UI tích hợp auth, hosting, quản trị hoặc S3 |
| `frontend/workspace-ui.js` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/workspace-view.js` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `frontend/workspace.css` | TV1 | Có trong đợt nhập TV1 | Workspace, trải nghiệm, i18n và template-view UI |
| `infra/container/Dockerfile` | TV2 | Chờ owner tự commit | IaC nền, networking, hosting và IAM |
| `infra/control-plane.json` | TV2 | Chờ owner tự commit | IaC nền, networking, hosting và IAM |
| `infra/hosting/api-domain.example.json` | TV2 | Chờ owner tự commit | IaC nền, networking, hosting và IAM |
| `infra/hosting/certificate-api.example.json` | TV2 | Chờ owner tự commit | IaC nền, networking, hosting và IAM |
| `infra/hosting/certificate-frontend.example.json` | TV2 | Chờ owner tự commit | IaC nền, networking, hosting và IAM |
| `infra/hosting/edge-domain.example.json` | TV2 | Chờ owner tự commit | IaC nền, networking, hosting và IAM |
| `infra/hosting/edge-import.example.json` | TV2 | Chờ owner tự commit | IaC nền, networking, hosting và IAM |
| `infra/hosting/public-zone.example.json` | TV2 | Chờ owner tự commit | IaC nền, networking, hosting và IAM |
| `infra/hosting/shared-routing.example.json` | TV2 | Chờ owner tự commit | IaC nền, networking, hosting và IAM |
| `infra/lifecycle.asl.json` | TV4 | Chờ owner tự commit | Step Functions và trạng thái vòng đời |
| `infra/network.json` | TV2 | Chờ owner tự commit | IaC nền, networking, hosting và IAM |
| `package-lock.json` | TV1 | Có trong đợt nhập TV1 | Repository, dependencies và CI |
| `package.json` | TV1 | Có trong đợt nhập TV1 | Repository, dependencies và CI |
| `requirements-dev.txt` | TV1 | Có trong đợt nhập TV1 | Repository, dependencies và CI |
| `scripts/access_token.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/admin_directory_openapi.py` | TV3 | Chờ owner tự commit | Contract API, dự toán và dữ liệu chứng cứ |
| `scripts/announcement_infra.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/announcement_openapi.py` | TV3 | Chờ owner tự commit | Contract API, dự toán và dữ liệu chứng cứ |
| `scripts/archive_test_data.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/aws_lifecycle.py` | TV4 | Chờ owner tự commit | Kiểm vòng đời, hiệu năng và thu hồi |
| `scripts/benchmark.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/benchmark_evidence.py` | TV3 | Chờ owner tự commit | Contract API, dự toán và dữ liệu chứng cứ |
| `scripts/benchmark_workloads.py` | TV4 | Chờ owner tự commit | Kiểm vòng đời, hiệu năng và thu hồi |
| `scripts/build_pages_live.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/build_pages_preview.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/check.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/check_product_release.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/check_t02_publication.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/check_team_ownership.py` | TV1 | Có trong đợt nhập TV1 | Tooling bàn giao/CI/UI |
| `scripts/cloudfront_viewer_prices.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/cognito_messages.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/configure_frontend.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/generate_benchmark_scenarios.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/generate_codeowners.py` | TV1 | Có trong đợt nhập TV1 | Tooling bàn giao/CI/UI |
| `scripts/generate_hosting_examples.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/generate_infra.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/generate_network.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/generate_openapi.py` | TV3 | Chờ owner tự commit | Contract API, dự toán và dữ liệu chứng cứ |
| `scripts/hosting.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/hosting_aws.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/hosting_changeset.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/hosting_upload_cors.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/infra_extensions.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/lifecycle_http.py` | TV4 | Chờ owner tự commit | Kiểm vòng đời, hiệu năng và thu hồi |
| `scripts/lifecycle_openapi.py` | TV3 | Chờ owner tự commit | Contract API, dự toán và dữ liệu chứng cứ |
| `scripts/measure_expiry.py` | TV4 | Chờ owner tự commit | Kiểm vòng đời, hiệu năng và thu hồi |
| `scripts/measure_product_local.py` | TV4 | Chờ owner tự commit | Kiểm vòng đời, hiệu năng và thu hồi |
| `scripts/migrate_account_wallets.py` | TV3 | Chờ owner tự commit | Contract API, dự toán và dữ liệu chứng cứ |
| `scripts/migrate_forecast_ledger.py` | TV3 | Chờ owner tự commit | Contract API, dự toán và dữ liệu chứng cứ |
| `scripts/migrate_regions.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/notification_infra.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/notification_openapi.py` | TV3 | Chờ owner tự commit | Contract API, dự toán và dữ liệu chứng cứ |
| `scripts/package_console.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/portal_infra.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/portal_openapi.py` | TV3 | Chờ owner tự commit | Contract API, dự toán và dữ liệu chứng cứ |
| `scripts/preflight.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/prepare_deployment.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/prepare_hosting.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/prepare_hosting_cutover.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/prepare_platform_target.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/prepare_product_0_8_packet.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/prepare_product_release.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/prepare_recommendations_release.py` | TV3 | Chờ owner tự commit | Contract API, dự toán và dữ liệu chứng cứ |
| `scripts/prepare_review.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/product_completion_infra.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/product_completion_openapi.py` | TV3 | Chờ owner tự commit | Contract API, dự toán và dữ liệu chứng cứ |
| `scripts/product_experience_openapi.py` | TV3 | Chờ owner tự commit | Contract API, dự toán và dữ liệu chứng cứ |
| `scripts/product_release_preflight.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/public_assets.py` | TV1 | Có trong đợt nhập TV1 | Tooling bàn giao/CI/UI |
| `scripts/public_catalog_openapi.py` | TV3 | Chờ owner tự commit | Contract API, dự toán và dữ liệu chứng cứ |
| `scripts/publish_hosting_config.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/recommendation_infra.py` | TV3 | Chờ owner tự commit | Contract API, dự toán và dữ liệu chứng cứ |
| `scripts/recommendation_openapi.py` | TV3 | Chờ owner tự commit | Contract API, dự toán và dữ liệu chứng cứ |
| `scripts/refresh_prices.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/region_i18n_infra.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/region_i18n_openapi.py` | TV3 | Chờ owner tự commit | Contract API, dự toán và dữ liệu chứng cứ |
| `scripts/regional_runtime.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/restore_aws_frontend.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/review_evidence.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/run_validation.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/template_view_infra.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/template_view_openapi.py` | TV3 | Chờ owner tự commit | Contract API, dự toán và dữ liệu chứng cứ |
| `scripts/test_visibility_openapi.py` | TV3 | Chờ owner tự commit | Contract API, dự toán và dữ liệu chứng cứ |
| `scripts/ui_fixture.py` | TV1 | Có trong đợt nhập TV1 | Tooling bàn giao/CI/UI |
| `scripts/validate_locales.py` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/verify_hosting.mjs` | TV2 | Chờ owner tự commit | Triển khai, IAM, hosting và cấu hình nền |
| `scripts/wallet_openapi.py` | TV3 | Chờ owner tự commit | Contract API, dự toán và dữ liệu chứng cứ |
| `team/FILE_OWNERSHIP.md` | TV1 | Có trong đợt nhập TV1 | Điều phối repository và bảng phân công |
| `team/README.md` | TV1 | Có trong đợt nhập TV1 | Điều phối repository và bảng phân công |
| `team/TV1.md` | TV1 | Có trong đợt nhập TV1 | Bàn giao riêng của người phụ trách |
| `team/TV2.md` | TV2 | Chờ owner tự commit | Bàn giao riêng của người phụ trách |
| `team/TV3.md` | TV3 | Chờ owner tự commit | Bàn giao riêng của người phụ trách |
| `team/TV4.md` | TV4 | Chờ owner tự commit | Bàn giao riêng của người phụ trách |
| `team/file-ownership.json` | TV1 | Có trong đợt nhập TV1 | Điều phối repository và bảng phân công |
| `team/handoff-validation.json` | TV1 | Có trong đợt nhập TV1 | Điều phối repository và bảng phân công |
| `team/members.json` | TV1 | Có trong đợt nhập TV1 | Điều phối repository và bảng phân công |
| `team/source-provenance.json` | TV1 | Có trong đợt nhập TV1 | Điều phối repository và bảng phân công |
| `tests/admin-directory-view.test.mjs` | TV2 | Chờ owner tự commit | Kiểm thử UI auth/hosting/file/quản trị |
| `tests/announcements.test.mjs` | TV2 | Chờ owner tự commit | Kiểm thử UI auth/hosting/file/quản trị |
| `tests/auth.test.mjs` | TV2 | Chờ owner tự commit | Kiểm thử UI auth/hosting/file/quản trị |
| `tests/catalog-view.test.mjs` | TV1 | Có trong đợt nhập TV1 | Kiểm thử frontend/UX và template viewer |
| `tests/cockpit.test.mjs` | TV1 | Có trong đợt nhập TV1 | Kiểm thử frontend/UX và template viewer |
| `tests/content-guard.test.mjs` | TV1 | Có trong đợt nhập TV1 | Kiểm thử frontend/UX và template viewer |
| `tests/create-flow.test.mjs` | TV1 | Có trong đợt nhập TV1 | Kiểm thử frontend/UX và template viewer |
| `tests/create-view.test.mjs` | TV1 | Có trong đợt nhập TV1 | Kiểm thử frontend/UX và template viewer |
| `tests/fixtures/recommendation-contract.json` | TV3 | Chờ owner tự commit | Kiểm API/SDK, dữ liệu, giá, idempotency và hợp đồng |
| `tests/frontend.test.mjs` | TV1 | Có trong đợt nhập TV1 | Kiểm thử frontend/UX và template viewer |
| `tests/guest-experience.test.mjs` | TV2 | Chờ owner tự commit | Kiểm thử UI auth/hosting/file/quản trị |
| `tests/hosting.test.mjs` | TV2 | Chờ owner tự commit | Kiểm thử UI auth/hosting/file/quản trị |
| `tests/i18n.test.mjs` | TV1 | Có trong đợt nhập TV1 | Kiểm thử frontend/UX và template viewer |
| `tests/lifecycle.test.mjs` | TV4 | Chờ owner tự commit | Kiểm thử UI vận hành |
| `tests/notifications.test.mjs` | TV2 | Chờ owner tự commit | Kiểm thử UI auth/hosting/file/quản trị |
| `tests/presentation-data.test.mjs` | TV4 | Chờ owner tự commit | Kiểm thử UI vận hành |
| `tests/product-view.test.mjs` | TV3 | Chờ owner tự commit | Kiểm thử UI giá/dữ liệu/tư vấn |
| `tests/recommendations.test.mjs` | TV3 | Chờ owner tự commit | Kiểm thử UI giá/dữ liệu/tư vấn |
| `tests/session.test.mjs` | TV2 | Chờ owner tự commit | Kiểm thử UI auth/hosting/file/quản trị |
| `tests/shell-view.test.mjs` | TV1 | Có trong đợt nhập TV1 | Kiểm thử frontend/UX và template viewer |
| `tests/template-view.test.mjs` | TV1 | Có trong đợt nhập TV1 | Kiểm thử frontend/UX và template viewer |
| `tests/test-data-view.test.mjs` | TV2 | Chờ owner tự commit | Kiểm thử UI auth/hosting/file/quản trị |
| `tests/test_admin_directory.py` | TV2 | Chờ owner tự commit | Kiểm IAM/auth/hosting/Region/file và quyền đọc |
| `tests/test_announcements.py` | TV2 | Chờ owner tự commit | Kiểm IAM/auth/hosting/Region/file và quyền đọc |
| `tests/test_applications.py` | TV3 | Chờ owner tự commit | Kiểm API/SDK, dữ liệu, giá, idempotency và hợp đồng |
| `tests/test_asg_inventory.py` | TV4 | Chờ owner tự commit | Kiểm race/retry, backup/cleanup, ALB/ECS/publication |
| `tests/test_benchmark_tools.py` | TV3 | Chờ owner tự commit | Kiểm API/SDK, dữ liệu, giá, idempotency và hợp đồng |
| `tests/test_cognito_messages.py` | TV2 | Chờ owner tự commit | Kiểm IAM/auth/hosting/Region/file và quyền đọc |
| `tests/test_configuration_choices.py` | TV3 | Chờ owner tự commit | Kiểm API/SDK, dữ liệu, giá, idempotency và hợp đồng |
| `tests/test_construction_retry.py` | TV4 | Chờ owner tự commit | Kiểm race/retry, backup/cleanup, ALB/ECS/publication |
| `tests/test_data_continuous.py` | TV3 | Chờ owner tự commit | Kiểm API/SDK, dữ liệu, giá, idempotency và hợp đồng |
| `tests/test_direct_uploads.py` | TV2 | Chờ owner tự commit | Kiểm IAM/auth/hosting/Region/file và quyền đọc |
| `tests/test_domain.py` | TV3 | Chờ owner tự commit | Kiểm API/SDK, dữ liệu, giá, idempotency và hợp đồng |
| `tests/test_ecs_retirement.py` | TV4 | Chờ owner tự commit | Kiểm race/retry, backup/cleanup, ALB/ECS/publication |
| `tests/test_external_frontend.py` | TV2 | Chờ owner tự commit | Kiểm IAM/auth/hosting/Region/file và quyền đọc |
| `tests/test_failed_source.py` | TV1 | Có trong đợt nhập TV1 | Kiểm EC2/EFS/readiness và dữ liệu nguồn |
| `tests/test_forecast_ledger.py` | TV3 | Chờ owner tự commit | Kiểm API/SDK, dữ liệu, giá, idempotency và hợp đồng |
| `tests/test_frontend_migration.py` | TV2 | Chờ owner tự commit | Kiểm IAM/auth/hosting/Region/file và quyền đọc |
| `tests/test_hosting.py` | TV2 | Chờ owner tự commit | Kiểm IAM/auth/hosting/Region/file và quyền đọc |
| `tests/test_hosting_publish.py` | TV2 | Chờ owner tự commit | Kiểm IAM/auth/hosting/Region/file và quyền đọc |
| `tests/test_hosting_upload_cors.py` | TV2 | Chờ owner tự commit | Kiểm IAM/auth/hosting/Region/file và quyền đọc |
| `tests/test_infra.py` | TV2 | Chờ owner tự commit | Kiểm IAM/auth/hosting/Region/file và quyền đọc |
| `tests/test_lifecycle.py` | TV4 | Chờ owner tự commit | Kiểm race/retry, backup/cleanup, ALB/ECS/publication |
| `tests/test_lifecycle_api.py` | TV4 | Chờ owner tự commit | Kiểm race/retry, backup/cleanup, ALB/ECS/publication |
| `tests/test_lifecycle_http.py` | TV4 | Chờ owner tự commit | Kiểm race/retry, backup/cleanup, ALB/ECS/publication |
| `tests/test_lifecycle_resume.py` | TV4 | Chờ owner tự commit | Kiểm race/retry, backup/cleanup, ALB/ECS/publication |
| `tests/test_lifecycle_scheduler.py` | TV4 | Chờ owner tự commit | Kiểm race/retry, backup/cleanup, ALB/ECS/publication |
| `tests/test_platform_target.py` | TV3 | Chờ owner tự commit | Kiểm API/SDK, dữ liệu, giá, idempotency và hợp đồng |
| `tests/test_portal.py` | TV3 | Chờ owner tự commit | Kiểm API/SDK, dữ liệu, giá, idempotency và hợp đồng |
| `tests/test_portal_sdk.py` | TV3 | Chờ owner tự commit | Kiểm API/SDK, dữ liệu, giá, idempotency và hợp đồng |
| `tests/test_processors.py` | TV3 | Chờ owner tự commit | Kiểm API/SDK, dữ liệu, giá, idempotency và hợp đồng |
| `tests/test_product_rollout_compatibility.py` | TV3 | Chờ owner tự commit | Kiểm API/SDK, dữ liệu, giá, idempotency và hợp đồng |
| `tests/test_product_ux.py` | TV3 | Chờ owner tự commit | Kiểm API/SDK, dữ liệu, giá, idempotency và hợp đồng |
| `tests/test_public_catalog.py` | TV2 | Chờ owner tự commit | Kiểm IAM/auth/hosting/Region/file và quyền đọc |
| `tests/test_publication_observer.py` | TV4 | Chờ owner tự commit | Kiểm race/retry, backup/cleanup, ALB/ECS/publication |
| `tests/test_quotes_continuous.py` | TV3 | Chờ owner tự commit | Kiểm API/SDK, dữ liệu, giá, idempotency và hợp đồng |
| `tests/test_rds_key_metadata.py` | TV3 | Chờ owner tự commit | Kiểm API/SDK, dữ liệu, giá, idempotency và hợp đồng |
| `tests/test_rds_reconciliation.py` | TV3 | Chờ owner tự commit | Kiểm API/SDK, dữ liệu, giá, idempotency và hợp đồng |
| `tests/test_readiness.py` | TV1 | Có trong đợt nhập TV1 | Kiểm EC2/EFS/readiness và dữ liệu nguồn |
| `tests/test_recommendation_release.py` | TV3 | Chờ owner tự commit | Kiểm API/SDK, dữ liệu, giá, idempotency và hợp đồng |
| `tests/test_recommendations.py` | TV3 | Chờ owner tự commit | Kiểm API/SDK, dữ liệu, giá, idempotency và hợp đồng |
| `tests/test_region_shards.py` | TV2 | Chờ owner tự commit | Kiểm IAM/auth/hosting/Region/file và quyền đọc |
| `tests/test_regional_runtime.py` | TV2 | Chờ owner tự commit | Kiểm IAM/auth/hosting/Region/file và quyền đọc |
| `tests/test_regions.py` | TV2 | Chờ owner tự commit | Kiểm IAM/auth/hosting/Region/file và quyền đọc |
| `tests/test_registration.py` | TV2 | Chờ owner tự commit | Kiểm IAM/auth/hosting/Region/file và quyền đọc |
| `tests/test_review_fixes.py` | TV3 | Chờ owner tự commit | Kiểm API/SDK, dữ liệu, giá, idempotency và hợp đồng |
| `tests/test_s3.py` | TV2 | Chờ owner tự commit | Kiểm IAM/auth/hosting/Region/file và quyền đọc |
| `tests/test_s3_sdk.py` | TV2 | Chờ owner tự commit | Kiểm IAM/auth/hosting/Region/file và quyền đọc |
| `tests/test_sdk.py` | TV3 | Chờ owner tự commit | Kiểm API/SDK, dữ liệu, giá, idempotency và hợp đồng |
| `tests/test_template_view.py` | TV2 | Chờ owner tự commit | Kiểm IAM/auth/hosting/Region/file và quyền đọc |
| `tests/test_termination_review.py` | TV4 | Chờ owner tự commit | Kiểm race/retry, backup/cleanup, ALB/ECS/publication |
| `tests/test_test_visibility.py` | TV4 | Chờ owner tự commit | Kiểm race/retry, backup/cleanup, ALB/ECS/publication |
| `tests/test_user_notifications.py` | TV2 | Chờ owner tự commit | Kiểm IAM/auth/hosting/Region/file và quyền đọc |
| `tests/test_vpc_metadata.py` | TV3 | Chờ owner tự commit | Kiểm API/SDK, dữ liệu, giá, idempotency và hợp đồng |
| `tests/test_wallet_migration.py` | TV3 | Chờ owner tự commit | Kiểm API/SDK, dữ liệu, giá, idempotency và hợp đồng |
| `tests/test_wallets.py` | TV3 | Chờ owner tự commit | Kiểm API/SDK, dữ liệu, giá, idempotency và hợp đồng |
| `tests/test_website_releases.py` | TV4 | Chờ owner tự commit | Kiểm race/retry, backup/cleanup, ALB/ECS/publication |
| `tests/uploads.test.mjs` | TV2 | Chờ owner tự commit | Kiểm thử UI auth/hosting/file/quản trị |
| `tests/wallets.test.mjs` | TV3 | Chờ owner tự commit | Kiểm thử UI giá/dữ liệu/tư vấn |
| `tests/workspace-view.test.mjs` | TV1 | Có trong đợt nhập TV1 | Kiểm thử frontend/UX và template viewer |
| `docs/requirements.md` | TV1 | Có trong đợt nhập TV1 | Scoped TV1 source handoff and local verification |
| `docs/linux-efs-handoff.md` | TV1 | Có trong đợt nhập TV1 | Scoped TV1 source handoff and local verification |
| `scripts/check_leader_handoff.py` | TV1 | Có trong đợt nhập TV1 | Scoped TV1 source handoff and local verification |
| `team/WEEKLY_IMPORT.md` | TV1 | Có trong đợt nhập TV1 | Scoped TV1 source handoff and local verification |
