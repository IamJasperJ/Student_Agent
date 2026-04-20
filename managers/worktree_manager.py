import re
import subprocess
import uuid
from pathlib import Path


class WorktreeManager:
    SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
    SAFE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./-]{0,127}$")

    def __init__(self, repo_root):
        self.repo_root = Path(repo_root).resolve()
        self.worktrees_root = self.repo_root / ".agent_worktrees"

    def _run_git(self, args, timeout=120):
        result = subprocess.run(
            ["git", *args],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            raise RuntimeError(output or f"git {' '.join(args)} failed")
        return output

    def _safe_name(self, name):
        if not self.SAFE_NAME_RE.match(name or ""):
            raise ValueError("name must use letters, numbers, dot, dash, or underscore, and start with a letter/number")
        return name

    def _safe_ref(self, ref, field_name):
        if not self.SAFE_REF_RE.match(ref or ""):
            raise ValueError(f"{field_name} has unsafe characters")
        if ".." in ref or ref.startswith("/") or ref.endswith("/"):
            raise ValueError(f"{field_name} is not a safe git ref")
        return ref

    def _managed_path(self, worktree_id):
        name = self._safe_name(worktree_id)
        path = (self.worktrees_root / name).resolve()
        try:
            path.relative_to(self.worktrees_root.resolve())
        except ValueError:
            raise ValueError(f"worktree escapes managed root: {worktree_id}")
        return path

    def _parse_porcelain(self, output):
        worktrees = []
        current = None
        for line in output.splitlines():
            if not line:
                if current:
                    worktrees.append(current)
                    current = None
                continue
            key, _, value = line.partition(" ")
            if key == "worktree":
                if current:
                    worktrees.append(current)
                path = Path(value).resolve()
                managed = self._is_managed_path(path)
                current = {
                    "path": str(path),
                    "worktree_id": path.name if managed else None,
                    "managed": managed,
                    "head": "",
                    "branch": "",
                    "detached": False,
                    "bare": False,
                }
            elif current is not None and key == "HEAD":
                current["head"] = value
            elif current is not None and key == "branch":
                current["branch"] = value
            elif current is not None and key == "detached":
                current["detached"] = True
            elif current is not None and key == "bare":
                current["bare"] = True
        if current:
            worktrees.append(current)
        return worktrees

    def _is_managed_path(self, path):
        try:
            path.relative_to(self.worktrees_root.resolve())
            return True
        except ValueError:
            return False

    def create(self, name, branch=None, base_ref=None, create_branch=True):
        try:
            name = self._safe_name(name)
            worktree_id = name
            path = self._managed_path(worktree_id)
            if path.exists():
                return {"ok": False, "error": f"Worktree path already exists: {path}"}

            base_ref = self._safe_ref(base_ref or "HEAD", "base_ref")
            self.worktrees_root.mkdir(parents=True, exist_ok=True)

            if create_branch:
                checkout_ref = branch or f"agent/{name}-{uuid.uuid4().hex[:8]}"
                checkout_ref = self._safe_ref(checkout_ref, "branch")
                args = ["worktree", "add", "-b", checkout_ref, str(path), base_ref]
            else:
                checkout_ref = self._safe_ref(branch or base_ref, "checkout_ref")
                args = ["worktree", "add", str(path), checkout_ref]
            output = self._run_git(args)
            return {
                "ok": True,
                "worktree_id": worktree_id,
                "path": str(path),
                "checkout_ref": checkout_ref,
                "base_ref": base_ref,
                "created_branch": bool(create_branch),
                "git_output": output,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def list(self):
        try:
            output = self._run_git(["worktree", "list", "--porcelain"])
            return {"ok": True, "worktrees": self._parse_porcelain(output)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get(self, worktree_id):
        try:
            target = self._managed_path(worktree_id)
            listing = self.list()
            if not listing.get("ok"):
                return listing
            for worktree in listing["worktrees"]:
                if Path(worktree["path"]).resolve() == target:
                    return {"ok": True, "worktree": worktree}
            return {"ok": False, "error": f"Unknown managed worktree: {worktree_id}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def remove(self, worktree_id, force=False):
        try:
            target = self._managed_path(worktree_id)
            details = self.get(worktree_id)
            if not details.get("ok"):
                return details
            args = ["worktree", "remove"]
            if force:
                args.append("--force")
            args.append(str(target))
            output = self._run_git(args)
            prune_output = self._run_git(["worktree", "prune"])
            return {
                "ok": True,
                "worktree_id": worktree_id,
                "path": str(target),
                "git_output": output,
                "prune_output": prune_output,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}
