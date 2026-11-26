# Connections and HPC

| Example action | Required scope |
| --- | --- |
| Configure a client, connection pool, or transport | None |
| Check account access with `identity.me()` | `users:read` |

## Tune network settings { #tune-network-settings }

**Start with `NomadClient(credential=…)`.** A notebook, script, or HPC worker normally uses one client and reuses its pool for every call. Each client defaults to 10 connections and keeps up to 5 idle for reuse.

For example, a worker with a smaller connection budget can set `pool_limits` and `timeouts` directly on `NomadClient`. This example returns one account with a four-connection pool and a three-second wait for a free slot. The SDK creates and closes the pool for you. Read and write timeouts measure inactivity within their phases. A transfer that keeps making progress can take longer in total. [Client settings and defaults](api.md#connection-limits)

```python
--8<-- "tests/snippets/identity/test_authentication.py:client_network_settings"
```

Use the [advanced connection setups](#share-or-borrow-http-connections) when several clients must share one pool or your application needs a custom network setup.

## Advanced connection setups { #share-or-borrow-http-connections }

!!! info "Advanced · Optional"

    Standard sign-in, local notebooks, and HPC workers that use one client per process can use the [regular settings](#tune-network-settings).

### Summary and basic examples { #advanced-connection-summary }

Transport injection lets your application supply the connections used by `NomadClient`. A shared `NomadTransport` supplies only the pool. A borrowed `httpx.Client` supplies the HTTP session and its network configuration. In either mode, the SDK uses the credential's deployment and applies the client's scope policy.

| Connection setup | Pass to `NomadClient` | Where settings go | Who closes the pool |
| --- | --- | --- | --- |
| SDK-managed pool | `pool_limits=…, timeouts=…` | Pool limits, CA trust, and API timeouts on `NomadClient` | The SDK client |
| Shared transport | `transport=…` | Pool limits and CA trust on `NomadTransport`. API timeouts on each client | The application |
| Borrowed HTTPX client | `http_client=…` | Pool limits, TLS trust, proxy, and timeouts on `httpx.Client` or its transport | The application |

For either example, set `NOMAD_PAT` to a Central token. Each call returns the authenticated account.

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

### Use cases { #advanced-connection-use-cases }

=== "HPC coordinator with two credentials"

    Suppose one Linux HPC coordinator runs two parts of a job, each with its own PAT and scope policy. With two independently configured eight-connection clients, the process could open 16 connections. A single `NomadTransport` capped at eight gives both parts one eight-connection budget. Each client keeps its own cookie jar and can have a different timeout. The calls share the connection budget, so one client can occupy all eight slots.

    Set `NOMAD_PAT` and `NOMAD_SECOND_PAT` to tokens from the same deployment. Replace `endpoint` with the API URL for an Oasis. Each call returns the account associated with its PAT. The first client waits up to three seconds for a connection. The second waits up to ten. Keep the outer transport open until both clients finish. For separate worker processes, use [worker-local configuration](#configure-an-hpc-worker) and size the total budget in the scheduler.

    ```python
    --8<-- "tests/snippets/identity/test_authentication.py:share_transport"
    ```

=== "Institutional proxy or application tracing"

    An institute may require the application's approved HTTP proxy to reach its Oasis. Set `NOMAD_PAT` to that deployment's token. Replace `endpoint` and `proxy_url` with the API URL and approved proxy URL. Use a trusted HTTPX session with certificate verification enabled. If the institute uses a private CA, configure that trust on the HTTPX client. The example returns the account and records only the response status when application logging is enabled.

    The SDK builds each NOMAD request with its own bearer token, headers, and query parameters. The borrowed client's default headers, cookies, query parameters, and authentication apply to the application's own HTTPX calls. Keep hooks focused on metadata. If a hook reads the body or raises an exception, it can buffer data before SDK validation or interrupt a call whose request already reached NOMAD.

    !!! note "Response cookies"

        NOMAD SDK requests omit cookies from the borrowed client's jar. HTTPX can still store cookies from a NOMAD response and send them on a later direct application call when the cookie rules match. Use a dedicated HTTPX client for NOMAD when you need custom network settings and a separate cookie jar. Use [`NomadTransport`](api.md#nomad-transport) to share connections across NOMAD clients with separate cookie jars. [Response-cookie behavior](api.md#borrowed-httpx-response-cookies)

    ```python
    --8<-- "tests/snippets/identity/test_authentication.py:borrow_http_client"
    ```

## Configure an HPC worker { #configure-an-hpc-worker }

Create the credential and client **inside each Slurm, pyiron, or multiprocessing worker after it starts**. Pass resource IDs and job inputs between processes. Supply the PAT through the site's secret mechanism and use the minimum scopes the job needs. The example uses `endpoint = "prod"` for NOMAD Central. Replace it with the full HTTPS API v1 URL for an Oasis.

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
