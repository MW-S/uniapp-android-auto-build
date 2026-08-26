import threading
from uuid import uuid4


class BuildManager:
    def __init__(self):
        self._busy_lock = threading.Lock()
        self._jobs_lock = threading.Lock()
        self._jobs = {}
        self._current_job_id = None
        self._reject_reason = ""

    @property
    def reject_reason(self) -> str:
        return self._reject_reason

    def trigger(self, project_key, project_name, build_fn) -> str | None:
        if not self._busy_lock.acquire(blocking=False):
            self._reject_reason = "已存在进行中的构建任务，请等待其完成后再发起新的构建"
            return None
        self._reject_reason = ""
        job_id = uuid4().hex[:8]
        job = {
            "job_id": job_id,
            "project_key": project_key,
            "project_name": project_name,
            "build_fn": build_fn,
            "report": None,
            "running_step": None,
            "busy": True,
            "result": None,
        }
        with self._jobs_lock:
            self._jobs[job_id] = job
            self._current_job_id = job_id

        def worker():
            try:
                with self._jobs_lock:
                    current = self._jobs.get(job_id)
                    if current is None:
                        return
                    current["busy"] = True
                    current["running_step"] = "启动中"
                try:
                    current["result"] = build_fn()
                except Exception as exc:
                    current["result"] = f"构建执行异常: {exc!r}"
            finally:
                with self._jobs_lock:
                    job_ref = self._jobs.get(job_id)
                    if job_ref is not None:
                        job_ref["busy"] = False
                        job_ref["running_step"] = None
                    if self._current_job_id == job_id:
                        self._current_job_id = None
                self._busy_lock.release()

        thread = threading.Thread(target=worker, name=f"build-{job_id}", daemon=True)
        thread.start()
        return job_id

    def get_job(self, job_id):
        with self._jobs_lock:
            return self._jobs.get(job_id)

    def current_job(self):
        with self._jobs_lock:
            if self._current_job_id is None:
                return None
            return self._jobs.get(self._current_job_id)

    def is_busy(self) -> bool:
        return self._busy_lock.locked()

    def set_running_step(self, job_id, step) -> bool:
        with self._jobs_lock:
            if job_id not in self._jobs:
                return False
            self._jobs[job_id]["running_step"] = step
        return True

    def set_report(self, job_id, report) -> bool:
        with self._jobs_lock:
            if job_id not in self._jobs:
                return False
            self._jobs[job_id]["report"] = report
        return True


build_manager = BuildManager()