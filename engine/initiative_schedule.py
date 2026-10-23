"""Actual participant slots and declared phase order over native turns.

Slots preserve one round's turn right across replacement. Source declarations
own phase layout; the shared initiative reader owns values and explicit ties.
This module never infers controller/player identity from a name or a side.
"""
from copy import deepcopy
import common_checks as C
import initiative as INIT
import initiative_derivation as DERIVE
import world_entities as WORLD
import state_grants as GRANTS

KEY = '_initiative_schedule'


def _text(value, label):
    if type(value) is not str or not value.strip():
        raise ValueError(label+' requires a nonempty identity')
    return value


def _current(state):
    return state['steps'][state['cursor']] if state['cursor'] < len(state['steps']) else None


def status(engine):
    state = getattr(engine, KEY, None)
    if state is None:
        return {'status':'not_attached','next':None}
    step = _current(state)
    next_step = None if step is None else dict(step, actor_id=state['slots'][step['slot']]['actor'].entity_id)
    return {'status':state['status'],'round':state['round'],'source':state['source'],
            'next':next_step,'completed_steps':state['cursor'],'total_steps':len(state['steps'])}


def _layout(slots, order, layout):
    if type(layout) is not list or not layout:
        raise ValueError('nonempty declared phase layout required')
    steps = []; names = set(); turns = []
    for phase in layout:
        if type(phase) is not dict or set(phase) != {'id','roles','reverse','declaration'}:
            raise ValueError('exact phase identity, roles, direction and declaration fields required')
        name = _text(phase['id'],'phase')
        if name in names:
            raise ValueError('duplicate phase identity')
        names.add(name)
        roles = phase['roles']
        if (type(roles) is not list or not roles or any(type(x) is not str or not x for x in roles)
                or len(roles) != len(set(roles)) or ('*' in roles and len(roles) != 1)):
            raise ValueError('distinct declared phase roles required')
        if type(phase['reverse']) is not bool or type(phase['declaration']) is not bool:
            raise ValueError('explicit boolean phase direction and declaration required')
        selected = [key for key in order if roles == ['*'] or slots[key]['role'] in roles]
        if phase['reverse']:
            selected.reverse()
        for key in selected:
            kind = 'declaration' if phase['declaration'] else 'turn'
            steps.append({'phase':name,'slot':key,'kind':kind})
            if kind == 'turn':
                turns.append(key)
    if len(turns) != len(set(turns)) or set(turns) != set(slots):
        raise ValueError('each participant slot needs exactly one resolution turn')
    declared = [step['slot'] for step in steps if step['kind']=='declaration']
    if len(declared) != len(set(declared)):
        raise ValueError('each slot may declare only once per schedule')
    for key in declared:
        if next(i for i,s in enumerate(steps) if s['slot']==key and s['kind']=='declaration') > next(i for i,s in enumerate(steps) if s['slot']==key and s['kind']=='turn'):
            raise ValueError('declaration must precede its own resolution')
    return steps


def _groups(slots, groups):
    groups = [['*']] if groups is None else groups
    if type(groups) is not list or not groups:
        raise ValueError('declared order groups required')
    result = []
    for roles in groups:
        if type(roles) is not list or not roles or any(type(r) is not str or not r for r in roles):
            raise ValueError('explicit group roles required')
        if len(roles) != len(set(roles)) or ('*' in roles and roles != ['*']):
            raise ValueError('distinct order-group roles required')
        result.append([key for key,row in slots.items() if roles==['*'] or row['role'] in roles])
    flattened = [key for group in result for key in group]
    if len(flattened) != len(set(flattened)) or set(flattened) != set(slots) or any(not group for group in result):
        raise ValueError('order groups must partition actual participant slots')
    return result


def prepare(engine, participants, *, source, bindings=None, layout=None, procedures=None, order_groups=None):
    """Resolve order before round/time progress; actual IDs bind stable slots."""
    actors = tuple(participants)
    if not actors or len({id(c) for c in actors}) != len(actors):
        raise ValueError('distinct actual participants required')
    WORLD.require_actors(engine,*actors)
    DERIVE.selected(engine.r,source)
    if engine.round_start_seconds is not None or engine._active_turn_actor is not None:
        raise ValueError('schedule preparation requires a closed round and turn')
    old = getattr(engine,KEY,None)
    if old is not None and old['status'] != 'completed':
        raise ValueError('previous schedule has not completed')
    if bindings is None:
        bindings = [{'slot':c.entity_id,'actor_id':c.entity_id,'role':c.kind} for c in actors]
    if type(bindings) is not list or len(bindings) != len(actors):
        raise ValueError('one declared stable slot per actual participant required')
    index = {c.entity_id:c for c in actors}; slots = {}; assigned = set()
    if procedures is not None and (type(procedures) is not dict or set(procedures)-set(index)):
        raise ValueError('initiative procedures must use actual participant identities')
    for row in bindings:
        if type(row) is not dict or set(row) != {'slot','actor_id','role'}:
            raise ValueError('exact slot, actor identity and role binding required')
        key = _text(row['slot'],'slot'); role = _text(row['role'],'role')
        identity = row['actor_id']
        if identity not in index or identity in assigned or key in slots:
            raise ValueError('unique actual participant/slot bindings required')
        assigned.add(identity)
        slots[key] = {'actor':index[identity],'role':role,'turn':'ready'}
    layout = deepcopy(layout if layout is not None else [
        {'id':'ordinary','roles':['*'],'reverse':False,'declaration':False}])
    # Validate layout before consuming an explicit tie decision or random face.
    _layout(slots,list(slots),layout)
    groups = _groups(slots,order_groups)
    import initiative_interrupts as INTERRUPTS
    INTERRUPTS.require_clear(engine)
    def apply(staged,_,*actual):
        actual_index = {c.entity_id:c for c in actual}
        staged_slots = {key:dict(row,actor=actual_index[row['actor'].entity_id]) for key,row in slots.items()}
        actor_slots = {row['actor'].entity_id:key for key,row in staged_slots.items()}
        order = []
        for group in groups:
            group_actors = [staged_slots[key]['actor'] for key in group]
            group_procedures = None if procedures is None else {c.entity_id:procedures[c.entity_id] for c in group_actors if c.entity_id in procedures}
            resolved = INIT.order(staged,group_actors,procedures=group_procedures,
                                  round_no=staged.round_no+1)
            if resolved is None:
                return {'status':'pending','reason':'initiative order requires a decision','consumed':False}
            order.extend(actor_slots[c.entity_id] for c in resolved)
        state = {'version':1,'source':source,'round':staged.round_no+1,'status':'prepared',
                 'slots':staged_slots,'order':order,'layout':deepcopy(layout),
                 'steps':_layout(staged_slots,order,layout),'cursor':0,'open_slot':None,
                 'declarations':{},'records':[],'replacements':[],
                 'initial_bindings':{key:{'actor':row['actor'],'role':row['role']} for key,row in staged_slots.items()}}
        INTERRUPTS.preflight_round(staged,state)
        setattr(staged,KEY,state)
        return status(staged)
    return GRANTS.transition(engine,None,apply,participants=actors,include_rulings=True)


def round_started(engine, participants):
    state = getattr(engine,KEY,None)
    if state is None:
        return
    if state['status'] != 'prepared' or state['round'] != engine.round_no:
        raise ValueError('prepared initiative schedule belongs to another round')
    expected = {id(row['actor']) for row in state['slots'].values()}
    if {id(c) for c in participants} != expected:
        raise ValueError('round participants differ from the prepared schedule')
    state['status'] = 'active'


def _actor_slot(state, actor):
    matches = [key for key,row in state['slots'].items() if row['actor'] is actor]
    if len(matches) != 1:
        raise ValueError('actor has no unique actual schedule slot')
    return matches[0]


def declare(engine, actor, intent):
    """Record detached data; declaring grants no action, budget or owner turn."""
    WORLD.require_actors(engine,actor)
    import root_resolution as ROOT
    intent = ROOT.plain(ROOT.freeze(intent))
    if type(intent) is not dict:
        raise ValueError('structured declaration data required')
    def apply(staged,subject):
        state = getattr(staged,KEY,None)
        if not state or state['status'] != 'active' or state['open_slot'] is not None:
            raise ValueError('active schedule declaration boundary required')
        key = _actor_slot(state,subject); step = _current(state)
        if step is None or step['kind'] != 'declaration' or step['slot'] != key:
            raise ValueError('actor is not next to declare')
        state['declarations'][key] = deepcopy(intent)
        state['records'].append(dict(step,actor=subject,outcome='declared',intent=deepcopy(intent)))
        state['cursor'] += 1
        return status(staged)
    return GRANTS.transition(engine,actor,apply)


def skip_unavailable(engine, actor):
    """Consume the next unavailable participant step without an owner turn."""
    WORLD.require_actors(engine,actor)
    import initiative_interrupts as INTERRUPTS
    INTERRUPTS.require_clear(engine)
    def apply(staged,subject):
        state = getattr(staged,KEY,None)
        if (not state or state['status']!='active' or state['round']!=staged.round_no
                or state['open_slot'] is not None or staged._active_turn_actor is not None):
            raise ValueError('unavailable step requires a closed active schedule boundary')
        key = _actor_slot(state,subject); step = _current(state)
        if step is None or step['slot']!=key or state['slots'][key]['turn']!='ready':
            raise ValueError('actor must own the next unconsumed schedule step')
        observed = dict(fainted=subject.fainted,captured=subject.captured,on_field=subject.on_field)
        if not (observed['fainted'] or observed['captured'] or not observed['on_field']):
            raise ValueError('available participant cannot skip its schedule step')
        if step['kind']=='turn' and INTERRUPTS._due(staged,key) is not None:
            raise ValueError('borrowed turn debt requires its actual settlement')
        state['records'].append(dict(step,actor=subject,outcome='skipped',unavailable=observed))
        if step['kind']=='turn':state['slots'][key]['turn']='closed'
        state['cursor']+=1
        return status(staged)
    return GRANTS.transition(engine,actor,apply)


def skip_switch_locked(engine,actor):
    """Close the actual voluntary-switch slot using its paid party receipt."""
    WORLD.require_actors(engine,actor)
    import initiative_interrupts as INTERRUPTS, party_actions as PARTY
    INTERRUPTS.require_clear(engine)
    def apply(staged,subject):
        state=getattr(staged,KEY,None)
        if (not state or state['status']!='active' or state['round']!=staged.round_no
                or state['open_slot'] is not None or staged._active_turn_actor is not None):
            raise ValueError('switch-locked step requires a closed active schedule boundary')
        key=_actor_slot(state,subject);step=_current(state)
        if (not step or step['kind']!='turn' or step['slot']!=key or state['slots'][key]['turn']!='ready'
                or INTERRUPTS._due(staged,key) is not None):
            raise ValueError('actual next unconsumed switch-locked turn required')
        proof=PARTY.switch_lock(staged,subject)
        if proof is None:raise ValueError('actual voluntary League switch lock required')
        PARTY.validate_switch_lock(staged,subject,proof)
        state['records'].append(dict(step,actor=subject,outcome='switch_locked',switch_lock=proof))
        state['slots'][key]['turn']='closed';state['cursor']+=1
        return status(staged)
    return GRANTS.transition(engine,actor,apply)


def preflight_turn(engine, actor):
    import initiative_interrupts as INTERRUPTS
    if INTERRUPTS.is_borrow_start(engine,actor):
        return
    INTERRUPTS.require_clear(engine)
    state = getattr(engine,KEY,None)
    if state is None:
        return
    if state['status'] != 'active' or state['round'] != engine.round_no or state['open_slot'] is not None:
        raise ValueError('schedule has no open resolution boundary')
    key = _actor_slot(state,actor); step = _current(state)
    if step is None or step['kind'] != 'turn' or step['slot'] != key or state['slots'][key]['turn'] != 'ready':
        raise ValueError('actor does not own the next unconsumed schedule turn')
    INTERRUPTS.preflight_ordinary(engine,key)


def select_mounted_turn(engine,actor):
    """Exchange two still-unused turn steps while their actual slots stay bound."""
    state=getattr(engine,KEY,None)
    import initiative_interrupts as INTERRUPTS
    if state is None or INTERRUPTS.is_borrow_start(engine,actor):return
    step=_current(state)
    if (state['status']!='active' or state['open_slot'] is not None or engine._active_turn_actor is not None
            or step is None or step['kind']!='turn' or state['slots'][step['slot']]['actor'] is actor):return
    INTERRUPTS.require_clear(engine)
    import control_mount as MOUNT
    current=state['slots'][step['slot']]['actor']
    pair=MOUNT.ride_pair(engine,actor,current)
    if pair is None:return
    key=_actor_slot(state,actor)
    if any(state['slots'][k]['turn']!='ready' or INTERRUPTS._due(engine,k) is not None for k in (key,step['slot'])):
        raise ValueError('Ride as One requires two unconsumed actual turn rights')
    later=next((n for n,s in enumerate(state['steps']) if n>state['cursor'] and s['kind']=='turn' and s['slot']==key),None)
    if later is None:raise ValueError('Ride as One requires its second actual initiative slot')
    receipt=MOUNT.acquired(pair[0],MOUNT.RIDE_AS_ONE)
    row={'cursor':state['cursor'],'later':later,'slot':step['slot'],'other_slot':key,
         'rider':pair[0],'mount':pair[1],'source':MOUNT.RIDE_AS_ONE,'acquisition_request_id':receipt['request_id'],
         'mount_contract_sha256':pair[0].spec[MOUNT.CONTRACT]['sha256']}
    row['sha256']=_exchange_sha(row)
    state.setdefault('mounted_exchanges',[]).append(row)
    state['steps'][state['cursor']]['slot'],state['steps'][later]['slot']=key,step['slot']


def _exchange_sha(row):
    import resolution_transaction as TX
    return TX.request_fingerprint({k:(v.entity_id if k in ('rider','mount') else v)
                                   for k,v in row.items() if k!='sha256'})


def _exchanged_steps(engine,state,bound_at,index):
    steps=_layout(state['slots'],state['order'],state['layout'])
    previous=-1
    for row in state.get('mounted_exchanges',[]):
        at=C.integer(row['cursor'],'mounted initiative cursor',0,state['cursor'])
        later=C.integer(row['later'],'second mounted initiative',at+1,len(steps)-1)
        if at<=previous or row.get('sha256')!=_exchange_sha(row):raise ValueError('mounted initiative exchange evidence changed')
        previous=at
        if (row['slot'] not in state['slots'] or row['other_slot'] not in state['slots']
                or steps[at]['kind']!='turn' or steps[later]['kind']!='turn'
                or steps[at]['slot']!=row['slot'] or steps[later]['slot']!=row['other_slot']
                or any(s['kind']=='turn' and s['slot'] in (row['slot'],row['other_slot']) for s in steps[:at])):
            raise ValueError('mounted initiative must exchange exactly two unused turn steps')
        import control_mount as MOUNT
        rider,mount=row['rider'],row['mount']
        if (index.get(rider.entity_id) is not rider or index.get(mount.entity_id) is not mount
                or rider.kind!='trainer' or mount.kind!='pokemon' or row['source']!=MOUNT.RIDE_AS_ONE
                or {bound_at(at)[row['slot']],bound_at(at)[row['other_slot']]}!={rider,mount}
                or type(row['mount_contract_sha256']) is not str or len(row['mount_contract_sha256'])!=64):
            raise ValueError('actual source-specific rider and mounted Pokemon required')
        receipts=[r for r in MOUNT._acquisitions(rider,MOUNT.RIDE_AS_ONE) if r['request_id']==row['acquisition_request_id']]
        if len(receipts)!=1:raise ValueError('historical Ride as One acquisition required')
        steps[at]['slot'],steps[later]['slot']=row['other_slot'],row['slot']
    return steps


def turn_started(engine, actor):
    import initiative_interrupts as INTERRUPTS
    if INTERRUPTS.is_borrow_start(engine,actor):
        return
    state = getattr(engine,KEY,None)
    if state is None:
        return
    preflight_turn(engine,actor)
    key = _actor_slot(state,actor)
    state['open_slot'] = key; state['slots'][key]['turn'] = 'open'


def turn_closed(engine, actor):
    state = getattr(engine,KEY,None)
    if state is None:
        return
    key = _actor_slot(state,actor); step = _current(state)
    if state['open_slot'] != key or state['slots'][key]['turn'] != 'open':
        raise ValueError('actor does not own the open schedule turn')
    state['records'].append(dict(step,actor=actor,outcome='closed',
                                closure_sequence=len(engine._turn_closures)+1))
    state['slots'][key]['turn'] = 'closed'; state['open_slot'] = None
    state['cursor'] += 1
    import initiative_interrupts as INTERRUPTS
    INTERRUPTS.ordinary_closed(engine,key,actor)


def replace(engine, slot, actor, *, source, reason):
    """Replace a binding, keeping the original slot's consumed turn right."""
    WORLD.require_actors(engine,actor)
    DERIVE.selected(engine.r,source); _text(reason,'replacement reason')
    import initiative_interrupts as INTERRUPTS
    INTERRUPTS.require_clear(engine)
    def apply(staged,subject):
        state = getattr(staged,KEY,None)
        if not state or state['status'] not in ('prepared','active') or slot not in state['slots']:
            raise ValueError('actual prepared/active schedule slot required')
        row = state['slots'][slot]
        if state['open_slot'] == slot:
            raise ValueError('cannot replace an open owner turn')
        if any(other['actor'] is subject for key,other in state['slots'].items() if key != slot):
            raise ValueError('replacement actor already owns another schedule slot')
        if row['actor'] is subject:
            raise ValueError('replacement must change the actual participant')
        INTERRUPTS.preflight_replacement(staged,slot,subject)
        state['replacements'].append({'slot':slot,'before':row['actor'],'after':subject,
                                      'source':source,'reason':reason,'cursor':state['cursor']})
        row['actor'] = subject
        return status(staged)
    return GRANTS.transition(engine,actor,apply)


def preflight_end_round(engine):
    import initiative_interrupts as INTERRUPTS
    INTERRUPTS.require_clear(engine)
    state = getattr(engine,KEY,None)
    if state is None:
        return
    if state['status'] != 'active' or state['open_slot'] is not None or _current(state) is not None:
        raise ValueError('initiative schedule still has outstanding declarations or turns')


def round_ended(engine):
    state = getattr(engine,KEY,None)
    if state is not None:
        state['status'] = 'completed'


def end_encounter(engine):
    # The native encounter boundary ends its turn-right domain, without an
    # invented final turn or clock event. Native closure/loan receipts remain.
    import initiative_interrupts as INTERRUPTS
    INTERRUPTS.end_encounter(engine)
    setattr(engine,KEY,None)


def _validate_world(engine,index):
    state = getattr(engine,KEY,None)
    if state is None:
        return True
    if state.get('version') != 1 or state.get('status') not in ('prepared','active','completed'):
        raise ValueError('known initiative schedule version/status required')
    DERIVE.selected(engine.r,state['source'])
    import party_actions as PARTY
    PARTY.validate_format(engine,state)
    C.integer(state['round'],'schedule round',1)
    expected_round = engine.round_no+1 if state['status']=='prepared' else engine.round_no
    if state['round'] != expected_round:
        raise ValueError('initiative schedule round differs from its native boundary')
    if not state['slots'] or set(state['initial_bindings']) != set(state['slots']):
        raise ValueError('original actual slot bindings required')
    bindings = dict(state['initial_bindings'])
    for key,row in bindings.items():
        if index.get(row['actor'].entity_id) is not row['actor'] or row['role'] != state['slots'][key]['role']:
            raise ValueError('original slot actor/role does not resolve')
    cursor = C.integer(state['cursor'],'schedule cursor',0,len(state['steps']))
    changes = state['replacements']
    previous = -1
    for change in changes:
        DERIVE.selected(engine.r,change['source']); _text(change['reason'],'replacement reason')
        at = C.integer(change['cursor'],'replacement cursor',0,cursor)
        if at < previous or change['slot'] not in bindings:
            raise ValueError('replacement history must follow actual schedule progress')
        previous = at
        if any(index.get(change[k].entity_id) is not change[k] for k in ('before','after')):
            raise ValueError('replacement history requires actual participants')
    def bound_at(at):
        current = {key:row['actor'] for key,row in bindings.items()}
        for change in changes:
            if change['cursor'] > at: break
            key = change['slot']
            if current[key] is not change['before'] or change['after'] is change['before']:
                raise ValueError('replacement changed its actual prior binding')
            if any(actor is change['after'] for k,actor in current.items() if k!=key):
                raise ValueError('replacement actor already holds another turn right')
            current[key] = change['after']
        return current
    current = bound_at(cursor)
    ids = set()
    for key,row in state['slots'].items():
        _text(key,'schedule slot'); _text(row['role'],'slot role')
        actor = row['actor']
        if index.get(actor.entity_id) is not actor or actor.entity_id in ids:
            raise ValueError('schedule binding must resolve to its unique actual participant')
        ids.add(actor.entity_id)
        if current[key] is not actor:
            raise ValueError('current participant differs from actual replacement history')
        if row['turn'] not in ('ready','open','closed'):
            raise ValueError('known schedule turn disposition required')
    order = state['order']
    if len(order) != len(set(order)) or set(order) != set(state['slots']):
        raise ValueError('exact schedule participant order required')
    if state['steps'] != _exchanged_steps(engine,state,bound_at,index):
        raise ValueError('schedule steps differ from the declared phase layout')
    if len(state['records']) != cursor:
        raise ValueError('schedule cursor needs exactly its completed step receipts')
    closed = set(); declared = set()
    for n,(step,record) in enumerate(zip(state['steps'],state['records'])):
        if {k:record[k] for k in ('phase','slot','kind')} != step:
            raise ValueError('completed schedule receipt differs from its actual phase')
        actor = record['actor']
        if index.get(actor.entity_id) is not actor:
            raise ValueError('completed schedule actor identity does not resolve')
        if actor is not bound_at(n)[step['slot']]:
            raise ValueError('completed step does not belong to its actual bound participant')
        if record['outcome']=='skipped':
            observed=record.get('unavailable')
            if (type(observed) is not dict or set(observed)!={'fainted','captured','on_field'}
                    or any(type(value) is not bool for value in observed.values())
                    or not (observed['fainted'] or observed['captured'] or not observed['on_field'])
                    or set(record)!={'phase','slot','kind','actor','outcome','unavailable'}):
                raise ValueError('skipped step requires actual unavailable participant observations')
            if step['kind']=='turn':
                import initiative_interrupts as INTERRUPTS
                if INTERRUPTS._due(engine,step['slot']) is not None:
                    raise ValueError('skipped turn cannot consume an owed borrowed slot')
                closed.add(step['slot'])
            continue
        if record['outcome']=='switch_locked':
            if (step['kind']!='turn' or record['switch_lock']['scope'][1]!=state['round']
                    or set(record)!={'phase','slot','kind','actor','outcome','switch_lock'}):
                raise ValueError('switch-locked slot needs its exact sourced turn disposition')
            PARTY.validate_switch_lock(engine,actor,record['switch_lock'])
            closed.add(step['slot'])
            continue
        if step['kind']=='declaration':
            if record['outcome'] != 'declared' or state['declarations'].get(step['slot']) != record['intent']:
                raise ValueError('declaration differs from its completed receipt')
            declared.add(step['slot'])
        else:
            closed.add(step['slot'])
            if record['outcome'] in ('borrow_settled','switch_interrupt_settled'):
                import initiative_interrupts as INTERRUPTS
                INTERRUPTS.validate_settlement(engine,state,record)
                continue
            if record['outcome']!='closed':
                raise ValueError('completed turn requires an actual close or loan settlement')
            sequence = record['closure_sequence']
            if type(sequence) is not int or not 1 <= sequence <= len(engine._turn_closures):
                raise ValueError('schedule turn requires its actual native closure')
            closure = engine._turn_closures[sequence-1]
            if closure['actor'] is not actor or closure['round'] != state['round']:
                raise ValueError('schedule closure belongs to another actual actor or round')
    if set(state['declarations']) != declared:
        raise ValueError('declaration state lacks exactly its actual receipts')
    open_slot = state['open_slot']
    if open_slot is not None:
        step = _current(state)
        import initiative_interrupts as INTERRUPTS
        owner = INTERRUPTS.suspended_owner(engine) or engine._active_turn_actor
        if step is None or step['kind'] != 'turn' or step['slot'] != open_slot or state['slots'][open_slot]['actor'] is not owner:
            raise ValueError('schedule open slot differs from actual Engine turn ownership')
    for key,row in state['slots'].items():
        expected = 'closed' if key in closed else 'open' if key==open_slot else 'ready'
        if row['turn'] != expected:
            raise ValueError('slot turn right differs from actual completed/open steps')
    if state['status']=='completed' and cursor != len(state['steps']):
        raise ValueError('completed schedule still has outstanding turn rights')
    if state['status']=='active' and (not engine.encounter_active or engine.round_start_seconds is None):
        raise ValueError('active schedule lacks its actual native round')
    if state['status'] in ('prepared','completed') and (engine.round_start_seconds is not None or engine._active_turn_actor is not None):
        raise ValueError('closed schedule boundary differs from actual native turn/round')
    if state['status']=='active' and open_slot is None and engine._active_turn_actor is not None:
        import initiative_interrupts as INTERRUPTS
        if not INTERRUPTS.between_frame(engine):
            raise ValueError('active owner has no actual schedule turn right')
    return True


def validate_world(engine,index):
    try:
        return _validate_world(engine,index)
    except (KeyError,TypeError,AttributeError,IndexError) as exc:
        raise ValueError('malformed actual initiative schedule state') from exc
