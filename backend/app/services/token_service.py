from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.core.security import generate_api_token, hash_api_token, token_display_prefix
from app.core.timeutil import today_str
from app.models.query import QueryStatsDaily
from app.models.token import ApiToken
from app.models.vocab import TokenVocabItem
from app.services.audit_service import log_action
from app.services.query_service import filter_existing_dictionary_ids


def _usage(db: Session, token_id: int) -> tuple[int, int]:
    # 计数器以本地日期为键（写入侧见 rate_limit_service），这里读同一个出处，避免以后又漂移
    today = today_str()
    today_row = (
        db.query(QueryStatsDaily)
        .filter(QueryStatsDaily.stat_date == today, QueryStatsDaily.token_id == token_id)
        .first()
    )
    total = db.query(QueryStatsDaily.query_count).filter(QueryStatsDaily.token_id == token_id).all()
    return (today_row.query_count if today_row else 0), sum(c for (c,) in total)


def _usage_maps(db: Session) -> tuple[dict[int, int], dict[int, int]]:
    today = today_str()
    today_rows = (
        db.query(QueryStatsDaily.token_id, QueryStatsDaily.query_count)
        .filter(QueryStatsDaily.stat_date == today, QueryStatsDaily.token_id.isnot(None))
        .all()
    )
    total_rows = (
        db.query(QueryStatsDaily.token_id, QueryStatsDaily.query_count)
        .filter(QueryStatsDaily.token_id.isnot(None))
        .all()
    )
    today_map: dict[int, int] = dict(today_rows)
    total_map: dict[int, int] = {}
    for token_id, count in total_rows:
        total_map[token_id] = total_map.get(token_id, 0) + count
    return today_map, total_map


def _to_out(token: ApiToken, today_count: int, total_count: int) -> dict:
    return {
        "id": token.id,
        "name": token.name,
        "token_prefix": token.token_prefix,
        "daily_limit": token.daily_limit,
        "status": token.status,
        "created_at": token.created_at,
        "last_used_at": token.last_used_at,
        "today_count": today_count,
        "total_count": total_count,
        "allowed_dictionary_ids": token.allowed_dictionary_ids,
    }


def list_tokens(db: Session) -> list[dict]:
    tokens = db.query(ApiToken).order_by(ApiToken.created_at.desc()).all()
    today_map, total_map = _usage_maps(db)
    return [_to_out(t, today_map.get(t.id, 0), total_map.get(t.id, 0)) for t in tokens]


def _get_or_404(db: Session, token_id: int) -> ApiToken:
    token = db.get(ApiToken, token_id)
    if token is None:
        raise NotFoundError("Token 不存在")
    return token


def get_token_out(db: Session, token_id: int) -> dict:
    token = _get_or_404(db, token_id)
    today_count, total_count = _usage(db, token_id)
    return _to_out(token, today_count, total_count)


def create_token(
    db: Session,
    name: str,
    daily_limit: int | None,
    admin_id: int,
    allowed_dictionary_ids: list[int] | None = None,
) -> dict:
    raw = generate_api_token()
    token = ApiToken(
        name=name,
        token_hash=hash_api_token(raw),
        token_prefix=token_display_prefix(raw),
        daily_limit=daily_limit,
        status="active",
        created_by=admin_id,
        allowed_dictionary_ids=filter_existing_dictionary_ids(db, allowed_dictionary_ids),
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    log_action(
        db, actor_type="admin", actor_id=admin_id, action="token.create", target=str(token.id)
    )
    return {**_to_out(token, 0, 0), "token": raw}


def set_allowed_dictionaries(
    db: Session, token_id: int, dictionary_ids: list[int] | None, admin_id: int
) -> dict:
    token = _get_or_404(db, token_id)
    token.allowed_dictionary_ids = filter_existing_dictionary_ids(db, dictionary_ids)
    db.commit()
    log_action(
        db,
        actor_type="admin",
        actor_id=admin_id,
        action="token.set_allowed_dictionaries",
        target=str(token_id),
        detail={"dictionary_ids": token.allowed_dictionary_ids},
    )
    return get_token_out(db, token_id)


def set_token_status(db: Session, token_id: int, status: str, admin_id: int) -> dict:
    token = _get_or_404(db, token_id)
    token.status = status
    db.commit()
    log_action(
        db, actor_type="admin", actor_id=admin_id, action=f"token.{status}", target=str(token_id)
    )
    return get_token_out(db, token_id)


def regenerate_token(db: Session, token_id: int, admin_id: int) -> dict:
    token = _get_or_404(db, token_id)
    raw = generate_api_token()
    token.token_hash = hash_api_token(raw)
    token.token_prefix = token_display_prefix(raw)
    db.commit()
    log_action(
        db, actor_type="admin", actor_id=admin_id, action="token.regenerate", target=str(token_id)
    )
    today_count, total_count = _usage(db, token_id)
    return {**_to_out(token, today_count, total_count), "token": raw}


def get_vocab_count(db: Session, token_id: int) -> int:
    _get_or_404(db, token_id)
    return db.query(TokenVocabItem).filter(TokenVocabItem.token_id == token_id).count()
