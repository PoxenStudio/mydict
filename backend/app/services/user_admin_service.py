from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import generate_temp_password, hash_password
from app.models.query import QueryLog
from app.models.user import User
from app.models.vocab import VocabItem
from app.services.audit_service import log_action


def _usage_maps(db: Session, user_ids: list[int]) -> tuple[dict[int, int], dict[int, int]]:
    if not user_ids:
        return {}, {}
    vocab_map: dict[int, int] = dict(
        db.query(VocabItem.user_id, func.count(VocabItem.id))
        .filter(VocabItem.user_id.in_(user_ids))
        .group_by(VocabItem.user_id)
        .all()
    )
    query_map: dict[int, int] = dict(
        db.query(QueryLog.user_id, func.count(QueryLog.id))
        .filter(QueryLog.user_id.in_(user_ids))
        .group_by(QueryLog.user_id)
        .all()
    )
    return vocab_map, query_map


def _to_out(user: User, vocab_count: int, query_count: int) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "status": user.status,
        "created_at": user.created_at,
        "last_login_at": user.last_login_at,
        "vocab_count": vocab_count,
        "query_count": query_count,
    }


def list_users(
    db: Session, search: str | None, status: str | None, page: int, page_size: int
) -> tuple[list[dict], int]:
    query = db.query(User)
    if search:
        like = f"%{search.strip()}%"
        query = query.filter(or_(User.username.like(like), User.email.like(like)))
    if status:
        query = query.filter(User.status == status)
    total = query.count()
    users = (
        query.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    )
    vocab_map, query_map = _usage_maps(db, [u.id for u in users])
    rows = [_to_out(u, vocab_map.get(u.id, 0), query_map.get(u.id, 0)) for u in users]
    return rows, total


def create_user(db: Session, username: str, email: str | None, admin_id: int) -> tuple[dict, str]:
    if db.query(User).filter(User.username == username).first() is not None:
        raise ConflictError("用户名已存在")
    temp_password = generate_temp_password()
    user = User(username=username, email=email, password_hash=hash_password(temp_password))
    db.add(user)
    db.commit()
    db.refresh(user)
    log_action(db, actor_type="admin", actor_id=admin_id, action="user.create", target=username)
    return _to_out(user, 0, 0), temp_password


def _get_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("用户不存在")
    return user


def set_user_status(db: Session, user_id: int, status: str, admin_id: int) -> dict:
    user = _get_or_404(db, user_id)
    user.status = status
    db.commit()
    log_action(
        db, actor_type="admin", actor_id=admin_id, action=f"user.{status}", target=str(user_id)
    )
    vocab_map, query_map = _usage_maps(db, [user_id])
    return _to_out(user, vocab_map.get(user_id, 0), query_map.get(user_id, 0))


def reset_user_password(db: Session, user_id: int, admin_id: int) -> str:
    user = _get_or_404(db, user_id)
    temp_password = generate_temp_password()
    user.password_hash = hash_password(temp_password)
    db.commit()
    log_action(
        db, actor_type="admin", actor_id=admin_id, action="user.reset_password", target=str(user_id)
    )
    return temp_password


def get_user_detail(db: Session, user_id: int, recent_limit: int = 20) -> dict:
    user = _get_or_404(db, user_id)
    vocab_items = (
        db.query(VocabItem)
        .filter(VocabItem.user_id == user_id)
        .order_by(VocabItem.created_at.desc())
        .all()
    )
    total_query_count = db.query(QueryLog).filter(QueryLog.user_id == user_id).count()
    recent_queries = (
        db.query(QueryLog)
        .filter(QueryLog.user_id == user_id)
        .order_by(QueryLog.created_at.desc())
        .limit(recent_limit)
        .all()
    )
    return {
        "user": _to_out(user, len(vocab_items), total_query_count),
        "vocab_items": vocab_items,
        "recent_queries": recent_queries,
    }
