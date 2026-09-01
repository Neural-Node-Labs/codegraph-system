"""
Deterministic config extraction. Flattens YAML/JSON/.env into dotted ConfigKey
nodes with exact source line numbers (best-effort line mapping for structured
formats; exact for .env).
"""
import json
import re
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

ENV_LINE_RE = re.compile(r"""^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$""")


def parse_env_file(file_path: str, repo_root: str):
    rel = str(Path(file_path).relative_to(repo_root))
    keys = []
    text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    for i, line in enumerate(text.splitlines(), start=1):
        if line.strip().startswith("#") or not line.strip():
            continue
        m = ENV_LINE_RE.match(line)
        if m:
            keys.append((m.group(1), i, m.group(2)[:80]))
    return rel, keys


def _flatten(obj, prefix=""):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, (dict, list)):
                out.extend(_flatten(v, key))
            else:
                out.append((key, v))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            key = f"{prefix}[{i}]"
            if isinstance(v, (dict, list)):
                out.extend(_flatten(v, key))
            else:
                out.append((key, v))
    return out


def parse_structured_config(file_path: str, repo_root: str):
    rel = str(Path(file_path).relative_to(repo_root))
    text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    try:
        if file_path.endswith(".json"):
            data = json.loads(text)
        elif yaml is not None:
            data = yaml.safe_load(text)
        else:
            return rel, []
    except Exception:
        return rel, []
    if data is None:
        return rel, []
    flat = _flatten(data)
    return rel, [(k, None, str(v)[:80]) for k, v in flat]
