"""Source-bound new acquisitions; declared sheets remain existing ownership.

Receipts live on the existing source-grant records. Qualification stores facts
from acquisition, not a continuing requirement to retain old skill ranks.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import csv
import json

import acquisition_qualification as Q
import state_grants as G
import source_context as SOURCES

DOCUMENT = json.loads((Path(__file__).resolve().parents[1] / 'data/native-acquisition-adapters.json').read_text(encoding='utf-8'))
DEFINITIONS = DOCUMENT['definitions']
KEY = 'native_acquisition'
LABEL = 'trainer-feature/native-acquisition/v1'
RESILIENCE = 'gift/축복받은-회복력'
INSIGHT = 'gift/위대한-존재의-통찰력'
PSYSTRIKE = 'feat/약속된-기프트-사이코브레이크'
JOURNEY = 'feat/영웅의-여행'
ROUTES = {'messiah': 'feat/나의-이름으로', 'contractor': 'feat/흔적-마스터리'}


def _digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _text(value, label):
    if type(value) is not str or not value.strip():
        raise ValueError('nonempty ' + label + ' required')
    return value


def _source(rules, uid):
    definition = DEFINITIONS[uid]
    for reference in [definition['source'], *DOCUMENT['shared_sources']]:
        content = SOURCES.verified_source(rules, reference, label='native acquisition')
        if 'record' in reference:
            rows = list(csv.reader(content.decode('utf-8-sig').splitlines(keepends=True)))
            cells = [rows[reference['record'] - 1][column - 1] for column in reference['columns']]
            if cells != reference['cells'] or _digest(cells) != reference['cell_sha256']:
                raise ValueError('native acquisition source cells changed')
        if 'span' in reference:
            start, end = reference['span']
            excerpt = '\n'.join(content.decode('utf-8-sig').splitlines()[start - 1:end])
            if sha256(excerpt.encode()).hexdigest() != reference['excerpt_sha256']:
                raise ValueError('native acquisition source excerpt changed')
    # Explicit CSV identities have no Markdown unit to resolve. Admit their
    # hash-pinned source through the same profile filter, including exact-ID
    # exclusion, before consulting any existing effect dependencies.
    rules.ruleset.require({'id': uid, 'title': definition['source'].get('cells', [uid])[0],
        'source': definition['source']})
    selected = definition.get('selected_id')
    if selected and rules._selected_rule(selected) != selected:
        raise ValueError('selected source needs its own acquisition adapter')
    if definition.get('static_row'):
        import static_feature_state_grants as STATIC
        if not STATIC._row_enabled(rules, STATIC.rules(rules)[definition['static_row']]):
            raise ValueError('native acquisition source or effect dependency is excluded')
    return dict(deepcopy(definition['source']), clause_id=definition['clause_id'])


def _count(actor, uid):
    import acquired_features as A
    if uid.startswith('C2CSV/'):
        import static_feature_state_grants as STATIC
        return sum(STATIC.identity(actor.r, value) == uid
                   for field in ('feats', 'classes') for value in actor.spec.get(field, []))
    if uid.startswith('supp-fantasy/'):
        if actor.r._selected_rule(uid) != uid:
            raise ValueError('selected prerequisite class needs its own source')
        title = actor.r.selection.units[uid]['title']
        aliases = {uid, title, title.split(': ', 1)[-1]}
        return sum(value in aliases for field in ('classes', 'feats') for value in actor.spec.get(field, []))
    if uid.startswith(('gift/', 'technique/')):
        field = 'gifts' if uid.startswith('gift/') else 'techniques'
        unit = actor.r.selection.units[uid]
        aliases = {uid, unit.get('title'), unit.get('eng')}
        return sum(value in aliases for value in actor.spec.get(field, []))
    return A.owned_rule_count(actor, uid)


def _rows(actor):
    state = actor.spec.get(G.KEY, {})
    rows = [(sid, row, True) for sid, row in state.get('sources', {}).items()]
    rows.extend((entry['source_id'], entry['record'], False) for entry in state.get('ended_sources', []))
    return [(sid, row, active) for sid, row, active in rows if KEY in row]


def _sid(actor, uid):
    definition = DEFINITIONS[uid]
    if definition.get('static_row'):
        import static_feature_state_grants as STATIC
        return STATIC._source(actor, definition['static_row'])
    return 'feature:' + actor.entity_id + ':' + uid


def _selection(uid, selection):
    definition = DEFINITIONS[uid]
    kind = definition['kind']
    if kind == 'blessing':
        if type(selection) is not dict or set(selection) != {'role', 'grant_rank', 'slot', 'configuration', 'permission', 'waivers'}:
            raise ValueError('exact native Blessing role, grant slot, configuration and permission required')
        role = selection['role']
        if type(role) is not str or role not in ROUTES:
            raise ValueError('explicit native Blessing role route required')
        if type(selection['grant_rank']) is not int or not 3 <= selection['grant_rank'] <= 4:
            raise ValueError('native rank3 Blessing needs a rank3 or rank4 grant')
        maximum = 1 if role == 'messiah' else 2
        if type(selection['slot']) is not int or not 1 <= selection['slot'] <= maximum:
            raise ValueError('Blessing grant slot outside selected role source')
        if type(selection['configuration']) is not dict:
            raise ValueError('actual native Blessing configuration required')
        if uid == INSIGHT:
            expected = {'role': '메시아' if role == 'messiah' else '계약자'}
            if selection['configuration'] != expected:
                raise ValueError('Insight configuration contradicts granting role')
        elif selection['configuration'].get('role') != role:
            raise ValueError('Resilience configuration contradicts granting role')
        if uid == RESILIENCE:
            eligible = selection['configuration'].get('eligible_types')
            if type(eligible) is not list or any(type(value) is not str for value in eligible):
                raise ValueError('actual patron resistance types required')
            selection = deepcopy(selection)
            selection['configuration']['eligible_types'] = sorted(eligible)
    elif kind == 'exalted':
        if type(selection) is not dict or set(selection) != {'permission', 'waivers'}:
            raise ValueError('exact Exalted Gift permission and scoped waivers required')
    elif definition.get('choices') is not None:
        if type(selection) is not dict or set(selection) != {'choice', 'waivers'}:
            raise ValueError('exact acquisition choice and scoped waivers required')
        choice = selection['choice']
        if uid == 'edge/여행자':
            if type(choice) is not list or any(type(v) is not str for v in choice) or len(set(choice)) != len(choice) or any(v not in definition['choices'] for v in choice):
                raise ValueError('distinct Traveler substitutions required')
        elif type(choice) is not str or choice not in definition['choices']:
            raise ValueError('acquisition choice outside the printed source domain')
    else:
        selection = {'waivers': []} if selection is None else selection
        if type(selection) is not dict or set(selection) != {'waivers'}:
            raise ValueError('this native source has no acquisition choice')
    if kind in ('blessing', 'exalted'):
        permission = selection['permission']
        expected = {'reason', 'patron_id'} if kind == 'exalted' else {'reason'}
        if type(permission) is not dict or set(permission) != expected:
            raise ValueError('exact source-specific GM permission required')
        _text(permission['reason'], 'GM permission reason')
        if kind == 'exalted':
            _text(permission['patron_id'], 'actual granting patron identity')
    if type(selection['waivers']) is not list:
        raise ValueError('scoped native qualification waivers required')
    return deepcopy(selection)


def _snapshot(engine, actor, uid, selection):
    import skill_modifiers as S
    definition = DEFINITIONS[uid]
    facts = {'trainer': actor.kind == 'trainer'}
    for parent in definition.get('parents', []):
        facts['owned:' + parent] = _count(actor, parent)
    for skill in definition.get('skills', {}):
        facts['skill:' + skill] = S.rank(engine.r, actor, skill)[2]
    if definition.get('element'):
        import elemental_connection as ELEMENTAL
        facts['elements'] = list(ELEMENTAL.choices(engine, actor))
    if definition.get('class_slot'):
        import acquired_features as A
        facts['classes'] = len(A.class_instances(actor))
    if definition['kind'] == 'technique':
        import acquired_features as A
        facts['journey_rank'] = A.feature_rank(actor, JOURNEY) if _count(actor, JOURNEY) else 0
        names = DOCUMENT['backpacker_talent_aliases']
        facts['talents'] = len([value for value in actor.spec.get('techniques', []) if value in names])
    if definition['kind'] == 'blessing':
        import acquired_features as A
        import blessing_skill_features as B
        route = ROUTES[selection['role']]
        facts['route_owned'] = _count(actor, route)
        facts['route_rank'] = A.feature_rank(actor, route) if facts['route_owned'] else 0
        required = definition['parents'][0]
        facts['prerequisite_permission'] = None
        if facts['owned:' + required] and required in B.SOURCES:
            facts['prerequisite_permission'] = (bool(B.approval(actor, required))
                if required in actor.spec.get('_blessing_gift_approvals', {}) else False)
        facts['permission_required'] = required in B.SOURCES
        native_gifts = {row[KEY]['feature_id'] for _, row, active in _rows(actor) if active}
        facts['legacy_rank3'] = [gift for gift in DOCUMENT['rank3_blessings']
                                 if gift not in native_gifts and _count(actor, gift)]
        facts['slot_used'] = any(active and row[KEY]['snapshot'].get('grant') == [selection['role'], selection['grant_rank'], selection['slot']]
                                 for _, row, active in _rows(actor))
        facts['grant'] = [selection['role'], selection['grant_rank'], selection['slot']]
    if definition['kind'] == 'exalted':
        import world_entities as W
        patron = W.actor_index(engine).get(selection['permission']['patron_id'])
        facts['patron_mewtwo'] = bool(patron is not None and patron.kind == 'pokemon'
            and engine.r.species.get(patron.spec.get('species'), {}).get('name') == '뮤츠')
        names = DOCUMENT['exalted_aliases']
        facts['exalted_count'] = sum(value in names for field in ('feats', 'gifts') for value in actor.spec.get(field, []))
    return facts


def _qualification(uid, facts, selection):
    d = DEFINITIONS[uid]
    checks = [Q.check('trainer', 'selection', facts['trainer'] is True, 'actual trainer required')]
    for parent in d.get('parents', []):
        checks.append(Q.check('owned:' + parent, 'prerequisite', facts['owned:' + parent] >= 1, 'actual acquired prerequisite required: ' + parent))
    skill_results = []
    for skill, minimum in d.get('skills', {}).items():
        rank = facts['skill:' + skill]
        if type(rank) is not int or rank < 1:
            raise ValueError('whole positive historical skill rank required')
        skill_results.append(rank >= minimum)
        if not d.get('any_skill'):
            checks.append(Q.check('skill:' + skill, 'prerequisite', rank >= minimum, 'native acquisition requires printed rank of ' + skill))
    if d.get('any_skill'):
        checks.append(Q.check('skill_alternative', 'prerequisite', any(skill_results), 'native acquisition requires Expert Focus or Intuition'))
    if d.get('element'):
        checks.append(Q.check('element', 'prerequisite', d['element'] in facts['elements'], 'actual selected Elemental Connection type required'))
    if d.get('class_slot'):
        checks.append(Q.check('class_capacity', 'capacity', facts['classes'] < 4, 'acquired class instances exceed four slots'))
    if d['kind'] == 'technique':
        checks.extend([Q.check('journey', 'prerequisite', facts['journey_rank'] >= 1, 'actual Hero Journey rank required'),
            Q.check('talent_capacity', 'capacity', facts['talents'] < 2 * facts['journey_rank'], 'Hero Journey talent slots are full')])
    if d['kind'] == 'blessing':
        checks.extend([Q.check('rank3_route', 'prerequisite', facts['route_owned'] >= 1 and facts['route_rank'] >= selection['grant_rank'], 'actual granting route rank3 or higher required'),
            Q.check('prerequisite_permission', 'prerequisite', facts['prerequisite_permission'] is (True if facts['permission_required'] else None), 'actual independent prerequisite Gift permission required'),
            Q.check('legacy_slot_authority', 'selection', not facts['legacy_rank3'], 'legacy rank3 Blessing grant-slot authority remains unresolved'),
            Q.check('grant_slot', 'capacity', facts['slot_used'] is False, 'actual granting role slot already used')])
    if d['kind'] == 'exalted':
        checks.extend([Q.check('granting_patron', 'prerequisite', facts['patron_mewtwo'] is True, 'actual Mewtwo granting patron required'),
            Q.check('one_exalted', 'capacity', facts['exalted_count'] == 0, 'a Trainer cannot acquire a second Exalted Gift')])
    result = Q.evaluate(source_id=uid, provider='native', stage='acquire', checks=checks, waivers=selection['waivers'])
    if result['status'] != 'qualified':
        raise ValueError(next(row['reason'] for row in result['checks'] if row['state'] in ('denied', 'pending')))
    return result


def _record(actor, uid, record):
    payload = {key: value for key, value in record.items() if key != 'integrity'}
    if set(record) != {'schema', 'basis', 'receipt_id', 'actor_id', 'feature_id', 'request_id', 'source', 'selection', 'snapshot', 'qualification', 'integrity'} or record['integrity'] != _digest(payload):
        raise ValueError('native acquisition receipt integrity changed')
    if record['schema'] != 1 or record['basis'] != LABEL or record['actor_id'] != actor.entity_id or record['feature_id'] != uid or record['source'] != _source(actor.r, uid):
        raise ValueError('native acquisition receipt source or owner changed')
    _text(record['request_id'], 'native acquisition request identity')
    if record['receipt_id'] != LABEL + '/' + record['request_id']:
        raise ValueError('native acquisition receipt identity changed')
    selection = _selection(uid, record['selection'])
    if record['qualification'] != _qualification(uid, record['snapshot'], selection):
        raise ValueError('historical native acquisition qualification changed')
    return record


def blessing_qualification(actor, gift, *, stored=None):
    """Native admission is distinct from GM's already-owned migration record."""
    matches = [row[KEY] for _, row, active in _rows(actor) if active and row[KEY]['feature_id'] == gift]
    if not matches:
        if isinstance(stored, dict) and stored.get('basis') == LABEL:
            raise ValueError('native Blessing admission receipt is missing')
        return None
    if len(matches) != 1:
        raise ValueError('one actual native Blessing admission receipt required')
    record = _record(actor, gift, matches[0])
    result = {'schema': 1, 'basis': LABEL, 'source': record['source'],
              'request_id': record['request_id'], 'grant': record['snapshot']['grant'],
              'qualification': record['qualification'], 'integrity': record['integrity']}
    if stored is not None and stored != result:
        raise ValueError('native Blessing acquisition snapshot changed')
    return deepcopy(result)


def class_instances(actor):
    # Existing declared synthetic classes also occupy slots; no past legality is inferred.
    result = []
    values = [value for field in ('feats', 'classes') for value in actor.spec.get(field, [])]
    for uid, definition in DEFINITIONS.items():
        if not definition.get('class_slot'):
            continue
        aliases = definition['owned_aliases']
        count = sum(value in aliases for value in values)
        if count > 1:
            raise ValueError('duplicate acquired synthetic class aliases')
        if not count:
            continue
        choices = [value for key, value in actor.spec.get('static_feature_choices', {}).items() if key in aliases]
        if len(choices) != 1:
            raise ValueError('one explicit owned synthetic class branch required')
        branch = choices[0]
        if isinstance(branch, (list, tuple)) and len(branch) == 1:
            branch = branch[0]
        if type(branch) is not str or branch not in definition['choices']:
            raise ValueError('owned synthetic class branch outside its source')
        result.append({'source_id': uid, 'branch': branch, 'instance_key': _sid(actor, uid)})
    return result


def validate_actor(actor):
    requests = set()
    for sid, row, active in _rows(actor):
        uid = row[KEY]['feature_id']
        if uid not in DEFINITIONS:
            raise ValueError('unknown native acquisition source')
        record = _record(actor, uid, row[KEY])
        if record['request_id'] in requests:
            raise ValueError('native acquisition request identity reused')
        requests.add(record['request_id'])
        if sid != _sid(actor, uid) or row.get('kind') != 'feature' or row.get('owner_id') != actor.entity_id or row.get('rule_id') != DEFINITIONS[uid]['rule_id'] or row.get('lifetime') != 'while_owned':
            raise ValueError('native acquisition grant-source provenance changed')
        if active:
            field = DEFINITIONS[uid]['field']
            if actor.spec.get(field, []).count(DEFINITIONS[uid]['owned_value']) != 1:
                raise ValueError('native acquisition needs its actual owned source')
            choice_field = DEFINITIONS[uid].get('choice_field')
            if choice_field and actor.spec.get(choice_field, {}).get(uid) != record['selection']['choice']:
                raise ValueError('native acquisition immutable choice changed')
            if DEFINITIONS[uid]['kind'] == 'blessing':
                import blessing_skill_features as B
                approval = actor.spec.get('_blessing_gift_approvals', {}).get(uid, {})
                if approval.get('acquisition') != blessing_qualification(actor, uid) or approval.get('configuration') != record['selection']['configuration']:
                    raise ValueError('native Blessing permission or acquired role changed')
                B.approval(actor, uid)
    return True


def receipts(actor):
    return [dict(deepcopy(row[KEY]), state='active' if active else 'ended', grant_source_id=sid)
            for sid, row, active in _rows(actor)]


def acquire(engine, actor, uid, *, acquisition_request_id, selection=None):
    import world_entities as W
    import acquired_features as A
    W.require_actors(engine, actor)
    _text(acquisition_request_id, 'native acquisition request identity')
    source = _source(engine.r, uid)
    selection = _selection(uid, selection)
    A.validate_class_slots(actor)
    for _, row, active in _rows(actor):
        record = row[KEY]
        if record['request_id'] == acquisition_request_id:
            if record['feature_id'] != uid or record['selection'] != selection:
                raise ValueError('native acquisition request replay changed intent')
            return dict(deepcopy(record), status='acquired' if active else 'withdrawn')
    d = DEFINITIONS[uid]
    if _count(actor, uid):
        raise ValueError('already-owned declaration is not a new native acquisition')
    if type(actor.spec.get(d['field'], [])) is not list:
        raise ValueError('actual mutable acquisition ownership list required')
    facts = _snapshot(engine, actor, uid, selection)
    qualification = _qualification(uid, facts, selection)
    record = {'schema': 1, 'basis': LABEL, 'receipt_id': LABEL + '/' + acquisition_request_id,
        'actor_id': actor.entity_id, 'feature_id': uid,
        'request_id': acquisition_request_id, 'source': source, 'selection': selection,
        'snapshot': facts, 'qualification': qualification}
    record['integrity'] = _digest(record)

    def apply(staged, trainer):
        trainer.spec.setdefault(d['field'], []).append(d['owned_value'])
        if d.get('choice_field'):
            trainer.spec.setdefault(d['choice_field'], {})[uid] = deepcopy(selection['choice'])
        if d['kind'] in ('static', 'class'):
            import static_feature_state_grants as STATIC
            # Install the new projection before attaching admission metadata to
            # its shared source. An empty admission record is not an old grant.
            STATIC.register_all(staged, trainer)
        G._source(trainer, _sid(trainer, uid), 'feature', owner_id=trainer.entity_id,
                  lifetime='while_owned', rule_id=d['rule_id'], tutor_points=0,
                  **{KEY: record})
        if d['kind'] == 'blessing':
            import blessing_skill_features as B
            B.confirm(staged, trainer, uid, reason=selection['permission']['reason'],
                      configuration=selection['configuration'])
        if d['kind'] == 'exalted':
            G.grant_moves(trainer, ['move/사이코브레이크'], _sid(trainer, uid), 'feature',
                owner_id=trainer.entity_id, lifetime='while_owned', rule_id=uid, tutor_points=0)
        import class_passive_combat as PASSIVE
        PASSIVE.register_all(staged, trainer)
        A.validate_class_slots(trainer)
        return dict(deepcopy(record), status='acquired')

    return G.transition(engine, actor, apply)
