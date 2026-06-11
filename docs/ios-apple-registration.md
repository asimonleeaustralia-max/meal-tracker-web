# iOS Apple ID registration & web sync

This guide covers how an iOS user registers with their Apple ID and syncs meals
with the MacrosSimple web app. The backend is already implemented; the iOS app
needs a small **Cloud Sync** toggle in Settings.

## Two ways to register

| Path | Who | How |
|------|-----|-----|
| **Native (recommended)** | iOS app user | Enable Cloud Sync → Sign in with Apple SDK → `POST /api/auth/oauth/apple/token-exchange` |
| **Web from iOS** | User opens website on phone | Tap **Continue with Apple** (uses device Apple ID in Safari) |

Both paths create or link the same cloud account. Meal data syncs automatically
once authenticated because every API call is scoped to the JWT `user_id`.

## iOS app: settings toggle (minimal change)

Add one boolean preference and wire it to Sign in with Apple:

```swift
// UserDefaults / @AppStorage
@AppStorage("cloudSyncEnabled") private var cloudSyncEnabled = false
```

In Settings:

```swift
Toggle("Cloud Sync", isOn: $cloudSyncEnabled)
    .onChange(of: cloudSyncEnabled) { enabled in
        if enabled {
            Task { await enableCloudSync() }
        } else {
            CloudAuth.shared.signOut()
        }
    }
```

### 1. Sign in with Apple (native)

```swift
import AuthenticationServices

final class CloudAuth: NSObject, ASAuthorizationControllerDelegate {
    static let shared = CloudAuth()
    private let apiBase = "https://your-gateway.example.com"  // or LAN IP in dev

    func signInWithApple() {
        let provider = ASAuthorizationAppleIDProvider()
        let request = provider.createRequest()
        request.requestedScopes = [.fullName, .email]

        let controller = ASAuthorizationController(authorizationRequests: [request])
        controller.delegate = self
        controller.performRequests()
    }

    func authorizationController(
        controller: ASAuthorizationController,
        didCompleteWithAuthorization authorization: ASAuthorization
    ) {
        guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential,
              let idTokenData = credential.identityToken,
              let idToken = String(data: idTokenData, encoding: .utf8) else { return }

        let email = credential.email
        let name = [credential.fullName?.givenName, credential.fullName?.familyName]
            .compactMap { $0 }.joined(separator: " ")

        Task {
            await exchangeToken(idToken: idToken, email: email, displayName: name.isEmpty ? nil : name)
        }
    }

    private func exchangeToken(idToken: String, email: String?, displayName: String?) async {
        var body: [String: Any] = ["id_token": idToken]
        if let email { body["email"] = email }
        if let displayName { body["display_name"] = displayName }

        var request = URLRequest(url: URL(string: "\(apiBase)/api/auth/oauth/apple/token-exchange")!)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        let (data, _) = try! await URLSession.shared.data(for: request)
        let pair = try! JSONDecoder().decode(TokenPair.self, from: data)

        // Store securely in Keychain
        KeychainStore.save(access: pair.access_token, refresh: pair.refresh_token)

        // Kick off initial sync
        await SyncEngine.shared.pullChanges(since: nil)
        await SyncEngine.shared.pushLocalChanges()
    }

    func signOut() {
        KeychainStore.clear()
    }
}

struct TokenPair: Decodable {
    let access_token: String
    let refresh_token: String
    let expires_in: Int
    let session_id: String?
}
```

`email` and `display_name` are only sent on the **first** Apple sign-in; Apple
does not return them again. Persist them locally if needed.

### 2. Enable cloud sync helper

```swift
func enableCloudSync() async {
    await MainActor.run { CloudAuth.shared.signInWithApple() }
}
```

If the user cancels Sign in with Apple, reset the toggle:

```swift
// In ASAuthorizationControllerDelegate error path:
UserDefaults.standard.set(false, forKey: "cloudSyncEnabled")
```

### 3. Sync after auth

Use the access token on all meal API calls:

```
Authorization: Bearer <access_token>
```

Pull changes (see `docs/ios-sync-mapping.md`):

```
GET /api/sync/changes?since=<last_cursor>
```

Push local meals:

```
PUT /api/meals/{uuid}
```

## Open web registration from the iOS app

To let users register on the website from the app (e.g. a "Set up web access"
link in Settings), open Safari or `SFSafariViewController` to:

```
https://macrossimple.com/?from=ios
```

The web app shows the registration screen with **Continue with Apple** prominent.
On iPhone, Apple's web flow uses the Apple ID already signed into the device.

Optional: use your production URL from `PASSWORD_RESET_BASE_URL` / gateway config.

## Apple Developer setup

Configure **two** identifiers:

| Identifier | Env var | Used for |
|------------|---------|----------|
| App ID (bundle ID) | `APPLE_IOS_CLIENT_ID` | Native iOS `id_token` audience |
| Services ID | `APPLE_CLIENT_ID` | Web OAuth client_id |
| Team ID | `APPLE_TEAM_ID` | Web OAuth JWT secret |
| Key ID + `.p8` key | `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY` | Web OAuth JWT secret |

Enable **Sign in with Apple** on both the App ID and Services ID. Add the
web redirect URI to the Services ID:

```
https://<gateway>/api/auth/oauth/apple/callback
```

## Environment variables (local)

```bash
export APPLE_CLIENT_ID="com.yourcompany.macrossimple.web"      # Services ID
export APPLE_IOS_CLIENT_ID="com.yourcompany.MacrosSimple"      # iOS bundle ID
export APPLE_TEAM_ID="ABCDE12345"
export APPLE_KEY_ID="XYZ98765"
export APPLE_PRIVATE_KEY="$(cat AuthKey_XYZ98765.p8)"
docker compose up --build
```

Native token exchange only requires `APPLE_IOS_CLIENT_ID`. Web **Continue with
Apple** also needs the team ID, key ID, and private key.

## Account linking

If a user registers on iOS with Apple and later opens the web app:

- **Same Apple ID** → same `oauth_identities` row → same meals.
- **Same email, different method** (e.g. email/password on web) → accounts merge
  automatically on first Apple or email login.

Private relay emails (`@privaterelay.appleid.com`) are stable per Apple ID;
linking uses Apple's `sub` claim, not email.

## Testing

1. Set `APPLE_IOS_CLIENT_ID` to your bundle ID.
2. Run `./scripts/test_full_sync.sh` after email/password signup to verify sync.
3. On device: enable Cloud Sync, sign in with Apple, add a meal, refresh web History.
4. Web Apple button: configure Services ID + `.p8` key, open site on iPhone, tap
   **Continue with Apple**.

See also: `docs/ios-auth.md`, `docs/ios-sync-mapping.md`.
