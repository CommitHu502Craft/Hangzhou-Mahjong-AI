# Known Limitations

This document records the current boundaries of the project in a form that is easier to review than a short README section.

## Model Validation Gap

Impact:

- current evidence is stronger in duplicate and simulation settings than in real gameplay
- public claims must stay below a strong real-human-performance claim

Mitigation:

- keep real-world evaluation as a separate gate
- expand evidence only after replay/offline and human-facing reports are stable

Related issues:

- `#5` Evaluation TODO

## Rule Coverage Scope

Impact:

- the current implementation is centered on the Hangzhou Mahjong MVP profile
- unsupported or partially-supported rule branches may affect broader reuse

Mitigation:

- add rule coverage mapping and edge-case fixtures
- prioritize missing cases by gameplay impact

Related issues:

- `#4` Rules Coverage Gap

## Public Repo Artifact Scope

Impact:

- trained models, generated datasets, reports, and logs are not shipped in the public repository
- visitors cannot reproduce published outputs only by browsing the repo tree

Mitigation:

- keep regeneration commands documented
- use release notes and docs to clarify what is and is not bundled

Related issues:

- `#8` Release Process

## Frontend Scope

Impact:

- the current frontend is best understood as a demo/showcase surface, not a complete product UI
- UX polish and operational workflows are intentionally limited

Mitigation:

- improve public-facing presentation iteratively
- avoid over-positioning the frontend as production-ready

Related issues:

- `#3` Frontend Polish

## Contributor Experience

Impact:

- new contributors can still lose time on environment setup, test expectations, and doc discovery

Mitigation:

- keep onboarding, contribution, and release docs explicit and current

Related issues:

- `#6` Docs Onboarding

