"""PTK actor field authority and explicit permanent-state changes.

Entity identifiers and receipts are modeling conventions, not rulebook clauses.
A structurally valid imported sheet is not a certified category-6 creation.
Runtime additions (equipment, transformations, conditions) are never copied into
permanent statistics by this adapter.
"""
from copy import copy, deepcopy
import hashlib
import json
from uuid import uuid4
from math import isfinite

STATS = ("hp", "atk", "def", "spa", "spd", "spe")
DESCRIPTION_FIELDS = ("appearance", "personality", "background")
MEASUREMENT_FIELDS = ("height_m", "weight_kg")
BASE_FIELDS = frozenset(("name", "level", "stats", "types", "moves", "abilities",
                        "skills", "capabilities", "movement", "size", "weight_class",
                        *DESCRIPTION_FIELDS, *MEASUREMENT_FIELDS))


if __package__:
    from . import resolution_transaction as _FINGERPRINTS
else:
    import resolution_transaction as _FINGERPRINTS

def new_id(kind):
    return str(kind) + "/instance/" + uuid4().hex


def identity(spec):
    value = spec.get("id")
    if value is None:
        value = spec["id"] = new_id(spec.get("kind", "actor"))
    if not isinstance(value, str) or not value.strip():
        raise ValueError("entity identity must be nonempty text")
    return value


def integer(value, label, lower=None, upper=None):
    if type(value) is not int or (lower is not None and value < lower) or (upper is not None and value > upper):
        raise ValueError(label + " is outside its whole-number domain")
    return value


def stat_minimum(spec, stat):
    from actor_templates import has_soulless
    return 0 if stat == "hp" and has_soulless(spec) else 1


def validate_base(spec):
    if spec.get("kind") not in ("trainer", "pokemon"):
        raise ValueError("Combatant is a trainer or Pokemon; other objects use their own schema")
    if not isinstance(spec.get("name"), str) or not spec["name"].strip():
        raise ValueError("display name must be nonempty text")
    for field in DESCRIPTION_FIELDS:
        value = spec.get(field)
        if value is not None and not isinstance(value, str):
            raise ValueError(field + " must be narrative text or unknown")
    for field in MEASUREMENT_FIELDS:
        value = spec.get(field)
        if value is not None and (type(value) not in (int, float) or not isfinite(value) or value < 0):
            raise ValueError(field + " must be an observed nonnegative finite measurement or unknown")
    integer(spec.get("level"), "level", 1, 50 if spec["kind"] == "trainer" else 100)
    stats = spec.get("stats")
    if not isinstance(stats, dict) or set(stats) != set(STATS):
        raise ValueError("the six base combat statistics must be explicit")
    for key, value in stats.items():
        integer(value, key, stat_minimum(spec, key))
    initial_stages = spec.get("initial_stages", {})
    if not isinstance(initial_stages, dict) or not set(initial_stages) <= set(STATS[1:]):
        raise ValueError("initial stages contain only the five non-HP combat statistics")
    for value in initial_stages.values():
        integer(value, "initial combat stage", -6, 6)
    for field in ("types", "moves", "abilities", "capabilities"):
        values = spec.get(field, [])
        if not isinstance(values, (list, tuple)) or any(not isinstance(v, str) or not v.strip() for v in values):
            raise ValueError(field + " must contain explicit identifiers")
        if len(values) != len(set(values)):
            raise ValueError(field + " contains duplicate identifiers")
    for field in ("skills", "movement"):
        if not isinstance(spec.get(field, {}), dict):
            raise ValueError(field + " must be a named mapping")
    for value in spec.get("skills", {}).values():
        if not (isinstance(value, str) and value.strip()):
            integer(value, "skill rank", 1)
    for key,value in spec.get("movement", {}).items():
        if key in ('high_jump','long_jump'):
            from physical_limits import number
            number(value,'observed jump capability',minimum=0)
        else:integer(value, "movement capability", 0)
    if spec.get("weight_class") is not None:
        integer(spec["weight_class"], "weight class", 1, 7)


def validate_actor(c):
    validate_base(c.spec)
    import equipment_variant_contracts as EQUIPMENT_VARIANTS
    EQUIPMENT_VARIANTS.validate_actor(c)
    import hazard_state as HAZARDS
    HAZARDS.validate_actor(c)
    import stat_exchange_state as STAT_EXCHANGE
    STAT_EXCHANGE.validate_actor(c)
    import status_sets as STATUS_SETS
    STATUS_SETS.validate(c)
    import skill_modifiers as SKILL
    for skill in c.spec.get("skills", {}):
        SKILL.rank(c.r, c, skill)
    if c.spec.get("id") != c.entity_id:
        raise ValueError("entity identity changed; rename or evolve without replacing the identity")
    if c.name != c.spec["name"] or c.level != c.spec["level"]:
        raise ValueError("permanent scalar fields have competing authorities")
    if set(c.stats) != set(STATS):
        raise ValueError("runtime statistics do not describe the six combat statistics")
    for key, value in c.stats.items():
        integer(value, "runtime " + key, stat_minimum(c.spec, key))
    for key, value in c.stages.items():
        if key not in STATS[1:]:
            raise ValueError("HP has no combat stage")
        integer(value, "combat stage", -6, 6)
    if set(c.stages) != set(STATS[1:]):
        raise ValueError("five non-HP combat stages are required")
    integer(c.accuracy_stage, "accuracy stage", -6, 6)
    integer(c.evasion_mod, "extra evasion", -6, 6)
    integer(c.movement, "effective land movement", 0)
    integer(c.hp, "current HP")
    import temporary_hp as TEMP_HP
    TEMP_HP.validate(c)
    import food_effects as FOOD
    FOOD.validate_herbal(c)
    import effect_instances as INSTANCES
    INSTANCES.validate_actor(c)
    import bandages as BANDAGES
    BANDAGES.validate(c)
    import crafting_resources as CRAFTING_RESOURCES
    CRAFTING_RESOURCES.validate(c)
    import cultivation_state as CULTIVATION
    CULTIVATION.validate(c)
    import aura_state as AURA
    AURA.validate(c)
    import dream_state as DREAM
    DREAM.validate(c)
    import pester_balls as PESTER
    PESTER.validate_actor(c)
    import aura_pulse as PULSE
    PULSE.validate(c)
    import capability_products as PRODUCTS
    PRODUCTS.validate(c)
    import keystone_state as K
    K.validate(c)
    import telekinetic_load as TK
    TK.validate(c)
    import tk_mastery as TK_MASTERY
    TK_MASTERY.validate(c)
    integer(c.injuries, "injuries", 0)
    location(c.location)
    if type(c.dead) is not bool:
        raise ValueError("life/death must be explicit")
    if c.dead and not c.fainted:
        raise ValueError("a dead actor cannot be conscious")
    import action_points as AP
    AP.validate(c, source_required=False)
    import frequency as FREQUENCY
    FREQUENCY.validate(c)
    import condition_recovery as RECOVERY
    RECOVERY.validate(c)
    import rest_intervals as REST,injury_recovery as INJURY
    REST.validate_actor(c);INJURY.validate(c)
    import environmental_effects as ENVIRONMENT
    ENVIRONMENT.validate_respiration(c)
    import actor_templates as TEMPLATES
    TEMPLATES.validate(c)
    import acquired_features as ACQUIRED
    ACQUIRED.validate_class_slots(c)
    import iron_mind as IRON_MIND
    IRON_MIND.validate(c)
    import throwing_masteries as THROWING
    THROWING.validate(c)
    import wallrunner as WALL
    WALL.validate(c)
    import stamina as STAMINA
    STAMINA.validate(c)
    import pokemon_progression as PROGRESSION
    PROGRESSION.validate(c.spec)
    import lifetime_consumables as LIFETIME
    LIFETIME.validate(c)
    import item_maturation as MATURATION
    MATURATION.validate(c)
    import pokemon_entities as POKEMON_ENTITIES
    POKEMON_ENTITIES.validate_actor(c)
    import pokemon_skill_profiles as POKEMON_SKILLS
    POKEMON_SKILLS.validate_actor(c)
    import pokemon_skill_edges as POKE_EDGES
    POKE_EDGES.validate(c.r,c.spec)
    import pokemon_stat_edges as STAT_EDGES
    STAT_EDGES.validate(c.r,c.spec)
    import underdog_edges as UNDERDOG
    UNDERDOG.validate(c)
    import mixed_sweeper as MIXED
    MIXED.validate(c)
    import underdog_lessons as LESSONS
    LESSONS.validate(c)
    import ability_mastery as ABILITY_MASTERY
    ABILITY_MASTERY.validate(c)
    import advanced_connection as CONNECTION
    CONNECTION.validate(c)
    import capability_parameter_edges as PARAMETERS
    PARAMETERS.validate(c)
    import pokemon_capability_edges as CAP_EDGES
    CAP_EDGES.validate(c.r,c.spec)
    import pokemon_move_edges as MOVE_EDGES
    MOVE_EDGES.validate(c.r,c.spec)
    import ranged_struggle as RANGED
    RANGED.validate(c)
    import invisibility_edge as INVISIBILITY_EDGE
    INVISIBILITY_EDGE.validate(c)
    import move_state as MOVE_STATE
    MOVE_STATE.validate_actor(c)
    import type_state as TYPE_STATE
    TYPE_STATE.validate_actor(c)
    import type_sync as TYPE_SYNC
    TYPE_SYNC.validate_spec(c.r,c.spec)
    import example_species as EXAMPLES
    EXAMPLES.validate_spec(c.r,c.spec)
    import move_capabilities as MOVE_CAPABILITIES
    MOVE_CAPABILITIES.validate_choices(c)
    MOVE_CAPABILITIES.validate_totals(c)
    import body_state as BODY
    BODY.validate(c)
    import terrain_actions as TERRAIN
    TERRAIN.validate_history(c)
    import sound_state as SOUND
    SOUND.validate(c)
    import invisibility_state as INVISIBILITY
    INVISIBILITY.validate(c)
    import blender_state as BLENDER
    BLENDER.validate(c)
    import homebrew_state as HOME
    HOME.validate(c)
    import exhaust_moves as EXHAUST
    EXHAUST.validate(c)
    import gmax_moves as GMAX
    GMAX.validate_actor(c)
    import static_trainer_modifiers as STATIC_MODIFIERS
    STATIC_MODIFIERS.validate(c)
    import static_feature_state_grants as STATIC_FEATURES
    STATIC_FEATURES.validate(c)
    import class_passive_combat as CLASS_PASSIVE
    CLASS_PASSIVE.validate(c)
    import class_actor_state_reactions as CLASS_REACTIONS
    CLASS_REACTIONS.validate(c)
    import class_actor_state_actions as CLASS_STATE_ACTIONS
    CLASS_STATE_ACTIONS.validate(c)
    import scene_feature_ability_grants as SCENE_FEATURE_ABILITIES
    SCENE_FEATURE_ABILITIES.validate(c)
    import priority_limited as PRIORITY_LIMITED
    PRIORITY_LIMITED.validate(c)
    import setup_move_state as SETUP_MOVE
    SETUP_MOVE.validate_actor(c)
    return True


def base_patch(c, changes, *, reason, source="gm/state", request_id=None, expected_revision=None):
    """Validate a permanent edit before applying it; preserve runtime additions.

    This is an explicit GM/import/growth adapter. It does not award growth rights
    or infer legal acquisition merely because the proposed fields are typed.
    """
    if not isinstance(changes, dict) or not changes or not set(changes) <= BASE_FIELDS:
        raise ValueError("an explicit patch of supported permanent fields is required")
    if not isinstance(reason, str) or not reason.strip() or not isinstance(source, str) or not source.strip():
        raise ValueError("state change requires a reason and source")
    if c.spec.get("id") != c.entity_id:
        raise ValueError("entity identity mismatch")
    import class_passive_combat as PASSIVE,type_ace as TA
    bound=(PASSIVE._state(c) or {}).get('sustains',{}).get(TA.uid('Iron Grit'))
    if bound and 'stats' in changes and changes['stats']['def']<c.spec['stats']['def']:raise ValueError('Iron Grit prevents lowering the actual Defense Stat')
    payload = {"entity_id": c.entity_id, "changes": changes, "reason": reason, "source": source}
    digest = _FINGERPRINTS.json_fingerprint(payload, sort_keys=True, compact=False, allow_nan=False)
    receipts = getattr(c, "_state_receipts", {})
    if request_id is not None:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request identity must be nonempty text")
        if request_id in receipts:
            if receipts[request_id]["payload_sha256"] != digest:
                raise ValueError("state change request identity was reused with different input")
            return deepcopy(receipts[request_id])
    revision = getattr(c, "_state_revision", 0)
    if expected_revision is not None and expected_revision != revision:
        raise ValueError("permanent state revision changed")
    proposed = __import__('world_entities').spec_copy(c)
    proposed.update(deepcopy(changes))
    validate_base(proposed)
    import iron_mind as IRON_MIND
    probe=copy(c);probe.spec=proposed
    IRON_MIND.validate(probe)
    import throwing_masteries as THROWING
    THROWING.validate(probe)
    import wallrunner as WALL
    WALL.validate(probe)
    import stamina as STAMINA
    STAMINA.validate(probe)
    import actor_templates as TEMPLATES
    TEMPLATES.validate_soulless_default(c.r,proposed)
    derived_changes = {}
    if c.kind == "pokemon" and ("level" in changes or "stats" in changes):
        import pokemon_capability_edges as CAP_EDGES
        CAP_EDGES.reconcile_spec(c.r,proposed,reason=reason)
        import pokemon_move_edges as MOVE_EDGES
        MOVE_EDGES.reconcile_spec(c.r,proposed,reason=reason)
        import ranged_struggle as RANGED
        probe=copy(c);probe.spec=proposed
        RANGED.reconcile(probe,reason=reason)
        import tk_mastery as TK_MASTERY
        TK_MASTERY.reconcile(probe,reason=reason)
        import capability_parameter_edges as PARAMETERS
        PARAMETERS.reconcile(probe,reason=reason)
        for field in ('tutor_points','learned_poke_edges'):
            if field in proposed and proposed[field]!=c.spec.get(field):derived_changes[field]=deepcopy(proposed[field])
    if c.kind=='pokemon' and set(changes)&{'level','stats','size','movement'}:
        probe=copy(c);probe.spec=proposed
        __import__('pokemon_capability_edges').reconcile_named(probe,reason=reason)
        for field in ('tutor_points','learned_poke_edges'):
            if field in proposed and proposed[field]!=c.spec.get(field):derived_changes[field]=deepcopy(proposed[field])
    if c.kind == "pokemon" and "skills" in changes:
        import pokemon_skill_edges as POKE_EDGES
        POKE_EDGES.refund_excess(c.r,proposed,reason=reason)
        for field in ('skills','tutor_points','learned_poke_edges'):
            if field in proposed and proposed[field]!=c.spec.get(field):derived_changes[field]=deepcopy(proposed[field])
    if c.kind == "pokemon" and ("level" in changes or "stats" in changes):
        import move_state as MOVE_STATE
        proposed = MOVE_STATE.prepare_observation(c.r, c.spec, proposed, reason=reason)
        for field in (MOVE_STATE.HISTORY, "move_learning"):
            if field in proposed and proposed[field] != c.spec.get(field):
                derived_changes[field] = deepcopy(proposed[field])
    if "skills" in changes:
        import skill_modifiers as SKILL
        probe = copy(c)
        probe.spec = proposed
        for skill in proposed["skills"]:
            SKILL.rank(c.r, probe, skill)
    if 'types' in changes and 'type_sync' in c.spec:
        import type_sync as TYPE_SYNC
        if source!=TYPE_SYNC.SOURCE and changes['types']!=c.spec.get('types'):raise ValueError('permanent Type Sync changes require the complete reviewed transition')
    before = {key: deepcopy(c.spec.get(key)) for key in changes}
    derived_before = {key: deepcopy(c.spec.get(key)) for key in derived_changes}
    runtime = {}
    import state_grants as GRANTS
    if "stats" in changes:
        # Explicit additive baseline replacement; a transform is not additive.
        import stat_exchange_state as STAT_EXCHANGE
        if STAT_EXCHANGE.active(c) or getattr(c, "_nonadditive_stats", None) or getattr(c, "custom_conditions", {}).get("transformed") or getattr(c, "form", None) == "transformed":
            raise ValueError("exchanged or transformed statistics need their source-specific baseline adapter")
        import state_grants as GRANTS
        runtime["stats"] = GRANTS.prepare_stat_baseline(c, proposed["stats"])
    if "movement" in changes or "skills" in changes:
        probe = copy(c)
        probe.spec = proposed
        if proposed.get("movement_basis") == "trainer_base":
            import trainer_capabilities as TRAINER
            if TRAINER.DERIVED.intersection(proposed.get("movement", {})):
                raise ValueError("derived trainer fields must not also be supplied as current values")
            # Live ranks recalculate the base; runtime source deltas stay separate.
            integer(probe.movement, "effective land movement", 0)
        elif "movement" in changes:
            runtime["movement"] = c.movement + proposed["movement"].get("land", 4) - c.spec.get("movement", {}).get("land", 4)
            integer(runtime["movement"], "effective land movement", 0)
    if 'movement' in changes:
        import move_capabilities as MOVE_CAPABILITIES
        probe=copy(c);probe.spec=proposed
        if 'movement' in runtime:probe._movement_value=runtime['movement']
        derived_changes[MOVE_CAPABILITIES.TOTALS_KEY]=MOVE_CAPABILITIES.observe_totals(probe)
    if "types" in changes:
        import type_state as TYPE_STATE
        TYPE_STATE.validate_types(c.r, proposed["types"], label="proposed permanent types")
        runtime["_types"] = GRANTS.prepare_type_baseline(c, proposed["types"])
        TYPE_STATE.validate_types(c.r, runtime["_types"], label="proposed effective types")
    if "weight_class" in changes:
        runtime["_weight_class"] = GRANTS.prepare_weight_baseline(c, proposed["weight_class"])
    # Ordered set union retains temporary grants; permanent removals are handled
    # by the grant registry once it is installed, never by copying effective data.
    for field in ("moves", "abilities"):
        if field in changes:
            raise ValueError("permanent acquisition uses state_grants.set_baseline")
    for key, value in {**changes, **derived_changes}.items():
        c.spec[key] = deepcopy(value)
    for key, value in runtime.items():
        setattr(c, key, value)
    if "stats" in changes:
        GRANTS.commit_stat_baseline(c)
    if "level" in changes:
        import static_trainer_modifiers as STATIC_MODIFIERS
        STATIC_MODIFIERS.refresh_level(c)
    if "types" in changes:
        GRANTS.commit_type_baseline(c)
    if "weight_class" in changes:
        GRANTS.commit_weight_baseline(c)
    c._state_revision = revision + 1
    receipt = {"entity_id": c.entity_id, "request_id": request_id, "source": source,
               "reason": reason, "revision": c._state_revision, "before": before,
               "after": deepcopy(changes), "payload_sha256": digest,
               "creation_legality_certified": False}
    if derived_changes:
        receipt["derived_before"] = derived_before
        receipt["derived_after"] = deepcopy(derived_changes)
    if request_id is not None:
        c.__dict__.setdefault("_state_receipts", {})[request_id] = deepcopy(receipt)
    return receipt


def location(value):
    if not isinstance(value, dict) or value.get("kind") not in ("grid", "abstract", "unknown"):
        raise ValueError("location must explicitly be grid, abstract, or unknown")
    result = deepcopy(value)
    if result["kind"] == "grid":
        cell = result.get("cell")
        if not isinstance(cell, (list, tuple)) or len(cell) != 2 or any(type(v) is not int for v in cell):
            raise ValueError("a grid cell is a pair of whole coordinates")
        result["cell"] = tuple(cell)
    elif result["kind"] == "abstract":
        if not isinstance(result.get("place_id"), str) or not result["place_id"].strip():
            raise ValueError("abstract location needs an explicit place identity")
    return result


def record_stat_exchange(c, *, channels, effect, before):
    """Preserve a nonadditive producer so permanent edits cannot treat it as +N.

    Resolving growth during this exchange needs the exchange/growth rule policy;
    an arbitrary permanent delta is not an implementation of that policy.
    """
    c.__dict__.setdefault("_nonadditive_stats", []).append({
        "channels": list(channels), "effect": deepcopy(effect),
        "before": deepcopy(before), "after": {k: c.stats[k] for k in channels},
        "source": effect.get("_rule_id") or effect.get("_ability") or "legacy/stat_exchange",
        "growth_policy": "unresolved_category6_dependency"})

