---
name: merge-main
description: Merge the latest changes from main into the current Git branch.
metadata:
  original-author: "John Egan"
---

# Merge Main

1. **Establish the source and current branches.** Use `main` as the source branch unless the user specifies another branch. Read the current branch with `git branch --show-current`. If the current branch is `main` or the specified source branch, stop and tell the user there is nothing to merge into this branch. If HEAD is detached, stop and ask which destination branch to use.

2. **Check the working state.** Inspect `git status`. Do not overwrite, discard, or automatically commit unrelated local changes. If local changes or an existing merge/rebase prevent this merge, explain the blocker before proceeding.

3. **Fetch the latest source branch.** Use the source branch's configured remote, falling back to `origin`. If the remote is ambiguous or unavailable, ask the user which remote to use. Run `git fetch <remote> <source-branch>` and proceed only if it succeeds.

4. **Merge into the current branch.** Run `git merge --no-edit FETCH_HEAD` to merge the fetched source commit without switching branches. If the merge fails, inspect the cause; do not assume every failure is a conflict.

5. **Resolve conflicts.** If conflicts occur, load and follow the `resolve-merge-conflicts` skill to resolve them, run the project's checks, and finish the merge commit.

6. **Report the result.** State the source and destination branches and whether the merge completed or was already up to date. Summarize any conflict resolutions, checks run, or remaining blocker. Do not push unless the user requests it.
