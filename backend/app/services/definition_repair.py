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
import re
from collections.abc import Callable, Mapping
from pathlib import Path

from sqlalchemy import bindparam, func, or_, select, update
from sqlalchemy.orm import Session

from app.models.dictionary import DictEntry, Dictionary
from app.parsers.mdict_stylesheet import expand_style_markers
from app.services.entry_scope import in_dictionary_for_id_window

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
                # 主键区间里可能夹着别的词典的行（导入/重新解析交错写入），必须按词典过滤
                in_dictionary_for_id_window(dictionary_id),
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
                in_dictionary_for_id_window(dictionary_id),
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
    """在 `dictionary_ids` 里找出「词条里含反引号」的 MDict 词典。

    为什么要先做这一步：展开需要 `.mdx` 头部里的 `StyleSheet`，而打开一个 `.mdx` 会把整份
    词头索引读进内存——实测 63 部全开要 60~80 秒（搜韵诗词 17.6s、The little dict 8.7s），
    还有个别是 LZO 压缩根本打不开。所以先定位真正含标记的少数几部，只对它们打开源文件。

    逐部用 `EXISTS … LIMIT 1` 判断，而不是对整张表 LIKE + GROUP BY：只看调用方要修的那几部
    （管理员只勾一部时不该扫 29GB）、只看 MDict（StyleSheet 只存在于 `.mdx`），且命中第一条就停。
    最坏情况（一部都不含）是把选中词典的释义各读一遍，不会比全表扫描更多。
    """
    if not dictionary_ids:
        return set()
    candidates = db.execute(
        select(Dictionary.id).where(
            Dictionary.id.in_(dictionary_ids), Dictionary.format == "mdict"
        )
    ).scalars()
    found: set[int] = set()
    for dictionary_id in candidates:
        hit = db.execute(
            select(DictEntry.id)
            .where(DictEntry.dictionary_id == dictionary_id, DictEntry.definition.like("%`%"))
            .limit(1)
        ).first()
        if hit is not None:
            found.add(dictionary_id)
    return found


# ---------------------------------------------------- 牛津9 例句红色美音喇叭清理

# 牛津高阶第9版例句的发音是一对喇叭：蓝色英音（audio-gbs-liju）+ 红色美音
# （audio-uss-liju）。美音 mp3 源词典就基本没打包——实测 38,869 个引用里 99% 的文件
# 不存在（38,739 个），点红色喇叭必弹「发音不存在或解码失败」。这里把**指向缺失文件**
# 的红色喇叭整对锚点删掉；文件还在的（实测 130 个）原样保留。
#
# 注意：重新解析会从源文件重灌释义，喇叭会被带回来，届时需要重跑本修复。

_USS_ANCHOR_RE = re.compile(
    r'<a href="(?P<url>[^"]*uss[^"]*\.mp3)"><audio-uss-liju>[^<]*</audio-uss-liju></a>'
)


def remove_missing_uss_speakers(
    db: Session,
    dictionary_id: int,
    res_dir: Path,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[int, int]:
    """删掉「指向缺失 mp3」的红色美音喇叭锚点，返回 (改动词条数, 删除的喇叭数)。

    只删锚点本身：包裹它的 <audio-wr>、蓝色英音喇叭与例句文本一概不动。文件存在性
    走 resolve_resource_file（大小写不敏感兜底），与 /dict-res 路由的解析完全一致——
    路由能取到的文件就不删按钮。
    """
    from app.services.resource_service import resolve_resource_file

    def clean(definition: str) -> tuple[str, int]:
        removed = 0

        def replace(match: re.Match[str]) -> str:
            nonlocal removed
            relative = match.group("url").split("/res/", 1)[-1]
            if resolve_resource_file(res_dir, relative) is not None:
                return match.group(0)  # 文件还在，按钮保留
            removed += 1
            return ""

        return _USS_ANCHOR_RE.sub(replace, definition), removed

    statement = (
        update(DictEntry.__table__)
        .where(DictEntry.__table__.c.id == bindparam("row_id"))
        .values(definition=bindparam("new_definition"))
    )

    entries_changed = 0
    anchors_removed = 0
    cursor = -1
    while True:
        rows = db.execute(
            select(DictEntry.id, DictEntry.definition)
            .where(
                DictEntry.id > cursor,
                DictEntry.dictionary_id == dictionary_id,
                DictEntry.definition.like("%audio-uss-liju%"),
            )
            .order_by(DictEntry.id)
            .limit(batch_size)
        ).all()
        if not rows:
            break
        cursor = rows[-1][0]
        updates = []
        for row_id, definition in rows:
            cleaned, removed = clean(definition or "")
            if removed:
                updates.append({"row_id": row_id, "new_definition": cleaned})
                anchors_removed += removed
        if updates:
            db.execute(statement, updates)
            db.commit()
            entries_changed += len(updates)
        if on_progress is not None:
            on_progress(entries_changed, anchors_removed)
    logger.info(
        "词典 %s 红色例句喇叭清理完成：改动 %s 条词条、删除 %s 个喇叭",
        dictionary_id,
        entries_changed,
        anchors_removed,
    )
    return entries_changed, anchors_removed
