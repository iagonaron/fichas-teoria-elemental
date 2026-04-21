"""
Ejercicios de Tonalidades + Armaduras (+ Tonos Vecinos) — Fichas 3ºGe.

Convención visual: todos los pentagramas de la ficha deben tener el
MISMO alto de pentagrama y el MISMO tamaño de clave. Para conseguirlo,
cada bloque se renderiza con verovio y luego se escala en el PDF usando
la misma constante K_VB_PER_MM (unidades verovio por mm) que produce
el módulo `generar_escalas` con su configuración. Así la clave, la
separación de las líneas del pentagrama y el grosor visual coinciden.

Bloques disponibles:
 - Tonalidades (2 compases): cada compás muestra una armadura;
   debajo hay 2 líneas por compás para que el alumno escriba la
   tonalidad Mayor y la menor relativa correspondientes.
 - Armaduras (2 compases): pentagrama limpio, debajo el nombre de
   una tonalidad; el alumno dibuja la armadura.
 - Tonos vecinos (1 compás, sin barra, medio pentagrama):
   muestra la armadura de una tonalidad, debajo el nombre y 5 huecos
   para que el alumno escriba los 5 tonos vecinos.

Probabilidad de armaduras con 6 o 7 alteraciones: <5% (muy rara).

Tonalidades + Armaduras comparten un sistema (una línea horizontal)
y se renderizan como dos SVG independientes para evitar que verovio
dibuje becuadros cancelatorios entre armaduras distintas.
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
# Catálogo de tonalidades
# -----------------------------------------------------------------------------
# (nombre en solfeo español, fifths). fifths ∈ [-7, 7]. |fifths| = nº alteraciones.
TONALIDADES = [
    # Mayores
    ("DoM",   0), ("SolM",  1), ("ReM",   2), ("LaM",   3),
    ("MiM",   4), ("SiM",   5), ("Fa#M",  6), ("Do#M",  7),
    ("FaM",  -1), ("SibM", -2), ("MibM", -3), ("LabM", -4),
    ("RebM", -5), ("SolbM",-6), ("DobM", -7),
    # Menores
    ("Lam",   0), ("Mim",   1), ("Sim",   2), ("Fa#m",  3),
    ("Do#m",  4), ("Sol#m", 5), ("Re#m",  6), ("La#m",  7),
    ("Rem",  -1), ("Solm", -2), ("Dom",  -3), ("Fam",  -4),
    ("Sibm", -5), ("Mibm", -6), ("Labm", -7),
]

# Pesos por nº de alteraciones.
# Con estos pesos:
#   - Sobre los 15 valores fifths distintos: P(|f|=6 o 7) ≈ 4/106 ≈ 3.8%.
#   - Sobre las 30 tonalidades distintas:    P(|f|=6 o 7) ≈ 8/212 ≈ 3.8%.
# Ambos bajo el 5% pedido.
PESOS_ALT = {0: 2, 1: 10, 2: 10, 3: 10, 4: 10, 5: 10, 6: 1, 7: 1}

FIFTHS_TODOS = list(range(-7, 8))  # -7..7


def peso_fifths(f):
    return PESOS_ALT[abs(f)]


def peso_tonalidad(t):
    return PESOS_ALT[abs(t[1])]


# -----------------------------------------------------------------------------
# Helpers de tonalidades (solución: M/m relativa + tonos vecinos)
# -----------------------------------------------------------------------------
# Mapa (fifths, es_mayor) → nombre en solfeo español.
_TON_POR_CLAVE = {}
for _nombre, _f in TONALIDADES:
    _es_mayor = _nombre.endswith("M")
    _TON_POR_CLAVE[(_f, _es_mayor)] = _nombre


def nombre_por_fifths(fifths, es_mayor):
    """Devuelve nombre ('DoM', 'Lam', etc.) de la tonalidad con esa
    armadura y esa modalidad. None si no existe (fuera de [-7,7])."""
    return _TON_POR_CLAVE.get((fifths, es_mayor))


def tonalidades_M_m_por_fifths(fifths):
    """Devuelve (mayor, menor_relativa) como par de nombres para una
    armadura dada. Ej: fifths=2 → ('ReM', 'Sim')."""
    return (
        nombre_por_fifths(fifths, True),
        nombre_por_fifths(fifths, False),
    )


def tonos_vecinos(fifths, es_mayor):
    """Devuelve la lista de 5 tonalidades vecinas de (fifths, es_mayor).

    Convención Conservatorio (5 vecinos):
      - Relativa (misma armadura, modalidad cambiada).
      - Dominante: armadura +1 alteración (misma modalidad).
      - Relativa de la Dominante (modalidad cambiada).
      - Subdominante: armadura -1 alteración (misma modalidad).
      - Relativa de la Subdominante (modalidad cambiada).
    """
    out = []
    # Relativa
    out.append(nombre_por_fifths(fifths, not es_mayor))
    # Dominante + relativa
    out.append(nombre_por_fifths(fifths + 1, es_mayor))
    out.append(nombre_por_fifths(fifths + 1, not es_mayor))
    # Subdominante + relativa
    out.append(nombre_por_fifths(fifths - 1, es_mayor))
    out.append(nombre_por_fifths(fifths - 1, not es_mayor))
    return out


# -----------------------------------------------------------------------------
# Sorteo
# -----------------------------------------------------------------------------
def elegir_tonalidades(n_ton=2, n_arm=2, seed=None):
    """Devuelve (ton_fifths, armaduras).

    - ton_fifths: lista de n_ton enteros en [-7..7] distintos. Cada valor
      es la armadura que se dibujará en un compás del bloque Tonalidades;
      el alumno escribe debajo las dos tonalidades (M y m relativa).
    - armaduras: lista de n_arm tuplas (nombre, fifths) distintas. Son
      las tonalidades cuyo nombre se imprimirá debajo de los compases
      limpios del bloque Armaduras; el alumno dibuja la armadura.

    Los fifths de ton_fifths y de armaduras no se solapan (para que el
    mismo dato no aparezca "pedido" y "regalado" en la misma ficha).
    """
    if seed is not None:
        random.seed(seed)

    pesos_f = [peso_fifths(f) for f in FIFTHS_TODOS]
    ton_f = []
    for _ in range(500):
        if len(ton_f) >= n_ton:
            break
        f = random.choices(FIFTHS_TODOS, weights=pesos_f, k=1)[0]
        if f not in ton_f:
            ton_f.append(f)

    arm_pool = [t for t in TONALIDADES if t[1] not in ton_f]
    pesos_arm = [peso_tonalidad(t) for t in arm_pool]
    arm = []
    for _ in range(500):
        if len(arm) >= n_arm:
            break
        t = random.choices(arm_pool, weights=pesos_arm, k=1)[0]
        if t not in arm:
            arm.append(t)
    # Fallback defensivo
    while len(arm) < n_arm:
        arm.append(random.choice(arm_pool))
    return ton_f[:n_ton], arm[:n_arm]


def elegir_tonica_tonos_vecinos(excluir_fifths=(), seed=None):
    """Elige UNA tonalidad para el ejercicio de Tonos Vecinos."""
    if seed is not None:
        random.seed(seed)
    pool = [t for t in TONALIDADES if t[1] not in excluir_fifths]
    pesos = [peso_tonalidad(t) for t in pool]
    return random.choices(pool, weights=pesos, k=1)[0]


# -----------------------------------------------------------------------------
# MusicXML
# -----------------------------------------------------------------------------
def _placeholder_oculto(n=1):
    """N redondas ocultas: obligan a verovio a reservar ancho por compás."""
    nota = """
      <note print-object="no">
        <pitch><step>B</step><octave>4</octave></pitch>
        <duration>4</duration>
        <type>whole</type>
      </note>"""
    return nota * n


def _musicxml_bloque(claves_fifths, key_inicial=None, final_bar=True,
                     n_placeholders=1):
    """Construye un MusicXML de una línea con len(claves_fifths) compases."""
    measures = []
    primer_fifths = key_inicial if key_inicial is not None else (
        claves_fifths[0] if claves_fifths[0] is not None else 0
    )
    m1 = f"""
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <key><fifths>{primer_fifths}</fifths></key>
        <time print-object="no"><beats>4</beats><beat-type>4</beat-type></time>
        <clef><sign>G</sign><line>2</line></clef>
      </attributes>{_placeholder_oculto(n_placeholders)}
    </measure>"""
    measures.append(m1)

    for i, fif in enumerate(claves_fifths[1:], start=2):
        attrs = ""
        if fif is not None:
            attrs = f"<attributes><key><fifths>{fif}</fifths></key></attributes>"
        measures.append(f"""
    <measure number="{i}">
      <print new-system="no"/>{attrs}{_placeholder_oculto(n_placeholders)}
    </measure>""")

    if final_bar:
        last = measures[-1]
        last = last.replace("</measure>",
            '<barline location="right"><bar-style>light-heavy</bar-style></barline>\n    </measure>')
        measures[-1] = last

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name></part-name></score-part>
  </part-list>
  <part id="P1">{"".join(measures)}
  </part>
</score-partwise>"""


def musicxml_tonalidades(ton_fifths, n_placeholders=1):
    """Bloque de len(ton_fifths) compases, cada uno con su armadura."""
    return _musicxml_bloque(
        list(ton_fifths), key_inicial=ton_fifths[0],
        n_placeholders=n_placeholders,
    )


def musicxml_armaduras(arm_list, n_placeholders=0):
    """Bloque de len(arm_list) compases limpios (key=0)."""
    return _musicxml_bloque(
        [0] * len(arm_list), key_inicial=0, n_placeholders=n_placeholders,
    )


def musicxml_tonos_vecinos(fifths, n_placeholders=1):
    """Un único compás CON armadura y SIN barra final (pentagrama abierto
    a la derecha)."""
    return _musicxml_bloque(
        [fifths], key_inicial=fifths, final_bar=False,
        n_placeholders=n_placeholders,
    )


# -----------------------------------------------------------------------------
# Render + coherencia visual con escalas
# -----------------------------------------------------------------------------
# K_VB_PER_MM = unidades verovio por mm de anchura en el PDF final.
# Lo fija `generar_escalas` con su configuración (pageWidth=2100, scale=35,
# adjustPageWidth=False) y ancho_util_mm=160. Medido: vb_w = 14410  ⇒  K≈90.06.
# Respetar este K en los demás bloques garantiza que TODOS los pentagramas
# tengan el mismo alto de pentagrama y el mismo tamaño de clave.
K_VB_PER_MM = 90.06


def _postprocess_keysig_rojo(svg):
    """Postprocesa el SVG de verovio para pintar en rojo las armaduras
    (grupos `class="keySig"`). El pentagrama, la clave y las barras siguen
    en negro. Usamos esto en la hoja de soluciones del bloque Armaduras:
    la respuesta al ejercicio es DIBUJAR la armadura, así que la pintamos
    en rojo sobre el mismo pentagrama en blanco que veía el alumno."""
    return re.sub(
        r'(<g[^>]*class="keySig"[^>]*)>',
        r'\1 style="color:#ff0000;fill:#ff0000;stroke:#ff0000">',
        svg,
    )


def _render_bloque(xml, n_compases, out_png_path, keysig_rojo=False):
    """Renderiza un MusicXML a un PNG (sin padding inferior) y devuelve
    (centros_frac, vb_w). centros_frac: lista de fracciones 0..1 con el
    centro horizontal de cada compás dentro del viewBox.
    vb_w es en unidades verovio → combinado con K_VB_PER_MM da el ancho
    mm necesario para que el pentagrama tenga el mismo alto que el del
    módulo de escalas.

    Si `keysig_rojo=True`, se postprocesa el SVG para pintar en rojo los
    grupos `class="keySig"` (armaduras) antes de pasar a PNG."""
    tk = verovio.toolkit()
    tk.setOptions({
        "pageWidth": 2100,
        "pageHeight": 2970,
        "pageMarginTop": 20, "pageMarginBottom": 20,
        "pageMarginLeft": 20, "pageMarginRight": 20,
        "scale": 35,                # == escalas
        "spacingStaff": 8,
        "spacingSystem": 8,
        "spacingNonLinear": 0.6,
        "spacingLinear": 0.25,
        "adjustPageHeight": True,
        "adjustPageWidth": True,    # aquí SÍ queremos vb_w ajustado al contenido
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
    vb_w = float(vb_match.group(1).split()[2]) if vb_match else 10000.0

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

    pm_match = re.search(
        r'class="page-margin"[^>]*transform="translate\((\-?[\d\.]+),\s*(\-?[\d\.]+)\)"',
        svg,
    )
    pm_x = float(pm_match.group(1)) if pm_match else 0.0

    clef_m = re.search(
        r'class="clef">\s*<use [^>]*transform="translate\((\-?[\d\.]+),',
        svg,
    )
    x_clef = float(clef_m.group(1)) if clef_m else 0.0
    ANCHO_CLEF = 300
    inicio = x_clef + ANCHO_CLEF

    centros = []
    for i in range(n_compases):
        left = inicio if i == 0 else (
            agrup[i - 1] if (i - 1) < len(agrup) else vb_w
        )
        right = agrup[i] if i < len(agrup) else vb_w
        centros.append((pm_x + (left + right) / 2) / vb_w)

    if keysig_rojo:
        svg = _postprocess_keysig_rojo(svg)

    ancho_pix = 2000
    png_bytes = gi.svg_a_png_bytes(svg, ancho_pix)
    with Image.open(io.BytesIO(png_bytes)) as im_rgba:
        if im_rgba.mode == "RGBA":
            fondo = Image.new("RGB", im_rgba.size, (255, 255, 255))
            fondo.paste(im_rgba, (0, 0), mask=im_rgba.split()[3])
        else:
            fondo = im_rgba.convert("RGB")
        fondo.save(out_png_path, "PNG")

    return centros, vb_w


# -----------------------------------------------------------------------------
# Composición PDF: Tonalidades + Armaduras (un sistema)
# -----------------------------------------------------------------------------
def componer_pdf_tonalidades_armaduras(ton_fifths, arm_list, numero_ficha,
                                        out_pdf,
                                        num_tonalidades=5,
                                        num_armaduras=6):
    """PDF con los dos bloques en una línea (Tonalidades a la izquierda,
    Armaduras a la derecha). Mantiene coherencia visual con escalas:
    mismo alto de pentagrama, misma clave."""
    out_pdf = Path(out_pdf)
    # Modo 2-bloques: anchos generosos porque solo hay 2 ejercicios en el sistema.
    xml_ton = musicxml_tonalidades(ton_fifths, n_placeholders=2)
    xml_arm = musicxml_armaduras(arm_list, n_placeholders=1)

    png_ton = out_pdf.with_name(out_pdf.stem + "_ton.png")
    png_arm = out_pdf.with_name(out_pdf.stem + "_arm.png")

    centros_ton, vb_ton = _render_bloque(xml_ton, len(ton_fifths), png_ton)
    centros_arm, vb_arm = _render_bloque(xml_arm, len(arm_list), png_arm)

    gap_mm = 6
    ancho_util_mm = 160

    # Tamaños "ideales" (mismo K que escalas → misma altura de pentagrama):
    ancho_ton_mm = vb_ton / K_VB_PER_MM
    ancho_arm_mm = vb_arm / K_VB_PER_MM

    total_necesario = ancho_ton_mm + gap_mm + ancho_arm_mm
    if total_necesario > ancho_util_mm:
        # Si no cabe, reducimos AMBOS por el mismo factor (mantenemos coherencia).
        factor = (ancho_util_mm - gap_mm) / (ancho_ton_mm + ancho_arm_mm)
        ancho_ton_mm *= factor
        ancho_arm_mm *= factor
        # Nota: si cae aquí, la altura bajará también proporcionalmente.

    img_ton = ImageReader(str(png_ton))
    img_arm = ImageReader(str(png_arm))
    iw_t, ih_t = img_ton.getSize()
    iw_a, ih_a = img_arm.getSize()
    alto_ton_mm = ancho_ton_mm * ih_t / iw_t
    alto_arm_mm = ancho_arm_mm * ih_a / iw_a
    alto_pentagrama_mm = max(alto_ton_mm, alto_arm_mm)

    c = canvas.Canvas(str(out_pdf), pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width / 2, height - 25 * mm, f"Ficha {numero_ficha}")
    c.setFont("Helvetica", 12)
    c.drawString(25 * mm, height - 35 * mm, "Nombre  _________________________")
    c.drawRightString(width - 25 * mm, height - 35 * mm, "Nota  _______")

    x_img = 25 * mm
    y_titulo = height - 55 * mm
    y_img = y_titulo - 8 * mm - alto_pentagrama_mm * mm
    x_arm = x_img + ancho_ton_mm * mm + gap_mm * mm

    c.setFont("Helvetica-Bold", 12)
    c.drawString(x_img, y_titulo, f"{num_tonalidades}. Tonalidades")
    c.drawString(x_arm, y_titulo, f"{num_armaduras}. Armaduras")

    c.drawImage(img_ton, x_img, y_img,
                width=ancho_ton_mm * mm, height=alto_ton_mm * mm)
    c.drawImage(img_arm, x_arm, y_img,
                width=ancho_arm_mm * mm, height=alto_arm_mm * mm)

    # Etiquetas debajo del pentagrama.
    c.setFont("Helvetica-Oblique", 9)
    y_label = y_img - 3 * mm
    # Tonalidades: DOS líneas por compás (M y m relativa).
    for frac in centros_ton:
        x_centro = x_img + ancho_ton_mm * mm * frac
        c.drawCentredString(x_centro, y_label, "______   ______")
    # Armaduras: nombre de la tonalidad por compás.
    for (nombre, _f), frac in zip(arm_list, centros_arm):
        x = x_arm + ancho_arm_mm * mm * frac
        c.drawCentredString(x, y_label, nombre)

    c.showPage()
    c.save()


# -----------------------------------------------------------------------------
# Composición PDF: Tonos vecinos (medio pentagrama, ejercicio aislado)
# -----------------------------------------------------------------------------
def componer_pdf_tonos_vecinos(tonica, numero_ficha, out_pdf,
                                num_enunciado=7):
    """PDF con el ejercicio de Tonos Vecinos. `tonica` = (nombre, fifths).
    Ocupa medio pentagrama (≈80 mm). Debajo: nombre de la tonalidad de
    partida y 5 líneas para que el alumno escriba los tonos vecinos."""
    out_pdf = Path(out_pdf)
    xml = musicxml_tonos_vecinos(tonica[1], n_placeholders=3)
    png = out_pdf.with_name(out_pdf.stem + "_tv.png")
    centros, vb = _render_bloque(xml, 1, png)

    # Medio pentagrama = 80 mm, manteniendo K.
    ancho_mm = vb / K_VB_PER_MM
    if ancho_mm > 80:
        ancho_mm = 80   # recortamos si sale mayor; la altura bajará un pelín

    img = ImageReader(str(png))
    iw, ih = img.getSize()
    alto_mm = ancho_mm * ih / iw

    c = canvas.Canvas(str(out_pdf), pagesize=A4)
    width, height = A4
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width / 2, height - 25 * mm, f"Ficha {numero_ficha}")
    c.setFont("Helvetica", 12)
    c.drawString(25 * mm, height - 35 * mm, "Nombre  _________________________")
    c.drawRightString(width - 25 * mm, height - 35 * mm, "Nota  _______")

    x_img = 25 * mm
    y_titulo = height - 55 * mm
    y_img = y_titulo - 8 * mm - alto_mm * mm

    c.setFont("Helvetica-Bold", 12)
    c.drawString(x_img, y_titulo, f"{num_enunciado}. Tonos vecinos")

    c.drawImage(img, x_img, y_img, width=ancho_mm * mm, height=alto_mm * mm)

    # Etiqueta: nombre de la tonalidad bajo el compás + 5 huecos de respuesta.
    c.setFont("Helvetica-Oblique", 9)
    y_label = y_img - 3 * mm
    x_centro = x_img + ancho_mm * mm * centros[0]
    c.drawCentredString(x_centro, y_label, tonica[0])
    c.drawCentredString(x_centro, y_label - 5 * mm,
                        "_____   _____   _____   _____   _____")

    c.showPage()
    c.save()


# -----------------------------------------------------------------------------
# Composición PDF: 3 bloques en UN sistema (Tonalidades + Armaduras + TV)
# -----------------------------------------------------------------------------
def _preparar_bloque(xml, n_compases, png_path):
    """Renderiza un bloque y devuelve dict con todo lo necesario para componer."""
    centros, vb = _render_bloque(xml, n_compases, png_path)
    img = ImageReader(str(png_path))
    iw, ih = img.getSize()
    return {"centros": centros, "vb": vb, "img": img, "iw": iw, "ih": ih}


def _preparar_bloque_rojo(xml, n_compases, png_path, keysig_rojo=False):
    """Como `_preparar_bloque` pero permite pedir armadura en rojo."""
    centros, vb = _render_bloque(
        xml, n_compases, png_path, keysig_rojo=keysig_rojo,
    )
    img = ImageReader(str(png_path))
    iw, ih = img.getSize()
    return {"centros": centros, "vb": vb, "img": img, "iw": iw, "ih": ih}


def dibujar_en_canvas(c, x_ini, y_top,
                       ton_fifths, arm_list, tonica_tv,
                       num_tonalidades, num_armaduras, num_tonos_vecinos,
                       out_pdf_path,
                       ancho_util_mm=160, modo_solucion=False):
    """Dibuja los 3 bloques TA+TV en una sola línea a partir de `y_top`.
    Devuelve `y_bottom`.

    En modo solución:
      - Tonalidades: debajo de cada armadura, "Mayor / menor relativa"
        (rojo).
      - Armaduras: el bloque se redibuja con las armaduras REALES visibles
        (en lugar del pentagrama limpio del ejercicio alumno).
      - Tonos vecinos: los 5 tonos en rojo debajo del nombre de la tónica.
    """
    out_pdf_path = Path(out_pdf_path)

    png_ton = out_pdf_path.with_name(out_pdf_path.stem + "_ton.png")
    png_arm = out_pdf_path.with_name(out_pdf_path.stem + "_arm.png")
    png_tv = out_pdf_path.with_name(out_pdf_path.stem + "_tv.png")

    # Armaduras:
    #  - Modo alumno: pentagramas limpios (key=0), el alumno dibuja la
    #    armadura correspondiente al nombre de la tonalidad que se indica
    #    debajo de cada compás.
    #  - Modo solución: el mismo pentagrama pero CON las armaduras reales
    #    dibujadas en ROJO (postprocesando el SVG para colorear los
    #    grupos `keySig`). Así el alto del pentagrama y la clave coinciden
    #    exactamente con la versión del alumno; lo único que cambia es
    #    que aparecen las alteraciones en rojo.
    if modo_solucion:
        xml_arm = _musicxml_bloque(
            [f for (_, f) in arm_list],
            key_inicial=arm_list[0][1],
            n_placeholders=0,
            final_bar=True,
        )
    else:
        xml_arm = musicxml_armaduras(arm_list, n_placeholders=0)

    bton = _preparar_bloque(
        musicxml_tonalidades(ton_fifths, n_placeholders=1),
        len(ton_fifths), png_ton,
    )
    barm = _preparar_bloque_rojo(
        xml_arm, len(arm_list), png_arm, keysig_rojo=modo_solucion,
    )
    btv = _preparar_bloque(
        musicxml_tonos_vecinos(tonica_tv[1], n_placeholders=1),
        1, png_tv,
    )

    gap_mm = 4
    num_gaps = 2

    aton = bton["vb"] / K_VB_PER_MM
    aarm = barm["vb"] / K_VB_PER_MM
    atv = btv["vb"] / K_VB_PER_MM

    total = aton + aarm + atv + num_gaps * gap_mm
    if total > ancho_util_mm:
        factor = (ancho_util_mm - num_gaps * gap_mm) / (aton + aarm + atv)
        aton *= factor
        aarm *= factor
        atv *= factor

    alto_ton = aton * bton["ih"] / bton["iw"]
    alto_arm = aarm * barm["ih"] / barm["iw"]
    alto_tv = atv * btv["ih"] / btv["iw"]
    alto_max = max(alto_ton, alto_arm, alto_tv)

    x_ton = x_ini
    x_arm = x_ton + aton * mm + gap_mm * mm
    x_tv = x_arm + aarm * mm + gap_mm * mm
    y_titulo = y_top
    y_img = y_titulo - 6 * mm - alto_max * mm

    c.setFont("Helvetica-Bold", 12)
    c.drawString(x_ton, y_titulo, f"{num_tonalidades}. Tonalidades")
    c.drawString(x_arm, y_titulo, f"{num_armaduras}. Armaduras")
    c.drawString(x_tv, y_titulo, f"{num_tonos_vecinos}. Tonos vecinos")

    c.drawImage(bton["img"], x_ton, y_img,
                width=aton * mm, height=alto_ton * mm)
    # Armaduras: mismo PNG en alumno y solución; en solución la armadura
    # ya viene pintada en rojo dentro del render, manteniendo intactos el
    # pentagrama, la clave y el tamaño global del ejercicio.
    c.drawImage(barm["img"], x_arm, y_img,
                width=aarm * mm, height=alto_arm * mm)
    c.drawImage(btv["img"], x_tv, y_img,
                width=atv * mm, height=alto_tv * mm)

    c.setFont("Helvetica-Oblique", 10)
    y_label = y_img - 3.5 * mm

    # --- Tonalidades ---
    for idx, frac in enumerate(bton["centros"]):
        x = x_ton + aton * mm * frac
        # Líneas siempre.
        c.setFillColorRGB(0, 0, 0)
        c.drawCentredString(x, y_label, "____   ____")
        if modo_solucion:
            f_aqui = ton_fifths[idx]
            nm_M, nm_m = tonalidades_M_m_por_fifths(f_aqui)
            c.saveState()
            c.setFillColorRGB(1, 0, 0)
            c.drawCentredString(
                x, y_label + 0.6 * mm, f"{nm_M}   {nm_m}"
            )
            c.restoreState()

    # --- Armaduras (enunciado) ---
    # El nombre de la tonalidad se imprime siempre bajo su compás, tanto
    # en la ficha del alumno como en la solución.
    for (nombre, _f), frac in zip(arm_list, barm["centros"]):
        x = x_arm + aarm * mm * frac
        c.drawCentredString(x, y_label, nombre)

    # --- Tonos vecinos ---
    # Nombre de la tónica ARRIBA del pentagrama, a la IZQUIERDA (encima
    # de la armadura), pegado al pentagrama. Las 5 líneas de respuesta
    # quedan a la misma altura que las etiquetas de Tonalidades y
    # Armaduras (y_label), y SÓLO aparecen en modo alumno.
    # En solución, la respuesta se coloca centrada debajo del pentagrama.
    x_tv_tonica = x_tv + atv * mm * 0.22
    x_tv_c = x_tv + atv * mm * btv["centros"][0]
    y_tonica_top = y_img + alto_tv * mm + 0.3 * mm
    c.setFont("Helvetica-Oblique", 10)
    c.drawCentredString(x_tv_tonica, y_tonica_top, tonica_tv[0])

    if modo_solucion:
        nombres_vec = tonos_vecinos(
            tonica_tv[1], tonica_tv[0].endswith("M")
        )
        c.saveState()
        c.setFillColorRGB(1, 0, 0)
        c.drawCentredString(
            x_tv_c, y_label, "  ".join(nombres_vec),
        )
        c.restoreState()
    else:
        # Líneas de respuesta SOLO en modo alumno.
        c.setFont("Helvetica-Oblique", 10)
        c.drawCentredString(
            x_tv_c, y_label, "___  ___  ___  ___  ___",
        )

    return y_label - 3 * mm


def componer_pdf_sistema_completo(ton_fifths, arm_list, tonica_tv,
                                   numero_ficha, out_pdf,
                                   num_tonalidades=5,
                                   num_armaduras=6,
                                   num_tonos_vecinos=7,
                                   modo_solucion=False):
    """PDF con Tonalidades + Armaduras + Tonos Vecinos en UN SOLO SISTEMA."""
    out_pdf = Path(out_pdf)
    c = canvas.Canvas(str(out_pdf), pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width / 2, height - 25 * mm, f"Ficha {numero_ficha}")
    c.setFont("Helvetica", 12)
    c.drawString(25 * mm, height - 35 * mm, "Nombre  _________________________")
    c.drawRightString(width - 25 * mm, height - 35 * mm, "Nota  _______")

    dibujar_en_canvas(
        c, 25 * mm, height - 55 * mm,
        ton_fifths, arm_list, tonica_tv,
        num_tonalidades, num_armaduras, num_tonos_vecinos,
        out_pdf_path=out_pdf, modo_solucion=modo_solucion,
    )

    c.showPage()
    c.save()


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3, help="cuántas fichas generar")
    ap.add_argument("--num-tonalidades", type=int, default=5)
    ap.add_argument("--num-armaduras", type=int, default=6)
    ap.add_argument("--num-tonos-vecinos", type=int, default=7)
    ap.add_argument("--modo",
                    choices=("sistema", "ta", "tv", "todos"),
                    default="sistema",
                    help=("sistema=3 bloques TA+TV en una línea (por defecto); "
                          "ta=solo Tonalidades+Armaduras; "
                          "tv=solo Tonos Vecinos; "
                          "todos=las 3 fichas separadas"))
    args = ap.parse_args()

    out_dir = Path("/sessions/elegant-busy-goldberg/mnt/outputs")
    out_dir.mkdir(parents=True, exist_ok=True)

    for i in range(1, args.n + 1):
        ton_f, arm = elegir_tonalidades(n_ton=2, n_arm=2, seed=4000 + i)
        tonica_tv = elegir_tonica_tonos_vecinos(
            excluir_fifths=set(ton_f) | {a[1] for a in arm},
            seed=5000 + i,
        )

        if args.modo in ("sistema", "todos"):
            pdf_sys = out_dir / f"prototipo_ficha_{i}_ej567.pdf"
            print(f"Generando {pdf_sys.name}")
            print(f"   Tonalidades (armaduras): {ton_f}")
            print(f"   Armaduras (nombres):     {[a[0] for a in arm]}")
            print(f"   Tonos vecinos (tónica):  {tonica_tv[0]}")
            componer_pdf_sistema_completo(
                ton_f, arm, tonica_tv, i, pdf_sys,
                num_tonalidades=args.num_tonalidades,
                num_armaduras=args.num_armaduras,
                num_tonos_vecinos=args.num_tonos_vecinos,
            )

        if args.modo in ("ta", "todos"):
            pdf_ta = out_dir / f"prototipo_ficha_{i}_ej56.pdf"
            print(f"Generando {pdf_ta.name}")
            componer_pdf_tonalidades_armaduras(
                ton_f, arm, i, pdf_ta,
                num_tonalidades=args.num_tonalidades,
                num_armaduras=args.num_armaduras,
            )

        if args.modo in ("tv", "todos"):
            pdf_tv = out_dir / f"prototipo_ficha_{i}_ej7.pdf"
            print(f"Generando {pdf_tv.name}  (tónica {tonica_tv[0]})")
            componer_pdf_tonos_vecinos(
                tonica_tv, i, pdf_tv,
                num_enunciado=args.num_tonos_vecinos,
            )

    print("\nListo")


if __name__ == "__main__":
    main()
