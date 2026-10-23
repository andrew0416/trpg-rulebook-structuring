"""Exact, selected type identities shared by state validation and native matchups.

Core identities come from ch05:21.  More than two or zero effective types are
legal state projections; this module does not certify acquisition or creation.
The sheet's extra Glitch column is admitted only with its Polygon source.
Custom profile extensions require an explicit selected source, reason and
complete attack/defense matrix; a misspelled actor value never creates a type.
"""
CORE_TYPES = ("노말", "격투", "비행", "독", "땅", "바위", "벌레", "고스트", "강철",
              "불꽃", "물", "풀", "전기", "에스퍼", "얼음", "드래곤", "악", "페어리")
GLITCH_SOURCE = "supp-polygon/버그-타입"
GLITCH = "에러"  # input/db/nature-type.csv:77 explicitly associates this name with 글리치.
GLASS = "유리"
EXAMPLE_SOURCE = "ch11-running-the-game/이로치-포켓몬/이로치-포켓몬의-예시"


def _selected(rules, source):
    try:
        return rules._selected_rule(source) == source
    except (KeyError, ValueError):
        return False


def _defenders(rules):
    # Installed source definitions are already anchored and fingerprinted by
    # ordinary Rules/state loading. Do not rehash the primary PDF per matchup.
    return getattr(rules, "example_defender_types", {}) if _selected(rules, EXAMPLE_SOURCE) else {}


def source_defense_steps(rules, attack, defenses):
    """Exact source whole-chart result; None leaves ordinary composition alone.

    A defense-only source does not invent attacking Moves or unseen mixtures.
    Glass/Ground is explicitly a final table, including its Flying exception.
    """
    rows = _defenders(rules)
    names = set(defenses) & set(rows)
    if not names:
        return None
    if len(names) != 1 or attack not in CORE_TYPES:
        raise ValueError("no reviewed source matchup for these defensive types")
    name = next(iter(names)); row = rows[name]
    chart = row["defense_steps"] if set(defenses) == {name} else None
    for combination in row.get("combinations", []):
        if set(defenses) == set(combination["types"]):
            chart = combination["defense_steps"]
    if chart is None:
        raise ValueError("no reviewed source whole-chart for this type combination")
    return {"net_steps": chart[attack], "source": EXAMPLE_SOURCE}


def source_stab_types(rules, ordinary):
    values = list(ordinary)
    for name, row in _defenders(rules).items():
        if name in ordinary:
            values = list(dict.fromkeys(values + row.get("stab_types", [])))
    return values


def validate_attack(rules, attack):
    validate_types(rules, [attack], label="attacking type")
    if attack in _defenders(rules):
        raise ValueError("source defines defensive Glass typing and Rock STAB, not Glass attacks")


def _extensions(rules):
    rows = {}
    if _selected(rules, GLITCH_SOURCE):
        attack = dict.fromkeys(CORE_TYPES + (GLITCH,), 1.0)
        defense = dict(attack)
        attack.update({"전기": 2.0, "에스퍼": 2.0, "강철": 2.0, "고스트": .5, "독": .5})
        defense.update({"고스트": 2.0, "에스퍼": 2.0, "노말": .5, "전기": .5})
        rows[GLITCH] = {"source_id": GLITCH_SOURCE, "attack_vs": attack, "defense_vs": defense}
    custom = rules.ruleset.profile.get("type_extensions", {})
    if not isinstance(custom, dict):
        raise ValueError("type_extensions must be an explicit profile mapping")
    for name, row in custom.items():
        if not isinstance(name, str) or not name.strip() or name in CORE_TYPES + (GLITCH, "None", "스텔라"):
            raise ValueError("custom type identity conflicts with a reserved identity")
        if name in _defenders(rules):
            raise ValueError("custom type cannot replace a selected source type")
        if not isinstance(row, dict) or set(row) != {"source_id", "reason", "attack_vs", "defense_vs"}:
            raise ValueError("custom type needs source, reason and both matchup directions")
        if not isinstance(row["source_id"], str) or not _selected(rules, row["source_id"]):
            raise ValueError("custom type source is not selected")
        if not isinstance(row["reason"], str) or not row["reason"].strip():
            raise ValueError("custom type needs its explicit GM source interpretation")
        rows[name] = row
    universe = set(CORE_TYPES) | set(rows)
    for name, row in rows.items():
        for direction in ("attack_vs", "defense_vs"):
            matrix = row[direction]
            # Polygon defines interactions with the original universe only. A
            # custom extension owns its own explicit interaction with Glitch.
            expected = set(CORE_TYPES) | {GLITCH} if name == GLITCH else universe
            if not isinstance(matrix, dict) or set(matrix) != expected or any(
                    type(v) not in (int, float) or v not in (0, .5, 1, 2) for v in matrix.values()):
                raise ValueError("custom type requires a complete 0/.5/1/2 matchup matrix")
        if name != GLITCH:
            for other in rows:
                if other == GLITCH:
                    continue
                if row["attack_vs"][other] != rows[other]["defense_vs"][name]:
                    raise ValueError("custom attack and defense declarations disagree")
    return rows


def allowed_types(rules):
    return CORE_TYPES + tuple(_extensions(rules)) + tuple(_defenders(rules))


def attack_types(rules):
    """Selected attacking identities; source-only defensive types stay separate."""
    return CORE_TYPES + tuple(_extensions(rules))


def validate_types(rules, values, *, label="types"):
    if not isinstance(values, (list, tuple)) or any(not isinstance(v, str) or not v.strip() for v in values):
        raise ValueError(label + " must be an explicit sequence of type identities")
    if len(values) != len(set(values)):
        raise ValueError(label + " contains duplicate identities")
    # The common case has no optional lookup or whole-profile traversal.
    unknown = set(values) - set(CORE_TYPES)
    if unknown and not unknown <= set(_extensions(rules)) | set(_defenders(rules)):
        raise ValueError(label + " contains an unknown or unselected type: " + ", ".join(sorted(unknown)))
    return list(values)


def validate_actor(actor):
    validate_types(actor.r, actor.spec.get("types", []), label="permanent types")
    validate_types(actor.r, actor._types, label="runtime types")
    validate_types(actor.r, actor.types, label="effective types")
    row = actor.spec.get("state_grants", {}).get("type_sources")
    if row is not None:
        if not isinstance(row, dict) or set(row) != {"base", "sources", "visible"} or not isinstance(row["sources"], dict):
            raise ValueError("invalid saved type-source state")
        if row["base"] is not None:
            validate_types(actor.r, row["base"], label="type-source baseline")
        validate_types(actor.r, row["visible"], label="type-source visibility")
        value = list(actor.spec.get("types", []) if row["base"] is None else row["base"])
        for source, op in row["sources"].items():
            if not isinstance(source, str) or not source.strip() or not isinstance(op, dict) or set(op) != {"mode", "values", "fallback"} or op["mode"] not in ("set", "add", "remove"):
                raise ValueError("invalid saved type-source operation")
            validate_types(actor.r, op["values"], label="type-source values")
            if op["fallback"] is not None:
                validate_types(actor.r, [op["fallback"]], label="type-source fallback")
            if op["mode"] == "set":
                value = list(op["values"])
            elif op["mode"] == "add":
                value = list(dict.fromkeys(value + op["values"]))
            else:
                value = [v for v in value if v not in op["values"]]
                if not value and op["fallback"]:
                    value = [op["fallback"]]
        if value != row["visible"] or value != actor._types:
            raise ValueError("type sources disagree with their effective runtime state")
    return True


def matchup(rules, attack, defense):
    validate_attack(rules, attack)
    validate_types(rules, [defense], label="defending type")
    defenders = _defenders(rules)
    if defense in defenders:
        row = source_defense_steps(rules, attack, [defense])
        step = row["net_steps"]
        return 0 if step is None else 2 if step > 0 else .5 if step < 0 else 1
    if attack in CORE_TYPES and defense in CORE_TYPES:
        return rules.mech("combat/type-chart")["attack_vs_defense"][attack][defense]
    extra = _extensions(rules)
    if attack in extra and not (attack == GLITCH and defense not in CORE_TYPES + (GLITCH,)):
        return extra[attack]["attack_vs"][defense]
    return extra[defense]["defense_vs"][attack]
