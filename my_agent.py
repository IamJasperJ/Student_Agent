from openai import OpenAI
import os
import json
from pathlib import Path
from dotenv import load_dotenv
import sys
import re
import subprocess
import threading
import time
import traceback
import uuid

root_path = str(Path(__file__).resolve().parent)
if root_path not in sys.path:
    sys.path.append(root_path)

import Tools
load_dotenv(override=True)

API_KEY = os.getenv('API_KEY')
MODEL = os.getenv('MODEL_ID')
API_URL = os.getenv('MODEL_BASE_URL')
if not API_KEY or not MODEL or not API_URL:
    raise RuntimeError("Missing API_KEY, MODEL_ID, or MODEL_BASE_URL in environment.")

client = OpenAI(
    api_key=API_KEY, 
    base_url=API_URL 
)

WORKDIR = Path.cwd()
EXECUTION_CONTEXT = threading.local()


def current_workdir():
    return getattr(EXECUTION_CONTEXT, "workdir", WORKDIR)


def current_tool_scope():
    return getattr(EXECUTION_CONTEXT, "tool_scope", "main")

BASE_TOOLS = [
    Tools.RUNBASH_DESCRIPTION,
    Tools.RUNREAD_DESCRIPTION,
    Tools.CONTEXTCOMPRESSION_DESCRIPTION,
    Tools.GETSCHE_DESCRIPTION,
]

START_BACKGROUND_TASK_DESCRIPTION = {
    "type": "function",
    "function": {
        "name": "start_background_task",
        "description": "Start a background sub-agent task and return a task id immediately.",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The concrete task for the background sub-agent to complete."
                }
            },
            "required": ["task"]
        }
    }
}

GET_BACKGROUND_TASK_DESCRIPTION = {
    "type": "function",
    "function": {
        "name": "get_background_task",
        "description": "Get status and result for a background sub-agent task.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The task id returned by start_background_task."
                }
            },
            "required": ["task_id"]
        }
    }
}

LIST_BACKGROUND_TASKS_DESCRIPTION = {
    "type": "function",
    "function": {
        "name": "list_background_tasks",
        "description": "List all background sub-agent tasks and their current status.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
}

CREATE_TEAM_AGENT_DESCRIPTION = {
    "type": "function",
    "function": {
        "name": "create_team_agent",
        "description": "Create a named sub-agent with a role and optional system prompt.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Short readable name for the sub-agent."
                },
                "role": {
                    "type": "string",
                    "description": "Responsibility or specialty for the sub-agent."
                },
                "system_prompt": {
                    "type": "string",
                    "description": "Optional extra instruction for this sub-agent."
                },
                "worktree_id": {
                    "type": "string",
                    "description": "Optional managed worktree id where this sub-agent should work."
                }
            },
            "required": ["name", "role"]
        }
    }
}

LIST_TEAM_AGENTS_DESCRIPTION = {
    "type": "function",
    "function": {
        "name": "list_team_agents",
        "description": "List agent team members and their lifecycle status.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
}

ASSIGN_TEAM_TASK_DESCRIPTION = {
    "type": "function",
    "function": {
        "name": "assign_team_task",
        "description": "Assign a task to a specific team sub-agent and run it in the background.",
        "parameters": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "The sub-agent id returned by create_team_agent."
                },
                "task": {
                    "type": "string",
                    "description": "The concrete task for the sub-agent."
                },
                "worktree_id": {
                    "type": "string",
                    "description": "Optional managed worktree id overriding the sub-agent default for this task."
                }
            },
            "required": ["agent_id", "task"]
        }
    }
}

GET_TEAM_TASK_DESCRIPTION = {
    "type": "function",
    "function": {
        "name": "get_team_task",
        "description": "Get status, result, review state, and lifecycle metadata for a team task.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The team task id returned by assign_team_task."
                }
            },
            "required": ["task_id"]
        }
    }
}

LIST_TEAM_TASKS_DESCRIPTION = {
    "type": "function",
    "function": {
        "name": "list_team_tasks",
        "description": "List team tasks with status, owner agent, and review state.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
}

CANCEL_TEAM_TASK_DESCRIPTION = {
    "type": "function",
    "function": {
        "name": "cancel_team_task",
        "description": "Request cancellation for a team task that has not completed.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The team task id to cancel."
                }
            },
            "required": ["task_id"]
        }
    }
}

REVIEW_TEAM_TASK_DESCRIPTION = {
    "type": "function",
    "function": {
        "name": "review_team_task",
        "description": "Approve or reject a completed team task result with optional feedback.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The team task id to review."
                },
                "decision": {
                    "type": "string",
                    "enum": ["approved", "rejected"],
                    "description": "Review decision for the completed task."
                },
                "feedback": {
                    "type": "string",
                    "description": "Optional review feedback."
                }
            },
            "required": ["task_id", "decision"]
        }
    }
}

STOP_TEAM_AGENT_DESCRIPTION = {
    "type": "function",
    "function": {
        "name": "stop_team_agent",
        "description": "Stop a team sub-agent lifecycle so it accepts no new tasks.",
        "parameters": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "The sub-agent id to stop."
                }
            },
            "required": ["agent_id"]
        }
    }
}

CREATE_WORKTREE_DESCRIPTION = {
    "type": "function",
    "function": {
        "name": "create_worktree",
        "description": "Create an isolated git worktree under .agent_worktrees for coding tasks.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Short safe name for the worktree directory."
                },
                "branch": {
                    "type": "string",
                    "description": "Optional branch name. Defaults to agent/<name>-<id>."
                },
                "base_ref": {
                    "type": "string",
                    "description": "Optional base ref to create from. Defaults to HEAD."
                },
                "create_branch": {
                    "type": "boolean",
                    "description": "Whether to create a new branch for the worktree. Defaults to true."
                }
            },
            "required": ["name"]
        }
    }
}

LIST_WORKTREES_DESCRIPTION = {
    "type": "function",
    "function": {
        "name": "list_worktrees",
        "description": "List git worktrees and mark which ones are managed by this agent.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
}

GET_WORKTREE_DESCRIPTION = {
    "type": "function",
    "function": {
        "name": "get_worktree",
        "description": "Get details for a managed worktree.",
        "parameters": {
            "type": "object",
            "properties": {
                "worktree_id": {
                    "type": "string",
                    "description": "Managed worktree id, usually the directory name."
                }
            },
            "required": ["worktree_id"]
        }
    }
}

REMOVE_WORKTREE_DESCRIPTION = {
    "type": "function",
    "function": {
        "name": "remove_worktree",
        "description": "Remove a managed worktree under .agent_worktrees.",
        "parameters": {
            "type": "object",
            "properties": {
                "worktree_id": {
                    "type": "string",
                    "description": "Managed worktree id to remove."
                },
                "force": {
                    "type": "boolean",
                    "description": "Force removal even if git reports local changes. Defaults to false."
                }
            },
            "required": ["worktree_id"]
        }
    }
}

BACKGROUND_TOOLS = [
    START_BACKGROUND_TASK_DESCRIPTION,
    GET_BACKGROUND_TASK_DESCRIPTION,
    LIST_BACKGROUND_TASKS_DESCRIPTION,
]

TEAM_TOOLS = [
    CREATE_TEAM_AGENT_DESCRIPTION,
    LIST_TEAM_AGENTS_DESCRIPTION,
    ASSIGN_TEAM_TASK_DESCRIPTION,
    GET_TEAM_TASK_DESCRIPTION,
    LIST_TEAM_TASKS_DESCRIPTION,
    CANCEL_TEAM_TASK_DESCRIPTION,
    REVIEW_TEAM_TASK_DESCRIPTION,
    STOP_TEAM_AGENT_DESCRIPTION,
]

WORKTREE_TOOLS = [
    CREATE_WORKTREE_DESCRIPTION,
    LIST_WORKTREES_DESCRIPTION,
    GET_WORKTREE_DESCRIPTION,
    REMOVE_WORKTREE_DESCRIPTION,
]

MANAGEMENT_TOOLS = BACKGROUND_TOOLS + TEAM_TOOLS + WORKTREE_TOOLS
SUB_AGENT_TOOLS = BASE_TOOLS
MAIN_AGENT_TOOLS = BASE_TOOLS + MANAGEMENT_TOOLS

# Backward-compatible alias for callers that import the old name.
tools = MAIN_AGENT_TOOLS

TOKEN_THRESHOLD = 80000
def estimate_tokens(messages: list) -> int:
    return len(json.dumps(messages, default=str)) // 4


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
                ]
            }


background_manager = BackgroundAgentManager()


class WorktreeManager:
    SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
    SAFE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./-]{0,127}$")

    def __init__(self, repo_root):
        self.repo_root = Path(repo_root).resolve()
        self.worktrees_root = self.repo_root / ".agent_worktrees"

    def _run_git(self, args, timeout=120):
        result = subprocess.run(
            ["git", *args],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            raise RuntimeError(output or f"git {' '.join(args)} failed")
        return output

    def _safe_name(self, name):
        if not self.SAFE_NAME_RE.match(name or ""):
            raise ValueError("name must use letters, numbers, dot, dash, or underscore, and start with a letter/number")
        return name

    def _safe_ref(self, ref, field_name):
        if not self.SAFE_REF_RE.match(ref or ""):
            raise ValueError(f"{field_name} has unsafe characters")
        if ".." in ref or ref.startswith("/") or ref.endswith("/"):
            raise ValueError(f"{field_name} is not a safe git ref")
        return ref

    def _managed_path(self, worktree_id):
        name = self._safe_name(worktree_id)
        path = (self.worktrees_root / name).resolve()
        try:
            path.relative_to(self.worktrees_root.resolve())
        except ValueError:
            raise ValueError(f"worktree escapes managed root: {worktree_id}")
        return path

    def _parse_porcelain(self, output):
        worktrees = []
        current = None
        for line in output.splitlines():
            if not line:
                if current:
                    worktrees.append(current)
                    current = None
                continue
            key, _, value = line.partition(" ")
            if key == "worktree":
                if current:
                    worktrees.append(current)
                path = Path(value).resolve()
                managed = self._is_managed_path(path)
                current = {
                    "path": str(path),
                    "worktree_id": path.name if managed else None,
                    "managed": managed,
                    "head": "",
                    "branch": "",
                    "detached": False,
                    "bare": False,
                }
            elif current is not None and key == "HEAD":
                current["head"] = value
            elif current is not None and key == "branch":
                current["branch"] = value
            elif current is not None and key == "detached":
                current["detached"] = True
            elif current is not None and key == "bare":
                current["bare"] = True
        if current:
            worktrees.append(current)
        return worktrees

    def _is_managed_path(self, path):
        try:
            path.relative_to(self.worktrees_root.resolve())
            return True
        except ValueError:
            return False

    def create(self, name, branch=None, base_ref=None, create_branch=True):
        try:
            name = self._safe_name(name)
            worktree_id = name
            path = self._managed_path(worktree_id)
            if path.exists():
                return {"ok": False, "error": f"Worktree path already exists: {path}"}

            base_ref = self._safe_ref(base_ref or "HEAD", "base_ref")
            self.worktrees_root.mkdir(parents=True, exist_ok=True)

            if create_branch:
                checkout_ref = branch or f"agent/{name}-{uuid.uuid4().hex[:8]}"
                checkout_ref = self._safe_ref(checkout_ref, "branch")
                args = ["worktree", "add", "-b", checkout_ref, str(path), base_ref]
            else:
                checkout_ref = self._safe_ref(branch or base_ref, "checkout_ref")
                args = ["worktree", "add", str(path), checkout_ref]
            output = self._run_git(args)
            return {
                "ok": True,
                "worktree_id": worktree_id,
                "path": str(path),
                "checkout_ref": checkout_ref,
                "base_ref": base_ref,
                "created_branch": bool(create_branch),
                "git_output": output,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def list(self):
        try:
            output = self._run_git(["worktree", "list", "--porcelain"])
            return {"ok": True, "worktrees": self._parse_porcelain(output)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get(self, worktree_id):
        try:
            target = self._managed_path(worktree_id)
            listing = self.list()
            if not listing.get("ok"):
                return listing
            for worktree in listing["worktrees"]:
                if Path(worktree["path"]).resolve() == target:
                    return {"ok": True, "worktree": worktree}
            return {"ok": False, "error": f"Unknown managed worktree: {worktree_id}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def remove(self, worktree_id, force=False):
        try:
            target = self._managed_path(worktree_id)
            details = self.get(worktree_id)
            if not details.get("ok"):
                return details
            args = ["worktree", "remove"]
            if force:
                args.append("--force")
            args.append(str(target))
            output = self._run_git(args)
            prune_output = self._run_git(["worktree", "prune"])
            return {
                "ok": True,
                "worktree_id": worktree_id,
                "path": str(target),
                "git_output": output,
                "prune_output": prune_output,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}


worktree_manager = WorktreeManager(WORKDIR)


class AgentTeamManager:
    def __init__(self):
        self._agents = {}
        self._tasks = {}
        self._lock = threading.Lock()

    def create_agent(self, name, role, system_prompt=None, worktree_id=None):
        if worktree_id:
            worktree = worktree_manager.get(worktree_id)
            if not worktree.get("ok"):
                return worktree

        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        record = {
            "agent_id": agent_id,
            "name": name,
            "role": role,
            "system_prompt": system_prompt or "",
            "worktree_id": worktree_id or "",
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
            worktree = worktree_manager.get(worktree_id)
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


team_manager = AgentTeamManager()


def assistant_message_to_dict(message):
    data = {"role": "assistant", "content": message.content or ""}
    if message.tool_calls:
        data["tool_calls"] = [
            {
                "id": tool_call.id,
                "type": tool_call.type,
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                },
            }
            for tool_call in message.tool_calls
        ]
    return data


def serialize_tool_output(output):
    if isinstance(output, (dict, list)):
        return json.dumps(output, ensure_ascii=False, default=str)
    return str(output) if output is not None else "success"


def extract_latest_assistant_text(messages):
    for message in reversed(messages):
        if message.get("role") == "assistant" and message.get("content"):
            return message["content"]
    return ""


def get_tools_for_scope(tool_scope):
    if tool_scope == "main":
        return MAIN_AGENT_TOOLS
    if tool_scope == "subagent":
        return SUB_AGENT_TOOLS
    raise ValueError(f"Unknown tool scope: {tool_scope}")


def agent_loop(messages, echo=True, tool_scope="main", max_steps=20):
    steps = 0
    active_tools = get_tools_for_scope(tool_scope)
    previous_scope = getattr(EXECUTION_CONTEXT, "tool_scope", None)
    EXECUTION_CONTEXT.tool_scope = tool_scope
    try:
        while steps < max_steps:
            steps += 1

            # 如果对话历史过长，主动调用 contextCompression
            if estimate_tokens(messages) > TOKEN_THRESHOLD:
                if echo:
                    print("--- 检测到对话过长，正在自动压缩上下文... ---")
                args = {
                    "messages": messages
                }
                messages[:] = TOOLS_HANDLE["contextCompression"](args)

            # send query
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=active_tools,
                max_tokens=8000
            )
            for choice in response.choices:

                # print content in console
                if echo and choice.message.content:
                    print(choice.message.content)
                messages.append(assistant_message_to_dict(choice.message))

                # deal with the tool call
                if choice.finish_reason != "tool_calls":
                    continue
                for tool_call in choice.message.tool_calls or []:
                    try:
                        args = json.loads(tool_call.function.arguments or "{}")
                    except json.JSONDecodeError as e:
                        output = f"Error: invalid tool arguments JSON: {e}"
                        messages.append({
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": tool_call.function.name,
                            "content": output
                        })
                        continue
                    
                    # print the tool call information
                    if echo:
                        print(f"\tNow agent will call the {tool_call.function.name} " +
                              f"with arguments: {args}")
                    output = None
                    if tool_call.function.name not in TOOLS_HANDLE:
                        output = f"Error: unknown tool '{tool_call.function.name}'"
                        if echo:
                            print(output)
                    if tool_call.function.name != "contextCompression":
                        if output is None:
                            output = TOOLS_HANDLE[tool_call.function.name](args)
                            if echo:
                                print(serialize_tool_output(output))
                    else:
                        args["messages"] = messages
                        messages[:] = TOOLS_HANDLE["contextCompression"](args)
                        output = "Compression Done."
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": tool_call.function.name,
                        "content": serialize_tool_output(output)
                    })
            if response.choices[0].finish_reason != "tool_calls":
                return extract_latest_assistant_text(messages)
    finally:
        if previous_scope is None:
            try:
                del EXECUTION_CONTEXT.tool_scope
            except AttributeError:
                pass
        else:
            EXECUTION_CONTEXT.tool_scope = previous_scope
    return "Error: agent loop reached max_steps before completion."


def run_background_task(task):
    messages = [
        {
            "role": "system",
            "content": (
                f"You are a background USTB sub-agent working at {WORKDIR}. "
                "Complete the assigned task independently with the available tools. "
                "You cannot create sub-agents or manage worktrees. "
                "Return a concise final result for the main agent."
            )
        },
        {"role": "user", "content": task}
    ]
    result = agent_loop(
        messages,
        echo=False,
        tool_scope="subagent",
        max_steps=20,
    )
    return result or extract_latest_assistant_text(messages) or "(no result)"


def run_team_agent_task(agent, task, worktree_id=None):
    active_workdir = WORKDIR
    selected_worktree = worktree_id or agent.get("worktree_id")
    if selected_worktree:
        worktree = worktree_manager.get(selected_worktree)
        if not worktree.get("ok"):
            return serialize_tool_output(worktree)
        active_workdir = Path(worktree["worktree"]["path"])

    system_prompt = (
        f"You are {agent['name']}, a USTB team sub-agent working at {active_workdir}. "
        f"Your role is: {agent['role']}. "
        "Complete only the assigned task, use tools when useful, and return a concise result for review. "
        "You cannot create sub-agents or manage worktrees."
    )
    if agent.get("system_prompt"):
        system_prompt = f"{system_prompt}\nAdditional instruction: {agent['system_prompt']}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task}
    ]
    previous_workdir = getattr(EXECUTION_CONTEXT, "workdir", None)
    EXECUTION_CONTEXT.workdir = active_workdir
    try:
        result = agent_loop(
            messages,
            echo=False,
            tool_scope="subagent",
            max_steps=20,
        )
    finally:
        if previous_workdir is None:
            try:
                del EXECUTION_CONTEXT.workdir
            except AttributeError:
                pass
        else:
            EXECUTION_CONTEXT.workdir = previous_workdir
    return result or extract_latest_assistant_text(messages) or "(no result)"


def main_scope_only(handler):
    def wrapped(kw):
        if current_tool_scope() != "main":
            return {
                "ok": False,
                "error": "This management tool is only available to the main agent loop.",
            }
        return handler(kw)
    return wrapped


TOOLS_HANDLE = {
    "bash": lambda kw: Tools.run_bash(kw['command'], current_workdir()),
    "read_file": lambda kw: Tools.run_read(kw['path'], kw.get('limit'), current_workdir()),
    # "write_file": lambda kw: Tools.run_write(kw['path'], kw.get('limit'), WORKDIR),
    "contextCompression": lambda kw: Tools.contextCompression(kw['messages'], kw.get('threshold'), kw.get('summary_focus')),
    "get_class_sche": lambda kw: Tools.get_class_sche(kw.get("update_force", False)),
    "start_background_task": main_scope_only(lambda kw: background_manager.start(kw["task"], run_background_task)),
    "get_background_task": main_scope_only(lambda kw: background_manager.get(kw["task_id"])),
    "list_background_tasks": main_scope_only(lambda kw: background_manager.list()),
    "create_team_agent": main_scope_only(lambda kw: team_manager.create_agent(
        kw["name"],
        kw["role"],
        kw.get("system_prompt"),
        kw.get("worktree_id"),
    )),
    "list_team_agents": main_scope_only(lambda kw: team_manager.list_agents()),
    "assign_team_task": main_scope_only(lambda kw: team_manager.assign_task(
        kw["agent_id"],
        kw["task"],
        run_team_agent_task,
        kw.get("worktree_id"),
    )),
    "get_team_task": main_scope_only(lambda kw: team_manager.get_task(kw["task_id"])),
    "list_team_tasks": main_scope_only(lambda kw: team_manager.list_tasks()),
    "cancel_team_task": main_scope_only(lambda kw: team_manager.cancel_task(kw["task_id"])),
    "review_team_task": main_scope_only(lambda kw: team_manager.review_task(
        kw["task_id"],
        kw["decision"],
        kw.get("feedback"),
    )),
    "stop_team_agent": main_scope_only(lambda kw: team_manager.stop_agent(kw["agent_id"])),
    "create_worktree": main_scope_only(lambda kw: worktree_manager.create(
        kw["name"],
        kw.get("branch"),
        kw.get("base_ref"),
        kw.get("create_branch", True),
    )),
    "list_worktrees": main_scope_only(lambda kw: worktree_manager.list()),
    "get_worktree": main_scope_only(lambda kw: worktree_manager.get(kw["worktree_id"])),
    "remove_worktree": main_scope_only(lambda kw: worktree_manager.remove(
        kw["worktree_id"],
        kw.get("force", False),
    )),
}


if __name__ == '__main__':
    messages = [{'role': 'system', 'content': f'You are a USTB agent work for student at {WORKDIR}, '
                 + 'work with tools and skills.'}]
    while True:
        try:
            query = input("\033[36mmy_agent >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        messages.append({"role": "user", "content": query})
        agent_loop(messages)
