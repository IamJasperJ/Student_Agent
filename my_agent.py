from openai import OpenAI
import os
import json
from pathlib import Path
from dotenv import load_dotenv
import sys

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

tools = [
    Tools.RUNBASH_DESCRIPTION,
    Tools.RUNREAD_DESCRIPTION,
    Tools.CONTEXTCOMPRESSION_DESCRIPTION,
    Tools.GETSCHE_DESCRIPTION,
]

TOOLS_HANDLE = {
    "bash": lambda kw: Tools.run_bash(kw['command'], WORKDIR),
    "read_file": lambda kw: Tools.run_read(kw['path'], kw.get('limit'), WORKDIR),
    # "write_file": lambda kw: Tools.run_write(kw['path'], kw.get('limit'), WORKDIR),
    "contextCompression": lambda kw: Tools.contextCompression(kw['messages'], kw.get('threshold'), kw.get('summary_focus')),
    "get_class_sche": lambda kw: Tools.get_class_sche(kw.get("update_force", False))
}

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


def agent_loop(messages):
    while True:

        # 如果对话历史过长，主动调用 contextCompression
        if estimate_tokens(messages) > TOKEN_THRESHOLD:
            print("--- 检测到对话过长，正在自动压缩上下文... ---")
            args = {
                "messages": messages
            }
            messages[:] = TOOLS_HANDLE["contextCompression"](args)

        # send query
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            max_tokens=8000
        )
        for choice in response.choices:

            # print content in console
            if choice.message.content:
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
                print(f"\tNow agent will call the {tool_call.function.name} " +
                      f"with arguments: {args}")
                output = None
                if tool_call.function.name not in TOOLS_HANDLE:
                    output = f"Error: unknown tool '{tool_call.function.name}'"
                    print(output)
                if tool_call.function.name != "contextCompression":
                    if output is None:
                        output = TOOLS_HANDLE[tool_call.function.name](args)
                        print(str(output) if output is not None else "success")
                else:
                    args["messages"] = messages
                    messages[:] = TOOLS_HANDLE["contextCompression"](args)
                    output = "Compression Done."
                messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": tool_call.function.name,
                    "content": str(output) if output is not None else "success"
                })
        if response.choices[0].finish_reason != "tool_calls":
            break


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
