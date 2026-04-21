"""
Fichas de Teoría Elemental — Generador web
=====================================

App Streamlit para generar en un clic las versiones Alumno y Solución
de una ficha completa (10 ejercicios + Dictado).
"""

import io
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
            "idénticas. Cambia la semilla para generar una ficha nueva."
        ),
    )

generar = st.button("Generar ficha", type="primary", use_container_width=True)


def _gen_pdf_bytes(numero_
