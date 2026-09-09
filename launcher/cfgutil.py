"""Read and write Soldat client.cfg without touching binds or comments."""

from __future__ import annotations

import re
from typing import Any

MANAGED = (
    "snd_volume",
    "cl_player_name",
    "cl_player_skin",
    "cl_player_shirt",
    "cl_player_pants",
    "cl_player_hair",
    "cl_player_jet",
    "cl_player_hairstyle",
    "cl_player_headstyle",
    "cl_player_chainstyle",
    "cl_player_secwep",
    "cl_sensitivity",
    "cl_autorecord",
)

STRING_CVARS = {"cl_player_name"}
COLOR_CVARS = {
    "cl_player_skin",
    "cl_player_shirt",
    "cl_player_pants",
    "cl_player_hair",
    "cl_player_jet",
}
INT_CVARS = {
    "snd_volume",
    "cl_player_hairstyle",
    "cl_player_headstyle",
    "cl_player_chainstyle",
    "cl_player_secwep",
    "cl_autorecord",
}
FLOAT_CVARS = {"cl_sensitivity"}

HEADSTYLE_NONE = 0
HEADSTYLE_HELMET = 34
HEADSTYLE_HAT = 124

DEFAULTS = {
    "snd_volume": 50,
    "cl_player_name": "Major",
    "cl_player_skin": "#8f8f8f",
    "cl_player_shirt": "#8f8f8f",
    "cl_player_pants": "#8f8f8f",
    "cl_player_hair": "#000000",
    "cl_player_jet": "#8f8f8f",
    "cl_player_hairstyle": 0,
    "cl_player_headstyle": 0,
    "cl_player_chainstyle": 0,
    "cl_player_secwep": 1,
    "cl_sensitivity": 0.37,
    "cl_autorecord": 0,
}

CVAR_RE = re.compile(r"^([A-Za-z0-9_]+)\s+(.*)$")


def strip_quotes(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        return raw[1:-1].replace('""', '"')
    return raw


def soldat_color_to_hex(value: str) -> str:
    value = strip_quotes(value).strip()
    if value.startswith("#") and len(value) == 7:
        return value.lower()
    if value.startswith("$"):
        digits = value[1:]
        if len(digits) == 8:
            return f"#{digits[2:]}".lower()
        if len(digits) == 6:
            return f"#{digits}".lower()
    return "#8f8f8f"


def hex_to_soldat_color(value: str) -> str:
    value = value.strip()
    if value.startswith("#"):
        value = value[1:]
    if len(value) == 8:
        value = value[2:]
    if len(value) != 6:
        value = "8f8f8f"
    return f"$00{value.upper()}"


def parse_cvar_value(name: str, raw: str) -> Any:
    text = strip_quotes(raw)
    if name in COLOR_CVARS:
        return soldat_color_to_hex(text)
    if name in INT_CVARS:
        try:
            return int(float(text))
        except ValueError:
            return DEFAULTS[name]
    if name in FLOAT_CVARS:
        try:
            return float(text)
        except ValueError:
            return DEFAULTS[name]
    return text


def format_cvar_value(name: str, value: Any, quoted: bool) -> str:
    if name in COLOR_CVARS:
        body = hex_to_soldat_color(str(value))
        return f'"{body}"'
    if name in STRING_CVARS:
        text = str(value).replace('"', "")
        return f'"{text}"'
    if name in FLOAT_CVARS:
        number = f"{float(value):.2f}".rstrip("0").rstrip(".")
        if "." not in number:
            number = f"{number}.0" if float(value) != int(float(value)) else number
        # keep two-decimal feel for sensitivity
        number = f"{float(value):.2f}"
        return f'"{number}"' if quoted else number
    if name in INT_CVARS:
        number = str(int(value))
        return f'"{number}"' if quoted else number
    text = str(value)
    return f'"{text}"' if quoted else text


def line_is_quoted(raw_value: str) -> bool:
    raw_value = raw_value.strip()
    return len(raw_value) >= 2 and raw_value[0] == '"' and raw_value[-1] == '"'


def read_settings(text: str) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("#"):
            continue
        match = CVAR_RE.match(stripped)
        if not match:
            continue
        name, raw = match.group(1), match.group(2)
        if name in MANAGED:
            found[name] = parse_cvar_value(name, raw)
    settings = dict(DEFAULTS)
    settings.update(found)
    return settings


def upsert_settings(text: str, updates: dict[str, Any]) -> str:
    """Replace managed cvars in place. Preserve every other line."""
    lines = text.splitlines(keepends=True)
    if text and not text.endswith("\n"):
        # keep original missing-final-newline behavior after rewrite
        pass

    seen: set[str] = set()
    out: list[str] = []
    last_player_idx = -1

    for line in lines:
        newline = ""
        body = line
        if line.endswith("\r\n"):
            newline = "\r\n"
            body = line[:-2]
        elif line.endswith("\n"):
            newline = "\n"
            body = line[:-1]

        stripped = body.strip()
        match = None
        if stripped and not stripped.startswith("//") and not stripped.startswith("#"):
            match = CVAR_RE.match(stripped)

        if match and match.group(1) in updates:
            name = match.group(1)
            quoted = line_is_quoted(match.group(2))
            value = format_cvar_value(name, updates[name], quoted)
            # preserve indentation
            indent = body[: len(body) - len(body.lstrip())] if body.lstrip() else ""
            out.append(f"{indent}{name} {value}{newline or chr(10)}")
            seen.add(name)
            if name.startswith("cl_player_"):
                last_player_idx = len(out) - 1
            continue

        if match and match.group(1).startswith("cl_player_"):
            out.append(line if line.endswith("\n") else line + "\n")
            last_player_idx = len(out) - 1
            continue

        out.append(line if (line.endswith("\n") or line.endswith("\r\n") or line == "") else line + "\n")

    missing = [name for name in MANAGED if name in updates and name not in seen]
    insert_at = last_player_idx + 1 if last_player_idx >= 0 else len(out)
    extra: list[str] = []
    for name in missing:
        quoted = name not in ("snd_volume",)
        extra.append(f"{name} {format_cvar_value(name, updates[name], quoted)}\n")
    if extra:
        out[insert_at:insert_at] = extra

    result = "".join(out)
    if text.endswith("\n") and not result.endswith("\n"):
        result += "\n"
    return result
