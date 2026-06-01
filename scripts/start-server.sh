#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
VENV_DIR="$REPO_ROOT/.venv"
HOST="${VIBE_ORCHESTRATOR_HOST:-127.0.0.1}"
PORT="${VIBE_ORCHESTRATOR_PORT:-8765}"
NO_INSTALL=0

while [ "$#" -gt 0 ]; do
    case "$1" in
        --host)
            HOST="$2"
            shift 2
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --no-install)
            NO_INSTALL=1
            shift
            ;;
        -h|--help)
            echo "Usage: scripts/start-server.sh [--host 127.0.0.1] [--port 8765] [--no-install]"
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

find_venv_python() {
    if [ -x "$VENV_DIR/bin/python" ]; then
        printf '%s\n' "$VENV_DIR/bin/python"
        return 0
    fi

    if [ -x "$VENV_DIR/Scripts/python.exe" ]; then
        printf '%s\n' "$VENV_DIR/Scripts/python.exe"
        return 0
    fi

    return 1
}

create_venv() {
    if command -v python3 >/dev/null 2>&1; then
        python3 -m venv "$VENV_DIR"
        return
    fi

    if command -v python >/dev/null 2>&1; then
        python -m venv "$VENV_DIR"
        return
    fi

    echo "Python was not found. Install Python 3.11+ and try again." >&2
    exit 1
}

cd "$REPO_ROOT"

if ! PYTHON_EXE=$(find_venv_python); then
    echo "Creating virtual environment in $VENV_DIR"
    create_venv
    PYTHON_EXE=$(find_venv_python)
fi

if [ "$NO_INSTALL" -eq 0 ]; then
    echo "Installing Vibe Orchestrator into the local virtual environment"
    "$PYTHON_EXE" -m pip install -e "$REPO_ROOT"
fi

export VIBE_ORCHESTRATOR_HOST="$HOST"
export VIBE_ORCHESTRATOR_PORT="$PORT"

echo "Starting Vibe Orchestrator on http://$HOST:$PORT"
exec "$PYTHON_EXE" -m vibe_orchestrator
