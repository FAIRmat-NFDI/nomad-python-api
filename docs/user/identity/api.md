# Authentication Python API

## Summary

This reference lists the SDK classes, instance methods, read-only properties, model fields, and enum members used for authentication and account lookup. The [Authentication guide](index.md#examples) has runnable examples. The [REST reference](rest.md) has request and response fields for the underlying HTTP endpoints.

| Type | Kind | Purpose |
| --- | --- | --- |
| [`NomadClient`](#nomad-client) | Class | Runs operations against the credential's deployment. |
| [`ConnectionLimits`](#connection-limits) and [`NetworkTimeouts`](#network-timeouts) | Frozen data classes | Configure connections and phase timeouts for API requests. |
| [`BearerTokenCredential`](#bearer-token-credential) | Class | Supplies an existing PAT or Keycloak access token. |
| [`BrowserCredential`](#browser-credential) | Class | Signs in through the system browser and manages the token session. |
| [`PasswordCredential`](#password-credential) | Class | Signs in using the deployment's password grant. |
| [`IdentityOperations`](#identity-operations) | Operation group class | Provides account lookup and operation metadata through `client.identity`. |
| [`Account`](#account) and [`OperationInfo`](#operation-info) | Data classes | Represent an account and registered operation metadata. |
| [`Scope`](#scope) | Enum | Names the NOMAD permissions the Python SDK recognizes. |

## NomadClient class { #nomad-client }

Import from `nomad_python_api`. The client owns its API connection pool and uses the credential's API URL. Use it as a context manager to close the pool automatically.

### Constructor { #nomad-client-constructor }

```python
NomadClient(
    *,
    credential: BearerTokenCredential | BrowserCredential | PasswordCredential,
    allowed_scopes: Iterable[Scope] | None = None,
    ca_bundle: str | PathLike[str] | None = None,
    pool_limits: ConnectionLimits | None = None,
    timeouts: NetworkTimeouts | None = None,
)
```

| Keyword-only parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `credential` | `BearerTokenCredential`, `BrowserCredential`, or `PasswordCredential` | Yes | — | Supplies the access token and selects the deployment. |
| `allowed_scopes` | `Iterable[Scope]` or `None` | No | `None` | Local policy. The client takes an immutable snapshot of the supplied scopes. |
| `ca_bundle` | `str`, `PathLike[str]`, or `None` | No | `None` | Path to a trusted PEM CA bundle for API calls. With `None`, HTTPX uses its default trust bundle. |
| `pool_limits` | [`ConnectionLimits`](#connection-limits) or `None` | No | `None` | Connection limits for this client. `None` uses the settings class defaults. |
| `timeouts` | [`NetworkTimeouts`](#network-timeouts) or `None` | No | `None` | Per-phase timeouts for API calls. `None` uses the settings class defaults. |

### Properties

| Property | Type | Description |
| --- | --- | --- |
| `client.identity` | [`IdentityOperations`](#identity-operations) | Read-only operation group. Accessing it is local. |
| [`client.allowed_scopes`](#client-allowed-scopes) | `frozenset[Scope]` or `None` | Read-only local scope policy. |

#### `client.allowed_scopes` { #client-allowed-scopes }

Read the property without parentheses. `None` means all scopes pass the local policy. An empty `frozenset` blocks any operation that requires a scope. A populated set permits only operations whose required scopes are included. NOMAD independently checks the token's permissions. [`Scope` enum](#scope) · [NOMAD scope catalog](https://docs.nomad-lab.eu/explanation/auth.html#authorization-via-scopes)

### Instance methods

| Method signature | Return type | Description |
| --- | --- | --- |
| `close()` | `None` | Closes the client's API connections. A credential can be reused by another client on the same deployment. Later API calls on the closed client raise `RuntimeError`. |

### Worked example: open and close an Oasis client

Set `OASIS_PAT` to a token with `users:read` and replace the example URL with your Oasis API URL. Set `NOMAD_CA_BUNDLE` if the API uses a private CA.

```python
--8<-- "tests/snippets/identity/test_authentication.py:oasis_setup"
```

On success, `account` contains your Oasis account. The `finally` block closes the client's connections even if the lookup raises an exception.

### Worked example for connection limits and timeouts

Set `NOMAD_PAT` to a token with `users:read`. This client allows four connections, holds up to two idle connections, and waits up to three seconds for a free connection. A successful request returns an `Account`.

```python
--8<-- "tests/snippets/identity/test_authentication.py:client_network_settings"
```

Create and reuse a client within each HPC worker process. Four workers running this example have independent pools and can use up to 16 connections in total.

## ConnectionLimits data class { #connection-limits }

Import from `nomad_python_api`. All fields are optional keyword arguments and read-only after construction. The pool limits apply to each client.

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `max_connections` | `int` | `10` | Positive maximum number of connections in the pool. |
| `max_keepalive_connections` | `int` | `5` | Maximum idle connections to retain, up to `max_connections`. Use zero to close idle connections. |
| `keepalive_expiry` | `float` | `5.0` | Finite number of seconds before an idle connection expires. Use zero to expire idle connections immediately. |

## NetworkTimeouts data class { #network-timeouts }

Import from `nomad_python_api`. All fields are optional keyword arguments and read-only after construction. Give each timeout a finite, positive value in seconds.

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `connect` | `float` | `5.0` | Maximum wait to establish a connection. |
| `pool` | `float` | `10.0` | Maximum wait to acquire a connection. Failure raises `PoolTimeoutError`. |
| `read` | `float` | `10.0` | Maximum wait for incoming data during a network read. |
| `write` | `float` | `10.0` | Maximum wait to send a chunk during a network write. |

These limits apply to individual phases of the API request. Credentials use their own connection and sign-in settings.

## BearerTokenCredential class { #bearer-token-credential }

Import from `nomad_python_api.identity`. Holds an existing token for one deployment. Create a new credential when the token expires or rotates.

### Constructor

```python
BearerTokenCredential(token: str, *, endpoint: str = "prod")
```

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `token` | `str` | Yes | — | The PAT or Keycloak access token, without the `Bearer` prefix or whitespace. |
| `endpoint` | `str` | No | `"prod"` | Keyword-only. Central or a complete HTTPS NOMAD API v1 base URL. |

### Worked example: look up your account with a PAT

Set `NOMAD_PAT` to a Central PAT with `users:read`.

```python
--8<-- "tests/snippets/identity/test_authentication.py:named_setup"
```

`account.user_id` contains the ID of the token's NOMAD account. The guide also shows how to [use an existing Keycloak access token](index.md#use-an-existing-keycloak-access-token).

## BrowserCredential class { #browser-credential }

Import from `nomad_python_api.identity`. Opens the browser on the first permitted API call or when you call `authenticate()`. Keeps tokens in memory and uses a refresh token when Keycloak provides one.

### Constructor { #browser-credential-constructor }

```python
BrowserCredential(
    *,
    issuer: str,
    client_id: str,
    endpoint: str = "prod",
    authorization_endpoint: str | None = None,
    token_endpoint: str | None = None,
    discover: bool = False,
    identity_provider: str | None = None,
    ca_bundle: str | PathLike[str] | None = None,
    login_timeout: float = 180,
    refresh_margin: float = 30,
    redirect_port: int = 0,
    redirect_path: str = "/",
)
```

| Keyword-only parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `issuer` | `str` | Yes | — | Full HTTPS URL of the Keycloak realm. |
| `client_id` | `str` | Yes | — | Public client registered in that realm for the loopback callback. |
| `endpoint` | `str` | No | `"prod"` | Central or a complete HTTPS NOMAD API v1 base URL. |
| `authorization_endpoint` | `str` or `None` | When `discover=False` | `None` | HTTPS authorization URL on the issuer's origin. Pass it together with `token_endpoint`. |
| `token_endpoint` | `str` or `None` | When `discover=False` | `None` | HTTPS token URL on the issuer's origin. Pass it together with `authorization_endpoint`. |
| `discover` | `bool` | No | `False` | Set to `True` to get both Keycloak URLs from the issuer's discovery document. Leave both explicit URLs unset in this mode. |
| `identity_provider` | `str` or `None` | No | `None` | Optional realm provider alias sent as `kc_idp_hint`. |
| `ca_bundle` | `str`, `PathLike[str]`, or `None` | No | `None` | Trusted PEM CA bundle for credential HTTPS calls. Configure the browser's trust and `NomadClient(ca_bundle=...)` separately where needed. |
| `login_timeout` | `float` | No | `180` | Positive time in seconds to wait for the loopback callback. |
| `refresh_margin` | `float` | No | `30` | Seconds before expiry to renew, capped at half the access token's lifetime. Use `0` to refresh at expiry. |
| `redirect_port` | `int` | No | `0` | Loopback TCP port. `0` asks the operating system for an available port. |
| `redirect_path` | `str` | No | `"/"` | Absolute callback path registered for the public client. The listener uses `127.0.0.1`. |

### Instance methods

| Method signature | Return type | Description |
| --- | --- | --- |
| `authenticate()` | `None` | Starts a fresh browser sign-in and replaces the cached session on success. Can raise `BrowserAuthenticationError`. |

### Worked example: sign in through Helmholtz ID

Run the example on a computer where Python and the browser share a loopback interface. Complete institutional sign-in in the browser when it opens.

```python
--8<-- "tests/snippets/identity/test_browser_login.py:central_browser_login"
```

After sign-in, `account` contains your Central account. For a custom installation, see the [Oasis browser example](index.md#browser-login). The [REST reference](rest.md#browser-login-rest) lists the messages exchanged during sign-in.

## PasswordCredential class { #password-credential }

Import from `nomad_python_api.identity`. Uses the selected deployment's password grant. Keeps the username and password in memory for the credential's lifetime and repeats the exchange when a new token is needed.

### Constructor { #password-credential-constructor }

```python
PasswordCredential(
    *,
    username: str | None = None,
    password: str | None = None,
    endpoint: str = "prod",
    ca_bundle: str | PathLike[str] | None = None,
    refresh_margin: float = 30,
)
```

| Keyword-only parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `username` | `str` or `None` | With explicit credentials | `None` | NOMAD username. When both arguments are omitted, the credential reads `NOMAD_USERNAME` and `NOMAD_PASSWORD` at construction. |
| `password` | `str` or `None` | With explicit credentials | `None` | NOMAD password. Pass a complete pair through the arguments or the environment. |
| `endpoint` | `str` | No | `"prod"` | Central or a complete HTTPS NOMAD API v1 base URL. |
| `ca_bundle` | `str`, `PathLike[str]`, or `None` | No | `None` | Trusted PEM CA bundle for the password exchange. Configure `NomadClient(ca_bundle=...)` separately for API calls where needed. |
| `refresh_margin` | `float` | No | `30` | Seconds before expiry to renew, capped at half the access token's lifetime. Use `0` to renew at expiry. |

### Instance methods

| Method signature | Return type | Description |
| --- | --- | --- |
| `authenticate()` | `None` | Repeats the password exchange and caches the access token on success. Can raise `PasswordAuthenticationError`. Create a new credential when the password changes. |

### Worked example: sign in with a username and password

Set `NOMAD_USERNAME` and `NOMAD_PASSWORD` for an account that can use the deployment's password grant. This example uses Central.

```python
--8<-- "tests/snippets/identity/test_password_login.py:central_password_login"
```

The first call signs in and returns the account. See the [Oasis password example](index.md#password-login) for explicit arguments and the [REST reference](rest.md#password-login-rest) for the token exchange.

## IdentityOperations class { #identity-operations }

Access this operation group through the `client.identity` property.

### Instance methods

| Method signature | Return type | Description |
| --- | --- | --- |
| [`client.identity.me()`](#identity-me) | [`Account`](#account) | Looks up the signed-in account. |
| [`client.identity.get_operation_info(name)`](#identity-get-operation-info) | [`OperationInfo`](#operation-info) | Reads operation metadata locally. |

#### `me()` { #identity-me }

Returns the signed-in account through [`GET /users/me`](rest.md#get-users-me). Takes no arguments and requires `Scope.USERS_READ`. The credential may need to sign in or obtain a fresh token before the account request.

#### `get_operation_info(name)` { #identity-get-operation-info }

Returns the `OperationInfo` registered for an operation. An unknown name raises `KeyError`.

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `name` | `str` | Yes | — | Identity method name, such as `"me"`. |

### Worked example: check scopes and read the account { #worked-account-lookup }

Set `NOMAD_PAT` to a Central PAT with `users:read`. The example reads the client's policy and `me()` metadata before making the account request.

```python
--8<-- "tests/snippets/identity/test_authentication.py:inspect_and_read_account"
```

`Allowed` and `Required` both show `users:read`. The account request prints `Account returned: True` on success. `Username available` depends on the account returned by NOMAD.

## Data classes

### Account class { #account }

Import from `nomad_python_api.identity`. An immutable model returned by `client.identity.me()`.

| Field | Type | Required at construction | Default | Description |
| --- | --- | --- | --- | --- |
| `user_id` | `str` | Yes | — | NOMAD account identifier. |
| `username` | `str` or `None` | No | `None` | Username, when returned by the deployment. |

The [worked account lookup](#worked-account-lookup) reads both fields from the result of `me()`.

### OperationInfo class { #operation-info }

Import from `nomad_python_api.identity`. An immutable model returned by `client.identity.get_operation_info(name)`.

| Field | Type | Required at construction | Default | Description |
| --- | --- | --- | --- | --- |
| `name` | `str` | Yes | — | Qualified operation name, such as `"identity.me"`. |
| `description` | `str` | Yes | — | Short summary of the operation. |
| `required_scopes` | `frozenset[Scope]` | Yes | — | Scopes required by the operation. |

The [worked account lookup](#worked-account-lookup) reads `required_scopes` from `get_operation_info("me")`.

## Scope enum { #scope }

Import from `nomad_python_api`. `Scope` is a string enum. Use `list(Scope)` to list the members supported by the installed SDK.

| Enum member | Value | Description |
| --- | --- | --- |
| `Scope.USERS_READ` | `"users:read"` | Permission required to read the authenticated account. |

The [worked account lookup](#worked-account-lookup) uses `Scope.USERS_READ` to set the local policy and reads `scope.value` to display the permission name.

## Exceptions { #exceptions }

Import these exception classes from `nomad_python_api.exceptions`. Catch `NomadError` to handle SDK request and authentication failures together.

| Exception class | Base class | Meaning |
| --- | --- | --- |
| `NomadError` | `Exception` | Base class for SDK request failures. |
| `ScopeNotAllowedError` | `NomadError` | The local client policy blocked an operation. Read `operation` (`str`) and `missing_scopes` (`frozenset[Scope]`) for context. |
| `CredentialEndpointMismatchError` | `NomadError` | The deployment check rejected a request outside the credential's binding. |
| `BrowserAuthenticationError` | `NomadError` | Browser sign-in or communication with Keycloak failed. Check the issuer, callback registration, browser, or timeout. |
| `ReauthenticationRequiredError` | `BrowserAuthenticationError` | The browser credential needs a fresh sign-in. Call `credential.authenticate()`. |
| `PasswordAuthenticationError` | `NomadError` | Password sign-in or token acquisition failed. Check the credentials and deployment's password-grant setting. After a rejection, call `credential.authenticate()` to try again with the same credentials. |
| `HttpResponseError` | `NomadError` | NOMAD returned an unexpected HTTP status. Read `operation` (`str`) and `status_code` (`int`) for context. |
| `ClientAuthenticationError` | `HttpResponseError` | NOMAD returned HTTP 401. Check the token's expiry and issuing deployment. |
| `AuthorizationError` | `HttpResponseError` | NOMAD returned HTTP 403. Check token scopes and account access. |
| `RateLimitError` | `HttpResponseError` | NOMAD returned HTTP 429. Wait before trying again. |
| `TransportError` | `NomadError` | The API transport failed or timed out. Check connectivity and certificate trust. |
| `PoolTimeoutError` | `TransportError` | The data request timed out before it acquired a connection. Review client concurrency and the pool wait budget. |
| `InvalidResponseError` | `NomadError` | The API response could not be interpreted as the expected account. |

### Worked example: handle scope and authentication errors

Run this inside an open `NomadClient` context. Set `allowed_scopes=set()` when constructing the client to see a local scope error. The example prints the missing scopes without sending an account request.

```python
--8<-- "tests/snippets/identity/test_authentication.py:error_recovery"
```
