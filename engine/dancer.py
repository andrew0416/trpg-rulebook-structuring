"""PTK ch04:2266-2323 Dancer class: printed Ability choice, Dance Moves, Dance Form,
Beguiling Dance, Choreographer, Power Pirouette and Passing Waltz.

Acquisition uses the shared static trainer-feature receipts (the class is a
branched acquisition whose branch is the printed Ability choice).  A Dance
Move is a self-describing move identity (``move/dance:<payload>``) built from
the printed template: the trainer who made it, its name, the fixed stage
benefit, the contest type chosen among the affected stats and, for Beguiling
Dance, the lowered stat.  Rules.move/move_mech/move_id resolve that identity
without a global move registry, so learned lists, grants and saves carry the
definition themselves and the choice can never be changed afterwards.

Dance Form grants the created moves on the trainer's Dance Form source
(while_owned).  Choreographer teaches an own Dance Move to an owned Pokemon
through the shared learning receipt (two Tutor Points, Extended).  Power
Pirouette is a Swift action following the trainer's own Dance Move in the same
turn (scene x2).  Passing Waltz is a triggered 1 AP Free Action resolved inside
the Dance Move's stage application: the trainer chooses (rulings prompt
``passing_waltz``) one ally within 3 m of the dancing user who gains the
stages instead.
"""
from copy import deepcopy
from pathlib import Path
import base64
import json

import common_checks as C
import contest_features as CF
import skill_modifiers as S
import state_grants as G

_data = json.loads((Path(__file__).resolve().parents[1] / 'data/dancer-definitions.json').read_text(encoding='utf8'))
CLASS = _data['rule_source']
CLASS_DEFINITION = _data['class_definition']
DEFINITIONS = _data['features']
RANKS = _data['ranks']
STATS = _data['stats']
CONTEST_TYPES = _data['contest_types_by_stat']
TEMPLATE = _data['dance_move_template']
PRINTED_DANCE_MOVES = tuple(_data['printed_dance_moves'])
SOURCE_SHA256 = _data['source_sha256']
DANCE_FORM = 'feat/댄스-폼'
BEGUILING = 'feat/기만적인-댄스'
PRACTICE = 'feat/댄스-연습'
CHOREOGRAPHER = 'feat/안무가'
PIROUETTE = 'feat/파워-피루엣'
WALTZ = 'feat/패싱-왈츠'
OTHER_DANCER_FEATURES = (BEGUILING, PRACTICE, CHOREOGRAPHER, PIROUETTE, WALTZ)
STATIC_DEFINITIONS = {CLASS: dict(CLASS_DEFINITION), **{uid: dict(row) for uid, row in DEFINITIONS.items()}}
FEATURES = {uid: tuple(row['span']) for uid, row in STATIC_DEFINITIONS.items()}
ENGLISH = {row['english']: uid for uid, row in STATIC_DEFINITIONS.items()}
KEY = 'dancer'                 # trainer.spec: created Dance Moves, last performed Dance Move, Pirouette and Waltz records
STAT_TAG = 'spe'               # every printed Dancer entry carries [+스피드]; Dance Practice's tag stays with its static grant table
DANCE_PREFIX = 'move/dance:'
TEMPLATES = ('form', 'beguiling')
PIROUETTE_OPTIONS = ('confuse_adjacent', 'stage', 'clear')
WALTZ_PROMPT = 'passing_waltz'
STATE_FIELDS = {'version', 'dance_moves', 'last_dance', 'pirouettes', 'waltzes'}


def uid(name):
    return name if name in STATIC_DEFINITIONS else ENGLISH[name]


def _text(value, label):
    if type(value) is not str or not value.strip():
        raise ValueError(label + ' required')
    return value


def _rank(e, actor, skill):
    return S.rank(e.r, actor, skill)[2]


def owns(trainer, feature):
    return trainer.kind == 'trainer' and CF.owned(trainer, feature)


def _any_rank(e, actor, rows):
    return any(_rank(e, actor, skill) >= rank for skill, rank in rows)


def _rank_text(rows):
    return ' or '.join(skill + ' ' + str(rank) for skill, rank in rows)


# ---------------------------------------------------------------- acquisition (shared static receipts)
def _records(actor, feature, *, active=True):
    import trainer_feature_acquisition as TFA
    return [row['static_acquisition'] for _, row, live in TFA._static_records(actor)
            if row['static_acquisition']['feature_id'] == feature and (live or not active)]


def _reference(actor, feature):
    rows = _records(actor, feature)
    if rows:
        return rows[-1]['request_id']
    if owns(actor, feature):
        return feature
    raise ValueError('actual acquired Dancer prerequisite required: ' + feature)


def acquisition_snapshot(engine, actor, feature, branch=None):
    import acquired_features as ACQUIRED
    d = STATIC_DEFINITIONS[feature]
    if feature == CLASS:
        if branch not in CLASS_DEFINITION['abilities']:
            raise ValueError('Dancer requires one printed Ability choice: ' + ' or '.join(CLASS_DEFINITION['abilities']))
        if ACQUIRED.owned_rule_count(actor, CLASS) or actor.spec.get('feature_choices', {}).get(CLASS):
            raise ValueError('Dancer class is already acquired; its Ability choice cannot be repeated')
        pre = CLASS_DEFINITION['prerequisites']
        return {'branch': branch, 'ranks': {skill: _rank(engine, actor, skill) for skill, _ in pre['skills'] + pre['any_skills']}}
    if branch is not None:
        raise ValueError('this Dancer Feature has no acquired branch')
    snapshot = {'parents': {parent: _reference(actor, parent) for parent in d['parents']}}
    if d.get('any_skills'):
        snapshot['ranks'] = {skill: _rank(engine, actor, skill) for skill, _ in d['any_skills']}
    return snapshot


def qualification(actor, feature, snapshot, prerequisite_source):
    import acquisition_qualification as Q
    d = STATIC_DEFINITIONS[feature]
    if prerequisite_source is not None or type(snapshot) is not dict:
        raise ValueError('exact Dancer acquisition observations required')
    checks = [Q.check('trainer', 'prerequisite', actor.kind == 'trainer', 'actual Trainer required')]
    if feature == CLASS:
        pre = CLASS_DEFINITION['prerequisites']
        if set(snapshot) != {'branch', 'ranks'} or set(snapshot['ranks']) != {skill for skill, _ in pre['skills'] + pre['any_skills']}:
            raise ValueError('exact Dancer acquisition observations required')
        for value in snapshot['ranks'].values():
            C.integer(value, 'Dancer skill rank', 0)
        checks.append(Q.check('ability', 'selection', snapshot['branch'] in CLASS_DEFINITION['abilities'], 'Dancer requires one printed Ability choice'))
        checks.append(Q.check('acrobatics', 'prerequisite', all(snapshot['ranks'][skill] >= rank for skill, rank in pre['skills']), 'Dancer requires Novice Acrobatics'))
        checks.append(Q.check('athletics_or_charm', 'prerequisite', any(snapshot['ranks'][skill] >= rank for skill, rank in pre['any_skills']), 'Dancer requires Novice Athletics or Charm'))
        return Q.require(feature, 'native', 'acquire', checks)
    fields = {'parents'} | ({'ranks'} if d.get('any_skills') else set())
    if set(snapshot) != fields or type(snapshot['parents']) is not dict or set(snapshot['parents']) != set(d['parents']):
        raise ValueError('printed Dancer prerequisites required')
    for parent, reference in snapshot['parents'].items():
        if reference != parent and not any(row['request_id'] == reference for row in _records(actor, parent, active=False)):
            raise ValueError('actual historical Dancer prerequisite acquisition required')
        if reference == parent and not owns(actor, parent):
            raise ValueError('actual acquired Dancer prerequisite required: ' + parent)
    if d.get('any_skills'):
        if type(snapshot['ranks']) is not dict or set(snapshot['ranks']) != {skill for skill, _ in d['any_skills']}:
            raise ValueError('exact Dancer skill observations required')
        for value in snapshot['ranks'].values():
            C.integer(value, 'Dancer skill rank', 0)
        checks.append(Q.check('skill_rank', 'prerequisite', any(snapshot['ranks'][skill] >= rank for skill, rank in d['any_skills']),
                              d['english'] + ' requires its printed skill rank: ' + _rank_text(d['any_skills'])))
    return Q.require(feature, 'native', 'acquire', checks)


def class_source_id(trainer, ability):
    return 'feature:' + trainer.entity_id + ':' + CLASS + ':' + ability


def acquisition_source_id(trainer, feature, branch=None):
    if feature == CLASS:
        return class_source_id(trainer, branch if branch is not None else chosen_ability(trainer))
    return 'feature:' + trainer.entity_id + ':' + feature


def after_acquire(engine, trainer, feature, branch=None):
    """acquire_static apply: the class owns its chosen Ability on the branch source; every entry except Dance Practice
    applies its printed [+스피드] as the source-owned acquisition stat tag (Rider/Athlete precedent)."""
    st = state(trainer, create=True)
    sid = acquisition_source_id(trainer, feature, branch)
    if sid not in G.state(trainer)['sources']:
        raise ValueError('Dancer acquisition source missing')
    if feature == CLASS:
        G.grant(trainer, 'abilities', branch, sid, 'feature', owner_id=trainer.entity_id, lifetime='while_owned', rule_id=CLASS, tutor_points=0)
        G.state(trainer)['sources'][sid]['dancer_class'] = {'ability': branch, 'clause_id': CLASS_DEFINITION['clause_id']}
        engine.register_abilities_one(trainer, branch)
    if feature == PRACTICE:
        import items
        items.register_feats(engine, trainer)   # the printed +Speed tag and lesson owner of Dance Practice stay with their existing table
    else:
        G.stat(trainer, STAT_TAG, 1, sid, operation_id='acquisition_stat_tag')
    return st


def stat_tag_operation(trainer, feature):
    """The source-owned [+스피드] operation of an acquired Dancer entry (None before acquisition or for Dance Practice)."""
    try:
        sid = acquisition_source_id(trainer, feature)
    except ValueError:
        return None
    return trainer.spec.get(G.KEY, {}).get('stat_sources', {}).get(STAT_TAG, {}).get('sources', {}).get(sid, {}).get('acquisition_stat_tag')


def chosen_ability(trainer):
    """The acquired Dancer Ability choice, or None for a sheet without the acquisition branch."""
    choices = trainer.spec.get('feature_choices', {}).get(CLASS)
    if choices is None:
        return None
    if not isinstance(choices, list) or len(choices) != 1 or choices[0] not in CLASS_DEFINITION['abilities']:
        raise ValueError('Dancer keeps exactly one printed Ability choice')
    return choices[0]


# ---------------------------------------------------------------- state and use prerequisites
def state(trainer, create=False):
    st = trainer.spec.get(KEY)
    if st is None:
        if not create:
            return None
        st = {'version': 1, 'dance_moves': [], 'last_dance': None, 'pirouettes': [], 'waltzes': []}
        trainer.spec[KEY] = st
    if type(st) is not dict or st.get('version') != 1 or set(st) != STATE_FIELDS:
        raise ValueError('unsupported Dancer state')
    return st


def qualify(e, trainer, feature):
    """Printed prerequisites against the actual sheet: parent Features/class and skill ranks, re-validated on every use."""
    d = STATIC_DEFINITIONS[feature]
    if trainer.kind != 'trainer':
        raise ValueError('actual Dancer trainer required')
    if not owns(trainer, feature):
        raise ValueError('actual acquired ' + d['english'] + ' required')
    for parent in d.get('parents', ()):
        qualify(e, trainer, parent)
    if feature != CLASS and d.get('any_skills') and not _any_rank(e, trainer, d['any_skills']):
        raise ValueError(d['english'] + ' requires its printed skill rank: ' + _rank_text(d['any_skills']))
    return d


def _outside(e):
    if e.encounter_active:
        raise ValueError('this Dancer Extended action runs outside an active encounter')


def _owned_pokemon(e, trainer, pokemon):
    import world_entities as W
    W.require_actors(e, trainer, pokemon)
    if pokemon.kind != 'pokemon' or pokemon.spec.get('trainer_id') != trainer.entity_id:
        raise ValueError('actual owned Pokemon required')


def _swift(e, t, feature):
    import action_lifecycle as A
    import turn as TURN
    if e.encounter_active:
        if not TURN.spend(e, t, 'swift', feature):
            raise ValueError(STATIC_DEFINITIONS[feature]['english'] + ' Swift action unavailable')
    else:
        if not TURN.can_act(e, t) or not A.ordinary_permission(e, t) or not A.status_permission(e, t, 'swift'):
            raise ValueError('Swift action unavailable')
        A.record_action(e, t, 'swift')


# ---------------------------------------------------------------- Dance Move identity (C04-096 template)
def _validate_shape(row):
    stages = row['stages']
    if type(row['name']) is not str or not row['name'].strip() or row['name'] != row['name'].strip():
        raise ValueError('Dance Move name required')
    if row['template'] not in TEMPLATES:
        raise ValueError('Dance Move template must be form or beguiling')
    if row['contest_type'] not in CONTEST_TYPES.values():
        raise ValueError('Dance Move contest type must be one of ' + ', '.join(CONTEST_TYPES.values()))
    if type(stages) is not dict or any(stat not in STATS or type(delta) is not int for stat, delta in stages.items()):
        raise ValueError('Dance Move stages must name combat stats with whole deltas')
    if row['template'] == 'form':
        pattern = sorted(stages.values())
        if row['lowered'] is not None or pattern not in [sorted(p) for p in TEMPLATE['stage_patterns']]:
            raise ValueError('Dance Move must raise one stat by +2 or two different stats by +1')
        affected = set(stages)
    else:
        if stages or row['lowered'] not in STATS:
            raise ValueError('Beguiling Dance Move lowers exactly one chosen combat stat')
        affected = {row['lowered']}
    if row['contest_type'] not in {CONTEST_TYPES[stat] for stat in affected}:
        raise ValueError('Dance Move contest type must match a stat the move affects')
    return row


def _payload(row):
    return [row['trainer_id'], row['name'], row['template'],
            ','.join(stat + ('%+d' % delta) for stat, delta in sorted(row['stages'].items())),
            row['contest_type'], row['lowered'] or '']


def dance_move_id(row):
    raw = json.dumps(_payload(row), ensure_ascii=False, separators=(',', ':')).encode('utf8')
    return DANCE_PREFIX + base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')


def dance_instance(rules, mid):
    """A narrow move identity adapter; never adds a global move definition."""
    if not isinstance(mid, str) or not mid.startswith(DANCE_PREFIX):
        return None
    token = mid[len(DANCE_PREFIX):]
    try:
        values = json.loads(base64.urlsafe_b64decode(token + '=' * (-len(token) % 4)))
    except Exception as exc:
        raise ValueError('invalid Dance Move identity') from exc
    if not isinstance(values, list) or len(values) != 6 or any(not isinstance(value, str) for value in values):
        raise ValueError('exact Dance Move identity required')
    trainer_id, name, template, stage_text, contest_type, lowered = values
    if not trainer_id:
        raise ValueError('Dance Move identity needs its creating trainer')
    stages = {}
    for part in [p for p in stage_text.split(',') if p]:
        stat, delta = part[:3], part[3:]
        if stat not in STATS or delta not in ('+1', '+2') or stat in stages:
            raise ValueError('exact Dance Move stage identity required')
        stages[stat] = int(delta)
    row = {'trainer_id': trainer_id, 'name': name, 'template': template, 'stages': stages,
           'contest_type': contest_type, 'lowered': lowered or None}
    _validate_shape(row)
    if dance_move_id(row) != mid:
        raise ValueError('noncanonical Dance Move identity')
    if rules._selected_rule(DANCE_FORM) != DANCE_FORM:
        raise ValueError('selected Dance Form source required')
    return row


def is_dance_move(rules, mid):
    return mid in PRINTED_DANCE_MOVES or dance_instance(rules, mid) is not None


def range_text(row):
    return TEMPLATE['range'] if row['template'] == 'form' else DEFINITIONS[BEGUILING]['template']['range']


def definition(rules, mid, row):
    """The printed template: Normal, EOT, Status, Self (or the Beguiling range/AC), Get Ready! (or Excitement)."""
    beguiling = DEFINITIONS[BEGUILING]['template']
    if row['template'] == 'form':
        effect = '사용자의 ' + ', '.join(STATS[stat] + ' 전투단계를 %+d' % delta for stat, delta in row['stages'].items()) + ' 만큼 상승시킵니다.'
        contest = row['contest_type'] + ' - ' + TEMPLATE['contest_effect']
        ac = TEMPLATE['ac']
    else:
        effect = '대상의 ' + STATS[row['lowered']] + ' 전투단계를 %d 만큼 하락시킵니다.' % beguiling['delta']
        contest = row['contest_type'] + ' - ' + beguiling['contest_effect']
        ac = beguiling['ac']
    return {'id': mid, 'name': row['name'], 'eng': None, 'type': TEMPLATE['type'], 'class': TEMPLATE['class'], 'damage_base': None,
            'ac': ac, 'frequency': TEMPLATE['frequency'], 'range': range_text(row), 'effect': effect, 'contest': contest,
            'homebrew': False, 'dancer_instance': deepcopy(row)}


def mechanics(rules, row):
    beguiling = DEFINITIONS[BEGUILING]['template']
    if row['template'] == 'form':
        effects = [{'type': 'stage_change', 'stat': stat, 'delta': delta, 'target': 'self', '_src': 'dancer:' + row['name']} for stat, delta in row['stages'].items()]
    else:
        effects = [{'type': 'stage_change', 'stat': row['lowered'], 'delta': beguiling['delta'], 'target': 'target', '_src': 'dancer:' + row['name']}]
    return rules.flatten_effects(effects)


def range_spec(move, result):
    """weapon_actions.range_spec: a Dance Move's printed range is parsed from its own template."""
    row = move.get('dancer_instance') if isinstance(move, dict) else None
    if row is None:
        return result
    import custom_species as CUSTOM
    return CUSTOM.parse_range(range_text(row))


def created_moves(trainer):
    st = state(trainer)
    return [] if st is None else list(st['dance_moves'])


def allowance(trainer):
    d = DEFINITIONS[DANCE_FORM]
    return d['base_dance_moves'] + d['per_other_dancer_feature'] * sum(1 for feature in OTHER_DANCER_FEATURES if owns(trainer, feature))


def _form_source(e, trainer):
    import trainer_retraining as RETRAINING
    return RETRAINING.owned_source(e, trainer, DANCE_FORM)


def own_dance_move(engine, trainer, move):
    """One of the trainer's created Dance Moves, by identity or by its name."""
    for record in created_moves(trainer):
        if move in (record['id'], record['name']):
            row = dance_instance(engine.r, record['id'])
            if row['trainer_id'] != trainer.entity_id:
                raise ValueError('Dance Move was created by another trainer')
            return record['id']
    raise ValueError('actual Dance Move created by this trainer required')


def create_dance_move(engine, trainer, *, name, contest_type, stages=None, template='form', lowered=None, reason):
    """Dance Form: create and learn a Dance Move (2 + one per other owned Dancer Feature); choices are fixed in its identity."""
    import world_entities as W
    W.require_actors(engine, trainer)
    qualify(engine, trainer, DANCE_FORM)
    _text(reason, 'Dance Move creation reason')
    _text(name, 'Dance Move name')
    if template == 'beguiling':
        qualify(engine, trainer, BEGUILING)
    row = _validate_shape({'trainer_id': trainer.entity_id, 'name': name.strip(), 'template': template,
                           'stages': dict(stages or {}), 'contest_type': contest_type, 'lowered': lowered})
    mid = dance_move_id(row)
    if engine.r.move_id(row['name']) is not None:
        raise ValueError('Dance Move name collides with an existing Move')
    existing = created_moves(trainer)
    if any(record['name'] == row['name'] or record['id'] == mid for record in existing):
        raise ValueError('Dance Move name is already used by this trainer')
    cap = allowance(trainer)
    if len(existing) >= cap:
        raise ValueError('Dance Form allows ' + str(cap) + ' Dance Moves with the currently owned Dancer Features')
    def apply(e, t):
        st = state(t, create=True)
        sid = _form_source(e, t)
        G.grant_moves(t, [mid], sid, 'feature', owner_id=t.entity_id, lifetime='while_owned', rule_id=DANCE_FORM, tutor_points=0)
        record = {'id': mid, **deepcopy(row), 'allowance': cap, 'other_features': [f for f in OTHER_DANCER_FEATURES if owns(t, f)],
                  'created_at': e.elapsed_seconds, 'reason': reason, 'source_id': sid,
                  'clause_id': DEFINITIONS[DANCE_FORM]['clause_id'] if template == 'form' else DEFINITIONS[BEGUILING]['clause_id']}
        st['dance_moves'].append(record)
        e.log('  ' + t.name + ': 댄스 폼 - ' + row['name'] + ' 생성·학습 (' + range_text(row) + ')', DANCE_FORM)
        return deepcopy(record)
    return G.transition(engine, trainer, apply)


# ---------------------------------------------------------------- Choreographer (other-category row, needed by the class)
def choreograph(engine, trainer, pokemon, move, *, seconds, reason):
    """Extended: the owned Pokemon loses two Tutor Points and learns one of the trainer's own Dance Moves (repeatable)."""
    import world_entities as W
    import pokemon_teaching as TEACH
    import pokemon_activities as P
    W.require_actors(engine, trainer, pokemon)
    d = qualify(engine, trainer, CHOREOGRAPHER)
    _text(reason, 'teaching reason')
    C.integer(seconds, 'actual Extended action seconds', 1)
    _outside(engine)
    _owned_pokemon(engine, trainer, pokemon)
    P._pokemon(pokemon)
    mid = own_dance_move(engine, trainer, move)
    if TEACH._balance(pokemon.spec) < d['tutor_points']:
        raise ValueError('target needs two actual Tutor Points')
    def apply(e, t, q):
        import move_state as M
        import learning_grant as LEARNING
        import activity_jobs as JOBS
        import turn as TURN
        if mid in M.known(e.r, q.spec):
            raise ValueError('Pokemon already learned that Dance Move')
        candidate = deepcopy(q.spec)
        LEARNING.learn_moves(e.r, candidate, candidates=[mid], selected=[mid], method='feature', source=CHOREOGRAPHER, reason=reason,
                             provider=t.entity_id, paid_tp=d['tutor_points'], details={'dancer_feature': CHOREOGRAPHER, 'seconds': seconds})
        M.validate_spec(e.r, candidate)
        if not TURN.spend(e, t, 'extended', CHOREOGRAPHER):
            raise ValueError('Choreographer Extended action unavailable')
        JOBS.run_fixed(e, t, (q,), seconds=seconds, source=CLASS, context={'move_id': mid, 'feature': CHOREOGRAPHER})
        for field in ('move_learning', 'move_learning_log'):
            if field in candidate:
                q.spec[field] = candidate[field]
        G.set_baseline(q, 'moves', candidate['moves'])
        TEACH._debit_points(q.spec, d['tutor_points'])
        e.log('  ' + t.name + ': 안무가 - ' + q.name + ' learns ' + mid + ' (' + str(d['tutor_points']) + ' TP)', CHOREOGRAPHER)
        return {'move': mid, 'point_cost': d['tutor_points'], 'seconds': seconds, 'classification': M.describe(e.r, q.spec)['classifications'][mid]}
    return G.transition(engine, trainer, apply, participants=(pokemon,), include_rulings=True)


# ---------------------------------------------------------------- performed Dance Moves (trigger records)
def after_move_use(engine, attacker, move_id, move, mm):
    """engine.use_move after the ordinary activation commits: a Dancer performed a Dance Move."""
    if attacker.kind != 'trainer' or not is_dance_move(engine.r, move_id):
        return None
    st = state(attacker)
    if st is None:
        if not owns(attacker, CLASS):
            return None
        st = state(attacker, create=True)
    raised = sorted({effect['stat'] for effect in mm.get('effects_exec', [])
                     if effect.get('type') == 'stage_change' and effect.get('target') == 'self'
                     and type(effect.get('delta')) is int and effect['delta'] > 0 and effect.get('stat') in STATS})
    st['last_dance'] = {'move_id': move_id, 'round': engine.round_no, 'turn_serial': attacker.custom_conditions.get('combat_turn_serial', 0),
                        'at': engine.elapsed_seconds, 'encounter': bool(engine.encounter_active), 'raised': raised, 'pirouette': None}
    return st['last_dance']


def _current_dance(engine, trainer, last):
    if engine.encounter_active:
        return (last['encounter'] and last['round'] == engine.round_no
                and last['turn_serial'] == trainer.custom_conditions.get('combat_turn_serial', 0))
    return not last['encounter'] and last['at'] == engine.elapsed_seconds


def _body_cells(actor):
    import body_state as BODY
    try:
        return set(BODY.cells(actor))
    except ValueError:
        return {tuple(actor.pos)} if getattr(actor, 'pos', None) is not None else set()


def _cells_within(engine, actor, radius):
    cells = set()
    for cell in _body_cells(actor):
        cells |= set(engine.grid.burst(tuple(cell), radius)) | {tuple(cell)}
    return cells


def _distance(engine, left, right):
    from grid import cheb
    a, b = _body_cells(left), _body_cells(right)
    if not a or not b:
        return None
    return min(cheb(x, y) for x in a for y in b)


def _clear_condition(engine, actor, condition):
    cured = False
    if condition in actor.custom_conditions and condition not in actor.conditions:
        actor.custom_conditions.pop(condition)
        cured = True
    if condition in actor.conditions:
        engine.cure_status(actor, condition)
        cured = cured or condition not in actor.conditions
    return cured


def power_pirouette(engine, trainer, option, *, stat=None):
    """Scene x2 Swift action after your own Dance Move this turn: confuse adjacent, +1 CS to an unraised stat, or clear traps/bindings."""
    import world_entities as W
    import frequency as F
    import effects as FX
    import hazard_state as HAZARDS
    W.require_actors(engine, trainer)
    d = qualify(engine, trainer, PIROUETTE)
    if option not in PIROUETTE_OPTIONS:
        raise ValueError('Power Pirouette option must be one of ' + ', '.join(PIROUETTE_OPTIONS))
    st = state(trainer)
    last = None if st is None else st['last_dance']
    if last is None or not _current_dance(engine, trainer, last):
        raise ValueError('Power Pirouette triggers only when you have just performed a Dance Move')
    if last.get('pirouette') is not None:
        raise ValueError('Power Pirouette was already used for this Dance Move')
    if option == 'stage':
        if stat not in STATS:
            raise ValueError('Power Pirouette needs one combat stat')
        if stat in last['raised']:
            raise ValueError('Power Pirouette cannot raise a stat the triggering Dance Move raised')
    elif stat is not None:
        raise ValueError('only the stage option takes a stat')
    if option == 'clear' and engine.grid is None:
        raise ValueError('Power Pirouette trap removal needs the actual map')
    def apply(e, t):
        if not F.activation_allowed(t, PIROUETTE, d['frequency'], engine=e):
            raise ValueError('Power Pirouette scene uses exhausted')
        _swift(e, t, PIROUETTE)
        F.consume_activation(t, PIROUETTE, d['frequency'], engine=e)
        s = state(t)
        record = {'option': option, 'move_id': s['last_dance']['move_id'], 'round': e.round_no, 'at': e.elapsed_seconds, 'clause_id': d['clause_id']}
        if option == 'confuse_adjacent':
            targets = [c for c in W.actor_index(e).values() if c is not t and c.on_field and not c.fainted and not getattr(c, 'captured', False)
                       and getattr(c, 'pos', None) is not None and e.adjacent(t, c)]
            record['targets'] = {c.entity_id: bool(e.apply_status(c, d['options']['confuse_adjacent']['status'], source=PIROUETTE, applied_by=t)) for c in targets}
        elif option == 'stage':
            FX.apply_stage_changes(e, t, t, {stat: d['options']['stage']['delta']}, source_id=PIROUETTE)
            record['stat'] = stat
        else:
            cells = _cells_within(e, t, d['options']['clear']['trap_radius'])
            record['traps_removed'] = HAZARDS.remove_cells(e, [cell for cell in HAZARDS.ensure(e) if tuple(cell) in cells])
            record['cured'] = [condition for condition in d['options']['clear']['conditions'] if _clear_condition(e, t, condition)]
        s['last_dance']['pirouette'] = option
        s['pirouettes'].append(record)
        e.log('  ' + t.name + ': 파워 피루엣 - ' + option, PIROUETTE)
        return deepcopy(record)
    return G.transition(engine, trainer, apply, include_rulings=True, include_grid=(option == 'clear'))


# ---------------------------------------------------------------- Passing Waltz (triggered inside the Dance Move's stage application)
def _ability_keys(rules, names):
    return {G._ability_key(rules, name) for name in names}


def _waltz_trainer(engine, user):
    import world_entities as W
    if user.kind == 'trainer':
        trainer = user
    elif user.kind == 'pokemon':
        trainer = W.actor_index(engine).get(user.spec.get('trainer_id'))
        if trainer is None or trainer.kind != 'trainer':
            return None
        wanted = _ability_keys(engine.r, DEFINITIONS[WALTZ]['pokemon_abilities'])
        if not (_ability_keys(engine.r, user.abilities) & wanted):
            return None
    else:
        return None
    if not owns(trainer, WALTZ):
        return None
    try:
        qualify(engine, trainer, WALTZ)
    except ValueError:
        return None
    return trainer


def _use_key(engine, user, source_id, ctx):
    return {'completion': ctx.get('move_completion'), 'move_id': source_id, 'user_id': user.entity_id, 'round': engine.round_no,
            'at': engine.elapsed_seconds, 'turn_serial': user.custom_conditions.get('combat_turn_serial', 0)}


def _waltz_candidates(engine, user, distance):
    import world_entities as W
    if engine.grid is None:
        return []
    return [c for c in W.actor_index(engine).values()
            if c is not user and c.on_field and not c.fainted and not getattr(c, 'captured', False)
            and user.side is not None and c.side == user.side
            and (_distance(engine, user, c) is not None and _distance(engine, user, c) <= distance)]


def stage_recipient(engine, source_actor, target, changes, source_id, ctx):
    """effects.apply_stage_changes: Passing Waltz moves a Dance Move's own stage gains to one chosen ally within 3 m."""
    import world_entities as W
    if target is not source_actor or not isinstance(ctx, dict) or ctx.get('move') is None or not changes:
        return target
    if any(type(delta) is not int or delta <= 0 for delta in changes.values()) or not is_dance_move(engine.r, source_id):
        return target
    trainer = _waltz_trainer(engine, source_actor)
    if trainer is None:
        return target
    d = DEFINITIONS[WALTZ]
    st = state(trainer, create=True)
    key = _use_key(engine, source_actor, source_id, ctx)
    index = W.actor_index(engine)
    for row in st['waltzes']:
        if row['use'] == key:
            ally = index.get(row['ally_id']) if row['ally_id'] else None
            return ally if ally is not None else target
    candidates = _waltz_candidates(engine, source_actor, d['ally_range'])
    ids = [c.entity_id for c in candidates]
    import action_points as AP
    import action_lifecycle as A
    import body_modes as BODY_MODES
    record = {'use': key, 'ally_id': None, 'trainer_id': trainer.entity_id, 'candidates': ids, 'clause_id': d['clause_id']}
    if not candidates or AP.available(trainer) < d['ap'] or not BODY_MODES.permits(trainer, 'free'):
        record['declined'] = 'no ally within range, no AP or no Free action permission'
        st['waltzes'].append(record)
        return target
    choice = engine.rulings.decide({'type': WALTZ_PROMPT, 'unit': WALTZ, 'actor': trainer.name, 'user': source_actor.entity_id, 'move': source_id,
                                    'targets': ids, 'text': 'Passing Waltz: choose one ally within 3 m of the dancing user, or decline.'})
    if choice is None or choice is False:
        record['declined'] = 'player declined'
        st['waltzes'].append(record)
        return target
    if type(choice) is not str or choice not in ids:
        # The Dance Move's own effect is already resolving; an answer outside the observed
        # candidates cannot abort it, so the Waltz does not activate and the reason is kept.
        record['declined'] = 'invalid choice: Passing Waltz needs one ally within 3 m of the dancing user'
        record['answer'] = choice if isinstance(choice, (str, int, float, bool)) else repr(choice)
        st['waltzes'].append(record)
        engine.log('  ' + trainer.name + ': 패싱 왈츠 미발동 - 3미터 이내의 동료가 아님', WALTZ)
        return target
    A.triggered_free_action(engine, trainer, WALTZ)
    AP.charge(trainer, d['ap'], mode='spend')
    ally = index[choice]
    record.update(ally_id=choice, ap=d['ap'], round=engine.round_no, at=engine.elapsed_seconds)
    st['waltzes'].append(record)
    engine.log('  ' + trainer.name + ': 패싱 왈츠 - ' + source_actor.name + '의 댄스 기술 전투단계를 ' + ally.name + '에게', WALTZ)
    return ally


# ---------------------------------------------------------------- world validation
def validate(engine):
    import world_entities as W
    index = W.actor_index(engine)
    for actor in index.values():
        st = actor.spec.get(KEY)
        if st is not None:
            if actor.kind != 'trainer':
                raise ValueError('Dancer state requires a trainer')
            state(actor)
            names = set()
            granted = {mid for row in actor.spec.get(G.KEY, {}).get('sources', {}).values() if row.get('rule_id') == DANCE_FORM
                       for mid in row.get('grants', {}).get('moves', [])}
            for record in st['dance_moves']:
                if type(record) is not dict:
                    raise ValueError('invalid Dance Move record')
                row = dance_instance(engine.r, record['id'])
                keys = ('name', 'template', 'stages', 'contest_type', 'lowered')
                if row['trainer_id'] != actor.entity_id or {k: record.get(k) for k in keys} != {k: row[k] for k in keys} or record['name'] in names:
                    raise ValueError('Dance Move record differs from its fixed identity')
                names.add(record['name'])
                C.integer(record.get('allowance'), 'Dance Form allowance', DEFINITIONS[DANCE_FORM]['base_dance_moves'])
                if type(record.get('other_features')) is not list or any(f not in OTHER_DANCER_FEATURES for f in record['other_features']):
                    raise ValueError('Dance Move allowance evidence must name Dancer Features')
                if record['template'] == 'beguiling' and BEGUILING not in record['other_features']:
                    raise ValueError('Beguiling Dance template requires the Feature at creation')
                if owns(actor, DANCE_FORM) and record['id'] not in granted:
                    raise ValueError('created Dance Move lost its Dance Form grant')
            last = st['last_dance']
            if last is not None and (type(last) is not dict or not is_dance_move(engine.r, last.get('move_id')) or last.get('pirouette') not in (None, *PIROUETTE_OPTIONS)):
                raise ValueError('invalid last Dance Move record')
            for row in st['pirouettes']:
                if type(row) is not dict or row.get('option') not in PIROUETTE_OPTIONS or not is_dance_move(engine.r, row.get('move_id')):
                    raise ValueError('invalid Power Pirouette record')
            for row in st['waltzes']:
                if type(row) is not dict or type(row.get('use')) is not dict or row.get('trainer_id') != actor.entity_id or not is_dance_move(engine.r, row['use'].get('move_id')):
                    raise ValueError('invalid Passing Waltz record')
                if row.get('ally_id') is not None and row['ally_id'] not in row.get('candidates', []):
                    raise ValueError('Passing Waltz ally must be one of its observed candidates')
        if actor.kind == 'trainer':
            ability = chosen_ability(actor) if owns(actor, CLASS) else None
            if ability is not None:
                row = actor.spec.get(G.KEY, {}).get('sources', {}).get(class_source_id(actor, ability))
                if row is None or row.get('grants', {}).get('abilities') != [ability] or row.get('rule_id') != CLASS:
                    raise ValueError('Dancer Ability grant must follow the acquired class choice')
            for feature in STATIC_DEFINITIONS:
                if feature == PRACTICE or not _records(actor, feature):
                    continue
                if stat_tag_operation(actor, feature) != {'delta': 1, 'minimum': None}:
                    raise ValueError('acquired Dancer entry requires its source-owned [+스피드] acquisition tag: ' + feature)
        elif actor.kind == 'pokemon':
            for mid in actor.spec.get('moves', []):
                if isinstance(mid, str) and mid.startswith(DANCE_PREFIX):
                    row = dance_instance(engine.r, mid)
                    record = actor.spec.get('move_learning', {}).get(mid)
                    if not isinstance(record, dict) or record.get('source') != CHOREOGRAPHER or record.get('teacher_id') != row['trainer_id']:
                        raise ValueError('Pokemon Dance Move requires its Choreographer teaching receipt')
    return True
