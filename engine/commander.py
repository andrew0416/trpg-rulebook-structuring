"""Commander acquisition, one logical Order, and its actual recipient windows.

Order effects remain with their native owners. This module owns the Class gift,
printed Commander modifiers and Mobilize's next-actual-turn encounter permission.
"""
from copy import deepcopy

CLASS = 'class/지휘관'
MOBILIZE = 'feat/동원'
LEADERSHIP = 'feat/리더십'
BATTLE = 'feat/전투-지휘'
COMPLEX = 'feat/복합-지시'
TIP = 'feat/상황-전환'
SCHEME = 'feat/계획-변경'
KEY = 'commander_orders'
USES = 'commander_order_uses'
ACTIVATIONS = 'commander_activations'
SOURCE_SHA = 'a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'
GENERAL_SHA = 'b94e43349794836391501f9aac10009d20746bf946ea0c4b5ff3adf85e982d23'
CORE_SHA = 'e5e0371031601c3ad0a04056771c17599a2d8826e5a5102ccd37f9b368108907'
DEFINITIONS = {
    CLASS: {'span': (422, 424), 'parents': [], 'rank': 3, 'action': 'static'},
    MOBILIZE: {'span': (426, 431), 'parents': [CLASS], 'rank': 0, 'action': 'free'},
    LEADERSHIP: {'span': (433, 436), 'parents': [CLASS], 'rank': 0, 'action': 'static'},
    BATTLE: {'span': (438, 445), 'parents': [LEADERSHIP], 'rank': 0, 'action': 'swift'},
    COMPLEX: {'span': (447, 451), 'parents': [], 'rank': 0, 'action': 'shift'},
    TIP: {'span': (453, 457), 'parents': [CLASS], 'rank': 5, 'action': 'swift'},
    SCHEME: {'span': (459, 463), 'parents': [CLASS], 'rank': 6, 'action': 'swift'},
}
FEATURES = {uid: row['span'] for uid, row in DEFINITIONS.items()}
BUNDLES = {
    'feat/유린-지시': {'span': (737, 740), 'skills': ('명령', '협박'), 'children': ('feat/난폭한-진격', 'feat/재공격')},
    'feat/명사수-지시': {'span': (754, 757), 'skills': ('통찰', '교활'), 'children': ('feat/트릭-샷', 'feat/롱-샷')},
    'feat/트릭스터-지시': {'span': (771, 774), 'skills': ('매력', '교활'), 'children': ('feat/변덕스러운-회전', 'feat/매혹적인-데르비시')},
    'feat/가디언-지시': {'span': (788, 791), 'skills': ('매력', '협박'), 'children': ('feat/충격-대비', 'feat/초계-자세')},
    'feat/정밀-지시': {'span': (805, 808), 'skills': ('명령', '통찰'), 'children': ('feat/핀포인트-스트라이크', 'feat/완벽한-에임')},
}


def install(rules):
    """Project the actual Perfect Aim block as its printed Feature identity."""
    from copy import deepcopy
    import source_context as S
    block = rules.selection.units['block/완벽한-에임']
    if (block.get('eng') != 'Perfect Aim' or block['source']['file'] != 'ch03-skills-edges-feats.md'
            or block['source']['lines'] != [816, 819]):
        raise ValueError('reviewed actual Perfect Aim source block required')
    S.verified_source(rules, {'file': 'input/ch03-skills-edges-feats.md', 'sha256': GENERAL_SHA})
    unit = deepcopy(block)
    unit.update(id='feat/완벽한-에임', kind='entity:feat', tags=['feat', '지시', 'Orders'])
    rules.selection.register_derived(unit, ('block/완벽한-에임',))
    return unit['id']


def receipts(actor, feature, *, active=False):
    import trainer_feature_acquisition as T
    return [row['static_acquisition'] for _, row, live in T._static_records(actor)
            if row['static_acquisition']['feature_id'] == feature and (live or not active)]


def acquired(actor, feature=CLASS):
    import acquired_features as A, trainer_feature_acquisition as T
    if gifted(actor, feature):
        source_id = actor.spec['commander_gifts'][feature]['source_id']
        import state_grants as G
        return actor.spec[G.KEY]['sources'][source_id]['static_acquisition']
    if not A.owned_rule_count(actor, feature):
        return None
    T.validate_actor(actor)
    rows = receipts(actor, feature, active=True)
    if actor.kind != 'trainer' or A.owned_rule_count(actor, feature) != 1 or len(rows) != 1:
        raise ValueError('one actual source-specific Commander acquisition required')
    return rows[0]


def acquisition_snapshot(engine, actor, feature, branch=None, selection=None):
    import skill_modifiers as S
    if feature in BUNDLES:
        return bundle_snapshot(engine, actor, feature)
    if selection is not None and feature != COMPLEX:
        raise ValueError('only Complex Orders has a prerequisite source selection')
    parents = DEFINITIONS[feature]['parents']
    source = 'core';declaration=None
    if feature == CLASS:
        if acquired(actor, CLASS) is not None:
            raise ValueError('Commander is one Class acquisition, not five repeatable branches')
        if type(branch) is not str or branch not in BUNDLES:
            raise ValueError('Commander requires exactly one of the five printed Orders bundles')
        if acquired(actor, branch):
            raise ValueError('Commander gift must acquire a previously unknown bundle')
    elif branch is not None:
        raise ValueError('only Commander has a gift selection')
    if feature == COMPLEX:
        if selection is not None and (type(selection) is not dict or set(selection) not in (
                {'prerequisite_source'},{'prerequisite_source','mastermind_declaration'})):
            raise ValueError('exact Complex Orders prerequisite source selection required')
        source = 'core' if selection is None else selection['prerequisite_source']
        if source not in ('core', 'local_translation'):
            raise ValueError('Core Mastermind or local translated Commander prerequisite required')
        if source == 'core':
            declaration=None if selection is None else selection.get('mastermind_declaration')
            validate_mastermind(actor,declaration)
        elif 'mastermind_declaration' in selection:
            raise ValueError('local translated Commander prerequisite does not declare Mastermind')
        parents = [CLASS] if source=='local_translation' else []
    parent_rows = {}
    for parent in parents:
        receipt = acquired(actor, parent)
        if receipt is None:
            raise ValueError('actual acquired Commander prerequisite required: ' + parent)
        parent_rows[parent] = receipt['request_id']
    known = targeted_orders(actor) if feature == COMPLEX else []
    return {'command': S.rank(engine.r, actor, '명령')[2], 'parents': parent_rows,
            'branch': branch, 'prerequisite_source': source, 'known_orders': known,
            'mastermind_declaration':deepcopy(declaration)}


def validate_mastermind(actor,declaration):
    """Retain an external ownership observation; this never acquires Mastermind."""
    import acquisition_qualification as Q
    from hashlib import sha256
    from pathlib import Path
    if (type(declaration)is not dict or set(declaration)!={'identity','source','locator','qualification'}
            or declaration['identity']!='Mastermind'):
        raise ValueError('Core Complex Orders requires literal Mastermind and an independently sourced ownership declaration')
    source={'file':'output/source-audit/2026-10-10/ptu-core-1.05.pdf','sha256':CORE_SHA}
    if (declaration['source']!=source or declaration['locator']!={'pages':[81,81]}
            or sha256((Path(actor.r.root)/source['file']).read_bytes()).hexdigest()!=CORE_SHA):
        raise ValueError('literal Mastermind declaration requires the actual Core p81 source and locator')
    definition=declaration['qualification']
    if (type(definition)is not dict or set(definition)!={'provider','stage','checks','waivers'}
            or definition['provider']!=actor.entity_id or definition['stage']!='commander_prerequisite'
            or definition['waivers'] or type(definition['checks'])is not list or len(definition['checks'])!=1
            or definition['checks'][0].get('id')!='Mastermind'
            or definition['checks'][0].get('kind')!='prerequisite'):
        raise ValueError('literal Mastermind ownership requires its actual Trainer provider and scoped external declaration')
    result=Q.declaration_result(COMPLEX,definition)
    if result['status']!='qualified':raise ValueError('literal Mastermind ownership is not independently established')
    return result


def qualification(actor, feature, snapshot, prerequisite_source):
    import acquisition_qualification as Q, common_checks as C
    if (prerequisite_source is not None or type(snapshot) is not dict
            or set(snapshot) != {'command', 'parents', 'branch', 'prerequisite_source', 'known_orders','mastermind_declaration'}):
        raise ValueError('exact Commander acquisition observations required')
    C.integer(snapshot['command'], 'Commander acquisition Command rank', 0)
    if feature in BUNDLES:
        return _bundle_qualification(actor, feature, snapshot)
    parents = DEFINITIONS[feature]['parents']
    if feature == COMPLEX:
        if snapshot['prerequisite_source']=='core':validate_mastermind(actor,snapshot['mastermind_declaration'])
        elif snapshot['prerequisite_source']!='local_translation' or snapshot['mastermind_declaration'] is not None:
            raise ValueError('explicit Core Mastermind or local Commander prerequisite declaration required')
        parents = [CLASS] if snapshot['prerequisite_source']=='local_translation' else []
        if (type(snapshot['known_orders']) is not list or len(set(snapshot['known_orders'])) < 2
                or any(not _targeted_identity(actor.r, uid) for uid in snapshot['known_orders'])):
            raise ValueError('Complex Orders requires two actually known targeted Orders')
    elif snapshot['prerequisite_source'] != 'core' or snapshot['known_orders'] or snapshot['mastermind_declaration'] is not None:
        raise ValueError('Commander acquisition source observations changed')
    if type(snapshot['parents']) is not dict or set(snapshot['parents']) != set(parents):
        raise ValueError('printed Commander prerequisite receipts required')
    for uid, request in snapshot['parents'].items():
        if not any(row['request_id'] == request for row in receipts(actor, uid)):
            raise ValueError('historical Commander prerequisite receipt required')
    if (feature == CLASS and snapshot['branch'] not in BUNDLES) or (feature != CLASS and snapshot['branch'] is not None):
        raise ValueError('exact one Commander gift selection required')
    return Q.require(feature, 'native', 'acquire', [
        Q.check('trainer', 'prerequisite', actor.kind == 'trainer', 'actual Trainer required'),
        Q.check('command', 'prerequisite', snapshot['command'] >= DEFINITIONS[feature]['rank'],
                'printed Commander Command rank required')])


def bundle_snapshot(engine, actor, feature):
    import skill_modifiers as S
    return {'command': 0, 'parents': {}, 'branch': None, 'prerequisite_source': 'ordinary',
            'known_orders': {skill: S.rank(engine.r, actor, skill)[2] for skill in BUNDLES[feature]['skills']},
            'mastermind_declaration':None}


def _bundle_qualification(actor, feature, snapshot):
    import acquisition_qualification as Q
    ranks = snapshot['known_orders']
    if (snapshot['command'] != 0 or snapshot['parents'] or snapshot['branch'] is not None
            or snapshot['prerequisite_source'] != 'ordinary' or snapshot['mastermind_declaration'] is not None or type(ranks) is not dict
            or set(ranks) != set(BUNDLES[feature]['skills'])
            or any(type(rank) is not int or rank < 0 for rank in ranks.values())):
        raise ValueError('exact Orders bundle acquisition observations required')
    return Q.require(feature, 'native', 'acquire', [
        Q.check('trainer', 'prerequisite', actor.kind == 'trainer', 'actual Trainer required'),
        Q.check('skill', 'prerequisite', any(rank >= 5 for rank in ranks.values()),
                'Orders bundle requires one printed Expert skill')])


def after_acquire(engine, actor, feature, source_id, branch):
    import state_grants as G
    bundle = branch if feature == CLASS else feature if feature in BUNDLES else None
    if bundle is None:
        return
    granted = [bundle, *BUNDLES[bundle]['children']] if feature == CLASS else list(BUNDLES[bundle]['children'])
    for uid in granted:
        if uid in actor.spec.get('feats', []):
            raise ValueError('Orders gift cannot silently replace an existing acquisition')
        actor.spec.setdefault('feats', []).append(uid)
        actor.spec.setdefault('commander_gifts', {})[uid] = {
            'source_id': source_id, 'bundle': bundle, 'class_gift': feature == CLASS}
        G._source(actor, source_id, 'feature', commander_gift={'bundle': bundle, 'features': granted})


def gifted(actor, feature):
    row = actor.spec.get('commander_gifts', {}).get(feature)
    if row is None:
        return False
    __import__('trainer_feature_acquisition').validate_actor(actor)
    bundle = row.get('bundle')
    # Use the common source-key constant rather than trusting a name-only feat list.
    import state_grants as G
    source = actor.spec.get(G.KEY, {}).get('sources', {}).get(row.get('source_id'), {})
    receipt = source.get('static_acquisition', {})
    expected = CLASS if row.get('class_gift') else bundle
    if (bundle not in BUNDLES or feature not in (bundle, *BUNDLES[bundle]['children'])
            or receipt.get('feature_id') != expected
            or feature not in actor.spec.get('feats', [])
            or source.get('commander_gift', {}).get('bundle') != bundle
            or row.get('class_gift') and receipt.get('snapshot', {}).get('branch') != bundle):
        raise ValueError('actual source-owned Commander gift required')
    return True


def _targeted_identity(rules, uid):
    import training_features as T
    if uid in (MOBILIZE,__import__('moment_of_action').FEATURE,__import__('ace_trainer').CRITICAL,__import__('chronicler').PROFILING) or uid in {child for row in BUNDLES.values() for child in row['children']}:
        return True
    unit = rules.selection.units.get(uid, {})
    if T.identity(uid) is not None:
        return True
    return bool(unit.get('text', {}).get('target') and any(
        '지시' in tag or tag == 'Orders' for tag in unit.get('tags', [])))


def targeted_orders(actor):
    import acquired_features as A
    return sorted(uid for uid in actor.r.selection.units
                  if _targeted_identity(actor.r, uid) and A.owned_rule_count(actor, uid))


def ally(engine, actor, target):
    import world_entities as W
    W.require_actors(engine, actor, target)
    if (target is actor or target.kind not in ('trainer', 'pokemon') or actor.side is None
            or target.side is None or target.side != actor.side):
        raise ValueError('actual allied Trainer or Pokemon required')
    if target.fainted or target.captured or not target.on_field:
        raise ValueError('actual ally must be conscious and available')
    return True


def leadership_target(engine, actor, target):
    if acquired(actor, LEADERSHIP) is None:
        return False
    ally(engine, actor, target)
    return True


def _seal(row):
    import trainer_feature_acquisition as T
    return T._digest('commander/order-use/v1', {key: value for key, value in row.items() if key != 'integrity'})


def uses(actor):
    rows = actor.spec.get(USES, [])
    if type(rows) is not list:
        raise ValueError('Commander Order history must be a list')
    return rows


def scope(engine, actor, feature=None, target=None):
    row = getattr(engine, '_commander_order_scope', None)
    if row is None or row['issuer'] is not actor:
        return None
    if feature is not None and not any(feature in (item['feature'],
            engine.r.selection.units[item['feature']].get('title'),engine.r.selection.units[item['feature']].get('eng')) and (
            target is None or item['target'] is target) for item in row['assignments']):
        return None
    return row


def _scope_proof(row):
    def plain(value):
        if hasattr(value,'entity_id'):return {'actor_id':value.entity_id}
        if type(value)is dict:return {key:plain(child) for key,child in value.items()}
        if type(value)in (tuple,list):return [plain(child) for child in value]
        return value
    return plain({key:value for key,value in row.items() if key not in ('integrity','activation')})


def transition_native(engine,actor,apply,*,participants=()):
    """Commit an actual native child pause, retaining its existing continuation."""
    import state_grants as G,passive_events as PASSIVE,heavy_injury_adapter as HEAVY
    pending=[]
    def invoke(e,owner,*targets):
        try:return apply(e,owner,*targets)
        except (PASSIVE.PassiveEventPending,HEAVY.HeavyPending) as error:
            field='_passive_pending' if type(error)is PASSIVE.PassiveEventPending else '_heavy_pending'
            events=e._passive_events if type(error)is PASSIVE.PassiveEventPending else e._heavy_events
            if getattr(e,field,None)!=error.event_id or error.event_id not in events:raise
            current=getattr(e,'_commander_order_scope',None)
            if current is not None:current['integrity']=_seal(_scope_proof(current))
            pending.append((type(error),error.event_id));return None
    result=G.transition(engine,actor,invoke,participants=participants,include_rulings=True,
        include_grid=engine.grid is not None)
    if pending:raise pending[0][0](pending[0][1])
    return result


def pay(engine, actor, feature, kind):
    row = scope(engine, actor, feature)
    if row is None:
        return kind
    if not row['paid']:
        row['paid'] = True
        return row['base_action']
    return 'free'


def transformed_target(engine, actor, target):
    row = scope(engine, actor, target=target)
    if row is None or not any(item['target'] is target for item in row['assignments']):
        return False
    ally(engine, actor, target)
    return target in row['changed_targets'] or leadership_target(engine, actor, target)


def sustained_target(engine, actor, target, feature):
    if transformed_target(engine, actor, target):return True
    if leadership_target(engine, actor, target):return True
    for row in actor.spec.get(ACTIVATIONS, []):
        if row.get('integrity') != _seal(row):raise ValueError('Commander activation evidence changed')
        if row['modifier'] in (BATTLE, TIP, SCHEME) and any(
                entry == {'target_id': target.entity_id, 'feature': feature} for entry in row['orders']):
            ally(engine, actor, target)
            return True
    return False


def _priority_components(activation):
    components=['standard']
    if activation['modifier'] is not None:components.append(DEFINITIONS[activation['modifier']]['action'])
    if activation['complex_orders']:components.append('shift')
    return components


def priority_action(engine, actor, feature):
    """The native Priority producer reserves this one activation's printed costs."""
    from action_metadata import ActionCost
    current=scope(engine,actor,feature)
    if current is None or not current.get('priority_actions'):return 'standard'
    components=tuple(current['priority_actions'])
    return components[0] if len(components)==1 else ActionCost(components)


def priority_funded(actor, feature, payment_id, activation_id=None):
    rows=[r for r in actor.spec.get(ACTIVATIONS,[]) if
        (r['priority_payment']==payment_id or activation_id is not None and r['id']==activation_id)
        and any(e['feature']==feature for e in r['orders'])]
    if not rows:return {'standard':1}
    if len(rows)!=1 or rows[0]['integrity']!=_seal(rows[0]):raise ValueError('Commander Priority activation changed')
    return {kind:1 for kind in _priority_components(rows[0])}


def training_payment(engine, actor, target, feature, communication, *, edition='local_csv'):
    import priority_limited as P
    row=scope(engine,actor,feature,target)
    if row is None:return None
    if edition=='core':
        payments=row.setdefault('standard_receipts',{})
        if feature not in payments:
            payments[feature]=__import__('training_features').pay_core_order(engine,actor,target,feature,communication)
        return deepcopy(payments[feature])
    if row.get('priority_receipt') is None:
        row['priority_receipt']=P.reserve(engine,actor,action=priority_action(engine,actor,feature),source=feature,
            subject=target.entity_id,communication=communication)
        row['paid']=True
        row['activation']['priority_payment']=row['priority_receipt']['id']
        row['activation']['integrity']=_seal(row['activation'])
    return deepcopy(row['priority_receipt'])


def training_authority(owner, target, feature, payment_id):
    import priority_limited as P
    for row in owner.spec.get(ACTIVATIONS,[]):
        if row.get('integrity')!=_seal(row):raise ValueError('Commander training activation changed')
        if any(p['id']==payment_id and p['commander_activation']==row['id'] and p['feature']==feature
               and p['target_id']==next(e['target_id'] for e in row['orders'] if e['feature']==feature) for p in __import__('training_features').core_payments(owner)):
            return {'target_id':target.entity_id,'feature':feature} in row['orders']
        if (row.get('priority_payment')==payment_id and row['modifier'] in (BATTLE,TIP)
                and {'target_id':target.entity_id,'feature':feature} in row['orders']):
            payments=[p for p in P.records(owner) if p['id']==payment_id]
            return len(payments)==1 and payments[0]['subject_id']==row['orders'][0]['target_id']
    return False


def _native_order(engine, actor, target, feature, options):
    import class_passive_combat as P, combat_precision_features as C, moment_of_action as M
    import commander_orders as O
    if feature == MOBILIZE:
        return mobilize(engine, actor, target, **options)
    if feature in O.FEATURES:
        return O.use(engine, actor, target, feature, **options)
    if feature in P.STRATAGEMS:
        return P.activate(engine, actor, target, feature, **({'edition':'core',**options} if feature==P.RECKLESS else options))
    if feature == C.PINPOINT:
        if options:raise ValueError('Pinpoint Strike has no extra native options')
        return C.activate(engine, actor, target)
    import chronicler as CH,ace_trainer as ACE,training_features as TRAINING
    if TRAINING.identity(feature):return TRAINING.orders(engine,actor,feature,target,**{'edition':'core',**options})
    if feature==CH.PROFILING:
        if options:raise ValueError('Targeted Profiling has no additional native options')
        return CH.profile_order(engine,actor,target)
    if feature in (M.FEATURE,ACE.CRITICAL):
        current=scope(engine,actor,feature)
        key='grouped:'+feature
        if current is not None and key in current:return current[key]
        targets=[target] if current is None else [c['target'] for c in current['assignments'] if c['feature']==feature]
        result=M.use(engine,actor,targets,**options) if feature==M.FEATURE else ACE.critical_moment(engine,actor,targets)
        if current is not None:
            current[key]=result;current['paid']=True
            payment=result.get('payment',{})
            payment_id=payment.get('receipt_id',payment.get('id'))
            receipts=[p for p in __import__('priority_limited').records(actor) if p['id']==payment_id]
            if len(receipts)==1:current['priority_receipt']=deepcopy(receipts[0])
        return result
    return engine.manual_feat(actor, feature, target, adjustment=options or None)


def group_authority(engine,actor,feature,target_ids,activation_id):
    rows=[r for r in actor.spec.get(ACTIVATIONS,[]) if r['id']==activation_id]
    return (len(rows)==1 and rows[0]['integrity']==_seal(rows[0])
        and rows[0]['modifier'] in (BATTLE,TIP,SCHEME)
        and {r['target_id'] for r in rows[0]['orders'] if r['feature']==feature}==set(target_ids))


def base_action(engine,feature):
    if feature==MOBILIZE:return 'free'
    if feature in {child for b in BUNDLES.values() for child in b['children']} or __import__('training_features').identity(feature):return 'standard'
    _,header=engine.r.feat_effects(feature)
    return (header or {}).get('action','standard')


def order_frequency(engine, feature):
    import commander_orders as O, class_passive_combat as P, training_features as T
    if feature==__import__('ace_trainer').CRITICAL:return {'kind':'scene','uses':2}
    if feature == MOBILIZE or feature in P.STRATAGEMS or feature in T.RULES or feature in (
            __import__('combat_precision_features').PINPOINT,__import__('chronicler').PROFILING,
            __import__('moment_of_action').FEATURE,__import__('directive_features').FEATURE):
        return {'kind': 'at_will', 'uses': 1}
    if feature in O.FEATURES:
        return O.FEATURES[feature]['frequency']
    _, header = engine.r.feat_effects(feature)
    if not header:
        raise ValueError('actual targeted Order frequency declaration required')
    return header.get('frequency')


def issue(engine, actor, feature, target, *, modifier=None, additional_targets=(), assignments=None, options=None):
    """Transform a native targeted Order, then complete its one actual activation."""
    import acquired_features as A, state_grants as G, frequency as F, body_state as B
    import cheerleader as CHEER, world_entities as W
    if not _targeted_identity(engine.r, feature) or not A.owned_rule_count(actor, feature):
        raise ValueError('actual known targeted Orders Feature required')
    if scope(engine, actor) is not None:
        raise ValueError('nested Commander Order activation is not a new trigger')
    if type(options or {}) is not dict:
        raise ValueError('native Order options must be a mapping')
    complex_mode = assignments is not None or modifier == COMPLEX
    if complex_mode and acquired(actor, COMPLEX) is None:
        raise ValueError('actual acquired Complex Orders required')
    if modifier == COMPLEX:modifier = None
    if modifier is not None and acquired(actor, modifier) is None:
        raise ValueError('actual acquired Commander modifier required')
    if modifier not in (None, BATTLE, TIP, SCHEME):
        raise ValueError('one explicitly supported Commander modifier required')
    kind, _ = F.parse(order_frequency(engine, feature))
    if modifier in (BATTLE, TIP) and kind != 'at_will':
        raise ValueError('Battle Conductor and Tip the Scales require an At-Will Order')
    if modifier == SCHEME and kind not in ('scene', 'daily'):
        raise ValueError('Scheme Twist requires a Scene or Daily Order')
    if modifier == TIP:
        if additional_targets:
            raise ValueError('Tip the Scales derives all actual allies within ten meters')
        recipients = []
        for candidate in W.actor_index(engine).values():
            if candidate is actor or candidate.side != actor.side or candidate.side is None:
                continue
            if not candidate.on_field or candidate.fainted or candidate.captured:
                continue
            if engine.grid is None:
                raise ValueError('Tip the Scales requires actual ten-meter geometry; mapless place adjacency does not establish meters')
            inside = B.in_range(engine, actor, candidate, 10)
            if inside:recipients.append(candidate)
        if not recipients or target not in recipients:
            raise ValueError('Tip the Scales trigger target must be an actual ally within ten meters')
        changed = list(recipients)
    else:
        if not isinstance(additional_targets, (list, tuple)) or len(additional_targets) > 2:
            raise ValueError('at most two actual additional allies required')
        if modifier not in (BATTLE, SCHEME) and additional_targets:
            raise ValueError('additional targets require the printed Commander modifier')
        recipients = [target, *additional_targets]
        changed = list(additional_targets)
    if len({id(c) for c in recipients}) != len(recipients):
        raise ValueError('distinct actual Commander recipients required')
    for recipient in recipients:ally(engine, actor, recipient)
    selected = [{'target': c, 'feature': feature, 'options': deepcopy(options or {})} for c in recipients]
    if complex_mode:
        if (not isinstance(assignments, (list, tuple)) or len(assignments) != len(recipients)
                or any(type(row) is not dict or set(row) != {'target_id', 'feature', 'options'} for row in assignments)
                or [row['target_id'] for row in assignments] != [c.entity_id for c in recipients]):
            raise ValueError('Complex Orders requires an explicit Order for every actual target')
        if len({row['feature'] for row in assignments}) != len(assignments):
            raise ValueError('Complex Orders must choose a different Order for each target')
        for recipient, choice in zip(recipients, assignments):
            if (not _targeted_identity(engine.r, choice['feature'])
                    or not A.owned_rule_count(actor, choice['feature']) or type(choice['options']) is not dict):
                raise ValueError('Complex Orders requires actually known targeted Orders and native options')
            if F.parse(order_frequency(engine, choice['feature']))[0] != kind:
                raise ValueError('mixed-frequency Complex Orders needs an explicit activation-boundary ruling')
        selected = [dict(choice, target=c) for c, choice in zip(recipients, assignments)]
    def priority_choice(choice):
        uid=choice['feature']
        return engine.encounter_active and (uid in (__import__('moment_of_action').FEATURE,__import__('ace_trainer').CRITICAL)
            or __import__('training_features').identity(uid) is not None and choice['options'].get('edition','core')=='local_csv')
    priority=[priority_choice(choice) for choice in selected]
    if any(priority) and not all(priority):raise ValueError('mixed native Priority and ordinary Orders require an explicit timing boundary')
    priority=all(priority)
    def apply(e, owner, *targets):
        import turn as TURN, action_points as AP
        native = [dict(choice, target=c, options=G._stage_transition_payload(engine,e,choice['options']))
                  for c, choice in zip(targets, selected)]
        if modifier == TIP:
            if AP.available(owner) < 2:raise ValueError('Tip the Scales requires two AP')
        if modifier == SCHEME and not F.activation_allowed(owner, SCHEME, {'kind': 'scene', 'uses': 2}, engine=e):
            raise ValueError('Scheme Twist Scene frequency exhausted')
        if not priority and modifier is not None and not TURN.spend(e, owner, DEFINITIONS[modifier]['action'], modifier):
            raise ValueError('actual Commander modifier action is unavailable')
        if not priority and complex_mode and not TURN.spend(e, owner, 'shift', COMPLEX):
            raise ValueError('actual Complex Orders Shift action is unavailable')
        if modifier == TIP:owner.ap_account.charge(2, mode='spend')
        if modifier == SCHEME:F.consume_activation(owner, SCHEME, {'kind': 'scene', 'uses': 2}, engine=e)
        activation = {'id': 'commander:' + owner.entity_id + ':' + str(len(owner.spec.get(ACTIVATIONS, [])) + 1),
            'feature': feature, 'modifier': modifier, 'complex_orders': complex_mode,
            'issuer_id': owner.entity_id, 'encounter': e._party_encounter_epoch,'priority_payment':None,
            'at':e.elapsed_seconds,'phase':'applying',
            'orders': [{'target_id': c['target'].entity_id, 'feature': c['feature']} for c in native],
            'source_requests': {uid: acquired(owner, uid)['request_id']
                                for uid in ([modifier] if modifier else []) + ([COMPLEX] if complex_mode else [])}}
        activation['integrity'] = _seal(activation)
        owner.spec.setdefault(ACTIVATIONS, []).append(activation)
        e._commander_order_scope = {'issuer': owner, 'assignments': native,'activation':activation,
            'changed_targets': [c for c in targets if c.entity_id in {x.entity_id for x in changed}],
            'paid': False, 'frequencies': [], 'completed': [],'cursor':0,'results':[],
            'waiting_use':None,'executing':False,'base_action':base_action(e,feature),
            'priority_actions':_priority_components(activation) if priority else []}
        return continue_orders(e)
    return transition_native(engine,actor,apply,participants=recipients)


def continue_orders(engine):
    """Resume only the stored native batch after its actual child Move completes."""
    import commander_orders as O,cheerleader as CHEER,passive_events as PASSIVE
    row=getattr(engine,'_commander_order_scope',None)
    if row is None or row['executing']:return None
    owner=row['issuer'];activation=row['activation']
    try:
        while row['cursor']<len(row['assignments']):
            choice=row['assignments'][row['cursor']]
            if row['waiting_use'] is not None:
                use=O.find_use(owner,row['waiting_use'])
                if use['phase']!='complete':return None
                result=O.result(engine,owner,use)
            else:
                row['executing']=True
                try:
                    O.deliver(engine,owner,choice['target'],choice['feature'])
                    result=_native_order(engine,owner,choice['target'],choice['feature'],choice['options'])
                finally:row['executing']=False
            if result is None or isinstance(result,tuple) and result!=(1,0):
                raise ValueError('native Order did not complete its actual effect')
            row['results'].append(result);row['cursor']+=1;row['waiting_use']=None
        if not row['paid']:raise ValueError('native Order did not pay its original action')
        activation['priority_payment']=(row.get('priority_receipt') or {}).get('id')
        activation['phase']='complete';activation['integrity']=_seal(activation)
        targets=[c['target'] for c in row['assignments']]
        engine._commander_order_scope=None
        CHEER.complete_native_order(engine,owner,targets,activation['feature'],origin={
            'kind':'commander_order','source':activation['feature'],'activation_id':activation['id']})
        return {'status':'applied','feature':activation['feature'],'modifier':activation['modifier'],
                'complex_orders':activation['complex_orders'],'target_ids':[c.entity_id for c in targets],
                'results':row['results']}
    except PASSIVE.PassiveEventPending:
        raise
    except Exception:
        engine._commander_order_scope=None
        raise


def no_opportunity(engine, mover):
    if not engine.encounter_active or getattr(engine, '_active_turn_actor', None) is not mover:
        return False
    import world_entities as W
    index = W.actor_index(engine)
    validate_world(engine,index)
    serial = mover.custom_conditions.get('combat_turn_serial', 0)
    return any(row['feature'] == MOBILIZE and row['encounter'] == engine._party_encounter_epoch
               and row['target_id'] == mover.entity_id and row['target_turn'] == serial
               for owner in index.values() for row in uses(owner))


def mobilize_source(rules, receipt, edition):
    import source_context as S
    if edition not in ('core','local_translation','local_csv'):
        raise ValueError('explicit reviewed Mobilize source choice required')
    if edition=='local_csv':
        import commander_orders as O
        S.verified_source(rules,{'file':'input/db/feats.csv','sha256':O.CSV_SHA})
        return {'file':'input/db/feats.csv','sha256':O.CSV_SHA,'record':84,
                'cell_sha256':'5aef5f0f947f504d2e59cc8b399d445c4cf14b81f27c77f4131ad26a0d002928'}
    source=deepcopy(receipt['source'])
    if edition=='core':
        from hashlib import sha256
        from pathlib import Path
        file='output/source-audit/2026-10-10/ptu-core-1.05.pdf'
        if sha256((Path(rules.root)/file).read_bytes()).hexdigest()!=CORE_SHA:
            raise ValueError('original Core Mobilize source changed')
        source['interpretation']={'file':file,'sha256':CORE_SHA,'pages':[80,81]}
    return source


def mobilize(engine, actor, target, *, edition='core'):
    import state_grants as G, turn as TURN, cheerleader as CHEER
    receipt = acquired(actor, MOBILIZE)
    if receipt is None:
        raise ValueError('actual acquired Mobilize required')
    selected_source=mobilize_source(engine.r,receipt,edition)
    ally(engine, actor, target)
    if not engine.encounter_active:
        raise ValueError('Mobilize requires an actual active encounter')
    epoch = engine._party_encounter_epoch
    if any(row['feature'] == MOBILIZE and row['target_id'] == target.entity_id and row['encounter'] == epoch
           for row in uses(actor)):
        raise ValueError('Mobilize may target this actual ally only once per encounter')
    def apply(e, owner, recipient):
        if scope(e,owner) is None:__import__('commander_orders').deliver(e,owner,recipient,MOBILIZE)
        if not TURN.spend(e, owner, 'free', MOBILIZE):
            return (0, 1)
        row = {'feature': MOBILIZE, 'issuer_id': owner.entity_id, 'target_id': recipient.entity_id,
               'encounter': e._party_encounter_epoch,
               'target_turn': recipient.custom_conditions.get('combat_turn_serial', 0) + 1,
               'source_request': receipt['request_id'], 'source': selected_source,'edition':edition,'at':e.elapsed_seconds}
        row['integrity'] = _seal(row)
        owner.spec.setdefault(USES, []).append(row)
        e.time_actors([owner, recipient])
        if scope(e, owner) is None:CHEER.complete_native_order(e, owner, [recipient], MOBILIZE,
            origin={'kind':'mobilize','source':MOBILIZE,'use_index':len(uses(owner))})
        return deepcopy(row)
    return G.transition(engine, actor, apply, participants=(target,), include_rulings=True)


def validate_world(engine, index):
    import common_checks as C
    for owner in index.values():
        seen = set()
        for row in uses(owner):
            fields = {'feature', 'issuer_id', 'target_id', 'encounter', 'target_turn',
                      'source_request', 'source', 'edition', 'at', 'integrity'}
            if (type(row) is not dict or set(row) != fields or row['feature'] != MOBILIZE
                    or row['issuer_id'] != owner.entity_id or row['target_id'] not in index
                    or row['integrity'] != _seal(row)):
                raise ValueError('Mobilize actual source, target and clock evidence changed')
            C.integer(row['encounter'], 'Mobilize encounter identity', 1)
            C.integer(row['target_turn'], 'Mobilize actual target turn', 1)
            if row['encounter'] > engine._party_encounter_epoch:
                raise ValueError('Mobilize encounter evidence is ahead of the actual encounter')
            key = (row['encounter'], row['target_id'])
            if key in seen:
                raise ValueError('Mobilize repeated its actual ally encounter quota')
            seen.add(key)
            matches = [r for r in receipts(owner, MOBILIZE) if r['request_id'] == row['source_request']]
            if len(matches) != 1 or mobilize_source(engine.r,matches[0],row['edition']) != row['source']:
                raise ValueError('Mobilize requires its actual historical acquisition source')
        for uid in owner.spec.get('commander_gifts', {}):
            gifted(owner, uid)
        for row in owner.spec.get(ACTIVATIONS, []):
            if (type(row) is not dict or set(row) != {'id', 'feature', 'modifier', 'complex_orders', 'issuer_id',
                    'encounter', 'orders', 'source_requests', 'priority_payment', 'at', 'phase','integrity'} or row['issuer_id'] != owner.entity_id
                    or row['integrity'] != _seal(row)):
                raise ValueError('Commander actual activation evidence changed')
            C.integer(row['encounter'],'Commander activation encounter',1)
            C.integer(row['at'],'Commander activation time',0,engine.elapsed_seconds)
            if row['phase'] not in ('applying','complete'):raise ValueError('actual Commander activation phase required')
            if row['phase']=='applying':
                current=scope(engine,owner)
                if current is None or current['activation'] is not row:raise ValueError('pending Commander batch lost its native owner')
                if not current['executing']:
                    if current.get('integrity')!=_seal(_scope_proof(current)):
                        raise ValueError('pending Commander native choices or continuation changed')
                    if (current['cursor']!=len(current['results']) or not 0<=current['cursor']<len(row['orders'])
                            or current['waiting_use'] is None or not current['paid']
                            or [{'target_id':c['target'].entity_id,'feature':c['feature']} for c in current['assignments']]!=row['orders']):
                        raise ValueError('pending Commander actual child or recipient sequence changed')
            if (row['modifier'] not in (None,BATTLE,TIP,SCHEME) or type(row['complex_orders'])is not bool
                    or type(row['orders'])is not list or not row['orders'] or not _targeted_identity(engine.r,row['feature'])
                    or len({entry.get('target_id') for entry in row['orders']})!=len(row['orders'])
                    or any(type(entry)is not dict or set(entry)!={'target_id','feature'}
                           or entry['target_id'] not in index or not _targeted_identity(engine.r,entry['feature']) for entry in row['orders'])):
                raise ValueError('Commander actual native activation target or Order changed')
            if row['priority_payment'] is not None:
                payments=[p for p in __import__('priority_limited').records(owner) if p['id']==row['priority_payment']]
                if (len(payments)!=1 or not any(e['feature']==payments[0]['source'] for e in row['orders'])
                        or payments[0]['payment']['funded']!=priority_funded(owner,row['feature'],row['priority_payment'])):
                    raise ValueError('Commander native Priority payment lost its actual action costs')
            expected=([row['modifier']] if row['modifier'] else [])+([COMPLEX] if row['complex_orders'] else [])
            if set(row['source_requests'])!=set(expected):raise ValueError('Commander actual modifier source set changed')
            for feature, request in row['source_requests'].items():
                if not any(r['request_id'] == request for r in receipts(owner, feature)):
                    raise ValueError('Commander actual modifier acquisition evidence changed')
    return True
