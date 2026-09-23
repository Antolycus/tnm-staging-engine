"""Semantic validation for cancer staging configs that JSON Schema
draft-07 cannot express: stage_groups row uniqueness, wildcard
ordering, cross-references to defined category codes, and strict
case-sensitivity of the 'Any' wildcard literal."""

import json
import sys
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_json(path: Path) -> dict[str, Any]:
    """Load and parse a JSON file from disk."""
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def check_any_case(rows: list[dict[str, str]], label: str) -> list[str]:
    """Flag any t/n/m value that looks like a case-variant or
    alternate spelling of the 'Any' wildcard (e.g. 'any', 'ANY', '*')
    instead of the exact literal 'Any'."""
    errors = []
    suspicious = {"any", "ANY", "aNY", "*", "ALL", "all"}
    for i, row in enumerate(rows):
        for field in ("t", "n", "m"):
            value = row[field]
            if value != "Any" and value.strip().lower() in {"any", "*", "all"}:
                errors.append(
                    f"{label} stage_groups[{i}].{field} = {value!r} looks like a "
                    "wildcard typo; the exact literal must be 'Any'."
                )
    return errors


def check_uniqueness(rows: list[dict[str, str]], label: str) -> list[str]:
    """Flag duplicate (t, n, m) keys mapped to different stages."""
    errors = []
    seen: dict[tuple[str, str, str], str] = {}
    for i, row in enumerate(rows):
        key = (row["t"], row["n"], row["m"])
        if key in seen:
            if seen[key] != row["stage"]:
                errors.append(
                    f"{label} stage_groups[{i}]: duplicate key {key} maps to "
                    f"'{row['stage']}' but an earlier row mapped it to '{seen[key]}'."
                )
            else:
                errors.append(
                    f"{label} stage_groups[{i}]: exact duplicate row {key} -> "
                    f"'{row['stage']}' (redundant, remove one)."
                )
        else:
            seen[key] = row["stage"]
    return errors


def _matches(row: dict[str, str], t: str, n: str, m: str) -> bool:
    """Return True if a stage_groups row would match this (t, n, m)."""
    return (
        (row["t"] in ("Any", t))
        and (row["n"] in ("Any", n))
        and (row["m"] in ("Any", m))
    )


def check_wildcard_ordering(rows: list[dict[str, str]], label: str) -> list[str]:
    """Flag any exact-match row that appears AFTER an earlier row that
    already matches it via a wildcard. Since lookup uses first-match-wins,
    such an exact row would be unreachable dead config."""
    errors = []
    for i, row in enumerate(rows):
        for j in range(i):
            earlier = rows[j]
            if _matches(earlier, row["t"], row["n"], row["m"]):
                if earlier != row:
                    errors.append(
                        f"{label} stage_groups[{i}] ({row['t']}/{row['n']}/{row['m']} -> "
                        f"'{row['stage']}') is unreachable: earlier wildcard row "
                        f"[{j}] ({earlier['t']}/{earlier['n']}/{earlier['m']} -> "
                        f"'{earlier['stage']}') already matches it first."
                    )
    return errors


def check_cross_reference(
    rows: list[dict[str, str]],
    t_codes: set[str],
    n_codes: set[str],
    m_codes: set[str],
    label: str,
) -> list[str]:
    """Flag any non-'Any' t/n/m value in stage_groups that isn't
    defined in the corresponding category list."""
    errors = []
    for i, row in enumerate(rows):
        if row["t"] != "Any" and row["t"] not in t_codes:
            errors.append(f"{label} stage_groups[{i}].t = '{row['t']}' not found in t_categories.")
        if row["n"] != "Any" and row["n"] not in n_codes:
            errors.append(f"{label} stage_groups[{i}].n = '{row['n']}' not found in n_categories.")
        if row["m"] != "Any" and row["m"] not in m_codes:
            errors.append(f"{label} stage_groups[{i}].m = '{row['m']}' not found in m_categories.")
    return errors


def lint_config(config: dict[str, Any]) -> list[str]:
    """Run all semantic checks across every edition/staging_type block
    in a cancer config and return a flat list of error strings."""
    all_errors: list[str] = []
    cancer_name = config.get("cancer_type", "UNKNOWN")

    for edition_name, edition in config.get("editions", {}).items():
        for staging_type_name, block in edition.get("staging_types", {}).items():
            label = f"[{cancer_name} / {edition_name} / {staging_type_name}]"
            rows = block["stage_groups"]
            t_codes = {c["code"] for c in block["t_categories"]}
            n_codes = {c["code"] for c in block["n_categories"]}
            m_codes = {c["code"] for c in block["m_categories"]}

            all_errors += check_any_case(rows, label)
            all_errors += check_cross_reference(rows, t_codes, n_codes, m_codes, label)
            all_errors += check_uniqueness(rows, label)
            all_errors += check_wildcard_ordering(rows, label)

    return all_errors


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "colorectal.json"
    config_path = DATA_DIR / target
    cfg = load_json(config_path)

    found_errors = lint_config(cfg)

    if found_errors:
        print(f"Lint FAILED for {target} ({len(found_errors)} issue(s)):\n")
        for err in found_errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print(f"Lint PASSED: {target} has no uniqueness, ordering, "
              "cross-reference, or wildcard-typo issues.")