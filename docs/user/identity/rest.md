# Authentication REST reference

This reference covers REST endpoints called by the SDK. For token creation, rotation, and other sign-in workflows, see the [NOMAD authentication guide](https://docs.nomad-lab.eu/howto/manage/program/auth.html).

## GET /users/me { #get-users-me }

**SDK instance method** · [`client.identity.me()`](api.md#identity-me)

The contract below was checked against the [NOMAD Central API v1 schema](https://nomad-lab.eu/prod/v1/api/v1/openapi.json) for NOMAD 2.0.1. Check your Oasis's own OpenAPI document for deployment-specific differences.

| Request part | REST contract | SDK mapping |
| --- | --- | --- |
| Base URL | Defaults to `https://nomad-lab.eu/prod/v1/api/v1`. | `NomadClient` uses the credential's endpoint. Set it on the credential for other deployments. |
| Method and path | `GET /users/me` | `client.identity.me()` |
| Authorization header | `Authorization: Bearer <access-token>` | Sent using the configured credential |
| Required scope | `users:read` | `Scope.USERS_READ` |
| Path parameters | None | None |
| Query parameters | None | No `extra_query` |
| Request body | None | No `extra_json` or multipart fields |

### Direct REST example

```python
--8<-- "tests/snippets/identity/test_authentication.py:rest_account"
```

### Response fields

On success, NOMAD returns a JSON `User` object. The upstream schema permits fields to be omitted or set to `null`. The SDK requires a non-empty string `user_id` for the authenticated account and accepts an absent or null `username`.

| REST field | Type when present and non-null | Meaning | SDK mapping |
| --- | --- | --- | --- |
| `name` | String | Display name | REST only |
| `first_name` | String | Given names | REST only |
| `last_name` | String | Surname | REST only |
| `email` | String | Email address | REST only |
| `affiliation` | String | Organization or institute | REST only |
| `affiliation_address` | String | Organization address | REST only |
| `user_id` | String | Persistent NOMAD account identifier | `Account.user_id` |
| `username` | String | Account username | `Account.username` |
| `created` | Date-time string | Account creation time | REST only |
| `repo_user_id` | String | Legacy repository identifier | REST only |
| `is_admin` | Boolean | NOMAD admin flag | REST only |
| `is_oasis_admin` | Boolean | Oasis admin flag, defaults to `false` in the upstream schema | REST only |

| Status | Meaning | SDK handling |
| --- | --- | --- |
| `200` | Account data returned | `Account`, or `InvalidResponseError` if the response cannot be mapped |
| `401` | Authentication rejected | `ClientAuthenticationError` |
| `403` | Authorization rejected, for example when a token lacks the required scope | `AuthorizationError` |
| `429` | Request throttled | `RateLimitError` |

Other unexpected statuses raise `HttpResponseError`. See the [SDK troubleshooting examples](index.md#troubleshoot-a-request) for local errors and recovery.

## Browser login requests { #browser-login-rest }

**SDK class** · [`BrowserCredential`](api.md#browser-credential)

The authorization and token URLs come from an explicit pair of endpoints or from OIDC discovery at the supplied Keycloak issuer. Keycloak may send the browser through an institutional provider before returning it to the SDK callback. [Keycloak OIDC endpoints](https://www.keycloak.org/securing-apps/oidc-layers) · [OIDC discovery](https://openid.net/specs/openid-connect-discovery-1_0.html)

| Step | Request | Fields and result |
| --- | --- | --- |
| Discover endpoints | `GET {issuer}/.well-known/openid-configuration` | Used with `discover=True`. Response must contain the exact `issuer`, `authorization_endpoint`, and `token_endpoint`. If present, `code_challenge_methods_supported` must include `S256`. |
| Authorize | Browser `GET {authorization_endpoint}` | Query includes `client_id`, `response_type=code`, `response_mode=query`, `scope=openid`, `redirect_uri`, a random `state`, `code_challenge`, and `code_challenge_method=S256`. Optional `identity_provider` becomes `kc_idp_hint`. |
| Receive callback | Browser `GET http://127.0.0.1:<port>/<path>` | Query includes `state` and either `code` or `error`. The SDK verifies the state and checks `iss` against the issuer when supplied. |
| Exchange code | `POST {token_endpoint}` | Form includes `grant_type=authorization_code`, `client_id`, `code`, the same `redirect_uri`, and `code_verifier`. |
| Refresh token | `POST {token_endpoint}` | Form includes `grant_type=refresh_token`, `client_id`, and `refresh_token`. A returned refresh token replaces the previous value. |

Both token requests use `application/x-www-form-urlencoded`. The SDK requires `access_token`, `token_type=Bearer`, and a positive integer `expires_in` in successful responses. It keeps an optional `refresh_token` in memory. The access token goes to the selected NOMAD API as a bearer token. The OAuth `openid` scope starts sign-in, while NOMAD applies its own API permissions to the issued access token. [NOMAD authorization model](https://docs.nomad-lab.eu/explanation/auth.html#keycloak-access-tokens)

## POST /auth/token { #password-login-rest }

**SDK class** · [`PasswordCredential`](api.md#password-credential)

This request uses the credential's NOMAD API base URL and sends an `application/x-www-form-urlencoded` body. The NOMAD deployment selects the Keycloak realm and client. [NOMAD production OpenAPI](https://nomad-lab.eu/prod/v1/api/v1/openapi.json) · [Upstream password handler](https://github.com/FAIRmat-NFDI/nomad/blob/0f19b93ffec1950e29b145fb008aad967ca9d530/nomad/app/v1/routers/auth.py#L344-L378)

| Form field | REST contract | SDK mapping |
| --- | --- | --- |
| `grant_type` | Required string, `password` | Supplied by `PasswordCredential` |
| `username` | Required string | `username` or `NOMAD_USERNAME` |
| `password` | Required string | `password` or `NOMAD_PASSWORD` |
| `scope` | Optional string, defaults to empty | The credential omits it. `allowed_scopes` is a separate local policy. |
| `client_id`, `client_secret` | Optional strings in the form schema | The credential omits them. The upstream handler uses the deployment's Keycloak client settings. |

The SDK requires a successful response to contain `access_token`, `token_type=Bearer`, and a positive integer `expires_in`. The response can also contain `id_token`, `refresh_token`, `scope`, and `refresh_expires_in`. The password credential uses the access token for API calls and repeats the password exchange for renewal. A rejected exchange raises `PasswordAuthenticationError` before any API operation is sent.
