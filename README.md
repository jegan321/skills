# Skills

Repository to keep track of my personal AI agent skills.

Only skills in the `skills` directory are ready to be used by coding agents. The `wip` directory skills should not be discoverable by agents. Once they are completed they will be moved to `skills`.

## Scripts

Run these commands from the repository root.

### Link skills

Symlinks `global.md` to `~/.codex/AGENTS.md` and each skill in `skills/` into
`~/.agents/skills`, making them available to Codex across local projects.
Existing links to the same sources are left unchanged; conflicting files,
directories, or links are reported without being overwritten.

```sh
./link-skills.sh
```

### Unlink skill

Removes one skill's repository-managed symlink from `~/.agents/skills`. The skill name is required:

```sh
./unlink-skill.sh skill-name
```

### Add skill

Prompts for a skill name and description and creates the standard boilerplate in `skills/`. Run the link script separately when the skill is ready to be made available to Codex:

```sh
./add-skill.sh
```

### Skills report

Produces an HTML report explaining each skill and opens it in the default browser.

```sh
./build_report.py
```
