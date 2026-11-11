"""Minimal YAML-subset parser for OpenAPI documents.

Supports what typical OpenAPI specs actually use:
- block mappings and sequences by indentation
- ``- key: value`` map items inside sequences
- plain, single-quoted and double-quoted scalars
- flow mappings ``{a: b}`` and flow sequences ``[a, b]``
- block scalars ``|`` (literal) and ``>`` (folded)
- numbers, booleans, null, ``---`` / ``...`` document markers
- ``#`` comments (outside quotes)

Deliberately NOT supported (raises UnsupportedYAML with a clear message):
anchors/aliases (``&x`` / ``*x``), tags (``!!str``), multi-document streams,
complex keys, merge keys. If a real-world spec needs them, use a full YAML
library -- this parser exists so ContractGuard works with zero dependencies.
"""

from __future__ import annotations


class YAMLParseError(ValueError):
    """Raised when the input is not parseable YAML (even in the subset)."""


class UnsupportedYAML(YAMLParseError):
    """Raised when the input uses YAML features this subset parser rejects."""


def _strip_comment(line: str) -> str:
    """Remove a ``#`` comment that is outside any quoted scalar."""
    in_single = False
    in_double = False
    i = 0
    while i < len(line):
        ch = line[i]
        if in_single:
            if ch == "'":
                if i + 1 < len(line) and line[i + 1] == "'":
                    i += 2
                    continue
                in_single = False
        elif in_double:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_double = False
        else:
            if ch == "'":
                in_single = True
            elif ch == '"':
                in_double = True
            elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
                return line[:i].rstrip()
        i += 1
    return line.rstrip()


def _split_flow(text: str, sep: str) -> list[str]:
    """Split a flow collection body on `sep` at the top level only."""
    parts: list[str] = []
    depth = 0
    in_single = False
    in_double = False
    cur: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if in_single:
            cur.append(ch)
            if ch == "'":
                if i + 1 < len(text) and text[i + 1] == "'":
                    cur.append(text[i + 1])
                    i += 2
                    continue
                in_single = False
        elif in_double:
            cur.append(ch)
            if ch == "\\":
                if i + 1 < len(text):
                    cur.append(text[i + 1])
                    i += 2
                    continue
            elif ch == '"':
                in_double = False
        else:
            if ch == "'":
                in_single = True
                cur.append(ch)
            elif ch == '"':
                in_double = True
                cur.append(ch)
            elif ch in "[{":
                depth += 1
                cur.append(ch)
            elif ch in "]}":
                depth -= 1
                cur.append(ch)
            elif ch == sep and depth == 0:
                parts.append("".join(cur))
                cur = []
            else:
                cur.append(ch)
        i += 1
    parts.append("".join(cur))
    return parts


def _parse_scalar(text: str):
    """Parse a plain / quoted / flow scalar into a Python value."""
    text = text.strip()
    if text == "" or text == "~" or text.lower() == "null":
        return None
    if text.startswith("{") and text.endswith("}"):
        body = text[1:-1].strip()
        result: dict = {}
        if body:
            for part in _split_flow(body, ","):
                if ":" not in part:
                    raise YAMLParseError(f"bad flow mapping entry: {part!r}")
                key, _, value = part.partition(":")
                result[_parse_scalar(key)] = _parse_scalar(value)
        return result
    if text.startswith("[") and text.endswith("]"):
        body = text[1:-1].strip()
        if not body:
            return []
        return [_parse_scalar(p) for p in _split_flow(body, ",")]
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        return text[1:-1].replace("''", "'")
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        body = text[1:-1]
        out: list[str] = []
        i = 0
        while i < len(body):
            if body[i] == "\\" and i + 1 < len(body):
                nxt = body[i + 1]
                out.append({"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}.get(nxt, nxt))
                i += 2
            else:
                out.append(body[i])
                i += 1
        return "".join(out)
    low = text.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    if text.startswith(("&", "*", "!", "%")):
        raise UnsupportedYAML(
            f"anchors, aliases and tags are not supported by this parser: {text!r}"
        )
    return text


def _split_key_value(text: str):
    """Split ``key: value`` at the first top-level colon.

    Returns (key, value_text_or_None, had_colon). A bare ``key:`` returns
    value None; ``key: value`` returns the value text.
    """
    in_single = False
    in_double = False
    depth = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if in_single:
            if ch == "'":
                in_single = False
        elif in_double:
            if ch == "\\":
                i += 1
            elif ch == '"':
                in_double = False
        else:
            if ch == "'":
                in_single = True
            elif ch == '"':
                in_double = True
            elif ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
            elif ch == ":" and depth == 0:
                if i + 1 == len(text) or text[i + 1] in " \t":
                    key = text[:i].strip()
                    value = text[i + 1 :].strip()
                    return key, (value if value else None), True
        i += 1
    return text.strip(), None, False


class _Line:
    __slots__ = ("indent", "text", "number")

    def __init__(self, indent: int, text: str, number: int):
        self.indent = indent
        self.text = text
        self.number = number


def _prepare_lines(source: str) -> list[_Line]:
    raw_lines = source.splitlines()
    lines: list[_Line] = []
    for idx, raw in enumerate(raw_lines, start=1):
        if raw.strip() in ("", "---", "..."):
            continue
        stripped = _strip_comment(raw)
        if not stripped.strip():
            continue
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise YAMLParseError(f"line {idx}: tabs are not allowed for indentation")
        indent = len(raw) - len(raw.lstrip(" "))
        lines.append(_Line(indent, stripped.strip(), idx))
    return lines


class _Parser:
    def __init__(self, lines: list[_Line]):
        self.lines = lines
        self.pos = 0

    def parse(self):
        if not self.lines:
            return None
        value = self._parse_block(self.lines[0].indent)
        if self.pos < len(self.lines):
            line = self.lines[self.pos]
            raise YAMLParseError(
                f"line {line.number}: unexpected content {line.text!r}"
            )
        return value

    def _peek(self) -> _Line | None:
        return self.lines[self.pos] if self.pos < len(self.lines) else None

    def _parse_block(self, indent: int):
        line = self._peek()
        if line is None or line.indent < indent:
            return None
        if line.text.startswith("- ") or line.text == "-":
            return self._parse_sequence(indent)
        if line.indent == indent:
            key, _, had_colon = _split_key_value(line.text)
            if had_colon:
                return self._parse_mapping(indent)
        # A lone scalar (e.g. a document that is just a string, or a value
        # on its own line). Only valid at top level or as a sequence item.
        self.pos += 1
        return _parse_scalar(line.text)

    def _parse_mapping(self, indent: int) -> dict:
        result: dict = {}
        while True:
            line = self._peek()
            if line is None or line.indent != indent:
                return result
            if line.text.startswith("- ") or line.text == "-":
                return result
            key, value, had_colon = _split_key_value(line.text)
            if not had_colon:
                raise YAMLParseError(
                    f"line {line.number}: expected 'key: value', got {line.text!r}"
                )
            key = _parse_scalar(key)
            if isinstance(key, (dict, list)):
                raise YAMLParseError(f"line {line.number}: complex keys are not supported")
            self.pos += 1
            if value is not None:
                if value in ("|", ">", "|-", ">-", "|+", ">+"):
                    result[key] = self._parse_block_scalar(indent, value)
                elif value.startswith(("&", "*", "!")):
                    raise UnsupportedYAML(
                        f"line {line.number}: anchors, aliases and tags are not supported: {value!r}"
                    )
                else:
                    result[key] = _parse_scalar(value)
                continue
            # Nested block on following lines.
            nxt = self._peek()
            if nxt is None or nxt.indent <= indent:
                result[key] = None
            else:
                result[key] = self._parse_block(nxt.indent)
        return result

    def _parse_sequence(self, indent: int) -> list:
        result: list = []
        while True:
            line = self._peek()
            if line is None or line.indent != indent:
                return result
            if not (line.text.startswith("- ") or line.text == "-"):
                return result
            item_text = line.text[1:].strip()
            self.pos += 1
            if item_text == "":
                nxt = self._peek()
                if nxt is None or nxt.indent <= indent:
                    result.append(None)
                else:
                    result.append(self._parse_block(nxt.indent))
                continue
            # Inline content after "- ". It may start a mapping whose
            # remaining keys sit on lines indented relative to the dash.
            dash_col = line.indent
            key, value, had_colon = _split_key_value(item_text)
            if had_colon:
                item: dict = {}
                key = _parse_scalar(key)
                if value is None:
                    nxt = self._peek()
                    if nxt is not None and nxt.indent > dash_col:
                        item[key] = self._parse_block(nxt.indent)
                    else:
                        item[key] = None
                else:
                    item[key] = _parse_scalar(value)
                # Continuation keys of this map item: indented deeper
                # than the dash (YAML allows them at dash indent + 2).
                while True:
                    nxt = self._peek()
                    if nxt is None or nxt.indent <= dash_col:
                        break
                    if nxt.text.startswith("- ") or nxt.text == "-":
                        break
                    k2, v2, had2 = _split_key_value(nxt.text)
                    if not had2:
                        break
                    self.pos += 1
                    k2 = _parse_scalar(k2)
                    if v2 is None:
                        nxt2 = self._peek()
                        if nxt2 is not None and nxt2.indent > nxt.indent:
                            item[k2] = self._parse_block(nxt2.indent)
                        else:
                            item[k2] = None
                    else:
                        item[k2] = _parse_scalar(v2)
                result.append(item)
            else:
                result.append(_parse_scalar(item_text))
        return result

    def _parse_block_scalar(self, parent_indent: int, style: str) -> str:
        folded = style.startswith(">")
        keep = style.endswith("+")
        strip = style.endswith("-")
        chunks: list[str] = []
        block_indent: int | None = None
        while True:
            line = self._peek()
            if line is None or line.indent <= parent_indent:
                break
            if block_indent is None:
                block_indent = line.indent
            if line.indent < block_indent:
                break
            self.pos += 1
            chunks.append(" " * (line.indent - block_indent) + line.text)
        if folded:
            text = " ".join(c.strip() for c in chunks)
        else:
            text = "\n".join(chunks)
        if not strip:
            text += "\n"
        if keep:
            text += "\n"
        return text


def parse_yaml(source: str):
    """Parse a YAML document in the supported subset.

    Raises YAMLParseError / UnsupportedYAML with a line number and a clear
    message on anything outside the subset.
    """
    lines = _prepare_lines(source)
    return _Parser(lines).parse()
