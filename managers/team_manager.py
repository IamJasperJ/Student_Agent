import threading
import time
import traceback
import uuid

from Tools.team_messages import normalize_group_id


class AgentTeamManager:
    def __init__(self, worktree_manager):
        self._worktrees = worktree_manager
        self._agents = {}
        self._tasks = {}
        self._lock = threading.Lock()

    def create_agent(self, name, role, system_prompt=None, worktree_id=None, group_id=None):
        # group_id：消息频道，同 id 的 subagent 可 post/fetch（默认 default）
        if worktree_id:
            worktree = self._worktrees.get(worktree_id)
            if not worktree.get("ok"):
                return worktree

        try:
            gid = normalize_group_id(group_id)
        except ValueError as e:
            return {"ok": False, "error": str(e)}

        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        record = {
            "agent_id": agent_id,
            "name": name,
            "role": role,
            "system_prompt": system_prompt or "",
            "worktree_id": worktree_id or "",
            "group_id": gid,
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "tasks": [],
        }
        with self._lock:
            self._agents[agent_id] = record
        return {
            "ok": True,
            "agent_id": agent_id,
            "name": name,
            "role": role,
            "worktree_id": worktree_id or "",
            "group_id": gid,
            "status": "active",
        }

    def list_agents(self):
        with self._lock:
            return {
                "ok": True,
                "agents": [
                    {
                        "agent_id": agent["agent_id"],
                        "name": agent["name"],
                        "role": agent["role"],
                        "worktree_id": agent["worktree_id"],
                        "group_id": agent["group_id"],
                        "status": agent["status"],
                        "task_count": len(agent["tasks"]),
                        "created_at": agent["created_at"],
                        "updated_at": agent["updated_at"],
                    }
                    for agent in self._agents.values()
                ],
            }

    def assign_task(self, agent_id, task, runner, worktree_id=None):
        if worktree_id:
            worktree = self._worktrees.get(worktree_id)
            if not worktree.get("ok"):
                return worktree

        with self._lock:
            agent = self._agents.get(agent_id)
            if not agent:
                return {"ok": False, "error": f"Unknown team agent: {agent_id}"}
            if agent["status"] != "active":
                return {
                    "ok": False,
                    "error": f"Team agent {agent_id} is {agent['status']} and cannot accept tasks.",
                }

            task_id = f"team_task_{uuid.uuid4().hex[:8]}"
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            record = {
                "task_id": task_id,
                "agent_id": agent_id,
                "agent_name": agent["name"],
                "worktree_id": worktree_id or agent["worktree_id"],
                "task": task,
                "status": "queued",
                "cancel_requested": False,
                "review_status": "pending",
                "review_feedback": "",
                "result": None,
                "error": None,
                "created_at": now,
                "updated_at": now,
            }
            self._tasks[task_id] = record
            agent["tasks"].append(task_id)
            agent["updated_at"] = now

        thread = threading.Thread(
            target=self._run_task,
            args=(task_id, runner),
            name=f"team-agent-{agent_id}-{task_id}",
            daemon=True,
        )
        thread.start()
        return {
            "ok": True,
            "agent_id": agent_id,
            "task_id": task_id,
            "status": "queued",
            "review_status": "pending",
        }

    def _update_task(self, task_id, **changes):
        changes["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            self._tasks[task_id].update(changes)

    def _run_task(self, task_id, runner):
        with self._lock:
            if self._tasks[task_id]["status"] == "cancelled":
                return
        self._update_task(task_id, status="running")
        with self._lock:
            task_record = dict(self._tasks[task_id])
            agent_record = dict(self._agents[task_record["agent_id"]])
        try:
            result = runner(agent_record, task_record["task"], task_record.get("worktree_id"))
            with self._lock:
                cancelled = self._tasks[task_id]["cancel_requested"]
            self._update_task(
                task_id,
                status="cancel_requested" if cancelled else "succeeded",
                result=result,
            )
        except Exception as e:
            self._update_task(
                task_id,
                status="failed",
                error=f"{e}\n{traceback.format_exc(limit=5)}",
            )

    def get_task(self, task_id):
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return {"ok": False, "error": f"Unknown team task: {task_id}"}
            return dict(task)

    def list_tasks(self):
        with self._lock:
            return {
                "ok": True,
                "tasks": [
                    {
                        "task_id": task["task_id"],
                        "agent_id": task["agent_id"],
                        "agent_name": task["agent_name"],
                        "worktree_id": task["worktree_id"],
                        "task": task["task"],
                        "status": task["status"],
                        "review_status": task["review_status"],
                        "created_at": task["created_at"],
                        "updated_at": task["updated_at"],
                    }
                    for task in self._tasks.values()
                ],
            }

    def cancel_task(self, task_id):
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return {"ok": False, "error": f"Unknown team task: {task_id}"}
            if task["status"] in {"succeeded", "failed", "cancelled", "cancel_requested"}:
                return {
                    "ok": False,
                    "error": f"Task {task_id} is already {task['status']}.",
                }
            task["cancel_requested"] = True
            if task["status"] == "queued":
                task["status"] = "cancelled"
            else:
                task["status"] = "cancel_requested"
            task["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            return {
                "ok": True,
                "task_id": task_id,
                "status": task["status"],
            }

    def review_task(self, task_id, decision, feedback=None):
        if decision not in {"approved", "rejected"}:
            return {"ok": False, "error": "decision must be approved or rejected"}

        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return {"ok": False, "error": f"Unknown team task: {task_id}"}
            if task["status"] != "succeeded" and task["result"] is None:
                return {
                    "ok": False,
                    "error": f"Task {task_id} is {task['status']} and cannot be reviewed yet.",
                }
            task["review_status"] = decision
            task["review_feedback"] = feedback or ""
            task["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            return {
                "ok": True,
                "task_id": task_id,
                "review_status": task["review_status"],
                "review_feedback": task["review_feedback"],
            }

    def stop_agent(self, agent_id):
        with self._lock:
            agent = self._agents.get(agent_id)
            if not agent:
                return {"ok": False, "error": f"Unknown team agent: {agent_id}"}
            agent["status"] = "stopped"
            agent["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            return {
                "ok": True,
                "agent_id": agent_id,
                "status": "stopped",
                "note": "Running tasks are allowed to finish; no new tasks will be accepted.",
            }
