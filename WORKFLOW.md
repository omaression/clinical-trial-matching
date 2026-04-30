---
workflow_version: 3
portal_profile: engineer
return_profile: engineer
max_concurrency: 4
default_workspace:
  engineer: scratch
  coder: worktree
  debugger: worktree
  researcher: scratch
  reviewer: scratch
  jobhunter: scratch
  symphony: scratch
---

# Runtime contract

1. Read the Kanban task first.
2. Read AGENTS.md and referenced repo files second.
3. Work only in the assigned workspace.
4. Coder and debugger tasks must use worktree workspace.
5. Use kanban_heartbeat during long work.
6. Complete with a structured handoff.
7. Block instead of guessing when required inputs are missing.
