import subprocess
import shlex

READ_ONLY_COMMANDS = {
    "pwd",
    "ls",
    "cat",
    "head",
    "tail",
    "sed",
    "wc",
    "rg",
    "grep",
    "find",
}

GIT_READ_ONLY_SUBCOMMANDS = {
    "status",
    "diff",
    "log",
    "show",
    "branch",
    "rev-parse",
}

PYTHON_ALLOWED_MODULES = {
    "py_compile",
    "pytest",
}

SHELL_OPERATORS = {
    "|",
    "||",
    "&",
    "&&",
    ";",
    ">",
    ">>",
    "<",
    "<<",
    "$(",
    "`",
}

BLOCKED_ARGUMENTS = {
    "-delete",
    "-exec",
    "-execdir",
    "-ok",
    "-okdir",
    "-i",
    "--in-place",
    "--ext-diff",
}


def _has_blocked_argument(args):
    for arg in args[1:]:
        if arg in BLOCKED_ARGUMENTS or arg.startswith("--output"):
            return True, arg
    return False, ""


def _is_allowed_command(args):
    if not args:
        return False, "empty command"

    blocked, arg = _has_blocked_argument(args)
    if blocked:
        return False, f"argument '{arg}' is not allowed"

    executable = args[0]
    if executable in READ_ONLY_COMMANDS:
        return True, ""

    if executable == "git":
        if len(args) < 2 or args[1] not in GIT_READ_ONLY_SUBCOMMANDS:
            return False, "only read-only git subcommands are allowed"
        return True, ""

    if executable in {"python", "python3", ".agent_env/bin/python"}:
        if len(args) >= 3 and args[1] == "-m" and args[2] in PYTHON_ALLOWED_MODULES:
            return True, ""
        return False, "only python -m py_compile/pytest is allowed"

    return False, f"command '{executable}' is not allowed"


def run_bash(command:str, WORKDIR) -> str:
    if any(op in command for op in SHELL_OPERATORS):
        return "Error: shell operators are not allowed"

    try:
        args = shlex.split(command)
    except ValueError as e:
        return f"Error: invalid command syntax: {e}"

    allowed, reason = _is_allowed_command(args)
    if not allowed:
        return f"Error: {reason}"

    try:
        r = subprocess.run(args, shell=False, cwd=WORKDIR,
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
    
RUNBASH_DESCRIPTION = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": "Run a restricted read/check command in the workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string"}
            },
            "required": ["command"]
        }
    }
}
