# Branches and deployment

| Branch | How changes arrive | What CI publishes |
| --- | --- | --- |
| `dev/<name>` | Create from `develop`, for example `dev/auth_module`. Open a PR into `develop`. | PR checks only |
| `develop` | Merge a reviewed feature PR after the checks pass. | User guide to GitHub Pages |
| `main` | After manual review of `develop`, merge a PR from `develop` using a merge commit. The initial scaffold is the one direct-commit exception. | Wheel and source distribution to PyPI |

Keep `main` as the repository default. Before each promotion, bump the package version and refresh `uv.lock` in a PR to `develop`, for example with `uv version 0.1.1` followed by `uv lock`. CI requires the version in the release PR to be greater than the version on `main`. PyPI filenames cannot be reused.

## One-time GitHub and PyPI setup

1. With explicit approval for the first scaffold commit, bootstrap `main` and create `develop` from it. Apply branch rules to `main` and `develop` after bootstrapping. Require PRs, manual approval, and the CI `docs` and `package` matrix checks. Disallow direct pushes and broad bypass access.
2. In GitHub **Settings → Pages**, select **GitHub Actions** as the source. Restrict the `github-pages` environment to deployments from `develop`. The workflow uploads `site/user/`, the Usage site built with `mkdocs.public.yml`. The combined site is used for local preview and CI checks.
3. In **Settings → Environments**, create `nomad-test` and allow deployments from `develop` and `main` only.
    - Under **Environment variables**, set `NOMAD_TEST_API_URL` to the complete HTTPS API base URL for the deployment to test. For the NOMAD test deployment, use `https://nomad-lab.eu/prod/v1/test/api/v1`. [GitHub environment variables](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-variables#creating-configuration-variables-for-an-environment)
    - Under **Environment secrets**, set `NOMAD_TEST_PAT` to a PAT issued by the deployment configured in `NOMAD_TEST_API_URL`. Give it only `users:read`. If the deployment changes, update both values together. Replace the secret when the PAT expires or is revoked. [Create a NOMAD PAT](https://docs.nomad-lab.eu/howto/manage/program/auth.html#create-a-pat)
4. Create the GitHub environment `pypi` and restrict it to `main`. Configure [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/adding-a-publisher/) for owner `FAIRmat-NFDI`, repository `nomad-python-api`, workflow `ci.yml`, and environment `pypi`. Use a pending publisher if the PyPI project is new. Set this up before the first push to `main` that should publish. If a release run fails because setup is incomplete, finish the setup and rerun the failed job for that commit.

PRs run the mocked offline tests and docs checks without access to the live-test secret. Pushes to `develop` and `main` run those checks and the **Live NOMAD test** job before publishing. The live job requires both `NOMAD_TEST_API_URL` and `NOMAD_TEST_PAT`. Once this workflow is on the default branch, you can rerun both test layers without publishing from **Actions → CI → Run workflow** by selecting `develop` or `main`. Publishing uses GitHub OIDC and needs no stored PyPI token.
