---
name: darkoffice-strategy-execution
description: Apply an accepted Work Chart to DarkOffice Strategy and Plane through confirmation-gated MCP tools. Use after a Work Chart is ready_for_handoff; never execute from a draft plan.
version: 1.0.0
---

# Thực thi Chiến lược đến Plane

Chỉ dùng skill này sau `darkoffice-planning-method-skill` và `darkoffice-plan-to-work-skill`, khi Work Chart đúng phiên bản đã có trạng thái `ready_for_handoff`. Skill này tạo cấu trúc chiến lược và thực thi công việc; không thay thế hai skill lập kế hoạch trước đó.

## Nguồn sự thật

- DarkOffice Strategy quản lý North Star, Pillar, Objective, Key Result, Initiative, liên kết và đo lường kết quả.
- Plane quản lý Plane Project, work item, dependency, assignee và trạng thái thực thi.
- Một North Star còn hiệu lực duy nhất. Mỗi Objective gắn đúng một Plane Project; một Plane Project không được gắn với hai Objective còn hiệu lực.
- Objective không có task đại diện. Mỗi Work Chart item được chấp thuận tạo đúng một Plane work item.
- Tiến độ Objective là tiến độ hoàn thành của các leaf work item hợp lệ trong Plane Project; không dùng trạng thái cảm tính để suy luận tiến độ.

## Quy trình bắt buộc

1. Đọc Work Chart đã được duyệt. Xác minh `ready_for_handoff`, `work_chart_id`, phiên bản, item ID, phụ thuộc và tiêu chí chấp nhận.
2. Đọc `darkoffice-strategy.get_strategy_dashboard`, `list_strategy_nodes`, `list_available_plane_projects` và Plane `project(action="list")`. Không tạo hoặc sửa dữ liệu trong bước này.
3. Lập phiếu áp dụng bằng tiếng Việt: cấu trúc Strategy sẽ thêm/sửa, Objective, Plane Project mới hoặc dùng lại, Work Chart item sẽ trở thành task, dependency và tác động. Nêu rõ không có task đại diện cho Objective.
4. Hỏi người dùng xác nhận rõ phiếu áp dụng. Không gọi tool thay đổi cho đến khi họ đồng ý với đúng phạm vi này.
5. Nếu cần Project mới, tạo bằng Plane MCP `project(action="create")`, rồi làm mới projection với `darkoffice-strategy.refresh_plane_projection(confirmed=true)`.
6. Tạo hoặc cập nhật Strategy node qua `darkoffice-strategy`. Tạo Objective chỉ khi đã có Plane Project ID; liên kết dùng `link_objective_to_plane_project` khi thay đổi liên kết hiện có.
7. Gọi `create_execution_run` với Work Chart ID, phiên bản, Objective và toàn bộ Work Chart item ID trước khi tạo task. Nếu run đã tồn tại, dùng run đó và chỉ tiếp tục các item chưa được ghi nhận.
8. Tạo một Plane work item cho từng item chưa hoàn tất. Ghi `work_chart_id`, `work_chart_item_id` vào trường external metadata nếu Plane action hỗ trợ; nếu không, kiểm tra task đã ghi trong execution ledger trước khi retry. Tạo dependencies sau khi cả hai task đã tồn tại.
9. Sau mỗi task thành công, gọi `record_execution_item`. Kết thúc bằng `complete_execution_run`, làm mới projection và trả bảng Objective, Plane Project, task đã tạo, task lỗi và tiến độ hiện tại.

## Quy tắc an toàn

- Mọi tool thay đổi của `darkoffice-strategy` phải truyền `confirmed=true`, nhưng chỉ sau xác nhận thật của người dùng trong hội thoại hiện tại.
- Chỉ retry các thao tác trong cùng execution run và cùng Work Chart version. Khác chart, khác Objective, khác Project hoặc khác danh sách item cần một phiếu áp dụng mới.
- Nếu Plane Project đã tạo nhưng không thể liên kết vào DarkOffice, không tự xóa Project. Đánh dấu execution run lỗi, báo Plane Project ID và yêu cầu quyết định tiếp theo.
- Không archive Objective, thay Project hay đổi parent nếu chưa có xác nhận mới, kể cả khi Work Chart cũ đã được duyệt.
- Không sửa state, assignee hoặc tiến độ công việc trong DarkOffice Strategy. Dùng Plane MCP cho các thao tác này.
