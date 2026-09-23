# Spec-driven workflow

- Specs are the highest-signal artifact in this project. Code implements a spec;
  it does not replace one.
- Before implementing a feature, check whether a spec already exists for it. If it
  does not, write one first, even briefly, rather than encoding the decision only
  in code.
- When a spec and the code it describes disagree, treat that as a bug regardless of
  which one is "right." Reconcile them and record which way it was resolved.
- Cartographer's ingestion hook watches spec files specifically, because they anchor
  recall. Keep specs in a predictable location and format so ingestion can find them.
- Update the spec in the same change that implements or alters the behavior it
  describes. A spec that lags the code it describes stops being trustworthy.
