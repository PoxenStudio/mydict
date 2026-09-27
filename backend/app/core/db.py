from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@event.listens_for(engine, "connect")
def _configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    # SQLite 默认不强制外键约束，ON DELETE CASCADE 需要每个连接显式开启。
    cursor.execute("PRAGMA foreign_keys=ON")
    # 默认回滚日志模式下写操作会独占锁，导入大文件时的批量 commit 与后台任务/其他请求
    # 并发写库会直接报 "database is locked"；WAL 允许读不阻塞写，busy_timeout 让写冲突
    # 等待重试而不是立刻抛错。
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
