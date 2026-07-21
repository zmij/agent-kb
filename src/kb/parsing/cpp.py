"""Extract public API symbols and their doxygen from C++ headers.

Uses tree-sitter-cpp for a robust AST walk. Emits one :class:`CppSymbol` per
class, struct, free function, public method, type alias, or enum found in the
header. Private and protected members are skipped — the KB is for documenting
the *public* surface that callers across FFI/Dart/Flutter would interact with.

Comments preceding a declaration are picked up when they are doxygen-shaped
(``/**`` or ``/*!``). The doxygen text is lifted verbatim (with leading ``*``
stripped) so existing ``@brief`` / ``@param`` markers survive into the chunk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

import tree_sitter_cpp
from tree_sitter import Language, Node, Parser


_CPP_LANGUAGE = Language(tree_sitter_cpp.language())
_PARSER = Parser(_CPP_LANGUAGE)

_DOXYGEN_START = re.compile(rb"^\s*/\*[*!]")
_DOXY_LINE_PREFIX = re.compile(r"^\s*\*\s?")


@dataclass
class CppSymbol:
    kind: str  # "class" | "struct" | "function" | "method" | "alias" | "enum" | "namespace"
    name: str
    qualified_name: str
    signature: str
    doxygen: str
    header_rel_path: str
    line_start: int  # 1-indexed
    line_end: int  # 1-indexed inclusive
    parent: str = ""  # owning class for methods, "" for top-level
    namespace: str = ""

    def is_documented(self) -> bool:
        return bool(self.doxygen.strip())


def _node_text(src: bytes, node: Node) -> str:
    return src[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _strip_doxygen(raw: str) -> str:
    """Strip the ``/**``/``*/`` envelope and leading ``*`` from each body line."""

    body = raw.strip()
    if body.startswith("/**"):
        body = body[3:]
    elif body.startswith("/*!"):
        body = body[3:]
    elif body.startswith("/*"):
        body = body[2:]
    if body.endswith("*/"):
        body = body[:-2]
    lines = [_DOXY_LINE_PREFIX.sub("", ln).rstrip() for ln in body.splitlines()]
    # Drop empty leading/trailing lines.
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _preceding_doxygen(src: bytes, node: Node) -> str:
    """Return the doxygen comment immediately preceding ``node`` (or '').

    Walks the previous siblings — but stops at the first non-comment / non-whitespace
    sibling. Only ``/**`` or ``/*!`` blocks qualify.
    """

    sib = node.prev_sibling
    while sib is not None:
        if sib.type == "comment":
            raw_bytes = src[sib.start_byte : sib.end_byte]
            if _DOXYGEN_START.match(raw_bytes):
                return _strip_doxygen(raw_bytes.decode("utf-8", errors="replace"))
            sib = sib.prev_sibling
            continue
        # Non-comment sibling on the same scope → no doxygen attached.
        return ""
    return ""


def _signature_line(src: bytes, node: Node) -> str:
    """Best-effort single-line signature for class/function nodes.

    Truncates at the first ``{``/``;`` to keep chunks compact.
    """

    text = _node_text(src, node)
    for stop in ("{", ";"):
        i = text.find(stop)
        if i != -1:
            text = text[:i]
    return " ".join(text.split())


def _qualify(namespace: str, parent: str, name: str) -> str:
    parts = [p for p in (namespace, parent, name) if p]
    return "::".join(parts)


def _find_class_name(class_node: Node) -> str:
    for child in class_node.children:
        if child.type == "type_identifier":
            return child.text.decode("utf-8")
    return ""


def _find_function_name(func_node: Node) -> tuple[str, bool]:
    """Return (name, is_method) for a function_definition or declaration.

    Walks down to the deepest function_declarator and returns its identifier.
    ``is_method`` is True when the identifier was a ``field_identifier`` (i.e.
    declared inside a class field_declaration_list).
    """

    declarator = _descend_to_declarator(func_node)
    if declarator is None:
        return "", False
    for child in declarator.children:
        if child.type == "field_identifier":
            return child.text.decode("utf-8"), True
        if child.type == "identifier":
            return child.text.decode("utf-8"), False
        # operators / destructors etc. — best effort
        if child.type in {"operator_name", "destructor_name"}:
            return child.text.decode("utf-8"), True
    return "", False


def _descend_to_declarator(node: Node) -> Optional[Node]:
    # function_definition → function_declarator (may be wrapped in pointer/ref declarator)
    queue = [node]
    while queue:
        n = queue.pop(0)
        if n.type == "function_declarator":
            return n
        queue.extend(n.children)
    return None


def _enum_name(enum_node: Node) -> str:
    for child in enum_node.children:
        if child.type == "type_identifier":
            return child.text.decode("utf-8")
    return ""


def _alias_name(alias_node: Node) -> str:
    for child in alias_node.children:
        if child.type == "type_identifier":
            return child.text.decode("utf-8")
    return ""


def parse_header(path: Path, repo_root: Path) -> Iterator[CppSymbol]:
    src = path.read_bytes()
    tree = _PARSER.parse(src)
    rel = str(path.relative_to(repo_root))
    yield from _walk(
        tree.root_node,
        src,
        rel,
        namespace="",
        parent="",
        access="public",
        comment_anchor=None,
    )


def _walk(
    node: Node,
    src: bytes,
    header_rel: str,
    *,
    namespace: str,
    parent: str,
    access: str,
    comment_anchor: Optional[Node],
) -> Iterator[CppSymbol]:
    # ``comment_anchor`` is the node whose prev_sibling carries the doxygen
    # for the symbol about to be emitted. It overrides per-node lookup for
    # cases like template_declaration where the symbol sits inside a wrapper
    # that has no comment sibling itself.
    def doxygen_for(default: Node) -> str:
        return _preceding_doxygen(src, comment_anchor or default)
    # Determine what *this* node contributes, then recurse.
    if node.type == "namespace_definition":
        name = ""
        for child in node.children:
            if child.type in {"namespace_identifier", "nested_namespace_specifier"}:
                name = child.text.decode("utf-8")
                break
        new_ns = _qualify(namespace, "", name) if name else namespace
        for child in node.children:
            yield from _walk(
                child,
                src,
                header_rel,
                namespace=new_ns,
                parent=parent,
                access=access,
                comment_anchor=None,
            )
        return

    if node.type in {"class_specifier", "struct_specifier"}:
        # An elaborated type specifier (e.g. ``const class Foo*``) parses as
        # class_specifier with no body — skip it; it's a *use*, not a *definition*.
        has_body = any(c.type == "field_declaration_list" for c in node.children)
        if not has_body:
            return
        name = _find_class_name(node)
        if name:
            yield CppSymbol(
                kind="class" if node.type == "class_specifier" else "struct",
                name=name,
                qualified_name=_qualify(namespace, parent, name),
                signature=_signature_line(src, node),
                doxygen=doxygen_for(node),
                header_rel_path=header_rel,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                parent=parent,
                namespace=namespace,
            )
        # Members default to private in `class`, public in `struct`.
        inner_access = "public" if node.type == "struct_specifier" else "private"
        new_parent = _qualify(parent, "", name) if name else parent
        for child in node.children:
            yield from _walk(
                child,
                src,
                header_rel,
                namespace=namespace,
                parent=new_parent,
                access=inner_access,
                comment_anchor=None,
            )
        return

    if node.type == "field_declaration_list":
        current_access = access
        for child in node.children:
            if child.type == "access_specifier":
                current_access = child.text.decode("utf-8")
                continue
            if current_access != "public":
                continue
            yield from _walk(
                child,
                src,
                header_rel,
                namespace=namespace,
                parent=parent,
                access=current_access,
                comment_anchor=None,
            )
        return

    if node.type == "function_definition":
        name, is_method = _find_function_name(node)
        if name:
            yield CppSymbol(
                kind="method" if is_method else "function",
                name=name,
                qualified_name=_qualify(namespace, parent, name),
                signature=_signature_line(src, node),
                doxygen=doxygen_for(node),
                header_rel_path=header_rel,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                parent=parent,
                namespace=namespace,
            )
        # Don't recurse into function bodies — no top-level symbols hide in there.
        return

    if node.type in {"declaration", "field_declaration"}:
        # Free-function declaration, or a class/struct member declaration with
        # no body (pure virtual, declared-elsewhere). field_declaration is the
        # in-class variant. Either way, look for a function_declarator deeper
        # down; if there is one, we treat this as a function/method.
        declarator = _descend_to_declarator(node)
        if declarator is not None:
            name, is_method = _find_function_name(node)
            # Inside a class, even a generic identifier resolves to a method.
            if name and parent:
                is_method = True
            if name:
                yield CppSymbol(
                    kind="method" if is_method else "function",
                    name=name,
                    qualified_name=_qualify(namespace, parent, name),
                    signature=_signature_line(src, node),
                    doxygen=doxygen_for(node),
                    header_rel_path=header_rel,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    parent=parent,
                    namespace=namespace,
                )
            return

    if node.type in {"alias_declaration", "type_definition"}:
        name = _alias_name(node)
        if name:
            yield CppSymbol(
                kind="alias",
                name=name,
                qualified_name=_qualify(namespace, parent, name),
                signature=_signature_line(src, node),
                doxygen=doxygen_for(node),
                header_rel_path=header_rel,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                parent=parent,
                namespace=namespace,
            )
        return

    if node.type == "enum_specifier":
        name = _enum_name(node)
        if name:
            yield CppSymbol(
                kind="enum",
                name=name,
                qualified_name=_qualify(namespace, parent, name),
                signature=_signature_line(src, node),
                doxygen=doxygen_for(node),
                header_rel_path=header_rel,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                parent=parent,
                namespace=namespace,
            )
        return

    if node.type == "template_declaration":
        # Recurse into the wrapped declaration, but anchor doxygen lookup to the
        # template_declaration itself — that's where the comment sits.
        for child in node.children:
            if child.type in {
                "class_specifier",
                "struct_specifier",
                "function_definition",
                "declaration",
                "alias_declaration",
                "type_definition",
            }:
                yield from _walk(
                    child,
                    src,
                    header_rel,
                    namespace=namespace,
                    parent=parent,
                    access=access,
                    comment_anchor=node,
                )
        return

    # Generic descent.
    for child in node.children:
        yield from _walk(
            child,
            src,
            header_rel,
            namespace=namespace,
            parent=parent,
            access=access,
            comment_anchor=None,
        )
