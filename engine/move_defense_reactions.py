"""Optional defenses at an authenticated native accuracy boundary.

The existing completion owns declared targets and received hits. The existing
passive continuation owns waits; initiative/action and movement modules own the
actual reaction. An armed watch contains choices, never an asserted hit.
"""
from contextlib import contextmanager
from copy import copy, deepcopy
from pathlib import Path
import hashlib
import json

import common_checks as CHECKS
import root_resolution as ROOT
import state_grants as GRANTS
import world_entities as WORLD

POLICY = 'data/move-defense-policy.json'
WATCH = 'move_defense_watch'
MELEE = 'maneuver/근접-가로채기'
RANGED = 'maneuver/원거리-가로채기'
DODGE = 'ability/회피'
DETECT = 'move/판별'
SOURCES = (MELEE, RANGED, DODGE)
PERCEPTION = 'ability/감지'
PERCEPTION_PLAYTEST = 'ability/감지-playtest'
PERCEPTIONS = (PERCEPTION, PERCEPTION_PLAYTEST)


def install(rules):
    value = json.loads((Path(rules.root) / POLICY).read_text(encoding='utf-8'))
    if value.get('version') != 1 or set(value.get('sources', {})) != set(SOURCES):
        raise ValueError('reviewed native defense source policy required')
    for name, digest in value['source_files'].items():
        if hashlib.sha256((Path(rules.root) / name).read_bytes()).hexdigest() != digest:
            raise ValueError('native defense source changed: ' + name)
    rules.move_defense_policy = value


def _reason(reason):
    if type(reason) is not str or not reason.strip():
        raise ValueError('explicit defense decision reason required')


def _selected(e, source):
    import initiative_derivation as DERIVE
    import unown_imbuement as UNOWN
    if source in PERCEPTIONS:
        __import__('chronicler').perception_definition(e.r,source)
        return
    if source==DETECT:
        import priority_actions as PRIORITY
        move=PRIORITY._move(e.r,DETECT)
        if move['range']!='자신, 발동조건, 방해, 방패' or move['_source']['record_span']!=[188,188]:
            raise ValueError('actual selected printed Detect Interrupt required')
        UNOWN._native(e.r,DETECT)
        return
    if source == UNOWN.SOURCE:
        UNOWN.policy(e.r)
        return
    if source not in SOURCES:
        raise ValueError('exact reviewed defense source required')
    DERIVE.selected(e.r, source)


def _active(e, actor):
    import turn as TURN
    WORLD.require_actors(e, actor)
    if actor.dead or actor.captured or not actor.on_field or not TURN.can_act(e, actor):
        raise ValueError('actual available defense owner required')


def watch(e, target, requests, *, reason):
    import passive_events as PASSIVE
    PASSIVE.ensure_clear(e)
    _reason(reason); WORLD.require_actors(e, target)
    if target.dead or target.captured or not target.on_field:
        raise ValueError('actual present living protected target required')
    if type(requests) is not list or not requests:
        raise ValueError('ordered actual defense requests required')
    index = WORLD.actor_index(e); normalized = []; seen = set()
    for request in requests:
        if type(request) is not dict or set(request) != {'actor_id', 'source'}:
            raise ValueError('watch accepts actor identity and source only')
        actor = index.get(request['actor_id']); _active(e, actor)
        source = request['source']; _selected(e, source)
        if actor.entity_id in seen:
            raise ValueError('one ordered defense offer per actual reactor required')
        import unown_imbuement as UNOWN
        if source==DETECT:
            if actor is not target:raise ValueError('Detect protects only its actual source target')
            _detect_ready(e,actor)
        elif source == UNOWN.SOURCE:
            if actor is not target:
                raise ValueError('Unown Detect protects its actual implanted owner')
            UNOWN.preflight_detect(e,actor)
        elif source == DODGE or source in PERCEPTIONS:
            import ability_transitions as ABILITIES
            title=e.r.selection.units[source]['title'] if source in PERCEPTIONS else source
            if actor is not target or not ABILITIES.active(actor, title):
                raise ValueError('defense offer requires the target actual owned ability')
        elif actor is target or actor.side != target.side or not actor.side:
            raise ValueError('Intercept offer requires another actual ally')
        seen.add(actor.entity_id); normalized.append(dict(request))
    target.spec[WATCH] = {'requests': normalized, 'reason': reason}
    return deepcopy(target.spec[WATCH])


def interested(e, actor=None, target=None):
    return any(c.spec.get(WATCH) for c in WORLD.actor_index(e).values())


def has_watch(target):
    return bool(target.spec.get(WATCH))


def watch_interested(target, move):
    if not has_watch(target):
        return False
    if move['class'] in ('물리','특수'):
        return True
    import unown_imbuement as UNOWN
    return (move['class'] == '변화' and
             any(r.get('source') in (UNOWN.SOURCE,DETECT,PERCEPTION) for r in target.spec[WATCH]['requests']))


def _detect_ready(e,actor):
    import priority_actions as PRIORITY, frequency as FREQUENCY
    _selected(e,DETECT);PRIORITY._owned_move(e,actor,DETECT)
    allowed,reason=FREQUENCY.move_allowed(e,actor,DETECT,outside_combat=not e.encounter_active)
    if not allowed:raise ValueError('actual Detect frequency unavailable: '+reason)


def authorize_move_interrupt(e,event_id,actor,move_id):
    """Authenticated by the existing actual defense delivery, never a hit flag."""
    authorize_trigger(e,event_id)
    event=e._passive_events[event_id];state=_defense(e,event)
    import style_expert as STYLE
    if STYLE.blocks_interrupt_move(e,event):raise ValueError('Rule of Cool prevents reacting Interrupt Moves')
    requests=state['facts']['watch']['requests'];cursor=state['cursor']
    if (move_id!=DETECT or event['target'] is not actor or event['actor'] is actor
            or not e.encounter_active or event['round']!=e.round_no or state['facts']['hit'] is not True
            or state['phase']!='choices' or cursor>=len(requests)
            or requests[cursor]!={'actor_id':actor.entity_id,'source':DETECT}
            or state['decisions'].get(str(cursor),{}).get('use') is not True):
        raise ValueError('selected Detect needs its actual other-combatant successful hit and owned decision')
    _detect_ready(e,actor)
    if _prohibited(e,state['facts']['move'],'shield'):raise ValueError('actual incoming Move prohibits Detect Shield')


def validate_move_interrupt_request(e,window,request):
    _selected(e,request['source'])
    event=e._passive_events.get(window['trigger'].get('event_id'))
    state=None if event is None else _defense(e,event)
    if (request['source']!=DETECT or request['move_id']!=DETECT or window['trigger']['kind']!='accuracy'
            or event is None or event['target'] is not request['actor'] or event['actor'] is request['actor']
            or state is None or state['facts']['hit'] is not True
            or not any(r=={'actor_id':request['actor'].entity_id,'source':DETECT}
                for r in state['facts']['watch']['requests'])
            or _prohibited(e,state['facts']['move'],'shield')
            or request['clock']!='none' or request['budget']!={'standard':1}
            or (request['mode']=='reaction' and request['payment']!='next')
            or request['mode'] not in ('reaction','switch_interrupt')):
        raise ValueError('Interrupt request lost its actual selected Detect accuracy source')


def _row(e, event):
    completion = getattr(e, '_move_completions', {}).get(event.get('completion_id'))
    if (completion is None or completion['actor'] is not event['actor'] or
            event['target'] not in completion['targets'] or
            event['target'].entity_id not in completion['started'] or
            completion['move_id'] != event['move_id']):
        raise ValueError('defense requires its actual started Move completion')
    return completion


def bind_event(e, event, move, completion_id):
    if not watch_interested(event['target'],move):
        return
    event['completion_id'] = completion_id
    _row(e, event)
    watch=deepcopy(event['target'].spec[WATCH])
    if any(r['source'] in PERCEPTIONS for r in watch['requests']):
        import body_state as BODY
        actor,target=event['actor'],event['target']
        cells=(set(_area_cells(e,event,move)) if actor is not target and target.side and actor.side==target.side else set())
        ally_area=bool(cells) and bool(cells.intersection(BODY.cells(target,require_complete=True)))
        watch['requests']=[r for r in watch['requests'] if r['source'] not in PERCEPTIONS
            or ally_area and (r['source']==PERCEPTION or move['class'] in ('물리','특수'))]
    if watch['requests']:event['defense_watch']=watch


def wants_boundary(event):
    return bool(event.get('defense_watch') and event.get('hit') is True)


def _move_facts(move):
    """A source snapshot uses identities rather than copied live actors."""
    def value(item):
        if hasattr(item,'entity_id'):return {'actor_id':item.entity_id}
        if isinstance(item,dict):return {k:value(v) for k,v in item.items()}
        if isinstance(item,(list,tuple)):return [value(v) for v in item]
        if isinstance(item,(set,frozenset)):return sorted((value(v) for v in item),key=ROOT.canonical)
        return item
    return value(move)


def _facts(e, event, args):
    completion = _row(e, event)
    return {'event_id': event['id'], 'completion_id': completion['id'],
            'actor_id': event['actor'].entity_id, 'original_id': event['target'].entity_id,
            'targets': [c.entity_id for c in completion['targets']],
            'move': _move_facts(args['move']), 'hit': args['hit'], 'natural': args['nat'],
            'critical': args['crit'], 'round': event['round'], 'seconds': event['elapsed_seconds'],
            'watch': event['defense_watch']}


def _area_cells(e,event,move):
    """Use the same native area producer for offer admission and accuracy facts."""
    import weapon_actions as WEAPON, area_targets as AREA
    shape=WEAPON.range_spec(e,move,event['actor']).get('shape')
    if e.grid is not None and shape:
        aim=move.get('_area_aim',event['actor'].pos if shape=='burst' else event['target'].pos)
        return sorted(AREA.cells(e,event['actor'],AREA.bind(e,event['actor'],move,aim)))
    return []


def begin_boundary(e, event, args):
    if not wants_boundary(event):
        return
    completion = _row(e, event); key = event['target'].entity_id
    facts = _facts(e, event, args)
    facts['area_cells']=_area_cells(e,event,args['move'])
    rows = completion.setdefault('defense', {})
    if key in rows:
        if rows[key]['fingerprint'] != ROOT.fingerprint(facts):
            raise ValueError('actual defense accuracy declaration changed')
        return
    rows[key] = {'facts': deepcopy(facts), 'fingerprint': ROOT.fingerprint(facts),
                 'event_id': event['id'], 'cursor': 0, 'decisions': {}, 'attempts': [],
                 'phase': 'choices', 'recipients': [], 'children': {}, 'total': 0}
    watch=event['target'].spec.get(WATCH)
    if watch is not None:
        remaining=[r for r in watch['requests'] if r not in facts['watch']['requests']]
        if remaining:watch['requests']=remaining
        else:event['target'].spec.pop(WATCH, None)


def _defense(e, event):
    if not event.get('defense_watch'):
        return None
    return _row(e, event).get('defense', {}).get(event['target'].entity_id)


def routed(e, event_id):
    event = getattr(e, '_passive_events', {}).get(event_id)
    return bool(event and event.get('defense_watch') and
                _defense(e, event) is not None)


def choose(e, event_id, reactor, *, use, options=None, reason):
    import passive_events as PASSIVE
    _reason(reason); WORLD.require_actors(e, reactor)
    validate_world(e,WORLD.actor_index(e))
    if type(use) is not bool or (options is not None and type(options) is not dict):
        raise ValueError('explicit Boolean defense choice and option mapping required')
    event = e._passive_events.get(event_id)
    if (event is None or e._passive_pending != event_id or
            event['phase'] != 'accuracy_boundary' or not routed(e, event_id)):
        raise ValueError('actual waiting accuracy defense required')
    state = _defense(e, event)
    requests = state['facts']['watch']['requests']; cursor = state['cursor']
    if state['phase'] != 'choices' or cursor >= len(requests) or requests[cursor]['actor_id'] != reactor.entity_id:
        raise ValueError('only the next actual defense owner may decide')
    choice = {'use': use, 'options': deepcopy(options or {}), 'reason': reason}
    previous=state['decisions'].get(str(cursor))
    if state.get('active_attempt') and previous != choice:
        raise ValueError('paid Intercept declaration cannot change during continuation')
    def apply(staged, owner):
        native_event = staged._passive_events[event_id]
        _defense(staged, native_event)['decisions'][str(cursor)] = choice
        try:
            return PASSIVE.deliver(staged, event_id)
        except PASSIVE.PassiveEventPending as pending:
            if staged._passive_pending != pending.event_id or pending.event_id not in staged._passive_events:
                raise
            return None
    result = GRANTS.transition(e, reactor, apply, include_grid=e.grid is not None, include_rulings=True)
    if e._passive_pending is not None:
        raise PASSIVE.PassiveEventPending(e._passive_pending)
    return result


def _prohibited(e, move, category):
    if move.get('_type_ace_boo') and category in ('intercept','dodge','parry','shield'):return True
    specific = e.r.move_defense_policy['prohibited_moves'].get(move['id'], ())
    if category in specific:
        return True
    if category != 'intercept':
        return False
    import combat_social_edges as SOCIAL
    mm, _ = e.r.move_mech(move['id'])
    if mm.get('never_miss') or move.get('ac') is None:
        return True
    effects = mm.get('effects_exec', ())
    if any(x.get('cannot_be_redirected') or 'intercept' in x.get('unavoidable_by', ()) for x in effects):
        return True
    return '사회적' in move.get('keywords', ()) or 'Social' in move.get('keywords', ())


def _intercept_permission(e, actor, target, attacker, move):
    import turn as TURN, vision_impairment as VISION
    import pokemon_entities as POKEMON
    _active(e, actor); WORLD.require_actors(e, target)
    if target.dead or target.captured or not target.on_field:
        raise ValueError('actual present living protected target required')
    if actor in (target, attacker) or not actor.side or actor.side != target.side or actor.side == attacker.side:
        raise ValueError('Intercept requires an attacked ally and actual enemy')
    if _prohibited(e, move, 'intercept'):
        raise ValueError('this actual attack prohibits Intercept attempts')
    blocked = {'수면','잠듦','혼란','난동','얼음','얼음상태','빙결','구속','마비'}
    if blocked.intersection(actor.conditions) or not TURN.movement_permission(e, actor) or VISION.accuracy_level(e, actor) == 'total':
        raise ValueError('current condition prohibits Intercept')
    if actor.kind == 'pokemon':
        import athlete as ATHLETE
        # An armed Athlete Coaching permits the Intercept for an ally regardless of loyalty.
        if ATHLETE.coaching_ready(e, actor, 'intercept') is None:
            loyalty = POKEMON.loyalty_value(actor, required=True)
            if loyalty < 3 or (loyalty < 6 and actor.spec.get('trainer_id') != target.entity_id):
                raise ValueError('actual trainer relationship and loyalty do not permit Intercept')
    words = ' '.join(move.get('keywords', ())) + ' ' + str(move.get('range', ''))
    if any(word in words for word in ('우선','방해','Priority','Interrupt')) and actor.staged('spe') <= attacker.staged('spe'):
        raise ValueError('Intercept of Priority/Interrupt requires greater Speed')


def _path_plan(e, actor, target, attacker, source, options):
    import movement_actions as MOVE, body_state as BODY, map_terrain as TERRAIN
    from grid import cheb
    perception=source in PERCEPTIONS
    allowed = {'path','mode'} if perception else {'path','skill','mode','roll_options'} | ({'shove_destination'} if source == MELEE else set())
    required={'path'} if perception else {'path','skill'}
    if set(options) - allowed or not required <= set(options):
        raise ValueError('exact source-specific Intercept choices required')
    if not perception and options['skill'] not in ('곡예','육상'):
        raise ValueError('Intercept requires Acrobatics or Athletics')
    path = options['path']
    if not isinstance(path, (tuple,list)) or len(path) < 2:
        raise ValueError('Intercept path includes actual origin and endpoint')
    path = tuple(MOVE._point(point) for point in path)
    if e.grid is None or path[0] != actor.pos or any(cheb(a,b) != 1 for a,b in zip(path,path[1:])):
        raise ValueError('actual continuous Intercept route required')
    mode = options.get('mode','land')
    if mode not in ('land','swim','sky','levitate'):
        raise ValueError('this physical Intercept route requires an observed continuous movement mode')
    allowance = MOVE.distance_budget(e, actor, mode)
    probe = copy(actor); probe.spec = dict(actor.spec)
    distance = 0; diagonal = getattr(actor,'_diagonal_steps',0); cumulative = []
    for point in path[1:]:
        step, diagonal = MOVE.step_cost(probe.pos, point, diagonal)
        step += MOVE.slow_terrain_penalty(e, probe, point, mode, step=step)
        if (not TERRAIN.can_travel(e, probe, point, mode, altitude=actor.spec.get('_movement_altitude',0), capability_actor=actor) or
                not BODY.can_place(e, probe, point, origin=probe.pos, ignore_actors=(target,) if source == MELEE and point == path[-1] else ())):
            raise ValueError('Intercept route is blocked or occupied')
        distance += step; cumulative.append(distance); probe.pos = point
    if distance > allowance:
        raise ValueError('Intercept route exceeds actual movement capability')
    if source == MELEE:
        if __import__('type_ace').push_immunity(e,target):
            raise ValueError('Melee Intercept requires an ally without Push immunity')
        if path[-1] != target.pos or not e.adjacent(attacker, target):
            raise ValueError('Melee Intercept ends at the ally attacked by an adjacent foe')
        destination = MOVE._point(options.get('shove_destination'))
        if cheb(target.pos,destination) != 1 or not BODY.can_place(e,target,destination,origin=target.pos):
            raise ValueError('actual legal one-metre ally push required')
    elif not perception:
        a,b = attacker.pos,target.pos; q = path[-1]
        if (q in (a,b) or (q[0]-a[0])*(b[1]-a[1]) != (q[1]-a[1])*(b[0]-a[0]) or
                not all(min(a[i],b[i]) <= q[i] <= max(a[i],b[i]) for i in (0,1))):
            raise ValueError('Ranged Intercept endpoint must lie directly between actual source and target')
        destination = None
    else:destination=None
    rolls = deepcopy(options.get('roll_options') or {})
    if type(rolls) is not dict:
        raise ValueError('actual skill roll option mapping required')
    if not perception:e._prepare_skill_roll(actor, options['skill'], **rolls)
    target_cells=BODY.cells(target,require_complete=True)
    offsets=sorted((p[0]-target.pos[0],p[1]-target.pos[1]) for p in target_cells)
    return {'path':path,'distance':distance,'cumulative':cumulative,'mode':mode,'ally_body_offsets':offsets,
            'allowance':allowance,'shove_destination':destination,'skill':options.get('skill'),'roll_options':rolls}


def authorize_trigger(e, event_id):
    event = e._passive_events.get(event_id)
    if (event is None or event['phase'] != 'accuracy_boundary' or
            getattr(e,'_defense_attempt',None) != event_id or not routed(e,event_id)):
        raise ValueError('actual native defense attempt scope required')
    state = _defense(e,event)
    return {'kind':'accuracy','event_id':event_id,'owner':event['actor'],
            'round':event['round'],'defense_fingerprint':state['fingerprint']}


def _cost_shape(profile):
    """Only reviewed Full/Shift next-action costs enter this native frame."""
    if type(profile) is not dict or set(profile) != {'action','payment','budget','modifier_sources'}:
        raise ValueError('exact native Intercept cost profile required')
    costs={'full':{'standard':1,'shift':1},'shift':{'shift':1}}
    if (profile['action'] not in costs or profile['payment']!='next' or
            type(profile['budget']) is not dict or profile['budget']!=costs[profile['action']] or
            any(type(v) is not int for v in profile['budget'].values()) or
            type(profile['modifier_sources']) is not list):
        raise ValueError('unsupported native Intercept cost profile')
    return profile


def _paid_cost_profile(e, actor, attempt):
    if attempt['source'] in PERCEPTIONS:
        profile=attempt.get('cost_profile')
        action='shift' if attempt['source']==PERCEPTION else 'free'
        expected={'action':action,'payment':'next' if action=='shift' else None,
                  'budget':{'shift':1} if action=='shift' else {},'modifier_sources':[]}
        if profile!=expected:raise ValueError('Perception paid cost differs from its selected source')
        return profile
    # Published 1220 receipts predate profiles and always paid exactly Full.
    # Removing a new Shift profile cannot forge a legacy receipt: the actual
    # initiative request and its paid action must still match the Full cost.
    if 'cost_profile' not in attempt:
        return {'action':'full','payment':'next','budget':{'standard':1,'shift':1},'modifier_sources':[]}
    import intercept_profiles as PROFILES
    profile=_cost_shape(attempt['cost_profile'])
    PROFILES.validate_profile(e,actor,profile,historical=True)
    return profile


def _paid_request(e,event,attempt,actor,*,completed):
    profile=_paid_cost_profile(e,actor,attempt)
    window=getattr(e,'_initiative_interrupts',{}).get('windows',{}).get(attempt['window_id'])
    if not window or window['trigger'].get('event_id')!=event['id']:
        raise ValueError('Intercept lacks its actual reaction action receipt')
    request=next((r for r in window['requests'] if r['id']==attempt['request_id']),None)
    if (request is None or request['actor'] is not actor or
            request['source']!=attempt['source'] or
            request['status']!=('completed' if completed else 'open') or
            request['payment']!=profile['payment'] or request['budget']!=profile['budget']):
        raise ValueError('Intercept reaction owner or sourced action cost changed')
    if completed and request['receipt']['actions']!=[profile['action']]:
        raise ValueError('Intercept paid action differs from its source profile')
    return profile


def _attempt(e, event, state, request, choice):
    import initiative_interrupts as INTERRUPTS, turn as TURN
    import movement_actions as MOVE, forced_movement as FORCED, body_state as BODY
    import frequency as FREQUENCY, ability_transitions as ABILITIES
    import reactive_ability_events as REACTIVE, action_lifecycle as ACTION
    actor = WORLD.actor_index(e)[request['actor_id']]
    source = request['source']; _selected(e,source)
    target,attacker = event['target'],event['actor']; move = state['facts']['move']
    if state.get('active_attempt'):
        if state['active_attempt'].get('kind')=='detect':return _continue_detect(e,event,state,actor)
        return _continue_intercept(e,event,state,actor,target)
    if not choice['use']:
        return {'source':source,'actor_id':actor.entity_id,'outcome':'declined','paid':False}
    _active(e,actor)
    if source==DETECT:
        if choice['options'] or actor is not target:raise ValueError('actual Detect takes no supplied hit or recipient options')
        return _begin_detect(e,event,state,actor)
    import unown_imbuement as UNOWN
    if source == UNOWN.SOURCE:
        if choice['options'] or actor is not target:
            raise ValueError('actual Unown Detect takes no supplied hit or recipient')
        proof=UNOWN.detect_actual(e,event,actor,reason=choice['reason'])
        state['recipients'] = [{'actor_id':target.entity_id,'hit':False,'intercepted':False}]
        return {'source':source,'actor_id':actor.entity_id,'outcome':'avoided','paid':True,'unown':proof}
    if source == DODGE:
        if choice['options'] or actor is not target or not ABILITIES.active(actor,DODGE):
            raise ValueError('actual owned Dodge takes no supplied hit/recipient options')
        if _prohibited(e,move,'avoid_hit'):
            raise ValueError('this actual Move prohibits Dodge reactions')
        frequency = e.r.move_defense_policy['sources'][DODGE]['frequency']
        import ability_interrupt_choices as ABILITY_INTERRUPTS
        ABILITY_INTERRUPTS.pay_free(e,actor,DODGE,frequency)
        state['recipients'] = [{'actor_id':target.entity_id,'hit':False,'intercepted':False}]
        return {'source':source,'actor_id':actor.entity_id,'outcome':'avoided','paid':True}
    if source in PERCEPTIONS:
        return _begin_perception(e,event,state,actor,source,choice)
    _intercept_permission(e,actor,target,attacker,move)
    if source == RANGED:
        import weapon_actions as WEAPON
        reach=WEAPON.range_spec(e,move,attacker)
        if reach.get('shape') or '근접' in str(move.get('range','')):
            raise ValueError('Ranged Intercept requires a ranged targeted attack')
    plan = _path_plan(e,actor,target,attacker,source,choice['options'])
    import intercept_profiles as PROFILES
    cost_profile=_cost_shape(deepcopy(PROFILES.profile(e,actor,event,source)))
    PROFILES.validate_profile(e,actor,cost_profile,historical=False)
    number = state['cursor']; request_id = event['id']+':defense:'+str(number)
    e._defense_attempt = event['id']
    try:
        queued = INTERRUPTS.queue(e,[{'id':request_id,'actor_id':actor.entity_id,'source':source,
            'priority':0,'mode':'reaction','payment':cost_profile['payment'],
            'budget':cost_profile['budget'],'clock':'none'}],
            trigger={'kind':'accuracy','event_id':event['id']})
        if queued['status'] not in ('queued','already_queued'):
            raise ValueError('Intercept reaction requires an established action cost')
        INTERRUPTS.begin(e,queued['window_id'],request_id)
        if not TURN.spend(e,actor,cost_profile['action'],source,movement=cost_profile['action']=='shift'):
            raise ValueError('actual sourced Intercept action unavailable')
        divisor = 3 if source == MELEE else 2
        import athlete as ATHLETE
        coaching = ATHLETE.coach_intercept(e,actor,target,source)
        if coaching is None:
            passed,total = e.skill_check(actor,plan['skill'],divisor*plan['distance'],**plan['roll_options'])
        else:
            # A coached Intercept automatically succeeds its skill check: no roll, full declared distance.
            passed,total = True,divisor*plan['distance']
        allowed = plan['distance'] if passed else min(plan['distance'],max(0,total//divisor))
        facts={'source':source,'actor_id':actor.entity_id,'paid':True,
               'window_id':queued['window_id'],'request_id':request_id,
               'check_total':total,'dc':divisor*plan['distance'],'plan':plan,
               'passed':passed,'allowed':allowed,'cost_profile':cost_profile}
        if coaching is not None:facts['coaching']=coaching
        state['active_attempt']={'facts':facts,'fingerprint':ROOT.fingerprint(facts),
                                 'progress':{},'push':None,'phase':'checked'}
        return _continue_intercept(e,event,state,actor,target)
    finally:
        del e._defense_attempt


def _begin_perception(e,event,state,actor,source,choice):
    """A real ally area hit supplies the trigger; the owner chooses only its route."""
    import chronicler as CH, body_state as BODY, turn as TURN
    import initiative_interrupts as INTERRUPTS, ability_transitions as ABILITIES
    definition=CH.perception_definition(e.r,source)
    attacker=event['actor'];move=state['facts']['move']
    cells={tuple(p) for p in state['facts']['area_cells']}
    if (actor is not event['target'] or attacker is actor or not actor.side or attacker.side!=actor.side
            or not ABILITIES.active(actor,e.r.selection.units[source]['title']) or not cells
            or not cells.intersection(BODY.cells(actor,require_complete=True))
            or definition['damaging_only'] and move['class'] not in ('물리','특수')):
        raise ValueError('Perception requires an actual ally area attack hitting its owned recipient')
    if not TURN.movement_permission(e,actor):raise ValueError('Perception requires actual Shift movement permission')
    plan=_path_plan(e,actor,actor,attacker,source,choice['options'])
    if source==PERCEPTION_PLAYTEST and (len(plan['path'])!=2 or plan['distance']!=1):
        raise ValueError('Playtest Perception grants only a one-metre Disengage')
    offsets=plan['ally_body_offsets'];endpoint=plan['path'][-1]
    if cells.intersection((endpoint[0]+dx,endpoint[1]+dy) for dx,dy in offsets):
        raise ValueError('Perception route must remove the complete body from the actual attack area')
    cost={'action':definition['action'],'payment':definition['payment'],
          'budget':{'shift':1} if source==PERCEPTION else {},'modifier_sources':[]}
    window_id=request_id=None
    history=len(getattr(actor,'_action_history',[]))
    if source==PERCEPTION:
        request_id=event['id']+':perception:'+str(state['cursor']);e._defense_attempt=event['id']
        try:
            queued=INTERRUPTS.queue(e,[{'id':request_id,'actor_id':actor.entity_id,'source':source,
                'priority':0,'mode':'reaction','payment':'next','budget':{'shift':1},'clock':'none'}],
                trigger={'kind':'accuracy','event_id':event['id']})
            if queued['status'] not in ('queued','already_queued'):raise ValueError('Perception Shift cost pending')
            window_id=queued['window_id'];INTERRUPTS.begin(e,window_id,request_id)
            if not TURN.spend(e,actor,'shift',source,movement=True):raise ValueError('Perception Shift action unavailable')
        finally:del e._defense_attempt
    else:
        __import__('ability_interrupt_choices').pay_free(e,actor,source,{'kind':'at_will','uses':1})
    payment={'source':source,'owner_id':actor.entity_id,'action':cost['action'],'round':e.round_no,
             'at':e.elapsed_seconds,'history_index':history}
    facts={'source':source,'actor_id':actor.entity_id,'paid':True,'window_id':window_id,'request_id':request_id,
           'check_total':0,'dc':0,'plan':plan,'passed':True,'allowed':plan['distance'],'cost_profile':cost,
           'payment':payment,'payment_fingerprint':ROOT.fingerprint(payment)}
    # Nested native transitions can replace dictionaries; retain the current declaration.
    state=_defense(e,e._passive_events[event['id']])
    state['active_attempt']={'facts':facts,'fingerprint':ROOT.fingerprint(facts),'progress':{},'push':None,'phase':'checked'}
    return _continue_intercept(e,e._passive_events[event['id']],state,actor,actor)


def perception_disengage_authority(e,actor,scope,destination,altitude):
    """Only the paid Playtest decision can suppress its one-metre opportunity attack."""
    if type(scope) not in (tuple,list) or len(scope)!=2 or scope[1]!=actor.entity_id:
        raise ValueError('actual Perception Disengage scope required')
    event=e._passive_events.get(scope[0]);state=None if event is None else _defense(e,event)
    active=None if state is None else state.get('active_attempt')
    facts={} if active is None else active['facts'];plan=facts.get('plan',{})
    if (event is None or event['target'] is not actor or state['phase']!='choices'
            or facts.get('source')!=PERCEPTION_PLAYTEST or facts.get('actor_id')!=actor.entity_id
            or active['fingerprint']!=ROOT.fingerprint(facts) or plan.get('distance')!=1
            or len(plan.get('path',()))!=2 or tuple(plan['path'][0])!=actor.pos
            or tuple(plan['path'][1])!=destination or altitude!=actor.spec.get('_movement_altitude',0)):
        raise ValueError('Perception Disengage differs from its paid native route')
    _validate_perception_attempt(e,event,actor,facts,completed=False)


def _begin_detect(e,event,state,actor):
    import initiative_interrupts as INTERRUPTS, party_actions as PARTY
    request_id=event['id']+':detect:'+str(state['cursor'])
    locked=PARTY.switch_lock(e,actor) is not None
    e._defense_attempt=event['id']
    try:
        queued=INTERRUPTS.queue(e,[{'id':request_id,'actor_id':actor.entity_id,'source':DETECT,
            'priority':0,'mode':'switch_interrupt' if locked else 'reaction',
            'payment':'future_turn' if locked else 'next','budget':{'standard':1},'clock':'none','move_id':DETECT}],
            trigger={'kind':'accuracy','event_id':event['id']})
        if queued['status'] not in ('queued','already_queued'):raise ValueError('actual Detect entitlement required')
        INTERRUPTS.begin(e,queued['window_id'],request_id)
        # Use the current native continuation container after nested transitions.
        state=_defense(e,e._passive_events[event['id']])
        facts={'source':DETECT,'actor_id':actor.entity_id,'window_id':queued['window_id'],'request_id':request_id}
        state['active_attempt']={'kind':'detect','facts':facts,'fingerprint':ROOT.fingerprint(facts),'phase':'started'}
        e.use_move_on(actor,actor,DETECT,e.everyone)
        return _continue_detect(e,e._passive_events[event['id']],_defense(e,e._passive_events[event['id']]),actor)
    finally:
        del e._defense_attempt


def _continue_detect(e,event,state,actor):
    import initiative_interrupts as INTERRUPTS, passive_events as PASSIVE
    active=state['active_attempt'];facts=active['facts'];current=INTERRUPTS.frame(e)
    if (active['kind']!='detect' or active['fingerprint']!=ROOT.fingerprint(facts) or not current
            or current['actor'] is not actor or current['window_id']!=facts['window_id']
            or current['request_id']!=facts['request_id']):
        raise ValueError('Detect continuation lost its selected actual native frame')
    completions=[row for key,row in getattr(e,'_move_completions',{}).items()
        if key not in current['completion_ids_before'] and row['actor'] is actor]
    if (len(completions)!=1 or completions[0]['move_id']!=DETECT
            or completions[0]['phase']=='interrupted'):
        raise ValueError('Detect native selected Move did not activate or was interrupted')
    if completions[0]['phase']!='complete':
        return PASSIVE._pending(e,event,'actual_detect_move_completion')
    completion=completions[0];shield=deepcopy(actor.shield)
    if (completion['move_id']!=DETECT or completion['targets']!=[actor]
            or not shield or shield.get('_native_shield')!={'completion_id':completion['id'],
                'source_id':DETECT,'actor_id':actor.entity_id}):
        raise ValueError('Detect needs its actual native Move Shield completion')
    INTERRUPTS.finish(e)
    event=e._passive_events[event['id']];state=_defense(e,event)
    if not consume_shield(e,event['actor'],actor,state['facts']['move'],actual_hit=True):
        raise ValueError('native Detect must consume its actual Shield for the triggering hit')
    state['recipients']=[{'actor_id':actor.entity_id,'hit':False,'intercepted':False}]
    state.pop('active_attempt')
    return dict(facts,outcome='avoided',paid=True,
        detect={'completion_id':completion['id'],'shield':shield})


def _validate_detect_attempt(e,event,actor,attempt):
    import initiative_interrupts as INTERRUPTS
    proof=attempt.get('detect',{});completion=getattr(e,'_move_completions',{}).get(proof.get('completion_id'))
    state=getattr(e,INTERRUPTS.KEY,None)
    window=None if state is None else state['windows'].get(attempt['window_id'])
    request=None if window is None else next((r for r in window['requests'] if r['id']==attempt['request_id']),None)
    if (completion is None or completion['actor'] is not actor or completion['move_id']!=DETECT
            or completion['phase']!='complete' or completion['targets']!=[actor]
            or completion['results']!={actor.entity_id:{'hit':True,'dealt':0,'cancelled':False}}
            or event['target'] is not actor or attempt['outcome']!='avoided' or attempt['paid'] is not True
            or request is None or request['status']!='completed' or request['actor'] is not actor
            or request['receipt'].get('move_completion')!=completion['id']
            or proof.get('shield',{}).get('_native_shield')!={'completion_id':completion['id'],
                'source_id':DETECT,'actor_id':actor.entity_id}):
        raise ValueError('Detect defense lost its actual completed selected Move and consumed native Shield')
    validate_move_interrupt_request(e,window,request)


def _continue_intercept(e,event,state,actor,target):
    import initiative_interrupts as INTERRUPTS, movement_actions as MOVE
    import forced_movement as FORCED, body_state as BODY, passive_events as PASSIVE
    import action_lifecycle as ACTION
    active=state['active_attempt']; facts=active['facts']; plan=facts['plan']
    if active['fingerprint']!=ROOT.fingerprint(facts) or facts['actor_id']!=actor.entity_id:
        raise ValueError('paid Intercept check or movement declaration changed')
    frame=INTERRUPTS.frame(e)
    if facts['source']!=PERCEPTION_PLAYTEST and (not frame or frame['window_id']!=facts['window_id'] or frame['request_id']!=facts['request_id']
            or frame['actor'] is not actor):
        raise ValueError('paid Intercept requires the same actual reaction frame')
    if active['phase']=='checked':
        if facts['passed'] and facts['source']==MELEE:
            active['push']=FORCED.along_path(e,actor,target,points=[target.pos,plan['shove_destination']],source=facts['source'])
            if active['push']['moved']!=1:
                raise ValueError('successful Intercept requires its actual one-metre push')
        active['phase']='moving'
    count=sum(n<=facts['allowed'] for n in plan['cumulative'])
    selected_path=list(plan['path'][1:1+count])
    if plan['mode'] in ('sky','levitate'):
        selected_path=[{'position':p,'altitude':actor.spec.get('_movement_altitude',0)} for p in selected_path]
    progress=active['progress']
    receipts=set(getattr(e,'_effect_dispatch_receipts',{}))
    try:
        movement=MOVE.follow_paid_path(e,actor,selected_path,mode=plan['mode'],
                                      maximum_distance=facts['allowed'],progress=progress,
                                      **({'disengage_scope':(event['id'],actor.entity_id)} if facts['source']==PERCEPTION_PLAYTEST else {}))
    except PASSIVE.PassiveEventPending as pending:
        if e._passive_pending!=pending.event_id or pending.event_id not in e._passive_events:raise
        if progress.get('phase')=='departing':progress['phase']='reaction_pending'
        active.setdefault('nested_events',[]).append(pending.event_id)
        raise
    except ValueError:
        # A real nested action may return with a Stamina choice. Preserve its
        # already executed departure and the paid movement prefix.
        outstanding=any(row['phase']!='resolving' and any(t['status']!='completed' for t in row['triggers'])
                        for row in getattr(e,'_native_action_resolutions',{}).values())
        held=[key for key in getattr(e,'_effect_dispatch_receipts',{}) if key not in receipts]
        if not outstanding and not ACTION.pending_resolution_effects(e,{'effects':held}):raise
        progress.setdefault('effects',[]).extend(k for k in held if k not in progress.get('effects',()))
        if progress.get('phase')=='departing':progress['phase']='reaction_pending'
        return PASSIVE._pending(e,event,'intercept_movement_effects_pending')
    active['movement']=movement
    if movement['steps']!=len(selected_path) or progress.get('phase')!='complete':
        return PASSIVE._pending(e,event,'intercept_paid_movement_pending')
    if facts['source']!=PERCEPTION_PLAYTEST:INTERRUPTS.finish(e)
    target_cells=sorted(BODY.cells(target,require_complete=True))
    if facts['source'] in PERCEPTIONS:
        if set(target_cells).intersection(tuple(p) for p in state['facts']['area_cells']):
            raise ValueError('Perception movement did not leave the actual attack area')
        state['recipients']=[{'actor_id':actor.entity_id,'hit':False,'intercepted':False}]
    elif facts['passed']:
        cells = {tuple(c) for c in state['facts']['area_cells']}
        remains = bool(cells and cells.intersection(BODY.cells(target,require_complete=True)))
        state['recipients'] = ([{'actor_id':target.entity_id,'hit':True,'intercepted':False}] if remains else [])
        state['recipients'].append({'actor_id':actor.entity_id,'hit':True,'intercepted':True})
    result={key:facts[key] for key in ('source','actor_id','paid','window_id','request_id','check_total','dc','plan')}
    if 'cost_profile' in facts:result['cost_profile']=deepcopy(facts['cost_profile'])
    if 'coaching' in facts:result['coaching']=deepcopy(facts['coaching'])
    if facts['source'] in PERCEPTIONS:
        result.update(payment=deepcopy(facts['payment']),payment_fingerprint=facts['payment_fingerprint'])
    result.update(outcome='avoided' if facts['source'] in PERCEPTIONS else 'intercepted' if facts['passed'] else 'failed',movement=movement,
                  push=active['push'],ally_cells_after=target_cells,progress=deepcopy(progress))
    state.pop('active_attempt')
    return result


def deliver_boundary(e,event):
    import passive_events as PASSIVE
    state = _defense(e,event)
    if state is None:
        return
    if state['fingerprint'] != ROOT.fingerprint(state['facts']):
        raise ValueError('native defense facts changed')
    if state['phase'] != 'choices':
        return
    requests = state['facts']['watch']['requests']
    while state['cursor'] < len(requests):
        cursor = state['cursor']; choice = state['decisions'].get(str(cursor))
        if choice is None:
            return PASSIVE._pending(e,event,'actual_defense_choice')
        result = _attempt(e,event,state,requests[cursor],choice)
        # Nested transactions preserve graph identity, but obtain the current
        # records again instead of relying on a pre-transition container.
        event = e._passive_events[event['id']]; state = _defense(e,event)
        state['attempts'].append(result); state['cursor'] += 1
        if result['outcome'] in ('intercepted','avoided'):
            break
    if not state['recipients']:
        state['recipients'] = [{'actor_id':event['target'].entity_id,'hit':True,'intercepted':False}]
    state['phase'] = 'resolving'


def cancel_waiting(e, event):
    """Cancel an unstarted defense when its native attacker becomes ineligible."""
    state = _defense(e, event)
    if state is None:
        return True
    ability_wait=(state['phase']=='resolving' and
        event.get('ability_interrupts',{}).get('phase')=='choices' and
        not state['children'] and not state['total'])
    if (state['phase'] != 'choices' and not ability_wait) or state.get('active_attempt'):
        # Already delivered recipient effects must finish their own receipts.
        return False
    if not (event['actor'].fainted or event['actor'].dead):
        raise ValueError('defense cancellation requires an ineligible actual attacker')
    state['phase'] = 'cancelled'
    state['recipients'] = []
    event['defense_routed'] = True
    return True


@contextmanager
def _recipient_scope(e, token):
    old = getattr(e,'_defense_recipient_scope',None)
    e._defense_recipient_scope = token
    try:
        yield
    finally:
        if old is None:del e._defense_recipient_scope
        else:e._defense_recipient_scope = old


def require_recipient(e, token, attacker, recipient, move, completion_id):
    if type(token) not in (tuple,list) or len(token) != 3 or tuple(token) != getattr(e,'_defense_recipient_scope',None):
        raise ValueError('actual native recipient producer required')
    event_id,original_id,recipient_id = token
    event = e._passive_events.get(event_id)
    if event is None or event['actor'] is not attacker or event['target'].entity_id != original_id:
        raise ValueError('recipient producer belongs to another declared attack')
    state = _defense(e,event)
    if (state['phase'] != 'resolving' or event['completion_id'] != completion_id or
            recipient.entity_id != recipient_id or _move_facts(move) != state['facts']['move']):
        raise ValueError('recipient producer differs from actual attack snapshot')
    matches = [r for r in state['recipients'] if r['actor_id'] == recipient_id]
    if len(matches) != 1:
        raise ValueError('recipient lacks a unique native defense outcome')
    return matches[0]['intercepted']


def recipient_prevented(e,token,attacker,recipient,move,completion_id):
    """Actual Detect negates effects; printed Dodge instead causes an ordinary miss."""
    require_recipient(e,token,attacker,recipient,move,completion_id)
    state=_defense(e,e._passive_events[token[0]])
    import unown_imbuement as UNOWN
    return (not next(row['hit'] for row in state['recipients'] if row['actor_id']==recipient.entity_id)
        and any(attempt['actor_id']==recipient.entity_id and attempt['source'] in (DETECT,UNOWN.SOURCE)
                and attempt.get('outcome')=='avoided' for attempt in state['attempts']))


def require_damage_receipt(e, token, attacker, recipient, move):
    event = e._passive_events.get(token[0]) if isinstance(token,(list,tuple)) and token else None
    if event is None:
        raise ValueError('actual defense event required for intercepted damage')
    return require_recipient(e,token,attacker,recipient,move,event['completion_id'])


def finish(e,args):
    previous=getattr(e,'_defense_finishing',False)
    e._defense_finishing=True
    try:return _finish(e,args)
    finally:
        if previous:e._defense_finishing=previous
        else:del e._defense_finishing


def _finish(e, args):
    import passive_events as PASSIVE, reactive_ability_events as REACTIVE
    import move_completion as COMPLETE, heavy_standard_adapter as STANDARD
    event = e._passive_events[args['passive_event']]; state = _defense(e,event)
    if state is None or state['phase'] not in ('resolving','complete'):
        raise ValueError('actual resolved defense choices required')
    if state['phase'] == 'complete':
        return state['total']
    completion = _row(e,event); index = WORLD.actor_index(e)
    for recipient_plan in state['recipients']:
        uid = recipient_plan['actor_id']; recipient = index[uid]
        received = completion.setdefault('received',{}).get(uid)
        if received is not None:
            continue
        prior=completion['results'].get(uid)
        if uid!=event['target'].entity_id and prior is not None and prior['hit'] and not prior['cancelled']:
            state.setdefault('prior_results',{})[uid]=dict(prior)
            continue
        token = (event['id'],event['target'].entity_id,uid)
        options = {key:args[key] for key in ('move_id','move','mm','conf','nat','crit','set_damage','precision_event','weather_attack','ordinary_single','completion_id')}
        with _recipient_scope(e,token):
            child = PASSIVE.begin_recipient(e,event,recipient,hit=recipient_plan['hit'],token=token)
            state['children'][uid] = child['id']
            import precise_actions as PRECISE
            if recipient is args['target']:
                precision=args['precision_event']
            else:
                precision=PRECISE.attacked(e,args['attacker'],recipient,args['move'],producer='Engine.use_move/defense-recipient')
            PRECISE.accuracy(precision,recipient_plan['hit'])
            options.update(hit=recipient_plan['hit'],passive_event=child['id'],defense_token=token,precision_event=precision)
            result = e._resolve_move_recipient(args['attacker'],recipient,**options)
        receipt = dict(result,actor=recipient,original_id=event['target'].entity_id,
                       event_id=event['id'],child_event=child['id'],intercepted=recipient_plan['intercepted'],
                       cancelled=False)
        completion.setdefault('received',{})[uid] = receipt
        state['total'] += result['dealt']
        import optional_weapon_framework as FRAMEWORK
        FRAMEWORK.observe_hit(e,completion,args['attacker'],recipient)
        REACTIVE.resolved_hit(e,args['attacker'],recipient,args['move'],args['completion_id'],
                              hit_prevented=result['hit_prevented'])
        PASSIVE.complete(e,child['id'],hit=recipient_plan['hit'],natural=args['nat'],critical=args['crit'],
                         dealt=result['dealt'],held=result['held'])
    # Re-entry after a child listener wait cannot apply damage or effects twice.
    for uid in state['children']:
        child = e._passive_events[state['children'][uid]]
        if child['phase'] != 'producer_return_boundary' or child['status'] not in ('applied','inapplicable'):
            return PASSIVE._pending(e,child,'recipient_effects_unresolved')
    receipts = [completion['received'][p['actor_id']] for p in state['recipients'] if p['actor_id'] in completion['received']]
    hit = any(r['hit'] for r in receipts) or any(r['hit'] for r in state.get('prior_results',{}).values())
    STANDARD.finish(e,args['standard_context'],hit=hit,dealt=state['total'])
    state['phase'] = 'complete'
    event.pop('continuation',None); event['phase'] = 'activated'
    event['defense_routed'] = True
    PASSIVE.complete(e,event['id'],hit=args['hit'],natural=args['nat'],critical=args['crit'],
                     dealt=state['total'],held=sum(r['held'] for r in receipts))
    COMPLETE.finish_target(e,args['completion_id'],args['attacker'],args['target'],hit=hit,dealt=state['total'],
                           effects=[key for r in receipts for key in r['effects']])
    for receipt in receipts:
        COMPLETE.record_return(e,receipt['child_event'],hit_prevented=receipt['hit_prevented'])
    COMPLETE.record_return(e,event['id'],hit_prevented=False)
    return state['total']


def skip_received(e, attacker, target, move, completion_id):
    import move_completion as COMPLETE
    completion = getattr(e,'_move_completions',{}).get(completion_id)
    received = None if completion is None else completion.get('received',{}).get(target.entity_id)
    if received is None:
        return False
    if completion['actor'] is not attacker or completion['move_id'] != move['id'] or received['actor'] is not target:
        raise ValueError('completed recipient alias belongs to another actual Move')
    completion.setdefault('recipient_aliases',{})[target.entity_id] = received['event_id']
    COMPLETE.finish_target(e,completion_id,attacker,target,hit=received['hit'],dealt=0)
    return True


def received_result(completion, target):
    return completion.get('received',{}).get(target.entity_id) or completion['results'].get(target.entity_id)


def hold_shield(e, actor, effect, ctx):
    result = deepcopy(effect)
    move = ctx.get('move'); token = ctx.get('move_completion')
    completion = getattr(e,'_move_completions',{}).get(token)
    if (move and completion and completion['actor'] is actor and completion['move_id'] == move.get('id') and
            any(word in move.get('keywords',()) for word in ('방패','Shield'))):
        result['_native_shield'] = {'completion_id':token,'source_id':move['id'],'actor_id':actor.entity_id}
    actor.shield = result


def shield_allowed(e, attacker, target, move):
    if not _prohibited(e,move,'shield'):
        return True
    proof = (target.shield or {}).get('_native_shield')
    if not proof:
        return True
    row = getattr(e,'_move_completions',{}).get(proof.get('completion_id'))
    if (not row or row['actor'] is not target or proof.get('actor_id') != target.entity_id or
            row['move_id'] != proof.get('source_id') or
            not any(word in row['move'].get('keywords',()) for word in ('방패','Shield'))):
        raise ValueError('held shield source provenance changed')
    return False


def native_detect(e, target):
    """Only the actual Detect Move grants its full 'hit by a Move' scope."""
    proof = (target.shield or {}).get('_native_shield')
    if not proof or proof.get('source_id') != 'move/판별':
        return False
    row = getattr(e,'_move_completions',{}).get(proof.get('completion_id'))
    if (not row or row['actor'] is not target or proof.get('actor_id') != target.entity_id or
            row['move_id'] != 'move/판별' or e.r._selected_rule(row['move_id']) != row['move_id'] or
            not any(word in row['move'].get('keywords',()) for word in ('방패','Shield'))):
        raise ValueError('held shield source provenance changed')
    return True


def consume_shield(e, attacker, target, move, *, actual_hit=False):
    """Preserve legacy timing; source-owned Detect waits for a real hit."""
    if target.shield is None or target.abilities_suppressed:
        return False
    detect = native_detect(e,target)
    if detect:
        if not actual_hit or move['class'] not in ('물리','특수','변화'):
            return False
    elif actual_hit or move['class'] not in ('물리','특수'):
        return False
    if not shield_allowed(e,attacker,target,move):
        return False
    e.log(f"  {attacker.name} {move['name']}: {target.name}의 방패({target.shield.get('trigger', '')[:20]}) → 명중 무효", 'effect/reaction_shield')
    target.shield = None
    return True


def _validate_perception_attempt(e,event,actor,attempt,*,completed):
    profile=_paid_cost_profile(e,actor,attempt)
    proof=attempt.get('payment',{})
    if (attempt.get('payment_fingerprint')!=ROOT.fingerprint(proof)
            or proof.get('source')!=attempt['source'] or proof.get('owner_id')!=actor.entity_id
            or proof.get('action')!=profile['action'] or proof.get('round')!=event['round']
            or proof.get('at')!=event['elapsed_seconds'] or actor is not event['target']):
        raise ValueError('Perception lost its actual paid source and owner receipt')
    if attempt['source']==PERCEPTION:
        _paid_request(e,event,attempt,actor,completed=completed)
    elif attempt.get('window_id') is not None or attempt.get('request_id') is not None:
        raise ValueError('Free Perception cannot manufacture a future Shift debt')
    if not completed and getattr(actor,'_action_history',[])[proof['history_index']:]!=[profile['action']]:
        raise ValueError('pending Perception lost its actual paid action')
    if completed:
        cells={tuple(p) for p in _defense(e,event)['facts']['area_cells']}
        if (attempt['outcome']!='avoided' or not attempt.get('paid')
                or not attempt.get('ally_cells_after') or cells.intersection(tuple(p) for p in attempt['ally_cells_after'])
                or attempt['movement']['steps']!=len(attempt['plan']['path'])-1
                or attempt['movement']['distance']!=attempt['plan']['distance']):
            raise ValueError('Perception outcome differs from its actual complete-body movement')


def validate_world(e,index):
    import passive_events as PASSIVE,move_completion as COMPLETE
    for actor in index.values():
        value = actor.spec.get(WATCH)
        if value is not None:
            if set(value) != {'requests','reason'}:
                raise ValueError('defense watch contains untrusted event facts')
            _reason(value['reason'])
            if type(value['requests']) is not list or not value['requests'] or len({r['actor_id'] for r in value['requests']})!=len(value['requests']):
                raise ValueError('distinct ordered actual defense offers required')
            for request in value['requests']:
                if set(request) != {'actor_id','source'} or request['actor_id'] not in index:
                    raise ValueError('defense watch lost actual reactor identity')
                _selected(e,request['source'])
    for token,row in getattr(e,'_move_completions',{}).items():
        for original_id,state in row.get('defense',{}).items():
            event = e._passive_events.get(state['event_id']); facts = state['facts']
            if (event is None or event['completion_id'] != token or event['actor'] is not row['actor'] or
                    event['target'].entity_id != original_id or original_id not in row['started'] or
                    facts['targets'] != [a.entity_id for a in row['targets']] or
                    state['fingerprint'] != ROOT.fingerprint(facts) or facts['move']['id'] != row['move_id'] or
                    facts['original_id']!=original_id or facts['event_id']!=event['id'] or
                    facts['actor_id']!=row['actor'].entity_id or facts['completion_id']!=token or
                    facts['watch']!=event['defense_watch'] or facts['move']!=_move_facts(COMPLETE.event_move(e,event))):
                raise ValueError('defense declaration lacks actual Move provenance')
            accuracy = next((o['facts'] for o in PASSIVE.observations(e,event['id']) if o['stage']=='accuracy'),None)
            if accuracy != {'hit':facts['hit'],'natural_roll':facts['natural'],'critical':facts['critical']}:
                raise ValueError('defense differs from original native accuracy result')
            if state['phase'] not in ('choices','resolving','complete','cancelled'):
                raise ValueError('known native defense phase required')
            requests = facts['watch']['requests']
            if len(state['attempts']) != state['cursor'] or not 0 <= state['cursor'] <= len(requests):
                raise ValueError('defense decision order changed')
            active=state.get('active_attempt')
            if active is not None:
                attempt=active['facts'];cursor=state['cursor']
                import initiative_interrupts as INTERRUPTS
                frame=INTERRUPTS.frame(e)
                if (state['phase']!='choices' or cursor>=len(requests) or
                        active['fingerprint']!=ROOT.fingerprint(attempt) or
                        any(attempt[k]!=requests[cursor][k] for k in ('source','actor_id')) or
                        (attempt['source']!=PERCEPTION_PLAYTEST and (not frame or frame['window_id']!=attempt['window_id'] or
                        frame['request_id']!=attempt['request_id'] or frame['actor'].entity_id!=attempt['actor_id']))):
                    raise ValueError('paid Intercept continuation lost its actual owner frame')
                if active.get('kind')=='detect':
                    window=getattr(e,INTERRUPTS.KEY)['windows'][attempt['window_id']]
                    request=window['requests'][window['cursor']]
                    validate_move_interrupt_request(e,window,request)
                    if (active['phase']!='started' or attempt['source']!=DETECT
                            or frame['actor'] is not event['target']
                            or getattr(frame['actor'],'_action_history',[])[frame['history_start']:] not in ([],['standard'])):
                        raise ValueError('pending Detect lost its one native selected Move')
                else:
                    plan=attempt['plan'];divisor=0 if attempt['source'] in PERCEPTIONS else 3 if attempt['source']==MELEE else 2
                    if (attempt['dc']!=divisor*plan['distance'] or
                            attempt['passed']!=(attempt['check_total']>=attempt['dc'])):
                        raise ValueError('paid Intercept continuation check changed')
                    progress=active['progress'];actor=index[attempt['actor_id']]
                    if attempt['source'] in PERCEPTIONS:
                        _validate_perception_attempt(e,event,actor,attempt,completed=False)
                    else:
                        profile=_paid_request(e,event,attempt,actor,completed=False)
                        if getattr(actor,'_action_history',[])[frame['history_start']:]!=[profile['action']]:
                            raise ValueError('paid Intercept continuation lost its sourced action')
                    if progress and (tuple(progress['position'])!=actor.pos or
                            progress['diagonals']!=getattr(actor,'_diagonal_steps',0)):
                        raise ValueError('paid Intercept movement prefix was displaced')
            for n,attempt in enumerate(state['attempts']):
                if any(attempt[k] != requests[n][k] for k in ('source','actor_id')):
                    raise ValueError('defense attempt lost its owned source')
                import unown_imbuement as UNOWN
                if attempt['source'] == UNOWN.SOURCE and attempt.get('paid'):
                    UNOWN.validate_detect_attempt(e,event,index[attempt['actor_id']],attempt)
                if attempt['source']==DETECT and attempt.get('paid'):
                    _validate_detect_attempt(e,event,index[attempt['actor_id']],attempt)
                elif attempt['source'] in PERCEPTIONS and attempt.get('paid'):
                    _validate_perception_attempt(e,event,index[attempt['actor_id']],attempt,completed=True)
                elif attempt.get('window_id'):
                    _paid_request(e,event,attempt,index[attempt['actor_id']],completed=True)
                    plan=attempt['plan'];divisor=3 if attempt['source']==MELEE else 2
                    if attempt['dc']!=divisor*plan['distance'] or (attempt['outcome']=='intercepted')!=(attempt['check_total']>=attempt['dc']):
                        raise ValueError('Intercept result differs from its actual check')
                    if attempt['outcome']=='intercepted' and attempt['source']==MELEE:
                        destination=plan['shove_destination']
                        expected_cells=sorted((destination[0]+x,destination[1]+y) for x,y in plan['ally_body_offsets'])
                        if attempt['push']['moved']!=1 or [tuple(c) for c in attempt['ally_cells_after']]!=expected_cells:
                            raise ValueError('Intercept area membership differs from the actual ally push')
            expected = []
            terminal = next((a for a in state['attempts'] if a['outcome'] in ('intercepted','avoided')),None)
            if state['phase'] == 'cancelled':
                result=row['results'].get(original_id)
                if (state['recipients'] or state['children'] or state['total'] or
                        event.get('continuation_cancelled')!='actor_no_longer_eligible' or
                        result is None or not result['cancelled']):
                    raise ValueError('cancelled defense lacks the native cancellation result')
            elif state['phase'] != 'choices':
                if terminal is None:expected = [{'actor_id':original_id,'hit':True,'intercepted':False}]
                elif terminal['outcome'] == 'avoided':expected = [{'actor_id':original_id,'hit':False,'intercepted':False}]
                else:
                    # The native post-push membership decision is preserved by
                    # its explicit recipient plan and immutable area snapshot.
                    cells={tuple(p) for p in terminal['ally_cells_after']}
                    if cells.intersection(tuple(p) for p in facts['area_cells']):
                        expected.append({'actor_id':original_id,'hit':True,'intercepted':False})
                        if not facts['area_cells']:
                            raise ValueError('second original victim requires actual area geometry')
                    expected.append({'actor_id':terminal['actor_id'],'hit':True,'intercepted':True})
                if state['recipients'] != expected:
                    raise ValueError('recipient plan is not the actual defense outcome')
            if state['phase'] in ('choices','resolving'):
                frame = event.get('continuation')
                if frame is None or ROOT.fingerprint(PASSIVE._continuation_facts(e,event,frame)) != frame['fingerprint']:
                    raise ValueError('waiting defense lost its authenticated continuation')
            owned={uid:r for uid,r in row.get('received',{}).items() if r['event_id']==event['id']}
            if (state['total']!=sum(r['dealt'] for r in owned.values()) or
                    state['children']!={uid:r['child_event'] for uid,r in owned.items()}):
                raise ValueError('defense aggregate differs from actual recipient returns')
            if state['phase']=='complete':
                result=row['results'].get(original_id)
                if (result is None or result['dealt']!=state['total'] or result['cancelled'] or
                        result['hit']!=(any(r['hit'] for r in owned.values()) or
                            any(r['hit'] for r in state.get('prior_results',{}).values())) or
                        any(p['actor_id'] not in row.get('received',{}) and p['actor_id'] not in state.get('prior_results',{})
                            for p in state['recipients'])):
                    raise ValueError('completed defense lacks every actual recipient result')
            for uid,prior in state.get('prior_results',{}).items():
                if (uid==original_id or uid not in row['results'] or prior!=row['results'][uid] or
                        not prior['hit'] or prior['cancelled'] or
                        row['started'].index(uid)>=row['started'].index(original_id) or
                        not any(p['actor_id']==uid for p in state['recipients'])):
                    raise ValueError('earlier recipient alias lacks a previous actual hit')
        for uid,receipt in row.get('received',{}).items():
            event = e._passive_events.get(receipt['event_id'])
            state = row.get('defense',{}).get(receipt['original_id'])
            if (event is None or state is None or state['event_id'] != event['id'] or
                    index.get(uid) is not receipt['actor'] or
                    type(receipt.get('hit_prevented')) is not bool or
                    not any(p['actor_id']==uid and
                        receipt['hit']==(p['hit'] and not receipt['hit_prevented']) and
                        p['intercepted']==receipt['intercepted'] for p in state['recipients'])):
                raise ValueError('received hit lacks authenticated recipient authority')
            child = e._passive_events.get(receipt['child_event'])
            if not child or child.get('defense_parent') != event['id'] or child['target'] is not receipt['actor']:
                raise ValueError('received hit lacks its actual recipient observation')
            if child['phase']=='producer_return_boundary' and (child['dealt']!=receipt['dealt'] or
                    receipt['hit']!=(child['hit'] and not receipt['hit_prevented']) or
                    child['effect_held_count']!=receipt['held']):
                raise ValueError('received result differs from native recipient observation')
            if receipt['hit_prevented'] and (receipt['dealt'] or receipt['held'] or receipt['effects']):
                raise ValueError('prevented hit cannot carry recipient damage or effects')
            returned=row.get('native_returns',{}).get(receipt['child_event'])
            if returned is not None and (returned['fingerprint']!=ROOT.fingerprint(returned['facts']) or
                    returned['facts']['hit_prevented']!=receipt['hit_prevented']):
                raise ValueError('recipient prevention differs from native returned evidence')
    return True
