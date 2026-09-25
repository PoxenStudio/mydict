import json
import shutil
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.deps import require_admin
from app.core.exceptions import NotFoundError, ValidationAppError
from app.models.admin import Admin
from app.models.dictionary import Dictionary
from app.schemas.dictionary import (
    BatchStatusRequest,
    DictionaryIdsRequest,
    DictionaryImportTaskOut,
    DictionaryOut,
    DictionaryUpdateRequest,
    DictsDirListingOut,
    ImportFromDictsDirRequest,
    RenameDictionariesOut,
    RenameDictionariesRequest,
    ReorderRequest,
    TestQueryEntryOut,
)
from app.services import dictionary_service, query_service, resource_service
from app.services.entry_render_service import render_entries_document

router = APIRouter(prefix="/admin/dictionaries", tags=["admin-dictionaries"])

_CHUNK_SIZE = 1024 * 1024


async def _save_upload_files(files: list[UploadFile], settings: Settings) -> list[Path]:
    staging_dir = Path(settings.dictionary_storage_path) / "_staging" / uuid.uuid4().hex
    staging_dir.mkdir(parents=True, exist_ok=True)
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    total = 0
    saved: list[Path] = []
    try:
        for upload in files:
            filename = Path(upload.filename or "").name
            if not filename:
                raise ValidationAppError("上传文件缺少文件名")
            target = staging_dir / filename
            with target.open("wb") as out:
                while chunk := await upload.read(_CHUNK_SIZE):
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValidationAppError(
                            f"上传文件总大小超过限制（{settings.max_upload_size_mb}MB）"
                        )
                    out.write(chunk)
            saved.append(target)
        return saved
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise


def _entry_to_out(entry) -> TestQueryEntryOut:
    return TestQueryEntryOut(
        word=entry.word,
        phonetic=entry.phonetic,
        definition=entry.definition,
        extra=json.loads(entry.extra) if entry.extra else None,
    )


@router.get("", response_model=list[DictionaryOut])
def list_dictionaries(
    db: Session = Depends(get_db),
    _admin: Admin = Depends(require_admin),
) -> list[DictionaryOut]:
    return dictionary_service.list_dictionaries(db)


@router.post("", response_model=DictionaryImportTaskOut)
async def upload_and_import(
    name: str = Form(...),
    format: str = Form(...),
    lang_from: str = Form(...),
    lang_to: str = Form(...),
    files: list[UploadFile] = File(...),
    admin: Admin = Depends(require_admin),
    settings: Settings = Depends(get_settings),
) -> DictionaryImportTaskOut:
    staged_paths = await _save_upload_files(files, settings)
    task_id = dictionary_service.start_dictionary_import(
        name=name,
        format_=format,
        lang_from=lang_from,
        lang_to=lang_to,
        staged_paths=staged_paths,
        settings=settings,
        admin_id=admin.id,
        import_method="upload",
    )
    return DictionaryImportTaskOut(task_id=task_id)


@router.get("/dicts-dir-files", response_model=DictsDirListingOut)
def dicts_dir_files(
    path: str = "",
    recursive: bool = False,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _admin: Admin = Depends(require_admin),
) -> DictsDirListingOut:
    normalized, entries, dictionaries, skipped = dictionary_service.list_dicts_dir_files(
        db, settings, path, recursive
    )
    return DictsDirListingOut(
        path=normalized,
        entries=entries,
        dictionaries=dictionaries,
        skipped=skipped,
    )


@router.post("/import-from-dicts-dir", response_model=DictionaryImportTaskOut)
def import_from_dicts_dir(
    body: ImportFromDictsDirRequest,
    admin: Admin = Depends(require_admin),
    settings: Settings = Depends(get_settings),
) -> DictionaryImportTaskOut:
    staged_paths = dictionary_service.resolve_dicts_dir_files(body.files, settings)
    task_id = dictionary_service.start_dictionary_import(
        name=body.name,
        format_=body.format,
        lang_from=body.lang_from,
        lang_to=body.lang_to,
        staged_paths=staged_paths,
        settings=settings,
        admin_id=admin.id,
        import_method="dicts_dir",
        skip_resources=body.skip_resources,
    )
    return DictionaryImportTaskOut(task_id=task_id)


@router.put("/reorder", response_model=list[DictionaryOut])
def reorder(
    body: ReorderRequest,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_admin),
) -> list[DictionaryOut]:
    return dictionary_service.reorder_dictionaries(db, body.ordered_ids, admin.id)


@router.put("/batch-status", response_model=list[DictionaryOut])
def batch_status(
    body: BatchStatusRequest,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_admin),
) -> list[DictionaryOut]:
    return dictionary_service.set_dictionaries_status(
        db, body.dictionary_ids, body.status, admin.id
    )


@router.post("/repair-from-source", response_model=DictionaryImportTaskOut)
def repair_from_source(
    body: DictionaryIdsRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _admin: Admin = Depends(require_admin),
) -> DictionaryImportTaskOut:
    """把「只存在于源文件里、导入时被漏掉的东西」补进已导入的词典。

    一次做两件事，都**不需要重新导入**：

    1. 补 `.mdx` 同级的附属资源（CSS/字体/脚本/图片）。MDict 的样式表与字体按惯例就躺在
       `.mdx` 旁边而不是 `.mdd` 里，早先的导入代码只解包 `.mdd`，于是这些文件全部缺失——
       词条以无样式渲染，图标回到原始像素、表格丢边框。
    2. 展开词条里的 `` `编号` `` 样式标记（规则来自 `.mdx` 头部的 `StyleSheet`）。此前完全
       没处理，标记原样显示，看起来就是排版错乱。

    空 dictionary_ids 表示全部词典。
    """
    return DictionaryImportTaskOut(
        task_id=dictionary_service.start_source_repair(db, body.dictionary_ids, settings)
    )


@router.post("/reparse", response_model=DictionaryImportTaskOut)
def reparse_dictionaries(
    body: DictionaryIdsRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _admin: Admin = Depends(require_admin),
) -> DictionaryImportTaskOut:
    """重新解析词典：重读源文件、把词条整个重灌一遍（词典 id 不变）。

    给「同名词词条曾被按词头去重丢掉」的存量词典找回内容——约束去掉后已入库的行不会自动
    长出来。词条 id 会变（没有数据引用它）；生词本存的是释义快照与词典 id，不受影响。
    空 dictionary_ids 表示全部词典；源文件不在的词典会被跳过并计数。
    """
    return DictionaryImportTaskOut(
        task_id=dictionary_service.start_reparse(db, body.dictionary_ids, settings)
    )


@router.post("/rename", response_model=RenameDictionariesOut)
def rename_dictionaries(
    body: RenameDictionariesRequest,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_admin),
) -> RenameDictionariesOut:
    """按正则批量重命名词典。

    默认 dry_run：前端先拿一份「原名称 → 新名称」的对照表给管理员过目，确认后再以
    dry_run=false 调一次真正落库。响应里只含会被改名的条目。
    """
    return dictionary_service.rename_dictionaries(
        db,
        pattern=body.pattern,
        replacement=body.replacement,
        dictionary_ids=body.dictionary_ids,
        dry_run=body.dry_run,
        admin_id=admin.id,
    )


@router.put("/{dictionary_id}", response_model=DictionaryOut)
def update_dictionary(
    dictionary_id: int,
    body: DictionaryUpdateRequest,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_admin),
) -> DictionaryOut:
    return dictionary_service.update_dictionary_metadata(
        db, dictionary_id, body.name, body.lang_from, body.lang_to, admin.id
    )


@router.put("/{dictionary_id}/enable", response_model=DictionaryOut)
def enable(
    dictionary_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_admin),
) -> DictionaryOut:
    return dictionary_service.set_dictionary_status(db, dictionary_id, "enabled", admin.id)


@router.put("/{dictionary_id}/disable", response_model=DictionaryOut)
def disable(
    dictionary_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_admin),
) -> DictionaryOut:
    return dictionary_service.set_dictionary_status(db, dictionary_id, "disabled", admin.id)


@router.delete("/{dictionary_id}")
def remove(
    dictionary_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_admin),
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    dictionary_service.delete_dictionary(db, dictionary_id, admin.id, settings)
    return {"ok": True}


@router.get("/{dictionary_id}/test-query", response_model=list[TestQueryEntryOut])
def test_query(
    dictionary_id: int,
    word: str,
    db: Session = Depends(get_db),
    _admin: Admin = Depends(require_admin),
) -> list[TestQueryEntryOut]:
    entries = dictionary_service.test_query(db, dictionary_id, word)
    return [_entry_to_out(e) for e in entries]


@router.get("/{dictionary_id}/entry", response_class=HTMLResponse)
def entry_document(
    dictionary_id: int,
    word: str,
    theme: Literal["light", "dark"] | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _admin: Admin = Depends(require_admin),
) -> HTMLResponse:
    """管理端预览单条词条，供「测试查询」弹窗放进隔离 iframe。

    与前台 /api/dict/entry/{id} 的区别是**不检查启用状态**——测试查询的对象常常正是
    一部还没启用的词典，前台那条路会把它们挡掉。
    必须走 iframe 而不是 v-html：管理端 token 也在 localStorage 里，用 v-html 渲染
    第三方词典的 HTML 等于把权限最高的凭证暴露出去。
    """
    dictionary = db.get(Dictionary, dictionary_id)
    if dictionary is None:
        raise NotFoundError("词典不存在")
    # 与前台一致：同一词头的多条聚合进一个文档（见 query_service.get_entries_for_document）
    entries = query_service.get_entries_for_document(db, dictionary_id, word)
    if not entries:
        raise NotFoundError("词条不存在")
    return HTMLResponse(
        render_entries_document(
            [(e.word, e.definition, e.phonetic) for e in entries],
            dictionary_id=dictionary_id,
            theme=theme,
            extra_head_assets=resource_service.same_name_assets(
                Path(settings.dictionary_storage_path) / str(dictionary_id) / "res",
                dictionary_id,
                dictionary.file_path,
            ),
        )
    )
