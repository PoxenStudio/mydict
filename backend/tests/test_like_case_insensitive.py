"""模糊搜索不区分大小写：连接层不得打开 case_sensitive_like 之类改变 LIKE 语义的全局设置。"""

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.vocab import VocabItem
from app.services import user_admin_service, vocab_service


def test_vocab_and_user_search_ignore_case(db_session: Session) -> None:
    user = User(username="CaseUser", email="Case.User@Example.com", password_hash="x")
    db_session.add(user)
    db_session.commit()
    db_session.add(VocabItem(user_id=user.id, word="Apple"))
    db_session.commit()

    items, total = vocab_service.list_vocab_items(db_session, "user", user.id, "apple", 1, 20)
    assert total == 1 and items[0].word == "Apple"

    for search in ("caseuser", "CASE.USER@example"):
        rows, total = user_admin_service.list_users(db_session, search, None, 1, 20)
        assert total == 1 and rows[0]["username"] == "CaseUser", search
