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

## Convenciones por ejercicio (NO PERDER)

Notas fijas de diseño que Iago ha decidido. Si se tocan los módulos,
respetar estas reglas o cambiarlas con intención:

- **Claves A** (clave visible, alumno escribe nombre):
  - Etiqueta solución: nombre SIN octava ("Re", "Sol#"...).
  - Barras de compás sencillas entre compases, doble barra al final.
  - El ejercicio se estira al ancho útil completo (como intervalos).

- **Claves B** (clave oculta, alumno dibuja clave):
  - Etiqueta impresa SIN octava ("Sib", "Re", "Sol#"...). NUNCA con
    el numerito de octava.
  - Mismas reglas de barras y ancho que Claves A.

- **Intervalos A** (dos notas por compás, alumno escribe el intervalo):
  - Etiqueta solución: solo el nombre ("4J", "6m"...) sin asc/desc
    (la dirección es visible en la partitura).

- **Intervalos B** (una nota + etiqueta, alumno dibuja la respuesta):
  - Etiqueta SIEMPRE con dirección: "4J asc", "6m desc", etc.
  - Sin la dirección el alumno no sabe si dibujar arriba o abajo.

- **Tonalidades + Armaduras + Tonos vecinos**: bloque fijo, cuenta como
  3 ejercicios en el contador.

- **Dictado**: bloque fijo al final de la ficha, no seleccionable. Si
  no cabe en la última página, salta a página nueva.
