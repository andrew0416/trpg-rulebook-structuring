"""GM-observed places, contact and target relations without invented coordinates.

Actors retain their existing abstract locations. A spatial frame binds a GM
ruling to those actual locations; movement invalidates old target rulings.
Action permission, movement capability, Sprint and attack execution stay native.
"""
from copy import deepcopy
import common_checks as C
import world_entities as W
import state_grants as G
import resolution_transaction as TX
import movement_actions as MOVEMENT
import turn as TURN

FIELD = '_mapless_space'


def active(e):
    return getattr(e, FIELD, None) is not None


def _sign(row):
    return dict(row, sha256=TX.request_fingerprint(row))


def _verify(row):
    if type(row) is not dict or row.get('sha256') != TX.request_fingerprint({k:v for k,v in row.items() if k != 'sha256'}):
        raise ValueError('mapless spatial observation changed')


def _positions(e, ids):
    index = W.actor_index(e)
    if not set(ids) <= set(index):
        raise ValueError('mapless participants must retain actual actor identities')
    import marsupial_state as MARSUPIAL
    ids=set(ids)
    for uid in tuple(ids):
        ids.update(baby.entity_id for baby in MARSUPIAL.children(e,index[uid]))
    return {uid: W.location_of(index[uid]) for uid in sorted(ids)}


def _contacts(value, ids):
    if type(value) is not list:
        raise ValueError('explicit complete contact pairs required')
    result = []
    for pair in value:
        if type(pair) is not list or len(pair) != 2 or len(set(pair)) != 2 or not set(pair) <= set(ids):
            raise ValueError('contact needs two different observed actual actors')
        result.append(sorted(pair))
    if len({tuple(x) for x in result}) != len(result):
        raise ValueError('contact pair cannot be repeated')
    return sorted(result)


def _frame(e, state):
    frame = state['frame']
    _verify(frame)
    if e.grid is not None or _positions(e, frame['positions']) != frame['positions']:
        raise ValueError('mapless spatial frame is stale; observe the changed locations')
    return frame


def configure(e, *, scene_id, places, placements, contacts, reason, environment_regions=None):
    """Observe a complete contact frame; place labels may be zones or landmarks."""
    ensure_clear(e)
    for value in (scene_id, reason):G._text(value, 'mapless scene observation')
    if e.grid is not None or type(places) is not dict or not places or type(placements) is not dict or not placements:
        raise ValueError('mapless scene requires described places and actual placements')
    for uid, description in places.items():
        G._text(uid, 'mapless place identity');G._text(description, 'mapless place description')
    index = W.actor_index(e)
    if not set(placements) <= set(index) or any(place not in places for place in placements.values()):
        raise ValueError('placements must resolve actual actors and described places')
    pairs = _contacts(contacts, _positions(e,placements))
    def apply(staged, _):
        state = getattr(staged, FIELD, None)
        if state is not None and (state['scene_id'] != scene_id or state['places'] != places):
            raise ValueError('end the old mapless scene before replacing its place identities')
        state = state or dict(scene_id=scene_id, places=deepcopy(places), observations={}, movements={})
        if environment_regions is not None:
            _environment_regions(staged,places,environment_regions)
            previous=state.get('environment')
            if previous is not None and previous['places']!=environment_regions:
                raise ValueError('end the old mapless scene before replacing its environment bindings')
            state['environment']=previous or _sign(dict(places=deepcopy(environment_regions),reason=reason))
        actual = W.actor_index(staged)
        for uid, place in placements.items():
            W.observe_location(staged, actual[uid], dict(kind='abstract',place_id=place),
                               reason=reason, source='gm/mapless-space')
        state['frame'] = _sign(dict(revision=state.get('frame',{}).get('revision',0)+1,
            positions=_positions(staged, placements),contacts=pairs,reason=reason))
        setattr(staged,FIELD,state)
        return deepcopy(state['frame'])
    return G.transition(e,None,apply)


def _environment_regions(e,places,regions):
    import environment_derive as ED
    if type(regions) is not dict or not regions or not set(regions)<=set(places):
        raise ValueError('explicit mapless places and observed environment regions required')
    for region in regions.values():
        if type(region) is not str or region not in ED._state(e)['regions']:
            raise ValueError('mapless environment binding needs an actual observed region')
        ED._verify(ED._state(e)['regions'][region])


def _environment_target(e,actor,declaration):
    import environment_derive as ED
    state,frame=_context(e,actor);binding=state.get('environment')
    if binding is not None:
        _verify(binding);_environment_regions(e,state['places'],binding['places'])
    if not ED.bound(e,actor):
        if binding is not None:raise ValueError('mapless environment travel needs the actual actor baseline')
        return None
    origin=frame['positions'][actor.entity_id]['place_id'];destination=declaration['destination']
    if binding is None or not {origin,destination}<=set(binding['places']):
        raise ValueError('observe both actual mapless environment places before travel')
    if ED.context(e,actor)['region_id']!=binding['places'][origin]:
        raise ValueError('actual environment differs from the observed mapless origin')
    region=binding['places'][destination]
    import environment_change as EC
    actual=EC.effective(e,ED._state(e)['regions'][region])
    if actual['air_available'] is None or actual['medium'] is None:
        raise ValueError('destination requires known atmospheric facts before travel')
    return region


def _transport(e,actor):
    """Actual native mount relation and pool, separate from the GM spatial ruling."""
    import control_mount as MOUNT
    if not MOUNT.manages(e,actor):return None
    donor,policy,pool=MOUNT.shared_movement(e,actor)
    group=sorted(c.entity_id for c in MOUNT.travel_group(e,actor))
    state,frame=_context(e,actor)
    if not set(group)<=set(frame['positions']) or any(frame['positions'][uid]!=W.location_of(actor) for uid in group):
        raise ValueError('observe the actual carried group together at its mapless origin')
    return dict(mover_id=donor.entity_id,group=group,policy=deepcopy(policy),
        period=pool['period'],used=pool['used'])


def _context(e, actor):
    W.require_actors(e,actor)
    if not active(e):raise ValueError('observe a mapless scene first')
    state = getattr(e,FIELD);frame = _frame(e,state)
    if actor.entity_id not in frame['positions']:
        raise ValueError('actor is outside the observed mapless frame')
    return state, frame


def adjacent(e, left, right):
    _, frame = _context(e,left);W.require_actors(e,right)
    if right.entity_id not in frame['positions']:
        raise ValueError('contact to an unobserved actor is unknown')
    return sorted([left.entity_id,right.entity_id]) in frame['contacts']


def _range(e, actor, move):
    import weapon_actions as WEAPONS
    import pokemon_move_edges as EDGES
    move = EDGES.prepare(e,actor,WEAPONS.prepare(e,actor,move))
    return WEAPONS.range_spec(e,move,actor)


def _observe(e, actor, event_id, kind, payload, reason):
    G._text(event_id,'mapless event identity');G._text(reason,'mapless ruling reason')
    def apply(staged, actual):
        state,frame = _context(staged,actual)
        declaration = dict(kind=kind,actor_id=actual.entity_id,reason=reason,**payload)
        if event_id in state['observations']:
            old=state['observations'][event_id];_verify(old)
            if old['declaration'] != declaration:raise ValueError('mapless event identity cannot change its ruling')
            return deepcopy(old)
        row=_sign(dict(event_id=event_id,declaration=declaration,frame=deepcopy(frame)))
        state['observations'][event_id]=row
        return deepcopy(row)
    return G.transition(e,actor,apply)


def observe_targets(e, actor, *, event_id, move_id, landmark_id, target_ids, reason):
    state,frame=_context(e,actor)
    if landmark_id not in state['places'] or type(target_ids) is not list or len(set(target_ids)) != len(target_ids) or not set(target_ids) <= set(frame['positions']):
        raise ValueError('area ruling needs a described landmark and distinct observed targets')
    rng=_range(e,actor,e.r.move(move_id))
    return _observe(e,actor,event_id,'targets',dict(move_id=move_id,range=rng,
        landmark_id=landmark_id,target_ids=deepcopy(target_ids)),reason)


def observe_movement(e, actor, *, event_id, destination, movement_cost, contacts_after, reason, timing_policy=None):
    state,frame=_context(e,actor)
    if destination not in state['places']:raise ValueError('actual described destination required')
    C.integer(movement_cost,'GM observed movement cost',1)
    pairs=_contacts(contacts_after,frame['positions'])
    transport=_transport(e,actor)
    group={actor.entity_id} if transport is None else set(transport['group'])
    import marsupial_state as MARSUPIAL
    index=W.actor_index(e)
    for uid in tuple(group):group.update(baby.entity_id for baby in MARSUPIAL.children(e,index[uid]))
    unaffected=lambda rows:[pair for pair in rows if not group.intersection(pair)]
    if unaffected(pairs) != unaffected(frame['contacts']):
        raise ValueError('one actor movement cannot rewrite other actors contact')
    import environmental_effects as ENV
    if timing_policy not in (None,*ENV.TIMINGS):raise ValueError('explicit native suffocation timing required')
    payload=dict(destination=destination,movement_cost=movement_cost,contacts_after=pairs)
    if transport is not None:payload['transport']=transport
    if timing_policy is not None:payload['timing_policy']=timing_policy
    return _observe(e,actor,event_id,'movement',payload,reason)


def _current(e, actor, kind, event_id=None, move=None):
    state,frame=_context(e,actor)
    rows=[row for key,row in state['observations'].items()
          if (event_id is None or key==event_id) and row['declaration']['kind']==kind
          and row['declaration']['actor_id']==actor.entity_id
          and (move is None or row['declaration']['move_id']==move['id'])]
    if not rows:raise ValueError('actual GM mapless '+kind+' ruling required')
    row=rows[-1];_verify(row)
    if row['frame'] != frame:raise ValueError('mapless ruling is stale after spatial change')
    if move is not None and row['declaration']['range'] != _range(e,actor,move):
        raise ValueError('effective attack range changed after GM ruling')
    return row


def targets(e, actor, move, candidates, primary):
    """Native range selector consumes the current explicit GM target relation."""
    _,frame=_context(e,actor)
    import weapon_actions as WEAPONS
    import body_modes as MODES
    import setup_move_state as SETUP
    import marsupial_state as MARSUPIAL
    rng=_range(e,actor,move)
    if WEAPONS.is_field(rng) or WEAPONS.is_self_only(rng):return [actor]
    candidates=list(candidates)
    W.require_actors(e,*candidates)
    live=[c for c in {c.entity_id:c for c in candidates}.values() if c is not actor and not c.fainted and not c.captured and MARSUPIAL.target_present(c,engine=e)
          and MODES.target_visible(e,actor,c) and SETUP.targetable(c,engine=e,attacker=actor,move=move)]
    if any(c.entity_id not in frame['positions'] for c in live):
        raise ValueError('observe all actual candidate positions before mapless targeting')
    # Contact establishes ordinary melee only. Reach extensions and areas need
    # their own observed range relation; sharing a place does not imply contact.
    import body_state as BODY
    if rng.get('origin')=='melee' and not rng.get('shape') and BODY.melee_reach(actor)==1:
        return [primary] if primary in live and adjacent(e,actor,primary) else []
    row=_current(e,actor,'targets',move=move)
    selected=set(row['declaration']['target_ids'])
    if not rng.get('shape'):
        return [primary] if primary in live and primary.entity_id in selected else []
    return [c for c in live if c.entity_id in selected]


def require_target(e, actor, target, move):
    if target not in targets(e,actor,move,[target],target):
        raise ValueError('target is outside the current GM mapless relation')


def move(e, actor, *, event_id):
    """Pay a quoted land Shift; resolve actual departures before committing place."""
    W.require_actors(e,actor);G._text(event_id,'mapless movement event')
    state=getattr(e,FIELD,None)
    old=None if state is None else state['movements'].get(event_id)
    if old is not None:
        _verify(old)
        if old['actor_id']!=actor.entity_id:raise ValueError('mapless movement belongs to another actor')
        if old.get('phase','complete')!='pending':return deepcopy(old)
        _validate_paid(e,actor,old)
        return G.transition(e,actor,lambda staged,actual:_continue_move(staged,actual,event_id))
    row=_current(e,actor,'movement',event_id=event_id)
    declaration=row['declaration']
    transport=_transport(e,actor)
    if transport!=declaration.get('transport'):raise ValueError('actual mapless transport changed after the GM observation')
    MOVEMENT.boundary(e,'mapless movement')
    ensure_clear(e,actor)
    import control_mount as MOUNT
    donor=actor if transport is None else W.actor_index(e)[transport['mover_id']]
    group=[actor] if transport is None else [W.actor_index(e)[uid] for uid in transport['group']]
    for member in group:_environment_target(e,member,declaration)
    if any(getattr(member,'airborne',False) or member.spec.get('_burrow',{}).get('underground') for member in group):
        raise ValueError('mapless carried/non-land movement needs its physical group adapter')
    allowance=MOVEMENT.distance_budget(e,donor,'land') if transport is None else MOUNT.shared_movement(e,actor)[2]['remaining']
    if declaration['movement_cost'] > allowance:
        raise ValueError('GM movement cost exceeds current native movement allowance')
    def apply(staged,actual):
        current=_current(staged,actual,'movement',event_id=event_id)
        current_transport=current['declaration'].get('transport')
        mover=actual if current_transport is None else W.actor_index(staged)[current_transport['mover_id']]
        if not TURN.can_act(staged,mover) or not TURN.movement_permission(staged,mover):return False
        owner=mover if current_transport is not None and current_transport['policy']['movement']['action_owner']=='mount' else actual
        if not TURN.spend(staged,owner,'shift','추상 지역 이동',movement=True):return False
        if current_transport is not None:
            _,policy,pool=MOUNT.shared_movement(staged,actual)
            MOUNT.record_movement(staged,mover,policy,distance=0,diagonals=pool['diagonals'])
        MOVEMENT.consume_sprint(mover)
        after=current['declaration']['contacts_after']
        leaving=[c.entity_id for c in TURN.adjacent_enemies(staged,mover)
                 if sorted([mover.entity_id,c.entity_id]) not in after]
        paid=dict(event_id=event_id,actor_id=actual.entity_id,
            origin=current['frame']['positions'][actual.entity_id],destination=W.location_of(actual),
            movement_cost=declaration['movement_cost'],at=staged.elapsed_seconds,
            phase='pending',clock=_clock(staged,actual),observation=current['sha256'],
            departure_ids=leaving,next_departure=0,progress=dict(phase='ready',effects=[]))
        if current_transport is not None:paid['transport']=deepcopy(current_transport)
        getattr(staged,FIELD)['movements'][event_id]=_sign(paid)
        return _continue_move(staged,actual,event_id)
    return G.transition(e,actor,apply)


def _clock(e,actor):return [e.encounter_active,e.round_no,actor.turns_taken]


def ensure_clear(e,actor=None):
    if not active(e):return
    if any(row.get('phase')=='pending' and (actor is None or actor.entity_id in row.get('transport',{}).get('group',[row['actor_id']]))
           for row in getattr(e,FIELD)['movements'].values()):
        raise ValueError('finish the already paid mapless Shift before another action or spatial reset')


def _validate_paid(e,actor,row):
    _verify(row)
    current=_current(e,actor,'movement',event_id=row['event_id'])
    if (row['observation']!=current['sha256'] or row['clock']!=_clock(e,actor)
            or row['origin']!=W.location_of(actor)):
        raise ValueError('paid mapless departure lost its actual origin, clock or observation')
    C.integer(row['next_departure'],'actual mapless departure prefix',0,len(row['departure_ids']))
    index=W.actor_index(e)
    if len(set(row['departure_ids']))!=len(row['departure_ids']) or not set(row['departure_ids'])<=set(index):
        raise ValueError('paid mapless departure lost actual opponents')
    contacts=current['frame']['contacts'];after=current['declaration']['contacts_after']
    if row.get('transport')!=current['declaration'].get('transport'):raise ValueError('paid mapless transport differs from its observed group')
    mover_id=row.get('transport',{}).get('mover_id',actor.entity_id)
    if any(sorted([mover_id,uid]) not in contacts or sorted([mover_id,uid]) in after
           for uid in row['departure_ids']):
        raise ValueError('paid mapless opponent was not part of the actual contact departure')


def _continue_move(e,actor,event_id):
    state=getattr(e,FIELD);paid=state['movements'][event_id]
    _validate_paid(e,actor,paid)
    progress=paid['progress']
    MOVEMENT._paid_receipts(e,progress)
    def finish(phase):
        # Native transitions may refresh containers while retaining actor IDs.
        row=getattr(e,FIELD)['movements'][event_id]
        row['phase']=phase;row['sha256']=TX.request_fingerprint({k:v for k,v in row.items() if k!='sha256'})
        return deepcopy(row)
    import control_mount as MOUNT
    def permitted():
        if paid.get('transport')!=_transport(e,actor):return False
        return all(TURN.can_act(e,c) and TURN.movement_permission(e,c) for c in (actor,mover))
    mover=actor if 'transport' not in paid else W.actor_index(e)[paid['transport']['mover_id']]
    if not permitted():return finish('stopped')
    while paid['next_departure']<len(paid['departure_ids']):
        enemy=W.actor_index(e)[paid['departure_ids'][paid['next_departure']]]
        paid['next_departure']+=1
        def resolve():
            TURN.trigger_aoo(e,mover,'관측된 접촉 밖으로 이동',[enemy])
            return permitted()
        allowed=MOVEMENT.observe_paid_departure(e,mover,progress,resolve)
        paid=getattr(e,FIELD)['movements'][event_id];progress=paid['progress']
        if progress['phase']=='reaction_pending':return finish('pending')
        if not allowed:return finish('stopped')
        _context(e,actor)
    if not permitted():return finish('stopped')
    current=_current(e,actor,'movement',event_id=event_id);declaration=current['declaration']
    members=[actor] if 'transport' not in paid else [W.actor_index(e)[uid] for uid in paid['transport']['group']]
    regions=[_environment_target(e,member,declaration) for member in members]
    for member,region in zip(members,regions):
        if region is not None:
            import environment_change as EC
            EC.transfer(e,member,region,reason=declaration['reason'],timing_policy=declaration.get('timing_policy'))
    for member in members:
        W.observe_location(e,member,dict(kind='abstract',place_id=declaration['destination']),
                           reason=declaration['reason'],source='ch07/abstracted-combat-distances')
    if 'transport' in paid:
        MOUNT.record_movement(e,mover,paid['transport']['policy'],distance=paid['movement_cost'],diagonals=getattr(mover,MOUNT.POOL)['diagonals'])
    state=getattr(e,FIELD)
    state['frame']=_sign(dict(revision=current['frame']['revision']+1,
        positions=_positions(e,current['frame']['positions']),
        contacts=deepcopy(declaration['contacts_after']),reason=declaration['reason']))
    state['movements'][event_id]['destination']=W.location_of(actor)
    import sound_state as SOUND
    SOUND.observe(e,actor,'movement')
    return finish('complete')


def end_scene(e):
    ensure_clear(e)
    if active(e):delattr(e,FIELD)


def validate_world(e,index=None):
    if not active(e):return
    state=getattr(e,FIELD);index=W.actor_index(e) if index is None else index
    required={'scene_id','places','frame','observations','movements'}
    if type(state) is not dict or not required<=set(state) or set(state)-required-{'environment'}:
        raise ValueError('mapless scene structure is malformed')
    if 'environment' in state:
        _verify(state['environment']);_environment_regions(e,state['places'],state['environment']['places'])
    G._text(state['scene_id'],'mapless scene identity')
    frame=state['frame'];_verify(frame)
    C.integer(frame['revision'],'mapless frame revision',1)
    if not set(frame['positions']) <= set(index):raise ValueError('mapless frame lost an actual actor')
    _contacts(frame['contacts'],frame['positions'])
    for location in frame['positions'].values():
        if location.get('kind')!='abstract' or location.get('place_id') not in state['places']:
            raise ValueError('mapless frame requires actual described places')
    for event_id,row in state['observations'].items():
        _verify(row);_verify(row['frame'])
        d=row['declaration']
        if row['event_id']!=event_id or d['actor_id'] not in index or d['kind'] not in ('targets','movement'):
            raise ValueError('mapless observation lost its actual identity')
    for event_id,row in state['movements'].items():
        _verify(row)
        original=state['observations'].get(event_id)
        if not original or original['declaration']['kind']!='movement' or row['event_id']!=event_id or row['actor_id']!=original['declaration']['actor_id']:
            raise ValueError('paid mapless movement lost its observation')
        if 'phase' in row:
            if row['phase'] not in ('pending','complete','stopped'):raise ValueError('unknown paid mapless movement phase')
            if row['observation']!=original['sha256']:raise ValueError('paid mapless movement observation changed')
            if row['phase']=='pending':_validate_paid(e,index[row['actor_id']],row)
