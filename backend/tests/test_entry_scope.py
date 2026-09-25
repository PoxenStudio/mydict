"""锁住 dict_entries 上几条关键查询的执行计划。

执行计划由 SQLite 规划器决定，写法上的细微差别（多一个过滤条件、少一个 `+ 0`）就能让一条
分批语句从「主键区间」退化成「每批扫整部词典的索引」，功能测试完全看不出来，只会在
2000 多万行的生产库上变成几个小时。
"""

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models.dictionary import DictEntry
from app.services.entry_scope import current_generation_only, in_dictionary_for_id_window


def _plan(db: Session, statement) -> str:
    connection = db.connection()
    sql = str(statement.compile(connection, compile_kwargs={"literal_binds": True}))
    return " | ".join(row[-1] for row in connection.exec_driver_sql("EXPLAIN QUERY PLAN " + sql))


def test_id_window_batches_scan_primary_key_range(db_session: Session) -> None:
    window = (in_dictionary_for_id_window(7), DictEntry.id > 100, DictEntry.id <= 5100)
    statements = [
        update(DictEntry).where(*window, DictEntry.definition.like("%x%")).values(definition="y"),
        select(DictEntry.id, DictEntry.definition).where(*window, DictEntry.definition.like("%`%")),
        delete(DictEntry).where(*window, DictEntry.generation != 1),
    ]
    for statement in statements:
        plan = _plan(db_session, statement)
        assert "INTEGER PRIMARY KEY (rowid>? AND rowid<?)" in plan, plan


def test_plain_dictionary_filter_would_skip_the_primary_key_range(db_session: Session) -> None:
    """反例：直接写 dictionary_id = ? 时规划器改走索引——这正是 helper 存在的原因。"""
    plan = _plan(
        db_session,
        select(DictEntry.id).where(
            DictEntry.dictionary_id == 7, DictEntry.id > 100, DictEntry.id <= 5100
        ),
    )
    assert "ix_dict_entries_dict_word_lower" in plan, plan


def test_search_uses_dictionary_word_index(db_session: Session) -> None:
    plan = _plan(
        db_session,
        current_generation_only(db_session.query(DictEntry))
        .filter(DictEntry.dictionary_id.in_([1, 2]), DictEntry.word_lower.in_(["a", "b"]))
        .statement,
    )
    assert "ix_dict_entries_dict_word_lower (dictionary_id=? AND word_lower=?)" in plan, plan
