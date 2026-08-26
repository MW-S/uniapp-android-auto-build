import time

from pipeline.build_manager import BuildManager


def wait_until(cond, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_trigger_rejected_while_busy():
    manager = BuildManager()
    first = manager.trigger("demo-app", "示例项目", lambda: time.sleep(0.3))
    assert first is not None
    assert manager.is_busy()
    rejected = manager.trigger("demo-app", "示例项目", lambda: None)
    assert rejected is None
    assert "进行中" in manager.reject_reason
    assert wait_until(lambda: not manager.is_busy())


def test_trigger_after_finished_returns_new_job_id():
    manager = BuildManager()
    first = manager.trigger("demo-app", "示例项目", lambda: "ok")
    assert wait_until(lambda: not manager.is_busy())
    finished = manager.get_job(first)
    assert finished is not None
    assert finished["busy"] is False
    assert finished["result"] == "ok"
    second = manager.trigger("demo-app", "示例项目", lambda: None)
    assert second is not None
    assert second != first
    assert wait_until(lambda: not manager.is_busy())


def test_build_fn_closure_has_access_to_job():
    manager = BuildManager()
    seen = {}

    def build_fn():
        seen["job"] = manager.current_job()
        return "done"

    job_id = manager.trigger("demo-app", "示例项目", build_fn)
    assert wait_until(lambda: not manager.is_busy())
    assert seen["job"] is not None
    assert seen["job"]["job_id"] == job_id
    assert manager.get_job(job_id)["result"] == "done"


def test_get_job_missing_returns_none():
    manager = BuildManager()
    assert manager.get_job("no-such-job") is None


def test_set_running_step_and_set_report_missing_job_return_false():
    manager = BuildManager()
    assert manager.set_running_step("no-such-job", "启动中") is False
    assert manager.set_report("no-such-job", object()) is False