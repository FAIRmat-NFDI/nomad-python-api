# Authentication

Use browser sign-in for an interactive script or local notebook. Use a personal access token (PAT) for unattended jobs and remote workers. To create a PAT for the account check, sign in to the deployment, open **User Settings → Tokens**, and grant `users:read`. Set `NOMAD_PAT` in your environment or have your secret manager supply it. [Create a PAT in NOMAD](https://docs.nomad-lab.eu/howto/manage/program/auth.html#create-a-pat)

`NomadClient` gets its deployment from the credential. Omit `endpoint` on the credential to use NOMAD Central. For a self-hosted NOMAD Oasis or a development or test deployment, set `endpoint` on the credential to the full HTTPS API v1 base URL. If a previous example passed `endpoint` to `NomadClient`, move it to the credential.

## Check your account { #check-your-account }

**REST endpoint used** · [`GET /users/me`](rest.md#get-users-me)

`client.identity.me()` returns an `Account` with a user ID and an optional username. Creating the client and inspecting its scope policy require no network access. Each account lookup makes one NOMAD API request. A browser or password credential may first need to obtain a token.

=== "Named arguments"

    Pass the credential object and scope limit as named Python arguments.

    ```python
    --8<-- "tests/snippets/identity/test_authentication.py:named_setup"
    ```

=== "Python options object"

    Build an options dictionary and unpack it with `**options`. Its keys must match the constructor's named arguments. An unknown key raises `TypeError`.

    ```python
    --8<-- "tests/snippets/identity/test_authentication.py:dictionary_setup"
    ```

=== "JSON settings file"

    Save these settings as `nomad-settings.json` in your working directory. Keep credentials in the environment or secret manager.

    ```json
    --8<-- "tests/snippets/identity/fixtures/nomad-settings.json"
    ```

    Load the JSON with the Python standard library. Omit `endpoint` for Central, or add the full HTTPS API v1 base URL for the deployment you want to use. Omitting `allowed_scopes` leaves the client without a local restriction. An empty array blocks scoped operations. An unknown scope name raises `ValueError`.

    ```python
    --8<-- "tests/snippets/identity/test_authentication.py:json_setup"
    ```

## Sign in with your browser { #browser-login }

**REST endpoints used** · [OIDC discovery, authorization, and token exchange](rest.md#browser-login-rest) · [`GET /users/me`](rest.md#get-users-me)

=== "NOMAD Central"

    NOMAD Central is the public deployment hosted by FAIRmat. The example passes `identity_provider="helmholtz-aai"` to open Helmholtz ID directly. Choose your institution there and finish signing in. Omit the provider alias to use the deployment's standard sign-in page. [NOMAD sign-in guide](https://docs.nomad-lab.eu/howto/manage/gui/account.html)

    ```python
    --8<-- "tests/snippets/identity/test_browser_login.py:central_browser_login"
    ```

=== "Self-hosted NOMAD Oasis"

    Ask your Oasis administrator for the API URL, Keycloak issuer, public client ID, and optional provider alias. This example supplies the two Keycloak URLs directly and signs in before making the API request. [Oasis Keycloak setup](../../dev/oasis/index.md#configure-browser-login)

    ```python
    --8<-- "tests/snippets/identity/test_browser_login.py:oasis_browser_login"
    ```

Always supply `issuer` and `client_id`. Pass `discover=True` to fetch the authorization and token endpoints from the issuer, or supply both `authorization_endpoint` and `token_endpoint` explicitly. Both must use HTTPS on the issuer's origin. `identity_provider` is the alias configured in that Keycloak realm.

The first allowed operation opens your system browser. Call `credential.authenticate()` if you want to open the browser first or start a fresh session. The credential keeps its tokens in memory and refreshes them when Keycloak issues a refresh token. `client.close()` closes the client's API connection pool. You can reuse the credential with another client on the same deployment.

| Option | Default and usage |
| --- | --- |
| `login_timeout` | 180 seconds to complete sign-in in the browser. |
| `refresh_margin` | Refresh up to 30 seconds before expiry, capped at half the token lifetime. |
| `redirect_port`, `redirect_path` | An OS-assigned port (`0`) and `/`. Set these when the public client registration requires a particular callback. The listener binds to `127.0.0.1`. |
| `ca_bundle` | HTTPX's default CA bundle for the credential's HTTPS calls. Supply a PEM bundle for a private issuer CA. Configure `NomadClient(ca_bundle=...)` separately when the API uses a private CA, and make sure the browser trusts the issuer's certificate. |

Run browser login where Python and the browser can reach the same loopback interface, including a local Jupyter kernel. Use a scoped PAT for a remote kernel, a headless pyiron worker, or CI.

## Sign in with a username and password { #password-login }

**REST endpoints used** · [`POST /auth/token`](rest.md#password-login-rest) · [`GET /users/me`](rest.md#get-users-me)

Use `PasswordCredential` on a deployment that enables Keycloak Direct Access Grants. Supply both `username` and `password` as keyword arguments or set both `NOMAD_USERNAME` and `NOMAD_PASSWORD` in the process environment. Load real secrets from a secure prompt or secret manager. Use browser sign-in for institutional SSO and MFA. [Keycloak password grant](https://www.keycloak.org/securing-apps/oidc-layers#_resource_owner_password_credentials) · [OAuth security guidance](https://www.rfc-editor.org/rfc/rfc9700.html#section-2.4)

=== "NOMAD Central"

    ```python
    --8<-- "tests/snippets/identity/test_password_login.py:central_password_login"
    ```

=== "Self-hosted NOMAD Oasis"

    The Oasis uses its own configured Keycloak realm and client. Pass its API URL to the credential. This example reads the pair from the environment and passes both arguments explicitly.

    ```python
    --8<-- "tests/snippets/identity/test_password_login.py:oasis_password_login"
    ```

The first permitted API call exchanges the password for an access token. You can also sign in explicitly with `credential.authenticate()`. The credential reads the pair at construction and retains it in memory so it can repeat the exchange near expiry. `refresh_margin` controls when renewal begins and defaults to 30 seconds, capped at half the access token's lifetime. Create a new credential if the password changes. For an Oasis that uses a private CA, pass the PEM bundle to `PasswordCredential(ca_bundle=...)` for sign-in and `NomadClient(ca_bundle=...)` for API calls.

## Use an existing Keycloak access token

If another application handles sign-in, supply its Keycloak **access token** the same way. Set `NOMAD_KEYCLOAK_ACCESS_TOKEN` in the process environment for this example. Replace the credential with a fresh access token when the old one expires.

```python
--8<-- "tests/snippets/identity/test_authentication.py:keycloak_setup"
```

## Connect to an Oasis

The SDK primarily targets NOMAD Central. The same client works with Oasis deployments that expose the compatible REST operation and accept bearer credentials. If your institute adds optional parameters to a wrapped route, use the operation's documented REST extension mapping when available. For routes or behavior that differ from the SDK contract, ask your Oasis maintainers whether they supply a fork or adapter.

Use your Oasis's complete HTTPS API base URL and a token issued for that deployment. For this example, set `OASIS_PAT` to the token. If your Oasis uses a private certificate authority, set `NOMAD_CA_BUNDLE` to the path of its trusted PEM bundle. The example passes that path to the constructor's `ca_bundle` keyword and shows how to explicitly close a long-lived client.

```python
--8<-- "tests/snippets/identity/test_authentication.py:oasis_setup"
```

In Jupyter, install the SDK in the active kernel's environment and run the same example in a cell. Avoid saving secrets or account details in cell output. In pyiron, install the SDK in the worker's environment and create the client inside the worker using a job-provided secret. Pass ordinary data between processes. Live clients and credentials are not serializable with Python's pickle.

## Choose and inspect scopes

| Inspect | What you learn |
| --- | --- |
| `list(Scope)` | Scope constants the installed SDK knows about. See the [NOMAD scope catalog](https://docs.nomad-lab.eu/explanation/auth.html#authorization-via-scopes) for the full server list. |
| `client.allowed_scopes` | The client's immutable local limit. It can block calls that the token would otherwise authorize. |
| `client.identity.get_operation_info("me")` | The operation's description and required scopes. This call reads local metadata. |

NOMAD enforces the token's actual permissions and resource access. Adding a member to the client's allowlist does not grant that permission to the token.

## Troubleshoot a request

Run this example inside your open client context.

```python
--8<-- "tests/snippets/identity/test_authentication.py:error_recovery"
```

| Error | What to check |
| --- | --- |
| `ScopeNotAllowedError` | The client's local policy blocked the call before HTTP. Use a client configured for the required scope. |
| `BrowserAuthenticationError` | Check the issuer, public client and redirect registration, browser availability, or sign-in timeout. |
| `ReauthenticationRequiredError` | Call `credential.authenticate()` to start a fresh browser sign-in, then retry the operation. |
| `PasswordAuthenticationError` | Check the username, password, and password-grant setting on the target deployment. After a rejection, call `credential.authenticate()` to try again, or create a new credential if the password changed. |
| `ClientAuthenticationError` (401) | Check whether the token is complete, expired, revoked, or issued by a different deployment. |
| `AuthorizationError` (403) | Check the token's scopes and the account's access to the resource. |
| `RateLimitError` (429) | Wait before issuing another request. |
| `TransportError` | Check the network, endpoint, and certificate trust. |
| `InvalidResponseError` or other `HttpResponseError` | Check that the endpoint is a supported NOMAD API base URL. Inspect the deployment's behavior if the server returns an unexpected response. |
