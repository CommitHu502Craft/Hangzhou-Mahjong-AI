# Discovery Baseline

Date: 2026-02-22  
Scope: tooling and runtime baseline for TASK 1

## Commands

1. `python --version`
2. `pip --version`
3. `pytest --version`
4. `rg --version`

## Outputs

- Python: `3.11.5`
- pip: `25.3 (python 3.11, conda base)`
- pytest: `7.4.0`
- rg: `15.1.0`

## Conclusion

- `python`, `pip`, `pytest`, `rg` are all available.
- Python pin recommendation remains:
1. Primary: `Python 3.11`
2. Fallback: `Python 3.10`

## Next Step

- Write pinned dependencies into `requirements.txt` and validate key pin lines.

## Dependency Install Feasibility (TASK 3)

Command:
- `python -m pip install -r requirements.txt --dry-run`

Result:
- Exit code `0`
- Resolver can locate all pinned packages.
- Note: `stable-baselines3==2.3.0` is marked yanked due to legacy `torch 1.13` loading issue; current baseline is `torch>=2.0.0`, so this pin remains acceptable for this project contract.
