# Claude Code usage norms

- Model-invoked work (skills, slash commands) is not a guarantee. Anything that must
  always happen belongs in a hook, not in an instruction to "remember to do X."
- Prefer editing existing files over creating new ones. Do not scaffold new
  abstractions for a task that a small, direct change would satisfy.
- Read enough of a file to understand it before editing it. Do not guess at
  surrounding context from a partial read.
- When a task is ambiguous, state the assumption being made and where it is
  recorded, rather than silently picking one interpretation.
- Treat generated commit messages and PR descriptions as communication to a human
  reviewer, not as documentation of the process that produced them.
