# Authentication REST reference

This reference covers REST endpoints called by the SDK. For token creation, rotation, and other sign-in workflows, see the [NOMAD authentication guide](https://docs.nomad-lab.eu/howto/manage/program/auth.html).

## GET /users/me { #get-users-me }

**SDK method** · [`client.identity.me()`](index.md#check-your-account)

The contract below was checked against the [NOMAD Central API v1 schema](https://nomad-lab.eu/prod/v1/api/v1/openapi.json) for NOMAD 2.0.1. Check your Oasis's own OpenAPI document for deployment-specific differences.

| Request part | REST contract | SDK mapping |
| --- | --- | --- |
| Base URL | Complete deployment API base URL, such as `https://nomad-lab.eu/prod/v1/api/v1`. | `NomadClient(endpoint=...)` |
| Method and path | `GET /users/me` | `client.identity.me()` |
| Authorization header | `Authorization: Bearer <access-token>` | Sent from `BearerTokenCredential` |
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
