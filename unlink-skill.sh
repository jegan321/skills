#!/usr/bin/env bash

# Remove one repository skill from the user's personal skills directory.

set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
repo_dir=$script_dir
source_dir="$repo_dir/skills"

usage() {
  printf 'Usage: %s <skill-name>\n' "${0##*/}" >&2
}

if (($# != 1)); then
  usage
  exit 2
fi

skill_name=$1
if [[ ! "$skill_name" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || ((${#skill_name} > 64)); then
  printf 'error: invalid skill name: %s\n' "$skill_name" >&2
  exit 1
fi

target_dir=${SKILLS_TARGET_DIR:-"$HOME/.agents/skills"}
link_path="$target_dir/$skill_name"
expected_target="$source_dir/$skill_name"

if [[ ! -L "$link_path" ]]; then
  printf 'error: skill symlink not found: %s\n' "$link_path" >&2
  exit 1
fi

# Only remove links created for this repository. Preserve a same-named link to
# any other location just as link-skills.sh preserves naming conflicts.
link_target=$(readlink "$link_path")
if [[ -e "$link_path" ]]; then
  if [[ ! "$link_path" -ef "$expected_target" ]]; then
    printf 'error: symlink points outside this repository: %s -> %s\n' \
      "$link_path" "$link_target" >&2
    exit 1
  fi
elif [[ "$link_target" != "$expected_target" ]]; then
  printf 'error: symlink points outside this repository: %s -> %s\n' \
    "$link_path" "$link_target" >&2
  exit 1
fi

unlink "$link_path"
printf 'unlinked   %s\n' "$skill_name"
