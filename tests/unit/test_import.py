def test_package_import() -> None:
    import nomad_python_api
    from nomad_python_api import NomadClient, Scope
    from nomad_python_api.identity import Account, BearerTokenCredential, OperationInfo

    assert nomad_python_api.__all__ == ["NomadClient", "Scope"]
    assert all(item.__doc__ for item in (NomadClient, Scope, Account, BearerTokenCredential, OperationInfo))
