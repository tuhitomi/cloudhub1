# Terminal trên web, đổi loại máy, RDS Multi-AZ và chi phí theo ngày

Bốn tính năng mới. Mỗi tính năng đi qua đúng các lớp có sẵn của CloudHub: kiểm owner và trạng thái ở API, khóa và idempotency, operation chạy trên Step Functions, CloudFormation của chính môi trường, và capability gate theo mẫu × cấu hình × Region.

## 1. Terminal trên web qua AWS Systems Manager Session Manager

Áp dụng cho T01, T05 và T08 (chọn máy 1 hoặc 2).

```
Trình duyệt ──POST /environments/{id}/terminal──► Lambda API ──ssm:StartSession──► SSM
     ▲                                               │ (kiểm owner, READY, ≤ 2 phiên)
     │  {session_id, stream_url, token}  ◄────────────┘
     │
     └──WebSocket wss://ssmmessages.<region>.amazonaws.com──► SSM Agent trên EC2 ──► shell (ssm-user)
```

- **Không SSH key, không mở cổng 22, không bastion.** Instance chỉ cần SSM Agent và instance profile có `ssmmessages:*`, vốn đã có cho các lệnh quản trị của CloudHub.
- **IAM của Lambda API:** `ssm:StartSession` chỉ trên instance có tag `cloudhub:managed=true` và tài liệu shell mặc định `SSM-SessionManagerRunShell` (`ssm:SessionDocumentAccessCheck`). `ssm:TerminateSession` chỉ trên session do chính function này tạo.
- **Token** là token một lần, trả thẳng về trình duyệt của owner và không được lưu. Bảng DynamoDB chỉ ghi `T#<session_id>`: owner, môi trường, instance, thời điểm bắt đầu/kết thúc.
- **Giới hạn:** tối đa 2 phiên đang mở cho mỗi môi trường. Phiên quá 1 giờ không bấm "Đóng phiên" được coi là đã hết, nhả chỗ cho phiên mới. Thời gian rảnh và log phiên (S3/CloudWatch) theo Session Manager preferences của tài khoản.
- **Giao thức** (`frontend/ssm-session.js`): mở WebSocket, gửi `TokenValue`, thực hiện handshake với agent, xác nhận (ack) mọi message, sắp xếp theo `SequenceNumber` và bỏ bản trùng. Mỗi message nhị phân có header 116 byte, `PayloadDigest` là SHA-256 và UUID được ghi đảo hai nửa đúng như session-manager-plugin. Phiên yêu cầu mã hóa KMS bị từ chối rõ ràng; trường hợp đó cần dùng AWS CLI.
- **Màn hình** (`frontend/terminal-screen.js`) xử lý prompt, màu, readline (`\r`, `ESC[K`, di chuyển con trỏ) và lệnh clear. Chương trình toàn màn hình như `vim` hay `top` cần AWS CLI.

## 2. Đổi loại máy EC2 khi đang chạy (T01, T05)

- **Profile mới:** `small` (t3.small, 2 vCPU, 2 GiB RAM, cùng ổ đĩa với cấu hình chuẩn). Profile này cần đơn giá riêng `ec2_hour.t3.small` và bằng chứng AWS như mọi profile khác; thiếu một trong hai thì không mở. Profile `t3.micro` cũ giữ nguyên đơn giá `ec2_hour`. Chiều đổi được là `standard ↔ small`.
- **Vì sao chỉ thêm một loại máy:** mỗi Region lưu toàn bộ bằng chứng kiểm chứng trong một SSM Parameter loại Standard (tối đa 4 KiB). Với 24 cấu hình, shard nặng 3.992 byte. Nếu thêm cả t3.medium và các biến thể ổ 16 GiB thì lên 30 cấu hình (4.976 byte) và vượt giới hạn. Muốn mở thêm loại máy phải chia shard theo mẫu hoặc chuyển sang Advanced tier (8 KiB, có phí).
- **`GET /environments/{id}/resize`:** liệt kê loại máy có **cùng dung lượng root/data** (không đổi đĩa), kèm trạng thái kiểm chứng và chênh lệch chi phí cho phần còn lại của kỳ.
- **`POST /environments/{id}/resize`:** phải gửi đúng `expected_delta_milliusd` vừa xem (đóng vai trò fingerprint của quote), `expected_revision`, `confirmed: true` và `Idempotency-Key`. Chênh lệch dương được giữ chỗ trong ví và ngân sách; khi spend guard đang khóa thì từ chối nâng cấp.
- **Thực thi** (worker, phase `RESIZE`):
  - `UPDATE_STACK`: đọc lại template gốc của stack môi trường, chỉ thay `Instance.InstanceType`, rồi `UpdateStack` với cùng tham số (`UsePreviousValue`) và `ClientRequestToken` theo operation. Nhờ vậy volume dữ liệu, snapshot nguồn khi restore và security group không bị đụng tới.
  - `WAIT_STACK`: chờ `UPDATE_COMPLETE` và đối chiếu loại máy thực tế từ EC2.
  - `READINESS`: dùng lại bước kiểm tra sẵn sàng của driver (EC2 status, SSM online, dữ liệu `/data`), đồng thời cập nhật IP công khai mới.
- Nếu AWS từ chối và CloudFormation đã rollback (`UPDATE_ROLLBACK_COMPLETE`), môi trường quay về `READY` với loại máy cũ và lỗi được ghi ở `last_resize_error`. Các lỗi khác giữ nguồn và chuyển cho quản trị.
- **Quyền:** role CloudFormation của môi trường được thêm `ec2:ModifyInstanceAttribute`, `StopInstances` và `StartInstances`, chỉ trên instance `cloudhub:managed=true`; worker được thêm `cloudformation:GetTemplate`.

## 3. RDS Multi-AZ cho T03 và T04

- **Profile `ha`:** `db_multi_az: true` trên cấu hình chuẩn. Template RDS đặt `MultiAZ: true`, nên RDS duy trì một bản standby đồng bộ ở AZ thứ hai (DB subnet group đã trải trên 2 AZ) và tự chuyển đổi khi có sự cố.
- **Dự toán:** tính gấp đôi phần instance và storage của DB; EC2, ALB và bản sao không đổi.
- **Mặc định khóa** (`VERIFYING`) cho tới khi có bằng chứng tạo, sao lưu và khôi phục riêng cho đúng cấu hình này. Nên kiểm thêm failover có chủ đích (`reboot-db-instance --force-failover`) và ghi lại thời gian ứng dụng mất kết nối.

## 4. Chi phí thực tế theo ngày so với dự toán

- **`GET /environments/{id}/cost-series`** trả tối đa 62 ngày UTC. Cột **ước tính** = đơn giá theo giờ của cấu hình hiện tại × số giờ môi trường tồn tại trong ngày. Cột **thực tế** lấy từ lần đối soát Cost Explorer gần nhất (`POST /environments/{id}/cost`, lọc theo tag `cloudhub:environment`).
- Ngày chưa có dữ liệu luôn là `null` và hiển thị "chưa có", **không bao giờ là 0**. Ngày AWS còn ước tính được đánh dấu riêng.
- **Giao diện:** cột màu xanh là số thực tế, đường nét đứt màu cam là ước tính, kèm bảng số liệu và các giả định. Biểu đồ vẽ bằng SVG thuần, không dùng thư viện ngoài.

## Kiểm thử

- `python -m unittest tests/test_cloud_features.py` (14 ca): terminal kiểm owner/trạng thái/giới hạn và không lưu token; resize kiểm danh sách đích, consent sai, giữ chỗ chênh lệch, chỉ đổi `InstanceType` (giữ `DataVolume`/`SnapshotId`), rollback và spend guard; Multi-AZ kiểm profile bị khóa, dự toán gấp đôi DB và `MultiAZ` trong template; chuỗi chi phí giữ `null` và giờ chạy đúng; IAM giới hạn theo tag.
- `node --test tests/cloud-tools.test.mjs` (8 ca): định dạng message nhị phân khớp plugin (header, SHA-256, UUID), handshake, ack và sắp xếp theo thứ tự, chặn stream URL lạ, màn hình terminal, biểu đồ không vẽ ngày thiếu số liệu, nút chỉ hiện cho mẫu được hỗ trợ.

Chưa kiểm trên AWS: phiên Session Manager thật qua trình duyệt, thời gian gián đoạn khi đổi loại máy, failover Multi-AZ và số liệu Cost Explorer thật.
