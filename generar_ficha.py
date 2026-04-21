"""
Orquestador de ficha — selector de ejercicios extensible.

`componer_ficha` recibe una lista de ids de ejercicios activos (ver
registro `EJERCICIOS` más abajo) y dibuja solo esos, en el orden en
que aparecen en el registro, con salto de página automático.

Para añadir un nuevo ejercicio en el futuro:
  1. Crear un módulo `generar_xxx.py` con una función
     `dibujar_en_canvas(c, x, y, ..., num_enunciado, out_pdf_path,
     ancho_util_mm, modo_solucion)` que devuelva y_bottom.
  2. Importarlo aquí.
  3. Escribir una función _dibujar_xxx(...) pequeña que haga el
     sorteo y llame a `dibujar_en_canvas`.
  4. Añadir una entrada en el registro `EJERCICIOS`.
  El selector de la UI y `componer_ficha` lo recogen automáticamente.
"""

import argparse
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

import generar_intervalos as gi
import generar_claves as gc
import generar_tonalidades_armaduras as gtav
import generar_semitonos as gs
import generar_acordes as ga
import generar_grados as gg
import generar_qihe as gq
import generar_enarmonias as gen
import generar_escalas as ges


OUT_DIR = Path("/sessions/elegant-busy-goldberg/mnt/outputs")

# Márgenes
MARGEN_LAT_MM = 25
ANCHO_UTIL_MM = 160
GAP_EJ_MM = 8

# Salto de página automático: si al terminar un ejercicio quedamos por
# debajo de este umbral (desde el fondo), rompemos antes del siguiente.
MARGEN_INF_MM = 30


# -----------------------------------------------------------------------------
# Cabeceras de página
# -----------------------------------------------------------------------------
def _dibujar_cabecera(c, titulo):
    """Cabecera inicial: título grande + campos Nombre/Nota."""
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
    return height - 42 * mm


def _dibujar_cabecera_simple(c, titulo):
    """Cabecera reducida para páginas interiores."""
    width, height = A4
    c.setFont("Helvetica-Oblique", 9)
    c.drawRightString(width - MARGEN_LAT_MM * mm, height - 12 * mm, titulo)
    return height - 20 * mm


# -----------------------------------------------------------------------------
# Dictado — bloque FIJO al final, no aparece en el selector. 4 pentagramas
# vacíos (2 pares) con "Dictado" como rótulo.
# -----------------------------------------------------------------------------
DICT_SEP_LINEAS_MM = 180.0 / 90.06
ALTO_DICTADO_MM = 72


def _dibujar_pentagrama_vacio(c, x_ini, y_top_linea1, ancho_util_mm=160,
                              grosor=0.3):
    c.setLineWidth(grosor)
    for i in range(5):
        y = y_top_linea1 - i * DICT_SEP_LINEAS_MM * mm
        c.line(x_ini, y, x_ini + ancho_util_mm * mm, y)
    return y_top_linea1 - 4 * DICT_SEP_LINEAS_MM * mm


def _dibujar_dictado(c, x_ini, y_top, ancho_util_mm=160):
    """Dictado: título + 2 pares de pentagramas vacíos.
    Devuelve y_bottom."""
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x_ini, y_top, "Dictado")

    gap_dentro_par = 8
    gap_entre_pares = 14
    margen_sup = 4
    y_actual = y_top - (5 + margen_sup) * mm
    for par_idx in range(2):
        for penta_idx in range(2):
            y_linea5 = _dibujar_pentagrama_vacio(
                c, x_ini, y_actual, ancho_util_mm=ancho_util_mm,
            )
            if penta_idx == 0:
                y_actual = y_linea5 - gap_dentro_par * mm
            else:
                y_actual = y_linea5
        if par_idx == 0:
            y_actual -= gap_entre_pares * mm
    return y_actual


# -----------------------------------------------------------------------------
# Dispatchers: uno por cada ejercicio disponible.
# Todos tienen la misma firma:
#   (c, x, y_top, seed, num, out_pdf, ancho_util_mm, modo_solucion) -> y_bottom
# -----------------------------------------------------------------------------
def _dibujar_claves(c, x, y, seed, num, out_pdf, ancho, sol, modo):
    items = gc.elegir_claves(n=8, seed=seed)
    return gc.dibujar_en_canvas(
        c, x, y, items, modo=modo, num_enunciado=num,
        out_pdf_path=out_pdf, ancho_util_mm=ancho, modo_solucion=sol,
    )


def _dibujar_claves_a(c, x, y, seed, num, out_pdf, ancho, sol):
    return _dibujar_claves(c, x, y, seed, num, out_pdf, ancho, sol, modo="A")


def _dibujar_claves_b(c, x, y, seed, num, out_pdf, ancho, sol):
    return _dibujar_claves(c, x, y, seed, num, out_pdf, ancho, sol, modo="B")


def _dibujar_intervalos(c, x, y, seed, num, out_pdf, ancho, sol, modo):
    if modo == "A":
        lista = gi.elegir_intervalos_a(n=8, seed=seed)
    else:
        lista = gi.elegir_intervalos(n=8, seed=seed)
    return gi.dibujar_en_canvas(
        c, x, y, lista, modo=modo, num_enunciado=num,
        out_pdf_path=out_pdf, ancho_util_mm=ancho, modo_solucion=sol,
    )


def _dibujar_intervalos_a(c, x, y, seed, num, out_pdf, ancho, sol):
    return _dibujar_intervalos(c, x, y, seed, num, out_pdf, ancho, sol, "A")


def _dibujar_intervalos_b(c, x, y, seed, num, out_pdf, ancho, sol):
    return _dibujar_intervalos(c, x, y, seed, num, out_pdf, ancho, sol, "B")


def _dibujar_tonalidades(c, x, y, seed, num, out_pdf, ancho, sol):
    ton_f, arm = gtav.elegir_tonalidades(n_ton=2, n_arm=2, seed=seed)
    tonica_tv = gtav.elegir_tonica_tonos_vecinos(
        excluir_fifths=set(ton_f) | {a[1] for a in arm},
        seed=seed + 1000,
    )
    return gtav.dibujar_en_canvas(
        c, x, y, ton_f, arm, tonica_tv,
        num_tonalidades=num, num_armaduras=num + 1, num_tonos_vecinos=num + 2,
        out_pdf_path=out_pdf, ancho_util_mm=ancho, modo_solucion=sol,
    )


def _dibujar_semitonos(c, x, y, seed, num, out_pdf, ancho, sol):
    ident, comp = gs.elegir_semitonos(seed=seed)
    return gs.dibujar_en_canvas(
        c, x, y, ident, comp, num_enunciado=num,
        out_pdf_path=out_pdf, ancho_util_mm=ancho, modo_solucion=sol,
    )


def _dibujar_acordes(c, x, y, seed, num, out_pdf, ancho, sol):
    ident, comp = ga.elegir_acordes(seed=seed, prob_doble=0.10)
    return ga.dibujar_en_canvas(
        c, x, y, ident, comp, num_enunciado=num,
        out_pdf_path=out_pdf, ancho_util_mm=ancho, modo_solucion=sol,
    )


def _dibujar_grados(c, x, y, seed, num, out_pdf, ancho, sol):
    items = gg.elegir_grados(seed=seed)
    return gg.dibujar_en_canvas(
        c, x, y, items, num_enunciado=num,
        out_pdf_path=out_pdf, ancho_util_mm=ancho, modo_solucion=sol,
    )


def _dibujar_qihe(c, x, y, seed, num, out_pdf, ancho, sol):
    item = gq.elegir_qihe(seed=seed)
    return gq.dibujar_en_canvas(
        c, x, y, item, num_enunciado=num,
        out_pdf_path=out_pdf, ancho_util_mm=ancho, modo_solucion=sol,
    )


def _dibujar_enarmonias(c, x, y, seed, num, out_pdf, ancho, sol):
    items = gen.elegir_enarmonias(seed=seed)
    return gen.dibujar_en_canvas(
        c, x, y, items, num_enunciado=num,
        out_pdf_path=out_pdf, ancho_util_mm=ancho, modo_solucion=sol,
    )


def _dibujar_escalas_men(c, x, y, seed, num, out_pdf, ancho, sol):
    lista = ges.elegir_escalas(seed=seed)
    return ges.dibujar_en_canvas(
        c, x, y, lista, num_enunciado=num,
        out_pdf_path=out_pdf, ancho_util_mm=ancho, modo_solucion=sol,
    )


# -----------------------------------------------------------------------------
# Registro extensible de ejercicios
# -----------------------------------------------------------------------------
# Cada entrada:
#   id:          identificador único (usado por la UI y persistencia).
#   nombre:      etiqueta que verá el usuario en el selector.
#   disponible:  False para ejercicios en construcción ("próximamente").
#   fija:        True si no se puede desmarcar en la UI (tonalidades).
#   fn:          dispatcher (o None si disponible=False).
#
# Cómo añadir un ejercicio nuevo (p. ej. "Escalas hexátonas"):
#   1. Crear generar_hexatonas.py con `elegir_hexatonas(seed)` y
#      `dibujar_en_canvas(c, x, y, items, num_enunciado, out_pdf_path,
#      ancho_util_mm, modo_solucion) -> y_bottom`.
#   2. Importarlo arriba (`import generar_hexatonas as ghx`).
#   3. Escribir un dispatcher `_dibujar_hexatonas` (8 líneas).
#   4. Añadir UNA entrada en EJERCICIOS.
#   El selector de la UI lo recoge automáticamente.
EJERCICIOS = [
    {"id": "claves_a",     "nombre": "Claves (A)",
     "disponible": True,  "fija": False, "n_numeros": 1,
     "fn": _dibujar_claves_a},
    {"id": "claves_b",     "nombre": "Claves (B)",
     "disponible": True,  "fija": False, "n_numeros": 1,
     "fn": _dibujar_claves_b},
    {"id": "intervalos_a", "nombre": "Intervalos (A)",
     "disponible": True,  "fija": False, "n_numeros": 1,
     "fn": _dibujar_intervalos_a},
    {"id": "intervalos_b", "nombre": "Intervalos (B)",
     "disponible": True,  "fija": False, "n_numeros": 1,
     "fn": _dibujar_intervalos_b},
    {"id": "acordes",      "nombre": "Acordes",
     "disponible": True,  "fija": False, "n_numeros": 1,
     "fn": _dibujar_acordes},
    {"id": "tonalidades",
     "nombre": "Tonalidades + Armaduras + Tonos vecinos",
     "disponible": True,  "fija": True,  "n_numeros": 3,
     "fn": _dibujar_tonalidades},
    {"id": "grados",       "nombre": "Grados",
     "disponible": True,  "fija": False, "n_numeros": 1,
     "fn": _dibujar_grados},
    {"id": "qihe",         "nombre": "QIHE",
     "disponible": True,  "fija": False, "n_numeros": 1,
     "fn": _dibujar_qihe},
    {"id": "escalas_men",  "nombre": "Escalas menores",
     "disponible": True,  "fija": False, "n_numeros": 1,
     "fn": _dibujar_escalas_men},
    {"id": "enarmonias",   "nombre": "Enarmonías",
     "disponible": True,  "fija": False, "n_numeros": 1,
     "fn": _dibujar_enarmonias},
    {"id": "semitonos",    "nombre": "Semitono diatónico y cromático",
     "disponible": True,  "fija": False, "n_numeros": 1,
     "fn": _dibujar_semitonos},
]


def ejercicios_disponibles():
    """Lista de ejercicios que se pueden seleccionar en la UI."""
    return [e for e in EJERCICIOS if e["disponible"]]


def ids_fijos():
    """Ids que deben estar siempre marcados (no desmarcables)."""
    return {e["id"] for e in EJERCICIOS if e.get("fija")}


def ids_por_defecto():
    """Ids marcados por defecto al abrir la UI.

    Suman 10 "ejercicios" totales (contando que Tonalidades+Armaduras+
    Tonos vecinos son 3 en uno): 7 opcionales + el fijo que vale 3.
    El usuario puede cambiar la selección después."""
    return {
        "claves_a",
        "intervalos_a",
        "acordes",
        "tonalidades",     # fijo, vale 3
        "grados",
        "qihe",
        "enarmonias",
        "semitonos",
    }


# -----------------------------------------------------------------------------
# Composición de la ficha
# -----------------------------------------------------------------------------
def componer_ficha(numero_ficha, out_pdf, seed_base=50000,
                   modo_solucion=False, ejercicios_activos=None):
    """Genera la ficha en PDF.

    ejercicios_activos: lista de ids (o None → ids_por_defecto()). El
    orden del registro EJERCICIOS determina el orden de dibujo.
    """
    if ejercicios_activos is None:
        ejercicios_activos = ids_por_defecto()
    ejercicios_activos = set(ejercicios_activos)

    out_pdf = Path(out_pdf)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(out_pdf), pagesize=A4)

    if modo_solucion:
        titulo = f"Ficha {numero_ficha} — Solución"
        titulo_p2 = f"Ficha {numero_ficha} — Solución (cont.)"
    else:
        titulo = f"Ficha {numero_ficha}"
        titulo_p2 = f"Ficha {numero_ficha} (cont.)"

    # Filtrado en el orden del registro
    a_dibujar = [
        e for e in EJERCICIOS
        if e["disponible"] and e["id"] in ejercicios_activos
    ]

    y_actual = _dibujar_cabecera(c, titulo)
    num_enunciado = 1

    for i, ej in enumerate(a_dibujar):
        # Salto de página si lo que queda por dibujar se arriesga a
        # salir del folio. Heurística: margen inferior mínimo en mm.
        if y_actual / mm < MARGEN_INF_MM:
            c.showPage()
            y_actual = _dibujar_cabecera_simple(c, titulo_p2)

        y_actual = ej["fn"](
            c, MARGEN_LAT_MM * mm, y_actual,
            seed_base + 100 * (i + 1), num_enunciado,
            out_pdf, ANCHO_UTIL_MM, modo_solucion,
        )
        num_enunciado += ej.get("n_numeros", 1)
        y_actual -= GAP_EJ_MM * mm

    # Dictado FIJO al fondo de la última página. Si no cabe, nueva página.
    y_top_dictado_ideal = ALTO_DICTADO_MM * mm + 15 * mm
    if y_actual < y_top_dictado_ideal:
        c.showPage()
        y_actual = _dibujar_cabecera_simple(c, titulo_p2)

    # Colocar el dictado pegado al fondo si cae espacio libre, o
    # justo debajo del último ejercicio si no.
    y_top_dictado = max(y_top_dictado_ideal, min(y_actual, 88 * mm))
    if y_top_dictado > y_actual:
        y_top_dictado = y_actual
    _dibujar_dictado(
        c, MARGEN_LAT_MM * mm, y_top_dictado, ancho_util_mm=ANCHO_UTIL_MM,
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
