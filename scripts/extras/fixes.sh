#!/bin/bash
# fixes.sh — one-off fixes for known errors. They do NOT run automatically:
# invoke them by hand when the symptom shows up.
#
#   bash scripts/extras/fixes.sh numpy      # WAS Node Suite / Numba error
#   bash scripts/extras/fixes.sh lfs        # ComfyUI won't start (git-lfs)
#   bash scripts/extras/fixes.sh joycaption # JoyCaption2 (LayerStyle_Advance)

set -uo pipefail
ROOT=/notebooks
COMFY="$ROOT/ComfyUI"
VENV="$COMFY/comfyenv/bin/activate"

usage() { sed -n '2,9p' "$0"; exit 1; }
[ $# -eq 0 ] && usage

case "$1" in

# Symptom: WAS Node Suite fails with "Numba needs NumPy 2.3 or less"
numpy)
    # shellcheck disable=SC1090
    source "$VENV"
    pip install numpy==2.3.0
    echo "✅ numpy pinned to 2.3.0"
    ;;

# Symptom: ComfyUI won't start — "git-lfs was not found on your path".
# Left behind by repos cloned with LFS (models, some custom nodes).
lfs)
    for d in "$COMFY" "$COMFY"/custom_nodes/*/ "$COMFY"/models/*/; do
        [ -d "$d/.git" ] || continue
        git -C "$d" config --unset-all core.hookspath 2>/dev/null
        rm -f "$d/.git/hooks/post-checkout" "$d/.git/hooks/post-commit" \
              "$d/.git/hooks/post-merge" "$d/.git/hooks/pre-push"
    done
    echo "✅ git-lfs hooks cleaned"
    ;;

# JoyCaption2 inside ComfyUI_LayerStyle_Advance.
# ⚠️ The patches are LOST every time that custom node updates:
#    re-run this after each update.
joycaption)
    TARGET="$COMFY/custom_nodes/ComfyUI_LayerStyle_Advance/py/joycaption_alpha_2.py"
    [ -f "$TARGET" ] || { echo "❌ ComfyUI_LayerStyle_Advance not installed"; exit 1; }

    # shellcheck disable=SC1090
    source "$VENV"
    pip install -q transformers==4.46.3

    # The model is an HF *Space*, not a regular repo. `hf` instead of git-lfs
    # because `apt install git-lfs` needs root and Paperspace has none.
    MODELS="$COMFY/models/Joy_caption"
    if [ ! -d "$MODELS/cgrkzexw-599808" ]; then
        mkdir -p "$MODELS" && cd "$MODELS"
        hf download fancyfeast/joy-caption-alpha-two --repo-type space \
            --local-dir cgrkzexw-599808
        # the download lands nested one level: flatten it
        if [ -d "cgrkzexw-599808/cgrkzexw-599808" ]; then
            mv cgrkzexw-599808/cgrkzexw-599808/* cgrkzexw-599808/
            rmdir cgrkzexw-599808/cgrkzexw-599808
        fi
    fi

    # Import SiglipVisionModel + use it instead of AutoModel
    sed -i 's/from transformers import AutoModel, AutoProcessor, AutoTokenizer, PreTrainedTokenizer, PreTrainedTokenizerFast, \\/from transformers import AutoModel, AutoProcessor, AutoTokenizer, PreTrainedTokenizer, PreTrainedTokenizerFast, SiglipVisionModel, \\/' "$TARGET"
    sed -i 's/clip_model = AutoModel.from_pretrained(CLIP_PATH).vision_model/clip_model = SiglipVisionModel.from_pretrained(CLIP_PATH)/g' "$TARGET"

    # Checkpoint key prefix. NOTE: this was INVERTED in May 2026 — current
    # transformers expects keys WITHOUT "vision_model.", older ones wanted it.
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
print(f"[joycaption] {n} block(s) patched" if n else
      "[joycaption] already patched (or upstream code changed)")
PY
    echo "✅ JoyCaption2 ready"
    ;;

*) usage ;;
esac
