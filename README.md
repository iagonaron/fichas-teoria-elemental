# Fichas de Teoría 3ºGe

Generador web de fichas para el Conservatorio de A Coruña.

## Local

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Despliegue gratuito (Streamlit Community Cloud)

1. Subir esta carpeta a un repo de GitHub.
2. Entrar en https://share.streamlit.io y conectar la cuenta de GitHub.
3. "Deploy an app" → seleccionar repo, rama `main`, fichero `app.py`.
4. Esperar 2 min. La app queda en `https://<usuario>-<repo>.streamlit.app`.

## Estructura

- `app.py` — interfaz Streamlit.
- `generar_*.py` — módulos de generación (un fichero por ejercicio).
- `requirements.txt` — dependencias Python.
- `packages.txt` — dependencias del sistema para Streamlit Cloud (poppler).
