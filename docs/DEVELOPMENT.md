# Hướng dẫn phát triển

## Bắt đầu

Clone `https://github.com/tuhitomi/cloudhub1.git`, cập nhật main rồi tạo nhánh theo thành viên hoặc chức năng. Kiểm tra tên/email Git của chính mình trước khi commit. Nhánh và mã đang làm cần được giữ lại khi đồng bộ, không reset hoặc ghi đè để làm sạch.

```sh
git clone https://github.com/tuhitomi/cloudhub1.git
cd cloudhub1
git switch -c team/tv1
npm ci --ignore-scripts
python scripts/check_team_ownership.py
python scripts/check_local.py
```

Thay `tv1` bằng nhánh phù hợp. Chỉ tạo nhánh mới nếu nó chưa tồn tại. Nếu thiếu Python/Node, cài phiên bản được README yêu cầu. Không cài hoặc đưa dependencies vào Git.

## Kiểm tra và commit

Review `git status --short` và `git diff`. Chọn từng file của đầu việc, dùng `git add -- path/to/file`, rồi `git diff --cached` trước khi commit. Tên commit mô tả thay đổi thật như `fix(api): reject expired quotes` hoặc `docs: update setup instructions`; chỉ dùng nội dung phù hợp thay đổi đã làm.

Không dùng `git add .` khi workspace có dữ liệu phát sinh, cấu hình riêng hoặc công việc của người khác. Không đưa ZIP, binary, credentials, token, URL ký, cấu hình production hoặc log chứa dữ liệu riêng lên repo.

Với GitHub Desktop: clone URL, tạo/chọn nhánh của mình, kiểm từng file trong Changes, commit rồi Push origin và Create Pull Request vào main. File không đổi thì không tạo commit rỗng. Nội dung và ngày Git phản ánh đúng thao tác đang thực hiện.

## Kiểm thử

`check_local.py` chỉ kiểm phần mã hiện có và các suite frontend đủ dependency, không gọi AWS. Sau khi đủ các module và cài dependencies trong `requirements-dev.txt`, chạy thêm Python unit/integration và toàn bộ frontend theo docs/testing.md. Báo rõ test không chạy được và nguyên nhân.

Không chạy script deployment, migration, load test hoặc vòng đời AWS chỉ để kiểm một PR tài liệu. Những tác vụ đó cần config, tài nguyên thử, quyền và ngân sách riêng. Review tác dụng phụ trước khi chạy script.

## Review và đồng bộ

PR nêu vấn đề, hành vi sau thay đổi, kết quả kiểm tra thật và phần chưa xác minh. Thay đổi quote, ledger, quota, lock, backup hoặc cleanup cần owner liên quan review. Không bỏ kiểm tra bảo vệ dữ liệu để làm test qua.

Sau khi lưu công việc của mình, Fetch origin và Update from main trong Desktop; CLI có thể dùng `git fetch origin` rồi `git merge origin/main` trên nhánh riêng. Review xung đột cùng owner, không force push vào main.
