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
| `labelStyle` | The look and place of the control's name (knob, fader, switch and button): `{"font": "Roboto", "style": "Bold", "size": 24, "align": "left", "dx": 0, "dy": 30}`, every key optional. `font` is one of the MPC's three fonts, `Titillium Web` (its own), `Roboto` or `Nexa`; `style` is one of `Thin`, `Light`, `Book`, `Regular`, `Medium`, `SemiBold`, `Bold`, `Black` and their `…Italic` forms; `size` is the text height in px (8 to 60); `align` is `left`, `centre` or `right`; `dx`/`dy` move the name in px within its slot (it stays inside the slot, and its box grows to fit a larger size). A knob's name spans the slot's width, so it moves sideways with `align`. In the layout editor: select the control and drag its name, or use **Name style** in the Inspector (also for several selected controls at once). |
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

## Opening the UI tools

Start them with **`Open UI tools.bat`** in the repo folder (double-click; on macOS `Open UI tools.command`), or `python tools/ui_server.py`. It starts a small server for this repo on your computer and opens the layout editor and the element designer in the browser (http://127.0.0.1:8770/; the next free port if that one is busy). Leave its window open while you work; closing it stops the server.

Opened this way, both tools read and save `ui-library/` and `ui-pages/` in the repo through the server: there is no folder to choose and nothing to reconnect after a reload, and a save in the designer shows in the layout editor at once. The server only listens on your own computer and only writes `.json` files inside those two folders. Opening the HTML files directly still works, but then the browser asks for the folders again on every visit.

Drafts are kept per address: a layout you had open as a file does not carry over to the server address. Save or export it to the plugin's `ui.json` first, then open it in the served editor.

## Element library

Build knobs, faders, switches, buttons and label styles once, and reuse them across plugins. Each element is a folder in `ui-library/` with an `element.json`. Design one in the browser with `tools/ui_designer.html` (choose the library folder, edit, save) or write it by hand, and check it with `python tools/ui_library.py check <name>`.

Name an element in `ui.json` with `"element"`. A build draws the element's pictures itself, so the plugin needs no image files of its own:

```json
{ "param": "Cutoff", "widget": "knob", "element": "example-knob" },
{ "param": "Comp On", "widget": "button", "element": "my-button" },
{ "widget": "text", "text": "Filter", "element": "example-label" }
```

**Putting a knob element on a layout in the editor.** Save the element from `tools/ui_designer.html`, then in `tools/ui_editor.html` select a knob slot and pick the element from **Element** in the Inspector. The editor draws it straight from its `element.json` (no render step), at the value set by **Preview**. If the list isn't there yet, press **Choose ui-library folder…** beside Element once and pick the repo's `ui-library` folder; the editor remembers it (after a reload it may ask with one click, **Reconnect**). Opened with `Open UI tools.bat` (see above), both tools find `ui-library/` by themselves and none of the folder steps here apply. The designer's **Library** panel (left column) shows which folder it saves to, a **Save to library** button (marked • while there are unsaved changes) and the saved elements listed by type (knobs, faders, switches, buttons, labels); click one to open it. After a reload the browser asks once before the designer can write to the folder again: press **Reconnect**. Saving under the same name updates the element. An open layout editor in the same browser draws the element as you edit it in the designer, before you save, and its Kit panel says "showing my-knob as edited in the designer (not saved yet)" until the library matches; a build only uses what is saved. The layout editor also reads the library again every few seconds and when you switch back to it (**↻** does it by hand).

To change many controls at once, select them (Shift-click, Ctrl-click, drag a box, or **Select all knobs on this page** in a knob's Inspector). The Inspector then shows the settings they share (Widget, Element, Name, Overlay, Polarity, Preview); a choice applies to every selected control it fits, an element only to the knobs. A field reads "(mixed)" while the selection differs. Undo reverts the whole change in one step.

`button` is a push button for a bool parameter (its own widget, drawn with the LED style). A button element sets its roundness (`corner`), the width of its highlight and the width of its drop shadow.

Knob, fader, switch and button elements can set depth (`shadow` and `highlight`, in px) and an `outlineWidth`; a knob can add ridges round its outer edge (`ridges`: `count` and `length`). Leaving a setting out keeps the kit's look.

A knob can also set:
- `cap`: `{"size": 0.7, "shade": 0.5, "invert": false, "curve": [[0, 0], [1, 1]]}`. A flat top `size` of the face radius (0.3 to 0.95), with a sloped ring down to the face. `shade` (0 to 1) sets how far the slope's light and dark sides move from the body (higher is darker). `invert: true` swaps the lit and dark sides. `curve` (optional, 2 to 16 points `[u, v]`) is a custom gradient across the slope: u runs from 0 at the flat top's edge to 1 at the face's edge, v from 0 (dark) to 1 (light). It scales with the knob.
- `highlight`: the width of the lit band along the rim (0 to 10 px, 0 is none), on its own or with a shadow.
- `highlightAngle`: where the lit band sits, in degrees clockwise from 12 o'clock (-180 to 180; the kit's is -74).
- `highlightFade`: fades the band's two ends (0 to 1). 0 keeps hard ends, the kit's look; 1 fades the ends to nothing.
- `colours`: for a knob, `secondary` (the flat top's colour), `highlight` and `shadow` (the drop shadow) join `body`, `track`, `pointer` and `outline`. The highlight and shadow keep their softness whatever colour you pick.
- `valueSize` (8 to 60 px, the MPC's default is 22) and `valueColour` (ARGB) set the value shown in the centre.
- `valueStyle`: `"segments"` with `glyphs` (a string of 1 to 64 characters, one per value) draws the value as a 16-segment character at the knob's centre, in place of the font text. Each knob frame carries the glyph for its value, so the arc and pointer still turn and the character changes with the value. The glyph height is `valueSize` (default 22 px), like the font text it replaces. The parameter must have a fixed list of values; the glyph count must match them. Letters, digits and `- / ( ) ' .` are available. The lit colour is red unless `valueColour` is set; the unlit segments are a dark red. The segment shapes and character table follow the Multi-trak project's notes (`tools/ui_segments.py`). Not checked on the MPC hardware.
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

**Q-Links.** By default each hardware Q-Link drives the control in its slot of the 4 x 4 grid (Q13 top-left, Q1 bottom-left; a 4-knob MPC steps through the columns as banks). A page's `qlinks` overrides single knobs: a Q-Link number (`"1"` to `"16"`) and a parameter name, or `null` to leave that knob unused on the page. Q-Links not listed keep following their slots. Any parameter works, even one not shown on the page:

```json
{ "name": "BASS", "controls": [ ... ], "qlinks": { "13": "Cutoff", "14": "Resonance", "1": null } }
```

In the layout editor, the **Q-Links on this page** panel under the screen sets these with one menu per knob. **Pin current mapping** writes down what every knob drives now, so moving controls afterwards leaves the hardware mapping alone; **Reset to automatic** removes the page's overrides. A slot's Q badge (plain view) and the Inspector show which Q-Links really drive it; "no Q" means none.

**Banks on a 4-knob MPC (One, Live).** These models step through a page's 16 Q-Links four at a time. By default a bank is a column (bank 1 = the left column, Q13 Q9 Q5 Q1). Set `"qlinkBanks": "rows"` on a page to bank by rows instead: bank 1 is the top row (Q13 Q14 Q15 Q16), bank 2 the next row, and the MPC's highlight frame goes round a row. Lay a rows page out with one related set of four controls per row. In the layout editor this is the **Banks for 4 Q-Links: Columns / Rows** switch in the Q-Links panel; the dashed bank frames on the screen follow it. Models with 16 Q-Links are not affected.

**Templates.** The layout editor's **Templates** panel (left column) saves into the repo's `ui-pages/` folder (opened with `Open UI tools.bat` it is already connected; otherwise the first save asks for the folder). It lists the saved ones in two groups:

- **Pages.** **Save this page…** saves the page on the screen. **Add as new page** puts a copy after the current page; **Replace this page** swaps the current page for it.
- **Layouts.** **Save whole layout…** saves every page together with the kit, style and other layout settings: the whole `ui.json`. **Use this layout** replaces the layout you are editing with it; **Add its pages** inserts its pages after the current page and keeps your own kit and style.

Undo brings back whatever a template replaced. Templates keep controls, names and name styles, elements, groups, Q-Links (and bank direction) and artwork names. Parameter names stay as saved: the list shows how many a plugin lacks, and Checks names those slots so you can point them at the plugin's own parameters. Artwork files are not in the template: copy the pictures into the plugin's `assets/` folder.

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
