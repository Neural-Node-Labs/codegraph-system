"""
Deterministic route-registration extraction for JS backends (Express-style):
    app.get('/api/users', handler)
    router.post('/api/orders/:id', handler)
"""
import re
from pathlib import Path

EXPRESS_ROUTE_RE = re.compile(
    r"""\b(?:app|router)\.(get|post|put|delete|patch)\(\s*[`'"]([^`'"]+)[`'"]"""
)


def _lineno_at(text, pos):
    return text.count("\n", 0, pos) + 1


def parse_express_routes(file_path: str, repo_root: str):
    text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    rel = str(Path(file_path).relative_to(repo_root))
    routes = []
    for m in EXPRESS_ROUTE_RE.finditer(text):
        method, path = m.group(1).upper(), m.group(2)
        routes.append((method, path, _lineno_at(text, m.start())))
    return rel, routes
