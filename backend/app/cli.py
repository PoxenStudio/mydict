"""管理命令行入口：python -m app.cli <command>"""

import argparse
import getpass
import sys
import time

from app.core import migrate as migrations
from app.core.db import SessionLocal
from app.core.exceptions import AppError
from app.core.security import hash_password
from app.models.admin import Admin
from app.models.dictionary import Dictionary
from app.services import definition_repair, dictionary_service


def reset_admin_password(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        admin = db.query(Admin).filter(Admin.username == args.username).first()
        if admin is None:
            print(f"管理员 '{args.username}' 不存在", file=sys.stderr)
            raise SystemExit(1)
        password = args.password or getpass.getpass("新密码：")
        admin.password_hash = hash_password(password)
        db.commit()
        print(f"管理员 '{args.username}' 密码已重置")
    finally:
        db.close()


def _selected_dictionaries(db, args: argparse.Namespace) -> list[Dictionary]:
    query = db.query(Dictionary).order_by(Dictionary.id)
    if args.dictionary_id is not None:
        query = query.filter(Dictionary.id == args.dictionary_id)
    targets = query.all()
    if not targets:
        scope = f"id={args.dictionary_id}" if args.dictionary_id is not None else "全部词典"
        print(f"未找到词典（{scope}）", file=sys.stderr)
        raise SystemExit(1)
    return targets


def repair_entry_links(args: argparse.Namespace) -> None:
    """修复历史上被误改写的 entry:// / sound:// / file:/// 链接（见 definition_repair）。"""
    db = SessionLocal()
    try:
        targets = _selected_dictionaries(db, args)
        if not args.dry_run and not args.yes:
            print(
                "该操作会就地改写 dict_entries.definition，影响面可能达数百万行。\n"
                "请先用 --dry-run 查看待修数量；确认无误后加 --yes 执行。",
                file=sys.stderr,
            )
            raise SystemExit(1)

        print(f"{'[dry-run] ' if args.dry_run else ''}待处理词典 {len(targets)} 部")
        total = 0
        touched = 0
        for dictionary in targets:
            # 先统计：既给 dry-run 用，也让真正执行时能跳过没有坏链接的词典
            # （避免为它们白扫一遍整部词典的 definition）。
            entry_rows, sound_rows, file_rows = definition_repair.count_legacy_links(
                db, dictionary.id
            )
            if entry_rows == 0 and sound_rows == 0 and file_rows == 0:
                continue
            touched += 1
            print(
                f"  id={dictionary.id} {dictionary.name}："
                f"entry {entry_rows} 行 / sound {sound_rows} 行 / file {file_rows} 行"
            )
            if args.dry_run:
                total += entry_rows + sound_rows + file_rows
                continue
            started = time.monotonic()
            repaired = definition_repair.repair_legacy_links(
                db, dictionary.id, batch_size=args.batch_size
            )
            total += repaired
            print(f"      已修复 {repaired} 行，用时 {time.monotonic() - started:.1f}s")

        if touched == 0:
            print("没有找到需要修复的坏链接。")
        else:
            print(f"{'合计待修复' if args.dry_run else '合计修复'} {total} 行（{touched} 部词典）")
        if not args.dry_run and touched:
            # query_cache 是进程内的，CLI 清不到正在服务的那个进程。
            print(
                "\n提示：查询结果缓存在应用进程内，本次修复不会清掉它。" "请重启应用容器后再验证。"
            )
    finally:
        db.close()


def redetect_languages(args: argparse.Namespace) -> None:
    """按当前采样逻辑重新识别词典的语言方向。

    语言方向是导入时自动识别的，而查询路由按 `lang_from` 过滤——判错就等于那部词典的
    内容查不到（实测用户的「汉典」46 万条被判成 en，中文查询永远匹配不到它）。采样
    逻辑已经改成「跨整部词典取词头 + 剔掉无信息量样本」，但**已入库的值不会自动更新**，
    所以需要这个命令回溯修正。
    """
    db = SessionLocal()
    try:
        targets = _selected_dictionaries(db, args)
        if not args.dry_run and not args.yes:
            print(
                "该操作会改写 dictionaries.lang_from / lang_to，可能覆盖手工修正过的值。\n"
                "请先用 --dry-run 查看识别结果；确认无误后加 --yes 执行。",
                file=sys.stderr,
            )
            raise SystemExit(1)

        print(f"{'[dry-run] ' if args.dry_run else ''}待识别词典 {len(targets)} 部")
        changed = 0
        for dictionary in targets:
            before = f"{dictionary.lang_from}→{dictionary.lang_to}"
            try:
                detected_from, detected_to = dictionary_service.detect_dictionary_language(
                    dictionary
                )
            except AppError as exc:
                print(f"  id={dictionary.id} {dictionary.name}：跳过（{exc.message}）")
                continue
            after = f"{detected_from or dictionary.lang_from}→{detected_to or dictionary.lang_to}"
            mark = "← 与现值不同" if after != before else ""
            print(f"  id={dictionary.id} {dictionary.name}：{before} → {after} {mark}")
            if args.dry_run or after == before:
                continue
            if dictionary_service.apply_detected_language(
                db, dictionary, detected_from, detected_to
            ):
                changed += 1

        if args.dry_run:
            print("\ndry-run 未写入任何改动。")
        else:
            print(f"\n共更新 {changed} 部词典的语言方向。")
            if changed:
                print("提示：查询结果缓存在应用进程内，请重启应用容器后再验证。")
    finally:
        db.close()


def _format_size(num_bytes: int) -> str:
    return f"{num_bytes / 1024**3:.1f}GB"


def migrate(args: argparse.Namespace) -> None:
    """手动执行数据库迁移。重型迁移不在启动时自动跑（见 app/core/migrate.py），走这里。

    必须先停掉服务：迁移期间 SQLite 被独占，服务同时读写只会互相卡住。
    """
    pending = migrations.pending_migrations()
    if not pending:
        print("数据库已是最新版本，无需迁移")
        return

    print(f"待执行的迁移 {len(pending)} 个：")
    for item in pending:
        print(f"  {item.revision}  {item.title}{'  [重型：整表重建]' if item.heavy else ''}")

    has_heavy = any(item.heavy for item in pending)
    if has_heavy:
        db_size, free = migrations.free_space_for_database()
        print(
            f"数据库文件 {_format_size(db_size)}，所在磁盘剩余 {_format_size(free)}。"
            "重型迁移会整表重建，需要约与数据库同等大小的剩余空间，大库上要跑很久。"
        )
        if free < db_size:
            print("剩余磁盘空间不足，已中止。请先腾出空间。", file=sys.stderr)
            raise SystemExit(1)

    if args.dry_run:
        return
    if not args.yes:
        print(
            "请先停止服务、备份数据库文件，确认后加 --yes 执行。中途被打断可以直接重跑。",
            file=sys.stderr,
        )
        raise SystemExit(1)

    started = time.monotonic()
    migrations.upgrade_to_head()
    print(f"迁移完成，用时 {time.monotonic() - started:.0f} 秒")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    reset_parser = subparsers.add_parser("reset-admin-password", help="重置管理员密码")
    reset_parser.add_argument("--username", default="admin")
    reset_parser.add_argument("--password", default=None, help="不传则交互式输入")
    reset_parser.set_defaults(func=reset_admin_password)

    repair_parser = subparsers.add_parser(
        "repair-entry-links",
        help="修复历史遗留的坏链接（entry:// / sound:// / file:///）",
    )
    repair_parser.add_argument(
        "--dictionary-id", type=int, default=None, help="只修某部词典，省略则处理全部"
    )
    repair_parser.add_argument(
        "--batch-size", type=int, default=definition_repair.DEFAULT_BATCH_SIZE
    )
    repair_parser.add_argument("--dry-run", action="store_true", help="只统计不写入")
    repair_parser.add_argument("--yes", action="store_true", help="确认执行写入")
    repair_parser.set_defaults(func=repair_entry_links)

    redetect_parser = subparsers.add_parser(
        "redetect-languages", help="重新识别词典语言方向（修正导入时的误判）"
    )
    redetect_parser.add_argument(
        "--dictionary-id", type=int, default=None, help="只处理某部词典，省略则处理全部"
    )
    redetect_parser.add_argument("--dry-run", action="store_true", help="只识别不写入")
    redetect_parser.add_argument("--yes", action="store_true", help="确认执行写入")
    redetect_parser.set_defaults(func=redetect_languages)

    migrate_parser = subparsers.add_parser(
        "migrate", help="手动执行数据库迁移（重型迁移不会在启动时自动执行）"
    )
    migrate_parser.add_argument("--dry-run", action="store_true", help="只列出待执行的迁移")
    migrate_parser.add_argument("--yes", action="store_true", help="确认执行")
    migrate_parser.set_defaults(func=migrate)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
