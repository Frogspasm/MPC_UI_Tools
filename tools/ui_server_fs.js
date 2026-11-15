// Folders of the repo reached through tools/ui_server.py, shaped like the browser's folder handles
// (FileSystemDirectoryHandle), so the layout editor and the element designer use them exactly like a folder
// the user picked, but with no permission to give and nothing to reconnect after a reload.
//
//   if (await UISERVER.available()) libDir = UISERVER.dir("ui-library");
//
// Only the calls the tools use are here: name, kind, entries(), values(), getDirectoryHandle(name, {create}),
// getFileHandle(name, {create}) -> getFile().text() / createWritable().write(text) + close(),
// queryPermission() / requestPermission() (always "granted"). The server writes only .json files inside
// ui-library/ and ui-pages/.
(function () {
  let probe = null;
  // True when this page was opened from tools/ui_server.py (not from a file, nor from another web server).
  function available() {
    if (!probe) probe = (location.protocol === "http:" || location.protocol === "https:")
      ? fetch("/api/info", { cache: "no-store" }).then(r => r.ok ? r.json() : null).then(j => !!(j && j.server === "mpc-ui-tools")).catch(() => false)
      : Promise.resolve(false);
    return probe;
  }
  const enc = p => p.split("/").map(encodeURIComponent).join("/");
  async function list(path) {
    const r = await fetch("/api/list?dir=" + encodeURIComponent(path), { cache: "no-store" });
    if (!r.ok) throw new Error("server: " + ((await r.json().catch(() => ({}))).error || r.status));
    return r.json();
  }
  function notFound(what) { const e = new Error(what + " not found"); e.name = "NotFoundError"; return e; }
  function fileHandle(path, name) {
    return {
      kind: "file", name,
      async getFile() {
        const r = await fetch("/" + enc(path), { cache: "no-store" });
        if (!r.ok) throw notFound(path);
        const text = await r.text();
        return { name, text: async () => text, size: text.length };
      },
      async createWritable() {
        let buf = "";
        return {
          async write(t) { buf += typeof t === "string" ? t : await new Blob([t]).text(); },
          async close() {
            const r = await fetch("/api/file?path=" + encodeURIComponent(path), { method: "PUT", headers: { "Content-Type": "application/json" }, body: buf });
            if (!r.ok) throw new Error("server: " + ((await r.json().catch(() => ({}))).error || r.status));
          },
        };
      },
    };
  }
  function dirHandle(path) {
    const name = path.split("/").pop();
    const self = {
      kind: "directory", name, served: true, path,
      async queryPermission() { return "granted"; },
      async requestPermission() { return "granted"; },
      async *entries() {
        const j = await list(path);
        for (const e of j.entries) yield [e.name, e.kind === "directory" ? dirHandle(path + "/" + e.name) : fileHandle(path + "/" + e.name, e.name)];
      },
      async *values() { for await (const [, h] of self.entries()) yield h; },
      async getDirectoryHandle(n, opt) {
        const j = await list(path);
        if (j.entries.some(e => e.name === n && e.kind === "directory") || (opt && opt.create)) return dirHandle(path + "/" + n);
        throw notFound(n);   // with create, the folder appears when its first file is written
      },
      async getFileHandle(n, opt) {
        const j = await list(path);
        if (j.entries.some(e => e.name === n && e.kind === "file") || (opt && opt.create)) return fileHandle(path + "/" + n, n);
        throw notFound(n);
      },
    };
    return self;
  }
  window.UISERVER = { available, dir: dirHandle };
})();
