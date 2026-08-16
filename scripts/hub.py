"""Helpers behind Hub.ipynb — the notebook only calls these.

Usage from a cell:
    import sys; sys.path.append('/notebooks/scripts')
    from hub import *

The widget UIs (civitai_ui, hf_ui, cleaner_ui, r2_ui) are ports of the
original Util.ipynb, with the known flaws fixed:
  - HF used cache + copy (double disk) -> hardlink with copy fallback
  - HF "Custom" destination was dead code -> now a real option
  - R2 force-overwrite monkeypatched a global -> plain `force` param
  - tokens are read/saved in config/keys.json (each UI has a save box)
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import urllib.parse
from datetime import datetime

ROOT = pathlib.Path("/notebooks")
MODELS = ROOT / "ComfyUI" / "models"
KEYS_FILE = ROOT / "config" / "keys.json"

# Destination folders are read LIVE from ComfyUI/models: whatever exists there
# (including folders created by custom nodes) shows up on its own — no list to
# maintain. "Custom" stays as a free-text path escape hatch.


# ── keys ────────────────────────────────────────────────────────
def _keys():
    try:
        return json.loads(KEYS_FILE.read_text())
    except Exception:
        return {}


def _save_key(name, value):
    keys = _keys()
    keys[name] = value
    KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEYS_FILE.write_text(json.dumps(keys, indent=2))


def _fmt(n):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} TB"


def _now():
    return datetime.now().strftime("%H:%M:%S")


# ── ComfyUI control ─────────────────────────────────────────────
COMFY = ROOT / "ComfyUI"
VENV_ACT = COMFY / "comfyenv" / "bin" / "activate"
# Keep in sync with start.sh step 6.
# MPLBACKEND=Agg: when launched from the notebook, the Jupyter kernel leaks
# MPLBACKEND=module://matplotlib_inline... into the child; the venv's matplotlib
# rejects it and every node importing matplotlib dies (Detail-Daemon, RES4LYF,
# LayerStyle, Impact-Subpack, RMBG, Comfyroll). Agg = headless-safe everywhere.
_COMFY_CMD = ("cd '{c}' && source '{v}' && MPLBACKEND=Agg nohup python main.py "
              "--listen --port 6006 --disable-metadata > '{log}' 2>&1 &")


def _comfy_running():
    try:
        return subprocess.run(["pgrep", "-f", "python.*main.py"],
                              capture_output=True).returncode == 0
    except FileNotFoundError:   # not on linux (local testing)
        return False


def _git(*args):
    r = subprocess.run(["git", "-C", str(COMFY), *args],
                       capture_output=True, text=True)
    return r.returncode, (r.stdout or r.stderr).strip()


def comfy_start():
    if _comfy_running():
        return "already running"
    (ROOT / "logs").mkdir(exist_ok=True)
    subprocess.Popen(["bash", "-c", _COMFY_CMD.format(
        c=COMFY, v=VENV_ACT, log=ROOT / "logs" / "comfyui.log")],
        start_new_session=True)
    return "starting — give it ~30-60s, then Refresh"


def comfy_stop():
    subprocess.run(["pkill", "-f", "python.*main.py"], capture_output=True)
    return "stopped"


def comfy_version():
    """(current, commits_behind_or_None). Fetches origin quietly."""
    _, desc = _git("describe", "--tags", "--always")
    code, _ = _git("fetch", "-q", "origin", "master")
    if code != 0:
        return desc, None
    _, behind = _git("rev-list", "--count", "HEAD..origin/master")
    return desc, int(behind) if behind.isdigit() else None


def comfy_update():
    """Same steps as the old manage.sh: stash if dirty, pull master, reqs."""
    yield "updating ComfyUI…"
    code, dirty = _git("status", "--porcelain")
    if dirty:
        _git("stash")
        yield "  (local changes stashed)"
    _git("checkout", "-q", "master")
    code, out = _git("pull", "--ff-only")
    yield f"  {out.splitlines()[-1] if out else 'pulled'}"
    r = subprocess.run(["bash", "-c",
                        f"source '{VENV_ACT}' && pip install -q -r '{COMFY}/requirements.txt'"],
                       capture_output=True, text=True)
    yield "  requirements ok" if r.returncode == 0 else f"  ⚠ pip: {r.stderr.strip()[-200:]}"
    _, desc = _git("describe", "--tags", "--always")
    yield f"✅ now at {desc} — Stop + Start to apply"


def link():
    """Plain-text status + URL (used by scripts; the panel supersedes it)."""
    fqdn = os.environ.get("PAPERSPACE_FQDN", "")
    if not _comfy_running():
        print("⚫ ComfyUI is not running")
        return
    print(f"🟢 https://tensorboard-{fqdn}")


def comfy_panel():
    """The ComfyUI cell: status + link + start/stop/version/update buttons."""
    import ipywidgets as W
    from IPython.display import display

    fqdn = os.environ.get("PAPERSPACE_FQDN", "")
    url = f"https://tensorboard-{fqdn}"
    status = W.HTML()
    version = W.HTML()
    out = W.Output(layout=W.Layout(max_height="160px", overflow="auto"))

    def _refresh(_=None):
        if _comfy_running():
            status.value = (f"🟢 <b>running</b> — "
                            f"<a href='{url}' target='_blank' "
                            f"style='color:#60a5fa'>{url}</a>")
        else:
            status.value = "⚫ <b>not running</b>"

    def _msg(text):
        out.clear_output(wait=True)
        with out:
            print(text)

    start_b = W.Button(description="▶ Start", button_style="success",
                       layout=W.Layout(width="110px", height="34px"))
    stop_b = W.Button(description="⏹ Stop", button_style="danger",
                      layout=W.Layout(width="110px", height="34px"))
    refresh_b = W.Button(description="🔄 Refresh", layout=W.Layout(width="110px", height="34px"))
    check_b = W.Button(description="🔍 Check version", button_style="info",
                       layout=W.Layout(width="140px", height="34px"))
    update_b = W.Button(description="⬆️ Update ComfyUI", button_style="warning",
                        layout=W.Layout(width="160px", height="34px"))

    def _start(_):
        _msg(comfy_start())
        _refresh()

    def _stop(_):
        _msg(comfy_stop())
        _refresh()

    def _check(_):
        version.value = "🔍 checking…"
        desc, behind = comfy_version()
        if behind is None:
            version.value = f"version <b>{desc}</b> (couldn't reach origin)"
        elif behind == 0:
            version.value = f"version <b>{desc}</b> — ✅ up to date"
        else:
            version.value = (f"version <b>{desc}</b> — ⬆️ <b>{behind} commits "
                             f"behind</b>: press Update ComfyUI")

    def _update(_):
        out.clear_output(wait=True)
        with out:
            for line in comfy_update():
                print(line)
        _check(None)
        _refresh()

    start_b.on_click(_start)
    stop_b.on_click(_stop)
    refresh_b.on_click(_refresh)
    check_b.on_click(_check)
    update_b.on_click(_update)

    _refresh()
    display(W.VBox([status, version,
                    W.HBox([start_b, stop_b, refresh_b, check_b, update_b]),
                    out]))


def log(name="boot", lines=40):
    """log('boot') or log('comfyui'). Live: tail -f /notebooks/logs/<name>.log"""
    p = ROOT / "logs" / f"{name}.log"
    print("\n".join(p.read_text(errors="replace").splitlines()[-lines:])
          if p.exists() else f"no {p}")


# ── shared widget bits ──────────────────────────────────────────
def _token_box(key_name, label, on_saved=None):
    """Password field + save button that stores into config/keys.json."""
    import ipywidgets as W
    current = _keys().get(key_name, "")
    status = W.HTML(
        f"<span style='color:green'>✅ {label} configured: "
        f"{current[:4]}…{current[-4:]}</span>" if current else
        f"<span style='color:orange'>⚠️ No {label} configured</span>")
    field = W.Password(value=current, placeholder=f"{label} token",
                       description="Token:", style={"description_width": "80px"},
                       layout=W.Layout(width="440px"))
    btn = W.Button(description="💾 Save", button_style="info",
                   layout=W.Layout(width="90px", height="32px"))

    def _save(_):
        tok = field.value.strip()
        if not tok:
            status.value = "<span style='color:red'>❌ empty token</span>"
            return
        _save_key(key_name, tok)
        status.value = (f"<span style='color:green'>✅ {label} saved: "
                        f"{tok[:4]}…{tok[-4:]}</span>")
        if on_saved:
            on_saved(tok)

    btn.on_click(_save)
    return W.VBox([status, W.HBox([field, btn])]), lambda: _keys().get(key_name, "")


def _model_folders():
    """Live list of ComfyUI/models subfolders (self-updating)."""
    if MODELS.is_dir():
        return sorted(d.name for d in MODELS.iterdir() if d.is_dir())
    return []


def _dest_picker():
    """Dropdown of ComfyUI/models/* (read live) + free-text 'Custom' path."""
    import ipywidgets as W
    opts = _model_folders() + ["Custom"]
    default = "checkpoints" if "checkpoints" in opts else opts[0]
    dd = W.Dropdown(options=opts, value=default, description="Save to:",
                    style={"description_width": "80px"},
                    layout=W.Layout(width="280px"))
    custom = W.Text(placeholder="/notebooks/custom/path",
                    layout=W.Layout(width="360px"), disabled=True)
    dd.observe(lambda ch: setattr(custom, "disabled", ch.new != "Custom"),
               names="value")

    def path():
        if dd.value == "Custom":
            return custom.value.strip()
        p = MODELS / dd.value
        p.mkdir(parents=True, exist_ok=True)
        return str(p)

    return W.HBox([dd, custom]), path


# ── Civitai ─────────────────────────────────────────────────────
_cd_re = re.compile(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', re.IGNORECASE)


def _civitai_resolve(url, token):
    """Accept a model PAGE url or a direct download url; return download url."""
    import requests
    m = re.search(r"civitai\.com/models/(\d+)", url)
    if m and "/api/download/" not in url:
        r = requests.get(f"https://civitai.com/api/v1/models/{m.group(1)}",
                         headers={"Authorization": f"Bearer {token}"} if token else {},
                         timeout=20)
        r.raise_for_status()
        v = r.json()["modelVersions"][0]
        return v["downloadUrl"], v.get("name", "")
    return url, None


def civitai_ui():
    import ipywidgets as W
    import requests
    from IPython.display import display

    out = W.Output()
    token_ui, get_token = _token_box("civitai", "Civitai")

    url_in = W.Text(placeholder="model page URL or direct download URL",
                    description="URL:", style={"description_width": "80px"},
                    layout=W.Layout(width="700px"))
    dest_ui, dest_path = _dest_picker()
    btn = W.Button(description="⬇️ Download", button_style="success",
                   layout=W.Layout(width="130px", height="35px"))
    bar = W.FloatProgress(value=0, min=0, max=100,
                          layout=W.Layout(width="700px", visibility="hidden"))
    lbl = W.HTML()

    def _dl(_):
        out.clear_output(wait=True)
        with out:
            url, token = url_in.value.strip(), get_token()
            if not url:
                print("❌ Enter a URL")
                return
            try:
                url, version = _civitai_resolve(url, token)
                if version:
                    print(f"latest version: {version}")
                if "token=" not in url and token:
                    url += ("&" if "?" in url else "?") + f"token={token}"
                r = requests.get(url, stream=True, timeout=30,
                                 headers={"User-Agent": "curl/8"})
                r.raise_for_status()
                total = int(r.headers.get("Content-Length") or 0)
                m = _cd_re.search(r.headers.get("Content-Disposition", ""))
                name = os.path.basename(urllib.parse.unquote(m.group(1))) if m \
                    else url.split("/")[-1].split("?")[0] or "model.safetensors"
                dest = pathlib.Path(dest_path()) / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                bar.layout.visibility = "visible"
                done = 0
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(1024 * 1024):
                        f.write(chunk)
                        done += len(chunk)
                        if total:
                            bar.value = done / total * 100
                            lbl.value = f"{name}: {_fmt(done)} / {_fmt(total)}"
                bar.layout.visibility = "hidden"
                lbl.value = f"✅ {name}"
                print(f"✅ {name}\n📁 {dest}")
            except Exception as e:
                bar.layout.visibility = "hidden"
                print(f"❌ {e}")

    btn.on_click(_dl)
    display(W.VBox([W.HTML("<h3>🎨 Civitai Download</h3>"), token_ui,
                    W.HTML("<hr>"), url_in, dest_ui, btn, bar, lbl, out],
                   layout=W.Layout(padding="8px")))


# ── HuggingFace ─────────────────────────────────────────────────
def hf_check(repo, token=None):
    """Can this token download that repo? Handles gated models (FLUX etc.).

    Returns (status, message) where status is 'ok' | 'gated' | 'not-found'.
    """
    from huggingface_hub import list_repo_files
    from huggingface_hub.errors import (GatedRepoError, RepositoryNotFoundError)
    token = token if token is not None else (_keys().get("huggingface") or None)
    try:
        list_repo_files(repo, token=token)
        return "ok", f"✅ access OK — you can download {repo}"
    except GatedRepoError:
        return "gated", (f"🔒 {repo} is gated and this token has NOT been "
                         f"granted access.\n   Accept the license at "
                         f"https://huggingface.co/{repo} (button on the page), "
                         f"then try again.")
    except RepositoryNotFoundError:
        return "not-found", (f"❌ {repo} not found — wrong name, or it's private "
                             f"and this token can't see it.")
    except Exception as e:
        return "error", f"⚠️ {e}"


def hf_ui():
    import ipywidgets as W
    from huggingface_hub import hf_hub_download, list_repo_files
    from IPython.display import display

    out = W.Output()
    token_ui, get_token = _token_box("huggingface", "HuggingFace")

    repo_in = W.Text(placeholder="username/repo-name",
                     layout=W.Layout(width="380px"))
    type_dd = W.Dropdown(options=["model", "dataset"], value="model",
                         description="Type:", layout=W.Layout(width="160px"))
    list_btn = W.Button(description="📋 List files", button_style="info",
                        layout=W.Layout(width="110px"))
    check_btn = W.Button(description="🔓 Check access", button_style="warning",
                         layout=W.Layout(width="130px"),
                         tooltip="Gated models (FLUX…) need their license accepted")
    files = W.SelectMultiple(options=[], layout=W.Layout(width="700px", height="220px"))
    dest_ui, dest_path = _dest_picker()
    dl_btn = W.Button(description="⬇️ Download selected", button_style="success",
                      layout=W.Layout(width="180px"), disabled=True)
    bar = W.FloatProgress(min=0, max=100, layout=W.Layout(width="700px"))
    status = W.HTML()

    def _list(_):
        out.clear_output(wait=True)
        with out:
            repo = repo_in.value.strip()
            if not repo:
                status.value = "<span style='color:red'>⚠️ enter a repository</span>"
                return
            status.value = "🔍 listing…"
            try:
                files.options = list_repo_files(repo, repo_type=type_dd.value,
                                                token=get_token() or None)
                dl_btn.disabled = False
                status.value = f"✅ {len(files.options)} files"
            except Exception as e:
                status.value = f"<span style='color:red'>⚠️ {e}</span>"

    def _dl(_):
        out.clear_output(wait=True)
        with out:
            sel = list(files.value)
            if not sel:
                status.value = "<span style='color:red'>⚠️ select files first</span>"
                return
            dest = pathlib.Path(dest_path())
            dest.mkdir(parents=True, exist_ok=True)
            for i, fname in enumerate(sel, 1):
                bar.value = (i - 1) / len(sel) * 100
                print(f"⬇️ [{i}/{len(sel)}] {fname}")
                try:
                    cached = hf_hub_download(repo_in.value.strip(), fname,
                                             repo_type=type_dd.value,
                                             token=get_token() or None)
                    target = dest / pathlib.Path(fname).name
                    if not target.exists():
                        # Hardlink: flat filename in models/ AND zero extra disk —
                        # the cache "copy" is the same physical bytes, so clearing
                        # the cache later never breaks the model file.
                        real = os.path.realpath(cached)
                        try:
                            os.link(real, target)
                        except OSError:
                            # copy fallback: now it IS duplicated, so drop the
                            # cache blob right away
                            shutil.copy2(real, target)
                            try:
                                os.remove(real)
                                if os.path.islink(cached):
                                    os.remove(cached)
                            except OSError:
                                pass
                    print(f"✅ {target.name}")
                except Exception as e:
                    print(f"❌ {e}")
            bar.value = 100
            status.value = f"✅ done — saved to {dest}"

    def _check(_):
        out.clear_output(wait=True)
        with out:
            repo = repo_in.value.strip()
            if not repo:
                status.value = "<span style='color:red'>⚠️ enter a repository</span>"
                return
            status.value = "🔍 checking access…"
            code, msg = hf_check(repo, get_token() or None)
            color = {"ok": "green", "gated": "orange"}.get(code, "red")
            status.value = f"<span style='color:{color}'>{msg.splitlines()[0]}</span>"
            print(msg)

    list_btn.on_click(_list)
    check_btn.on_click(_check)
    dl_btn.on_click(_dl)
    display(W.VBox([W.HTML("<h3>🤗 HuggingFace Download</h3>"), token_ui,
                    W.HTML("<hr>"), W.HBox([repo_in, type_dd, list_btn, check_btn]),
                    files, dest_ui, dl_btn, bar, status, out]))


def _hf_fetch(repo, file, folder, token=None):
    """Download one HF file flat into ComfyUI/models/<folder> via hardlink."""
    from huggingface_hub import hf_hub_download
    dest = MODELS / folder
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / pathlib.Path(file).name
    if target.exists():
        return target, False
    cached = hf_hub_download(repo, file, token=token)
    real = os.path.realpath(cached)
    try:
        os.link(real, target)
    except OSError:
        shutil.copy2(real, target)
        try:
            os.remove(real)
            if os.path.islink(cached):
                os.remove(cached)
        except OSError:
            pass
    return target, True


# ── Model presets ───────────────────────────────────────────────
def _presets():
    try:
        data = json.loads((ROOT / "config" / "presets.json").read_text())
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except Exception as e:
        print(f"⚠ can't read config/presets.json: {e}")
        return {}


def presets_ui():
    import ipywidgets as W
    from IPython.display import display

    presets = _presets()
    if not presets:
        return
    out = W.Output()
    model_dd = W.Dropdown(
        options=[(v["name"], k) for k, v in presets.items()],
        description="Model:", style={"description_width": "70px"},
        layout=W.Layout(width="320px"))
    var_tg = W.ToggleButtons(options=["bf16", "fp8"], value="bf16",
                             layout=W.Layout(width="220px"))
    table = W.HTML()
    dl_btn = W.Button(description="⬇️ Download missing", button_style="success",
                      layout=W.Layout(width="180px", height="34px"))
    bar = W.FloatProgress(min=0, max=100,
                          layout=W.Layout(width="700px", visibility="hidden"))
    lbl = W.HTML()

    def _files():
        return presets[model_dd.value]["variants"][var_tg.value]

    def _render(_=None):
        rows, missing = [], 0.0
        for f in _files():
            have = (MODELS / f["folder"] / pathlib.Path(f["file"]).name).exists()
            if not have:
                missing += f["gb"]
            rows.append(
                f"<tr><td>{'✅' if have else '⬜'}</td>"
                f"<td style='padding:0 10px'>{pathlib.Path(f['file']).name}</td>"
                f"<td>{f['folder']}</td>"
                f"<td style='text-align:right;padding-left:10px'>{f['gb']:.2f} GB</td></tr>")
        about = presets[model_dd.value].get("about", "")
        table.value = (f"<i>{about}</i><table style='font-family:monospace'>"
                       + "".join(rows) + "</table>"
                       + (f"<b>to download: {missing:.1f} GB</b>" if missing
                          else "<b>✅ complete — nothing to download</b>"))
        dl_btn.disabled = missing == 0

    def _download(_):
        out.clear_output(wait=True)
        with out:
            token = _keys().get("huggingface") or None
            todo = [f for f in _files()
                    if not (MODELS / f["folder"] / pathlib.Path(f["file"]).name).exists()]
            # pre-check de acceso por repo (los gated avisan ANTES de bajar 10 GB)
            for repo in sorted({f["repo"] for f in todo}):
                code, msg = hf_check(repo, token)
                if code != "ok":
                    print(msg)
                    if code == "gated":
                        return
            bar.layout.visibility = "visible"
            # HF's own progress bars are noisy (split_files/... names, double
            # bars) — silence them; our bar + label carry the progress.
            from huggingface_hub.utils import disable_progress_bars, enable_progress_bars
            disable_progress_bars()
            try:
                for i, f in enumerate(todo, 1):
                    name = pathlib.Path(f["file"]).name
                    bar.value = (i - 1) / len(todo) * 100
                    lbl.value = f"⬇️ [{i}/{len(todo)}] {name} ({f['gb']:.2f} GB)…"
                    try:
                        _hf_fetch(f["repo"], f["file"], f["folder"], token)
                        print(f"✅ {name} → {f['folder']}")
                    except Exception as e:
                        print(f"❌ {name}: {e}")
            finally:
                enable_progress_bars()
            bar.value = 100
            bar.layout.visibility = "hidden"
            lbl.value = "✅ done"
            _render()

    model_dd.observe(_render, names="value")
    var_tg.observe(_render, names="value")
    dl_btn.on_click(_download)
    _render()
    display(W.VBox([W.HTML("<h3>📦 Model Presets</h3>"),
                    W.HBox([model_dd, var_tg]), table, dl_btn, bar, lbl, out]))


# ── Cleaner ─────────────────────────────────────────────────────
def _disk_html():
    """Usage bar for /notebooks + breakdown of the heavy folders.
    Hardlinked files (models <-> HF cache) are counted once, under the
    first bucket that sees them — so 'HF cache' shows only its UNIQUE bytes."""
    try:
        usage = shutil.disk_usage(ROOT)
    except OSError:
        return "<i>disk info unavailable</i>"
    seen = set()

    def sz(path):
        total = 0
        p = pathlib.Path(path)
        if not p.is_dir():
            return 0
        for f in p.rglob("*"):
            try:
                st = f.lstat()
            except OSError:
                continue
            if not f.is_file() or f.is_symlink():
                continue
            key = (st.st_dev, st.st_ino)
            if key in seen:
                continue
            seen.add(key)
            total += st.st_size
        return total

    # Order matters: earlier buckets claim shared (hardlinked) bytes.
    # 'ComfyUI (rest)' scans all of ComfyUI/ but venv+models are already seen.
    parts = [("models", sz(MODELS)),
             ("ComfyUI venv", sz(COMFY / "comfyenv")),
             ("ComfyUI (rest)", sz(COMFY)),
             ("HF cache", sz(ROOT / "huggingface_cache"))]
    parts.append(("other", max(0, usage.used - sum(s for _, s in parts))))

    pct = usage.used / usage.total * 100 if usage.total else 0
    color = "#4caf50" if pct < 80 else "#ff9800" if pct < 90 else "#f44336"
    rows = "".join(
        f"<tr><td style='padding-right:14px'>{name}</td>"
        f"<td style='text-align:right'>{_fmt(size)}</td>"
        f"<td style='text-align:right;padding-left:14px;opacity:.7'>"
        f"{size / usage.total * 100:.0f}%</td></tr>"
        for name, size in parts if size)
    return (
        f"<b>💾 /notebooks: {_fmt(usage.used)} / {_fmt(usage.total)} ({pct:.0f}%)</b>"
        f"<div style='width:700px;height:10px;background:#333;border-radius:5px;margin:4px 0 8px'>"
        f"<div style='width:{min(pct, 100):.1f}%;height:100%;background:{color};border-radius:5px'></div></div>"
        f"<table style='font-family:monospace'>{rows}</table>")


def _dir_size(path):
    total = 0
    for p in pathlib.Path(path).rglob("*"):
        try:
            if p.is_file() or p.is_symlink():
                total += p.lstat().st_size
        except OSError:
            pass
    return total


def cleaner_ui():
    import ipywidgets as W
    from IPython.display import display

    roots = {
        "models": MODELS, "output": ROOT / "ComfyUI" / "output",
        "input": ROOT / "ComfyUI" / "input", "temp": ROOT / "ComfyUI" / "temp",
        "hf cache": ROOT / "huggingface_cache", "trash": ROOT / ".Trash-0",
    }

    def _allowed(p):
        p = pathlib.Path(p).resolve()
        return any(str(p) == str(r.resolve()) or str(p).startswith(str(r.resolve()) + os.sep)
                   for r in roots.values() if r.exists())

    def folder_options():
        opts = []
        if MODELS.is_dir():
            for sub in sorted(MODELS.iterdir()):
                if sub.is_dir():
                    opts.append((f"models/{sub.name}  —  {_fmt(_dir_size(sub))}", str(sub)))
        for name, p in roots.items():
            if name != "models" and p.is_dir():
                opts.append((f"{name}  —  {_fmt(_dir_size(p))}", str(p)))
        return opts

    def list_items(path):
        opts = []
        if not path:   # fresh machine: no folders yet -> empty list, not a crash
            return opts
        p = pathlib.Path(path)
        if p.is_dir():
            for e in sorted(p.iterdir(), key=lambda x: x.name.lower()):
                size = _dir_size(e) if e.is_dir() else e.lstat().st_size
                tag = "DIR" if e.is_dir() else "FILE"
                opts.append((f"[{tag}] {e.name}  —  {_fmt(size)}", str(e)))
        return opts

    folder_dd = W.Dropdown(options=folder_options(), description="📁 Folder:",
                           style={"description_width": "90px"},
                           layout=W.Layout(width="700px"))
    mode = W.ToggleButtons(
        options=[("🗑️ Delete selected items (SAFE)", "items"),
                 ("⚠️ Empty whole folder (DANGEROUS)", "clean")],
        value="items", layout=W.Layout(width="700px"))
    items = W.SelectMultiple(options=[], description="📋 Items:",
                             style={"description_width": "70px"},
                             layout=W.Layout(width="860px", height="260px"))
    sel_all = W.ToggleButtons(options=[("✅ Select all", "all"), ("❌ None", "none")],
                              button_style="info", layout=W.Layout(width="320px"))
    refresh = W.Button(description="🔄 Refresh", button_style="info",
                       layout=W.Layout(width="120px", height="32px"))
    confirm = W.Checkbox(description="✔️ I confirm the deletion", indent=False)
    run = W.Button(description="🗑️ RUN CLEANUP", button_style="danger",
                   disabled=True, layout=W.Layout(width="220px", height="40px"))
    logw = W.Output(layout=W.Layout(max_height="240px", overflow="auto",
                                    border="1px solid #555", padding="8px"))

    def _refresh_items(_=None):
        items.options = list_items(folder_dd.value)
        items.value = ()
        _gate(None)

    def _refresh_all(_=None):
        disk.value = _disk_html()
        folder_dd.options = folder_options()
        _refresh_items()

    def _gate(_):
        ok = folder_dd.value and _allowed(folder_dd.value) and confirm.value
        run.disabled = not (ok and (mode.value == "clean" or items.value))

    def _sel(ch):
        items.value = tuple(v for _, v in items.options) if ch["new"] == "all" else ()

    def _delete(p):
        p = pathlib.Path(p)
        if p.is_dir() and not p.is_symlink():
            shutil.rmtree(p, onerror=lambda f, x, e: (os.chmod(x, 0o700), f(x)))
        else:
            p.unlink(missing_ok=True)

    def _run(_):
        path = folder_dd.value
        if not _allowed(path):
            with logw:
                print(f"[{_now()}] ❌ path not allowed")
            return
        with logw:
            if mode.value == "clean":
                print(f"[{_now()}] 🧹 emptying {path}")
                for child in pathlib.Path(path).iterdir():
                    try:
                        _delete(child)
                    except Exception as e:
                        print(f"   ⚠️ {child.name}: {e}")
                print(f"[{_now()}] ✅ emptied")
            else:
                for it in items.value:
                    try:
                        _delete(it)
                        print(f"[{_now()}] ✅ deleted {it}")
                    except Exception as e:
                        print(f"[{_now()}] ❌ {it}: {e}")
        _refresh_all()

    refresh.on_click(_refresh_all)
    folder_dd.observe(_refresh_items, names="value")
    sel_all.observe(_sel, names="value")
    for w in (items, mode, confirm):
        w.observe(_gate, names="value")
    run.on_click(_run)

    disk = W.HTML(_disk_html())
    display(W.VBox([W.HTML("<h3>🧹 Cleaner</h3>"), disk, W.HTML("<hr>"),
                    folder_dd, mode,
                    W.HBox([sel_all, refresh]), items, confirm, run, logw]))
    _refresh_items()


# ── Cloudflare R2 ───────────────────────────────────────────────
def _r2_cfg():
    return _keys().get("r2", {})


def _r2_client():
    import boto3
    c = _r2_cfg()
    endpoint = c.get("endpoint_url") or (
        f"https://{c['account_id']}.r2.cloudflarestorage.com" if c.get("account_id") else None)
    return boto3.client("s3", endpoint_url=endpoint, region_name="auto",
                        aws_access_key_id=c.get("access_key_id"),
                        aws_secret_access_key=c.get("secret_access_key")), c.get("bucket")


def _r2_folders():
    try:
        s3, bucket = _r2_client()
        r = s3.list_objects_v2(Bucket=bucket, Delimiter="/")
        return sorted(p["Prefix"].rstrip("/") for p in r.get("CommonPrefixes", []))
    except Exception:
        return []


def r2_ui():
    import ipywidgets as W
    from IPython.display import display

    # -- Config tab --
    c = _r2_cfg()
    endpoint_in = W.Text(value=c.get("endpoint_url", ""),
                         placeholder="https://<account_id>.r2.cloudflarestorage.com",
                         description="Endpoint:", style={"description_width": "100px"},
                         layout=W.Layout(width="620px"))
    access_in = W.Text(value=c.get("access_key_id", ""), description="Access key:",
                       style={"description_width": "100px"}, layout=W.Layout(width="520px"))
    secret_in = W.Password(value=c.get("secret_access_key", ""), description="Secret:",
                           style={"description_width": "100px"}, layout=W.Layout(width="520px"))
    bucket_in = W.Text(value=c.get("bucket", ""), description="Bucket:",
                       style={"description_width": "100px"}, layout=W.Layout(width="380px"))
    cfg_status = W.HTML(f"<span style='color:green'>✅ bucket: {c['bucket']}</span>"
                        if c.get("bucket") else
                        "<span style='color:orange'>⚠️ not configured</span>")
    cfg_btn = W.Button(description="💾 Save config", button_style="success",
                       layout=W.Layout(width="150px", height="34px"))
    cfg_out = W.Output()

    def _cfg_save(_):
        cfg_out.clear_output(wait=True)
        with cfg_out:
            if not all([endpoint_in.value, access_in.value, secret_in.value, bucket_in.value]):
                print("❌ all fields required")
                return
            _save_key("r2", {"endpoint_url": endpoint_in.value.strip(),
                             "access_key_id": access_in.value.strip(),
                             "secret_access_key": secret_in.value.strip(),
                             "bucket": bucket_in.value.strip()})
            cfg_status.value = f"<span style='color:green'>✅ bucket: {bucket_in.value}</span>"
            print("✅ saved")

    cfg_btn.on_click(_cfg_save)
    cfg_tab = W.VBox([cfg_status, W.HTML("<hr>"), endpoint_in, access_in,
                      secret_in, bucket_in, cfg_btn, cfg_out])

    # -- Upload tab --
    up_out = W.Output()
    up_path = W.Text(placeholder="/notebooks/ComfyUI/models/loras/file.safetensors",
                     description="File:", style={"description_width": "80px"},
                     layout=W.Layout(width="560px"))
    up_folder = W.Dropdown(options=_r2_folders() or [""], description="R2 folder:",
                           style={"description_width": "80px"},
                           layout=W.Layout(width="300px"))
    up_btn = W.Button(description="⬆️ Upload", button_style="success",
                      layout=W.Layout(width="110px", height="34px"))
    up_force = W.Button(description="✅ Overwrite", button_style="warning",
                        layout=W.Layout(width="110px", height="34px", visibility="hidden"))
    up_bar = W.FloatProgress(min=0, max=100, layout=W.Layout(width="560px",
                                                             visibility="hidden"))
    up_lbl = W.HTML()

    def _upload(force):
        up_out.clear_output(wait=True)
        with up_out:
            p = pathlib.Path(up_path.value.strip())
            if not p.exists():
                print(f"❌ not found: {p}")
                return
            s3, bucket = _r2_client()
            key = f"{up_folder.value}/{p.name}" if up_folder.value else p.name
            if not force:
                try:
                    s3.head_object(Bucket=bucket, Key=key)
                    print(f"⚠️ already exists: {key} — use Overwrite")
                    up_force.layout.visibility = "visible"
                    return
                except Exception:
                    pass
            size = p.stat().st_size
            state = {"done": 0}
            up_bar.layout.visibility = "visible"

            def cb(n):
                state["done"] += n
                pct = state["done"] / size * 100
                up_bar.value = pct
                up_lbl.value = f"{p.name}: {_fmt(state['done'])} / {_fmt(size)}"

            s3.upload_file(str(p), bucket, key, Callback=cb)
            up_bar.layout.visibility = "hidden"
            up_force.layout.visibility = "hidden"
            up_lbl.value = f"✅ {key}"
            print(f"✅ uploaded: {key}")

    up_btn.on_click(lambda _: _upload(False))
    up_force.on_click(lambda _: _upload(True))
    up_tab = W.VBox([up_path, up_folder, W.HBox([up_btn, up_force]),
                     up_bar, up_lbl, up_out])

    # -- Download tab --
    dl_out = W.Output()
    dl_folder = W.Dropdown(options=_r2_folders() or [""], description="R2 folder:",
                           style={"description_width": "80px"},
                           layout=W.Layout(width="300px"))
    dl_search = W.Text(placeholder="search…", description="Search:",
                       style={"description_width": "80px"},
                       layout=W.Layout(width="280px"))
    dl_list_btn = W.Button(description="📋 List", button_style="info",
                           layout=W.Layout(width="90px"))
    dl_files = W.SelectMultiple(options=[], layout=W.Layout(width="700px", height="220px"))
    dest_ui, dest_path = _dest_picker()
    dl_btn = W.Button(description="⬇️ Download selected", button_style="primary",
                      layout=W.Layout(width="180px", height="34px"))
    dl_bar = W.FloatProgress(min=0, max=100, layout=W.Layout(width="700px",
                                                             visibility="hidden"))
    dl_lbl = W.HTML()

    def _dl_list(_):
        dl_out.clear_output(wait=True)
        with dl_out:
            s3, bucket = _r2_client()
            prefix = f"{dl_folder.value}/" if dl_folder.value else ""
            try:
                r = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
                opts = []
                for o in r.get("Contents", []):
                    if o["Key"].endswith("/"):
                        continue
                    if dl_search.value and dl_search.value.lower() not in o["Key"].lower():
                        continue
                    when = o["LastModified"].strftime("%Y-%m-%d %H:%M")
                    opts.append((f"{o['Key'].split('/')[-1]}  ({_fmt(o['Size'])})  {when}",
                                 o["Key"]))
                dl_files.options = opts
                print(f"✅ {len(opts)} files")
            except Exception as e:
                print(f"❌ {e}")

    def _dl_go(_):
        dl_out.clear_output(wait=True)
        with dl_out:
            sel = list(dl_files.value)
            if not sel:
                print("❌ select files first")
                return
            s3, bucket = _r2_client()
            dest = pathlib.Path(dest_path())
            dest.mkdir(parents=True, exist_ok=True)
            dl_bar.layout.visibility = "visible"
            ok = 0
            for i, key in enumerate(sel, 1):
                try:
                    size = s3.head_object(Bucket=bucket, Key=key)["ContentLength"]
                    state = {"done": 0, "last": -1}

                    def cb(n, size=size, key=key, i=i, state=state):
                        state["done"] += n
                        pct = state["done"] / size * 100
                        if pct - state["last"] >= 0.5 or state["done"] >= size:
                            state["last"] = pct
                            dl_bar.value = pct
                            dl_lbl.value = (f"[{i}/{len(sel)}] {key.split('/')[-1]}: "
                                            f"{_fmt(state['done'])} / {_fmt(size)}")

                    s3.download_file(bucket, key, str(dest / key.split("/")[-1]),
                                     Callback=cb)
                    print(f"✅ {key}")
                    ok += 1
                except Exception as e:
                    print(f"❌ {key}: {e}")
            dl_bar.layout.visibility = "hidden"
            dl_lbl.value = f"✅ {ok}/{len(sel)} downloaded to {dest}"

    dl_list_btn.on_click(_dl_list)
    dl_btn.on_click(_dl_go)
    dl_tab = W.VBox([W.HBox([dl_folder, dl_search, dl_list_btn]), dl_files,
                     dest_ui, dl_btn, dl_bar, dl_lbl, dl_out])

    tabs = W.Tab(children=[cfg_tab, up_tab, dl_tab])
    for i, t in enumerate(["⚙️ Config", "⬆️ Upload", "⬇️ Download"]):
        tabs.set_title(i, t)
    display(W.VBox([W.HTML("<h3>☁️ Cloudflare R2</h3>"), tabs]))
