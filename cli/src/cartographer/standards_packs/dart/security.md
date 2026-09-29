# Dart / Flutter Security

- Never hardcode API keys, tokens, or credentials in Dart source. Compile-time config via `--dart-define` is not secret — values are embedded in the binary and can be extracted. Use a backend proxy for server-side secrets; `--dart-define` is only for non-secret config (base URLs, feature flags, environment names).
- Store runtime secrets (auth tokens, private keys, user credentials) in `flutter_secure_storage`, which uses Keychain on iOS and EncryptedSharedPreferences on Android. Never write sensitive data to `SharedPreferences` or local files in plaintext.
- Clear all auth state on logout: tokens, cached user data, cookies, secure storage entries. Incomplete logout leaves tokens accessible to the next person who picks up the device.
- Enforce HTTPS for all API calls — no `http://` in production. Configure `network_security_config.xml` on Android to block cleartext traffic. Set `NSAllowsArbitraryLoads = false` in `Info.plist` on iOS. Always set connection and receive timeouts on HTTP clients.
- Parameterize all SQL queries — never interpolate user input into query strings.

```dart
// BAD — SQL injection
await db.rawQuery("SELECT * FROM users WHERE email = '$userInput'");

// GOOD
await db.query('users', where: 'email = ?', whereArgs: [userInput]);
```

- Validate deep link URLs before navigation: parse with `Uri.tryParse`, verify the host matches your domain, and check the path against an allowlist. Never navigate to an arbitrary path from an incoming deep link.
- WebView: use `webview_flutter` v4+ (`WebViewController` + `WebViewWidget`). Disable JavaScript unless required (`JavaScriptMode.disabled`). Validate URLs in `NavigationDelegate.onNavigationRequest` — reject any navigation to a non-trusted host.
- Android: declare only required permissions. Set `android:exported="false"` on Activities, Services, and BroadcastReceivers that are not entry points. Use `FLAG_SECURE` on screens displaying sensitive data.
- iOS: declare only required usage descriptions in `Info.plist`. Enable the data protection entitlement for files containing sensitive data. Store secrets in Keychain — never write them to the app's Documents directory.
- Enable obfuscation in release builds: `flutter build apk --obfuscate --split-debug-info=./debug-info/`. Store `--split-debug-info` output for crash symbolication — keep it out of version control.
- Never log sensitive data: no `print(token)`, `debugPrint(password)`, or logging PII at any level. Use structured logging with field redaction.
