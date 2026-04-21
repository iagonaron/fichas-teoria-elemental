"""
Fichas de Teoría 3ºGe — Generador web
=====================================

App Streamlit para generar en un clic las versiones Alumno y Solución
de una ficha completa (10 ejercicios + Dictado).

Uso local:
    pip install -r requirements.txt
    streamlit run app.py

Despliegue gratuito en Streamlit Community Cloud:
    https://share.streamlit.io  → "Deploy an app" → repo de GitHub.
"""

import io
import tempfile
from pathlib import Path
page_title="Fichas de Teoría Elemental",
import streamlit as st

# Los módulos generar_*.py viven al lado de este archivo.
import generar_ficha as gfi st.title("Fichas de Teoría Elemental")


st.set_page_config(
    page_title="Fichas de Teoría 3ºGe",
    page_icon="🎼",
    layout="centered",
)

st.title("Fichas de Teoría 3ºGe")
st.caption("Generador de fichas para el Conservatorio de A Coruña.")

# ---------------------------------------------------------------------------
# Parámetros
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Generación
# ---------------------------------------------------------------------------
def _gen_pdf_bytes(numero_ficha: int, seed_base: int,
                   modo_solucion: bool) -> bytes:
    """Genera el PDF en un fichero temporal y devuelve sus bytes."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / (
            "solucion.pdf" if modo_solucion else "alumno.pdf"
        )
        gfi.componer_ficha(
            numero_ficha=numero_ficha,
            out_pdf=out,
            seed_base=seed_base,
            modo_solucion=modo_solucion,
        )
        return out.read_bytes()


if generar:
    with st.spinner("Generando fichas…"):
        try:
            pdf_alumno = _gen_pdf_bytes(
                int(numero), int(seed), modo_solucion=False,
            )
            pdf_solucion = _gen_pdf_bytes(
                int(numero), int(seed), modo_solucion=True,
            )
        except Exception as e:
            st.error(f"Error generando la ficha: {e}")
            st.stop()

    st.success("Listo. Descarga debajo los dos PDFs.")

    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            label="Descargar Alumno",
            data=pdf_alumno,
            file_name=f"Ficha {numero} — Alumno.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    with c2:
        st.download_button(
            label="Descargar Solución",
            data=pdf_solucion,
            file_name=f"Ficha {numero} — Solución.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

    # Previsualización rápida (página 1 del alumno)
    with st.expander("Vista previa (página 1 — Alumno)"):
        try:
            from pdf2image import convert_from_bytes
            imgs = convert_from_bytes(pdf_alumno, dpi=110, first_page=1,
                                      last_page=1)
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
