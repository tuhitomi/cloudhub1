# Đối chiếu mã nguồn với hệ thống đang chạy

Ngày đối chiếu: 14/11/2026, tài khoản 133130236086. Số liệu chụp bằng `scripts/snapshot_deployed.py`, so với `origin/main` (`6f9dc0f`) và với nhánh `ops/production-observability`.

- Template gốc của **17 stack** `cloudhub*` ở ba Region nằm trong `infra/deployed/<region>/<stack>.json`.
- `infra/deployed/manifest.json` ghi trạng thái stack, CodeSha256 của từng Lambda và SHA-256 của từng file frontend.
- Template không chứa giá trị bí mật: `UiEdgeSecret` là tham số `NoEcho`, CloudFormation không trả về giá trị của nó.

## Kết quả

| Thành phần | Khớp với | Ghi chú |
|---|---|---|
| 6 stack vận hành (`cloudhub-observability`, `-healthchecks`, `-security-baseline`, `-dr-tokyo`, `-user-experience`, `-chaos`) | `infra/observability`, `infra/security`, `infra/dr`, `infra/experience`, `infra/chaos` của nhánh này | Giống từng tài nguyên |
| `cloudhub-shared-edge` | `hosting.configure_edge`, cộng `performance_infra.edge_api_cache` và `dr_infra.attach_failover` | Bản đang chạy lưu tại `infra/deployed/ap-southeast-1/cloudhub-shared-edge.json` |
| `cloudhub-pages-live` (control plane) | Không có generator nào trong repo sinh ra đúng template này | Production có 119 tài nguyên, `infra/control-plane.json` có 74. Template production được dựng theo quy trình phát hành riêng của nhóm; bản đang chạy giờ được lưu ở `infra/deployed/ap-southeast-1/cloudhub-pages-live.json` |
| Các stack còn lại (mạng, tên miền, chứng chỉ, runtime theo Region) | Ví dụ trong `infra/hosting/*.example.json` và các generator | Bản đang chạy được lưu trong `infra/deployed/` |
| Lambda `api` (cập nhật 29/10) | `origin/main`: 66/67 module giống | Khác duy nhất `worker.py` (xem bên dưới) |
| Lambda `worker`, `expiry`, `sweep` (cập nhật 24/10) | `origin/main`: 64/66 module giống | Khác `worker.py`, và `api.py` (bản trên Lambda chưa có route `GET /environments/{id}/template`; ba function này không phục vụ HTTP nên route đó không dùng tới) |
| Frontend (52 file trên S3) | 29 file giống cả `main` lẫn nhánh này. 7 file chỉ giống nhánh này: `index.html`, `public-preview.js`, `rum.js`, `vendor/aws-rum-web/cwr.js`, `portal.js`, `quota-view.js`, `error-text.js`. 3 file chỉ giống `main`. 10 file locale: xem bên dưới | Xem bên dưới |
| `config.js`, `maintenance.json`, `rum-config.json` | Sinh lúc triển khai từ output của stack | Không thuộc mã nguồn |

### Frontend

- **Đã sửa trong lần đối chiếu này.** 13 file giao diện ví/quota và 3 file kiểm thử đã được upload lên production ngày 12/11 nhưng chưa từng commit. Commit `600c4dc` đưa chúng vào nhánh này.
- **10 file locale** trên production bằng đúng bản của nhánh này, chỉ bớt 26 khóa của tính năng nhóm 3 (terminal, resize, chi phí). Mọi bản dịch còn lại giống từng chữ. Phần nhóm 3 chưa phát hành, vì backend tương ứng chưa được deploy.
- `app.js`, `catalog-text.js`, `workspace-view.js` trên production giống `main`. Thay đổi nhóm 3 của ba file này cũng chưa phát hành.

### Backend: bản vá chưa được deploy

`origin/main` có commit `2323ef8` (04/11/2026), thêm kiểm tra quyền sở hữu và Region trong nhánh dự phòng `MarkFailure` của `worker.py`:

```python
if not env or env.get('owner_id') != op.get('owner_id'):
    raise HubError('RESOURCE_SCOPE_MISMATCH', ...)
if s.region_for(op) != region:
    raise HubError('RESOURCE_REGION_MISMATCH', ...)
# và kiểm owner/Region của recovery point
```

Cả bốn Lambda đang chạy **chưa có** đoạn này. Ngoài 12 dòng đó, `worker.py` trên Lambda giống `main`. Đây là chiều lệch ngược: GitHub có mã mới hơn production. Muốn khớp thì cần phát hành control plane hoặc cập nhật code của bốn function.

### Phần chưa phát hành (đúng dự kiến)

Mã backend của các nhánh nhóm 1–3 (gzip, cache catalog trong Lambda, SnapStart, spend guard, terminal, resize, chi phí) và các thay đổi control plane đi kèm chưa được triển khai, vì việc phát hành stack `cloudhub-pages-live` đi theo quy trình riêng của nhóm. Mọi phần đã triển khai ngoài stack đó đều có mã tương ứng trong nhánh này.

## Chạy lại

```sh
python scripts/snapshot_deployed.py --bucket <frontend bucket> --compare-ref origin/main --compare-ref HEAD
git diff --stat infra/deployed/
```
