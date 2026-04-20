import threading
import time
import traceback
import uuid


class BackgroundAgentManager:
    def __init__(self):
        self._tasks = {}
        self._lock = threading.Lock()

    def start(self, task, runner):
        task_id = uuid.uuid4().hex[:8]
        record = {
            "task_id": task_id,
            "task": task,
            "status": "queued",
            "result": None,
            "error": None,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        with self._lock:
            self._tasks[task_id] = record

        thread = threading.Thread(
            target=self._run_task,
            args=(task_id, runner),
            name=f"background-agent-{task_id}",
            daemon=True,
        )
        thread.start()
        return {"ok": True, "task_id": task_id, "status": "queued"}

    def _update(self, task_id, **changes):
        changes["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            self._tasks[task_id].update(changes)

    def _run_task(self, task_id, runner):
        self._update(task_id, status="running")
        with self._lock:
            task = self._tasks[task_id]["task"]
        try:
            result = runner(task)
            self._update(task_id, status="succeeded", result=result)
        except Exception as e:
            self._update(
                task_id,
                status="failed",
                error=f"{e}\n{traceback.format_exc(limit=5)}",
            )

    def get(self, task_id):
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return {"ok": False, "error": f"Unknown background task: {task_id}"}
            return dict(task)

    def list(self):
        with self._lock:
            return {
                "ok": True,
                "tasks": [
                    {
                        "task_id": task["task_id"],
                        "task": task["task"],
                        "status": task["status"],
                        "created_at": task["created_at"],
                        "updated_at": task["updated_at"],
                    }
                    for task in self._tasks.values()
                ],
            }
