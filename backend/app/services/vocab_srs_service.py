"""生词本的 FSRS 复习调度。

这是**唯一**直接接触 py-fsrs 的地方：数据库里存 `Card.to_json()` 原样快照，
其余列（due_at / reps / lapses）只是给查询和列表展示用的镜像。

约定：
- 库里所有时间列都是**naive UTC**（SQLite 上比较方便），FSRS 要求 aware UTC，
  进出各转一次。
- 新词 = `reps == 0`；到期 = `reps > 0 且 due_at <= now`。
- 复习流水写入 `vocab_reviews`，`client_review_id` 命中时直接返回上次结果（幂等）。
"""

from datetime import datetime, timezone

from fsrs import Card, Rating, Scheduler, State
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.timeutil import day_bounds_utc, today
from app.models.vocab import VocabReview
from app.services import vocab_service

# 纯函数式调度器，无状态；默认参数即可（等复习记录攒够再谈 optimizer）
_scheduler = Scheduler()

# 桌面/手机/扩展统一按「到期优先，新词补足」的顺序取卡片
DEFAULT_LIMIT = 20
DEFAULT_NEW_LIMIT = 10


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_aware(value: datetime) -> datetime:
    """库里是 naive UTC，FSRS 只接受 aware UTC。"""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(
        timezone.utc
    )


def _to_naive(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _model(owner_kind: vocab_service.OwnerKind):
    return vocab_service._MODEL_BY_KIND[owner_kind]


def _owner_field(owner_kind: vocab_service.OwnerKind) -> str:
    return vocab_service._OWNER_FIELD_BY_KIND[owner_kind]


def _find_duplicate(
    db: Session, owner_kind: vocab_service.OwnerKind, owner_id: int, client_review_id: str
) -> VocabReview | None:
    return (
        db.query(VocabReview)
        .filter(
            VocabReview.owner_kind == owner_kind,
            VocabReview.owner_id == owner_id,
            VocabReview.client_review_id == client_review_id,
        )
        .first()
    )


def _scoped(db: Session, owner_kind: vocab_service.OwnerKind, owner_id: int):
    model_cls = _model(owner_kind)
    return db.query(model_cls).filter(getattr(model_cls, _owner_field(owner_kind)) == owner_id)


def counts(db: Session, owner_kind: vocab_service.OwnerKind, owner_id: int) -> dict[str, int]:
    """新词 / 到期 / 总数（列表页和复习页共用的口径）。"""
    now = _to_naive(_utcnow())
    query = _scoped(db, owner_kind, owner_id)
    model_cls = _model(owner_kind)
    total = query.count()
    new_count = query.filter(model_cls.reps == 0).count()
    due_count = query.filter(model_cls.reps > 0, model_cls.due_at <= now).count()
    return {"total": total, "new": new_count, "due": due_count}


def list_due(
    db: Session,
    owner_kind: vocab_service.OwnerKind,
    owner_id: int,
    limit: int = DEFAULT_LIMIT,
    new_limit: int = DEFAULT_NEW_LIMIT,
) -> tuple[list, dict[str, int]]:
    """取本次要复习的卡片：先到期（逾期越久越前），不够再用新词补到 limit。"""
    now = _to_naive(_utcnow())
    model_cls = _model(owner_kind)
    due_query = (
        _scoped(db, owner_kind, owner_id)
        .filter(model_cls.reps > 0, model_cls.due_at <= now)
        .order_by(model_cls.due_at.asc(), model_cls.id.asc())
        .limit(limit)
    )
    items = list(due_query.all())

    remaining = max(0, limit - len(items))
    if remaining:
        items.extend(
            _scoped(db, owner_kind, owner_id)
            .filter(model_cls.reps == 0)
            .order_by(model_cls.created_at.asc(), model_cls.id.asc())
            .limit(min(remaining, max(0, new_limit)))
            .all()
        )
    return items, counts(db, owner_kind, owner_id)


def review(
    db: Session,
    owner_kind: vocab_service.OwnerKind,
    owner_id: int,
    item_id: int,
    rating: int,
    reviewed_at: datetime | None = None,
    client: str | None = None,
    client_review_id: str | None = None,
) -> tuple[object, dict[str, int]]:
    """提交一次评分，落库并返回更新后的生词条目与最新计数。"""
    item = vocab_service.get_vocab_item(db, owner_kind, owner_id, item_id)

    # 幂等：离线队列重发同一个 client_review_id 时不再重复计入
    if client_review_id and _find_duplicate(db, owner_kind, owner_id, client_review_id):
        # 先查命中时，手里这份 item 可能是在别的请求提交之前读出来的，刷新一下再返回，
        # 免得响应里的 reps/due 与刚统计的 counts 对不上
        db.refresh(item)
        return item, counts(db, owner_kind, owner_id)

    card = Card.from_json(item.fsrs_card) if item.fsrs_card else Card()
    prev_state = card.state
    prev_due = item.due_at

    when = _utcnow()
    if reviewed_at is not None:
        when = _to_aware(reviewed_at)
        # 补交的旧记录不能早于上一次复习，否则 FSRS 的时间差会算成负数
        if item.last_review_at is not None:
            when = max(when, _to_aware(item.last_review_at))
        when = min(when, _utcnow())

    new_card, _log = _scheduler.review_card(card, Rating(int(rating)), when)

    item.fsrs_card = new_card.to_json()
    item.due_at = _to_naive(new_card.due)
    item.last_review_at = _to_naive(when)
    item.reps = (item.reps or 0) + 1
    if int(rating) == Rating.Again and prev_state == State.Review:
        item.lapses = (item.lapses or 0) + 1

    db.add(
        VocabReview(
            owner_kind=owner_kind,
            owner_id=owner_id,
            vocab_item_id=item.id,
            rating=int(rating),
            reviewed_at=_to_naive(when),
            prev_due_at=prev_due,
            next_due_at=item.due_at,
            client=client,
            client_review_id=client_review_id,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        # 并发重放：两次请求都通过了上面的「先查」，插入时撞唯一索引。
        # 回滚后重新确认确实是同一条 client_review_id，按已处理返回，别让客户端收到 500。
        db.rollback()
        if client_review_id and _find_duplicate(db, owner_kind, owner_id, client_review_id):
            db.refresh(item)
            return item, counts(db, owner_kind, owner_id)
        raise
    db.refresh(item)
    return item, counts(db, owner_kind, owner_id)


def stats(db: Session, owner_kind: vocab_service.OwnerKind, owner_id: int) -> dict[str, int]:
    """复习页用的汇总：总量、今日已复习、今天还能复习多少。"""
    base = counts(db, owner_kind, owner_id)
    start, end = day_bounds_utc(today())
    reviewed_today = (
        db.query(VocabReview)
        .filter(
            VocabReview.owner_kind == owner_kind,
            VocabReview.owner_id == owner_id,
            VocabReview.reviewed_at >= start,
            VocabReview.reviewed_at < end,
        )
        .count()
    )
    model_cls = _model(owner_kind)
    learned = _scoped(db, owner_kind, owner_id).filter(model_cls.reps > 0).count()
    return {
        **base,
        "learned": learned,
        "reviewed_today": reviewed_today,
        "scheduled_total": base["due"] + base["new"],
    }
