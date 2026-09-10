from datetime import date, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from app.tasks.stats_aggregation import aggregate_date

_scheduler = BackgroundScheduler()


def _run_aggregation() -> None:
    today = date.today()
    aggregate_date((today - timedelta(days=1)).isoformat())  # 补齐重启前可能错过的前一天
    aggregate_date(today.isoformat())


def start_scheduler() -> None:
    if _scheduler.running:
        return
    _scheduler.add_job(_run_aggregation, "interval", minutes=10, next_run_time=datetime.now())
    _scheduler.start()
