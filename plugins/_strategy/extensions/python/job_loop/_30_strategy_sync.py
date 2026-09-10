import asyncio
from typing import Any

from helpers.extension import Extension
from helpers.print_style import PrintStyle
from plugins._strategy.helpers import services


SYNC_INTERVAL_SECONDS = 2
RECONCILIATION_INTERVAL_SECONDS = 15 * 60
_worker_task: asyncio.Task[None] | None = None


class StrategySyncWorker(Extension):
    """Start one durable, non-blocking sync worker for Strategy projections."""

    async def execute(self, **kwargs: Any) -> None:
        global _worker_task
        if _worker_task is None or _worker_task.done():
            _worker_task = asyncio.create_task(_run_worker())


async def _run_worker() -> None:
    last_reconciliation = 0.0
    loop = asyncio.get_running_loop()
    while True:
        try:
            await asyncio.to_thread(services.process_sync, 20)
            if loop.time() - last_reconciliation >= RECONCILIATION_INTERVAL_SECONDS:
                await asyncio.to_thread(services.sync_projects)
                last_reconciliation = loop.time()
        except Exception as error:
            PrintStyle.error(f"Strategy sync worker failed: {error}")
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)
