# Authentication

## Summary

Create a credential, pass it to `NomadClient`, and call [`client.identity.me()`](api.md#identity-me) to get your NOMAD account.

| Sign-in option | Credential | When to use it |
| --- | --- | --- |
| Personal access token (PAT) | [`BearerTokenCredential`](api.md#bearer-token-credential) | Scripts, remote kernels, CI, and scheduled work. |
| Browser | [`BrowserCredential`](api.md#browser-credential) | Interactive sign-in, including institutional SSO and MFA. |
| Username and password | [`PasswordCredential`](api.md#password-credential) | Deployments that enable Keycloak Direct Access Grants. |
| Existing Keycloak access token | [`BearerTokenCredential`](api.md#bearer-token-credential) | Another application handles sign-in and token renewal. |

`NomadClient` uses the credential's deployment. Omit `endpoint` on the credential for NOMAD Central. Set it to the full HTTPS API v1 base URL for a self-hosted Oasis, development, or test deployment. Move any old `NomadClient(endpoint=...)` setting to its credential.

## Examples

### Check your account with a PAT { #check-your-account }

Create a PAT with `users:read` in **User Settings → Tokens**, then set `NOMAD_PAT` in your process environment. This example calls [GET `/users/me`](rest.md#get-users-me) and returns an [`Account`](api.md#account). [Create a PAT in NOMAD](https://docs.nomad-lab.eu/howto/manage/program/auth.html#create-a-pat)

=== "Named arguments"

    ```python
    --8<-- "tests/snippets/identity/test_authentication.py:named_setup"
    ```

=== "Python options object"

    Unpack an options dictionary with `**options`. Use the names in the [`NomadClient` constructor](api.md#nomad-client-constructor).

    ```python
    --8<-- "tests/snippets/identity/test_authentication.py:dictionary_setup"
    ```

=== "JSON settings file"

    Save the settings as `nomad-settings.json`. Supply the token through the environment or a secret manager.

    ```json
    --8<-- "tests/snippets/identity/fixtures/nomad-settings.json"
    ```

    Add `endpoint` to the JSON for a custom deployment. The example passes it to the credential. The [`allowed_scopes` reference](api.md#client-allowed-scopes) explains omitted and empty policies.

    ```python
    --8<-- "tests/snippets/identity/test_authentication.py:json_setup"
    ```

### Tune network settings { #tune-network-settings }

Reuse one client per process. Set `pool_limits` and `timeouts` when a notebook or HPC job needs different connection limits or wait times. This example returns an account using the configured pool. [Client settings and defaults](api.md#connection-limits)

```python
--8<-- "tests/snippets/identity/test_authentication.py:client_network_settings"
```

### Sign in with your browser { #browser-login }

**REST endpoints used** · [OIDC discovery, authorization, and token exchange](rest.md#browser-login-rest) · [`GET /users/me`](rest.md#get-users-me)

=== "NOMAD Central"

    `identity_provider="helmholtz-aai"` opens Helmholtz ID. Choose your institution there. Omit the alias to use Central's standard sign-in page. [NOMAD sign-in guide](https://docs.nomad-lab.eu/howto/manage/gui/account.html)

    ```python
    --8<-- "tests/snippets/identity/test_browser_login.py:central_browser_login"
    ```

=== "Self-hosted NOMAD Oasis"

    Get the API URL and Keycloak settings from your Oasis administrator. This example uses explicit Keycloak URLs and signs in before calling the API. [Oasis Keycloak setup](../../dev/oasis/index.md#configure-browser-login)

    ```python
    --8<-- "tests/snippets/identity/test_browser_login.py:oasis_browser_login"
    ```

Run browser login where Python and the browser share a loopback interface, including a local Jupyter kernel. See [browser credential parameters](api.md#browser-credential-constructor) for discovery, timeout, callback, and CA settings.

### Sign in with a username and password { #password-login }

**REST endpoints used** · [`POST /auth/token`](rest.md#password-login-rest) · [`GET /users/me`](rest.md#get-users-me)

Set `NOMAD_USERNAME` and `NOMAD_PASSWORD` through a secure prompt or secret manager. The target deployment must enable Keycloak Direct Access Grants. [Keycloak password grant](https://www.keycloak.org/securing-apps/oidc-layers#_resource_owner_password_credentials) · [OAuth security guidance](https://www.rfc-editor.org/rfc/rfc9700.html#section-2.4)

=== "NOMAD Central"

    ```python
    --8<-- "tests/snippets/identity/test_password_login.py:central_password_login"
    ```

=== "Self-hosted NOMAD Oasis"

    Pass the Oasis API URL to the credential. This example reads the pair from the environment and passes both arguments explicitly.

    ```python
    --8<-- "tests/snippets/identity/test_password_login.py:oasis_password_login"
    ```

See [`PasswordCredential`](api.md#password-credential) for renewal and private CA settings.

### Use an existing Keycloak access token

Set `NOMAD_KEYCLOAK_ACCESS_TOKEN` to the access token supplied by your sign-in application. Replace the credential when that application issues a fresh token.

```python
--8<-- "tests/snippets/identity/test_authentication.py:keycloak_setup"
```

### Connect to an Oasis with a PAT { #connect-to-an-oasis }

Set `OASIS_PAT` to a PAT issued by your Oasis. If the API uses a private CA, set `NOMAD_CA_BUNDLE` to the path of its PEM bundle. See the [Oasis developer guide](../../dev/oasis/index.md) for custom REST contracts.

```python
--8<-- "tests/snippets/identity/test_authentication.py:oasis_setup"
```

In Jupyter, install the SDK in the active kernel's environment. In pyiron, create the client inside the worker using a job-provided secret.

### Choose and inspect scopes

`client.allowed_scopes` is a [read-only property](api.md#client-allowed-scopes). Call [`client.identity.get_operation_info("me")`](api.md#identity-get-operation-info) to see what an operation requires. `Scope.USERS_READ` is a member of the [`Scope` enum](api.md#scope).

With `NOMAD_PAT` set, compare your local policy with the scopes required by `me()` before looking up the account.

```python
--8<-- "tests/snippets/identity/test_authentication.py:inspect_and_read_account"
```

`Allowed` and `Required` both show `users:read`. A successful lookup prints `Account returned: True`. `Username available` depends on the account returned by NOMAD.

### Troubleshoot a request

Run this example inside your open client context.

```python
--8<-- "tests/snippets/identity/test_authentication.py:error_recovery"
```

See [exceptions](api.md#exceptions) for sign-in errors and API responses.

## API reference

- [Python API](api.md) covers classes, constructor parameters, instance methods, properties, model fields, and enum members.
- [REST API](rest.md) covers HTTP endpoints, request fields, and responses.
