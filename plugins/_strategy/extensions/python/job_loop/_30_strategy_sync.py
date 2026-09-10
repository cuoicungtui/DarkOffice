from plugins._strategy.helpers import services


_last_import = 0.0


async def execute(**kwargs):
    global _last_import
    import time
    services.process_sync(limit=20)
    if time.time() - _last_import >= 900:
        services.sync_projects()
        _last_import=time.time()
