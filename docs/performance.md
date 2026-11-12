# Hiệu năng truy cập và phân phối

Đo ngày 12/11/2026 từ một máy khách tại Việt Nam, 20 yêu cầu tuần tự mỗi điểm cuối, mỗi yêu cầu mở kết nối TLS mới. Đây là số đo trước khi áp dụng các thay đổi trong tài liệu này; số đo sau khi triển khai cần ghi lại theo cùng cách đo.

| Điểm cuối | p50 | p95 | Quan sát |
|---|---|---|---|
| `GET https://cloudhub1.me/` | 1.322 ms | 2.812 ms | Edge `HIO52` (Oregon); TCP 280 ms; `X-Cache: Miss`; HTML 33 KB không nén |
| `GET /public/catalog` | 434 ms | 2.246 ms | JSON 16.385 byte không nén (gzip: 994 byte); ngoại lai do cold start |
| `GET /ui-context` | 283 ms | 1.282 ms | Đạt mục tiêu 2 s |

## Nguyên nhân

1. **Edge xa người dùng.** Distribution dùng `PriceClass_100` (chỉ Bắc Mỹ và châu Âu), nên người xem ở châu Á được phục vụ từ Mỹ.
2. **Edge gần như không cache.** Đối tượng S3 mang `Cache-Control: no-cache, max-age=0`. Với `CachingOptimized` (MinTTL 1 s), mọi yêu cầu đều quay về S3 Singapore (`RefreshHit`/`Miss`). `index.html` dùng `CachingDisabled` nên còn không được nén.
3. **API không nén JSON và tính lại catalog mỗi lần.** HTTP API không tự nén; `/public/catalog` đọc lại giá và chính sách Region cho mỗi yêu cầu ẩn danh.
4. **Cold start.** Import `boto3`/`botocore` cùng mã backend diễn ra trong yêu cầu đầu tiên của mỗi môi trường thực thi.

## Thay đổi

| Lớp | Thay đổi | Tệp |
|---|---|---|
| CloudFront (edge stack) | `PriceClass_200` (thêm edge châu Á); cache policy riêng: MinTTL 60 s, MaxTTL 300 s, gzip + brotli, không đưa cookie/query/header vào khóa cache; áp dụng cho asset và `index.html`. `config.js` giữ `CachingDisabled`. | `scripts/performance_infra.py`, `scripts/hosting.py` |
| Lambda API | Nén gzip mọi phản hồi JSON từ 1 KiB khi client gửi `Accept-Encoding: gzip` (`Vary: Accept-Encoding`). | `backend/cloudhub/api.py` |
| `/public/catalog` | Cache 60 s trong môi trường thực thi đang ấm, khóa theo query; `Cache-Control: public, max-age=60`; lỗi không cache và giữ `no-store`. Tắt bằng `PUBLIC_CATALOG_CACHE_SECONDS=0`. | `backend/cloudhub/api.py` |
| Cold start | Handler mới `cloudhub.api_entry.handler` import SDK trong pha init; `AutoPublishAlias: live`; tham số `ApiSnapStart` (mặc định `Disabled`). | `backend/cloudhub/api_entry.py`, `scripts/performance_infra.py` |
| Bảo vệ API | Throttling stage: mặc định burst 200 / rate 100 rps; `GET /public/catalog` burst 50 / rate 25 rps. | `scripts/performance_infra.py` |
| Quan sát | Alarm p95 `AWS/ApiGateway Latency` và `AWS/Lambda Duration` > 2 s (2/3 chu kỳ 5 phút) gửi về `AlertTopic`; thêm widget thời gian chạy, concurrency và throttle trên dashboard. | `scripts/performance_infra.py` |

Account data vẫn `no-store`. Bộ cache catalog chỉ chứa phép chiếu công khai đã có từ trước, không chứa owner, quote hay dữ liệu tài khoản.

## Chi phí và đánh đổi

- `PriceClass_200`: giá truyền dữ liệu từ edge châu Á cao hơn Bắc Mỹ, nhưng trang chủ và asset chỉ khoảng vài trăm KB mỗi lượt xem nên chênh lệch không đáng kể. Bảng giá T02 (`PriceClass_100`) của môi trường người dùng không thay đổi.
- Edge TTL 60 s: sau một lần phát hành, edge có thể phục vụ bản cũ tối đa 60 s (tối đa 300 s nếu origin đặt `max-age` dài). Muốn hiển thị ngay thì tạo invalidation `/*` sau khi `s3 sync`.
- SnapStart cho Python tính phí lưu snapshot và mỗi lần khôi phục, ước khoảng 6 USD/tháng ở 1.536 MB. Vì vậy mặc định tắt. Bật bằng `ApiSnapStart=Enabled` khi nhóm chấp nhận chi phí. Mã khởi tạo không tạo client AWS, không đọc credentials và không mở kết nối, nên an toàn khi khôi phục snapshot.
- Throttling HTTP API áp dụng cho cả tài khoản trên mỗi route, không theo IP. Chặn theo IP cần AWS WAF, chưa nằm trong thay đổi này.

## Triển khai

1. Sinh template: `python scripts/generate_infra.py`. Stack edge dùng `configure_edge` qua quy trình hosting hiện có.
2. Tạo change set cho stack control plane và stack edge; kiểm tra rằng chỉ có `ApiFunction` (handler, alias, version), `HttpApi` stage, hai alarm, dashboard, `FrontendEdgeCachePolicy` và `FrontendDistribution` thay đổi.
3. Sau khi thực thi: `aws cloudfront create-invalidation --distribution-id <id> --paths "/*"`.

## Kiểm tra sau triển khai

```sh
curl -sI -H 'Accept-Encoding: gzip, br' https://cloudhub1.me/ | grep -iE 'x-amz-cf-pop|x-cache|content-encoding'
curl -s -o /dev/null -H 'Accept-Encoding: gzip' -w '%{size_download} %{time_total}\n' https://api.cloudhub1.me/public/catalog
curl -sI https://api.cloudhub1.me/public/catalog | grep -iE 'cache-control|x-cloudhub-cache'
```

Kỳ vọng: POP của edge là một địa điểm châu Á (ví dụ `HAN`, `SGN`, `SIN`); lần gọi thứ hai trả `X-Cache: Hit from cloudfront`; `/public/catalog` trả `content-encoding: gzip` và khoảng 1 KB; `x-cloudhub-cache: HIT` khi gọi lại trong 60 giây. Chạy lại phép đo 20 yêu cầu ở đầu tài liệu và ghi kết quả sau triển khai vào bảng.

Kiểm thử cục bộ: `python -m unittest tests/test_performance.py`.
