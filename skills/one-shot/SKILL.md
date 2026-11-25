---
name: one-shot
description: 'Create a merge request for a Jira ticket'
metadata:
  original-author: "John Egan"
---

# One Shot

1. Start with a Jira ticket number. If none is provided, ask for it.
2. Create a git worktree with a new branch based on `main`, named `<TICKET>-<short-description>`, e.g. `WTF-123-short-desc`. Use a kebab-case description, usually no more than four words. Perform all subsequent git and code changes in that worktree.
3. Fetch the Jira ticket details using `fetch-jira-issue`.
4. Implement the code changes and run relevant checks.
5. Commit and push the branch to `origin`.
6. Create a merge request titled `<TICKET>: <Jira Ticket Title>`. Start its description with `Created by {model_name} using one-shot skill`, substituting the actual model name, then add a short explanation of the change. Return the merge request link.
7. If the Jira ticket is in the backlog or to do status, tell the user they need to update that.
