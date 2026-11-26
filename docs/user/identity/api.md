# Authentication Python API

## Summary

This reference lists the SDK classes, instance methods, read-only properties, model fields, and enum members used for authentication and account lookup. The [Authentication guide](index.md#examples) has runnable examples. The [REST reference](rest.md) has request and response fields for the underlying HTTP endpoints.

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
    transport: NomadTransport | None = None,
    http_client: httpx.Client | None = None,
)
```

| Keyword-only parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `credential` | `BearerTokenCredential`, `BrowserCredential`, or `PasswordCredential` | Yes | — | Supplies the access token and selects the deployment. |
| `allowed_scopes` | `Iterable[Scope]` or `None` | No | `None` | Local policy. The client takes an immutable snapshot of the supplied scopes. |
| `ca_bundle` | `str`, `PathLike[str]`, or `None` | No | `None` | Path to a trusted PEM CA bundle for API calls. With `None`, HTTPX uses its default trust bundle. |
| `pool_limits` | [`ConnectionLimits`](#connection-limits) or `None` | No | `None` | Connection limits for this client. `None` uses the settings class defaults. |
| `timeouts` | [`NetworkTimeouts`](#network-timeouts) or `None` | No | `None` | Per-phase timeouts for API calls. `None` uses the settings class defaults. |
| `transport` | [`NomadTransport`](#nomad-transport) or `None` | No | `None` | **Advanced.** Caller-owned connection pool. Set `pool_limits` and `ca_bundle` on the transport. Set `timeouts` on each client as needed. |
| `http_client` | Synchronous `httpx.Client` or `None` | No | `None` | **Advanced.** Trusted, caller-owned HTTPX client. Configure its network settings when you create it. Combining it with `transport`, `pool_limits`, `ca_bundle`, or `timeouts` raises `ValueError`. |

#### Connection ownership and configuration

Start with the default client. Choose a borrowed connection setup when the [advanced use cases](connections.md#share-or-borrow-http-connections) apply.

| Mode | Configure pool and CA trust on | Configure API timeouts on | Close the pool with |
| --- | --- | --- | --- |
| Default client | `NomadClient` | `NomadClient` | `NomadClient.close()` or its context manager |
| Shared transport | `NomadTransport` | Each `NomadClient` | `NomadTransport.close()` or its outer context manager |
| Existing HTTPX client | The HTTPX client or its transport | The HTTPX client | The HTTPX client's `close()` or its outer context manager |

Providing `pool_limits` or `ca_bundle` on a client that uses `transport` raises `ValueError`. A closed injected object also raises `ValueError` during construction. See [when to choose each mode](connections.md#tune-network-settings).

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
| `close()` | `None` | Closes the client and the connections it owns. Caller-owned transports and HTTP clients stay open. Later API calls on the closed client raise `RuntimeError`. |

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
| `pool` | `float` | `10.0` | Maximum wait to acquire a connection in an SDK-managed HTTP session. Failure raises `PoolTimeoutError`. |
| `read` | `float` | `10.0` | Maximum wait for incoming data during a network read. |
| `write` | `float` | `10.0` | Maximum wait to send a chunk during a network write. |

These limits apply to individual phases of the API request. Values above Python's platform-specific `threading.TIMEOUT_MAX` raise `ValueError` during construction. Credentials use their own connection and sign-in settings.

## NomadTransport class { #nomad-transport }

!!! info "Advanced · Optional"

    Use this separate object when several sessions in one process need the same connection budget. For one client, [configure the SDK-owned pool directly](connections.md#tune-network-settings).

Import from `nomad_python_api`. Use a context manager or call `close()` after all borrowing clients finish. The pool is shared within a process. Each borrowing client keeps its own HTTP session, cookies, credential, and scope policy.

| Keyword-only argument | Type | Default | Purpose |
| --- | --- | --- | --- |
| `pool_limits` | `ConnectionLimits` or `None` | `None` | Shared connection limits. |
| `ca_bundle` | `str`, `PathLike[str]`, or `None` | `None` | Trusted PEM CA bundle for the shared pool. |

| Member | Kind | Returns | Purpose |
| --- | --- | --- | --- |
| `is_closed` | Read-only property | `bool` | Indicates whether the shared pool is closed. |
| `close()` | Instance method | `None` | Closes the shared pool. Call after its borrowing clients finish. Repeated calls are safe. |

## Borrowed HTTPX client { #borrowed-httpx-client }

See the [worked network examples](connections.md#share-or-borrow-http-connections). NOMAD borrows the HTTPX client's connection pool, proxy, TLS settings, timeouts, and hooks. The SDK constructs its own headers and query parameters and disables automatic redirects. The borrowed client's default headers, cookies, query parameters, and authentication stay with the application's own requests. Credential exchanges use their own network settings.

### Response cookies { #borrowed-httpx-response-cookies }

NOMAD SDK requests omit cookies from the borrowed HTTPX client's jar. HTTPX can still store `Set-Cookie` values from NOMAD responses in that jar. Later direct application requests through the same HTTPX client may send those cookies when their domain, path, and other cookie rules match.

For custom network settings with cookie isolation from other application requests, dedicate an HTTPX client to NOMAD. For several NOMAD clients that need one connection pool and separate cookie jars, use [`NomadTransport`](#nomad-transport).

### Request hooks and errors

Use a trusted HTTPX client with certificate verification enabled. Its hooks can inspect and modify authenticated requests. Response hooks run before the SDK checks status, content encoding, and the 256 KiB JSON body limit. Keep hooks focused on response metadata. A hook that reads or decodes the response may buffer the body before the SDK can enforce its limit.

If a response hook calls `raise_for_status()` on the original NOMAD response, the SDK raises the corresponding HTTP exception, such as `AuthorizationError` for HTTP `403` or `RateLimitError` for HTTP `429`. A status error for a separate request made by the hook, or another dispatch or hook failure, raises `TransportError`. In those cases the original request may already have reached NOMAD. The SDK reserves `PoolTimeoutError` for connection waits it can classify as unsent.

## BearerTokenCredential class { #bearer-token-credential }

Import from `nomad_python_api.identity`. Holds an existing token for one deployment. Create a new credential when the token expires or rotates.

### Constructor

```python
BearerTokenCredential(token: str, *, endpoint: str = "prod", pat_id: str | None = None)
```

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `token` | `str` | Yes | — | The PAT or Keycloak access token, without the `Bearer` prefix or whitespace. |
| `endpoint` | `str` | No | `"prod"` | Keyword-only. Central or a complete HTTPS NOMAD API v1 base URL. |
| `pat_id` | `str \| None` | No | `None` | Metadata ID for referring to this PAT from a management call. |

The read-only `pat_id` property exposes the optional metadata ID.
`BearerTokenCredential.from_issued(issued)` creates a credential from a
[`PatIssuedResult`](#pat-models) and keeps the issuing deployment and metadata
ID with it. See the [PAT lifecycle example](pats.md#inspect-use-rotate-and-revoke).

### Worked example: look up your account with a PAT

Set `NOMAD_PAT` to a Central PAT with `users:read`.

```python
--8<-- "tests/snippets/identity/test_authentication.py:named_setup"
```

`account.user_id` contains the ID of the token's NOMAD account. The guide also shows how to [use an existing Keycloak access token](sign-in.md#use-an-existing-keycloak-access-token).

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

### Advanced settings { #advanced-browser-settings }

The defaults work for standard sign-in. Set the callback port or path when your Keycloak client registration requires specific values.

| Optional keyword argument | Type | Default | Description |
| --- | --- | --- | --- |
| `refresh_margin` | `float` | `30` | Start renewing up to this many seconds before expiry, capped at half the token's lifetime. Renewal happens on the next request that needs a token. Use `0` to wait until expiry. |
| `redirect_port` | `int` | `0` | Loopback TCP port. `0` asks the operating system for an available port. |
| `redirect_path` | `str` | `"/"` | Absolute callback path registered for the public client. The listener uses `127.0.0.1`. |

If Keycloak registers `http://127.0.0.1:9123/return`, pass `redirect_port=9123` and `redirect_path="/return"` to `BrowserCredential`. The browser returns the authorization code to that local callback. Set `endpoint` to the NOMAD API base URL for the deployment.

Browser credentials renew when a refresh token is available. [Password credentials](#password-credential) use the same margin to time their next password exchange.

### Instance methods

| Method signature | Return type | Description |
| --- | --- | --- |
| `authenticate()` | `None` | Starts a fresh browser sign-in and replaces the cached session on success. Can raise `BrowserAuthenticationError`. |

### Worked example: sign in through Helmholtz ID

Run the example on a computer where Python and the browser share a loopback interface. Complete institutional sign-in in the browser when it opens.

```python
--8<-- "tests/snippets/identity/test_browser_login.py:central_browser_login"
```

After sign-in, `account` contains your Central account. For a custom installation, see the [Oasis browser example](sign-in.md#browser-login). The [REST reference](rest.md#browser-login-rest) lists the messages exchanged during sign-in.

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
| `refresh_margin` | `float` | No | `30` | Advanced setting for when to repeat the password exchange. See [how the renewal margin works](#advanced-browser-settings). |

### Instance methods

| Method signature | Return type | Description |
| --- | --- | --- |
| `authenticate()` | `None` | Repeats the password exchange and caches the access token on success. Can raise `PasswordAuthenticationError`. Create a new credential when the password changes. |

### Worked example: sign in with a username and password

Set `NOMAD_USERNAME` and `NOMAD_PASSWORD` for an account that can use the deployment's password grant. This example uses Central.

```python
--8<-- "tests/snippets/identity/test_password_login.py:central_password_login"
```

The first call signs in and returns the account. See the [Oasis password example](sign-in.md#password-login) for explicit arguments and the [REST reference](rest.md#password-login-rest) for the token exchange.

## IdentityOperations class { #identity-operations }

Access this operation group through the `client.identity` property.

`client.identity.pats` is the [PAT operation group](#pat-operations).

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
| `name` | `str` | Yes | — | Identity method name, such as `"me"` or `"pats.rotate"`. |

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

Optional profile fields are keyword-only and default to `None`. These include
`name`, `first_name`, `last_name`, `email`, `affiliation`,
`affiliation_address`, and `repo_user_id` as strings, `created` as
`datetime`, and `is_admin` and `is_oasis_admin` as booleans.
The [REST field table](rest.md#get-users-me) describes each field.

`account.as_user()` returns a local Pydantic `User` with the same profile
attributes. Use `model_dump(mode="json")` for an explicit JSON-compatible
profile export. Account profiles may contain private information.

`account.get_all_pats(**options)` delegates to [`pats.list()`](#pat-list)
using the originating client. It raises `RuntimeError` for a detached
account or a closed client.

### PatOperations class { #pat-operations }

Access the operation group through `client.identity.pats`. PAT management uses
the authenticated user's management access token from the same deployment.

| Instance method | Required inputs | Return type | REST contract |
| --- | --- | --- | --- |
| `create(options, *, extra_json=None)` | `PatCreateOptions` or a Python mapping with its fields | `PatIssuedResult` | [Create](rest.md#create-pat) |
| `list(*, limit=None, extra_query=None, **filters)` | None | `PatList` | [List](rest.md#list-pats) |
| `get(target)` | A PAT metadata ID string, `PatMetadata`, or `BearerTokenCredential` with a PAT ID | `PatMetadata` | [Get](rest.md#get-pat) |
| `rotate(target)` | Same target forms as `get()` | `PatIssuedResult` | [Rotate](rest.md#rotate-pat) |
| `revoke(target)`, `delete(target)` | Same target forms as `get()` | `None` | [Revoke](rest.md#revoke-pat) |
| `get_operation_info(name)` | Method name as `str` | `OperationInfo` | Local metadata. Unknown names raise `KeyError`. |

`extra_json` is an optional mapping of custom top-level body fields.
`extra_query` is an optional mapping of custom query fields.
The [worked lifecycle](pats.md#manage-pats) covers typed options and reusable dictionaries,
access and rotation, and Oasis extensions.

With a Keycloak access token on the client, bind `pats = client.identity.pats`
and issue a PAT using typed options. The example prints metadata and expiry.

```python
--8<-- "tests/snippets/identity/test_pat_management.py:pat_create_object"
```

#### Listing and filtering { #pat-list }

All options are optional. Leaving a REST option unset uses NOMAD's
defaults. `.filter(**filters)` accepts the filter fields in the first
four rows. It returns a new listing and raises `ValueError` if a field
already has a different value.

| Options | Type | Default and behavior |
| --- | --- | --- |
| `search` | `str` | Case-insensitive search by token name. |
| `state` | `"active"` or `"inactive"` | Filter by whether the PAT is currently active. |
| `revoked` | `bool` | Filter by explicit revocation. |
| `created_after`, `created_before`, `last_used_after`, `last_used_before`, `expires_after`, `expires_before` | `datetime` or ISO 8601 string | Filter the corresponding dates. Include the timezone for reproducible runs. |
| `order_by` | `str` | Server default is `"created_desc"`. Select `created`, `expires`, `last_used`, or `name` with an `_asc` or `_desc` suffix. |
| `order` | `"asc"` or `"desc"` | Server default is `"asc"`. |
| `limit` | Nonnegative `int` | SDK cap on total items yielded. `0` makes no request. |
| `page_size` | Nonnegative `int` | Server default is `10`. `0` allows reading page metadata without items. |
| `page_after_value`, `page`, `page_offset` | Cursor `str`, 1-based `int`, or 0-based `int` | Starting position. Supply at most one. |

Iterate a `PatList` for items. A new iteration starts a new listing.
Call `by_page(continuation_token=None)` for an iterator of `PatPage`.
Supply a saved cursor or a starting position. `PatPage.items` is a tuple
of metadata records, `.query` is a `PatFilters` snapshot, `.pagination`
is a `PatPagination` model, and `.next_cursor` is a string or `None`.
`PatPagination` exposes the server pagination fields listed in the
[REST reference](rest.md#list-pats), including the total match count.

#### PAT models { #pat-models }

| Model | Fields |
| --- | --- |
| `PatCreateOptions` | Required `name: str` and `scopes: tuple[str, ...]`. Scope enum members are accepted as input. Optional `description: str \| None` defaults to `None`. Optional `expires_in_days: int \| None` has a model default of 30, and the API request omits an unset value. |
| `PatMetadata` | Required `id`, `name`, and `scopes` (string tuple), `revoked: bool`, and `created_at: datetime`. Optional `description`, `expired_at`, and `last_used_at` default to `None`. The two optional timestamps are `datetime` when supplied. |
| `PatIssuedResult` | Required `pat: PatMetadata` and `raw_token: SecretStr`. Use `BearerTokenCredential.from_issued()` to use the result for a job. The secret is excluded from default representation and model serialization. Pickling is disabled. |

#### PAT errors { #pat-errors }

| Error | When to expect it | What to check |
| --- | --- | --- |
| `ScopeNotAllowedError` | The caller's local policy blocks the request. | Include the operation's documented scopes in `allowed_scopes`. NOMAD also checks the access token. |
| `ClientAuthenticationError`, `AuthorizationError` | HTTP `401` or `403`, respectively. | Check token validity and deployment for `401`. Use a management access token with the required scopes for `403`. |
| `CredentialEndpointMismatchError` | A credential or returned metadata identifies a different deployment. | Connect to the issuing deployment. |
| `ValueError` | Invalid options, missing PAT metadata ID, conflicting filters, or an extension collision. | Use the fields described above. |
| `PatRequestError`, `PatNotFoundError` | HTTP `400` or `422`, or a target `404`, respectively. | Inspect supported options, target ID, active state, and account. |
| `RateLimitError`, `PoolTimeoutError` | HTTP `429` or a confirmed unsent pool wait timeout. | Let concurrent work settle and review the pool or request rate. |
| `InvalidResponseError` | Read response cannot be interpreted or returns a repeated cursor. | Check deployment compatibility before continuing. |
| `PatWriteOutcomeUnknownError` | A write may have succeeded before the response was lost or could be interpreted. | Inspect the PAT list in NOMAD before attempting another write. |

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
| `Scope.UPLOADS_READ` | `"uploads:read"` | Permission to read Project data under NOMAD's upload API. |
| `Scope.TOKENS_CREATE` | `"tokens:create"` | Management permission for issuing a PAT. |
| `Scope.TOKENS_READ` | `"tokens:read"` | Management permission for listing and inspecting PATs. |
| `Scope.TOKENS_DELETE` | `"tokens:delete"` | Management permission for revoking a PAT. Rotation also requires create. |

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
| `InvalidResponseError` | `NomadError` | The API read response could not be interpreted as the expected model. |
| `PatRequestError` | `HttpResponseError` | NOMAD rejected the PAT request or target state. |
| `PatNotFoundError` | `HttpResponseError` | NOMAD could not find a PAT accessible to the caller. |
| `PatWriteOutcomeUnknownError` | `NomadError` | Verify the result in NOMAD before repeating a PAT write. |

### Worked example: handle scope and authentication errors

Run this inside an open `NomadClient` context. Set `allowed_scopes=set()` when constructing the client to see a local scope error. The example prints the missing scopes without sending an account request.

```python
--8<-- "tests/snippets/identity/test_authentication.py:error_recovery"
```
