# Shared NOMAD theme assets

The user and developer guides inherit their Material settings from `mkdocs.theme.yml`. A MkDocs hook includes the same stylesheet and favicon in both builds. Both guides use the logo from the shared theme override.

The three assets below are copied with maintainer-confirmed permission from FAIRmat-NFDI's [NOMAD documentation at commit `858e285`](https://github.com/FAIRmat-NFDI/nomad-docs/tree/858e285ce0070a6359024bfbde16bef6bf00f2f5).

| Local asset | Upstream source |
| --- | --- |
| `extra.css` | `docs/stylesheets/extra.css` |
| `favicon.png` | `docs/assets/favicon.png` |
| `overrides/.icons/nomad/nomad-logo-unfilled.svg` | `overrides/.icons/nomad/nomad-logo-unfilled.svg` |

When updating these assets, record the new upstream commit and rebuild both guides in strict mode.
