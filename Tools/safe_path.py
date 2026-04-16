from pathlib import Path
def safe_path(p: str, WORKDIR) -> Path:
    root = Path(WORKDIR).resolve()
    path = (root / p).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise ValueError(f"Path escapes workspace: {p}")
    return path
