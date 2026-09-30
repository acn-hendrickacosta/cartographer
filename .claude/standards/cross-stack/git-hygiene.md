# Git hygiene

- Commit in small, reviewable units. A commit should do one thing and say so in its
  first line.
- Write commit messages that explain why a change was made, not just what changed.
  The diff already shows what changed.
- Never force-push to a shared branch without asking. Never rewrite history that
  other people has already pulled.
- Keep the working tree clean before switching context. Stash or commit
  work-in-progress rather than leaving it uncommitted and unattended.
- Branch names should say what the branch is for, not who is working on it.
- Squash merges are fine. Cartographer's promotion model keys knowledge by artifact
  identity, not commit SHA, so squashing does not break the knowledge graph.
- Use Conventional Commits format: `<type>(<scope>): <description>`. Types: `feat`,
  `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci`. The type signals intent
  and enables automated changelogs.
- Choose a branching strategy that matches the team's release cadence. GitHub Flow
  (main + short-lived feature branches merged via PR) works for most teams. Trunk-
  based development suits high-velocity teams with strong CI and feature flags.
  GitFlow (develop/release/hotfix branches) suits scheduled enterprise releases.
- Keep feature branches short-lived — days, not weeks. Rebase onto the target branch
  frequently to minimize conflict surface.
- Pull requests should focus on a single concern. A diff over 500 lines is a signal
  to split the change. PRs should describe what changed, why it changed, and how it
  was tested.
- Use `--force-with-lease` instead of `--force` when updating a remote branch you
  own; it fails safely if someone else has pushed since your last fetch.
- Tag releases with semantic versioning (`MAJOR.MINOR.PATCH`). Breaking changes
  increment MAJOR, new backward-compatible features increment MINOR, bug fixes
  increment PATCH.
