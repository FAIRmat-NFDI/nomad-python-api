from types import ModuleType

import pytest


@pytest.mark.snippet
@pytest.mark.parametrize(
    ("with_example", "expected_output"),
    [
        (False, "No public API entries.\n"),
        (True, "example: An example export.\n"),
    ],
)
def test_discover_api(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    with_example: bool,
    expected_output: str,
) -> None:
    if with_example:
        import nomad_python_api

        example = ModuleType("example", "An example export.\n\nAdditional details.")
        monkeypatch.setattr(nomad_python_api, "example", example, raising=False)
        monkeypatch.setattr(nomad_python_api, "__all__", ["example"])

    # --8<-- [start:discover_api]
    from inspect import getdoc

    import nomad_python_api as nomad

    if not nomad.__all__:
        print("No public API entries.")

    for name in nomad.__all__:
        description = getdoc(getattr(nomad, name))
        summary = description.splitlines()[0] if description else "No description available."
        print(f"{name}: {summary}")
    # --8<-- [end:discover_api]

    assert capsys.readouterr().out == expected_output
