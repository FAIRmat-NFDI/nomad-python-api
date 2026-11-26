# System architecture

`nomad-python-api` is a Python client for NOMAD Central's REST API. It can connect to a compatible Oasis using an explicit API base URL. A client instance selects one deployment and uses a credential bound to that deployment. Application code can use the same public API in a script, a Jupyter kernel, or a pyiron worker.

## Components and deployment

```mermaid
flowchart LR
    subgraph Process["Application process"]
        Caller["Python, Jupyter, or pyiron worker"] --> Client["NomadClient"]
        Secret["Job or environment secret"] --> Credential["Deployment-bound bearer credential"]
        Credential --> Client
        Settings["Connection limits and phase timeouts"] --> Client
        Client --> Group["Identity operation group"]
        Group --> Pipeline["Shared request pipeline"]
        Pipeline --> Pool["Client-owned HTTPS pool"]
    end

    Pool -->|"One configured API base URL"| Endpoint{"Selected deployment"}
    Endpoint --> Central["NOMAD Central REST API"]
    Endpoint --> Oasis["Compatible NOMAD Oasis REST API"]
```

The client application and the chosen deployment are separate trust boundaries. Only the transport holds HTTPX request and response objects. Public operation results and exceptions use SDK-owned types.

## Package organization

| Location | Responsibility |
| --- | --- |
| `nomad_python_api/_client.py` | Public constructor, feature group properties, and connection-pool lifecycle. |
| `nomad_python_api/_network.py` | SDK-owned immutable connection limits and network timeout settings. |
| `nomad_python_api/identity/` | Bearer credential, identity operations, account model, and public identity exports. |
| `nomad_python_api/_core/` | Deployment URL validation, shared operation records, local scope policy, and HTTP response handling. |
| `nomad_python_api/_scopes.py` and `exceptions.py` | Shared scope names and the exception types callers use across features. |
| `tests/unit/identity/` and `tests/snippets/identity/` | Offline behavior tests and the runnable examples used in the user docs. |

The public client wires feature groups to the shared pipeline. A feature declares its operation and maps a bounded response into an SDK type. The pipeline applies transport and security policy without depending on the feature's response model. An Oasis fork should change a feature's route, request fields, or mapper at that feature boundary when the difference is specific to its deployment.

## Design boundaries

| Area | Rule |
| --- | --- |
| **Local authorization** | The allowed scope set is a client-side limit checked before credentials and HTTP. The deployment authorizes actual token privileges and resource access. |
| **Network** | Bind credentials to the complete API base URL, including the deployment path. Use HTTPS and verified certificates, support explicit private CA trust, and decline redirects. |
| **Performance** | Client construction and local inspection send zero requests. Reuse one bounded HTTP pool per client, and close it when done. The current account call attempts one request. |
| **Process isolation** | Construct clients within the script, kernel, or worker that uses them. Keep bearer tokens out of serialized job inputs, saved notebook output, and source files. |
| **Extension fields** | Add explicit per-operation mappings for a supported query, JSON, or multipart location. Keep destination, authentication, and required scopes under SDK control. |

See [Identity architecture](../identity/index.md) for class relationships, call flow, state, and data. See [Develop for NOMAD Oasis](../oasis/index.md) to onboard a fork.

## Network and transfer design

The default client owns its pool. A caller can also share a `NomadTransport` between independent NOMAD sessions or inject a trusted synchronous HTTPX client. Both modes borrow caller-owned resources. The pipeline still checks the credential's complete deployment URL and local scopes before attaching a bearer token. Close borrowing clients before closing their shared transport or HTTPX client. [Transport examples](../../user/identity/connections.md#share-or-borrow-http-connections)

```mermaid
flowchart LR
    subgraph Process["One worker process"]
        ClientA["Client A with credential A"] --> SessionA["HTTP session A"]
        ClientB["Client B with credential B"] --> SessionB["HTTP session B"]
        SessionA --> Pool["Caller-owned NomadTransport pool"]
        SessionB --> Pool
    end
    Pool --> Deployment["NOMAD deployment"]
```

Sharing `NomadTransport` keeps connection reuse below the HTTP session boundary. Each client builds its own request and retains its own cookies and per-phase timeouts. With a borrowed HTTPX client, the SDK builds the operation URL and bearer header directly. Client-wide headers, request cookies, query parameters, and authentication stay with the application's own requests. The SDK borrows the network configuration and hooks and disables redirects for its calls. Inject an application client you trust because its hooks can alter authenticated requests.

HTTPX can store cookies from a NOMAD response in the borrowed client's jar. On subsequent direct application requests, HTTPX can send those cookies when its cookie rules match. A dedicated HTTPX client isolates that jar from other application requests. `NomadTransport` shares connections across NOMAD sessions while each session owns its own jar. [Response-cookie behavior](../../user/identity/api.md#borrowed-httpx-response-cookies)

For HPC, size the process-local pool and the number of active workers together. Eight workers with four connections each can open up to 32 connections. Monitor pool timeouts, throttling responses, bytes per second, and status-call latency before increasing parallelism. One coordinator can enforce a shared connection budget and fetch common inputs once for compute workers. A connection budget controls concurrent work. Rate controls can be enforced separately by the deployment or workflow. [Worker setup and scenarios](../../user/identity/connections.md#configure-an-hpc-worker)

The client passes [connection limits and phase timeouts](../../user/identity/api.md#connection-limits) into the shared request pipeline. A pool timeout from an SDK-managed session occurs before sending the data request. When a borrowed HTTPX client's hook raises an HTTP status error for the original NOMAD response, the normal SDK status mapping applies. Other borrowed-client failures surface as `TransportError` because the server may already have received the request. Keep these outcomes distinct so a caller can make the right recovery decision.

Future uploads, downloads, and archive transfers share the pipeline's authentication and scope checks. Bulk data needs explicit streaming with bounded buffers and an overall deadline in addition to network inactivity timeouts. Reserve capacity for short status and metadata requests when transfers run concurrently. Use deployment-specific size limits for project planning and verify source identity before implementing download resume. Handle uncertain upload outcomes before offering replay.
