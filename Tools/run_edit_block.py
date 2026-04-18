from Tools.safe_path import safe_path

def run_edit_block(path: str, old_str: str, new_str: str, WORKDIR = None) -> str:
    """
    通过 搜索-替换 模式修改文件内容。
    """
    try:
        if not isinstance(path, str) or not path.strip():
            return "Error: 'path' must be a non-empty string."
        if not isinstance(old_str, str) or not old_str:
            return "Error: 'old_str' must be a non-empty string."
        if not isinstance(new_str, str):
            return "Error: 'new_str' must be a string."

        file_ptr = safe_path(path, WORKDIR)
        if not file_ptr.exists():
            return f"Error: File {path} does not exist."
            
        content = file_ptr.read_text(encoding="utf-8")
        
        # 统计匹配次数，确保唯一性，防止 AI 找错位置
        count = content.count(old_str)
        if count == 0:
            return "Error: Could not find the 'old_str' in the file. Please provide the exact code block (including indentation)."
        if count > 1:
            return f"Error: Found {count} occurrences of the code block. Please provide more context to make it unique."
        
        # 执行替换
        new_content = content.replace(old_str, new_str)
        file_ptr.write_text(new_content, encoding="utf-8")
        
        return f"Successfully updated {path}."
    except Exception as e:
        return f"Error: {e}"
    
RUNEDIT_DESCRIPTION = {
    "type": "function",
    "function": {
        "name": "edit_file_block",
        "description": "Update a specific block of code in a file using search and replace. You must provide the exact original text (old_str) to be replaced.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The path to the file to edit."
                },
                "old_str": {
                    "type": "string",
                    "description": "The exact lines of code you want to change (must match the file exactly including indentation)."
                },
                "new_str": {
                    "type": "string",
                    "description": "The new code that should replace the 'old_str'."
                }
            },
            "required": ["path", "old_str", "new_str"]
        }
    }
}