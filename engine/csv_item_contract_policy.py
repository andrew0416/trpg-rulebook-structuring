"""Hash-pinned policy for the remaining CSV item/capability contracts.

The policy is deliberately shared by the physical-item, capability, form and
environment adapters.  A consumer cannot silently drift to a similarly named
core rule or to another homebrew row.
"""
from copy import deepcopy
from functools import lru_cache
import json
import os


POLICY_FILE = "csv-remaining-item-contract-policy.json"
EXPECTED_COUNT = 34


@lru_cache(maxsize=1)
def _item_status_index(content):
    status = json.loads(content.decode("utf-8"))
    return {row["clause_id"]: row for row in status.get("new_clauses", ())}


def registered_item_rows(rules, clause_ids):
    """Read live status bytes; share parsing only, never a freshness decision."""
    with open(os.path.join(rules.root, "data", "verification", "category2-item-table-status.json"), "rb") as handle:
        indexed = _item_status_index(handle.read())
    return {clause: deepcopy(indexed[clause]) for clause in clause_ids if clause in indexed}


def _path(rules):
    staged = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", POLICY_FILE))
    canonical = os.path.join(rules.root, "data", POLICY_FILE)
    return staged if os.path.exists(staged) else canonical


def policy(rules):
    import source_selection as SOURCES
    return deepcopy(SOURCES.verified_declaration(rules, "_csv_remaining_item_contract_policy", lambda: _policy(rules)))


def _policy(rules):
    # Cache the reviewed declaration only. An earlier successful read is not
    # permission to use changed source bytes or a changed registered locator.
    value = getattr(rules, "_csv_remaining_item_contract_policy", None)
    if value is None:
        with open(_path(rules), encoding="utf-8") as handle:
            value = json.load(handle)
    if value.get("schema_version") != 1 or value.get("contract") != "remaining CSV item physical, receipt, activation and capability contracts":
        raise ValueError("remaining CSV item policy schema changed")
    rows = value.get("rows")
    if not isinstance(rows, dict) or len(rows) != EXPECTED_COUNT or set(rows) != {row.get("clause_id") for row in rows.values()}:
        raise ValueError("remaining CSV item policy must contain the exact reviewed rows")
    inputs = {
        "input/db/inventory.csv": value.get("inventory_file_sha256"),
        "input/db/item-data.csv": value.get("item_data_file_sha256"),
    }
    from source_context import verified_source
    for relative, expected in inputs.items():
        verified_source(rules, {"file": relative, "sha256": expected}, label="remaining CSV item")
    indexed = registered_item_rows(rules, rows)
    for clause_id, row in rows.items():
        if row.get("clause_id") != clause_id or row.get("domain") not in {"physical", "food", "form", "capability", "environment"}:
            raise ValueError("remaining CSV item identity or domain changed")
        registered = indexed.get(clause_id)
        if registered is None or len(registered.get("source", ())) != 1:
            raise ValueError("remaining CSV item source row is missing: " + clause_id)
        source = registered["source"][0]
        expected = (row.get("source_file"), row.get("source_row"), row.get("source_columns"), row.get("source_row_sha256"))
        actual = (source.get("file"), source.get("row"), source.get("columns"), source.get("raw_cells_sha256"))
        if expected != actual:
            raise ValueError("remaining CSV item source provenance changed: " + clause_id)
        item_id = row.get("item_id")
        if item_id is not None:
            # The reviewed CSV set intentionally includes explicit homebrew
            # variants.  They exist in ``items_mech`` but are excluded from the
            # core ruleset's automatic variant selector.  The source-pinned
            # policy is the explicit selection receipt, so validate the exact
            # registry key rather than silently replacing it with a similarly
            # named core item. This does not admit that variant through the
            # core profile's automatic selector.
            registered_item = rules.items_mech.get(item_id)
            if not isinstance(registered_item, dict) or not registered_item.get("name"):
                raise ValueError("registered remaining CSV item changed: " + item_id)
    rules._csv_remaining_item_contract_policy = value
    # Public callers may edit their returned data without rewriting a later
    # consumer's reviewed declaration through the private parse cache.
    return value


def definition(rules, *, clause_id=None, kind=None, item_id=None):
    matches = []
    for row in policy(rules)["rows"].values():
        if clause_id is not None and row["clause_id"] != clause_id:
            continue
        if kind is not None and row["kind"] != kind:
            continue
        if item_id is not None and row.get("item_id") != item_id:
            continue
        matches.append(row)
    if len(matches) > 1:
        raise ValueError("remaining CSV item policy selector is ambiguous")
    return deepcopy(matches[0]) if matches else None


def clauses(rules):
    return frozenset(policy(rules)["rows"])
