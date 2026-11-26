# Set up a client

## Summary

Create a [credential](sign-in.md), then pass it to `NomadClient`. The
credential selects the NOMAD API endpoint. Leave the endpoint at its default
for NOMAD Central, or set the complete HTTPS API v1 URL for your Oasis.

Use `with NomadClient(credential=credential) as client:` to close the client
at the end of the session. The [client reference](api.md#nomad-client)
covers constructor options and ownership. For connection pools and worker
examples, see [Connections and HPC](connections.md).

## Open a client and check your account

Set `NOMAD_PAT` to a token issued by NOMAD Central. This example checks
which account the token belongs to and closes the client when the lookup ends.

| Action | Required scope |
| --- | --- |
| Construct or close a client | None |
| Read your account with `identity.me()` | `users:read` |

```python
--8<-- "tests/snippets/identity/test_authentication.py:named_setup"
```

## Advanced client options for workers

Use a Python dictionary when a script builds the same client options for multiple
workers or runs. Include the job's credential and unpack the dictionary with
`**options`. The keys match the
[`NomadClient` constructor](api.md#nomad-client-constructor).

```python
--8<-- "tests/snippets/identity/test_authentication.py:dictionary_setup"
```

For process-based work, [construct the client inside each worker](connections.md#configure-an-hpc-worker).
