"""
Ejercicio 3 (Escalas) — Fichas de Teoría 3ºGe.

Un único ejercicio con DOS compases. En cada compás:
 - El pentagrama aparece vacío (solo clave y armadura).
 - Debajo, alineada al INICIO del compás (después de clave / barra media),
   la etiqueta de la escala a escribir ("Re menor armónica", etc.).
El alumno escribe las notas de la escala sobre el pentagrama.

Entre ambos compases: doble barra simple (light-light).
Al final del ejercicio: doble barra final (light-heavy).
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

# Reutilizamos utilidades del módulo de intervalos (render verovio, etc.).
import generar_intervalos as gi


# -----------------------------------------------------------------------------
# Catálogo de escalas
# -----------------------------------------------------------------------------
# Tónicas disponibles (nombre solfeo español + step inglés + octava base).
# Elegidas para que la escala ascendente cumpla el rango La3–Sol5 cómodamente.
TONICAS = [
    ("La",  "A", 3),
    ("Si",  "B", 3),
    ("Do",  "C", 4),
    ("Re",  "D", 4),
    ("Mi",  "E", 4),
    ("Fa",  "F", 4),
    ("Sol", "G", 4),
    ("La",  "A", 4),  # LA4 a LA5 = MIDI 69..81, se pasa. Filtraremos abajo.
]

# Tipos de escala con el nombre en español de conservatorio.
# Siempre se muestran con la palabra "menor" por delante.
TIPOS_ESCALA = [
    "menor natural",
    "menor armónica",
    "menor melódica",
    "menor dórica",
]

# Peso de cada tipo en el sorteo. "Menor natural" debe ser la menos
# probable (se practica menos porque es más sencilla).
PESOS_TIPOS = {
    "menor natural":  1,
    "menor armónica": 3,
    "menor melódica": 3,
    "menor dórica":   3,
}

# Patrones de semitonos desde la tónica (7 notas distintas, sin la octava).
PATRONES = {
    "menor natural":  [0, 2, 3, 5, 7, 8, 10],
    "menor armónica": [0, 2, 3, 5, 7, 8, 11],
    "menor melódica": [0, 2, 3, 5, 7, 9, 11],   # ascendente
    "menor dórica":   [0, 2, 3, 5, 7, 9, 10],
}


def generar_escala_notas(step_tonica, octava_tonica, tipo):
    """Devuelve lista de 7 tuplas (step, octave, alter) con las notas de
    la escala ascendente empezando por la tónica (sin repetir la octava)."""
    patron = PATRONES[tipo]
    midi_ton = gi.midi_nota(step_tonica, octava_tonica, 0)
    idx_ton = gi.STEPS.index(step_tonica)
    notas = []
    for i in range(7):
        idx = (idx_ton + i) % 7
        octava = octava_tonica + (idx_ton + i) // 7
        step = gi.STEPS[idx]
        midi_natural = gi.midi_nota(step, octava, 0)
        alter = midi_ton + patron[i] - midi_natural
        notas.append((step, octava, alter))
    return notas


def contar_alteraciones(notas):
    return sum(1 for _s, _o, a in notas if a != 0)


MAX_ALTERACIONES = 6  # tope de alteraciones en la respuesta del alumno


def elegir_escalas(seed=None):
    """Devuelve dos tuplas (tonica_nombre, step, octava, tipo) para los
    dos compases del ejercicio. Filtros:
      - Tónica tal que la 8ª ascendente no se pase de Sol5.
      - Escala con un máximo de MAX_ALTERACIONES alteraciones.
      - 'menor natural' con menor probabilidad (PESOS_TIPOS).
      - Evita duplicar la misma combinación exacta en el ejercicio.
    """
    if seed is not None:
        random.seed(seed)

    # Tónicas cuya escala ascendente quepa razonablemente en La3–Sol5.
    validas = [
        (n, s, o) for (n, s, o) in TONICAS
        if gi.midi_nota(s, o, 0) + 12 <= gi.MIDI_MAX + 2
    ]
    if not validas:
        validas = [("La", "A", 3), ("Re", "D", 4)]

    tipos_pond = list(PESOS_TIPOS.keys())
    pesos = [PESOS_TIPOS[t] for t in tipos_pond]

    picks = []
    for _ in range(2):
        for _ in range(100):
            nombre, step, oct_ = random.choice(validas)
            tipo = random.choices(tipos_pond, weights=pesos, k=1)[0]
            notas = generar_escala_notas(step, oct_, tipo)
            if contar_alteraciones(notas) > MAX_ALTERACIONES:
                continue
            cand = (nombre, step, oct_, tipo)
            if cand not in picks:
                picks.append(cand)
                break
        else:
            picks.append((nombre, step, oct_, tipo))
    return picks


# -----------------------------------------------------------------------------
# MusicXML: 2 compases vacíos (clave sol, sin armadura) con doble barra
# simple intermedia y doble barra final.
# -----------------------------------------------------------------------------
def musicxml_ejercicio_escalas():
    """Devuelve el MusicXML. Cada compás tiene un silencio de compás OCULTO
    para que verovio reserve espacio suficiente pero no dibuje nada."""
    # Time signature grande oculta para forzar un compás ancho que el alumno
    # pueda rellenar con 8 redondas. Usamos 8/1 (8 redondas por compás) y
    # ponemos 8 notas-placeholder ocultas (print-object="no") para que verovio
    # reserve ~8 posiciones horizontales por compás.
    def placeholders_ocultos(n_notas=8):
        notas = []
        for _ in range(n_notas):
            notas.append("""
      <note print-object="no">
        <pitch><step>B</step><octave>4</octave></pitch>
        <duration>4</duration>
        <type>whole</type>
      </note>""")
        return "".join(notas)

    first_attrs = """
        <attributes>
          <divisions>1</divisions>
          <key><fifths>0</fifths></key>
          <time print-object="no"><beats>32</beats><beat-type>4</beat-type></time>
          <clef><sign>G</sign><line>2</line></clef>
        </attributes>"""

    # Compás 1: placeholders ocultos + barra derecha doble simple (light-light).
    m1 = f"""
    <measure number="1">{first_attrs}{placeholders_ocultos(4)}
      <barline location="right"><bar-style>light-light</bar-style></barline>
    </measure>"""

    # Compás 2: print new-system="no" fuerza que siga en la misma línea.
    # Placeholders ocultos + barra final doble (light-heavy).
    m2 = f"""
    <measure number="2">
      <print new-system="no"/>{placeholders_ocultos(4)}
      <barline location="right"><bar-style>light-heavy</bar-style></barline>
    </measure>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name></part-name></score-part>
  </part-list>
  <part id="P1">{m1}{m2}
  </part>
</score-partwise>"""


# -----------------------------------------------------------------------------
# Extracción de posiciones "inicio de compás" (después de clave / barra media)
# -----------------------------------------------------------------------------
def extraer_anclas(svg_str):
    """Devuelve fracciones horizontales (0..1) de los puntos de anclaje:
      - ancla[0]: FIN visual de la clave (tras la clave).
      - ancla[1]: posición de la barra medial.
    El componer_pdf añade luego un gap en mm IGUAL a ambas etiquetas,
    garantizando la misma separación visual."""
    vb_match = re.search(
        r'class="definition-scale"[^>]*viewBox="([\d\s\.\-]+)"', svg_str
    )
    if not vb_match:
        return []
    vb_width = float(vb_match.group(1).split()[2])

    pm_match = re.search(
        r'class="page-margin"[^>]*transform="translate\((\-?[\d\.]+),\s*(\-?[\d\.]+)\)"',
        svg_str,
    )
    pm_x = float(pm_match.group(1)) if pm_match else 0.0

    barras = []
    for m in re.finditer(r'class="barLine">\s*<path d="M(\-?[\d\.]+)\s', svg_str):
        barras.append(float(m.group(1)))
    barras.sort()
    agrup = []
    for b in barras:
        if agrup and abs(b - agrup[-1]) < 80:
            agrup[-1] = (agrup[-1] + b) / 2
        else:
            agrup.append(b)

    clef_m = re.search(
        r'class="clef">\s*<use [^>]*transform="translate\((\-?[\d\.]+),',
        svg_str,
    )
    x_clef = float(clef_m.group(1)) if clef_m else 0.0
    # Ancho visual aproximado del glifo de clave de sol (scale 0.72 interno
    # de verovio). Calibrado empíricamente para scale global=35.
    ANCHO_CLEF = 300

    if len(agrup) < 1:
        return []
    fin_clef = x_clef + ANCHO_CLEF
    barra_media = agrup[0]
    return [
        (pm_x + fin_clef) / vb_width,
        (pm_x + barra_media) / vb_width,
    ]


# -----------------------------------------------------------------------------
# MusicXML con las notas de la escala ya escritas (versión SOLUCIÓN).
# -----------------------------------------------------------------------------
def _alter_to_xml(alter):
    """Alter → XML: 0, ±1, ±2."""
    return f"<alter>{alter}</alter>" if alter else ""


def musicxml_ejercicio_escalas_solucion(lista_escalas):
    """Dos compases con las notas de la escala escritas (redondas).
    La lista debe tener 2 elementos (nombre, step, octava, tipo)."""
    def notas_xml(step_ton, oct_ton, tipo):
        notas = generar_escala_notas(step_ton, oct_ton, tipo)
        out = []
        for (s, o, a) in notas:
            alter_xml = _alter_to_xml(a)
            pitch = (
                f"<pitch><step>{s}</step>"
                f"{alter_xml}<octave>{o}</octave></pitch>"
            )
            out.append(
                f"\n      <note color=\"#FF0000\">{pitch}"
                "<duration>4</duration><type>whole</type></note>"
            )
        return "".join(out)

    first_attrs = """
        <attributes>
          <divisions>1</divisions>
          <key><fifths>0</fifths></key>
          <time print-object="no"><beats>32</beats><beat-type>4</beat-type></time>
          <clef><sign>G</sign><line>2</line></clef>
        </attributes>"""

    (n1, s1, o1, t1) = lista_escalas[0]
    (n2, s2, o2, t2) = lista_escalas[1]

    m1 = (
        f'\n    <measure number="1">{first_attrs}'
        f'{notas_xml(s1, o1, t1)}'
        '\n      <barline location="right"><bar-style>light-light</bar-style></barline>'
        '\n    </measure>'
    )
    m2 = (
        '\n    <measure number="2">'
        '\n      <print new-system="no"/>'
        f'{notas_xml(s2, o2, t2)}'
        '\n      <barline location="right"><bar-style>light-heavy</bar-style></barline>'
        '\n    </measure>'
    )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name></part-name></score-part>
  </part-list>
  <part id="P1">{m1}{m2}
  </part>
</score-partwise>"""


# -----------------------------------------------------------------------------
# Dibujar dentro de un canvas ya abierto (firma compatible con la ficha)
# -----------------------------------------------------------------------------
def _render_png_escalas(xml, png_path, padding_inf_mm=9):
    """Renderiza el MusicXML a PNG. Devuelve (anclas, ancho_mm_natural)."""
    tk = verovio.toolkit()
    tk.setOptions({
        "pageWidth": 2100,
        "pageHeight": 2970,
        "pageMarginTop": 20, "pageMarginBottom": 20,
        "pageMarginLeft": 20, "pageMarginRight": 20,
        "scale": 35,
        "spacingStaff": 8,
        "spacingSystem": 8,
        "spacingNonLinear": 0.6,
        "spacingLinear": 0.25,
        "adjustPageHeight": True,
        "adjustPageWidth": False,
        "barLineWidth": 0.3,
        "staffLineWidth": 0.2,
        "header": "none",
        "footer": "none",
        "breaks": "none",
    })
    tk.loadData(xml)
    tk.redoLayout()
    svg = tk.renderToSVG(1)
    anclas = extraer_anclas(svg)

    # Mismo patrón visual que otros ejercicios: renderizar con el ancho
    # natural y luego escalar.
    vb_match = re.search(
        r'class="definition-scale"[^>]*viewBox="([\d\s\.\-]+)"', svg
    )
    vb_w = float(vb_match.group(1).split()[2]) if vb_match else 2100.0
    K_VB_PER_MM = 90.06
    ancho_mm_natural = vb_w / K_VB_PER_MM

    dpi = 300
    ancho_pix = max(400, int(ancho_mm_natural / 25.4 * dpi))
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

    return anclas, ancho_mm_natural


def dibujar_en_canvas(c, x_ini, y_top, lista_escalas, num_enunciado,
                      out_pdf_path, ancho_util_mm=160, modo_solucion=False):
    """Dibuja el ejercicio de Escalas menores en `c` a partir de `y_top`.
    Devuelve el Y del borde inferior (y_bottom)."""
    out_pdf_path = Path(out_pdf_path)

    if modo_solucion:
        xml = musicxml_ejercicio_escalas_solucion(lista_escalas)
    else:
        xml = musicxml_ejercicio_escalas()

    png_path = out_pdf_path.with_name(
        out_pdf_path.stem + f"_escalas_{num_enunciado}.png"
    )
    anclas, ancho_mm_natural = _render_png_escalas(xml, png_path)

    img = ImageReader(str(png_path))
    iw, ih = img.getSize()
    factor = min(1.0, ancho_util_mm / ancho_mm_natural)
    ancho_pdf_mm = ancho_mm_natural * factor
    alto_mm = ancho_pdf_mm * ih / iw

    # Título
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x_ini, y_top, f"{num_enunciado}. Escalas menores")

    # Imagen del pentagrama centrada en el ancho útil
    ancho_pdf = ancho_pdf_mm * mm
    alto_pdf = alto_mm * mm
    x_img = x_ini + (ancho_util_mm - ancho_pdf_mm) * mm / 2
    y_img = y_top - 6 * mm - alto_pdf
    c.drawImage(img, x_img, y_img, width=ancho_pdf, height=alto_pdf)

    # Etiquetas debajo de cada compás
    y_label = y_img + 6 * mm
    GAP_ETIQUETA_MM = 3.5
    c.setFont("Helvetica-Oblique", 9)
    if len(anclas) == 2:
        for (nombre, _s, _o, tipo), frac in zip(lista_escalas, anclas):
            x = x_img + ancho_pdf * frac + GAP_ETIQUETA_MM * mm
            c.drawString(x, y_label, f"{nombre} {tipo}")
    else:
        for i, (nombre, _s, _o, tipo) in enumerate(lista_escalas):
            x = x_img + ancho_pdf * (0.08 + 0.5 * i)
            c.drawString(x, y_label, f"{nombre} {tipo}")

    return y_img


# -----------------------------------------------------------------------------
# Composición del PDF (standalone, para pruebas sueltas)
# -----------------------------------------------------------------------------
def componer_pdf_escalas(lista_escalas, numero_ficha, out_pdf, num_enunciado=3):
    """Genera un PDF con el ejercicio de Escalas: 2 compases vacíos y la
    etiqueta de cada escala al inicio del compás, debajo del pentagrama.
    `num_enunciado` es el número que aparece delante del título (ajustable
    según el orden final que tenga el ejercicio en la ficha completa)."""
    xml = musicxml_ejercicio_escalas()

    tk = verovio.toolkit()
    tk.setOptions({
        "pageWidth": 2100,
        "pageHeight": 2970,
        "pageMarginTop": 20, "pageMarginBottom": 20,
        "pageMarginLeft": 20, "pageMarginRight": 20,
        "scale": 35,
        "spacingStaff": 8,
        "spacingSystem": 8,
        "spacingNonLinear": 0.6,
        "spacingLinear": 0.25,
        "adjustPageHeight": True,
        "adjustPageWidth": False,   # mantener pageWidth fijo = mismo viewBox
                                     # width que en intervalos ⇒ staff alto
                                     # proporcionalmente igual.
        "barLineWidth": 0.3,
        "staffLineWidth": 0.2,
        "header": "none",
        "footer": "none",
        "breaks": "none",   # no romper sistemas automáticamente
    })
    tk.loadData(xml)
    tk.redoLayout()
    svg = tk.renderToSVG(1)

    anclas = extraer_anclas(svg)

    # SVG → PNG
    ancho_util_mm = 160
    dpi = 300
    ancho_pix = int(ancho_util_mm / 25.4 * dpi)
    padding_inf_mm = 9  # espacio para escribir la etiqueta y notas graves
    padding_inf_px = int(padding_inf_mm / 25.4 * dpi)
    png_bytes = gi.svg_a_png_bytes(svg, ancho_pix)
    with Image.open(io.BytesIO(png_bytes)) as im_rgba:
        w0, h0 = im_rgba.size
        fondo = Image.new("RGB", (w0, h0 + padding_inf_px), (255, 255, 255))
        if im_rgba.mode == "RGBA":
            fondo.paste(im_rgba, (0, 0), mask=im_rgba.split()[3])
        else:
            fondo.paste(im_rgba, (0, 0))
        png_path = Path(out_pdf).with_suffix(".png")
        fondo.save(png_path, "PNG")

    img = ImageReader(str(png_path))
    iw, ih = img.getSize()
    ancho_pdf = ancho_util_mm * mm
    alto_pdf = ancho_pdf * ih / iw

    c = canvas.Canvas(str(out_pdf), pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width / 2, height - 25 * mm, f"Ficha {numero_ficha}")
    c.setFont("Helvetica", 12)
    c.drawString(25 * mm, height - 35 * mm, "Nombre  _________________________")
    c.drawRightString(width - 25 * mm, height - 35 * mm, "Nota  _______")

    c.setFont("Helvetica-Bold", 12)
    c.drawString(25 * mm, height - 55 * mm, f"{num_enunciado}. Escalas")

    x_img = 25 * mm
    y_img = height - 55 * mm - 8 * mm - alto_pdf
    c.drawImage(img, x_img, y_img, width=ancho_pdf, height=alto_pdf)

    # Etiquetas al inicio de cada compás, debajo del pentagrama.
    # Gap IGUAL en mm desde la clave (etiqueta 1) y desde la barra medial
    # (etiqueta 2), para que la separación visual sea idéntica.
    y_label = y_img + 6 * mm     # pegado al pentagrama (deja ~3 mm para líneas
                                   # adicionales graves que escriba el alumno)
    GAP_ETIQUETA_MM = 3.5         # algo más separado de clave / barra media
    c.setFont("Helvetica-Oblique", 9)
    if len(anclas) == 2:
        for (nombre, _step, _oct, tipo), frac in zip(lista_escalas, anclas):
            x = x_img + ancho_pdf * frac + GAP_ETIQUETA_MM * mm
            c.drawString(x, y_label, f"{nombre} {tipo}")
    else:
        for i, (nombre, _step, _oct, tipo) in enumerate(lista_escalas):
            x = x_img + ancho_pdf * (0.08 + 0.5 * i)
            c.drawString(x, y_label, f"{nombre} {tipo}")

    c.showPage()
    c.save()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3, help="cuántas fichas generar")
    args = ap.parse_args()

    out_dir = Path("/sessions/elegant-busy-goldberg/mnt/outputs")
    out_dir.mkdir(parents=True, exist_ok=True)

    for i in range(1, args.n + 1):
        escalas = elegir_escalas(seed=3000 + i)
        pdf_path = out_dir / f"prototipo_ficha_{i}_ej3.pdf"
        print(f"Generando {pdf_path.name} con escalas:")
        for nombre, s, o, tipo in escalas:
            print(f"   · {nombre} {tipo}  (tónica {s}{o})")
        componer_pdf_escalas(escalas, i, pdf_path)
    print("\nListo")


if __name__ == "__main__":
    main()
