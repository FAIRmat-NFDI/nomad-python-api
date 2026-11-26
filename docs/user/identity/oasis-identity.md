# Oasis identity setups

A self-hosted NOMAD Oasis can sign users in through several kinds of identity
service. The SDK talks to any of them through standard OAuth 2.0 and OpenID
Connect (OIDC). Find your setup below, ask your Oasis administrator for the
values it needs, and copy the matching example.

In every setup, the credential's `endpoint` is the Oasis's full HTTPS API v1
URL. The identity settings only decide how you sign in.

## Choose your setup { #choose }

| Setup | Browser sign-in | Password sign-in | PAT / existing token | Users, groups, ownership | `enforced_scopes` | `requested_scopes` |
| --- | --- | --- | --- | --- | --- | --- |
| [S1 · Central's Keycloak realm](#central-realm) | ✅ | ✅ | ✅ | ✅ | ✅ | browser: OIDC client scopes; password: ignored¹ |
| [S2 · Own Keycloak](#own-keycloak) | ✅ | ✅² | ✅ | ✅ | ✅ | browser: OIDC client scopes; password: ignored¹ |
| [S3 · Own Keycloak, explicit endpoints](#keycloak-explicit) | ✅ | ✅² | ✅ | ✅ | ✅ | browser: OIDC client scopes; password: ignored¹ |
| [S4 · External SSO brokered by Keycloak](#sso-brokered) | ✅ | ⚠️ local Keycloak accounts only³ | ✅ | ✅ | ✅ | browser: OIDC client scopes; password: ignored¹ |
| [S5 · External SSO directly, no Keycloak](#direct-sso) | ⚠️ customised Oasis⁴ | ❌ usually⁵ | ⚠️ customised Oasis⁴ | ⚠️ customised Oasis⁴ | ✅ | ✅ needed⁶ |

1. Keycloak processes browser values as registered OIDC client scopes, which may affect claims, audiences, or refresh-token issuance. They do not narrow standard NOMAD API permissions. Stock NOMAD 2.x ignores the password form's scope field. Restrict access with [server-side scope settings](#server-scope-settings), PATs, or `enforced_scopes`. See [Advanced: request scopes at sign-in](access.md#requested-scopes).
2. The Keycloak client must allow Direct Access Grants. See [Configure password login](../../dev/oasis/index.md#configure-password-login).
3. Users who sign in through the external provider have no Keycloak password. They use browser sign-in or a PAT.
4. A stock Oasis validates tokens and looks up users through Keycloak. Accepting another provider's tokens directly requires a customised Oasis backend, which then decides how PATs, users, and groups work.
5. `/auth/token` is NOMAD's own wrapper around Keycloak. Many SSO providers also disable password grants or require interactive MFA.
6. Without the right scopes, many providers issue a token meant for a different API, and no refresh token.

`enforced_scopes` is local to the SDK and works the same way in every setup.

## Server-side scope settings { #server-scope-settings }

Independently of the identity setup, an Oasis administrator can limit the scopes
NOMAD applies to whole groups of users. These settings act on the server, so they
also restrict Keycloak tokens, which otherwise carry the full user scope set.

| Setting | Effect |
| --- | --- |
| `auth.require_authentication` | When on, requests without a valid token get HTTP 401. |
| `unauthenticated_user_scopes` | Scopes for requests without a token, when authentication is not required. |
| `authorized_users` | The users whose token scopes apply in full. |
| `reject_unauthorized_users` | When on, users outside `authorized_users` get HTTP 403. |
| `unauthorized_user_scopes` | Scopes for users outside `authorized_users`, when they are not rejected. |

Configuration may use wildcards such as `*:read`. Tokens may not. These settings
apply to groups of users, not to individual jobs: for a job that should only read,
use a [scoped PAT](access.md#granted-scopes). The SDK cannot see these settings, so
a refused request surfaces as `AuthorizationError` (403).
[NOMAD authorization model](https://docs.nomad-lab.eu/explanation/auth.html)

## S1 · Oasis using Central's Keycloak realm { #central-realm }

**Admin configures:** the Oasis trusts NOMAD Central's user management. Nothing else.

**You need:** the Oasis API URL. The issuer and client ID are Central's.

```python
--8<-- "tests/snippets/identity/test_oasis_identity.py:oasis_central_realm"
```

**Expected result:** your browser opens Central's sign-in page, then
`Signed in as: <your username>` prints. The account request goes to the Oasis.

## S2 · Oasis with its own Keycloak { #own-keycloak }

**Admin configures:**

- A **public** OIDC client in the Oasis realm with the authorization code flow and PKCE `S256` required.
- A valid redirect URI for the loopback callback, for example `http://127.0.0.1/*`. If Keycloak needs an exact port, use [S3](#keycloak-explicit) and pin it.
- An HTTPS issuer URL. The SDK refuses plaintext identity endpoints.

**You need:** the Oasis API URL, the realm issuer URL, and the client ID.

```python
--8<-- "tests/snippets/identity/test_oasis_identity.py:oasis_own_keycloak"
```

**Expected result:** the SDK reads
`<issuer>/.well-known/openid-configuration`, your browser opens the Oasis's
Keycloak sign-in page, and `Signed in as: <your username>` prints.

## S3 · Own Keycloak with explicit endpoints { #keycloak-explicit }

Use explicit settings when any of these apply:

- A reverse proxy makes discovery report a different issuer, so discovery is refused.
- The identity service uses a private certificate authority.
- An older Keycloak serves realms under `/auth/realms/...`.
- The client registration allows only one exact redirect URI.

**You need:** the issuer, the authorization and token endpoint URLs (same HTTPS origin as the issuer), the client ID, and, if needed, the CA bundle and the registered callback port and path.

```python
--8<-- "tests/snippets/identity/test_oasis_identity.py:oasis_keycloak_explicit"
```

**Expected result:** no discovery request is made. The browser returns to
`http://127.0.0.1:8765/nomad-callback`, and `Signed in as: <your username>` prints.
Pass `ca_bundle` to `NomadClient` too when the Oasis API uses the same private CA.

## S4 · External SSO provider brokered by Keycloak { #sso-brokered }

This is the standard way to offer institutional single sign-on on an Oasis.
Keycloak stays in place and forwards sign-in to the external OAuth 2.0 / OIDC
provider. NOMAD keeps receiving Keycloak tokens, so every SDK feature works.

**Admin configures:** everything from S2, plus an identity provider in the
Keycloak realm with an alias such as `institution-sso`.

**You need:** the S2 values and the provider alias.

```python
--8<-- "tests/snippets/identity/test_oasis_identity.py:oasis_sso_brokered"
```

**Expected result:** the SDK sends the alias as `kc_idp_hint`, so the browser
goes straight to your institution's sign-in page instead of Keycloak's
chooser. Then `Signed in as: <your username>` prints.

## S5 · External SSO provider directly, without Keycloak { #direct-sso }

!!! warning "Requires a customised Oasis and has not been verified against a live deployment"
    A stock Oasis cannot accept tokens from another identity service. This setup works
    only if the Oasis backend has been extended to validate the provider's tokens
    (issuer, audience, and signing keys) and to map its users to NOMAD accounts.

**Admin configures:**

- A public or native client at the SSO provider with PKCE `S256` and a loopback redirect `http://127.0.0.1`.
- A published discovery document whose `issuer` matches the configured URL exactly.
- An API scope for the Oasis, such as `nomad-api`, and refresh tokens (often through `offline_access`).
- The customised Oasis backend described above.

**You need:** the provider's exact issuer URL, the client ID, and the scope names to request.

```python
--8<-- "tests/snippets/identity/test_oasis_identity.py:oasis_direct_sso"
```

**Expected result:** the authorization request carries
`scope=openid nomad-api offline_access` and no Keycloak hint. After sign-in,
`Signed in as: <your username>` prints if the Oasis accepts the token.

## S6 · Password sign-in on an Oasis { #password }

Available in S1–S3, and in S4 for local Keycloak accounts. The password goes
to the Oasis's own `/auth/token`, which signs in with the Oasis's Keycloak.

```python
--8<-- "tests/snippets/identity/test_password_login.py:oasis_password_login"
```

**Expected result:** one request to `<Oasis API>/auth/token`, then the account request.

## Troubleshooting { #troubleshooting }

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `OIDC discovery did not confirm the configured issuer.` | A proxy or a multi-tenant provider reports a different or templated issuer | Use the exact issuer URL, or switch to explicit endpoints ([S3](#keycloak-explicit)). |
| `Authorization and token endpoints must share the issuer's HTTPS origin.` (explicit endpoints) or `OIDC discovery returned invalid identity endpoints.` (discovery) | Endpoints on a different host from the issuer | Use the endpoints the identity service publishes for that issuer. |
| `Use a complete HTTPS identity URL…` | A plaintext `http://` issuer | Serve the identity service over HTTPS. Only the loopback callback uses HTTP. |
| Browser shows "invalid redirect_uri" | The loopback callback is not registered | Register `http://127.0.0.1` with the path, or pin `redirect_port` and `redirect_path` to the registered URI. |
| Certificate error at sign-in | The identity service uses a private CA | Pass `ca_bundle` to the credential. |
| `ClientAuthenticationError` (401) after a direct-SSO sign-in | The token was issued for another API | Add the Oasis API scope to `requested_scopes`. |
| Asked to sign in again after a few minutes | No refresh token was issued | Request `offline_access`, or your provider's equivalent, in `requested_scopes`. |
| `PasswordAuthenticationError` for an SSO user | That account has no Keycloak password | Use browser sign-in or a PAT. |
| `AuthorizationError` (403) for a signed-in user on simple reads or writes | The Oasis limits users outside `authorized_users` | Ask the administrator to add you, or check `unauthorized_user_scopes`. See [server-side scope settings](#server-scope-settings). |

See the [Oasis developer guide](../../dev/oasis/index.md#configure-browser-login) for administrator setup steps.
