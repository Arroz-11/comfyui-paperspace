# comfyui-paperspace

Run ComfyUI on a Paperspace Gradient notebook with **zero manual setup**: create
the machine and everything installs itself — the free-tier GPUs (up to an A6000
48 GB) cost nothing beyond the Pro/Growth subscription.

## Create the machine

| Field | Value |
|---|---|
| Container | `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404` |
| Workspace | this repo's URL (`ref: main`) |
| Command | see below |

```
bash /notebooks/scripts/start.sh & PIP_DISABLE_PIP_VERSION_CHECK=1 jupyter lab --allow-root --ip=0.0.0.0 --no-browser --ServerApp.trust_xheaders=True --ServerApp.disable_check_xsrf=False --ServerApp.allow_remote_access=True --ServerApp.allow_origin='*' --ServerApp.allow_credentials=True
```

First boot installs everything in **~5 minutes** (measured); boots after that
take ~2. ComfyUI ends up at `https://tensorboard-<your-notebook-fqdn>`.

## Day to day

Open a terminal in Jupyter:

```bash
# what is the boot doing right now?
tail -f /notebooks/logs/boot.log

# ComfyUI's own log
tail -f /notebooks/logs/comfyui.log

# restart ComfyUI by hand
pkill -f "python.*main.py"; cd /notebooks/ComfyUI && \
  nohup bash -c "source comfyenv/bin/activate && python main.py --listen --port 6006 --disable-metadata" \
  > /notebooks/logs/comfyui.log 2>&1 &
```

`Hub.ipynb` has the rest: ComfyUI link, model downloaders (Civitai /
HuggingFace), log viewer and a disk cleaner.

## Tokens

Copy `config/keys.example.json` to `config/keys.json` and fill in what you use
(Civitai, HuggingFace, Cloudflare R2). It lives only on your machine's
persistent storage — it is git-ignored and never leaves it.

## Layout

```
/notebooks              ← this repo, cloned by Paperspace (persistent)
├── ComfyUI/            ← installed by start.sh on first boot (git-ignored)
├── scripts/
│   ├── start.sh        ← runs on every boot: system deps → install if missing → launch
│   └── extras/fixes.sh ← one-off fixes for known errors (run by hand)
├── config/keys.json    ← your tokens (git-ignored)
├── Hub.ipynb           ← everyday utilities
└── logs/               ← boot.log + comfyui.log (fresh on every boot)
```

## Notes

- Only `/notebooks` survives a shutdown — that's why system packages reinstall
  on every boot and ComfyUI doesn't.
- Free-tier machines auto-stop after 6 h and run one at a time.
- Port 6006 is mandatory: it's the one Paperspace proxies (as "tensorboard").
  Tunnels are against Paperspace ToS — don't.
