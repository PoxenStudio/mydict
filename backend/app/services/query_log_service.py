from sqlalchemy.orm import Session

from app.models.dictionary import Dictionary
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


def get_recent_history(db: Session, user_id: int, limit: int = 100) -> list[dict]:
    """登录用户最近的查询历史（仅 Web 端查询会写 user_id，第三方 Token 调用不计入）；
    只取查到结果的记录——未命中时没有 dictionary_id，收藏不了，历史里意义不大。"""
    rows = (
        db.query(QueryLog, Dictionary.name)
        .join(Dictionary, QueryLog.dictionary_id == Dictionary.id)
        .filter(QueryLog.user_id == user_id, QueryLog.status == "success")
        .order_by(QueryLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "word": log.word,
            "dictionary_id": log.dictionary_id,
            "dictionary_name": name,
            "created_at": log.created_at,
        }
        for log, name in rows
    ]
