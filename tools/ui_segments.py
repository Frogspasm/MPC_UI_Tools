"""16-segment alphanumeric glyphs, drawn to PNG for the MPC skin.

The segment shapes and the character table follow the Multi-trak project's "Alphanumeric LED display"
notes (SEG16 / CHAR16): a cell is a 40 x 70 unit grid, and each character lights a set of named segments.
The notes give the letters K, N, X, Y, Z, A and B and the symbols; the other letters and digits are set
here in the same convention and have not been checked against the original panel.

The MPC shows text only in its own font, so a segment glyph is drawn into the knob's picture: each frame of
the knob carries the glyph for its value, at the knob's centre, sized by the element's valueSize (like the
font text it replaces).
"""
import re

import make_ui_kit as mk

GRID_W, GRID_H = 40.0, 70.0

#: Each segment as a polygon on the 40 x 70 grid.
SEG16 = {
    "a1": [(6, 4), (19, 4), (16, 10), (10, 10)], "a2": [(21, 4), (34, 4), (30, 10), (24, 10)],
    "b": [(36, 6), (36, 32), (31, 30), (31, 10)], "c": [(36, 38), (36, 64), (31, 60), (31, 40)],
    "d1": [(6, 66), (19, 66), (16, 60), (10, 60)], "d2": [(21, 66), (34, 66), (30, 60), (24, 60)],
    "e": [(4, 38), (4, 64), (9, 60), (9, 40)], "f": [(4, 6), (4, 32), (9, 30), (9, 10)],
    "g1": [(8, 35), (10, 32), (18, 32), (19, 35), (18, 38), (10, 38)],
    "g2": [(21, 35), (22, 32), (30, 32), (32, 35), (30, 38), (22, 38)],
    "h": [(11, 10), (17, 10), (20, 31), (17, 31)], "i": [(29, 10), (23, 10), (20, 31), (23, 31)],
    "j": [(11, 60), (17, 60), (20, 39), (17, 39)], "k": [(29, 60), (23, 60), (20, 39), (23, 39)],
    "l": [(19, 38), (21, 38), (21, 62), (19, 62)], "m": [(19, 8), (21, 8), (21, 32), (19, 32)],
}
#: Drawing order: later segments sit on top of earlier ones.
SEG_ORDER = ["a1", "a2", "b", "c", "d1", "d2", "e", "f", "g1", "g2", "h", "i", "j", "k", "l", "m"]

#: Which segments each character lights. These are the characters a glyph list may use.
CHAR16 = {
    " ": "", "-": "g1g2", "/": "ij", "(": "fe", ")": "bc", "'": "m", ".": "l",
    "0": "a1a2bcd1d2efij", "1": "bcm", "2": "a1a2bg1g2ed1d2", "3": "a1a2bcd1d2g2",
    "4": "fg1g2bc", "5": "a1a2fg1g2cd1d2", "6": "a1a2fg1g2ced1d2", "7": "a1a2bc",
    "8": "a1a2bcd1d2efg1g2", "9": "a1a2bcd1d2fg1g2",
    "A": "a1a2bcefg1g2", "B": "a1a2bcd1d2mlg1g2", "C": "a1a2fed1d2", "D": "a1a2bcd1d2ml",
    "E": "a1a2fed1d2g1", "F": "a1a2feg1", "G": "a1a2fed1d2cg2", "H": "febcg1g2", "I": "a1a2d1d2ml",
    "J": "bcd1d2e", "K": "feg1hk", "L": "fed1d2", "M": "febchi", "N": "febchk", "O": "a1a2bcd1d2ef",
    "P": "a1a2bfeg1g2", "Q": "a1a2bcd1d2efk", "R": "a1a2bfeg1g2k", "S": "a1a2fg1g2cd1d2",
    "T": "a1a2ml", "U": "bcd1d2ef", "V": "efjk", "W": "efbcjkhi", "X": "hijk", "Y": "him",
    "Z": "a1a2d1d2ij",
}
#: The characters a glyph list may use.
GLYPH_CHARS = "".join(CHAR16.keys())

LIT = (255, 74, 58, 255)     # #ff4a3a, the notes' lit segment
DARK = (58, 20, 16, 255)     # #3a1410, the notes' unlit segment
SUB = 3                      # samples per pixel per side (3 x 3 supersampling)
DEFAULT_HEIGHT = 22          # the glyph height in px when the element sets no valueSize (the MPC's text size)

_SEG_TOKEN = re.compile(r"a[12]|d[12]|g[12]|[a-m]")
_cover_cache = {}


def chars_of(ch):
    """The segment names a character lights, in order."""
    return _SEG_TOKEN.findall(CHAR16[ch])


def check_glyphs(chars):
    """Returns an error message, or None when every character is one the glyph set has."""
    bad = [c for c in chars if c not in CHAR16]
    if bad:
        return "these characters have no 16-segment glyph: %s" % " ".join(repr(c) for c in bad)
    return None


def glyph_width(h):
    """The width of a glyph of height h (the notes' 40 : 70 cell)."""
    return h * GRID_W / GRID_H


def _point_in_poly(x, y, pts):
    inside = False
    j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _segment_cover(name, h):
    """Coverage of one segment in a glyph of height h, centred in a box of its own width.
    Returns (box width, [(x, y, fraction), ...]). Cached: every glyph reuses it."""
    key = (name, h)
    if key in _cover_cache:
        return _cover_cache[key]
    w = int(round(glyph_width(h))) + 2          # one pixel of margin each side
    gw = glyph_width(h)
    x0 = (w - gw) / 2.0
    pts = [(x0 + x * gw / GRID_W, y * h / GRID_H) for x, y in SEG16[name]]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    out = []
    for py in range(max(0, int(min(ys))), min(h, int(max(ys)) + 1)):
        for px in range(max(0, int(min(xs))), min(w, int(max(xs)) + 1)):
            hit = 0
            for sy in range(SUB):
                for sx in range(SUB):
                    if _point_in_poly(px + (sx + 0.5) / SUB, py + (sy + 0.5) / SUB, pts):
                        hit += 1
            if hit:
                out.append((px, py, hit / float(SUB * SUB)))
    _cover_cache[key] = (w, out)
    return w, out


def _over(dst, src, a):
    """Composite colour src over dst (RGBA floats) with coverage a."""
    sa = src[3] / 255.0 * a
    if sa <= 0:
        return dst
    da = dst[3] / 255.0
    oa = sa + da * (1 - sa)
    if oa <= 0:
        return (0.0, 0.0, 0.0, 0.0)
    return tuple((src[i] * sa + dst[i] * da * (1 - sa)) / oa for i in range(3)) + (oa * 255.0,)


def glyph_box(ch, h, lit=LIT, dark=DARK):
    """One glyph of height h on a transparent box: returns (width, height, rows) with RGBA rows."""
    active = set(chars_of(ch))
    boxes = {name: _segment_cover(name, h) for name in SEG_ORDER}
    w = boxes[SEG_ORDER[0]][0]
    pix = [[(0.0, 0.0, 0.0, 0.0)] * w for _ in range(h)]
    for name in SEG_ORDER:
        colour = lit if name in active else dark
        for px, py, cov in boxes[name][1]:
            pix[py][px] = _over(pix[py][px], colour, cov)
    rows = []
    for y in range(h):
        row = bytearray()
        for x in range(w):
            r, g, b, a = pix[y][x]
            row += bytes((int(round(r)), int(round(g)), int(round(b)), int(round(a))))
        rows.append(bytes(row))
    return w, h, rows


def composite(base, bw, bh, over, ow, oh, ox, oy):
    """Lays the RGBA rows `over` onto `base` (both lists of RGBA rows) with its top-left at (ox, oy).
    Returns new rows; `base` is not changed."""
    out = [bytearray(r) for r in base]
    for y in range(oh):
        by = oy + y
        if by < 0 or by >= bh:
            continue
        src_row = over[y]
        for x in range(ow):
            bx = ox + x
            if bx < 0 or bx >= bw:
                continue
            si = 4 * x
            sr, sg, sb, sa = src_row[si], src_row[si + 1], src_row[si + 2], src_row[si + 3]
            if sa == 0:
                continue
            a = sa / 255.0
            bi = 4 * bx
            dst = out[by]
            dr, dg, db, da = dst[bi], dst[bi + 1], dst[bi + 2], dst[bi + 3] / 255.0
            oa = a + da * (1 - a)
            if oa <= 0:
                continue
            dst[bi] = int(round((sr * a + dr * da * (1 - a)) / oa))
            dst[bi + 1] = int(round((sg * a + dg * da * (1 - a)) / oa))
            dst[bi + 2] = int(round((sb * a + db * da * (1 - a)) / oa))
            dst[bi + 3] = int(round(oa * 255))
    return [bytes(r) for r in out]
