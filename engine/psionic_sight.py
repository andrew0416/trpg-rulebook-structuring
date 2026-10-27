"""Acquired Psionic Sight reads actual traces, never administrative caster IDs."""
from copy import deepcopy
import common_checks as C
import state_grants as G
import world_entities as W
import resolution_transaction as TX

FEATURE = 'feat/사이오닉-시야'
BOOK = 'input/ch03-skills-edges-feats.md:903-907'
CSV = 'C2CSV/input/db/feats.csv:R50:main'
BOOK_SHA = 'b94e43349794836391501f9aac10009d20746bf946ea0c4b5ff3adf85e982d23'
CSV_SHA = '4435ff1c462a211564c85d2c1c9a2ac6e7c790c7545e1ad7056d32888b2367bd'
CORE_SHA = 'e5e0371031601c3ad0a04056771c17599a2d8826e5a5102ccd37f9b368108907'
KNOWLEDGE = 'psionic_sight_knowledge'
DEFINITION = {'clause_id': BOOK, 'span': [903, 907], 'catalog_span': [903, 907],
              'stat_tags': ['spd'], 'source_choices': ['core', 'local_csv']}


def source(rules, edition):
    from source_context import verified_source
    if edition not in ('core', 'local_csv'):
        raise ValueError('reviewed Psionic Sight source edition required')
    if rules._selected_rule(FEATURE) != FEATURE:
        raise ValueError('selected Psionic Sight source needs its own adapter')
    if any(uid in rules.ruleset.unit_versions for uid in (FEATURE, BOOK, CSV)):
        raise ValueError('Psionic Sight source version needs its own adapter')
    authority = {'file': 'input/ch03-skills-edges-feats.md', 'sha256': BOOK_SHA}
    verified_source(rules, authority, label='Psionic Sight')
    if edition == 'local_csv':
        authority = {'file': 'input/db/feats.csv', 'sha256': CSV_SHA}
        verified_source(rules, authority, label='local CSV Psionic Sight')
        rules.ruleset.require({'id': CSV, 'source': {'file': 'db/feats.csv', 'record_span': [50, 50]}})
        return dict(authority, edition=edition, clause_id=CSV, record=50)
    original = {'file': 'source-audit/ptu-core-1.05.pdf', 'sha256': CORE_SHA, 'pages': [64]}
    verified_source(rules, original, label='original Core Psionic Sight', source_root='source-audit')
    return dict(authority, edition=edition, clause_id=BOOK, span=[903, 907], interpretation=original)


def edition(selection):
    if selection is None:
        return 'core'
    if type(selection) is not dict or set(selection) != {'edition'} or selection['edition'] not in ('core', 'local_csv'):
        raise ValueError('exact reviewed Psionic Sight edition selection required')
    return selection['edition']


def acquisition_snapshot(engine, actor, selection):
    import elemental_connection as E
    selected = edition(selection)
    # choices also validates the actual Mystic Senses rank, exclusion and source.
    types = E.choices(engine, actor)
    mystic = any(E.matches(name, E.MYSTIC) for name in actor.spec.get('edges', []) + actor.spec.get('feats', []))
    return {'selection': deepcopy(selection), 'source': source(engine.r, selected),
            'elemental_types': list(types), 'mystic_senses': mystic}


def qualification(actor, snapshot, prerequisite_source):
    import acquisition_qualification as Q
    import type_state as TYPES
    if prerequisite_source is not None or type(snapshot) is not dict or set(snapshot) != {
            'selection', 'source', 'elemental_types', 'mystic_senses'}:
        raise ValueError('actual Psionic Sight acquisition observations required')
    selected = edition(snapshot['selection'])
    if snapshot['source'] != source(actor.r, selected):
        raise ValueError('immutable actual Psionic Sight source required')
    types = snapshot['elemental_types']
    if type(types) is not list or len(types) != len(set(types)) or type(snapshot['mystic_senses']) is not bool:
        raise ValueError('actual distinct Elemental Connection choices or Mystic Senses required')
    if types:
        TYPES.validate_types(actor.r, types, label='Psionic Sight elemental prerequisite')
    eligible = (bool(types) or snapshot['mystic_senses']) if selected == 'local_csv' else '에스퍼' in types
    return Q.require(FEATURE, 'native', 'acquire', [
        Q.check('trainer', 'prerequisite', actor.kind == 'trainer', 'actual Trainer required'),
        Q.check('edge', 'prerequisite', eligible,
                'Elemental Connection or Mystic Senses required' if selected == 'local_csv' else 'Psychic Elemental Connection required')])


def records(actor, *, active=True):
    import trainer_feature_acquisition as T
    return T.static_acquisitions(actor, FEATURE, active=active)


def after_acquire(engine, actor, source_id):
    G.stat(actor, 'spd', 1, source_id, operation_id='acquisition_stat_tag')


def validate_acquisition(actor, record, source_id, active):
    if active and actor.spec.get(G.KEY, {}).get('stat_sources', {}).get('spd', {}).get('sources', {}).get(source_id, {}).get('acquisition_stat_tag') != {'delta': 1, 'minimum': None}:
        raise ValueError('actual source-owned Psionic Sight Special Defense tag required')


def validate_actor(actor):
    rows = records(actor)
    names = {FEATURE, '사이오닉 시야', 'Psionic Sight'}.intersection(actor.spec.get('feats', []))
    if bool(names) != bool(rows) or names and names != {FEATURE} or len(rows) > 1:
        raise ValueError('Psionic Sight requires its one actual acquired source')
    data = actor.spec.get(KNOWLEDGE)
    if data is None:
        return
    if type(data) is not dict or set(data) != {'groups', 'sha256'} or data['sha256'] != TX.request_fingerprint(data['groups']):
        raise ValueError('actual Psionic signature knowledge evidence changed')
    groups = data['groups']
    if type(groups) is not dict:
        raise ValueError('Psionic signature knowledge must be a mapping')
    tokens = set()
    for caster, row in groups.items():
        G._text(caster, 'actual signature owner')
        if type(row) is not dict or set(row) != {'group', 'witnesses'} or type(row['witnesses']) is not list:
            raise ValueError('actual anonymous signature group required')
        G._text(row['group'], 'anonymous signature group')
        if row['group'] in tokens or not row['group'].startswith('psionic-signature-'):
            raise ValueError('distinct anonymous signature groups required')
        tokens.add(row['group'])


def require(engine, actor):
    W.require_actors(engine, actor)
    validate_actor(actor)
    rows = records(actor)
    if len(rows) != 1:
        raise ValueError('actual acquired Psionic Sight required')
    if actor.dead or actor.fainted or not actor.on_field or actor.captured:
        raise ValueError('available Psionic Sight observer required')
    record = rows[0][1]
    if record['snapshot']['source'] != source(engine.r, edition(record['snapshot']['selection'])):
        raise ValueError('actual selected Psionic Sight source changed')
    return record


def ignores_invisibility(engine, observer, target):
    if observer is None or observer is target or not records(observer):
        return False
    W.require_actors(engine, observer, target)
    if observer.dead or observer.fainted or not observer.on_field or observer.captured:
        return False
    return edition(require(engine, observer)['snapshot']['selection']) == 'local_csv'


def declaration(actor):
    return {'id': 'native:' + FEATURE, 'source': FEATURE, 'capabilities': [],
            'mode': 'visual', 'range': None, 'path': 'visual', 'medium': [],
            'vision': 'usable', 'provider': 'psychic_residue', 'information': ['presence', 'traces'], 'check': None}


def route(engine, observer, target, value):
    require(engine, observer)
    W.require_actors(engine, target)
    if target.kind not in ('trainer', 'pokemon') or value != declaration(observer):
        raise ValueError('exact native Psionic Sight declaration and Human or Pokemon target required')


def _group(observer, caster_id):
    data = observer.spec.setdefault(KNOWLEDGE, {'groups': {}, 'sha256': TX.request_fingerprint({})})
    if caster_id not in data['groups']:
        data['groups'][caster_id] = {'group': 'psionic-signature-' + str(len(data['groups']) + 1), 'witnesses': []}
    data['sha256'] = TX.request_fingerprint(data['groups'])
    return data['groups'][caster_id]


def values(engine, observer, target, chosen):
    import telepath as T
    local_csv = edition(require(engine, observer)['snapshot']['selection']) == 'local_csv'
    familiar_powers = {w['power_id'] for group in observer.spec.get(KNOWLEDGE, {}).get('groups', {}).values()
                       for w in group['witnesses']}
    traces = []
    for trace in T.live(target, 'psychic_residue'):
        T.validate_effect(target, trace)
        caster_id = trace['effect']['caster_id']
        row = _group(observer, caster_id)
        item = {'instance_id': trace['id'], 'signature': row['group']}
        # Internal world IDs are not player knowledge. Only a real witnessed
        # casting and its visible resulting trace unlock the association.
        if any(w['caster_identified'] for w in row['witnesses']):
            item['caster_id'] = caster_id
        # CSV familiarity concerns the power, not this caster's identity.
        if local_csv and trace['source'] in familiar_powers:
            item['power_id'] = trace['source']
        traces.append(item)
    return {field: bool(traces) if field == 'presence' else deepcopy(traces) for field in chosen}


def observe(engine, observer, target):
    return __import__('perception_observe').observe(engine, observer, target, declaration(observer))


def witness_created(engine, caster, target, trace):
    """Called only by the actual residue producer at the casting boundary."""
    import perception_observe as O
    if target.kind not in ('trainer', 'pokemon'):
        return
    for observer in W.actor_index(engine).values():
        if not records(observer) or observer.dead or observer.fainted or not observer.on_field or observer.captured:
            continue
        require(engine, observer)
        sight = declaration(observer)
        # Seeing a trace later, or knowing an administrative caster ID, does
        # not establish that the observer saw this casting happen.
        _, _, blocked = O.route(engine, observer, target, sight)
        caster_sight = O.native(FEATURE, [], mode='visual', information=['presence', 'identity'])
        caster_sight.update(path='visual', vision='usable')
        seen = O.observe(engine, observer, caster, caster_sight)
        if blocked is not None or seen['status'] not in ('observed', 'partial') or seen['values'].get('presence') is not True:
            continue
        # This is still inside the actual producer's atomic transition. Read
        # its newly installed trace through the routed finite native provider;
        # an administrative casting notification alone is not a witnessed result.
        result = O._values(engine, observer, target, sight, sight['information'])
        if result['status'] != 'observed' or not any(r['instance_id'] == trace['id'] for r in result['values']['traces']):
            continue
        row = _group(observer, caster.entity_id)
        witness = {'target_id': target.entity_id, 'instance_id': trace['id'], 'power_id': trace['source'],
                   'at': engine.elapsed_seconds, 'acquisition_request': records(observer)[0][1]['request_id'],
                   'caster_observation': deepcopy(seen), 'target_observation': deepcopy(result),
                   'caster_identified': seen['status'] == 'observed' and seen['values'].get('identity') == caster.entity_id}
        if witness not in row['witnesses']:
            row['witnesses'].append(witness)
            observer.spec[KNOWLEDGE]['sha256'] = TX.request_fingerprint(observer.spec[KNOWLEDGE]['groups'])


def validate_world(engine, index):
    import telepath as T
    for observer in index.values():
        validate_actor(observer)
        for caster_id, group in observer.spec.get(KNOWLEDGE, {}).get('groups', {}).items():
            if caster_id not in index:
                raise ValueError('actual signature caster required')
            requests = {r['request_id'] for _, r in records(observer, active=False)}
            for witness in group['witnesses']:
                if type(witness) is not dict or set(witness) != {'target_id', 'instance_id', 'power_id', 'at', 'acquisition_request', 'caster_observation', 'target_observation', 'caster_identified'}:
                    raise ValueError('actual witnessed signature receipt required')
                target = index.get(witness['target_id'])
                if target is None or witness['acquisition_request'] not in requests:
                    raise ValueError('witnessed signature requires its actual target and acquisition')
                traces = T.live(target, 'psychic_residue') + target.spec.get('effect_instance_history', [])
                found = [r for r in traces if r.get('id') == witness['instance_id'] and r.get('effect', {}).get('operation') == 'psychic_residue']
                if len(found) != 1 or found[0]['effect']['caster_id'] != caster_id or found[0]['source'] != witness['power_id'] or found[0]['at'] != witness['at']:
                    raise ValueError('witnessed signature requires its actual casting and resulting trace')
                C.integer(witness['at'], 'signature witness time', 0, engine.elapsed_seconds)
                seen = witness['caster_observation']
                if type(seen) is not dict or seen.get('source') != FEATURE or seen.get('mode') != 'visual' or seen.get('status') not in ('observed', 'partial') or type(seen.get('values')) is not dict or set(seen['values']) != {'presence', 'identity'} or seen['values']['presence'] is not True:
                    raise ValueError('signature familiarity requires actual visible casting')
                identified = seen['status'] == 'observed' and seen['values']['identity'] == caster_id
                if type(witness['caster_identified']) is not bool or witness['caster_identified'] is not identified:
                    raise ValueError('signature identity requires actual visible caster knowledge')
                result = witness['target_observation']
                if type(result) is not dict or result.get('source') != FEATURE or result.get('mode') != 'visual' or result.get('status') != 'observed' or type(result.get('values')) is not dict or set(result['values']) != {'presence', 'traces'} or result['values']['presence'] is not True or type(result['values']['traces']) is not list:
                    raise ValueError('signature familiarity requires actual visible resulting trace')
                observed = [r for r in result['values']['traces'] if type(r) is dict and r.get('instance_id') == witness['instance_id'] and r.get('signature') == group['group']]
                if len(observed) != 1:
                    raise ValueError('signature familiarity requires its actual observed trace instance')
    return True
