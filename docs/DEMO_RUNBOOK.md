# Kịch bản trình diễn TV4

## Chuẩn bị

Giữ T01–T09, ba Region và tám locale hiện có. Không bật feature gate chỉ vì local PASS. Đọc owner, quote, quota, ledger và inventory; với AWS thật phải kiểm lại account, Region, quyền và ngân sách hiện tại. Không tạo EC2/RDS hoặc chạy tải chỉ để có ảnh trình diễn.

## Phần local có thể lặp lại

```sh
npm ci --ignore-scripts
python -m pip install -r requirements-dev.txt
python scripts/check_team_ownership.py
python scripts/check_local.py
python -m unittest discover -s tests -p test_tv4_release_tools.py -v
python scripts/check_tv4.py --out tv4-checks.private.json
python scripts/check_product_release.py --out main-checks.private.json
```

Main đã có đủ mã của các thành viên và chạy trực tiếp, không cần `--support-source`. Thiếu module trên một checkout cũ vẫn trả BLOCKED và mã thoát 2; không đổi tên kết quả thành PASS. Chỉ khi nghiên cứu bản nguồn chưa tích hợp mới dùng chế độ fixture riêng:

```sh
python scripts/check_tv4.py --support-source /path/to/complete/team/source --out /path/outside/repository/tv4-fixture.json
```

Phải cài requirements-dev.txt hoặc chọn thư mục SDK local qua `--deps`. Kết quả này mang scope LOCAL_SUPPORT_FIXTURE và ghi SHA của các file hỗ trợ; không chứng minh clone public đã chạy độc lập hoặc tài khoản AWS có quyền.

Cho người xem đối chiếu ba ca owner/Region sai ở nhánh MarkFailure: phiên bản trước sửa không chặn, phiên bản đã sửa từ chối mà không thay metadata hoặc resume nguồn. Trình diễn thêm callback cũ, request trùng, schedule_pending và sao lưu lỗi giữ nguồn bằng các test tương ứng.

## Vòng AWS khi đủ điều kiện

1. Đăng nhập bằng tài khoản thử hiện có; chọn mẫu/profile/Region đang mở, lấy quote mới và xác nhận. Ghi operation ID và thời gian trả ID riêng với thời gian hạ tầng sẵn sàng.
2. Truy cập địa chỉ/hướng dẫn kết nối; ghi một marker dữ liệu và SHA. Đọc trạng thái thực, không chỉ stack UPDATE_COMPLETE.
3. Với mẫu hỗ trợ, gia hạn hoặc đổi chế độ đã được phép; kiểm resource ID và dữ liệu không thay, callback cũ không tác động.
4. Sao lưu; đọc recovery point, phạm vi và hạn giữ. Chỉ fault-inject ở fixture/tài nguyên thử được duyệt; backup lỗi phải giữ nguồn.
5. Kết thúc theo consent, kiểm inventory deleted/retained/residual/unknown/billable. Tài nguyên giữ lại có thể còn phí.
6. Khôi phục thành môi trường mới, dùng quote/quota hiện tại; đọc lại marker/SHA từ đích. Phân biệt hạ tầng sẵn sàng và dữ liệu đã kiểm.
7. Dọn đúng môi trường thử và bản sao được phép, kiểm lại schedule/stack/tài nguyên giữ lại và ledger. Giữ bằng chứng đúng mẫu/profile/Region/artifact.

Lượt chốt nguồn main ngày 09/11/2026 không thực hiện vòng AWS trên. Chỉ tiêu API đọc p95 dưới 2 giây với 20 người dùng, trả operation ID dưới 2 giây, kích hoạt hết hạn trong 2 phút và sweep mỗi 5 phút cần phép đo AWS riêng; unit test không chứng minh các chỉ tiêu đó.

## Chuẩn bị manifest

```sh
python scripts/prepare_product_release.py --results tv4-checks.private.json --out source-manifest.private.json
```

Manifest kiểm nguồn khớp kết quả test, ghi file thiếu và giữ aws_deployed=false. Bản kiểm nguồn hiện tại ở main-integration-manifest.json; không ghi đè manifest fixture lịch sử. Kết quả fixture không mở gate đóng gói. Khi đã đủ nguồn, test native và review mục tiêu, công cụ packet yêu cầu thêm `--deployment-target` chứa account_id, primary_region và stack_name được duyệt; không còn account production mặc định.

Fingerprint nguồn tuần 10 dùng UTF8_LF_SHA256 để Windows CRLF và Git LF không gây drift giả. SHA của dữ liệu người dùng, bản sao và ZIP triển khai vẫn tính trên byte thật; không áp dụng chuẩn hóa này cho tệp dữ liệu.
