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
# MusicXML: dos enfoques disponibles.
#
# 1) `musicxml_ejercicio_claves`: TODOS los compases en un mismo part.
#    Histórico. Resuelve el bug "anchos desiguales". No se usa ya en la
#    composición final, queda como referencia.
#
# 2) `musicxml_un_compas_clave`: UN compás independiente. Lo usa la nueva
#    arquitectura "1 PNG por compás" (similar a Grados/QIHE/Acordes).
#    Permite controlar exactamente el layout de cada compás:
#      - Barra-izq visible en TODOS los compases (clave dentro del
#        compás efectivo, no como anacrusa).
#      - Padding oculto al inicio de B para empujar la nota a la derecha
#        sin que dispare el ancho del SISTEMA entero (que sí pasaba con
#        el enfoque 1).
#      - Puntitos a las claves de Do cada uno por separado.
# -----------------------------------------------------------------------------
def musicxml_un_compas_clave(clave, step, octave, alter,
                              es_primero=False, es_ultimo=False,
                              pad_izq=0):
    """MusicXML de UN compás con barra-izq (solo el primero) + clave +
    pad-oculto + nota visible + barra-der. Pensado para componer N PNGs
    lado a lado.

    La barra-izq solo aparece en el PRIMER compás del sistema; los
    demás compases comparten la barra-der del anterior como divisoria
    izquierda visual al yuxtaponerse.
    """
    _, sign, line, _, _ = clave
    alter_xml = f"<alter>{alter}</alter>" if alter else ""
    accidental_xml = ""
    if alter == 1:
        accidental_xml = "<accidental>sharp</accidental>"
    elif alter == -1:
        accidental_xml = "<accidental>flat</accidental>"

    silencio_oculto = (
        '<note print-object="no">'
        '<rest/><duration>16</duration><type>whole</type>'
        '</note>'
    )
    pad_xml = silencio_oculto * pad_izq
    beats_total = 4 * (pad_izq + 1)

    # OJO: NO usamos <barline location="left">. verovio la renderiza
    # DESPUÉS de la clave (entre clave y nota), no al borde izquierdo
    # del compás. La barra inicial del PRIMER compás se inyecta como
    # <path> en el SVG post-render (`_render_un_compas_clave`).
    if es_ultimo:
        barra_der = ('<barline location="right">'
                     '<bar-style>light-heavy</bar-style></barline>')
    else:
        barra_der = ('<barline location="right">'
                     '<bar-style>regular</bar-style></barline>')

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

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name></part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>4</divisions>
        <key><fifths>0</fifths></key>
        <time print-object="no"><beats>{beats_total}</beats><beat-type>4</beat-type></time>
        <clef><sign>{sign}</sign><line>{line}</line></clef>
      </attributes>
      {pad_xml}{nota}
      {barra_der}
    </measure>
  </part>
</score-partwise>"""


def musicxml_ejercicio_claves(items, pad_izq_per_compas=0):
    """MusicXML con n compases: cada compás trae su <clef>, una redonda y
    una barra sencilla al final (doble barra en el último).

    `pad_izq_per_compas`: nº de redondas ocultas insertadas al INICIO de
    cada compás, antes de la nota visible. Empuja la nota hacia la
    derecha del compás (usado en Claves B para dejar espacio donde el
    alumno escribe la clave). Por defecto 0 (la nota va centrada).

    El primer compás siempre lleva `<barline location="left">` para que
    tenga una barra de compás visible al inicio del sistema y la clave
    quede claramente DENTRO del compás efectivo (no como anacrusa).
    """
    n = len(items)
    measures = []
    beats_total = 4 * (pad_izq_per_compas + 1)
    silencio_oculto = (
        '<note print-object="no">'
        '<rest/><duration>16</duration><type>whole</type>'
        '</note>'
    )
    pad_xml = silencio_oculto * pad_izq_per_compas

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
            attrs_base = f"""
        <divisions>4</divisions>
        <key><fifths>0</fifths></key>
        <time print-object="no"><beats>{beats_total}</beats><beat-type>4</beat-type></time>"""
        attrs = f"""<attributes>{attrs_base}
        <clef><sign>{sign}</sign><line>{line}</line></clef>
      </attributes>"""

        # Barra izquierda visible SÓLO en el primer compás. En el resto,
        # la barra derecha del compás anterior ya hace ese papel.
        barra_izq = ""
        if i == 1:
            barra_izq = ('<barline location="left">'
                         '<bar-style>regular</bar-style></barline>')

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
    <measure number="{i}">{barra_izq}{attrs}{pad_xml}{nota}
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


def _render_un_compas_clave(xml, png_path, ocultar_clave=False,
                              spacing_linear=0.18, spacing_non_linear=0.55,
                              clave_rojo=False, barra_inicial=False):
    """Renderiza UN compás a PNG. Devuelve (vb_w_mm, iw, ih, ancla_nota_frac,
    staff_top_frac, staff_bot_frac).

    `staff_top_frac` / `staff_bot_frac`: fracciones 0..1 desde ARRIBA del
    PNG que marcan los bordes del pentagrama. Las usa `dibujar_en_canvas`
    para alinear los staffs de los 8 compases a la misma Y en el PDF
    aunque cada compás tenga un rango vertical distinto de notas.

    `ancla_nota_frac`: fracción 0..1 con la X (dentro del PNG) del
    notehead. Usado para alinear la etiqueta en Claves B.

    Si `ocultar_clave=True`, la clave se hace invisible con
    `visibility:hidden` (conserva el layout: el hueco queda donde el
    alumno escribe la clave).

    Spacings calibrados (con `scale=35`) para que el ANCHO TOTAL de
    los 8 compases yuxtapuestos quede cerca de 170 mm, lo que al
    estirar a 160 mm da factor ≈ 0.95x — el "tamaño estándar" que
    iguala a Semitonos.
      - Claves A (pad=0): 0.18/0.55 → 166 mm total, factor 0.97x.
      - Claves B (pad=2): 0.15/0.45 → 170 mm total, factor 0.94x.
    """
    tk = verovio.toolkit()
    tk.setOptions({
        "pageWidth": 2100, "pageHeight": 2970,
        "pageMarginTop": 20, "pageMarginBottom": 20,
        # Márgenes laterales a 0 para que los PNGs se yuxtapongan sin
        # huecos blancos entre compases (pentagrama continuo).
        "pageMarginLeft": 0, "pageMarginRight": 0,
        "scale": 35,
        "spacingStaff": 8, "spacingSystem": 8,
        "spacingNonLinear": spacing_non_linear,
        "spacingLinear": spacing_linear,
        "adjustPageHeight": True, "adjustPageWidth": True,
        "barLineWidth": 0.3, "staffLineWidth": 0.2,
        "header": "none", "footer": "none", "breaks": "none",
    })
    tk.loadData(xml)
    tk.redoLayout()
    svg = tk.renderToSVG(1)

    # ViewBox
    vb_match = re.search(
        r'class="definition-scale"[^>]*viewBox="([\d\s\.\-]+)"', svg
    )
    vb_w = float(vb_match.group(1).split()[2]) if vb_match else 10000.0
    vb_h = float(vb_match.group(1).split()[3]) if vb_match else 2000.0

    # Y de las líneas del pentagrama (formato `M0 Y L1774 Y` en el SVG).
    # IMPORTANTE: filtrar para quedarse SOLO con las 5 líneas del staff
    # (van de borde a borde del compás), no las "ledger lines" cortas
    # que verovio dibuja debajo/encima del staff para notas extremas.
    # Si no se filtra, las ledger lines mueven artificialmente el
    # `staff_top_frac` y los compases acaban desalineados verticalmente.
    staff_ys = []
    for m_path in re.finditer(
        r'<path d="M\s*([-\d.]+)\s+([-\d.]+)\s+L\s*([-\d.]+)\s+([-\d.]+)"',
        svg,
    ):
        x1, y1, x2, y2 = (float(g) for g in m_path.groups())
        if (abs(y1 - y2) < 1
                and x1 < 50
                and x2 > vb_w - 50):
            staff_ys.append(y1)
    if staff_ys and vb_h > 0:
        staff_top_frac = min(staff_ys) / vb_h
        staff_bot_frac = max(staff_ys) / vb_h
    else:
        staff_top_frac = 0.4
        staff_bot_frac = 0.6

    # Offset page-margin
    pm_match = re.search(
        r'class="page-margin"[^>]*transform="translate\((\-?[\d\.]+),\s*(\-?[\d\.]+)\)"',
        svg,
    )
    pm_x = float(pm_match.group(1)) if pm_match else 0.0

    # X del notehead (compás de 1 sola nota)
    nh_match = re.search(
        r'class="notehead"[^>]*>\s*<use[^>]*transform="translate\((\-?[\d\.]+),',
        svg,
    )
    if nh_match and vb_w > 0:
        nh_x = float(nh_match.group(1))
        ancla_nota_frac = (pm_x + nh_x) / vb_w
    else:
        ancla_nota_frac = 0.5

    # Puntitos a las claves de Do
    svg = _inyectar_puntos_claves_do(svg)

    # Ocultar la clave si se pide (preservando el layout)
    if ocultar_clave:
        svg = re.sub(
            r'(<g[^>]*class="clef"[^>]*)>',
            r'\1 style="visibility:hidden">',
            svg,
        )
    elif clave_rojo:
        # Pintar la clave (glifo + puntitos) en rojo. Útil en Claves B
        # solución: la clave es lo que el alumno debe haber escrito.
        svg = re.sub(
            r'(<g[^>]*class="clef"[^>]*)>',
            r'\1 style="color:#ff0000;fill:#ff0000;stroke:#ff0000">',
            svg,
        )

    # NOTA: la barra inicial NO se inyecta en el SVG (verovio no mantiene
    # aspect ratio exacto entre el viewBox interno y el SVG raíz, así que
    # las coords del SVG no caen donde deben en el PNG). Se pinta sobre
    # el PNG con PIL después de la rasterización, usando las Y reales
    # detectadas del staff (`staff_top_frac` / `staff_bot_frac`).

    # Rasterizar al ancho natural en mm × dpi
    ancho_mm_natural = vb_w / K_VB_PER_MM
    dpi = 300
    ancho_pix = max(200, int(ancho_mm_natural / 25.4 * dpi))
    png_bytes = gi.svg_a_png_bytes(svg, ancho_pix)
    with Image.open(io.BytesIO(png_bytes)) as im_rgba:
        if im_rgba.mode == "RGBA":
            fondo = Image.new("RGB", im_rgba.size, (255, 255, 255))
            fondo.paste(im_rgba, (0, 0), mask=im_rgba.split()[3])
        else:
            fondo = im_rgba.convert("RGB")
        fondo.save(png_path, "PNG")

    img = ImageReader(str(png_path))
    iw, ih = img.getSize()

    # Detectar la Y REAL de las staff lines y la X REAL del notehead
    # en el PNG. Más fiable que extraerlas del SVG:
    #   - Y: verovio no mantiene aspect ratio exacto entre viewBox
    #        interno y SVG raíz.
    #   - X: la posición del notehead dentro del compás varía según
    #        accidentes y otros elementos que verovio inserta delante.
    staff_top_y_px = None
    staff_bot_y_px = None
    try:
        import numpy as _np
        with Image.open(png_path) as pil:
            arr_rgb = _np.array(pil.convert("RGB"))
        # Sólo consideramos píxeles NEGROS (los tres canales bajos),
        # no rojos. En Claves B solución la clave se pinta en rojo y
        # NO debe interferir con la detección del notehead (que sigue
        # siendo negro). Antes usábamos luminancia (`< 128`) y los
        # píxeles rojos saturados pasaban como oscuros, lo que hacía
        # que el detector eligiera la columna de la clave en vez de
        # la del notehead.
        darks = (
            (arr_rgb[:, :, 0] < 128)
            & (arr_rgb[:, :, 1] < 128)
            & (arr_rgb[:, :, 2] < 128)
        )
        h_px, w_px = arr_rgb.shape[:2]
        darks_per_row = darks.sum(axis=1)
        umbral_staff = max(int(w_px * 0.7), 50)
        candidatos = _np.where(darks_per_row >= umbral_staff)[0]
        if len(candidatos) >= 2:
            staff_top_y_px = int(candidatos.min())
            staff_bot_y_px = int(candidatos.max())
            staff_top_frac = staff_top_y_px / h_px
            staff_bot_frac = staff_bot_y_px / h_px

        # Detectar X del notehead: pico de píxeles oscuros por columna,
        # tras excluir:
        #   - Las staff lines (filas con muchos píxeles oscuros).
        #   - Las BARRAS de compás (columnas que conectan el top y el
        #     bottom del staff: una barra vertical alta cubre ambas
        #     filas; un notehead o un accidente no las cubre las dos).
        #   - Los primeros píxeles (clave + barra inicial).
        darks_no_staff = darks.copy()
        if candidatos.size:
            darks_no_staff[candidatos, :] = False
        # Excluir columnas que son barras de compás (vertical de
        # arriba a abajo del staff). Tomamos píxeles a uno-dos píxeles
        # por dentro del staff top/bot para evitar tocar la misma
        # staff line.
        if staff_top_y_px is not None and staff_bot_y_px is not None:
            margen = 2
            y_chk_top = min(h_px - 1, staff_top_y_px + margen)
            y_chk_bot = max(0, staff_bot_y_px - margen)
            es_barra = darks[y_chk_top, :] & darks[y_chk_bot, :]
            darks_no_staff[:, es_barra] = False
        darks_per_col = darks_no_staff.sum(axis=0)
        inicio_col = int(w_px * 0.15)
        fin_col = w_px - 2
        if fin_col > inicio_col:
            sub = darks_per_col[inicio_col:fin_col]
            if sub.max() > 2:
                nh_x_px = inicio_col + int(sub.argmax())
                ancla_nota_frac = nh_x_px / w_px
    except Exception:
        pass

    # Pintar la barra inicial directamente en el PNG con PIL (en lugar
    # de inyectarla en el SVG). Así cae exactamente sobre el staff
    # detectado, sin depender de mapeos interno→raíz que verovio no
    # respeta con precisión.
    if barra_inicial and staff_top_y_px is not None:
        try:
            from PIL import ImageDraw
            color = (255, 0, 0) if clave_rojo else (0, 0, 0)
            # Ancho de la barra ≈ 2 píxeles (escalado al tamaño del PNG).
            with Image.open(png_path) as pil:
                pil = pil.convert("RGB")
                draw = ImageDraw.Draw(pil)
                # X=1 para no salirse del borde. Tomamos un grosor
                # proporcional al alto del staff (1.5% como referencia).
                grosor = max(1, int((staff_bot_y_px - staff_top_y_px) * 0.02))
                for dx in range(grosor):
                    draw.line(
                        [(dx, staff_top_y_px), (dx, staff_bot_y_px)],
                        fill=color, width=1,
                    )
                pil.save(png_path, "PNG")
        except Exception:
            pass

    return ancho_mm_natural, iw, ih, ancla_nota_frac, staff_top_frac, staff_bot_frac


def _render_claves_png(items, png_path, ocultar_claves=False,
                        ancho_util_mm=160, pad_izq_per_compas=0):
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
    xml = musicxml_ejercicio_claves(items, pad_izq_per_compas=pad_izq_per_compas)
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
        # Forzar UN solo sistema (los 8 compases en una línea). Sin
        # esto, el pad_izq de Claves B engorda los compases y verovio
        # parte automáticamente en 2 sistemas.
        "breaks": "none",
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
        # Hacer las claves INVISIBLES (con visibility:hidden) en vez de
        # borrarlas del SVG. Ojo: si las borrásemos, verovio dejaría el
        # hueco en los compases 2..N pero NO en el compás 1, porque
        # trata la clave inicial del sistema como un bloque "system-
        # level" cuyo espacio se libera cuando desaparece. Resultado:
        # la nota del compás 1 quedaba pegada al borde izquierdo y no
        # había hueco para que el alumno dibujara la clave.
        # Con visibility:hidden el espacio se conserva intacto, igual
        # que en la versión solución, y todos los compases quedan con
        # el mismo layout.
        svg = re.sub(
            r'(<g[^>]*class="clef"[^>]*)>',
            r'\1 style="visibility:hidden">',
            svg,
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
    n = len(items)

    # En Claves B la nota se desplaza hacia la derecha del compás dejando
    # hueco a la izquierda para que el alumno dibuje la clave. La
    # posición exacta depende del nº de placeholders ocultos que
    # añadimos al inicio del compás (verovio decide el reparto):
    #   pad_izq=1 → nota en ~72 % (suficiente hueco pero no al borde)
    #   pad_izq=2 → nota en ~77 %
    #   pad_izq=3 → nota en ~81 %
    pad_izq = 1 if modo == "B" else 0
    # En Claves B la clave SOLO se oculta en la versión ALUMNO (el alumno
    # debe escribirla). En la SOLUCIÓN sí se muestra para que el alumno
    # vea cuál tenía que haber dibujado.
    ocultar = (modo == "B" and not modo_solucion)

    # Spacings de verovio calibrados por modo para igualar al "tamaño
    # estándar" de Semitonos (factor de estirado ≈ 0.95x-1.0x). Ver
    # `_render_un_compas_clave` para los detalles del cálculo.
    if modo == "A":
        sp_lin, sp_nl = 0.18, 0.55   # 8 compases con pad=0 → 166 mm.
    else:  # B (pad=1 añade un placeholder por compás)
        sp_lin, sp_nl = 0.165, 0.50  # 8 compases con pad=1 → 160 mm.

    # Renderizar UN PNG por compás (control total del layout).
    bloques = []
    for i, (clave, _pos, step, octave, alter) in enumerate(items):
        png_path = out_pdf_path.with_name(
            out_pdf_path.stem + f"_cl_{i+1:02d}.png"
        )
        xml = musicxml_un_compas_clave(
            clave, step, octave, alter,
            es_primero=(i == 0), es_ultimo=(i == n - 1),
            pad_izq=pad_izq,
        )
        # En Claves B modo solución, la CLAVE es la respuesta del alumno,
        # así que se pinta en rojo (igual que se hace con las notas en
        # Intervalos B / la sensible en QIHE / etc).
        clave_rojo = (modo == "B" and modo_solucion)
        (ancho_mm_nat, iw, ih, ancla_frac,
         staff_top_frac, staff_bot_frac) = _render_un_compas_clave(
            xml, png_path, ocultar_clave=ocultar,
            spacing_linear=sp_lin, spacing_non_linear=sp_nl,
            clave_rojo=clave_rojo,
            barra_inicial=(i == 0),
        )
        bloques.append({
            "png": png_path, "ancho_nat": ancho_mm_nat,
            "iw": iw, "ih": ih, "ancla_frac": ancla_frac,
            "staff_top_frac": staff_top_frac,
            "staff_bot_frac": staff_bot_frac,
            "clave": clave, "step": step, "octave": octave, "alter": alter,
        })

    # Yuxtaposición: cada compás ocupa una proporción del ancho útil
    # según su ancho natural. Esto evita el bug "ancho desigual" del
    # enfoque por-PNG-recortado: al respetar el aspect ratio natural
    # de cada compás, no hay deformaciones.
    total_natural = sum(b["ancho_nat"] for b in bloques)
    factor = ancho_util_mm / total_natural
    anchos_mm = [b["ancho_nat"] * factor for b in bloques]
    altos_mm = [a * b["ih"] / b["iw"] for a, b in zip(anchos_mm, bloques)]

    # Alinear los pentagramas: cada compás puede tener un alto distinto
    # (depende del rango vertical de notas). Si los alineáramos por el
    # borde inferior, los staffs quedarían a distintas Y (el bug "puzzle
    # mal montado" que reportó Iago). En su lugar, calculamos el Y del
    # TOP del staff en el PDF y bajamos cada imagen lo necesario para
    # que sus líneas del pentagrama caigan exactamente en esa Y común.
    arriba_staff = [h * b["staff_top_frac"]
                    for h, b in zip(altos_mm, bloques)]
    abajo_staff = [h * (1 - b["staff_top_frac"])
                    for h, b in zip(altos_mm, bloques)]
    max_arriba = max(arriba_staff)
    max_abajo = max(abajo_staff)

    c.setFont("Helvetica-Bold", 12)
    c.drawString(x_ini, y_top, f"{num_enunciado}. Claves")

    # Y del top del pentagrama común (la imagen del compás que tenga
    # notas más agudas necesita el máximo de espacio "encima del staff").
    y_staff_top_pdf = y_top - 6 * mm - max_arriba * mm

    # Dibujar cada compás alineando su staff_top con y_staff_top_pdf.
    x_inicios = []
    x_cur_mm = 0
    for b, a_mm, h_mm in zip(bloques, anchos_mm, altos_mm):
        x_inicios.append(x_cur_mm)
        # En reportlab Y crece hacia arriba: el borde inferior de la
        # imagen va a y_staff_top_pdf - (alto_debajo_del_staff).
        h_below = h_mm * (1 - b["staff_top_frac"])
        y_img_i = y_staff_top_pdf - h_below * mm
        img = ImageReader(str(b["png"]))
        c.drawImage(
            img, x_ini + x_cur_mm * mm, y_img_i,
            width=a_mm * mm, height=h_mm * mm,
        )
        x_cur_mm += a_mm

    # Etiqueta global "Y del borde inferior del bloque visual": Y bajo
    # el staff común menos el máximo "alto debajo del staff" de los 8.
    y_img = y_staff_top_pdf - max_abajo * mm

    # Etiquetas debajo del pentagrama
    y_label = y_img - 1 * mm
    c.setFont("Helvetica-Oblique", 10)

    for idx, b in enumerate(bloques):
        x_inicio_mm = x_inicios[idx]
        a_mm = anchos_mm[idx]
        # Centro del compás (modo A) o posición de la nota (modo B)
        x_centro = x_ini + (x_inicio_mm + a_mm / 2) * mm
        x_nota = x_ini + (x_inicio_mm + a_mm * b["ancla_frac"]) * mm
        if modo == "A":
            c.setFillColorRGB(0, 0, 0)
            c.drawCentredString(x_centro, y_label, "______")
            if modo_solucion:
                c.saveState()
                c.setFillColorRGB(1, 0, 0)
                c.drawCentredString(
                    x_centro, y_label + 0.6 * mm,
                    nombre_nota_corto(b["step"], b["alter"]),
                )
                c.restoreState()
        else:
            # Claves B: etiqueta bajo la nota (sin octava).
            c.drawCentredString(
                x_nota, y_label,
                nombre_nota_corto(b["step"], b["alter"]),
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
