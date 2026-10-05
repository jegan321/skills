#!/usr/bin/env bash

# Make this repository's skills available to Codex across all local projects
# by symlinking them into the user's personal skills directory.

set -euo pipefail

# Resolve paths relative to this script instead of the caller's working
# directory, allowing the command to be run from anywhere.
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
repo_dir=$script_dir
source_dir="$repo_dir/skills"

usage() {
  printf 'Usage: %s [skill-name]\n' "${0##*/}" >&2
}

if (($# > 1)); then
  usage
  exit 2
fi

# Install personal skills in Codex's user-wide directory. The override is
# useful for testing without modifying the real destination.
skills_target_dir=${SKILLS_TARGET_DIR:-"$HOME/.agents/skills"}

# Fail with useful errors instead of creating dangling symlinks if the
# repository is incomplete or a source file was moved.
if [[ ! -d "$source_dir" ]]; then
  printf 'error: skills directory not found: %s\n' "$source_dir" >&2
  exit 1
fi

# Support fresh Codex installations where the destination does not exist.
mkdir -p -- "$skills_target_dir"

# Track results so the final summary shows whether every selected skill was
# linked.
linked=0
unchanged=0
conflicts=0

# Avoid iterating over a literal "*" when the source directory is empty.
shopt -s nullglob

if (($# == 1)); then
  skill_name=$1

  if [[ ! "$skill_name" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || ((${#skill_name} > 64)); then
    printf 'error: invalid skill name: %s\n' "$skill_name" >&2
    exit 1
  fi

  skill_dirs=("$source_dir/$skill_name")

  if [[ ! -d "${skill_dirs[0]}" || ! -f "${skill_dirs[0]}/SKILL.md" ]]; then
    printf 'error: skill not found: %s\n' "$skill_name" >&2
    exit 1
  fi
else
  skill_dirs=("$source_dir"/*)
fi

# Treat each immediate child containing SKILL.md as an installable skill.
for skill_dir in "${skill_dirs[@]}"; do
  [[ -d "$skill_dir" && -f "$skill_dir/SKILL.md" ]] || continue

  skill_name=${skill_dir##*/}
  link_path="$skills_target_dir/$skill_name"

  # Leave a correctly linked skill unchanged. Preserve any different file,
  # directory, or symlink with the same name and report it as a conflict.
  if [[ -e "$link_path" || -L "$link_path" ]]; then
    if [[ "$link_path" -ef "$skill_dir" ]]; then
      printf 'unchanged  %s\n' "$skill_name"
      ((unchanged += 1))
    else
      printf 'conflict   %s already exists at %s\n' "$skill_name" "$link_path" >&2
      ((conflicts += 1))
    fi
    continue
  fi

  # Use an absolute symlink so skills remain available from every project.
  ln -s -- "$skill_dir" "$link_path"
  printf 'linked     %s -> %s\n' "$skill_name" "$skill_dir"
  ((linked += 1))
done

printf '\nLinked: %d; unchanged: %d; conflicts: %d\n' \
  "$linked" "$unchanged" "$conflicts"

if ((conflicts > 0)); then
  exit 1
fi
