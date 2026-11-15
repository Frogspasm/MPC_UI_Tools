#!/usr/bin/env python3
"""Serve the UI tools (layout editor, element designer) from this repo on your own computer.

Opened this way, the tools read and save the element library (ui-library/) and the page templates (ui-pages/)
through this server, so the browser never has to be given those folders and never "loses" them on a reload.
Both tools share one web address, so a save in the designer reaches an open layout editor at once.

    python tools/ui_server.py              # starts the server and opens both tools in the browser
    python tools/ui_server.py --no-browser
    python tools/ui_server.py --port 8770

Or double-click "Open UI tools.bat" (Windows) / "Open UI tools.command" (macOS) in the repo folder.
Stop it with Ctrl+C or by closing its window.

Safety: it listens on 127.0.0.1 only (not reachable from other machines), answers only requests addressed to
127.0.0.1/localhost (so other web sites cannot reach it through DNS tricks), sends no CORS headers (so other web
pages cannot call it), and writes only .json files inside ui-library/ and ui-pages/. Everything else is read only.
"""
import argparse
import http.server
import json
import os
import re
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_ID = "mpc-ui-tools"
WRITABLE = ("ui-library", "ui-pages")     # the only folders the tools may write in
MAX_BODY = 4 * 1024 * 1024                # an element or a page template is a few kB
PART_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,63}$")
DEFAULT_PORT = 8770

INDEX = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MPC UI tools</title>
<style>body{font:15px system-ui,sans-serif;background:#1c1b1f;color:#e6e4ea;margin:40px auto;max-width:560px;padding:0 16px}
a{display:block;padding:14px 16px;margin:10px 0;border:1px solid #3a383f;border-radius:8px;color:#fff;text-decoration:none;background:#242327}
a:hover{border-color:#d31145}small{color:#8d8a94}</style>
<h1>MPC UI tools</h1>
<a href="tools/ui_editor.html">Layout editor<br><small>Pages, controls, Q-Links, page templates</small></a>
<a href="tools/ui_designer.html">Element designer<br><small>Knobs, faders, switches, buttons for ui-library</small></a>
<p><small>Served from %s. The library and templates are saved straight into the repo.</small></p>
"""


def safe_rel(path, for_write):
    """A repo-relative path from the client, checked: plain names only, no "..", and for writes inside WRITABLE."""
    parts = [p for p in path.replace("\\", "/").split("/") if p]
    if not parts or any(not PART_RE.match(p) or p in (".", "..") for p in parts):
        return None
    if for_write and (parts[0] not in WRITABLE or len(parts) < 2 or not parts[-1].lower().endswith(".json")):
        return None
    if not for_write and parts[0] not in WRITABLE:
        return None
    full = os.path.realpath(os.path.join(ROOT, *parts))
    base = os.path.realpath(os.path.join(ROOT, parts[0]))
    if full != base and not full.startswith(base + os.sep):
        return None
    return full


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *args):   # quiet: only writes and errors
        status = str(args[1]) if fmt.startswith('"%s"') and len(args) > 1 else ""
        if self.command != "GET" or not fmt.startswith('"%s"') or status[:1] in "45":
            sys.stderr.write("ui_server: %s\n" % (fmt % args))

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")   # the tools always see the files as they are now
        super().end_headers()

    def host_ok(self):
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        if host in ("127.0.0.1", "localhost"):
            return True
        self.send_error(403, "Use http://127.0.0.1")
        return False

    def reply(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.host_ok():
            return
        url = urllib.parse.urlsplit(self.path)
        q = urllib.parse.parse_qs(url.query)
        if url.path == "/api/info":
            return self.reply(200, {"server": SERVER_ID, "version": 1, "writable": list(WRITABLE)})
        if url.path == "/api/list":
            # The folders and files in one folder of ui-library/ or ui-pages/ (missing folder: exists false).
            full = safe_rel((q.get("dir") or [""])[0], for_write=False)
            if not full:
                return self.reply(400, {"error": "not a library or templates folder"})
            if not os.path.isdir(full):
                return self.reply(200, {"exists": False, "entries": []})
            entries = []
            for name in sorted(os.listdir(full)):
                if name.startswith("."):
                    continue
                p = os.path.join(full, name)
                entries.append({"name": name, "kind": "directory" if os.path.isdir(p) else "file"})
            return self.reply(200, {"exists": True, "entries": entries})
        if url.path == "/":
            body = (INDEX % ROOT).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()

    def do_HEAD(self):
        if self.host_ok():
            super().do_HEAD()

    def do_PUT(self):
        # PUT /api/file?path=ui-library/<name>/element.json  (body: the file). Creates the folders it needs.
        if not self.host_ok():
            return
        url = urllib.parse.urlsplit(self.path)
        if url.path != "/api/file":
            return self.reply(404, {"error": "no such endpoint"})
        if "json" not in (self.headers.get("Content-Type") or ""):
            return self.reply(415, {"error": "send application/json"})
        full = safe_rel((urllib.parse.parse_qs(url.query).get("path") or [""])[0], for_write=True)
        if not full:
            return self.reply(400, {"error": "only .json files inside %s can be written" % " or ".join(WRITABLE)})
        try:
            n = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            n = -1
        if not 0 < n <= MAX_BODY:
            return self.reply(413, {"error": "body missing or too large"})
        data = self.rfile.read(n)
        try:
            json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            return self.reply(400, {"error": "not valid JSON: %s" % e})
        os.makedirs(os.path.dirname(full), exist_ok=True)
        tmp = full + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, full)   # never a half-written file
        self.log_message('saved %s (%d bytes)', os.path.relpath(full, ROOT).replace(os.sep, "/"), len(data))
        return self.reply(200, {"ok": True})

    def do_POST(self):
        self.reply(405, {"error": "use PUT"})


def ours(port):
    """True when a UI tools server from this repo already answers on the port."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/info" % port, timeout=1) as r:
            return json.load(r).get("server") == SERVER_ID
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(description="Serve the MPC UI tools from this repo on 127.0.0.1.")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help="port to use (default %d; the next free one if busy)" % DEFAULT_PORT)
    ap.add_argument("--no-browser", action="store_true", help="do not open the tools in the browser")
    a = ap.parse_args()

    server = None
    for port in range(a.port, a.port + 20):
        if ours(port):
            print("The UI tools are already running at http://127.0.0.1:%d/" % port)
            if not a.no_browser:
                webbrowser.open("http://127.0.0.1:%d/tools/ui_editor.html" % port)
            return 0
        try:
            server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if server is None:
        print("ui_server: no free port between %d and %d." % (a.port, a.port + 19), file=sys.stderr)
        return 1
    port = server.server_address[1]
    base = "http://127.0.0.1:%d/" % port
    print("MPC UI tools: %s" % base)
    print("  Layout editor:    %stools/ui_editor.html" % base)
    print("  Element designer: %stools/ui_designer.html" % base)
    print("Saves go into %s and %s. Leave this window open while you work; Ctrl+C stops it."
          % (os.path.join(ROOT, "ui-library"), os.path.join(ROOT, "ui-pages")))
    if not a.no_browser:
        def open_tools():
            webbrowser.open(base + "tools/ui_editor.html")
            webbrowser.open(base + "tools/ui_designer.html")
        threading.Timer(0.5, open_tools).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
