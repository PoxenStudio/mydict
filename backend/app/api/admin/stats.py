import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_admin
from app.models.admin import Admin
from app.schemas.stats import OverviewOut, StatRow, TopWordRow
from app.services import stats_service

router = APIRouter(prefix="/admin/stats", tags=["admin-stats"])


@router.get("/overview", response_model=OverviewOut)
def overview(db: Session = Depends(get_db), _admin: Admin = Depends(require_admin)) -> OverviewOut:
    return stats_service.get_overview(db)


@router.get("/top-words", response_model=list[TopWordRow])
def top_words(
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 10,
    db: Session = Depends(get_db),
    _admin: Admin = Depends(require_admin),
) -> list[TopWordRow]:
    return stats_service.top_words(db, start_date, end_date, min(limit, 50))


@router.get("")
def dimension_stats(
    dimension: str,
    start_date: str | None = None,
    end_date: str | None = None,
    export: str | None = None,
    db: Session = Depends(get_db),
    _admin: Admin = Depends(require_admin),
):
    rows = stats_service.query_dimension_stats(db, dimension, start_date, end_date)
    if export == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(
            buf, fieldnames=["id", "label", "query_count", "rate_limited_count"]
        )
        writer.writeheader()
        writer.writerows(rows)
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="stats-{dimension}.csv"'},
        )
    return [StatRow(**row) for row in rows]
