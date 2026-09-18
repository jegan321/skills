#!/usr/bin/env bash

set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
repo_dir=$script_dir
skills_dir="$repo_dir/skills"

printf 'Skill name: '
IFS= read -r skill_name

if [[ ! "$skill_name" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || ((${#skill_name} > 64)); then
  printf 'error: name must be at most 64 characters and use lowercase letters, digits, and single hyphens\n' >&2
  exit 1
fi

skill_dir="$skills_dir/$skill_name"
if [[ -e "$skill_dir" || -L "$skill_dir" ]]; then
  printf 'error: skill already exists: %s\n' "$skill_dir" >&2
  exit 1
fi

printf 'Description: '
IFS= read -r description

if [[ -z "$description" ]]; then
  printf 'error: description cannot be empty\n' >&2
  exit 1
fi

# YAML single-quoted values escape apostrophes by doubling them.
yaml_description=${description//\'/\'\'}

mkdir -p -- "$skill_dir/agents"

printf '%s\n' \
  '---' \
  "name: $skill_name" \
  "description: '$yaml_description'" \
  'metadata:' \
  '  original-author: "John Egan"' \
  '---' \
  '' \
  'TODO: Add skill content here' > "$skill_dir/SKILL.md"

printf '%s\n' \
  'policy:' \
  '  allow_implicit_invocation: false' > "$skill_dir/agents/openai.yaml"

printf 'Skill boilerplate created\n'
