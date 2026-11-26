# Sign in

## Check your account with a PAT { #check-your-account }

Create a PAT with `users:read` in **User Settings → Tokens**, then set `NOMAD_PAT` in your process environment. This example calls [GET `/users/me`](rest.md#get-users-me) and returns an [`Account`](api.md#account). [Create a PAT in NOMAD](https://docs.nomad-lab.eu/howto/manage/program/auth.html#create-a-pat)

```python
--8<-- "tests/snippets/identity/test_authentication.py:named_setup"
```

See the [`me()` return value](api.md#me-returns) and [`Account` fields and methods](api.md#account) for what you can do with the returned profile.

## Advanced client options for workers

Use a Python dictionary when a script builds the same client options for multiple
workers or runs. Unpack it with `**options` and pass the job's credential
separately where needed. The keys match the
[`NomadClient` constructor](api.md#nomad-client-constructor).

```python
--8<-- "tests/snippets/identity/test_authentication.py:dictionary_setup"
```

For process-based work, [construct the client inside each worker](connections.md#configure-an-hpc-worker).

## Sign in with your browser { #browser-login }

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

Run browser login where Python and the browser share a loopback interface, including a local Jupyter kernel. By default, the SDK lets the operating system pick a free callback port and handles token renewal as requests need it. Use the [advanced browser settings](api.md#advanced-browser-settings) if your Oasis administrator gives you a fixed callback URL.

## Sign in with a username and password { #password-login }

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

## Use an existing Keycloak access token

Set `NOMAD_KEYCLOAK_ACCESS_TOKEN` to the access token supplied by your sign-in application. Replace the credential when that application issues a fresh token.

```python
--8<-- "tests/snippets/identity/test_authentication.py:keycloak_setup"
```

## Connect to an Oasis with a PAT { #connect-to-an-oasis }

Set `OASIS_PAT` to a PAT issued by your Oasis. If the API uses a private CA, set `NOMAD_CA_BUNDLE` to the path of its PEM bundle. See the [Oasis developer guide](../../dev/oasis/index.md) for custom REST contracts.

```python
--8<-- "tests/snippets/identity/test_authentication.py:oasis_setup"
```

In Jupyter, install the SDK in the active kernel's environment. In pyiron, create the client inside the worker using a job-provided secret.

## Choose and inspect scopes

`client.allowed_scopes` is a [read-only property](api.md#client-allowed-scopes). Call [`client.identity.get_operation_info("me")`](api.md#identity-get-operation-info) to see what an operation requires. `Scope.USERS_READ` is a member of the [`Scope` enum](api.md#scope).

With `NOMAD_PAT` set, compare your local policy with the scopes required by `me()` before looking up the account.

```python
--8<-- "tests/snippets/identity/test_authentication.py:inspect_and_read_account"
```

`Allowed` and `Required` both show `users:read`. A successful lookup prints `Account returned: True`. `Username available` depends on the account returned by NOMAD.

## Troubleshoot a request

Run this example inside your open client context.

```python
--8<-- "tests/snippets/identity/test_authentication.py:error_recovery"
```

See [exceptions](api.md#exceptions) for sign-in errors and API responses.
