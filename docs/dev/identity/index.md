# Identity architecture

`client.identity.me()` calls `GET /users/me` using a bearer token and returns an SDK-owned `Account`. The credential selects the deployment and can supply an existing token or obtain one through browser or password sign-in. The [system architecture](../architecture/index.md) shows how this fits into NOMAD Central and self-hosted NOMAD Oasis. The [production OpenAPI schema](https://nomad-lab.eu/prod/v1/api/v1/openapi.json) defines the account route and response.

## Classes and their responsibilities

```mermaid
classDiagram
    class NomadClient {
        +identity
        +ownership_transfers
        +enforced_scopes
        +close()
    }
    class IdentityOperations {
        +me() Account
        +pats PatOperations
        +users UserOperations
        +groups GroupOperations
        +get_operation_info(name) OperationInfo
    }
    class RequestPipeline {
        +send(operation)
        +close()
    }
    class BearerTokenCredential {
        -deployment URL
        -token
        +pat_id
        +granted_scopes
        +from_issued()
    }
    class BrowserCredential {
        -deployment URL
        -issuer and client ID
        -in-memory session
        +requested_scopes
        +granted_scopes = None
        +authenticate()
    }
    class PasswordCredential {
        -deployment URL
        -username and password
        -in-memory session
        +requested_scopes
        +granted_scopes = None
        +authenticate()
    }
    class TokenSession {
        -cached token and expiry
        -acquisition lock
    }
    class Operation {
        +method
        +path
        +success_status
    }
    class OperationInfo {
        +name
        +description
        +required_scopes
    }
    class Account {
        +user_id
        +username
        +as_user() User
        +get_all_pats() PatList
    }
    class PatOperations {
        +create(options) PatIssuedResult
        +list() PatList
        +get(target) PatMetadata
        +rotate(target) PatIssuedResult
        +revoke(target)
    }
    class PatIssuedResult {
        +pat PatMetadata
        -one-time secret
    }
    class OwnershipTransferOperations {
        +create(resource, target) OwnershipTransfer
        +get(target, filters) OwnershipTransfer or list
        +accept(target) ActionResult
        +refuse(target) ActionResult
        +cancel(target) ActionResult
    }
    class OwnershipTransfer {
        +transfer_id
        +resource_type
        +resource_id
        +accept()
        +refuse()
        +cancel()
    }
    NomadClient *-- IdentityOperations : owns
    NomadClient *-- RequestPipeline : owns
    NomadClient *-- OwnershipTransferOperations : owns
    IdentityOperations --> RequestPipeline : uses
    IdentityOperations --> Operation : selects
    IdentityOperations *-- PatOperations : owns
    IdentityOperations *-- UserOperations : owns
    IdentityOperations *-- GroupOperations : owns
    GroupOperations --> UserOperations : resolves exact selectors
    PatOperations --> RequestPipeline : uses
    PatOperations ..> PatIssuedResult : issues
    Account ..> PatOperations : delegates listing
    OwnershipTransferOperations --> RequestPipeline : uses
    OwnershipTransferOperations ..> OwnershipTransfer : binds
    GroupOperations ..> OwnershipTransferOperations : binds returned groups
    OwnershipTransfer ..> OwnershipTransferOperations : delegates actions
    RequestPipeline --> BearerTokenCredential : asks for bearer token
    RequestPipeline --> BrowserCredential : asks for bearer token
    RequestPipeline --> PasswordCredential : asks for bearer token
    BrowserCredential *-- TokenSession : owns
    PasswordCredential *-- TokenSession : owns
    Operation *-- OperationInfo : includes
    IdentityOperations ..> Account : returns
```

The `me` operation declaration in `identity/_operations.py` supplies both the required scope used by the pipeline and the metadata returned by `get_operation_info("me")`. The client initializes the pipeline with the credential's normalized API URL. Each credential still checks deployment binding before supplying a token. `identity/_account.py` holds the public result model.

Scopes appear in three separate roles. `NomadClient(enforced_scopes=...)` is the
client's local policy. `requested_scopes` on the browser and password credentials
is sent at sign-in and never consulted locally. OIDC providers process browser
scope names as client scopes; stock NOMAD 2.x accepts but ignores the password
form field. Neither mechanism narrows standard NOMAD API permissions.
`granted_scopes` is known only for a `BearerTokenCredential` built with
`from_issued()`; the sign-in credentials report `None`. The pipeline checks the
enforced policy and then any known grants before asking the credential for a
token, so both refusals happen without network access. NOMAD remains
authoritative. [Access and scopes](../../user/identity/access.md)

PAT management is registered in `identity/_pats.py`. The pipeline applies
scope policy before token acquisition and keeps the method, encoded path,
query, and JSON body separate. Each declaration supplies an accepted
status. The shared pipeline handles bounded JSON and empty `204` replies.
The PAT layer handles request, target, and uncertain-write errors.

### PAT rotation sequence

```mermaid
sequenceDiagram
    participant Researcher
    participant Client as NomadClient
    participant NOMAD
    participant Job as NomadClient in the job
    Researcher->>Client: rotate(job_credential)
    Note over Client: Resolve PAT ID from the object locally
    Client->>NOMAD: POST rotate with Keycloak access token
    NOMAD->>NOMAD: Revoke old PAT and issue replacement
    NOMAD-->>Client: Replacement metadata and one-time secret
    Client-->>Researcher: PatIssuedResult
    Researcher->>Job: Use a new BearerTokenCredential
```

The PAT management call sends the client's access token and the target's
metadata ID. Only the job credential carries the target secret. Write calls
have a single attempt. Rotation can revoke the original and then return
HTTP `400` if replacement creation fails. The SDK treats that response
and unusable issuance results as uncertain outcomes. The caller checks
server state before another attempt.

`Account` holds a weak reference to the originating PAT operations for
`get_all_pats()`. Serialization omits that connection. PAT listing is lazy.
It reapplies the same validated filters and uses only opaque continuation
cursors against the configured deployment. It never follows server-provided
pagination URLs. The [REST reference](../../user/identity/rest.md#pat-rest)
describes the request fields and extension points.

### Group membership writes

```mermaid
sequenceDiagram
    participant Caller
    participant Groups as GroupOperations
    participant Users as UserOperations
    participant NOMAD
    Caller->>Groups: create or replace_members
    Groups->>Groups: Check local group scope and validate references
    opt Create with role-bearing members
        Groups->>Users: Read the signed-in account
        Users->>NOMAD: GET /users/me
        NOMAD-->>Users: Signed-in user profile
        Users-->>Groups: Owner ID
    end
    opt Inputs contain exact selectors
        Groups->>Users: Resolve distinct selectors
        Users->>NOMAD: GET user lookup
        NOMAD-->>Users: User profiles
        Users-->>Groups: Ordered users
    end
    Groups->>Groups: Validate unique IDs and owner
    Groups->>NOMAD: POST group or group edit
    NOMAD-->>Groups: Group response
    Groups-->>Caller: Group model
```

Loaded users and accounts supply their IDs locally. SDK-issued objects are
bound to their deployment. Group and PAT listings share cursor traversal
and keep their own filter and response models. The transport bounds responses
and leaves membership authorization to the server. Replacement sends a full
list. An uncertain write needs reconciliation on the server before any retry.

### Ownership-transfer lifecycle

```mermaid
sequenceDiagram
    participant Source
    participant SourceClient as Source NomadClient
    participant NOMAD
    participant TargetClient as Target NomadClient
    Source->>SourceClient: group.ownership_transfers.create(target)
    SourceClient->>SourceClient: Normalize SDK object or REST mapping
    SourceClient->>NOMAD: POST /ownership-transfers
    NOMAD-->>SourceClient: Pending OwnershipTransfer
    SourceClient-->>Source: Client-bound transfer object
    TargetClient->>NOMAD: GET transfer or incoming listing
    NOMAD-->>TargetClient: OwnershipTransfer
    TargetClient->>NOMAD: POST transfer/respond {action: accept}
    NOMAD-->>TargetClient: Action result and optional resource data
```

Ownership transfer is top-level because it spans group and project resources.
`GroupOperations` binds each returned group to the same transfer operation
group, enabling resource chaining without giving models their own network
session. Inputs normalize to explicit `(resource_type, resource_id)` and target
selector pairs. Unknown future resource types remain possible through an
explicit string and protocol-style resource properties.

A bare transfer ID requires read-only discovery across the built-in `upload`
and `group` types. An explicit type makes one request. Blank `get()` performs
both built-in listings and sorts the combined models locally. Bulk actions are
sequential, reject duplicates before sending, and collect per-item failures.
No action is retried: transport failures, server failures, and invalid success
payloads are uncertain writes that callers must reconcile.

## Request sequence

```mermaid
sequenceDiagram
    participant App as Application
    participant Identity as IdentityOperations
    participant Pipeline as RequestPipeline
    participant Credential as Selected credential
    participant NOMAD as Selected NOMAD deployment

    App->>Identity: me()
    Identity->>Pipeline: send the registered account operation
    Pipeline->>Pipeline: Check users:read against enforced_scopes
    alt Client policy denies
        Pipeline-->>App: ScopeNotAllowedError
    else Known grants lack users:read
        Pipeline-->>App: ScopeNotGrantedError
    else Policy and known grants permit, or grants unknown
        Pipeline->>Credential: Request token for deployment and scopes
        alt Deployment differs
            Credential-->>App: CredentialEndpointMismatchError
        else Deployment matches
            Credential-->>Pipeline: Bearer token or typed sign-in error
            Pipeline->>NOMAD: GET /users/me via verified TLS
            NOMAD-->>Pipeline: HTTP status and response
            Pipeline-->>Identity: Bounded decoded response or typed error
            Identity-->>App: Account on success
        end
    end
```

Construction and inspection are local. A policy denial, a known-grant denial, or a deployment mismatch occurs before the first HTTP request. On this feature, server `401`, `403`, and `429` map to different errors. No automatic retry occurs.

## Browser sign-in and refresh

```mermaid
sequenceDiagram
    participant Pipeline as RequestPipeline
    participant Credential as BrowserCredential
    participant Browser as System browser
    participant Keycloak as Configured Keycloak realm
    participant Listener as Loopback listener

    Pipeline->>Credential: Get bearer token after local checks
    alt First sign-in
        opt Discovery selected
            Credential->>Keycloak: GET OpenID configuration
            Keycloak-->>Credential: Issuer and identity endpoints
        end
        Credential->>Listener: Bind IPv4 loopback and open callback window
        Credential->>Browser: Open authorization URL with PKCE, state, and scope openid plus requested_scopes
        Browser->>Keycloak: Sign in, optionally through a configured provider
        Browser->>Listener: Return authorization code and state
        Listener-->>Credential: Validated code and redirect URI
        Credential->>Keycloak: Exchange code with PKCE verifier
        Keycloak-->>Credential: Access token and optional refresh token
    else Near expiry with refresh token
        Credential->>Keycloak: Exchange refresh token
        Keycloak-->>Credential: New access token and optional rotated refresh token
    else Valid cached token
        Credential->>Credential: Reuse access token
    end
    Credential-->>Pipeline: Bearer token
```

One lock per credential serializes discovery, sign-in, and refresh. The callback accepts only the configured path and loopback host header, validates state, checks `iss` when present, and closes at the end of each sign-in attempt. Discovery and token requests use a short-lived HTTP client with verified TLS and redirects disabled. The SDK bounds their JSON responses to 64 KiB. [Browser-login REST fields](../../user/identity/rest.md#browser-login-rest)

## Password sign-in and renewal

```mermaid
sequenceDiagram
    participant Pipeline as RequestPipeline
    participant Credential as PasswordCredential
    participant Session as Shared token session
    participant NOMAD as Bound NOMAD deployment

    Pipeline->>Credential: Get bearer token after local scope check
    Credential->>Session: Read or renew token under lock
    alt Token absent or near expiry
        Session->>Credential: Obtain an access token
        Credential->>NOMAD: POST /auth/token with password form and optional scope
        NOMAD-->>Credential: Token response or rejection
        Credential-->>Session: Validated token or typed error
    else Valid cached token
        Session->>Session: Reuse access token
    end
    Session-->>Pipeline: Bearer token or typed error
```

`identity/_token.py` shares token response validation, bounded HTTP exchanges, and concurrent caching between the two sign-in credentials. Password renewal repeats the exchange against the same NOMAD endpoint. A rejected login clears the cached token and blocks automatic exchanges until explicit authentication. [Password-login REST fields](../../user/identity/rest.md#password-login-rest)

## Activity and lifecycle

```mermaid
flowchart TD
    Start([Call identity.me]) --> Open{Client open?}
    Open -->|No| ClosedError[Raise closed-client error]
    Open -->|Yes| Scope{Inside enforced_scopes?}
    Scope -->|No| ScopeError[Raise ScopeNotAllowedError]
    Scope -->|Yes or unset| Granted{Inside known granted_scopes?}
    Granted -->|No| GrantError[Raise ScopeNotGrantedError]
    Granted -->|Yes or unknown| Bound{Credential matches deployment?}
    Bound -->|No| BindingError[Raise credential mismatch]
    Bound -->|Yes| Token[Obtain or reuse a bearer token]
    Token --> Send[Send one bearer request]
    Send --> Valid{Successful and valid account response?}
    Valid -->|No| ResponseError[Raise typed transport or response error]
    Valid -->|Yes| Result[Return Account]
```

```mermaid
stateDiagram-v2
    [*] --> Ready : Construct client and pool
    Ready --> Ready : Inspect operation locally
    Ready --> Ready : Complete or reject account call
    Ready --> Closed : close or context exit
    Closed --> [*]
```

The state diagram describes the API client lifecycle. The browser and password credentials keep their sessions in memory, and the bearer credential holds its supplied token. Each can be reused in another client on its bound deployment. The default client owns its API pool. A client using an injected transport or HTTPX client leaves the borrowed pool open.

## Timing and resource limits

```mermaid
flowchart LR
    Local["Local checks<br/>0 network requests"] --> Wait["Pool wait<br/>up to 10 s"]
    Wait --> Connect["Connect if needed<br/>up to 5 s"]
    Connect --> Write["Write request<br/>10 s per write wait"]
    Write --> Read["Read account response<br/>10 s per read wait"]
    Read --> Parse["Validate and map<br/>256 KiB body limit"]
```

The API client defaults to 10 connections, 5 idle keep-alive connections, and 5 seconds of idle reuse. The connect timeout defaults to 5 seconds. Pool, read, and write timeouts each default to 10 seconds. Callers can configure each setting. Read and write timeouts measure inactivity within their respective phases, and the connect timeout governs opening a connection. A `PoolTimeoutError` means the data request timed out before sending. The account call requests an uncompressed body so the byte limit can be enforced before JSON parsing. [SDK connection settings](../../user/identity/api.md#connection-limits) · [HTTPX timeout model](https://www.python-httpx.org/advanced/timeouts/)

## Identity and scope data

This is a conceptual entity-relationship diagram for SDK objects and the deployment that validates them.

```mermaid
erDiagram
    DEPLOYMENT ||--o{ CLIENT : targets
    DEPLOYMENT ||--o{ BEARER_CREDENTIAL : binds
    BEARER_CREDENTIAL ||--o{ CLIENT : supplies
    CLIENT ||--o{ ENFORCED_SCOPE : limits
    BEARER_CREDENTIAL ||--o{ GRANTED_SCOPE : "knows (from_issued)"
    SIGN_IN_CREDENTIAL ||--o{ REQUESTED_SCOPE : "sends at sign-in"
    OPERATION ||--o{ REQUIRED_SCOPE : declares
    SCOPE ||--o{ ENFORCED_SCOPE : identifies
    SCOPE ||--o{ REQUIRED_SCOPE : identifies
    DEPLOYMENT ||--o{ ACCOUNT : returns
```

The SDK does not create a credential database or infer token grants from the token string. Granted scopes come only from the PAT issuance response. The enforced scopes and operation requirements are separate from the deployment's authorization data. An account response contains only values returned by the deployment and mapped by the SDK.

## Where to customize and verify

To adapt a fork, start with the identity operation declaration and the account mapper. Keep endpoint validation, bearer attachment, scope checks, and response bounds in the shared pipeline. Place offline tests in `tests/unit/identity/` and runnable examples in `tests/snippets/identity/`. Update the identity walkthrough and REST appendix together so the documented route, fields, and scope match the code. Follow the [Oasis onboarding guide](../oasis/index.md) for the fork and release workflow.
