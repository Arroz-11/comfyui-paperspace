#!/bin/bash
# fixes.sh — arreglos puntuales para errores conocidos. NO se corren solos:
# se invocan a mano cuando aparece el síntoma.
#
#   bash scripts/extras/fixes.sh numpy      # WAS Node Suite / Numba
#   bash scripts/extras/fixes.sh lfs        # ComfyUI no arranca por git-lfs
#   bash scripts/extras/fixes.sh joycaption # JoyCaption2 (LayerStyle_Advance)

set -uo pipefail
ROOT="${NOTEBOOKS_DIR:-/notebooks}"
COMFY="$ROOT/ComfyUI"
VENV="$COMFY/comfyenv/bin/activate"

usage() { sed -n '2,9p' "$0"; exit 1; }
[ $# -eq 0 ] && usage

case "$1" in

# Síntoma: WAS Node Suite falla con "Numba needs NumPy 2.3 or less"
numpy)
    # shellcheck disable=SC1090
    source "$VENV"
    pip install numpy==2.3.0
    echo "✅ numpy fijado en 2.3.0"
    ;;

# Síntoma: ComfyUI no arranca — "git-lfs was not found on your path".
# Lo dejan los repos clonados con LFS (modelos, algunos custom nodes).
lfs)
    for d in "$COMFY" "$COMFY"/custom_nodes/*/ "$COMFY"/models/*/; do
        [ -d "$d/.git" ] || continue
        git -C "$d" config --unset-all core.hookspath 2>/dev/null
        rm -f "$d/.git/hooks/post-checkout" "$d/.git/hooks/post-commit" \
              "$d/.git/hooks/post-merge" "$d/.git/hooks/pre-push"
    done
    echo "✅ hooks de git-lfs limpiados"
    ;;

# JoyCaption2 dentro de ComfyUI_LayerStyle_Advance.
# ⚠️ Los parches se PIERDEN cada vez que se actualiza ese custom node:
#    hay que volver a correr esto después de cada update.
joycaption)
    TARGET="$COMFY/custom_nodes/ComfyUI_LayerStyle_Advance/py/joycaption_alpha_2.py"
    [ -f "$TARGET" ] || { echo "❌ no está ComfyUI_LayerStyle_Advance"; exit 1; }

    # shellcheck disable=SC1090
    source "$VENV"
    pip install -q transformers==4.46.3

    # Modelo (es un Space de HF, no un repo normal). `hf` en vez de git-lfs
    # porque `apt install git-lfs` necesita root y en Paperspace no hay.
    MODELS="$COMFY/models/Joy_caption"
    if [ ! -d "$MODELS/cgrkzexw-599808" ]; then
        mkdir -p "$MODELS" && cd "$MODELS"
        hf download fancyfeast/joy-caption-alpha-two --repo-type space \
            --local-dir cgrkzexw-599808
        # el download queda anidado un nivel: aplanarlo
        if [ -d "cgrkzexw-599808/cgrkzexw-599808" ]; then
            mv cgrkzexw-599808/cgrkzexw-599808/* cgrkzexw-599808/
            rmdir cgrkzexw-599808/cgrkzexw-599808
        fi
    fi

    # Import de SiglipVisionModel + usarlo en vez de AutoModel
    sed -i 's/from transformers import AutoModel, AutoProcessor, AutoTokenizer, PreTrainedTokenizer, PreTrainedTokenizerFast, \\/from transformers import AutoModel, AutoProcessor, AutoTokenizer, PreTrainedTokenizer, PreTrainedTokenizerFast, SiglipVisionModel, \\/' "$TARGET"
    sed -i 's/clip_model = AutoModel.from_pretrained(CLIP_PATH).vision_model/clip_model = SiglipVisionModel.from_pretrained(CLIP_PATH)/g' "$TARGET"

    # Prefijo de las keys del checkpoint. OJO: esto se INVIRTIÓ en may-2026 —
    # transformers ahora espera las keys SIN "vision_model.", antes las pedía CON.
    python - "$TARGET" <<'PY'
import sys
path = sys.argv[1]
src = open(path).read()
old = '''checkpoint = {k.replace("_orig_mod.module.", ""): v for k, v in checkpoint.items()}
            clip_model.load_state_dict(checkpoint)'''
new = '''checkpoint = {k.replace("_orig_mod.module.", ""): v for k, v in checkpoint.items()}
            checkpoint = {k.replace("vision_model.", ""): v for k, v in checkpoint.items()}
            clip_model.load_state_dict(checkpoint)'''
n = src.count(old)
open(path, "w").write(src.replace(old, new))
print(f"[joycaption] {n} bloque(s) parcheado(s)" if n else
      "[joycaption] ya estaba parcheado (o cambió el código upstream)")
PY
    echo "✅ JoyCaption2 listo"
    ;;

*) usage ;;
esac
