from app.services.background_task_service import BackgroundTaskService


def test_start_update_finish_lifecycle() -> None:
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
            "created_at": task.created_at,
            "updated_at": task.created_at,
        }
    ]

    service.update_progress(task.id, {"done": 2000})
    running = service.list_running()
    assert running[0]["progress_data"] == {"done": 2000}

    service.finish(task.id)
    assert service.list_running() == []


def test_finish_unknown_task_is_noop() -> None:
    service = BackgroundTaskService()
    service.finish(999)  # 不存在的 id 不应报错
    assert service.list_running() == []


def test_list_running_sorted_by_start_order() -> None:
    service = BackgroundTaskService()
    first = service.start("dictionary_import", "第一个")
    second = service.start("dictionary_import", "第二个")
    titles = [t["title"] for t in service.list_running()]
    assert titles == ["第一个", "第二个"]
    service.finish(first.id)
    service.finish(second.id)
