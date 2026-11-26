from collections.abc import Mapping, Sequence

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from .._core._operation import Operation, OperationInfo
from .._core._pipeline import RequestPipeline
from .._scopes import Scope
from ..exceptions import AmbiguousUserError, HttpResponseError, InvalidResponseError, UserNotFoundError
from ._directory_support import (
    directory_id, json_extension, query_extension, send_directory_lookup, send_directory_write,
)
from ._user import User, UserInviteOptions

_READ = frozenset({Scope.USERS_READ})
_ME = Operation(OperationInfo(
    "identity.me", "Get the authenticated NOMAD account.", _READ,
), "GET", "/users/me")
_FILTERED = Operation(OperationInfo(
    "identity.users.search", "Find NOMAD users by a directory selector.", _READ
), "GET", "/users")
_GET = Operation(OperationInfo(
    "identity.users.get", "Look up a NOMAD user.", _READ
), "GET", "/users/{user_id}")
_EXACT = Operation(_GET.info, "GET", _FILTERED.path)
_INVITE = Operation(OperationInfo(
    "identity.users.invite", "Invite a user to the deployment.", frozenset({Scope.USERS_INVITE})
), "PUT", "/users/invite")
_SELECTORS = {"user_id", "email", "username"}
_FILTERS = _SELECTORS | {"prefix"}


class _UserResults(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    data: list[User]


def _exact_selector(values: Mapping[str, object]) -> tuple[str, str]:
    if not isinstance(values, Mapping) or len(values) != 1 or values.keys() - _SELECTORS:
        raise ValueError("Supply exactly one user_id, username, or email selector.")
    field, value = next(iter(values.items()))
    if not isinstance(value, str) or not value.strip() or not value.isprintable():
        raise ValueError("The user selector must be a nonempty string.")
    if field == "user_id" and directory_id(value) in {"me", "invite"}:
        raise ValueError("Supply a user ID rather than a reserved route name.")
    return field, value


class UserOperations:
    """Find and invite users on the client's deployment."""

    def __init__(self, pipeline: RequestPipeline) -> None:
        self._pipeline = pipeline

    def get_operation_info(self, name: str) -> OperationInfo:
        """Return the name and required scopes of a user operation."""
        if name in {"get", "get_by_id", "get_by_email", "get_by_username", "get_many"}:
            return _GET.info
        return {"search": _FILTERED, "invite": _INVITE}[name].info

    def get(
        self, *, user_id: str | None = None, username: str | None = None, email: str | None = None
    ) -> User:
        """Resolve one exact user selector."""
        return self._get(*_exact_selector({
            field: value for field, value in (
                ("user_id", user_id), ("username", username), ("email", email)
            ) if value is not None
        }))

    def get_by_id(self, user_id: str) -> User:
        return self.get(user_id=user_id)

    def get_by_username(self, username: str) -> User:
        return self.get(username=username)

    def get_by_email(self, email: str) -> User:
        return self.get(email=email)

    def get_many(self, selectors: Sequence[Mapping[str, str]]) -> list[User]:
        """Resolve exact selectors in order, reusing each distinct lookup within the call."""
        if not isinstance(selectors, Sequence) or isinstance(selectors, (str, bytes)):
            raise ValueError("Supply a sequence of exact user selectors.")
        exact = [_exact_selector(selector) for selector in selectors]
        resolved = {selector: self._get(*selector) for selector in dict.fromkeys(exact)}
        return [resolved[selector] for selector in exact]

    def search(self, *, prefix: str, extra_query: Mapping[str, object] | None = None) -> list[User]:
        """Find candidates by a nonempty prefix."""
        if not isinstance(prefix, str) or not prefix.strip() or not prefix.isprintable():
            raise ValueError("Supply a nonempty user search prefix.")
        query = httpx.QueryParams({"prefix": prefix}).merge(query_extension(extra_query, _FILTERS))
        return self._find(_FILTERED, query)

    def invite(
        self, options: UserInviteOptions | Mapping[str, object], *,
        extra_json: Mapping[str, object] | None = None,
    ) -> User:
        """Send one invitation through the deployment's user provider."""
        if not isinstance(options, UserInviteOptions):
            if not isinstance(options, Mapping):
                raise ValueError("Supply invitation options as an object or mapping.")
            try:
                options = UserInviteOptions.model_validate(dict(options))
            except ValidationError:
                raise ValueError("Invalid invitation options. A nonempty email is required.") from None
        if not options.email.strip() or not options.email.isprintable():
            raise ValueError("A nonempty email is required.")
        body = options.model_dump(mode="json", exclude_unset=True)
        body.update(json_extension(extra_json, set(User.model_fields) | {"options", "password", "roles"}))
        user = send_directory_write(self._pipeline, _INVITE, User, body=body)
        assert user is not None
        return self._bind(user)

    def _get(self, field: str, value: str) -> User:
        if field == "user_id":
            try:
                data = send_directory_lookup(self._pipeline, _GET, user_id=value)
            except HttpResponseError as error:
                if error.status_code == 404:
                    raise UserNotFoundError("No user matched the exact selector.") from None
                raise
            if data is None:
                raise UserNotFoundError("No user matched the exact selector.")
            try:
                user = User.model_validate(data)
            except ValidationError:
                pass
            else:
                if user.user_id == value:
                    return self._bind(user)
            raise InvalidResponseError("identity.users.get returned an invalid user response.")

        matches = self._find(_EXACT, httpx.QueryParams({field: value}))
        if not matches:
            raise UserNotFoundError("No user matched the exact selector.")
        if len(matches) > 1:
            raise AmbiguousUserError("The exact selector matched multiple users.")
        return matches[0]

    def _get_me(self) -> User:
        data = self._pipeline.send(_ME)
        try:
            user = User.model_validate(data)
        except ValidationError:
            pass
        else:
            return self._bind(user)
        raise InvalidResponseError("identity.me returned an invalid account response.")

    def _find(self, operation: Operation, query: httpx.QueryParams) -> list[User]:
        data = send_directory_lookup(self._pipeline, operation, query)
        try:
            results = _UserResults.model_validate(data)
        except ValidationError:
            pass
        else:
            return [self._bind(user) for user in results.data]
        raise InvalidResponseError(f"{operation.info.name} returned an invalid user list.")

    def _bind(self, user: User) -> User:
        user._endpoint = self._pipeline.endpoint
        return user
