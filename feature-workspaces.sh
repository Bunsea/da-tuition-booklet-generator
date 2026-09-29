#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACES="$ROOT/feature-workspaces"

usage() {
    cat <<'EOF'
Usage:
  ./feature-workspaces.sh new NAME    Create an isolated feature folder
  ./feature-workspaces.sh list        Show feature folders
  ./feature-workspaces.sh run NAME    Start that feature's app

Use short names such as attendance or report-layout. Each feature gets its own
Git branch, app files, local database, and Streamlit port.
EOF
}

command_name="${1:-}"
feature_name="${2:-}"

if [[ "$command_name" == "list" ]]; then
    git -C "$ROOT" worktree list
    exit 0
fi

if [[ "$command_name" != "new" && "$command_name" != "run" ]]; then
    usage
    exit 1
fi

if [[ ! "$feature_name" =~ ^[a-z][a-z0-9-]*$ ]]; then
    echo "Choose a name using lowercase letters, numbers, and hyphens, starting with a letter." >&2
    exit 1
fi

target="$WORKSPACES/$feature_name"
branch="feature/$feature_name"

if [[ "$command_name" == "new" ]]; then
    if [[ -e "$target" ]] || git -C "$ROOT" show-ref --verify --quiet "refs/heads/$branch"; then
        echo "That feature already exists: $feature_name" >&2
        exit 1
    fi
    mkdir -p "$WORKSPACES"
    git -C "$ROOT" worktree add -b "$branch" "$target" main

    # These files are local to each workspace and never enter Git.
    for local_file in .env .streamlit/credentials.toml da_tuition.db 'Answer Sheet Template.pdf'; do
        if [[ -f "$ROOT/$local_file" ]]; then
            mkdir -p "$(dirname "$target/$local_file")"
            cp -p "$ROOT/$local_file" "$target/$local_file"
        fi
    done
    if [[ -x "$ROOT/.venv/bin/streamlit" ]]; then
        ln -s "$ROOT/.venv" "$target/.venv"
    fi
    echo "Created $target"
    echo "Open this folder in your coding tool to work on $feature_name."
    exit 0
fi

if [[ ! -d "$target" ]]; then
    echo "Feature folder not found: $feature_name" >&2
    exit 1
fi

# Give each feature a stable port based on its position in the worktree list.
port=8502
while IFS= read -r path; do
    if [[ "$path" == "$target" ]]; then
        break
    fi
    if [[ "$path" == "$WORKSPACES/"* ]]; then
        ((port += 1))
    fi
done < <(git -C "$ROOT" worktree list --porcelain | sed -n 's/^worktree //p')

cd "$target"
if [[ ! -x .venv/bin/streamlit ]]; then
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi
echo "Starting $feature_name at http://localhost:$port"
exec .venv/bin/streamlit run app.py --server.port "$port"
