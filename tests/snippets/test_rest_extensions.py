import json

import httpx
import pytest

pytestmark = pytest.mark.snippet


# --8<-- [start:extra_json_demo]
def build_example_payload(
    *,
    name: str,
    extra_json: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {"name": name}
    if extra_json is not None:
        duplicate_fields = payload.keys() & extra_json.keys()
        if duplicate_fields:
            names = ", ".join(sorted(duplicate_fields))
            raise ValueError(f"Fields already set by the wrapper: {names}")
        payload.update(extra_json)
    return payload


body = build_example_payload(
    name="Example record",
    extra_json={"institute_tag": "materials-lab"},
)
# --8<-- [end:extra_json_demo]


def test_extra_json_fields_are_encoded_at_the_top_level() -> None:
    request = httpx.Request("POST", "https://oasis.example.org/api/v1/example", json=body)
    assert request.method == "POST"
    assert request.url.path == "/api/v1/example"
    assert json.loads(request.content) == {
        "name": "Example record",
        "institute_tag": "materials-lab",
    }


def test_extra_json_preserves_the_base_payload_when_omitted() -> None:
    assert build_example_payload(name="Example record") == {"name": "Example record"}


def test_an_extra_field_cannot_overwrite_a_named_argument() -> None:
    with pytest.raises(ValueError, match="Fields already set by the wrapper: name"):
        build_example_payload(name="Example record", extra_json={"name": "Override"})
