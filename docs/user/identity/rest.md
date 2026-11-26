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
| `name` | String | Display name | `Account.name` |
| `first_name` | String | Given names | `Account.first_name` |
| `last_name` | String | Surname | `Account.last_name` |
| `email` | String | Email address | `Account.email` |
| `affiliation` | String | Organization or institute | `Account.affiliation` |
| `affiliation_address` | String | Organization address | `Account.affiliation_address` |
| `user_id` | String | Persistent NOMAD account identifier | `Account.user_id` |
| `username` | String | Account username | `Account.username` |
| `created` | Date-time string | Account creation time | `Account.created` as `datetime` |
| `repo_user_id` | String | Legacy repository identifier | `Account.repo_user_id` |
| `is_admin` | Boolean | NOMAD admin flag | `Account.is_admin` |
| `is_oasis_admin` | Boolean | Oasis admin flag | `Account.is_oasis_admin` |

| Status | Meaning | SDK handling |
| --- | --- | --- |
| `200` | Account data returned | `Account`, or `InvalidResponseError` if the response cannot be mapped |
| `401` | Authentication rejected | `ClientAuthenticationError` |
| `403` | Authorization rejected, for example when a token lacks the required scope | `AuthorizationError` |
| `429` | Request throttled | `RateLimitError` |

Other unexpected statuses raise `HttpResponseError`. See the [SDK troubleshooting examples](sign-in.md#troubleshoot-a-request) for local errors and recovery.

## PAT management { #pat-rest }

All five routes use the current user's management access token as
`Authorization: Bearer <access-token>`. Use the API base URL of the issuing
deployment. The credential used as a target supplies a metadata ID only.
[NOMAD PAT management guide](https://docs.nomad-lab.eu/howto/manage/program/auth.html#use-a-keycloak-access-token-when-required)

### POST /auth/pats { #create-pat }

[`pats.create(options, extra_json=None)`](api.md#pat-operations) requires
`tokens:create` and returns `201` with `pat` metadata and `raw_token`.
It has no path or query fields. The JSON request body accepts the following.

| REST field | Type | Required | SDK input |
| --- | --- | --- | --- |
| `metadata` | Object | Yes | Built from `PatCreateOptions` or the equivalent mapping |
| `metadata.name` | String | Yes | `name` |
| `metadata.scopes` | Array of strings | Yes | `scopes`, including `Scope` enums |
| `metadata.description` | String or null | No | `description` |
| `expires_in_days` | Integer or null | No | `expires_in_days`. Omitted uses NOMAD's documented default of 30. |

```json
{
  "metadata": {
    "name": "Diffraction analysis",
    "scopes": ["users:read", "uploads:read"]
  },
  "expires_in_days": 30
}
```

On a deployment that documents an extra top-level field, pass it
through `extra_json`. See the [worked Oasis example](pats.md#advanced-oasis-extensions).

### GET /auth/pats { #list-pats }

[`pats.list()`](api.md#pat-list) and `account.get_all_pats()` require
`tokens:read`. The route accepts query parameters and has no body.

| Query parameters | SDK mapping |
| --- | --- |
| `search`, `revoked`, `state` | Named filters or `.filter()`. |
| `created_after`, `created_before`, `last_used_after`, `last_used_before`, `expires_after`, `expires_before` | Named date filters or `.filter()`. Written as ISO 8601 date-times. |
| `order_by`, `order`, `page_size` | Named listing options. |
| `page_after_value`, `page`, `page_offset` | Starting position. A continuation token maps to `page_after_value`. |
| Deployment-specific query fields | `extra_query`. Standard names are reserved. |

HTTP `200` returns `data` (the metadata records), `query` (echoed
filters), and `pagination`. `PatPage` exposes the records as `items`.
Pagination includes `total` and optional `page_size`, `order_by`,
`order`, `page_after_value`, `page`, `page_offset`,
`next_page_after_value`, `page_url`, `next_page_url`, `prev_page_url`,
and `first_page_url`. The SDK uses the opaque cursor for follow-up requests
to the configured deployment. NOMAD computes it from an offset in the
current sorted results. See the [checkpoint guide](pats.md#advanced-paging-and-checkpointing)
for the effects of list changes.

### GET /auth/pats/{pat_id} { #get-pat }

`pats.get(target)` requires `tokens:read`. It sends the target's
24-character hexadecimal metadata ID as `pat_id` without query parameters or a body. HTTP `200`
returns `PatMetadata`.

### POST /auth/pats/{pat_id}/rotate { #rotate-pat }

`pats.rotate(target)` requires `tokens:create` and `tokens:delete`.
It sends `pat_id` without query parameters or a body. HTTP `200`
returns the replacement `pat` and one-time `raw_token`, as with creation.

### DELETE /auth/pats/{pat_id} { #revoke-pat }

`pats.revoke(target)` and `pats.delete(target)` require `tokens:delete`.
They send `pat_id` without query parameters or a body. HTTP `204`
has an empty response and the SDK returns `None`.

### PAT response fields and errors

| Response field | Wire type | SDK mapping |
| --- | --- | --- |
| `id`, `name` | Strings | Metadata ID and label |
| `scopes` | Array of strings | Tuple of granted scope names |
| `description` | String or null | Optional description |
| `revoked` | Boolean | Revocation flag |
| `created_at` | Date-time string | Creation timestamp |
| `expired_at`, `last_used_at` | Date-time string or null | Optional timestamps |
| `pat` | Metadata object | `PatIssuedResult.pat` on create and rotate |
| `raw_token` | Secret string | `PatIssuedResult.raw_token` on create and rotate |

Swagger advertises `400` for invalid requests or inactive rotation
targets, `404` for unavailable targets, and `422` for validation
failures. For rotation, HTTP `400` also covers failure after the original
PAT was revoked. The SDK raises `PatWriteOutcomeUnknownError` in that case
and when an issuance response contains an unusable credential.
See [PAT errors](api.md#pat-errors).

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
