# Access and scopes

Credentials identify the caller. NOMAD checks the caller's permissions for
each operation. The client's optional `allowed_scopes` policy can also
block an operation locally before it sends a request.

| Example action | Required scope |
| --- | --- |
| Inspect the local policy and operation metadata | None |
| Read your account | `users:read` |

## Choose and inspect scopes

`client.allowed_scopes` is a [read-only property](api.md#client-allowed-scopes). Call [`client.identity.get_operation_info("me")`](api.md#identity-get-operation-info) to see what an operation requires. `Scope.USERS_READ` is a member of the [`Scope` enum](api.md#scope).

With `NOMAD_PAT` set, compare your local policy with the scopes required by `me()` before looking up the account.

```python
--8<-- "tests/snippets/identity/test_authentication.py:inspect_and_read_account"
```

`Allowed` and `Required` both show `users:read`. A successful lookup prints `Account returned: True`. `Username available` depends on the account returned by NOMAD.

## Troubleshoot a request

Set `NOMAD_PAT` and run this example to check how account lookups report
authentication and permission errors.

```python
--8<-- "tests/snippets/identity/test_authentication.py:error_recovery"
```

See [exceptions](api.md#exceptions) for sign-in errors and API responses.
