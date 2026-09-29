#!/usr/bin/env python3
"""Soldat Discord-style launcher. Serves UI, edits client.cfg, launches the game."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cfgutil import MANAGED, read_settings, upsert_settings

LAUNCHER_DIR = Path(__file__).resolve().parent
GAME_DIR = Path.cwd()
UI_DIR = LAUNCHER_DIR / "ui"
CLIENT_CFG = Path()
SERVER_CFG = Path()
MAPSLIST = Path()
CLIENT_BIN = Path()
SERVER_BIN = Path()
GOSTEK_DIR = Path()
GUNS_DIR = Path()
WEAPONS_DIR = Path()
MAP_DIRS: tuple[Path, ...] = ()
DEMOS_DIR = Path()
SCREENS_DIR = Path()
DEMO_PLAY_ALIAS = "play"
LOCAL_PORT = 23040
ICON_PNG = LAUNCHER_DIR / "ui" / "icon.png"
MAPSLIST_PRACTICE_BACKUP: str | None = None

# Official 1.7.1 dedicated server reads GAME_DIR/bots/*.bot (not configs/bots).
# Missing files make bots_random_* crash with "List index (0) out of bounds".
BOT_PROFILES = (
    ("Sniper", "Barrett M82A1", "$00464646", "$004B3532", 4, 1, 80),
    ("Dutch", "Ak-74", "$00C45C26", "$003C3C3C", 1, 1, 70),
    ("Commando", "Steyr AUG", "$002D5A27", "$001E1E1E", 0, 1, 60),
    ("Admiral", "Desert Eagles", "$001F4E79", "$00C9A227", 3, 2, 90),
    ("Danko", "FN Minimi", "$005C4033", "$002A2A2A", 2, 1, 75),
    ("Terminator", "Barrett M82A1", "$00464646", "$004B3532", 4, 1, 50),
    ("Kruger", "Ruger 77", "$006B4F3A", "$00323232", 1, 0, 85),
    ("Poncho", "Spas-12", "$008B6914", "$00442211", 3, 2, 95),
    ("Blain", "HK MP5", "$003D5C4A", "$00222222", 2, 1, 65),
    ("Billy", "M79", "$005A3A1A", "$002B1D12", 0, 0, 100),
    ("Roach", "XM214 Minigun", "$004A4A4A", "$00111111", 4, 1, 55),
    ("John", "Ak-74", "$00355C7A", "$00EEEEEE", 1, 1, 70),
    ("Stevie", "Steyr AUG", "$007A3A3A", "$00D0D0D0", 2, 0, 80),
    ("SgtMac", "FN Minimi", "$002F4F2F", "$001A1A1A", 0, 1, 60),
)


def find_game_dir() -> Path:
    candidates: list[Path] = []
    appimage = os.environ.get("APPIMAGE")
    if appimage:
        candidates.append(Path(appimage).resolve().parent)
    owd = os.environ.get("OWD")
    if owd:
        candidates.append(Path(owd).resolve())
    candidates.append(LAUNCHER_DIR.parent)
    candidates.append(LAUNCHER_DIR.parent.parent)
    candidates.append(Path.cwd())
    for cand in candidates:
        if (cand / "soldat_x64").is_file():
            return cand
    return Path.cwd()


def bind_paths(game_dir: Path | None = None) -> None:
    global GAME_DIR, UI_DIR, CLIENT_CFG, SERVER_CFG, MAPSLIST
    global CLIENT_BIN, SERVER_BIN, GOSTEK_DIR, GUNS_DIR, WEAPONS_DIR
    global MAP_DIRS, DEMOS_DIR, SCREENS_DIR, ICON_PNG
    GAME_DIR = (game_dir or find_game_dir()).resolve()
    for ui in (LAUNCHER_DIR / "ui", LAUNCHER_DIR):
        if (ui / "index.html").is_file():
            UI_DIR = ui
            break
    CLIENT_CFG = GAME_DIR / "configs" / "client.cfg"
    SERVER_CFG = GAME_DIR / "configs" / "server.cfg"
    MAPSLIST = GAME_DIR / "mapslist.txt"
    CLIENT_BIN = GAME_DIR / "soldat_x64"
    SERVER_BIN = GAME_DIR / "soldatserver_x64"
    GOSTEK_DIR = GAME_DIR / "soldat" / "gostek-gfx"
    GUNS_DIR = GAME_DIR / "soldat" / "interface-gfx" / "guns"
    WEAPONS_DIR = GAME_DIR / "soldat" / "weapons-gfx"
    MAP_DIRS = (
        GAME_DIR / "soldat" / "maps",
        GAME_DIR / "downloads" / "maps",
        GAME_DIR / "maps",
        GAME_DIR / "soldat" / "downloads" / "maps",
        GAME_DIR / "soldat" / "download" / "maps",
        GAME_DIR / "download" / "maps",
    )
    DEMOS_DIR = GAME_DIR / "demos"
    SCREENS_DIR = GAME_DIR / "screens"
    ICON_PNG = UI_DIR / "icon.png"


bind_paths()

LOBBY_URL = "http://api.soldat.pl/v0/servers?version=1.7.1"
SERVER_INFO_URL = "http://api.soldat.pl/v0/server/{ip}/{port}"

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}

GUN_FILES = {
    "ussocom": WEAPONS_DIR / "colt1911.png",
    "knife": GUNS_DIR / "knife.png",
    "chainsaw": GUNS_DIR / "chainsaw.png",
    "law": GUNS_DIR / "law.png",
}

_lock = threading.Lock()
_client_proc: subprocess.Popen | None = None
_server_proc: subprocess.Popen | None = None
_server_log: list[str] = []


def json_bytes(payload: object, status: int = 200) -> tuple[int, bytes, str]:
    return status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8"


def clamp_settings(data: dict) -> dict:
    out = {}
    for name in MANAGED:
        if name not in data:
            continue
        value = data[name]
        if name == "cl_player_name":
            text = str(value).strip()[:24] or "Major"
            out[name] = text
        elif name == "snd_volume":
            out[name] = max(0, min(100, int(round(float(value)))))
        elif name == "cl_sensitivity":
            out[name] = max(0.0, min(1.0, round(float(value), 2)))
        elif name == "cl_player_hairstyle":
            out[name] = max(0, min(4, int(value)))
        elif name == "cl_player_headstyle":
            out[name] = int(value) if int(value) in (0, 34, 124) else 0
        elif name == "cl_player_chainstyle":
            out[name] = max(0, min(2, int(value)))
        elif name == "cl_player_secwep":
            out[name] = max(0, min(3, int(value)))
        elif name == "cl_autorecord":
            out[name] = 1 if str(value).lower() in ("1", "true", "on", "yes") or value is True else 0
        elif name.startswith("cl_player_") and name.endswith(
            ("skin", "shirt", "pants", "hair", "jet")
        ):
            out[name] = str(value)
        else:
            out[name] = value
    return out


def load_settings() -> dict:
    if not CLIENT_CFG.exists():
        from cfgutil import DEFAULTS

        return dict(DEFAULTS)
    return read_settings(CLIENT_CFG.read_text(encoding="utf-8", errors="replace"))


def save_settings(updates: dict) -> dict:
    updates = clamp_settings(updates)
    if not CLIENT_CFG.exists():
        CLIENT_CFG.parent.mkdir(parents=True, exist_ok=True)
        CLIENT_CFG.write_text("", encoding="utf-8")
    original = CLIENT_CFG.read_text(encoding="utf-8", errors="replace")
    written = upsert_settings(original, updates)
    CLIENT_CFG.write_text(written, encoding="utf-8")
    return read_settings(written)


SKIP_MAPS = frozenset({"lobby"})
MAP_SUFFIXES = {".pms", ".smap"}


def is_playable_map(name: str) -> bool:
    stem = Path(str(name).strip()).stem
    return bool(stem) and stem.lower() not in SKIP_MAPS


def list_smod_maps() -> set[str]:
    smod = GAME_DIR / "soldat.smod"
    names: set[str] = set()
    if not smod.is_file():
        return names
    try:
        with zipfile.ZipFile(smod) as archive:
            for info in archive.infolist():
                path = Path(info.filename.replace("\\", "/"))
                if path.suffix.lower() != ".pms":
                    continue
                if is_playable_map(path.stem):
                    names.add(path.stem)
    except (zipfile.BadZipFile, OSError):
        pass
    return names


def list_available_maps() -> list[str]:
    names: set[str] = set()
    for folder in MAP_DIRS:
        if not folder.is_dir():
            continue
        for path in folder.iterdir():
            if path.suffix.lower() in MAP_SUFFIXES and is_playable_map(path.stem):
                names.add(path.stem)
    names.update(list_smod_maps())
    return sorted(names, key=str.lower)


def read_mapslist() -> list[str]:
    if not MAPSLIST.exists():
        return []
    maps = []
    for line in MAPSLIST.read_text(encoding="utf-8", errors="replace").splitlines():
        name = line.strip()
        if name and not name.startswith("//"):
            maps.append(name)
    return maps


def write_mapslist(maps: list[str]) -> None:
    body = "\n".join(maps) + ("\n" if maps else "")
    MAPSLIST.write_text(body, encoding="utf-8")


def fetch_json(url: str, timeout: float = 6.0) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": "SoldatLauncher/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def fetch_gamestat(ip: str, port: int, timeout: float = 2.0) -> dict | None:
    try:
        sock = socket.create_connection((ip, int(port) + 10), timeout=timeout)
    except OSError:
        return None
    try:
        sock.settimeout(timeout)
        sock.sendall(b"STARTFILES\r\nlogs/gamestat.txt\r\nENDFILES\r\n")
        chunks: list[bytes] = []
        while True:
            try:
                piece = sock.recv(4096)
            except OSError:
                break
            if not piece:
                break
            chunks.append(piece)
            if b"In-Game" in b"".join(chunks) and len(b"".join(chunks)) > 80:
                # keep reading a bit more
                sock.settimeout(0.4)
        text = b"".join(chunks).decode("utf-8", errors="replace")
    finally:
        try:
            sock.close()
        except OSError:
            pass
    if "In-Game" not in text and "Players" not in text:
        return None
    try:
        start = text.find("Players")
        if start < 0:
            start = 0
        lines = [ln.strip("\r") for ln in text[start:].split("\n")]
        # Players: N
        players_num = lines[0].split(": ", 1)[1].strip() if ": " in lines[0] else "0"
        current_map = lines[1].split(": ", 1)[1].strip() if len(lines) > 1 and ": " in lines[1] else ""
        game_mode = lines[2].split(": ", 1)[1].strip() if len(lines) > 2 and ": " in lines[2] else ""
        timeleft = lines[3].split(": ", 1)[1].strip() if len(lines) > 3 and ": " in lines[3] else ""
        team_modes = {
            "Capture the Flag",
            "Infiltration",
            "Hold the Flag",
            "Teammatch",
        }
        index = 4
        scores: list[str] = []
        if game_mode in team_modes:
            for _ in range(4):
                if index >= len(lines):
                    break
                if lines[index].startswith("Team") and ": " in lines[index]:
                    scores.append(lines[index].split(": ", 1)[1].strip())
                    index += 1
                else:
                    break
        # Player records start right after the "Players list: (...)" header
        header = next(
            (i for i in range(index, len(lines)) if lines[i].startswith("Players list")),
            None,
        )
        if header is not None:
            index = header + 1
        players = []
        count = int(players_num or 0)
        for _ in range(count):
            if index + 4 >= len(lines):
                break
            players.append(
                {
                    "name": lines[index].strip(),
                    "kills": lines[index + 1].strip(),
                    "deaths": lines[index + 2].strip(),
                    "team": lines[index + 3].strip(),
                    "ping": lines[index + 4].strip(),
                }
            )
            index += 5
        return {
            "players_num": players_num,
            "map": current_map,
            "game_mode": game_mode,
            "timeleft": timeleft,
            "scores": scores,
            "players": players,
        }
    except (IndexError, ValueError):
        return None


def _append_log(stream, prefix: str = "") -> None:
    try:
        for line in iter(stream.readline, ""):
            if not line:
                break
            with _lock:
                _server_log.append(line.rstrip("\n"))
                if len(_server_log) > 400:
                    del _server_log[: len(_server_log) - 400]
    except Exception:
        pass


def kill_proc(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    if proc.poll() is not None:
        return
    try:
        proc.kill()
        proc.wait(timeout=2)
    except Exception:
        pass


def list_demos() -> list[dict]:
    DEMOS_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for path in DEMOS_DIR.iterdir():
        if not path.is_file() or path.suffix.lower() != ".sdm":
            continue
        if path.stem.lower() == DEMO_PLAY_ALIAS:
            continue
        stat = path.stat()
        items.append(
            {
                "file": path.name,
                "name": path.stem,
                "size": stat.st_size,
                "mtime": int(stat.st_mtime),
            }
        )
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items


def demo_path(name: str) -> Path:
    raw = str(name or "").strip()
    if not raw:
        raise ValueError("missing demo name")
    base = Path(raw).name
    if base.lower().endswith(".sdm"):
        stem = base[:-4]
        filename = base
    else:
        stem = base
        filename = base + ".sdm"
    if not stem or stem in (".", "..") or "/" in stem or "\\" in stem:
        raise ValueError("invalid demo name")
    path = (DEMOS_DIR / filename).resolve()
    if DEMOS_DIR.resolve() not in path.parents:
        raise ValueError("invalid demo path")
    if not path.is_file():
        raise FileNotFoundError(f"demo not found: {filename}")
    return path


def parse_soldat_url(text: str) -> dict | None:
    raw = str(text or "").strip()
    match = re.search(
        r"soldat://([^:/\s]+)(?::(\d+))?(?:/([^\s]*))?",
        raw,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    ip = match.group(1).strip()
    port = (match.group(2) or "23073").strip()
    password = (match.group(3) or "").strip()
    if not ip:
        return None
    return {"ip": ip, "port": port or "23073", "password": password}


def spawn_game(args: list[str]) -> None:
    global _client_proc
    if not CLIENT_BIN.exists():
        raise FileNotFoundError(f"missing {CLIENT_BIN}")
    print("[launcher] spawn:", args, flush=True)
    with _lock:
        kill_proc(_client_proc)
        _client_proc = subprocess.Popen(
            args,
            cwd=str(GAME_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


def spawn_demo(name: str) -> None:
    path = demo_path(name)
    # Linux Soldat only plays demos via:
    #   soldat_x64 -joinurl soldat://name:0
    # and `name` cannot contain _, - or digits. Copy to play.sdm first.
    alias = DEMOS_DIR / f"{DEMO_PLAY_ALIAS}.sdm"
    if alias.exists() or alias.is_symlink():
        alias.unlink()
    shutil.copy2(path, alias)
    spawn_game([str(CLIENT_BIN), f"-joinurl soldat://{DEMO_PLAY_ALIAS}:0"])


def spawn_client(
    ip: str, port: str | int, password: str = "", team: int | None = None
) -> None:
    parsed = parse_soldat_url(ip)
    if parsed:
        ip = parsed["ip"]
        port = parsed["port"]
        password = parsed["password"] or password
    ip = str(ip).strip()
    port = str(port).strip() or "23073"
    password = str(password or "").strip()
    extra: list[str] = []
    if team in (1, 2, 3, 4):
        extra += ["-cl_player_team", str(team)]
    if port == "0":
        spawn_game([str(CLIENT_BIN), *extra, f'-join "{ip}" 0'])
        return
    url = f"soldat://{ip}:{port}"
    if password:
        url += f"/{password}"
    spawn_game([str(CLIENT_BIN), *extra, f"-joinurl {url}"])


def list_screens() -> list[dict]:
    SCREENS_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for path in SCREENS_DIR.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".png", ".bmp", ".jpg", ".jpeg"}:
            continue
        stat = path.stat()
        items.append(
            {
                "file": path.name,
                "size": stat.st_size,
                "mtime": int(stat.st_mtime),
            }
        )
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items


def screen_path(name: str) -> Path:
    base = Path(str(name or "")).name
    if not base or base in (".", ".."):
        raise ValueError("invalid screenshot")
    path = (SCREENS_DIR / base).resolve()
    if SCREENS_DIR.resolve() not in path.parents:
        raise ValueError("invalid screenshot path")
    if not path.is_file():
        raise FileNotFoundError(base)
    return path


def upsert_server_cvars(updates: dict[str, str]) -> None:
    SERVER_CFG.parent.mkdir(parents=True, exist_ok=True)
    text = SERVER_CFG.read_text(encoding="utf-8", errors="replace") if SERVER_CFG.exists() else ""
    lines = text.splitlines()
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        name = ""
        if stripped and not stripped.startswith("//") and not stripped.startswith("#"):
            name = stripped.split()[0]
        if name in updates:
            out.append(f"{name} {updates[name]}")
            seen.add(name)
        else:
            out.append(line)
    for name, value in updates.items():
        if name not in seen:
            out.append(f"{name} {value}")
    SERVER_CFG.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")


def ensure_loose_map(map_name: str) -> None:
    """Copy a smod map to soldat/maps so the client does not need the fileserver."""
    stem = Path(map_name).name
    if stem.lower().endswith(".pms") or stem.lower().endswith(".smap"):
        stem = Path(stem).stem
    if not stem:
        return
    for folder in MAP_DIRS:
        if not folder.is_dir():
            continue
        for suffix in (".pms", ".smap"):
            if (folder / f"{stem}{suffix}").is_file():
                return
    smod = GAME_DIR / "soldat.smod"
    if not smod.is_file():
        return
    dest_dir = GAME_DIR / "soldat" / "maps"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{stem}.pms"
    try:
        with zipfile.ZipFile(smod) as archive:
            for info in archive.infolist():
                path = Path(info.filename.replace("\\", "/"))
                if path.suffix.lower() == ".pms" and path.stem == stem:
                    dest.write_bytes(archive.read(info))
                    return
    except (zipfile.BadZipFile, OSError):
        pass


def gamemode_for_map(name: str) -> int | None:
    stem = Path(name).stem.lower()
    if stem.startswith("ctf_"):
        return 3
    if stem.startswith("inf_"):
        return 5
    if stem.startswith("htf_"):
        return 6
    if stem.startswith("tm_"):
        return 2
    return None


def ensure_bot_files() -> None:
    folder = GAME_DIR / "bots"
    folder.mkdir(parents=True, exist_ok=True)
    for name, weapon, shirt, pants, hair, head, acc in BOT_PROFILES:
        path = folder / f"{name}.bot"
        if path.exists():
            continue
        path.write_text(
            "\n".join(
                [
                    "[BOT]",
                    f"Name={name}",
                    f"Color1={shirt}",
                    f"Color2={pants}",
                    "Skin_Color=$00A8CAA8",
                    "Hair_Color=$00010101",
                    f"Favourite_Weapon={weapon}",
                    "Secondary_Weapon=1",
                    "Friend=",
                    f"Accuracy={acc}",
                    "Shoot_Dead=0",
                    "Grenade_Frequency=180",
                    "Camping=0",
                    "OnStartUse=255",
                    f"Hair={hair}",
                    f"Headgear={head}",
                    "Chain=0",
                    "Chat_Frequency=3",
                    "Chat_Kill=",
                    "Chat_Dead=",
                    "Chat_LowHealth=",
                    "Chat_SeeEnemy=",
                    "Chat_Winning=",
                    "",
                ]
            ),
            encoding="utf-8",
        )


def server_log_text(limit: int = 80) -> str:
    with _lock:
        return "\n".join(_server_log[-limit:])


def _proc_net_has_port(kind: str, port: int, listen_only: bool = False) -> bool:
    needle = f":{port:04X}"
    path = Path(f"/proc/net/{kind}")
    if not path.is_file():
        return False
    try:
        lines = path.read_text().splitlines()[1:]
    except OSError:
        return False
    for line in lines:
        cols = line.split()
        if len(cols) < 4:
            continue
        if not cols[1].upper().endswith(needle):
            continue
        if listen_only and cols[3] != "0A":
            continue
        return True
    return False


def udp_port_bound(port: int) -> bool:
    return _proc_net_has_port("udp", port) or _proc_net_has_port("udp6", port)


def tcp_port_listening(port: int) -> bool:
    return _proc_net_has_port("tcp", port, True) or _proc_net_has_port("tcp6", port, True)


def wait_server_ready(port: int = LOCAL_PORT, timeout: float = 15.0) -> None:
    """Wait until game UDP + fileserver TCP are listening. Do not connect to them."""
    deadline = time.monotonic() + timeout
    fileserver = port + 10
    while time.monotonic() < deadline:
        if not server_running():
            raise RuntimeError(
                "dedicated server exited before it was ready:\n" + server_log_text()
            )
        blob = server_log_text(200)
        if "Encountered an error" in blob:
            time.sleep(0.2)
            raise RuntimeError("dedicated server crashed:\n" + server_log_text())
        udp_ok = udp_port_bound(port)
        fs_ok = tcp_port_listening(fileserver) or (
            "Connection for file server started" in blob
        )
        if udp_ok and fs_ok:
            time.sleep(1.0)
            if not server_running():
                raise RuntimeError(
                    "dedicated server crashed after bind:\n" + server_log_text()
                )
            return
        time.sleep(0.1)
    raise RuntimeError("dedicated server did not become ready:\n" + server_log_text())


def backup_mapslist(map_name: str) -> None:
    global MAPSLIST_PRACTICE_BACKUP
    if MAPSLIST_PRACTICE_BACKUP is None:
        MAPSLIST_PRACTICE_BACKUP = (
            MAPSLIST.read_text(encoding="utf-8", errors="replace")
            if MAPSLIST.exists()
            else ""
        )
    MAPSLIST.write_text(f"{map_name}\n", encoding="utf-8")


def restore_mapslist() -> None:
    global MAPSLIST_PRACTICE_BACKUP
    if MAPSLIST_PRACTICE_BACKUP is None:
        return
    MAPSLIST.write_text(MAPSLIST_PRACTICE_BACKUP, encoding="utf-8")
    MAPSLIST_PRACTICE_BACKUP = None


def spawn_server(practice: dict | None = None) -> None:
    global _server_proc
    if not SERVER_BIN.exists():
        raise FileNotFoundError(f"missing {SERVER_BIN}")
    args = [str(SERVER_BIN), "-net_port", str(LOCAL_PORT), "-log_level", "1"]
    if practice:
        shared = practice.get("bots")
        alpha = max(0, min(8, int(practice.get("bots_alpha", shared if shared is not None else 0) or 0)))
        bravo = max(0, min(8, int(practice.get("bots_bravo", shared if shared is not None else 0) or 0)))
        difficulty = int(practice.get("difficulty") or 100)
        if difficulty not in (10, 50, 100, 200, 300):
            difficulty = 100
        args += [
            "-sv_botbalance",
            "0",
            "-sv_balanceteams",
            "0",
            "-sv_pure",
            "0",
            "-net_lan",
            "1",
        ]
        map_name = str(practice.get("map") or "").strip()
        mode = gamemode_for_map(map_name) if map_name else None
        upsert_server_cvars(
            {
                "sv_pure": "0",
                "sv_botbalance": "0",
                "sv_balanceteams": "0",
                "sv_lobby": "0",
            }
        )
        if map_name:
            backup_mapslist(Path(map_name).name)
            ensure_loose_map(map_name)
            if mode is not None:
                args += ["-sv_gamemode", str(mode)]
        if alpha or bravo:
            ensure_bot_files()
            args += ["-bots_difficulty", str(difficulty)]
            if mode in (2, 3, 5, 6):
                args += [
                    "-bots_random_alpha",
                    str(alpha),
                    "-bots_random_bravo",
                    str(bravo),
                ]
            else:
                args += ["-bots_random_noteam", str(alpha + bravo)]
    else:
        restore_mapslist()
    with _lock:
        kill_proc(_server_proc)
        _server_log.clear()
        (GAME_DIR / "banned.txt").touch(exist_ok=True)
        (GAME_DIR / "bannedhw.txt").touch(exist_ok=True)
        print("[launcher] server:", args, flush=True)
        _server_proc = subprocess.Popen(
            args,
            cwd=str(GAME_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        threading.Thread(
            target=_append_log, args=(_server_proc.stdout,), daemon=True
        ).start()


def stop_server() -> None:
    global _server_proc
    with _lock:
        kill_proc(_server_proc)
        _server_proc = None
    restore_mapslist()


def client_running() -> bool:
    with _lock:
        return _client_proc is not None and _client_proc.poll() is None


def server_running() -> bool:
    with _lock:
        if _server_proc is None:
            return False
        if _server_proc.poll() is not None:
            return False
        return True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[launcher] " + (fmt % args) + "\n")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        if not raw:
            return {}
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("expected object")
        return data

    def do_GET(self) -> None:
        try:
            self._do_GET()
        except Exception:
            traceback.print_exc()
            self._send(*json_bytes({"error": "internal error"}, 500))

    def do_PUT(self) -> None:
        self.do_POST()

    def do_POST(self) -> None:
        try:
            self._do_POST()
        except Exception as exc:
            traceback.print_exc()
            self._send(*json_bytes({"error": str(exc)}, 500))

    def _do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self._send_file(UI_DIR / "index.html")
            return
        if path.startswith("/ui/"):
            self._send_file(UI_DIR / path[len("/ui/") :])
            return
        if path.startswith("/assets/gostek/"):
            self._send_file(GOSTEK_DIR / path.split("/")[-1])
            return
        if path.startswith("/assets/guns/"):
            key = path.split("/")[-1].rsplit(".", 1)[0]
            target = GUN_FILES.get(key)
            if target:
                self._send_file(target)
                return
            self._send(*json_bytes({"error": "not found"}, 404))
            return
        if path.startswith("/assets/screens/"):
            try:
                self._send_file(screen_path(path.split("/")[-1]))
            except (ValueError, FileNotFoundError):
                self._send(*json_bytes({"error": "not found"}, 404))
            return

        if path == "/api/settings":
            self._send(*json_bytes(load_settings()))
            return
        if path == "/api/servers":
            try:
                data = fetch_json(LOBBY_URL)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                self._send(*json_bytes({"error": str(exc), "Servers": []}, 502))
                return
            self._send(*json_bytes(data))
            return
        if path == "/api/server":
            ip = (query.get("ip") or [""])[0]
            port = (query.get("port") or [""])[0]
            info = None
            try:
                info = fetch_json(SERVER_INFO_URL.format(ip=ip, port=port))
            except Exception:
                info = None
            live = fetch_gamestat(ip, int(port or 0) or 23073)
            self._send(*json_bytes({"info": info, "live": live}))
            return
        if path == "/api/maps":
            self._send(
                *json_bytes(
                    {"selected": read_mapslist(), "available": list_available_maps()}
                )
            )
            return
        if path == "/api/demos":
            self._send(*json_bytes({"demos": list_demos()}))
            return
        if path == "/api/screens":
            self._send(*json_bytes({"screens": list_screens()}))
            return
        if path == "/api/local/status":
            with _lock:
                log = "\n".join(_server_log[-200:])
            self._send(
                *json_bytes(
                    {
                        "server": server_running(),
                        "client": client_running(),
                        "log": log,
                    }
                )
            )
            return
        if path == "/api/status":
            self._send(
                *json_bytes({"client": client_running(), "server": server_running()})
            )
            return

        # static from ui/
        candidate = UI_DIR / path.lstrip("/")
        if candidate.is_file():
            self._send_file(candidate)
            return
        self._send(*json_bytes({"error": "not found"}, 404))

    def _do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/settings":
            body = self._read_json()
            saved = save_settings(body)
            self._send(*json_bytes(saved))
            return
        if path == "/api/join":
            body = self._read_json()
            ip = str(body.get("ip") or "").strip() or "127.0.0.1"
            port = str(body.get("port") or "23073").strip()
            password = str(body.get("password") or "")
            spawn_client(ip, port, password)
            self._send(*json_bytes({"ok": True, "client": True}))
            return
        if path == "/api/client/stop":
            global _client_proc
            with _lock:
                kill_proc(_client_proc)
                _client_proc = None
            self._send(*json_bytes({"ok": True}))
            return
        if path == "/api/local/start":
            body = self._read_json()
            practice = body.get("practice") if isinstance(body.get("practice"), dict) else None
            try:
                spawn_server(practice)
                wait_server_ready(LOCAL_PORT)
            except Exception:
                stop_server()
                raise
            team = 1
            if practice:
                shared = practice.get("bots")
                alpha = int(practice.get("bots_alpha", shared if shared is not None else 0) or 0)
                bravo = int(practice.get("bots_bravo", shared if shared is not None else 0) or 0)
                if alpha and not bravo:
                    team = 2
                elif bravo and not alpha:
                    team = 1
            spawn_client("127.0.0.1", str(LOCAL_PORT), "", team=team)
            self._send(*json_bytes({"ok": True, "server": True, "client": True}))
            return
        if path == "/api/local/stop":
            stop_server()
            self._send(*json_bytes({"ok": True, "server": False}))
            return
        if path == "/api/maps":
            body = self._read_json()
            maps = [str(m).strip() for m in body.get("selected") or [] if str(m).strip()]
            write_mapslist(maps)
            self._send(*json_bytes({"selected": maps, "available": list_available_maps()}))
            return
        if path == "/api/demo/play":
            body = self._read_json()
            spawn_demo(str(body.get("name") or body.get("file") or ""))
            self._send(*json_bytes({"ok": True, "client": True}))
            return
        self._send(*json_bytes({"error": "not found"}, 404))

    def _send_file(self, path: Path) -> None:
        path = path.resolve()
        allowed = (
            UI_DIR.resolve(),
            GOSTEK_DIR.resolve(),
            GUNS_DIR.resolve(),
            WEAPONS_DIR.resolve(),
            SCREENS_DIR.resolve(),
        )
        if not any(path == root or root in path.parents for root in allowed):
            self._send(*json_bytes({"error": "forbidden"}, 403))
            return
        if not path.is_file():
            self._send(*json_bytes({"error": "not found"}, 404))
            return
        data = path.read_bytes()
        content_type = MIME.get(path.suffix.lower(), "application/octet-stream")
        self._send(200, data, content_type)


def prepare_display_env() -> None:
    """Keep native Wayland when available; only harden WebKit on NVIDIA."""
    wayland = bool(os.environ.get("WAYLAND_DISPLAY")) or os.environ.get(
        "XDG_SESSION_TYPE", ""
    ).lower() == "wayland"
    nvidia = Path("/proc/driver/nvidia/version").exists()
    if wayland and nvidia:
        os.environ.setdefault("WEBKIT_DISABLE_COMPOSITING_MODE", "1")
    os.environ.pop("GDK_BACKEND", None)


def load_gtk():
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("Gio", "2.0")
    webkit_error = None
    for version in ("4.1", "4.0"):
        try:
            gi.require_version("WebKit2", version)
            from gi.repository import Gtk, WebKit2, Gdk, Gio, GLib

            return Gtk, WebKit2, Gdk, Gio, GLib
        except (ValueError, ImportError) as exc:
            webkit_error = exc
    raise RuntimeError(f"WebKit2 GTK bindings not found: {webkit_error}")


def open_window(url: str) -> bool:
    prepare_display_env()
    try:
        Gtk, WebKit2, Gdk, Gio, GLib = load_gtk()
    except Exception as exc:
        print("WebKit window unavailable:", exc, file=sys.stderr)
        return False

    GLib.set_prgname("knifelauncher")
    try:
        Gdk.set_program_class("knifelauncher")
    except Exception:
        pass

    class LauncherApp(Gtk.Application):
        def __init__(self) -> None:
            super().__init__(
                application_id="pl.knife.Launcher",
                flags=Gio.ApplicationFlags.FLAGS_NONE,
            )
            self.win = None

        def do_activate(self):  # noqa: N802
            if self.win is not None:
                self.win.present()
                return
            self.win = Gtk.ApplicationWindow(application=self, title="Knife Launcher 1.1")
            self.win.set_default_size(1280, 720)
            if ICON_PNG.is_file():
                try:
                    self.win.set_icon_from_file(str(ICON_PNG))
                except Exception:
                    pass
            webview = WebKit2.WebView()
            settings = webview.get_settings()
            settings.set_enable_developer_extras(False)
            webview.load_uri(url)
            self.win.add(webview)
            self.win.connect("destroy", lambda *_: self.quit())
            self.win.show_all()
            self.win.present()

    app = LauncherApp()
    app.run(None)
    return True


def main() -> int:
    bind_paths()
    os.chdir(GAME_DIR)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"Soldat launcher at {url}", flush=True)
    print(f"Game dir {GAME_DIR}", flush=True)

    if not open_window(url):
        import webbrowser

        print(
            "Opening Knife Launcher in your web browser instead of its own window.\n"
            "For the app window, install WebKitGTK and PyGObject:\n"
            "  Debian/Ubuntu/Mint: sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1\n"
            "  Fedora:             sudo dnf install python3-gobject gtk3 webkit2gtk4.1\n"
            "  Arch:               sudo pacman -S python-gobject gtk3 webkit2gtk-4.1",
            file=sys.stderr,
            flush=True,
        )
        webbrowser.open(url)
        try:
            thread.join()
        except KeyboardInterrupt:
            pass
    server.shutdown()
    stop_server()
    with _lock:
        kill_proc(_client_proc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
