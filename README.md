# Knife Launcher

A Linux launcher for [Soldat](https://www.soldat.pl/). Paste a `soldat://` link, join, edit your soldier, play demos, and run local practice with bots.

This repository is **only the launcher**. It does not include Soldat, maps, or your config.

**Coder:** [Grok](https://x.ai) (xAI)  
**Collaborator:** [Enzo](https://github.com/enz0afk)

---

## Requirements

- Soldat for Linux (`soldat_x64` / `soldatserver_x64`)
- Python 3
- GTK 3 and WebKitGTK

Debian / Ubuntu / Linux Mint:

```bash
sudo apt install python3 python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1
```

If `gir1.2-webkit2-4.1` is missing, try `gir1.2-webkit2-4.0`.

Fedora:

```bash
sudo dnf install python3 python3-gobject gtk3 webkit2gtk4.1
```

Arch / CachyOS / Endeavour:

```bash
sudo pacman -S python python-gobject gtk3 webkit2gtk-4.1
```

---

## Download

Ready-to-run AppImage (drop it next to `soldat_x64`):

**[Releases](https://github.com/enz0afk/knife-launcher/releases)** — `KnifeLauncher-2.0.AppImage`

```bash
chmod +x KnifeLauncher-2.0.AppImage
./KnifeLauncher-2.0.AppImage
```

## Run from source

```bash
git clone https://github.com/enz0afk/knife-launcher.git
```

Put this repo **next to** `soldat_x64` (clone it inside your Soldat folder):

```text
Soldat/
  soldat_x64
  soldatserver_x64
  knife-launcher/
    launch
    launcher/
```

Then:

```bash
cd /path/to/Soldat
chmod +x knife-launcher/launch
./knife-launcher/launch
```

Or copy `launch` and `launcher/` into the Soldat folder and run `./launch`.

Knife reads your existing `configs/client.cfg`. It does not wipe binds.

---

## Features

- Join by IP / port / password, or paste `soldat://host:port/pass`
- Lobby list (optional)
- Soldier: name, sensitivity, volume, colors, hair, headgear, chain, secondary, record demos
- Demo player (`demos/*.sdm`)
- Screenshot grid (`screens/`)
- Local dedicated server and Practice (map, Alpha/Bravo bots, difficulty)

Wayland (including KDE Plasma) is supported. You should not need to force X11.

---

## License

MIT. See [LICENSE](LICENSE).

Soldat itself is a separate game and is not included here.
