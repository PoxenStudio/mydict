from app.services.background_task_service import BackgroundTaskService


def test_start_update_succeed_lifecycle() -> None:
    service = BackgroundTaskService()
    task = service.start("dictionary_import", "测试词典")
    assert task.status == "running"
    assert service.list_running() == [
        {
            "id": task.id,
            "task_type": "dictionary_import",
            "title": "测试词典",
            "status": "running",
            "progress_data": {},
            "result": None,
            "error": None,
            "created_at": task.created_at,
            "updated_at": task.created_at,
        }
    ]

    service.update_progress(task.id, {"done": 2000})
    running = service.list_running()
    assert running[0]["progress_data"] == {"done": 2000}

    service.succeed(task.id, {"dictionary_id": 1, "word_count": 2000})
    # 成功/失败后不再是 running，不出现在 list_running() 里，但 get() 仍能取到终态
    assert service.list_running() == []
    finished = service.get(task.id)
    assert finished is not None
    assert finished["status"] == "success"
    assert finished["result"] == {"dictionary_id": 1, "word_count": 2000}


def test_fail_records_error_message() -> None:
    service = BackgroundTaskService()
    task = service.start("dictionary_import", "测试词典")
    service.fail(task.id, "解析失败：缺少必要文件")
    finished = service.get(task.id)
    assert finished is not None
    assert finished["status"] == "error"
    assert finished["error"] == "解析失败：缺少必要文件"
    assert service.list_running() == []


def test_succeed_unknown_task_is_noop() -> None:
    service = BackgroundTaskService()
    service.succeed(999, {})  # 不存在的 id 不应报错
    assert service.get(999) is None
    assert service.list_running() == []


def test_get_unknown_task_returns_none() -> None:
    service = BackgroundTaskService()
    assert service.get(999) is None


def test_list_running_sorted_by_start_order() -> None:
    service = BackgroundTaskService()
    first = service.start("dictionary_import", "第一个")
    second = service.start("dictionary_import", "第二个")
    titles = [t["title"] for t in service.list_running()]
    assert titles == ["第一个", "第二个"]
    service.succeed(first.id, {})
    service.fail(second.id, "boom")
    assert service.list_running() == []
