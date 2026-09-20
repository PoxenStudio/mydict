from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.timeutil import day_str, local_zone
from app.tasks.stats_aggregation import aggregate_date

# 聚合的目标日按本地日划分，调度器时区与之保持一致
_scheduler = BackgroundScheduler(timezone=local_zone())


def _run_aggregation() -> None:
    aggregate_date(day_str(-1))  # 补齐重启前可能错过的前一天
    aggregate_date(day_str())


def start_scheduler() -> None:
    if _scheduler.running:
        return
    _scheduler.add_job(_run_aggregation, "interval", minutes=10, next_run_time=datetime.now())
    _scheduler.start()
