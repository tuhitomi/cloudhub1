# TV4 — Hoàng Đường Anh Tú

Nhóm trưởng; điều phối vòng đời, lịch, bảo vệ dữ liệu, quản trị và phát hành.

Kiến trúc phụ trách: M5, điều phối M7, M8; D05–D08, D11, D12.

## Công việc

| Mã | Kế hoạch trong báo cáo | Đầu ra |
|---|---|---|
| KH13 | 1–2Hoàn thành | Thống nhất hợp đồng service–worker–driver; xây dựng operation, phase, checkpoint và state machine Tick/Wait/Retry/Catch để chạy công việc dài. |
| KH14 | 3–4Hoàn thành | Xây dựng expiry, sweep, gia hạn, PAUSE/resume và đồng bộ lịch; dùng revision, generation và khóa để bỏ callback cũ và sửa lịch lỗi. |
| KH15 | 5–6Hoàn thành | Điều phối backup, restore, export, retention và thu hồi; giữ nguồn khi backup lỗi, kiểm readiness và audit trước khi trả quota. |
| KH16 | 6–7Hoàn thành | Tích hợp quản trị, thông báo theo owner, email tùy chọn, CloudWatch và kiểm tra CI; ghép giao diện, API và driver thành luồng chung. |
| KH20 | 8–9Kế hoạch | Kiểm thử callback cũ, dispatch lỗi, workflow thử lại, schedule_pending, backup lỗi và quyền kiểm kê thiếu; đối chiếu log, trạng thái giữ nguồn và cơ chế phục hồi. |
| KH24 | 9–10Kế hoạch | Tổ chức kiểm thử hồi quy chung, tổng hợp kết quả và rủi ro; chốt phiên bản repo, cấu hình phát hành, báo cáo và kịch bản trình diễn cuối tuần 10. |

## File phụ trách

Owner chịu trách nhiệm tích hợp và review. File chưa có trên nhánh hiện tại cần được bổ sung trước khi chạy luồng liên quan; không coi danh sách này là kết quả kiểm thử.

| File | Công việc |
|---|---|
| `.gitattributes` | KH24 |
| `.github/CODEOWNERS.example` | KH24 |
| `.github/pull_request_template.md` | KH24 |
| `.github/workflows/ci.yml` | KH24 |
| `.gitignore` | KH24 |
| `README.md` | KH24 |
| `backend/cloudhub/admin_directory.py` | KH16 |
| `backend/cloudhub/announcements.py` | KH16 |
| `backend/cloudhub/archive.py` | KH15 |
| `backend/cloudhub/backup_export.py` | KH15 |
| `backend/cloudhub/driver_router.py` | KH13 |
| `backend/cloudhub/lifecycle.py` | KH14 |
| `backend/cloudhub/lifecycle_scheduler.py` | KH14 |
| `backend/cloudhub/notification_email.py` | KH16 |
| `backend/cloudhub/notifications.py` | KH16 |
| `backend/cloudhub/operating_policy.py` | KH14 |
| `backend/cloudhub/portal.py` | KH16 |
| `backend/cloudhub/portal_api.py` | KH16 |
| `backend/cloudhub/recovery_actions.py` | KH15 |
| `backend/cloudhub/runtime.py` | KH13 |
| `backend/cloudhub/test_visibility.py` | KH16 |
| `backend/cloudhub/worker.py` | KH13 |
| `config/product-release.example.json` | KH24 |
| `docs/DEVELOPMENT.md` | KH24 |
| `docs/architecture.md` | KH24 |
| `docs/backup-restore.md` | KH24 |
| `docs/local-check-results.json` | KH24 |
| `docs/product-scope.md` | KH24 |
| `docs/requirements.md` | KH24 |
| `docs/source-record.json` | KH24 |
| `docs/testing.md` | KH24 |
| `infra/lifecycle.asl.json` | KH13 |
| `requirements-dev.txt` | KH24 |
| `scripts/announcement_infra.py` | KH16 |
| `scripts/archive_test_data.py` | KH16 |
| `scripts/benchmark.py` | KH16 |
| `scripts/check.py` | KH16 |
| `scripts/check_leader_handoff.py` | KH16 |
| `scripts/check_local.py` | KH16 |
| `scripts/check_product_release.py` | KH16 |
| `scripts/check_team_ownership.py` | KH16 |
| `scripts/generate_codeowners.py` | KH16 |
| `scripts/lifecycle_http.py` | KH16 |
| `scripts/measure_expiry.py` | KH14 |
| `scripts/measure_product_local.py` | KH16 |
| `scripts/notification_infra.py` | KH16 |
| `scripts/package_console.py` | KH16 |
| `scripts/portal_infra.py` | KH16 |
| `scripts/prepare_product_0_8_packet.py` | KH16 |
| `scripts/prepare_product_release.py` | KH16 |
| `scripts/prepare_recommendations_release.py` | KH16 |
| `scripts/product_completion_infra.py` | KH16 |
| `scripts/product_release_preflight.py` | KH16 |
| `scripts/recommendation_infra.py` | KH16 |
| `scripts/region_i18n_infra.py` | KH16 |
| `team/FILE_OWNERSHIP.md` | KH24 |
| `team/MILESTONES.md` | KH24 |
| `team/README.md` | KH24 |
| `team/TV1.md` | KH24 |
| `team/TV2.md` | KH24 |
| `team/TV3.md` | KH24 |
| `team/TV4.md` | KH24 |
| `team/file-ownership.json` | KH24 |
| `team/members.json` | KH24 |
| `tests/test_admin_directory.py` | KH20 |
| `tests/test_announcements.py` | KH20 |
| `tests/test_construction_retry.py` | KH20 |
| `tests/test_lifecycle.py` | KH20 |
| `tests/test_lifecycle_http.py` | KH20 |
| `tests/test_lifecycle_resume.py` | KH20 |
| `tests/test_lifecycle_scheduler.py` | KH20 |
| `tests/test_portal.py` | KH20 |
| `tests/test_portal_sdk.py` | KH20 |
| `tests/test_product_rollout_compatibility.py` | KH20 |
| `tests/test_test_visibility.py` | KH20 |
| `tests/test_user_notifications.py` | KH20 |
