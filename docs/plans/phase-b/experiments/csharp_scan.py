"""B0 prototype: find C# type declarations and their full names (dt:fullName format) in one source file."""

from __future__ import annotations

import re

TYPE_KEYWORDS = {"class", "interface", "struct", "enum", "record", "delegate"}
NOT_NAMES = {"where", "new", "class", "struct", "unmanaged", "notnull", "default"}
_IDENT = re.compile(r"@?[A-Za-z_À-￿][A-Za-z0-9_À-￿]*")


_PP = re.compile(r"[ \t]*#[ \t]*(if|elif|else|endif)\b(.*)")


def _pp_eval(expr: str, defines: set[str]) -> bool:
    expr = expr.split("//", 1)[0]
    py = re.sub(r"&&", " and ", expr)
    py = re.sub(r"\|\|", " or ", py)
    py = re.sub(r"!(?!=)", " not ", py)
    py = re.sub(r"[A-Za-z_][A-Za-z0-9_]*", lambda m: m.group() if m.group() in ("and", "or", "not") else
                ("True" if m.group() == "true" else "False" if m.group() == "false" else str(m.group() in defines)), py)
    try:
        return bool(eval(py, {"__builtins__": {}}))
    except Exception:
        return True


def preprocess(text: str, defines: set[str] | None) -> str:
    """Blank lines in inactive #if branches (defines given), keeping line numbers. None keeps every branch."""
    if defines is None:
        return text
    lines = text.split("\n")
    stack: list[tuple[bool, bool]] = []   # (branch active, some branch already taken)
    out = []
    for line in lines:
        m = _PP.match(line)
        outer = all(a for a, _ in stack)
        if m:
            d, rest = m.group(1), m.group(2)
            if d == "if":
                v = _pp_eval(rest, defines)
                stack.append((v, v))
            elif d == "elif" and stack:
                _, taken = stack[-1]
                v = not taken and _pp_eval(rest, defines)
                stack[-1] = (v, taken or v)
            elif d == "else" and stack:
                _, taken = stack[-1]
                stack[-1] = (not taken, True)
            elif d == "endif" and stack:
                stack.pop()
            out.append("")
            continue
        out.append(line if outer else "")
    return "\n".join(out)


def strip(text: str) -> str:
    """Blank out comments, strings, char literals and preprocessor lines, keeping newlines and code."""
    out: list[str] = []
    i, n = 0, len(text)
    at_line_start = True
    while i < n:
        c = text[i]
        if c == "\n":
            out.append(c); i += 1; at_line_start = True; continue
        if at_line_start and c in " \t":
            out.append(c); i += 1; continue
        if at_line_start and c == "#":
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        at_line_start = False
        if text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            end = n if j < 0 else j + 2
            out.append("".join(ch if ch == "\n" else " " for ch in text[i:end])); i = end
            continue
        m = re.match(r'(\$+)?(@)?(\$+)?("{3,})', text[i:i + 12])
        if m and m.group(4):
            quotes = m.group(4)
            j = text.find(quotes, i + m.end())
            end = n if j < 0 else j + len(quotes)
            out.append('""' + "\n" * text[i:end].count("\n")); i = end
            continue
        m = re.match(r'(\$)?(@)?(\$)?"', text[i:i + 4])
        if m:
            interpolated = bool(m.group(1) or m.group(3))
            verbatim = bool(m.group(2))
            j = i + m.end()
            depth = 0
            while j < n:
                ch = text[j]
                if verbatim and ch == '"' and text.startswith('""', j) and depth == 0:
                    j += 2; continue
                if not verbatim and ch == "\\":
                    j += 2; continue
                if interpolated and ch == "{":
                    if text.startswith("{{", j) and depth == 0:
                        j += 2; continue
                    depth += 1
                elif interpolated and ch == "}" and depth:
                    depth -= 1
                elif ch == '"' and depth == 0:
                    j += 1; break
                elif ch == "\n" and not verbatim and depth == 0:
                    break
                j += 1
            out.append('""' + "\n" * text[i:j].count("\n")); i = j
            continue
        if c == "'":
            m = re.match(r"'(\\.[^']*|[^'\\])'", text[i:i + 12])
            if m:
                out.append("' '"); i += m.end(); continue
        out.append(c); i += 1
    return "".join(out)


_TOKEN = re.compile(r"@?[A-Za-z_À-￿][A-Za-z0-9_À-￿]*|[{};<>(),.=:\[\]]|\S")


def tokens(text: str):
    line = 1
    for m in re.finditer(r"\n|" + _TOKEN.pattern, text):
        if m.group() == "\n":
            line += 1
        else:
            yield m.group(), line


def _type_params(toks: list[tuple[str, int]], k: int) -> tuple[list[str], int]:
    """At toks[k] == '<': the parameter names (variance keywords dropped) and the index after '>'."""
    names, depth, j, current = [], 0, k, []
    while j < len(toks):
        t = toks[j][0]
        if t == "<":
            depth += 1
        elif t == ">":
            depth -= 1
            if depth == 0:
                if current:
                    names.append(current[-1])
                return names, j + 1
        elif t == "," and depth == 1:
            if current:
                names.append(current[-1])
            current = []
        elif depth == 1 and _IDENT.fullmatch(t) and t not in {"in", "out"}:
            current.append(t.lstrip("@"))
        elif t == "[" and depth == 1:
            pass
        j += 1
    return names, j


def declarations(text: str, defines: set[str] | None = None) -> list[tuple[str, int]]:
    """(full name as dt:fullName, line) for every type declared in the file's active branches."""
    toks = list(tokens(strip(preprocess(text, defines))))
    found: list[tuple[str, int]] = []
    scopes: list[tuple[str, str]] = []   # (kind, name): kind in namespace|type|other
    file_namespace = ""
    pending: tuple[str, str] | None = None
    k = 0

    def prefix() -> str:
        parts = [file_namespace] if file_namespace else []
        parts += [name for kind, name in scopes if kind in ("namespace", "type") and name]
        return ".".join(p for p in parts if p)

    while k < len(toks):
        t, line = toks[k]
        if t == "namespace":
            j, parts = k + 1, []
            while j < len(toks) and toks[j][0] not in ("{", ";"):
                if toks[j][0] != ".":
                    parts.append(toks[j][0].lstrip("@"))
                j += 1
            name = ".".join(parts)
            if j < len(toks) and toks[j][0] == ";":
                file_namespace = name
                k = j + 1
                continue
            pending = ("namespace", name)
            k = j
            continue
        if t in TYPE_KEYWORDS and not (k and toks[k - 1][0] in (".", ":", ",") and t in ("class", "struct")):
            j = k + 1
            if t == "record" and j < len(toks) and toks[j][0] in ("class", "struct"):
                j += 1
            if t == "delegate":
                end = j
                while end < len(toks) and toks[end][0] not in ("(", ";", "{"):
                    end += 1
                if end >= len(toks) or toks[end][0] != "(":
                    k += 1
                    continue
                stop = end
                params: list[str] = []
                if toks[stop - 1][0] == ">":
                    depth, s = 0, stop - 1
                    while s > j:
                        if toks[s][0] == ">":
                            depth += 1
                        elif toks[s][0] == "<":
                            depth -= 1
                            if depth == 0:
                                break
                        s -= 1
                    params, _ = _type_params(toks, s)
                    stop = s
                name = toks[stop - 1][0].lstrip("@")
                if _IDENT.fullmatch(name) and name not in NOT_NAMES:
                    display = name + (f"<{', '.join(params)}>" if params else "")
                    found.append((".".join(p for p in (prefix(), display) if p), line))
                k = end
                continue
            if j < len(toks) and _IDENT.fullmatch(toks[j][0]) and toks[j][0] not in NOT_NAMES and toks[j][0] not in TYPE_KEYWORDS:
                name = toks[j][0].lstrip("@")
                params, after = ([], j + 1)
                if after < len(toks) and toks[after][0] == "<":
                    params, after = _type_params(toks, after)
                display = name + (f"<{', '.join(params)}>" if params else "")
                found.append((".".join(p for p in (prefix(), display) if p), line))
                depth, m = 0, after
                while m < len(toks):
                    s = toks[m][0]
                    if s in ("(", "["):
                        depth += 1
                    elif s in (")", "]"):
                        depth -= 1
                    elif depth == 0 and s in ("{", ";"):
                        break
                    m += 1
                if m < len(toks) and toks[m][0] == "{":
                    pending = ("type", display)
                k = m
                continue
        if t == "{":
            scopes.append(pending or ("other", ""))
            pending = None
        elif t == "}":
            if scopes:
                scopes.pop()
        elif t == ";":
            pending = None if pending and pending[0] == "type" else pending
        k += 1
    return found
