"""Builds function-calling schema for Buddy's newer tool modules straight from
their source (via ast, no imports), so adding a tool = writing a function with
a docstring and type hints. Appended to tools_schema at the bottom of that file."""
import ast
from pathlib import Path

_MODULES = ("browser_control", "lessons", "guides", "code_agent", "google_extras", "microsoft_extras")
_TYPES = {"int": "integer", "float": "number", "bool": "boolean", "list": "array", "dict": "object", "str": "string"}


def _entry(fn):
    props, required = {}, []
    args = fn.args.args
    defaults = [None] * (len(args) - len(fn.args.defaults)) + list(fn.args.defaults)
    for arg, default in zip(args, defaults):
        ann = getattr(arg.annotation, "id", "str")
        props[arg.arg] = {"type": _TYPES.get(ann, "string")}
        if ann == "list":
            props[arg.arg]["items"] = {"type": "array", "items": {"type": "string"}}
        if default is None:
            required.append(arg.arg)
    doc = (ast.get_docstring(fn) or fn.name.replace("_", " ")).strip().replace("\n", " ")
    return {"type": "function", "function": {
        "name": fn.name, "description": doc,
        "parameters": {"type": "object", "properties": props, "required": required}}}


def build_extra_schema():
    out = []
    folder = Path(__file__).resolve().parent
    for name in _MODULES:
        path = folder / (name + ".py")
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                out.append(_entry(node))
    return out


def extra_tool_names(module_name):
    path = Path(__file__).resolve().parent / (module_name + ".py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {n.name for n in tree.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")}
