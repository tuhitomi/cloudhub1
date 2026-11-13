# DR đa Region, cache API tại edge, giám sát trải nghiệm và chaos engineering

Thực hiện ngày 13/11/2026 trên production (tài khoản 133130236086). Region chính là Singapore (`ap-southeast-1`), Region dự phòng là Tokyo (`ap-northeast-1`). Stack điều khiển `cloudhub-pages-live` không bị sửa: mọi thứ mới nằm trong stack riêng, hoặc là cấu hình của tài nguyên không thuộc stack đó (ghi rõ ở mục 6).

## 1. Kiến trúc

```
                 cloudhub1.me (CloudFront, PriceClass_200, HTTP/3)
                 │
   ┌─────────────┼──────────────────────────┬───────────────────────────┐
   │ default, index.html, config.js         │ /public/catalog           │ /ui-context
   │ origin group frontend-failover         │ origin group              │ API Singapore
   │  1. S3 Singapore (OAC)                 │ catalog-failover          │
   │  2. S3 Tokyo (OAC)  ← 403/404/5xx      │  1. HTTP API Singapore    │
   │                                        │  2. S3 Tokyo snapshot ← 5xx
   │                                        │  cache 60 s theo query    │
   └────────────────────────────────────────┴───────────────────────────┘
 S3 Singapore ──Cross-Region Replication──▶ S3 Tokyo ◀── Lambda snapshot catalog (15 phút/lần)
 DynamoDB Singapore ◀──global table 2019.11.21──▶ bản sao Tokyo (PITR bật cả hai bên)
```

| Thành phần | Mã | Stack / cách triển khai |
|---|---|---|
| Cache `/public/catalog` tại edge | `scripts/performance_infra.py` (`edge_api_cache`) | `cloudhub-shared-edge` (change set `edge-cache-and-failover`) |
| Origin group và origin Tokyo | `scripts/dr_infra.py` (`attach_failover`) | `cloudhub-shared-edge` (cùng change set) |
| Bucket Tokyo, role CRR, Lambda snapshot, EventBridge Scheduler | `scripts/dr_infra.py` → `infra/dr/tokyo.json` | `cloudhub-dr-tokyo` (Tokyo) |
| Global table, PITR bản sao, versioning và CRR của bucket chính | `dr_infra.replica_commands` | Lệnh CLI một lần (mục 6) |
| Canary Synthetics, CloudWatch RUM | `scripts/experience_infra.py` → `infra/experience/regional.json`; `frontend/rum.js` | `cloudhub-user-experience` |
| Thí nghiệm chaos | `scripts/chaos_infra.py` → `infra/chaos/regional.json` | `cloudhub-chaos` |

Phạm vi failover: khi Region chính hoặc API gặp sự cố, khách vẫn mở được trang và xem danh mục mẫu (chế độ chỉ đọc). Đăng nhập và tạo môi trường vẫn cần control plane ở Singapore, vì Cognito và API là tài nguyên theo Region. Dữ liệu đã có sẵn ở Tokyo, độ trễ khoảng 1 giây. Muốn khôi phục toàn bộ ở Tokyo thì triển khai control plane tại đó và trỏ tham số `Table` vào bản sao.

## 2. Cache catalog tại edge

Thử tải ở mục 2.1 của `docs/production-operations.md` cho thấy throttle 5 request/giây của route `/public/catalog` trả 429 cho 813/1.279 request ở mức 100 người dùng. Cách sửa:

- CloudFront phục vụ `GET /public/catalog` với cache policy riêng: TTL 60–300 giây, khóa cache là toàn bộ query string, không dùng header hay cookie, nén gzip/brotli. Catalog chỉ phụ thuộc query (`cloudhub.api.public_catalog_response`), nên mọi khách dùng chung một bản cache.
- `frontend/public-preview.js` gọi `https://cloudhub1.me/public/catalog` (cùng domain) khi trang được mở từ đúng site production. Nếu lỗi mạng hoặc HTTP lỗi thì gọi thẳng `apiBase`. Môi trường phát triển và preview vẫn gọi API.

Kiểm chứng: request đầu tiên `X-Cache: Miss`, các request sau `Hit from cloudfront` tại HAN51 (Hà Nội), nén brotli. Trình duyệt tải `/public/catalog` bằng HTTP/3. Mỗi POP chỉ gọi API khoảng một lần mỗi phút cho mỗi query khác nhau.

## 3. DR đa Region

### 3.1 Frontend

- Bucket `cloudhub-dr-frontend-133130236086-ap-northeast-1`: riêng tư, có versioning, mã hóa, chỉ cho phép TLS, chỉ cho phép distribution `E29Q1P8948MCCD` đọc qua OAC. Phiên bản cũ tự xóa sau 30 ngày.
- S3 Cross-Region Replication từ bucket chính (có sao chép cả delete marker). Lần đầu đồng bộ bằng `aws s3 sync`, gồm 50 file. Các file upload sau đó ở trạng thái `COMPLETED` bên nguồn và `REPLICA` bên Tokyo.
- Diễn tập failover: đặt `dr-probe.txt` chỉ trong bucket Tokyo rồi tải `https://cloudhub1.me/dr-probe.txt`. Singapore trả 403, CloudFront tự lấy từ Tokyo và trả **200**. Server-Timing cho thấy `cdn-upstream-connect` 158 ms tới Tokyo. Một đường dẫn không tồn tại ở cả hai bucket vẫn trả 403.

### 3.2 Catalog

Lambda `cloudhub-dr-tokyo-catalog-snapshot` (Python 3.13, arm64) đọc `https://api.cloudhub1.me/public/catalog` mỗi 15 phút qua EventBridge Scheduler. Nó kiểm tra nội dung (có `items` không rỗng và `signup_policy`) rồi ghi vào `public/catalog` trong bucket Tokyo, kèm metadata `snapshot-at`. Nếu API trả nội dung lạ, Lambda báo lỗi và giữ nguyên bản chụp tốt gần nhất. Role của Lambda chỉ được `s3:PutObject` đúng key này.

### 3.3 Dữ liệu: DynamoDB global table

| Bước | Kết quả |
|---|---|
| Bật DynamoDB Streams `NEW_AND_OLD_IMAGES` | OK |
| Thêm bản sao `ap-northeast-1` (global table 2019.11.21) | Bản sao `ACTIVE` sau **662 giây**, GSI `by_owner` ACTIVE, mã hóa KMS |
| Đối chiếu số item (scan COUNT) | Singapore 2.970 = Tokyo 2.970 |
| Bật PITR cho bản sao | `ENABLED` |
| Độ trễ sao chép, 20 lần ghi (`scripts/replication_lag.py`) | **p50 923 ms, p95 1.284 ms, max 1.481 ms**; xóa sao chép trong 91 ms |

Số đo trên gồm cả vòng gọi đọc tới Tokyo từ Việt Nam, nên là cận trên. **RPO giảm từ khoảng 5 phút (PITR) xuống khoảng 1 giây.** Các item thử dùng khóa `DRPROBE#…`, nằm ngoài mọi tiền tố khóa của ứng dụng, và đã được xóa. Kết quả gốc nằm trong `docs/dr/replication-lag-2026-11-13.json`.

## 4. Giám sát trải nghiệm người dùng

**Canary `cloudhub-journey`** (Synthetics, `syn-nodejs-puppeteer-9.1`, 10 phút/lần) chạy 4 bước: mở trang chủ, chờ đủ 9 mẫu hiển thị, gọi `/public/catalog` qua edge, gọi `/ui-context`. Ảnh chụp, HAR và log lưu 30 ngày trong bucket riêng. Alarm `journey-failing` kêu khi tỷ lệ chạy thành công dưới 90 %.

**CloudWatch RUM `cloudhub-web`**: đo thời gian tải trang (kèm LCP, CLS, INP) và lỗi JavaScript từ trình duyệt thật.

- Trình duyệt lấy credential tạm từ Cognito identity pool `cloudhub_rum`. Role khách chỉ được `rum:PutRumEvents` lên đúng app monitor này.
- Client `aws-rum-web` 1.x được tự host (`frontend/vendor/aws-rum-web/`), vì CSP chỉ cho phép script từ `'self'`. Client chỉ tải sau khi trang rảnh, và chỉ khi có `rum-config.json` (lấy từ output `RumConfig` của stack).
- Không dùng cookie, không bật X-Ray, chỉ thu `performance` và `errors`.

Kiểm chứng trên trình duyệt: `rum.js`, `rum-config.json` và `cwr.js` đều tải qua h3. Cognito Identity trả credential, request tới `dataplane.rum.ap-southeast-1` thành công, không có vi phạm CSP. Namespace `AWS/RUM` đã có `PageViewCount`, `SessionCount`, `PerformanceNavigationDuration`, `NavigationSatisfiedTransaction`…

## 5. Chaos engineering: API ngừng hoạt động 3 phút

AWS FIS chưa dùng được trên tài khoản (`SubscriptionRequiredException` trong lúc AWS xác minh tài khoản), nên nhóm dựng thí nghiệm bằng Step Functions theo đúng mô hình của một experiment template FIS:

| Thành phần | Thiết kế |
|---|---|
| Lỗi gây ra | Reserved concurrency = 0 cho `cloudhub-pages-live-api`: mọi request API thất bại; không xóa gì, không đổi mã |
| Điều kiện trước | Function chưa có reserved concurrency riêng (để hoàn tác đúng trạng thái cũ); không có guard alarm nào đang kêu |
| Điều kiện dừng | Mỗi 15 giây đọc guard alarm `cloudhub-chaos-guard-lifecycle-failed` (workflow tạo/xóa môi trường của người dùng thật bị lỗi); nếu kêu thì hoàn tác ngay |
| Thời lượng | 30–600 giây, kiểm tra đầu vào |
| Hoàn tác | `DeleteFunctionConcurrency` có retry, sau đó đọc lại để xác minh; mọi lỗi giữa chừng đều đi qua bước hoàn tác (có kiểm thử duyệt đồ thị trạng thái) |
| Lưới an toàn | Execution bị hủy tay hoặc quá giờ thì EventBridge tự chạy workflow `cloudhub-chaos-restore` |

Execution `api-outage-130213`: bắt đầu 13:02:14, gây lỗi lúc 13:02:14,7, hoàn tác lúc 13:05:16,6, `SUCCEEDED` lúc 13:05:16,9. `scripts/chaos_probe.py` đo mỗi giây từ phía người dùng, tổng 393 lượt (kết quả gốc trong `docs/chaos/probe-2026-11-13.json`):

| Điểm cuối | Trước sự cố | Trong sự cố (182 s) | Sau hoàn tác |
|---|---|---|---|
| Trang chủ | 55/55 OK, p50 183 ms | **172/172 OK**, p50 131 ms | 166/166 OK |
| Catalog qua edge | 55/55 OK | **172/172 OK**: 57 từ cache edge, sau đó **115 từ bản chụp Tokyo**, p50 125 ms | 166/166 OK, về lại API |
| API `/ui-context` | 55/55 OK | 0/172 (503) | **OK ngay giây đầu tiên sau hoàn tác** |

Phát hiện và cảnh báo:

| Thời điểm | Sự kiện |
|---|---|
| 13:02:14 | Gây lỗi |
| 13:03:16 | Cache catalog hết hạn; CloudFront nhận 503 và chuyển sang bản chụp Tokyo |
| 13:03:43 | `cloudhub-observability-Throttles` → ALARM |
| 13:04:06 | Canary: 3 bước đầu đạt, bước `ui-context` báo 503 |
| 13:04:12 | `api-burn-1h` (burn rate > 14,4) → ALARM; composite **`slo-page`** → ALARM (**2 phút sau sự cố**) |
| 13:05:16 | Hoàn tác; API trả 200 ngay |
| 13:06:14 | Route 53 `cloudhub-healthchecks-api-down` → ALARM (đánh giá 2/3 phút, nên trễ hơn) |
| 13:07:43 | `Throttles` → OK |

Alarm `cloudhub-healthchecks-cloudfront-5xx` vẫn OK suốt thí nghiệm: người dùng không nhận lỗi 5xx nào từ CDN. Kết luận: giả thuyết được xác nhận. Kiến trúc cô lập được sự cố của API khỏi phần công khai của site, và hệ thống giám sát phát hiện sự cố trong khoảng 2 phút qua ba kênh độc lập (metric Lambda, SLO burn rate, canary). Bài học rút ra: health check Route 53 phát hiện chậm hơn burn-rate alarm, vì nó cần 2/3 phút thất bại và hồi phục cũng trễ tương ứng. Alarm burn-rate 1 giờ giữ trạng thái ALARM tới khi cửa sổ 1 giờ trôi qua; đây là hành vi đúng, vì error budget đã thực sự bị tiêu.

Phụ: alarm CIS `IamPolicyChanges` đã kêu khi các stack mới tạo IAM role, và `RootUsage` kêu vì phiên làm việc dùng tài khoản root. Cả hai đều phát hiện đúng.

## 6. Thay đổi ngoài CloudFormation

Các lệnh lấy từ `dr_infra.replica_commands`:

```sh
aws dynamodb update-table --region ap-southeast-1 --table-name <Table> --stream-specification StreamEnabled=true,StreamViewType=NEW_AND_OLD_IMAGES
aws dynamodb update-table --region ap-southeast-1 --table-name <Table> --replica-updates '[{"Create":{"RegionName":"ap-northeast-1"}}]'
aws dynamodb update-continuous-backups --region ap-northeast-1 --table-name <Table> --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true
aws s3api put-bucket-versioning --bucket <frontend bucket> --versioning-configuration Status=Enabled
aws s3api put-bucket-replication --bucket <frontend bucket> --replication-configuration '<role + đích Tokyo>'
aws s3 sync s3://<frontend bucket> s3://<bucket Tokyo> --exclude "public/catalog"
```

Bảng metadata được truyền vào stack điều khiển qua tham số, nên không gây drift. Bucket frontend thuộc stack điều khiển, nhưng template của nó không khai báo versioning hay replication. Khi phát hành control plane lần tới, nên thêm `VersioningConfiguration` và `ReplicationConfiguration` vào template để hai thuộc tính này được quản lý bằng mã.

Frontend (upload lên bucket chính, CRR tự sao chép sang Tokyo, có invalidation): `public-preview.js`, `rum.js`, `vendor/aws-rum-web/cwr.js`, `index.html` (thêm một thẻ `<script type="module" src="rum.js">`), `rum-config.json`.

## 7. Chi phí ước tính thêm

| Hạng mục | USD/tháng |
|---|---|
| Canary 10 phút/lần (≈ 4.320 lượt × 0,0012) | ≈ 5,2 |
| DynamoDB bản sao (ghi sao chép, lưu trữ 4,5 MB, PITR) | < 1 |
| S3 Tokyo, CRR, Lambda snapshot, Scheduler | < 0,5 |
| RUM (1 USD / 100.000 sự kiện) | < 1 |
| Step Functions chaos (chỉ khi chạy) | ≈ 0 |

## Tái hiện

```sh
python scripts/dr_infra.py && python scripts/experience_infra.py && python scripts/chaos_infra.py
python scripts/replication_lag.py --table <Table> --count 20 --out lag.json
python scripts/chaos_probe.py --seconds 420 --out probe.json   # rồi start-execution với output StartInput của cloudhub-chaos
```
