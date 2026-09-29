from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import generate_temp_password, hash_password
from app.models.query import QueryLog
from app.models.token import ApiToken
from app.models.user import User
from app.models.vocab import VocabItem
from app.services import token_service
from app.services.audit_service import log_action
from app.services.query_service import filter_existing_dictionary_ids


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


def _token_map(db: Session, user_ids: list[int]) -> dict[int, str | None]:
    if not user_ids:
        return {}
    return dict(
        db.query(ApiToken.user_id, ApiToken.token_plain)
        .filter(ApiToken.user_id.in_(user_ids))
        .all()
    )


def _to_out(user: User, vocab_count: int, query_count: int, api_token: str | None = None) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "status": user.status,
        "created_at": user.created_at,
        "last_login_at": user.last_login_at,
        "vocab_count": vocab_count,
        "query_count": query_count,
        "allowed_dictionary_ids": user.admin_allowed_dictionary_ids,
        "api_token": api_token,
    }


def _out(db: Session, user: User) -> dict:
    vocab_map, query_map = _usage_maps(db, [user.id])
    return _to_out(
        user,
        vocab_map.get(user.id, 0),
        query_map.get(user.id, 0),
        _token_map(db, [user.id]).get(user.id),
    )


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
    user_ids = [u.id for u in users]
    vocab_map, query_map = _usage_maps(db, user_ids)
    tokens = _token_map(db, user_ids)
    rows = [
        _to_out(u, vocab_map.get(u.id, 0), query_map.get(u.id, 0), tokens.get(u.id)) for u in users
    ]
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
    return _out(db, user)


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
        "user": _to_out(
            user, len(vocab_items), total_query_count, _token_map(db, [user_id]).get(user_id)
        ),
        "vocab_items": vocab_items,
        "recent_queries": recent_queries,
    }


def set_allowed_dictionaries(
    db: Session, user_id: int, dictionary_ids: list[int] | None, admin_id: int
) -> dict:
    """管理员配置用户「可用词典」的上限（None 为不限制）；用户在前台只能在上限内自选。"""
    user = _get_or_404(db, user_id)
    user.admin_allowed_dictionary_ids = filter_existing_dictionary_ids(db, dictionary_ids)
    db.commit()
    log_action(
        db,
        actor_type="admin",
        actor_id=admin_id,
        action="user.set_allowed_dictionaries",
        target=str(user_id),
        detail={"dictionary_ids": user.admin_allowed_dictionary_ids},
    )
    return _out(db, user)


def generate_token(db: Session, user_id: int, admin_id: int) -> dict:
    """生成（已有则重新生成）用户 Token：以该用户身份调用对外 API。"""
    user = _get_or_404(db, user_id)
    token_service.issue_user_token(db, user, admin_id)
    return _out(db, user)


def delete_token(db: Session, user_id: int, admin_id: int) -> dict:
    user = _get_or_404(db, user_id)
    token = token_service.find_user_token(db, user_id)
    if token is None:
        raise NotFoundError("该用户没有 Token")
    token_service.delete_token(db, token.id, admin_id)
    return _out(db, user)
