# Release Process

This document defines a lightweight release flow for alpha, beta, and stable tags.

## Versioning

Recommended tag format:

- alpha: `v0.0.1-alpha.1`
- beta: `v0.1.0-beta.1`
- stable: `v0.1.0`

## Release Types

### Alpha

Use alpha releases when:

- APIs and docs may still move quickly
- feature coverage is incomplete
- results are still exploratory

Required checks:

- repository is public-safe
- CI is green
- README reflects current limitations
- release notes are written

### Beta

Use beta releases when:

- main workflows are reproducible
- key docs exist and are current
- major breakages are not expected for normal evaluation flows

Required checks:

- alpha checklist passes
- quickstart path is validated
- duplicate evaluation path is documented
- major known limitations are explicitly listed

### Stable

Use stable releases when:

- public APIs and workflows are intentionally supported
- documentation is coherent and reviewable
- release risk is materially lower than beta

Required checks:

- beta checklist passes
- no known release-blocking regressions
- version tag and release notes are final

## Pre-Release Checklist

- [ ] Pull latest `main`
- [ ] Confirm CI status is green
- [ ] Confirm `README.md` and `README-cn.md` match current scope
- [ ] Confirm generated artifacts are not accidentally staged
- [ ] Confirm version tag naming is correct
- [ ] Draft release notes from `docs/release-notes-template.md`

## Tagging Commands

Create an annotated tag:

```powershell
git tag -a v0.0.1-alpha.1 -m "Initial public alpha release"
git push origin v0.0.1-alpha.1
```

## GitHub Release Notes

Use the template in `docs/release-notes-template.md`.

Recommended flags:

- mark alpha and beta tags as pre-releases
- keep stable releases as normal releases

## Post-Release Follow-Up

- verify the tag is visible on GitHub
- verify the release notes render correctly
- open follow-up issues for anything deferred from the checklist

