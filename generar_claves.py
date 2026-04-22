"""
Ejercicio 1 — Claves (Fichas de Teoría 3ºGe).

Dos variantes:
 - Claves A: se da la CLAVE + una nota. El alumno escribe el
   nombre de la nota debajo del compás.
 - Claves B: se da la NOTA (la clave NO se dibuja, el espacio
   queda en blanco) + el nombre de la nota debajo. El alumno
   dibuja la clave antes.

8 compases en una línea, como Intervalos. Cada compás se
renderiza como un SVG independiente (una clave distinta por
compás) y se compone lado a lado en el PDF. Esto evita que
verovio introduzca "claves de cortesía" al final de cada
compás cuando cambia la clave entre compases.

Coherencia visual: mismo K_VB_PER_MM que escalas / TA+TV, así
el pentagrama y el tamaño de clave coinciden con el resto de
ejercicios.
"""

import argparse
import random
import io
import re
import verovio
from pathlib import Path
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader

import generar_intervalos as gi


# -----------------------------------------------------------------------------
# Catálogo de claves
# -----------------------------------------------------------------------------
# (etiqueta, sign, line, step_linea1, octave_linea1)
# step_linea1 / octave_linea1 = nota que se lee SOBRE la 1ª línea del
# pentagrama (la línea más grave) con esa clave.
CLAVES = [
    ("Sol en 2ª", "G", 2, "E", 4),
    ("Fa en 4ª",  "F", 4, "G", 2),
    ("Fa en 3ª",  "F", 3, "B", 2),
    ("Do en 1ª",  "C", 1, "C", 4),
    ("Do en 2ª",  "C", 2, "A", 3),
    ("Do en 3ª",  "C", 3, "F", 3),
    ("Do en 4ª",  "C", 4, "D", 3),
]

# Alias cortos para la hoja de soluciones / nombre de archivo.
CLAVE_ABREV = {
    "Sol en 2ª": "G2", "Fa en 4ª": "F4", "Fa en 3ª": "F3",
    "Do en 1ª": "C1", "Do en 2ª": "C2", "Do en 3ª": "C3", "Do en 4ª": "C4",
}

# Nombres de nota en solfeo español (para la etiqueta impresa en Claves B).
NOMBRE_ES = {
    "C": "Do", "D": "Re", "E": "Mi", "F": "Fa",
    "G": "Sol", "A": "La", "B": "Si",
}
# Usamos "b" (en lugar del carácter ♭) porque la Helvetica de reportlab
# no lleva el glifo U+266D. Convención solfeo española: Sib, Lab, Mib, etc.
ACC_ES = {-1: "b", 0: "", 1: "#"}


def nombre_nota_es(step, octave, alter):
    return f"{NOMBRE_ES[step]}{ACC_ES[alter]}{octave}"


def nombre_nota_corto(step, alter):
    """Nombre de la nota SIN número de octava (para la hoja de soluciones
    de Claves A: basta con 'Re', 'Sol#', etc.)."""
    return f"{NOMBRE_ES[step]}{ACC_ES[alter]}"


def position_to_note(position, step_linea1, octave_linea1):
    """position = 0 → línea 1; position = 8 → línea 5;
    position < 0 → por debajo de la línea 1 (ledger lines);
    position > 8 → por encima de la línea 5."""
    idx = gi.STEPS.index(step_linea1)
    raw = idx + position
    octave_shift, new_idx = divmod(raw, 7)
    return gi.STEPS[new_idx], octave_linea1 + octave_shift


# -----------------------------------------------------------------------------
# Sorteo
# -----------------------------------------------------------------------------
# Rango de posiciones: de -2 (1 línea adicional bajo el pentagrama) a +10
# (1 línea adicional sobre el pentagrama). 13 posiciones en total.
POSICIONES_VALIDAS = list(range(-2, 11))


def elegir_claves(n=8, seed=None, prob_alteracion=0.4, evitar_repes=True):
    """Devuelve lista de n tuplas (clave, posicion, step, octave, alter).

    - clave: tupla del catálogo CLAVES.
    - posicion: -2..10 (línea 1 = 0, línea 5 = 8).
    - step, octave, alter: nota resultante (alter ∈ {-1, 0, 1}).

    Restricciones:
      - Sin dobles alteraciones.
      - Sin enharmónicos raros (Fb, Cb, B#, E#).
      - Si `evitar_repes`, tratamos de que las 7 claves salgan al
        menos una vez antes de repetir (solo si n ≥ 7).
    """
    if seed is not None:
        random.seed(seed)

    # Baraja de claves: garantizamos que las 7 aparecen antes de repetir
    # (cuando n >= 7) para ejercitar todas las claves en una misma ficha.
    claves_pool = list(CLAVES)
    random.shuffle(claves_pool)
    claves_secuencia = []
    while len(claves_secuencia) < n:
        if evitar_repes and (n - len(claves_secuencia)) >= len(claves_pool):
            random.shuffle(claves_pool)
            claves_secuencia.extend(claves_pool)
        else:
            # Completamos al azar para el remanente
            claves_secuencia.append(random.choice(CLAVES))
    claves_secuencia = claves_secuencia[:n]

    resultado = []
    for clave in claves_secuencia:
        _, _sign, _line, s1, o1 = clave
        for _ in range(200):
            pos = random.choice(POSICIONES_VALIDAS)
            step, octave = position_to_note(pos, s1, o1)
            alter = 0
            if random.random() < prob_alteracion:
                cand = random.choice([-1, 1])
                if (step, cand) not in gi.RARAS:
                    alter = cand
            # Evita dobles (imposible por construcción, pero por seguridad):
            if abs(alter) > 1:
                continue
            if (step, alter) in gi.RARAS:
                continue
            resultado.append((clave, pos, step, octave, alter))
            break
        else:
            # Fallback defensivo
            resultado.append((clave, 2, s1, o1, 0))
    return resultado


# -----------------------------------------------------------------------------
# MusicXML: TODOS los compases en un mismo part. Cada compás declara su
# propia clef en <attributes>, de modo que cada nota se lee con su clave.
# Verovio NO añade clave de cortesía entre compases de un mismo sistema,
# así que este enfoque —idéntico al de intervalos— nos da un pentagrama
# único con clef distintas por compás. Renderizando todo junto en un solo
# PNG obtenemos el mismo tamaño de pentagrama que el resto de ejercicios.
# -----------------------------------------------------------------------------
def musicxml_ejercicio_claves(items):
    """MusicXML con n compases: cada compás trae su <clef>, una redonda y
    una barra sencilla al final (doble barra en el último)."""
    n = len(items)
    measures = []
    for i, (clave, _pos, step, octave, alter) in enumerate(items, start=1):
        _, sign, line, _, _ = clave
        alter_xml = f"<alter>{alter}</alter>" if alter else ""
        accidental_xml = ""
        if alter == 1:
            accidental_xml = "<accidental>sharp</accidental>"
        elif alter == -1:
            accidental_xml = "<accidental>flat</accidental>"

        attrs_base = ""
        if i == 1:
            # Primer compás: divisions + key + time (ocultos).
            attrs_base = """
        <divisions>4</divisions>
        <key><fifths>0</fifths></key>
        <time print-object="no"><beats>4</beats><beat-type>4</beat-type></time>"""
        attrs = f"""<attributes>{attrs_base}
        <clef><sign>{sign}</sign><line>{line}</line></clef>
      </attributes>"""

        nota = f"""
      <note>
        <pitch>
          <step>{step}</step>
          {alter_xml}
          <octave>{octave}</octave>
        </pitch>
        <duration>16</duration>
        <type>whole</type>
        {accidental_xml}
      </note>"""

        if i == n:
            barra = ('<barline location="right">'
                     '<bar-style>light-heavy</bar-style></barline>')
        else:
            barra = ('<barline location="right">'
                     '<bar-style>regular</bar-style></barline>')

        measures.append(f"""
    <measure number="{i}">{attrs}{nota}
      {barra}
    </measure>""")
    measures_xml = "".join(measures)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name></part-name></score-part>
  </part-list>
  <part id="P1">{measures_xml}
  </part>
</score-partwise>"""


# -----------------------------------------------------------------------------
# Render SVG -> PNG con K coherente
# -----------------------------------------------------------------------------
# Mismo K que escalas / TA+TV → pentagrama y clave del mismo tamaño.
K_VB_PER_MM = 90.06


# Puntos "apuntadores" para las claves de Do (glifo SMuFL E05C).
# Verovio dibuja el símbolo sin los 2 puntitos que flanquean la línea
# central (los que sí lleva el glifo E062 de Fa). Se los inyectamos a
# mano como <circle> a la derecha del glifo, a ±DOTS_DY de la Y del
# "translate" (que coincide con la Y de la línea donde se sitúa la clave).
# Coordenadas en unidades del viewBox interno de verovio.
# Separación entre líneas del pentagrama = 180 unidades.
_DO_DOT_DX = 440    # desplazamiento horizontal relativo al translate del <use>
_DO_DOT_DY = 55     # separación vertical respecto a la línea central
_DO_DOT_R = 24      # radio del punto


def _inyectar_puntos_claves_do(svg):
    """Añade 2 puntitos a cada clave de Do (glifo SMuFL E05C) para marcar
    la línea donde se sitúa. Los puntos van a la derecha del glifo,
    flanqueando verticalmente la línea central de la clave."""
    pattern = re.compile(
        r'(<g[^>]*class="clef"[^>]*>\s*<use[^>]*xlink:href="#E05C[^"]*"'
        r'[^/]*transform="translate\((\-?[\d\.]+),\s*(\-?[\d\.]+)\)'
        r'[^"]*"\s*/>\s*)(</g>)',
        re.DOTALL,
    )

    def repl(m):
        antes, x_str, y_str, cierre = m.groups()
        x = float(x_str)
        y = float(y_str)
        dx = x + _DO_DOT_DX
        dots = (
            f'<circle cx="{dx}" cy="{y - _DO_DOT_DY}" r="{_DO_DOT_R}" '
            f'fill="currentColor"/>'
            f'<circle cx="{dx}" cy="{y + _DO_DOT_DY}" r="{_DO_DOT_R}" '
            f'fill="currentColor"/>'
        )
        return antes + dots + cierre

    return pattern.sub(repl, svg)


def _render_claves_png(items, png_path, ocultar_claves=False,
                        ancho_util_mm=160):
    """Renderiza TODOS los compases del ejercicio en UN SOLO PNG (igual
    que Intervalos). Devuelve `(centros_x, anclas_nota, iw, ih)`:

      - centros_x: lista de fracciones 0..1 (relativas al ancho del PNG)
        con el centro visual de cada compás (entre el final de la clave
        y la barra de cierre). Se usa en modo A para colocar la línea
        "______" y el nombre en rojo.
      - anclas_nota: fracciones 0..1 con la X del notehead de cada
        compás. Se usa en modo B para alinear la etiqueta bajo la nota.
      - iw, ih: tamaño en píxeles del PNG (para calcular el aspect ratio
        en la composición PDF).

    Si `ocultar_claves` es True, elimina del SVG los grupos
    `<g class="clef">...</g>` antes de rasterizar. El hueco horizontal
    queda reservado: el alumno dibuja la clave.
    """
    xml = musicxml_ejercicio_claves(items)
    n = len(items)

    tk = verovio.toolkit()
    tk.setOptions({
        "pageWidth": 2100, "pageHeight": 2970,
        "pageMarginTop": 20, "pageMarginBottom": 20,
        "pageMarginLeft": 20, "pageMarginRight": 20,
        "scale": 35,
        "spacingStaff": 8, "spacingSystem": 8,
        "spacingNonLinear": 0.6,
        "spacingLinear": 0.25,
        "adjustPageHeight": True, "adjustPageWidth": True,
        "barLineWidth": 0.3, "staffLineWidth": 0.2,
        "header": "none", "footer": "none",
    })
    tk.loadData(xml)
    tk.redoLayout()
    svg = tk.renderToSVG(1)

    # viewBox y page-margin
    vb_match = re.search(
        r'class="definition-scale"[^>]*viewBox="([\d\s\.\-]+)"', svg
    )
    vb_w = float(vb_match.group(1).split()[2]) if vb_match else 10000.0
    pm_match = re.search(
        r'class="page-margin"[^>]*transform="translate\((\-?[\d\.]+),\s*(\-?[\d\.]+)\)"',
        svg,
    )
    pm_x = float(pm_match.group(1)) if pm_match else 0.0

    # Barras — agrupamos las muy juntas (la doble final son 2 líneas)
    barras_raw = sorted(
        float(m.group(1))
        for m in re.finditer(r'class="barLine">\s*<path d="M(\-?[\d\.]+)\s', svg)
    )
    agrup = []
    for b in barras_raw:
        if agrup and abs(b - agrup[-1]) < 60:
            agrup[-1] = (agrup[-1] + b) / 2
        else:
            agrup.append(b)

    # Posición X de cada clave (una por compás, en el mismo orden).
    claves_x = [
        float(m.group(1))
        for m in re.finditer(
            r'class="clef">\s*<use [^>]*transform="translate\((\-?[\d\.]+),',
            svg,
        )
    ]
    ANCHO_CLEF = 500

    # Centros horizontales de cada compás dentro del viewBox.
    # Compás i: entre la CLAVE i (final) y la barra i.
    centros_x = []
    for i in range(n):
        x_clave_fin = (claves_x[i] + ANCHO_CLEF) if i < len(claves_x) else 0
        x_barra = agrup[i] if i < len(agrup) else vb_w
        centros_x.append((pm_x + (x_clave_fin + x_barra) / 2) / vb_w)

    # X del notehead de cada compás (1 por compás).
    notas_x_vb = [
        float(m.group(1))
        for m in re.finditer(
            r'class="notehead"[^>]*>\s*<use[^>]*transform="translate\((\-?[\d\.]+),',
            svg,
        )
    ]
    anclas_nota = [(pm_x + x) / vb_w for x in notas_x_vb]
    while len(anclas_nota) < n:
        anclas_nota.append(centros_x[len(anclas_nota)])

    # Puntitos en claves de Do
    svg = _inyectar_puntos_claves_do(svg)

    if ocultar_claves:
        # Quitar el GLIFO de cada clave (no su hueco en el layout).
        svg = re.sub(
            r'<g[^>]*class="clef"[^>]*>.*?</g>',
            '',
            svg,
            flags=re.DOTALL,
        )

    # Rasterizar al ancho útil con padding inferior (igual que intervalos)
    dpi = 300
    ancho_pix = int(ancho_util_mm / 25.4 * dpi)
    padding_inf_mm = 6
    padding_inf_px = int(padding_inf_mm / 25.4 * dpi)
    png_bytes = gi.svg_a_png_bytes(svg, ancho_pix)
    with Image.open(io.BytesIO(png_bytes)) as im_rgba:
        w0, h0 = im_rgba.size
        fondo = Image.new("RGB", (w0, h0 + padding_inf_px), (255, 255, 255))
        if im_rgba.mode == "RGBA":
            fondo.paste(im_rgba, (0, 0), mask=im_rgba.split()[3])
        else:
            fondo.paste(im_rgba, (0, 0))
        fondo.save(png_path, "PNG")

    img = ImageReader(str(png_path))
    iw, ih = img.getSize()
    return centros_x, anclas_nota, iw, ih


# -----------------------------------------------------------------------------
# Composición PDF: 8 compases en una línea
# -----------------------------------------------------------------------------
def dibujar_en_canvas(c, x_ini, y_top, items, modo, num_enunciado,
                       out_pdf_path, ancho_util_mm=160, modo_solucion=False):
    """Dibuja el ejercicio de Claves en `c` a partir de `y_top`.
    Devuelve `y_bottom`.

    Arquitectura idéntica a Intervalos: UN SOLO PNG con todos los
    compases en el mismo sistema. Así el pentagrama tiene exactamente
    la misma pinta (altura, grosor de línea) que el resto de ejercicios
    y los compases quedan uniformes, sin el efecto "chapuza" de
    componer PNGs individuales con ratios distintos.

    - modo "A": clave visible, línea "______" bajo cada compás
      (nombre en rojo sobre la línea en modo solución).
    - modo "B": clave oculta, etiqueta con el nombre de la nota bajo
      el notehead. Sin octava ("Sib", "Re", "Sol#"...).
    """
    out_pdf_path = Path(out_pdf_path)
    png_path = out_pdf_path.with_name(out_pdf_path.stem + "_cl.png")

    centros_x, anclas_nota, iw, ih = _render_claves_png(
        items, png_path,
        ocultar_claves=(modo == "B"),
        ancho_util_mm=ancho_util_mm,
    )

    ancho_pdf = ancho_util_mm * mm
    alto_pdf = ancho_pdf * ih / iw

    c.setFont("Helvetica-Bold", 12)
    # En la ficha siempre se imprime "Claves" a secas — la distinción
    # A/B queda solo en el CLI / nombre de archivo.
    c.drawString(x_ini, y_top, f"{num_enunciado}. Claves")

    y_img = y_top - 6 * mm - alto_pdf
    c.drawImage(
        ImageReader(str(png_path)), x_ini, y_img,
        width=ancho_pdf, height=alto_pdf,
    )

    # Etiquetas: dentro del padding inferior del PNG (2 mm por encima
    # del borde inferior), como hace intervalos. Así quedan pegadas al
    # compás sin pisar la línea inferior del pentagrama.
    y_label = y_img + 2 * mm
    c.setFont("Helvetica-Oblique", 10)

    # Fallback si la extracción de posiciones falla: reparto uniforme.
    if len(centros_x) != len(items):
        margen_clave_pct = 0.085
        x_start_frac = margen_clave_pct
        x_end_frac = 1.0 - 0.012
        paso = (x_end_frac - x_start_frac) / len(items)
        centros_x = [x_start_frac + paso * (i + 0.5)
                     for i in range(len(items))]
    if len(anclas_nota) != len(items):
        anclas_nota = list(centros_x)

    for idx, (clave, _pos, step, octave, alter) in enumerate(items):
        if modo == "A":
            x_centro = x_ini + ancho_pdf * centros_x[idx]
            # Línea del alumno SIEMPRE (también en modo solución).
            c.setFillColorRGB(0, 0, 0)
            c.drawCentredString(x_centro, y_label, "______")
            if modo_solucion:
                c.saveState()
                c.setFillColorRGB(1, 0, 0)
                c.drawCentredString(
                    x_centro, y_label + 0.6 * mm,
                    nombre_nota_corto(step, alter),
                )
                c.restoreState()
        else:
            # Claves B: etiqueta con el NOMBRE de la nota SIN octava
            # (solo "Sib", "Re", "Sol#"...). Convención fijada por Iago.
            x_nota = x_ini + ancho_pdf * anclas_nota[idx]
            c.drawCentredString(
                x_nota, y_label,
                nombre_nota_corto(step, alter),
            )

    return y_label - 2 * mm


def componer_pdf_claves(items, modo, numero_ficha, out_pdf, num_enunciado=1,
                         modo_solucion=False):
    """Genera un PDF de una hoja con 8 compases de claves."""
    out_pdf = Path(out_pdf)
    c = canvas.Canvas(str(out_pdf), pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width / 2, height - 25 * mm, f"Ficha {numero_ficha}")
    c.setFont("Helvetica", 12)
    c.drawString(25 * mm, height - 35 * mm, "Nombre  _________________________")
    c.drawRightString(width - 25 * mm, height - 35 * mm, "Nota  _______")

    dibujar_en_canvas(
        c, 25 * mm, height - 55 * mm, items, modo, num_enunciado,
        out_pdf_path=out_pdf, modo_solucion=modo_solucion,
    )

    c.showPage()
    c.save()


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modo", choices=["A", "B"], default="A",
                    help="A: clave visible, alumno escribe nombre; "
                         "B: clave oculta, alumno dibuja la clave")
    ap.add_argument("--n", type=int, default=3, help="cuántas fichas")
    args = ap.parse_args()

    out_dir = Path("/sessions/elegant-busy-goldberg/mnt/outputs")
    out_dir.mkdir(parents=True, exist_ok=True)

    for i in range(1, args.n + 1):
        seed = (3000 if args.modo == "A" else 4000) + i
        items = elegir_claves(n=8, seed=seed)

        pdf_path = out_dir / f"prototipo_ficha_{i}_ej1{args.modo.lower()}.pdf"
        print(f"Generando {pdf_path.name} (modo {args.modo}) con:")
        for clave, pos, s, o, a in items:
            ab = CLAVE_ABREV[clave[0]]
            print(f"   · {ab} pos={pos:+d} → {nombre_nota_es(s, o, a)}")
        componer_pdf_claves(items, args.modo, i, pdf_path)

    print("\nListo")


if __name__ == "__main__":
    main()
