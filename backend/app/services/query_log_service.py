from sqlalchemy.orm import Session

from app.models.query import QueryLog


def log_query(
    db: Session,
    *,
    source: str,
    word: str,
    status: str,
    duration_ms: int,
    token_id: int | None = None,
    user_id: int | None = None,
    dictionary_id: int | None = None,
    ip: str | None = None,
) -> None:
    db.add(
        QueryLog(
            source=source,
            token_id=token_id,
            user_id=user_id,
            word=word,
            dictionary_id=dictionary_id,
            ip=ip,
            status=status,
            duration_ms=duration_ms,
        )
    )
    db.commit()
