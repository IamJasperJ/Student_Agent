"""
同组 team 子 agent 的进程内消息总线。

- 按 group_id 分频道；消息仅存内存，进程退出即清空。
- 广播：to_agent_id 为空；私聊：填写目标 agent_id。
- fetch 对子 agent 仅返回「全员广播 + 发给自己的 DM」；主 agent 的 peek 可看该组全部消息。
"""

import re
import threading
import time
import uuid

# group_id 与目录名等风格一致，避免路径注入或奇怪字符
GROUP_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
MAX_MESSAGES_PER_GROUP = 1000


def _safe_group_id(raw: str) -> str:
    s = (raw or "default").strip() or "default"
    if not GROUP_ID_RE.match(s):
        raise ValueError(
            "group_id must be 1–64 chars: letters, digits, dot, dash, underscore; "
            "must start with letter or digit."
        )
    return s


def normalize_group_id(raw: str | None) -> str:
    """Validate and return a safe group id (default 'default')."""
    return _safe_group_id(raw)


class TeamMessageBus:
    """按 group_id 隔离的线程安全广播 / 点对点消息。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._by_group: dict[str, list[dict]] = {}

    def post(
        self,
        group_id: str,
        from_agent_id: str,
        from_name: str,
        content: str,
        to_agent_id: str | None = None,
    ) -> dict:
        gid = _safe_group_id(group_id)
        msg = {
            "message_id": f"msg_{uuid.uuid4().hex[:12]}",
            "group_id": gid,
            "from_agent_id": from_agent_id,
            "from_name": from_name or "",
            "to_agent_id": (to_agent_id or "").strip(),
            "content": content,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        with self._lock:
            lst = self._by_group.setdefault(gid, [])
            lst.append(msg)
            # 防止单组无限增长占满内存
            overflow = len(lst) - MAX_MESSAGES_PER_GROUP
            if overflow > 0:
                del lst[:overflow]
        return {"ok": True, "message": msg}

    def _visible(self, msg: dict, viewer_agent_id: str) -> bool:
        # 无 to_agent_id 为群发；有 to_agent_id 时仅收件人可见（发件人不会在 fetch 里看到自己发出的 DM）
        to_id = msg.get("to_agent_id") or ""
        if not to_id:
            return True
        return to_id == viewer_agent_id

    def fetch_for_agent(
        self,
        group_id: str,
        viewer_agent_id: str,
        limit: int = 30,
        since_message_id: str | None = None,
    ) -> dict:
        gid = _safe_group_id(group_id)
        limit = max(1, min(int(limit or 30), 100))
        with self._lock:
            lst = list(self._by_group.get(gid, []))
        filtered = [m for m in lst if self._visible(m, viewer_agent_id)]
        # since_message_id：增量拉取，只取该 id 之后的新消息
        if since_message_id:
            idx = next(
                (i for i, m in enumerate(filtered) if m["message_id"] == since_message_id),
                None,
            )
            if idx is not None:
                filtered = filtered[idx + 1 :]
        out = filtered[-limit:] if len(filtered) > limit else filtered
        return {"ok": True, "group_id": gid, "messages": out, "count": len(out)}

    def peek_group(self, group_id: str, limit: int = 50) -> dict:
        """主循环专用：不按收件过滤，便于审计整组协作。"""
        gid = _safe_group_id(group_id)
        limit = max(1, min(int(limit or 50), 200))
        with self._lock:
            lst = list(self._by_group.get(gid, []))
        out = lst[-limit:] if len(lst) > limit else lst
        return {"ok": True, "group_id": gid, "messages": out, "count": len(out)}


# OpenAI tools schema：供 my_agent 注册到对应 tool_scope
POST_TEAM_MESSAGE_DESCRIPTION = {
    "type": "function",
    "function": {
        "name": "post_team_message",
        "description": (
            "Post a message to your team channel. Same-group sub-agents can read it. "
            "Omit to_agent_id to broadcast; set to_agent_id to send a direct message to one peer."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Message body (plain text).",
                },
                "to_agent_id": {
                    "type": "string",
                    "description": "Optional. Target sub-agent id for a DM; omit for broadcast.",
                },
            },
            "required": ["content"],
        },
    },
}

FETCH_TEAM_MESSAGES_DESCRIPTION = {
    "type": "function",
    "function": {
        "name": "fetch_team_messages",
        "description": (
            "Fetch recent team messages visible to you (broadcasts and DMs addressed to your agent_id). "
            "Optionally pass since_message_id to get only newer messages after that id."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max messages to return (1–100). Default 30.",
                },
                "since_message_id": {
                    "type": "string",
                    "description": "If set, return messages after this message_id only.",
                },
            },
            "required": [],
        },
    },
}

PEEK_TEAM_MESSAGES_DESCRIPTION = {
    "type": "function",
    "function": {
        "name": "peek_team_messages",
        "description": (
            "Main agent only: read recent messages for a team group (full channel including DMs). "
            "Useful to monitor coordination between sub-agents."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "group_id": {
                    "type": "string",
                    "description": "Team group id (same as used in create_team_agent). Default group is 'default'.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max messages (1–200). Default 50.",
                },
            },
            "required": [],
        },
    },
}
