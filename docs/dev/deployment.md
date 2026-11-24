# Branches and deployment

| Branch | How changes arrive | What CI publishes |
| --- | --- | --- |
| `dev/<name>` | Create from `develop`, for example `dev/auth_module`. Open a PR into `develop`. | PR checks only |
| `develop` | Merge a reviewed feature PR after the checks pass. | User guide to GitHub Pages |
| `main` | After manual review of `develop`, merge a PR from `develop` using a merge commit. The initial scaffold is the one direct-commit exception. | Wheel and source distribution to PyPI |

Keep `main` as the repository default. Before each promotion, bump the package version and refresh `uv.lock` in a PR to `develop`, for example with `uv version 0.1.1` followed by `uv lock`. CI requires the version in the release PR to be greater than the version on `main`. PyPI filenames cannot be reused.

## One-time GitHub and PyPI setup

1. With explicit approval for the first scaffold commit, bootstrap `main` and create `develop` from it. Apply branch rules to `main` and `develop` after bootstrapping. Require PRs, manual approval, and the CI `docs` and `package` matrix checks. Disallow direct pushes and broad bypass access.
2. In GitHub **Settings → Pages**, select **GitHub Actions** as the source. Restrict the `github-pages` environment to deployments from `develop`. The workflow uploads only `site/user/`. The developer guide builds locally and in CI.
3. Create the GitHub environment `pypi` and restrict it to `main`. Configure [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/adding-a-publisher/) for owner `FAIRmat-NFDI`, repository `nomad-python-api`, workflow `ci.yml`, and environment `pypi`. Use a pending publisher if the PyPI project is new. Set this up before the first push to `main` that should publish. If a release run fails because setup is incomplete, finish the setup and rerun the failed job for that commit.

The deployment jobs run after the package and docs checks succeed. A PR runs the checks without deploying. Publishing needs no stored PyPI token.
