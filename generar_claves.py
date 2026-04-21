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
# MusicXML: un compás independiente por cada elemento
# -----------------------------------------------------------------------------
def musicxml_un_compas(clave, step, octave, alter, con_barra_final=True,
                       n_placeholders=0):
    """MusicXML de UN compás con clef + una redonda.

    - `con_barra_final` añade doble barra final (si queremos un único
      compás aislado).
    - `n_placeholders`: redondas ocultas adicionales para forzar ancho.
    """
    _, sign, line, _, _ = clave
    alter_xml = f"<alter>{alter}</alter>" if alter else ""
    accidental_xml = ""
    if alter == 1:
        accidental_xml = "<accidental>sharp</accidental>"
    elif alter == -1:
        accidental_xml = "<accidental>flat</accidental>"

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

    # Placeholder ocultos en C4 — a verovio solo le interesa que existan
    # para reservar ancho; no se imprimen.
    placeholders = ""
    for _ in range(n_placeholders):
        placeholders += """
      <note print-object="no">
        <pitch><step>C</step><octave>4</octave></pitch>
        <duration>16</duration>
        <type>whole</type>
      </note>"""

    barra = ""
    if con_barra_final:
        barra = ('<barline location="right">'
                 '<bar-style>light-heavy</bar-style></barline>')

    # Tiempo adaptado al contenido (1 redonda + placeholders)
    beats = 4 * (1 + n_placeholders)

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
        <time print-object="no"><beats>{beats}</beats><beat-type>4</beat-type></time>
        <clef><sign>{sign}</sign><line>{line}</line></clef>
      </attributes>{nota}{placeholders}
      {barra}
    </measure>
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


def _render_compas_png(xml, png_path, ocultar_clave=False):
    """Renderiza un compás a PNG y devuelve dict:
      - vb_w: anchura del viewBox verovio (para convertir a mm con K).
      - x_centro_frac: fracción 0..1 del centro del compás (entre clave
        y barra) dentro del PNG.
      - x_nota_frac: fracción 0..1 de la POSICIÓN HORIZONTAL DE LA NOTA
        (notehead) dentro del PNG. La usamos para alinear la etiqueta
        justo debajo de la nota en Claves B.

    Si `ocultar_clave` es True, se eliminan del SVG los grupos
    `<g class="clef">...</g>` antes de convertir a PNG. El espacio
    horizontal queda reservado → el alumno escribe la clave ahí.
    """
    tk = verovio.toolkit()
    tk.setOptions({
        "pageWidth": 2100,
        "pageHeight": 2970,
        "pageMarginTop": 20, "pageMarginBottom": 20,
        # Márgenes horizontales a 0: cuando yuxtaponemos los 8 PNG en el
        # PDF, las líneas del pentagrama se tienen que tocar. Si dejamos
        # márgenes, aparecen huecos blancos entre compases.
        "pageMarginLeft": 0, "pageMarginRight": 0,
        "scale": 35,
        "spacingStaff": 8,
        "spacingSystem": 8,
        "spacingNonLinear": 0.6,
        "spacingLinear": 0.25,
        "adjustPageHeight": True,
        "adjustPageWidth": True,
        "barLineWidth": 0.3,
        "staffLineWidth": 0.2,
        "header": "none",
        "footer": "none",
        "breaks": "none",
    })
    tk.loadData(xml)
    tk.redoLayout()
    svg = tk.renderToSVG(1)

    # viewBox width (coordenadas internas de verovio)
    vb_match = re.search(
        r'class="definition-scale"[^>]*viewBox="([\d\s\.\-]+)"', svg
    )
    vb_w = float(vb_match.group(1).split()[2]) if vb_match else 10000.0

    # page-margin offset
    pm_match = re.search(
        r'class="page-margin"[^>]*transform="translate\((\-?[\d\.]+),\s*(\-?[\d\.]+)\)"',
        svg,
    )
    pm_x = float(pm_match.group(1)) if pm_match else 0.0

    # X de la barra final (debería ser una sola en un compás aislado)
    barras = sorted(
        float(m.group(1))
        for m in re.finditer(r'class="barLine">\s*<path d="M(\-?[\d\.]+)\s', svg)
    )
    agrup = []
    for b in barras:
        if agrup and abs(b - agrup[-1]) < 80:
            agrup[-1] = (agrup[-1] + b) / 2
        else:
            agrup.append(b)
    x_barra = agrup[0] if agrup else vb_w

    # X del final de la clave
    clef_m = re.search(
        r'class="clef">\s*<use [^>]*transform="translate\((\-?[\d\.]+),',
        svg,
    )
    x_clef = float(clef_m.group(1)) if clef_m else 0.0
    ANCHO_CLEF = 300
    inicio = x_clef + ANCHO_CLEF

    x_centro_vb = pm_x + (inicio + x_barra) / 2
    x_centro_frac = x_centro_vb / vb_w

    # X del notehead (para alinear la etiqueta justo debajo de la nota
    # en Claves B). Cogemos el PRIMER notehead visible (solo hay uno por
    # compás en este ejercicio).
    nota_m = re.search(
        r'class="notehead"[^>]*>\s*<use[^>]*transform="translate\((\-?[\d\.]+),',
        svg,
    )
    x_nota_vb = float(nota_m.group(1)) if nota_m else x_centro_vb
    x_nota_frac = (pm_x + x_nota_vb) / vb_w

    # Claves de Do: añadimos los 2 puntitos tradicionales que marcan la
    # línea donde se sitúa la clave (las de Fa ya los llevan incorporados
    # en el glifo SMuFL E062; las de Sol no los llevan nunca).
    svg = _inyectar_puntos_claves_do(svg)

    if ocultar_clave:
        # Quitamos el GLIFO de la clave, NO su hueco en el layout.
        svg = re.sub(
            r'<g[^>]*class="clef"[^>]*>.*?</g>',
            '',
            svg,
            flags=re.DOTALL,
        )

    ancho_pix = 1400
    png_bytes = gi.svg_a_png_bytes(svg, ancho_pix)
    with Image.open(io.BytesIO(png_bytes)) as im_rgba:
        if im_rgba.mode == "RGBA":
            fondo = Image.new("RGB", im_rgba.size, (255, 255, 255))
            fondo.paste(im_rgba, (0, 0), mask=im_rgba.split()[3])
        else:
            fondo = im_rgba.convert("RGB")
        fondo.save(png_path, "PNG")

    return vb_w, x_centro_frac, x_nota_frac


# -----------------------------------------------------------------------------
# Composición PDF: 8 compases en una línea
# -----------------------------------------------------------------------------
def dibujar_en_canvas(c, x_ini, y_top, items, modo, num_enunciado,
                       out_pdf_path, ancho_util_mm=160, modo_solucion=False):
    """Dibuja el ejercicio de Claves en `c` a partir de `y_top`.
    Devuelve `y_bottom`.

    - modo "A": clave visible, etiqueta "______" debajo (o nombre en rojo
      en modo solución).
    - modo "B": clave oculta, etiqueta con nombre de la nota impresa
      siempre en negro (el alumno dibuja la clave, no hay "respuesta"
      textual). No usamos modo B en Ficha 5 pero se mantiene la API.
    """
    out_pdf_path = Path(out_pdf_path)
    bloques = []
    for i, (clave, _pos, step, octave, alter) in enumerate(items, start=1):
        con_barra_final = (i == len(items))
        xml = musicxml_un_compas(
            clave, step, octave, alter,
            con_barra_final=con_barra_final, n_placeholders=0,
        )
        png_path = out_pdf_path.with_name(
            out_pdf_path.stem + f"_cl_c{i:02d}.png"
        )
        vb_w, xcf, xnf = _render_compas_png(
            xml, png_path, ocultar_clave=(modo == "B"),
        )
        img = ImageReader(str(png_path))
        iw, ih = img.getSize()
        bloques.append({
            "clave": clave, "step": step, "octave": octave, "alter": alter,
            "vb_w": vb_w, "x_centro_frac": xcf, "x_nota_frac": xnf,
            "img": img, "iw": iw, "ih": ih, "png": png_path,
        })

    anchos_mm_ideales = [b["vb_w"] / K_VB_PER_MM for b in bloques]
    total_ideal = sum(anchos_mm_ideales)
    if total_ideal > ancho_util_mm:
        factor = ancho_util_mm / total_ideal
        anchos_mm = [a * factor for a in anchos_mm_ideales]
    else:
        anchos_mm = list(anchos_mm_ideales)
    altos_mm = [a * b["ih"] / b["iw"] for a, b in zip(anchos_mm, bloques)]
    alto_max = max(altos_mm)

    c.setFont("Helvetica-Bold", 12)
    # En la ficha siempre se imprime "Claves" a secas — la distinción A/B
    # queda solo en el CLI / nombre de archivo.
    c.drawString(x_ini, y_top, f"{num_enunciado}. Claves")

    y_img = y_top - 6 * mm - alto_max * mm

    x_img_mm_list = []
    x_cur_mm = 0
    for a in anchos_mm:
        x_img_mm_list.append(x_cur_mm)
        x_cur_mm += a

    for b, x_mm, a_mm, alto_mm_b in zip(bloques, x_img_mm_list,
                                          anchos_mm, altos_mm):
        c.drawImage(
            b["img"], x_ini + x_mm * mm, y_img,
            width=a_mm * mm, height=alto_mm_b * mm,
        )

    c.setFont("Helvetica-Oblique", 10)
    y_label = y_img - 3.5 * mm
    for b, x_mm, a_mm in zip(bloques, x_img_mm_list, anchos_mm):
        if modo == "A":
            x_centro = x_ini + x_mm * mm + a_mm * mm * b["x_centro_frac"]
            # Línea del alumno SIEMPRE (también en modo solución).
            c.setFillColorRGB(0, 0, 0)
            c.drawCentredString(x_centro, y_label, "______")
            if modo_solucion:
                # Respuesta en rojo cursiva encima de la línea, sin
                # número de octava (ej. "Re", "Sol#").
                c.saveState()
                c.setFillColorRGB(1, 0, 0)
                c.drawCentredString(
                    x_centro, y_label + 0.6 * mm,
                    nombre_nota_corto(b["step"], b["alter"]),
                )
                c.restoreState()
        else:
            x_nota = x_ini + x_mm * mm + a_mm * mm * b["x_nota_frac"]
            c.drawCentredString(
                x_nota, y_label,
                nombre_nota_es(b["step"], b["octave"], b["alter"]),
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
