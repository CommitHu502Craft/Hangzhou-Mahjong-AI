from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple


def load_ab_records(paths: Sequence[Path]) -> Tuple[List[Dict[str, object]], List[str]]:
    records: List[Dict[str, object]] = []
    errors: List[str] = []
    for path in paths:
        path = Path(path)
        if not path.exists():
            errors.append(f"missing file: {path}")
            continue
        suffix = path.suffix.lower()
        try:
            if suffix in (".ndjson", ".jsonl"):
                records.extend(_read_jsonl(path))
            elif suffix == ".json":
                records.extend(_read_json(path))
            elif suffix == ".csv":
                records.extend(_read_csv(path))
            else:
                errors.append(f"unsupported file type: {path}")
        except Exception as exc:  # pragma: no cover - defensive.
            errors.append(f"failed to parse {path}: {exc}")
    return records, errors


def canonicalize_records(raw_records: Iterable[Mapping[str, object]]) -> Tuple[List[Dict[str, object]], List[str]]:
    rows: List[Dict[str, object]] = []
    errors: List[str] = []
    for idx, rec in enumerate(raw_records):
        try:
            row = _canonicalize_one(rec, idx=idx)
            rows.append(row)
        except Exception as exc:
            errors.append(f"record[{idx}] invalid: {exc}")
    return rows, errors


def summarize_diffs(diffs: Sequence[float]) -> Dict[str, float]:
    n = len(diffs)
    if n <= 0:
        return {
            "n_games": 0,
            "mean_diff": 0.0,
            "std_diff": 0.0,
            "ci95": 0.0,
            "lower_ci95": 0.0,
        }
    mean = sum(diffs) / n
    if n == 1:
        std = 0.0
    else:
        var = sum((x - mean) ** 2 for x in diffs) / n
        std = math.sqrt(var)
    ci95 = 1.96 * std / math.sqrt(n) if n > 0 else 0.0
    return {
        "n_games": int(n),
        "mean_diff": float(mean),
        "std_diff": float(std),
        "ci95": float(ci95),
        "lower_ci95": float(mean - ci95),
    }


def _read_jsonl(path: Path) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        if not isinstance(item, dict):
            raise ValueError(f"jsonl item is not object in {path}")
        rows.append(item)
    return rows


def _read_json(path: Path) -> List[Dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        out: List[Dict[str, object]] = []
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError(f"json list item is not object in {path}")
            out.append(item)
        return out
    if isinstance(payload, dict):
        if isinstance(payload.get("records"), list):
            out = []
            for item in payload["records"]:
                if not isinstance(item, dict):
                    raise ValueError(f"json records item is not object in {path}")
                out.append(item)
            return out
        return [payload]
    raise ValueError(f"json payload must be object or list in {path}")


def _read_csv(path: Path) -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            out.append({str(k): (v if v is not None else "") for k, v in row.items()})
    return out


def _canonicalize_one(rec: Mapping[str, object], idx: int) -> Dict[str, object]:
    diff = _extract_diff(rec)
    game_id = str(rec.get("game_id", f"game_{idx+1:06d}"))
    timestamp = str(rec.get("timestamp", ""))
    source = str(rec.get("source", ""))
    notes = str(rec.get("notes", ""))
    return {
        "game_id": game_id,
        "timestamp": timestamp,
        "source": source,
        "diff": float(diff),
        "notes": notes,
    }


def _extract_diff(rec: Mapping[str, object]) -> float:
    for key in ("diff", "score_diff", "ab_diff"):
        if key in rec:
            return float(rec[key])
    if "model_score" in rec and "baseline_score" in rec:
        return float(rec["model_score"]) - float(rec["baseline_score"])
    if "hero_score" in rec and "table_avg" in rec:
        return float(rec["hero_score"]) - float(rec["table_avg"])
    raise ValueError(
        "missing diff fields; expected one of "
        "[diff/score_diff/ab_diff] or [model_score,baseline_score] or [hero_score,table_avg]"
    )
