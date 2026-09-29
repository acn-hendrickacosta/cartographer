# Swift Security

- Store all sensitive data — tokens, passwords, private keys, biometric state — in Keychain Services. Never store secrets in `UserDefaults`, `NSUserDefaults`, plists, or the file system without encryption. `flutter_secure_storage` uses Keychain on iOS; for native Swift use `Security.SecItemAdd` directly or a Keychain wrapper.
- Inject build-time configuration (API base URLs, non-secret feature flags) via `ProcessInfo.processInfo.environment` in development and via CI environment variables in production builds. Never hardcode environment-specific values in source code.
- App Transport Security (ATS) is enforced by default — do not add `NSAllowsArbitraryLoads` to `Info.plist`. If a third-party endpoint requires HTTP, use `NSExceptionDomains` for that specific domain with documented justification, not a global ATS bypass.
- For high-security endpoints (authentication, payment), implement certificate pinning. Validate the server certificate chain against your pinned public key fingerprints. Reject connections that fail pinning, even if the certificate is otherwise valid.
- Validate all user input before use: sanitize strings, validate URL schemes before navigating (`guard url.scheme == "https" else { return }`), and reject unexpected values at API boundaries.
- When constructing SQL queries (SQLite, GRDB, SQLCipher), always use parameterized queries. Never interpolate user input into a SQL string.
- Avoid path traversal: normalize file paths with `URL.standardized` and verify the result is within your app's sandbox directory before reading or writing.
- Use secure deserialization: prefer `Codable` with explicit type definitions over `NSKeyedUnarchiver` with arbitrary class sets. Restrict unarchiving with `NSKeyedUnarchiver.unarchivedObject(ofClasses:from:)`.
