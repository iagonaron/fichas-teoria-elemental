"""
Fichas de Teoría Elemental — Generador web
=====================================

App Streamlit para generar en un clic las versiones Alumno y Solución
de una ficha. El usuario elige qué ejercicios incluir; el registro
está definido en generar_ficha.EJERCICIOS, por lo que añadir un nuevo
tipo en el futuro solo requiere tocar ese módulo.
"""

import io
import random
import tempfile
from pathlib import Path

import streamlit as st

# Configurar verovio para encontrar sus fuentes (Bravura, Leipzig, etc.).
# En Streamlit Cloud el resource path por defecto no funciona; lo ponemos
# explícito antes de importar cualquier módulo que cree un verovio.toolkit.
import os as _os
import verovio as _verovio

_vrv_data = _os.path.join(
    _os.path.dirname(_os.path.abspath(_verovio.__file__)), "data"
)
if _os.path.isdir(_vrv_data):
    _verovio.setDefaultResourcePath(_vrv_data)

# Los módulos generar_*.py viven al lado de este archivo.
import generar_ficha as gfi


st.set_page_config(
    page_title="Fichas de Teoría Elemental",
    page_icon="🎼",
    layout="centered",
)

st.title("Fichas de Teoría Elemental")
st.caption("Generador de fichas para el Conservatorio de A Coruña.")

# -----------------------------------------------------------------------------
# Estado persistente entre reruns (para que descargar un PDF no borre el otro)
# -----------------------------------------------------------------------------
DEFAULTS = {
    "pdf_alumno": None,
    "pdf_solucion": None,
    "ultimo_num": None,
    "ultimo_seed": None,
    "ultimos_ids": None,
}
for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)

# Selección de ejercicios (persistida)
for ej in gfi.ejercicios_disponibles():
    key = f"sel_{ej['id']}"
    # Por defecto, todos los disponibles están marcados.
    st.session_state.setdefault(key, True)


# -----------------------------------------------------------------------------
# Parámetros básicos
# -----------------------------------------------------------------------------
col1, col2 = st.columns(2)

with col1:
    numero = st.number_input(
        "Número de ficha", min_value=1, max_value=999, value=5, step=1,
        help="Aparece en el título de la ficha.",
    )

with col2:
    seed = st.number_input(
        "Semilla (seed)", min_value=1, max_value=999999, value=50000, step=1,
        help=(
            "Controla los sorteos. Dos fichas con la misma semilla son "
            "idénticas. Cámbiala para generar una ficha nueva."
        ),
    )


# -----------------------------------------------------------------------------
# Selector de ejercicios
# -----------------------------------------------------------------------------
st.markdown("### Ejercicios")

ejs = gfi.ejercicios_disponibles()
ids_opcionales = [e["id"] for e in ejs if not e.get("fija")]

# Botón aleatorio: propone 9 opcionales + el fijo (tonalidades).
# El usuario puede editar la selección después.
_b1, _b2 = st.columns([1, 1])
with _b1:
    if st.button("🎲 Proponer aleatorio", use_container_width=True):
        n_opcionales = min(9, len(ids_opcionales))
        elegidos = set(random.sample(ids_opcionales, n_opcionales))
        for eid in ids_opcionales:
            st.session_state[f"sel_{eid}"] = eid in elegidos
        st.rerun()
with _b2:
    if st.button("Marcar todos", use_container_width=True):
        for eid in ids_opcionales:
            st.session_state[f"sel_{eid}"] = True
        st.rerun()

cols_chk = st.columns(2)
for i, ej in enumerate(ejs):
    col = cols_chk[i % 2]
    key = f"sel_{ej['id']}"
    with col:
        if ej.get("fija"):
            # Siempre activo y bloqueado.
            st.checkbox(
                f"{ej['nombre']} — siempre incluido",
                value=True, disabled=True, key=f"disp_{ej['id']}",
            )
            st.session_state[key] = True
        else:
            st.checkbox(ej["nombre"], key=key)

# Resumen de ejercicios seleccionados
ids_activos = [
    ej["id"] for ej in ejs
    if st.session_state.get(f"sel_{ej['id']}", False) or ej.get("fija")
]
st.caption(f"Seleccionados: **{len(ids_activos)}** ejercicios")


# -----------------------------------------------------------------------------
# Generar
# -----------------------------------------------------------------------------
generar = st.button(
    "Generar ficha", type="primary", use_container_width=True,
    disabled=len(ids_activos) == 0,
)


def _gen_pdf_bytes(numero_ficha, seed_base, modo_solucion, ids):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / (
            "solucion.pdf" if modo_solucion else "alumno.pdf"
        )
        gfi.componer_ficha(
            numero_ficha=numero_ficha,
            out_pdf=out,
            seed_base=seed_base,
            modo_solucion=modo_solucion,
            ejercicios_activos=ids,
        )
        return out.read_bytes()


if generar:
    with st.spinner("Generando fichas…"):
        try:
            pdf_alumno = _gen_pdf_bytes(
                int(numero), int(seed), False, ids_activos,
            )
            pdf_solucion = _gen_pdf_bytes(
                int(numero), int(seed), True, ids_activos,
            )
        except Exception as e:
            st.error(f"Error generando la ficha: {e}")
            st.stop()

    # Guardar en session_state para que no se pierda al pulsar un
    # botón de descarga (que provoca rerun).
    st.session_state["pdf_alumno"] = pdf_alumno
    st.session_state["pdf_solucion"] = pdf_solucion
    st.session_state["ultimo_num"] = int(numero)
    st.session_state["ultimo_seed"] = int(seed)
    st.session_state["ultimos_ids"] = list(ids_activos)


# -----------------------------------------------------------------------------
# Zona de descargas (se muestra mientras haya PDFs en estado)
# -----------------------------------------------------------------------------
if st.session_state["pdf_alumno"] and st.session_state["pdf_solucion"]:
    num = st.session_state["ultimo_num"]
    seed_usada = st.session_state["ultimo_seed"]
    st.success(
        f"Ficha {num} (seed {seed_usada}) lista. Descarga los dos PDFs:"
    )

    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            label="⬇ Alumno",
            data=st.session_state["pdf_alumno"],
            file_name=f"Ficha {num} — Alumno.pdf",
            mime="application/pdf",
            use_container_width=True,
            key="dl_alumno",
        )
    with c2:
        st.download_button(
            label="⬇ Solución",
            data=st.session_state["pdf_solucion"],
            file_name=f"Ficha {num} — Solución.pdf",
            mime="application/pdf",
            use_container_width=True,
            key="dl_solucion",
        )

    with st.expander("Vista previa (página 1 — Alumno)"):
        try:
            from pdf2image import convert_from_bytes
            imgs = convert_from_bytes(
                st.session_state["pdf_alumno"],
                dpi=110, first_page=1, last_page=1,
            )
            st.image(imgs[0])
        except Exception as e:
            st.info(
                "Previsualización no disponible en este entorno "
                f"({e}). Descarga el PDF para verlo."
            )

st.markdown("---")
st.caption(
    "Proyecto personal de Iago. Los sorteos son reproducibles con la "
    "semilla. Si un ejercicio sale raro, prueba con otra semilla."
)
