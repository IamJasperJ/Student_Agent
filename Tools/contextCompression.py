import os
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv(override=True)
API_KEY = os.getenv('API_KEY')
MODEL = os.getenv('MODEL_ID')
API_URL = os.getenv('MODEL_BASE_URL')

def _message_to_text(message):
    if isinstance(message, dict):
        content = message.get("content") or ""
        tool_calls = message.get("tool_calls")
        if tool_calls:
            content = f"{content}\nTool calls: {tool_calls}".strip()
        return f"{message.get('role', 'unknown')}: {content}"
    return str(message)


def contextCompression(messages, threshold: int = None, summary_focus=None):
    """
    当消息列表超过 threshold 时，对旧消息进行压缩。
    """
    if not threshold:
        threshold = 10
    if len(messages) <= threshold:
        return messages
    
    # 始终保留 System Prompt
    system_prompt = messages[0] if messages[0]['role'] == 'system' else None
    
    # 提取需要压缩的消息（跳过 system prompt，保留最近 5 条消息作为 buffer）
    keep_recent = 5
    to_compress = messages[1:-keep_recent]
    recent_messages = messages[-keep_recent:]

    if not to_compress:
        return messages
    
    client = OpenAI(
        api_key=API_KEY, 
        base_url=API_URL 
)   

    # 使用 LLM 生成摘要 (这里可以调用一个更便宜的模型压缩，省钱且快)
    content_to_summarize = "\n".join(_message_to_text(m) for m in to_compress)

    focus = "Focus on key facts and progress to maintain context for future interactions."
    if summary_focus:
        focus = summary_focus

    summary_response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "Summarize the following conversation history and completed task details concisely. "
                + focus},
            {"role": "user", "content": content_to_summarize}
        ]
    )
    summary_content = summary_response.choices[0].message.content
    new_messages = []
    if system_prompt:
        new_messages.append(system_prompt)
    
    new_messages.append(
        {"role": "user", 
        "content": f"Summary of previous interactions:{summary_content}"}
    )
    new_messages.extend(recent_messages)
    return new_messages

CONTEXTCOMPRESSION_DESCRIPTION = {
    "type": "function",
    "function": {
        "name": "contextCompression",
        "description": "Manually compress conversation context. "
                        "Use this when the conversation is becoming too "
                        "long or before starting a complex new task.",
        "parameters": {
            "type": "object",
            "properties": {
                "summary_focus": {
                    "type": "string",
                    "description": "Optional: Specify specific topics or critical data that must be preserved in the summary (e.g., 'keep the file paths' or 'summarize only the student's personal info')."
                },
                "threshold": {
                    "type": "integer",
                    "description": "Optional: Compress only when the message count exceeds this threshold."
                }
            },
            "required": []
        }
    }
}
