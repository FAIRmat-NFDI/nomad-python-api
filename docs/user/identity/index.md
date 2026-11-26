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

<span id="check-your-account"></span><span id="browser-login"></span><span id="password-login"></span><span id="use-an-existing-keycloak-access-token"></span><span id="connect-to-an-oasis"></span><span id="choose-and-inspect-scopes"></span><span id="troubleshoot-a-request"></span>

- [Sign in](sign-in.md) with a PAT, a browser, a username and password, or an existing Keycloak access token.

<span id="manage-pats"></span><span id="inspect-use-rotate-and-revoke"></span><span id="advanced-oasis-extensions"></span>

- [Manage PATs](pats.md) to create, filter, rotate, and revoke tokens.

<span id="tune-network-settings"></span><span id="share-or-borrow-http-connections"></span><span id="configure-an-hpc-worker"></span><span id="advanced-connection-summary"></span><span id="advanced-connection-use-cases"></span>

- [Connections and HPC](connections.md) covers worker setup, connection pools, and custom network settings.

## API reference

- [Python API](api.md) covers classes, constructor parameters, instance methods, properties, model fields, and enum members.
- [REST API](rest.md) covers HTTP endpoints, request fields, and responses.
