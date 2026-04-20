"""
主 agent 侧 Notion MCP 桥接：通过 mcpsdk 连接子进程（默认 npx 官方包）或 SSE。

- 连接参数来自环境变量，见 .env.example；stdio 模式需 NOTION_TOKEN 注入子进程环境。
- 失败时断开并重置单例，便于下次调用重试（例如 npx 首次下载超时）。
"""

import os
import shlex
import threading
import traceback

from mcpsdk import MCPClient

_client: MCPClient | None = None
_client_lock = threading.Lock()


def _reset_client():
    global _client
    with _client_lock:
        if _client is not None:
            try:
                _client.disconnect()
            except Exception:
                pass
            _client = None


def _build_client() -> MCPClient:
    # stdio：由本进程拉起 MCP server；SSE：连接已托管的 HTTP MCP（鉴权方式依 Notion 文档）
    transport = (os.getenv("NOTION_MCP_TRANSPORT") or "stdio").strip().lower()
    if transport == "sse":
        url = (os.getenv("NOTION_MCP_SSE_URL") or "https://mcp.notion.com/mcp").strip()
        if not url:
            raise RuntimeError("NOTION_MCP_SSE_URL is empty.")
        return MCPClient.from_sse(url)
    cmd = (os.getenv("NOTION_MCP_COMMAND") or "npx").strip()
    if not cmd:
        raise RuntimeError("NOTION_MCP_COMMAND is empty.")
    # 与 shell 类似分词，支持带引号的参数
    args_line = os.getenv("NOTION_MCP_ARGS", "-y @notionhq/notion-mcp-server")
    args = shlex.split(args_line)
    return MCPClient.from_stdio(cmd, args)


def get_notion_mcp_client() -> MCPClient:
    """懒加载单例；子进程继承当前进程 environ，故 .env 加载后的 NOTION_TOKEN 会生效。"""
    global _client
    with _client_lock:
        if _client is None:
            _client = _build_client()
            _client.connect()
        return _client


def notion_mcp_list_tools() -> dict:
    try:
        # 本地 stdio 无 token 时提前失败，避免无意义拉起 npx
        if (os.getenv("NOTION_MCP_TRANSPORT") or "stdio").strip().lower() == "stdio":
            if not (os.getenv("NOTION_TOKEN") or "").strip():
                return {
                    "ok": False,
                    "error": "NOTION_TOKEN is not set; required for local Notion MCP (stdio).",
                }
        client = get_notion_mcp_client()
        tools = client.list_tools()
        return {"ok": True, "tools": tools}
    except Exception as e:
        _reset_client()
        return {
            "ok": False,
            "error": str(e),
            "trace": traceback.format_exc(limit=5),
        }


def notion_mcp_call_tool(tool_name: str, arguments: dict | None) -> dict:
    try:
        if (os.getenv("NOTION_MCP_TRANSPORT") or "stdio").strip().lower() == "stdio":
            if not (os.getenv("NOTION_TOKEN") or "").strip():
                return {
                    "ok": False,
                    "error": "NOTION_TOKEN is not set; required for local Notion MCP (stdio).",
                }
        client = get_notion_mcp_client()
        text = client.call_tool(tool_name, arguments or {})
        return {"ok": True, "tool": tool_name, "result": text}
    except Exception as e:
        _reset_client()
        return {
            "ok": False,
            "error": str(e),
            "trace": traceback.format_exc(limit=5),
        }


# 与 Tools/team_messages 相同：供主循环注册为 OpenAI tool schema
NOTION_MCP_LIST_TOOLS_DESCRIPTION = {
    "type": "function",
    "function": {
        "name": "notion_mcp_list_tools",
        "description": (
            "List tools exposed by the configured Notion MCP server (pages, databases, search, etc.). "
            "Requires NOTION_TOKEN when using the default stdio server."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

NOTION_MCP_CALL_TOOL_DESCRIPTION = {
    "type": "function",
    "function": {
        "name": "notion_mcp_call_tool",
        "description": (
            "Invoke a tool by name on the Notion MCP server. "
            "Use notion_mcp_list_tools first to see names and JSON parameter shapes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tool_name": {"type": "string", "description": "MCP tool name."},
                "arguments": {
                    "type": "object",
                    "description": "Arguments object as required by that tool (may be empty).",
                },
            },
            "required": ["tool_name"],
        },
    },
}
