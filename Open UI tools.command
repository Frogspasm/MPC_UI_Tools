#!/bin/sh
# Starts the MPC UI tools server (tools/ui_server.py) and opens the layout editor and element designer.
# Leave this window open while you work; close it to stop the server.
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then exec python3 tools/ui_server.py "$@"; fi
exec python tools/ui_server.py "$@"
