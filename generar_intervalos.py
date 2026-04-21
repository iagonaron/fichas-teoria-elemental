"""
Prototipo del Ejercicio 2 (Intervalos) de las Fichas de Teoría 3ºGe.

Dos variantes:
 - Intervalos A: se dan DOS notas por compás (melódico o armónico) y el
   alumno escribe el nombre del intervalo.
 - Intervalos B: se da UNA nota y la etiqueta del intervalo; el alumno
   escribe la nota respuesta.

Ambos comparten la misma infraestructura (catálogo, rangos, validaciones,
render verovio, composición reportlab).
"""

import argparse
import random
import io
import re
import verovio
import cairosvg
from pathlib import Path
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader


def extraer_centros_compases(svg_str, n_compases):
    """Dado un SVG de verovio, devuelve una lista con la fracción horizontal
    (0..1) del CENTRO de cada compás dentro del ancho total del SVG.
    - Para los compases 2..N: centro = punto medio entre barra izquierda y
      barra derecha.
    - Para el compás 1: centro = punto medio entre el final de la clave y
      la barra derecha.
    Los valores devueltos están listos para multiplicar por ancho_pdf y
    sumarle x_img (offset horizontal de la imagen en la página).
    """
    # viewBox del inner svg
    vb_match = re.search(
        r'class="definition-scale"[^>]*viewBox="([\d\s\.\-]+)"', svg_str
    )
    if not vb_match:
        return []
    vb_width = float(vb_match.group(1).split()[2])
    # Traslación del grupo page-margin
    pm_match = re.search(
        r'class="page-margin"[^>]*transform="translate\((\-?[\d\.]+),\s*(\-?[\d\.]+)\)"',
        svg_str,
    )
    pm_x = float(pm_match.group(1)) if pm_match else 0.0
    # X de cada barLine (`<path d="M X Y L X Y2" ... />`)
    barras = []
    for m in re.finditer(r'class="barLine">\s*<path d="M(\-?[\d\.]+)\s', svg_str):
        barras.append(float(m.group(1)))
    barras.sort()
    # Agrupar barras muy cercanas (p. ej. doble barra final: fina + gruesa)
    agrup = []
    for b in barras:
        if agrup and abs(b - agrup[-1]) < 60:
            agrup[-1] = (agrup[-1] + b) / 2
        else:
            agrup.append(b)
    # Si no coincide el número esperado, devolvemos vacío para fallback
    if len(agrup) != n_compases:
        return []
    # Posición horizontal donde "acaba" la clave (aprox.): X del glifo +
    # ancho estimado del glifo de clave de sol en las unidades de verovio.
    clef_m = re.search(
        r'class="clef">\s*<use [^>]*transform="translate\((\-?[\d\.]+),',
        svg_str,
    )
    x_clef = float(clef_m.group(1)) if clef_m else 0.0
    ANCHO_CLEF = 500  # unidades viewBox; calibrado para scale=35 en verovio
    x_fin_clef = x_clef + ANCHO_CLEF
    # Centros en viewBox
    centros = []
    for i in range(n_compases):
        if i == 0:
            centro = (x_fin_clef + agrup[0]) / 2
        else:
            centro = (agrup[i - 1] + agrup[i]) / 2
        centros.append((pm_x + centro) / vb_width)
    return centros


# -----------------------------------------------------------------------------
# Catálogo de intervalos usables en 3ºGe según KIT SALVAVIDAS
# -----------------------------------------------------------------------------
# Tuplas: (etiqueta, semitonos, "grados diatónicos" = número del intervalo - 1)
INTERVALOS = [
    ("2m", 1, 1),
    ("2M", 2, 1),
    ("2A", 3, 1),
    ("3m", 3, 2),
    ("3M", 4, 2),
    ("4J", 5, 3),
    ("4A", 6, 3),
    ("5D", 6, 4),
    ("5J", 7, 4),
    ("5A", 8, 4),
    ("6m", 8, 5),
    ("6M", 9, 5),
    ("7m", 10, 6),
    ("7M", 11, 6),
    ("8J", 12, 7),
]

# Posibles steps+octavas de partida (rango La3–Sol5).
# La alteración se decide aparte.
NOTAS_PARTIDA_SO = [
    ("A", 3), ("B", 3),
    ("C", 4), ("D", 4), ("E", 4), ("F", 4), ("G", 4),
    ("A", 4), ("B", 4),
    ("C", 5), ("D", 5), ("E", 5), ("F", 5), ("G", 5),
]

# Combinaciones step+alter que dan notas "raras" (enharmónicos poco usados
# en 3ºGe). Las evitamos para no confundir al alumno, tanto en la partida
# como en la respuesta.
RARAS = {("F", -1), ("C", -1), ("B", 1), ("E", 1)}

# ----- Utilidades MIDI-like para cálculo de respuesta -----
STEPS = ["C", "D", "E", "F", "G", "A", "B"]
STEP_ST = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# Rango válido para partida Y respuesta: La3 (MIDI 57) – Sol5 (MIDI 79)
def midi_nota(step, octave, alter):
    return 12 * (octave + 1) + STEP_ST[step] + alter

MIDI_MIN = midi_nota("A", 3, 0)   # 57
MIDI_MAX = midi_nota("G", 5, 0)   # 79


def calcular_intervalo(nota1, nota2):
    """Dadas dos notas (step, octave, alter), devuelve (etiqueta, direccion)
    si el intervalo entre ellas está en el catálogo; None si no."""
    s1, o1, a1 = nota1
    s2, o2, a2 = nota2
    m1 = midi_nota(s1, o1, a1)
    m2 = midi_nota(s2, o2, a2)
    if m1 == m2:
        return None  # unísono no está en el catálogo
    direccion = "asc" if m2 > m1 else "desc"
    semitonos = abs(m2 - m1)
    idx1 = STEPS.index(s1)
    idx2 = STEPS.index(s2)
    grados = abs((o2 - o1) * 7 + (idx2 - idx1))
    for lab, sem_i, gr_i in INTERVALOS:
        if sem_i == semitonos and gr_i == grados:
            return lab, direccion
    return None


def calcular_respuesta(step, octave, alter, grados_int, semitonos_int, direccion):
    """Dada nota de partida y el intervalo pedido, devuelve la nota de respuesta
    como (step, octave, alter, midi). La alteración puede ser cualquier entero
    (incluyendo ±2 = doble alteración); quien llama decide si aceptarla."""
    idx = STEPS.index(step)
    signo = 1 if direccion == "asc" else -1
    midi_resp = midi_nota(step, octave, alter) + signo * semitonos_int
    idx_resp_raw = idx + signo * grados_int
    octave_shift, idx_resp = divmod(idx_resp_raw, 7)
    octave_resp = octave + octave_shift
    step_resp = STEPS[idx_resp]
    midi_natural = midi_nota(step_resp, octave_resp, 0)
    alter_resp = midi_resp - midi_natural
    return step_resp, octave_resp, alter_resp, midi_resp


def elegir_intervalos(n=8, seed=None, prob_alteracion=0.4):
    """Elige n intervalos al azar, validando que:
      - La nota de partida está en [La3, Sol5]
      - La nota de respuesta también está en [La3, Sol5]
      - Ni partida ni respuesta llevan doble alteración
      - Ni partida ni respuesta son enharmónicos raros (Fb, Cb, B#, E#)
    prob_alteracion: probabilidad inicial de que la partida lleve alteración.
    """
    if seed is not None:
        random.seed(seed)
    if n <= len(INTERVALOS):
        muestras = random.sample(INTERVALOS, n)
    else:
        muestras = random.choices(INTERVALOS, k=n)

    resultado = []
    for lab, semitonos_int, grados_int in muestras:
        # Hasta 200 intentos por compás para encontrar una combinación válida
        for _ in range(200):
            direccion = random.choice(["asc", "desc"])
            step, octave = random.choice(NOTAS_PARTIDA_SO)
            alter = 0
            if random.random() < prob_alteracion:
                cand = random.choice([-1, 1])
                if (step, cand) not in RARAS:
                    alter = cand
            # Rango de la partida
            mp = midi_nota(step, octave, alter)
            if not (MIDI_MIN <= mp <= MIDI_MAX):
                continue
            # Calcular respuesta
            s_r, o_r, a_r, mr = calcular_respuesta(
                step, octave, alter, grados_int, semitonos_int, direccion
            )
            # Rango de la respuesta
            if not (MIDI_MIN <= mr <= MIDI_MAX):
                continue
            # No doble alteración
            if abs(a_r) > 1:
                continue
            # Respuesta enharmónica rara
            if (s_r, a_r) in RARAS:
                continue
            resultado.append((lab, direccion, (step, octave, alter)))
            break
        else:
            # Fallback muy defensivo (no debería ocurrir con catálogo amplio)
            resultado.append((lab, "asc", ("C", 4, 0)))
    return resultado


def elegir_intervalos_a(n=8, seed=None, prob_alteracion=0.4, prob_armonico=0.3):
    """Genera n "intervalos A": por cada compás se dan DOS notas (melódicas
    o armónicas) y el alumno escribe el nombre del intervalo.

    Devuelve lista de tuplas: (etiqueta, direccion, nota1, nota2, tipo)
      - etiqueta, direccion: para hoja de soluciones.
      - tipo: "mel" o "arm".
      - nota1, nota2: tuplas (step, octave, alter).

    Restricciones:
      - Ambas notas en [La3, Sol5].
      - Sin doble alteración en ninguna.
      - Sin enharmónicos raros (Fb, Cb, B#, E#).
      - El intervalo resultante debe estar en INTERVALOS.
      - Intervalos variados: se toma 1 muestra aleatoria del catálogo por
        compás (sin reposición si n <= len(INTERVALOS)).
      - prob_alteracion: probabilidad por NOTA (≈40% ⇒ ~6-7 de 16 notas
        alteradas en una ficha con 8 compases).
      - prob_armonico: probabilidad de compás armónico (30% por defecto).
    """
    if seed is not None:
        random.seed(seed)
    if n <= len(INTERVALOS):
        muestras = random.sample(INTERVALOS, n)
    else:
        muestras = random.choices(INTERVALOS, k=n)

    resultado = []
    for lab, semitonos_int, grados_int in muestras:
        # Regla: las 2as no pueden ser armónicas (visualmente engañoso
        # para los alumnos, notas muy pegadas). Fuerza melódico.
        es_segunda = grados_int == 1
        for _ in range(300):
            direccion = random.choice(["asc", "desc"])
            if es_segunda:
                tipo = "mel"
            else:
                tipo = "arm" if random.random() < prob_armonico else "mel"
            step, octave = random.choice(NOTAS_PARTIDA_SO)
            alter = 0
            if random.random() < prob_alteracion:
                cand = random.choice([-1, 1])
                if (step, cand) not in RARAS:
                    alter = cand
            m1 = midi_nota(step, octave, alter)
            if not (MIDI_MIN <= m1 <= MIDI_MAX):
                continue
            s_r, o_r, a_r, m2 = calcular_respuesta(
                step, octave, alter, grados_int, semitonos_int, direccion
            )
            if not (MIDI_MIN <= m2 <= MIDI_MAX):
                continue
            if abs(a_r) > 1:
                continue
            if (s_r, a_r) in RARAS:
                continue
            nota1 = (step, octave, alter)
            nota2 = (s_r, o_r, a_r)
            # Doble verificación: el intervalo entre ambas debe estar en catálogo
            chk = calcular_intervalo(nota1, nota2)
            if chk is None or chk[0] != lab:
                continue
            resultado.append((lab, direccion, nota1, nota2, tipo))
            break
        else:
            resultado.append((lab, "asc", ("C", 4, 0), ("E", 4, 0), "mel"))
    return resultado


# -----------------------------------------------------------------------------
# MusicXML: una "medida" por intervalo, con la nota de partida y debajo
# un texto (la etiqueta del intervalo) como direction-type words.
# -----------------------------------------------------------------------------
def musicxml_nota(step, octave, alter, es_chord=False):
    alter_xml = f"<alter>{alter}</alter>" if alter else ""
    accidental_xml = ""
    if alter == 1:
        accidental_xml = "<accidental>sharp</accidental>"
    elif alter == -1:
        accidental_xml = "<accidental>flat</accidental>"
    chord_xml = "<chord/>" if es_chord else ""
    return f"""
      <note>
        {chord_xml}
        <pitch>
          <step>{step}</step>
          {alter_xml}
          <octave>{octave}</octave>
        </pitch>
        <duration>16</duration>
        <type>whole</type>
        {accidental_xml}
      </note>"""


def musicxml_ejercicio_intervalos(lista):
    """Devuelve un MusicXML con n compases, cada uno con una nota entera.
    Las etiquetas ('4J asc', etc.) NO van en el MusicXML — las pintará
    reportlab debajo del render para tener control total del margen y tamaño.
    El último compás lleva doble barra final."""
    measures = []
    n = len(lista)
    for i, (_etiqueta, _direccion, (step, octave, alter)) in enumerate(lista, start=1):
        first_measure_attrs = ""
        if i == 1:
            first_measure_attrs = """
        <attributes>
          <divisions>4</divisions>
          <key><fifths>0</fifths></key>
          <time print-object="no"><beats>4</beats><beat-type>4</beat-type></time>
          <clef><sign>G</sign><line>2</line></clef>
        </attributes>"""
        barra = ""
        if i == n:
            barra = """
      <barline location="right"><bar-style>light-heavy</bar-style></barline>"""
        nota = musicxml_nota(step, octave, alter)
        measures.append(f"""
    <measure number="{i}">{first_measure_attrs}{nota}{barra}
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


def musicxml_ejercicio_intervalos_a(lista):
    """Devuelve un MusicXML para el ejercicio Intervalos A: 2 redondas por
    compás (melódicas o armónicas). Tiempo 8/4 oculto: los compases armónicos
    rellenan con silencio oculto para mantener ancho consistente."""
    measures = []
    n = len(lista)
    for i, (_et, _dir, nota1, nota2, tipo) in enumerate(lista, start=1):
        first_measure_attrs = ""
        if i == 1:
            first_measure_attrs = """
        <attributes>
          <divisions>4</divisions>
          <key><fifths>0</fifths></key>
          <time print-object="no"><beats>8</beats><beat-type>4</beat-type></time>
          <clef><sign>G</sign><line>2</line></clef>
        </attributes>"""
        barra = ""
        if i == n:
            barra = """
      <barline location="right"><bar-style>light-heavy</bar-style></barline>"""
        s1, o1, a1 = nota1
        s2, o2, a2 = nota2
        if tipo == "mel":
            contenido = musicxml_nota(s1, o1, a1) + musicxml_nota(s2, o2, a2)
        else:
            # Acorde de 2 redondas + silencio oculto para rellenar 8/4
            contenido = (
                musicxml_nota(s1, o1, a1)
                + musicxml_nota(s2, o2, a2, es_chord=True)
                + """
      <note print-object="no"><rest/><duration>16</duration><type>whole</type></note>"""
            )
        measures.append(f"""
    <measure number="{i}">{first_measure_attrs}{contenido}{barra}
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
# Render: MusicXML -> SVG (verovio) -> composición en PDF con reportlab
# -----------------------------------------------------------------------------
def render_svg(musicxml, svg_path):
    tk = verovio.toolkit()
    # Opciones de verovio
    tk.setOptions({
        "pageWidth": 2100,           # 210 mm * 10 (unidades en décimas de mm)
        "pageHeight": 2970,
        "pageMarginTop": 0,
        "pageMarginBottom": 0,
        "pageMarginLeft": 0,
        "pageMarginRight": 0,
        "scale": 45,                 # tamaño del grabado
        "adjustPageHeight": True,
        "adjustPageWidth": False,
        "barLineWidth": 0.3,
        "staffLineWidth": 0.15,
    })
    tk.loadData(musicxml)
    tk.redoLayout()
    svg = tk.renderToSVG(1)
    with open(svg_path, "w") as f:
        f.write(svg)


def svg_a_png_bytes(svg_text, ancho_pixeles):
    """Convierte SVG (string) a PNG bytes con el ancho deseado."""
    return cairosvg.svg2png(
        bytestring=svg_text.encode("utf-8"),
        output_width=ancho_pixeles,
    )


def _render_intervalos_png(lista_intervalos, modo, png_path,
                           ancho_util_mm=160):
    """Render de la partitura de Intervalos a PNG. Devuelve (centros_x, iw, ih).
    `centros_x` son fracciones 0..1 con el centro de cada compás.
    """
    if modo == "A":
        xml = musicxml_ejercicio_intervalos_a(lista_intervalos)
    else:
        xml = musicxml_ejercicio_intervalos(lista_intervalos)

    scale_verovio = 26 if modo == "A" else 35
    spacing_lineal = 0.18 if modo == "A" else 0.25
    spacing_no_lineal = 0.55 if modo == "A" else 0.6
    tk = verovio.toolkit()
    tk.setOptions({
        "pageWidth": 2100, "pageHeight": 2970,
        "pageMarginTop": 20, "pageMarginBottom": 20,
        "pageMarginLeft": 20, "pageMarginRight": 20,
        "scale": scale_verovio,
        "spacingStaff": 8, "spacingSystem": 8,
        "spacingNonLinear": spacing_no_lineal,
        "spacingLinear": spacing_lineal,
        "adjustPageHeight": True, "adjustPageWidth": True,
        "barLineWidth": 0.3, "staffLineWidth": 0.2,
        "header": "none", "footer": "none",
    })
    tk.loadData(xml)
    tk.redoLayout()
    svg = tk.renderToSVG(1)

    centros_x = extraer_centros_compases(svg, len(lista_intervalos))

    dpi = 300
    ancho_pix = int(ancho_util_mm / 25.4 * dpi)
    padding_inf_mm = 9 if modo == "A" else 6
    padding_inf_px = int(padding_inf_mm / 25.4 * dpi)
    png_bytes = svg_a_png_bytes(svg, ancho_pix)
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
    return centros_x, iw, ih


def dibujar_en_canvas(c, x_ini, y_top, lista_intervalos, modo,
                      num_enunciado, out_pdf_path,
                      ancho_util_mm=160, modo_solucion=False):
    """Dibuja el ejercicio de Intervalos en `c` a partir de `y_top`.
    Devuelve `y_bottom`.

    Solución (modo A):
      - Cada compás: escribe "4J asc" / "6m desc" / etc. en rojo.
    Solución (modo B):
      - Bajo cada etiqueta, añade la nota respuesta en rojo.
    """
    out_pdf_path = Path(out_pdf_path)
    png_path = out_pdf_path.with_name(out_pdf_path.stem + "_int.png")

    centros_x, iw, ih = _render_intervalos_png(
        lista_intervalos, modo, png_path, ancho_util_mm=ancho_util_mm,
    )

    ancho_pdf = ancho_util_mm * mm
    alto_pdf = ancho_pdf * ih / iw

    c.setFont("Helvetica-Bold", 12)
    # Título sin A/B — el alumno no necesita la distinción.
    c.drawString(x_ini, y_top, f"{num_enunciado}. Intervalos")

    y_img = y_top - 6 * mm - alto_pdf
    c.drawImage(ImageReader(str(png_path)), x_ini, y_img,
                width=ancho_pdf, height=alto_pdf)

    y_label = y_img + 2 * mm
    c.setFont("Helvetica-Oblique", 9)

    # Si el número de centros extraídos no coincide, reparto uniforme.
    if len(centros_x) != len(lista_intervalos):
        margen_clave_pct = 0.085
        x_start = x_ini + ancho_pdf * margen_clave_pct
        x_end = x_ini + ancho_pdf - 2 * mm
        ancho_por_compas = (x_end - x_start) / len(lista_intervalos)
        centros_x = [(x_start + ancho_por_compas * (i + 0.5) - x_ini) / ancho_pdf
                      for i in range(len(lista_intervalos))]

    for idx, frac in enumerate(centros_x):
        x_centro = x_ini + ancho_pdf * frac
        if modo == "A":
            # Línea siempre (también en solución).
            c.setFillColorRGB(0, 0, 0)
            c.drawCentredString(x_centro, y_label, "______")
            if modo_solucion:
                etiqueta, _direccion, _n1, _n2, _tipo = lista_intervalos[idx]
                # Solo el nombre del intervalo. No se indica asc/desc: es
                # visible en la partitura y no es lo que el alumno debe
                # nombrar.
                c.saveState()
                c.setFillColorRGB(1, 0, 0)
                c.drawCentredString(
                    x_centro, y_label + 0.6 * mm, etiqueta,
                )
                c.restoreState()
        else:
            etiqueta, _direccion, _ = lista_intervalos[idx]
            c.drawCentredString(x_centro, y_label, etiqueta)

    return y_label - 2 * mm


def componer_pdf(lista_intervalos, numero_ficha, out_pdf, modo="B",
                 num_enunciado=2, modo_solucion=False):
    """Genera un PDF de una sola hoja con el ejercicio de Intervalos."""
    out_pdf = Path(out_pdf)
    c = canvas.Canvas(str(out_pdf), pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width / 2, height - 25 * mm, f"Ficha {numero_ficha}")
    c.setFont("Helvetica", 12)
    c.drawString(25 * mm, height - 35 * mm, "Nombre  _________________________")
    c.drawRightString(width - 25 * mm, height - 35 * mm, "Nota  _______")

    dibujar_en_canvas(
        c, 25 * mm, height - 55 * mm, lista_intervalos, modo,
        num_enunciado, out_pdf_path=out_pdf, modo_solucion=modo_solucion,
    )

    c.showPage()
    c.save()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modo", choices=["A", "B"], default="B",
                    help="A: dos notas por compás; B: nota + etiqueta")
    ap.add_argument("--n", type=int, default=3, help="cuántas fichas generar")
    args = ap.parse_args()

    out_dir = Path("/sessions/elegant-busy-goldberg/mnt/outputs")
    out_dir.mkdir(parents=True, exist_ok=True)

    acc = {-1: "b", 0: "", 1: "#"}
    for i in range(1, args.n + 1):
        seed = 1000 + i if args.modo == "B" else 2000 + i
        pdf_path = out_dir / f"prototipo_ficha_{i}_ej2{args.modo.lower()}.pdf"
        if args.modo == "A":
            lista = elegir_intervalos_a(n=8, seed=seed)
            print(f"Generando {pdf_path.name} (modo A) con:")
            for lab, direc, n1, n2, tipo in lista:
                s1, o1, a1 = n1; s2, o2, a2 = n2
                print(f"   · {lab} {direc} [{tipo}]  "
                      f"{s1}{acc[a1]}{o1} → {s2}{acc[a2]}{o2}")
        else:
            lista = elegir_intervalos(n=8, seed=seed)
            print(f"Generando {pdf_path.name} (modo B) con:")
            for lab, direc, (s, o, a) in lista:
                print(f"   · {lab} {direc}  (partida: {s}{acc[a]}{o})")
        componer_pdf(lista, i, pdf_path, modo=args.modo)
    print("\nListo")


if __name__ == "__main__":
    main()
