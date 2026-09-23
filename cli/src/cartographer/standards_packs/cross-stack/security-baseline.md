# Security baseline

- Validate and sanitize input at system boundaries: user input, external APIs, file
  uploads. Do not add defensive checks for internal calls that cannot receive
  attacker-controlled data.
- Never commit secrets, credentials, or API keys. Configuration that carries secrets
  belongs in a gitignored local override or the environment, never in a committed
  file.
- Treat anything that builds a shell command, SQL query, or HTML fragment from
  untrusted input as a candidate for injection until proven otherwise. Use
  parameterized queries and established escaping, not string concatenation.
- Source code is confidential by default. Do not send it to a third-party API
  (including an embedding API) unless the team has explicitly opted in and accepted
  the egress.
- When you find a vulnerability while working on something else, fix it immediately
  if it is small, or flag it clearly if it is not, rather than leaving it for later
  silently.
