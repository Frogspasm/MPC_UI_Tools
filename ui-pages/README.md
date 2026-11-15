# Page templates

Saved pages from the layout editor (`tools/ui_editor.html`, **Page templates** panel), one `<name>.json` per template:

```json
{ "format": 1, "name": "Filter page", "page": { "name": "FILTER", "controls": [ ... ], "groups": [ ... ], "qlinks": { ... } } }
```

A whole-layout template (**Save whole layout…**) holds the complete `ui.json` instead:

```json
{ "format": 1, "name": "Synth layout", "layout": { "pages": [ ... ], "kit": { ... } } }
```

`page` is one page exactly as it appears in a plugin's `ui.json` (controls, names and name styles, elements, groups, Q-Links, background and artwork file names). In the editor, **Add as new page** or **Replace this page** puts it into the layout you are editing. Parameter names stay as they were saved: on a plugin that does not have them, those slots show in Checks so you can point them at its own parameters. Artwork file names refer to the plugin's `assets/` folder, so copy the pictures too.
