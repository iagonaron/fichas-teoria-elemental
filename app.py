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
    "ultimo_titulo": None,
}
for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)

# Semilla inicial aleatoria para cada nueva sesión (cada vez que se abre
# la web). Una vez generada, el usuario puede cambiarla a mano o dejarla.
st.session_state.setdefault("seed_inicial", random.randint(1, 999999))

# Selección de ejercicios (persistida). Marca inicial = ids_por_defecto()
_ids_default = gfi.ids_por_defecto()
for ej in gfi.ejercicios_disponibles():
    key = f"sel_{ej['id']}"
    st.session_state.setdefault(key, ej["id"] in _ids_default)


# -----------------------------------------------------------------------------
# Parámetros básicos
# -----------------------------------------------------------------------------
es_examen = st.checkbox(
    "Ficha de examen",
    help=(
        "Si se marca, el título pasa a ser 'Examen de teoría' "
        "y los PDFs se llaman 'Alumno Examen de teoría.pdf' y "
        "'Solución Examen de teoría.pdf'. Se ignora el número de ficha."
    ),
)

col1, col2, col3 = st.columns([3, 3, 1])

with col1:
    numero = st.number_input(
        "Número de ficha", min_value=1, max_value=999, value=5, step=1,
        help="Aparece en el título de la ficha.",
        disabled=es_examen,
    )

with col2:
    seed = st.number_input(
        "Semilla (seed)", min_value=1, max_value=999999,
        value=st.session_state["seed_inicial"], step=1, key="seed_widget",
        help=(
            "Controla los sorteos. Dos fichas con la misma semilla son "
            "idénticas. Al abrir la web se genera una nueva al azar; "
            "puedes cambiarla a mano o pulsar el dado para otra."
        ),
    )

with col3:
    # Alineación visual con los number_input (que llevan label arriba).
    st.markdown("<div style='height:1.8em'></div>", unsafe_allow_html=True)
    if st.button("🎲", help="Nueva semilla al azar",
                 use_container_width=True):
        st.session_state["seed_inicial"] = random.randint(1, 999999)
        # Borra el widget para que tome el valor nuevo en el próximo render
        st.session_state.pop("seed_widget", None)
        st.rerun()


# -----------------------------------------------------------------------------
# Selector de ejercicios
# -----------------------------------------------------------------------------
st.markdown("### Ejercicios")

ejs = gfi.ejercicios_disponibles()
ids_opcionales = [e["id"] for e in ejs if not e.get("fija")]

# Botón aleatorio: propone 7 opcionales + el fijo (tonalidades vale 3)
# = 10 ejercicios en total. El usuario puede editar después.
_b1, _b2 = st.columns([1, 1])
with _b1:
    if st.button("🎲 Proponer aleatorio", use_container_width=True):
        n_opcionales = min(7, len(ids_opcionales))
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

# Resumen de ejercicios seleccionados. Tonalidades cuenta como 3 porque
# abarca Tonalidades + Armaduras + Tonos vecinos.
ids_activos = [
    ej["id"] for ej in ejs
    if st.session_state.get(f"sel_{ej['id']}", False) or ej.get("fija")
]
total_ejercicios = sum(
    ej.get("n_numeros", 1) for ej in ejs if ej["id"] in ids_activos
)
st.caption(
    f"Seleccionados: **{total_ejercicios}** ejercicios "
    f"(Tonalidades + Armaduras + Tonos vecinos cuentan como 3)"
)


# -----------------------------------------------------------------------------
# Generar
# -----------------------------------------------------------------------------
generar = st.button(
    "Generar ficha", type="primary", use_container_width=True,
    disabled=len(ids_activos) == 0,
)


def _gen_pdf_bytes(numero_ficha, seed_base, modo_solucion, ids,
                    titulo_override=None):
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
            titulo_override=titulo_override,
        )
        return out.read_bytes()


if generar:
    titulo_override = "Examen de teoría" if es_examen else None
    with st.spinner("Generando fichas…"):
        try:
            pdf_alumno = _gen_pdf_bytes(
                int(numero), int(seed), False, ids_activos,
                titulo_override=titulo_override,
            )
            pdf_solucion = _gen_pdf_bytes(
                int(numero), int(seed), True, ids_activos,
                titulo_override=titulo_override,
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
    st.session_state["ultimo_titulo"] = titulo_override  # None o "Examen..."


# -----------------------------------------------------------------------------
# Zona de descargas (se muestra mientras haya PDFs en estado)
# -----------------------------------------------------------------------------
if st.session_state["pdf_alumno"] and st.session_state["pdf_solucion"]:
    num = st.session_state["ultimo_num"]
    seed_usada = st.session_state["ultimo_seed"]
    titulo_ultimo = st.session_state.get("ultimo_titulo")

    if titulo_ultimo:
        etiqueta_msg = f"{titulo_ultimo} (seed {seed_usada}) lista."
        nombre_alumno = f"Alumno {titulo_ultimo}.pdf"
        nombre_solucion = f"Solución {titulo_ultimo}.pdf"
    else:
        etiqueta_msg = f"Ficha {num} (seed {seed_usada}) lista."
        nombre_alumno = f"Ficha {num} — Alumno.pdf"
        nombre_solucion = f"Ficha {num} — Solución.pdf"

    st.success(f"{etiqueta_msg} Descarga los dos PDFs:")

    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            label="⬇ Alumno",
            data=st.session_state["pdf_alumno"],
            file_name=nombre_alumno,
            mime="application/pdf",
            use_container_width=True,
            key="dl_alumno",
        )
    with c2:
        st.download_button(
            label="⬇ Solución",
            data=st.session_state["pdf_solucion"],
            file_name=nombre_solucion,
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
