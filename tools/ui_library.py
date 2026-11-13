#!/usr/bin/env python3
"""ui_library.py - a shared library of UI elements (knobs, faders, switches, buttons, labels) for MPC plugins.

An element is a folder in ui-library/ holding element.json. The file says what the element looks like
(its colours, sizes, parts and ticks); render_element() draws the film strips and button images with the
same renderer that makes the UI kit (tools/make_ui_kit.py), so the PNGs match the kit exactly.

    element.json
    {
      "format": 1,
      "name": "amber-knob",          folder name; letters, digits, '-' and '_'
      "type": "knob",                knob | fader | switch | button | label
      "base": "amber",               a kit theme for every colour not set below
      "accent": "ffffa21a",          optional: the value arc / LED colour (ARGB)
      "colours": {                   optional overrides (ARGB): body, track, pointer, thumb, outline
        "body": "ff2a2a2d"
      },
      "parts": {                     optional: switch a part off (true = drawn, the default)
        "pointer": false
      },
      "size": 90,                    knob: diameter in px (40 to 160)
      "ticks": {                     knob or fader: marks round a knob (a 270 degree ring) or along a fader
        "count": 11, "length": 6, "stroke": 2, "colour": "ff8a8a8e",
        "radius": 52                 knob only: outer radius of the ring, from the knob's centre
      },
      "width": 120, "height": 44,    button: size in px
      "led": true,                   button: show the LED
      "corner": 8,                   button: corner roundness in px
      "highlight": 2,                button: width of the lit band along the top, in px (0 = none)
      "shadow": 4,                   button: how far the drop shadow falls below, in px (0 = none)
      "text": {                      label: the text style of a heading or label
        "height": 26, "colour": "ffffffff", "justification": "left"
      }
    }

Usage:
    ui_library.py list                          list the elements in ui-library/
    ui_library.py new <name> --type knob        write a starter element.json
    ui_library.py check <name>                  validate an element
    ui_library.py render <name>                 draw its PNGs into ui-library/<name>/ (for viewing)

tools/gen_ui.py uses elements through load_element() and render_element(); you do not need to render
them yourself before a build.

Fixed sizes: a fader is always 248 x 36 and a switch always uses the kit's sizes, because the MPC
slot layout is fixed for them. Only colours, parts and ticks change for those. Standard library only; Python 3.9+.
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_ui_kit as mk  # noqa: E402

FORMAT = 1
TYPES = ("knob", "fader", "switch", "button", "label")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$")
COLOUR_KEYS = ("body", "track", "pointer", "thumb", "outline", "accent", "secondary", "highlight", "shadow")
KNOB_COLOURS = ("secondary", "highlight", "shadow")   # the knob's cap top, highlight band and drop shadow
PART_KEYS = ("body", "track", "pointer", "thumb", "outline")
TICK_KEYS = ("count", "length", "stroke", "colour", "radius")
TICK_TYPES = ("knob", "fader")
FRAMES = mk.FRAMES
DEFAULT_LIBRARY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui-library")
JUSTIFY = ("left", "centre", "right")


class ElementError(ValueError):
    pass


def library_dir():
    return DEFAULT_LIBRARY


def _colour(value, where):
    """Checks an ARGB colour and returns it as 8 lowercase hex digits."""
    try:
        r, g, b, a = mk.parse_argb(value)
    except (ValueError, TypeError):
        raise ElementError('%s must be an 8-digit ARGB colour like "ffd31145", got %r' % (where, value))
    return "%02x%02x%02x%02x" % (a, r, g, b)


def _int(value, where, lo, hi):
    if not isinstance(value, int) or isinstance(value, bool) or not lo <= value <= hi:
        raise ElementError("%s must be a whole number from %d to %d, got %r" % (where, lo, hi, value))
    return value


def _number(value, where, lo, hi):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not lo <= value <= hi:
        raise ElementError("%s must be a number from %g to %g, got %r" % (where, lo, hi, value))
    return float(value)


def _depth_and_outline(el, out, typ):
    """Depth (shadow, highlight) and outline width, for the types that take them. Keys left out keep the kit's look."""
    if "shadow" in el:
        out["shadow"] = _int(el["shadow"], '"shadow"', 0, 12)
    if "highlight" in el:
        out["highlight"] = _int(el["highlight"], '"highlight"', 0, 10)
    if "outlineWidth" in el:
        out["outlineWidth"] = _number(el["outlineWidth"], '"outlineWidth"', 0.5, 4.0)


def _ridges(spec):
    """Ridges round the outer edge of a knob: `count` notches of `length` px into the body's rim."""
    if not isinstance(spec, dict):
        raise ElementError('"ridges" must be an object like {"count": 24, "length": 3}')
    for k in spec:
        if k not in ("count", "length"):
            raise ElementError('"ridges" key "%s" is not one of count, length' % k)
    return {"count": _int(spec.get("count", 24), '"ridges".count', 2, 96),
            "length": _int(spec.get("length", 3), '"ridges".length', 1, 8)}


def _cap(spec):
    """The flat top of a knob: size (fraction of the face radius), shade (0 flat .. 1 strong slope), invert
    (swap the lit and dark sides) and curve (optional custom gradient across the slope: points [u, v], u 0 at
    the flat top's edge .. 1 at the face's edge, v 0 dark .. 1 light; 2 to 16 points)."""
    if not isinstance(spec, dict):
        raise ElementError('"cap" must be an object like {"size": 0.7, "shade": 0.5}')
    for k in spec:
        if k not in ("size", "shade", "invert", "curve"):
            raise ElementError('"cap" key "%s" is not one of size, shade, invert, curve' % k)
    out = {"size": _number(spec.get("size", 0.7), '"cap".size', 0.3, 0.95),
           "shade": _number(spec.get("shade", 0.5), '"cap".shade', 0.0, 1.0)}
    if "invert" in spec:
        if not isinstance(spec["invert"], bool):
            raise ElementError('"cap".invert must be true or false')
        out["invert"] = spec["invert"]
    if "curve" in spec:
        pts = spec["curve"]
        if not isinstance(pts, list) or not 2 <= len(pts) <= 16:
            raise ElementError('"cap".curve must be a list of 2 to 16 points like [[0, 0], [1, 1]]')
        clean = []
        for i, p in enumerate(pts):
            if not isinstance(p, list) or len(p) != 2:
                raise ElementError('"cap".curve point %d must be [u, v]' % i)
            clean.append((_number(p[0], '"cap".curve point %d u' % i, 0.0, 1.0),
                          _number(p[1], '"cap".curve point %d v' % i, 0.0, 1.0)))
        out["curve"] = sorted(clean)
    return out


def _ticks(spec, typ):
    """The ticks block of a knob or fader element, checked and filled with defaults."""
    if not isinstance(spec, dict):
        raise ElementError('"ticks" must be an object like {"count": 11, "length": 6}')
    for k in spec:
        if k not in TICK_KEYS:
            raise ElementError('"ticks" key "%s" is not one of %s' % (k, ", ".join(TICK_KEYS)))
        if k == "radius" and typ != "knob":
            raise ElementError('"ticks".radius only applies to a knob (ticks along a fader have no radius)')
    out = {"count": _int(spec.get("count", 11), '"ticks".count', 2, 33),
           "length": _int(spec.get("length", 6), '"ticks".length', 2, 60),
           "stroke": _int(spec.get("stroke", 2), '"ticks".stroke', 1, 6),
           "colour": _colour(spec.get("colour", "ff8a8a8e"), '"ticks".colour')}
    if typ == "knob":
        out["radius"] = _int(spec.get("radius", 52), '"ticks".radius', 20, 140)
    return out


def validate(el, folder_name=None):
    """Checks an element dict and returns a normalised copy. Raises ElementError with a plain message."""
    if not isinstance(el, dict):
        raise ElementError("the element file must hold one JSON object")
    allowed = {"format", "name", "type", "base", "accent", "colours", "parts", "ticks", "size",
               "width", "height", "led", "corner", "highlight", "shadow", "outlineWidth", "ridges", "text",
               "cap", "pointerLength", "pointerOffset", "showValue", "valueSize", "valueColour", "highlightAngle"}
    knob_only = ("cap", "pointerLength", "pointerOffset", "showValue", "valueSize", "valueColour", "highlightAngle")
    for k in el:
        if k not in allowed:
            raise ElementError('unknown key "%s" (allowed: %s)' % (k, ", ".join(sorted(allowed))))
    if el.get("format", FORMAT) != FORMAT:
        raise ElementError('"format" must be %d' % FORMAT)
    name = el.get("name")
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise ElementError('"name" must start with a letter or digit and use only letters, digits, "-" and "_"')
    if folder_name is not None and folder_name != name:
        raise ElementError('"name" is "%s" but the folder is "%s"; they must match' % (name, folder_name))
    typ = el.get("type")
    if typ not in TYPES:
        raise ElementError('"type" must be one of %s' % ", ".join(TYPES))
    base = el.get("base", "mpc-red")
    if base not in mk.THEMES:
        raise ElementError('"base" must be a kit theme (%s), got %r' % (", ".join(sorted(mk.THEMES)), base))
    out = {"format": FORMAT, "name": name, "type": typ, "base": base}
    if "accent" in el:
        out["accent"] = _colour(el["accent"], '"accent"')
    colours = el.get("colours", {})
    if not isinstance(colours, dict):
        raise ElementError('"colours" must be an object like {"body": "ff2a2a2d"}')
    for k, v in colours.items():
        if k not in COLOUR_KEYS:
            raise ElementError('"colours" key "%s" is not one of %s' % (k, ", ".join(COLOUR_KEYS)))
        if k in KNOB_COLOURS and typ != "knob":
            raise ElementError('"colours".%s applies to a knob element (this one is a %s)' % (k, typ))
        out.setdefault("colours", {})[k] = _colour(v, '"colours".%s' % k)
    parts = el.get("parts", {})
    if not isinstance(parts, dict):
        raise ElementError('"parts" must be an object like {"pointer": false}')
    for k, v in parts.items():
        if k not in PART_KEYS:
            raise ElementError('"parts" key "%s" is not one of %s' % (k, ", ".join(PART_KEYS)))
        if not isinstance(v, bool):
            raise ElementError('"parts".%s must be true or false' % k)
    if parts:
        out["parts"] = dict(parts)
    if "ticks" in el and typ not in TICK_TYPES:
        raise ElementError('"ticks" applies to knob and fader elements (this one is a %s)' % typ)
    if typ == "knob":
        out["size"] = _int(el.get("size", 90), '"size"', 40, 160)
        _depth_and_outline(el, out, typ)
        if "ridges" in el:
            out["ridges"] = _ridges(el["ridges"])
        if "ticks" in el:
            out["ticks"] = _ticks(el["ticks"], typ)
        if "cap" in el:
            out["cap"] = _cap(el["cap"])
        if "pointerLength" in el:
            out["pointerLength"] = _number(el["pointerLength"], '"pointerLength"', 0.3, 1.0)
        if "pointerOffset" in el:
            out["pointerOffset"] = _number(el["pointerOffset"], '"pointerOffset"', -20.0, 20.0)
        if "showValue" in el:
            if not isinstance(el["showValue"], bool):
                raise ElementError('"showValue" must be true or false')
            out["showValue"] = el["showValue"]
        if "valueSize" in el:
            out["valueSize"] = _int(el["valueSize"], '"valueSize"', 8, 60)
        if "valueColour" in el:
            out["valueColour"] = _colour(el["valueColour"], '"valueColour"')
        if "highlightAngle" in el:
            out["highlightAngle"] = _number(el["highlightAngle"], '"highlightAngle"', -180.0, 180.0)
    elif typ == "fader":
        for k in ("size", "width", "height", "led", "text", "corner", "ridges") + knob_only:
            if k in el:
                raise ElementError('"%s" does not apply to a fader element' % k)
        _depth_and_outline(el, out, typ)
        if "ticks" in el:
            out["ticks"] = _ticks(el["ticks"], typ)
    elif typ == "button":
        out["width"] = _int(el.get("width", 120), '"width"', 40, 240)
        out["height"] = _int(el.get("height", 44), '"height"', 20, 120)
        led = el.get("led", True)
        if not isinstance(led, bool):
            raise ElementError('"led" must be true or false')
        out["led"] = led
        out["corner"] = _int(el.get("corner", 8), '"corner"', 0, 30)
        out["highlight"] = _int(el.get("highlight", 0), '"highlight"', 0, 10)
        out["shadow"] = _int(el.get("shadow", 0), '"shadow"', 0, 12)
        if "outlineWidth" in el:
            out["outlineWidth"] = _number(el["outlineWidth"], '"outlineWidth"', 0.5, 4.0)
    elif typ == "label":
        text = el.get("text", {})
        if not isinstance(text, dict):
            raise ElementError('"text" must be an object like {"height": 26, "colour": "ffffffff"}')
        for k in text:
            if k not in ("height", "colour", "justification"):
                raise ElementError('"text" key "%s" is not one of height, colour, justification' % k)
        just = text.get("justification", "left")
        if just not in JUSTIFY:
            raise ElementError('"text".justification must be one of %s' % ", ".join(JUSTIFY))
        out["text"] = {"height": _int(text.get("height", 26), '"text".height', 8, 60),
                       "colour": _colour(text.get("colour", "ffffffff"), '"text".colour'),
                       "justification": just}
    elif typ == "switch":
        for k in ("size", "width", "height", "led", "text", "corner", "ridges") + knob_only:
            if k in el:
                raise ElementError('"%s" does not apply to a switch element' % k)
        _depth_and_outline(el, out, typ)
    return out


def load_element(folder):
    """Reads and validates <folder>/element.json. Returns the normalised element dict."""
    path = os.path.join(folder, "element.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except OSError:
        raise ElementError('no element.json in "%s"' % folder)
    except ValueError as e:
        raise ElementError("%s is not valid JSON: %s" % (path, e))
    return validate(raw, os.path.basename(os.path.normpath(folder)))


def find_element(name, library=None):
    """The folder of a library element called `name`, or raises ElementError."""
    lib = library or library_dir()
    folder = os.path.join(lib, name)
    if not os.path.isfile(os.path.join(folder, "element.json")):
        have = sorted(n for n in (os.listdir(lib) if os.path.isdir(lib) else [])
                      if os.path.isfile(os.path.join(lib, n, "element.json")))
        raise ElementError('no element named "%s" in %s (have: %s)' % (name, lib, ", ".join(have) or "none"))
    return folder


# --------------------------------------------------------------------------------------------
# Colours: a kit theme with the element's overrides applied, and the colours that follow from them
# --------------------------------------------------------------------------------------------
def element_style(el):
    """The depth, outline and ridge settings the renderer takes (None when the element sets none)."""
    st = {}
    if "shadow" in el and el["type"] != "button":
        st["shadow"] = el["shadow"]
    if "highlight" in el and el["type"] != "button":
        st["highlight"] = el["highlight"]
    if "outlineWidth" in el:
        st["outline_w"] = el["outlineWidth"]
    if "ridges" in el:
        st["ridges"] = (el["ridges"]["count"], el["ridges"]["length"])
    if "cap" in el:
        st["cap"] = el["cap"]
    if "pointerLength" in el:
        st["pointer_len"] = el["pointerLength"]
    if "pointerOffset" in el:
        st["pointer_off"] = el["pointerOffset"]
    if "highlightAngle" in el:
        st["hl_angle"] = math.radians(el["highlightAngle"])   # the renderer works in radians from 12 o'clock
    return st or None


def element_theme(el):
    acc = el.get("accent") or (el.get("colours") or {}).get("accent")
    th = mk.make_theme(el["base"], acc)
    white, black = (255, 255, 255, 255), (0, 0, 0, 255)
    c = el.get("colours", {})
    if "outline" in c:
        th["outline"] = mk.parse_argb(c["outline"])
    if "body" in c:
        b = mk.parse_argb(c["body"])
        th.update(body=b, bodyLight=mk.mix(b, white, 0.15), bodyDark=mk.mix(b, black, 0.35))
    if "track" in c:
        th["track"] = mk.parse_argb(c["track"])
    if "pointer" in c:
        th["pointer"] = mk.parse_argb(c["pointer"])
    if "thumb" in c:
        t = mk.parse_argb(c["thumb"])
        th.update(thumb=t, thumbLight=mk.mix(t, white, 0.4), thumbDark=mk.mix(t, black, 0.25))
    for k in KNOB_COLOURS:   # only set when the element asks; the kit's own look is kept otherwise
        if k in c:
            th[k] = mk.parse_argb(c[k])
    acc_rgba = mk.parse_argb(acc) if acc else th["accent"]
    th["accent"] = acc_rgba
    th["accentDark"] = mk.mix(acc_rgba, th["outline"], 0.35)
    th["accentGlow"] = mk.with_alpha(acc_rgba, 70)
    th["ledOff"] = mk.mix(acc_rgba, th["body"], 0.78)
    return th


# --------------------------------------------------------------------------------------------
# Ticks: part of a knob or fader element
# --------------------------------------------------------------------------------------------
def tick_geometry(tk, target):
    """Where the ticks are. A knob's ring has radius R: the picture is 2R x 2R, centred on the knob.
    A fader's marks sit in a 248-wide strip, one per cap position, `length` tall.
    Returns (w, h, marks) with marks as (x0, y0, x1, y1) in picture pixels."""
    n, L = tk["count"], tk["length"]
    if target == "knob":
        R = tk["radius"]
        marks = []
        for i in range(n):
            a = math.radians(-135.0 + 270.0 * i / (n - 1))
            r0, r1 = R - L, R
            marks.append((R + math.sin(a) * r0, R - math.cos(a) * r0, R + math.sin(a) * r1, R - math.cos(a) * r1))
        return 2 * R, 2 * R, marks
    xs = [11 + 226.0 * i / (n - 1) for i in range(n)]   # the cap centres run from x=11 to x=237
    return 248, L, [(x, 0.5, x, L - 0.5) for x in xs]


def emit_ticks(el, out_dir, assets):
    tk = el["ticks"]
    w, h, marks = tick_geometry(tk, el["type"])
    c = mk.Canvas(w, h)
    col = mk.parse_argb(tk["colour"])
    for x0, y0, x1, y1 in marks:
        mk.capsule(c, x0, y0, x1, y1, tk["stroke"], col)
    mk.write_png(os.path.join(out_dir, "ticks.png"), w, c.rows())
    assets["ticks"] = {"file": "ticks.png", "width": w, "height": h, "frames": 1}


# --------------------------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------------------------
def source_hash(el):
    return hashlib.sha256(json.dumps(el, sort_keys=True).encode("utf-8")).hexdigest()


def render_element(el, out_dir, quiet=True):
    """Draws the element's PNGs into out_dir and writes manifest.json there. Returns the manifest dict.

    The manifest's "assets" maps each asset key (the same keys as the kit: knob_uni, toggle_on, ticks, ...)
    to its file, frame count and size, so the generator can use an element exactly like a kit."""
    th = element_theme(el)
    parts = {**mk.ALL_PARTS, **el.get("parts", {})}
    os.makedirs(out_dir, exist_ok=True)
    assets = {}

    def emit(key, rows, w, h, frames):
        mk.write_png(os.path.join(out_dir, key + ".png"), w, rows)
        assets[key] = {"file": key + ".png", "width": w, "height": h, "frames": frames}

    typ = el["type"]
    if typ == "knob":
        s = el["size"]
        style = element_style(el)
        emit("knob_uni", mk.render_knob(s, FRAMES, th, False, parts, style), s, s, FRAMES)
        emit("knob_bi", mk.render_knob(s, FRAMES, th, True, parts, style), s, s, FRAMES)
        if "ticks" in el:
            emit_ticks(el, out_dir, assets)
    elif typ == "fader":
        style = element_style(el)
        emit("fader_h_uni", mk.render_fader(248, 36, FRAMES, th, False, False, parts, style), 248, 36, FRAMES)
        emit("fader_h_bi", mk.render_fader(248, 36, FRAMES, th, True, False, parts, style), 248, 36, FRAMES)
        if "ticks" in el:
            emit_ticks(el, out_dir, assets)
    elif typ == "switch":
        for state in ("on", "off"):
            emit("toggle_" + state, mk.render_toggle(th, state == "on", parts, element_style(el))[0], 64, 32, 1)
        for n, w in ((2, 122), (3, 80), (4, 58)):
            for state in ("on", "off"):
                emit("seg%d_%s" % (n, state), mk.render_button(th, state == "on", w, 40, led=False, parts=parts)[0], w, 40, 1)
    elif typ == "button":
        w, h, led = el["width"], el["height"], el["led"]
        shape = dict(radius=el["corner"], highlight=el["highlight"], shadow=el["shadow"],
                     outline_w=el.get("outlineWidth"))
        emit("button_on", mk.render_button(th, True, w, h, led=led, parts=parts, **shape)[0], w, h, 1)
        emit("button_off", mk.render_button(th, False, w, h, led=led, parts=parts, **shape)[0], w, h, 1)
    manifest = {"format": FORMAT, "name": el["name"], "type": typ, "base": el["base"],
                "source": source_hash(el), "assets": assets}
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    if not quiet:
        print("ui_library: rendered %s (%s, %d file%s)" % (el["name"], typ, len(assets), "" if len(assets) == 1 else "s"))
    return manifest


def cached_manifest(el, cache_dir):
    """Renders the element into cache_dir unless that copy is already current, and returns its manifest."""
    path = os.path.join(cache_dir, "manifest.json")
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                m = json.load(f)
            if m.get("source") == source_hash(el) and all(os.path.isfile(os.path.join(cache_dir, a["file"]))
                                                         for a in m.get("assets", {}).values()):
                return m
        except (OSError, ValueError):
            pass
    return render_element(el, cache_dir, quiet=True)


# --------------------------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------------------------
def starter(name, typ, base):
    el = {"format": FORMAT, "name": name, "type": typ, "base": base}
    if typ == "knob":
        el["size"] = 90
    elif typ == "button":
        el.update(width=120, height=44, led=True, corner=8, highlight=2, shadow=4)
    elif typ == "label":
        el["text"] = {"height": 26, "colour": "ffffffff", "justification": "left"}
    if typ in ("knob", "fader", "switch", "button"):
        el["colours"] = {}
    return el


def main(argv=None):
    ap = argparse.ArgumentParser(description="Manage the shared UI element library (ui-library/).")
    ap.add_argument("--library", default=None, help="library folder (default: ui-library/ at the repo root)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p = sub.add_parser("new")
    p.add_argument("name")
    p.add_argument("--type", required=True, choices=TYPES)
    p.add_argument("--base", default="mpc-red", choices=sorted(mk.THEMES))
    p = sub.add_parser("check")
    p.add_argument("name")
    p = sub.add_parser("render")
    p.add_argument("name")
    args = ap.parse_args(argv)
    lib = args.library or library_dir()
    try:
        if args.cmd == "list":
            names = sorted(n for n in (os.listdir(lib) if os.path.isdir(lib) else [])
                           if os.path.isfile(os.path.join(lib, n, "element.json")))
            if not names:
                print("No elements in %s yet. Make one with: ui_library.py new <name> --type knob" % lib)
            for n in names:
                try:
                    el = load_element(os.path.join(lib, n))
                    print("%-24s %-8s base %s" % (n, el["type"], el["base"]))
                except ElementError as e:
                    print("%-24s ERROR: %s" % (n, e))
        elif args.cmd == "new":
            folder = os.path.join(lib, args.name)
            if os.path.exists(folder):
                raise ElementError('"%s" already exists' % folder)
            el = validate(starter(args.name, args.type, args.base))
            os.makedirs(folder)
            with open(os.path.join(folder, "element.json"), "w", encoding="utf-8") as f:
                json.dump(el, f, indent=2)
                f.write("\n")
            print("Wrote %s" % os.path.join(folder, "element.json"))
        elif args.cmd == "check":
            el = load_element(find_element(args.name, lib))
            print("OK: %s is a valid %s element" % (args.name, el["type"]))
        elif args.cmd == "render":
            folder = find_element(args.name, lib)
            el = load_element(folder)
            render_element(el, folder, quiet=False)
    except ElementError as e:
        print("ui_library: ERROR: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
