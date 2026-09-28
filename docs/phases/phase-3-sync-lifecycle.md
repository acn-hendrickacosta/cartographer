# Phase 3: Sync and Lifecycle

## Goal

Handle the data lifecycle gaps that were deferred in Phase 2: deletions, renames, rebase handling, and conflict resolution when local and global indexes diverge. After Phase 3, the global index accurately reflects the current state of the main branch, including removed and renamed artifacts.

**Entry condition:** Phase 2 is complete and stable. The central topology is in active use on at least one real project. Phase 3 must not start until Phase 2 has been running long enough to surface real-world edge cases in promotion behavior.

---

## References

| Document | What to read |
|---|---|
| [DATA_MODEL.md](../DATA_MODEL.md) | Section 7: known gaps and deferred concerns |
| [ARCHITECTURE.md](../ARCHITECTURE.md) | Section 9: what is not in scope (the original deferral rationale) |
| [ROADMAP.md](../ROADMAP.md) | Phase 3 entry condition and design spike requirement |

---

## Scope

Phase 3 is preceded by a **design spike**. The spike produces written protocols for each deferred concern before any implementation begins. Implementation does not start until the spike documents are reviewed and accepted.

### Design spike deliverables

| Protocol | What it must define |
|---|---|
| Tombstone protocol | How a deleted artifact is represented in the global index; how the CLI detects deletions at promotion time; how stale tombstones are cleaned up |
| Rename tracking protocol | How a renamed artifact's old identity is linked to its new identity; how the KG edge graph is updated when a node identity changes |
| Rebase and force-push policy | Whether artifacts from force-pushed commits are removed from the global index; what the operator must do to trigger cleanup |
| Conflict resolution policy | When local and global versions of the same artifact diverge, what wins and when; how Claude is informed about the conflict |

Each protocol is written as a document in `docs/phases/phase-3-protocols/` before implementation begins. Each must be reviewed and approved before the corresponding implementation starts.

### Implementation scope (post-spike)

| Concern | What ships |
|---|---|
| Deletion across promotion boundary | Tombstone records written to global index on promotion; stale nodes and chunks marked, not deleted immediately |
| Rename handling | Old artifact identity redirects to new identity in global index; `kg_move_node` tool or equivalent |
| Stale tombstone cleanup | `cartographer gc` command: remove tombstoned artifacts older than a configurable retention period |
| Rebase handling | Policy implementation per the spike protocol |
| Conflict resolution | Tagging strategy for conflicting local/global versions; surfaced to Claude in recall context |

### Explicitly out of scope

- Real-time bidirectional sync (explicitly a non-goal per [ARCHITECTURE.md](../ARCHITECTURE.md))
- Cross-tenant reconciliation (never in scope)
- Standards Registry and web app (independent track)

---

## Component breakdown

Components cannot be detailed until the design spike is complete. The following are placeholder areas that the spike will fill in.

### 1. Tombstone protocol implementation

**What the spike must define first:**
- The tombstone record schema (fields, stored in VDB and/or KG)
- How `cartographer promote` detects deleted artifacts (git diff, explicit manifest, or index scan)
- Tombstone retention policy (how long before a tombstone can be cleaned up)
- Whether Claude is told about tombstoned artifacts in recall context

**Likely implementation touchpoints:**
- `cartographer promote`: detect deleted artifacts and write tombstone records
- VDB driver: add `tombstone` field to chunk record or a separate tombstone collection
- KG driver: mark deleted nodes with a `tombstoned_at` attribute rather than deleting
- Recall hooks: filter tombstoned results from context injection
- `cartographer gc`: new command to clean up expired tombstones

---

### 2. Rename tracking

**What the spike must define first:**
- Whether renames are tracked via git rename detection or artifact identity comparison
- The KG edge type for rename relationships (`renamed_to`? `supersedes`?)
- How the VDB handles the old identity (tombstone? redirect? both?)

**Likely implementation touchpoints:**
- `cartographer promote`: detect renames via `git diff --name-status` and write rename records
- KG driver: new `kg_move_node` operation or `supersedes` edge writing
- Recall hooks: follow rename chains when resolving artifact identity

---

### 3. `cartographer gc`

New CLI command added in Phase 3:

```
cartographer gc [--dry-run] [--older-than <days>]
```

Removes tombstoned artifacts from the global index that have exceeded the retention period. `--dry-run` reports what would be removed without writing.

---

### 4. Conflict resolution

**What the spike must define first:**
- Definition of "conflict": when does a local version count as conflicting with a global version rather than simply being ahead of it?
- Tagging strategy: how is a conflicting result surfaced in recall context?
- Whether Claude is asked to resolve the conflict or only informed of it

---

## Open questions (to be defined during the spike)

| Question | Blocks |
|---|---|
| Tombstone schema | Tombstone protocol implementation |
| Rename detection strategy (git vs identity comparison) | Rename tracking implementation |
| Conflict definition | Conflict resolution implementation |
| Retention policy default for tombstone cleanup | `cartographer gc` implementation |
| Whether `kg_move_node` requires a new MCP tool (breaking change) | ADR required if yes |

---

## Exit criteria

Exit criteria cannot be fully defined until the design spike is complete and the protocols are accepted. The following are the minimum criteria regardless of spike outcomes:

| # | Criterion | How to verify |
|---|---|---|
| 1 | Deleting a file on a branch and merging does not leave the artifact permanently in the global index | Delete a file; merge; promote; run `kg_namespace_stats` and `vdb_collection_stats`; confirm artifact is tombstoned or removed |
| 2 | Renaming a file and merging links the old identity to the new identity in the global index | Rename a file; merge; promote; query by old path; confirm redirect or supersedes relationship exists |
| 3 | `cartographer gc` removes tombstoned artifacts beyond the retention period | Tombstone an artifact; advance time past retention; run gc; confirm artifact is gone from global index |
| 4 | Recall does not surface tombstoned artifacts in context | Tombstone an artifact; run a recall query that would have matched it; confirm it does not appear in results |
| 5 | All Phase 2 exit criteria still pass after Phase 3 changes | Re-run Phase 2 acceptance test; confirm no regression |

---

## Test approach

### Design spike review

Before any code is written, each protocol document is reviewed by at least two people familiar with the data model. The review must confirm:
- The protocol handles the stated edge cases
- The protocol does not break the Phase 2 promotion idempotency guarantee
- The MCP tool contract changes (if any) are backward-compatible or have an ADR

### Unit tests

To be defined after the spike. Will cover: tombstone record creation; rename detection logic; gc retention filter; conflict detection heuristic.

### Integration tests

To be defined after the spike. Will require: a real central backend (pgvector + Neo4j); a git repo with known deletion and rename history; before/after index state verification.

### Regression test

Phase 2 end-to-end acceptance test (two-developer walkthrough) must pass unchanged after Phase 3 changes are applied. This is a required gate before Phase 3 is considered complete.

---

*For the known gaps this phase closes, see [DATA_MODEL.md: Known gaps](../DATA_MODEL.md). For Phase 2 foundation, see [phase-2-central.md](phase-2-central.md).*
