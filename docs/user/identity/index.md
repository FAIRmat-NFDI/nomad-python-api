# Authentication

Use a personal access token (PAT) for scripts, notebooks, and scheduled jobs. Sign in to the NOMAD deployment you want to use, open **User Settings → Tokens**, and create a PAT with `users:read` for the account check. Set `NOMAD_PAT` in your environment or have your secret manager supply it to the process. Use the token exactly as NOMAD issued it. [Create a PAT in NOMAD](https://docs.nomad-lab.eu/howto/manage/program/auth.html#create-a-pat)

## Check your account { #check-your-account }

**REST endpoint used** · [`GET /users/me`](rest.md#get-users-me)

`client.identity.me()` returns an `Account` with a user ID and an optional username. Creating the client and inspecting its scope policy require no network access. The account lookup makes one request.

=== "Named arguments"

    Pass the credential object and scope limit as named Python arguments.

    ```python
    --8<-- "tests/snippets/identity/test_authentication.py:named_setup"
    ```

=== "Python options object"

    Build an options dictionary and unpack it with `**options`. Its keys must match the constructor's named arguments. An unknown key raises `TypeError`.

    ```python
    --8<-- "tests/snippets/identity/test_authentication.py:dictionary_setup"
    ```

=== "JSON settings file"

    Save these settings as `nomad-settings.json` in your working directory. Keep credentials in the environment or secret manager.

    ```json
    --8<-- "tests/snippets/identity/fixtures/nomad-settings.json"
    ```

    Load the JSON with the Python standard library. Omitting `allowed_scopes` leaves the client without a local restriction. An empty array blocks scoped operations. An unknown scope name raises `ValueError`.

    ```python
    --8<-- "tests/snippets/identity/test_authentication.py:json_setup"
    ```

## Use an existing Keycloak access token

If another application handles sign-in, supply its Keycloak **access token** the same way. Set `NOMAD_KEYCLOAK_ACCESS_TOKEN` in the process environment for this example. Replace the credential with a fresh access token when the old one expires.

```python
--8<-- "tests/snippets/identity/test_authentication.py:keycloak_setup"
```

## Connect to an Oasis

The SDK primarily targets NOMAD Central. The same client works with Oasis deployments that expose the compatible REST operation and accept bearer credentials. If your institute adds optional parameters to a wrapped route, use the operation's documented REST extension mapping when available. For routes or behavior that differ from the SDK contract, ask your Oasis maintainers whether they supply a fork or adapter.

Use your Oasis's complete HTTPS API base URL and a token issued for that deployment. For this example, set `OASIS_PAT` to the token. If your Oasis uses a private certificate authority, set `NOMAD_CA_BUNDLE` to the path of its trusted PEM bundle. The example passes that path to the constructor's `ca_bundle` keyword and shows how to explicitly close a long-lived client.

```python
--8<-- "tests/snippets/identity/test_authentication.py:oasis_setup"
```

In Jupyter, install the SDK in the active kernel's environment and run the same example in a cell. Avoid saving secrets or account details in cell output. In pyiron, install the SDK in the worker's environment and create the client inside the worker using a job-provided secret. Pass ordinary data between processes. Live clients and credentials are not serializable with Python's pickle.

## Choose and inspect scopes

| Inspect | What you learn |
| --- | --- |
| `list(Scope)` | Scope constants the installed SDK knows about. See the [NOMAD scope catalog](https://docs.nomad-lab.eu/explanation/auth.html#authorization-via-scopes) for the full server list. |
| `client.allowed_scopes` | The client's immutable local limit. It can block calls that the token would otherwise authorize. |
| `client.identity.get_operation_info("me")` | The operation's description and required scopes. This call reads local metadata. |

NOMAD enforces the token's actual permissions and resource access. Adding a member to the client's allowlist does not grant that permission to the token.

## Troubleshoot a request

Run this example inside your open client context.

```python
--8<-- "tests/snippets/identity/test_authentication.py:error_recovery"
```

| Error | What to check |
| --- | --- |
| `ScopeNotAllowedError` | The client's local policy blocked the call before HTTP. Use a client configured for the required scope. |
| `CredentialEndpointMismatchError` | The SDK blocked the call before HTTP because the credential and client target different deployments. |
| `ClientAuthenticationError` (401) | Check whether the token is complete, expired, revoked, or issued by a different deployment. |
| `AuthorizationError` (403) | Check the token's scopes and the account's access to the resource. |
| `RateLimitError` (429) | Wait before issuing another request. |
| `TransportError` | Check the network, endpoint, and certificate trust. |
| `InvalidResponseError` or other `HttpResponseError` | Check that the endpoint is a supported NOMAD API base URL. Inspect the deployment's behavior if the server returns an unexpected response. |
