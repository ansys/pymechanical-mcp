---
description: "Use when: preparing, reviewing, merging, tagging, or publishing a PyMechanical MCP release; editing version metadata or Towncrier release notes; handling the automatic post-tag changelog PR."
---

# PyMechanical MCP Release Procedure

## Verified Release Model

- The package version is in `pyproject.toml`.
- Towncrier fragments are in `doc/changelog.d/`; rendered notes are `doc/source/changelog.rst`.
- `.github/workflows/ci.yml` triggers release automation only on a pushed `v*` tag. That tag triggers the GitHub release, PyPI publication, stable docs deployment, and the separate automated `Update CHANGELOG (on release)` PR.

## Required Order

1. Prepare a reviewed release PR: set the intended version, render the Towncrier notes, and remove the consumed fragments. Validate hooks, non-integration tests, documentation, and package artifacts.
2. Wait for all required PR checks and an independent approval. Do not merge without explicit user authorization.
3. After the release PR is merged and `main` CI is green, confirm `main` contains the intended version and rendered release notes. Obtain explicit authorization before pushing `v<version>`.
4. Push the annotated release tag from the validated `main` commit. Monitor the tag workflow through GitHub release, PyPI publication, and stable documentation deployment.
5. Only after the tag workflow succeeds, review the automated changelog PR it creates. It is a post-release documentation update; never merge it before the release tag is created and its workflow completes.
6. Verify the GitHub release, PyPI version, published documentation, and `main`/tag commit relationship. Report results before deleting release branches or worktrees.

## Safeguards

- Never create, push, move, or delete a release tag without explicit user confirmation immediately before that action.
- Never merge the automatic changelog PR as a substitute for the release-preparation PR or before tag workflow success.
- A failed local Sphinx build must be investigated: distinguish pre-existing environment/API warnings from warnings introduced by release notes, and do not suppress unrelated warnings.
- Release-prep PR titles must use an allowed conventional-commit type, for example `chore(release): prepare v<version>`; `release:` is rejected by CI.
