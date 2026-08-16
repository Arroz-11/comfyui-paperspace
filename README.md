# comfyui-paperspace

**ComfyUI on Paperspace Gradient, fully automated.** Create the machine, wait
for the first boot, open the link — ComfyUI is installed, configured and
running. No terminal, no manual setup.

Paperspace's Growth/Pro subscription includes free-tier GPUs (up to an A6000
48 GB) with persistent storage, which makes it one of the cheapest ways to run
ComfyUI in the cloud.

## Features

- **Self-installing**: every boot checks the machine and installs whatever is
  missing — ComfyUI, its venv, a curated set of custom nodes, system packages.
  First boot does everything; later boots just launch.
- **Curated custom nodes** ([config/nodes.txt](config/nodes.txt)): Manager,
  Impact, Inspire, WAS, rgthree, Easy-Use and more — edit the file to make it
  yours.
- **`Hub.ipynb`** — everything for the day to day, in one notebook:
  - **ComfyUI panel**: start / stop / restart, version checker, one-click update
  - **Model downloaders**: Civitai (paste any model page URL) and HuggingFace
    (browse a repo, pick files), with live progress and gated-repo access check
  - **Model presets**: complete model packs (diffusion + text encoder + VAE)
    with a bf16 / fp8 switch — downloads only what's missing
  - **Disk cleaner**: browse and delete safely, plus a storage overview of
    what's eating your quota
  - **Cloudflare R2** upload/download (optional)
- **Persistent**: models, outputs and settings live in `/notebooks` and survive
  shutdowns. Tokens are saved once and never leave the machine.

## Requirements

- A [Paperspace](https://www.paperspace.com/) account with a **Growth or Pro**
  subscription (for the free GPUs and the storage).

## Quick start

Create a Gradient notebook with **Advanced options**:

| Field | Value |
|---|---|
| Container | `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404` |
| Workspace | this repo's URL (`ref: main`) |
| Command | see below |

```
bash /notebooks/scripts/start.sh & PIP_DISABLE_PIP_VERSION_CHECK=1 jupyter lab --allow-root --ip=0.0.0.0 --no-browser --ServerApp.trust_xheaders=True --ServerApp.disable_check_xsrf=False --ServerApp.allow_remote_access=True --ServerApp.allow_origin='*' --ServerApp.allow_credentials=True
```

First boot installs everything (~15–20 min with all the custom nodes); boots
after that take ~2 min. ComfyUI ends up at `https://tensorboard-<your-notebook-fqdn>`
— the link is also shown in `Hub.ipynb`.

## Day to day

Open `Hub.ipynb` in Jupyter — the ComfyUI panel, downloaders, presets and
cleaner are all there. To watch what a boot is doing, open a terminal:

```bash
tail -f /notebooks/logs/boot.log      # boot progress
tail -f /notebooks/logs/comfyui.log   # ComfyUI's own log
```

`scripts/extras/fixes.sh` has on-demand fixes for known issues (run by hand,
each one documented inside).

## Tokens

Copy `config/keys.example.json` to `config/keys.json` and fill in what you use
(Civitai, HuggingFace, Cloudflare R2) — or just paste them in the save box each
downloader has in `Hub.ipynb`. The file lives only on your machine's persistent
storage: it is git-ignored and never leaves it.

## Layout

```
/notebooks              ← this repo, cloned by Paperspace (persistent)
├── ComfyUI/            ← installed by start.sh on first boot (git-ignored)
├── scripts/
│   ├── start.sh        ← runs on every boot: system deps → install if missing → launch
│   ├── hub.py          ← all the code behind Hub.ipynb
│   ├── update.sh       ← pull the latest version of this repo
│   └── extras/fixes.sh ← one-off fixes (run by hand)
├── config/
│   ├── nodes.txt       ← which custom nodes to install
│   ├── presets.json    ← model packs for the presets downloader
│   └── keys.json       ← your tokens (git-ignored)
├── Hub.ipynb           ← everyday utilities
└── logs/               ← boot.log + comfyui.log (fresh on every boot)
```

## Good to know

- Only `/notebooks` survives a shutdown — that's why system packages reinstall
  on every boot and ComfyUI doesn't.
- Free-tier machines auto-stop after 6 h and run one at a time.
- Port 6006 is mandatory: it's the only one Paperspace proxies (as
  "tensorboard"). Tunnels are against Paperspace ToS — don't.
- The ComfyUI URL changes on every machine start (new machine id) — reopen it
  from `Hub.ipynb`, don't bookmark it.
