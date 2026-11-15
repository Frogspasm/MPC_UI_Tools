#!/usr/bin/env python3
"""gen_ui.py - generate MPC "Plugin Skins" (TUI.json + Q-Links.json) for a plugin.

Usage:
    gen_ui.py --params build/params.json [--ui ui.json] --out "<output folder>/Plugin Skins"
              [--assets-dir skins-assets]

Inputs
    params.json   dumped by host_sim from the native build (parameter names, kinds, choices).
    ui.json       OPTIONAL layout spec. Without it, pages of 16 parameters are generated in
                  index order, named "1", "2", ...
    --kit-cache   OPTIONAL directory where the rendered film-strip kit (tools/make_ui_kit.py) is
                  cached between builds; without it the kit is rendered into the output folder.

Output
    TUI.json      the scripted UI: one tab per page, a 4 x 4 grid of controls per tab.
    Q-Links.json  maps the 16 hardware Q-Link knobs of every tab to parameter indices.
    *.png         the film-strip kit assets used by "knob", "fader" and "switch" widgets.

The JSON written here mirrors the shapes the MPC firmware expects, including the DUPLICATE
"version" keys inside the KnobOverlay / MenuOverlay widget data. Python's json module cannot
write duplicate keys, so this file carries its own tiny ordered-pairs JSON writer.

Standard library only; Python 3.9+.
"""

import argparse
import difflib
import hashlib
import json
import math
import os
import re
import shutil
import struct
import sys

# --------------------------------------------------------------------------------------------
# Layout constants (1280 x 628 tab area, 4 x 4 grid, reading order)
# --------------------------------------------------------------------------------------------
SLOT_X = [23, 343, 663, 983]
SLOT_Y = [45, 196, 346, 497]
SLOT_W, SLOT_H = 278, 107
QLINK_BOUNDS = ["38 0 248 624", "358 0 248 624", "678 0 248 624", "998 0 248 624"]   # column banks
QLINK_ROW_BOUNDS = ["8 %d 1268 137" % (y - 15) for y in [45, 196, 346, 497]]            # row banks, top row first
# How a model with 4 Q-Links (MPC One, Live) steps through a page's 16: a column at a time or a row at a time.
QLINK_BANKS = {"columns": ("Column", QLINK_BOUNDS), "rows": ("RowTopDown", QLINK_ROW_BOUNDS)}
MAX_CONTROLS_PER_PAGE = 16
MAX_PAGES = 32
FONT_NAME = "Titillium Web"

DEFAULT_STYLE = {
    "background": "ff1e1d1e",
    "accent": "ffd31145",
    "text": "ffffffff",
    "muted": "ff6a6a6c",
}

WIDGETS = ("slider", "knob", "fader", "switch", "button", "empty", "text", "plotter")
OVERLAYS = ("knob", "menu")
POLARITIES = ("auto", "unipolar", "bipolar")
CONTROL_KEYS = ("param", "widget", "visibleWhen", "text", "overlay", "polarity", "min", "max", "label", "element", "labelStyle")
# The MPC's fonts (docs/ui-reference.md 1.5). There is no way to ship another font; an unknown name draws as Titillium Web.
FONTS = ("Titillium Web", "Roboto", "Nexa")
FONT_STYLES = ("Thin", "ThinItalic", "Light", "LightItalic", "Book", "BookItalic", "Regular", "Italic", "Medium",
               "SemiBold", "SemiBoldItalic", "Bold", "BoldItalic", "Black")
LABEL_STYLE_KEYS = ("font", "style", "size", "align", "dx", "dy")
LABEL_STYLE_WIDGETS = ("knob", "fader", "switch", "button")   # the widgets whose name label the generator draws
# Which library element type each widget may use (ui_library.TYPES); "text" uses a "label" element.
ELEMENT_FOR_WIDGET = {"knob": "knob", "fader": "fader", "switch": "switch", "button": "button", "text": "label"}
LABEL_JUSTIFY = {"left": "left", "right": "right", "centre": "horizontallyCentred verticallyCentred"}
LABEL_MAX = 24   # longest on-screen label a control may have
PLOTTER_HISTORY_SECONDS = 4.0
PAGE_KEYS = ("name", "controls", "background", "backgroundTile", "backgroundScale", "art", "groups", "qlinks", "qlinkBanks")
GROUP_KEYS = ("x", "y", "w", "h", "label")
GROUP_LABEL_MAX = 40
GROUP_RADIUS = 12   # corner radius of a group outline, in pixels
GROUP_STROKE = 2    # outline thickness, in pixels
ART_KEYS = ("image", "x", "y", "w", "h", "tile", "scale")
MAX_TILES = 400   # per picture; each tile is one Image component on the tab
UI_KEYS = ("pages", "style", "kit", "knobImage", "knobFrames")
KIT_KEYS = ("theme", "accent")
KIT_WIDGETS = ("knob", "fader", "switch", "button")
MAX_SWITCH_CHOICES = 4
BIPOLAR_ZERO_RE = re.compile(r"^[+-]?0*(\.0+)?\s*[^0-9.]*$")

# Segment buttons for choice switches: (asset width, x positions in the slot) per choice count.
SEGMENTS = {2: (122, [15, 141]), 3: (80, [15, 99, 183]), 4: (58, [15, 77, 139, 201])}


def parse_qlinks(spec, table, where):
    """A page's Q-Link overrides: {"1": "Cutoff", "5": null, ...}. Keys are Q-Link numbers 1..16, values a parameter
    name or null (the knob does nothing on this page). Q-Links not listed drive the control in their slot."""
    if not isinstance(spec, dict):
        fail(where, 'must be an object like {"1": "Cutoff", "5": null}: Q-Link number -> parameter name, or null for none')
    out = {}
    for k, v in spec.items():
        if not (isinstance(k, str) and k.isdigit() and 1 <= int(k) <= 16):
            fail(where, 'has the key %s; keys are Q-Link numbers "1" to "16"' % json.dumps(k))
        out[int(k)] = None if v is None else table.lookup(v, '%s["%s"]' % (where, k))
    return out


def slot_qlink(row, col):
    """Hardware Q-Link number (1..16) for grid slot (row, col), both 0-based."""
    return 13 + col - 4 * row


# --------------------------------------------------------------------------------------------
# Ordered JSON with duplicate keys
# --------------------------------------------------------------------------------------------
class Obj(list):
    """A JSON object as an ordered list of (key, value) pairs. Keys may repeat."""


def obj(*pairs):
    return Obj(pairs)


def dump_json(value, indent=0):
    """Pretty-print like json.dumps(indent=4) but accepting Obj (ordered, duplicate keys)."""
    pad = " " * indent
    inner_pad = " " * (indent + 4)
    if isinstance(value, Obj):
        if not value:
            return "{}"
        parts = [inner_pad + json.dumps(str(k)) + ": " + dump_json(v, indent + 4) for k, v in value]
        return "{\n" + ",\n".join(parts) + "\n" + pad + "}"
    if isinstance(value, dict):
        return dump_json(Obj(value.items()), indent)
    if isinstance(value, (list, tuple)):
        if not value:
            return "[]"
        parts = [inner_pad + dump_json(v, indent + 4) for v in value]
        return "[\n" + ",\n".join(parts) + "\n" + pad + "]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    return json.dumps(value, ensure_ascii=False)


# --------------------------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------------------------
class UiError(Exception):
    """A problem in ui.json / params.json, with a message aimed at whoever edits ui.json."""


def fail(where, msg, *hints):
    text = "ERROR in %s: %s" % (where, msg) if where else "ERROR: " + msg
    for h in hints:
        if h:
            text += "\n  " + h
    raise UiError(text)


# --------------------------------------------------------------------------------------------
# params.json
# --------------------------------------------------------------------------------------------
class Param:
    def __init__(self, index, name, kind, choices, default=None, display=""):
        self.index = index
        self.name = name
        self.kind = kind
        self.choices = choices  # list of labels for choice/bool kinds, else None
        self.default = default  # normalised default (0..1) when known
        self.display = display  # display text at the default value
        self.automatable = True  # False for display-only parameters (plotters, meters)

    @property
    def looks_bipolar(self):
        """A continuous parameter whose default sits at the centre and reads as zero ("0", "0.0 dB", "+0 st")."""
        if self.is_discrete or not isinstance(self.default, (int, float)):
            return False
        return abs(self.default - 0.5) <= 0.01 and bool(BIPOLAR_ZERO_RE.match(self.display.strip()))

    @property
    def handle(self):
        return "Parameter %d" % self.index

    @property
    def is_discrete(self):
        return self.kind in ("choice", "bool")


def load_params(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        fail(None, "cannot read params.json: %s" % e,
             "params.json is produced by the build (host_sim <native lib> dump). Run tools/build.py first.")
    except ValueError as e:
        fail(path, "not valid JSON (%s)" % e)
    if not isinstance(data, dict) or not isinstance(data.get("params"), list):
        fail(path, 'expected an object with a "params" array (as written by host_sim dump).')
    params = []
    for i, p in enumerate(data["params"]):
        if not isinstance(p, dict) or "name" not in p:
            fail(path, "params[%d] is not an object with a \"name\"" % i)
        index = p.get("index", i)
        if not isinstance(index, int):
            fail(path, "params[%d].index must be an integer" % i)
        kind = p.get("kind") or "float"
        choices = p.get("choices")
        if kind == "bool":
            if not (isinstance(choices, list) and len(choices) == 2):
                choices = ["Off", "On"]
        elif kind == "choice":
            if not (isinstance(choices, list) and len(choices) >= 1):
                fail(path, 'params[%d] ("%s") has kind "choice" but no "choices" list' % (i, p["name"]))
        else:
            choices = None
        default = p.get("default")
        params.append(Param(index, str(p["name"]), kind, [str(c) for c in choices] if choices else None,
                            default if isinstance(default, (int, float)) and not isinstance(default, bool) else None,
                            str(p.get("display", ""))))
        params[-1].automatable = p.get("automatable", True) is not False
    if not params:
        fail(path, "the plugin reports no parameters; there is nothing to lay out.",
             "Add parameters with addParam() in the plugin source, or use --no-ui in build.py.")
    return params


class ParamTable:
    def __init__(self, params):
        self.params = params
        self.by_name = {}
        self.by_lower = {}
        for p in params:
            self.by_name.setdefault(p.name, p)
            self.by_lower.setdefault(p.name.lower(), p)

    def lookup(self, name, where):
        if not isinstance(name, str):
            fail(where, '"param" must be a parameter name (a string), got %s' % json.dumps(name))
        p = self.by_name.get(name)
        if p is None:
            p = self.by_lower.get(name.lower())
        if p is None:
            names = [q.name for q in self.params]
            close = difflib.get_close_matches(name, names, n=3, cutoff=0.5)
            fail(where, 'unknown parameter "%s".' % name,
                 "Available parameter names (from params.json): " + ", ".join('"%s"' % n for n in names),
                 ("Did you mean " + " or ".join('"%s"' % c for c in close) + "?") if close else "")
        return p


# --------------------------------------------------------------------------------------------
# ui.json
# --------------------------------------------------------------------------------------------
class Control:
    def __init__(self, widget, param=None, text=None, visible=None, overlay="knob", polarity="auto", plot_range=None, label=None):
        self.widget = widget      # slider | knob | fader | switch | empty | text | plotter
        self.param = param        # Param or None
        self.text = text          # for widget "text"
        self.visible = visible    # None or (Param, choiceIndex)
        self.overlay = overlay    # knob | menu
        self.polarity = polarity  # auto | unipolar | bipolar (knob and fader only)
        self.plot_range = plot_range  # plotter only: (min, max) of the value it draws
        self.label = label        # on-screen name, or None to show the parameter's name
        self.label_style = None   # {font, style, size, align, dx, dy} for the name label, or None for the default
        self.element = None       # name of a ui-library element, or None for the kit
        self.element_def = None   # its validated element.json (ui_library.load_element)
        self.element_assets = None  # its rendered assets: key -> (file, frames, (w, h))
        self.ticks_asset = None     # (file, w, h) of the ticks picture once it is copied into Plugin Skins/
        self.knob_size = 77         # the knob's diameter in px, for placing ticks round it

    @property
    def bipolar(self):
        if self.polarity == "bipolar":
            return True
        if self.polarity == "unipolar":
            return False
        return self.param is not None and self.param.looks_bipolar

    @property
    def definition(self):
        """Name of the reusable component definition this control instantiates."""
        if self.widget == "plotter":
            return None   # drawn directly in the tab, not from a reusable definition
        if self.widget == "switch":
            return "toggle" if self.param.kind == "bool" or len(self.param.choices) == 1 else "radio%d" % len(self.param.choices)
        if self.widget == "button":
            return "button"
        pol = "Bi" if self.bipolar else "Uni"
        base = {"slider": "sliderWithFocus", "knob": "knob" + pol, "fader": "fader" + pol}[self.widget]
        return base + ("Menu" if self.overlay == "menu" else "")

    @property
    def definition_key(self):
        """Component definition name. A custom label needs its own definition, because the name
        is drawn inside it. The part before '@' is the base definition (see build_tui)."""
        key = self.definition
        if self.element and self.widget != "text":
            key += "#" + self.element   # a library element draws its own pictures
        if self.label is not None and self.widget != "slider":
            key += "@" + self.label
        if self.label_style:
            # A styled name needs its own definition too; '~' and a short hash of the style mark it (see build_tui).
            key += "~" + hashlib.sha1(json.dumps(self.label_style, sort_keys=True).encode("utf-8")).hexdigest()[:8]
        return key

    @property
    def tui_key(self):
        """The definition's name as written to TUI.json (see tui_key)."""
        return tui_key(self.definition_key)


def tui_key(name):
    """A definition name safe for the MPC: letters and digits only. definition_key marks an element, a label and
    a label style with '#', '@' and '~' (build_tui reads them back); a skin whose definitions were named that way
    showed a blank screen on an MPC One, so those names are written as the base name plus a short hash."""
    if name.isalnum() and name.isascii():
        return name
    base = name.split("@")[0].split("~")[0].partition("#")[0]
    return base + hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]


class Page:
    def __init__(self, name, controls, background=None, art=None, background_tile=False, background_scale=100, groups=None,
                 qlinks=None, qlink_banks="columns"):
        self.name = name
        self.qlink_banks = qlink_banks  # "columns" (bank 1 = left column) or "rows" (bank 1 = top row)
        self.controls = controls  # list of Control, at most 16, in reading order
        self.qlinks = qlinks or {}  # Q-Link number (1..16) -> Param, or None for no parameter; others follow the slots
        self.background_tile = background_tile   # True: repeat the background picture as tiles
        self.background_scale = background_scale  # tile size as a percentage of the picture's own size
        self.background = background  # file name of a full-tab image, or None
        self.art = art or []          # [(file, x, y, w, h)] decorations, drawn under the controls
        self.groups = groups or []    # outlines around related controls, drawn under the controls


def check_keys(where, d, allowed):
    for k in d:
        if k not in allowed:
            close = difflib.get_close_matches(k, allowed, n=1)
            fail(where, 'unknown key "%s".' % k,
                 "Allowed keys: " + ", ".join('"%s"' % a for a in allowed),
                 ('Did you mean "%s"?' % close[0]) if close else "")


def parse_visible_when(spec, table, where):
    if not isinstance(spec, dict):
        fail(where, '"visibleWhen" must be an object like {"param": "Mode", "choice": "Dual"} or {"param": "Mode", "index": 1}')
    check_keys(where, spec, ("param", "choice", "index"))
    if "param" not in spec:
        fail(where, '"visibleWhen" needs a "param" (the name of the choice/bool parameter it depends on)')
    p = table.lookup(spec["param"], where)
    if not p.is_discrete:
        fail(where, '"visibleWhen" parameter "%s" is kind "%s"; it must be a choice or bool parameter.' % (p.name, p.kind),
             "Only discrete parameters can drive IndexedEnabling. Choice/bool parameters: "
             + (", ".join('"%s"' % q.name for q in table.params if q.is_discrete) or "(none)"))
    if ("choice" in spec) == ("index" in spec):
        fail(where, '"visibleWhen" needs exactly one of "choice" (a label) or "index" (0-based number)')
    if "index" in spec:
        idx = spec["index"]
        if not isinstance(idx, int) or isinstance(idx, bool) or not (0 <= idx < len(p.choices)):
            fail(where, '"visibleWhen".index must be an integer in 0..%d for "%s" (choices: %s)'
                 % (len(p.choices) - 1, p.name, ", ".join('"%s"' % c for c in p.choices)))
        return (p, idx)
    label = spec["choice"]
    if not isinstance(label, str):
        fail(where, '"visibleWhen".choice must be a string label')
    if label in p.choices:
        return (p, p.choices.index(label))
    lowered = [c.lower() for c in p.choices]
    if label.lower() in lowered:
        return (p, lowered.index(label.lower()))
    fail(where, 'parameter "%s" has no choice "%s".' % (p.name, label),
         "Its choices are: " + ", ".join('"%s"' % c for c in p.choices))


def parse_control(spec, table, where):
    control = parse_control_body(spec, table, where)
    if isinstance(spec, dict) and "element" in spec:
        element = spec["element"]
        if not isinstance(element, str) or not element:
            fail(where, '"element" must be the name of an element in ui-library/, got %s' % json.dumps(element))
        if control.widget not in ELEMENT_FOR_WIDGET:
            fail(where, '"element" applies to knob, fader, switch, button and text controls (this one is "%s")' % control.widget)
        control.element = element
    if isinstance(spec, dict) and "label" in spec:
        label = spec["label"]
        if not isinstance(label, str):
            fail(where, '"label" must be a string (the name shown on the MPC; "" hides the name), got %s' % json.dumps(label))
        if len(label.strip()) > LABEL_MAX:
            fail(where, '"label" is %d characters; the most is %d.' % (len(label.strip()), LABEL_MAX),
                 'Shorten it, e.g. "label": "Cutoff".')
        if control.widget in ("empty", "text"):
            fail(where, '"label" does not apply to a "%s" control.' % control.widget)
        control.label = label.strip()   # the slider widget draws the parameter's own name, so it ignores this
    if isinstance(spec, dict) and "labelStyle" in spec:
        control.label_style = parse_label_style(spec["labelStyle"], control.widget, where)
    return control


def parse_label_style(ls, widget, where):
    """The name label's font, style, size (px), align and move (dx, dy in px), checked. None when it sets nothing."""
    if widget not in LABEL_STYLE_WIDGETS:
        fail(where, '"labelStyle" applies to knob, fader, switch and button controls (this one is "%s").' % widget,
             "The slider bar draws the parameter's own name, and text controls take their style from a label element.")
    if not isinstance(ls, dict):
        fail(where, '"labelStyle" must be an object like {"font": "Roboto", "style": "Bold", "size": 24, "dy": 6}')
    check_keys(where, ls, LABEL_STYLE_KEYS)
    out = {}
    if "font" in ls:
        if ls["font"] not in FONTS:
            fail(where, '"labelStyle".font must be one of %s, got %s.' % (", ".join('"%s"' % f for f in FONTS), json.dumps(ls["font"])),
                 "The MPC has only these fonts; another name would silently draw as Titillium Web.")
        out["font"] = ls["font"]
    if "style" in ls:
        if ls["style"] not in FONT_STYLES:
            fail(where, '"labelStyle".style must be one of %s, got %s.' % (", ".join(FONT_STYLES), json.dumps(ls["style"])))
        out["style"] = ls["style"]
    if "size" in ls:
        v = ls["size"]
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not 8 <= v <= 60:
            fail(where, '"labelStyle".size must be a number of px from 8 to 60, got %s.' % json.dumps(v))
        out["size"] = v
    if "align" in ls:
        if ls["align"] not in LABEL_JUSTIFY:
            fail(where, '"labelStyle".align must be "left", "centre" or "right", got %s.' % json.dumps(ls["align"]))
        out["align"] = ls["align"]
    for k, lim in (("dx", SLOT_W), ("dy", SLOT_H)):
        if k in ls:
            v = ls[k]
            if not isinstance(v, int) or isinstance(v, bool) or not -lim <= v <= lim:
                fail(where, '"labelStyle".%s must be a whole number of px from %d to %d, got %s.' % (k, -lim, lim, json.dumps(v)))
            if v:
                out[k] = v
    return out or None


def _get(o, key):
    return next(v for k, v in o if k == key)


def _set(o, key, value):
    for i, (k, _) in enumerate(o):
        if k == key:
            o[i] = (key, value)
            return
    o.append((key, value))


def restyle_name(comp, ls):
    """Applies a control's labelStyle to the name label inside its component definition: font, style, size and
    alignment, and a move by (dx, dy) px. The label's box stays inside the slot, and grows to fit a larger font.
    Returns False when the definition has no name label."""
    for child in _get(comp, "componentsData"):
        cd = _get(child, "componentData")
        if _get(cd, "name") != "name":
            continue
        ts = _get(_get(cd, "data"), "textStyle")
        font = _get(ts, "font")
        if "font" in ls:
            _set(font, "name", ls["font"])
        if "style" in ls:
            _set(font, "style", ls["style"])
        if "size" in ls:
            _set(font, "height", float(ls["size"]))
        if "align" in ls:
            _set(ts, "justification", LABEL_JUSTIFY[ls["align"]])
        b = _get(child, "bounds")
        x, y, w, h = (int(v) for v in _get(b, "bounds").split())
        if "size" in ls:
            h = min(SLOT_H, max(h, int(math.ceil(ls["size"] * 1.3))))
        x = max(0, min(SLOT_W - w, x + ls.get("dx", 0)))
        y = max(0, min(SLOT_H - h, y + ls.get("dy", 0)))
        _set(b, "bounds", "%d %d %d %d" % (x, y, w, h))
        return True
    return False


def parse_control_body(spec, table, where):
    if isinstance(spec, str):
        if spec.strip().lower() == "empty" and spec not in table.by_name:
            return Control("empty")
        return Control("slider", param=table.lookup(spec, where))
    if not isinstance(spec, dict):
        fail(where, "each control must be a parameter name (string) or an object, got %s" % json.dumps(spec))
    check_keys(where, spec, CONTROL_KEYS)
    widget = spec.get("widget", "slider")
    if widget not in WIDGETS:
        fail(where, '"widget" must be one of %s, got %s' % (", ".join('"%s"' % w for w in WIDGETS), json.dumps(widget)))
    overlay = spec.get("overlay", "menu" if widget in ("switch", "button") else "knob")
    if overlay not in OVERLAYS:
        fail(where, '"overlay" must be "knob" or "menu", got %s' % json.dumps(overlay))
    polarity = spec.get("polarity", "auto")
    if polarity not in POLARITIES:
        fail(where, '"polarity" must be one of %s, got %s' % (", ".join('"%s"' % p for p in POLARITIES), json.dumps(polarity)))
    if "polarity" in spec and widget not in ("knob", "fader"):
        fail(where, '"polarity" only applies to "knob" and "fader" widgets (this control is a "%s")' % widget)
    visible = parse_visible_when(spec["visibleWhen"], table, where) if "visibleWhen" in spec else None
    if widget == "empty":
        return Control("empty", visible=visible)
    if widget != "plotter" and ("min" in spec or "max" in spec):
        fail(where, '"min" and "max" only apply to the "plotter" widget (this control is a "%s")' % widget)
    if widget == "text":
        text = spec.get("text")
        if not isinstance(text, str):
            fail(where, '"widget": "text" needs a "text" string (the heading to show in this slot)')
        return Control("text", text=text, visible=visible)
    if "param" not in spec:
        fail(where, 'control needs a "param" (parameter name); use "widget": "empty" for a blank slot')
    param = table.lookup(spec["param"], where)
    if widget == "plotter":
        if param.is_discrete:
            fail(where, '"plotter" draws a continuous value; "%s" is kind "%s".' % (param.name, param.kind),
                 'Use "switch" for on/off or choice parameters.')
        lo, hi = spec.get("min", 0), spec.get("max", 1)
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (lo, hi)) or hi <= lo:
            fail(where, '"plotter" needs numeric "min" < "max" (the range of the value it draws), got min %s, max %s'
                 % (json.dumps(lo), json.dumps(hi)),
                 'Use the parameter\'s real range, e.g. {"param": "Out Level", "widget": "plotter", "min": 0, "max": 100}.')
        if param.automatable:
            print('gen_ui: NOTE: "%s" is automatable. A plotter should show a display-only parameter (automatable = false), '
                  'so the host does not treat it as a control.' % param.name)
        return Control("plotter", param=param, visible=visible, plot_range=(float(lo), float(hi)))
    if widget == "button":
        if param.kind != "bool":
            fail(where, '"button" needs a bool parameter; "%s" is kind "%s".' % (param.name, param.kind),
                 'Use "switch" for a choice parameter, or make the parameter a boolParam() in the code.')
    if widget == "switch":
        if not param.is_discrete:
            fail(where, '"switch" needs a bool or choice parameter; "%s" is kind "%s".' % (param.name, param.kind),
                 'Use "knob" or "fader" for continuous parameters, or make the parameter a choiceParam()/boolParam() in the code.')
        if len(param.choices) > MAX_SWITCH_CHOICES:
            fail(where, '"switch" fits at most %d choices in a slot; "%s" has %d.' % (MAX_SWITCH_CHOICES, param.name, len(param.choices)),
                 'Use {"param": "%s", "widget": "slider", "overlay": "menu"} instead (a bar that steps through the choices with a menu on double-tap).' % param.name)
    return Control(widget, param=param, visible=visible, overlay=overlay, polarity=polarity)


def load_ui(path, table):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        fail(None, "cannot read ui.json: %s" % e)
    except ValueError as e:
        fail(path, "not valid JSON (%s)" % e, "Check for trailing commas or comments; ui.json must be strict JSON.")
    if not isinstance(data, dict):
        fail(path, 'top level must be an object like {"pages": [...]}')
    check_keys(path, data, UI_KEYS)
    pages_spec = data.get("pages")
    if not isinstance(pages_spec, list) or not pages_spec:
        fail(path, '"pages" must be a non-empty array of pages ({"name": "...", "controls": [...]})')
    if len(pages_spec) > MAX_PAGES:
        fail(path, "%d pages given; the MPC supports at most %d tabs." % (len(pages_spec), MAX_PAGES))

    style = dict(DEFAULT_STYLE)
    if "style" in data:
        if not isinstance(data["style"], dict):
            fail(path + ' "style"', "must be an object of ARGB hex colours")
        check_keys(path + ' "style"', data["style"], tuple(DEFAULT_STYLE))
        for k, v in data["style"].items():
            if not (isinstance(v, str) and len(v) == 8 and all(ch in "0123456789abcdefABCDEF" for ch in v)):
                fail(path + ' "style"', '"%s" must be an 8-digit ARGB hex string like "ff1e1d1e", got %s' % (k, json.dumps(v)))
            style[k] = v.lower()

    kit = parse_kit(data.get("kit"), path, "accent" in data.get("style", {}), style)

    knob_image = data.get("knobImage")
    if knob_image is not None and (not isinstance(knob_image, str) or not knob_image.strip()):
        fail(path, '"knobImage" must be a file name (a PNG film strip in the project\'s assets/ folder, which build.py copies into Plugin Skins/)')
    frames = data.get("knobFrames", 127)
    if not isinstance(frames, int) or isinstance(frames, bool) or frames < 2:
        fail(path, '"knobFrames" must be an integer >= 2 (number of frames in the film strip), got %s' % json.dumps(frames))

    pages = []
    for pi, pspec in enumerate(pages_spec):
        where = "%s pages[%d]" % (path, pi)
        if not isinstance(pspec, dict):
            fail(where, 'each page must be an object like {"name": "OSC", "controls": [...]}')
        check_keys(where, pspec, PAGE_KEYS)
        name = pspec.get("name", str(pi + 1))
        if not isinstance(name, str) or not name:
            fail(where, '"name" must be a non-empty string (the tab label)')
        if len(name) > 8:
            print('gen_ui: WARNING: %s name "%s" is longer than 8 characters and may be truncated on the tab.' % (where, name))
        controls_spec = pspec.get("controls", [])
        if not isinstance(controls_spec, list):
            fail(where, '"controls" must be an array')
        if len(controls_spec) > MAX_CONTROLS_PER_PAGE:
            fail(where, "has %d controls but a page is a 4 x 4 grid with at most %d slots."
                 % (len(controls_spec), MAX_CONTROLS_PER_PAGE),
                 "Split the controls over more pages (add another entry to \"pages\").")
        controls = [parse_control(c, table, "%s.controls[%d]" % (where, ci)) for ci, c in enumerate(controls_spec)]
        background = parse_image_name(pspec.get("background"), where + ' "background"')
        bg_tile = pspec.get("backgroundTile", False)
        if not isinstance(bg_tile, bool):
            fail(where, '"backgroundTile" must be true or false')
        bg_scale = parse_scale(pspec.get("backgroundScale", 100), where + ' "backgroundScale"')
        art = [parse_art(a, where + ".art[%d]" % ai) for ai, a in enumerate(pspec.get("art", []))]
        groups = [parse_group(g, where + ".groups[%d]" % gi) for gi, g in enumerate(pspec.get("groups", []))]
        qlinks = parse_qlinks(pspec.get("qlinks", {}), table, where + ' "qlinks"')
        qlink_banks = pspec.get("qlinkBanks", "columns")
        if qlink_banks not in QLINK_BANKS:
            fail(where, '"qlinkBanks" must be "columns" or "rows", got %s' % json.dumps(qlink_banks),
                 'It says how a model with 4 Q-Links (MPC One, Live) steps through the page: "rows" makes bank 1 the top row.')
        pages.append(Page(name, controls, background, art, bg_tile, bg_scale, groups, qlinks, qlink_banks))

    uses_kit = any(c.widget in KIT_WIDGETS for pg in pages for c in pg.controls)
    if kit is None and uses_kit:
        kit = {"theme": "mpc-red", "accent": style["accent"] if "accent" in data.get("style", {}) else None}
    elif kit is not None and not uses_kit:
        print('gen_ui: NOTE: "kit" is set but no control uses "knob", "fader" or "switch"; nothing from the kit is drawn.')
    return pages, style, knob_image, frames, kit


def parse_image_name(value, where):
    """A picture file name from the project's assets/ folder (copied into Plugin Skins/ by build.py)."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or "/" in value or "\\" in value:
        fail(where, 'must be a file name in the project\'s assets/ folder (no folders), got %s' % json.dumps(value),
             'Put the PNG or JPEG in assets/ and write just its name, for example "bg.png".')
    if not value.lower().endswith((".png", ".jpg", ".jpeg")):
        fail(where, 'must be a PNG or JPEG, got %s' % json.dumps(value))
    return value


def parse_scale(value, where):
    """Tile scale as a whole percentage of the picture's own size (1 to 400)."""
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 400:
        fail(where, 'must be a whole percentage from 1 to 400, got %s' % json.dumps(value),
             '100 draws each tile at the picture\'s own size; 50 halves it.')
    return value


def parse_art(spec, where):
    """One picture laid over the tab: {"image": "logo.png", "x": 900, "y": 20, "w": 300, "h": 80} (tab pixels).
    Optional "tile": true repeats it inside its box at "scale" percent of its own size."""
    if not isinstance(spec, dict):
        fail(where, 'must be an object like {"image": "logo.png", "x": 0, "y": 0, "w": 200, "h": 100}')
    check_keys(where, spec, ART_KEYS)
    for k in ("image", "x", "y", "w", "h"):
        if k not in spec:
            fail(where, 'is missing "%s"' % k)
    image = parse_image_name(spec["image"], where + ' "image"')
    x, y, w, h = (spec[k] for k in ("x", "y", "w", "h"))
    for k, v in (("x", x), ("y", y), ("w", w), ("h", h)):
        if not isinstance(v, int) or isinstance(v, bool):
            fail(where, '"%s" must be a whole number of pixels, got %s' % (k, json.dumps(v)))
    if w < 1 or h < 1 or x < 0 or y < 0 or x + w > 1280 or y + h > 628:
        fail(where, "must lie inside the 1280 x 628 tab area (x 0-1279, y 0-627, w and h at least 1)")
    tile = spec.get("tile", False)
    if not isinstance(tile, bool):
        fail(where, '"tile" must be true or false')
    scale = parse_scale(spec.get("scale", 100), where + ' "scale"')
    return {"image": image, "x": x, "y": y, "w": w, "h": h, "tile": tile, "scale": scale, "cells": None}


def parse_group(spec, where):
    """A labelled outline around a set of controls, in tab pixels:
    {"x": 20, "y": 9, "w": 300, "h": 180, "label": "Filter"}. The label is optional."""
    if not isinstance(spec, dict):
        fail(where, 'must be an object like {"x": 20, "y": 9, "w": 300, "h": 180, "label": "Filter"}')
    check_keys(where, spec, GROUP_KEYS)
    for k in ("x", "y", "w", "h"):
        if k not in spec:
            fail(where, 'is missing "%s"' % k)
        if not isinstance(spec[k], int) or isinstance(spec[k], bool):
            fail(where, '"%s" must be a whole number of pixels, got %s' % (k, json.dumps(spec[k])))
    x, y, w, h = (spec[k] for k in ("x", "y", "w", "h"))
    if w < 1 or h < 1 or x < 0 or y < 0 or x + w > 1280 or y + h > 628:
        fail(where, "must lie inside the 1280 x 628 tab area (x 0-1279, y 0-627, w and h at least 1)")
    label = spec.get("label", "")
    if not isinstance(label, str):
        fail(where, '"label" must be a string')
    if len(label) > GROUP_LABEL_MAX:
        fail(where, '"label" is %d characters; the most is %d.' % (len(label), GROUP_LABEL_MAX))
    return {"x": x, "y": y, "w": w, "h": h, "label": label.strip(), "image": None}


def write_group_png(path, w, h, argb):
    """A rounded-rectangle outline as an RGBA PNG (no fill). Pure Python, so no image library is needed."""
    import zlib
    a0, r0, g0, b0 = (int(argb[i:i + 2], 16) for i in (0, 2, 4, 6))
    rad, st = float(GROUP_RADIUS), GROUP_STROKE

    def inside(px, py, x0, y0, x1, y1, r):
        # Rounded rectangle test for a pixel centre: clamp to the inner rectangle, then check the distance.
        qx = min(max(px, x0 + r), x1 - r)
        qy = min(max(py, y0 + r), y1 - r)
        return (px - qx) ** 2 + (py - qy) ** 2 <= r * r

    rows = []
    for yy in range(h):
        row = bytearray([0])   # PNG filter type 0
        py = yy + 0.5
        for xx in range(w):
            px = xx + 0.5
            on = inside(px, py, 0, 0, w, h, rad) and not inside(px, py, st, st, w - st, h - st, max(0.0, rad - st))
            row += bytes((r0, g0, b0, 255 if on else 0)) if on else b"\x00\x00\x00\x00"
        rows.append(bytes(row))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def image_size(path):
    """(width, height) of a PNG or JPEG read from its header, or None if it cannot be read."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        return struct.unpack(">II", data[16:24])
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return (w, h)
            i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
    return None


def tile_cells(x, y, w, h, tw, th):
    """Rectangles covering x, y, w, h with tw x th tiles. Edge tiles are shrunk to fit the box."""
    return [(x + tx, y + ty, min(tw, w - tx), min(th, h - ty))
            for ty in range(0, h, th) for tx in range(0, w, tw)]


def layout_pictures(pages, assets_dir):
    """Work out the rectangles each picture is drawn in (one per tile for tiled pictures)."""
    for pg in pages:
        if pg.background:
            cells = [(0, 0, 1280, 628)]
            if pg.background_tile:
                size = image_size(os.path.join(assets_dir, pg.background)) if assets_dir else None
                if size is None:
                    print('gen_ui: WARNING: cannot read the size of "%s" on page "%s"; it is drawn untiled.' % (pg.background, pg.name))
                else:
                    tw = max(1, round(size[0] * pg.background_scale / 100))
                    th = max(1, round(size[1] * pg.background_scale / 100))
                    cells = tile_cells(0, 0, 1280, 628, tw, th)
            pg.background_cells = cells
        for pic in pg.art:
            cells = [(pic["x"], pic["y"], pic["w"], pic["h"])]
            if pic["tile"]:
                size = image_size(os.path.join(assets_dir, pic["image"])) if assets_dir else None
                if size is None:
                    print('gen_ui: WARNING: cannot read the size of "%s" on page "%s"; it is drawn untiled.' % (pic["image"], pg.name))
                else:
                    tw = max(1, round(size[0] * pic["scale"] / 100))
                    th = max(1, round(size[1] * pic["scale"] / 100))
                    cells = tile_cells(pic["x"], pic["y"], pic["w"], pic["h"], tw, th)
            pic["cells"] = cells
        for pic in pg.art:
            if len(pic["cells"]) > MAX_TILES:
                fail(None, 'picture "%s" on page "%s" would need %d tiles; the limit is %d.'
                     % (pic["image"], pg.name, len(pic["cells"]), MAX_TILES),
                     "Use a larger scale (a smaller number of tiles) or a smaller box.")
        if len(getattr(pg, "background_cells", [])) > MAX_TILES:
            fail(None, 'the background of page "%s" would need %d tiles; the limit is %d.'
                 % (pg.name, len(pg.background_cells), MAX_TILES), "Use a larger backgroundScale.")


def parse_kit(spec, path, accent_in_style, style):
    """Returns None or {"theme": name, "accent": ARGB-or-None}. Also aligns the focus-ring accent with the kit."""
    if spec is None:
        return None
    try:
        import make_ui_kit
    except ImportError:
        fail(path, '"kit" needs tools/make_ui_kit.py next to gen_ui.py')
    where = path + ' "kit"'
    if isinstance(spec, str):
        spec = {"theme": spec}
    if not isinstance(spec, dict):
        fail(where, 'must be a theme name like "mpc-red" or an object like {"theme": "amber"} / {"accent": "ff19c6e0"}')
    check_keys(where, spec, KIT_KEYS)
    theme = spec.get("theme", "mpc-red")
    if theme not in make_ui_kit.THEMES:
        fail(where, 'unknown theme %s.' % json.dumps(theme), "Themes: " + ", ".join('"%s"' % t for t in sorted(make_ui_kit.THEMES)))
    accent = spec.get("accent")
    if accent is not None:
        if not (isinstance(accent, str) and len(accent) == 8 and all(ch in "0123456789abcdefABCDEF" for ch in accent)):
            fail(where, '"accent" must be an 8-digit ARGB hex string like "ff19c6e0", got %s' % json.dumps(accent))
        accent = accent.lower()
    elif accent_in_style:
        accent = style["accent"]
    if not accent_in_style:
        # The focus ring follows the kit colour unless style.accent was set explicitly.
        style["accent"] = accent or make_ui_kit.THEMES[theme].lower()
    return {"theme": theme, "accent": accent}


def auto_pages(params):
    pages = []
    for start in range(0, len(params), MAX_CONTROLS_PER_PAGE):
        chunk = params[start:start + MAX_CONTROLS_PER_PAGE]
        pages.append(Page(str(len(pages) + 1), [Control("slider", param=p) for p in chunk]))
    if len(pages) > MAX_PAGES:
        fail(None, "the plugin has %d parameters, which needs %d pages; the MPC supports at most %d tabs."
             % (len(params), len(pages), MAX_PAGES), "Write a ui.json that lays out only the parameters you need.")
    return pages


# --------------------------------------------------------------------------------------------
# TUI.json building blocks (shapes mirror the firmware's generic skins)
# --------------------------------------------------------------------------------------------
def action(on_action, handler, handle_name, additional=""):
    return obj(("version", 1), ("onAction", on_action), ("handler", handler),
               ("handleName", handle_name), ("additionalData", additional))


def background_data(colour):
    def side():
        return obj(("version", 1), ("colour", colour), ("image", ""))
    return obj(("version", 1), ("focussed", side()), ("unfocussed", side()))


def component_definition(actions, children, bg_colour, ignore_mouse=False):
    return obj(("version", 2), ("actions", actions), ("backgroundData", background_data(bg_colour)),
               ("ignoreMousePresses", ignore_mouse), ("disableCoarseDataWheel", False),
               ("componentsData", children))


def entry(name, type_name, data, bounds, accepts_focus, show_invalid, when_visible, remap=(), invalidating=None):
    bounds_pairs = [("version", 2 if invalidating else 1), ("acceptsHWFocus", accepts_focus),
                    ("showWhenDataModelInvalid", show_invalid), ("whenVisible", when_visible),
                    ("boundsType", "Absolute"), ("bounds", bounds)]
    if invalidating:
        bounds_pairs.append(("additionalInvalidatingHandles", list(invalidating)))
    return obj(("version", 2),
               ("componentData", obj(("version", 1), ("name", name), ("type", type_name), ("data", data))),
               ("handle remapping", obj(("version", 1), ("map", [obj(("key", k), ("value", v)) for k, v in remap]))),
               ("bounds", Obj(bounds_pairs)))


def slider_data():
    return obj(("version", 1), ("handleName", "Data"))


def knob_filmstrip_data(image, frames, drag=None):
    pairs = [("version", 3 if drag else 2), ("knobType", "FilmStrip"), ("filmStrip", image), ("numFrames", frames),
             ("invert", False)]
    if drag:
        pairs.append(("dragOrientation", drag))
    pairs.append(("handleName", "Data"))
    return Obj(pairs)


def button_data(on_image, off_image, button_id, group_size):
    return obj(("version", 2), ("onImage", on_image), ("offImage", off_image), ("buttonId", button_id),
               ("numButtonsInGroup", group_size), ("handleName", "Data"), ("gestureBehaviour", "Instant"))


def label_data(label_type, colour, height=30.0, justification="left", text=None):
    """A text label: "Name" or "Value" read the parameter, "Text" draws the fixed text. handleName is always
    written (the MPC requires it, even for "Text"), and text only goes with type "Text" (docs/ui-reference.md)."""
    if (text is not None) != (label_type == "Text"):
        fail(None, "internal error: a %s label %s fixed text" % (label_type, "with" if text is not None else "without"))
    pairs = [("version", 1),
             ("textStyle", obj(("version", 1),
                               ("font", obj(("version", 1), ("name", FONT_NAME), ("style", "Regular"), ("height", float(height)))),
                               ("colour", colour), ("justification", justification), ("case", "Original"))),
             ("type", label_type),
             ("handleName", "Data")]
    if text is not None:
        pairs.append(("text", text))
    return Obj(pairs)


def name_label(style, height, justification, name_text, colour_key="muted"):
    """The parameter-name label of a control: the parameter's name, or the user's label as fixed text. A label
    of type "Name" with a text key and no handleName made the MPC One show a blank screen for the whole skin."""
    if name_text is None:
        return label_data("Name", style[colour_key], height, justification)
    return label_data("Text", style[colour_key], height, justification, name_text)


def focus_data(accent):
    return obj(("version", 1), ("backgroundColour", "19ffffff"), ("outlineColour", accent),
               ("backgroundInset", 4.0), ("outlineThickness", 1.0))


def focus_lost_action():
    return action("Focus Lost", "Focus Lost", "Focus Lost", "")


def knob_overlay_data(bipolar=False):
    return obj(("version", 2), ("version", 1), ("actions", [focus_lost_action()]),
               ("overlayType", "Knob With Header"), ("scaleType", "Linear"),
               ("polarityType", "Bipolar" if bipolar else "Unipolar"),
               ("showMinusSign", True), ("handleName", "Data"))


def menu_overlay_data():
    return obj(("version", 1), ("version", 1), ("actions", [focus_lost_action()]),
               ("withNumbers", False), ("handleName", "Data"))


def control_actions(overlay_name, double_click=True):
    acts = [action("Mouse Down", "Q-Link", "Data", "")]
    if double_click:
        acts.append(action("Double Click", "Show Overlay", "Data", overlay_name))
    acts.append(action("Enter Pressed", "Show Overlay", "Data", overlay_name))
    return acts


def slot_bounds_str():
    return "0 0 %d %d" % (SLOT_W, SLOT_H)


def focus_child(style):
    return entry("focus", "Focus", focus_data(style["accent"]), slot_bounds_str(), "No", "Show", "WhenFocussed")


def slider_component(style, overlay_name):
    children = [focus_child(style),
                entry("slider", "Slider", slider_data(), "15 15 248 77", "No", "Show", "Always")]
    return component_definition(control_actions(overlay_name), children, "00000000")


def knob_stacked(style, knob, size, name_text=None, show_value=True, value_size=22.0, value_colour=None):
    """Knob layout: the name is centred above the knob, and the value is centred on the knob's middle
    (unless the element sets "showValue": false). The knob sits at the bottom of the slot, centred horizontally."""
    band = SLOT_H - size                     # height left above the knob for the name
    x = (SLOT_W - size) // 2
    name_font = max(14, min(26, round(band * 0.92)))
    parts = [entry("knob", "Knob", knob, "%d %d %d %d" % (x, band, size, size), "No", "Show", "Always"),
             entry("name", "Label", name_label(style, float(name_font), "horizontallyCentred verticallyCentred", name_text),
                   "0 0 %d %d" % (SLOT_W, band), "No", "Show", "Always")]
    if show_value:
        # The value's box is centred on the knob: 32 px tall, taller for a large valueSize so it is not cut off
        # (the editors use the same box, ui_elements.js valueBoxH).
        vh = max(32, int(math.ceil(value_size * 1.2)))
        parts.append(entry("value", "Label", label_data("Value", value_colour or style["text"], value_size, "horizontallyCentred verticallyCentred"),
                           "%d %d %d %d" % (x, band + size // 2 - vh // 2, size, vh), "No", "Show", "Always"))
    return parts


def knob_component(style, overlay_name, knob_image, frames, bipolar=False, name_text=None, show_value=True,
                   value_size=22.0, value_colour=None):
    """A knob slot. knob_image: (file, frames, size) for a film strip, or None for the generic knob."""
    if knob_image:
        image, frames, size = knob_image
        knob = knob_filmstrip_data(image, frames)
    else:
        size = 77
        knob = obj(("version", 5), ("knobType", "GenericLegacy"), ("polarity", "BiPolar" if bipolar else "UniPolar"),
                   ("dragOrientation", "Vertical"), ("handleName", "Data"))
    children = [focus_child(style)] + knob_stacked(style, knob, size, name_text, show_value, value_size, value_colour)
    return component_definition(control_actions(overlay_name), children, "00000000")


def fader_component(style, overlay_name, image, frames, name_text=None):
    """A horizontal film-strip fader (248 x 36) under a name / value header. Drawn by the Knob widget with a horizontal drag."""
    children = [focus_child(style),
                entry("name", "Label", name_label(style, 24.0, "left", name_text), "15 8 135 34", "No", "Show", "Always"),
                entry("value", "Label", label_data("Value", style["text"], 26.0, "right"), "150 8 113 34", "No", "Show", "Always"),
                entry("fader", "Knob", knob_filmstrip_data(image, frames, "Horizontal"), "15 54 248 36", "No", "Show", "Always")]
    return component_definition(control_actions(overlay_name), children, "00000000")


def toggle_component(style, overlay_name, name_text=None, on_file="toggle_on.png", off_file="toggle_off.png"):
    """A bool switch: name and value text on the left, a pill toggle (Button widget) on the right."""
    children = [focus_child(style),
                entry("name", "Label", name_label(style, 26.0, "left", name_text), "15 12 170 36", "No", "Show", "Always"),
                entry("value", "Label", label_data("Value", style["text"], 30.0), "15 52 170 42", "No", "Show", "Always"),
                entry("toggle", "Button", button_data(on_file, off_file, 1, 1), "186 20 84 68", "No", "Show", "Always")]
    return component_definition(control_actions(overlay_name, double_click=False), children, "00000000")


def button_component(style, overlay_name, on_image, off_image, w, h, name_text=None):
    """A push button (a bool parameter): name and value text on the left, the button picture on the right,
    centred vertically. The picture is drawn at its own size, so w and h are its pixel size."""
    bx, by = SLOT_W - 8 - w, (SLOT_H - h) // 2
    lw = max(60, bx - 15 - 8)   # the text stops just before the button
    children = [focus_child(style),
                entry("name", "Label", name_label(style, 26.0, "left", name_text), "15 12 %d 36" % lw, "No", "Show", "Always"),
                entry("value", "Label", label_data("Value", style["text"], 30.0), "15 52 %d 42" % lw, "No", "Show", "Always"),
                entry("button", "Button", button_data(on_image, off_image, 1, 1), "%d %d %d %d" % (bx, by, w, h), "No", "Show", "Always")]
    return component_definition(control_actions(overlay_name, double_click=False), children, "00000000")


def radio_component(style, overlay_name, n, name_text=None, files=None):
    """files: (on, off) picture names for each segment size n: {n: (on, off)}; the kit's names by default."""
    """An n-way choice switch: name on top, n segment buttons below (their captions are added by the tab)."""
    width, xs = SEGMENTS[n]
    children = [focus_child(style),
                entry("name", "Label", name_label(style, 24.0, "left", name_text), "15 8 248 34", "No", "Show", "Always")]
    for i, x in enumerate(xs):
        on_file, off_file = files if files else ("seg%d_on.png" % n, "seg%d_off.png" % n)
        children.append(entry("seg %d" % i, "Button", button_data(on_file, off_file, i, n),
                              "%d 54 %d 40" % (x, width), "No", "Show", "Always"))
    return component_definition(control_actions(overlay_name, double_click=False), children, "00000000")


def overlay_component(type_name, data, bg_colour):
    child = entry("overlay", type_name, data, "0 0 1280 800", "No", "Show", "Always")
    return component_definition([], [child], bg_colour, ignore_mouse=True)


# --------------------------------------------------------------------------------------------
# Assembling the two files
# --------------------------------------------------------------------------------------------
def image_entry(name, image, x, y, w, h):
    """A picture drawn at absolute tab coordinates; it takes no touches or focus."""
    return entry(name, "Image", obj(("version", 2), ("imageType", "Regular"), ("colour", "0"), ("image", image)),
                 "%d %d %d %d" % (x, y, w, h), "No", "Show", "Always")


PLOTTER_H = 80   # slot height used by a plotter; the name sits under it


def plotter_data(style, plot_range):
    """A scrolling trace of one display-only parameter. The 'Data' handle is remapped to the parameter."""
    lo, hi = plot_range
    acc = style["accent"]
    return obj(("version", 2), ("backgroundColour", style["background"]), ("drawLine", True),
               ("lineDirection", "Up"), ("lineColourStart", acc), ("lineColourEnd", acc),
               ("horizLineGradient", False), ("lineWidth", 2.0),
               ("fillColourStart", "40" + acc[2:]), ("fillColourEnd", "00" + acc[2:]),
               ("horizFillGradient", False), ("fillZero", 0.0), ("dataHandle", "Data"),
               ("dataMin", lo), ("dataMax", hi), ("drawHistory", True), ("historyDirection", "Left"),
               ("historyColour1", "30" + acc[2:]), ("historyColour2", "08" + acc[2:]),
               ("historyTime", PLOTTER_HISTORY_SECONDS), ("historySkipFrames", 5))


def tab_component(page, style):
    children = []
    # Paint order is first = bottom: background, then art, then the controls on top.
    if page.background:
        for ci, (x, y, w, h) in enumerate(page.background_cells):
            name = "background" if len(page.background_cells) == 1 else "background tile %d" % ci
            children.append(image_entry(name, page.background, x, y, w, h))
    for ai, pic in enumerate(page.art):
        for ci, (x, y, w, h) in enumerate(pic["cells"]):
            name = "art %d" % ai if len(pic["cells"]) == 1 else "art %d tile %d" % (ai, ci)
            children.append(image_entry(name, pic["image"], x, y, w, h))
    # Groups: an outline picture with its label in the band above the outline's top edge.
    for gi, g in enumerate(page.groups):
        children.append(image_entry("group %d" % gi, g["image"], g["x"], g["y"], g["w"], g["h"]))
        if g["label"]:
            children.append(entry("group %d label" % gi, "Label", label_data("Text", style["accent"], 20.0, "left", g["label"]),
                                  "%d %d %d 26" % (g["x"] + 18, g["y"] + 6, g["w"] - 36), "No", "Show", "Always"))
    # Ticks sit under their control: a ring centred on the knob, or a row of marks under a fader's track.
    for i, ctl in enumerate(page.controls):
        if not ctl.ticks_asset:
            continue
        row, col = divmod(i, 4)
        fname, w, h = ctl.ticks_asset
        if ctl.widget == "knob":
            cx = SLOT_X[col] + SLOT_W / 2.0
            cy = SLOT_Y[row] + SLOT_H - ctl.knob_size / 2.0   # the knob sits at the slot's bottom, centred
            x, y = int(round(cx - w / 2.0)), int(round(cy - h / 2.0))
        else:
            x, y = SLOT_X[col] + 15, SLOT_Y[row] + 92         # under the fader strip (its bounds are 15, 54 in the slot)
        children.append(image_entry("ticks %d" % i, fname, x, y, w, h))
    for i, ctl in enumerate(page.controls):
        row, col = divmod(i, 4)
        bounds = "%d %d %d %d" % (SLOT_X[col], SLOT_Y[row], SLOT_W, SLOT_H)
        invalidating = None
        if ctl.visible:
            vp, idx = ctl.visible
            invalidating = ["IndexedEnabling/%d/%d/%s" % (idx, len(vp.choices), vp.handle)]
        if ctl.widget == "empty":
            continue
        if ctl.widget == "text":
            ts = ctl.element_def["text"] if ctl.element_def else None   # a label element sets the text style
            colour = ts["colour"] if ts else style["text"]
            height = float(ts["height"]) if ts else 30.0
            just = LABEL_JUSTIFY[ts["justification"]] if ts else "left"
            children.append(entry("text %d" % i, "Label", label_data("Text", colour, height, just, ctl.text),
                                  bounds, "No", "Show", "Always", invalidating=invalidating))
            continue
        if ctl.widget == "plotter":
            children.append(entry(ctl.param.name + " plot", "Plotter", plotter_data(style, ctl.plot_range),
                                  "%d %d %d %d" % (SLOT_X[col], SLOT_Y[row], SLOT_W, PLOTTER_H),
                                  "No", "Hide", "Always", remap=[("Data", ctl.param.handle)], invalidating=invalidating))
            children.append(entry(ctl.param.name + " name", "Label", name_label(style, 22.0, "left", ctl.label),
                                  "%d %d %d 24" % (SLOT_X[col], SLOT_Y[row] + PLOTTER_H + 4, SLOT_W),
                                  "No", "Hide", "Always", invalidating=invalidating))
            continue
        children.append(entry(ctl.param.name, ctl.tui_key, obj(("version", 1), ("handleName", "Data")), bounds,
                              "Yes", "Hide", "Always", remap=[("Data", ctl.param.handle)], invalidating=invalidating))
        if ctl.definition.startswith("radio"):
            # Segment captions live in the tab (the definition is shared by every n-way switch).
            width, xs = SEGMENTS[len(ctl.param.choices)]
            for ci, (choice, x) in enumerate(zip(ctl.param.choices, xs)):
                children.append(entry("%s seg %d" % (ctl.param.name, ci), "Label",
                                      label_data("Text", style["text"], 22.0, "horizontallyCentred verticallyCentred", choice),
                                      "%d %d %d 40" % (SLOT_X[col] + x, SLOT_Y[row] + 54, width),
                                      "No", "Hide", "Always", invalidating=invalidating))
    return component_definition([], children, style["background"])


def build_tui(pages, params, style, knob_image, frames, kit_assets):
    """kit_assets: dict asset name -> (file, frames, (w, h)) for the kit files available, or {} without a kit."""
    used = []
    label_of = {}   # definition key -> the custom label it draws (only for keys with one)
    style_of = {}   # definition key -> the labelStyle its name label takes (only for keys with one)
    element_of = {}  # definition key -> the library element whose pictures it draws
    for page in pages:
        for ctl in page.controls:
            if ctl.param is None or ctl.widget == "plotter":
                continue
            key = ctl.definition_key
            if key not in used:
                used.append(key)
                if ctl.label is not None and ctl.widget != "slider":
                    label_of[key] = ctl.label
                if ctl.element:
                    element_of[key] = ctl
                if ctl.label_style:
                    style_of[key] = ctl.label_style
    if "sliderWithFocus" not in used:
        used.insert(0, "sliderWithFocus")  # always present, so hand edits have a template to copy

    def source(elem):
        """Picture lookup for a component: the library element's assets, or the kit's."""
        table = elem.element_assets if elem is not None else kit_assets
        where = ("library element %s" % elem.element) if elem is not None else "the UI kit"

        def get(name):
            if name not in table:
                fail(None, "%s has no picture %s%s" % (where, name,
                     "" if elem is not None else " (tools/make_ui_kit.py --list shows the kit's pictures)"))
            return table[name]
        return get

    defs = []
    for name in used:
        # "base#element@label~style": the base definition, the library element, the custom name and the name's
        # style (each optional).
        head = name.split("@")[0].split("~")[0]
        full, _, _ = head.partition("#")
        elem = element_of.get(name)
        get = source(elem)
        text = label_of.get(name)
        menu = full.endswith("Menu")
        overlay = "menu overlay" if menu else ("knob overlay bipolar" if "Bi" in full else "knob overlay")
        base = full[:-4] if menu else full
        if base == "sliderWithFocus":
            comp = slider_component(style, overlay)
        elif base in ("knobUni", "knobBi"):
            bi = base == "knobBi"
            if elem is not None:
                f, n, size = get("knob_uni" if not bi else "knob_bi")
                ed = elem.element_def or {}
                comp = knob_component(style, overlay, (f, n, size[0]), n, bipolar=bi, name_text=text,
                                      show_value=ed.get("showValue", True) and ed.get("valueStyle") != "segments",   # the glyph is the value
                                      value_size=float(ed.get("valueSize", 22)),
                                      value_colour=ed.get("valueColour"))
            elif knob_image:
                comp = knob_component(style, overlay, (knob_image, frames, 77), frames, bipolar=bi, name_text=text)
            elif kit_assets:
                f, n, size = get("knob_uni" if not bi else "knob_bi")
                comp = knob_component(style, overlay, (f, n, size[0]), n, bipolar=bi, name_text=text)
            else:
                comp = knob_component(style, overlay, None, frames, bipolar=bi, name_text=text)
        elif base in ("faderUni", "faderBi"):
            f, n, _ = get("fader_h_uni" if base == "faderUni" else "fader_h_bi")
            comp = fader_component(style, overlay, f, n, name_text=text)
        elif base == "toggle":
            on, off = get("toggle_on"), get("toggle_off")
            comp = toggle_component(style, overlay, name_text=text, on_file=on[0], off_file=off[0])
        elif base == "button":
            on, off = get("button_on"), get("button_off")
            comp = button_component(style, overlay, on[0], off[0], on[2][0], on[2][1], name_text=text)
        elif base.startswith("radio"):
            n = int(base[5:])
            on, off = get("seg%d_on" % n), get("seg%d_off" % n)
            comp = radio_component(style, overlay, n, name_text=text, files=(on[0], off[0]))
        else:
            fail(None, "internal error: no builder for component %s" % name)
        if style_of.get(name) and not restyle_name(comp, style_of[name]):
            fail(None, "internal error: component %s has no name label to style" % name)
        defs.append((tui_key(name), comp))
    if len({k for k, _ in defs}) != len(defs):
        fail(None, "internal error: two component definitions got the same TUI name")
    defs.append(("knob overlay", overlay_component("KnobOverlay", knob_overlay_data(False), style["background"])))
    defs.append(("knob overlay bipolar", overlay_component("KnobOverlay", knob_overlay_data(True), style["background"])))
    defs.append(("menu overlay", overlay_component("MenuOverlay", menu_overlay_data(), style["background"])))

    # replacementStrings: every discrete parameter referenced by a control or a visibleWhen.
    referenced = {}
    for page in pages:
        for ctl in page.controls:
            if ctl.param is not None:
                referenced[ctl.param.index] = ctl.param
            if ctl.visible:
                referenced[ctl.visible[0].index] = ctl.visible[0]
    replacements = [obj(("key", p.handle), ("value", list(p.choices)))
                    for _, p in sorted(referenced.items()) if p.is_discrete]

    tabs = []
    for ti, page in enumerate(pages):
        tabs.append(obj(("version", 1), ("tabName", page.name), ("fnKeyIndex", ti), ("fnKeySubIndex", 0),
                        ("componentDefinition", tab_component(page, style)),
                        ("qlinkBoundsData", list(QLINK_BANKS[page.qlink_banks][1]))))

    page_data = obj(
        ("version", 1),
        ("componentDefinitions", obj(("version", 2), ("importFiles", []),
                                     ("localComponentDefinitions", [obj(("key", k), ("value", v)) for k, v in defs]))),
        ("replacementStrings", replacements),
        ("info", obj(("version", 1), ("type", "CompleteDescription"))),
        ("tabs", tabs))
    return obj(("pageData", page_data))


def build_qlinks(pages, params):
    entries = []
    for ti, page in enumerate(pages):
        assigned = {}
        for i, ctl in enumerate(page.controls):
            if ctl.param is not None and ctl.widget != "plotter":   # display-only: no hardware knob
                row, col = divmod(i, 4)
                assigned[slot_qlink(row, col)] = ctl.param.index
        for q, p in page.qlinks.items():   # the page's own choices win over the slot order
            assigned[q] = -1 if p is None else p.index
        qmap = Obj(("Q-Link %d" % q, assigned.get(q, -1)) for q in range(1, 17))
        entries.append(obj(("Tab", ti + 1), ("SubTab", 1), ("Bank Direction", QLINK_BANKS[page.qlink_banks][0]), ("Q-Links", qmap)))
    by_index = {p.index: p for p in params}
    first16 = sorted(by_index)[:16]
    program = Obj(("Q-Link %d" % (q + 1), first16[q] if q < len(first16) else -1) for q in range(16))
    return obj(("version", 4),
               ("info", obj(("version", 1), ("type", "CompleteDescription"))),
               ("Screen Mode Q-Links", obj(("version", 4), ("map", entries))),
               ("Program Mode Q-Links", program))


def kit_dir_for(kit, cache_dir, out_dir):
    """Render (or reuse) the kit and return (directory holding the PNGs, assets dict from kit.json)."""
    import make_ui_kit
    tag = "ui-kit-%s%s" % (kit["theme"], ("-" + kit["accent"]) if kit["accent"] else "")
    target = os.path.join(cache_dir, tag) if cache_dir else out_dir
    manifest_path = os.path.join(target, "kit.json")
    fresh = False
    if cache_dir and os.path.isfile(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                m = json.load(f)
            want_accent = (kit["accent"] or make_ui_kit.THEMES[kit["theme"]]).lower()
            fresh = (m.get("kitVersion") == make_ui_kit.KIT_VERSION and m.get("theme") == kit["theme"]
                     and m.get("colours", {}).get("accent") == want_accent
                     and all(os.path.isfile(os.path.join(target, a["file"])) for a in m.get("assets", {}).values()))
        except (OSError, ValueError):
            fresh = False
    if not fresh:
        make_ui_kit.render_kit(target, kit["theme"], kit["accent"], quiet=True)
    with open(manifest_path, "r", encoding="utf-8") as f:
        m = json.load(f)
    assets = {name: (a["file"], a["frames"], (a["width"], a["height"])) for name, a in m["assets"].items()}
    return target, assets


def referenced_images(value, acc):
    """Collect every image file name used in the generated TUI (filmStrip / onImage / offImage / image keys)."""
    if isinstance(value, Obj):
        for k, v in value:
            if k in ("filmStrip", "onImage", "offImage", "image") and isinstance(v, str) and v:
                acc.add(v)
            referenced_images(v, acc)
    elif isinstance(value, (list, tuple)):
        for v in value:
            referenced_images(v, acc)
    return acc


def resolve_elements(pages, library, cache_root, out_dir):
    """Finds, renders (when needed) and loads every library element the layout uses. Its pictures are copied
    into out_dir as "<element>__<file>.png", so two elements never share a file name."""
    import shutil
    import ui_library
    loaded = {}
    for pg in pages:
        for ctl in pg.controls:
            if not ctl.element:
                continue
            if ctl.element not in loaded:
                try:
                    folder = ui_library.find_element(ctl.element, library)
                    el = ui_library.load_element(folder)
                except ui_library.ElementError as e:
                    fail(None, str(e))
                if el["type"] != ELEMENT_FOR_WIDGET[ctl.widget]:
                    fail(None, 'element "%s" is a %s element; a "%s" control needs a %s element'
                         % (ctl.element, el["type"], ctl.widget, ELEMENT_FOR_WIDGET[ctl.widget]))
                assets = {}
                if el["type"] != "label":   # a label element is only a text style, with no pictures
                    cache_dir = os.path.join(cache_root, "ui-library-" + el["name"])
                    manifest = ui_library.cached_manifest(el, cache_dir)
                    for key, a in manifest["assets"].items():
                        fname = "%s__%s" % (el["name"], a["file"])
                        shutil.copy2(os.path.join(cache_dir, a["file"]), os.path.join(out_dir, fname))
                        assets[key] = (fname, a["frames"], (a["width"], a["height"]))
                loaded[ctl.element] = (el, assets)
            ctl.element_def, ctl.element_assets = loaded[ctl.element]
            # A knob or fader element may carry ticks: its picture is drawn under every control that uses it.
            t = ctl.element_assets.get("ticks")
            ctl.ticks_asset = (t[0], t[2][0], t[2][1]) if t else None


def knob_size_for(ctl, kit, knob_image):
    """The diameter the knob is drawn at: a library element's, the kit's, or the generic knob's."""
    if ctl.element_def is not None and ctl.element_def.get("type") == "knob":
        return ctl.element_def["size"]
    if knob_image:
        return 77
    return 90 if kit else 77


def generate(params_path, ui_path, out_dir, assets_dir=None, quiet=False, kit_cache=None, library=None):
    params = load_params(params_path)
    table = ParamTable(params)
    if ui_path:
        pages, style, knob_image, frames, kit = load_ui(ui_path, table)
    else:
        pages, style, knob_image, frames, kit = auto_pages(params), dict(DEFAULT_STYLE), None, 127, None
    if knob_image:
        knob_image = os.path.basename(knob_image)
        if assets_dir and not os.path.isfile(os.path.join(assets_dir, knob_image)):
            print('gen_ui: WARNING: knobImage "%s" not found in %s; the knob will render blank on the MPC.'
                  ' (tools/make_knob.py can generate one.)' % (knob_image, assets_dir))
    if assets_dir:
        for pg in pages:
            for image in ([pg.background] if pg.background else []) + [a["image"] for a in pg.art]:
                if not os.path.isfile(os.path.join(assets_dir, image)):
                    print('gen_ui: WARNING: picture "%s" on page "%s" not found in %s; nothing will be drawn for it.'
                          % (image, pg.name, assets_dir))
    if len(pages) > 6 and not quiet:
        print("gen_ui: NOTE: %d pages; the MPC screen has six function keys, so tabs beyond the sixth are untested." % len(pages))

    os.makedirs(out_dir, exist_ok=True)
    kit_dir, kit_assets = (kit_dir_for(kit, kit_cache, out_dir) if kit else (None, {}))
    cache_root = kit_cache or os.path.join(os.path.dirname(os.path.normpath(out_dir)), "ui-library-cache")
    resolve_elements(pages, library, cache_root, out_dir)
    for pg in pages:
        for ctl in pg.controls:
            if ctl.widget == "knob":
                ctl.knob_size = knob_size_for(ctl, kit, knob_image)
    layout_pictures(pages, assets_dir)
    for pi, pg in enumerate(pages):
        for gi, g in enumerate(pg.groups):
            g["image"] = "group-%d-%d.png" % (pi + 1, gi + 1)
            write_group_png(os.path.join(out_dir, g["image"]), g["w"], g["h"], style["accent"])
    tui = build_tui(pages, params, style, knob_image, frames, kit_assets)
    qlinks = build_qlinks(pages, params)
    if kit_dir and os.path.abspath(kit_dir) != os.path.abspath(out_dir):
        for img in sorted(referenced_images(tui, set())):
            src = os.path.join(kit_dir, img)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(out_dir, img))
    elif kit_dir:
        # Rendered straight into the output: drop the files no control uses.
        keep = referenced_images(tui, set())
        for name in list(kit_assets):
            f = kit_assets[name][0]
            if f not in keep and os.path.isfile(os.path.join(out_dir, f)):
                os.remove(os.path.join(out_dir, f))
        if os.path.isfile(os.path.join(out_dir, "kit.json")):
            os.remove(os.path.join(out_dir, "kit.json"))
    tui_path = os.path.join(out_dir, "TUI.json")
    q_path = os.path.join(out_dir, "Q-Links.json")
    with open(tui_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(dump_json(tui) + "\n")
    with open(q_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(dump_json(qlinks) + "\n")
    if not quiet:
        n_controls = sum(1 for pg in pages for c in pg.controls if c.param is not None)
        print("gen_ui: wrote %s and %s (%d page%s, %d bound control%s, %s%s)"
              % (tui_path, q_path, len(pages), "" if len(pages) == 1 else "s",
                 n_controls, "" if n_controls == 1 else "s",
                 "layout from " + ui_path if ui_path else "auto layout",
                 ", kit " + kit["theme"] + (" accent " + kit["accent"] if kit["accent"] else "") if kit else ""))
        bip = [c.param.name for pg in pages for c in pg.controls if c.widget in ("knob", "fader") and c.polarity == "auto" and c.bipolar]
        if bip:
            print('gen_ui: NOTE: drawn bipolar (centre-zero) by auto-detection: %s. Set "polarity" to override.'
                  % ", ".join('"%s"' % n for n in bip))
    return tui_path, q_path


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate MPC Plugin Skins (TUI.json + Q-Links.json) from params.json and an optional ui.json.")
    ap.add_argument("--params", required=True, help="build/params.json written by host_sim dump")
    ap.add_argument("--ui", help="ui.json layout spec (omit for an automatic layout of all parameters)")
    ap.add_argument("--out", required=True, help='output directory, normally "<plugin folder>/Plugin Skins"')
    ap.add_argument("--assets-dir", help="folder holding knobImage (only used to warn when the file is missing)")
    ap.add_argument("--kit-cache", help="directory to cache the rendered UI kit between builds (e.g. the project's build/)")
    ap.add_argument("--library", help="folder of UI elements that ui.json may name (default: ui-library/ at the repo root)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    try:
        generate(args.params, args.ui, args.out, args.assets_dir, args.quiet, args.kit_cache, args.library)
    except UiError as e:
        print("gen_ui: " + str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
