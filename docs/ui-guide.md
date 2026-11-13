# Giving your plugin a touch UI (the easy way)

Without any UI files, the MPC already gives your plugin a working screen: pages of 16 parameter sliders, hardware knobs mapped in order. That is enough to test a plugin. A real UI needs three things more: named pages, parameters grouped sensibly, and controls that look like what they do. The SDK's `ui.json` gives you those in a few lines; `tools/gen_ui.py` turns it into the MPC's own skin files (`Plugin Skins/TUI.json` and `Q-Links.json`), which `build.py` runs automatically.

For full control over the look (images, custom widgets, envelopes), read `ui-reference.md` and write the skin files yourself in `plugins/MyPlugin/skins/`; the build copies them verbatim and skips the generator.

## The screen

- Pages are function keys along the bottom of the screen; the page name is the key label (keep it short, 8 characters or fewer).
- Each page offers a 4 × 4 grid of control slots, matching the 16 hardware knobs (Q-Links) in their 4 × 4 arrangement on MPCs. The grid is a convenience of the simple `ui.json` layout, not a limit of the MPC: with a hand-written skin controls can go anywhere (see `ui-reference.md`).
- The hardware knobs work in **groups of four**. Touching a control selects its group, and the MPC draws a focus rectangle around that group on screen. That rectangle looks right only when the four controls it encloses sit together as one block, so lay pages out as blocks of four side by side: a row of four, or a column of four. Q-Link groups can run horizontally or vertically around the on-screen controls (bank direction `Row` or `Column`), so either shape is fine; mixing them on one page is fine too, as long as every control belongs to a clean block of four. On products with fewer knobs (Force, MPC X) the mapping still works; the bank buttons select the group.
- Controls are listed in reading order: left to right, top to bottom. Leave a slot empty with `"empty"`.
- Each control shows the parameter's name and current value text from your code. Double-tap or Enter opens a large edit overlay.

## ui.json

```json
{
  "kit": "mpc-red",
  "pages": [
    {
      "name": "OSC",
      "controls": [
        { "param": "Wave",      "widget": "switch" },
        { "param": "Detune",    "widget": "knob" },
        { "param": "Octave",    "widget": "knob" },
        { "param": "Level",     "widget": "fader" },
        { "param": "Sub Level", "widget": "fader" },
        { "param": "PWM Depth", "widget": "knob", "visibleWhen": { "param": "Wave", "choice": "Square" } },
        "empty",
        { "widget": "text", "text": "Oscillator 2" }
      ]
    },
    {
      "name": "FILTER",
      "controls": [
        { "param": "Cutoff",    "widget": "knob" },
        { "param": "Reso",      "widget": "knob" },
        { "param": "Mode",      "widget": "switch" },
        { "param": "Env Amt",   "widget": "knob", "polarity": "bipolar" },
        { "param": "Attack",    "widget": "fader" },
        { "param": "Decay",     "widget": "fader" },
        { "param": "Sustain",   "widget": "fader" },
        { "param": "Release",   "widget": "fader" }
      ]
    },
    {
      "name": "LFO",
      "controls": [
        { "param": "Shape", "widget": "slider", "overlay": "menu" },
        { "param": "Sync",  "widget": "switch" },
        { "param": "Rate",  "widget": "knob", "visibleWhen": { "param": "Sync", "choice": "Off" } },
        { "param": "Div",   "widget": "slider", "overlay": "menu", "visibleWhen": { "param": "Sync", "choice": "On" } }
      ]
    }
  ],
  "style": { "background": "ff1e1d1e" }
}
```

| Field | Meaning |
|---|---|
| `pages[].name` | Function-key label. Up to 32 pages. |
| `pages[].controls[]` | Up to 16 entries. A plain string is a parameter **name** exactly as declared in code (`floatParam("cutoff", "Cutoff", ...)` → `"Cutoff"`), shown as a generic slider; the string `"empty"` leaves the slot blank. |
| `widget` | `"knob"` (film-strip knob with name and value), `"fader"` (horizontal film-strip fader under a name / value header), `"switch"` (toggle for bool parameters, 2–4 captioned segment buttons for choice parameters), `"slider"` (default: the MPC's generic name + value bar), `"text"` (a static heading; needs `text`), `"empty"`. |
| `polarity` | For `knob` and `fader`: `"auto"` (default), `"unipolar"` or `"bipolar"`. Bipolar strips fill from the centre. Auto picks bipolar when the parameter's default is the centre of its range and its value text reads as zero. |
| `label` | The name shown on the MPC for a `knob`, `fader`, `switch` or `plotter` (up to 24 characters). Defaults to the parameter's name. `""` hides the name on the MPC, leaving only the value. Not used by `"slider"`, whose bar draws the parameter's own name. |
| `element` | The name of a picture-and-style element in `ui-library/` (see the element library section below). It replaces the kit's pictures for that control: `knob`, `fader`, `switch`, `button`, or `text` (a label style). |
| `overlay` | What double-tap / Enter opens: `"knob"` (big knob editor, default) or `"menu"` (a list; the default for `switch`, and the right choice for any long choice list). |
| `visibleWhen` | Show this control only while another parameter has a given value: `{"param": "Wave", "choice": "Square"}` or `{"param": "Sync", "index": 1}`. Works with choice and bool parameters. |
| `kit` | The film-strip theme for `knob` / `fader` / `switch`: `"mpc-red"` (assumed when absent), `"amber"`, `"cyan"`, `"lime"`, `"violet"`, `"mono"`, or `{ "theme": "...", "accent": "AARRGGBB" }`. See `ui-kit/README.md` and `ui-kit/preview.png`. |
| `style` | Optional ARGB colours: `background`, `accent` (focus ring; follows the kit colour unless set), `text`, `muted`. |
| `knobImage`, `knobFrames` | Optional: your own film-strip PNG from the project's `assets/` folder for `"knob"` widgets instead of the kit's. `tools/make_knob.py` can generate a plain one. |

Every bool and choice parameter you reference is given discrete steps on the data wheel and the overlay, using the choice labels from your code.

Parameters you leave out of `ui.json` are still reachable through automation and still saved; they are simply not on screen. A common pattern is to put rarely used settings on a last page called `MORE`.

## Choosing knob, fader, switch or slider

The kit exists so a page reads at a glance: a knob says "dial this in", a fader says "how much", a switch says "pick one". Use the same widget for the same kind of job on every page.

| Parameter | Widget | Why |
|---|---|---|
| On/off (bool) | `switch` | A pill toggle; the value text still says On / Off. |
| Mode with 2–4 options (filter type, waveform, routing) | `switch` | Segment buttons captioned with the choice names; one tap selects. |
| Mode with 5 or more options (note divisions, long wave lists) | `slider` + `"overlay": "menu"` | Segments would not fit; the bar steps with the Q-Link and the menu lists everything. |
| Tone and character: cutoff, resonance, drive, tune, detune, rate, depth, width | `knob` | Dialled by feel; the arc shows where you are in the range. |
| Anything centred on zero: pan, fine tune, pitch offsets, modulation amounts that go negative | `knob` (bipolar) | The arc grows from the centre, so zero is obvious. Auto-detected for centre-zero defaults; set `"polarity": "bipolar"` otherwise. |
| Levels and mixes: volume, level, mix, dry/wet, send | `fader` | "How much" reads best as a bar filling from the left. |
| Envelope stages (A, D, S, R) | four `fader`s in one row | A row of faders looks like the envelope it controls. |
| Time, size, feedback on delays and reverbs | `knob` | Range-y parameters that are dialled, not set. |
| Values where the text matters more than the position (note names, ratios, divisions) | `slider` | The generic bar shows the value text large. |

Rules of thumb:

- Top row of page 1: the four controls someone touches first (cutoff and resonance on a synth; time, feedback and mix on a delay), as knobs or faders, never switches.
- Group by signal flow: oscillators, filter, envelopes, modulation, effects, output. Put a section's switch (its mode) in the same row as the knobs it changes.
- Make each block of four mean something. The four knobs of a Q-Link group drive its four controls and the focus rectangle wraps them, so put one related set in each block: the four stages of an envelope, the cutoff / resonance / drive / key-tracking of a filter, the time / feedback / tone / mix of a delay. A block of four can be a row or a column. Avoid splitting a section across two blocks, and avoid blocks that mix unrelated controls just to fill space; a deliberate `empty` slot or a `text` heading is better than a stray control.
- One theme per plugin. `mpc-red` matches the MPC; `amber` suits drums and analogue-style synths, `cyan` delays, reverbs and digital effects, `lime` and `violet` playful instruments, `mono` utilities. An `accent` colour makes the kit match a brand.
- Do not rely on colour alone; the MPC screen is small and often viewed from an angle. Short names and unit-bearing value text (`1.2 kHz`, `-6.0 dB`, `1/8T`) matter more than the graphics.

## Artwork and live displays

**Pictures.** Put PNG or JPEG files in the project's `assets/` folder (build.py copies that folder into `Plugin Skins/`) and name them in `ui.json`:

```json
{ "name": "BASS",
  "background": "bg.png",
  "art": [ { "image": "logo.png", "x": 900, "y": 20, "w": 300, "h": 100 } ],
  "controls": [ ... ] }
```

`background` covers the whole 1280 x 628 tab area and sits under everything. `art` pictures are placed in tab pixels (0, 0 is the top-left of the area) and sit under the controls. Use file names only, not folders. The editor (`tools/ui_editor.html`) shows them when you load the assets folder.

**Tiling.** Set `"backgroundTile": true` on a page, or `"tile": true` on an `art` item, to repeat the picture. `backgroundScale` and `scale` set the size of each tile as a percentage of the picture's own size (1 to 400, default 100). Each tile is one image on the tab, so keep the count modest: 400 per picture at most. Tiles along the right and bottom edges are squashed to fit the box, and the generator reads each picture's size from its file header.

```json
{ "name": "BASS", "background": "grain.png", "backgroundTile": true, "backgroundScale": 25, "controls": [ ... ] }
```

## Element library

Build knobs, faders, switches, buttons and label styles once, and reuse them across plugins. Each element is a folder in `ui-library/` with an `element.json`. Design one in the browser with `tools/ui_designer.html` (choose the library folder, edit, save) or write it by hand, and check it with `python tools/ui_library.py check <name>`.

Name an element in `ui.json` with `"element"`. A build draws the element's pictures itself, so the plugin needs no image files of its own:

```json
{ "param": "Cutoff", "widget": "knob", "element": "example-knob" },
{ "param": "Comp On", "widget": "button", "element": "my-button" },
{ "widget": "text", "text": "Filter", "element": "example-label" }
```

`button` is a push button for a bool parameter (its own widget, drawn with the LED style). A button element sets its roundness (`corner`), the width of its highlight and the width of its drop shadow.

Knob, fader, switch and button elements can set depth (`shadow` and `highlight`, in px) and an `outlineWidth`; a knob can add ridges round its outer edge (`ridges`: `count` and `length`). Leaving a setting out keeps the kit's look.

A knob can also set:
- `cap`: `{"size": 0.7, "shade": 0.5, "invert": false, "curve": [[0, 0], [1, 1]]}`. A flat top `size` of the face radius (0.3 to 0.95), with a sloped ring down to the face. `shade` (0 to 1) sets how far the slope's light and dark sides move from the body (higher is darker). `invert: true` swaps the lit and dark sides. `curve` (optional, 2 to 16 points `[u, v]`) is a custom gradient across the slope: u runs from 0 at the flat top's edge to 1 at the face's edge, v from 0 (dark) to 1 (light). It scales with the knob.
- `highlight`: the width of the lit band along the rim (0 to 10 px, 0 is none), on its own or with a shadow.
- `highlightAngle`: where the lit band sits, in degrees clockwise from 12 o'clock (-180 to 180; the kit's is -74).
- `colours`: for a knob, `secondary` (the flat top's colour), `highlight` and `shadow` (the drop shadow) join `body`, `track`, `pointer` and `outline`. The highlight and shadow keep their softness whatever colour you pick.
- `valueSize` (8 to 60 px, the MPC's default is 22) and `valueColour` (ARGB) set the value shown in the centre.
- `pointerLength`: how far the pointer tip reaches, as a fraction of the face (0.3 to 1; 1 is the kit's).
- `pointerOffset`: move the pointer along its radius in px (-20 to 20): positive towards the rim, negative towards the centre.
- `showValue`: `false` leaves the parameter's value off the knob's centre (the default is on, as the MPC layout has it). A knob or fader element can carry ticks (`"ticks"` in its element.json): marks round a knob, or in a row under a fader. Their picture is drawn under every control that uses the element.

**Groups.** A labelled rounded outline around a set of related controls, drawn behind them. Give each as tab pixels, with an optional label of up to 40 characters that sits in the band above the outline's top edge:

```json
{ "name": "BASS",
  "groups": [ { "x": 9, "y": 0, "w": 626, "h": 166, "label": "Filter" } ],
  "controls": [ ... ] }
```

The generator writes each outline as `group-<page>-<n>.png` into Plugin Skins/. The outline does not move with the controls. Leave 14 px on the sides and below the controls and about 36 px above them, so the label has room.

**Plotter.** A scrolling trace of one value the plugin writes for the screen. It needs a parameter that is not automatable (`automatable = false` in `addParam`), so the host does not treat it as a control:

```json
{ "param": "LFO View", "widget": "plotter", "min": 0, "max": 1 }
```

`min` and `max` give the range of the value being drawn. The plugin fills it with `setDisplayNormalised()`. A plotter takes a slot and has no Q-Link. Not yet tested on hardware: it is not confirmed whether the plotter reads the plain value (here 0..100) or the normalised 0..1 value. If a trace looks flat on the MPC, try `"min": 0, "max": 1`.

## Regenerating

`build.py` regenerates the skins on every full build unless `plugins/MyPlugin/skins/` exists. For a quick check without cross-compiling, run the generator directly:

```
python tools/gen_ui.py --params plugins/MyPlugin/build/params.json --ui plugins/MyPlugin/ui.json --out "plugins/MyPlugin/build/<Manufacturer> - VST - <Name>/Plugin Skins" --kit-cache plugins/MyPlugin/build
```

To go from generated to hand-written, copy `build/<folder>/Plugin Skins/` to `plugins/MyPlugin/skins/` and edit from there; the kit PNGs come with it.

## What the generator cannot do

Vertical faders, custom graphics beyond the kit, envelope displays, XY pads and sub-tabs. All are possible in the full format; see `ui-reference.md` and the hand-written section of `ui-kit/README.md`.
