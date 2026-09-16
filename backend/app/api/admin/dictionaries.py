import json
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.deps import require_admin
from app.core.exceptions import ValidationAppError
from app.models.admin import Admin
from app.schemas.dictionary import (
    DictionaryImportTaskOut,
    DictionaryOut,
    DictionaryUpdateRequest,
    DictsDirListingOut,
    ImportFromDictsDirRequest,
    ReorderRequest,
    TestQueryEntryOut,
)
from app.services import dictionary_service

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
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _admin: Admin = Depends(require_admin),
) -> DictsDirListingOut:
    normalized, entries = dictionary_service.list_dicts_dir_files(db, settings, path)
    return DictsDirListingOut(path=normalized, entries=entries)


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
    )
    return DictionaryImportTaskOut(task_id=task_id)


@router.put("/reorder", response_model=list[DictionaryOut])
def reorder(
    body: ReorderRequest,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_admin),
) -> list[DictionaryOut]:
    return dictionary_service.reorder_dictionaries(db, body.ordered_ids, admin.id)


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
