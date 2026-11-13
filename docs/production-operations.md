# Vận hành production: đo tải, khôi phục dữ liệu, giám sát SLO và bảo mật

Thực hiện ngày 12/11/2026 trên tài khoản production (Singapore, stack điều khiển `cloudhub-pages-live`). Không thay đổi stack điều khiển; mọi thứ mới nằm trong stack riêng hoặc là cấu hình của tài nguyên không thuộc stack đó.

## 1. CDN gần người dùng (stack `cloudhub-shared-edge`)

Change set: `PriceClass_100 → PriceClass_200` và cache policy `FrontendEdgeCachePolicy` (TTL 60–300 s, gzip/brotli) cho asset và `index.html`; `config.js` vẫn không cache. `Modify FrontendDistribution` (không thay thế) + `Add` một cache policy.

| Trang chủ, 20 lượt tuần tự từ Việt Nam | Trước | Sau |
|---|---|---|
| Edge | HIO52 (Oregon) | SGN50 (TP.HCM) |
| TCP connect p50 | ~280 ms | 145 ms |
| Kích thước | 33.358 B, không nén | 7.431 B, brotli |
| Cache | Miss mọi lần | Hit (Age tăng dần) |
| p50 / p95 | 1.322 / 2.812 ms | **531 / 1.326 ms** |

### HTTP/3 và header bảo mật (đợt 2, ngày 13/11)

`tune_distribution` thêm:

- `HttpVersion: http2and3`. Trình duyệt hỗ trợ QUIC sẽ dùng HTTP/3 (bắt tay gộp TCP và TLS, chịu mất gói tốt hơn trên mạng di động); các trình duyệt khác vẫn dùng HTTP/2.
- Response headers policy `FrontendSecurityHeaders`, thay cho policy có sẵn `SecurityHeadersPolicy` của AWS:
  - HSTS 2 năm, có `includeSubDomains; preload`. Giữ `X-Content-Type-Options`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy` và `X-XSS-Protection`.
  - `Content-Security-Policy-Report-Only`: chỉ cho phép script và style từ `'self'`, không `unsafe-inline` hay `unsafe-eval`, `object-src 'none'`, `frame-ancestors 'self'`. `connect-src` gồm API, Cognito, S3 và WebSocket Session Manager. Frontend không có script, style hay event handler inline nên CSP chặt vẫn chạy được. Sau khi console trình duyệt không còn vi phạm thì chuyển `enforce_csp=True`.
  - `Permissions-Policy`: tắt camera, micro, định vị, thanh toán, USB. Thêm `Cross-Origin-Opener-Policy: same-origin`.
  - `Server-Timing` (lấy mẫu 100 %): DevTools hiện thời gian xử lý tại CloudFront, cache hit/miss và độ trễ origin cho từng request.

Change set chỉ gồm `Modify FrontendDistribution` (không thay thế) và `Add FrontendSecurityHeaders`. Đã thực thi ngày 13/11.

Kiểm chứng sau khi thực thi:

- `Alt-Svc: h3=":443"; ma=86400`. Trình duyệt dùng `h2` ở lần tải đầu, sau đó chuyển sang `h3` (`PerformanceNavigationTiming.nextHopProtocol`).
- Có đủ các header HSTS preload, CSP report-only, Permissions-Policy, COOP và Server-Timing (ví dụ `cdn-pop;desc="HAN51-P1"`, `cdn-upstream-connect;dur=71`, `cdn-upstream-fbl;dur=129`). Edge phục vụ là HAN51 (Hà Nội).
- Khi tải trang và mở hộp thoại tư vấn, cấu hình: không có sự kiện `securitypolicyviolation` nào. Console chỉ báo `upgrade-insecure-requests` bị bỏ qua ở chế độ report-only; code đã sửa để chỉ thêm chỉ thị này khi CSP chuyển sang chế độ chặn.
- Trang vẫn hiển thị đủ 9 mẫu; `/ui-context`, API và catalog trả 200.

### Quota Lambda

Đã gửi yêu cầu tăng `Concurrent executions` của Lambda ở ap-southeast-1 từ 10 lên 1.000 qua Service Quotas (case 179452889900816, miễn phí). AWS duyệt lúc 11:39 ngày 13/11/2026; `get-account-settings` trả `ConcurrentExecutions: 1000`. Tham số `AccountConcurrencyLimit` của stack `cloudhub-observability` cập nhật lên 1.000 bằng change set `raise-concurrency-quota` (chỉ `Modify ConcurrencyAlarm`). Kết quả thử tải sau khi tăng quota ở mục 2.1.

## 2. Thử tải 20 người dùng đồng thời

`loadtest`: 20 người dùng ảo, giữ kết nối như trình duyệt, nghỉ 0,5 s giữa các request, 120 s, trộn 40 % `/public/catalog`, 30 % `/ui-context`, 30 % trang chủ. Tổng 3.499 request, 28,9 request/s.

| Điểm cuối | Thành công | p50 | p95 | p99 |
|---|---|---|---|---|
| Trang chủ (CloudFront) | 1.133/1.133 | 93 ms | 589 ms | 1.020 ms |
| `GET /ui-context` | 1.025/1.026 (1 × 503) | 112 ms | 472 ms | 1.030 ms |
| `GET /public/catalog` | **609/1.340 (731 × 429)** | 185 ms | 1.021 ms | 2.795 ms |

**Phát hiện**

1. **`GET /public/catalog` bị throttle ở mức 5 request/s, burst 10** (route setting của stage `$default`). Đây là giới hạn chung cho mọi khách, mà mỗi lượt mở trang chủ đều gọi catalog, nên khoảng 5 khách/giây đã gặp 429.
2. **Lambda concurrency của cả tài khoản chỉ là 10** (`AccountLimit.ConcurrentExecutions`), mức mặc định của tài khoản mới (bình thường là 1.000). Bốn function dùng chung 10 suất; khi đầy, API trả 503.

**Khắc phục đề xuất**

- Gửi yêu cầu tăng quota Lambda concurrent executions qua Service Quotas (miễn phí; AWS thường duyệt khi tài khoản đã xác minh xong).
- Đưa `/public/catalog` qua cache: mã của PR #2 đã có cache 60 s trong Lambda và `Cache-Control: public, max-age=60`. Cách triệt để hơn là route `/public/catalog` qua CloudFront với TTL 60 s, khi đó API chỉ nhận tối đa khoảng 1 request/phút cho mỗi POP. Sau đó nâng throttle của route lên 25–50 request/s qua quy trình phát hành của stack điều khiển.

## 2.1 Thử tải tăng dần sau khi tăng quota (tự co giãn)

`python scripts/load_ramp.py --stages 10,25,50,100 --seconds 90`, chạy ngày 13/11/2026 từ 11:40 đến 11:47 (giờ Việt Nam), sau khi quota tăng lên 1.000. Mỗi mức gồm N người dùng ảo giữ kết nối, nghỉ 0,5 s giữa các request, chạy 90 s; mức sau bắt đầu sau 20 s nghỉ. Lưu lượng trộn 50 % `/ui-context`, 40 % trang chủ, 10 % `/public/catalog`. Kết quả gốc nằm trong `docs/loadtest/ramp-2026-11-13.json`.

| Người dùng | Request | Thông lượng | Lỗi 5xx | `/ui-context` p50 / p95 | Trang chủ p50 / p95 | Lambda concurrency (max/phút) |
|---|---|---|---|---|---|---|
| 10 | 1.380 | 15,3 req/s | 0 | 128 / 305 ms | 108 / 302 ms | 5–8 |
| 25 | 3.483 | 38,4 req/s | 0 | 118 / 297 ms | 108 / 283 ms | 14–17 |
| 50 | 6.910 | 76,2 req/s | 0 | 124 / 298 ms | 109 / 239 ms | 19–22 |
| 100 | 13.370 | **147,2 req/s** | **0** | 150 / 345 ms | 113 / 304 ms | 25–30 |

Tổng cộng 25.143 request trong khoảng 7 phút. Không có request nào lỗi 5xx hoặc timeout, và CloudWatch ghi nhận `Throttles = 0`.

**Nhận xét**

- **Lambda tự co giãn theo tải.** Số môi trường chạy song song tăng từ 5 lên 30 khi tải tăng 10 lần, không cần cấu hình thêm. Mức đỉnh 30 gấp 3 lần quota cũ: trước khi tăng quota, mức 25 người dùng trở lên sẽ bị trả 503.
- **Thông lượng tăng gần tuyến tính** (15 → 147 req/s, gấp 9,6 lần khi tải gấp 10 lần), trong khi p95 của `/ui-context` gần như giữ nguyên (khoảng 300 ms, lên 345 ms ở 100 người dùng). Mỗi môi trường xử lý khoảng 5 req/s; tải 100 người dùng chỉ dùng 3 % quota mới.
- **`/public/catalog` vẫn bị throttle có chủ đích** ở 5 req/s: không có 429 ở mức 10 và 25 người dùng, 239/699 request bị 429 ở mức 50 và 813/1.279 ở mức 100. Đây là giới hạn của route trong stack điều khiển, không phải giới hạn của Lambda. Cần tăng lên 25 req/s (`PUBLIC_ROUTE_RATE` trong `scripts/performance_infra.py`) khi phát hành stack điều khiển.

## 3. Diễn tập khôi phục dữ liệu (DynamoDB PITR)

Bảng metadata: 2.970 item, 4,5 MB, on-demand, đã mã hóa, PITR đã bật (35 ngày).

| Bước | Kết quả |
|---|---|
| Lệnh restore (latest restorable time) sang bảng mới | 21:07:04 |
| Điểm khôi phục | 21:02:06, nên **RPO ≈ 5 phút** (độ trễ của PITR) |
| Bảng mới ACTIVE, kèm GSI `by_owner` | **RTO = 255 s** |
| Đối chiếu `pk` + `version` | **2.970/2.970 khớp**, 0 khác biệt |
| Dọn dẹp | Xóa bảng diễn tập |

Sau diễn tập: bật **Deletion Protection** cho bảng production (trước đó đang tắt). Bảng không do stack quản lý trực tiếp (được truyền vào qua tham số `Table`), nên không gây drift.

RTO trên chỉ tính phần dữ liệu. Để chuyển ứng dụng sang bảng mới còn cần cập nhật tham số `Table` của stack điều khiển (một change set).

## 4. Giám sát và SLO

**`cloudhub-observability`** (Singapore, `infra/observability/regional.json`):

- Dashboard `cloudhub-observability-slo`: tỷ lệ khả dụng 30 ngày và error budget còn lại; request, 4xx, 5xx; latency p50/p95/p99 và integration latency; Lambda concurrency so với quota tài khoản, throttle, duration, error theo function; DynamoDB RCU/WCU/throttle; Step Functions started/succeeded/failed/time; CloudFront request và error rate.
- **SLO:** 99,5 % request API không lỗi 5xx trong 30 ngày, tức error budget 0,5 %.
- **Burn-rate alarm** đa cửa sổ (Google SRE workbook): 1 giờ > 14,4 (tiêu 2 % budget/giờ) và 6 giờ > 6. Composite alarm `slo-page` gom hai alarm này với alarm concurrency > 80 % quota.
- Alarm riêng cho latency p95 > 2 s, Lambda throttle, DynamoDB throttle, workflow thất bại. Tất cả gửi về `AlertTopic` hiện có.

**`cloudhub-healthchecks`** (us-east-1, `infra/observability/global-checks.json`):

- Route 53 health check HTTPS 30 giây/lần cho `https://cloudhub1.me/` và `https://api.cloudhub1.me/ui-context`, từ Singapore, Tokyo, N. Virginia và Ireland. Tất cả đang `200 OK`. Mỗi Region phân giải ra edge CloudFront khác nhau (ví dụ 13.35.163.x ở Singapore, 3.162.140.x ở Ireland), cho thấy CDN đang phục vụ theo vị trí địa lý.
- Alarm khi check fail (2/3 phút) và khi CloudFront 5xx > 1 %. Topic `GlobalAlerts` gửi email; người nhận cần bấm xác nhận đăng ký trong email AWS.

Chi phí ước tính: 2 health check HTTPS khoảng 3,5 USD/tháng; khoảng 12 alarm 1,2 USD/tháng; dashboard 3 USD/tháng (3 dashboard đầu miễn phí).

## 5. Bảo mật tài khoản

Hiện trạng: root đã có MFA và không có access key. Chưa có IAM user, password policy, CloudTrail trail, AWS Config hay Access Analyzer. GuardDuty và Security Hub trả `SubscriptionRequiredException` vì tài khoản đang được AWS xác minh.

Đã triển khai stack `cloudhub-security-baseline` ngày 13/11/2026 từ `infra/security/baseline.json` (`scripts/security_baseline_infra.py`). Trail `IsLogging=true`, `IsMultiRegionTrail=true`, `LogFileValidationEnabled=true`; Access Analyzer `ACTIVE`; 5 alarm CIS gửi về `AlertTopic`. Stack gồm:

- CloudTrail ghi mọi Region, có xác thực tính toàn vẹn log. Bucket S3 mã hóa, chặn public, chỉ cho TLS, versioning, xóa sau 1 năm.
- Log đẩy vào CloudWatch Logs (lưu 90 ngày), kèm alarm theo CIS 4.1–4.5: dùng root, đăng nhập console không MFA, gọi API trái phép, sửa IAM policy, sửa CloudTrail.
- IAM Access Analyzer phạm vi tài khoản.

Lệnh đã dùng để triển khai (cần quyền tạo IAM role và CloudTrail):

```sh
aws cloudformation deploy --region ap-southeast-1 --stack-name cloudhub-security-baseline \
  --template-file infra/security/baseline.json --capabilities CAPABILITY_IAM \
  --parameter-overrides AlertTopicArn=<AlertTopic ARN>
```

Việc nên làm thêm: tạo người dùng IAM Identity Center thay cho root; đặt password policy; bật GuardDuty và Security Hub (AWS Foundational Security Best Practices) khi tài khoản xác minh xong.

## Tái hiện

```sh
python scripts/observability_infra.py      # infra/observability/*.json
python scripts/security_baseline_infra.py  # infra/security/baseline.json
```
