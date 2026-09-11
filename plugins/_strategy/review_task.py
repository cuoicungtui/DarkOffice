"""Install the read-only strategy review scheduled task idempotently."""
from __future__ import annotations

import asyncio

from helpers.task_scheduler import ScheduledTask, TaskSchedule, TaskScheduler


REVIEW_TASK_NAME = "Review chiến lược và cảnh báo tiến độ"
REVIEW_SYSTEM_PROMPT = (
    "Bạn là bộ đọc báo cáo DarkOffice. Chỉ được đọc dữ liệu; không tạo, sửa, xóa "
    "Strategy hoặc Plane. Chỉ chạy đúng hai lệnh darkoffice delivery reconcile và "
    "darkoffice delivery inspect."
)
REVIEW_PROMPT = (
    "Chạy lần lượt darkoffice delivery reconcile rồi darkoffice delivery inspect. "
    "Xuất báo cáo tiếng Việt ngắn gồm tiến độ từng Objective và Project liên kết; "
    "task quá hạn, hoàn thành muộn, chưa có hạn, chưa bắt đầu; lỗi webhook/inbox/"
    "outbox, mapping hỏng và projection cũ. Nếu sạch, ghi 'Không có cảnh báo'. "
    "Không thực hiện thao tác ghi nào."
)


async def ensure_review_task() -> ScheduledTask:
    scheduler = TaskScheduler.get()
    await scheduler.reload()
    schedule = TaskSchedule(
        minute="*/10", hour="*", day="*", month="*", weekday="*",
        timezone="Asia/Ho_Chi_Minh",
    )
    existing = scheduler.get_task_by_name(REVIEW_TASK_NAME)
    if isinstance(existing, ScheduledTask):
        updated = await scheduler.update_task(
            existing.uuid,
            system_prompt=REVIEW_SYSTEM_PROMPT,
            prompt=REVIEW_PROMPT,
            schedule=schedule,
        )
        return updated or existing
    task = ScheduledTask.create(
        name=REVIEW_TASK_NAME,
        system_prompt=REVIEW_SYSTEM_PROMPT,
        prompt=REVIEW_PROMPT,
        schedule=schedule,
        timezone="Asia/Ho_Chi_Minh",
    )
    await scheduler.add_task(task)
    return task


def main() -> None:
    task = asyncio.run(ensure_review_task())
    print(task.model_dump_json(ensure_ascii=False))


if __name__ == "__main__":
    main()
