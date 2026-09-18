#!/usr/bin/env bash

# Make this repository's global agent instructions and skills available to
# Codex across all local projects by symlinking them into the user's personal
# configuration directories.

set -euo pipefail

# Resolve paths relative to this script instead of the caller's working
# directory, allowing the command to be run from anywhere.
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
repo_dir=$script_dir
source_file="$repo_dir/global.md"
source_dir="$repo_dir/skills"

usage() {
  printf 'Usage: %s [skill-name]\n' "${0##*/}" >&2
}

if (($# > 1)); then
  usage
  exit 2
fi

# Install global instructions in Codex's user-wide configuration directory.
# The override keeps tests and one-off installations isolated from the real
# home directory.
codex_target_dir=${CODEX_TARGET_DIR:-"$HOME/.codex"}
agents_link_path="$codex_target_dir/AGENTS.md"

# Install personal skills in Codex's user-wide directory. The override is
# useful for testing without modifying the real destination.
skills_target_dir=${SKILLS_TARGET_DIR:-"$HOME/.agents/skills"}

# Fail with useful errors instead of creating dangling symlinks if the
# repository is incomplete or a source file was moved.
if [[ ! -f "$source_file" ]]; then
  printf 'error: global instructions not found: %s\n' "$source_file" >&2
  exit 1
fi

if [[ ! -d "$source_dir" ]]; then
  printf 'error: skills directory not found: %s\n' "$source_dir" >&2
  exit 1
fi

# Support fresh Codex installations where either destination does not exist.
mkdir -p -- "$codex_target_dir" "$skills_target_dir"

agents_conflict=0

# Link global instructions on every invocation, before processing skills.
# Preserve every other existing file, directory, or symlink.
if [[ -e "$agents_link_path" || -L "$agents_link_path" ]]; then
  if [[ "$agents_link_path" -ef "$source_file" ]]; then
    printf 'unchanged  %s -> %s\n' "$agents_link_path" "$source_file"
  else
    printf 'conflict   AGENTS.md already exists at %s\n' "$agents_link_path" >&2
    agents_conflict=1
  fi
else
  # Use an absolute source path so the link remains valid regardless of the
  # current working directory or how Codex discovers it.
  ln -s -- "$source_file" "$agents_link_path"
  printf 'linked     %s -> %s\n' "$agents_link_path" "$source_file"
fi

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

if ((agents_conflict > 0 || conflicts > 0)); then
  exit 1
fi
