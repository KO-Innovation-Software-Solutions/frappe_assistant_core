# frappe_assistant_core/aiko/openui/dsl_manifest.py
"""
Lightweight OpenUI-Lang scanner used ONLY for refresh purposes.

Supports two DSL shapes:
  1. Single expression:      root = Stack([Card([...]), ...])
  2. Multi-statement:        root = Stack([masthead, kpi1, ...])
                             masthead = Card([...])
                             kpi1 = Card([...])
     where bare identifiers referencing other top-level statements are
     resolved and walked into.

Anything we don't recognize (ternaries, ``@Each(...)``, and ``Query(...)``
live data-bindings) is captured as an opaque node and left untouched on
rebuild — Query() results in particular are resolved at render time by the
frontend, not baked into the DSL as literals, so we can't refresh them via
literal diffing at all.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, List, Union

# ---------------------------------------------------------------- tokenizer

_PUNCT = set("()[],")

def _tokenize(src: str):
    i, n = 0, len(src)
    tokens = []
    while i < n:
        c = src[i]
        if c.isspace():
            i += 1
            continue
        if c == '"':
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == '"':
                    break
                j += 1
            tokens.append(("STRING", src[i:j + 1]))
            i = j + 1
            continue
        if c in _PUNCT:
            tokens.append((c, c))
            i += 1
            continue
        if c.isdigit() or (c == "-" and i + 1 < n and src[i + 1].isdigit()):
            j = i + 1
            while j < n and (src[j].isdigit() or src[j] == "."):
                j += 1
            tokens.append(("NUMBER", src[i:j]))
            i = j
            continue
        # Plain identifier (letters/digits/underscore only): tokenize it on
        # its own, separate from whatever follows. This is what lets a bare
        # call name like `Stack` or `TextContent` come through as its own
        # token immediately before a `(` token, so parse_value's one-token
        # lookahead can recognize "NAME immediately followed by (" and route
        # into parse_call(). Without this, scanning falls straight into the
        # balanced-bracket branch below, which — since it starts counting
        # depth from the call's own opening paren — never stops until the
        # WHOLE expression closes, collapsing every call into a single
        # opaque RAW blob and silently defeating literal extraction entirely.
        if c.isalpha() or c == "_":
            j = i
            while j < n and (src[j].isalnum() or src[j] == "_"):
                j += 1
            tokens.append(("RAW", src[i:j]))
            i = j
            continue
        # Anything else (ternaries, `@Sum(...)`, string concatenation with
        # `+`, dotted Query field access, etc.) is deliberately left as one
        # opaque, unparsed blob — see module docstring.
        j = i
        depth = 0
        while j < n:
            ch = src[j]
            if ch in "([":
                depth += 1
            elif ch in ")]":
                if depth == 0:
                    break
                depth -= 1
            elif ch == "," and depth == 0:
                break
            elif ch == '"' and depth == 0:
                break
            j += 1
        chunk = src[i:j]
        if chunk.strip():
            tokens.append(("RAW", chunk))
        else:
            i += 1
            continue
        i = j
    return tokens


# ---------------------------------------------------------------- AST

@dataclass
class Lit:
    kind: str
    value: Any
    path: tuple = ()

@dataclass
class Raw:
    text: str
    path: tuple = ()

@dataclass
class Call:
    name: str
    args: List[Union["Call", "Arr", Lit, Raw]] = field(default_factory=list)
    path: tuple = ()

@dataclass
class Arr:
    items: List[Union["Call", "Arr", Lit, Raw]] = field(default_factory=list)
    path: tuple = ()


class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (None, None)

    def next(self):
        t = self.peek()
        self.pos += 1
        return t

    def parse_value(self):
        kind, val = self.peek()
        if kind == "STRING":
            self.next()
            return Lit("string", val[1:-1])
        if kind == "NUMBER":
            self.next()
            num = float(val) if "." in val else int(val)
            return Lit("number", num)
        if kind == "[":
            return self.parse_array()
        if kind == "RAW":
            nxt = self.tokens[self.pos + 1] if self.pos + 1 < len(self.tokens) else (None, None)
            if nxt[0] == "(" and val.strip().replace("_", "").isalnum():
                return self.parse_call()
            self.next()
            if val.strip() in ("true", "false"):
                return Lit("bool", val.strip() == "true")
            if val.strip() == "null":
                return Lit("null", None)
            return Raw(val)
        self.next()
        return Raw(val or "")

    def parse_call(self):
        name_tok = self.next()
        name = name_tok[1].strip()
        assert self.next()[0] == "("
        args = []
        while self.peek()[0] != ")":
            args.append(self.parse_value())
            if self.peek()[0] == ",":
                self.next()
        self.next()
        return Call(name, args)

    def parse_array(self):
        assert self.next()[0] == "["
        items = []
        while self.peek()[0] != "]":
            items.append(self.parse_value())
            if self.peek()[0] == ",":
                self.next()
        self.next()
        return Arr(items)


def parse_dsl(src: str):
    """Parses a single `root = <expr>` (or bare expr) into our light AST."""
    t = src.strip()
    if t.startswith("root"):
        eq = t.find("=")
        if eq != -1:
            t = t[eq + 1:].strip()
    tokens = _tokenize(t)
    return _Parser(tokens).parse_value()


# ---------------------------------------------------------- multi-statement

_STMT_RE = re.compile(r'^[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*', re.MULTILINE)
_IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def parse_program(src: str):
    """
    Parses a full DSL source that may contain one or many `name = expr`
    top-level statements. Returns (env, order, root_name):
      env       -> {name: node}
      order     -> [name, ...] in original source order
      root_name -> the statement to start walking from ("root" if present)
    """
    src = src.strip()
    matches = list(_STMT_RE.finditer(src))
    if not matches:
        return {"root": parse_dsl(src)}, ["root"], "root"

    env, order = {}, []
    for i, m in enumerate(matches):
        name = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(src)
        expr_src = src[start:end].strip()
        try:
            node = _Parser(_tokenize(expr_src)).parse_value()
        except Exception:
            node = Raw(expr_src)
        env[name] = node
        order.append(name)

    root_name = "root" if "root" in env else order[-1]
    return env, order, root_name


def walk_literals_env(node, env, path=(), visited=None):
    """Depth-first walk that resolves bare-identifier references into env."""
    if visited is None:
        visited = set()
    node.path = path
    if isinstance(node, Lit):
        yield path, node
    elif isinstance(node, Raw):
        ident = node.text.strip()
        if _IDENT_RE.match(ident) and ident in env and ident not in visited:
            yield from walk_literals_env(env[ident], env, path + (ident,), visited | {ident})
        return
    elif isinstance(node, Call):
        if node.name == "Query":
            # Live data binding resolved at render time — not literal-diffable.
            return
        for idx, a in enumerate(node.args):
            yield from walk_literals_env(a, env, path + (node.name, idx), visited)
    elif isinstance(node, Arr):
        for idx, a in enumerate(node.items):
            yield from walk_literals_env(a, env, path + ("[]", idx), visited)


def _apply_updates_env(node, env, updates, path=(), visited=None):
    if visited is None:
        visited = set()
    if isinstance(node, Lit):
        if path in updates:
            new_val = updates[path]
            if isinstance(new_val, bool):
                node.kind, node.value = "bool", new_val
            elif isinstance(new_val, (int, float)):
                node.kind, node.value = "number", new_val
            elif new_val is None:
                node.kind, node.value = "null", None
            else:
                node.kind, node.value = "string", str(new_val)
    elif isinstance(node, Raw):
        ident = node.text.strip()
        if _IDENT_RE.match(ident) and ident in env and ident not in visited:
            _apply_updates_env(env[ident], env, updates, path + (ident,), visited | {ident})
    elif isinstance(node, Call):
        if node.name == "Query":
            return
        for idx, a in enumerate(node.args):
            _apply_updates_env(a, env, updates, path + (node.name, idx), visited)
    elif isinstance(node, Arr):
        for idx, a in enumerate(node.items):
            _apply_updates_env(a, env, updates, path + ("[]", idx), visited)


def serialize(node) -> str:
    if isinstance(node, Lit):
        if node.kind == "string":
            escaped = node.value.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        if node.kind == "number":
            return str(node.value)
        if node.kind == "bool":
            return "true" if node.value else "false"
        return "null"
    if isinstance(node, Raw):
        return node.text
    if isinstance(node, Call):
        return f"{node.name}({', '.join(serialize(a) for a in node.args)})"
    if isinstance(node, Arr):
        return f"[{', '.join(serialize(i) for i in node.items)}]"
    return ""


def rebuild_dsl(original_src: str, updates: dict) -> str:
    """
    updates: {path_tuple: new_python_value}
    Reconstructs the full DSL source (single- or multi-statement) with
    those literals swapped in, preserving statement order and `name = ` form.
    """
    env, order, root_name = parse_program(original_src)
    _apply_updates_env(env[root_name], env, updates, path=(root_name,))
    return "\n".join(f"{name} = {serialize(env[name])}" for name in order)


# ---------------------------------------------------------------- manifest

_CURRENCY_CHARS = "₹$€£,"
_PLAIN_NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?$")


def _clean_numeric(val):
    """Strip currency symbols/commas/whitespace and try to parse a float.
    Returns None if val isn't number-shaped at all (so we never accidentally
    treat an ID-like string, e.g. 'AP39TC6094', as a number)."""
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if not isinstance(val, str):
        return None
    s = val.strip()
    for ch in _CURRENCY_CHARS:
        s = s.replace(ch, "")
    s = s.strip()
    if not _PLAIN_NUMBER_RE.match(s):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _infer_format(literal_str):
    """
    Inspect how a DSL string literal is formatted (currency symbol, thousands
    separator, decimal precision) so a fresh raw number can later be rendered
    back into the *same shape* of string instead of requiring exact identity.
    Returns None if the literal isn't a simple formatted number (e.g. it's a
    sentence, an ID, or a label — those are left alone, never guessed at).
    NOTE: thousands formatting is re-rendered Western-style (1,234,567). If a
    literal used Indian digit grouping (1,23,45,678) the re-rendered string
    won't match that exact grouping — acceptable for now, flagged as a
    follow-up rather than silently mis-formatting.
    """
    if not isinstance(literal_str, str):
        return None
    s = literal_str.strip()
    currency = False
    currency_symbol = None
    for ch in ("₹", "$", "€", "£"):
        if s.startswith(ch):
            currency = True
            currency_symbol = ch
            break
    thousands = "," in s
    stripped = s
    for ch in _CURRENCY_CHARS:
        stripped = stripped.replace(ch, "")
    stripped = stripped.strip()
    if not _PLAIN_NUMBER_RE.match(stripped):
        return None
    decimals = len(stripped.split(".")[1]) if "." in stripped else 0
    return {"decimals": decimals, "currency": currency, "currency_symbol": currency_symbol, "thousands": thousands}


def format_value(raw_value, fmt):
    """Re-render a freshly fetched raw value using a previously inferred
    format so refresh doesn't require exact byte-for-byte identity. Falls
    back to returning raw_value untouched if there's nothing to apply."""
    if fmt is None or raw_value is None:
        return raw_value
    try:
        num = float(raw_value)
    except (TypeError, ValueError):
        return raw_value
    decimals = fmt.get("decimals", 0)
    text = f"{num:,.{decimals}f}" if fmt.get("thousands") else f"{num:.{decimals}f}"
    if fmt.get("currency"):
        symbol = fmt.get("currency_symbol") or "\u20b9"
        text = f"{symbol}{text}"
    return text


def flatten(obj, prefix=""):
    """Flatten nested dict/list into {path_string: scalar_value}."""
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = obj
    return out


def build_manifest(dsl_src: str, tool_results: List[Any]) -> List[dict]:
    """
    Returns a list of {path, tool_index, field_path, value} — one entry
    per literal we could confidently match to exactly one source field.
    """
    env, order, root_name = parse_program(dsl_src)
    literals = list(walk_literals_env(env[root_name], env, path=(root_name,)))

    flattened_per_tool = [flatten(r) for r in tool_results]
    used = set()
    manifest = []

    for path, lit in literals:
        if lit.kind not in ("string", "number"):
            continue
        target = lit.value
        fmt = _infer_format(target) if lit.kind == "string" else None
        target_num = _clean_numeric(target)

        candidates = []
        for t_idx, flat in enumerate(flattened_per_tool):
            for field_path, val in flat.items():
                if (t_idx, field_path) in used:
                    continue
                # Rank 0 — exact match (existing behaviour, cheapest/safest).
                if val == target or str(val) == str(target):
                    candidates.append((t_idx, field_path, 0))
                    continue
                # Rank 1 — tolerant numeric match: same number once currency
                # symbols/commas are stripped and both sides are rounded to
                # the precision the DSL literal actually displays. This is
                # what lets a KPI like "185564" match a raw 185563.98, or
                # "₹1,232" match a raw 1232.0.
                if target_num is not None:
                    val_num = _clean_numeric(val)
                    if val_num is not None:
                        decimals = fmt.get("decimals", 0) if fmt else 0
                        if round(val_num, decimals) == round(target_num, decimals):
                            candidates.append((t_idx, field_path, 1))
        if candidates:
            candidates.sort(key=lambda c: c[2])  # prefer exact over tolerant
            t_idx, field_path, _rank = candidates[0]
            used.add((t_idx, field_path))
            manifest.append({
                "path": path,
                "tool_index": t_idx,
                "field_path": field_path,
                "value": target,
                "format": fmt,
            })
    return manifest


def resolve_path(obj, field_path: str):
    """Resolve a 'a.b[3].c' style path against a parsed JSON structure."""
    cur = obj
    for part in re.findall(r"([^.\[\]]+)|\[(\d+)\]", field_path):
        key, idx = part
        if key:
            if not isinstance(cur, dict) or key not in cur:
                return None
            cur = cur[key]
        else:
            i = int(idx)
            if not isinstance(cur, list) or i >= len(cur):
                return None
            cur = cur[i]
    return cur