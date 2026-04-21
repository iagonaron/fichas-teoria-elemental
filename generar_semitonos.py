"""
Ejercicio de Semitono (cromático / diatónico) — Fichas 3ºGe.

Estructura idéntica a la Ficha 4 original (ej. 7):

  | c1: 2 notas | c2: 2 notas || c3: 1 nota + etiqueta | c4: 1 nota + etiqueta |
        ^--- doble barra entre c2 y c3

  - Compases 1 y 2: se muestran dos redondas (melódicas). El alumno
    escribe 'C' (cromático) o 'D' (diatónico) debajo del compás.
  - Compases 3 y 4: se muestra UNA redonda + etiqueta
    's. cromático asc.' / 's. diatónico desc.' etc. El alumno
    escribe la segunda nota en el mismo compás.

Reglas:
  - Clave fija: Sol en 2ª.
  - Notas en rango La3..Sol5 (igual que el resto).
  - Sin dobles alteraciones, sin enharmónicos raros (Fb, Cb, B#, E#).
  - Por ficha: 1 cromático + 1 diatónico en cada mitad (el orden se
    mezcla). Direcciones sorteadas por compás.
  - Coherencia visual: K_VB_PER_MM = 90.06, scale verovio = 35.
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


# Tipos / direcciones
TIPOS = ("cromatico", "diatonico")
DIRECCIONES = ("asc", "desc")


def segunda_nota(step, octave, alter, direccion, tipo):
    """Dado el primer tono y los parámetros del semitono, devuelve la
    segunda nota (step, octave, alter) o None si inválida."""
    if tipo == "cromatico":
        delta = 1 if direccion == "asc" else -1
        new_alter = alter + delta
        if abs(new_alter) > 1:
            return None
        if (step, new_alter) in gi.RARAS:
            return None
        return step, octave, new_alter
    else:  # diatonico
        idx = gi.STEPS.index(step)
        delta_step = 1 if direccion == "asc" else -1
        raw = idx + delta_step
        octave_shift, new_idx = divmod(raw, 7)
        step2 = gi.STEPS[new_idx]
        octave2 = octave + octave_shift
        delta_midi = 1 if direccion == "asc" else -1
        target = gi.midi_nota(step, octave, alter) + delta_midi
        alter2 = target - gi.midi_nota(step2, octave2, 0)
        if abs(alter2) > 1:
            return None
        if (step2, alter2) in gi.RARAS:
            return None
        return step2, octave2, alter2


def _sortea_un_semitono(tipo, prob_alteracion=0.4):
    """Intenta producir una tupla (tipo, direccion, nota1, nota2) válida.
    Devuelve None si tras 300 intentos no lo consigue (muy raro).
    """
    for _ in range(300):
        direccion = random.choice(DIRECCIONES)
        step, octave = random.choice(gi.NOTAS_PARTIDA_SO)
        alter = 0
        if random.random() < prob_alteracion:
            cand = random.choice([-1, 1])
            if (step, cand) not in gi.RARAS:
                alter = cand
        if (step, alter) in gi.RARAS:
            continue
        m1 = gi.midi_nota(step, octave, alter)
        if not (gi.MIDI_MIN <= m1 <= gi.MIDI_MAX):
            continue
        segunda = segunda_nota(step, octave, alter, direccion, tipo)
        if segunda is None:
            continue
        s2, o2, a2 = segunda
        m2 = gi.midi_nota(s2, o2, a2)
        if not (gi.MIDI_MIN <= m2 <= gi.MIDI_MAX):
            continue
        return (tipo, direccion, (step, octave, alter), segunda)
    return None


def elegir_semitonos(seed=None, prob_alteracion=0.4):
    """Genera dos listas de 2 elementos cada una:

    - identificar (compases 1-2): una cromática + una diatónica,
      en orden aleatorio. El alumno escribirá 'C' o 'D'.
    - completar (compases 3-4): una cromática + una diatónica,
      en orden aleatorio. El alumno escribirá la 2ª nota.

    Cada elemento es tupla (tipo, direccion, nota1, nota2).
    """
    if seed is not None:
        random.seed(seed)
    identificar = []
    completar = []
    for target, tipo in [(identificar, "cromatico"), (identificar, "diatonico"),
                          (completar, "cromatico"), (completar, "diatonico")]:
        res = _sortea_un_semitono(tipo, prob_alteracion=prob_alteracion)
        if res is None:
            # Fallback ultra-defensivo
            if tipo == "cromatico":
                res = (tipo, "asc", ("C", 4, 0), ("C", 4, 1))
            else:
                res = (tipo, "asc", ("E", 4, 0), ("F", 4, 0))
        target.append(res)
    random.shuffle(identificar)
    random.shuffle(completar)
    return identificar, completar


# -----------------------------------------------------------------------------
# MusicXML
# -----------------------------------------------------------------------------
def _nota(step, octave, alter, es_oculta=False, force_natural=False,
           color=None):
    alter_xml = f"<alter>{alter}</alter>" if alter else ""
    accidental_xml = ""
    if alter == 1:
        accidental_xml = "<accidental>sharp</accidental>"
    elif alter == -1:
        accidental_xml = "<accidental>flat</accidental>"
    elif force_natural:
        # En un compás donde una nota PREVIA con el mismo step+octave ya
        # fue alterada, la alteración persiste hasta el final del compás.
        # Si la siguiente nota en la misma línea/espacio es natural, hay
        # que dibujar el becuadro explícito para que suene Natural.
        accidental_xml = "<accidental>natural</accidental>"
    pattr = ' print-object="no"' if es_oculta else ""
    color_attr = f' color="{color}"' if color else ""
    return f"""
      <note{pattr}{color_attr}>
        <pitch>
          <step>{step}</step>
          {alter_xml}
          <octave>{octave}</octave>
        </pitch>
        <duration>4</duration>
        <type>whole</type>
        {accidental_xml}
      </note>"""


def _necesita_becuadro(n1, n2):
    """True si n2 está en la misma línea/espacio que n1 (mismo step+octave)
    y n1 tenía alteración pero n2 es natural."""
    s1, o1, a1 = n1
    s2, o2, a2 = n2
    return s1 == s2 and o1 == o2 and a1 != 0 and a2 == 0


def musicxml_ejercicio_semitonos(identificar, completar, modo_solucion=False):
    """Construye un MusicXML con 4 compases:
      c1-c2: 2 redondas melódicas (visibles)
      c3-c4: 1 redonda visible + 1 redonda para la respuesta.
             - Alumno: la 2ª va OCULTA (reserva de ancho, en blanco).
             - Solución: la 2ª es VISIBLE y se pinta en ROJO (la respuesta
               al ejercicio es dibujar esa nota, no escribir su nombre).
    Barra intermedia (light-light) al final del c2; doble barra final en c4.
    """
    measures = []
    # c1
    _, _, n1, n2 = identificar[0]
    n2_force_nat = _necesita_becuadro(n1, n2)
    m1_contenido = _nota(*n1) + _nota(*n2, force_natural=n2_force_nat)
    m1 = f"""
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <key><fifths>0</fifths></key>
        <time print-object="no"><beats>8</beats><beat-type>4</beat-type></time>
        <clef><sign>G</sign><line>2</line></clef>
      </attributes>{m1_contenido}
    </measure>"""
    measures.append(m1)

    # c2 (mismo layout que c1, con doble barra fina al final)
    _, _, n1, n2 = identificar[1]
    n2_force_nat = _necesita_becuadro(n1, n2)
    m2_contenido = _nota(*n1) + _nota(*n2, force_natural=n2_force_nat)
    m2 = f"""
    <measure number="2">
      <print new-system="no"/>{m2_contenido}
      <barline location="right"><bar-style>light-light</bar-style></barline>
    </measure>"""
    measures.append(m2)

    # c3 (1 nota visible + 1 respuesta: oculta en alumno, roja en solución)
    _, _, n1_c3, n2_c3 = completar[0]
    if modo_solucion:
        nat_c3 = _necesita_becuadro(n1_c3, n2_c3)
        resp_c3 = _nota(*n2_c3, force_natural=nat_c3, color="#FF0000")
    else:
        resp_c3 = _nota("C", 4, 0, es_oculta=True)
    m3_contenido = _nota(*n1_c3) + resp_c3
    m3 = f"""
    <measure number="3">
      <print new-system="no"/>{m3_contenido}
    </measure>"""
    measures.append(m3)

    # c4 (idem + doble barra final)
    _, _, n1_c4, n2_c4 = completar[1]
    if modo_solucion:
        nat_c4 = _necesita_becuadro(n1_c4, n2_c4)
        resp_c4 = _nota(*n2_c4, force_natural=nat_c4, color="#FF0000")
    else:
        resp_c4 = _nota("C", 4, 0, es_oculta=True)
    m4_contenido = _nota(*n1_c4) + resp_c4
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
def _extraer_geometria(svg, n_compases):
    """Devuelve (vb_w, pm_x, barras_vb, x_fin_clef_vb). Sirve para situar
    centros de compases y notas después."""
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
    # Agrupamos barras muy cercanas (dobles fina+gruesa, fina+fina)
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


def _x_noteheads(svg):
    """Devuelve lista con la X (en coordenadas viewBox) de todos los
    noteheads VISIBLES del SVG, en orden de aparición."""
    xs = []
    for m in re.finditer(
        r'class="notehead"[^>]*>\s*<use[^>]*transform="translate\((\-?[\d\.]+),',
        svg,
    ):
        xs.append(float(m.group(1)))
    return xs


NOMBRE_ES = {
    "C": "Do", "D": "Re", "E": "Mi", "F": "Fa",
    "G": "Sol", "A": "La", "B": "Si",
}
ACC_ES = {-2: "bb", -1: "b", 0: "", 1: "#", 2: "x"}


def nombre_nota(step, alter):
    return f"{NOMBRE_ES[step]}{ACC_ES[alter]}"


def _render_semitonos_png(identificar, completar, png_path,
                          ancho_util_mm=160, padding_inf_mm=9,
                          modo_solucion=False):
    """Render del SVG → PNG del ejercicio de Semitonos.
    Devuelve (centros, x_notas_frac, iw, ih) donde centros es la lista
    de fracciones 0..1 con el centro de cada compás y x_notas_frac las
    fracciones 0..1 de cada notehead visible (en orden de aparición).
    """
    xml = musicxml_ejercicio_semitonos(
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

    vb_w, pm_x, barras, x_fin_clef = _extraer_geometria(svg, 4)
    centros = []
    for i in range(4):
        left = x_fin_clef if i == 0 else (
            barras[i - 1] if (i - 1) < len(barras) else vb_w
        )
        right = barras[i] if i < len(barras) else vb_w
        centros.append((pm_x + (left + right) / 2) / vb_w)

    x_notas_vb = _x_noteheads(svg)
    x_notas_frac = [(pm_x + x) / vb_w for x in x_notas_vb]

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
    return centros, x_notas_frac, iw, ih


def dibujar_en_canvas(c, x_ini, y_top, identificar, completar,
                      num_enunciado, out_pdf_path,
                      ancho_util_mm=160, modo_solucion=False):
    """Dibuja el ejercicio de Semitonos en `c` a partir de `y_top`.
    Devuelve `y_bottom`.

    Solución:
      - c1-c2 (identificar): escribe 'C' o 'D' en rojo.
      - c3-c4 (completar): escribe la 2ª nota (nombre) en rojo
        debajo, centrada en la mitad DERECHA del compás (donde
        está la redonda oculta reservada para la respuesta del
        alumno). La etiqueta 's. cromático asc.' sigue estando a
        la IZQUIERDA de ese texto (o omitimos la segunda línea y
        nos quedamos solo con la etiqueta + nombre).
    """
    out_pdf_path = Path(out_pdf_path)
    png_path = out_pdf_path.with_name(out_pdf_path.stem + "_sem.png")

    centros, x_notas_frac, iw, ih = _render_semitonos_png(
        identificar, completar, png_path,
        ancho_util_mm=ancho_util_mm,
        modo_solucion=modo_solucion,
    )

    ancho_pdf = ancho_util_mm * mm
    alto_pdf = ancho_pdf * ih / iw

    c.setFont("Helvetica-Bold", 12)
    c.drawString(x_ini, y_top, f"{num_enunciado}. Semitono")

    y_img = y_top - 6 * mm - alto_pdf
    c.drawImage(ImageReader(str(png_path)), x_ini, y_img,
                width=ancho_pdf, height=alto_pdf)

    c.setFont("Helvetica-Oblique", 10)
    y_label = y_img + 3 * mm

    # ----- Compases 1 y 2 (identificar) -----
    for i, frac in enumerate(centros[:2]):
        x = x_ini + ancho_pdf * frac
        if modo_solucion:
            tipo, _, _, _ = identificar[i]
            texto = (
                "Semitono cromático" if tipo == "cromatico"
                else "Semitono diatónico"
            )
            c.saveState()
            c.setFillColorRGB(1, 0, 0)
            c.drawCentredString(x, y_label, texto)
            c.restoreState()
        else:
            c.drawCentredString(x, y_label, "______")

    # ----- Compases 3 y 4 (completar) -----
    # Etiqueta 's. cromático asc.' / 's. diatónico desc.' etc. La
    # respuesta NO se escribe como texto: la segunda nota aparece ya
    # dibujada en rojo dentro del pentagrama (render de verovio con
    # color="#FF0000" cuando modo_solucion=True).
    for idx, item in enumerate(completar):
        tipo, direccion, _, _n2 = item
        x_centro = x_ini + ancho_pdf * centros[2 + idx]
        abrev_tipo = "cromático" if tipo == "cromatico" else "diatónico"
        abrev_dir = "asc." if direccion == "asc" else "desc."
        c.drawCentredString(
            x_centro, y_label, f"s. {abrev_tipo} {abrev_dir}"
        )

    return y_label - 3 * mm


def componer_pdf_semitonos(identificar, completar, numero_ficha, out_pdf,
                            num_enunciado=7, modo_solucion=False):
    """Genera un PDF con el ejercicio de Semitonos en una hoja."""
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
    ap.add_argument("--num-enunciado", type=int, default=7,
                    help="número del ejercicio en la ficha")
    args = ap.parse_args()

    out_dir = Path("/sessions/elegant-busy-goldberg/mnt/outputs")
    out_dir.mkdir(parents=True, exist_ok=True)

    acc = {-1: "b", 0: "", 1: "#"}
    for i in range(1, args.n + 1):
        seed = 6000 + i
        ident, comp = elegir_semitonos(seed=seed)
        pdf_path = out_dir / f"prototipo_ficha_{i}_ej7sem.pdf"
        print(f"Generando {pdf_path.name}")
        print("   Identificar (alumno escribe C/D):")
        for tipo, direc, n1, n2 in ident:
            s1, o1, a1 = n1; s2, o2, a2 = n2
            print(f"     · {tipo} {direc}: "
                  f"{s1}{acc[a1]}{o1} → {s2}{acc[a2]}{o2}")
        print("   Completar (alumno escribe 2ª nota):")
        for tipo, direc, n1, n2 in comp:
            s1, o1, a1 = n1; s2, o2, a2 = n2
            print(f"     · s. {tipo} {direc}: "
                  f"{s1}{acc[a1]}{o1} → {s2}{acc[a2]}{o2}")
        componer_pdf_semitonos(ident, comp, i, pdf_path,
                                num_enunciado=args.num_enunciado)

    print("\nListo")


if __name__ == "__main__":
    main()
