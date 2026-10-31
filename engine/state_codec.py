"""Versioned, data-only current-gameplay saves for the native Engine.

No pickle, dynamic import, eval, property reads or callback reconstruction.
The graph retains actor identity and mutable aliases; each load creates a new
Engine. In-memory GM checkpoint history is outside the declared save scope.
A save is a state record, not proof of category-6 creation legality or an
execution-authority certificate. Common-check observations can be saved; live
authentication must be installed afresh before continuing those checks.
"""
from copy import copy
from dataclasses import fields
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re

FORMAT = 'ptk-engine-state'
VERSION = 1
MAX_NODES = 200000


if __package__:
    from . import resolution_transaction as _FINGERPRINTS
else:
    import resolution_transaction as _FINGERPRINTS

class StateCodecError(ValueError):
    pass


# Shared snapshot fields are gameplay fields, not an invitation to deserialize
# arbitrary engine attributes. New native fields must explicitly join this set.
EXTRA_ENGINE_FIELDS = frozenset(('seed', 'log_lines', 'effect_stats', 'gm_prompts',
    '_root_common_epoch', '_league_dispatch', '_inflictor', 'random_db_flag',
    '_state_changes', '_state_receipts', '_state_revision', 'state_changes',
    'state_receipts', 'state_revision', 'state_import_provenance',
    '_state_codec_authentication', '_world_facts', '_world_relation_receipts',
    '_root_common_saved'))
ENGINE_SPECIAL = frozenset(('r', 'rulings', 'gm', 'grid', 'rng'))
RULING_FIELDS = frozenset(('formulas', 'mech', 'effects', 'situational', 'answers',
    'hooks', 'provider', 'log', '_mech_cache'))
GRID_REQUIRED_FIELDS = frozenset(('w', 'h', 'blocking', 'rough', 'slow', 'walls'))
GRID_OPTIONAL_FIELDS = frozenset(('terrain_types', 'terrain_observations', 'base_terrain', '_tunnel_map_id', 'nicolette_gym'))
GRID_FIELDS = GRID_REQUIRED_FIELDS | GRID_OPTIONAL_FIELDS
AUTH_NOTICE = 'reauthentication_required; prior live bindings and tickets are not restored'


def _fail(message):
    raise StateCodecError(message)


def _types():
    import engine as native
    import sys
    names = ('Engine', 'Combatant', 'Rules')
    if all(name in vars(native) for name in names):
        from engine import Engine, Combatant, Rules
        qualified = sys.modules.get('engine.engine')
        if qualified is not None and any(vars(qualified).get(name) is not vars(native)[name] for name in names):
            _fail('conflicting native engine module identities')
    else:
        # A real namespace package has no bare API; preserve that import mode.
        from engine.engine import Engine, Combatant, Rules
    from gm_state import GMState
    from grid import Grid
    from rulings import Rulings
    return Engine, Combatant, Rules, GMState, Grid, Rulings


def _data_types():
    # Fixed, callback-free native observations; payloads never select a module.
    from common_checks import SkillRoll, AdjustedSkillRoll, CheckResult, ExtendedResult, PendingDecision, ActionOutcome
    from skill_feature_actions import SkillEvent
    from researcher_features import PokemonSkillRoll
    from contest_features import ContentSkillRoll
    from common_action_checks import ExtendedAction
    from league_agenda import Agenda, Participant, Record
    from effect_contracts import Outcome, Issue
    from maneuver_grants import Policy, ManeuverPending, ManeuverResult
    from root_resolution import Predicate
    result = {cls.__name__: cls for cls in (SkillRoll, AdjustedSkillRoll, CheckResult,
            ExtendedResult, PendingDecision, ActionOutcome, SkillEvent, PokemonSkillRoll,
            ContentSkillRoll, ExtendedAction, Agenda, Participant, Record, ManeuverPending, ManeuverResult)}
    result.update(EffectOutcome=Outcome, EffectIssue=Issue, ManeuverPolicy=Policy, RootPredicate=Predicate)
    return result


def _enum_types():
    from league_agenda import Phase, Role
    from root_resolution import Truth
    return {'LeaguePhase': Phase, 'LeagueRole': Role, 'RootTruth': Truth}


def _batch_type():
    from effect_contracts import BatchResult
    return BatchResult


def native_data_types():
    """Fixed callback-free observation classes shared with state graph walkers."""
    return tuple(_data_types().values())


def native_batch_type():
    """Fixed tuple-compatible native effect batch class for graph walkers."""
    return _batch_type()


def _validate_observation(value):
    cls = type(value)
    allowed = {field.name for field in fields(cls)}
    if set(vars(value)) != allowed:
        _fail('observation fields disagree with fixed data type')
    try:
        checked = cls(**vars(value))
        if checked != value:
            _fail('observation is not canonical')
        if cls.__name__ == 'SkillEvent':
            if type(value.actor) is not _types()[1] or type(value.skill) is not str or type(value.request) is not tuple or type(value.prepared) is not tuple or type(value.first) not in tuple(_data_types()[k] for k in ('SkillRoll', 'AdjustedSkillRoll', 'PokemonSkillRoll', 'ContentSkillRoll')) or value.state not in ('observed', 'pending', 'final'):
                _fail('invalid observed native skill event')
        if cls.__name__ in ('Participant', 'Record', 'Agenda'):
            import league_agenda as A
            if cls is A.Participant:
                if any(type(v) is not str or not v for v in (value.actor_id, value.player_id)) or type(value.role) is not A.Role or type(value.initiative) is not int or type(value.able) is not bool:
                    _fail('invalid saved League participant')
            elif cls is A.Record:
                if type(value.phase) is not A.Phase or any(type(v) is not str or not v for v in (value.actor_id, value.event_id, value.evidence_ref, value.disposition)):
                    _fail('invalid saved League record')
            else:
                if type(value.participants) is not tuple or type(value.records) is not tuple or type(value.pending) is not tuple or type(value.phase) is not A.Phase or type(value.cursor) is not int:
                    _fail('invalid saved League agenda fields')
                reconstructed = A.create(value.round_id, value.participants)
                for record in value.records:
                    fn = A.declare if record.phase is A.Phase.DECLARE else A.acknowledge
                    reconstructed = fn(reconstructed, record.actor_id, record.event_id,
                        record.evidence_ref, disposition=record.disposition)
                if any(getattr(reconstructed,k) != getattr(value,k) for k in ('phase','cursor','declaration_order','trainer_order','pokemon_order')) or value.pending[:len(reconstructed.pending)] != reconstructed.pending:
                    _fail('saved League agenda disagrees with its progress records')
        if cls.__name__ == 'CheckResult':
            if any(type(getattr(value, k)) is not int for k in ('total', 'dc', 'margin')) or type(value.passed) is not bool or value.margin != value.total-value.dc or value.passed != (value.total >= value.dc):
                _fail('inconsistent observed check result')
    except (TypeError, ValueError) as exc:
        raise StateCodecError('invalid fixed observation: ' + str(exc)) from exc


def _engine_fields():
    from gm_state import ENGINE_FIELDS
    return frozenset(ENGINE_FIELDS) | EXTRA_ENGINE_FIELDS | ENGINE_SPECIAL


def _plain(value):
    """Internal hash data; already canonical containers may be shared read-only."""
    kind = type(value)
    if value is None or kind in (str, bool, int):
        return value
    if kind is float:
        if not math.isfinite(value):
            _fail('nonfinite value in selected rule data')
        return value
    if kind is list:
        result = None
        for index, item in enumerate(value):
            if item is None or type(item) in (str, bool, int):
                continue
            normalized = _plain(item)
            if normalized is not item:
                if result is None:
                    result = value[:]
                result[index] = normalized
        return value if result is None else result
    if kind is tuple:
        return [_plain(v) for v in value]
    if kind in (set, frozenset):
        return {'set': sorted((_plain(v) for v in value), key=lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False))}
    if kind is dict:
        # json_fingerprint sorts every dictionary key when hashing the result.
        result = None
        for key, item in value.items():
            if type(key) is not str:
                _fail('selected rule fingerprint requires text keys')
            if item is None or type(item) in (str, bool, int):
                continue
            normalized = _plain(item)
            if normalized is not item:
                if result is None:
                    result = dict(value)
                result[key] = normalized
        return value if result is None else result
    _fail('unsupported selected rule data: ' + kind.__name__)


def _corpus_paths(root):
    """Enumerate live rule files without descending into excluded audit records."""
    for directory in ('input', 'data', 'output/entities'):
        folder = root / directory
        if not folder.is_dir():
            _fail('rule corpus directory missing: ' + directory)
        paths = []
        for parent, subdirs, files in os.walk(folder):
            subdirs[:] = [name for name in subdirs if name != 'verification']
            paths.extend(Path(parent) / name for name in files)
        for path in sorted(paths):
            if not path.is_file() or 'verification' in path.relative_to(root).parts:
                continue
            if directory != 'input' and path.suffix != '.json':
                continue
            yield path


_CORPUS_DIGESTS = {}


def _corpus_digest(path):
    # The digest of unchanged bytes is reused; any change of size, modification
    # time or file identity re-reads and re-hashes the file.
    stat = path.stat()
    key = str(path)
    cached = _CORPUS_DIGESTS.get(key)
    signature = (stat.st_size, stat.st_mtime_ns, stat.st_ino, stat.st_dev)
    if cached is not None and cached[0] == signature:
        return cached[1]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    _CORPUS_DIGESTS[key] = (signature, digest)
    return digest


_FINGERPRINT_JSON = {'sort_keys': True, 'ensure_ascii': False, 'allow_nan': False, 'separators': (',', ':')}
_CACHED_PIECE_MIN = 32768


def _piece(value):
    return json.dumps(_plain(value), **_FINGERPRINT_JSON)


def _selected_digest(rules, manifest, policy):
    """sha256 of exactly the compact JSON json_fingerprint produces for
    {'files': manifest, 'selected': policy}, assembled from per-attribute pieces.

    A piece is reused while the attribute still holds the same object. A reassigned
    attribute misses the cache; an in-place change is declared with Rules.touch().
    PTK_FINGERPRINT_FULL=1 recomputes every piece (the self-check path)."""
    cache = None if os.environ.get('PTK_FINGERPRINT_FULL') else rules.__dict__.setdefault('_fingerprint_cache', {})
    parts = []
    for key in sorted(policy):
        if type(key) is not str:
            _fail('selected rule fingerprint requires text keys')
        value = policy[key]
        entry = cache.get(key) if cache is not None else None
        if key == 'selection' and type(value) is dict:
            identity = tuple((k, id(v)) for k, v in sorted(value.items()))
            if entry is not None and entry[0] == identity:
                text = entry[2]
            else:
                text = _piece(value)
                if cache is not None:
                    cache[key] = (identity, tuple(value.values()), text)
        else:
            if entry is not None and entry[0] is value:
                text = entry[1]
            else:
                text = _piece(value)
                # Only large tables are cached; a small policy is re-read on every call, so an
                # in-place edit of it is still detected without a declaration.
                if cache is not None and len(text) >= _CACHED_PIECE_MIN:
                    cache[key] = (value, text)
        if cache is not None and os.environ.get('PTK_FINGERPRINT_CHECK') and text != _piece(value):
            _fail('fingerprint cache stale for ' + key + ' (in-place edit without Rules.touch)')
        parts.append(json.dumps(key, **_FINGERPRINT_JSON) + ':' + text)
    document = '{"files":' + json.dumps(manifest, **_FINGERPRINT_JSON) + ',"selected":{' + ','.join(parts) + '}}'
    return hashlib.sha256(document.encode()).hexdigest()


def rules_fingerprint(rules):
    """Hash selected in-memory policy and the actual saved source/data corpus."""
    root = Path(rules.root)
    manifest = [(path.relative_to(root).as_posix(), _corpus_digest(path))
                for path in _corpus_paths(root)]
    policy = {k: v for k, v in vars(rules).items()
              if k not in ('root', 'rulings', 'ruleset', 'selection', '_source_context_reads', '_coordinator_contest_reader', '_runtime_weapon_declarations', '_fingerprint_cache')}
    # Loading a policy cache is not a rules change. Use its saved definition
    # when cold and its actual contents when warm, preserving override checks.
    # Keep this registry explicit: arbitrary private rule state is still hashed.
    caches = {
        '_juggler_contract': ('juggler-source-contract.json', None),
        'capability_policy': ('capability-policy.json', None),
        '_blessing_effect_policy': ('blessing-effect-policy.json', None),
        '_coat_effect_policy': ('coat-effect-policy.json', None),
        '_food_buff_policy': ('food-buff-policy.json', None),
        '_event_effect_policy': ('event-effect-policy.json', None),
        '_item_container_policy': ('item-container-policy.json', None),
        '_item_maturation_policy': ('item-maturation-policy.json', 'juicer'),
        '_lifetime_consumable_policies': ('lifetime-consumable-policy.json', 'rules'),
        '_move_accuracy_policy': ('move-accuracy-policy.json', None),
        '_move_capability_policy': ('move-capability-policy.json', None),
        '_poke_edge_variants': ('poke-edge-variants.json', 'entries'),
        '_roll_effect_policy': ('roll-effect-policy.json', None),
        '_temporary_hp_policy': ('temporary-hp-policy.json', None),
        '_weapon_policy': ('weapon-policy.json', None),
        '_gmax_move_policy': ('gmax-move-policy.json', None),
        '_setup_move_state_policy': ('setup-move-state-policy.json', None),
        '_ability_native_actions_policy': ('ability-native-actions-policy.json', None),
        '_class_passive_combat_policy': ('class-passive-combat-policy.json', None),
        '_class_actor_state_action_policy': ('class-actor-state-actions-policy.json', None),
        '_stellar_tera_blast_policy': ('stellar-tera-blast-policy.json', None),
        '_declarative_move_contract_policy': ('declarative-move-contract-policy.json', None),
        '_csv_remaining_item_contract_policy': ('csv-remaining-item-contract-policy.json', None),
        '_equipment_variant_contract_policy': ('equipment-variant-contract-policy.json', None),
        '_optional_physical_equipment_policy': ('optional-physical-equipment-policy.json', None),
        '_move_type_choice_policy': ('move-type-choice-policy.json', None),
        '_static_feature_state_policy': ('static-feature-state-grants-policy.json', None),
        '_survivalist_csv_policy': ('survivalist-csv-policy.json', None),
        '_scene_feature_ability_grant_policy': ('scene-feature-ability-grant-policy.json', None),
    }
    def saved_policy(filename, member=None):
        try:
            value = json.loads((root/'data'/filename).read_text(encoding='utf-8'))
            return value if member is None else value[member]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            _fail('selected rule/profile/source fingerprint mismatch: saved rule policy unavailable: ' + filename + ': ' + str(exc))
    # This later cache was absent from older cold fingerprints. Drop only an
    # exact redundant copy of the corpus policy; overrides remain fingerprinted.
    static_name='_static_trainer_modifier_policy'
    if static_name in policy and policy[static_name]==saved_policy('static-trainer-modifier-policy.json'):
        policy.pop(static_name)
    lesson_name='_feature_ability_lessons'
    ranked_name='_ranked_class_move_tables'
    if ranked_name in policy and policy[ranked_name]==saved_policy('class-ranked-move-tables.json','rules'):
        policy.pop(ranked_name)
    redundant = {
        '_class_actor_state_reaction_policy': ('class-actor-state-reactions-policy.json', None),
        '_native_class_actor_state_reaction_policy': ('native-class-reaction-policy.json', None),
        '_optional_state_effect_contract_policy': ('optional-state-effect-contract-policy.json', None),
        '_optional_weapon_framework_policy': ('optional-weapon-framework-policy.json', None),
        '_survivalist_class_definitions': ('survivalist-definitions.json', None),
        '_juggler_contract': ('juggler-source-contract.json', None),
    }
    for name, (filename, member) in redundant.items():
        if name in policy and policy[name] == saved_policy(filename, member):
            policy.pop(name)
    # Recompute derived indexes with their existing readers on an isolated copy.
    # Only an exact redundant result may disappear; authored definitions stay hashed.
    def uncached(*names):
        checked = copy(rules)
        checked._source_context_reads = {}
        for name in names:
            vars(checked).pop(name, None)
        return checked
    def derived(compute, label):
        # A derived index is recomputed from the selected root's files. A root that
        # cannot supply them is a source mismatch, exactly like a missing saved policy.
        try:
            return compute()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            _fail('selected rule/profile/source fingerprint mismatch: derived ' + label + ' unavailable: ' + str(exc))
    weather_name = '_native_weather_action_sources'
    if weather_name in policy:
        import ability_native_actions as NATIVE_ACTIONS
        expected_weather = derived(lambda: NATIVE_ACTIONS.weather_action_sources(uncached(weather_name)), 'weather action sources')
        if (json.dumps(_plain(policy[weather_name]), sort_keys=True, ensure_ascii=False, allow_nan=False)
                == json.dumps(_plain(expected_weather), sort_keys=True, ensure_ascii=False, allow_nan=False)):
            policy.pop(weather_name)
    hb_name = '_survivalist_hb_definitions'
    if hb_name in policy:
        import survivalist_class as SURVIVAL
        expected_hb = derived(lambda: SURVIVAL.hb_definitions(uncached(hb_name)), 'Survivalist HB definitions')
        if (json.dumps(_plain(policy[hb_name]), sort_keys=True, ensure_ascii=False, allow_nan=False)
                == json.dumps(_plain(expected_hb), sort_keys=True, ensure_ascii=False, allow_nan=False)):
            policy.pop(hb_name)
    passive_name = '_weather_passive_checked'
    if type(policy.get(passive_name)) is set:
        import weather_passive_benefits as WEATHER_PASSIVES
        if policy[passive_name] <= WEATHER_PASSIVES.SOURCES.keys():
            checked = uncached(passive_name)
            for source in policy[passive_name]:
                WEATHER_PASSIVES.definition(checked, source)
            policy.pop(passive_name)
    if lesson_name in policy:
        import feature_ability_lessons as LESSONS
        saved_policy('feature-ability-lessons.json', 'rules')
        expected_lessons = LESSONS._policy(uncached(lesson_name))
        if (policy[lesson_name] == expected_lessons
                and LESSONS._same(_plain(policy[lesson_name]), _plain(expected_lessons))):
            policy.pop(lesson_name)
    edge_name='_poke_edge_variants'
    if edge_name in policy:
        import poke_edge_variants as EDGES
        saved_policy('poke-edge-variants.json', 'entries')
        checked = uncached(edge_name, '_poke_edge_variants_identity')
        expected_edges = EDGES.catalog(checked)
        if (policy.get('_poke_edge_variants_identity') == checked._poke_edge_variants_identity
                and policy[edge_name] == expected_edges
                and json.dumps(_plain(policy[edge_name]), sort_keys=True, ensure_ascii=False, allow_nan=False)
                    == json.dumps(_plain(expected_edges), sort_keys=True, ensure_ascii=False, allow_nan=False)):
            policy.pop(edge_name)  # The existing cold baseline below uses saved entries.
        else:
            # A manual raw list must not masquerade as the absent-cache baseline.
            policy[edge_name] = {'unverified_runtime_catalog': policy[edge_name]}
    if '_source_catalog' in policy or '_source_catalog_identity' in policy:
        import source_catalog as CATALOG
        checked = uncached('_source_catalog', '_source_catalog_identity')
        expected_catalog = CATALOG._document(checked)
        if (policy.get('_source_catalog') == expected_catalog
                and policy.get('_source_catalog_identity') == checked._source_catalog_identity):
            policy.pop('_source_catalog')
            policy.pop('_source_catalog_identity')
    if '_equipment_variant_punch_moves' in policy:
        import equipment_variant_contracts as EQUIPMENT
        checked = uncached('_equipment_variant_punch_moves')
        if policy['_equipment_variant_punch_moves'] == EQUIPMENT._punch_moves(checked):
            policy.pop('_equipment_variant_punch_moves')
    skill_reads = policy.get('_skill_csv_sources')
    if type(skill_reads) is set:
        import skill_modifiers as SKILLS
        records = { (source['id'], source['sha256']): row
            for section in ('edges', 'rank_effects')
            for row in rules.skill_policy.get(section, {}).values()
            if (source := row.get('equivalent_csv_source')) is not None }
        if skill_reads <= records.keys():
            checked = uncached('_skill_csv_sources')
            for identity in skill_reads:
                SKILLS.validate_csv_source(checked, records[identity], [identity[0]])
            policy.pop('_skill_csv_sources')
    custom=saved_policy('custom-condition-policy.json')
    if policy.get('_custom_condition_policy')==custom:
        policy.pop('_custom_condition_policy')
    verified=policy.get('_custom_condition_source_records')
    if type(verified) is set:
        expected={tuple(row['source_record'][key] for key in ('file','record','sha256'))
                  for row in custom['sources'].values() if row.get('source_record')}
        valid=verified<=expected
        if valid:
            import csv
            records={}
            for filename,number,digest in verified:
                if filename not in records:
                    with (root/filename).open(encoding='utf-8-sig',newline='') as stream:
                        records[filename]=list(csv.reader(stream))
                actual=_FINGERPRINTS.json_fingerprint(records[filename][number-1], sort_keys=False, compact=True, allow_nan=True)
                if actual!=digest:valid=False;break
        if valid:policy.pop('_custom_condition_source_records')
    for name, (filename, member) in caches.items():
        if policy.get(name) is None:
            policy[name] = saved_policy(filename, member)
    if policy.get('_ability_native_actions_catalog') is None:
        native_sources = saved_policy('ability-native-actions-policy.json')['sources']
        catalog = json.loads((root/'output/entities/abilities.json').read_text(encoding='utf-8'))
        policy['_ability_native_actions_catalog'] = {
            entry['id']: entry for entry in catalog if entry['id'] in native_sources}
    policy.setdefault('_poke_edge_variants_identity',
                      (str(root.resolve()), hashlib.sha256((root/'data/poke-edge-variants.json').read_bytes()).hexdigest()))
    training=saved_policy('training-source-policies.json')
    training_identity=(str(root.resolve()),hashlib.sha256((root/'data/training-source-policies.json').read_bytes()).hexdigest())
    for name,provider in (('_groomer_csv_policy','groomer'),('_beast_csv_policy','beast_master')):
        if policy.get(name) is None:policy[name]=training[provider]['csv_target_limit']
        policy.setdefault(name+'_identity',training_identity)
    cultivation = policy.get('_cultivation_state_policies')
    if cultivation is None:
        cultivation = {}
    if not isinstance(cultivation, dict):
        _fail('cultivation policy cache must be a mapping')
    policy['_cultivation_state_policies'] = {
        name: cultivation[name] if name in cultivation else saved_policy(name+'-policy.json')
        for name in set(cultivation) | {'cultivation', 'planter'}
    }
    selection = vars(rules.selection)
    policy['selected_profile'] = vars(rules.ruleset)
    policy['selection'] = {k: v for k, v in selection.items() if k not in ('filter', 'dependencies')}
    digest = _selected_digest(rules, manifest, policy)
    result={'sha256': digest, 'profile': rules.ruleset.name, 'file_count': len(manifest)}
    generated=__import__('weapon_actions').generated_declarations(rules)
    if generated:result['generated_weapons']=generated
    return result


def _field_names(attrs, allowed, label):
    if type(attrs) is not dict or any(type(k) is not str or k.startswith('__') for k in attrs):
        _fail(label + ' attributes must be plain named fields')
    if allowed is not None and set(attrs) - allowed:
        _fail(label + ' has unsupported fields: ' + ', '.join(sorted(set(attrs) - allowed)))


def _all_actor_values(engine):
    from world_entities import actors
    return actors(engine)


def _validate_current_state(engine, actors):
    import gameplay_validation as GAMEPLAY
    try:
        GAMEPLAY.validate(engine, actors)
    except GAMEPLAY.WorldIntegrityError as exc:
        raise StateCodecError(str(exc)) from exc
    except StateCodecError:
        raise
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        raise StateCodecError('invalid current gameplay state: ' + str(exc)) from exc

class _Encoder:
    def __init__(self, engine, *, contest=None):
        self.engine, self.rules = engine, None if engine is None else engine.r
        self.contest = contest
        self.contestants = []
        self.contest_rules = None if contest is None else contest.r
        self.nodes, self.memo, self.actor_ids = {}, {}, {}
        self._pins = {}  # Keep temporary RNG/export containers alive until encoding finishes.
        self.classes = _types()
        self.effect_tokens = set(getattr(engine, '_effect_dispatch_receipts', {}))

    def value(self, value):
        if value is None or type(value) in (str, bool, int):
            return value
        if type(value) is float:
            if not math.isfinite(value):
                _fail('nonfinite gameplay number')
            return value
        if value is self.rules and self.rules is not None:
            return {'$rules': True}
        if value is self.contest_rules and self.contest_rules is not None:
            return {'$contest_rules': True}
        identity = id(value)
        if identity in self.memo:
            return {'$ref': self.memo[identity]}
        if len(self.nodes) >= MAX_NODES:
            _fail('gameplay graph exceeds node limit')
        node_id = 'n' + str(len(self.nodes))
        self.memo[identity] = node_id
        self._pins[identity] = value
        self.nodes[node_id] = node = {}
        Engine, Combatant, Rules, GMState, Grid, Rulings = self.classes
        cls = type(value)
        if cls in (list, tuple, set, frozenset):
            node.update(kind=cls.__name__, items=[self.value(v) for v in value])
        elif cls is dict:
            observed = value.get('observed_resolution')
            if type(observed) is dict and observed.get('state') == 'deciding':
                _fail('cannot save while an observed decision callback is executing')
            node.update(kind='dict', items=[[self.value(k), self.value(v)] for k, v in value.items()])
        elif self.contest is not None and cls in _contest_types()[:2]:
            ContestEngine, Contestant, _ = _contest_types()
            attrs = vars(value)
            if cls is ContestEngine:
                if value is not self.contest:
                    _fail('one ContestEngine per saved contest session required')
                _field_names(attrs, CONTEST_FIELDS | {'_snapshots'}, 'ContestEngine')
                if value._paired_busy or getattr(value, '_standard_busy', False):
                    _fail('cannot save inside an executing contest callback')
                attrs = {k:v for k,v in attrs.items() if k != '_snapshots'}
                node.update(kind='contest', attrs=self.value(attrs))
            else:
                self.contestants.append(value)
                _field_names(attrs, None, 'Contestant')
                node.update(kind='contestant', attrs=self.value(attrs))
        elif cls is object and value in self.effect_tokens:
            row = self.engine._effect_dispatch_receipts[value]
            if row.get('receipt') is not value or row.get('status') == 'dispatching':
                _fail('native effect receipt is invalid or still executing')
            node.update(kind='effect_receipt')
        elif cls in _enum_types().values():
            node.update(kind='enum', type=next(k for k, c in _enum_types().items() if c is cls), member=value.name)
        elif cls is _batch_type():
            _field_names(vars(value), frozenset(('outcomes', 'engine')), 'Effect batch')
            node.update(kind='effect_batch', items=[self.value(v) for v in value], attrs=self.value(vars(value)))
        elif cls in _data_types().values():
            _validate_observation(value)
            node.update(kind='observation', type=next(k for k, c in _data_types().items() if c is cls), attrs=self.value(vars(value)))
        elif cls is random.Random:
            node.update(kind='random', state=self.value(value.getstate()))
        elif cls is Engine:
            if value is not self.engine:
                _fail('multiple Engines require a separately specified session contract')
            attrs = dict(vars(value))
            if attrs.pop('_native_roll_deciding',False):
                _fail('cannot save while a native roll decision callback is executing')
            if attrs.pop('_glitch_replacing_status',False):
                _fail('cannot save inside an executing I Am Error replacement')
            metronome_choices=attrs.pop('_glitch_metronome_choices',None)
            if metronome_choices is not None and (type(metronome_choices)is not dict or any(type(k)is not str or type(v)is not tuple or len(v)!=2 or not callable(v[0]) or type(v[1])is not bool for k,v in metronome_choices.items())):
                _fail('invalid live Metronome decision bindings')
            if attrs.get('_glitch_metronome_child') is not None:
                _fail('cannot save inside an executing Metronome child source grant')
            glitch_choices=attrs.pop('_glitch_error_choices',None)
            if glitch_choices is not None and (type(glitch_choices)is not dict or any(type(k)is not str or not callable(v) for k,v in glitch_choices.items())):
                _fail('invalid live I Am Error decision bindings')
            for key in ('_coordinator_damage_decisions','_coordinator_nuanced_decisions'):
                live=attrs.pop(key,None)
                if live is not None and (type(live)is not dict or any(type(k)is not str or not callable(v) for k,v in live.items())):_fail('invalid live Coordinator decision bindings')
            decisions = attrs.pop('_native_roll_decisions',None)
            if decisions is not None and (type(decisions) is not dict or any(type(k)is not str or not callable(v) for k,v in decisions.items())):
                _fail('invalid live native roll decision bindings')
            offers=attrs.get('_let_me_help_offers')
            if offers is not None:
                if type(offers)is not dict or any(type(row)is not dict or ('decision' in row and not callable(row['decision'])) for row in offers.values()):
                    _fail('invalid live Let Me Help decision bindings')
                attrs['_let_me_help_offers']={key:{k:v for k,v in row.items() if k!='decision'} for key,row in offers.items()}
            # The data-only actor offer survives. Its observation callback must
            # be authenticated again after load, like other live decision input.
            binding = attrs.pop('_root_common_binding', None)
            if binding is not None:
                attrs['_root_common_saved'] = _export_common(binding)
            fixed = attrs.pop('_heavy_native_types', None)
            if fixed != (Engine, Rules, Combatant):
                _fail('unrecognized native producer authority configuration')
            _field_names(attrs, _engine_fields(), 'Engine')
            if attrs.get('_league_dispatch'):
                _fail('cannot save inside an executing league dispatcher')
            node.update(kind='engine', attrs=self.value(attrs))
        elif cls is Combatant:
            attrs = vars(value)
            _field_names(attrs, None, 'Actor')
            spec = attrs.get('spec')
            actor_id = spec.get('id') if type(spec) is dict else None
            if type(actor_id) is not str or not actor_id.strip():
                _fail('actor requires persistent spec.id; import migration must supply it')
            if attrs.get('_entity_id', actor_id) != actor_id:
                _fail('actor stable identity disagrees with spec.id')
            if actor_id in self.actor_ids and self.actor_ids[actor_id] != identity:
                _fail('duplicate actor identity: ' + actor_id)
            self.actor_ids[actor_id] = identity
            node.update(kind='actor', entity_id=actor_id, attrs=self.value(attrs))
        elif cls is GMState:
            if value is not self.engine.gm:
                _fail('foreign GMState in gameplay graph')
            _field_names(vars(value), frozenset(('e', 'everyone', 'snapshots')), 'GMState')
            node.update(kind='gm', attrs=self.value({'e': value.e, 'everyone': value.everyone}))
        elif cls is Grid:
            _field_names(vars(value), GRID_FIELDS, 'Grid')
            node.update(kind='grid', attrs=self.value(vars(value)))
        elif cls is Rulings:
            if value is not self.rules.rulings:
                _fail('foreign Rulings object')
            attrs = vars(value)
            _field_names(attrs, RULING_FIELDS, 'Rulings')
            if attrs.get('provider') is not None or any(attrs.get('hooks', {}).values()):
                _fail('runtime ruling provider/hooks cannot be serialized')
            node.update(kind='rulings', attrs=self.value(attrs))
        else:
            _fail('unsupported gameplay object: ' + cls.__name__)
        return {'$ref': node_id}


def _common_ledger(binding):
    """Data-only comparison witness; functions and live input handles stay out."""
    m, state = binding.rm, binding.runtime.machine.state
    rows = {}
    for key, rec in state.occurrences.items():
        out = rec.outcome
        rows[key] = dict(event=m.event_fingerprint(rec.event), plan=rec.plan.id,
            revision=rec.revision, settled=list(rec.settled), committed=list(rec.committed),
            excluded=list(rec.excluded), results=m.thaw(rec.results), evidence=m.thaw(rec.evidence),
            state_fingerprint=rec.state_fingerprint,
            outcome=None if out is None else dict(tag=out.tag, event_id=out.event_id,
                committed=list(out.committed), excluded=list(out.excluded), results=m.thaw(out.results),
                obligation=None if out.obligation is None else m.thaw(vars(out.obligation))))
    return dict(profile=state.profile, revision=state.revision, game=m.thaw(state.game), occurrences=rows)


def _common_context(binding):
    # The codec forbids ruling callbacks. id(None) is process-local, not state.
    from root_common_engine import host_context
    context = host_context(binding.engine, binding.actors)
    context['provider'] = None
    return context


def _export_common(binding):
    from root_common_engine import EngineCheckBinding
    if type(binding) is not EngineCheckBinding:
        _fail('fixed native common-check binding required')
    issue = binding._fresh()
    if issue is not None:
        _fail('cannot save stale common binding: ' + issue.detail)
    rt = binding.runtime
    checked = rt.registry.checked(binding.session.registration)
    if isinstance(checked, binding.ra.Finding):
        _fail('common registration is no longer admitted: ' + checked.detail)
    cert, adapter = checked
    if adapter != binding.api.adapter() or rt.machine.invariants or rt.machine.state.children or rt._child_tickets:
        _fail('common save requires the fixed ordinary-check adapter without custom callbacks/children')
    receipts = []
    for pending, row in rt._input_pending.items():
        receipt = row['broker']._receipts.get(pending.request.id)
        if receipt is not None:
            receipts.append(dict(event_id=pending.event_id,
                request=binding.rm.thaw(binding.ra.ri.request_payload(pending.request)),
                principal_id=receipt.principal_id, value=binding.rm.thaw(receipt.value)))
    events = [dict(id=e.id, request_key=e.payload['request_key'], revision=e.expected_revision,
                   prepared=e.id in rt._prepared)
              for e in binding.session._events.values()]
    return dict(version=1, certificate=cert.fingerprint(), actors=binding.actors,
        configuration=binding.rm.thaw(binding.configuration), context=_common_context(binding),
        principal_ids=[p.id for p in rt._principals], events=events, inputs=receipts,
        recorded=sorted(binding._recorded), ledger=_common_ledger(binding))


def reauthenticate_common_checks(engine, registry, registration, principals):
    """Revalidate saved common evidence under a freshly installed authority.

    Only fixed ordinary arithmetic is reconstructed, with the exact saved dice
    faces. This does not draw native RNG, repeat native costs, publish old receipts
    or execute narrative world effects. No serialized authority is accepted.
    Returns a live binding; obtain fresh tickets with binding.begin(event, key).
    """
    from root_common_engine import EngineCheckBinding
    saved = vars(engine).get('_root_common_saved')
    if type(saved) is not dict or saved.get('version') != 1:
        _fail('no supported saved common-check session')
    if '_root_common_binding' in vars(engine):
        _fail('Engine already has a live common-check binding')
    principals = tuple(principals)
    if sorted(p.id for p in principals) != sorted(saved['principal_ids']):
        _fail('fresh authenticated principals must cover the saved principal identities')
    binding = None
    try:
        binding = EngineCheckBinding(engine, registry, registration, saved['actors'],
                                     saved['configuration'], principals)
        checked = registry.checked(registration)
        if isinstance(checked, binding.ra.Finding) or checked[0].fingerprint() != saved['certificate'] or checked[1] != binding.api.adapter():
            _fail('fresh common registration differs from saved admitted scope')
        if _common_context(binding) != saved['context']:
            _fail('saved common native context changed')
        rt, m = binding.runtime, binding.rm
        identities = {p.id:p for p in principals}
        todo = list(saved['events'])
        submitted = set()
        def prepare_at_revision():
            for row in list(todo):
                if row['revision'] != rt.machine.state.revision:
                    continue
                if not row['prepared']:
                    # A failed declaration owns no execution authority, but its
                    # original expected revision still locks its request identity.
                    binding.session._events[row['id']] = m.Event(row['id'], binding.api.EVENT_KIND,
                        rt.machine.state.profile, row['revision'], {'request_key':row['request_key']})
                else:
                    ticket = binding.session.begin(row['id'], row['request_key'])
                    if not isinstance(ticket, binding.ra.Ticket):
                        _fail('saved common preparation cannot be revalidated')
                todo.remove(row)
        def submit_saved(event_id):
            if event_id in submitted:
                return
            ticket = rt._prepared.get(event_id)
            if ticket is None:
                _fail('saved input has no revalidated event')
            out = rt.submit(ticket)
            if not isinstance(out, m.Outcome):
                _fail('saved common submission cannot be revalidated')
            submitted.add(event_id)
        for row in saved['inputs']:
            prepare_at_revision()
            submit_saved(row['event_id'])
            pending = rt.get_input(rt._prepared[row['event_id']])
            if not isinstance(pending, binding.ra.PendingInput) or binding.ra.ri.canonical(binding.ra.ri.request_payload(pending.request)) != binding.ra.ri.canonical(row['request']):
                _fail('saved common input differs from reconstructed obligation')
            out = rt.answer(pending, identities[row['principal_id']], row['value'])
            if not isinstance(out, m.Outcome):
                _fail('saved common answer cannot be revalidated')
        prepare_at_revision()
        for event_id in saved['ledger']['occurrences']:
            submit_saved(event_id)
        if todo or _common_ledger(binding) != saved['ledger']:
            _fail('saved common transcript does not reproduce the exact observed state')
        binding._recorded = set(saved['recorded'])
        del engine._root_common_saved
        engine._state_codec_authentication = 'reauthenticated_common_checks; historical evidence revalidated; fresh handles required'
        return binding
    except Exception as exc:
        if vars(engine).get('_root_common_binding') is binding:
            engine.__dict__.pop('_root_common_binding', None)
        if isinstance(exc, StateCodecError):
            raise
        raise StateCodecError('common reauthentication failed: ' + str(exc)) from exc


def _dump_engine(engine):
    """Return a JSON-compatible, versioned current-gameplay graph.

    Existing GM snapshot history is intentionally outside this API's save scope
    and its omitted count is explicit. Unknown engine fields and all callbacks
    fail instead of producing an incomplete save.
    """
    Engine, Combatant, Rules, GMState, Grid, Rulings = _types()
    if type(engine) is not Engine or type(engine.r) is not Rules:
        _fail('native Engine and Rules required')
    if engine.rulings is not engine.r.rulings:
        _fail('Engine and Rules must share their Rulings object')
    if getattr(engine,'_native_action_stack',[]):
        _fail('cannot save inside an executing native action')
    encoder = _Encoder(engine)
    root = encoder.value(engine)
    _validate_current_state(engine, [actor for actor in _all_actor_values(engine)])
    payload = {'format': FORMAT, 'version': VERSION, 'rules': rules_fingerprint(engine.r),
               'root': root, 'nodes': encoder.nodes,
               'save_scope': {'current_gameplay': True, 'gm_checkpoint_history': False,
                              'omitted_checkpoint_count': len(engine.gm.snapshots)},
               'authentication': AUTH_NOTICE}
    # A final strict JSON boundary also rejects non-JSON scalar subclasses.
    json.dumps(payload, ensure_ascii=False, allow_nan=False)
    return payload


class _Decoder:
    def __init__(self, rules, nodes, *, contest_rules=None, graph_roots=None, expected_native_rules=None):
        self.rules, self.nodes, self.objects, self.building = rules, nodes, {}, set()
        self.expected_native_rules=expected_native_rules
        self.contest_rules, self.graph_roots = contest_rules, graph_roots
        self.classes = _types()
        self.engine_ids, self.actor_ids = [], {}
        self._validate_nodes()
        Engine, Combatant, Rules, GMState, Grid, Rulings = self.classes
        allocators = {'list': list, 'dict': dict, 'set': set,
                      'engine': lambda: Engine.__new__(Engine),
                      'actor': lambda: Combatant.__new__(Combatant),
                      'gm': lambda: GMState.__new__(GMState),
                      'grid': lambda: Grid.__new__(Grid),
                      'rulings': lambda: Rulings.__new__(Rulings), 'random': random.Random, 'effect_receipt': object}
        if self.contest_rules is not None:
            ContestEngine, Contestant, _ = _contest_types()
            allocators.update(contest=lambda: ContestEngine.__new__(ContestEngine),
                              contestant=lambda: Contestant.__new__(Contestant))
        for uid, node in nodes.items():
            if node['kind'] == 'enum':
                self.objects[uid] = _enum_types()[node['type']][node['member']]
            if node['kind'] == 'observation':
                cls = _data_types()[node['type']]
                self.objects[uid] = cls.__new__(cls)
            if node['kind'] in allocators:
                self.objects[uid] = allocators[node['kind']]()
        # Immutable containers can refer to mutable shells. Populate the shells
        # afterwards, allowing tuple -> list -> tuple cycles without proxies.
        for uid in nodes:
            self.node(uid)
        for uid, node in nodes.items():
            target, kind = self.objects[uid], node['kind']
            if kind == 'list':
                target.extend(self.value(v) for v in node['items'])
            elif kind == 'dict':
                for k, v in node['items']:
                    key = self.value(k)
                    try:
                        if key in target:
                            _fail('duplicate decoded dictionary key')
                        target[key] = self.value(v)
                    except TypeError as exc:
                        raise StateCodecError('unhashable decoded dictionary key') from exc
            elif kind == 'set':
                try:
                    for v in node['items']:
                        item = self.value(v)
                        if item in target:
                            _fail('duplicate decoded set item')
                        target.add(item)
                except TypeError as exc:
                    raise StateCodecError('unhashable decoded set item') from exc
        # Attribute maps are now populated. No descriptors or setters execute.
        for uid, node in nodes.items():
            kind, target = node['kind'], self.objects[uid]
            if kind in ('engine', 'actor', 'gm', 'grid', 'rulings', 'observation', 'effect_batch', 'contest', 'contestant'):
                attrs = self.value(node['attrs'])
                allowed = {'engine': _engine_fields(), 'actor': None, 'gm': frozenset(('e', 'everyone')),
                           'grid': GRID_FIELDS, 'rulings': RULING_FIELDS, 'observation': None, 'effect_batch': frozenset(('outcomes', 'engine')), 'contest': CONTEST_FIELDS, 'contestant': None}[kind]
                _field_names(attrs, allowed, kind)
                object.__setattr__(target, '__dict__', attrs)
            elif kind == 'random':
                try:
                    target.setstate(self.value(node['state']))
                except (TypeError, ValueError, OverflowError) as exc:
                    raise StateCodecError('invalid RNG state') from exc
        for uid, node in nodes.items():
            if node['kind'] == 'observation':
                _validate_observation(self.objects[uid])
        self._validate_graph()

    def _validate_nodes(self):
        if type(self.nodes) is not dict or not 1 <= len(self.nodes) <= MAX_NODES:
            _fail('nonempty bounded graph required')
        shapes = {'list': {'kind', 'items'}, 'tuple': {'kind', 'items'}, 'set': {'kind', 'items'},
                  'frozenset': {'kind', 'items'}, 'dict': {'kind', 'items'}, 'random': {'kind', 'state'},
                  'engine': {'kind', 'attrs'}, 'actor': {'kind', 'attrs', 'entity_id'},
                  'gm': {'kind', 'attrs'}, 'grid': {'kind', 'attrs'}, 'rulings': {'kind', 'attrs'},
                  'observation': {'kind', 'type', 'attrs'}, 'effect_receipt': {'kind'},
                  'enum': {'kind', 'type', 'member'}, 'effect_batch': {'kind', 'items', 'attrs'}}
        if self.contest_rules is not None:
            shapes.update(contest={'kind', 'attrs'}, contestant={'kind', 'attrs'})
        for uid, node in self.nodes.items():
            if type(uid) is not str or not re.fullmatch(r'n[0-9]+', uid) or type(node) is not dict:
                _fail('malformed graph node')
            kind = node.get('kind')
            if type(kind) is not str or kind not in shapes or set(node) != shapes[kind]:
                _fail('unknown graph tag or fields')
            if kind == 'observation' and (type(node['type']) is not str or node['type'] not in _data_types()):
                _fail('unknown fixed observation type')
            if kind == 'enum' and (type(node['type']) is not str or node['type'] not in _enum_types() or type(node['member']) is not str or node['member'] not in _enum_types()[node['type']].__members__):
                _fail('unknown fixed enum member')
            if kind == 'effect_batch' and len(node['items']) != 2:
                _fail('effect batch needs exactly done/held counts')
            if kind == 'engine':
                self.engine_ids.append(uid)
            if kind == 'actor':
                value = node['entity_id']
                if type(value) is not str or not value.strip() or value in self.actor_ids:
                    _fail('invalid or duplicate actor identity')
                self.actor_ids[value] = uid
            if 'items' in node and type(node['items']) is not list:
                _fail('graph items must be a JSON array')
            for value in (node.get('items', []) if kind != 'dict' else [v for pair in node['items'] for v in self._pair(pair)]):
                self._encoded_value(value)
            for key in ('attrs', 'state'):
                if key in node:
                    self._encoded_value(node[key])
        if self.contest_rules is None and len(self.engine_ids) != 1:
            _fail('one Engine graph root required')
        if self.contest_rules is not None and len(self.engine_ids) > 1:
            _fail('one native Engine per contest session required')

    def _pair(self, value):
        if type(value) is not list or len(value) != 2:
            _fail('dictionary entries must be key/value pairs')
        return value

    def _encoded_value(self, value):
        if value is None or type(value) in (str, bool, int):
            return
        if type(value) is float and math.isfinite(value):
            return
        if type(value) is dict:
            if set(value) == {'$rules'} and value['$rules'] is True and self.rules is not None:
                return
            if set(value) == {'$contest_rules'} and value['$contest_rules'] is True and self.contest_rules is not None:
                return
            if set(value) == {'$ref'} and type(value['$ref']) is str and value['$ref'] in self.nodes:
                return
        _fail('invalid tagged value or dangling reference')

    def value(self, value):
        self._encoded_value(value)
        if type(value) is dict:
            if '$rules' in value:
                return self.rules
            if '$contest_rules' in value:
                return self.contest_rules
            return self.node(value['$ref'])
        return value

    def node(self, uid):
        if uid in self.objects:
            return self.objects[uid]
        if uid in self.building:
            _fail('immutable-only reference cycle')
        self.building.add(uid)
        node = self.nodes[uid]
        try:
            values = [self.value(v) for v in node['items']]
            if node['kind'] == 'effect_batch':
                if any(type(v) is not int or v < 0 for v in values):
                    _fail('invalid effect batch counts')
                result = _batch_type()(*values)
            else:
                result = tuple(values) if node['kind'] == 'tuple' else frozenset(values)
            if node['kind'] == 'frozenset' and len(result) != len(values):
                _fail('duplicate frozenset item')
        except TypeError as exc:
            raise StateCodecError('unhashable immutable set item') from exc
        self.building.remove(uid)
        self.objects[uid] = result
        return result

    def _validate_graph(self):
        from state_fields import validate_base
        Engine, Combatant, Rules, GMState, Grid, Rulings = self.classes
        if not self.engine_ids:
            if any(n['kind'] in ('actor','gm','rulings','effect_receipt','effect_batch') for n in self.nodes.values()):
                _fail('native state requires its actual Engine context')
            self._validate_contest_graph()
            _validate_reachability(self.nodes, self.graph_roots)
            return
        engine = self.objects[self.engine_ids[0]]
        required = ENGINE_SPECIAL | {'seed', 'log_lines', '_root_common_epoch', 'everyone',
            'death_enabled', 'friendly_battle', 'session_frequency', 'defer_session_refresh'}
        if not required <= vars(engine).keys():
            _fail('Engine save lacks required state fields')
        if engine.r is not self.rules or type(engine.rulings) is not Rulings:
            _fail('invalid rule references')
        if type(engine.gm) is not GMState or engine.gm.e is not engine:
            _fail('invalid GM owner reference')
        if type(engine.rng) is not random.Random or type(engine.log_lines) is not list:
            _fail('invalid RNG or log state')
        if type(engine._root_common_epoch) is not int or engine._root_common_epoch < 0:
            _fail('invalid root epoch')
        if type(engine.everyone) is not list or type(engine.gm.everyone) is not list:
            _fail('native rosters must be lists')
        for roster in (engine.everyone, engine.gm.everyone):
            if any(type(c) is not Combatant for c in roster) or len({id(c) for c in roster}) != len(roster):
                _fail('invalid or duplicate roster actor')
        for field in ('death_enabled', 'friendly_battle', 'session_frequency'):
            if type(getattr(engine, field)) is not bool:
                _fail('invalid Engine boolean policy')
        if engine.session_frequency:
            if type(engine.defer_session_refresh) is not bool:
                _fail('session refresh choice required')
        elif engine.defer_session_refresh is not None:
            _fail('unexpected session refresh choice')
        if engine._league_dispatch:
            _fail('in-progress dispatcher cannot be restored')
        for uid, node in self.nodes.items():
            value = self.objects[uid]
            if node['kind'] == 'actor':
                spec = vars(value).get('spec')
                if type(spec) is not dict or spec.get('id') != node['entity_id']:
                    _fail('actor header disagrees with spec identity')
                if vars(value).get('_entity_id', node['entity_id']) != node['entity_id']:
                    _fail('actor stable identity disagrees with spec')
                if vars(value).get('r') is not self.rules:
                    _fail('actor has foreign rules reference')
                try:
                    validate_base(spec)
                except (ValueError, TypeError, KeyError) as exc:
                    raise StateCodecError('invalid actor base state: ' + str(exc)) from exc
                value.__dict__.setdefault('_entity_id', node['entity_id'])
            elif node['kind'] == 'effect_batch':
                from effect_contracts import Outcome
                if type(value.outcomes) is not tuple or any(type(row) is not Outcome for row in value.outcomes) or ('engine' in vars(value) and value.engine is not engine):
                    _fail('invalid fixed effect batch references')
            elif node['kind'] == 'grid':
                if not GRID_REQUIRED_FIELDS <= set(vars(value)) <= GRID_FIELDS or any(type(getattr(value, k)) is not int or getattr(value, k) <= 0 for k in ('w', 'h')):
                    _fail('invalid grid dimensions/fields')
                if any(type(getattr(value, k)) is not set for k in ('blocking', 'rough', 'slow', 'walls')):
                    _fail('invalid grid terrain containers')
                if any(type(vars(value)[k]) is not dict for k in GRID_OPTIONAL_FIELDS - {'_tunnel_map_id'} if k in vars(value)):
                    _fail('invalid grid observed terrain containers')
            elif node['kind'] == 'rulings':
                if set(vars(value)) != RULING_FIELDS or value.provider is not None or any(value.hooks.values()):
                    _fail('runtime ruling callbacks cannot be restored')
        # Validate gameplay against the saved declarations on this private Rules copy.
        self.rules.rulings = engine.rulings
        if self.expected_native_rules is not None:
            try:
                __import__('weapon_actions').restore_generated(self.rules,self.expected_native_rules['generated_weapons'])
                if rules_fingerprint(self.rules)!=self.expected_native_rules:
                    _fail('selected rule/profile/source fingerprint mismatch after native weapon reconstruction')
            except (ValueError,KeyError,TypeError) as exc:
                raise StateCodecError('invalid native generated weapon declaration: '+str(exc)) from exc
        receipts = getattr(engine, '_effect_dispatch_receipts', {})
        opaque = {self.objects[uid] for uid,node in self.nodes.items() if node['kind'] == 'effect_receipt'}
        if type(receipts) is not dict or set(receipts) != opaque:
            _fail('opaque native effect receipts must belong to the Engine ledger')
        import effect_contracts as EFFECTS
        for token, row in receipts.items():
            if type(row) is not dict or row.get('receipt') is not token or row.get('status') == 'dispatching':
                _fail('invalid or executing native effect receipt')
            try:
                EFFECTS.validate_receipt(engine, token, row['source_id'], row['occurrence'], row['actor'], row['target'], row['effect'])
            except (ValueError, TypeError, KeyError) as exc:
                raise StateCodecError('invalid native effect evidence: ' + str(exc)) from exc
        if engine.grid is not None and type(engine.grid) is not Grid:
            _fail('invalid grid reference')
        # Reachability closes the declared graph; orphan actor definitions must
        # not smuggle a different rule context or inflate identity claims.
        roots = self.graph_roots[:] if self.graph_roots is not None else [self.engine_ids[0]]
        # Native-host malformed roots retain load_contest's KeyError adapter;
        # standalone contests keep the helper's existing missing-root error.
        for uid in reversed(roots):
            if uid not in self.nodes:
                raise KeyError(uid)
        _validate_reachability(self.nodes, roots)
        actors=[self.objects[uid] for uid, node in self.nodes.items() if node['kind'] == 'actor']
        import equipment_suppression as SUPPRESSION
        SUPPRESSION.upgrade_legacy(engine,{actor.entity_id:actor for actor in actors})
        import csv_item_physical_contracts as CSV_ITEMS
        CSV_ITEMS.upgrade_legacy_cannon(engine, {actor.entity_id:actor for actor in actors})
        import equipment_variant_contracts as EQUIPMENT_VARIANTS
        EQUIPMENT_VARIANTS.upgrade_legacy_slipstream(engine)
        import martial_artist as MARTIAL
        MARTIAL.upgrade_legacy(engine)
        _validate_current_state(engine, actors)
        engine._heavy_native_types = (Engine, Rules, Combatant)
        engine.gm.snapshots = {}
        engine._root_common_epoch += 1
        engine._state_codec_authentication = AUTH_NOTICE
        if self.contest_rules is not None:
            self._validate_contest_graph()

    def _validate_contest_graph(self):
        contests = [self.objects[k] for k,n in self.nodes.items() if n['kind'] == 'contest']
        if len(contests) != 1:
            _fail('one contest host required')
        native = self.objects[self.engine_ids[0]] if self.engine_ids else None
        contestants = [self.objects[k] for k,n in self.nodes.items() if n['kind'] == 'contestant']
        _validate_contest_state(contests[0], contestants, native)
        contests[0]._snapshots = {}


def _load_engine(rules, payload):
    """Validate and load into a new Engine; supplied Rules are never mutated."""
    _, _, Rules, _, _, _ = _types()
    if type(rules) is not Rules or type(payload) is not dict:
        _fail('native Rules and a save envelope required')
    keys = {'format', 'version', 'rules', 'root', 'nodes', 'save_scope', 'authentication'}
    if set(payload) != keys or payload['format'] != FORMAT or type(payload['version']) is not int or payload['version'] != VERSION:
        _fail('unsupported or malformed save envelope')
    if payload['authentication'] != AUTH_NOTICE:
        _fail('save must declare reauthentication')
    scope = payload['save_scope']
    if type(scope) is not dict or set(scope) != {'current_gameplay', 'gm_checkpoint_history', 'omitted_checkpoint_count'} or scope['current_gameplay'] is not True or scope['gm_checkpoint_history'] is not False or type(scope['omitted_checkpoint_count']) is not int or scope['omitted_checkpoint_count'] < 0:
        _fail('invalid current-gameplay save scope')
    generated=type(payload['rules'])is dict and 'generated_weapons' in payload['rules']
    if generated:
        if set(payload['rules'])!={'sha256','profile','file_count','generated_weapons'} or type(payload['rules']['sha256'])is not str or re.fullmatch(r'[0-9a-f]{64}',payload['rules']['sha256'])is None or type(payload['rules']['profile'])is not str or type(payload['rules']['file_count'])is not int or payload['rules']['file_count']<0 or type(payload['rules']['generated_weapons'])is not list or len(payload['rules']['generated_weapons'])>MAX_NODES:
            _fail('invalid native generated weapon rules header')
    elif payload['rules'] != rules_fingerprint(rules):
        _fail('selected rule/profile/source fingerprint mismatch')
    if type(payload['root']) is not dict or set(payload['root']) != {'$ref'}:
        _fail('graph root must reference the Engine')
    try:
        clone_rules = __import__('weapon_actions').private_restore_rules(rules) if generated else copy(rules)
        decoder = _Decoder(clone_rules, payload['nodes'],expected_native_rules=payload['rules'] if generated else None)
        if payload['root']['$ref'] != decoder.engine_ids[0]:
            _fail('root reference is not the unique Engine')
        return decoder.value(payload['root'])
    except StateCodecError:
        raise
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError, RecursionError) as exc:
        raise StateCodecError('malformed or unsupported gameplay save: ' + str(exc)) from exc


def import_legacy_encounter(root, path, *, reason, ruleset=None, seed=None):
    """Explicitly import a scenario, never claim it is a current-state save.

    This audited loader builds initial actors. It cannot recover previously
    lost HP, effects or pending choices from an old scenario file.
    """
    if type(reason) is not str or not reason.strip():
        _fail('legacy import requires a recorded GM reason')
    from encounter import load_encounter
    source = Path(path)
    if not source.is_absolute():
        source = Path(root) / source
    engine, _, _, _ = load_encounter(str(root), str(source), ruleset=ruleset, seed=seed)
    provenance = {'kind': 'legacy_encounter_initial_state', 'source': str(source.resolve()),
        'sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'reason': reason,
        'creation_legality_certified': False, 'previous_runtime_state_recovered': False}
    engine.state_import_provenance = provenance
    for actor in engine.everyone:
        actor.__dict__['_state_import_provenance'] = provenance
    return engine


# Contest state has its own rule reader and identity graph, optionally sharing
# one actual native Engine. Neither reader nor callbacks are reconstructed.
CONTEST_FORMAT = 'ptk-contest-state'
CONTEST_FIELDS = frozenset(('r', 'rng', 'log_lines', 'apply_intro_bonus',
    '_native_intro_bindings', '_trainer_partners', '_flourish_used', '_fashion_used',
    '_performance_observations', '_coordinator_used', '_paired_run', '_paired_busy',
    '_trainer_interactions', 'last_standings', '_standard_run', '_standard_busy',
    '_festival_run', '_festival_busy', '_adaptable_uses', '_adaptable_plan'))


def _contest_types():
    from contest import ContestEngine, Contestant, ContestRules
    return ContestEngine, Contestant, ContestRules


def _validate_reachability(nodes, roots):
    reachable, todo = set(), list(roots or ())
    while todo:
        uid = todo.pop()
        if uid in reachable:
            continue
        if uid not in nodes:
            _fail('missing contest graph root')
        reachable.add(uid)
        node = nodes[uid]
        values = list(node.get('items', []))
        if node['kind'] == 'dict':
            values = [v for pair in values for v in pair]
        values += [node[k] for k in ('attrs', 'state') if k in node]
        todo.extend(v['$ref'] for v in values if type(v) is dict and '$ref' in v)
    if reachable != set(nodes):
        _fail('save contains unreachable graph nodes')


def _validate_contest_state(contest, contestants, native):
    ContestEngine, Contestant, ContestRules = _contest_types()
    Engine, Combatant, _, _, _, _ = _types()
    if type(contest) is not ContestEngine or type(contest.r) is not ContestRules:
        _fail('native contest host and selected rules required')
    required = CONTEST_FIELDS - {'last_standings', '_standard_run', '_standard_busy', '_festival_run', '_festival_busy', '_adaptable_plan'}
    if not required <= vars(contest).keys():
        _fail('contest lacks required current-state fields')
    _field_names(vars(contest), CONTEST_FIELDS | {'_snapshots'}, 'ContestEngine')
    if type(contest.rng) is not random.Random or type(contest.log_lines) is not list:
        _fail('invalid contest RNG/log state')
    if type(contest.apply_intro_bonus) is not bool or contest._paired_busy is not False or getattr(contest, '_standard_busy', False) is not False or getattr(contest, '_festival_busy', False) is not False:
        _fail('contest is executing or has invalid boolean state')
    for name in ('_native_intro_bindings', '_trainer_partners', '_performance_observations'):
        if type(getattr(contest,name)) is not dict:
            _fail('contest ledger must be a dictionary')
    for name in ('_flourish_used','_fashion_used','_coordinator_used'):
        if type(getattr(contest,name)) is not set:
            _fail('contest feature usage must be a set')
    __import__('coordinator').validate_contest(contest,set(contestants))
    stats = set(contest.r.mech('contest/type-match')['ring'])
    ids = set()
    for c in contestants:
        if type(c) is not Contestant:
            _fail('native Contestant required')
        _field_names(vars(c), None, 'Contestant')
        uid = vars(c).get('_contestant_id')
        if type(uid) is not str or not uid or uid in ids:
            _fail('contest participant needs a unique stable identity')
        ids.add(uid)
        if type(c.name) is not str or type(c.stat_dice) is not dict or set(c.stat_dice)-stats or any(type(n) is not int or n<0 for n in c.stat_dice.values()):
            _fail('invalid contest name or remaining stat pool')
        if type(c.moves) is not list or any(type(m) is not str for m in c.moves):
            _fail('invalid learned contest moves')
        for move in c.moves:
            contest.r.move_contest(move)
        for key in ('appeal','fumble'):
            if type(getattr(c,key)) is not int or getattr(c,key)<0:
                _fail('invalid contest score')
        if type(c.excitement) is not int or not 0<=c.excitement<=5:
            _fail('invalid contest excitement')
        for key in ('intro_completed','been_center','double_next','immune_fumble'):
            if type(getattr(c,key)) is not bool:
                _fail('invalid contestant flag')
        if c.letter is not None and c.letter not in tuple('ABCDE'):
            _fail('invalid contest letter')
        if type(c.intro_rank_dice) is not int or c.intro_rank_dice<1:
            _fail('invalid introduction rank')
        if '_intro_stat_dice' in vars(c):
            pool=c._intro_stat_dice
            if type(pool) is not dict or set(pool)-stats or any(type(n) is not int or n<0 for n in pool.values()):
                _fail('invalid shared introduction pool')
        if c.intro_stat is not None and c.intro_stat not in stats:
            _fail('invalid introduction stat')
        if type(c.intro_sources) is not set or type(c.trainer_edges) is not set or type(c.intro_bonuses) is not list:
            _fail('invalid introduction source records')
        if '_paired_state' in vars(c):
            shared=vars(c)['_paired_state']
            if type(shared) is not dict or set(shared)!={'excitement','double_next','immune_fumble'}:
                _fail('invalid shared participant state')
    known=set(contestants)
    for c,binding in contest._native_intro_bindings.items():
        if c not in known or type(binding) is not tuple or len(binding)!=5:
            _fail('invalid native contest binding')
        e,pokemon,trainer,skill,choices=binding
        if e is not native or type(e) is not Engine or type(pokemon) is not Combatant or type(trainer) is not Combatant or pokemon.r is not e.r or trainer.r is not e.r or type(skill) is not str or type(choices) is not dict:
            _fail('foreign or malformed native contest binding')
        if pokemon.kind!='pokemon' or trainer.kind!='trainer':
            _fail('native contest binding kind mismatch')
    for c,partner in contest._trainer_partners.items():
        if c not in contest._native_intro_bindings or partner not in known or partner is c or partner.stat_dice is not c.stat_dice:
            _fail('trainer pair must share its actual stat pool')
    for key,row in contest._performance_observations.items():
        if type(key) is not str or type(row) is not dict or set(row)!={'observed_resolution'}:
            _fail('invalid contest observed occurrence')
        record=row['observed_resolution']
        if type(record) is not dict or record.get('family')!='contest.performance' or record.get('state') not in ('pending','complete'):
            _fail('invalid or executing contest observation')
        participants=record.get('participants')
        declaration=record.get('declaration')
        if type(participants) is not tuple or len(participants)!=1 or participants[0] not in known or type(declaration) is not dict:
            _fail('invalid observed contest participant')
        adjacent=declaration.get('adjacent')
        intro_spend=declaration.get('spend_intro_dice',0)
        if type(intro_spend) is not int or not 0<=intro_spend<=declaration.get('spend_stat_dice',-1):
            _fail('invalid observed shared introduction spend')
        if type(adjacent) is not tuple or any(c not in known for c in adjacent) or len(set(adjacent))!=len(adjacent) or participants[0] in adjacent:
            _fail('invalid observed adjacent contestants')
        observation=record.get('observation')
        if type(observation) is not dict or set(observation)!={'frame','coordinator','flourish','fashion'}:
            _fail('invalid performance observation fields')
        frame=observation['frame']
        expected={'pool_components','move_id','total','rolls','appeal','fumble','eff','center','rerolled'}
        if type(frame) is not dict or set(frame)!=expected or frame['move_id']!=declaration.get('move') or frame['center']!=declaration.get('center'):
            _fail('invalid or changed performance frame')
        _,effect=contest.r.move_contest(frame['move_id'])
        if frame['eff']!=contest.r.performance_rules()['effects'][effect]:
            _fail('performance effect disagrees with selected source')
        if type(frame['total']) is not int or frame['total']<0 or type(frame['rolls']) is not tuple:
            _fail('invalid saved performance dice')
        parts=frame['pool_components']
        if (type(parts) is not dict or set(parts)!={'move','turn_start_excitement','type_match','spent_stat'}
                or any(type(value) is not int for value in parts.values())
                or not 0<=parts['turn_start_excitement']<=5
                or not 0<=parts['spent_stat']<=contest.r.performance_rules()['stat-dice']['max_spend_per_move']
                or parts['spent_stat']!=declaration['spend_stat_dice']
                or sum(parts.values())!=frame['total']):
            _fail('saved performance pool differs from its observed components')
        contest.validate_d6(frame['rolls'],frame['total'])
        if type(frame['center']) is not bool or frame['rerolled'] is not False:
            _fail('initial contest roll must precede any reroll')
        appeal,fumble=contest.score(list(frame['rolls']),frame['center'],frame['eff'].get('scoring_override'))
        if (frame['appeal'],frame['fumble'])!=(appeal,fumble):
            _fail('saved initial contest score disagrees with its public dice')
        coordinator=observation['coordinator']
        if coordinator is not None and (type(coordinator) is not tuple or len(coordinator)!=2 or coordinator[0] is not native or type(coordinator[1]) is not str):
            _fail('invalid Coordinator occurrence owner')
        fashion=observation['fashion']
        if fashion is not None and (type(fashion) is not tuple or len(fashion)!=3 or any(type(value) is not str or not value for value in fashion)):
            _fail('invalid Fashion physical occurrence owner')
        if record['state']=='complete':
            if type(record.get('result')) is not dict or record['result'].get('attempt_id')!=key:
                _fail('completed performance lacks its once-only result')
    paired=contest._paired_run
    if paired is not None:
        if type(paired) is not dict or paired.get('phase') not in ('intro','round','perform','complete') or paired.get('model') not in ('simultaneous','alternating'):
            _fail('invalid paired contest phase')
        pairs=paired.get('pairs')
        if type(pairs) is not dict or pairs!=contest._trainer_partners:
            _fail('paired session differs from bound partners')
        if len(set(pairs.values()))!=len(pairs) or set(pairs)&set(pairs.values()):
            _fail('one performer cannot occupy multiple contest pairs')
        if len({id(c.stat_dice) for c in pairs})!=len(pairs):
            _fail('different contest pairs cannot share a stat pool')
        if paired['model']=='simultaneous' and any('_paired_state' in vars(c) for c in (*pairs,*pairs.values())):
            _fail('simultaneous participants must track excitement separately')
        if paired['model']=='alternating' and paired['phase']!='intro':
            for c,partner in pairs.items():
                if vars(c).get('_paired_state') is not vars(partner).get('_paired_state') or '_paired_state' not in vars(c):
                    _fail('alternating participants must share excitement and next-performance effects')
        for field in ('round','slot','performer'):
            if type(paired.get(field)) is not int or paired[field]<0:
                _fail('invalid paired progress cursor')
        if type(paired.get('contract')) is not tuple or paired['contract'][0]!=tuple(pairs):
            _fail('paired contract changed participant identity/order')
        _validate_contest_progress(contest,paired,tuple(pairs),paired=True)
        selections=paired.get('selections');previous=paired.get('previous')
        if type(selections) is not dict or type(previous) is not dict:
            _fail('paired contest requires explicit current and previous performers')
        if (paired['phase']=='perform' and set(selections)!=set(pairs)) or (paired['phase'] in ('intro','complete') and selections):
            _fail('paired selections disagree with the session phase')
        if (paired['round']==0 and previous) or (paired['round']>0 and set(previous)!=set(pairs)):
            _fail('paired previous performers disagree with completed rounds')
        for owner,actor in previous.items():
            if owner not in pairs or actor not in (owner,pairs[owner]):
                _fail('previous performer does not belong to its contest pair')
        for owner,selection in selections.items():
            if owner not in pairs or type(selection) is not tuple:
                _fail('invalid paired performer selection')
            if paired['model']=='simultaneous':
                if len(selection)!=2 or set(selection)!={owner,pairs[owner]}:
                    _fail('both distinct partners must perform in simultaneous mode')
            elif len(selection)!=1 or selection[0] not in (owner,pairs[owner]) or previous.get(owner) is selection[0]:
                _fail('alternating contest must switch to the other partner')
    try:
        import contest_festival as FESTIVAL
        FESTIVAL.validate(contest, known)
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise StateCodecError('invalid Festival state: ' + str(exc)) from exc
    standard=getattr(contest,'_standard_run',None)
    if standard is not None:
        if type(standard) is not dict or standard.get('phase') not in ('intro','round','perform','complete'):
            _fail('invalid standard contest phase')
        if type(standard.get('contract')) is not tuple or any(c not in known for c in standard['contract'][0]):
            _fail('invalid standard contestant contract')
        _validate_contest_progress(contest,standard,standard['contract'][0],paired=False)
        rotation=standard.get('rotation')
        if rotation is not None:
            try:
                import contest_rotation as ROTATION
                if rotation.get('representatives') != standard['contract'][0]:
                    _fail('rotation representatives differ from the contest contract')
                ROTATION.validate(
                    rotation, state=standard,
                    valid_types=contest.r.mech('contest/type-match')['ring'],
                    move_validator=contest.r.move_contest,
                    native_bindings=(None if standard['phase'] == 'complete'
                                     else contest._native_intro_bindings))
            except (ValueError, TypeError, KeyError, IndexError) as exc:
                raise StateCodecError('invalid rotation contest state: ' + str(exc)) from exc
    try:
        import contest_halls as HALLS
        HALLS.validate_contest(contest)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
        raise StateCodecError('invalid Contest Hall/Ribbon state: ' + str(exc)) from exc



def _validate_contest_progress(contest,state,participants,*,paired):
    if type(state.get('id')) is not str or not state['id'] or type(participants) is not tuple or not 3<=len(participants)<=5 or len(set(participants))!=len(participants):
        _fail('invalid contest session identity/participants')
    contract=state['contract']
    if len(contract)!=(5 if paired else 3) or contract[2] not in ('standard','super'):
        _fail('invalid contest variant contract')
    if (contract[2]=='super' and contract[1] is not None) or (contract[2]=='standard' and contract[1] not in contest.r.mech('contest/type-match')['ring']):
        _fail('invalid contest type contract')
    table=contest.r.mech('contest/position-tables')[str(len(participants))]
    if state.get('table')!=table:
        _fail('saved contest table differs from selected source')
    rnd,slot=state.get('round'),state.get('slot')
    if type(rnd) is not int or not 0<=rnd<=len(table['rounds']) or type(slot) is not int or not 0<=slot<len(participants):
        _fail('invalid contest progress cursor')
    phase=state['phase']
    if phase=='complete':
        result=state.get('result')
        if rnd!=len(table['rounds']) or slot!=0 or state.get('pending') is not None or type(result) is not tuple or len(result)!=len(participants) or set(result)!=set(participants):
            _fail('invalid completed contest result/cursor')
    elif rnd==len(table['rounds']):
        _fail('unfinished contest is beyond the final round')
    if phase=='intro' and (rnd or slot or state.get('pending') is not None):
        _fail('invalid introduction progress')
    if phase!='intro':
        letters=[c.letter for c in participants]
        if set(letters)!=set('ABCDE'[:len(participants)]) or any(not c.intro_completed for c in participants):
            _fail('current contest requires completed unique introduction letters')
    if not paired and phase!='intro':
        # A center visit is committed only after its performance succeeds.
        center_column=table['turn_order_by_column'].index(1)
        visited={row[center_column] for row in table['rounds'][:rnd]}
        if phase=='perform' and slot>0:
            visited.add(table['rounds'][rnd][center_column])
        if any(c.been_center != (c.letter in visited) for c in participants):
            _fail('center history disagrees with committed contest progress')
    actors=[*participants,*state['pairs'].values()] if paired else participants
    if phase in ('round','complete') and any(c.immune_fumble for c in actors):
        _fail('round protection outlived its contest round')
    if phase=='complete' and any(c.double_next for c in actors):
        _fail('next-round boost outlived the contest')
    round_type=state.get('round_type')
    if phase=='perform' and round_type not in contest.r.mech('contest/type-match')['ring']:
        _fail('performing contest must retain its chosen round type')
    if round_type is not None and contract[2]=='standard' and round_type!=contract[1]:
        _fail('standard round type changed')
    if paired:
        if contract[3]!=state['model'] or contract[4]!=contest._trainer_interactions:
            _fail('paired interaction contract changed')
        performer=state['performer']
        if not 0<=performer<(2 if state['model']=='simultaneous' else 1):
            _fail('invalid paired performer cursor')
    if state.get('pending') is not None:
        if phase!='perform':
            _fail('pending performance outside performing phase')
        columns=sorted(range(len(participants)),key=lambda i:table['turn_order_by_column'][i])
        column=columns[slot]
        attempt=state['id']+':'+str(rnd+1)+':'+str(column)
        if paired:attempt+=':'+str(state['performer'])
        observed=contest._performance_observations.get(attempt,{}).get('observed_resolution')
        if type(observed) is not dict or observed.get('state')!='pending':
            _fail('pending cursor lacks the preserved first observation')
        declaration=observed['declaration'];locked=state['pending']
        move_key='requested_move' if 'adaptable' in declaration else 'move'
        if 'adaptable' in declaration and (type(locked) is not dict or tuple(contest.r.move(m)['id'] for m in locked.get('adaptable',()))!=declaration['adaptable']):
            _fail('pending Adaptable constituents differ from their observation')
        if type(locked) is not dict or any(locked.get(k)!=declaration.get(v) for k,v in (('move',move_key),('spend','spend_stat_dice'),('feature','feature'))):
            _fail('pending cursor declaration differs from its observation')


def dump_contest(contest, contestants):
    """Save one current contest and its native context; callbacks are supplied again.

    Returns a JSON envelope. Checkpoint history is excluded explicitly, matching
    dump_engine. Contestants may share names but must retain stable identities.
    """
    ContestEngine, Contestant, ContestRules = _contest_types()
    if type(contest) is not ContestEngine or type(contest.r) is not ContestRules:
        _fail('native ContestEngine/ContestRules required')
    if type(contestants) not in (list,tuple) or not contestants or any(type(c) is not Contestant for c in contestants) or len(set(contestants))!=len(contestants):
        _fail('explicit ordered distinct contest participants required')
    natives={binding[0] for binding in contest._native_intro_bindings.values()}
    if len(natives)>1:
        _fail('one native Engine per contest session required')
    native=next(iter(natives),None)
    encoder=_Encoder(native,contest=contest)
    root=encoder.value(contest)
    participants=encoder.value(tuple(contestants))
    _validate_contest_state(contest,encoder.contestants,native)
    if native is not None:
        _validate_current_state(native,_all_actor_values(native))
    payload={'format':CONTEST_FORMAT,'version':VERSION,
             'rules':rules_fingerprint(contest.r),
             'native_rules':None if native is None else rules_fingerprint(native.r),
             'root':root,'participants':participants,'nodes':encoder.nodes,
             'authentication':AUTH_NOTICE,
             'save_scope':{'current_gameplay':True,'checkpoint_history':False,
                           'omitted_contest_checkpoints':len(contest._snapshots),
                           'omitted_native_checkpoints':0 if native is None else len(native.gm.snapshots)}}
    json.dumps(payload,ensure_ascii=False,allow_nan=False)
    return payload


def _load_contest(contest_rules,payload,*,native_rules=None):
    """Return (new ContestEngine, ordered contestant tuple), preserving native refs."""
    _,_,ContestRules=_contest_types()
    if type(contest_rules) is not ContestRules or type(payload) is not dict:
        _fail('native ContestRules and contest save required')
    required={'format','version','rules','native_rules','root','participants','nodes','authentication','save_scope'}
    if set(payload)!=required or payload['format']!=CONTEST_FORMAT or type(payload['version']) is not int or payload['version']!=VERSION or payload['authentication']!=AUTH_NOTICE:
        _fail('invalid contest envelope/version/authentication boundary')
    scope=payload['save_scope']
    if type(scope) is not dict or set(scope)!={'current_gameplay','checkpoint_history','omitted_contest_checkpoints','omitted_native_checkpoints'} or scope['current_gameplay'] is not True or scope['checkpoint_history'] is not False or any(type(scope[k]) is not int or scope[k]<0 for k in ('omitted_contest_checkpoints','omitted_native_checkpoints')):
        _fail('invalid contest save scope')
    if payload['rules']!=rules_fingerprint(contest_rules):
        _fail('contest source/profile fingerprint mismatch')
    generated_native=type(payload['native_rules'])is dict and 'generated_weapons' in payload['native_rules']
    if payload['native_rules'] is None:
        if native_rules is not None:
            _fail('standalone contest has no native rule context')
        native_copy=None
    else:
        if type(native_rules) is not _types()[2]:_fail('native contest source/profile fingerprint mismatch')
        if generated_native:
            if set(payload['native_rules'])!={'sha256','profile','file_count','generated_weapons'} or type(payload['native_rules']['sha256'])is not str or re.fullmatch(r'[0-9a-f]{64}',payload['native_rules']['sha256'])is None or type(payload['native_rules']['profile'])is not str or type(payload['native_rules']['file_count'])is not int or payload['native_rules']['file_count']<0 or type(payload['native_rules']['generated_weapons'])is not list or len(payload['native_rules']['generated_weapons'])>MAX_NODES:
                _fail('invalid native generated weapon rules header')
            try:native_copy=__import__('weapon_actions').private_restore_rules(native_rules)
            except (ValueError,KeyError,TypeError) as exc:_fail('invalid native generated weapon declaration: '+str(exc))
        else:
            if payload['native_rules']!=rules_fingerprint(native_rules):_fail('native contest source/profile fingerprint mismatch')
            native_copy=copy(native_rules)
    roots=[]
    for key in ('root','participants'):
        ref=payload[key]
        if type(ref) is not dict or set(ref)!={'$ref'} or type(ref['$ref']) is not str:
            _fail('contest roots must be graph references')
        roots.append(ref['$ref'])
    try:
        decoder=_Decoder(native_copy,payload['nodes'],contest_rules=copy(contest_rules),graph_roots=roots,
                         expected_native_rules=payload['native_rules'] if generated_native else None)
        contest,contestants=(decoder.value(payload[k]) for k in ('root','participants'))
        if type(contest) is not _contest_types()[0] or type(contestants) is not tuple or not contestants or any(type(c) is not _contest_types()[1] for c in contestants) or len(set(contestants))!=len(contestants):
            _fail('invalid contest graph roots')
        if bool(decoder.engine_ids)!=(native_copy is not None):
            _fail('contest native host and source header disagree')
        return contest,contestants
    except StateCodecError:
        raise
    except (TypeError,ValueError,KeyError,AttributeError,OverflowError,RecursionError) as exc:
        raise StateCodecError('malformed or unsupported contest save: '+str(exc)) from exc

def dump_engine(engine):
    import source_selection as SOURCES
    with SOURCES.verification_scope():
        return _dump_engine(engine)
dump_engine.__doc__ = _dump_engine.__doc__


def load_engine(rules, payload):
    import source_selection as SOURCES
    with SOURCES.verification_scope():
        return _load_engine(rules, payload)
load_engine.__doc__ = _load_engine.__doc__


def load_contest(contest_rules,payload,*,native_rules=None):
    import source_selection as SOURCES
    with SOURCES.verification_scope():
        return _load_contest(contest_rules,payload,native_rules=native_rules)
load_contest.__doc__ = _load_contest.__doc__

