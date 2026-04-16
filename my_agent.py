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

BACKGROUND_TOOLS = [
    START_BACKGROUND_TASK_DESCRIPTION,
    GET_BACKGROUND_TASK_DESCRIPTION,
    LIST_BACKGROUND_TASKS_DESCRIPTION,
]

tools = BASE_TOOLS + BACKGROUND_TOOLS

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


def agent_loop(messages, echo=True, allow_background=True, max_steps=20):
    steps = 0
    active_tools = tools if allow_background else BASE_TOOLS
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
