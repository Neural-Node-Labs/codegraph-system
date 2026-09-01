"""
Deterministic JS/TS/JSX static analysis via regular expressions over source text.
No LLM. Regex is applied structurally (line-anchored, syntax-specific patterns),
not as free-text guessing -- every match maps to an exact line number.
"""
import re
from pathlib import Path

IMPORT_RE = re.compile(r"""^\s*import\s+(?:[\w*{}\s,]+\s+from\s+)?['"]([^'"]+)['"]""", re.M)
REQUIRE_RE = re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)""")
FUNC_DECL_RE = re.compile(r"""^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)""", re.M)
ARROW_FUNC_RE = re.compile(r"""^\s*(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>""", re.M)
FETCH_RE = re.compile(r"""fetch\(\s*[`'"]([^`'"]+)[`'"](?:\s*,\s*\{([^}]*)\})?""")
FETCH_METHOD_RE = re.compile(r"""method\s*:\s*[`'"](\w+)[`'"]""")
AXIOS_RE = re.compile(r"""axios\.(get|post|put|delete|patch)\(\s*[`'"]([^`'"]+)[`'"]""")
JSX_COMPONENT_RE = re.compile(r"""<([A-Z][A-Za-z0-9_]*)[\s/>]""")
CALL_RE = re.compile(r"""\b([A-Za-z_]\w*)\s*\(""")


class JsResult:
    def __init__(self, file_path):
        self.file_path = file_path
        self.imports = []     # (module_path, lineno)
        self.functions = []   # (name, lineno, signature)
        self.api_calls = []   # (method, path, lineno)
        self.renders = []     # (component_name, lineno)
        self.calls = []       # (name, lineno)  -- coarse, function-call level


def _lineno_at(text, pos):
    return text.count("\n", 0, pos) + 1


def parse_js_file(file_path: str, repo_root: str):
    text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    rel = str(Path(file_path).relative_to(repo_root))
    r = JsResult(rel)

    for m in IMPORT_RE.finditer(text):
        r.imports.append((m.group(1), _lineno_at(text, m.start())))
    for m in REQUIRE_RE.finditer(text):
        r.imports.append((m.group(1), _lineno_at(text, m.start())))

    for m in FUNC_DECL_RE.finditer(text):
        name, args = m.group(1), m.group(2)
        r.functions.append((name, _lineno_at(text, m.start()), f"{name}({args})"))
    for m in ARROW_FUNC_RE.finditer(text):
        name, args = m.group(1), m.group(2)
        r.functions.append((name, _lineno_at(text, m.start()), f"{name}({args})"))

    for m in FETCH_RE.finditer(text):
        method = "GET"
        opts = m.group(2)
        if opts:
            mm = FETCH_METHOD_RE.search(opts)
            if mm:
                method = mm.group(1).upper()
        r.api_calls.append((method, m.group(1), _lineno_at(text, m.start())))
    for m in AXIOS_RE.finditer(text):
        r.api_calls.append((m.group(1).upper(), m.group(2), _lineno_at(text, m.start())))

    for m in JSX_COMPONENT_RE.finditer(text):
        r.renders.append((m.group(1), _lineno_at(text, m.start())))

    known_func_names = {f[0] for f in r.functions}
    for m in CALL_RE.finditer(text):
        name = m.group(1)
        if name in ("function", "if", "for", "while", "switch", "catch", "return"):
            continue
        r.calls.append((name, _lineno_at(text, m.start())))

    return r
