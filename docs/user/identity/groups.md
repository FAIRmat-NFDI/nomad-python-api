# Groups

Use groups to organize collaborators under a single ID. A group contains
users and their roles. Use [Accounts and users](users.md) to find the people
you want to add. Resource permissions remain with the operation that
shares the resource.

Each example opens and closes its own client. Set `NOMAD_PAT` to a
token from your deployment. The examples use NOMAD Central by default.
For an Oasis, set the [endpoint on your credential](sign-in.md#connect-to-an-oasis).

| Action | Required scope |
| --- | --- |
| Create without role-bearing members | `groups:write` |
| Create with members or maintainers | `groups:write` and `users:read` |
| Fetch or list groups | `groups:read` |
| Edit metadata or replace membership | `groups:write` |
| Resolve a collaborator by email or username | `users:read` |
| Delete a group | `groups:delete` |

## Create a group with a known team

Replace `email` and `username` with values for two different existing users.
NOMAD makes the signed-in user the sole owner.
With role-bearing members, the SDK reads the signed-in account once to
fill in the owner record required by NOMAD.

```python
--8<-- "tests/snippets/identity/test_users_and_groups.py:directory_create_group"
```

The returned `Group` includes its ID, owner, and the membership fields
provided by NOMAD. You can pass loaded users, IDs, or exact selector
dictionaries. Loaded `User` and `Account` objects supply IDs locally.
Selectors may require one lookup each. Choose a user from prefix search
before adding them.

## Edit group metadata and replace roles

Replace `group_id` with the ID of a group you can edit and `username`
with the account to add or promote. The
example updates the description and preserves the other members.

```python
--8<-- "tests/snippets/identity/test_users_and_groups.py:directory_group_roles"
```

!!! warning "Membership replacement"

    `replace_members()` sends the entire role-bearing list. Anyone omitted
    from the list is removed, except that the SDK preserves the owner.
    Use the current group state when other people may be editing membership.
    When passing only a group ID, supply its current owner explicitly.

Group ownership is fixed by NOMAD. Maintainers can manage membership.

## List groups and work in pages

Iterating `groups.list()` fetches groups as needed. `.filter()` returns a
new listing for criteria such as `group_id`, `user_id`, and `search_terms`.
Use `limit` for a total item cap. For batch work, use `.by_page()` to read
whole pages and their opaque continuation cursors. An offset is calculated
from the current sorted results. Changes can shift records across pages.

```python
--8<-- "tests/snippets/identity/test_users_and_groups.py:directory_list_groups"
```

## Delete a group

Replace `group_id` with the ID of a group you intend to delete. Only the owner or
a deployment administrator can delete it. Successful deletion returns `None`.

```python
--8<-- "tests/snippets/identity/test_users_and_groups.py:directory_delete_group"
```

See the [Python reference](api.md#groups-reference) and
[Groups REST routes](rest.md#groups-rest) for every input and response field.
