"""Reusable python-pptx drawing helpers for faithful slide reconstruction.

All geometry is expressed in PERCENT of the slide (0-100), because every
measurement taken from the source raster is naturally a percentage.  The
helpers convert to EMU internally.

Slide is fixed at 16:9, 13.333 x 7.5 in.  A 3840x2160 source raster therefore
maps 1 px -> 0.25 pt (useful when calibrating font sizes).
"""
from pptx.util import Emu, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import qn
from lxml import etree

SW, SH = 12192000, 6858000          # 13.333 x 7.5 in
PX_PER_PT = 4.0                     # at 3840 px wide


def X(p):
    return Emu(int(round(p / 100.0 * SW)))


def Y(p):
    return Emu(int(round(p / 100.0 * SH)))


# --------------------------------------------------------------------------- #
# fills / lines
# --------------------------------------------------------------------------- #
def set_fill(shape, hexv=None, alpha=None, grad=None, ang=5400000):
    """Solid or vertical gradient fill.

    grad = [(pos%, 'RRGGBB'[, alpha%]), ...]  (pos 0 = start, 100 = end)
    alpha = 0..100 (percent opacity)
    ang = gradient direction in 60000ths of a degree, clockwise from east.
          5400000 (90 deg) = top -> bottom, the default.
    """
    spPr = shape._element.spPr
    for tag in ("a:solidFill", "a:gradFill", "a:noFill", "a:blipFill", "a:pattFill"):
        for e in spPr.findall(qn(tag)):
            spPr.remove(e)
    if grad:
        g = etree.SubElement(spPr, qn("a:gradFill"))
        g.set("rotWithShape", "1")
        lst = etree.SubElement(g, qn("a:gsLst"))
        for st in grad:
            gs = etree.SubElement(lst, qn("a:gs"))
            gs.set("pos", str(int(st[0] * 1000)))
            c = etree.SubElement(gs, qn("a:srgbClr"))
            c.set("val", st[1])
            if len(st) > 2 and st[2] is not None:
                etree.SubElement(c, qn("a:alpha")).set("val", str(int(st[2] * 1000)))
        lin = etree.SubElement(g, qn("a:lin"))
        lin.set("ang", str(int(ang)))
        lin.set("scaled", "1")
    else:
        f = etree.SubElement(spPr, qn("a:solidFill"))
        c = etree.SubElement(f, qn("a:srgbClr"))
        c.set("val", hexv)
        if alpha is not None:
            etree.SubElement(c, qn("a:alpha")).set("val", str(int(alpha * 1000)))
    ln = spPr.find(qn("a:ln"))
    if ln is not None:                     # keep <a:ln> last in spPr
        spPr.remove(ln)
        spPr.append(ln)


def set_line(shape, hexv, wpt, alpha=None, dash=None, head=None):
    """dash = (dash_len, space_len) in 1000ths of a percent of line width,
    e.g. (350, 650) = 3.5x / 6.5x the line width.
    head = 'triangle' | 'arrow' | 'stealth' | None (tail arrowhead)."""
    spPr = shape._element.spPr
    for e in spPr.findall(qn("a:ln")):
        spPr.remove(e)
    ln = etree.SubElement(spPr, qn("a:ln"))
    ln.set("w", str(int(wpt * 12700)))
    ln.set("cap", "flat")
    f = etree.SubElement(ln, qn("a:solidFill"))
    c = etree.SubElement(f, qn("a:srgbClr"))
    c.set("val", hexv)
    if alpha is not None:
        etree.SubElement(c, qn("a:alpha")).set("val", str(int(alpha * 1000)))
    if dash:
        cd = etree.SubElement(ln, qn("a:custDash"))
        ds = etree.SubElement(cd, qn("a:ds"))
        ds.set("d", str(int(dash[0] * 1000)))
        ds.set("sp", str(int(dash[1] * 1000)))
    if head:
        te = etree.SubElement(ln, qn("a:tailEnd"))
        te.set("type", head)
        te.set("w", "med")
        te.set("len", "med")


def no_line(shape):
    spPr = shape._element.spPr
    for e in spPr.findall(qn("a:ln")):
        spPr.remove(e)
    etree.SubElement(spPr, qn("a:ln")).append(etree.Element(qn("a:noFill")))


def no_fill(shape):
    spPr = shape._element.spPr
    for e in spPr.findall(qn("a:solidFill")) + spPr.findall(qn("a:gradFill")):
        spPr.remove(e)
    etree.SubElement(spPr, qn("a:noFill"))


# --------------------------------------------------------------------------- #
# shapes
# --------------------------------------------------------------------------- #
def roundrect(slide, x0, y0, x1, y1, radius_in=0.06, fill=None, alpha=None,
              grad=None, line=None, lw=0.75, ang=5400000):
    w, h = x1 - x0, y1 - y0
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, X(x0), Y(y0), X(w), Y(h))
    wemu, hemu = int(w / 100 * SW), int(h / 100 * SH)
    shp.adjustments[0] = max(0.0, min(0.5, (radius_in * 914400) / max(1, min(wemu, hemu))))
    shp.shadow.inherit = False
    if grad:
        set_fill(shp, grad=grad, ang=ang)
    elif fill:
        set_fill(shp, fill, alpha)
    else:
        no_fill(shp)
    set_line(shp, line, lw) if line else no_line(shp)
    return shp


def oval(slide, x0, y0, x1, y1, fill, line=None, lw=0.75):
    shp = slide.shapes.add_shape(MSO_SHAPE.OVAL, X(x0), Y(y0), X(x1 - x0), Y(y1 - y0))
    shp.shadow.inherit = False
    set_fill(shp, fill)
    set_line(shp, line, lw) if line else no_line(shp)
    return shp


def line(slide, x0, y0, x1, y1, hexv, wpt, dash=None, head=None):
    conn = slide.shapes.add_connector(1, X(x0), Y(y0), X(x1), Y(y1))
    set_line(conn, hexv, wpt, dash=dash, head=head)
    return conn


def top_border(slide, x0, y0, x1, y1, radius_in, hexv, wpt):
    """Open rounded TOP edge only: line + two corner arcs.

    Use for cards whose top edge is an accent colour while the other three
    edges are a neutral border (common in brand decks).  Draw this AFTER the
    card's own border so the accent sits on top.
    """
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, X(x0), Y(y0), X(x1 - x0), Y(y1 - y0))
    shp.shadow.inherit = False
    w, h = int((x1 - x0) / 100 * SW), int((y1 - y0) / 100 * SH)
    r = int(radius_in * 914400)
    spPr = shp._element.spPr
    for e in spPr.findall(qn("a:prstGeom")):
        spPr.remove(e)
    cg = etree.Element(qn("a:custGeom"))
    etree.SubElement(cg, qn("a:avLst"))
    etree.SubElement(cg, qn("a:gdLst"))
    etree.SubElement(cg, qn("a:ahLst"))
    etree.SubElement(cg, qn("a:cxnLst"))
    rect = etree.SubElement(cg, qn("a:rect"))
    for k, v in (("l", 0), ("t", 0), ("r", w), ("b", h)):
        rect.set(k, str(v))
    path = etree.SubElement(etree.SubElement(cg, qn("a:pathLst")), qn("a:path"))
    path.set("w", str(w)); path.set("h", str(h)); path.set("fill", "none")
    mt = etree.SubElement(path, qn("a:moveTo"))
    pt = etree.SubElement(mt, qn("a:pt")); pt.set("x", "0"); pt.set("y", str(r))
    ar = etree.SubElement(path, qn("a:arcTo"))
    ar.set("wR", str(r)); ar.set("hR", str(r)); ar.set("stAng", "10800000"); ar.set("swAng", "5400000")
    lt = etree.SubElement(path, qn("a:lnTo"))
    pt = etree.SubElement(lt, qn("a:pt")); pt.set("x", str(w - r)); pt.set("y", "0")
    ar = etree.SubElement(path, qn("a:arcTo"))
    ar.set("wR", str(r)); ar.set("hR", str(r)); ar.set("stAng", "16200000"); ar.set("swAng", "5400000")
    spPr.find(qn("a:xfrm")).addnext(cg)
    no_fill(shp)
    set_line(shp, hexv, wpt)
    return shp


# --------------------------------------------------------------------------- #
# text
# --------------------------------------------------------------------------- #
VCORR = 0.026   # empirical: rendered ink sits low by ~0.026 %/pt of slide height


def text(slide, x, yc, w, runs, font=None, size=None, bold=False, color="FFFFFF",
         align=PP_ALIGN.LEFT, h=3.0, spacing=None, top=None, anchor=MSO_ANCHOR.MIDDLE,
         line_spacing_pt=None, wrap=True):
    """Add a text box whose INK CENTRE lands on `yc` (percent).

    runs: str  -> single run using (font, size, bold, color, spacing)
          list -> [(text, font, size, bold, color, spacing_pt), ...]
    `spacing` is letter tracking in pt (OOXML `spc`).

    `yc` must be the ink centre measured from the source raster.  The VCORR
    term compensates for LibreOffice/PowerPoint centring the line box rather
    than the ink; verify with measure_slide.ink_bbox and nudge if needed.
    """
    if isinstance(runs, str):
        runs = [(runs, font, size, bold, color, spacing)]
    if top is None:
        top = yc - h / 2.0 - VCORR * max(r[2] for r in runs)
    tb = slide.shapes.add_textbox(X(x), Y(top), X(w), Y(h))
    tf = tb.text_frame
    tf.word_wrap = wrap
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    bodyPr = tf._txBody.find(qn("a:bodyPr"))
    for e in bodyPr.findall(qn("a:normAutofit")) + bodyPr.findall(qn("a:spAutoFit")):
        bodyPr.remove(e)
    etree.SubElement(bodyPr, qn("a:noAutofit"))
    p = tf.paragraphs[0]
    p.alignment = align
    if line_spacing_pt:
        p.line_spacing = Pt(line_spacing_pt)
    for (t, fnt, sz, bd, col, sp) in runs:
        r = p.add_run()
        r.text = t
        r.font.name = fnt
        r.font.size = Pt(sz)
        r.font.bold = bd
        r.font.color.rgb = RGBColor.from_string(col)
        rPr = r._r.get_or_add_rPr()
        if sp is not None:
            rPr.set("spc", str(int(sp * 100)))
        lat = rPr.find(qn("a:latin"))
        if lat is None:
            lat = etree.SubElement(rPr, qn("a:latin"))
        lat.set("typeface", fnt)
    return tb


def picture(slide, path, x0, y0, w, h):
    return slide.shapes.add_picture(path, X(x0), Y(y0), X(w), Y(h))
