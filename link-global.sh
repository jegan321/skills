#!/usr/bin/env bash

# Make this repository's global agent instructions available to Codex across
# all local projects by symlinking them into the user's configuration directory.

set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
source_file="$script_dir/global.md"

usage() {
  printf 'Usage: %s\n' "${0##*/}" >&2
}

if (($# != 0)); then
  usage
  exit 2
fi

# The override keeps tests and one-off installations isolated from the real
# home directory.
codex_target_dir=${CODEX_TARGET_DIR:-"$HOME/.codex"}
agents_link_path="$codex_target_dir/AGENTS.md"

if [[ ! -f "$source_file" ]]; then
  printf 'error: global instructions not found: %s\n' "$source_file" >&2
  exit 1
fi

mkdir -p -- "$codex_target_dir"

# Preserve every existing file, directory, or symlink that points elsewhere.
if [[ -e "$agents_link_path" || -L "$agents_link_path" ]]; then
  if [[ "$agents_link_path" -ef "$source_file" ]]; then
    printf 'unchanged  %s -> %s\n' "$agents_link_path" "$source_file"
    exit 0
  fi

  printf 'conflict   AGENTS.md already exists at %s\n' "$agents_link_path" >&2
  exit 1
fi

# Use an absolute source path so the link remains valid regardless of the
# current working directory or how Codex discovers it.
ln -s -- "$source_file" "$agents_link_path"
printf 'linked     %s -> %s\n' "$agents_link_path" "$source_file"
