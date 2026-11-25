from types import ModuleType

import pytest


@pytest.mark.snippet
@pytest.mark.parametrize(
    ("export_mode", "expected_output"),
    [
        ("empty", "No public API entries.\n"),
        ("example", "example: An example export.\n"),
        (
            "actual",
            "ConnectionLimits: Bound the client's connection pool and idle connection reuse.\n"
            "NetworkTimeouts: Set timeouts in seconds for the individual API network phases.\n"
            "NomadClient: Use a bearer credential to call a NOMAD deployment.\n"
            "NomadTransport: Own a connection pool that several NOMAD clients can borrow.\n"
            "Scope: NOMAD permission names used by this SDK.\n",
        ),
    ],
)
def test_discover_api(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    export_mode: str,
    expected_output: str,
) -> None:
    import nomad_python_api

    if export_mode == "empty":
        monkeypatch.setattr(nomad_python_api, "__all__", [])
    if export_mode == "example":
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
