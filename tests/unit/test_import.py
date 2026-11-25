def test_package_import() -> None:
    import nomad_python_api
    from nomad_python_api import ConnectionLimits, NetworkTimeouts, NomadClient, NomadTransport, Scope
    from nomad_python_api.identity import Account, BearerTokenCredential, OperationInfo

    assert nomad_python_api.__all__ == [
        "ConnectionLimits", "NetworkTimeouts", "NomadClient", "NomadTransport", "Scope",
    ]
    public_types = (
        ConnectionLimits, NetworkTimeouts, NomadClient, NomadTransport, Scope,
        Account, BearerTokenCredential, OperationInfo,
    )
    assert all(item.__doc__ for item in public_types)
