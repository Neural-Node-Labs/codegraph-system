"""
Deterministic Python static analysis using the stdlib `ast` module.
Extracts: imports, function/class defs, calls, config reads, route decorators.
No LLM, no inference beyond standard AST walking.
"""
import ast
from pathlib import Path


CONFIG_READ_FUNCS = {"getenv", "get"}  # os.getenv(...), config.get(...), os.environ.get(...)
ROUTE_DECORATOR_HINTS = {"route", "get", "post", "put", "delete", "patch"}


def _sig_of_func(node: ast.FunctionDef):
    args = [a.arg for a in node.args.args]
    return f"{node.name}({', '.join(args)})"


class PyVisitor(ast.NodeVisitor):
    def __init__(self, file_path, module_name):
        self.file_path = file_path
        self.module_name = module_name
        self.imports = []      # (imported_module, alias, lineno, fallback_mod)
        self.functions = []    # (name, lineno, end_lineno, signature, docstring)
        self.classes = []      # (name, lineno, end_lineno, docstring)
        self.calls = []        # (caller_name_or_module, called_name, lineno)
        self.config_reads = [] # (caller_name_or_module, key, lineno)
        self.routes = []       # (func_name, method, path, lineno)
        self._scope_stack = []

    def _current_scope(self):
        return self._scope_stack[-1] if self._scope_stack else self.module_name

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.append((alias.name, alias.asname, node.lineno, None))
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        mod = node.module or ""
        for alias in node.names:
            # Record both possibilities: the imported name might be a submodule
            # (from pkg import submodule) or a symbol inside `mod` (from mod import Symbol).
            # Resolution tries the full path first, then falls back to `mod` alone.
            full = f"{mod}.{alias.name}" if mod else alias.name
            self.imports.append((full, alias.asname, node.lineno, mod or None))
        self.generic_visit(node)

    def _decorator_route(self, node):
        for dec in node.decorator_list:
            call = dec if isinstance(dec, ast.Call) else None
            func = call.func if call else dec
            attr_name = None
            if isinstance(func, ast.Attribute):
                attr_name = func.attr
            elif isinstance(func, ast.Name):
                attr_name = func.id
            if attr_name in ROUTE_DECORATOR_HINTS:
                path = None
                if call and call.args:
                    a0 = call.args[0]
                    if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                        path = a0.value
                method = attr_name.upper() if attr_name != "route" else "GET"
                # FastAPI/Flask: methods=["POST"] kwarg
                if call:
                    for kw in call.keywords:
                        if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                            vals = [e.value for e in kw.value.elts if isinstance(e, ast.Constant)]
                            if vals:
                                method = vals[0].upper()
                if path:
                    self.routes.append((node.name, method, path, node.lineno))

    def visit_FunctionDef(self, node):
        doc = ast.get_docstring(node)
        self.functions.append((node.name, node.lineno, node.end_lineno, _sig_of_func(node), doc))
        self._decorator_route(node)
        self._scope_stack.append(node.name)
        self.generic_visit(node)
        self._scope_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        doc = ast.get_docstring(node)
        self.classes.append((node.name, node.lineno, node.end_lineno, doc))
        self._scope_stack.append(node.name)
        self.generic_visit(node)
        self._scope_stack.pop()

    def visit_Call(self, node):
        func = node.func
        name = None
        owner = None
        if isinstance(func, ast.Attribute):
            name = func.attr
            if isinstance(func.value, ast.Name):
                owner = func.value.id
        elif isinstance(func, ast.Name):
            name = func.id

        if name in CONFIG_READ_FUNCS and (owner in ("os", "environ", "config", "settings") or owner is None):
            key = None
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                key = node.args[0].value
            if key:
                self.config_reads.append((self._current_scope(), key, node.lineno))
        elif name:
            self.calls.append((self._current_scope(), name, node.lineno))

        self.generic_visit(node)


def parse_python_file(file_path: str, repo_root: str):
    rel = str(Path(file_path).relative_to(repo_root))
    module_name = rel[:-3].replace("/", ".") if rel.endswith(".py") else rel.replace("/", ".")
    try:
        source = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source, filename=file_path)
    except SyntaxError:
        return None
    v = PyVisitor(rel, module_name)
    v.visit(tree)
    return v
