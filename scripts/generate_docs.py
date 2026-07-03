#!/usr/bin/env python3
"""Generate ADK API reference markdown pages from Python docstrings.

Scans ``adk/tesserax_adk/`` for modules, extracts module/class/function
docstrings, and writes VitePress-friendly markdown pages into
``adk/docs/content/adk/``.

Run from the adk/ directory:
    python scripts/generate_docs.py
"""

from __future__ import annotations

import ast
import inspect
import os
import re
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent  # adk/
ADK_SRC = REPO_ROOT / "tesserax_adk"
DOCS_OUT = REPO_ROOT / "docs" / "content"

#  helpers 

MODULE_DISPLAY = {
    "__init__": {"title": "Package Overview", "order": 0},
    "cli": {"title": "CLI Reference", "order": 1},
    "client": {"title": "Arena Client", "order": 2},
    "adapter": {"title": "Adapter", "order": 3},
    "server": {"title": "Webhook Server", "order": 4},
    "config": {"title": "Configuration", "order": 5},
}

MODULE_SKIP = frozenset()


def _md_escape(text: str) -> str:
    """Light escaping for markdown -- angle brackets and backticks."""
    return text.replace("<", r"\<").replace(">", r"\>")


def _module_name(path: Path) -> str:
    return path.stem  # e.g. "cli" from "cli.py"


def _display_name(path: Path) -> str:
    name = _module_name(path)
    return MODULE_DISPLAY.get(name, {}).get("title", name.title())


def _order(path: Path) -> int:
    name = _module_name(path)
    return MODULE_DISPLAY.get(name, {}).get("order", 99)


def _type_annotation(node: ast.expr | None) -> str:
    """Convert an AST type annotation to a readable string."""
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant):
        if node.value is None:
            return "None"
        if isinstance(node.value, str):
            return f'"{node.value}"'
        if isinstance(node.value, bool):
            return "True" if node.value else "False"
        return str(node.value)
    if isinstance(node, ast.Subscript):
        value = _type_annotation(node.value)
        slice_ = _type_annotation(node.slice)
        return f"{value}[{slice_}]"
    if isinstance(node, ast.Attribute):
        return f"{_type_annotation(node.value)}.{node.attr}"
    if isinstance(node, ast.Tuple):
        return ", ".join(_type_annotation(e) for e in node.elts)
    if isinstance(node, ast.BinOp):
        return f"{_type_annotation(node.left)} | {_type_annotation(node.right)}"
    return ast.dump(node)


def _extract_default(node: ast.expr | None) -> str:
    """Extract a default value literal from an AST node."""
    if node is None:
        return ""
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.List):
        items = ", ".join(_extract_default(e) for e in node.elts)
        return f"[{items}]"
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return "not " + _extract_default(node.operand)
    return ast.dump(node)


def _trim_doc(doc: str) -> str:
    """Trim leading/trailing whitespace and dedent."""
    return textwrap.dedent(doc).strip() if doc else ""


def _parse_typer_params(node: ast.FunctionDef) -> list[dict]:
    """Parse typer.Option / typer.Argument calls from a function body."""
    params = []
    for stmt in node.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.annotation, ast.Name) and stmt.annotation.id == "int":
            continue  # skip type-only annotations
    for stmt in node.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Attribute) and target.attr == "args" and isinstance(target.value, ast.Attribute):
                    pass  # ctx.args handling

    # Walk calls in body for typer.Option(...), typer.Argument(...)
    for stmt in node.body:
        for called_node in ast.walk(stmt):
            if not isinstance(called_node, ast.Call):
                continue
            func = called_node.func
            if isinstance(func, ast.Attribute) and func.attr in ("Option", "Argument"):
                parent = func.value
                if isinstance(parent, ast.Name) and parent.id == "typer":
                    kind = "option" if func.attr == "Option" else "argument"
                    param = _parse_typer_arg(called_node, kind)
                    if param:
                        params.append(param)
    return params


def _parse_typer_arg(call: ast.Call, kind: str) -> dict:
    """Extract typer.Option/Argument metadata."""
    param = {"kind": kind, "names": [], "help": "", "default": None}
    for kw in call.keywords:
        if kw.arg == "help" and isinstance(kw.value, ast.Constant):
            param["help"] = kw.value.value
        elif kw.arg == "default" or (kw.arg == "..."):
            param["default"] = _extract_default(kw.value)
    for arg in call.args:
        if isinstance(arg, ast.Constant):
            param["names"].append(arg.value)
    return param


def _iter_functions(body: list[ast.stmt], source: str) -> list[dict]:
    """Yield function dicts: name, sig, doc, params (typer)."""
    funcs = []
    for stmt in body:
        if isinstance(stmt, ast.FunctionDef):
            doc = ast.get_docstring(stmt) or ""
            params = _parse_typer_params(stmt)

            # Build signature from the function definition
            sig_parts = []
            for arg in stmt.args.args:
                if arg.arg == "self" or arg.arg == "cls":
                    continue
                part = arg.arg
                if arg.annotation:
                    part += f": {_type_annotation(arg.annotation)}"
                sig_parts.append(part)
            if stmt.args.vararg:
                sig_parts.append(f"*{stmt.args.vararg.arg}")
            if stmt.args.kwonlyargs:
                for arg in stmt.args.kwonlyargs:
                    part = arg.arg
                    if arg.annotation:
                        part += f": {_type_annotation(arg.annotation)}"
                    sig_parts.append(part)
            if stmt.args.kwarg:
                sig_parts.append(f"**{stmt.args.kwarg.arg}")

            funcs.append({
                "name": stmt.name,
                "signature": f"({', '.join(sig_parts)})",
                "doc": _trim_doc(doc),
                "is_typer_command": any(
                    isinstance(d, ast.Call)
                    and isinstance(d.func, ast.Attribute)
                    and d.func.attr == "command"
                    for d in ast.walk(stmt)
                ),
                "typer_params": params,
                "decorators": [d for d in stmt.decorator_list],
            })
    return funcs


def _iter_classes(body: list[ast.stmt]) -> list[dict]:
    """Yield class dicts: name, bases, doc, methods."""
    classes = []
    for stmt in body:
        if isinstance(stmt, ast.ClassDef):
            doc = ast.get_docstring(stmt) or ""
            bases = []
            for base in stmt.bases:
                if isinstance(base, ast.Name):
                    bases.append(base.id)
                elif isinstance(base, ast.Attribute):
                    bases.append(f"{base.value.id}.{base.attr}" if isinstance(base.value, ast.Name) else ast.dump(base))
                else:
                    bases.append(ast.dump(base))
            methods = []
            for child in stmt.body:
                if isinstance(child, ast.FunctionDef) and not child.name.startswith("_"):
                    mdoc = ast.get_docstring(child) or ""
                    sig_parts = []
                    for arg in child.args.args:
                        if arg.arg == "self":
                            continue
                        part = arg.arg
                        if arg.annotation:
                            part += f": {_type_annotation(arg.annotation)}"
                        sig_parts.append(part)
                    if child.args.vararg:
                        sig_parts.append(f"*{child.args.vararg.arg}")
                    if child.args.kwonlyargs:
                        for arg in child.args.kwonlyargs:
                            part = arg.arg
                            if arg.annotation:
                                part += f": {_type_annotation(arg.annotation)}"
                            sig_parts.append(part)
                    if child.args.kwarg:
                        sig_parts.append(f"**{child.args.kwarg.arg}")

                    methods.append({
                        "name": child.name,
                        "signature": f"({', '.join(sig_parts)})",
                        "doc": _trim_doc(mdoc),
                    })
            classes.append({
                "name": stmt.name,
                "bases": bases,
                "doc": _trim_doc(doc),
                "methods": methods,
            })
    return classes


#  generators 


def _fmt_doc(doc: str, indent: str = "") -> str:
    """Format a docstring as markdown prose."""
    if not doc:
        return ""
    # Convert RST-style ``code`` to markdown backticks
    text = re.sub(r"``([^`]+)``", r"`\1`", doc)
    # Convert single-backtick to inline code
    text = re.sub(r"(?<!\w)`(\w[^`]*\w)`(?!\w)", r"`\1`", text)
    lines = text.split("\n")
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(":param") or stripped.startswith(":type") or stripped.startswith(":return"):
            continue  # skip Sphinx-style param docs, we have the function sig
        # If line looks like an example command, make it a code block
        if stripped.startswith("$ ") or stripped.startswith(">>> "):
            out.append(f"{indent}```")
            out.append(f"{indent}{stripped}")
            out.append(f"{indent}```")
        else:
            out.append(f"{indent}{line}")
    return "\n".join(out)


def _generate_module_page(path: Path) -> str:
    """Generate a complete markdown page for a single ADK module."""
    name = _module_name(path)
    display = _display_name(path)
    source = path.read_text()

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""

    module_doc = ast.get_docstring(tree) or ""
    classes = _iter_classes(tree.body)
    functions = _iter_functions(tree.body, source)

    lines = [
        f"# {display}",
        "",
    ]

    # Module docstring
    if module_doc:
        lines.append(_fmt_doc(module_doc))
        lines.append("")

    # Source link
    lines.append(f"> **Source:** `tesserax_adk/{path.name}`")
    lines.append("")

    #  Classes 
    for cls in classes:
        lines.append(f"## `{cls['name']}`")
        if cls['bases']:
            lines.append("")
            bases_str = " | ".join(cls['bases'])
            lines.append(f"Extends: `{bases_str}`")
            lines.append("")
        if cls['doc']:
            lines.append(_fmt_doc(cls['doc']))
            lines.append("")

        if cls['methods']:
            for m in cls['methods']:
                lines.append(f"### `{m['name']}{m['signature']}`")
                if m['doc']:
                    lines.append("")
                    lines.append(_fmt_doc(m['doc']))
                    lines.append("")

    #  Functions 
    for fn in functions:
        lines.append(f"## `{fn['name']}{fn['signature']}`")
        if fn["doc"]:
            lines.append("")
            lines.append(_fmt_doc(fn["doc"]))
            lines.append("")

        # typer-specific: show option/argument details
        if fn["typer_params"]:
            lines.append("")
            lines.append("**CLI parameters:**")
            lines.append("")
            for p in fn["typer_params"]:
                names = ", ".join(p["names"])
                lines.append(f"- **`{names}`** ({p['kind']})")
                if p.get("help"):
                    lines.append(f"  - {p['help']}")
                if p.get("default"):
                    lines.append(f"  - Default: `{p['default']}`")
            lines.append("")

    return "\n".join(lines)


def generate_all() -> dict[str, str]:
    """Generate all module pages. Returns {slug: markdown_content}."""
    pages = {}
    for py_file in sorted(ADK_SRC.glob("*.py"), key=_order):
        if _module_name(py_file) in MODULE_SKIP:
            continue
        content = _generate_module_page(py_file)
        if content:
            pages[_module_name(py_file)] = content
    return pages


def write_pages(pages: dict[str, str]) -> list[Path]:
    """Write generated markdown pages to DOCS_OUT."""
    DOCS_OUT.mkdir(parents=True, exist_ok=True)
    written = []
    for slug, content in pages.items():
        out_path = DOCS_OUT / f"{slug}.md"
        out_path.write_text(content)
        written.append(out_path)
        print(f"  wrote {out_path.relative_to(REPO_ROOT.parent)}")
    return written


def generate_sidebar_items() -> list[dict]:
    """Return VitePress sidebar items for the ADK section."""
    items = []
    for py_file in sorted(ADK_SRC.glob("*.py"), key=_order):
        name = _module_name(py_file)
        if name in MODULE_SKIP:
            continue
        items.append({
            "text": _display_name(py_file),
            "link": f"/{name}",
        })
    items.insert(0, {"text": "Overview", "link": "/"})
    return items


def generate_sidebar_block() -> str:
    """Generate a Python snippet for the VitePress sidebar config."""
    items = generate_sidebar_items()
    lines = ["sidebar_adk = ["]
    for item in items:
        lines.append(f'    {{text: "{item["text"]}", link: "{item["link"]}"}},')
    lines.append("]")
    return "\n".join(lines)


#  main 


def main():
    print("Generating ADK API docs from docstrings...")
    pages = generate_all()
    written = write_pages(pages)
    print(f"\n{len(written)} pages written to {DOCS_OUT}")
    print(f"\nSidebar config snippet:\n")
    print(generate_sidebar_block())


if __name__ == "__main__":
    main()
