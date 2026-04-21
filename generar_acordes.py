"""
Ejercicio de Acordes (tríadas) — Fichas 3ºGe.

Mismo layout que Semitonos:

  | c1: acorde | c2: acorde || c3: fund + etiqueta | c4: fund + etiqueta |
        ^--- doble barra entre c2 y c3

  - Compases 1 y 2 (identificar): se muestra un acorde (3 notas
    simultáneas: fundamental, 3ª y 5ª) y el alumno escribe el tipo
    debajo: PM, Pm, Aum o Dis.
  - Compases 3 y 4 (completar): se muestra UNA redonda (la fundamental)
    + etiqueta "Do PM", "Fa# Dis", etc. El alumno dibuja la 3ª y la 5ª.

Reglas:
  - Clave fija: Sol en 2ª.
  - Notas en rango La3..Sol5 (MIDI_MIN..MIDI_MAX).
  - Enharmónicos raros (Fb, Cb, B#, E#) siempre prohibidos.
  - Dobles alteraciones: 90% de los acordes sin dobles, 10% con
    doble (calibrable con `prob_doble`).
  - Coherencia visual: scale verovio = 35 (mismo K que el resto).

Tipos de tríada:
  - PM  (Perfecto Mayor):    3M + 5J  → semitonos +4, +7
  - Pm  (Perfecto menor):    3m + 5J  → semitonos +3, +7
  - Aum (Aumentado):         3M + 5A  → semitonos +4, +8
  - Dis (Disminuido):        3m + 5D  → semitonos +3, +6
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
# Catálogo de acordes
# -----------------------------------------------------------------------------
# Cada tríada se define por los intervalos de 3ª y 5ª sobre la fundamental.
# i3_gr = nº grados diatónicos de la 3ª (siempre 2); idem i5_gr (siempre 4).
# i3_st = semitonos de la 3ª; i5_st = semitonos de la 5ª.
TIPOS_ACORDE = {
    "PM":  {"label": "PM",  "i3_gr": 2, "i3_st": 4, "i5_gr": 4, "i5_st": 7},
    "Pm":  {"label": "Pm",  "i3_gr": 2, "i3_st": 3, "i5_gr": 4, "i5_st": 7},
    "Aum": {"label": "Aum", "i3_gr": 2, "i3_st": 4, "i5_gr": 4, "i5_st": 8},
    "Dis": {"label": "Dis", "i3_gr": 2, "i3_st": 3, "i5_gr": 4, "i5_st": 6},
}

# Nombres solfeo español (para la etiqueta de c3-c4).
NOMBRE_ES = {
    "C": "Do", "D": "Re", "E": "Mi", "F": "Fa",
    "G": "Sol", "A": "La", "B": "Si",
}
ACC_ES = {-2: "bb", -1: "b", 0: "", 1: "#", 2: "x"}


def nombre_nota(step, alter):
    return f"{NOMBRE_ES[step]}{ACC_ES[alter]}"


# -----------------------------------------------------------------------------
# Cálculo de las 3 notas del acorde
# -----------------------------------------------------------------------------
def notas_acorde(step, octave, alter, tipo):
    """Devuelve lista [(step, oct, alter)] × 3 (fund, 3ª, 5ª) o None si
    alguna nota cae en un enharmónico raro (Fb, Cb, B#, E#) o en una
    alteración inmanejable (|alter| > 2).
    """
    t = TIPOS_ACORDE[tipo]
    notas = [(step, octave, alter)]
    m_fund = gi.midi_nota(step, octave, alter)
    for gr, st in [(t["i3_gr"], t["i3_st"]), (t["i5_gr"], t["i5_st"])]:
        idx = gi.STEPS.index(step)
        raw = idx + gr
        octave_shift, new_idx = divmod(raw, 7)
        step_n = gi.STEPS[new_idx]
        octave_n = octave + octave_shift
        target = m_fund + st
        alter_n = target - gi.midi_nota(step_n, octave_n, 0)
        if abs(alter_n) > 2:
            return None
        if (step_n, alter_n) in gi.RARAS:
            return None
        notas.append((step_n, octave_n, alter_n))
    return notas


def hay_doble_alteracion(notas):
    return any(abs(a) > 1 for _, _, a in notas)


# -----------------------------------------------------------------------------
# Sorteo
# -----------------------------------------------------------------------------
def _sortea_un_acorde(prob_alteracion_fund=0.4, prob_doble=0.10):
    """Devuelve tupla (tipo, notas) o None si no encuentra candidato válido.

    El 10% (prob_doble) de los acordes saldrán con alguna doble alteración
    (se fuerza que hay_doble == permitir_doble_esta_vez). El resto limpio.
    """
    permitir_doble = random.random() < prob_doble
    for _ in range(1200):
        tipo = random.choice(list(TIPOS_ACORDE.keys()))
        step, octave = random.choice(gi.NOTAS_PARTIDA_SO)
        alter = 0
        if random.random() < prob_alteracion_fund:
            alter = random.choice([-1, 1])
        if (step, alter) in gi.RARAS:
            continue
        m1 = gi.midi_nota(step, octave, alter)
        # La 5ª puede ser hasta +8 semitonos: la fund no debe pasar de
        # MIDI_MAX - 8. Por abajo, no debe bajar de MIDI_MIN.
        if not (gi.MIDI_MIN <= m1 <= gi.MIDI_MAX - 8):
            continue
        notas = notas_acorde(step, octave, alter, tipo)
        if notas is None:
            continue
        # Filtro 90/10
        if hay_doble_alteracion(notas) != permitir_doble:
            continue
        # Rango del resto de notas
        if any(not (gi.MIDI_MIN <= gi.midi_nota(s, o, a) <= gi.MIDI_MAX)
               for s, o, a in notas):
            continue
        return (tipo, notas)

    # Fallback defensivo: sin el filtro 90/10, solo validar rango y raras.
    for _ in range(500):
        tipo = random.choice(list(TIPOS_ACORDE.keys()))
        step, octave = random.choice(gi.NOTAS_PARTIDA_SO)
        alter = 0
        if (step, alter) in gi.RARAS:
            continue
        m1 = gi.midi_nota(step, octave, alter)
        if not (gi.MIDI_MIN <= m1 <= gi.MIDI_MAX - 8):
            continue
        notas = notas_acorde(step, octave, alter, tipo)
        if notas is None:
            continue
        if any(not (gi.MIDI_MIN <= gi.midi_nota(s, o, a) <= gi.MIDI_MAX)
               for s, o, a in notas):
            continue
        return (tipo, notas)
    return None


def elegir_acordes(seed=None, prob_doble=0.10):
    """Genera identificar (2 acordes) + completar (2 acordes)."""
    if seed is not None:
        random.seed(seed)
    identificar = [_sortea_un_acorde(prob_doble=prob_doble) for _ in range(2)]
    completar = [_sortea_un_acorde(prob_doble=prob_doble) for _ in range(2)]
    random.shuffle(identificar)
    random.shuffle(completar)
    return identificar, completar


# -----------------------------------------------------------------------------
# MusicXML
# -----------------------------------------------------------------------------
def _accidental_xml(alter):
    return {
        2:  "<accidental>double-sharp</accidental>",
        1:  "<accidental>sharp</accidental>",
        0:  "",
        -1: "<accidental>flat</accidental>",
        -2: "<accidental>flat-flat</accidental>",
    }.get(alter, "")


def _nota(step, octave, alter, es_oculta=False, es_chord=False,
          duracion=4, type_xml="whole", color=None):
    alter_xml = f"<alter>{alter}</alter>" if alter else ""
    accidental_xml = _accidental_xml(alter)
    pattr = ' print-object="no"' if es_oculta else ""
    chord_xml = "<chord/>" if es_chord else ""
    color_attr = f' color="{color}"' if color else ""
    return f"""
      <note{pattr}{color_attr}>
        {chord_xml}
        <pitch>
          <step>{step}</step>
          {alter_xml}
          <octave>{octave}</octave>
        </pitch>
        <duration>{duracion}</duration>
        <type>{type_xml}</type>
        {accidental_xml}
      </note>"""


def _acorde_xml(notas, color_extras=None):
    """Acorde de 3 notas. Si `color_extras` está seteado (p.ej. "#FF0000"),
    la 3ª y la 5ª se pintan en ese color (la fundamental permanece en
    negro, como estaba dada al alumno)."""
    n1, n2, n3 = notas
    return (_nota(*n1)
            + _nota(*n2, es_chord=True, color=color_extras)
            + _nota(*n3, es_chord=True, color=color_extras))


def musicxml_ejercicio_acordes(identificar, completar, modo_solucion=False):
    """4 compases:
      c1-c2: acorde completo (3 notas simultáneas) centrado en el compás.
      c3-c4: fundamental sola centrada en el compás.
    Cada compás lleva un placeholder OCULTO de duración half a izq y
    otro a derecha del contenido visible → contenido físicamente
    centrado pero sin que los placeholders "engorden" demasiado el
    compás (si fueran `whole` el compás saldría ~50% más ancho y las
    cabezas se reducirían al comprimir a 160 mm).
    Tiempo 8/4 oculto (2 + 4 + 2 = 8 tiempos).
    Doble barra fina al final de c2, doble barra gruesa al final de c4.
    """
    measures = []

    def _pad():
        # Quarter hidden placeholder (duración 1 → ocupa ~1/6 del 6/4).
        # Con `whole` el compás se inflaba ~50% y las cabezas salían más
        # pequeñas que en otros ejercicios; con `quarter` el ancho natural
        # se acerca al de Semitonos (≈166 mm).
        return _nota("C", 4, 0, es_oculta=True,
                     duracion=1, type_xml="quarter")

    # c1
    _, notas1 = identificar[0]
    m1_contenido = _pad() + _acorde_xml(notas1) + _pad()
    m1 = f"""
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <key><fifths>0</fifths></key>
        <time print-object="no"><beats>6</beats><beat-type>4</beat-type></time>
        <clef><sign>G</sign><line>2</line></clef>
      </attributes>{m1_contenido}
    </measure>"""
    measures.append(m1)

    # c2
    _, notas2 = identificar[1]
    m2_contenido = _pad() + _acorde_xml(notas2) + _pad()
    m2 = f"""
    <measure number="2">
      <print new-system="no"/>{m2_contenido}
      <barline location="right"><bar-style>light-light</bar-style></barline>
    </measure>"""
    measures.append(m2)

    # c3-c4 (completar):
    #  - Alumno: solo se dibuja la fundamental. El alumno añade 3ª y 5ª.
    #  - Solución: acorde COMPLETO con la 3ª y la 5ª en rojo (la
    #    fundamental sigue en negro, es el dato que ya tenía el alumno).
    _, notas3 = completar[0]
    if modo_solucion:
        m3_cont_notes = _acorde_xml(notas3, color_extras="#FF0000")
    else:
        m3_cont_notes = _nota(*notas3[0])
    m3_contenido = _pad() + m3_cont_notes + _pad()
    m3 = f"""
    <measure number="3">
      <print new-system="no"/>{m3_contenido}
    </measure>"""
    measures.append(m3)

    _, notas4 = completar[1]
    if modo_solucion:
        m4_cont_notes = _acorde_xml(notas4, color_extras="#FF0000")
    else:
        m4_cont_notes = _nota(*notas4[0])
    m4_contenido = _pad() + m4_cont_notes + _pad()
    m4 = f"""
    <measure number="4">
      <print new-system="no"/>{m4_contenido}
      <barline location="right"><bar-style>light-heavy</bar-style></barline>
    </measure>"""
    measures.append(m4)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name></part-name></score-part>
  </part-list>
  <part id="P1">{"".join(measures)}
  </part>
</score-partwise>"""


# -----------------------------------------------------------------------------
# Render + PDF
# -----------------------------------------------------------------------------
def _extraer_geometria(svg):
    vb_match = re.search(
        r'class="definition-scale"[^>]*viewBox="([\d\s\.\-]+)"', svg
    )
    vb_w = float(vb_match.group(1).split()[2]) if vb_match else 10000.0
    pm_match = re.search(
        r'class="page-margin"[^>]*transform="translate\((\-?[\d\.]+),\s*(\-?[\d\.]+)\)"',
        svg,
    )
    pm_x = float(pm_match.group(1)) if pm_match else 0.0
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
    clef_m = re.search(
        r'class="clef">\s*<use [^>]*transform="translate\((\-?[\d\.]+),',
        svg,
    )
    x_clef = float(clef_m.group(1)) if clef_m else 0.0
    ANCHO_CLEF = 500
    x_fin_clef = x_clef + ANCHO_CLEF
    return vb_w, pm_x, agrup, x_fin_clef


def _render_acordes_png(identificar, completar, png_path,
                        ancho_util_mm=160, padding_inf_mm=6,
                        modo_solucion=False):
    """Render del SVG a PNG y extracción de centros de compás."""
    xml = musicxml_ejercicio_acordes(
        identificar, completar, modo_solucion=modo_solucion,
    )

    tk = verovio.toolkit()
    tk.setOptions({
        "pageWidth": 2100, "pageHeight": 2970,
        "pageMarginTop": 20, "pageMarginBottom": 20,
        "pageMarginLeft": 20, "pageMarginRight": 20,
        "scale": 35,
        "spacingStaff": 8, "spacingSystem": 8,
        "spacingNonLinear": 0.6, "spacingLinear": 0.25,
        "adjustPageHeight": True, "adjustPageWidth": True,
        "barLineWidth": 0.3, "staffLineWidth": 0.2,
        "header": "none", "footer": "none", "breaks": "none",
    })
    tk.loadData(xml)
    tk.redoLayout()
    svg = tk.renderToSVG(1)

    vb_w, pm_x, barras, x_fin_clef = _extraer_geometria(svg)
    centros = []
    for i in range(4):
        left = x_fin_clef if i == 0 else (
            barras[i - 1] if (i - 1) < len(barras) else vb_w
        )
        right = barras[i] if i < len(barras) else vb_w
        centros.append((pm_x + (left + right) / 2) / vb_w)

    dpi = 300
    ancho_pix = int(ancho_util_mm / 25.4 * dpi)
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
    return centros, iw, ih


def dibujar_en_canvas(c, x_ini, y_top, identificar, completar,
                      num_enunciado, out_pdf_path,
                      ancho_util_mm=160, modo_solucion=False):
    """Dibuja el ejercicio de Acordes en `c` a partir de `y_top`.
    Devuelve `y_bottom`.

    Solución:
      - c1-c2: escribe PM/Pm/Aum/Dis en rojo.
      - c3-c4: debajo de "Do PM" añade (en rojo) los 3 nombres del
        acorde completo p.ej. "Do + Mi + Sol".
    """
    out_pdf_path = Path(out_pdf_path)
    png_path = out_pdf_path.with_name(out_pdf_path.stem + "_acor.png")

    centros, iw, ih = _render_acordes_png(
        identificar, completar, png_path, ancho_util_mm=ancho_util_mm,
        modo_solucion=modo_solucion,
    )

    ancho_pdf = ancho_util_mm * mm
    alto_pdf = ancho_pdf * ih / iw

    c.setFont("Helvetica-Bold", 12)
    c.drawString(x_ini, y_top, f"{num_enunciado}. Acordes")

    y_img = y_top - 6 * mm - alto_pdf
    c.drawImage(ImageReader(str(png_path)), x_ini, y_img,
                width=ancho_pdf, height=alto_pdf)

    c.setFont("Helvetica-Oblique", 10)
    y_label = y_img + 2 * mm

    # Compases 1 y 2 (identificar)
    for i in range(2):
        x = x_ini + ancho_pdf * centros[i]
        if modo_solucion:
            tipo, notas = identificar[i]
            # Nombre completo con fundamental: "DoAum", "SolPm", etc.
            s, _o, a = notas[0]
            label_fund = nombre_nota(s, a)
            label_tipo = TIPOS_ACORDE[tipo]["label"]
            c.saveState()
            c.setFillColorRGB(1, 0, 0)
            c.drawCentredString(x, y_label, f"{label_fund}{label_tipo}")
            c.restoreState()
        else:
            c.drawCentredString(x, y_label, "______")

    # Compases 3 y 4 (completar). La etiqueta "DoPM", "Fa#Dis" etc. queda
    # debajo del compás y actúa como enunciado (se da la fundamental +
    # tipo de acorde). En solución, la 3ª y la 5ª ya están DIBUJADAS en
    # rojo sobre el pentagrama; no hace falta más texto.
    for idx, item in enumerate(completar):
        tipo, notas = item
        s, _o, a = notas[0]
        label_nota = nombre_nota(s, a)
        label_tipo = TIPOS_ACORDE[tipo]["label"]
        x_centro = x_ini + ancho_pdf * centros[2 + idx]
        c.drawCentredString(x_centro, y_label, f"{label_nota}{label_tipo}")

    return y_label - 3 * mm


def componer_pdf_acordes(identificar, completar, numero_ficha, out_pdf,
                          num_enunciado=8, modo_solucion=False):
    """Genera un PDF con el ejercicio de Acordes en una hoja."""
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
        identificar, completar, num_enunciado,
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
    ap.add_argument("--num-enunciado", type=int, default=8,
                    help="número del ejercicio en la ficha")
    ap.add_argument("--prob-doble", type=float, default=0.10,
                    help="probabilidad de que un acorde lleve doble alt.")
    args = ap.parse_args()

    out_dir = Path("/sessions/elegant-busy-goldberg/mnt/outputs")
    out_dir.mkdir(parents=True, exist_ok=True)

    for i in range(1, args.n + 1):
        seed = 7000 + i
        ident, comp = elegir_acordes(seed=seed, prob_doble=args.prob_doble)
        pdf_path = out_dir / f"prototipo_ficha_{i}_ej8acor.pdf"
        print(f"Generando {pdf_path.name}")
        print("   Identificar (alumno escribe PM/Pm/Aum/Dis):")
        for tipo, notas in ident:
            nombres = " + ".join(nombre_nota(s, a) + str(o)
                                 for s, o, a in notas)
            print(f"     · {tipo}: {nombres}")
        print("   Completar (alumno dibuja 3ª y 5ª sobre la fundamental):")
        for tipo, notas in comp:
            s, o, a = notas[0]
            print(f"     · {nombre_nota(s, a)}{o} {tipo} → "
                  + " + ".join(nombre_nota(x, z) + str(y)
                               for x, y, z in notas))
        componer_pdf_acordes(ident, comp, i, pdf_path,
                              num_enunciado=args.num_enunciado)

    print("\nListo")


if __name__ == "__main__":
    main()
