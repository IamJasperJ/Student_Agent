from openai import OpenAI
import os
import json
from pathlib import Path
from dotenv import load_dotenv
import sys
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

tools = BASE_TOOLS + BACKGROUND_TOOLS + TEAM_TOOLS

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


class AgentTeamManager:
    def __init__(self):
        self._agents = {}
        self._tasks = {}
        self._lock = threading.Lock()

    def create_agent(self, name, role, system_prompt=None):
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        record = {
            "agent_id": agent_id,
            "name": name,
            "role": role,
            "system_prompt": system_prompt or "",
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
                        "status": agent["status"],
                        "task_count": len(agent["tasks"]),
                        "created_at": agent["created_at"],
                        "updated_at": agent["updated_at"],
                    }
                    for agent in self._agents.values()
                ],
            }

    def assign_task(self, agent_id, task, runner):
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
            result = runner(agent_record, task_record["task"])
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


def agent_loop(messages, echo=True, allow_background=True, allow_team=True, max_steps=20):
    steps = 0
    active_tools = list(BASE_TOOLS)
    if allow_background:
        active_tools.extend(BACKGROUND_TOOLS)
    if allow_team:
        active_tools.extend(TEAM_TOOLS)
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
    return "Error: agent loop reached max_steps before completion."


def run_background_task(task):
    messages = [
        {
            "role": "system",
            "content": (
                f"You are a background USTB sub-agent working at {WORKDIR}. "
                "Complete the assigned task independently with the available tools. "
                "Return a concise final result for the main agent."
            )
        },
        {"role": "user", "content": task}
    ]
    result = agent_loop(
        messages,
        echo=False,
        allow_background=False,
        allow_team=False,
        max_steps=20,
    )
    return result or extract_latest_assistant_text(messages) or "(no result)"


def run_team_agent_task(agent, task):
    system_prompt = (
        f"You are {agent['name']}, a USTB team sub-agent working at {WORKDIR}. "
        f"Your role is: {agent['role']}. "
        "Complete only the assigned task, use tools when useful, and return a concise result for review."
    )
    if agent.get("system_prompt"):
        system_prompt = f"{system_prompt}\nAdditional instruction: {agent['system_prompt']}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task}
    ]
    result = agent_loop(
        messages,
        echo=False,
        allow_background=False,
        allow_team=False,
        max_steps=20,
    )
    return result or extract_latest_assistant_text(messages) or "(no result)"


TOOLS_HANDLE = {
    "bash": lambda kw: Tools.run_bash(kw['command'], WORKDIR),
    "read_file": lambda kw: Tools.run_read(kw['path'], kw.get('limit'), WORKDIR),
    # "write_file": lambda kw: Tools.run_write(kw['path'], kw.get('limit'), WORKDIR),
    "contextCompression": lambda kw: Tools.contextCompression(kw['messages'], kw.get('threshold'), kw.get('summary_focus')),
    "get_class_sche": lambda kw: Tools.get_class_sche(kw.get("update_force", False)),
    "start_background_task": lambda kw: background_manager.start(kw["task"], run_background_task),
    "get_background_task": lambda kw: background_manager.get(kw["task_id"]),
    "list_background_tasks": lambda kw: background_manager.list(),
    "create_team_agent": lambda kw: team_manager.create_agent(
        kw["name"],
        kw["role"],
        kw.get("system_prompt"),
    ),
    "list_team_agents": lambda kw: team_manager.list_agents(),
    "assign_team_task": lambda kw: team_manager.assign_task(
        kw["agent_id"],
        kw["task"],
        run_team_agent_task,
    ),
    "get_team_task": lambda kw: team_manager.get_task(kw["task_id"]),
    "list_team_tasks": lambda kw: team_manager.list_tasks(),
    "cancel_team_task": lambda kw: team_manager.cancel_task(kw["task_id"]),
    "review_team_task": lambda kw: team_manager.review_task(
        kw["task_id"],
        kw["decision"],
        kw.get("feedback"),
    ),
    "stop_team_agent": lambda kw: team_manager.stop_agent(kw["agent_id"]),
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
