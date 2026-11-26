# Manage personal access tokens { #manage-pats }

Use a Keycloak access token to create, list, inspect, rotate, and revoke
personal access tokens (PATs). Use a scoped PAT for a notebook or an
unattended job.
[NOMAD authentication guide](https://docs.nomad-lab.eu/howto/manage/program/auth.html#use-a-keycloak-access-token-when-required)

| Action | Required scope |
| --- | --- |
| Read the signed-in account | `users:read` |
| Create a PAT | `tokens:create` |
| List or inspect PATs | `tokens:read` |
| Rotate a PAT | `tokens:create` and `tokens:delete` |
| Revoke a PAT | `tokens:delete` |

## Connect and check your account

Set `NOMAD_KEYCLOAK_ACCESS_TOKEN` to a valid access token obtained through
your deployment's sign-in flow. The examples use `endpoint = "prod"`
for NOMAD Central. For a self-hosted NOMAD Oasis, replace that value with
the issuing deployment's complete HTTPS API v1 URL. You can also use a [browser credential](sign-in.md#browser-login)
to acquire the access token interactively. Each example opens and
closes its own client.

```python
--8<-- "tests/snippets/identity/test_pat_management.py:pat_client"
```

The command prints your username and optional display name.
The `Account` also provides fields such as affiliation and creation time
when NOMAD returns them. `as_user()` produces a local profile model
without calling NOMAD again.

## Create a PAT

Choose the permissions the job needs. Pass enum members and scope
strings together as needed.

| Scope granted to the job PAT | What it lets the job do |
| --- | --- |
| `users:read` | Read its account profile |
| `uploads:read` | Read Project metadata it can access |

```python
--8<-- "tests/snippets/identity/test_pat_management.py:pat_create_object"
```

Create returns the PAT metadata and the one-time secret. The result's
representation and default JSON export exclude the secret. Use
`BearerTokenCredential.from_issued(issued)` to use it directly, or
explicitly extract it with `issued.raw_token.get_secret_value()` when
transferring it to a protected secret store.

## List and filter PATs

Both listing methods return a lazy iterable. A plain loop fetches
additional results as needed. `limit` caps the total number consumed.
`.filter()` builds another listing with additional server-side filters.
It leaves the original reusable and rejects a conflicting value for a
filter already set.

```python
--8<-- "tests/snippets/identity/test_pat_management.py:pat_list"
```

The [list reference](api.md#pat-list) covers every filter, including
creation, last-use, and expiration bounds, as well as sorting.

## Inspect, use, rotate, and revoke { #inspect-use-rotate-and-revoke }

The example creates a temporary PAT, uses it to check the job's account,
rotates it, and revokes the replacement. The original Keycloak client
manages the PAT. The job credential carries the PAT metadata ID so it
can also identify the rotation target. Revocation accepts metadata as well.
`delete()` is another name for `revoke()`.

```python
--8<-- "tests/snippets/identity/test_pat_management.py:pat_lifecycle"
```

Rotation invalidates the old PAT when NOMAD processes the request.
Update the jobs that used it with the replacement. NOMAD can also revoke
the original PAT before replacement creation fails with HTTP `400`.
If rotation raises `PatWriteOutcomeUnknownError`, use
`pats.get(job_credential).revoked` to check the original PAT before another
write. Inspect the PAT list in NOMAD if you need to reconcile the outcome.
Revocation invalidates the selected PAT.

## Advanced dictionaries for bulk workflows

When a workflow prepares several PATs, put the shared fields in a Python
dictionary and add each run's name and lifetime. Pass each dictionary directly
to `pats.create()`. Each iteration sends one request and issues one PAT.
If a later request fails, the PATs already issued stay active.

```python
--8<-- "tests/snippets/identity/test_pat_management.py:pat_create_dict"
```

Keep each issued result in memory until the job consumes its credential or the
secret is transferred to a protected store. Omitting `expires_in_days` uses the
server default. Passing `None` explicitly sends JSON `null`, which the deployment
interprets according to its expiry policy. The same dictionary pattern works
for `.filter(**filters)` when several runs reuse search criteria.

## Advanced paging and checkpointing

`page_size` controls how many entries NOMAD returns per request. Use
`.by_page()` for whole batches and store the opaque cursor after a batch
is processed. Resume with the same deployment, account, filters, and
sort order. A listing with `limit` is for item iteration.

!!! warning "A PAT cursor resumes against the current results"

    NOMAD uses an offset into the current sorted list. Additions or removals
    before that offset can skip or repeat records even with identical filters
    and sorting. For complete coverage, scan while the results are stable.
    If the list changed after your checkpoint, restart from the first page
    and deduplicate by `pat.id`.

```python
--8<-- "tests/snippets/identity/test_pat_management.py:pat_pages"
```

## Advanced Oasis extensions { #advanced-oasis-extensions }

Suppose your self-hosted Oasis documents an extra `institute_tag`
field for PAT creation and listing. Set `endpoint` to its API URL in
the example. Use `extra_json` for the body field and `extra_query` for the
query parameter.

```python
--8<-- "tests/snippets/identity/test_pat_management.py:pat_oasis"
```

Check your deployment's REST contract for its supported extensions.
Standard fields use the named SDK options.

## Diagnose an authorization error

A PAT can authenticate `NomadClient` for job operations. PAT management
requires a Keycloak access token with the scopes in the table above.
To see how the SDK reports rejected PAT management, set `NOMAD_PAT`
and replace the example `pat_id` with its metadata ID.
`401` means NOMAD rejected the credential. `403` means NOMAD refused
the action for the authenticated caller.

```python
--8<-- "tests/snippets/identity/test_pat_management.py:pat_permission_error"
```

See [PAT errors](api.md#pat-errors) for local policy, deployment
mismatches, ambiguous write outcomes, and recovery.

The next example attempts a rotation using a Keycloak access token.
Replace `pat_id` with the metadata ID of a PAT you intend to replace.
If the outcome is uncertain, reconcile it before making another write.

```python
--8<-- "tests/snippets/identity/test_pat_management.py:pat_rotation_errors"
```
