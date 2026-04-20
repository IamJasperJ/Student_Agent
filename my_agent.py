from openai import OpenAI
import os
import json
from pathlib import Path
from dotenv import load_dotenv
import sys
import threading
import time
import traceback

root_path = str(Path(__file__).resolve().parent)
if root_path not in sys.path:
    sys.path.append(root_path)

import Tools
# 同组子 agent 消息总线 schema + Notion MCP 代理（仅主循环注册 notion 工具，见 MANAGEMENT_TOOLS）
from Tools.team_messages import (
    TeamMessageBus,
    POST_TEAM_MESSAGE_DESCRIPTION,
    FETCH_TEAM_MESSAGES_DESCRIPTION,
    PEEK_TEAM_MESSAGES_DESCRIPTION,
)
from Tools.notion_mcp import (
    notion_mcp_list_tools,
    notion_mcp_call_tool,
    NOTION_MCP_LIST_TOOLS_DESCRIPTION,
    NOTION_MCP_CALL_TOOL_DESCRIPTION,
)
from managers.background_manager import BackgroundAgentManager
from managers.team_manager import AgentTeamManager
from managers.worktree_manager import WorktreeManager
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
# 每线程执行上下文：workdir / tool_scope / team_* 供工具闭包读取（无则视为非 team 子 agent）
EXECUTION_CONTEXT = threading.local()


def current_workdir():
    return getattr(EXECUTION_CONTEXT, "workdir", WORKDIR)


def current_tool_scope():
    return getattr(EXECUTION_CONTEXT, "tool_scope", "main")


worktree_manager = WorktreeManager(WORKDIR)
team_manager = AgentTeamManager(worktree_manager)
background_manager = BackgroundAgentManager()
# 进程内邮箱；与持久化无关，重启即空
team_message_bus = TeamMessageBus()

BASE_TOOLS = [
    Tools.RUNBASH_DESCRIPTION,
    Tools.RUNREAD_DESCRIPTION,
    Tools.RUNEDIT_DESCRIPTION,
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
                },
                "group_id": {
                    "type": "string",
                    "description": "Optional team channel id for peer messaging. Same group_id can exchange post_team_message/fetch_team_messages. Defaults to 'default'."
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

# Notion：仅挂到主循环（MANAGEMENT_TOOLS）；子 agent 不暴露，避免并发共用一个 MCP 子进程
NOTION_MCP_TOOLS = [
    NOTION_MCP_LIST_TOOLS_DESCRIPTION,
    NOTION_MCP_CALL_TOOL_DESCRIPTION,
]

# Team 子 agent：BASE + 发帖/拉取；主循环另含 peek（见 MANAGEMENT_TOOLS）
TEAM_MESSAGE_SUB_TOOLS = [
    POST_TEAM_MESSAGE_DESCRIPTION,
    FETCH_TEAM_MESSAGES_DESCRIPTION,
]

MANAGEMENT_TOOLS = (
    BACKGROUND_TOOLS
    + TEAM_TOOLS
    + WORKTREE_TOOLS
    + [PEEK_TEAM_MESSAGES_DESCRIPTION]
    + NOTION_MCP_TOOLS
)
SUB_AGENT_TOOLS = BASE_TOOLS + TEAM_MESSAGE_SUB_TOOLS
MAIN_AGENT_TOOLS = BASE_TOOLS + MANAGEMENT_TOOLS

# Backward-compatible alias for callers that import the old name.
tools = MAIN_AGENT_TOOLS

TOKEN_THRESHOLD = 80000
def estimate_tokens(messages: list) -> int:
    return len(json.dumps(messages, default=str)) // 4


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
    # 后台任务：仅基础工具，不包含 post_team_message（无 team 上下文）
    if tool_scope == "background":
        return BASE_TOOLS
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
    # background：与 team 子 agent 区分，不挂载团队消息工具
    result = agent_loop(
        messages,
        echo=False,
        tool_scope="background",
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

    # 与 TeamMessageBus 的频道一致；EXECUTION_CONTEXT.team_* 供 post/fetch 解析发送者与组
    group_id = agent.get("group_id") or "default"
    system_prompt = (
        f"You are {agent['name']}, a USTB team sub-agent working at {active_workdir}. "
        f"Your role is: {agent['role']}. "
        f"Your team agent_id is {agent['agent_id']}; message group_id is {group_id}. "
        "Use post_team_message and fetch_team_messages to coordinate with peers in the same group. "
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
    # 嵌套 team 调用极少见：仍保存/恢复，避免覆盖外层上下文
    previous_team_agent_id = getattr(EXECUTION_CONTEXT, "team_agent_id", None)
    previous_team_group_id = getattr(EXECUTION_CONTEXT, "team_group_id", None)
    previous_team_agent_name = getattr(EXECUTION_CONTEXT, "team_agent_name", None)
    EXECUTION_CONTEXT.workdir = active_workdir
    EXECUTION_CONTEXT.team_agent_id = agent["agent_id"]
    EXECUTION_CONTEXT.team_group_id = group_id
    EXECUTION_CONTEXT.team_agent_name = agent.get("name") or ""
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
        if previous_team_agent_id is None:
            try:
                del EXECUTION_CONTEXT.team_agent_id
            except AttributeError:
                pass
        else:
            EXECUTION_CONTEXT.team_agent_id = previous_team_agent_id
        if previous_team_group_id is None:
            try:
                del EXECUTION_CONTEXT.team_group_id
            except AttributeError:
                pass
        else:
            EXECUTION_CONTEXT.team_group_id = previous_team_group_id
        if previous_team_agent_name is None:
            try:
                del EXECUTION_CONTEXT.team_agent_name
            except AttributeError:
                pass
        else:
            EXECUTION_CONTEXT.team_agent_name = previous_team_agent_name
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


def _post_team_message(kw):
    # 仅在 run_team_agent_task 设置了 team_agent_id 时成功；否则提示非 team 子 agent
    agent_id = getattr(EXECUTION_CONTEXT, "team_agent_id", None)
    if not agent_id:
        return {
            "ok": False,
            "error": "post_team_message is only available inside a team sub-agent task.",
        }
    return team_message_bus.post(
        getattr(EXECUTION_CONTEXT, "team_group_id", "default"),
        agent_id,
        getattr(EXECUTION_CONTEXT, "team_agent_name", "") or "",
        kw["content"],
        kw.get("to_agent_id"),
    )


def _fetch_team_messages(kw):
    # 与 post 相同：依赖 EXECUTION_CONTEXT（team 任务线程）
    agent_id = getattr(EXECUTION_CONTEXT, "team_agent_id", None)
    if not agent_id:
        return {
            "ok": False,
            "error": "fetch_team_messages is only available inside a team sub-agent task.",
        }
    return team_message_bus.fetch_for_agent(
        getattr(EXECUTION_CONTEXT, "team_group_id", "default"),
        agent_id,
        int(kw.get("limit") or 30),
        kw.get("since_message_id"),
    )


TOOLS_HANDLE = {
    "bash": lambda kw: Tools.run_bash(kw['command'], current_workdir()),
    "read_file": lambda kw: Tools.run_read(kw['path'], kw.get('limit'), current_workdir()),
    "edit_file_block": lambda kw: Tools.run_edit_block(
        kw['path'],
        kw['old_str'],
        kw['new_str'],
        current_workdir(),
    ),
    # "write_file": lambda kw: Tools.run_write(kw['path'], kw.get('limit'), WORKDIR),
    "contextCompression": lambda kw: Tools.contextCompression(kw['messages'], kw.get('threshold'), kw.get('summary_focus')),
    "get_class_sche": lambda kw: Tools.get_class_sche(kw.get("update_force", False)),
    # --- 同组消息（子 agent / 主 agent 分工见 get_tools_for_scope）---
    "post_team_message": _post_team_message,
    "fetch_team_messages": _fetch_team_messages,
    "peek_team_messages": main_scope_only(
        lambda kw: team_message_bus.peek_group(
            kw.get("group_id") or "default",
            int(kw.get("limit") or 50),
        )
    ),
    # Notion MCP：仅主循环；内部单例见 Tools/notion_mcp.py
    "notion_mcp_list_tools": main_scope_only(lambda kw: notion_mcp_list_tools()),
    "notion_mcp_call_tool": main_scope_only(
        lambda kw: notion_mcp_call_tool(kw["tool_name"], kw.get("arguments") or {})
    ),
    "start_background_task": main_scope_only(lambda kw: background_manager.start(kw["task"], run_background_task)),
    "get_background_task": main_scope_only(lambda kw: background_manager.get(kw["task_id"])),
    "list_background_tasks": main_scope_only(lambda kw: background_manager.list()),
    "create_team_agent": main_scope_only(lambda kw: team_manager.create_agent(
        kw["name"],
        kw["role"],
        kw.get("system_prompt"),
        kw.get("worktree_id"),
        kw.get("group_id"),
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
