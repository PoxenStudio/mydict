import json

from sqlalchemy.orm import Session

from app.models.audit import AuditLog


def log_action(
    db: Session,
    actor_type: str,
    action: str,
    actor_id: int | None = None,
    target: str | None = None,
    detail: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            target=target,
            detail=json.dumps(detail, ensure_ascii=False) if detail else None,
        )
    )
    db.commit()
