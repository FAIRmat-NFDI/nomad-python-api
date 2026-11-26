# Identity Python API { .api-reference-title }

<div id="authentication-python-api"></div>

## Summary

This reference covers client setup, credentials, permissions, accounts, users, groups, and personal access tokens. The [Identity guide](index.md#examples) has runnable examples. The [REST reference](rest.md) has request and response fields for the underlying HTTP endpoints.

<nav class="api-reference-nav" aria-label="Identity API sections">
  <a href="#client-reference"><strong>Clients</strong><span>Client options, connections, and timeouts</span></a>
  <a href="#credential-reference"><strong>Authentication</strong><span>Bearer tokens, browser login, and passwords</span></a>
  <a href="#scope-and-error-reference"><strong>Access and scopes</strong><span>Permissions and exceptions</span></a>
  <a href="#account-reference"><strong>Accounts and users</strong><span>Profiles, account methods, and user lookup</span></a>
  <a href="#groups-reference"><strong>Groups</strong><span>Membership, roles, and listing</span></a>
  <a href="#pat-reference"><strong>Personal access tokens</strong><span>Creation, filtering, rotation, and data models</span></a>
</nav>

??? info "Browse classes and models"

    | Type | Kind | Purpose |
    | --- | --- | --- |
    | [`NomadClient`](#nomad-client) | Class | Runs operations against the credential's deployment. |
    | [`NomadTransport`](#nomad-transport) | Class | Owns a connection pool that several clients can borrow. |
    | [`ConnectionLimits`](#connection-limits) and [`NetworkTimeouts`](#network-timeouts) | Frozen data classes | Configure connections and phase timeouts for API requests. |
    | [`BearerTokenCredential`](#bearer-token-credential) | Class | Supplies an existing PAT or Keycloak access token. |
    | [`BrowserCredential`](#browser-credential) | Class | Signs in through the system browser and manages the token session. |
    | [`PasswordCredential`](#password-credential) | Class | Signs in using the deployment's password grant. |
    | [`IdentityOperations`](#identity-operations) | Operation group class | Provides account lookup and operation metadata through `client.identity`. |
    | [`Account`](#account) and [`OperationInfo`](#operation-info) | Data classes | Represent an account and registered operation metadata. |
    | [`User`](#user) | Pydantic model | Holds an account profile for local use and export. |
    | [`UserOperations`](#users-reference) and [`GroupOperations`](#groups-reference) | Operation groups | Look up users and manage group membership. |
    | [`PatOperations`](#pat-operations) | Operation group class | Creates, lists, inspects, rotates, and revokes personal access tokens. |
    | [PAT models](#pat-models) and [`PatList`](#pat-list-type) | Data models and iterable | Hold PAT options and results and provide lazy listing. |
    | [`Scope`](#scope) | Enum | Names the NOMAD permissions the Python SDK recognizes. |

## Clients and connections { #client-reference .api-reference-section }

### NomadClient class { #nomad-client }

Import from `nomad_python_api`. The client owns its API connection pool and uses the credential's API URL. Use it as a context manager to close the pool automatically.

#### Constructor { #nomad-client-constructor }

```python
NomadClient(
    *,
    credential: BearerTokenCredential | BrowserCredential | PasswordCredential,
    allowed_scopes: Iterable[Scope] | None = None,
    ca_bundle: str | PathLike[str] | None = None,
    pool_limits: ConnectionLimits | None = None,
    timeouts: NetworkTimeouts | None = None,
    transport: NomadTransport | None = None,
    http_client: httpx.Client | None = None,
)
```

| Keyword-only parameter | Type | Required or default | Description |
| --- | --- | --- | --- |
| `credential` | `BearerTokenCredential`, `BrowserCredential`, or `PasswordCredential` | **Required** | Supplies the access token and selects the deployment. |
| `allowed_scopes` | `Iterable[Scope]` or `None` | `None` | Local policy. The client takes an immutable snapshot of the supplied scopes. |
| `ca_bundle` | `str`, `PathLike[str]`, or `None` | `None` | Path to a trusted PEM CA bundle for API calls. With `None`, HTTPX uses its default trust bundle. |
| `pool_limits` | [`ConnectionLimits`](#connection-limits) or `None` | `None` | Connection limits for this client. `None` uses the settings class defaults. |
| `timeouts` | [`NetworkTimeouts`](#network-timeouts) or `None` | `None` | Per-phase timeouts for API calls. `None` uses the settings class defaults. |
| `transport` | [`NomadTransport`](#nomad-transport) or `None` | `None` | **Advanced.** Caller-owned connection pool. Set `pool_limits` and `ca_bundle` on the transport. Set `timeouts` on each client as needed. |
| `http_client` | Synchronous `httpx.Client` or `None` | `None` | **Advanced.** Trusted, caller-owned HTTPX client. Configure its network settings when you create it. Combining it with `transport`, `pool_limits`, `ca_bundle`, or `timeouts` raises `ValueError`. |

<strong class="api-reference-label">Returns</strong> A `NomadClient` instance. Construction sets up the client. Token acquisition happens when a request needs it.

<strong class="api-reference-label">Raises</strong> `TypeError` for invalid types of scope values or network objects. `ValueError` for incompatible options or closed caller-owned resources.

##### Connection ownership and configuration

Start with the default client. Choose a borrowed connection setup when the [advanced use cases](connections.md#share-or-borrow-http-connections) apply.

| Mode | Configure pool and CA trust on | Configure API timeouts on | Close the pool with |
| --- | --- | --- | --- |
| Default client | `NomadClient` | `NomadClient` | `NomadClient.close()` or its context manager |
| Shared transport | `NomadTransport` | Each `NomadClient` | `NomadTransport.close()` or its outer context manager |
| Existing HTTPX client | The HTTPX client or its transport | The HTTPX client | The HTTPX client's `close()` or its outer context manager |

Providing `pool_limits` or `ca_bundle` on a client that uses `transport` raises `ValueError`. A closed injected object also raises `ValueError` during construction. See [when to choose each mode](connections.md#tune-network-settings).

#### Properties

| Property | Type | Description |
| --- | --- | --- |
| [`client.identity`](#client-identity) | [`IdentityOperations`](#identity-operations) | Read-only operation group. Accessing it is local. |
| [`client.allowed_scopes`](#client-allowed-scopes) | `frozenset[Scope]` or `None` | Read-only local scope policy. |

##### `client.identity` { #client-identity }

<strong class="api-reference-label">Returns</strong> Read-only [`IdentityOperations`](#identity-operations) bound to this client. Reading the property makes no request.

##### `client.allowed_scopes` { #client-allowed-scopes }

<strong class="api-reference-label">Returns</strong> Read-only `frozenset[Scope] | None`. `None` means all scopes pass the local policy. An empty set blocks any operation that requires a scope. A populated set permits only operations whose required scopes are included. NOMAD independently checks the token's permissions. [`Scope` enum](#scope) · [NOMAD scope catalog](https://docs.nomad-lab.eu/explanation/auth.html#authorization-via-scopes)

#### `NomadClient.close()` { #nomad-client-close }

<strong class="api-reference-label">Signature</strong> `close() -> None`

<strong class="api-reference-label">Parameters</strong> None.

<strong class="api-reference-label">Returns</strong> `None` after closing the client and its owned connections. Caller-owned pools and HTTP clients stay open. Repeated calls are safe. Later API calls raise `RuntimeError`.

#### Worked example: open and close an Oasis client

Set `OASIS_PAT` to a token with `users:read` and replace the example URL with your Oasis API URL. Set `ca_bundle` to the PEM bundle path for a private CA, or to `None` for a publicly trusted CA.

```python
--8<-- "tests/snippets/identity/test_authentication.py:oasis_setup"
```

On success, `account` contains your Oasis account. The `finally` block closes the client's connections even if the lookup raises an exception.

#### Worked example for connection limits and timeouts

Set `NOMAD_PAT` to a token with `users:read`. This client allows four connections, holds up to two idle connections, and waits up to three seconds for a free connection. A successful request returns an `Account`.

```python
--8<-- "tests/snippets/identity/test_authentication.py:client_network_settings"
```

Create and reuse a client within each HPC worker process. Four workers running this example have independent pools and can use up to 16 connections in total.

### ConnectionLimits data class { #connection-limits }

Import from `nomad_python_api`. All fields are optional keyword arguments and read-only after construction. The pool limits apply to each client.

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `max_connections` | `int` | `10` | Positive maximum number of connections in the pool. |
| `max_keepalive_connections` | `int` | `5` | Maximum idle connections to retain, up to `max_connections`. Use zero to close idle connections. |
| `keepalive_expiry` | `float` | `5.0` | Finite number of seconds before an idle connection expires. Use zero to expire idle connections immediately. |

<strong class="api-reference-label">Returns</strong> A frozen `ConnectionLimits` instance.

<strong class="api-reference-label">Raises</strong> `ValueError` for out-of-range or invalid values.

### NetworkTimeouts data class { #network-timeouts }

Import from `nomad_python_api`. All fields are optional keyword arguments and read-only after construction. Give each timeout a finite, positive value in seconds.

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `connect` | `float` | `5.0` | Maximum wait to establish a connection. |
| `pool` | `float` | `10.0` | Maximum wait to acquire a connection in an SDK-managed HTTP session. Failure raises `PoolTimeoutError`. |
| `read` | `float` | `10.0` | Maximum wait for incoming data during a network read. |
| `write` | `float` | `10.0` | Maximum wait to send a chunk during a network write. |

These limits apply to individual phases of the API request. Values above Python's platform-specific `threading.TIMEOUT_MAX` raise `ValueError` during construction. Credentials use their own connection and sign-in settings.

<strong class="api-reference-label">Returns</strong> A frozen `NetworkTimeouts` instance.

<strong class="api-reference-label">Raises</strong> `ValueError` for invalid or unrepresentable timeout values.

### NomadTransport class { #nomad-transport }

!!! info "Advanced · Optional"

    Use this separate object when several sessions in one process need the same connection budget. For one client, [configure the SDK-owned pool directly](connections.md#tune-network-settings).

Import from `nomad_python_api`. Use a context manager or call `close()` after all borrowing clients finish. The pool is shared within a process. Each borrowing client keeps its own HTTP session, cookies, credential, and scope policy.

| Keyword-only argument | Type | Default | Purpose |
| --- | --- | --- | --- |
| `pool_limits` | `ConnectionLimits` or `None` | `None` | Shared connection limits. |
| `ca_bundle` | `str`, `PathLike[str]`, or `None` | `None` | Trusted PEM CA bundle for the shared pool. |

<strong class="api-reference-label">Returns</strong> A `NomadTransport` instance. Both constructor arguments are optional.

<strong class="api-reference-label">Raises</strong> `TypeError` for invalid pool settings. CA-loading errors propagate if the supplied bundle cannot be used.

#### `NomadTransport.is_closed` { #nomad-transport-is-closed }

<strong class="api-reference-label">Returns</strong> Read-only `bool`. `True` indicates the shared pool is closed.

#### `NomadTransport.close()` { #nomad-transport-close }

<strong class="api-reference-label">Signature</strong> `close() -> None`

<strong class="api-reference-label">Parameters</strong> None.

<strong class="api-reference-label">Returns</strong> `None` after closing the shared pool. Call it after the borrowing clients finish. Repeated calls are safe.

### Borrowed HTTPX client { #borrowed-httpx-client }

See the [worked network examples](connections.md#share-or-borrow-http-connections). NOMAD borrows the HTTPX client's connection pool, proxy, TLS settings, timeouts, and hooks. The SDK constructs its own headers and query parameters and disables automatic redirects. The borrowed client's default headers, cookies, query parameters, and authentication stay with the application's own requests. Credential exchanges use their own network settings.

#### Response cookies { #borrowed-httpx-response-cookies }

NOMAD SDK requests omit cookies from the borrowed HTTPX client's jar. HTTPX can still store `Set-Cookie` values from NOMAD responses in that jar. Later direct application requests through the same HTTPX client may send those cookies when their domain, path, and other cookie rules match.

For custom network settings with cookie isolation from other application requests, dedicate an HTTPX client to NOMAD. For several NOMAD clients that need one connection pool and separate cookie jars, use [`NomadTransport`](#nomad-transport).

#### Request hooks and errors

Use a trusted HTTPX client with certificate verification enabled. Its hooks can inspect and modify authenticated requests. Response hooks run before the SDK checks status, content encoding, and the 256 KiB JSON body limit. Keep hooks focused on response metadata. A hook that reads or decodes the response may buffer the body before the SDK can enforce its limit.

If a response hook calls `raise_for_status()` on the original NOMAD response, the SDK raises the corresponding HTTP exception, such as `AuthorizationError` for HTTP `403` or `RateLimitError` for HTTP `429`. A status error for a separate request made by the hook, or another dispatch or hook failure, raises `TransportError`. In those cases the original request may already have reached NOMAD. The SDK reserves `PoolTimeoutError` for connection waits it can classify as unsent.

## Authentication { #credential-reference .api-reference-section }

### BearerTokenCredential class { #bearer-token-credential }

Import from `nomad_python_api.identity`. Holds an existing token for one deployment. Create a new credential when the token expires or rotates.

#### Constructor

```python
BearerTokenCredential(token: str, *, endpoint: str = "prod", pat_id: str | None = None)
```

| Parameter | Type | Required or default | Description |
| --- | --- | --- | --- |
| `token` | `str` | **Required** | The PAT or Keycloak access token, without the `Bearer` prefix or whitespace. |
| `endpoint` | `str` | `"prod"` | Keyword-only. Central or a complete HTTPS NOMAD API v1 base URL. |
| `pat_id` | `str \| None` | `None` | 24-character hexadecimal metadata ID for referring to this PAT from a management call. |

<strong class="api-reference-label">Returns</strong> A `BearerTokenCredential` instance bound to the selected deployment.

<strong class="api-reference-label">Raises</strong> `ValueError` for an invalid token, endpoint, or PAT metadata ID.

#### `BearerTokenCredential.pat_id` { #bearer-pat-id }

<strong class="api-reference-label">Returns</strong> Read-only `str | None`. This is the metadata ID when the credential carries one.

#### `BearerTokenCredential.from_issued()` { #bearer-from-issued }

<strong class="api-reference-label">Signature</strong> `from_issued(issued: PatIssuedResult) -> BearerTokenCredential`

<strong class="api-reference-label">Parameters</strong> `issued` is a required [`PatIssuedResult`](#pat-issued-result) returned by `pats.create()` or `pats.rotate()`.

<strong class="api-reference-label">Returns</strong> A credential carrying the issued PAT, metadata ID, and issuing deployment. The conversion is local.

<strong class="api-reference-label">Raises</strong> `ValueError` if the result lacks an SDK issuing deployment or contains an invalid credential. See the [PAT lifecycle example](pats.md#inspect-use-rotate-and-revoke).

#### Worked example: look up your account with a PAT

Set `NOMAD_PAT` to a Central PAT with `users:read`.

```python
--8<-- "tests/snippets/identity/test_authentication.py:named_setup"
```

`account.user_id` contains the ID of the token's NOMAD account. The guide also shows how to [use an existing Keycloak access token](sign-in.md#use-an-existing-keycloak-access-token).

### BrowserCredential class { #browser-credential }

Import from `nomad_python_api.identity`. Opens the browser on the first permitted API call or when you call `authenticate()`. Keeps tokens in memory and uses a refresh token when Keycloak provides one.

#### Constructor { #browser-credential-constructor }

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

| Keyword-only parameter | Type | Required or default | Description |
| --- | --- | --- | --- |
| `issuer` | `str` | **Required** | Full HTTPS URL of the Keycloak realm. |
| `client_id` | `str` | **Required** | Public client registered in that realm for the loopback callback. |
| `endpoint` | `str` | `"prod"` | Central or a complete HTTPS NOMAD API v1 base URL. |
| `authorization_endpoint` | `str` or `None` | `None` | Required when `discover=False`. HTTPS authorization URL on the issuer's origin. Pass it together with `token_endpoint`. |
| `token_endpoint` | `str` or `None` | `None` | Required when `discover=False`. HTTPS token URL on the issuer's origin. Pass it together with `authorization_endpoint`. |
| `discover` | `bool` | `False` | Set to `True` to get both Keycloak URLs from the issuer's discovery document. Leave both explicit URLs unset in this mode. |
| `identity_provider` | `str` or `None` | `None` | Optional realm provider alias sent as `kc_idp_hint`. |
| `ca_bundle` | `str`, `PathLike[str]`, or `None` | `None` | Trusted PEM CA bundle for credential HTTPS calls. Configure the browser's trust and `NomadClient(ca_bundle=...)` separately where needed. |
| `login_timeout` | `float` | `180` | Positive time in seconds to wait for the loopback callback. |

<strong class="api-reference-label">Returns</strong> A `BrowserCredential` instance. Construction does not open the browser.

<strong class="api-reference-label">Raises</strong> `ValueError` for invalid sign-in, callback, or endpoint settings. CA-loading errors propagate if the supplied bundle cannot be used.

#### Advanced settings { #advanced-browser-settings }

The defaults work for standard sign-in. Set the callback port or path when your Keycloak client registration requires specific values.

| Optional keyword argument | Type | Default | Description |
| --- | --- | --- | --- |
| `refresh_margin` | `float` | `30` | Start renewing up to this many seconds before expiry, capped at half the token's lifetime. Renewal happens on the next request that needs a token. Use `0` to wait until expiry. |
| `redirect_port` | `int` | `0` | Loopback TCP port. `0` asks the operating system for an available port. |
| `redirect_path` | `str` | `"/"` | Absolute callback path registered for the public client. The listener uses `127.0.0.1`. |

If Keycloak registers `http://127.0.0.1:9123/return`, pass `redirect_port=9123` and `redirect_path="/return"` to `BrowserCredential`. The browser returns the authorization code to that local callback. Set `endpoint` to the NOMAD API base URL for the deployment.

Browser credentials renew when a refresh token is available. [Password credentials](#password-credential) use the same margin to time their next password exchange.

#### `BrowserCredential.authenticate()` { #browser-authenticate }

<strong class="api-reference-label">Signature</strong> `authenticate() -> None`

<strong class="api-reference-label">Parameters</strong> None.

<strong class="api-reference-label">Returns</strong> `None` after sign-in succeeds and replaces the cached session.

<strong class="api-reference-label">Raises</strong> `BrowserAuthenticationError` if the browser flow, callback, or token exchange fails.

#### Worked example: sign in through Helmholtz ID

Run the example on a computer where Python and the browser share a loopback interface. Complete institutional sign-in in the browser when it opens.

```python
--8<-- "tests/snippets/identity/test_browser_login.py:central_browser_login"
```

After sign-in, `account` contains your Central account. For a custom installation, see the [Oasis browser example](sign-in.md#browser-login). The [REST reference](rest.md#browser-login-rest) lists the messages exchanged during sign-in.

### PasswordCredential class { #password-credential }

Import from `nomad_python_api.identity`. Uses the selected deployment's password grant. Keeps the username and password in memory for the credential's lifetime and repeats the exchange when a new token is needed.

#### Constructor { #password-credential-constructor }

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

| Keyword-only parameter | Type | Required or default | Description |
| --- | --- | --- | --- |
| `username` | `str` or `None` | `None` | NOMAD username. When both arguments are omitted, the credential reads `NOMAD_USERNAME` and `NOMAD_PASSWORD` at construction. |
| `password` | `str` or `None` | `None` | NOMAD password. Pass a complete pair through the arguments or the environment. |
| `endpoint` | `str` | `"prod"` | Central or a complete HTTPS NOMAD API v1 base URL. |
| `ca_bundle` | `str`, `PathLike[str]`, or `None` | `None` | Trusted PEM CA bundle for the password exchange. Configure `NomadClient(ca_bundle=...)` separately for API calls where needed. |
| `refresh_margin` | `float` | `30` | Advanced setting for when to repeat the password exchange. See [how the renewal margin works](#advanced-browser-settings). |

<strong class="api-reference-label">Returns</strong> A `PasswordCredential` instance. Construction reads the supplied arguments or environment.

<strong class="api-reference-label">Raises</strong> `ValueError` for invalid settings or an incomplete credential pair. CA-loading errors propagate if the supplied bundle cannot be used.

#### `PasswordCredential.authenticate()` { #password-authenticate }

<strong class="api-reference-label">Signature</strong> `authenticate() -> None`

<strong class="api-reference-label">Parameters</strong> None.

<strong class="api-reference-label">Returns</strong> `None` after a successful password exchange caches the access token. Create a new credential when the password changes.

<strong class="api-reference-label">Raises</strong> `PasswordAuthenticationError` when the exchange fails.

#### Worked example: sign in with a username and password

Replace the example username and set `NOMAD_PASSWORD` for an account that can use the deployment's password grant. This example uses Central.

```python
--8<-- "tests/snippets/identity/test_password_login.py:central_password_login"
```

The first call signs in and returns the account. See the [Oasis password example](sign-in.md#password-login) for explicit arguments and the [REST reference](rest.md#password-login-rest) for the token exchange.

## Access and scopes { #scope-and-error-reference .api-reference-section }

### Scope enum { #scope }

Import from `nomad_python_api`. `Scope` is a string enum. Use `list(Scope)` to list the members supported by the installed SDK.

| Enum member | Value | Description |
| --- | --- | --- |
| `Scope.USERS_READ` | `"users:read"` | Permission required to read the authenticated account. |
| `Scope.USERS_INVITE` | `"users:invite"` | Permission to invite a user on deployments that support invitations. |
| `Scope.GROUPS_READ` | `"groups:read"` | Permission to read groups. |
| `Scope.GROUPS_WRITE` | `"groups:write"` | Permission to create or edit groups. |
| `Scope.GROUPS_DELETE` | `"groups:delete"` | Permission to delete groups. |
| `Scope.UPLOADS_READ` | `"uploads:read"` | Permission to read Project data under NOMAD's upload API. |
| `Scope.TOKENS_CREATE` | `"tokens:create"` | Management permission for issuing a PAT. |
| `Scope.TOKENS_READ` | `"tokens:read"` | Management permission for listing and inspecting PATs. |
| `Scope.TOKENS_DELETE` | `"tokens:delete"` | Management permission for revoking a PAT. Rotation also requires create. |

The [worked account lookup](#worked-account-lookup) uses `Scope.USERS_READ` to set the local policy and reads `scope.value` to display the permission name.

### Exceptions { #exceptions }

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
| `InvalidResponseError` | `NomadError` | The API read response could not be interpreted as the expected model. |
| `UserNotFoundError` | `NomadError` | The exact selector returned no accessible user. |
| `AmbiguousUserError` | `NomadError` | The exact selector returned multiple users. |
| `GroupNotFoundError` | `HttpResponseError` | NOMAD could not find a group accessible to the caller. |
| `IdentityWriteOutcomeUnknownError` | `NomadError` | Check server state before repeating a user or group write. |
| `PatRequestError` | `HttpResponseError` | NOMAD rejected the PAT request or target state. |
| `PatNotFoundError` | `HttpResponseError` | NOMAD could not find a PAT accessible to the caller. |
| `PatWriteOutcomeUnknownError` | `NomadError` | Verify the result in NOMAD before repeating a PAT write. |

#### Worked example: handle scope and authentication errors

Run this inside an open `NomadClient` context. Set `allowed_scopes=set()` when constructing the client to see a local scope error. The example prints the missing scopes without sending an account request.

```python
--8<-- "tests/snippets/identity/test_authentication.py:error_recovery"
```

## Accounts and users { #account-reference .api-reference-section }

### IdentityOperations class { #identity-operations }

Access this operation group through the `client.identity` property. Its
read-only `users` and `groups` properties return [`UserOperations`](#users-reference)
and [`GroupOperations`](#groups-reference). Reading the properties is local.

#### `IdentityOperations.pats` { #identity-pats }

<strong class="api-reference-label">Returns</strong> Read-only [`PatOperations`](#pat-operations) bound to this client. Reading the property is local.

#### Instance methods

| Method signature | Return type | Description |
| --- | --- | --- |
| [`client.identity.me()`](#identity-me) | [`Account`](#account) | Looks up the signed-in account. |
| [`client.identity.get_operation_info(name)`](#identity-get-operation-info) | [`OperationInfo`](#operation-info) | Reads operation metadata locally. |

#### `me()` { #identity-me }

<strong class="api-reference-label">Signature</strong> `client.identity.me() -> Account`

<strong class="api-reference-label">Parameters</strong> None.

##### Returns { #me-returns }

!!! success "Account"

    An immutable [`Account`](#account) for the user authenticated by this client's credential. `user_id` is a nonempty string. Other fields, including `username`, profile details, and administrator flags, can be `None` when the deployment omits them or returns null. The result is a snapshot. Reading its fields makes no request.

##### Request and exceptions

<strong class="api-reference-label">Request</strong> [`GET /users/me`](rest.md#get-users-me) with `Scope.USERS_READ`. The credential may sign in or renew before the request.

<strong class="api-reference-label">Raises</strong>

| Exception | When |
| --- | --- |
| `ScopeNotAllowedError` | The local client policy excludes `users:read`. |
| `ClientAuthenticationError` or `AuthorizationError` | NOMAD returns `401` for rejected authentication or `403` for denied access. |
| `InvalidResponseError` | The response cannot be decoded or validated as an account. |
| `RateLimitError`, `HttpResponseError`, or `TransportError` | NOMAD throttles, returns another unexpected status, or the request fails at the transport layer. |
| `RuntimeError` | The client or its transport is closed. |

Credential errors, including `ReauthenticationRequiredError`, can propagate during sign-in or refresh. See the [exception reference](#exceptions).

<strong class="api-reference-label">Example</strong> With `NOMAD_PAT` set to a token with `users:read`, read the profile fields and convert the result to a `User`.

```python
--8<-- "tests/snippets/identity/test_authentication.py:me_profile"
```

#### `get_operation_info(name)` { #identity-get-operation-info }

<strong class="api-reference-label">Signature</strong> `client.identity.get_operation_info(name: str) -> OperationInfo`

<strong class="api-reference-label">Parameters</strong>

| Parameter | Type | Required or default | Description |
| --- | --- | --- | --- |
| `name` | `str` | **Required** | Identity method name, such as `"me"` or `"pats.rotate"`. |

<strong class="api-reference-label">Returns</strong> The registered [`OperationInfo`](#operation-info). The lookup is local.

<strong class="api-reference-label">Raises</strong> `KeyError` for an unknown operation name.

#### Worked example: check scopes and read the account { #worked-account-lookup }

Set `NOMAD_PAT` to a Central PAT with `users:read`. The example reads the client's policy and `me()` metadata before making the account request.

```python
--8<-- "tests/snippets/identity/test_authentication.py:inspect_and_read_account"
```

`Allowed` and `Required` both show `users:read`. The account request prints `Account returned: True` on success. `Username available` depends on the account returned by NOMAD.

<div id="data-classes"></div>

### Account class { #account }

Import from `nomad_python_api.identity`. This immutable model is the return value of [`client.identity.me()`](#identity-me). At construction, `user_id` and `username` can be passed positionally. The remaining fields are keyword-only.

| Field | Type | Required or default | Description |
| --- | --- | --- | --- |
| `user_id` | `str` | **Required** | NOMAD account identifier. |
| `username` | `str \| None` | `None` | Username on the deployment. |
| `name` | `str \| None` | `None` | Display name. |
| `first_name` | `str \| None` | `None` | Given names. |
| `last_name` | `str \| None` | `None` | Surname. |
| `email` | `str \| None` | `None` | Email address. |
| `affiliation` | `str \| None` | `None` | Organization or institution. |
| `affiliation_address` | `str \| None` | `None` | Organization address. |
| `created` | `datetime \| None` | `None` | Account creation time. |
| `repo_user_id` | `str \| None` | `None` | Legacy repository identifier. |
| `is_admin` | `bool \| None` | `None` | NOMAD administrator flag. |
| `is_oasis_admin` | `bool \| None` | `None` | Oasis administrator flag. |

#### `Account.as_user()` { #account-as-user }

<strong class="api-reference-label">Signature</strong> `as_user() -> User`

<strong class="api-reference-label">Parameters</strong> None.

<strong class="api-reference-label">Returns</strong> A new [`User`](#user) with the same profile fields. Conversion is local.

<strong class="api-reference-label">Raises</strong> Pydantic `ValidationError` if a manually constructed account contains invalid values.

#### `Account.get_all_pats()` { #account-get-all-pats }

<strong class="api-reference-label">Signature</strong> `get_all_pats(**options) -> PatList`

<strong class="api-reference-label">Parameters</strong> The optional [`pats.list()` arguments](#pat-list), including filters, `limit`, and `extra_query`. With no options, the listing uses the deployment's defaults.

<strong class="api-reference-label">Returns</strong> A lazy [`PatList`](#pat-list-type) of this account's PAT metadata. Iteration uses the originating client, requires `tokens:read`, and calls the PAT endpoint without repeating `GET /users/me`.

<strong class="api-reference-label">Raises</strong> `RuntimeError` for a detached account or closed client. Invalid options raise `ValueError`. The [PAT listing errors](#pat-errors) apply when the returned listing is consumed.

See the [worked account listing example](pats.md#list-and-filter-pats).

### User model { #user }

Import from `nomad_python_api.identity`. The Pydantic `User` model has the same [12 typed profile fields](#account). `user_id` is required and the other fields default to `None`. Constructing or converting the model is local. Use `model_dump(mode="json")` for an explicit JSON-compatible export. Account profiles may contain private information.

### OperationInfo class { #operation-info }

Import from `nomad_python_api.identity`. An immutable model returned by `client.identity.get_operation_info(name)`.

| Field | Type | Required or default | Description |
| --- | --- | --- | --- |
| `name` | `str` | **Required** | Qualified operation name, such as `"identity.me"`. |
| `description` | `str` | **Required** | Short summary of the operation. |
| `required_scopes` | `frozenset[Scope]` | **Required** | Scopes required by the operation. |

The [worked account lookup](#worked-account-lookup) reads `required_scopes` from `get_operation_info("me")`.

### UserOperations { #users-reference }

Use `client.identity.users`. Lookup and search require `Scope.USERS_READ`.
Invitations require `Scope.USERS_INVITE`.

| Method | Parameters | Returns | Exceptions and conditions |
| --- | --- | --- | --- |
| `get(*, user_id=None, username=None, email=None)` | Exactly one selector as a nonempty `str`. | [`User`](#user) | `ValueError` for invalid selection, `UserNotFoundError` for no match, `AmbiguousUserError` for multiple matches. |
| `get_by_id(user_id)`, `get_by_username(username)`, `get_by_email(email)` | One required `str`. | `User` | Same as `get()`. |
| `get_many(selectors)` | Required sequence of mappings, each with one of `user_id`, `username`, or `email` and a string value. | `list[User]` in input order. Empty input returns an empty list. | Same lookup errors as `get()`. Resolves each distinct selector once. |
| `search(*, prefix, extra_query=None)` | Required `prefix: str`. Optional custom query mapping. | `list[User]` of candidates. | `ValueError` for an empty prefix or extension collision. |
| `invite(options, *, extra_json=None)` | Required [`UserInviteOptions`](#user-invite-options) or matching dictionary. Optional custom JSON mapping. | `User` from the deployment. | `ValueError` for invalid options, `HttpResponseError` for a server rejection, `IdentityWriteOutcomeUnknownError` for an uncertain write. |
| `get_operation_info(name)` | Required unqualified operation name as `str`. | `OperationInfo` from the local registry. | `KeyError` for an unknown name. |

Read operations raise `InvalidResponseError` if the response cannot be
mapped to the return model. The [shared SDK errors](#exceptions) apply to
requests. See the [Users REST reference](rest.md#users-rest).

```python
--8<-- "tests/snippets/identity/test_users_and_groups.py:directory_lookup"
```

#### UserInviteOptions { #user-invite-options }

Import `UserInviteOptions` from `nomad_python_api.identity`.

| Field | Type | Required or default | Use |
| --- | --- | --- | --- |
| `email` | `str` | **Required** | Recipient email. |
| `username`, `first_name`, `last_name` | `str \| None` | `None` | Optional account name fields. |
| `affiliation`, `affiliation_address` | `str \| None` | `None` | Optional organization information. |
| `user_id`, `repo_user_id` | `str \| None` | `None` | Optional identifiers accepted by the standard provider. |
| `created` | `datetime \| None` | `None` | Optional provider creation timestamp. |

The server supplies the display name and administrator flags. See the
[invitation guide](users.md#invite-a-user) for prerequisites and delivery
behavior.

## Groups { #groups-reference .api-reference-section }

### GroupOperations

Access the group API through `client.identity.groups`.

| Method | Parameters | Returns | Scope |
| --- | --- | --- | --- |
| `list(*, limit=None, extra_query=None, **filters)` | Optional [listing options](#group-list). | Lazy `GroupList`. | `groups:read` during iteration. |
| `get(target)` | A group ID or a `Group`. | `Group`. | `groups:read`. |
| `create(*, name=None, description=None, members=None, legacy_member_ids=None, extra_json=None)` | See [write options](#group-write-options). | The created `Group`. | `groups:write`. Add `users:read` for a nonempty `members` list. |
| `update(target, *, name=None, description=None, legacy_member_ids=None, extra_json=None)` | A group ID or `Group`, plus [edit options](#group-write-options). | The updated `Group`. | `groups:write`. |
| `replace_members(target, *, members, owner=None, extra_json=None)` | Target and complete set of role-bearing membership inputs. Supply the current owner for a group ID. | `Group` with the server's updated data. | `groups:write`. |
| `delete(target)` | A group ID or a `Group`. | `None` on HTTP 204. | `groups:delete`. |
| `get_operation_info(name)` | Required unqualified operation name as `str`. | `OperationInfo` from the local registry. | Local lookup. |

Group lookup or writes to an unavailable target raise `GroupNotFoundError`.
Invalid options or membership raise `ValueError`. Bound objects from a
different deployment raise `CredentialEndpointMismatchError`. Reads can
raise `InvalidResponseError`. Uncertain writes raise
`IdentityWriteOutcomeUnknownError`. The operation lookup raises `KeyError`
for an unknown name. See [shared errors](#exceptions).

#### Group write options { #group-write-options }

| Option | Type | Required or default | Behavior |
| --- | --- | --- | --- |
| `name` | `str \| None` | `None` | Supply a nonempty name or omit the field. |
| `description` | `str \| None` | `None` | Send a description when supplied. |
| `owner` | `Account`, `User`, ID string, exact selector, or `None` | Required when replacing membership by group ID | Only accepted by `replace_members()`. It identifies the existing owner. |
| `members` | Sequence of `Account`, `User`, ID strings, exact selectors, or `GroupMember` | Optional for create. Required for replacement. | For creation, supply only members and maintainers. The SDK adds the signed-in user as owner when it constructs `members_info`. |
| `legacy_member_ids` | Sequence of ID strings or `None` | `None` | Deprecated REST ID-only format. Use separately from role-bearing membership. |
| `extra_json` | `Mapping[str, object] \| None` | `None` | Custom top-level body fields for a supported deployment. |

| Additional request | Required scope |
| --- | --- |
| Read the signed-in account once for nonempty create membership | `users:read` |
| Resolve an exact selector | `users:read` |

Loaded user objects and known IDs skip individual directory lookups.
The operation metadata reports the scope for the group route. Use the
table above to account for any lookup the SDK makes before the write.
See the [role example](groups.md#edit-group-metadata-and-replace-roles).

#### Group listing and pagination { #group-list }

All listing options are optional. `group_id` accepts a string or list of
strings. `user_id` and `search_terms` accept strings. `page_size` is a
nonnegative integer, `order_by` is a sort field, and `order` accepts
`"asc"` or `"desc"`. Choose at most one starting position: a
`page_after_value` string, one-based `page`, or nonnegative `page_offset`.
`limit` caps the total items. `extra_query` accepts a custom query mapping.

| Member | Parameters | Returns | Errors |
| --- | --- | --- | --- |
| `GroupList.filter(**filters)` | `group_id`, `user_id`, or `search_terms`. | New lazy `GroupList`. | `ValueError` for invalid or conflicting filters. |
| `GroupList.by_page(continuation_token=None)` | Optional opaque cursor string. | Iterator of `GroupPage`. | `ValueError` for incompatible resume options or if `limit` is set. Request and response errors occur during iteration. |

`GroupPage.items` is a tuple of groups. `pagination` is
`GroupPagination | None` and uses the same fields as [PAT pagination](#pat-pagination).
`next_cursor` is the optional continuation string from that metadata.
Offset-based resume uses the server's current sorted results.

#### Group and GroupMember models

| Model | Field | Type and availability |
| --- | --- | --- |
| `Group` | `group_id`, `owner_id` | Required strings. |
| `Group` | `name` | String. Defaults to `"Default Group Name"` when omitted. |
| `Group` | `description` | Optional string. |
| `Group` | `member_ids` | Optional tuple of user ID strings. |
| `Group` | `members` | Optional tuple of `GroupMember`. `None` indicates absent details. An empty tuple represents an empty list. |
| `GroupMember` | `user_id`, `role` | Required ID string. Role is `GroupRole` and defaults to `MEMBER`. |

`GroupRole` has the values `OWNER`, `MAINTAINER`, and `MEMBER`.

```python
--8<-- "tests/snippets/identity/test_users_and_groups.py:directory_create_group"
```

## Personal access tokens { #pat-reference .api-reference-section }

### PatOperations class { #pat-operations }

Access the operation group through `client.identity.pats`.

!!! info "PAT management credential"

    Use the authenticated user's management access token from the issuing deployment.

| Instance method | Required inputs | Return type | REST contract |
| --- | --- | --- | --- |
| [`create(options, *, extra_json=None)`](#pat-create) | Creation options | `PatIssuedResult` | [Create](rest.md#create-pat) |
| [`list(*, limit=None, extra_query=None, **filters)`](#pat-list) | None | `PatList` | [List](rest.md#list-pats) |
| [`get(target)`](#pat-get) | A PAT target | `PatMetadata` | [Get](rest.md#get-pat) |
| [`rotate(target)`](#pat-rotate) | A PAT target | `PatIssuedResult` | [Rotate](rest.md#rotate-pat) |
| [`revoke(target)` or `delete(target)`](#pat-revoke) | A PAT target | `None` | [Revoke](rest.md#revoke-pat) |
| [`get_operation_info(name)`](#pat-get-operation-info) | Method name | `OperationInfo` | Local lookup |

The [worked lifecycle](pats.md#manage-pats) covers typed options and reusable dictionaries,
access and rotation, and Oasis extensions.

#### `PatOperations.create()` { #pat-create }

<strong class="api-reference-label">Signature</strong> `create(options, *, extra_json=None) -> PatIssuedResult`

<strong class="api-reference-label">Parameters</strong>

| Parameter | Type | Required or default | Description |
| --- | --- | --- | --- |
| `options` | [`PatCreateOptions`](#pat-create-options) or `Mapping[str, object]` | **Required** | Creation fields. A mapping uses the same field names as the model. |
| `extra_json` | `Mapping[str, object] \| None` | `None` | Custom top-level JSON fields documented by the deployment. |

<strong class="api-reference-label">Returns</strong> A [`PatIssuedResult`](#pat-issued-result) with the new PAT's metadata and its one-time secret. The server returns `201`.

<strong class="api-reference-label">Raises</strong> `ValueError` for invalid dictionary options or extension collisions, `PatRequestError` for server validation, and `PatWriteOutcomeUnknownError` if the outcome cannot be confirmed. See [shared PAT errors](#pat-errors).

<strong class="api-reference-label">Required scope</strong> `tokens:create`.

With a Keycloak access token on the client, bind `pats = client.identity.pats`
and issue a PAT using typed options. The example prints metadata and expiry.

```python
--8<-- "tests/snippets/identity/test_pat_management.py:pat_create_object"
```

#### `PatOperations.list()` { #pat-list }

<strong class="api-reference-label">Signature</strong> `list(*, limit=None, extra_query=None, **filters) -> PatList`

<strong class="api-reference-label">Parameters</strong> All options are optional. Unset REST options use NOMAD's defaults.

| Options | Type | Default and behavior |
| --- | --- | --- |
| `search` | `str` | Case-insensitive search by token name. |
| `state` | `"active"` or `"inactive"` | Filter by whether the PAT is currently active. |
| `revoked` | `bool` | Filter by explicit revocation. |
| `created_after`, `created_before`, `last_used_after`, `last_used_before`, `expires_after`, `expires_before` | `datetime` or ISO 8601 string | Filter the corresponding dates. Include the timezone for reproducible runs. |
| `order_by` | `str` | Server default is `"created_desc"`. Select `created`, `expires`, `last_used`, or `name` with an `_asc` or `_desc` suffix. |
| `order` | `"asc"` or `"desc"` | Server default is `"asc"`. |
| `limit` | Nonnegative `int` | SDK cap on total items yielded. `0` makes no request. |
| `extra_query` | `Mapping[str, object] \| None` | Defaults to `None`. Additional query fields documented by the deployment. |
| `page_size` | Nonnegative `int` | Server default is `10`. `0` allows reading page metadata without items. |
| `page_after_value`, `page`, `page_offset` | Cursor `str`, 1-based `int`, or 0-based `int` | Starting position. Supply at most one. |

<strong class="api-reference-label">Returns</strong> A reusable [`PatList`](#pat-list-type) that yields `PatMetadata`. Building the listing makes no request. Each iteration starts a fresh listing.

<strong class="api-reference-label">Raises</strong> `ValueError` for invalid options or extension collisions and `RuntimeError` for a closed client. Server and response errors surface during iteration. See [shared PAT errors](#pat-errors).

<strong class="api-reference-label">Required scope when consumed</strong> `tokens:read`.

#### `PatOperations.get()` { #pat-get }

<strong class="api-reference-label">Signature</strong> `get(target) -> PatMetadata`

<strong class="api-reference-label">Parameters</strong> Required `target` is a 24-character hexadecimal metadata ID (`str`), a [`PatMetadata`](#pat-metadata) instance, or a [`BearerTokenCredential`](#bearer-token-credential) carrying that ID.

<strong class="api-reference-label">Returns</strong> [`PatMetadata`](#pat-metadata) for the selected PAT, including its scopes and available timestamps. HTTP `200` contains metadata only.

<strong class="api-reference-label">Raises</strong> `ValueError` for an invalid ID or a credential without one, `CredentialEndpointMismatchError` for a known deployment mismatch, and `PatNotFoundError` for a target `404`. See [shared PAT errors](#pat-errors).

<strong class="api-reference-label">Required scope</strong> `tokens:read`.

#### `PatOperations.rotate()` { #pat-rotate }

<strong class="api-reference-label">Signature</strong> `rotate(target) -> PatIssuedResult`

<strong class="api-reference-label">Parameters</strong> Required `target` accepts the [same forms as `get()`](#pat-get).

<strong class="api-reference-label">Returns</strong> A [`PatIssuedResult`](#pat-issued-result) with replacement metadata and its one-time secret. The server returns `200` and invalidates the old PAT.

<strong class="api-reference-label">Raises</strong> The target errors documented for [`get()`](#pat-get) or `PatRequestError` for HTTP `422`. HTTP `400` and unusable replacement credentials raise `PatWriteOutcomeUnknownError`. NOMAD can revoke the original before replacement creation fails. Check its status with `pats.get(target)` before another write. See [shared PAT errors](#pat-errors).

<strong class="api-reference-label">Required scopes</strong> `tokens:create` and `tokens:delete`.

#### `PatOperations.revoke()` and `delete()` { #pat-revoke }

<strong class="api-reference-label">Signatures</strong> `revoke(target) -> None` and `delete(target) -> None`.

<strong class="api-reference-label">Parameters</strong> Required `target` accepts the [same forms as `get()`](#pat-get).

<strong class="api-reference-label">Returns</strong> `None` on HTTP `204`. Both method names revoke the selected PAT.

<strong class="api-reference-label">Raises</strong> The target errors documented for [`get()`](#pat-get) and `PatWriteOutcomeUnknownError` if the outcome cannot be confirmed. See [shared PAT errors](#pat-errors).

<strong class="api-reference-label">Required scope</strong> `tokens:delete`.

#### `PatOperations.get_operation_info()` { #pat-get-operation-info }

<strong class="api-reference-label">Signature</strong> `get_operation_info(name: str) -> OperationInfo`

<strong class="api-reference-label">Parameters</strong> Required `name` is an unqualified PAT method name such as `"rotate"`. `"delete"` resolves to revocation metadata.

<strong class="api-reference-label">Returns</strong> [`OperationInfo`](#operation-info) for the method. This is a local lookup.

<strong class="api-reference-label">Raises</strong> `KeyError` for an unknown operation name.

### PatList iterable { #pat-list-type }

Iterating a `PatList` yields one [`PatMetadata`](#pat-metadata) at a time. Each iteration starts a new listing. The server fetches additional pages when the caller continues iterating.

#### `PatList.filter()` { #pat-list-filter }

<strong class="api-reference-label">Signature</strong> `filter(**filters) -> PatList`

<strong class="api-reference-label">Parameters</strong> Optional named filters are `search`, `state`, `revoked`, and the six [date bounds](#pat-list).

<strong class="api-reference-label">Returns</strong> A new `PatList` with the additional server-side filters. The original remains reusable. The method makes no request.

<strong class="api-reference-label">Raises</strong> `ValueError` for an unsupported filter, invalid value, or a conflicting value for a filter already set.

#### `PatList.by_page()` { #pat-list-by-page }

<strong class="api-reference-label">Signature</strong> `by_page(continuation_token: str | None = None) -> Iterator[PatPage]`

<strong class="api-reference-label">Parameters</strong> Optional `continuation_token` is an opaque cursor from a prior page. The default `None` uses the listing's starting position. Use either the cursor or an explicit starting position.

<strong class="api-reference-label">Returns</strong> An iterator yielding whole [`PatPage`](#pat-page) objects. Requests occur during iteration.

NOMAD interprets the cursor as an offset into the current sorted results.
Changes before that offset can skip or repeat PATs. See the [checkpoint guide](pats.md#advanced-paging-and-checkpointing).

<strong class="api-reference-label">Raises</strong> `ValueError` for an invalid cursor, conflicting starting positions, or a listing with `limit`. The [PAT listing errors](#pat-errors) also apply during iteration.

### PAT models { #pat-models }

Import these models from `nomad_python_api.identity`. Pydantic model constructors return instances of the named model and raise `ValidationError` for invalid input.

#### `PatCreateOptions` { #pat-create-options }

| Field | Type | Required or default | Description |
| --- | --- | --- | --- |
| `name` | `str` | **Required** | PAT label. |
| `scopes` | Sequence of `Scope` or `str` | **Required** | Explicit permissions. The model stores a tuple of scope strings. |
| `description` | `str \| None` | `None` | Optional PAT description. |
| `expires_in_days` | `int \| None` | `30` | PAT lifetime in days. Unset uses the server default. Explicit `None` sends JSON null. |

#### `PatMetadata` { #pat-metadata }

| Field | Type | Required or default | Description |
| --- | --- | --- | --- |
| `id` | `str` | **Required** | 24-character hexadecimal PAT metadata ID for management calls. |
| `name` | `str` | **Required** | PAT label. |
| `scopes` | `tuple[str, ...]` | **Required** | Granted permissions. |
| `revoked` | `bool` | **Required** | Whether the PAT has been explicitly revoked. |
| `created_at` | `datetime` | **Required** | Creation time. |
| `description` | `str \| None` | `None` | Optional description. |
| `expired_at` | `datetime \| None` | `None` | Expiration time, when supplied. |
| `last_used_at` | `datetime \| None` | `None` | Most recent use, when supplied. |

#### `PatIssuedResult` { #pat-issued-result }

| Field | Type | Required or default | Description |
| --- | --- | --- | --- |
| `pat` | `PatMetadata` | **Required** | Metadata for the issued token. |
| `raw_token` | `SecretStr` | **Required** | One-time token secret. Excluded from representations and model serialization. |

Use [`BearerTokenCredential.from_issued()`](#bearer-from-issued) to use it in a job. Pickling the issued result raises `TypeError`.

#### `PatPage` { #pat-page }

| Returned member | Type | Description |
| --- | --- | --- |
| `items` | `tuple[PatMetadata, ...]` | The page's records, mapped from REST `data`. |
| `query` | `PatFilters` | The filters echoed by NOMAD. |
| `pagination` | `PatPagination` | Page metadata, including the total match count. |
| `next_cursor` | `str \| None` | Read-only continuation token. `None` indicates the server supplied no next cursor. |

The first three fields are required. `next_cursor` is derived from `pagination.next_page_after_value`.

#### `PatFilters` { #pat-filters }

The echoed filters consist of `search: str`, `state: Literal["active", "inactive"]`, `revoked: bool`, and `created_after`, `created_before`, `last_used_after`, `last_used_before`, `expires_after`, and `expires_before` as `datetime` values. All fields are optional and default to `None`. See [list parameters](#pat-list) for what each filter selects.

#### `PatPagination` { #pat-pagination }

| Field | Type | Required or default | Description |
| --- | --- | --- | --- |
| `total` | `int` | **Required** | Total records matching the server query. |
| `page_size`, `page`, `page_offset` | `int \| None` | `None` | Returned size and starting position, when supplied. |
| `order_by`, `order` | `str \| None` | `None` | Returned sort key and direction. `order` is `"asc"` or `"desc"` when supplied. |
| `page_after_value`, `next_page_after_value` | `str \| None` | `None` | Opaque cursors for the current and next pages. |
| `page_url`, `next_page_url`, `prev_page_url`, `first_page_url` | `str \| None` | `None` | Server-supplied links. The SDK advances via the cursor against the configured endpoint. |

#### PAT errors { #pat-errors }

| Error | When to expect it | What to check |
| --- | --- | --- |
| `ScopeNotAllowedError` | The caller's local policy blocks the request. | Include the operation's documented scopes in `allowed_scopes`. NOMAD also checks the access token. |
| `ClientAuthenticationError`, `AuthorizationError` | HTTP `401` or `403`, respectively. | Check token validity and deployment for `401`. Use a management access token with the required scopes for `403`. |
| `CredentialEndpointMismatchError` | A credential or returned metadata identifies a different deployment. | Connect to the issuing deployment. |
| `ValueError` | Invalid options, missing PAT metadata ID, conflicting filters, or an extension collision. | Use the fields described above. |
| `PatRequestError`, `PatNotFoundError` | HTTP `400` outside rotation or HTTP `422` for request errors. HTTP `404` for an unavailable target. | Inspect supported options, target ID, active state, and account. |
| `RateLimitError`, `PoolTimeoutError` | HTTP `429` or a confirmed unsent pool wait timeout. | Let concurrent work settle and review the pool or request rate. |
| `InvalidResponseError` | Read response cannot be interpreted or returns a repeated cursor. | Check deployment compatibility before continuing. |
| `PatWriteOutcomeUnknownError` | A write may have taken effect. This includes HTTP `400` during rotation or a success response containing an unusable issued credential. | Check the original PAT after a rotation error and inspect the PAT list in NOMAD before another write. |
