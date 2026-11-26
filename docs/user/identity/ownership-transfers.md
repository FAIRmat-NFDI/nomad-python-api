# Ownership transfers

Transfer ownership of a group or project to another NOMAD user. The SDK
returns Python objects that can be passed to later operations or used directly
through method chaining. A transfer remains pending until the target user
accepts or refuses it; the SDK never accepts on another user's behalf.

Each example opens and closes its own client. Set `NOMAD_PAT` to a token from
your deployment. NOMAD Central is the default. For an Oasis, set the
[endpoint on the credential](sign-in.md#connect-to-an-oasis).

## Permissions

NOMAD currently applies upload scopes to both project and group ownership
transfer routes.

| Action | Required scopes |
| --- | --- |
| List or get transfers | `uploads:read` |
| Create, accept, refuse, or cancel | `uploads:read` and `uploads:write` |

The client's `allowed_scopes` is a local safety boundary. NOMAD independently
checks the credential and whether the signed-in user is allowed to act on the
resource or transfer.

## Transfer a loaded group

Load a group and create its transfer through the bound operation. The target
can be selected by `user_id`, `username`, or `email`. Use an exact value for
one person.

```python
--8<-- "tests/snippets/identity/test_ownership_transfers.py:ownership_create_chain"
```

Expected output:

```text
group Diffraction team
```

`transfer` is an `OwnershipTransfer`. It includes the visible `transfer_id`,
but normal object chaining does not require you to copy that ID.

## Use object or dictionary inputs

Use `OwnershipResourceRef` when you know a resource ID without loading the
resource. A complete `OwnershipTransferCreateRequest` is convenient when a
validated job or notebook creates several transfers. Equivalent Python
dictionaries are accepted at both boundaries.

```python
--8<-- "tests/snippets/identity/test_ownership_transfers.py:ownership_create_forms"
```

Expected output:

```text
group-id-1 group-id-1
```

The supported input shapes are:

| Input | Accepted forms |
| --- | --- |
| Resource | Loaded `Group`; `OwnershipResourceRef`; `{"resource_type": "group", "resource_id": "..."}`; raw group mapping with `group_id`; raw project mapping with `upload_id`; or a future SDK object exposing `ownership_resource_type` and `ownership_resource_id`. |
| Target user | Loaded `User` or `Account`; or a mapping containing `user_id`, `username`, or `email`. A present `user_id` is preferred over other fields in a raw user response. |
| Complete request | `OwnershipTransferCreateRequest` or its equivalent four-field mapping. |

## List and retrieve transfers

Calling `get()` without a target lists transfers. With no `resource_type`, the
SDK requests both currently supported types—projects (`upload`) and groups—and
returns one list sorted by `updated_at`, newest first. Filters run on NOMAD.

```python
--8<-- "tests/snippets/identity/test_ownership_transfers.py:ownership_list_get"
```

Expected output:

```text
2 Diffraction team
```

Use `direction="incoming"`, `"outgoing"`, or `"all"`; the enum values are
equivalent. Optional `resource_id` and `state` further narrow a listing.
When you know a transfer's resource type, passing it avoids discovery calls.
For a deployment-specific future type, pass its raw string explicitly.

## Accept, refuse, cancel, and process a batch

The target user can accept or refuse an incoming transfer. The source user can
cancel an outgoing pending transfer. A loaded transfer supports `.accept()`,
`.refuse()`, and `.cancel()` while its client remains open.

```python
--8<-- "tests/snippets/identity/test_ownership_transfers.py:ownership_actions"
```

Expected output:

```text
transfer-id-1 2 0
```

You can also call `client.ownership_transfers.accept(...)`, `.refuse(...)`, or
`.cancel(...)` with one transfer object, REST-shaped mapping, or transfer ID.
A list runs sequentially, continues after individual failures, and returns an
`OwnershipTransferBatchResult` with ordered `succeeded` and `failed` tuples.
Duplicate targets are rejected before any request.

!!! warning "Refresh after an uncertain write"

    A timeout, server error, or malformed success response does not prove that
    a write failed. The SDK raises `OwnershipTransferOutcomeUnknownError`.
    Refresh the transfer and resource before issuing another write. A response
    that says a transfer is no longer pending raises
    `OwnershipTransferNotPendingError`.

See the [Python API reference](api.md#ownership-transfer-reference) for every
parameter, return model, and error. The [REST and Oasis reference](rest.md#ownership-transfer-rest)
contains the complete wire payload and deployment-extension controls.
