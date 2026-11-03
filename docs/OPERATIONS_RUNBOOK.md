# Vận hành vòng đời CloudHub

Phạm vi TV4: service–worker–driver, Scheduler, Step Functions, bảo vệ nguồn dữ liệu, thông báo và phát hành. Các thao tác AWS dưới đây cần phiên và phạm vi được cấp riêng; không lấy quota trên UI làm quyền chi tiêu.

## Tra cứu sự cố

Ghi operation ID, environment ID, owner, Region, generation, phase, deadline/revision và thời điểm cập nhật. Che token, cookie, thông tin đăng nhập, URL ký và nội dung Secrets Manager. Không chép toàn bộ DynamoDB export hoặc raw stack vào repo public.

| Hiện tượng | Bản ghi cần kiểm tra | Xử lý an toàn |
|---|---|---|
| Lệnh đã nhận nhưng chưa chạy | `O#...`, QUEUED, generation, execution name | Giữ operation ID và idempotency key; dispatch lại cùng định danh sau khi kiểm quyền. Sweep là đường phục hồi bền vững. |
| Gia hạn đã đổi deadline, Scheduler lỗi | `schedule_pending`, `schedule_sync_operation_id`, lifecycle revision | Retry/sync operation hiện có; không tính kỳ mới hoặc dựng lại stack. |
| Callback cũ | expected_deadline, expected_revision, Region | Worker/service đọc lại dữ liệu hiện tại. Không sửa deadline để làm callback cũ hợp lệ. |
| Sao lưu bắt buộc lỗi | failed_phase, recovery point, ERROR_RETAINED, needs_admin | Giữ nguồn và quota; kiểm quyền/vault/snapshot/manifest, retry trong giới hạn được backend cho phép. |
| Thu hồi còn sót hoặc thiếu quyền inventory | deleted/retained/residual/unknown/billable | Giữ trạng thái chưa sạch; xác định tài nguyên đúng tag/owner/Region trước khi bổ sung quyền hoặc retry. |
| Lỗi MarkFailure có scope không khớp | owner/Region của operation, môi trường và recovery point | Không sửa trạng thái nguồn hoặc resume tài nguyên khác. Kiểm dữ liệu và quyền; không bỏ guard để chạy tiếp. |
| Chưa nhận email | preference, verified email, subscription, delivery state | Phân biệt pending confirmation, published và người nhận đã xác nhận nhận thư; không gửi lặp để che lỗi. |

Chỉ bấm Thử lại/Hủy khi API actions cho phép. Không trả quota trước khi audit đạt phạm vi quy định, không reset ledger hay hoàn reservation chưa đối soát.

## Đọc trên AWS Console

1. DynamoDB → Explore items: đọc `O#operation_id`, `E#environment_id`, recovery point và version. Đối chiếu owner/Region và lock; không chỉnh tay để vượt fence.
2. Step Functions → Executions: kiểm tên `operation_id` hoặc `operation_id-r<generation>`, input và Tick/Wait/Catch. Execution mới không được thay operation đã nhận chỉ vì mất kết nối.
3. EventBridge Scheduler: đọc lịch `env-...-lifecycle`, group, timezone, target, role, DLQ và payload expected_deadline/revision. Lịch ổn định không auto-delete phiên kế tiếp.
4. CloudWatch Logs: lọc operation/environment ID, CloudHubOperationFailed và CloudHubSweepFailed. Kiểm generation và phase trước khi kết luận workflow đã thành công.
5. CloudFormation và dịch vụ dữ liệu tại đúng Region: đọc stack/tag, tài nguyên giữ lại và snapshot/bản sao. Không xóa hạ tầng dùng chung hoặc tài nguyên không xác định owner.

Việc đọc được các màn hình này chưa chứng minh AWS đã kiểm đủ vòng đời hay ngân sách còn đủ.

## Tài liệu dịch vụ

- [Step Functions StartExecution](https://docs.aws.amazon.com/step-functions/latest/apireference/API_StartExecution.html): STANDARD dùng cùng name/input khi execution còn chạy; execution đã đóng có thể trả ExecutionAlreadyExists. Không suy rộng sang EXPRESS.
- [Scheduler UpdateSchedule](https://docs.aws.amazon.com/scheduler/latest/APIReference/API_UpdateSchedule.html): đọc GetSchedule và giữ đầy đủ trường cần thiết vì Update thay thế cấu hình, kể cả mặc định của trường bị bỏ.
- [Lambda asynchronous retry](https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-error-handling.html): sự kiện có thể được giao lại; xử lý trùng phải dựa trên operation/generation và cập nhật có điều kiện.

## Phát hành và quay lại

Chạy test, kiểm source hash và dependency; chuẩn bị manifest, config, IAM/change set, inventory, dự toán và thu hồi trước khi xin triển khai. Chỉ manifest có nguồn đầy đủ và test native-scope local tương ứng mới được chuẩn bị packet. Cả bước đó cũng chưa phê duyệt chạy AWS.

Quay lại phải giữ worker tương thích ledger schema 2, operation ID/generation, upload/publication và bản sao còn hoạt động. Không đưa worker cũ thiếu guard vào record mới, không reset DynamoDB hoặc xóa dữ liệu người dùng để quay lại code. Đối chiếu dữ liệu và tác vụ phát sinh trước khi đổi đích hoặc thu hồi nguồn.
