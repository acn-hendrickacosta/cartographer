# Rebase and Force-Push Policy

**Status:** Draft — awaiting review  
**Phase:** 3  
**Blocks:** operator runbook section; `cartographer promote --full` documentation

---

## Problem

When a developer rebases a branch or force-pushes to main, the git history is rewritten. Commits that were previously promoted may no longer exist in the new history. Cartographer cannot automatically detect this because:

- git reflog is per-machine and not accessible in CI
- The global index has no record of which commit SHA each artifact was promoted from (only `last_promoted_sha` of the most recent promote)
- A shallow CI clone may not have the old `last_promoted_sha` in its history at all

---

## Policy decision

**Cartographer does not automatically clean up artifacts from force-pushed or rebased commits.**

Rationale:
1. Reliable detection requires per-machine reflog — not feasible in CI
2. A rebase that only rewrites commit messages (common) should not trigger artifact cleanup
3. A rebase that changes file content will naturally be resolved at the next `cartographer promote`, which will promote the new file content (upsert overwrites the old)
4. Only a rebase that deletes files creates a real problem — and those deletions are caught by the tombstone protocol's index comparison at the next promote

---

## What happens in practice

| Rebase scenario | Effect on global index | Action required |
|---|---|---|
| Rebase that rewrites commit messages only | Files unchanged → next promote upserts same content (idempotent) | None |
| Rebase that amends file content | New content promoted on next `cartographer promote` (upsert overwrites) | None |
| Rebase that deletes a file | File missing from local VDB → tombstoned on next `cartographer promote` | None (automatic) |
| Force-push that removes an entire branch from main | Artifacts from that branch remain in global until next promote from a checkout without those files | Run `cartographer promote --full` from a clean checkout of the new main |
| Squash merge | All files are present; content may differ → upsert overwrites | None |

---

## Operator action for destructive force-pushes

When a force-push removes significant content (e.g., reverting a large merge), the operator should:

```bash
# 1. Checkout the new main
git checkout main && git pull --force

# 2. Re-seed from scratch to ensure local VDB reflects new main
rm -rf .cartographer/local/
cartographer seed .

# 3. Full re-promote to sync global index with new main
cartographer promote --full
```

`cartographer promote --full` bypasses the incremental filter and re-promotes all local artifacts. The tombstone detection (index comparison) then removes any global artifacts not present in the new local VDB.

This is documented in the operator runbook (`docs/runbooks/two-developer-walkthrough.md`) under the "Recovery" section.

---

## Why we do not add force-push detection

Options considered and rejected:

| Option | Why rejected |
|---|---|
| Read git reflog | Per-machine only; not available in CI |
| Compare `last_promoted_sha` against `git log` | Shallow clones don't have old SHAs; breaks in CI |
| Store promoted artifact SHAs in global index | High storage overhead; complex; adds write latency to promote |
| Webhook from git host on force-push | Out of scope for self-contained CLI; requires server-side infrastructure |

---

## Open questions resolved

| Question | Decision |
|---|---|
| Automatic cleanup on force-push | Not implemented; operator runs `cartographer promote --full` |
| Detection mechanism | None — policy relies on next regular promote + tombstone detection |
| Documentation | Operator runbook updated with recovery steps |
