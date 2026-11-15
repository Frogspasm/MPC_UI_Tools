// Element drawing, shared by the element designer (ui_designer.html) and the layout editor (ui_editor.html).
// Draws an element from its element.json on a canvas, as close to tools/ui_library.py's renderer as a canvas allows.
// The build does not use this file: it renders the real pictures in Python. Everything is inside UIEL, so the
// pages that load this file keep their own names.
const UIEL = (() => {
  // ---------- theme defaults (copied from THEMES in tools/make_ui_kit.py) ----------
  const THEME_ACCENT = { "mpc-red": "ffd31145", "amber": "ffffa21a", "cyan": "ff19c6e0", "lime": "ff8fd21f", "violet": "ff9b63ff", "mono": "ffe4e4e6", "acidbox": "ffd93a25", "acidbox-midnight": "ffff5b40" };
  const VALUE_FONT_EM = 1.521;   // Titillium Web: ascent + descent per em (as FONT_EM in the layout editor)
  // The box the knob's value sits in, centred on the knob, as tools/gen_ui.py knob_stacked writes it: 32 px tall,
  // taller for a large value so the MPC does not cut it off.
  const valueBoxH = size => Math.max(32, Math.ceil(size * 1.2));
  const GREY = { body: "ff2a2a2d", track: "ff434347", pointer: "fff2f2f2", thumb: "ffb9b9bd", outline: "ff0e0e0f" };

  // ---------- colours: ARGB strings <-> arrays and CSS ----------
  const argb = v => { const n = parseInt(v, 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255, (n >>> 24) & 255]; };
  const cssA = a => `rgba(${a[0]},${a[1]},${a[2]},${(a[3] / 255).toFixed(3)})`;
  const css = v => cssA(argb(v));
  const mixA = (a, b, t) => a.map((x, i) => Math.round(x + (b[i] - x) * t));
  const WHITE = [255, 255, 255, 255], BLACK = [0, 0, 0, 255];
  const hexOf = a => [a[3], a[0], a[1], a[2]].map(x => Math.max(0, Math.min(255, Math.round(x))).toString(16).padStart(2, "0")).join("");   // [r,g,b,a] -> "aarrggbb"

  // ---------- canvas helpers ----------
  const SWEEP = Math.PI * 1.5, HALF_PI = Math.PI / 2;
  const canvasAng = a => a - HALF_PI;   // renderer angles (0 = 12 o'clock) to canvas angles (0 = 3 o'clock)
  function drawArc(ctx, cx, cy, r, w, a0, a1, colour) {
    ctx.beginPath(); ctx.strokeStyle = colour; ctx.lineWidth = w; ctx.lineCap = "butt";
    ctx.arc(cx, cy, r, canvasAng(a0), canvasAng(a1), a1 < a0); ctx.stroke();
  }
  function roundRect(ctx, x, y, w, h, r) { ctx.beginPath(); ctx.roundRect ? ctx.roundRect(x, y, w, h, Math.max(0, r)) : ctx.rect(x, y, w, h); ctx.fill(); }
  function strokeRoundRect(ctx, x, y, w, h, r) { ctx.beginPath(); ctx.roundRect ? ctx.roundRect(x, y, w, h, Math.max(0, r)) : ctx.rect(x, y, w, h); ctx.stroke(); }

  // Same as the renderer's curve_value: piecewise linear, held flat past the ends.
  function curveAt(pts, u) {
    const p = [...pts].sort((a, b) => a[0] - b[0]);
    if (u <= p[0][0]) return p[0][1];
    for (let i = 1; i < p.length; i++) {
      if (u <= p[i][0]) { const [x0, y0] = p[i - 1], [x1, y1] = p[i]; return x1 === x0 ? y1 : y0 + (y1 - y0) * (u - x0) / (x1 - x0); }
    }
    return p[p.length - 1][1];
  }

  // ---------- 16-segment glyphs (the same tables as tools/ui_segments.py) ----------
  const SEG16 = {
    a1: [[6,4],[19,4],[16,10],[10,10]], a2: [[21,4],[34,4],[30,10],[24,10]],
    b: [[36,6],[36,32],[31,30],[31,10]], c: [[36,38],[36,64],[31,60],[31,40]],
    d1: [[6,66],[19,66],[16,60],[10,60]], d2: [[21,66],[34,66],[30,60],[24,60]],
    e: [[4,38],[4,64],[9,60],[9,40]], f: [[4,6],[4,32],[9,30],[9,10]],
    g1: [[8,35],[10,32],[18,32],[19,35],[18,38],[10,38]], g2: [[21,35],[22,32],[30,32],[32,35],[30,38],[22,38]],
    h: [[11,10],[17,10],[20,31],[17,31]], i: [[29,10],[23,10],[20,31],[23,31]],
    j: [[11,60],[17,60],[20,39],[17,39]], k: [[29,60],[23,60],[20,39],[23,39]],
    l: [[19,38],[21,38],[21,62],[19,62]], m: [[19,8],[21,8],[21,32],[19,32]],
  };
  const SEG_ORDER = ["a1", "a2", "b", "c", "d1", "d2", "e", "f", "g1", "g2", "h", "i", "j", "k", "l", "m"];
  const CHAR16 = {
    " ": "", "-": "g1g2", "/": "ij", "(": "fe", ")": "bc", "'": "m", ".": "l",
    "0": "a1a2bcd1d2efij", "1": "bcm", "2": "a1a2bg1g2ed1d2", "3": "a1a2bcd1d2g2", "4": "fg1g2bc",
    "5": "a1a2fg1g2cd1d2", "6": "a1a2fg1g2ced1d2", "7": "a1a2bc", "8": "a1a2bcd1d2efg1g2", "9": "a1a2bcd1d2fg1g2",
    A: "a1a2bcefg1g2", B: "a1a2bcd1d2mlg1g2", C: "a1a2fed1d2", D: "a1a2bcd1d2ml", E: "a1a2fed1d2g1", F: "a1a2feg1",
    G: "a1a2fed1d2cg2", H: "febcg1g2", I: "a1a2d1d2ml", J: "bcd1d2e", K: "feg1hk", L: "fed1d2", M: "febchi",
    N: "febchk", O: "a1a2bcd1d2ef", P: "a1a2bfeg1g2", Q: "a1a2bcd1d2efk", R: "a1a2bfeg1g2k", S: "a1a2fg1g2cd1d2",
    T: "a1a2ml", U: "bcd1d2ef", V: "efjk", W: "efbcjkhi", X: "hijk", Y: "him", Z: "a1a2d1d2ij",
  };
  // One glyph at the knob's centre-square: lit segments in `lit`, the rest in `dark` (colours as css strings).
  function drawGlyph(ctx, cx, cy, H, ch, lit, dark) {
    const W = H * 40 / 70, x0 = cx - W / 2, y0 = cy - H / 2;
    const on = new Set((CHAR16[ch] || "").match(/a[12]|d[12]|g[12]|[a-m]/g) || []);
    for (const name of SEG_ORDER) {
      ctx.beginPath();
      SEG16[name].forEach(([x, y], i) => { const X = x0 + x * W / 40, Y = y0 + y * H / 70; i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); });
      ctx.closePath(); ctx.fillStyle = on.has(name) ? lit : dark; ctx.fill();
    }
  }

  // Knob at (0,0)-(S,S). Value arc is always drawn; body, track, pointer and outline follow P.
  function drawKnob(ctx, S, t, bi, th, P, st) {
    st = st || {};
    const c = S / 2, rOut = c - 1, rIn = c - Math.max(4, S * 0.1);
    const mid = (rIn + rOut) / 2, w = rOut - rIn;
    if (P.track) drawArc(ctx, c, c, mid, w, -SWEEP / 2, SWEEP / 2, css(th.track));
    const a = -SWEEP / 2 + SWEEP * t;
    if (bi) { if (Math.abs(t - 0.5) > 0.002) drawArc(ctx, c, c, mid, w, Math.min(0, a), Math.max(0, a), css(th.accent)); }
    else if (t > 0.002) drawArc(ctx, c, c, mid, w, -SWEEP / 2, a, css(th.accent));
    const bodyR = rIn - Math.max(3, S * 0.07), faceR = bodyR - Math.max(1.5, S * 0.035);
    const body = argb(th.body), outl = argb(th.outline);
    const shc = th.shadow ? argb(th.shadow) : outl;   // the drop shadow's colour
    if (P.body) {
      if (st.shadow && P.outline) {
        ctx.beginPath(); ctx.fillStyle = cssA(shc.slice(0, 3).concat(120)); ctx.arc(c, c + st.shadow, bodyR + 1, 0, Math.PI * 2); ctx.fill();
      }
      ctx.beginPath(); ctx.fillStyle = css(th.body); ctx.arc(c, c, bodyR, 0, Math.PI * 2); ctx.fill();
      ctx.beginPath(); ctx.fillStyle = css(th.body); ctx.arc(c, c, faceR, 0, Math.PI * 2); ctx.fill();
      if (st.cap) {
        // Taper: the slope from the face to a flat top. Mirrors the renderer: shade, invert, and the custom curve.
        const cp = st.cap, capR = faceR * cp.size, shade = cp.shade;
        const bodyLight = mixA(body, WHITE, 0.15);
        let lit = mixA(body, bodyLight, 0.25 + 0.6 * shade), dark = mixA(body, BLACK, 0.15 + 0.75 * shade);
        if (cp.invert) [lit, dark] = [dark, lit];
        if (cp.curve && cp.curve.length >= 2) {
          const N = 28;   // the curve drawn as thin rings, dark to light
          for (let i = 0; i < N; i++) {
            const u0 = i / N, u1 = (i + 1) / N;
            const r0 = capR + (faceR - capR) * u0, r1 = capR + (faceR - capR) * u1;
            ctx.beginPath(); ctx.strokeStyle = cssA(mixA(dark, lit, curveAt(cp.curve, (u0 + u1) / 2)));
            ctx.lineWidth = r1 - r0 + 0.6; ctx.arc(c, c, (r0 + r1) / 2, 0, Math.PI * 2); ctx.stroke();
          }
        } else {
          const g = ctx.createLinearGradient(c - faceR, c - faceR, c + faceR, c + faceR);
          g.addColorStop(0, cssA(lit)); g.addColorStop(1, cssA(dark));
          ctx.beginPath(); ctx.strokeStyle = g; ctx.lineWidth = faceR - capR; ctx.arc(c, c, (faceR + capR) / 2, 0, Math.PI * 2); ctx.stroke();
        }
        const sec = th.secondary ? argb(th.secondary) : body;
        const secLight = th.secondary ? mixA(sec, WHITE, 0.15) : bodyLight;
        const top = ctx.createLinearGradient(0, c - capR, 0, c + capR);
        top.addColorStop(0, cssA(mixA(sec, secLight, 0.35))); top.addColorStop(1, cssA(sec));
        ctx.beginPath(); ctx.fillStyle = top; ctx.arc(c, c, capR, 0, Math.PI * 2); ctx.fill();
        if (P.outline) { ctx.beginPath(); ctx.strokeStyle = cssA(outl.slice(0, 3).concat(150)); ctx.lineWidth = 0.75; ctx.arc(c, c, capR - 0.375, 0, Math.PI * 2); ctx.stroke(); }
      }
      if (st.highlight) {
        // The lit band, centred on hlAngle (radians from 12 o'clock) when set; the kit's own band otherwise.
        const set = st.hlAngle !== undefined, hc = set ? st.hlAngle : -1.3;
        const a0 = canvasAng(set ? hc - 0.9 : -2.2), a1 = canvasAng(set ? hc + 0.9 : -0.4);
        if (!st.hlFade) {
          ctx.beginPath(); ctx.strokeStyle = th.highlight ? css(th.highlight) : "rgba(255,255,255,0.5)"; ctx.lineWidth = st.highlight;
          ctx.arc(c, c, bodyR - st.highlight / 2, a0, a1); ctx.stroke();
        } else {
          // Faded ends: 24 slices, each one's alpha falling off towards both ends (as the renderer does).
          const hcol = th.highlight ? argb(th.highlight) : [255, 255, 255, 128], N = 24;
          for (let i = 0; i < N; i++) {
            const s0 = i / N, s1 = (i + 1) / N, f = 1 - st.hlFade * Math.abs(s0 + s1 - 1) ** 2;
            ctx.beginPath(); ctx.strokeStyle = cssA(hcol.slice(0, 3).concat(Math.round(hcol[3] * f))); ctx.lineWidth = st.highlight;
            ctx.arc(c, c, bodyR - st.highlight / 2, a0 + (a1 - a0) * s0, a0 + (a1 - a0) * s1); ctx.stroke();
          }
        }
      }
      if (P.outline) {
        ctx.beginPath(); ctx.strokeStyle = css(th.outline); ctx.lineWidth = st.outline_w || 1;
        ctx.arc(c, c, bodyR - (st.outline_w || 1) / 2, 0, Math.PI * 2); ctx.stroke();
      }
      if (st.ridges) {
        const [n, len] = [st.ridges.count, st.ridges.length];
        ctx.strokeStyle = cssA(argb(th.outline).slice(0, 3).concat(190)); ctx.lineWidth = 1.4; ctx.lineCap = "round";
        for (let i = 0; i < n; i++) {
          const an = 2 * Math.PI * i / n;
          ctx.beginPath();
          ctx.moveTo(c + Math.sin(an) * (bodyR - len), c - Math.cos(an) * (bodyR - len));
          ctx.lineTo(c + Math.sin(an) * (bodyR - 0.5), c - Math.cos(an) * (bodyR - 0.5)); ctx.stroke();
        }
      }
    }
    if (P.pointer) {
      // Same geometry as the renderer: length (fraction of the face) and offset (px along the radius).
      // Length is measured from the outside edge: the tip stays at the rim, the inner end moves (as the renderer does).
      const scale = st.pLen ?? 1, tip = faceR - 2, base = tip - (tip - faceR * 0.38) * scale, off = st.pOff ?? 0;
      const r0 = Math.max(0, base + off), r1 = Math.max(r0, tip + off);
      const px0 = c + Math.sin(a) * r0, py0 = c - Math.cos(a) * r0;
      const px1 = c + Math.sin(a) * r1, py1 = c - Math.cos(a) * r1;
      ctx.beginPath(); ctx.strokeStyle = css(th.pointer); ctx.lineWidth = Math.max(2.5, faceR * 0.11); ctx.lineCap = "round";
      ctx.moveTo(px0, py0); ctx.lineTo(px1, py1); ctx.stroke();
    }
    if (st.glyphs && st.glyphs.length) {
      // A 16-segment value: the glyph for this value at the centre, sized by valueSize (value i of n at t = i/(n-1)).
      const n = st.glyphs.length, ch = st.glyphs[Math.min(n - 1, Math.round(t * (n - 1)))];
      drawGlyph(ctx, S / 2, S / 2, st.valueSize ?? 22, ch, st.glyphLit || "rgb(255,74,58)", st.glyphDark || "rgb(58,20,16)");
    }
    if (st.valueText) drawValueText(ctx, S, st);
  }
  // The parameter's value, centred on the knob (a preview of the number the MPC shows there).
  function drawValueText(ctx, S, st) {
    const c = S / 2;
    // The MPC's font height is the line height (ascent + descent), 1.521 em for Titillium Web, so the CSS size is
    // smaller than valueSize; the layout editor and tools/gen_ui.py use the same rule.
    ctx.font = `${(st.valueSize ?? 22) / VALUE_FONT_EM}px "Titillium Web", system-ui, sans-serif`; ctx.fillStyle = st.valueColour ? css(st.valueColour) : "#ffffff";
    ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(st.valueText, c, c);
  }

  // Fader at (0,0)-(248,36): track, value fill, cap.
  function drawFader(ctx, t, th, bi, P, st) {
    st = st || {};
    const from = 11, to = 237, mid = 18;
    if (P.track) { ctx.fillStyle = css(th.track); roundRect(ctx, from - 4, mid - 4, to - from + 8, 8, 4); }
    const x = from + (to - from) * t;
    const c0 = bi ? (from + to) / 2 : from - 2;   // unipolar fills from the left; bipolar from the centre
    ctx.fillStyle = css(th.accent); roundRect(ctx, Math.min(c0, x), mid - 2, Math.abs(x - c0) + (bi ? 0 : 2), 4, 2);
    if (P.thumb) {
      if (st.shadow && P.outline) { ctx.fillStyle = cssA(argb(th.outline).slice(0, 3).concat(110)); roundRect(ctx, x - 11, mid - 15 + st.shadow, 22, 30, 5); }
      ctx.fillStyle = css(th.thumb); roundRect(ctx, x - 11, mid - 15, 22, 30, 5);
      if (st.highlight) { ctx.fillStyle = "rgba(255,255,255,0.5)"; roundRect(ctx, x - 9, mid - 13, 18, st.highlight, 1); }
      if (P.outline) { ctx.strokeStyle = css(th.outline); ctx.lineWidth = st.outline_w || 1; strokeRoundRect(ctx, x - 11, mid - 15, 22, 30, 5); }
      ctx.fillStyle = css(th.accent); ctx.fillRect(x - 0.7, mid - 6, 1.4, 12);
    }
  }

  function drawSwitch(ctx, on, th, P, st) {
    st = st || {};
    const w = 64, h = 32;
    if (P.track) {
      ctx.fillStyle = on ? css(th.accent) : css(th.track); roundRect(ctx, 1, 1, w - 2, h - 2, (h - 2) / 2);
      if (st.highlight) { ctx.fillStyle = "rgba(255,255,255,0.45)"; roundRect(ctx, 4, 2, w - 8, st.highlight, Math.min(st.highlight / 2, (h - 2) / 2)); }
    }
    if (P.outline) { ctx.strokeStyle = css(th.outline); ctx.lineWidth = st.outline_w || 1; strokeRoundRect(ctx, 1.5, 1.5, w - 3, h - 3, (h - 3) / 2); }
    if (P.thumb) {
      const r = (h - 4) / 2 - 1, cx = on ? w - 4 - r : 4 + r;
      if (st.shadow && P.outline) { ctx.beginPath(); ctx.fillStyle = cssA(argb(th.outline).slice(0, 3).concat(110)); ctx.arc(cx, h / 2 + st.shadow, r, 0, Math.PI * 2); ctx.fill(); }
      ctx.beginPath(); ctx.fillStyle = css(th.thumb); ctx.arc(cx, h / 2, r, 0, Math.PI * 2); ctx.fill();
    }
  }

  // Button, as the renderer draws it: roundness, a lit top band (highlight) and a drop shadow.
  // Flat (no highlight and no shadow) it is the kit's button.
  function drawButton(ctx, W, H, on, led, th, P, corner, hl, sh, ow) {
    const rad = Math.max(0, Math.min(corner, (H - 4) / 2));
    let s = sh || 0;
    if (s && on) s = Math.max(1, Math.floor(s / 2));
    const body = argb(th.body), light = argb(th.bodyLight), dark = argb(th.bodyDark), acc = argb(th.accent);
    if (s || hl) {
      if (s && P.outline) {
        ctx.fillStyle = cssA(argb(th.outline).slice(0, 3).concat(110)); roundRect(ctx, 1, 1 + s, W - 2, H - 4, rad);
        ctx.fillStyle = cssA(argb(th.outline).slice(0, 3).concat(70)); roundRect(ctx, 1, 1 + Math.max(1, Math.floor(s / 2)), W - 2, H - 4, rad);
      }
      if (P.body) {
        if (on && !led) { ctx.fillStyle = css(th.accent); }
        else {
          const g = ctx.createLinearGradient(0, 1, 0, H - 3);
          g.addColorStop(0, cssA(mixA(light, WHITE, 0.25))); g.addColorStop(1, cssA(mixA(body, dark, 0.6)));
          ctx.fillStyle = g;
        }
        roundRect(ctx, 1, 1, W - 2, H - 4, rad);
        if (hl) {
          const inset = Math.min(rad * 0.5, (H - 4) / 4);
          ctx.fillStyle = "rgba(255,255,255,0.5)"; roundRect(ctx, 2 + inset, 2, W - 4 - 2 * inset, hl, Math.min(hl / 2, rad));
        }
        if (s) { ctx.fillStyle = cssA(argb(th.outline).slice(0, 3).concat(90)); roundRect(ctx, 3 + rad * 0.3, H - 6, W - 6 - rad * 0.6, 2, 1); }
      }
    } else if (P.body) {
      ctx.fillStyle = on && !led ? css(th.accent) : (() => { const g = ctx.createLinearGradient(0, 1, 0, H - 3); g.addColorStop(0, cssA(light)); g.addColorStop(1, cssA(body)); return g; })();
      roundRect(ctx, 1, 1, W - 2, H - 4, rad);
    }
    if (P.outline) { ctx.strokeStyle = on ? css(th.accent) : cssA(argb(th.outline).slice(0, 3).concat(220)); ctx.lineWidth = ow || 1; strokeRoundRect(ctx, 1.5, 1.5, W - 3, H - 5, rad); }
    if (led) { ctx.fillStyle = on ? css(th.accent) : css(th.ledOff || "ff3a2b2e"); roundRect(ctx, 9, (H - 18) / 2, 6, 18, 3); }
  }
  // Ticks as the library draws them: a 270-degree ring centred on (cx, cy), or a row under a fader's track.
  function drawTicks(ctx, tk, kind, cx, cy) {
    const marks = [];
    if (kind === "knob") {
      const R = tk.radius;
      for (let i = 0; i < tk.count; i++) {
        const a = (-135 + 270 * i / (tk.count - 1)) * Math.PI / 180;
        marks.push([cx + Math.sin(a) * (R - tk.length), cy - Math.cos(a) * (R - tk.length), cx + Math.sin(a) * R, cy - Math.cos(a) * R]);
      }
    } else {
      for (let i = 0; i < tk.count; i++) { const x = 11 + 226 * i / (tk.count - 1); marks.push([x, cy + 0.5, x, cy + tk.length - 0.5]); }
    }
    ctx.strokeStyle = css(tk.colour); ctx.lineWidth = tk.stroke; ctx.lineCap = "round";
    for (const [x0, y0, x1, y1] of marks) { ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke(); }
  }

  // ---------- an element.json -> what the drawing functions take ----------
  // The colours an element draws with: its own, else its base theme's (plus the shades the button derives).
  function theme(f) {
    const c = f.colours || {};
    const acc = f.accent || c.accent || THEME_ACCENT[f.base] || THEME_ACCENT["mpc-red"];
    const pick = k => c[k] || GREY[k];
    const body = pick("body");
    return { accent: acc, body, track: pick("track"), pointer: pick("pointer"), thumb: pick("thumb"), outline: pick("outline"),
             secondary: c.secondary, highlight: c.highlight, shadow: c.shadow,   // knob-only colours, unset unless the element sets them
             bodyLight: hexOf(mixA(argb(body), WHITE, 0.15)), bodyDark: hexOf(mixA(argb(body), BLACK, 0.35)),
             ledOff: hexOf(mixA(argb(acc), argb(body), 0.78)) };
  }
  // Which parts are drawn: all of them, except those the element switches off.
  function parts(f) {
    return Object.fromEntries(["body", "track", "pointer", "thumb", "outline"].map(k => [k, !(f.parts && f.parts[k] === false)]));
  }
  // The style settings the drawing functions read. opts.valueText: the number to draw at a knob's centre, if any.
  function style(f, opts = {}) {
    const isKnob = f.type === "knob", depth = isKnob || f.type === "fader" || f.type === "switch";
    return { shadow: depth ? f.shadow : undefined, highlight: depth ? f.highlight : undefined,
             outline_w: f.outlineWidth, ridges: f.ridges, cap: f.cap,
             hlAngle: f.highlightAngle !== undefined ? f.highlightAngle * Math.PI / 180 : undefined,
             hlFade: isKnob ? f.highlightFade : undefined,
             pLen: f.pointerLength, pOff: f.pointerOffset,
             valueSize: f.valueSize, valueColour: f.valueColour,
             glyphs: isKnob && f.valueStyle === "segments" && f.glyphs ? f.glyphs : undefined,
             glyphLit: isKnob && f.valueColour ? css(f.valueColour) : undefined,
             glyphDark: isKnob && f.valueColour ? cssA(mixA(argb(f.valueColour), BLACK, 0.85)) : undefined,
             valueText: opts.valueText };
  }
  // A knob element at value t as an image: { url, size (the knob), box (the picture, with ticks and shadow), off }.
  // Draw the picture at (knob x - off, knob y - off), box wide, so the knob lands where the MPC puts it.
  const pictures = new Map();
  function knobPicture(f, t, bi) {
    const key = JSON.stringify(f) + "|" + t.toFixed(3) + "|" + (bi ? 1 : 0);
    if (pictures.has(key)) return pictures.get(key);
    const S = f.size || 90, tk = f.ticks && f.ticks.radius ? f.ticks : null;
    const box = Math.max(S, tk ? 2 * tk.radius : 0) + 2 * ((f.shadow || 0) + 2), Z = 2;   // drawn at 2x for a sharp picture
    const cv = document.createElement("canvas");
    cv.width = cv.height = Math.ceil(box * Z);
    const ctx = cv.getContext("2d");
    ctx.setTransform(Z, 0, 0, Z, 0, 0);
    if (tk) drawTicks(ctx, tk, "knob", box / 2, box / 2);
    ctx.save(); ctx.translate((box - S) / 2, (box - S) / 2);
    drawKnob(ctx, S, t, bi, theme(f), parts(f), style(f));
    ctx.restore();
    const out = { url: cv.toDataURL(), size: S, box, off: (box - S) / 2 };
    if (pictures.size > 300) pictures.clear();
    pictures.set(key, out);
    return out;
  }

  return { THEME_ACCENT, GREY, argb, cssA, css, mixA, hexOf, WHITE, BLACK, SWEEP, canvasAng, drawArc, roundRect, strokeRoundRect,
           curveAt, SEG16, SEG_ORDER, CHAR16, drawGlyph, drawKnob, drawValueText, drawFader, drawSwitch, drawButton, drawTicks,
           theme, parts, style, knobPicture, VALUE_FONT_EM, valueBoxH };
})();
