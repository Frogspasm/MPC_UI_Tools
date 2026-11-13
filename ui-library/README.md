# UI element library

Shared knobs, faders, switches, buttons and label styles for MPC plugins. Each element is a folder
holding `element.json`. Make and edit them with `tools/ui_designer.html` (browser) or
`tools/ui_library.py` (command line), then name them in a plugin's `ui.json`:

```json
{ "param": "Cutoff", "widget": "knob", "element": "example-knob" }
{ "widget": "text", "text": "Filter", "element": "example-label" }
```

| Element type | Used by widget | What it sets |
|---|---|---|
| `knob` | `knob` | the knob's colours, diameter, depth (shadow and highlight), outline width, ridges round the outer edge, a taper `cap` (flat top with a sloped ring; `shade`, `invert` and an optional custom `curve` for the slope), `highlightAngle`, `pointerLength` and `pointerOffset`, `showValue`, `valueSize` and `valueColour` (the value in the centre), extra `colours` (`secondary`, `highlight`, `shadow`), and optional ticks: a 270° ring of marks round it |
| `fader` | `fader` | the fader's colours, depth, outline width, and optional ticks: a row of marks under its track |
| `switch` | `switch` | the toggle and segment colours, depth and outline width (sizes are fixed) |
| `button` | `button` | the push button's colours, size, LED, roundness (`corner`), highlight width, shadow width and outline width |
| `label` | `text` | the text height, colour and alignment of a heading |

`python tools/ui_library.py list` shows the elements, `check <name>` validates one and
`render <name>` draws its PNGs into its folder so you can look at them. A build renders what it
needs by itself, so `render` is only for viewing.
