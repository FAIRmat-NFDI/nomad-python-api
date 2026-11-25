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

**Start with `NomadClient(credential=…)`.** A notebook, script, or HPC worker normally uses one client and reuses its pool for every call. Each client defaults to 10 connections and keeps up to 5 idle for reuse.

For example, a worker with a smaller connection budget can set `pool_limits` and `timeouts` directly on `NomadClient`. This example returns one account with a four-connection pool and a three-second wait for a free slot. The SDK creates and closes the pool for you. Read and write timeouts measure inactivity within their phases. A transfer that keeps making progress can take longer in total. [Client settings and defaults](api.md#connection-limits)

```python
--8<-- "tests/snippets/identity/test_authentication.py:client_network_settings"
```

Use the [advanced connection setups](#share-or-borrow-http-connections) when several clients must share one pool or your application needs a custom network setup.

### Advanced connection setups { #share-or-borrow-http-connections }

!!! info "Advanced · Optional"

    Standard sign-in, local notebooks, and HPC workers that use one client per process can use the [regular settings](#tune-network-settings).

#### Summary and basic examples { #advanced-connection-summary }

Transport injection lets your application supply the connections used by `NomadClient`. A shared `NomadTransport` supplies only the pool. A borrowed `httpx.Client` supplies the HTTP session and its network configuration. In either mode, the SDK uses the credential's deployment and applies the client's scope policy.

| Connection setup | Pass to `NomadClient` | Where settings go | Who closes the pool |
| --- | --- | --- | --- |
| SDK-managed pool | `pool_limits=…, timeouts=…` | Pool limits, CA trust, and API timeouts on `NomadClient` | The SDK client |
| Shared transport | `transport=…` | Pool limits and CA trust on `NomadTransport`. API timeouts on each client | The application |
| Borrowed HTTPX client | `http_client=…` | Pool limits, TLS trust, proxy, and timeouts on `httpx.Client` or its transport | The application |

For either example, set `NOMAD_PAT` to a Central token with `users:read`. Each call returns the authenticated account.

=== "Share a connection pool"

    Two NOMAD clients use a single pool. Each has its own HTTP session and cookie jar. Close the clients before closing the transport.

    ```python
    --8<-- "tests/snippets/identity/test_authentication.py:basic_shared_transport"
    ```

=== "Borrow an HTTPX client"

    The NOMAD client uses the supplied HTTPX session's network settings and hooks. Your application can continue using that session after its NOMAD client closes.

    ```python
    --8<-- "tests/snippets/identity/test_authentication.py:basic_borrowed_http_client"
    ```

#### Use cases { #advanced-connection-use-cases }

=== "HPC coordinator with two credentials"

    Suppose one Linux HPC coordinator runs two parts of a job, each with its own PAT and scope policy. With two independently configured eight-connection clients, the process could open 16 connections. A single `NomadTransport` capped at eight gives both parts one eight-connection budget. Each client keeps its own cookie jar and can have a different timeout. The calls share the connection budget, so one client can occupy all eight slots.

    Set `NOMAD_PAT` and `NOMAD_SECOND_PAT` to tokens with `users:read` from the same deployment. Set `NOMAD_API_URL` for an Oasis. Each call returns the account associated with its PAT. The first client waits up to three seconds for a connection. The second waits up to ten. Keep the outer transport open until both clients finish. For separate worker processes, use [worker-local configuration](#configure-an-hpc-worker) and size the total budget in the scheduler.

    ```python
    --8<-- "tests/snippets/identity/test_authentication.py:share_transport"
    ```

=== "Institutional proxy or application tracing"

    An institute may require the application's approved HTTP proxy to reach its Oasis. Set `NOMAD_API_URL` to that deployment's HTTPS API v1 URL, `NOMAD_PAT` to its PAT with `users:read`, and `NOMAD_HTTPS_PROXY` to the approved proxy URL. Use a trusted HTTPX session with certificate verification enabled. If the institute uses a private CA, configure that trust on the HTTPX client. The example returns the account and records only the response status when application logging is enabled.

    The SDK builds each NOMAD request with its own bearer token, headers, and query parameters. The borrowed client's default headers, cookies, query parameters, and authentication apply to the application's own HTTPX calls. Keep hooks focused on metadata. If a hook reads the body or raises an exception, it can buffer data before SDK validation or interrupt a call whose request already reached NOMAD.

    !!! note "Response cookies"

        NOMAD SDK requests omit cookies from the borrowed client's jar. HTTPX can still store cookies from a NOMAD response and send them on a later direct application call when the cookie rules match. Use a dedicated HTTPX client for NOMAD when you need custom network settings and a separate cookie jar. Use [`NomadTransport`](api.md#nomad-transport) to share connections across NOMAD clients with separate cookie jars. [Response-cookie behavior](api.md#borrowed-httpx-response-cookies)

    ```python
    --8<-- "tests/snippets/identity/test_authentication.py:borrow_http_client"
    ```

### Configure an HPC worker { #configure-an-hpc-worker }

Create the credential and client **inside each Slurm, pyiron, or multiprocessing worker after it starts**. Pass resource IDs and job inputs between processes. Supply the PAT through the site's secret mechanism and use the minimum scopes the job needs. For this account check, use a token with `users:read`. Set `NOMAD_API_URL` to the complete HTTPS API base URL for a self-hosted Oasis. Omit it to use NOMAD Central.

```python
--8<-- "tests/snippets/identity/test_authentication.py:hpc_worker"
```

A successful check returns the worker's account. In a real worker, keep subsequent NOMAD operations inside the same `with` block so they reuse the pool. The pool in this example allows up to two open connections.

| HPC situation | How to use the client |
| --- | --- |
| **Four processes contact NOMAD directly** | Two connections per worker means up to eight across the job. Share a client among threads in each process. Set the number of active workers in the scheduler or workflow. |
| **Compute workers all need the same input** | Let a coordinator fetch the input once and give workers the resulting file reference. This reduces duplicate requests and transfers. |
| **Short status calls run alongside long transfers** | Keep capacity for status calls by limiting simultaneous transfers. If all connections are busy, a call can raise `PoolTimeoutError` before it reaches NOMAD. A worker can defer that call until capacity is available. |
| **NOMAD returns `429`** | Handle `RateLimitError` in the application or workflow. The connection limit controls simultaneous connections. The deployment can impose a separate request-rate limit. |

A shared transport works within one process. A job-wide concurrency budget belongs in the scheduler or coordinator. See the [API reference](api.md#nomad-transport) for ownership and configuration rules.

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

Run browser login where Python and the browser share a loopback interface, including a local Jupyter kernel. By default, the SDK lets the operating system pick a free callback port and handles token renewal as requests need it. Use the [advanced browser settings](api.md#advanced-browser-settings) if your Oasis administrator gives you a fixed callback URL.

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
