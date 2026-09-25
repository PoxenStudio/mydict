import argparse
import sqlite3
from pathlib import Path

import pytest

from app import cli
from app.core import migrate
from app.core.config import get_settings

_BEFORE_HEAVY = "c8f1a2b3d4e5"
_HEAVY = "e5b7c9d1a3f4"
_TMP = "_alembic_tmp_dict_entries"


@pytest.fixture
def scratch_db(tmp_path: Path, monkeypatch) -> Path:
    """每个用例一个独立的库文件：迁移测试要从旧版本起步、手工摆出中断现场。"""
    database = tmp_path / "migrate.sqlite3"
    monkeypatch.setattr(get_settings(), "database_path", str(database))
    return database


def _upgrade(revision: str) -> None:
    from alembic import command

    command.upgrade(migrate._alembic_config(), revision)


def _seed_entries(database: Path) -> None:
    with sqlite3.connect(database) as conn:
        conn.execute(
            "INSERT INTO dictionaries (id, name, format, lang_from, lang_to, file_path)"
            " VALUES (1, 'd', 'mdict', 'zh-Hans', 'zh-Hans', 'x')"
        )
        conn.executemany(
            "INSERT INTO dict_entries (dictionary_id, word, word_lower, definition)"
            " VALUES (1, ?, ?, ?)",
            [("毛泽东", "毛泽东", "第一首"), ("沁园春", "沁园春", "别的")],
        )


def _state(database: Path) -> dict:
    with sqlite3.connect(database) as conn:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
        rows = conn.execute("SELECT word, definition FROM dict_entries ORDER BY id").fetchall()
        schema = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'dict_entries'"
        ).fetchone()[0]
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    return {"names": names, "rows": rows, "schema": schema, "version": version}


def _assert_migrated(database: Path) -> None:
    state = _state(database)
    assert state["rows"] == [("毛泽东", "第一首"), ("沁园春", "别的")]
    assert _TMP not in state["names"]
    assert "uq_dict_entries_dictionary_word" not in state["schema"]
    assert {"ix_dict_entries_word_lower", "ix_dict_entries_dict_word_lower"} <= state["names"]
    # 同名词条可以写进去了
    with sqlite3.connect(database) as conn:
        conn.execute(
            "INSERT INTO dict_entries (dictionary_id, word, word_lower, definition)"
            " VALUES (1, '毛泽东', '毛泽东', '第二首')"
        )


def test_heavy_migration_retries_after_leftover_empty_tmp_table(scratch_db: Path) -> None:
    """中断在「拷数据」途中：原表还在，临时表是半成品，删掉重来。"""
    _upgrade(_BEFORE_HEAVY)
    _seed_entries(scratch_db)
    with sqlite3.connect(scratch_db) as conn:
        conn.execute(f"CREATE TABLE {_TMP} (id INTEGER PRIMARY KEY)")

    _upgrade("head")
    _assert_migrated(scratch_db)


def test_heavy_migration_recovers_data_from_tmp_table(scratch_db: Path) -> None:
    """中断在「删原表」与「改名」之间：数据全在临时表里，必须改名回来而不是删掉它。"""
    _upgrade(_BEFORE_HEAVY)
    _seed_entries(scratch_db)
    with sqlite3.connect(scratch_db) as conn:
        conn.execute(
            f"CREATE TABLE {_TMP} ("
            " id INTEGER NOT NULL PRIMARY KEY,"
            " dictionary_id INTEGER NOT NULL REFERENCES dictionaries (id) ON DELETE CASCADE,"
            " word VARCHAR(255) NOT NULL, word_lower VARCHAR(255) NOT NULL,"
            " phonetic VARCHAR(255), definition TEXT NOT NULL, extra TEXT)"
        )
        conn.execute(f"INSERT INTO {_TMP} SELECT * FROM dict_entries")
        conn.execute("DROP TABLE dict_entries")

    _upgrade("head")
    _assert_migrated(scratch_db)


def test_heavy_migration_is_idempotent_when_rebuild_already_done(scratch_db: Path) -> None:
    """重建已完成、但版本号没来得及写入：约束已经没了，只补索引。"""
    _upgrade(_HEAVY)
    _seed_entries(scratch_db)
    with sqlite3.connect(scratch_db) as conn:
        conn.execute("DROP INDEX ix_dict_entries_dict_word_lower")
        conn.execute("UPDATE alembic_version SET version_num = ?", (_BEFORE_HEAVY,))

    _upgrade("head")
    _assert_migrated(scratch_db)


def test_pending_migrations_marks_heavy(scratch_db: Path) -> None:
    _upgrade(_BEFORE_HEAVY)
    pending = migrate.pending_migrations()
    assert pending[0].revision == _HEAVY and pending[0].heavy
    assert all(not item.heavy for item in pending[1:])
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(migrate._alembic_config()).get_current_head()
    assert pending[-1].revision == head


def test_startup_refuses_heavy_migration_on_large_database(
    scratch_db: Path, monkeypatch
) -> None:
    _upgrade(_BEFORE_HEAVY)
    _seed_entries(scratch_db)
    monkeypatch.setattr(migrate, "HEAVY_MIGRATION_ROW_THRESHOLD", 1)

    with pytest.raises(SystemExit, match="app.cli migrate"):
        migrate.run_migrations()
    assert _state(scratch_db)["version"] == _BEFORE_HEAVY


def test_startup_runs_heavy_migration_on_small_database(scratch_db: Path) -> None:
    """新装或数据很少的库照常自动迁移，不给小部署添麻烦。"""
    _upgrade(_BEFORE_HEAVY)
    _seed_entries(scratch_db)
    migrate.run_migrations()
    assert migrate.pending_migrations() == []


def test_startup_refuses_any_pending_migration_when_auto_migrate_disabled(
    scratch_db: Path, monkeypatch
) -> None:
    _upgrade(_HEAVY)
    monkeypatch.setattr(get_settings(), "auto_migrate", False)
    with pytest.raises(SystemExit, match="AUTO_MIGRATE=false"):
        migrate.run_migrations()

    _upgrade("head")
    migrate.run_migrations()  # 没有待执行的迁移时照常启动


def test_cli_migrate_requires_yes(scratch_db: Path, capsys) -> None:
    _upgrade(_BEFORE_HEAVY)
    _seed_entries(scratch_db)

    cli.migrate(argparse.Namespace(dry_run=True, yes=False))
    assert "[重型：整表重建]" in capsys.readouterr().out
    assert _state(scratch_db)["version"] == _BEFORE_HEAVY

    with pytest.raises(SystemExit):
        cli.migrate(argparse.Namespace(dry_run=False, yes=False))
    assert _state(scratch_db)["version"] == _BEFORE_HEAVY

    cli.migrate(argparse.Namespace(dry_run=False, yes=True))
    assert migrate.pending_migrations() == []
    _assert_migrated(scratch_db)


def test_drop_spx_columns_keeps_dictionaries_and_entries(scratch_db: Path) -> None:
    """删掉转码遗留列：词典与词条原样保留（外键不受影响），废弃的系统设置被清掉。"""
    _upgrade("a3d5f7b9c1e2")
    _seed_entries(scratch_db)
    with sqlite3.connect(scratch_db) as conn:
        conn.execute("UPDATE dictionaries SET spx_pending_count = 5")
        conn.execute(
            "INSERT INTO system_settings (key, value) VALUES ('spx_online_transcode', 'true')"
        )

    _upgrade("b4e6a8c0d2f4")
    with sqlite3.connect(scratch_db) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(dictionaries)")}
        assert not {"spx_pending_count", "spx_scanned_at"} & columns
        assert conn.execute("SELECT name FROM dictionaries").fetchall() == [("d",)]
        assert conn.execute("SELECT COUNT(*) FROM dict_entries").fetchone()[0] == 2
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM system_settings WHERE key = 'spx_online_transcode'"
            ).fetchone()[0]
            == 0
        )
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM dictionaries WHERE id = 1")
        assert conn.execute("SELECT COUNT(*) FROM dict_entries").fetchone()[0] == 0
