# Actualización Fichas de Teoría — 22/04/2026

Instrucciones para llevar los cambios de hoy al repo `fichas-teoria-elemental` y que Streamlit Cloud los recoja.

## Archivos en esta carpeta

Los 7 archivos de esta carpeta deben reemplazar a los homónimos del repo. Ninguno es nuevo: todos existen ya en el repo, se trata de sobrescribir.

- `generar_claves.py` — reescrito: ahora usa 1 PNG único con los 8 compases (misma arquitectura que Intervalos). Pentagrama con el mismo alto que el resto de ejercicios, compases uniformes, barras sencillas entre compases y doble al final.
- `generar_intervalos.py` — modo B: la etiqueta incluye siempre la dirección ("4J asc", "6m desc").
- `README.md` — sección "Convenciones por ejercicio (NO PERDER)" documentando las reglas fijadas (claves sin octava, intervalos B con dirección, etc.).
- `app.py`, `generar_ficha.py`, `generar_escalas.py`, `generar_enarmonias.py` — cambios menores de sesiones anteriores que no recuerdo haber pusheado ya. Los incluyo por seguridad; si `git diff` dice que no hay cambios respecto al repo, ignóralos.

## Pasos

Asumo que tienes el repo clonado en algún sitio (por ejemplo `~/dev/fichas-teoria-elemental`). Ajusta la ruta si es otra.

### 1. Copiar los archivos al repo

```bash
cd ~/dev/fichas-teoria-elemental
cp /ruta/a/update_fichas_20260422/*.py .
cp /ruta/a/update_fichas_20260422/README.md .
```

(En macOS la carpeta descargada de Cowork suele quedar en `~/Downloads/update_fichas_20260422`.)

### 2. Comprobar qué ha cambiado

```bash
git status
git diff --stat
```

Deberías ver algo como:

```
  app.py                   | ...
  generar_claves.py        | ...
  generar_enarmonias.py    | ...
  generar_escalas.py       | ...
  generar_ficha.py         | ...
  generar_intervalos.py    | ...
  README.md                | ...
```

Si algún archivo no aparece en el diff, es que ya estaba idéntico en el repo: no pasa nada.

### 3. Probar en local (opcional pero recomendado)

```bash
pip install -r requirements.txt
streamlit run app.py
```

Genera una ficha y mira el ejercicio 1 (Claves): pentagrama del mismo alto que los demás, compases uniformes.

### 4. Commit + push

```bash
git add .
git commit -m "Claves: 1 PNG único + barras; Intervalos B: asc/desc; convenciones en README"
git push
```

### 5. Esperar el redeploy

Streamlit Cloud detecta el push y redespliega automáticamente en 1-2 min. Entra a la URL de la app y genera una ficha para confirmar.

## Si algo falla

- **Conflicto al hacer pull/push:** haz `git pull --rebase` primero, resuelve si hay conflictos, y vuelve a intentar el push.
- **El deploy falla en Streamlit Cloud:** mira los logs en la pestaña "Manage app" → "Logs". Normalmente un ImportError por dependencia que falta en `requirements.txt`.
- **La app arranca pero claves sigue saliendo mal:** fuerza el redeploy desde el panel de Streamlit Cloud ("Reboot app"). A veces cachea bytecode.
