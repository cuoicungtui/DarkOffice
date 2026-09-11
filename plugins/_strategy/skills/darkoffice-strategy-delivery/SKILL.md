---
name: darkoffice-strategy-delivery
description: Apply approved strategy objectives and Work Charts to their Plane projects, then monitor project-derived progress. Use for strategy, Plane project, or execution-task changes.
version: 2.0.0
---

# Chiến lược đến Dự án Thực thi

Skill này điều hành toàn bộ luồng DarkOffice Strategy và Plane qua CLI nội bộ. Không khởi động hoặc gọi Plane MCP hay Strategy MCP.

## Quy tắc nghiệp vụ

- DarkOffice quản lý North Star, Pillar, Objective, KR, Initiative và lịch sử liên kết.
- Plane quản lý Project, work item, dependency, assignee và trạng thái thực thi.
- Chỉ có một North Star còn hiệu lực. Mỗi Objective của team/phòng ban gắn đúng một Plane Project; một Project không thuộc hai Objective còn hiệu lực.
- Tiến độ Objective là tỷ lệ leaf work item hoàn thành trong Plane Project. KR/check-in là số đo riêng, không bị phần trăm task ghi đè.
- Không tự xóa Project hoặc task Plane. Đổi Project giữ lịch sử Project/task cũ và cần phiếu áp dụng mới.

## Luồng bắt buộc

1. Đọc trạng thái hiện có bằng `sh /a0/plugins/_strategy/scripts/darkoffice delivery inspect`.
2. Chuẩn bị delivery specification JSON với Work Chart có `status: "ready_for_handoff"`, `id`, `version`, item ID duy nhất, title và dependency. Project mới bắt buộc `identifier`.
3. Chạy `sh /a0/plugins/_strategy/scripts/darkoffice delivery prepare --spec-file <file>`; trình bày **phiếu áp dụng** bằng tiếng Việt từ `application_sheet` gồm Objective, Project, task, dependency và tác động.
4. Chỉ khi người dùng xác nhận đúng phiếu trong cuộc hội thoại hiện tại, chạy `sh /a0/plugins/_strategy/scripts/darkoffice delivery apply --confirmation-token <token>`.
5. Khi run lỗi hoặc bị ngắt, dùng `sh /a0/plugins/_strategy/scripts/darkoffice delivery resume --run-id <id>`; không chuẩn bị chart/version khác để tiếp tục run cũ.
6. Sau thay đổi thực thi từ Plane, dùng `sh /a0/plugins/_strategy/scripts/darkoffice delivery reconcile`; webhook backend sẽ tiếp tục cập nhật projection và tiến độ.

## Sửa công việc sau bàn giao

Đọc Project, state và member trước. Với state, assignee, cycle hoặc module, chuẩn bị specification có `operation: "task_update"`, `project_id`, `work_item_id` và `changes`. Với comment dùng `operation: "task_comment"`; với dependency dùng `operation: "task_dependency"`. Chạy `prepare`, trình bày tác động và chỉ chạy `sh /a0/plugins/_strategy/scripts/darkoffice delivery task-update --confirmation-token <token>` sau xác nhận.

## An toàn

- `apply` chỉ nhận confirmation token còn hạn do `prepare` cấp. Không tự tạo token hoặc tái dùng token đã áp dụng.
- Nếu CLI trả `ok: false`, đọc `error.code`, báo kết quả ngắn gọn và dừng. Chỉ `resume` cùng run khi lỗi có thể khắc phục.
- Không dùng lifecycle cảm tính như “Đúng hướng” để báo tiến độ. Chỉ dùng số liệu Work item Plane và check-in KR.
