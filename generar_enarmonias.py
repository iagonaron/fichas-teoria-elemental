"""
Ejercicio Enarmonías — Fichas de Teoría 3ºGe.

Estructura muy sencilla (palabras de Iago: "es muy fácil"):
  - 4 compases en una línea, clave de Sol fija, SIN armadura.
  - Cada compás: 1 redonda visible al principio. El alumno escribe
    debajo el nombre enarmónico equivalente.
  - Doble barra gruesa al final; entre compases barras sencillas.

Catálogo de pares enarmónicos que usamos (bidireccional — podemos
presentar cualquiera de los dos lados y esperar el otro):

  - Do# ↔ Reb · Re# ↔ Mib · Fa# ↔ Solb · Sol# ↔ Lab · La# ↔ Sib
    (pares "seguros": ambos lados son alteraciones simples que sí
     existen en armaduras reales).
  - Fa ↔ Mi# · Si ↔ Dob · Mi ↔ Fab · Do ↔ Si#
    (pares "raros": uno de los dos lados es un enharmónico
     considerado "raro" — Fb, Cb, B#, E# — que en el resto de
     ejercicios evitamos. Aquí sí entran porque son el sentido
     mismo del ejercicio.)

Por defecto mezclamos 2 pares seguros + 2 raros para que siempre
haya variedad y el alumno vea también los raros.
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
# Catálogo
# -----------------------------------------------------------------------------
# Cada par = (nota1, nota2, octava_delta) con (step, alter).
# octava_delta: cuando la nota2 está en OCTAVA distinta a la nota1
# (p.ej. Si natural ↔ Dob de la octava SIGUIENTE). 0 = misma octava.
PARES_SEGUROS = [
    (("C", 1),  ("D", -1), 0),
    (("D", 1),  ("E", -1), 0),
    (("F", 1),  ("G", -1), 0),
    (("G", 1),  ("A", -1), 0),
    (("A", 1),  ("B", -1), 0),
]
PARES_RAROS = [
    (("F", 0),  ("E", 1),  0),    # Fa ↔ Mi#
    (("E", 0),  ("F", -1), 0),    # Mi ↔ Fab
    (("B", 0),  ("C", -1), +1),   # Si ↔ Dob (la Dob va a la octava siguiente)
    (("C", 0),  ("B", 1),  -1),   # Do ↔ Si# (la Si# va a la octava anterior)
]

# Catálogo COMPLETO de enarmonías por nota dada.
# Formato: (step, alter) → lista de (step_enh, alter_enh, delta_oct).
# Regla (kit salvavidas de Iago): toda nota tiene 2 enarmonías EXCEPTO
# Sol# y Lab, que solo tienen una entre sí.
TODAS_ENARMONIAS = {
    # --- Naturales ---
    ("C", 0):  [("B", 1, -1),  ("D", -2, 0)],     # Do: Si#↓, Rebb
    ("D", 0):  [("C", 2, 0),   ("E", -2, 0)],     # Re: Dox,  Mibb
    ("E", 0):  [("F", -1, 0),  ("D", 2, 0)],      # Mi: Fab,  Rex
    ("F", 0):  [("E", 1, 0),   ("G", -2, 0)],     # Fa: Mi#,  Solbb
    ("G", 0):  [("F", 2, 0),   ("A", -2, 0)],     # Sol:Fax,  Labb
    ("A", 0):  [("G", 2, 0),   ("B", -2, 0)],     # La: Solx, Sibb
    ("B", 0):  [("C", -1, +1), ("A", 2, 0)],      # Si: Dob↑, Lax

    # --- Sostenidos ---
    ("C", 1):  [("D", -1, 0),  ("B", 2, -1)],     # Do#: Reb,  Six↓
    ("D", 1):  [("E", -1, 0),  ("F", -2, 0)],     # Re#: Mib,  Fabb
    ("F", 1):  [("G", -1, 0),  ("E", 2, 0)],      # Fa#: Solb, Mix
    ("G", 1):  [("A", -1, 0)],                    # Sol#: SOLO Lab
    ("A", 1):  [("B", -1, 0),  ("C", -2, +1)],    # La#: Sib,  Dobb↑

    # --- Bemoles ---
    ("D", -1): [("C", 1, 0),   ("E", -2, 0)],     # Reb: Do#, Mibb
    ("E", -1): [("D", 1, 0),   ("F", -2, 0)],     # Mib: Re#, Fabb
    ("G", -1): [("F", 1, 0),   ("A", -2, 0)],     # Solb: Fa#, Labb
    ("A", -1): [("G", 1, 0)],                     # Lab: SOLO Sol#
    ("B", -1): [("A", 1, 0),   ("C", -2, +1)],    # Sib: La#, Dobb↑

    # --- Enarmónicos raros cuando son el lado "dado" ---
    ("E", 1):  [("F", 0, 0),   ("G", -2, 0)],     # Mi# = Fa, Solbb
    ("B", 1):  [("C", 0, +1),  ("D", -2, +1)],    # Si# = Do↑, Rebb↑
    ("F", -1): [("E", 0, 0),   ("D", 2, 0)],      # Fab = Mi, Rex
    ("C", -1): [("B", 0, -1),  ("A", 2, -1)],     # Dob = Si↓, Lax↓
}

NOMBRE_ES = {"C": "Do", "D": "Re", "E": "Mi", "F": "Fa",
             "G": "Sol", "A": "La", "B": "Si"}
ACC_ES = {-2: "bb", -1: "b", 0: "", 1: "#", 2: "x"}

# Cantidad de enarmonías posibles por compás (placeholders). 2 en todos
# los compases para mantener el ancho coherente — si una nota solo tiene
# 1 enarmonía (Sol#/Lab), el segundo hueco queda oculto.
N_ENH_PLACEHOLDERS = 2


def nombre_nota(step, alter):
    return f"{NOMBRE_ES[step]}{ACC_ES[alter]}"


# -----------------------------------------------------------------------------
# Sorteo
# -----------------------------------------------------------------------------
def elegir_enarmonias(seed=None, n_compases=4, proporcion_raros=0.5):
    """Devuelve lista de `n_compases` dicts:
       { step, octave, alter, respuestas }
    donde `respuestas` es una lista de dicts {step, alter, octave} con
    TODAS las enarmonías posibles de la nota dada (1 o 2 elementos).

    - Octava base: 4. La nota suena en el centro del pentagrama de Sol.
    - Dirección del par: sorteada (presentamos nota1 o nota2 50/50).
    - `proporcion_raros`: fracción de enharmónicos "raros" vs seguros.
    - No repetimos el mismo par dentro de la ficha.
    """
    if seed is not None:
        random.seed(seed)

    n_raros = round(n_compases * proporcion_raros)
    n_seguros = n_compases - n_raros

    elegidos = (
        random.sample(PARES_RAROS, min(n_raros, len(PARES_RAROS))) +
        random.sample(PARES_SEGUROS, min(n_seguros, len(PARES_SEGUROS)))
    )
    random.shuffle(elegidos)

    items = []
    for (n1, n2, delta_oct) in elegidos:
        # Sorteo cuál de los 2 lados se ENSEÑA (sigue existiendo para
        # garantizar variedad entre presentaciones).
        if random.random() < 0.5:
            (step, alter) = n1
            octave = 4
        else:
            (step, alter) = n2
            octave = 4 + delta_oct

        # Todas las enarmonías posibles de la nota dada.
        respuestas = []
        for (rs, ra, rd) in TODAS_ENARMONIAS.get((step, alter), []):
            respuestas.append({
                "step": rs, "alter": ra, "octave": octave + rd,
            })
        items.append({
            "step": step, "octave": octave, "alter": alter,
            "respuestas": respuestas,
        })
    return items


# -----------------------------------------------------------------------------
# MusicXML
# -----------------------------------------------------------------------------
def _nota_xml(step, octave, alter, es_oculta=False, color=None):
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


def musicxml_ejercicio(items, modo_solucion=False):
    """4 compases, cada uno con 1 redonda visible (la que se le da al
    alumno) + N_ENH_PLACEHOLDERS redondas reservadas a la derecha para
    las enarmonías (2 por compás en todos los casos, para mantener el
    ancho constante).

    Alumno: las respuestas van ocultas (solo reservan ancho).
    Solución: cada enarmonía posible se dibuja en ROJO (1 o 2 notas).
    Si la nota dada es Sol#/Lab (1 sola enarmonía), el segundo hueco
    queda oculto también en solución — así todos los compases tienen
    el mismo ancho."""
    measures = []
    for i, it in enumerate(items, start=1):
        respuestas = it.get("respuestas", [])
        contenido = _nota_xml(it["step"], it["octave"], it["alter"])
        # Notas de respuesta: 1 o 2 visibles en rojo si es solución,
        # o totalmente ocultas si es alumno. Rellenamos con ocultos
        # hasta N_ENH_PLACEHOLDERS para mantener el ancho.
        for k in range(N_ENH_PLACEHOLDERS):
            if k < len(respuestas) and modo_solucion:
                r = respuestas[k]
                contenido += _nota_xml(
                    r["step"], r["octave"], r["alter"],
                    color="#FF0000",
                )
            else:
                contenido += _nota_xml("C", 4, 0, es_oculta=True)
        is_last = (i == len(items))
        barra_final = ''
        if is_last:
            barra_final = (
                '<barline location="right">'
                '<bar-style>light-heavy</bar-style></barline>'
            )
        if i == 1:
            meas = f"""
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <key><fifths>0</fifths></key>
        <time print-object="no"><beats>8</beats><beat-type>4</beat-type></time>
        <clef><sign>G</sign><line>2</line></clef>
      </attributes>{contenido}
      {barra_final}
    </measure>"""
        else:
            meas = f"""
    <measure number="{i}">
      <print new-system="no"/>{contenido}
      {barra_final}
    </measure>"""
        measures.append(meas)

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
# Render + extracción de geometría
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
    x_fin_clef = x_clef + 500
    return vb_w, pm_x, agrup, x_fin_clef


def _x_noteheads(svg):
    xs = []
    for m in re.finditer(
        r'class="notehead"[^>]*>\s*<use[^>]*transform="translate\((\-?[\d\.]+),',
        svg,
    ):
        xs.append(float(m.group(1)))
    return xs


def _render_png(xml, png_path, padding_inf_mm=9):
    tk = verovio.toolkit()
    tk.setOptions({
        "pageWidth": 2100,
        "pageHeight": 2970,
        "pageMarginTop": 20, "pageMarginBottom": 20,
        "pageMarginLeft": 20, "pageMarginRight": 20,
        "scale": 35,
        "spacingStaff": 8,
        "spacingSystem": 8,
        # snl=0.55 da un ancho natural ~180mm para 4 compases × 3 notas.
        # Con snl=0.6 (default en otros ejercicios) salía 240mm y al
        # escalar a 160mm el pentagrama quedaba demasiado bajo.
        "spacingNonLinear": 0.55,
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

    vb_w, pm_x, barras, x_fin_clef = _extraer_geometria(svg)
    centros = []
    for i in range(4):
        left = x_fin_clef if i == 0 else (
            barras[i - 1] if (i - 1) < len(barras) else vb_w
        )
        right = barras[i] if i < len(barras) else vb_w
        centros.append((pm_x + (left + right) / 2) / vb_w)

    # Verovio dibuja también los noteheads de los placeholders ocultos
    # (12 en total para 4 compases con 1 nota dada + 2 enarmonías).
    # Nos quedamos con el PRIMER notehead de cada compás (la dada).
    step_por_compas = 1 + N_ENH_PLACEHOLDERS
    x_notas_vb = _x_noteheads(svg)[::step_por_compas]
    x_notas_frac = [(pm_x + x) / vb_w for x in x_notas_vb]

    # Generamos el PNG con un ancho proporcional al ancho NATURAL del
    # contenido (vb_w). Así el pentagrama siempre tiene el mismo tamaño
    # visual, independientemente de cuántas notas haya por compás.
    # Mismo patrón que generar_grados / generar_qihe.
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

    return centros, x_notas_frac, ancho_mm_natural


# -----------------------------------------------------------------------------
# Dibujo en un canvas (para la ficha combinada) y PDF standalone
# -----------------------------------------------------------------------------
def dibujar_en_canvas(c, x_ini, y_top, items, num_enunciado,
                      out_pdf_path, ancho_util_mm=160,
                      modo_solucion=False):
    """Dibuja el ejercicio de Enarmonías en `c` a partir de `y_top`.
    Devuelve el Y del borde inferior de lo dibujado (y_bottom).

    `out_pdf_path` se usa solo para generar el PNG auxiliar del
    pentagrama (mismo disco donde está el PDF final). Se acepta
    Path o str.
    """
    out_pdf_path = Path(out_pdf_path)

    xml = musicxml_ejercicio(items, modo_solucion=modo_solucion)
    png_path = out_pdf_path.with_name(out_pdf_path.stem + "_enarm.png")
    centros, x_notas_frac, ancho_mm_natural = _render_png(xml, png_path)
    img = ImageReader(str(png_path))
    iw, ih = img.getSize()
    # Patrón QIHE/grados: mantener escala natural cuando cabe, reducir
    # solo si el contenido natural supera el ancho útil. Así el staff
    # preserva su altura visual coherente con los demás ejercicios.
    factor = min(1.0, ancho_util_mm / ancho_mm_natural)
    ancho_pdf_mm = ancho_mm_natural * factor
    alto_mm = ancho_pdf_mm * ih / iw

    # Título del ejercicio
    y_titulo = y_top
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x_ini, y_titulo, f"{num_enunciado}. Enarmonía")

    # Pentagrama centrado horizontalmente
    x_img = x_ini + (ancho_util_mm - ancho_pdf_mm) * mm / 2
    y_img = y_titulo - 6 * mm - alto_mm * mm
    c.drawImage(img, x_img, y_img, width=ancho_pdf_mm * mm,
                height=alto_mm * mm)

    # Alumno: SIN líneas de respuesta — escribe en el hueco debajo
    # de la nota (placeholder oculto). Solución: la enarmónica se
    # dibuja como nota en ROJO sobre el pentagrama — verovio colorea
    # via atributo color="#FF0000" en el <note>.
    return y_img


def componer_pdf_enarmonias(items, numero_ficha, out_pdf,
                             num_enunciado=12, modo_solucion=False):
    """PDF standalone de una página con el ejercicio de Enarmonías."""
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
    ap.add_argument("--num-enunciado", type=int, default=12,
                    help="número del ejercicio en la ficha")
    ap.add_argument("--solucion", action="store_true",
                    help="dibujar respuestas en rojo")
    args = ap.parse_args()

    out_dir = Path("/sessions/elegant-busy-goldberg/mnt/outputs")
    out_dir.mkdir(parents=True, exist_ok=True)

    for i in range(1, args.n + 1):
        seed = 12000 + i
        items = elegir_enarmonias(seed=seed)
        sufijo = "_sol" if args.solucion else ""
        pdf_path = out_dir / f"prototipo_ficha_{i}_ej12enarm{sufijo}.pdf"
        print(f"Generando {pdf_path.name}")
        for it in items:
            nombres_r = " / ".join(
                f"{nombre_nota(r['step'], r['alter'])}{r['octave']}"
                for r in it["respuestas"]
            )
            print(f"   · {nombre_nota(it['step'], it['alter'])}"
                  f"{it['octave']} → {nombres_r}")
        componer_pdf_enarmonias(
            items, i, pdf_path,
            num_enunciado=args.num_enunciado,
            modo_solucion=args.solucion,
        )

    print("\nListo")


if __name__ == "__main__":
    main()
