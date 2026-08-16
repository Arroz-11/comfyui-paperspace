#!/bin/bash
# start.sh — runs on EVERY boot of the notebook.
#
# On Paperspace only /notebooks persists: anything installed at system level
# (apt, global pips, Jupyter config) is wiped on shutdown, so those steps repeat
# every boot. ComfyUI lives in /notebooks, so it installs only once.
#
# Goes in the notebook's Command, in the background, followed by Jupyter:
#   bash /notebooks/scripts/start.sh & PIP_DISABLE_PIP_VERSION_CHECK=1 jupyter lab ...

set -u
ROOT=/notebooks
COMFY="$ROOT/ComfyUI"
VENV="$COMFY/comfyenv"
LOG="$ROOT/logs/boot.log"

# Fresh logs every boot: these are per-session logs, letting them grow forever
# just wastes persistent storage.
mkdir -p "$ROOT/logs"
: > "$LOG"
exec > >(tee -a "$LOG") 2>&1

step() { echo "[$(date +%H:%M:%S)] === $* ==="; }

step "boot"

# ── 1. System (wiped on every shutdown) ───────────────────────
step "1/6 system packages"
apt-get update -qq && apt-get upgrade -y -qq
apt-get install -y -qq ffmpeg p7zip-full aria2
apt-get clean

# ── 2. JupyterLab dark theme ──────────────────────────────────
step "2/6 dark theme"
SETTINGS=/root/.jupyter/lab/user-settings/@jupyterlab/apputils-extension
mkdir -p "$SETTINGS"
echo '{"theme": "JupyterLab Dark High Contrast"}' > "$SETTINGS/themes.jupyterlab-settings"

# ── 3. Global packages (used by Hub.ipynb) ────────────────────
step "3/6 global packages"
pip install -q -U pip
pip install -q tqdm ipywidgets huggingface_hub hf_transfer boto3 pytz

# ── 4. HuggingFace cache on persistent storage ────────────────
# Without this, models re-download from scratch on every boot.
step "4/6 HuggingFace cache"
if ! grep -q HF_HOME ~/.bashrc 2>/dev/null; then
    cat >> ~/.bashrc <<'EOF'
export HF_HOME=/notebooks/huggingface_cache
export HF_HUB_CACHE=/notebooks/huggingface_cache
export HF_HUB_ENABLE_HF_TRANSFER=1
EOF
fi
export HF_HOME=$ROOT/huggingface_cache
export HF_HUB_CACHE=$ROOT/huggingface_cache
export HF_HUB_ENABLE_HF_TRANSFER=1
mkdir -p "$HF_HOME"

# ── 5. ComfyUI: install only if missing ───────────────────────
if [ ! -d "$COMFY/.git" ]; then
    step "5/6 installing ComfyUI (first time, ~4 min)"

    git clone https://github.com/comfyanonymous/ComfyUI.git "$COMFY"

    # git-lfs hooks break ComfyUI's startup with
    # "git-lfs was not found on your path"
    cd "$COMFY"
    git config --unset-all core.hookspath 2>/dev/null || true
    rm -f .git/hooks/post-checkout .git/hooks/post-commit \
          .git/hooks/post-merge .git/hooks/pre-push

    echo "  creating venv..."
    python -m venv "$VENV"
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
    pip install -q -U pip

    echo "  installing PyTorch (cu128)..."
    pip install -q torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/cu128

    echo "  installing requirements..."
    pip install -q -r "$COMFY/requirements.txt"

    # Default UI settings (only on first install — after that they're yours)
    mkdir -p "$COMFY/user/default"
    cp "$ROOT/config/comfy.settings.json" "$COMFY/user/default/comfy.settings.json" 2>/dev/null || true

    python -c "import torch; print(f'  PyTorch {torch.__version__} | CUDA {torch.version.cuda} | GPU {torch.cuda.is_available()}')"
    deactivate
else
    step "5/6 ComfyUI already installed"
fi

# ── 5b. Custom nodes from config/nodes.txt ────────────────────
# Runs every boot but only clones what's missing, so it's a no-op when
# everything is already there. Edit the list, push, recreate → done.
if [ -f "$ROOT/config/nodes.txt" ]; then
    step "5b/6 custom nodes"
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
    while IFS= read -r url; do
        case "$url" in ''|\#*) continue ;; esac
        name=$(basename "$url" .git)
        dir="$COMFY/custom_nodes/$name"
        if [ ! -d "$dir" ]; then
            echo "  + $name"
            git clone -q "$url" "$dir" || { echo "    ⚠ clone failed"; continue; }
            [ -f "$dir/requirements.txt" ] && pip install -q -r "$dir/requirements.txt" || true
        fi
    done < "$ROOT/config/nodes.txt"
    deactivate
fi

# ── 6. Launch ComfyUI ─────────────────────────────────────────
step "6/6 launching ComfyUI"
if pgrep -f "python.*main.py" > /dev/null; then
    echo "  already running"
else
    cd "$COMFY"
    nohup bash -c "source '$VENV/bin/activate' && python main.py --listen --port 6006 --disable-metadata" \
        > "$ROOT/logs/comfyui.log" 2>&1 &
    echo "  launched (PID $!) — log: $ROOT/logs/comfyui.log"
fi

step "done — ComfyUI at https://tensorboard-\$PAPERSPACE_FQDN"
