from Tools.safe_path import safe_path
def run_read(path: str, limit: int = None, WORKDIR = None) -> str:
    try:
        text = safe_path(path, WORKDIR).read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
        return "\n".join(lines)[:50000]
    except Exception as e:
        return f"Error: {e}"
    
RUNREAD_DESCRIPTION = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read file contents.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"}, 
                "limit": {"type": "integer"}
            },
            "required": ["path"]
        }
    }
}
