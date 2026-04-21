"""
Ejercicio QIHE (¿Qué Intervalo Hay Entre?) — Fichas de Teoría 3ºGe.

Nombre interno para selector de la app: "qihe".
Enunciado visible al alumno:
  "¿Cuál es el intervalo entre la {grado1} y la {grado2} de {tonalidad}?"

Layout (basado en Ficha 4):
  - 2 compases en una línea. Pentagrama SIN armadura (solo clave de
    Sol); el alumno deduce la armadura a partir de la tonalidad del
    enunciado — igual criterio que en Grados (ej 10).
  - c1 ≈ 3/4 del ancho útil, totalmente vacío (espacio de trabajo
    por si el alumno quiere dibujar las 2 notas para razonar).
  - c2 ≈ 1/4 del ancho útil. Debajo: "Respuesta: ______".
  - Doble barra gruesa (light-heavy) al final. Entre c1 y c2 va una
    barra sencilla (light-light funciona también pero el enunciado
    dice "Dos compases" sin especificar; usamos light-light para
    coherencia con Grados).

Ancho: con N_PLACEHOLDERS_C1 = 7 silencios ocultos y
N_PLACEHOLDERS_C2 = 2 silencios ocultos, el ancho natural sale:
  c1 ≈ 138 mm, c2 ≈ 50 mm → total 188 mm.
  factor = 160/188 ≈ 0.85.
  Resultado visual: c1 ≈ 117 mm (73%), c2 ≈ 43 mm (27%). Cerca
  del ideal 75/25 y sin estirar por encima de 1.0.
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
import generar_grados as gg


def _octava_grado(tonica_step, octava_tonica, grado_num):
    """Octava real (C-based) de la nota que ocupa `grado_num` en la escala
    que empieza en `tonica_step` / `octava_tonica`.

    Las octavas en MusicXML/MIDI cambian al pasar de B a C. Cuando una
    escala cruza esa frontera subiendo (p.ej. FaM: ...Bb4 C5 D5...) los
    grados V, VI y VII viven en la octava siguiente. Esta función lo
    calcula a partir del índice alfabético de la tónica y del grado.
    """
    idx_tonica = gi.STEPS.index(tonica_step)
    new_idx = (idx_tonica + grado_num - 1) % 7
    octava = octava_tonica + (1 if new_idx < idx_tonica else 0)
    return octava


# -----------------------------------------------------------------------------
# Sorteo: elegir 2 grados distintos en una tonalidad válida
# -----------------------------------------------------------------------------
def elegir_qihe(seed=None):
    """Devuelve dict con la info necesaria para componer el ejercicio:
       tonalidad_nombre, fifths, grado1_num, grado1_nombre,
       grado2_num, grado2_nombre, intervalo.

    - 2 grados DISTINTOS.
    - El intervalo es ASCENDENTE: desde grado1 hasta grado2 (si
      grado2 > grado1 en orden I-VII, directo; si grado2 < grado1,
      grado2 sube a la siguiente octava). Así el intervalo siempre
      está entre 2ª y 7ª, que es lo que se espera del alumno.
    - Evitamos dobles alteraciones y enharmónicos raros en cualquiera
      de las 2 notas (como en Grados).
    - Evitamos que el intervalo contenga doble alteración/raras al
      calcularlo (aunque cada nota sea válida, la combinación podría
      generar un intervalo no clasificable).
    """
    if seed is not None:
        random.seed(seed)

    pesos = [gtav.peso_fifths(f) for _, f in gtav.TONALIDADES]

    for _ in range(500):
        t = random.choices(gtav.TONALIDADES, weights=pesos)[0]
        tonal, fifths = t
        g1, g1_nombre = random.choice(gg.GRADOS)
        g2, g2_nombre = random.choice(gg.GRADOS)
        if g1 == g2:
            continue

        step1, alter1 = gg.nota_del_grado(tonal, fifths, g1)
        step2, alter2 = gg.nota_del_grado(tonal, fifths, g2)

        # Filtros de validez de cada nota.
        if abs(alter1) > 1 or abs(alter2) > 1:
            continue
        if (step1, alter1) in gi.RARAS:
            continue
        if (step2, alter2) in gi.RARAS:
            continue

        # Intervalo ascendente desde g1 a g2, dentro de 1 octava como máximo.
        # Tomamos la tónica en octava 4 y posicionamos los grados según su
        # octava NATURAL en la escala (cruce B→C). Si el grado 2 queda por
        # debajo del 1 (p.ej. Mediante→Tónica), subimos el 2 una octava
        # para que el intervalo sea siempre ascendente.
        tonica_step, _ = gg.TONICA[tonal]
        octave1 = _octava_grado(tonica_step, 4, g1)
        octave2 = _octava_grado(tonica_step, 4, g2)
        if g2 < g1:
            octave2 += 1
        intervalo = gi.calcular_intervalo(
            (step1, octave1, alter1),
            (step2, octave2, alter2),
        )
        if intervalo is None:
            continue
        etiqueta, direccion = intervalo
        # Doble comprobación: el cálculo debe resultar ascendente.
        if direccion != "asc":
            continue

        return {
            "tonalidad_nombre": tonal,
            "fifths": fifths,
            "grado1_num": g1,
            "grado1_nombre": g1_nombre,
            "grado2_num": g2,
            "grado2_nombre": g2_nombre,
            "step1": step1, "alter1": alter1,
            "step2": step2, "alter2": alter2,
            "intervalo": etiqueta,
        }

    raise RuntimeError("No pude sortear un QIHE válido en 500 intentos")


# -----------------------------------------------------------------------------
# MusicXML de UN compás (vacío, sin armadura — igual que Grados)
# -----------------------------------------------------------------------------
def musicxml_un_compas(n_placeholders, con_barra_final=False, final_heavy=True):
    """Pentagrama vacío con clave de Sol y SIN armadura (fifths=0).

    `n_placeholders` redondas ocultas controlan el ancho natural.
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
    silencios = silencio * n_placeholders
    beats_total = 4 * n_placeholders

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


def musicxml_c1_solucion(fifths, nota1, nota2, n_placeholders,
                          con_barra_final=True, final_heavy=False,
                          pos_n1=2, pos_n2=5):
    """c1 de la solución: armadura REAL + 2 redondas rojas visibles
    (las 2 notas del intervalo). El resto de slots se rellena con
    silencios ocultos para conservar el ancho natural.

    `nota1` y `nota2` son tuplas (step, octave, alter).
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
    n1 = gg._nota_visible_xml(*nota1, color="#FF0000")
    n2 = gg._nota_visible_xml(*nota2, color="#FF0000")
    elementos = []
    for i in range(1, n_placeholders + 1):
        if i == pos_n1:
            elementos.append(n1)
        elif i == pos_n2:
            elementos.append(n2)
        else:
            elementos.append(silencio)
    beats_total = 4 * n_placeholders

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


def musicxml_c2_solucion(fifths, nota1, nota2, n_placeholders,
                          con_barra_final=True, final_heavy=True,
                          pos_n1=1, pos_n2=2):
    """c2 de la solución: armadura REAL + las 2 notas rojas consecutivas
    (intervalo melódico).

    Por coherencia con el c1 original del alumno, se repite la armadura
    aquí también (el alumno nunca la ha visto, pero en la solución es
    útil dibujarla para reforzar).
    """
    return musicxml_c1_solucion(
        fifths, nota1, nota2, n_placeholders,
        con_barra_final=con_barra_final, final_heavy=final_heavy,
        pos_n1=pos_n1, pos_n2=pos_n2,
    )


def musicxml_c2_intervalo_melodico(nota1, nota2, n_placeholders,
                                     con_barra_final=True, final_heavy=True,
                                     pos_n1=1, pos_n2=2):
    """c2 SIN armadura (fifths=0) con las 2 redondas consecutivas.

    Regla del ejercicio: aquí NO hay armadura, así que cualquier
    alteración de las notas se dibuja explícitamente. Como pasamos
    `<alter>` correcto, verovio se encarga de pintar # o b si alter != 0.
    """
    return musicxml_c1_solucion(
        0, nota1, nota2, n_placeholders,
        con_barra_final=con_barra_final, final_heavy=final_heavy,
        pos_n1=pos_n1, pos_n2=pos_n2,
    )


# -----------------------------------------------------------------------------
# Render
# -----------------------------------------------------------------------------
K_VB_PER_MM = 90.06
N_PLACEHOLDERS_C1 = 7
N_PLACEHOLDERS_C2 = 2


def _render_compas_png(xml, png_path, ocultar_clave=False,
                        keysig_rojo=False, return_noteheads=False):
    """Renderiza un compás a PNG. Devuelve vb_w (o tupla extendida si
    return_noteheads=True: (vb_w, vb_h, noteheads)).

    Si `ocultar_clave=True`, quita el grupo `<g class="clef">...` del SVG
    (no su espacio reservado en el layout, que queda como pequeño hueco
    a la izquierda del compás). Se usa para el c2 de QIHE, donde la
    clave es redundante porque se repite idéntica a la del c1.
    Si `keysig_rojo=True`, postprocesa el SVG para pintar la armadura en rojo.
    """
    tk = verovio.toolkit()
    tk.setOptions({
        "pageWidth": 2100,
        "pageHeight": 2970,
        "pageMarginTop": 20, "pageMarginBottom": 20,
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

    noteheads = gg._extraer_noteheads(svg) if return_noteheads else []

    if ocultar_clave:
        svg = re.sub(
            r'<g[^>]*class="clef"[^>]*>.*?</g>',
            '',
            svg,
            flags=re.DOTALL,
        )

    if keysig_rojo:
        svg = gg._postprocess_keysig_rojo(svg)

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
def enunciado_qihe(item):
    """Texto largo tipo '¿Cuál es el intervalo entre la Dominante y la
    Sensible de Sim?'."""
    return (
        f"¿Cuál es el intervalo entre la "
        f"{item['grado1_nombre']} y la "
        f"{item['grado2_nombre']} de "
        f"{item['tonalidad_nombre']}?"
    )


def dibujar_en_canvas(c, x_ini, y_top, item, num_enunciado, out_pdf_path,
                      ancho_util_mm=160, modo_solucion=False):
    """Dibuja el ejercicio QIHE en `c` a partir de `y_top`.
    Devuelve `y_bottom`.
    """
    out_pdf_path = Path(out_pdf_path)

    png1 = out_pdf_path.with_name(out_pdf_path.stem + "_qihe_c01.png")
    png2 = out_pdf_path.with_name(out_pdf_path.stem + "_qihe_c02.png")

    if modo_solucion:
        # Calculamos octavas reales de las 2 notas (tónica en octava 4).
        tonica_step, _ = gg.TONICA[item["tonalidad_nombre"]]
        oct1 = _octava_grado(tonica_step, 4, item["grado1_num"])
        oct2 = _octava_grado(tonica_step, 4, item["grado2_num"])
        if item["grado2_num"] < item["grado1_num"]:
            oct2 += 1
        nota1 = (item["step1"], oct1, item["alter1"])
        nota2 = (item["step2"], oct2, item["alter2"])

        # c1: ESCALA completa (negras sin plica) con las 2 notas del
        # intervalo en rojo. Flechas sobre ellas las marcan abajo.
        xml1 = gg.musicxml_escala_solucion(
            item["fifths"], item["tonalidad_nombre"],
            tonica_octava=4,
            grado_objetivo=[item["grado1_num"], item["grado2_num"]],
            con_barra_final=True, final_heavy=False,
        )
        # c2: intervalo melódico SIN armadura. Las notas van con su
        # alteración explícita (alter ≠ 0 → verovio pinta # o b).
        xml2 = musicxml_c2_intervalo_melodico(
            nota1, nota2, N_PLACEHOLDERS_C2,
            con_barra_final=True, final_heavy=True,
            pos_n1=1, pos_n2=2,
        )
        vb1, vbh1, noteheads1 = _render_compas_png(
            xml1, png1, keysig_rojo=True, return_noteheads=True,
        )
        # c2 ya NO es rojo en la armadura (no tiene armadura). La clave
        # tampoco la pintamos en rojo: sólo las 2 notas, que el XML ya
        # marca en rojo.
        vb2, vbh2, noteheads2 = _render_compas_png(
            xml2, png2, ocultar_clave=True, keysig_rojo=False,
            return_noteheads=True,
        )
    else:
        xml1 = musicxml_un_compas(
            N_PLACEHOLDERS_C1, con_barra_final=True, final_heavy=False,
        )
        xml2 = musicxml_un_compas(
            N_PLACEHOLDERS_C2, con_barra_final=True, final_heavy=True,
        )
        vb1 = _render_compas_png(xml1, png1)
        vb2 = _render_compas_png(xml2, png2, ocultar_clave=True)
        vbh1 = vbh2 = None
        noteheads1 = noteheads2 = []

    img1 = ImageReader(str(png1)); iw1, ih1 = img1.getSize()
    img2 = ImageReader(str(png2)); iw2, ih2 = img2.getSize()

    a1_mm_ideal = vb1 / K_VB_PER_MM
    a2_mm_ideal = vb2 / K_VB_PER_MM
    total_ideal = a1_mm_ideal + a2_mm_ideal
    factor = min(1.0, ancho_util_mm / total_ideal)
    a1_mm = a1_mm_ideal * factor
    a2_mm = a2_mm_ideal * factor
    alto1_mm = a1_mm * ih1 / iw1
    alto2_mm = a2_mm * ih2 / iw2
    alto_max = max(alto1_mm, alto2_mm)

    c.setFont("Helvetica-Bold", 12)
    c.drawString(x_ini, y_top, f"{num_enunciado}. {enunciado_qihe(item)}")

    y_img = y_top - 6 * mm - alto_max * mm

    c.drawImage(img1, x_ini, y_img, width=a1_mm * mm, height=alto1_mm * mm)
    c.drawImage(
        img2, x_ini + a1_mm * mm, y_img,
        width=a2_mm * mm, height=alto2_mm * mm,
    )

    # Señalización en c1: FLECHA roja apuntando a cada una de las 2 notas
    # del intervalo (grado1 y grado2 dentro de la escala I..VII).
    if modo_solucion and noteheads1 and vbh1:
        indices = [item["grado1_num"] - 1, item["grado2_num"] - 1]
        for idx in indices:
            if idx >= len(noteheads1):
                continue
            xv, yv = noteheads1[idx]
            frac_x = xv / vb1
            frac_y = yv / vbh1
            x_cx = x_ini + frac_x * a1_mm * mm
            y_cy = y_img + alto1_mm * mm - frac_y * alto1_mm * mm
            y_base = y_cy + 7 * mm
            y_punta = y_cy + 2.2 * mm
            ancho_cabeza = 1.2 * mm
            alto_cabeza = 1.6 * mm
            c.saveState()
            c.setStrokeColorRGB(1, 0, 0)
            c.setFillColorRGB(1, 0, 0)
            c.setLineWidth(0.6)
            c.line(x_cx, y_base, x_cx, y_punta)
            p = c.beginPath()
            p.moveTo(x_cx, y_punta - alto_cabeza)
            p.lineTo(x_cx - ancho_cabeza, y_punta)
            p.lineTo(x_cx + ancho_cabeza, y_punta)
            p.close()
            c.drawPath(p, stroke=1, fill=1)
            c.restoreState()

    c.setFont("Helvetica-Oblique", 10)
    y_label = y_img - 4 * mm
    margen_lateral_mm = 4
    x_der = x_ini + (a1_mm + a2_mm) * mm - margen_lateral_mm * mm

    if modo_solucion:
        # La respuesta al enunciado (nombre del intervalo) sigue siendo
        # texto: el alumno escribe "5ª Justa", no una nota. Mantenemos
        # "Respuesta:" en negro + el intervalo en rojo.
        resp_text = item["intervalo"]
        etiq = "Respuesta: "
        w_resp = c.stringWidth(resp_text, "Helvetica-Oblique", 10)
        w_etiq = c.stringWidth(etiq, "Helvetica-Oblique", 10)
        x_resp_start = x_der - w_resp
        x_etiq_start = x_resp_start - w_etiq
        c.drawString(x_etiq_start, y_label, etiq)
        c.saveState()
        c.setFillColorRGB(1, 0, 0)
        c.drawString(x_resp_start, y_label, resp_text)
        c.restoreState()
    else:
        c.drawRightString(x_der, y_label, "Respuesta: ______")

    return y_label - 2 * mm


def componer_pdf_qihe(item, numero_ficha, out_pdf, num_enunciado=11,
                       modo_solucion=False):
    """2 compases: c1 grande (3/4), c2 pequeño (1/4) con 'Respuesta:'."""
    out_pdf = Path(out_pdf)
    c = canvas.Canvas(str(out_pdf), pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width / 2, height - 25 * mm, f"Ficha {numero_ficha}")
    c.setFont("Helvetica", 12)
    c.drawString(25 * mm, height - 35 * mm, "Nombre  _________________________")
    c.drawRightString(width - 25 * mm, height - 35 * mm, "Nota  _______")

    dibujar_en_canvas(
        c, 25 * mm, height - 55 * mm, item, num_enunciado,
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
    ap.add_argument("--num-enunciado", type=int, default=11,
                    help="número del ejercicio en la ficha")
    ap.add_argument("--solucion", action="store_true",
                    help="dibujar armadura+notas en rojo")
    args = ap.parse_args()

    out_dir = Path("/sessions/elegant-busy-goldberg/mnt/outputs")
    out_dir.mkdir(parents=True, exist_ok=True)

    for i in range(1, args.n + 1):
        seed = 9000 + i
        item = elegir_qihe(seed=seed)
        sufijo = "_sol" if args.solucion else ""
        pdf_path = out_dir / f"prototipo_ficha_{i}_ej11qihe{sufijo}.pdf"
        print(f"Generando {pdf_path.name}")
        print(f"   · {enunciado_qihe(item)} → {item['intervalo']}")
        componer_pdf_qihe(
            item, i, pdf_path, num_enunciado=args.num_enunciado,
            modo_solucion=args.solucion,
        )

    print("\nListo")


if __name__ == "__main__":
    main()
