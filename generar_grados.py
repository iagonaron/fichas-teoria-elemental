"""
Ejercicio de Grados (armónicos) — Fichas 3ºGe.

Basado en Ficha 4:
  - 2 compases en una línea, cada uno con su propia armadura.
  - Doble barra fina (light-light) entre c1 y c2.
  - Doble barra gruesa (light-heavy) al final de c2.
  - Debajo de cada compás, dos etiquetas:
      izq: "Dominante de ReM"  (Grado + de + tonalidad)
      der: "Respuesta: ______"  (el alumno escribe la nota)
  - Pentagrama vacío (solo clave + armadura). El alumno razona y
    escribe la nota pedida en el hueco "Respuesta".

Por qué 1 SVG por compás:
  Si los 2 compases viven en el mismo SVG y tienen armaduras distintas,
  verovio pinta becuadros cancelatorios al pasar de una armadura a
  otra (mismo bug que resolvimos en Claves y en TA+TV). Renderizando
  cada compás independiente esto se evita.

Coherencia visual: mismo K_VB_PER_MM = 90.06 que el resto (cabezas
y altura de pentagrama iguales).
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
import generar_tonalidades_armaduras as gtav


# -----------------------------------------------------------------------------
# Catálogo de grados y utilidades
# -----------------------------------------------------------------------------
GRADOS = [
    (1, "Tónica"),          # Presente para referencia/utilidades, pero
                            # EXCLUIDA del sorteo del ejercicio (demasiado
                            # evidente para el alumno).
    (2, "Supertónica"),
    (3, "Mediante"),
    (4, "Subdominante"),
    (5, "Dominante"),
    (6, "Superdominante"),
    (7, "Sensible"),
]

# Grados sorteables en el ejercicio: todos menos la Tónica.
GRADOS_SORTEABLES = [g for g in GRADOS if g[0] != 1]

NOMBRE_ES = {
    "C": "Do", "D": "Re", "E": "Mi", "F": "Fa",
    "G": "Sol", "A": "La", "B": "Si",
}
ACC_ES = {-2: "bb", -1: "b", 0: "", 1: "#", 2: "x"}


def nombre_nota(step, alter):
    return f"{NOMBRE_ES[step]}{ACC_ES[alter]}"


# Orden canónico de alteraciones en armaduras.
ORDEN_SOSTENIDOS = ["F", "C", "G", "D", "A", "E", "B"]
ORDEN_BEMOLES = ["B", "E", "A", "D", "G", "C", "F"]


def alteracion_en_armadura(step, fifths):
    """Devuelve qué alteración tiene `step` en una armadura de `fifths`
    (p. ej. fifths=2 → Fa# y Do# alterados)."""
    if fifths > 0:
        if step in ORDEN_SOSTENIDOS[:fifths]:
            return 1
    elif fifths < 0:
        if step in ORDEN_BEMOLES[:-fifths]:
            return -1
    return 0


# Mapeo: nombre de tonalidad → (step de la tónica, alter de la tónica).
TONICA = {
    # Mayores
    "DoM": ("C", 0),  "SolM": ("G", 0),  "ReM": ("D", 0),  "LaM": ("A", 0),
    "MiM": ("E", 0),  "SiM": ("B", 0),   "Fa#M": ("F", 1), "Do#M": ("C", 1),
    "FaM": ("F", 0),  "SibM": ("B", -1), "MibM": ("E", -1), "LabM": ("A", -1),
    "RebM": ("D", -1),"SolbM": ("G", -1),"DobM": ("C", -1),
    # Menores
    "Lam": ("A", 0),  "Mim": ("E", 0),   "Sim": ("B", 0),  "Fa#m": ("F", 1),
    "Do#m": ("C", 1), "Sol#m": ("G", 1), "Re#m": ("D", 1), "La#m": ("A", 1),
    "Rem": ("D", 0),  "Solm": ("G", 0),  "Dom": ("C", 0),  "Fam": ("F", 0),
    "Sibm": ("B", -1),"Mibm": ("E", -1), "Labm": ("A", -1),
}


def es_menor(nombre):
    """True si la tonalidad es menor (termina en 'm' sin 'M')."""
    return nombre.endswith("m")


def nota_del_grado(tonalidad_nombre, fifths, grado_num):
    """Devuelve (step, alter) de la nota que ocupa `grado_num` en la
    tonalidad dada.

    Convención:
      - Mayores: escala mayor natural (lo que marca la armadura).
      - Menores: escala menor ARMÓNICA. Esto implica que el VII
        ("Sensible") va elevado un semitono respecto a la armadura
        (p. ej. en Sim, VII = La# en lugar de La). Los demás grados
        coinciden con la menor natural.

    En español se distingue:
      - VII natural = "Subtónica"
      - VII elevado = "Sensible"
    Como nuestras etiquetas usan siempre "Sensible", en menores hay
    que elevar el VII para que la teoría coincida con la etiqueta.
    """
    tonica_step, _ = TONICA[tonalidad_nombre]
    idx_tonica = gi.STEPS.index(tonica_step)
    new_idx = (idx_tonica + grado_num - 1) % 7
    step_n = gi.STEPS[new_idx]
    alter_n = alteracion_en_armadura(step_n, fifths)

    # En menor armónica el VII está elevado un semitono.
    if es_menor(tonalidad_nombre) and grado_num == 7:
        alter_n += 1

    return step_n, alter_n


# -----------------------------------------------------------------------------
# Sorteo
# -----------------------------------------------------------------------------
def elegir_grados(seed=None, n_compases=2):
    """Devuelve lista de n_compases dicts con:
      tonalidad_nombre, fifths, grado_num, grado_nombre,
      respuesta_step, respuesta_alter.

    - Tonalidades: mayores y menores, con `peso_fifths` para que las
      armaduras de 6-7 alteraciones salgan raramente.
    - Grados: sorteo uniforme (I-VII).
    - No repetimos (tonalidad, grado) en la misma ficha.
    """
    if seed is not None:
        random.seed(seed)

    pesos = [gtav.peso_fifths(f) for _, f in gtav.TONALIDADES]

    items = []
    usados_grado = set()       # para no repetir (tonalidad, grado)
    tonalidades_usadas = set() # para no repetir la misma tonalidad
    for _ in range(n_compases):
        for _ in range(300):
            t = random.choices(gtav.TONALIDADES, weights=pesos)[0]
            grado_num, grado_nombre = random.choice(GRADOS_SORTEABLES)
            # La tonalidad no puede repetirse entre los 2 compases de la
            # ficha (aunque el grado sea distinto). Evita confusión visual
            # y hace el ejercicio más variado.
            if t[0] in tonalidades_usadas:
                continue
            key = (t[0], grado_num)
            if key in usados_grado:
                continue
            step_r, alter_r = nota_del_grado(t[0], t[1], grado_num)
            # Evitar dobles alteraciones (Sol#m/Re#m/La#m con sensible).
            if abs(alter_r) > 1:
                continue
            # Evitar enharmónicos raros (Fb, Cb, B#, E#).
            if (step_r, alter_r) in gi.RARAS:
                continue
            usados_grado.add(key)
            tonalidades_usadas.add(t[0])
            items.append({
                "tonalidad_nombre": t[0],
                "fifths": t[1],
                "grado_num": grado_num,
                "grado_nombre": grado_nombre,
                "respuesta_step": step_r,
                "respuesta_alter": alter_r,
            })
            break
    return items


# -----------------------------------------------------------------------------
# MusicXML de UN compás (pentagrama vacío, SOLO con clave; sin armadura)
# -----------------------------------------------------------------------------
# Nº de silencios ocultos por compás. Cada redonda oculta añade ~17.6 mm de
# ancho natural al viewBox de verovio. Con N_PLACEHOLDERS=4 → ~85.5 mm por
# compás → 2 compases = 171 mm natural → se comprimen levemente a 160 mm
# (factor ≈0.93) SIN deformar el pentagrama verticalmente. Si fuese 1 solo
# silencio (32.5 mm), al estirar a 160 mm se dispararía la altura por
# aspect-ratio y el pentagrama quedaría gigante.
N_PLACEHOLDERS = 4


def _octava_grado(tonica_step, octava_tonica, grado_num):
    """Octava real (C-based) de la nota que ocupa `grado_num` a partir de
    la tónica, respetando el cruce B→C.
    """
    idx_tonica = gi.STEPS.index(tonica_step)
    new_idx = (idx_tonica + grado_num - 1) % 7
    return octava_tonica + (1 if new_idx < idx_tonica else 0)


def musicxml_un_compas(con_barra_final=False, final_heavy=True):
    """MusicXML de UN compás vacío con SOLO la clave de Sol.

    Importante: **NO se dibuja la armadura**. El alumno tiene que deducir
    la armadura a partir de la tonalidad indicada en la etiqueta
    ("Dominante de ReM") y aplicar mentalmente las alteraciones.
    Por eso `<fifths>0</fifths>` siempre.

    Llevamos N_PLACEHOLDERS silencios ocultos para fijar el ancho natural
    del compás alrededor de los 80-90 mm que pide la maqueta.
    """
    if con_barra_final:
        style = "light-heavy" if final_heavy else "light-light"
        barra = (f'<barline location="right">'
                 f'<bar-style>{style}</bar-style></barline>')
    else:
        barra = ""

    silencio = (
        '<note print-object="no">'
        '<rest/><duration>4</duration><type>whole</type>'
        '</note>'
    )
    silencios = silencio * N_PLACEHOLDERS
    beats_total = 4 * N_PLACEHOLDERS

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name></part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <key><fifths>0</fifths></key>
        <time print-object="no"><beats>{beats_total}</beats><beat-type>4</beat-type></time>
        <clef><sign>G</sign><line>2</line></clef>
      </attributes>
      {silencios}
      {barra}
    </measure>
  </part>
</score-partwise>"""


def _nota_visible_xml(step, octave, alter, color=None):
    """Redonda visible. `color` opcional (string tipo '#FF0000')."""
    alter_xml = f"<alter>{alter}</alter>" if alter else ""
    accidental_xml = ""
    if alter == 1:
        accidental_xml = "<accidental>sharp</accidental>"
    elif alter == -1:
        accidental_xml = "<accidental>flat</accidental>"
    elif alter == 2:
        accidental_xml = "<accidental>double-sharp</accidental>"
    elif alter == -2:
        accidental_xml = "<accidental>flat-flat</accidental>"
    color_attr = f' color="{color}"' if color else ""
    return f"""
      <note{color_attr}>
        <pitch>
          <step>{step}</step>
          {alter_xml}
          <octave>{octave}</octave>
        </pitch>
        <duration>4</duration>
        <type>whole</type>
        {accidental_xml}
      </note>"""


def _nota_negra_sin_plica_xml(step, octave, alter, color=None):
    """Cabeza de negra SIN plica (stem=none). Usada en la escala del
    modo solución (estilo "escala cursiva" del profesor)."""
    alter_xml = f"<alter>{alter}</alter>" if alter else ""
    color_attr = f' color="{color}"' if color else ""
    return f"""
      <note{color_attr}>
        <pitch>
          <step>{step}</step>
          {alter_xml}
          <octave>{octave}</octave>
        </pitch>
        <duration>1</duration>
        <type>quarter</type>
        <stem>none</stem>
      </note>"""


def musicxml_escala_solucion(fifths, tonalidad_nombre, tonica_octava,
                              grado_objetivo,
                              con_barra_final=False, final_heavy=True):
    """Compás con armadura REAL + escala completa (7 notas) como cabezas
    de negra sin plica. La(s) nota(s) del/los grado(s) pedido(s) van en
    ROJO, el resto en negro.

    `grado_objetivo` puede ser un int (un solo grado) o un iterable de
    ints (p.ej. [2, 5] para señalar grados II y V en el QIHE).

    Regla de alteraciones: NINGUNA nota lleva accidental explícito.
    Verovio dibuja el accidental automáticamente SOLO cuando la
    alteración de la nota difiere de la armadura — es exactamente la
    regla que usamos (p. ej. la VII elevada en menor armónica).
    """
    if con_barra_final:
        style = "light-heavy" if final_heavy else "light-light"
        barra = (f'<barline location="right">'
                 f'<bar-style>{style}</bar-style></barline>')
    else:
        barra = ""

    if isinstance(grado_objetivo, int):
        objetivos = {grado_objetivo}
    else:
        objetivos = set(grado_objetivo)

    tonica_step, _ = TONICA[tonalidad_nombre]
    notas = []
    for g in range(1, 8):
        step_g, alter_g = nota_del_grado(tonalidad_nombre, fifths, g)
        octava_g = _octava_grado(tonica_step, tonica_octava, g)
        color = "#FF0000" if g in objetivos else None
        notas.append(_nota_negra_sin_plica_xml(
            step_g, octava_g, alter_g, color=color,
        ))

    beats_total = 7  # 7 negras

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name></part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <key><fifths>{fifths}</fifths></key>
        <time print-object="no"><beats>{beats_total}</beats><beat-type>4</beat-type></time>
        <clef><sign>G</sign><line>2</line></clef>
      </attributes>
      {"".join(notas)}
      {barra}
    </measure>
  </part>
</score-partwise>"""


def musicxml_un_compas_solucion(fifths, step, octave, alter,
                                 con_barra_final=False, final_heavy=True,
                                 pos_nota=2):
    """Compás con armadura REAL + 1 redonda roja (la respuesta) visible.

    Conserva el mismo ancho natural que `musicxml_un_compas` usando
    N_PLACEHOLDERS - 1 silencios ocultos + 1 nota visible (= N_PLACEHOLDERS
    elementos en total). `pos_nota` (1-indexado) indica en qué posición
    aparece la redonda visible dentro del compás.
    """
    if con_barra_final:
        style = "light-heavy" if final_heavy else "light-light"
        barra = (f'<barline location="right">'
                 f'<bar-style>{style}</bar-style></barline>')
    else:
        barra = ""

    silencio = (
        '<note print-object="no">'
        '<rest/><duration>4</duration><type>whole</type>'
        '</note>'
    )
    nota = _nota_visible_xml(step, octave, alter, color="#FF0000")
    elementos = []
    for i in range(1, N_PLACEHOLDERS + 1):
        if i == pos_nota:
            elementos.append(nota)
        else:
            elementos.append(silencio)
    beats_total = 4 * N_PLACEHOLDERS

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name></part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <key><fifths>{fifths}</fifths></key>
        <time print-object="no"><beats>{beats_total}</beats><beat-type>4</beat-type></time>
        <clef><sign>G</sign><line>2</line></clef>
      </attributes>
      {"".join(elementos)}
      {barra}
    </measure>
  </part>
</score-partwise>"""


# -----------------------------------------------------------------------------
# Render de un compás a PNG
# -----------------------------------------------------------------------------
K_VB_PER_MM = 90.06


def _postprocess_keysig_rojo(svg):
    """Pinta en rojo los grupos `class="keySig"` del SVG (mismas reglas
    que en generar_tonalidades_armaduras)."""
    return re.sub(
        r'(<g[^>]*class="keySig"[^>]*)>',
        r'\1 style="color:#ff0000;fill:#ff0000;stroke:#ff0000">',
        svg,
    )


def _extraer_noteheads(svg):
    """Devuelve lista de (x, y) en coordenadas del viewBox para cada
    notehead visible en el SVG. Incluye offset de page-margin."""
    pm_match = re.search(
        r'class="page-margin"[^>]*transform="translate\((\-?[\d\.]+),\s*(\-?[\d\.]+)\)"',
        svg,
    )
    pm_x = float(pm_match.group(1)) if pm_match else 0.0
    pm_y = float(pm_match.group(2)) if pm_match else 0.0
    out = []
    for m in re.finditer(
        r'class="notehead"[^>]*>\s*<use[^>]*transform="translate\((\-?[\d\.]+),\s*(\-?[\d\.]+)\)',
        svg,
    ):
        out.append((pm_x + float(m.group(1)), pm_y + float(m.group(2))))
    return out


def _render_compas_png(xml, png_path, keysig_rojo=False,
                       return_noteheads=False):
    """Renderiza un compás a PNG. Devuelve vb_w (o (vb_w, vb_h, noteheads)
    si `return_noteheads=True`).
    """
    tk = verovio.toolkit()
    tk.setOptions({
        "pageWidth": 2100,
        "pageHeight": 2970,
        "pageMarginTop": 20, "pageMarginBottom": 20,
        # Márgenes horizontales a 0 para que los PNG se puedan yuxtaponer
        # sin huecos blancos entre compases (líneas del pentagrama continuas).
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

    vb_match = re.search(
        r'class="definition-scale"[^>]*viewBox="([\d\s\.\-]+)"', svg
    )
    if vb_match:
        vb_parts = vb_match.group(1).split()
        vb_w = float(vb_parts[2])
        vb_h = float(vb_parts[3])
    else:
        vb_w, vb_h = 10000.0, 2000.0

    noteheads = _extraer_noteheads(svg) if return_noteheads else []

    if keysig_rojo:
        svg = _postprocess_keysig_rojo(svg)

    ancho_pix = 1400
    png_bytes = gi.svg_a_png_bytes(svg, ancho_pix)
    with Image.open(io.BytesIO(png_bytes)) as im_rgba:
        if im_rgba.mode == "RGBA":
            fondo = Image.new("RGB", im_rgba.size, (255, 255, 255))
            fondo.paste(im_rgba, (0, 0), mask=im_rgba.split()[3])
        else:
            fondo = im_rgba.convert("RGB")
        fondo.save(png_path, "PNG")

    if return_noteheads:
        return vb_w, vb_h, noteheads
    return vb_w


# -----------------------------------------------------------------------------
# Composición PDF
# -----------------------------------------------------------------------------
def dibujar_en_canvas(c, x_ini, y_top, items, num_enunciado, out_pdf_path,
                      ancho_util_mm=160, modo_solucion=False):
    """Dibuja el ejercicio de Grados en `c` comenzando en `y_top`.
    Devuelve `y_bottom` (la Y más baja usada, incluido el espacio de
    etiquetas). Ideal para encadenar ejercicios verticalmente.

    `out_pdf_path` es cualquier Path válido en disco; se usa solo para
    generar PNGs auxiliares (un compás por PNG).
    """
    out_pdf_path = Path(out_pdf_path)
    n = len(items)

    bloques = []
    for i, it in enumerate(items):
        final_heavy = (i == n - 1)
        png_path = out_pdf_path.with_name(
            out_pdf_path.stem + f"_grad_c{i+1:02d}.png"
        )
        if modo_solucion:
            # Escala completa (I–VII) como negras sin plica. La nota del
            # grado pedido se pinta en rojo.
            xml = musicxml_escala_solucion(
                it["fifths"], it["tonalidad_nombre"],
                tonica_octava=4,
                grado_objetivo=it["grado_num"],
                con_barra_final=True, final_heavy=final_heavy,
            )
            vb_w, vb_h, noteheads = _render_compas_png(
                xml, png_path, keysig_rojo=True, return_noteheads=True,
            )
        else:
            xml = musicxml_un_compas(
                con_barra_final=True, final_heavy=final_heavy,
            )
            vb_w = _render_compas_png(xml, png_path)
            vb_h, noteheads = None, []

        img = ImageReader(str(png_path))
        iw, ih = img.getSize()
        bloques.append({
            "item": it, "vb_w": vb_w, "vb_h": vb_h, "noteheads": noteheads,
            "img": img, "iw": iw, "ih": ih, "png": png_path,
        })

    anchos_mm_ideales = [b["vb_w"] / K_VB_PER_MM for b in bloques]
    total_ideal = sum(anchos_mm_ideales)
    factor = min(1.0, ancho_util_mm / total_ideal)
    anchos_mm = [a * factor for a in anchos_mm_ideales]
    altos_mm = [a * b["ih"] / b["iw"] for a, b in zip(anchos_mm, bloques)]
    alto_max = max(altos_mm)

    # Título
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x_ini, y_top, f"{num_enunciado}. Grados")

    y_img = y_top - 6 * mm - alto_max * mm

    x_cur_mm = 0
    x_compas_mm = []
    for a in anchos_mm:
        x_compas_mm.append(x_cur_mm)
        x_cur_mm += a

    for b, x_mm, a_mm, alto_mm_b in zip(bloques, x_compas_mm, anchos_mm, altos_mm):
        c.drawImage(
            b["img"], x_ini + x_mm * mm, y_img,
            width=a_mm * mm, height=alto_mm_b * mm,
        )

    # Señalización: flecha roja apuntando a la cabeza de la nota respuesta.
    # Las 7 noteheads corresponden a los grados I..VII en orden; cogemos
    # la del grado objetivo.
    if modo_solucion:
        for b, x_mm, a_mm, alto_mm_b in zip(
            bloques, x_compas_mm, anchos_mm, altos_mm,
        ):
            if not b["noteheads"] or not b["vb_h"]:
                continue
            grado_obj = b["item"]["grado_num"]
            if grado_obj - 1 >= len(b["noteheads"]):
                continue
            xv, yv = b["noteheads"][grado_obj - 1]
            frac_x = xv / b["vb_w"]
            frac_y = yv / b["vb_h"]
            x_cx = x_ini + x_mm * mm + frac_x * a_mm * mm
            y_cy = y_img + alto_mm_b * mm - frac_y * alto_mm_b * mm
            # Flecha vertical apuntando HACIA ABAJO a la nota.
            y_base = y_cy + 7 * mm
            y_punta = y_cy + 2.2 * mm       # justo encima del notehead
            ancho_cabeza = 1.2 * mm
            alto_cabeza = 1.6 * mm
            c.saveState()
            c.setStrokeColorRGB(1, 0, 0)
            c.setFillColorRGB(1, 0, 0)
            c.setLineWidth(0.6)
            c.line(x_cx, y_base, x_cx, y_punta)
            p = c.beginPath()
            p.moveTo(x_cx, y_punta - alto_cabeza)         # punta
            p.lineTo(x_cx - ancho_cabeza, y_punta)        # ala izq
            p.lineTo(x_cx + ancho_cabeza, y_punta)        # ala der
            p.close()
            c.drawPath(p, stroke=1, fill=1)
            c.restoreState()

    c.setFont("Helvetica-Oblique", 10)
    y_label = y_img - 4 * mm
    margen_lateral_mm = 4

    # Etiqueta izquierda: "Dominante de ReM".
    # Etiqueta derecha: "Respuesta: ______" (alumno) o "Respuesta: Sib"
    # en rojo (solución).
    for b, x_mm, a_mm in zip(bloques, x_compas_mm, anchos_mm):
        it = b["item"]
        label_izq = f"{it['grado_nombre']} de {it['tonalidad_nombre']}"
        x_izq = x_ini + x_mm * mm + margen_lateral_mm * mm
        x_der = x_ini + (x_mm + a_mm) * mm - margen_lateral_mm * mm
        c.drawString(x_izq, y_label, label_izq)
        if modo_solucion:
            resp_txt = nombre_nota(it["respuesta_step"], it["respuesta_alter"])
            c.saveState()
            c.setFillColorRGB(1, 0, 0)
            c.drawRightString(x_der, y_label, f"Respuesta: {resp_txt}")
            c.restoreState()
        else:
            c.drawRightString(x_der, y_label, "Respuesta: ______")

    return y_label - 2 * mm  # y_bottom con un pequeño colchón inferior


def componer_pdf_grados(items, numero_ficha, out_pdf, num_enunciado=10,
                         modo_solucion=False):
    """2 compases lado a lado, cada uno con su armadura.
    Debajo de cada uno: etiqueta izq (grado) + etiqueta der (respuesta).
    """
    out_pdf = Path(out_pdf)
    c = canvas.Canvas(str(out_pdf), pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width / 2, height - 25 * mm, f"Ficha {numero_ficha}")
    c.setFont("Helvetica", 12)
    c.drawString(25 * mm, height - 35 * mm, "Nombre  _________________________")
    c.drawRightString(width - 25 * mm, height - 35 * mm, "Nota  _______")

    dibujar_en_canvas(
        c, 25 * mm, height - 55 * mm, items, num_enunciado,
        out_pdf_path=out_pdf, modo_solucion=modo_solucion,
    )

    c.showPage()
    c.save()


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3, help="cuántas fichas")
    ap.add_argument("--num-enunciado", type=int, default=10,
                    help="número del ejercicio en la ficha")
    ap.add_argument("--solucion", action="store_true",
                    help="dibujar armadura+nota en rojo")
    args = ap.parse_args()

    out_dir = Path("/sessions/elegant-busy-goldberg/mnt/outputs")
    out_dir.mkdir(parents=True, exist_ok=True)

    for i in range(1, args.n + 1):
        seed = 8000 + i
        items = elegir_grados(seed=seed)
        sufijo = "_sol" if args.solucion else ""
        pdf_path = out_dir / f"prototipo_ficha_{i}_ej10grad{sufijo}.pdf"
        print(f"Generando {pdf_path.name}")
        for it in items:
            resp = nombre_nota(it["respuesta_step"], it["respuesta_alter"])
            print(f"   · {it['grado_nombre']} de {it['tonalidad_nombre']} "
                  f"(armadura {it['fifths']:+d}) → {resp}")
        componer_pdf_grados(items, i, pdf_path,
                             num_enunciado=args.num_enunciado,
                             modo_solucion=args.solucion)

    print("\nListo")


if __name__ == "__main__":
    main()
