#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
LAUNCH_DIR=$(pwd)
VENV_DIR="$REPO_ROOT/.venv"
HOST="${VIBE_ORCHESTRATOR_HOST:-127.0.0.1}"
PORT="${VIBE_ORCHESTRATOR_PORT:-8765}"
TARGET_REPO_INPUT="${VIBE_ORCHESTRATOR_TARGET_REPO:-}"
NO_PICKER=0
NO_OPEN=0
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
        --repo)
            TARGET_REPO_INPUT="$2"
            shift 2
            ;;
        --no-install)
            NO_INSTALL=1
            shift
            ;;
        --no-picker)
            NO_PICKER=1
            shift
            ;;
        --no-open)
            NO_OPEN=1
            shift
            ;;
        -h|--help)
            echo "Usage: scripts/start-server.sh [--repo /path/to/project] [--host 127.0.0.1] [--port 8765] [--no-install] [--no-picker] [--no-open]"
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

pick_target_repo() {
    case "$(uname -s)" in
        Darwin)
            if command -v osascript >/dev/null 2>&1; then
                osascript -e 'POSIX path of (choose folder with prompt "Select the repository folder Vibe Orchestrator should work on")'
                return $?
            fi
            ;;
    esac

    if command -v zenity >/dev/null 2>&1; then
        zenity --file-selection --directory --title="Select repository folder"
        return $?
    fi

    if command -v kdialog >/dev/null 2>&1; then
        kdialog --getexistingdirectory "$LAUNCH_DIR" --title "Select repository folder"
        return $?
    fi

    return 2
}

resolve_target_repo() {
    if [ -z "$TARGET_REPO_INPUT" ]; then
        if [ "$NO_PICKER" -eq 1 ]; then
            TARGET_REPO_INPUT="$LAUNCH_DIR"
        else
            set +e
            PICKED_REPO=$(pick_target_repo)
            PICKER_STATUS=$?
            set -e

            if [ "$PICKER_STATUS" -eq 0 ] && [ -n "$PICKED_REPO" ]; then
                TARGET_REPO_INPUT="$PICKED_REPO"
            elif [ "$PICKER_STATUS" -eq 2 ]; then
                echo "No graphical folder picker found; using current directory: $LAUNCH_DIR" >&2
                TARGET_REPO_INPUT="$LAUNCH_DIR"
            else
                echo "No target repository selected." >&2
                exit 1
            fi
        fi
    fi

    case "$TARGET_REPO_INPUT" in
        /*)
            TARGET_REPO_CANDIDATE="$TARGET_REPO_INPUT"
            ;;
        *)
            TARGET_REPO_CANDIDATE="$LAUNCH_DIR/$TARGET_REPO_INPUT"
            ;;
    esac

    if [ ! -d "$TARGET_REPO_CANDIDATE" ]; then
        echo "Target repository folder does not exist: $TARGET_REPO_INPUT" >&2
        exit 1
    fi

    TARGET_REPO=$(CDPATH= cd -- "$TARGET_REPO_CANDIDATE" && pwd)
    printf '%s\n' "$TARGET_REPO"
}

has_ui_shell() {
    if [ -n "${CI:-}" ] || [ -n "${SSH_CLIENT:-}" ] || [ -n "${SSH_TTY:-}" ]; then
        return 1
    fi

    case "$(uname -s)" in
        Darwin)
            command -v open >/dev/null 2>&1
            return $?
            ;;
        *)
            if [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; then
                return 0
            fi
            return 1
            ;;
    esac
}

open_url() {
    URL_TO_OPEN="$1"

    case "$(uname -s)" in
        Darwin)
            if command -v open >/dev/null 2>&1; then
                open "$URL_TO_OPEN" >/dev/null 2>&1 &
                return 0
            fi
            ;;
    esac

    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$URL_TO_OPEN" >/dev/null 2>&1 &
        return 0
    fi

    if command -v gio >/dev/null 2>&1; then
        gio open "$URL_TO_OPEN" >/dev/null 2>&1 &
        return 0
    fi

    return 1
}

open_when_ready() {
    URL_TO_OPEN="$1"
    HEALTH_URL="$URL_TO_OPEN/api/health"

    if [ "$NO_OPEN" -eq 1 ]; then
        return
    fi

    if ! has_ui_shell; then
        echo "No UI shell detected; not opening browser." >&2
        return
    fi

    (
        i=0
        while [ "$i" -lt 60 ]; do
            if command -v curl >/dev/null 2>&1; then
                if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
                    open_url "$URL_TO_OPEN"
                    exit 0
                fi
            elif command -v wget >/dev/null 2>&1; then
                if wget -q -O /dev/null "$HEALTH_URL" >/dev/null 2>&1; then
                    open_url "$URL_TO_OPEN"
                    exit 0
                fi
            else
                sleep 1
                open_url "$URL_TO_OPEN"
                exit 0
            fi
            i=$((i + 1))
            sleep 1
        done
    ) &
}

browser_url() {
    case "$HOST" in
        0.0.0.0)
            printf 'http://127.0.0.1:%s\n' "$PORT"
            ;;
        ::)
            printf 'http://[::1]:%s\n' "$PORT"
            ;;
        *)
            printf 'http://%s:%s\n' "$HOST" "$PORT"
            ;;
    esac
}

TARGET_REPO=$(resolve_target_repo)

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
export VIBE_ORCHESTRATOR_TARGET_REPO="$TARGET_REPO"

BROWSER_URL=$(browser_url)
open_when_ready "$BROWSER_URL"

echo "Starting Vibe Orchestrator on http://$HOST:$PORT"
echo "Target repository: $TARGET_REPO"
exec "$PYTHON_EXE" -m vibe_orchestrator
