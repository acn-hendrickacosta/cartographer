# Git hygiene

- Commit in small, reviewable units. A commit should do one thing and say so in its
  first line.
- Write commit messages that explain why a change was made, not just what changed.
  The diff already shows what changed.
- Never force-push to a shared branch without asking. Never rewrite history that
  other people have already pulled.
- Keep the working tree clean before switching context. Stash or commit
  work-in-progress rather than leaving it uncommitted and unattended.
- Branch names should say what the branch is for, not who is working on it.
- Squash merges are fine. Cartographer's promotion model keys knowledge by artifact
  identity, not commit SHA, so squashing does not break the knowledge graph.
