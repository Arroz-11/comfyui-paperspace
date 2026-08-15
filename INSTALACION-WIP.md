# Instalación manual de ComfyUI en Paperspace — WIP

Lo corremos a mano paso a paso. Marcá `[x]` lo que funcione y anotá los errores al final.
Cuando esté validado, esto se convierte en el script y la guía final.

---

## 0. Crear el notebook

Hub (`localhost:8000`) → **New machine** → Advanced options:

| Campo | Valor |
|---|---|
| Machine | `Free-A6000` (si está lleno, `Free-A5000`) |
| Auto-shutdown | 6 |
| Container → Name | `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404` |
| Workspace | *(vacío — el repo todavía no existe)* |

**Container → Command:**

```
PIP_DISABLE_PIP_VERSION_CHECK=1 jupyter lab --allow-root --ip=0.0.0.0 --no-browser --ServerApp.trust_xheaders=True --ServerApp.disable_check_xsrf=False --ServerApp.allow_remote_access=True --ServerApp.allow_origin='*' --ServerApp.allow_credentials=True
```

- [ ] Arrancó y abre Jupyter

Después: en Jupyter → **File → New → Terminal**. Todo lo demás va ahí.

---

## 1. Ver qué tenemos

```bash
nvidia-smi && python --version && df -h /notebooks
```

- [ ] Se ve la GPU

---

## 2. Sistema (esto se borra en cada apagado)

```bash
apt-get update -qq && apt-get upgrade -y -qq && apt-get install -y -qq ffmpeg p7zip-full aria2 && apt-get clean && echo OK
```

- [ ] OK

---

## 3. Tema oscuro + paquetes globales

```bash
mkdir -p /root/.jupyter/lab/user-settings/@jupyterlab/apputils-extension && \
echo '{"theme": "JupyterLab Dark High Contrast"}' > /root/.jupyter/lab/user-settings/@jupyterlab/apputils-extension/themes.jupyterlab-settings && \
pip install -q -U pip && pip install -q tqdm ipywidgets huggingface_hub hf_transfer boto3 pytz && echo OK
```

- [ ] OK (el tema se ve al recargar Jupyter)

---

## 4. Cache de HuggingFace en zona persistente

```bash
echo 'export HF_HOME=/notebooks/huggingface_cache
export HF_HUB_CACHE=/notebooks/huggingface_cache
export HF_HUB_ENABLE_HF_TRANSFER=1' >> ~/.bashrc && source ~/.bashrc && mkdir -p $HF_HOME && echo OK
```

- [ ] OK

---

## 5. Clonar ComfyUI + limpiar hooks de git-lfs

```bash
cd /notebooks && git clone https://github.com/comfyanonymous/ComfyUI.git && cd ComfyUI && \
git config --unset-all core.hookspath 2>/dev/null; \
rm -f .git/hooks/post-checkout .git/hooks/post-commit .git/hooks/post-merge .git/hooks/pre-push; echo OK
```

- [ ] OK

---

## 6. venv + PyTorch

```bash
cd /notebooks/ComfyUI && python -m venv comfyenv && source comfyenv/bin/activate && \
pip install -U pip && pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
```

```bash
python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

- [ ] `True` en cuda.is_available ← si da False, parar acá

---

## 7. Dependencias + Manager

```bash
cd /notebooks/ComfyUI && pip install -r requirements.txt && \
cd custom_nodes && git clone https://github.com/Comfy-Org/ComfyUI-Manager.git && \
pip install -r ComfyUI-Manager/requirements.txt && echo OK
```

> `sqlalchemy`/`alembic` **no** hacen falta aparte: ya están en el `requirements.txt`
> de ComfyUI (verificado 15-ago). Los usa la base SQLite de assets — por eso en el
> arranque ves `Running upgrade -> 0001_assets`.

- [ ] OK

---

## 8. Arrancar

```bash
cd /notebooks/ComfyUI && source comfyenv/bin/activate && python main.py --listen --port 6006 --disable-metadata
```

- [ ] Dice que escucha en `0.0.0.0:6006`

Abrir: `https://tensorboard-$PAPERSPACE_FQDN` (el FQDN sale del Hub)

- [ ] Carga ComfyUI y corre el workflow default

---

## 9. Dejarlo en background

```bash
cd /notebooks/ComfyUI && mkdir -p /notebooks/logs && \
nohup bash -c "source comfyenv/bin/activate && python main.py --listen --port 6006 --disable-metadata" > /notebooks/logs/comfyui.log 2>&1 & \
sleep 5 && tail -5 /notebooks/logs/comfyui.log
```

- [ ] Sigue corriendo con la terminal cerrada

---

## 10. Prueba de fuego: apagar y prender

- [ ] Stop y Start desde el Hub
- [ ] `ls /notebooks/ComfyUI` → sigue estando ✅
- [ ] `ffmpeg -version` → NO está (confirma que hay que repetir el paso 2)
- [ ] Arranca de nuevo con el comando del paso 9

---

## Errores encontrados

| Paso | Error | Solución |
|---|---|---|
| | | |

## Para la 2ª pasada

- [ ] `python -m venv comfyenv --system-site-packages` → heredar torch del container y ahorrar el paso 6
- [ ] ¿SageAttention / xformers?
- [ ] ¿Qué custom nodes preinstalar además del Manager?
