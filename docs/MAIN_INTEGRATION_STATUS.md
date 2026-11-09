# Chốt tích hợp main — 09/11/2026

Phạm vi: kiểm commit/nhánh và tích hợp mã nguồn CloudHub. Thời gian kiểm tra theo Asia/Bangkok (UTC+07). Không triển khai AWS hoặc thay đổi dữ liệu, ngân sách, IAM, DNS hay feature gate trong lượt này.

## Nhánh và lịch sử đã kiểm

Repository: https://github.com/tuhitomi/cloudhub1. Main khi bắt đầu kiểm: `76caaccaf94af7544bd51638a4f736c88364a312`.

| Phần | Commit/nhánh đã kiểm | Kết quả |
|---|---|---|
| TV1 | `TV1` — `6b83c8886588761b95bfab6260c77d5a774f3152` | Đã nằm trong main qua PR #1, merge `5974c5054fed0b85236432e4a2abbb0a33b1621b` |
| TV2 | `8a0e1487afca7aa9bc38c29657caabcd9a9ff645` | Đã tích hợp qua merge `fb9ef98ddc698de2b986c21583c0cc078c0206c9` |
| TV3 | `Tv3` — `f6b94932aad88c65941e6f0f82a4163956b13453` | Đã nằm trong main qua merge `76caaccaf94af7544bd51638a4f736c88364a312` |
| TV4 | `2323ef8aef2ab494ab88748714cfa1b776b90826`, `e3d4d45afd5e1cdfa7e200cc316ba47b6e225e60` | Đã nằm trong main |

Không còn PR mở tại thời điểm đọc GitHub. Các đầu nhánh remote đều là ancestor của main; không tạo merge rỗng, không cherry-pick trùng, không sửa tác giả/ngày hoặc force-push. Commit thành viên và nội dung runtime được giữ lại.

## Điều chỉnh chốt nguồn

- Khôi phục `backend/requirements.txt` (`boto3==1.43.110`), khớp requirements-dev và packager. File này bị mất khi revert commit khởi tạo; `package_console.py` vẫn cần nó để kiểm phiên bản SDK trước khi đóng gói.
- CI bỏ chế độ cho qua khi thiếu module; chạy hồi quy TV4 và toàn bộ Python/frontend/OpenAPI/IaC, lưu JSON kết quả làm artifact.
- Release checker không còn tham chiếu thư viện/thư mục tạm riêng trên máy tác giả. Dùng thư mục tạm của Python, credentials giả, chặn transport AWS và kết nối bên ngoài trước khi discover test; chỉ cho HTTP loopback của fixture. Ba test mới bảo vệ các ranh giới này.
- Ownership chuyển sang bắt buộc đủ file hoạt động. Giữ việc thành viên đã loại bỏ bốn tài liệu kế hoạch cũ trong commit `91802ab1d2e1cdb2578c23130fcc6099ebb0e178`; chuyển metadata của chúng sang `retired_files`, không khôi phục các tài liệu lỗi thời.
- Cập nhật README, hướng dẫn kiểm thử/demo và bảng file cho trạng thái đã tích hợp. Bằng chứng TV4 ngày 04/11 được giữ nguyên; không đổi fixture cũ thành lần kiểm AWS mới.

## Kiểm tra và kết quả

Kết quả cuối, thời điểm và nguồn được ghi trong `main-integration-results.json`; hash nguồn ở `main-integration-manifest.json`. Manifest có base commit và SHA từng file, tránh tham chiếu vòng tới SHA của chính commit chứa manifest. `ready_for_native_review` chỉ cho phép bước review triển khai tiếp theo, không phải AWS PASS.

| Kiểm tra đã chạy | Kết quả local trên checkout |
|---|---|
| Ownership | 343/343 file hoạt động có owner; 0 thiếu, 0 chưa phân công |
| Toàn bộ Python | 549 test đạt; 0 lỗi, 0 thất bại, 0 bỏ qua |
| Hồi quy TV4 | 152 test đạt, nằm trong tổng Python trên |
| Toàn bộ frontend | 229 test DOM/mock đạt, 0 bỏ qua |
| Cú pháp/locale | 200 file Python, 61 JavaScript, 44 JSON; 8 locale × 1.244 khóa |
| OpenAPI | Schema hợp lệ |
| CloudFormation lint | 7 biến thể đạt, không lỗi chặn hoặc cảnh báo |
| Manifest nguồn | 219 file, 0 nguồn còn thiếu; chưa triển khai AWS |
| Đóng gói backend offline | ZIP 16.841.541 byte, CRC hợp lệ; không upload hoặc đưa ZIP vào Git |

Nguồn hiện tại chạy trực tiếp, 0 file hỗ trợ bên ngoài. Vòng đầy đủ ghi nhận 0 lần thử kết nối bên ngoài và hai kết nối loopback từ fixture download/traversal; không có lời gọi AWS. Các lần cố gọi SDK/mạng trong ba unit test mới được chặn và xác minh ngay trong fixture riêng. Môi trường local: Python 3.13, Node.js 24; CI chạy Python 3.13/Node.js 22 trên Linux.

Lệnh tái hiện sau khi cài Node.js 22+/Python 3.13:

```sh
npm ci --ignore-scripts
python -m pip install -r requirements-dev.txt
python scripts/check_team_ownership.py
python scripts/check_local.py
python scripts/check_tv4.py --out tv4-checks.private.json
python scripts/check_product_release.py --out main-checks.private.json
```

Mỗi lệnh kiểm thử dùng trực tiếp mã của checkout; không dùng support source hoặc thay module bằng bộ nguồn khác. Python tests vẫn dùng mock/SDK Stubber; frontend dùng DOM/mocked API. Không cộng suite TV4 vào tổng Python vì nó đã nằm trong tổng.

OpenAPI và IaC được kiểm cấu trúc/lint, chưa chứng minh IAM hoặc dịch vụ thật. Ba biến thể control-plane và T02/T07 standard/files có lint riêng; T01–T09 còn có test cấu trúc và vòng đời mock trong suite. Không suy rộng thành mọi cấu hình/Region đã được nghiệm thu AWS.

## Đóng gói, triển khai và quay lại

Đã khôi phục đầu vào đóng gói; source manifest không chứa cấu hình thật, credentials hoặc artifact ZIP. Đóng gói offline bằng `package_console.py` cần dependency đúng phiên bản và bucket artifact riêng do operator chỉ định; không tự upload. Trước khi phát hành AWS: kiểm danh tính, Region, inventory/operation, giá, ledger/Billing và ngân sách hiện tại, rồi lập change set/rollback và đối chiếu artifact thực.

Phép thử đóng gói dùng tên bucket placeholder `cloudhub-local-validation-artifacts` để sinh tham chiếu local, không tạo/đọc bucket. SHA256 của ZIP: `168670dca7a31b35aad065ac69c8aa9082b70fcabb25afe223f57754488e95df`. Đây là artifact kiểm đóng gói, chưa có cấu hình deployment được duyệt và chưa được tải lên AWS.

Lượt này chỉ thay công cụ kiểm tra, CI, metadata và tài liệu cùng file pin dependency. Không migration database hoặc thay hợp đồng runtime; không reset ledger. Nếu cần quay lại phần chốt nguồn, tạo commit revert có review, giữ các merge của thành viên và worker tương thích schema hiện có. Không đổi về worker cũ thiếu guard hoặc xóa dữ liệu để rollback.

## Giới hạn

Chưa đối chiếu code phục vụ tại cloudhub1.me với revision main này; chưa đăng nhập website hoặc chạy vòng đời AWS, đo p95/20 người dùng, kiểm credits, kiểm dữ liệu restore thật hoặc kiểm trực quan mobile trong lượt này. Không tạo tài nguyên thử, không phát sinh một đợt triển khai AWS mới. Các feature gate tiếp tục do runtime/capability hiện có quyết định.

Main được chốt ở mức tích hợp nguồn và kiểm tra local. Nghiệm thu/phát hành AWS là bước riêng với cấu hình và bằng chứng mới; không gọi toàn bộ dự án AWS đã hoàn tất từ kết quả CI.
