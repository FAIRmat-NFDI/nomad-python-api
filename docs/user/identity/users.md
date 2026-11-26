# Accounts and users

Use `client.identity.me()` for the signed-in account. Use
`client.identity.users` to find collaborators or invite a new account.
Set `NOMAD_PAT` to a NOMAD Central token. Each example sets up its own
[client](client.md). For an Oasis, set the
[endpoint on your credential](sign-in.md#connect-to-an-oasis).

| Action | Required scope |
| --- | --- |
| Read your own account | `users:read` |
| Find collaborators by exact lookup, batch lookup, or prefix | `users:read` |
| Invite a new user | `users:invite` |

## Read your own account

This example reads the account ID and available profile fields.
`as_user()` converts the returned `Account` to a local `User` model.

```python
--8<-- "tests/snippets/identity/test_authentication.py:me_profile"
```

See the [Account return value](api.md#me-returns) for fields and methods.

## Find collaborators

Replace the example `email`, `username`, and `prefix` with values from
your deployment. An exact lookup
accepts one ID, username, or email. Pass a list of dictionaries to `get_many()` to
resolve a team in input order. Calling `search(prefix=...)` gives you
candidates to inspect before choosing a user.

```python
--8<-- "tests/snippets/identity/test_users_and_groups.py:directory_lookup"
```

The result contains user objects you can reuse in [group membership](groups.md).
NOMAD may omit email from a directory profile, including one found by email.
An exact lookup raises `UserNotFoundError` for a missing match or
`AmbiguousUserError` when several records match. A search with no candidates
returns an empty list. Each distinct selector in a batch can make one request.

## Invite a user

Replace the example `email` with the intended recipient's address. Pass a
`UserInviteOptions` object or a dictionary with the same fields.
On success, the example prints the user ID returned by NOMAD.

```python
--8<-- "tests/snippets/identity/test_users_and_groups.py:directory_invite"
```

!!! note "Deployment and delivery"

    NOMAD rejects invitations when the server's Oasis mode is enabled.
    The account result confirms the API outcome. Email delivery depends on
    the deployment. Check server state if the request outcome is uncertain.

See the [Python reference](api.md#users-reference) and the
[Users REST routes](rest.md#users-rest).
