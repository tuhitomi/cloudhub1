# Kiểm thử

## Phần đang chạy được

`python scripts/check_team_ownership.py` kiểm mỗi file hiện có có đúng một owner và không thiếu file trong phân công v2 đang hoạt động. Bốn tài liệu kế hoạch đã bị revert được lưu ở `retired_files`, không tính là module ứng dụng.

`python scripts/check_local.py` kiểm cú pháp Python/JavaScript, JSON, đủ khóa và placeholder của tám locale, rồi chạy bốn suite Node: i18n, cockpit, shell-view và template-view. Các bước này không import runtime AWS hoặc tạo tài nguyên. `check_leader_handoff.py` được giữ làm lệnh tương thích và gọi cùng checker.

Kết quả tích hợp mới nằm trong `main-integration-results.json`; `local-check-results.json`, `source-record.json` và các file `tv4-*` giữ bằng chứng cũ đúng ngày/phạm vi. Không dùng kết quả lịch sử thay cho lần chạy trên revision mới.

## Kiểm tra đầy đủ trên main

Các module API, auth, lifecycle và driver đã có trên main. Python 3.13 và Node.js 22 trở lên:

```sh
python -m pip install -r requirements-dev.txt
npm ci --ignore-scripts
python scripts/check_team_ownership.py
python scripts/check_local.py
python scripts/check_tv4.py --out tv4-checks.private.json
python scripts/check_product_release.py --out main-checks.private.json
```

Release checker chạy toàn bộ Python unittest, toàn bộ Node/DOM suite, OpenAPI, locale và bảy biến thể control-plane/S3 IaC. Nó ẩn profile/session AWS thật, dùng credentials giả, chặn AWS SDK/DNS/socket bên ngoài, cho phép loopback của test download/traversal. Không cần phiên AWS. Không có test hoặc có test bị bỏ qua sẽ không PASS. Các template còn lại có kiểm thử cấu trúc riêng trong suite; bảy lượt lint không phải nghiệm thu mọi tổ hợp mẫu/Region.

Chỉ ghi PASS sau khi chạy thật. Unit/DOM không chứng minh owner trên API thật, độ trễ AWS, chất lượng ảnh giao diện hoặc dữ liệu khôi phục. `--deps /path/to/local/dependencies` là lựa chọn cho thư viện đã cài sẵn; mặc định dùng môi trường Python hiện tại, không đọc thư mục thư viện riêng của máy tác giả.

## Nghiệm thu AWS

Chỉ dùng tài nguyên thử đã được duyệt, kiểm lại account/Region, quota, ledger, inventory và ngân sách trước mỗi vòng. Đối chiếu theo từng mẫu/profile/Region và phiên bản: tạo → truy cập/ghi → backup → thu hồi/audit → restore → đọc/checksum → dọn.

Giữ nguồn khi backup bắt buộc lỗi; phân biệt deleted, retained, residual, unknown và billable. Chỉ công bố số đo hiệu năng với phép đo phù hợp, bao gồm lỗi/throttling. Không dùng trạng thái stack hoặc mock để thay bằng chứng dữ liệu.

## Hồi quy TV4

`python -m unittest discover -s tests -p test_tv4_release_tools.py -v` kiểm manifest, source drift, path và gate đóng gói ngay trên checkout hiện tại.

`python scripts/check_tv4.py --out /path/outside/repository/result.json` yêu cầu dependency thật của repo. Thiếu file trả BLOCKED và nonzero. `--support-source` chỉ phục vụ một vòng local fixture được gắn nhãn riêng, ghi SHA từng file hỗ trợ; không đưa các file đó vào commit của TV4.

CI không dùng `--allow-missing-dependencies`: thiếu module sẽ fail. CI lưu hai JSON kết quả ở artifact `local-validation-results`; CI xanh vẫn không chứng minh AWS đã nghiệm thu hoặc code đã triển khai lên website.
