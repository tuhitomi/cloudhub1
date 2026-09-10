# TV1 — Workspace, frontend/UX và Linux/EFS

Nhóm trưởng/TV1, GitHub: `tuhitomi`. Đợt nhập nguồn được đưa lên main; các thành viên khác tự tạo nhánh nhận phần việc.

Mốc tuần chỉ là giai đoạn nhập mã hiện có; xem `WEEKLY_IMPORT.md`. Không chứng minh thời điểm viết mã hay chạy AWS.

AWS tự phụ trách: **T01, T08 — EC2/EBS/EFS**.

Vẽ topology; giải thích SG/IMDS/OAC; SSH và /data; so checksum sau snapshot/EFS restore; chỉ rõ root/RAM không được bảo vệ.

Mỗi người bàn giao mã, unit/integration test, cấu hình mẫu/IaC liên quan, runbook/demo và bằng chứng thật đúng phạm vi. Không nhận rằng mình đã viết hoặc đã chạy phần chỉ được giao đọc/tiếp quản.

## Danh sách file chính xác

- [`.gitattributes`](../.gitattributes) — Repository, dependencies và CI
- [`.github/CODEOWNERS.example`](../.github/CODEOWNERS.example) — Điều phối repository và bảng phân công
- [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) — Repository, dependencies và CI
- [`.gitignore`](../.gitignore) — Repository, dependencies và CI
- [`README.md`](../README.md) — Điều phối repository và bảng phân công
- [`backend/cloudhub/aws_driver.py`](../backend/cloudhub/aws_driver.py) — Linux/EC2/EBS và EFS T01/T08
- [`backend/cloudhub/efs_driver.py`](../backend/cloudhub/efs_driver.py) — Linux/EC2/EBS và EFS T01/T08
- [`backend/cloudhub/efs_records.py`](../backend/cloudhub/efs_records.py) — Linux/EC2/EBS và EFS T01/T08
- [`backend/cloudhub/efs_template.py`](../backend/cloudhub/efs_template.py) — Linux/EC2/EBS và EFS T01/T08
- [`backend/cloudhub/templates.py`](../backend/cloudhub/templates.py) — Linux/EC2/EBS và EFS T01/T08
- [`docs/architecture.md`](../docs/architecture.md) — Tài liệu tích hợp và kiểm thử
- [`docs/testing.md`](../docs/testing.md) — Tài liệu tích hợp và kiểm thử
- [`frontend/app.js`](../frontend/app.js) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/appearance.js`](../frontend/appearance.js) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/architecture.js`](../frontend/architecture.js) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/catalog-text.js`](../frontend/catalog-text.js) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/catalog-view.js`](../frontend/catalog-view.js) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/cockpit.js`](../frontend/cockpit.js) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/config.example.js`](../frontend/config.example.js) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/create-flow.js`](../frontend/create-flow.js) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/create-view.js`](../frontend/create-view.js) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/error-text.js`](../frontend/error-text.js) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/i18n.js`](../frontend/i18n.js) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/index.html`](../frontend/index.html) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/locale-en.js`](../frontend/locale-en.js) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/locale-source.js`](../frontend/locale-source.js) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/locales/de.json`](../frontend/locales/de.json) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/locales/en.json`](../frontend/locales/en.json) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/locales/es.json`](../frontend/locales/es.json) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/locales/fr.json`](../frontend/locales/fr.json) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/locales/ja.json`](../frontend/locales/ja.json) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/locales/ko.json`](../frontend/locales/ko.json) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/locales/vi.json`](../frontend/locales/vi.json) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/locales/zh-Hans.json`](../frontend/locales/zh-Hans.json) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/maintenance.css`](../frontend/maintenance.css) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/maintenance.html`](../frontend/maintenance.html) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/pages-preview.js`](../frontend/pages-preview.js) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/portal.js`](../frontend/portal.js) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/redesign.css`](../frontend/redesign.css) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/shell-view.js`](../frontend/shell-view.js) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/style.css`](../frontend/style.css) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/template-view.js`](../frontend/template-view.js) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/workspace-ui.js`](../frontend/workspace-ui.js) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/workspace-view.js`](../frontend/workspace-view.js) — Workspace, trải nghiệm, i18n và template-view UI
- [`frontend/workspace.css`](../frontend/workspace.css) — Workspace, trải nghiệm, i18n và template-view UI
- [`package-lock.json`](../package-lock.json) — Repository, dependencies và CI
- [`package.json`](../package.json) — Repository, dependencies và CI
- [`requirements-dev.txt`](../requirements-dev.txt) — Repository, dependencies và CI
- [`scripts/check_team_ownership.py`](../scripts/check_team_ownership.py) — Tooling bàn giao/CI/UI
- [`scripts/generate_codeowners.py`](../scripts/generate_codeowners.py) — Tooling bàn giao/CI/UI
- [`scripts/public_assets.py`](../scripts/public_assets.py) — Tooling bàn giao/CI/UI
- [`scripts/ui_fixture.py`](../scripts/ui_fixture.py) — Tooling bàn giao/CI/UI
- [`team/FILE_OWNERSHIP.md`](../team/FILE_OWNERSHIP.md) — Điều phối repository và bảng phân công
- [`team/README.md`](../team/README.md) — Điều phối repository và bảng phân công
- [`team/TV1.md`](../team/TV1.md) — Bàn giao riêng của người phụ trách
- [`team/file-ownership.json`](../team/file-ownership.json) — Điều phối repository và bảng phân công
- [`team/handoff-validation.json`](../team/handoff-validation.json) — Điều phối repository và bảng phân công
- [`team/members.json`](../team/members.json) — Điều phối repository và bảng phân công
- [`team/source-provenance.json`](../team/source-provenance.json) — Điều phối repository và bảng phân công
- [`tests/catalog-view.test.mjs`](../tests/catalog-view.test.mjs) — Kiểm thử frontend/UX và template viewer
- [`tests/cockpit.test.mjs`](../tests/cockpit.test.mjs) — Kiểm thử frontend/UX và template viewer
- [`tests/content-guard.test.mjs`](../tests/content-guard.test.mjs) — Kiểm thử frontend/UX và template viewer
- [`tests/create-flow.test.mjs`](../tests/create-flow.test.mjs) — Kiểm thử frontend/UX và template viewer
- [`tests/create-view.test.mjs`](../tests/create-view.test.mjs) — Kiểm thử frontend/UX và template viewer
- [`tests/frontend.test.mjs`](../tests/frontend.test.mjs) — Kiểm thử frontend/UX và template viewer
- [`tests/i18n.test.mjs`](../tests/i18n.test.mjs) — Kiểm thử frontend/UX và template viewer
- [`tests/shell-view.test.mjs`](../tests/shell-view.test.mjs) — Kiểm thử frontend/UX và template viewer
- [`tests/template-view.test.mjs`](../tests/template-view.test.mjs) — Kiểm thử frontend/UX và template viewer
- [`tests/test_failed_source.py`](../tests/test_failed_source.py) — Kiểm EC2/EFS/readiness và dữ liệu nguồn
- [`tests/test_readiness.py`](../tests/test_readiness.py) — Kiểm EC2/EFS/readiness và dữ liệu nguồn
- [`tests/workspace-view.test.mjs`](../tests/workspace-view.test.mjs) — Kiểm thử frontend/UX và template viewer
