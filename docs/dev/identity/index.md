# Identity architecture

`client.identity.me()` calls `GET /users/me` using an existing bearer token and returns an SDK-owned `Account`. This page describes the identity feature and the shared request pipeline it uses. The [system architecture](../architecture/index.md) shows where it fits in a Python or Oasis deployment. The [production OpenAPI schema](https://nomad-lab.eu/prod/v1/api/v1/openapi.json) defines the upstream route and response.

## Classes and their responsibilities

```mermaid
classDiagram
    class NomadClient {
        +identity
        +allowed_scopes
        +close()
    }
    class IdentityOperations {
        +me() Account
        +get_operation_info(name) OperationInfo
    }
    class RequestPipeline {
        +send(operation)
        +close()
    }
    class BearerTokenCredential {
        -deployment URL
        -token
    }
    class Operation {
        +method
        +path
    }
    class OperationInfo {
        +name
        +description
        +required_scopes
    }
    class Account {
        +user_id
        +username
    }
    NomadClient *-- IdentityOperations : owns
    NomadClient *-- RequestPipeline : owns
    IdentityOperations --> RequestPipeline : uses
    IdentityOperations --> Operation : selects
    RequestPipeline --> BearerTokenCredential : asks for bearer token
    Operation *-- OperationInfo : includes
    IdentityOperations ..> Account : returns
```

The `me` operation declaration in `identity/_operations.py` supplies both the required scope used by the pipeline and the metadata returned by `get_operation_info("me")`. `identity/_credential.py` checks the credential's deployment binding. `identity/_account.py` holds the public result model.

## Request sequence

```mermaid
sequenceDiagram
    participant App as Application
    participant Identity as IdentityOperations
    participant Pipeline as RequestPipeline
    participant Credential as BearerTokenCredential
    participant NOMAD as Selected NOMAD deployment

    App->>Identity: me()
    Identity->>Pipeline: send the registered account operation
    Pipeline->>Pipeline: Check local users:read policy
    alt Client scope denies
        Pipeline-->>App: ScopeNotAllowedError
    else Client scope permits
        Pipeline->>Credential: Request token for deployment and scopes
        alt Deployment differs
            Credential-->>App: CredentialEndpointMismatchError
        else Deployment matches
            Credential-->>Pipeline: Existing bearer token
            Pipeline->>NOMAD: GET /users/me via verified TLS
            NOMAD-->>Pipeline: HTTP status and response
            Pipeline-->>Identity: Bounded decoded response or typed error
            Identity-->>App: Account on success
        end
    end
```

Construction and inspection are local. A scope denial or deployment mismatch occurs before the first HTTP request. On this feature, server `401`, `403`, and `429` map to different errors. No automatic retry occurs.

## Activity and lifecycle

```mermaid
flowchart TD
    Start([Call identity.me]) --> Open{Client open?}
    Open -->|No| ClosedError[Raise closed-client error]
    Open -->|Yes| Scope{Allowed by local scope policy?}
    Scope -->|No| ScopeError[Raise local scope error]
    Scope -->|Yes| Bound{Credential matches deployment?}
    Bound -->|No| BindingError[Raise credential mismatch]
    Bound -->|Yes| Send[Send one bearer request]
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

The state diagram describes the client lifecycle. The supplied credential holds one opaque token in memory throughout that lifecycle. The caller can reuse the credential in another client for the same deployment. Sockets belong to each client's pool.

## Timing and resource limits

```mermaid
flowchart LR
    Local["Local checks<br/>0 network requests"] --> Wait["Pool wait<br/>up to 10 s"]
    Wait --> Connect["Connect if needed<br/>up to 5 s"]
    Connect --> Write["Write request<br/>10 s per write wait"]
    Write --> Read["Read account response<br/>10 s per read wait"]
    Read --> Parse["Validate and map<br/>256 KiB body limit"]
```

HTTPX timeouts bound individual phases. Read and write timeouts apply to activity within the corresponding phase. They do not add up to a fixed end-to-end deadline. Pool limits are 10 connections and 5 idle keep-alive connections per client. The account call requests an uncompressed body so the byte limit can be enforced before JSON parsing. [HTTPX timeout model](https://www.python-httpx.org/advanced/timeouts/) · [HTTPX pool limits](https://www.python-httpx.org/advanced/resource-limits/)

## Identity and scope data

This is a conceptual entity-relationship diagram for SDK objects and the deployment that validates them.

```mermaid
erDiagram
    DEPLOYMENT ||--o{ CLIENT : targets
    DEPLOYMENT ||--o{ BEARER_CREDENTIAL : binds
    BEARER_CREDENTIAL ||--o{ CLIENT : supplies
    CLIENT ||--o{ ALLOWED_SCOPE : limits
    OPERATION ||--o{ REQUIRED_SCOPE : declares
    SCOPE ||--o{ ALLOWED_SCOPE : identifies
    SCOPE ||--o{ REQUIRED_SCOPE : identifies
    DEPLOYMENT ||--o{ ACCOUNT : returns
```

The SDK does not create a credential database or infer token grants from the token string. The local allowed scopes and operation requirements are separate from the deployment's authorization data. An account response contains only values returned by the deployment and mapped by the SDK.

## Where to customize and verify

To adapt a fork, start with the identity operation declaration and the account mapper. Keep endpoint validation, bearer attachment, scope checks, and response bounds in the shared pipeline. Place offline tests in `tests/unit/identity/` and runnable examples in `tests/snippets/identity/`. Update the identity walkthrough and REST appendix together so the documented route, fields, and scope match the code. Follow the [Oasis onboarding guide](../oasis/index.md) for the fork and release workflow.
