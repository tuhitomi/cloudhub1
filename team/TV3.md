# TV3 — Nguyễn Hải Dương

IaC, mạng, IAM và driver T01–T09.

Kiến trúc phụ trách: M6 và driver của M7; D08–D11, D13, D14.

## Công việc

| Mã | Kế hoạch trong báo cáo | Đầu ra |
|---|---|---|
| KH09 | 1–2Hoàn thành | Thiết lập SAM/CloudFormation, mạng hai AZ, role, secret và tham số; tách tài nguyên chung khỏi workload và chuẩn bị cấu hình triển khai theo Region. |
| KH10 | 3–4Hoàn thành | Xây dựng driver T01, T03, T04, T05 với EC2, EBS, RDS và ALB/ASG; bổ sung readiness, snapshot và cấu hình ứng dụng được duyệt. |
| KH11 | 5–6Hoàn thành | Xây dựng driver T06 và T08; cấu hình Fargate, dữ liệu S3, EFS, hai client và AWS Backup; xác định dữ liệu bảo vệ của từng mẫu. |
| KH12 | 6–7Hoàn thành | Xây dựng driver T02, T07, T09; tích hợp staging, checksum, publish/rollback và dữ liệu API; cung cấp inventory cùng thao tác backup/restore theo mẫu. |
| KH19 | 8–9Kế hoạch | Kiểm chứng tạo, truy cập, backup, restore và thu hồi T01–T09 với cấu hình chuẩn tại Singapore; đối chiếu dữ liệu và inventory, kiểm gate của tổ hợp chưa được mở. |
| KH23 | 9–10Kế hoạch | Rà soát role, security group, secret và cấu hình triển khai; xử lý tài nguyên thử còn sót, chốt IaC/driver và hướng dẫn triển khai, sao lưu, thu hồi. |

## File phụ trách

Owner chịu trách nhiệm tích hợp và review. File chưa có trên nhánh hiện tại cần được bổ sung trước khi chạy luồng liên quan; không coi danh sách này là kết quả kiểm thử.

| File | Công việc |
|---|---|
| `backend/cloudhub/application_driver.py` | KH10 |
| `backend/cloudhub/aws_driver.py` | KH10 |
| `backend/cloudhub/benchmark_agent.py` | KH09 |
| `backend/cloudhub/cf_common.py` | KH09 |
| `backend/cloudhub/container_app.py` | KH11 |
| `backend/cloudhub/content_app.py` | KH10 |
| `backend/cloudhub/content_routing.py` | KH12 |
| `backend/cloudhub/data_api_app.py` | KH12 |
| `backend/cloudhub/data_driver.py` | KH12 |
| `backend/cloudhub/data_template.py` | KH12 |
| `backend/cloudhub/ecs_driver.py` | KH11 |
| `backend/cloudhub/ecs_template.py` | KH11 |
| `backend/cloudhub/efs_driver.py` | KH11 |
| `backend/cloudhub/efs_records.py` | KH11 |
| `backend/cloudhub/efs_template.py` | KH11 |
| `backend/cloudhub/rds_app.py` | KH10 |
| `backend/cloudhub/rds_driver.py` | KH10 |
| `backend/cloudhub/rds_template.py` | KH10 |
| `backend/cloudhub/redshift_driver.py` | KH09 |
| `backend/cloudhub/redshift_template.py` | KH09 |
| `backend/cloudhub/s3_driver.py` | KH12 |
| `backend/cloudhub/s3_template.py` | KH12 |
| `backend/cloudhub/stack_driver.py` | KH09 |
| `backend/cloudhub/templates.py` | KH10 |
| `backend/requirements.txt` | KH09 |
| `benchmarks/http.js` | KH19 |
| `config/deployment.example.json` | KH09 |
| `config/hosting.example.json` | KH09 |
| `config/hosting.readiness.example.json` | KH09 |
| `config/platform-target.example.json` | KH09 |
| `config/regions.example.json` | KH09 |
| `docs/deployment.md` | KH23 |
| `docs/linux-efs-handoff.md` | KH23 |
| `docs/platform-portability-runbook.md` | KH23 |
| `infra/container/Dockerfile` | KH11 |
| `infra/control-plane.json` | KH09 |
| `infra/hosting/api-domain.example.json` | KH09 |
| `infra/hosting/certificate-api.example.json` | KH09 |
| `infra/hosting/certificate-frontend.example.json` | KH09 |
| `infra/hosting/edge-domain.example.json` | KH09 |
| `infra/hosting/edge-import.example.json` | KH09 |
| `infra/hosting/public-zone.example.json` | KH09 |
| `infra/hosting/shared-routing.example.json` | KH09 |
| `infra/network.json` | KH09 |
| `scripts/aws_lifecycle.py` | KH19 |
| `scripts/benchmark_workloads.py` | KH19 |
| `scripts/build_pages_live.py` | KH09 |
| `scripts/build_pages_preview.py` | KH09 |
| `scripts/check_t02_publication.py` | KH19 |
| `scripts/generate_hosting_examples.py` | KH09 |
| `scripts/generate_infra.py` | KH09 |
| `scripts/generate_network.py` | KH09 |
| `scripts/hosting.py` | KH09 |
| `scripts/hosting_aws.py` | KH09 |
| `scripts/hosting_changeset.py` | KH09 |
| `scripts/hosting_upload_cors.py` | KH09 |
| `scripts/infra_extensions.py` | KH09 |
| `scripts/preflight.py` | KH09 |
| `scripts/prepare_deployment.py` | KH09 |
| `scripts/prepare_hosting.py` | KH09 |
| `scripts/prepare_hosting_cutover.py` | KH09 |
| `scripts/prepare_platform_target.py` | KH09 |
| `scripts/prepare_review.py` | KH09 |
| `scripts/publish_hosting_config.py` | KH09 |
| `scripts/regional_runtime.py` | KH09 |
| `scripts/restore_aws_frontend.py` | KH09 |
| `scripts/review_evidence.py` | KH19 |
| `scripts/run_validation.py` | KH19 |
| `scripts/template_view_infra.py` | KH09 |
| `scripts/verify_hosting.mjs` | KH09 |
| `tests/content-guard.test.mjs` | KH19 |
| `tests/hosting.test.mjs` | KH19 |
| `tests/test_asg_inventory.py` | KH19 |
| `tests/test_benchmark_tools.py` | KH19 |
| `tests/test_data_continuous.py` | KH19 |
| `tests/test_ecs_retirement.py` | KH19 |
| `tests/test_external_frontend.py` | KH19 |
| `tests/test_failed_source.py` | KH19 |
| `tests/test_frontend_migration.py` | KH19 |
| `tests/test_hosting.py` | KH19 |
| `tests/test_hosting_publish.py` | KH19 |
| `tests/test_hosting_upload_cors.py` | KH19 |
| `tests/test_infra.py` | KH19 |
| `tests/test_platform_target.py` | KH19 |
| `tests/test_processors.py` | KH19 |
| `tests/test_publication_observer.py` | KH19 |
| `tests/test_rds_key_metadata.py` | KH19 |
| `tests/test_rds_reconciliation.py` | KH19 |
| `tests/test_readiness.py` | KH19 |
| `tests/test_regional_runtime.py` | KH19 |
| `tests/test_s3.py` | KH19 |
| `tests/test_s3_sdk.py` | KH19 |
| `tests/test_sdk.py` | KH19 |
| `tests/test_vpc_metadata.py` | KH19 |
