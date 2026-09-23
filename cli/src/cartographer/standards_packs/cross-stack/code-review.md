# Review

- A reviewer's job is to find correctness problems first, then reuse and
  simplification, then style. Do not spend the first pass on formatting.
- State the concrete failure scenario for anything flagged as a bug: what input or
  state triggers it, and what goes wrong. A vague "this looks risky" is not a
  finding.
- Prefer fewer, high-confidence comments over an exhaustive list of low-confidence
  ones. A review that flags everything is as useless as one that flags nothing.
- Approve changes that are correct and reasonably scoped even if you would have
  written them differently. Style disagreements are not blockers unless a
  documented convention says otherwise.
- Do not ask for speculative generalization. A change should be reviewed against
  what it actually needs to do, not against imagined future requirements.
