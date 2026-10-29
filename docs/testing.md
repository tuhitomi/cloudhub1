# Kiểm thử

## Phần đang chạy được

`python scripts/check_team_ownership.py` kiểm mỗi file hiện có có đúng một owner, đồng thời đếm phần đang chờ tích hợp theo phân công v2.

`python scripts/check_local.py` kiểm cú pháp Python/JavaScript, JSON, đủ khóa và placeholder của tám locale, rồi chạy bốn suite Node: i18n, cockpit, shell-view và template-view. Các bước này không import runtime AWS hoặc tạo tài nguyên. `check_leader_handoff.py` được giữ làm lệnh tương thích và gọi cùng checker.

Kết quả lần chạy gần nhất nằm trong `local-check-results.json`. Phạm vi này chưa phải kiểm thử toàn ứng dụng hoặc một vòng AWS. Lịch sử nguồn và các kết quả cũ nằm trong `source-record.json`.

## Kiểm tra đầy đủ sau khi tích hợp

Một số suite hiện cần module từ API, auth, lifecycle hoặc driver chưa có trên nhánh. Khi đã đủ mã và dependencies:

```sh
python -m unittest discover -s tests -v
npm run test:frontend
python scripts/validate_locales.py
```

Chỉ ghi PASS sau khi chạy thật. Báo riêng test bị bỏ qua, thiếu dependency hoặc lỗi môi trường. Unit/DOM không chứng minh owner trên API thật, độ trễ AWS hoặc dữ liệu khôi phục.

## Nghiệm thu AWS

Chỉ dùng tài nguyên thử đã được duyệt, kiểm lại account/Region, quota, ledger, inventory và ngân sách trước mỗi vòng. Đối chiếu theo từng mẫu/profile/Region và phiên bản: tạo → truy cập/ghi → backup → thu hồi/audit → restore → đọc/checksum → dọn.

Giữ nguồn khi backup bắt buộc lỗi; phân biệt deleted, retained, residual, unknown và billable. Chỉ công bố số đo hiệu năng với phép đo phù hợp, bao gồm lỗi/throttling. Không dùng trạng thái stack hoặc mock để thay bằng chứng dữ liệu.
