"""Printed Ravager/Marksman/Trickster/Guardian/Precision Order consumers.

Native Move, accuracy, damage, movement and defense owners supply occurrences;
callers cannot claim that an attack, interception or Shift already happened.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from contextlib import contextmanager
from contextvars import ContextVar
import commander as C
_STRIKE=ContextVar('commander_actual_strike_again',default=None)

STRIKE = 'feat/재공격'
LONG = 'feat/롱-샷'
DAZZLING = 'feat/매혹적인-데르비시'
BRACE = 'feat/충격-대비'
SENTINEL = 'feat/초계-자세'
PERFECT = 'feat/완벽한-에임'
KEY = 'general_order_instances'
USES = 'general_order_uses'
FEATURES = {
    STRIKE: {'span': (748, 752), 'csv': 22, 'frequency': {'kind': 'scene', 'uses': 1}},
    LONG: {'span': (765, 769), 'csv': 25, 'frequency': {'kind': 'scene', 'uses': 2}},
    DAZZLING: {'span': (782, 786), 'csv': 28, 'frequency': {'kind': 'scene', 'uses': 2}},
    BRACE: {'span': (793, 797), 'csv': 30, 'frequency': {'kind': 'at_will', 'uses': 1}},
    SENTINEL: {'span': (799, 803), 'csv': 31, 'frequency': {'kind': 'scene', 'uses': 2}},
    PERFECT: {'span': (816, 819), 'csv': 34, 'frequency': {'kind': 'scene', 'uses': 2}},
}
CSV_SHA = '4435ff1c462a211564c85d2c1c9a2ac6e7c790c7545e1ad7056d32888b2367bd'


def _seal(row):
    import trainer_feature_acquisition as T
    return T._digest('general-order/instance/v1', {k: v for k, v in row.items() if k != 'integrity'})


def _source(rules, feature, edition):
    import source_context as S
    if edition not in ('core', 'local_csv', 'local_translation'):
        raise ValueError('explicit reviewed Core or local source choice required')
    if rules._selected_rule(feature) != feature:
        raise ValueError('selected general Order variant requires its own native adapter')
    S.verified_source(rules, {'file': 'input/ch03-skills-edges-feats.md', 'sha256': C.GENERAL_SHA})
    row = {'edition': edition, 'feature': feature, 'file': 'input/ch03-skills-edges-feats.md',
           'sha256': C.GENERAL_SHA, 'span': list(FEATURES[feature]['span'])}
    if edition == 'core':
        file = 'output/source-audit/2026-10-10/ptu-core-1.05.pdf'
        if sha256((Path(rules.root) / file).read_bytes()).hexdigest() != C.CORE_SHA:
            raise ValueError('reviewed original Core Orders source changed')
        row['interpretation'] = {'file': file, 'sha256': C.CORE_SHA, 'pages': [60, 61, 62]}
    elif edition == 'local_csv':
        S.verified_source(rules, {'file': 'input/db/feats.csv', 'sha256': CSV_SHA})
        row = {'edition': edition, 'feature': feature, 'file': 'input/db/feats.csv',
               'sha256': CSV_SHA, 'record': FEATURES[feature]['csv']}
    elif feature in (DAZZLING, PERFECT):
        raise ValueError('ambiguous local translated Order requires an explicit source ruling')
    return row


def reckless_source(rules, edition):
    if edition!='core':raise ValueError('existing local Reckless Advance source remains with its native owner')
    import source_context as S
    S.verified_source(rules,{'file':'input/ch03-skills-edges-feats.md','sha256':C.GENERAL_SHA})
    file='output/source-audit/2026-10-10/ptu-core-1.05.pdf'
    if sha256((Path(rules.root)/file).read_bytes()).hexdigest()!=C.CORE_SHA:raise ValueError('original Core Reckless source changed')
    return {'edition':edition,'file':'input/ch03-skills-edges-feats.md','span':[742,746],'sha256':C.GENERAL_SHA,
            'interpretation':{'file':file,'sha256':C.CORE_SHA,'pages':[60]}}


def records(actor):
    rows = actor.spec.get(KEY, [])
    if type(rows) is not list:raise ValueError('general Order instances must be a list')
    return rows

def transfer_baton(engine,old,new,identifiers,*,source,recall_id=None,scope='stratagems',clocks=None):
    """Move selected live Orders with their original issuer, bindings and clocks."""
    if source not in ('feat/태그-인','move/배턴터치'):raise ValueError('reviewed Baton transfer source required')
    if scope not in ('orders','stratagems'):raise ValueError('reviewed Baton scope required')
    actual=[r for r in live(engine,old,None if scope=='orders' else BRACE) if r['id'] in identifiers]
    if [r['id'] for r in actual]!=identifiers:raise ValueError('actual recalled general Order instances changed')
    for row in actual:
        if recall_id is not None:
            import native_order_transfer as TRANSFER
            clock=clocks[row['id']]
            TRANSFER.observe(engine,old,new,row,source,recall_id,clock=clock)
            if clock['phase']=='pending' and row['turn_owner_id']==old.entity_id:
                row['turn_owner_id']=new.entity_id;row['deadline']+=clock['shift']
        row.setdefault('baton_transfers',[]).append({'source':source,'from':old.entity_id,'to':new.entity_id,'at':engine.elapsed_seconds})
        row['target_id']=new.entity_id
        if recall_id is None and row['turn_owner_id']==old.entity_id:row['turn_owner_id']=new.entity_id
        row['integrity']=_seal(row)
        records(old).remove(row);new.spec.setdefault(KEY,[]).append(row)
    return [row['id'] for row in actual]


def find_use(actor,identifier):
    rows=[r for r in actor.spec.get(USES,[]) if r['id']==identifier]
    if len(rows)!=1 or rows[0]['integrity']!=_seal(rows[0]):raise ValueError('actual general Order activation required')
    return rows[0]


def result(engine,actor,use):
    if use['phase']!='complete':raise ValueError('actual completed general Order required')
    if use['feature']==STRIKE:
        completion=engine._move_completions[use['completion_id']]
        return {'feature':STRIKE,'target_id':use['target_id'],'damage':sum(r.get('dealt',0) for r in completion['results'].values()),'source':deepcopy(use['source'])}
    import world_entities as W
    return deepcopy(next(r for actual in W.actor_index(engine).values() for r in records(actual) if r['id']==use['instance']))


def finish_use(engine,owner,use):
    if use['phase']=='complete':return
    use['phase']='complete';use['integrity']=_seal(use)
    scope=C.scope(engine,owner)
    if scope is None:
        import world_entities as W
        __import__('cheerleader').complete_native_order(engine,owner,[W.actor_index(engine)[use['target_id']]],
            use['feature'],origin={'kind':'general_order','source':use['feature'],'use_id':use['id']})
    elif not scope['executing']:
        C.continue_orders(engine)


def _clock(engine, row):
    import world_entities as W
    return W.actor_index(engine).get(row['turn_owner_id'])


def live(engine, actor, feature=None):
    result = []
    for row in records(actor):
        if row.get('integrity')!=_seal(row):raise ValueError('general Order actual instance evidence changed')
        if feature is not None and row['feature'] != feature:continue
        if row['ended'] or not engine.encounter_active or row['encounter'] != engine._party_encounter_epoch:continue
        if row['lifetime'] == 'sustained':
            import action_points as AP, world_entities as W
            owner = W.actor_index(engine).get(row['issuer_id'])
            if owner is None or AP.ActionPointAccount(owner).identified_bindings(allow_missing=True).get(row['id']) != 2:
                raise ValueError('Brace requires its actual matching two AP reservation')
        else:
            import native_order_transfer as TRANSFER
            if row.get(TRANSFER.KEY,{}).get('turn_anchor') is not None:
                if not TRANSFER.active_window(engine,actor,row):continue
                result.append(row);continue
            clock = _clock(engine, row)
            serial = clock.custom_conditions.get('combat_turn_serial', 0) if clock is not None else None
            if clock is None:raise ValueError('Order requires its actual turn owner')
            if serial > row['deadline'] or (serial == row['deadline'] and not clock.custom_conditions.get('blessing_ignore_turn_open')):
                continue
        result.append(row)
    return result


def owns(actor, feature):
    import acquired_features as A
    bundle = next(uid for uid, row in C.BUNDLES.items() if feature in row['children'])
    if not A.owned_rule_count(actor, feature) or C.acquired(actor, bundle) is None:
        raise ValueError('actual acquired Orders bundle and its known Order required')
    return True


def acquisition(actor,feature):
    bundle=next(uid for uid,row in C.BUNDLES.items() if feature in row['children'])
    receipt=C.acquired(actor,bundle)
    if receipt is None:raise ValueError('actual general Order acquisition receipt required')
    return {'bundle':bundle,'request_id':receipt['request_id']}


def validate_acquisition(actor,feature,proof):
    bundle=next(uid for uid,row in C.BUNDLES.items() if feature in row['children'])
    if type(proof)is not dict or set(proof)!={'bundle','request_id'} or proof['bundle']!=bundle:
        raise ValueError('general Order acquisition bundle changed')
    rows=C.receipts(actor,bundle)+[r for r in C.receipts(actor,C.CLASS) if r['snapshot']['branch']==bundle]
    if not any(r['request_id']==proof['request_id'] for r in rows):
        raise ValueError('general Order historical bundle acquisition required')


def target(engine, actor, recipient):
    import world_entities as W, pokemon_activities as P
    W.require_actors(engine, actor, recipient)
    if not (C.transformed_target(engine, actor, recipient) or C.leadership_target(engine, actor, recipient)):
        P._pokemon(recipient);P._owner(actor, recipient)
    if recipient.fainted or recipient.captured or not recipient.on_field:
        raise ValueError('actual conscious available Order recipient required')
    return True


def deliver(engine, actor, recipient, feature):
    import perception_communicate as COMM
    policy = {'id': 'general-order:' + feature, 'source': feature, 'capabilities': [], 'requirements': [],
              'mode': 'auditory', 'range': None, 'path': 'auditory', 'medium': [],
              'consent': {'kind': 'none'}, 'blockers': [], 'connection': None,
              'frequency': {'kind': 'at_will', 'uses': 1}, 'retry': None, 'distance_exceptions': []}
    state = getattr(engine, COMM.KEY, {'attempts': []})
    result = COMM.send(engine, actor, recipient, policy, 'Orders: ' + feature,
                       request_id='general-order:' + actor.entity_id + ':' + str(len(state['attempts']) + 1))
    if result['status'] != 'delivered':
        raise ValueError('actual Order communication was not delivered: '+str(result.get('reason')))
    return result


def _frequency(engine, actor, feature):
    import frequency as F
    scope = C.scope(engine, actor, feature)
    if scope is not None and feature in scope['frequencies']:return
    freq = FEATURES[feature]['frequency']
    if not F.activation_allowed(actor, feature, freq, engine=engine):
        raise ValueError('actual Order Scene frequency exhausted')
    F.consume_activation(actor, feature, freq, engine=engine)
    if scope is not None:scope['frequencies'].append(feature)


def use(engine, actor, recipient, feature, *, edition='core', attack=None):
    import state_grants as G, turn as TURN, action_points as AP, class_passive_combat as P
    if feature not in FEATURES:raise ValueError('reviewed actual general Order required')
    owns(actor, feature);target(engine, actor, recipient)
    source = _source(engine.r, feature, edition)
    if not engine.encounter_active:raise ValueError('Orders require an actual active encounter')
    if feature != STRIKE and attack is not None:raise ValueError('only Strike Again accepts an immediate attack choice')
    if feature == STRIKE and (type(attack) is not dict or set(attack) != {'move', 'target_id'}):
        raise ValueError('Strike Again requires one actual immediate At-Will attack choice')
    def apply(e, owner, ally):
        if C.scope(e, owner) is None:deliver(e, owner, ally, feature)
        if feature == BRACE:
            P._require_stratagem_slot(ally)
            if live(e, ally, BRACE):raise ValueError('only one actual Stratagem may be sustained')
            if AP.available(owner) < 2:raise ValueError('Brace for Impact requires two AP')
            __import__('temporary_ap').preflight_binding(owner, 2, 'commander_orders')
        _frequency(e, owner, feature)
        if not TURN.spend(e, owner, 'standard', feature):
            raise ValueError('actual Standard Order action unavailable')
        use={'id':'general-order:'+owner.entity_id+':'+str(len(owner.spec.get(USES,[]))+1),
             'feature':feature,'issuer_id':owner.entity_id,'target_id':ally.entity_id,'source':source,
             'acquisition':acquisition(owner,feature),'at':e.elapsed_seconds,'phase':'applying',
             'instance':None,'completion_id':None,'attack':deepcopy(attack)}
        use['integrity']=_seal(use);owner.spec.setdefault(USES,[]).append(use)
        active_scope=C.scope(e,owner)
        if active_scope is not None and feature==STRIKE:active_scope['waiting_use']=use['id']
        if feature == STRIKE:
            import world_entities as W, action_lifecycle as A, frequency as F
            victim = W.actor_index(e).get(attack['target_id'])
            if victim is None:raise ValueError('actual immediate attack target required')
            move = e.r.move(attack['move'])
            if move['class'] not in ('물리', '특수') or F.move_frequency(e, attack['move'], ally)[0] != 'at_will':
                raise ValueError('Strike Again requires an actual damaging At-Will attack')
            if attack['move'] != 'struggle' and attack['move'] not in ally.moves:
                raise ValueError('Strike Again requires an actually known attack')
            token=_STRIKE.set((owner.entity_id,use['id']))
            try:
                with A.move_grant(e, ally, victim, attack['move'], source=STRIKE, kind='free') as grant:
                    damage = e.use_move(ally, victim, attack['move'], count_use=True, free_action=True, _action_grant=grant)
            finally:_STRIKE.reset(token)
            if use['phase']!='complete':raise ValueError('Strike Again did not complete an actual immediate attack')
        else:
            identifier = 'orders:' + owner.entity_id + ':' + str(sum(len(records(c)) for c in e.time_actors()) + 1)
            clock = owner if feature in (SENTINEL, PERFECT) and edition == 'core' else ally
            row = {'id': identifier, 'feature': feature, 'issuer_id': owner.entity_id, 'target_id': ally.entity_id,
                   'source': source,'acquisition':acquisition(owner,feature), 'encounter': e._party_encounter_epoch,
                   'turn_owner_id': clock.entity_id, 'deadline': clock.custom_conditions.get('combat_turn_serial', 0) + 1,
                   'lifetime': 'sustained' if feature == BRACE else 'next_turn_end',
                   'ended': False, 'used_rounds': {}, 'consumed_by': None}
            if feature == BRACE:owner.ap_account.charge(2, mode='bind', instance_id=identifier, temporary_binding_owner='commander_orders')
            row['integrity'] = _seal(row)
            ally.spec.setdefault(KEY, []).append(row)
            use['instance']=identifier;use['integrity']=_seal(use)
            e.time_actors([owner, ally, clock]);finish_use(e,owner,use)
        return result(e,owner,use)
    return C.transition_native(engine,actor,apply,participants=(recipient,))


def release(engine, actor, recipient):
    import state_grants as G, turn as T
    row = next((r for r in live(engine, recipient, BRACE) if r['issuer_id'] == actor.entity_id), None)
    if row is None:raise ValueError('actual issuer of the live Brace Stratagem required')
    def apply(e, owner, ally):
        actual = next(r for r in records(ally) if r['id'] == row['id'])
        if not T.spend(e, owner, 'free', BRACE + ' release'):return (0, 1)
        owner.ap_account.release_binding(actual['id'], expected_amount=2)
        actual['ended'] = True;actual['integrity'] = _seal(actual)
        return (1, 0)
    return G.transition(engine, actor, apply, participants=(recipient,))


def end_encounter(engine, actors):
    import world_entities as W
    index = W.actor_index(engine)
    for target in actors:
        for row in records(target):
            if row['ended']:continue
            if row['feature'] == BRACE:
                owner = index.get(row['issuer_id'])
                if owner is None:raise ValueError('actual Brace AP owner required')
                owner.ap_account.release_binding(row['id'], expected_amount=2)
            row['ended'] = True;row['integrity'] = _seal(row)


def end_binding(engine, owner, row):
    if row['feature'] != BRACE or row['issuer_id'] != owner.entity_id or row['ended']:
        raise ValueError('actual live Brace binding owner required')
    owner.ap_account.release_binding(row['id'], expected_amount=2)
    row['ended'] = True;row['integrity'] = _seal(row)


def strike_authority(engine, actor, target, move_id, source):
    frame=_STRIKE.get()
    if source!=STRIKE:return False
    if frame is None:
        raise ValueError('Strike Again requires its actual paid immediate Order')
    import world_entities as W
    owner=W.actor_index(engine).get(frame[0])
    if owner is None:raise ValueError('actual Strike Again issuer required')
    use=find_use(owner,frame[1])
    if (use['feature']!=STRIKE or use['phase']!='applying' or use['target_id']!=actor.entity_id
            or use['attack']!={'move':move_id,'target_id':target.entity_id}):
        raise ValueError('Strike Again actual immediate Move scope changed')
    owns(owner,STRIKE)
    return True


def _damaging(move):return move.get('class') in ('물리', '특수')


def _ranged(move):return _damaging(move) and bool(move.get('range')) and '근접' not in str(move['range'])


def range_spec(engine, actor, move, result):
    if actor is None or not _ranged(move) or not live(engine, actor, LONG):return result
    result = deepcopy(result)
    if type(result.get('origin')) in (int, float):result['origin'] *= 2
    # Area size is unchanged; origin distance alone is the attack's range.
    return result


def distance(engine, actor, victim, move):
    import body_state as B
    if engine.grid is None:
        raise ValueError('Long Shot damage needs an actual traveled-distance observation')
    from grid import cheb
    return min(cheb(a, b) for a in B.attack_cells(engine, actor, move) for b in B.cells(victim, require_complete=True))


def long_damage(engine, actor, victim, move, dice_part, crit):
    if not _ranged(move) or not live(engine, actor, LONG):return 0
    return distance(engine, actor, victim, move) + (dice_part if crit else 0)


def movement_bonus(engine, actor):
    if not live(engine, actor, DAZZLING):return 0
    import class_passive_combat as P
    return max(0, actor.evasion('물리', engine=engine, ignore_stats=True,
                                conditional_bonus=P.evasion_bonus(engine, actor)))


def dazzle(engine, actor, victim):
    if actor is victim or getattr(actor,'side',None) is None or getattr(victim,'side',None) is None or actor.side == victim.side:return
    import combat_timing as T
    for row in live(engine, actor, DAZZLING):
        key = str(engine.round_no) + (':one_foe' if row['source']['edition'] == 'local_csv' else ':' + victim.entity_id)
        if key in row['used_rounds']:continue
        row['used_rounds'][key] = victim.entity_id;row['integrity'] = _seal(row)
        T.install(engine, victim, {'source': DAZZLING, 'all_roll_modifier': -3,
            'turn_owner': victim, 'turn_deadline': victim.custom_conditions.get('combat_turn_serial', 0) + 1})


def shifted(engine, actor, path):
    if not live(engine, actor, DAZZLING):return
    import body_state as B, world_entities as W
    traversed = set()
    for point in path:traversed.update(B.at_position(actor, point))
    for victim in W.actor_index(engine).values():
        if victim is not actor and victim.on_field and not victim.captured and traversed.intersection(B.cells(victim, require_complete=True)):
            dazzle(engine, actor, victim)


def passers(engine, actor):
    if not live(engine,actor,DAZZLING):return ()
    import world_entities as W
    return tuple(c for c in W.actor_index(engine).values() if c is not actor and c.on_field
                 and not c.captured and getattr(actor,'side',None) is not None and getattr(c,'side',None) is not None and c.side!=actor.side)


def path_passers(engine, actor, path, *, mode, remaining):
    """Only cross occupied cells when this paid Shift can reach a free cell."""
    foes=passers(engine,actor)
    if not foes or mode not in ('land','육상'):return ()
    import body_state as B,movement_actions as M
    origin=actor.pos;diagonals=getattr(actor,'_diagonal_steps',0);cost=0
    occupied=set().union(*(set(B.cells(c,require_complete=True)) for c in foes))
    for point in path:
        q=tuple(point[:2]);step,diagonals=M.step_cost(origin,q,diagonals)
        cost+=step+M.slow_terrain_penalty(engine,actor,q,mode,step=step)
        if cost>remaining:return ()
        if not occupied.intersection(B.at_position(actor,q)):
            return foes if B.can_place(engine,actor,q,origin=origin) else ()
        origin=q
    return ()


def move_interested(engine, actor, target):
    return bool(live(engine,actor) or live(engine,target))


def brace(engine, actor, *, standard=False):
    import combat_timing as T, turn as TURN
    rows = live(engine, actor, BRACE)
    if not rows:return False
    row = rows[0]
    key = ('round:' + str(engine.round_no) if row['source']['edition'] == 'core'
           else 'turn:' + str(actor.custom_conditions.get('combat_turn_serial', 0)))
    if key in row['used_rounds']:return False
    if standard:
        if not TURN.spend(engine, actor, 'standard', BRACE):raise ValueError('actual Standard Brace action unavailable')
    else:
        choice = engine.rulings.decide({'type': 'brace_for_impact', 'unit': BRACE, 'actor': actor.name,
            'text': 'Gain Brace for Impact damage reduction from the actual self-targeting Status Move?'})
        if choice is None or choice is False:return False
        if choice is not True:raise ValueError('explicit optional Brace choice required')
    row['used_rounds'][key] = actor.entity_id;row['integrity'] = _seal(row)
    T.install(engine, actor, {'source': BRACE, 'commander_brace_dr': 5, 'turn_owner': actor,
        'turn_deadline': actor.custom_conditions.get('combat_turn_serial', 0) + 1})
    return True


def reduction(actor):
    import combat_timing as T
    return max((row.get('commander_brace_dr', 0) for row in T.records(actor)), default=0)


def after_move(engine, actor, target, move):
    if move.get('class') == '변화' and actor is target:
        import weapon_actions as W
        if W.is_self_only(W.range_spec(engine, move, actor)):brace(engine, actor)
    elif _damaging(move):dazzle(engine, actor, target)


def perfect(engine, actor, move):
    if not _damaging(move):return None
    rows = live(engine, actor, PERFECT)
    return rows[0] if rows else None


def perfect_for_move(engine, actor, move):
    identifier = move.get('_commander_perfect')
    if identifier is None:return False
    rows = [row for row in records(actor) if row['id'] == identifier and row['feature'] == PERFECT]
    if len(rows) != 1 or rows[0]['integrity'] != _seal(rows[0]):
        raise ValueError('Perfect Aim requires its actual bound Order instance')
    row = rows[0]
    completion = getattr(engine, '_move_completions', {}).get(row['consumed_by'])
    if (completion is None or completion['actor'] is not actor or completion['move_id'] != move['id']
            or completion['phase'] in ('complete', 'interrupted') or row['ended']):
        raise ValueError('Perfect Aim belongs to the actual unfinished damaging Move')
    return True


def begin_move(engine, actor, target, move, completion_id):
    frame=_STRIKE.get()
    if frame is not None:
        import world_entities as W
        owner=W.actor_index(engine)[frame[0]];use=find_use(owner,frame[1])
        if use['target_id']==actor.entity_id and use['attack']=={'move':move['id'],'target_id':target.entity_id}:
            strike_authority(engine,actor,target,move['id'],STRIKE)
            if use['completion_id'] not in (None,completion_id):raise ValueError('Strike Again actual Move completion changed')
            use['completion_id']=completion_id;use['integrity']=_seal(use)
            engine._move_completions[completion_id]['commander_strike']={'issuer_id':owner.entity_id,'use_id':use['id']}
    row = perfect(engine, actor, move)
    if row is not None:
        if row['consumed_by'] not in (None, completion_id):
            raise ValueError('Perfect Aim already belongs to another damaging attack')
        row['consumed_by'] = completion_id;row['integrity'] = _seal(row)
        move['_commander_perfect'] = row['id']
        engine._move_completions[completion_id]['target_moves'][target.entity_id]['_commander_perfect'] = row['id']
        engine._move_completions[completion_id]['commander_perfect'] = row['id']


def mark_complete(engine,completion):
    actor=completion['actor']
    proof=completion.get('commander_strike')
    if proof is not None:
        import world_entities as W
        owner=W.actor_index(engine)[proof['issuer_id']];use=find_use(owner,proof['use_id'])
        use['phase']='complete';use['integrity']=_seal(use)
    identifier = completion.get('commander_perfect')
    if identifier is not None:
        row = next(row for row in records(actor) if row['id'] == identifier)
        if row['consumed_by'] != completion['id']:
            raise ValueError('Perfect Aim actual completed Move changed')
        row['ended'] = True;row['integrity'] = _seal(row)


def after_completion(engine, completion):
    actor=completion['actor'];move=completion['move']
    for target in completion['targets']:
        result=completion['results'].get(target.entity_id,{})
        if not result.get('cancelled',False):after_move(engine,actor,target,move)
    proof=completion.get('commander_strike')
    if proof is not None:
        import world_entities as W
        owner=W.actor_index(engine)[proof['issuer_id']];use=find_use(owner,proof['use_id'])
        current=C.scope(engine,owner)
        if current is None:
            __import__('cheerleader').complete_native_order(engine,owner,[W.actor_index(engine)[use['target_id']]],
                STRIKE,origin={'kind':'general_order','source':STRIKE,'use_id':use['id']})
        elif not current['executing']:C.continue_orders(engine)


def ignore_defensive(engine, actor, target):
    for row in live(engine,actor,PERFECT):
        completion=getattr(engine,'_move_completions',{}).get(row['consumed_by'])
        if completion is not None and completion['phase'] not in ('complete','interrupted') and target in completion['targets']:
            return True
    return False


def blocks_blessing(engine, actor):
    event = getattr(engine, '_passive_events', {}).get(getattr(engine, '_passive_pending', None))
    return bool(event and event.get('target') is actor and
                perfect_for_move(engine, event['actor'], event['move']))


def sentinel_profile(engine, actor):
    rows = live(engine, actor, SENTINEL)
    if not rows:return None
    row = rows[0]
    return {'action': 'shift', 'payment': 'next', 'budget': {'shift': 1},
            'modifier_sources': [{'source_id': SENTINEL, 'actor_id': actor.entity_id,
                                  'order_instance': row['id'], 'source': deepcopy(row['source'])}]}


def validate_sentinel_profile(engine, actor, value, *, historical):
    sources = value.get('modifier_sources', [])
    if len(sources) != 1 or sources[0].get('source_id') != SENTINEL:return False
    proof = sources[0]
    rows = [row for row in records(actor) if row['id'] == proof.get('order_instance') and row['feature'] == SENTINEL]
    if (len(rows) != 1 or value != {'action': 'shift', 'payment': 'next', 'budget': {'shift': 1},
            'modifier_sources': [{'source_id': SENTINEL, 'actor_id': actor.entity_id,
                'order_instance': rows[0]['id'], 'source': rows[0]['source']}]}
            or not historical and rows[0] not in live(engine, actor, SENTINEL)):
        raise ValueError('Sentinel Intercept requires its actual source-owned stance')
    return True


def sentinel_attempt(engine, actor, facts):
    if validate_sentinel_profile(engine, actor, facts.get('cost_profile', {}), historical=False):
        facts['sentinel'] = {'instance': facts['cost_profile']['modifier_sources'][0]['order_instance'], 'damage_reduction': 10}
        brace(engine, actor)


def sentinel_reduction(engine, actor, event):
    if not event or event.get('passive_event') is None:return 0
    native = engine._passive_events.get(event['passive_event'])
    if native is None:return 0
    import move_defense_reactions as D
    parent = engine._passive_events.get(native.get('defense_parent'), native)
    state = D._defense(engine, parent)
    if state is None:return 0
    attempts = [row for row in state['attempts'] if row.get('actor_id') == actor.entity_id
                and row.get('paid') and row.get('sentinel')]
    return 10 if attempts else 0


def validate_world(engine, index):
    import common_checks as CHECKS
    ids = set();use_ids=set()
    for target in index.values():
        for use in target.spec.get(USES,[]):
            fields={'id','feature','issuer_id','target_id','source','acquisition','at','phase','instance','completion_id','attack','integrity'}
            if (type(use)is not dict or set(use)!=fields or use['issuer_id']!=target.entity_id
                    or use['target_id'] not in index or use['feature'] not in FEATURES
                    or use['id'] in use_ids or use['integrity']!=_seal(use) or use['phase'] not in ('applying','complete')):
                raise ValueError('actual general Order activation evidence changed')
            use_ids.add(use['id'])
            if use['source']!=_source(engine.r,use['feature'],use['source'].get('edition')):raise ValueError('general Order activation source changed')
            validate_acquisition(target,use['feature'],use['acquisition'])
            CHECKS.integer(use['at'],'general Order activation time',0,engine.elapsed_seconds)
            if use['feature']==STRIKE:
                completion=getattr(engine,'_move_completions',{}).get(use['completion_id'])
                if completion is None:
                    if _STRIKE.get()!=(target.entity_id,use['id']):raise ValueError('Strike Again lost actual child Move')
                elif (completion['actor'] is not index[use['target_id']] or completion['move_id']!=use['attack']['move']
                      or completion.get('commander_strike')!={'issuer_id':target.entity_id,'use_id':use['id']}
                      or (use['phase']=='complete')!=(completion['phase']=='complete')):
                    raise ValueError('Strike Again actual child Move provenance changed')
            elif use['phase']!='complete' or use['attack']is not None or use['completion_id']is not None:
                raise ValueError('persistent general Order requires actual completed activation')
        for row in records(target):
            fields = {'id', 'feature', 'issuer_id', 'target_id', 'source', 'acquisition', 'encounter', 'turn_owner_id',
                      'deadline', 'lifetime', 'ended', 'used_rounds', 'consumed_by', 'integrity'}
            if (type(row) is not dict or set(row)-{'baton_transfers','native_order_handoff'} != fields or row['id'] in ids or row['feature'] not in FEATURES
                    or row['target_id'] != target.entity_id or row['issuer_id'] not in index
                    or row['turn_owner_id'] not in index or row['integrity'] != _seal(row)):
                raise ValueError('general Order actual source, clock or recipient evidence changed')
            ids.add(row['id']);CHECKS.integer(row['encounter'], 'Order encounter identity', 1)
            CHECKS.integer(row['deadline'], 'Order turn deadline', 1)
            if row['source'] != _source(engine.r, row['feature'], row['source'].get('edition')):
                raise ValueError('general Order source selection changed')
            validate_acquisition(index[row['issuer_id']],row['feature'],row['acquisition'])
            if row['encounter']>engine._party_encounter_epoch:raise ValueError('general Order encounter is ahead of actual encounter')
            if row['lifetime'] != ('sustained' if row['feature'] == BRACE else 'next_turn_end'):
                raise ValueError('general Order native lifetime changed')
            if type(row['ended']) is not bool or type(row['used_rounds']) is not dict:
                raise ValueError('typed general Order state required')
            live(engine, target, row['feature'])
    return True
