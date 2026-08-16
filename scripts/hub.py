"""Helpers behind Hub.ipynb — the notebook only calls these.

Usage from a cell:
    import sys; sys.path.append('/notebooks/scripts')
    from hub import *
"""
import json
import os
import pathlib
import re
import subprocess

ROOT = pathlib.Path("/notebooks")
MODELS = ROOT / "ComfyUI" / "models"

def _keys():
    f = ROOT / "config" / "keys.json"
    if f.exists():
        return json.loads(f.read_text())
    print("⚠ no config/keys.json — copy config/keys.example.json and fill it in")
    return {}

KEYS = _keys()


# ── ComfyUI link ────────────────────────────────────────────────
def link():
    """Show the ComfyUI URL (and whether it's actually running)."""
    fqdn = os.environ.get("PAPERSPACE_FQDN", "")
    up = subprocess.run(["pgrep", "-f", "python.*main.py"],
                        capture_output=True).returncode == 0
    if not up:
        print("⚫ ComfyUI is not running — start it with: bash /notebooks/scripts/start.sh")
        return
    print("🟢 ComfyUI is running")
    print(f"https://tensorboard-{fqdn}")


# ── logs ────────────────────────────────────────────────────────
def log(name="boot", lines=40):
    """log('boot') or log('comfyui'). Live follow -> terminal: tail -f /notebooks/logs/<name>.log"""
    p = ROOT / "logs" / f"{name}.log"
    if not p.exists():
        print(f"no {p}")
        return
    print("\n".join(p.read_text(errors="replace").splitlines()[-lines:]))


# ── downloads ───────────────────────────────────────────────────
def civitai(url, folder="checkpoints"):
    """civitai('https://civitai.com/models/1102...', 'loras')
    Folders: checkpoints · loras · vae · diffusion_models · text_encoders · upscale_models"""
    import requests
    from tqdm.auto import tqdm

    token = KEYS.get("civitai", "")
    m = re.search(r"models/(\d+)", url)
    if m and "download" not in url:
        v = requests.get(f"https://civitai.com/api/v1/models/{m.group(1)}").json()
        url = v["modelVersions"][0]["downloadUrl"]
        print("latest version:", v["modelVersions"][0]["name"])
    dest = MODELS / folder
    dest.mkdir(parents=True, exist_ok=True)
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"} if token else {},
                     stream=True, allow_redirects=True)
    r.raise_for_status()
    name = re.findall('filename="?([^";]+)', r.headers.get("content-disposition", ""))
    name = name[0] if name else url.split("/")[-1].split("?")[0]
    total = int(r.headers.get("content-length", 0))
    with open(dest / name, "wb") as f, tqdm(total=total, unit="B", unit_scale=True,
                                            desc=name) as bar:
        for chunk in r.iter_content(1024 * 1024):
            f.write(chunk)
            bar.update(len(chunk))
    print("->", dest / name)


def hf_ls(repo):
    """List a repo's files: hf_ls('Comfy-Org/z_image_turbo')"""
    from huggingface_hub import list_repo_files
    for f in list_repo_files(repo, token=KEYS.get("huggingface") or None):
        print(f)


def hf(repo, file, folder="checkpoints"):
    """hf('Comfy-Org/z_image_turbo', 'split_files/.../z_image_turbo_bf16.safetensors', 'diffusion_models')"""
    from huggingface_hub import hf_hub_download
    dest = MODELS / folder
    dest.mkdir(parents=True, exist_ok=True)
    path = hf_hub_download(repo, file, token=KEYS.get("huggingface") or None)
    target = dest / pathlib.Path(file).name
    if not target.exists():
        os.link(path, target)  # hardlink from the HF cache: no duplicated disk
    print("->", target)


# ── disk ────────────────────────────────────────────────────────
def disk():
    """Size per folder under ComfyUI/models + output + HF cache."""
    dirs = sorted(MODELS.glob("*")) + [ROOT / "ComfyUI" / "output",
                                       ROOT / "huggingface_cache"]
    for d in dirs:
        if d.is_dir():
            size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            if size > 1e6:
                print(f"{size/1e9:7.2f} GB  {d}")


def rm(path):
    """Delete a file or folder (use the full path printed by disk())."""
    import shutil
    p = pathlib.Path(path)
    assert str(p).startswith("/notebooks/"), "only inside /notebooks"
    shutil.rmtree(p) if p.is_dir() else p.unlink()
    print("deleted", p)


# ── Cloudflare R2 (optional) ────────────────────────────────────
def _r2():
    import boto3
    c = KEYS["r2"]
    return (boto3.client("s3",
                         endpoint_url=f"https://{c['account_id']}.r2.cloudflarestorage.com",
                         aws_access_key_id=c["access_key_id"],
                         aws_secret_access_key=c["secret_access_key"]),
            c["bucket"])


def r2_ls(prefix=""):
    s3, bucket = _r2()
    for o in s3.list_objects_v2(Bucket=bucket, Prefix=prefix).get("Contents", []):
        print(f"{o['Size']/1e9:7.2f} GB  {o['Key']}")


def r2_get(key, folder="checkpoints"):
    """r2_get('loras/mystyle.safetensors', 'loras')"""
    s3, bucket = _r2()
    dest = MODELS / folder / pathlib.Path(key).name
    dest.parent.mkdir(parents=True, exist_ok=True)
    s3.download_file(bucket, key, str(dest))
    print("->", dest)


def r2_put(path, key=None):
    """r2_put('/notebooks/ComfyUI/output/img.png')"""
    s3, bucket = _r2()
    p = pathlib.Path(path)
    s3.upload_file(str(p), bucket, key or p.name)
    print("->", f"r2://{bucket}/{key or p.name}")
