"""
Orquestador de ficha completa (Ficha 5) — Fichas de Teoría 3ºGe.

Genera 2 PDFs A4 en /sessions/elegant-busy-goldberg/mnt/outputs:
  - "Alumno Ficha 5.pdf"   → versión para el alumno (huecos vacíos).
  - "Solución Ficha 5.pdf" → versión con las respuestas en ROJO.

Layout (10 ejercicios + Dictado):

  Página 1 (full):
    1. Claves A
    2. Intervalos A
    3+4+5. Tonalidades + Armaduras + Tonos vecinos (1 sistema)
    6. Semitonos
    7. Acordes

  Página 2:
    8. Grados
    9. QIHE
    10. Enarmonía
    --- media carilla ---
    Dictado (2 pares de pentagramas con ligera separación)

Cada módulo expone `dibujar_en_canvas(c, x_ini, y_top, ..., modo_solucion)`
que devuelve `y_bottom`. Aquí encadenamos los ejercicios con un gap
constante entre bloques y forzamos un saltopágina entre el 7 y el 8.
"""

import argparse
import io
import random
import re
from pathlib import Path

import verovio
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

import generar_intervalos as gi
import generar_claves as gc
import generar_tonalidades_armaduras as gtav
import generar_semitonos as gs
import generar_acordes as ga
import generar_grados as gg
import generar_qihe as gq
import generar_enarmonias as gen


OUT_DIR = Path("/sessions/elegant-busy-goldberg/mnt/outputs")

# Márgenes
MARGEN_LAT_MM = 25
ANCHO_UTIL_MM = 160

# Gap vertical entre ejercicios.
GAP_EJ_MM = 8


# -----------------------------------------------------------------------------
# Cabecera común a ambas páginas
# -----------------------------------------------------------------------------
def _dibujar_cabecera(c, titulo):
    """Cabecera (título + Nombre/Nota) en la parte superior de la página.
    Devuelve la Y de arranque para el primer ejercicio."""
    width, height = A4
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width / 2, height - 22 * mm, titulo)
    c.setFont("Helvetica", 11)
    c.drawString(
        MARGEN_LAT_MM * mm, height - 32 * mm,
        "Nombre  _________________________",
    )
    c.drawRightString(
        width - MARGEN_LAT_MM * mm, height - 32 * mm,
        "Nota  _______",
    )
    # El primer ejercicio arranca 42 mm por debajo del top.
    return height - 42 * mm


def _dibujar_cabecera_simple(c, titulo):
    """Cabecera reducida para páginas interiores: solo título pequeño.
    Devuelve la Y de arranque para el primer ejercicio de la página."""
    width, height = A4
    c.setFont("Helvetica-Oblique", 9)
    c.drawRightString(width - MARGEN_LAT_MM * mm, height - 12 * mm, titulo)
    return height - 20 * mm


# -----------------------------------------------------------------------------
# Dictado: 2 pares de pentagramas vacíos
# -----------------------------------------------------------------------------
# Separación entre líneas del pentagrama en los ejercicios: viene del
# viewBox de verovio (180 uds / K_VB_PER_MM ≈ 2.0 mm). Lo usamos también
# aquí para que los pentagramas del dictado tengan el MISMO alto de
# pentagrama que los de los ejercicios.
DICT_SEP_LINEAS_MM = 180.0 / 90.06


def _dibujar_pentagrama_vacio(c, x_ini, y_top_linea1, ancho_util_mm=160,
                                grosor=0.3):
    """Dibuja 5 líneas horizontales de largo `ancho_util_mm` a partir
    de la Y de la línea 1 (top). Sin clave, sin barras de compás.
    Devuelve la Y de la línea 5 (bottom)."""
    c.setLineWidth(grosor)
    for i in range(5):
        y = y_top_linea1 - i * DICT_SEP_LINEAS_MM * mm
        c.line(x_ini, y, x_ini + ancho_util_mm * mm, y)
    return y_top_linea1 - 4 * DICT_SEP_LINEAS_MM * mm


def _dibujar_dictado(c, x_ini, y_top, out_pdf_path,
                      ancho_util_mm=160):
    """Título 'Dictado' + 2 pares de pentagramas.
    Pentagrama = 5 líneas horizontales sin clave ni barras. Mismo alto
    de pentagrama (4 × 2.0 mm = 8 mm) que los ejercicios de la ficha.
    2 pentagramas pegados (gap pequeño dentro del par) + gap mayor +
    otros 2 pentagramas (para que el alumno pase a limpio).

    Devuelve y_bottom.
    """
    # Título
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x_ini, y_top, "Dictado")

    alto_penta = 4 * DICT_SEP_LINEAS_MM   # mm
    gap_dentro_par = 8    # espacio cómodo dentro del par para escribir notas
    gap_entre_pares = 14  # separación CLARA entre los dos pares

    # Margen por encima de la línea 1 para que las notas altas con líneas
    # adicionales no se peguen al texto de arriba.
    margen_sup = 4   # mm
    y_actual = y_top - (5 + margen_sup) * mm
    for par_idx in range(2):
        for penta_idx in range(2):
            y_linea1 = y_actual
            y_linea5 = _dibujar_pentagrama_vacio(
                c, x_ini, y_linea1, ancho_util_mm=ancho_util_mm,
            )
            # Reset de color por si el stroke queda en otro.
            if penta_idx == 0:
                y_actual = y_linea5 - gap_dentro_par * mm
            else:
                y_actual = y_linea5
        if par_idx == 0:
            y_actual -= gap_entre_pares * mm

    return y_actual


# -----------------------------------------------------------------------------
# Composición de la ficha completa
# -----------------------------------------------------------------------------
def componer_ficha(numero_ficha, out_pdf, seed_base=50000,
                    modo_solucion=False):
    """Genera una ficha completa (10 ejercicios + dictado) en 2 páginas.

    `numero_ficha` aparece en el título.
    `seed_base` fija el sorteo para reproducibilidad. Cada ejercicio usa
    una seed distinta (seed_base + offset) para que al cambiar seed_base
    cambie TODA la ficha a la vez.
    """
    out_pdf = Path(out_pdf)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(out_pdf), pagesize=A4)

    if modo_solucion:
        titulo = f"Ficha {numero_ficha} — Solución"
        titulo_p2 = f"Ficha {numero_ficha} — Solución (cont.)"
    else:
        titulo = f"Ficha {numero_ficha}"
        titulo_p2 = f"Ficha {numero_ficha} (cont.)"

    # ---------- SORTEO DE DATOS (una vez, mismo para alumno y solución) ----------
    items_claves = gc.elegir_claves(n=8, seed=seed_base + 1)
    lista_intervalos = gi.elegir_intervalos_a(n=8, seed=seed_base + 2)
    ton_f, arm = gtav.elegir_tonalidades(
        n_ton=2, n_arm=2, seed=seed_base + 3,
    )
    tonica_tv = gtav.elegir_tonica_tonos_vecinos(
        excluir_fifths=set(ton_f) | {a[1] for a in arm},
        seed=seed_base + 4,
    )
    ident_sem, comp_sem = gs.elegir_semitonos(seed=seed_base + 5)
    ident_ac, comp_ac = ga.elegir_acordes(seed=seed_base + 6, prob_doble=0.10)
    items_grados = gg.elegir_grados(seed=seed_base + 7)
    item_qihe = gq.elegir_qihe(seed=seed_base + 8)
    items_enarm = gen.elegir_enarmonias(seed=seed_base + 9)

    # ---------- PÁGINA 1 ----------
    y_actual = _dibujar_cabecera(c, titulo)

    # Ej 1. Claves A
    y_actual = gc.dibujar_en_canvas(
        c, MARGEN_LAT_MM * mm, y_actual,
        items_claves, modo="A", num_enunciado=1,
        out_pdf_path=out_pdf, ancho_util_mm=ANCHO_UTIL_MM,
        modo_solucion=modo_solucion,
    )
    y_actual -= GAP_EJ_MM * mm

    # Ej 2. Intervalos A
    y_actual = gi.dibujar_en_canvas(
        c, MARGEN_LAT_MM * mm, y_actual,
        lista_intervalos, modo="A", num_enunciado=2,
        out_pdf_path=out_pdf, ancho_util_mm=ANCHO_UTIL_MM,
        modo_solucion=modo_solucion,
    )
    y_actual -= GAP_EJ_MM * mm

    # Ej 3+4+5. Tonalidades + Armaduras + Tonos vecinos (1 línea)
    y_actual = gtav.dibujar_en_canvas(
        c, MARGEN_LAT_MM * mm, y_actual,
        ton_f, arm, tonica_tv,
        num_tonalidades=3, num_armaduras=4, num_tonos_vecinos=5,
        out_pdf_path=out_pdf, ancho_util_mm=ANCHO_UTIL_MM,
        modo_solucion=modo_solucion,
    )
    y_actual -= GAP_EJ_MM * mm

    # Ej 6. Semitonos
    y_actual = gs.dibujar_en_canvas(
        c, MARGEN_LAT_MM * mm, y_actual,
        ident_sem, comp_sem, num_enunciado=6,
        out_pdf_path=out_pdf, ancho_util_mm=ANCHO_UTIL_MM,
        modo_solucion=modo_solucion,
    )
    y_actual -= GAP_EJ_MM * mm

    # Ej 7. Acordes
    y_actual = ga.dibujar_en_canvas(
        c, MARGEN_LAT_MM * mm, y_actual,
        ident_ac, comp_ac, num_enunciado=7,
        out_pdf_path=out_pdf, ancho_util_mm=ANCHO_UTIL_MM,
        modo_solucion=modo_solucion,
    )

    c.showPage()

    # ---------- PÁGINA 2 ----------
    y_actual = _dibujar_cabecera_simple(c, titulo_p2)

    # Ej 8. Grados
    y_actual = gg.dibujar_en_canvas(
        c, MARGEN_LAT_MM * mm, y_actual,
        items_grados, num_enunciado=8,
        out_pdf_path=out_pdf, ancho_util_mm=ANCHO_UTIL_MM,
        modo_solucion=modo_solucion,
    )
    y_actual -= GAP_EJ_MM * mm

    # Ej 9. QIHE
    y_actual = gq.dibujar_en_canvas(
        c, MARGEN_LAT_MM * mm, y_actual,
        item_qihe, num_enunciado=9,
        out_pdf_path=out_pdf, ancho_util_mm=ANCHO_UTIL_MM,
        modo_solucion=modo_solucion,
    )
    y_actual -= GAP_EJ_MM * mm

    # Ej 10. Enarmonía
    y_actual = gen.dibujar_en_canvas(
        c, MARGEN_LAT_MM * mm, y_actual,
        items_enarm, num_enunciado=10,
        out_pdf_path=out_pdf, ancho_util_mm=ANCHO_UTIL_MM,
        modo_solucion=modo_solucion,
    )
    # Dictado: empujado al fondo de la página para que se vea como
    # sección aparte. Calculamos una Y fija desde el borde inferior.
    # Alto total del bloque Dictado: título (~5 mm) + margen_sup (4 mm)
    # + 4 pentagramas (4 × 8 mm) + gaps (8 + 14 + 8 mm) ≈ 71 mm.
    # Con ~15 mm de margen inferior → y_top_dictado ≈ 86 mm.
    _, height = A4
    y_top_dictado = 88 * mm
    # Solo usamos la posición calculada si no se solapa con el ej 10;
    # en caso extremo, caemos al comportamiento anterior.
    if y_top_dictado < y_actual - GAP_EJ_MM * mm:
        y_actual = y_top_dictado
    else:
        y_actual -= (GAP_EJ_MM + 2) * mm

    # Dictado (bloque final, media carilla)
    _dibujar_dictado(
        c, MARGEN_LAT_MM * mm, y_actual,
        out_pdf_path=out_pdf, ancho_util_mm=ANCHO_UTIL_MM,
    )

    c.showPage()
    c.save()


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--num", type=int, default=5,
                    help="Número de la ficha (aparece en el título)")
    ap.add_argument("--seed", type=int, default=50000,
                    help="Semilla base (determinista)")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    pdf_alumno = OUT_DIR / f"Alumno Ficha {args.num}.pdf"
    pdf_solucion = OUT_DIR / f"Solución Ficha {args.num}.pdf"

    print(f"Generando {pdf_alumno.name}")
    componer_ficha(args.num, pdf_alumno,
                    seed_base=args.seed, modo_solucion=False)
    print(f"Generando {pdf_solucion.name}")
    componer_ficha(args.num, pdf_solucion,
                    seed_base=args.seed, modo_solucion=True)
    print("\nListo")


if __name__ == "__main__":
    main()
