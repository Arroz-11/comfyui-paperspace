#!/bin/bash
# start.sh — se ejecuta en CADA arranque de la notebook.
# Subir a: /notebooks/start.sh
#
# En Paperspace solo persiste /notebooks: lo instalado a nivel sistema (apt,
# pips globales, tema de Jupyter) se borra al apagar, así que se repite siempre.
# ComfyUI vive en /notebooks, por eso se instala UNA sola vez.
#
# Va en el Command del notebook, en segundo plano y seguido de Jupyter:
#   bash /notebooks/start.sh >> /tmp/boot.log 2>&1 & PIP_DISABLE_PIP_VERSION_CHECK=1 jupyter lab ...

set -u
ROOT=/notebooks
COMFY="$ROOT/ComfyUI"
VENV="$COMFY/comfyenv"
LOG="$ROOT/logs/boot.log"

mkdir -p "$ROOT/logs"
# Todo lo que sigue queda también en el log persistente (para verlo desde Jupyter)
exec > >(tee -a "$LOG") 2>&1

step() { echo "[$(date +%H:%M:%S)] === $* ==="; }

step "arranque"

# ── 1. Sistema (se borra en cada apagado) ─────────────────────
step "1/6 actualizando sistema"
apt-get update -qq && apt-get upgrade -y -qq
apt-get install -y -qq ffmpeg p7zip-full aria2
apt-get clean

# ── 2. Tema oscuro de JupyterLab ──────────────────────────────
step "2/6 tema oscuro"
SETTINGS=/root/.jupyter/lab/user-settings/@jupyterlab/apputils-extension
mkdir -p "$SETTINGS"
echo '{"theme": "JupyterLab Dark High Contrast"}' > "$SETTINGS/themes.jupyterlab-settings"

# ── 3. Paquetes globales (los usa el notebook de utilidades) ──
step "3/6 paquetes globales"
pip install -q -U pip
pip install -q tqdm ipywidgets huggingface_hub hf_transfer boto3 pytz

# ── 4. Cache de HuggingFace en zona persistente ───────────────
# Sin esto los modelos se rebajan enteros en cada arranque.
step "4/6 cache de HuggingFace"
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

# ── 5. ComfyUI: instalar solo si falta ────────────────────────
if [ ! -d "$COMFY/.git" ]; then
    step "5/6 instalando ComfyUI (primera vez, tarda ~15 min)"

    git clone https://github.com/comfyanonymous/ComfyUI.git "$COMFY"

    # Hooks de git-lfs: hacen fallar el arranque con
    # "git-lfs was not found on your path"
    cd "$COMFY"
    git config --unset-all core.hookspath 2>/dev/null || true
    rm -f .git/hooks/post-checkout .git/hooks/post-commit \
          .git/hooks/post-merge .git/hooks/pre-push

    echo "  creando venv…"
    python -m venv "$VENV"
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
    pip install -q -U pip

    echo "  instalando PyTorch (cu128)…"
    pip install -q torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/cu128

    echo "  instalando requirements…"
    pip install -q -r "$COMFY/requirements.txt"

    echo "  instalando ComfyUI-Manager…"
    git clone https://github.com/Comfy-Org/ComfyUI-Manager.git \
        "$COMFY/custom_nodes/ComfyUI-Manager"
    pip install -q -r "$COMFY/custom_nodes/ComfyUI-Manager/requirements.txt" || true

    python -c "import torch; print(f'  PyTorch {torch.__version__} | CUDA {torch.version.cuda} | GPU {torch.cuda.is_available()}')"
    deactivate
else
    step "5/6 ComfyUI ya instalado"
fi

# ── 6. Arrancar ComfyUI ───────────────────────────────────────
step "6/6 arrancando ComfyUI"
if pgrep -f "python.*main.py" > /dev/null; then
    echo "  ya estaba corriendo"
else
    cd "$COMFY"
    nohup bash -c "source '$VENV/bin/activate' && python main.py --listen --port 6006 --disable-metadata" \
        > "$ROOT/logs/comfyui.log" 2>&1 &
    echo "  lanzado (PID $!) — log en $ROOT/logs/comfyui.log"
fi

step "listo — ComfyUI en https://tensorboard-\$PAPERSPACE_FQDN"
