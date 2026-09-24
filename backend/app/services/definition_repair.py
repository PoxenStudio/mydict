"""修复历史遗留的坏资源链接。

`rewrite_resource_refs()` 早期版本把 `entry://`、`sound://` 与实际指向词典资源的 `file:///`
都当成普通的相对路径，改写成了指向不存在位置的 URL：

    entry://苹果          -> /dict-res/7/res/entry:/苹果
    sound://audio/x.spx   -> /dict-res/7/res/sound:/audio/x.spx
    file:///down/7/x.gif  -> /dict-res/7/res/file:/down/7/x.gif

导入代码已经修好（新导入的词典不会再产生这种值），但**已入库的行不会自动恢复**，
所以需要这个一次性的修复动作。它是纯字符串替换，结果与新导入代码产出的值逐条一致。

`file:/` 那一条实测影响 7 部词典（汉典、千篇汉语词典 2021/2023、说文解字段注、大辭海、
朗文 LDOCE5、新世纪日汉双解），约 99 万行；这些引用全都是 `<img src>`，指向 `.mdd` 里的
图片，所以「恢复成资源 URL」是对的，不是把危险协议变成可执行内容。

刻意不做的事：
  - 不恢复 `javascript:`（那本来就不该被改成可访问的 URL）
  - 不尝试还原 `//host/path` 与 `www.host/path`（旧改写把它们变成了
    `/dict-res/{id}/res/host/path`，与真实的资源路径已经无法区分）
  - 不动**没有被改写过的** `file:///…` 原文：它可能是作者想引用本机文件（词典打包在
    Windows 上），也可能是词典内部资源，从文本上无法区分；好在它本来在浏览器里也打不开，
    保持原样不会比现在更糟。要区分得靠文件系统，而那是 `/dict-res` 路由的活儿
    （`resolve_resource_file` 会做大小写与 `file:/` 前缀的兜底）。
"""

import logging
from collections.abc import Callable, Mapping

from sqlalchemy import bindparam, func, or_, select, update
from sqlalchemy.orm import Session

from app.models.dictionary import DictEntry
from app.parsers.mdict_stylesheet import expand_style_markers

logger = logging.getLogger("mydict.dictionary")

# 单批处理的主键区间大小。SQLite 一次 UPDATE 的行数不宜过大：大事务会长时间持有写锁，
# 与正在服务的查询互相阻塞；分批 commit 也让中断后重跑只损失最后一批。
DEFAULT_BATCH_SIZE = 5000

_ENTRY_SUFFIX = "entry:/"
_SOUND_SUFFIX = "sound:/"
_FILE_SUFFIX = "file:/"


def _prefixes(dictionary_id: int) -> tuple[str, str, str]:
    """返回 (坏 entry 前缀, 坏 sound 前缀, 坏 file 前缀)。"""
    base = f"/dict-res/{dictionary_id}/res/"
    return base + _ENTRY_SUFFIX, base + _SOUND_SUFFIX, base + _FILE_SUFFIX


def count_legacy_links(db: Session, dictionary_id: int) -> tuple[int, int, int]:
    """统计该词典里含坏 entry / sound / file 链接的行数（只读，供 dry-run 与进度预估）。"""
    entry_from, sound_from, file_from = _prefixes(dictionary_id)
    # 用 FILTER 一次扫描同时拿到三个计数；分三条 SQL 会把该词典的 definition 读三遍。
    row = db.execute(
        select(
            func.count().filter(DictEntry.definition.like(f"%{entry_from}%")),
            func.count().filter(DictEntry.definition.like(f"%{sound_from}%")),
            func.count().filter(DictEntry.definition.like(f"%{file_from}%")),
        ).where(DictEntry.dictionary_id == dictionary_id)
    ).one()
    return int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)


def repair_legacy_links(
    db: Session,
    dictionary_id: int,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    dry_run: bool = False,
    on_progress: Callable[[int, int], None] | None = None,
) -> int:
    """修复某部词典里全部坏链接，返回实际改动的行数。

    dry_run=True 时只统计不改写。按主键区间分批（而不是按 (dictionary_id, word) 唯一索引），
    这样每批只扫一段连续区间；用唯一索引反而会因为排序是 word 导致每批都重扫。
    """
    entry_from, sound_from, file_from = _prefixes(dictionary_id)
    res_prefix = f"/dict-res/{dictionary_id}/res/"
    entry_like = f"%{entry_from}%"
    sound_like = f"%{sound_from}%"
    file_like = f"%{file_from}%"

    bounds = db.execute(
        select(func.min(DictEntry.id), func.max(DictEntry.id)).where(
            DictEntry.dictionary_id == dictionary_id
        )
    ).one()
    lowest, highest = bounds
    if lowest is None or highest is None:
        return 0

    if dry_run:
        entry_count, sound_count, file_count = count_legacy_links(db, dictionary_id)
        logger.info(
            "词典 %s 待修复：entry %s 行、sound %s 行、file %s 行（dry-run，未写入）",
            dictionary_id,
            entry_count,
            sound_count,
            file_count,
        )
        return entry_count + sound_count + file_count

    # 三条替换互不包含，顺序只是保持确定性。内层先执行：
    #   /res/file:/x  -> /res/x      （去掉多出来的 file:/ 前缀）
    #   /res/sound:/x -> /res/x
    #   /res/entry:/x -> entry://x
    new_definition = func.replace(
        func.replace(
            func.replace(DictEntry.definition, file_from, res_prefix), sound_from, res_prefix
        ),
        entry_from,
        "entry://",
    )

    repaired = 0
    scanned = 0
    cursor = lowest - 1
    while cursor < highest:
        window_end = min(cursor + batch_size, highest)
        result = db.execute(
            update(DictEntry)
            .where(
                DictEntry.id > cursor,
                DictEntry.id <= window_end,
                or_(
                    DictEntry.definition.like(entry_like),
                    DictEntry.definition.like(sound_like),
                    DictEntry.definition.like(file_like),
                ),
            )
            .values(definition=new_definition)
        )
        db.commit()
        repaired += result.rowcount or 0
        cursor = window_end
        scanned += 1
        if on_progress is not None:
            on_progress(repaired, cursor - lowest)
    logger.info("词典 %s 修复完成：改动 %s 行（扫了 %s 批）", dictionary_id, repaired, scanned)
    return repaired


def expand_stored_styles(
    db: Session,
    dictionary_id: int,
    stylesheet: Mapping[str, tuple[str, str]],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    on_progress: Callable[[int, int], None] | None = None,
) -> int:
    """把已入库释义里的 `` `编号` `` 样式标记就地展开，返回实际改动的行数。

    与 `repair_legacy_links` 的关键差别：**这次不能用 `func.replace` 表达**。展开时要记住
    「上一个标记的结束标记」（见 `parsers/mdict_stylesheet.py` 里对规则的说明），是带状态的
    扫描，只能在 Python 里逐条转换，所以分批策略变成「按主键区间取一批 → 转换 → 批量写回」。
    写回用 `update(...).where(id == bindparam('row_id'))` 的 executemany 形式，一批一次往返。

    幂等：编号没在样式表里定义时 `expand_style_markers` 原样返回，而展开过之后文本里已经不剩
    定义过的编号了，所以第二次跑改动的行数为 0。

    只挑含反引号的行走转换：绝大多数词典一条都不含，等于省掉整轮 Python 转换。
    """
    bounds = db.execute(
        select(func.min(DictEntry.id), func.max(DictEntry.id)).where(
            DictEntry.dictionary_id == dictionary_id
        )
    ).one()
    lowest, highest = bounds
    if lowest is None or highest is None:
        return 0

    # 用 Core 的 Table 而不是 ORM 实体：ORM 的 update() 在收到 executemany 参数时会走
    # 「按主键批量更新」那条路，而这批参数里只有 id 与 definition、没有完整主键行，会直接报错
    statement = (
        update(DictEntry.__table__)
        .where(DictEntry.__table__.c.id == bindparam("row_id"))
        .values(definition=bindparam("new_definition"))
    )

    changed_total = 0
    cursor = lowest - 1
    while cursor < highest:
        window_end = min(cursor + batch_size, highest)
        # 只取列而不是 ORM 对象：不会往 identity map 里塞几万条记录
        rows = db.execute(
            select(DictEntry.id, DictEntry.definition).where(
                DictEntry.id > cursor,
                DictEntry.id <= window_end,
                DictEntry.dictionary_id == dictionary_id,
                DictEntry.definition.like("%`%"),
            )
        ).all()
        updates = [
            {"row_id": row_id, "new_definition": expanded}
            for row_id, definition in rows
            if (expanded := expand_style_markers(definition or "", stylesheet)) != definition
        ]
        if updates:
            db.execute(statement, updates)
            db.commit()
            changed_total += len(updates)
        cursor = window_end
        if on_progress is not None:
            on_progress(changed_total, cursor - lowest)
    logger.info("词典 %s 样式展开完成：改动 %s 行", dictionary_id, changed_total)
    return changed_total


def dictionaries_using_style_markers(db: Session, dictionary_ids: set[int]) -> set[int]:
    """一次扫描找出「词条里含反引号」的词典，返回与 `dictionary_ids` 的交集。

    为什么要先做这一步：展开需要 `.mdx` 头部里的 `StyleSheet`，而打开一个 `.mdx` 会把整份
    词头索引读进内存——实测 63 部全开要 60~80 秒（搜韵诗词 17.6s、The little dict 8.7s），
    还有个别是 LZO 压缩根本打不开。所以先用一次 LIKE 扫描定位真正含标记的少数几部，
    只对它们打开源文件。这次扫描本身要读一遍全部释义文本（几十秒），但只跑一次，
    而它省下的是 60~80 秒的解析开销加几百 MB 的内存峰值。
    """
    rows = db.execute(
        select(DictEntry.dictionary_id)
        .where(DictEntry.definition.like("%`%"))
        .group_by(DictEntry.dictionary_id)
    ).all()
    return {row[0] for row in rows if row[0] in dictionary_ids}
