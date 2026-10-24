"""Native producer event transport with durable per-listener delivery receipts.
Moxie retains its source-specific consequence adapter. Authored policies may
subscribe at observed accuracy or completion; this creates no additional action
grant. Standalone accuracy waits preserve the paid native continuation. Other
source choices and event phases require their own adapters.
"""
from copy import deepcopy
import heavy_injury_adapter as HEAVY

import passive_event_profiles as PROFILES

class PassiveEventPending(RuntimeError):
    def __init__(self,event_id):
        self.event_id=event_id
        super().__init__("unresolved passive event "+event_id)

def initialize(e):
    e._passive_sequence=0
    e._passive_listeners={}
    e._passive_events={}
    e._passive_receipts={}
    e._passive_pending=None
    e._passive_driver_result=None

def ensure_clear(e):
    import dynamic_chain_moves as CHAIN
    CHAIN.ensure_clear(e)
    import captured_momentum as MOMENTUM
    MOMENTUM.ensure_clear(e)
    pending = getattr(e, "_passive_pending", None)
    if pending is not None:
        raise PassiveEventPending(pending)

def register(e,owner,selected_id):
    import ability_native_actions as NATIVE
    if NATIVE.register(e,owner,selected_id):return True
    profile=PROFILES.register_profile(e,selected_id)
    if profile is None:return False
    e._passive_listeners.setdefault(owner,{})[selected_id]=profile
    return True

EVENT_FIELDS={'hit','critical','natural_roll','real_hp_loss','temp_hp_loss','move_id','move_class','round','elapsed_seconds'}


def subscribe_policy(e,owner,subscription_id,document,*,event='move_resolved',inputs=None):
    """Application-authorized listener; only native producers create occurrences."""
    import world_entities as W
    import source_policy as POLICY
    W.require_actors(e,owner,owner)
    if type(subscription_id) is not str or not subscription_id.strip() or event not in ('move_resolved','accuracy_resolved'):
        raise ValueError('explicit subscription identity and supported native event required')
    inputs={} if inputs is None else inputs
    if type(inputs) is not dict or any(type(k) is not str or not k or v not in EVENT_FIELDS for k,v in inputs.items()):
        raise ValueError('event inputs require known native observation fields')
    if event=='accuracy_resolved' and any(v in ('real_hp_loss','temp_hp_loss') for v in inputs.values()):
        raise ValueError('damage observations do not exist at accuracy boundary')
    POLICY.resolve(e.r,document)  # Admission validates sources/schema; missing inputs may remain pending.
    for row in document['variants']:
        contexts={k for k,v in row['inputs'].items() if v['authority']=='context'}
        if contexts!=set(inputs):raise ValueError('all context inputs must bind to native event observations')
    key='authored:'+subscription_id
    profile={'kind':'authored_policy','event':event,'document':deepcopy(document),'inputs':dict(inputs)}
    listeners=e._passive_listeners.setdefault(owner,{})
    if key in listeners and listeners[key]!=profile:raise ValueError('subscription identity already has another definition')
    listeners[key]=profile
    return key


def _deliver_policy(e,ev,key,profile):
    import source_policy as POLICY
    if ev.get('listener_profiles',{}).get(key)!=profile:
        return 'pending','subscription_definition_changed'
    if ev.get('effect_held_count',0):return 'pending','producer_effects_unresolved'
    if ev['actor'].fainted or ev['actor'].dead:return 'inapplicable','owner_no_longer_eligible'
    context={name:ev[field] for name,field in profile['inputs'].items()}
    try:
        result=POLICY.execute_effects(e,ev['actor'],ev['target'],profile['document'],
            context=context,decisions=(ev.get('source_choice') or {}).get(key,{}),
            request_id=ev['id']+':'+key)
    except POLICY.PolicyExecutionPending:return 'pending','listener_effects_unresolved'
    ev.setdefault('outcomes',{}).setdefault(key,{})['resolution']=deepcopy(result)
    status=result['status']
    if status=='PolicyEffectsCompleted':return 'applied',result['execution_id']
    if status=='PolicyNotApplicable':return 'inapplicable','declared_condition_false'
    return 'pending',status


def _continuation_facts(e,ev,frame):
    import world_entities as W
    args=frame['args']
    W.require_actors(e,args['attacker'],args['target'])
    if args['attacker'] is not ev['actor'] or args['target'] is not ev['target'] or args['passive_event']!=ev['id']:
        raise ValueError('native continuation participant mismatch')
    for scope in frame['scopes']:
        W.require_actors(e,scope['actor'],scope['target'])
    if frame['scopes'] and (frame['scopes'][-1]['actor'] is not args['attacker'] or frame['scopes'][-1]['target'] is not args['target']):
        raise ValueError('native effect contribution scope changed')
    precision=args['precision_event']
    if precision is not None and not any(row is precision for row in e._precision_events):
        raise ValueError('native precision observation identity changed')
    standard=args['standard_context']
    if standard is not None:
        receipt=e._heavy_standard_receipts.get(standard)
        if receipt is None or receipt['actor'] is not args['attacker']:
            raise ValueError('native Standard receipt changed')
    facts={k:v for k,v in args.items() if k not in ('attacker','target','standard_context','precision_event')}
    facts['clock']={'round':e.round_no,'elapsed_seconds':e.elapsed_seconds}
    facts['profile']={'name':e.r.ruleset.name,'profile':e.r.ruleset.profile,
                      'choices':e.r.ruleset.variant_choices,'versions':e.r.ruleset.unit_versions}
    facts.update(actor_id=args['attacker'].entity_id,target_id=args['target'].entity_id,
                 observations=observations(e,ev['id']),listener_profiles=ev['listener_profiles'])
    # Preserve native next-use contribution data independently of live stack refs.
    facts['contributions']=[{k:v for k,v in scope.items() if k not in ('actor','target')}
                            for scope in frame['scopes']]
    if frame.get('kind')=='recipient_return':
        import action_lifecycle as ACTION
        action=ACTION.move_frame(e,e._move_completions[args['completion_id']])
        facts['native_action']=None if action is None else {k:action[k] for k in ('actor','source','kind','id')}
        standard_event=args.get('completed_standard_event')
        if standard_event is not None and e._heavy_events[standard_event]['status']!='applied':
            raise ValueError('native recipient Standard has not returned')
        result=frame['result']
        facts['recipient_return']={k:v for k,v in result.items() if k!='effects'}
        facts['recipient_effects']=[]
        for token in result['effects']:
            effect=e._effect_dispatch_receipts[token]
            facts['recipient_effects'].append({k:effect[k] for k in
                ('source_id','occurrence','fingerprint','actor','target')})
    def identity_data(value):
        if hasattr(value,'entity_id') and getattr(value,'r',None) is e.r:
            W.require_actors(e,value,value)
            return {'native_actor_id':value.entity_id}
        if isinstance(value,dict):return {k:identity_data(v) for k,v in value.items()}
        if isinstance(value,(tuple,list)):return [identity_data(v) for v in value]
        if isinstance(value,(set,frozenset)):
            import root_resolution as ROOT
            return sorted((identity_data(v) for v in value),key=ROOT.canonical)
        return value
    return identity_data(facts)


def after_recipient(e,args,result):
    """Retain the actual applied hit while its listeners await source input."""
    event_id=args['passive_event']
    frame={'kind':'recipient_return','args':args,'result':result,
           'scopes':list(getattr(e,'_event_use_scopes',()))}
    if event_id is not None:e._passive_events[event_id]['continuation']=frame
    complete(e,event_id,hit=args['hit'],natural=args['nat'],critical=args['crit'],
             dealt=result['dealt'],held=result['held'])
    return _finish_recipient_return(e,frame)


def _finish_recipient_return(e,frame):
    """Run only the producer tail; damage, effects and payment already happened."""
    import move_completion as COMPLETE, reactive_ability_events as REACTIVE
    args=frame['args'];result=frame['result'];event_id=args['passive_event']
    if event_id is not None:
        ev=e._passive_events[event_id]
        from root_resolution import fingerprint
        if (ev.get('return_fingerprint')!=frame.get('fingerprint') or
                fingerprint(_continuation_facts(e,ev,frame))!=frame.get('fingerprint')):
            raise ValueError('native recipient return continuation changed')
        if e._ruleset_move(args['attacker'],args['move_id'])!=args['move_id']:
            raise ValueError('selected move changed during recipient wait')
        if ev['status'] not in ('applied','inapplicable'):
            raise ValueError('native recipient listeners have not returned')
        import move_defense_reactions as DEFENSE
        row=e._move_completions[args['completion_id']]
        if ('target_moves' in row and
                DEFENSE._move_facts(COMPLETE.event_move(e,ev))!=DEFENSE._move_facts(args['move'])):
            raise ValueError('native recipient prepared Move changed')
    COMPLETE.finish_target(e,args['completion_id'],args['attacker'],args['target'],
        hit=result['hit'],dealt=result['dealt'],effects=result['effects'])
    REACTIVE.resolved_hit(e,args['attacker'],args['target'],args['move'],args['completion_id'],
        hit_prevented=result['hit_prevented'])
    COMPLETE.record_return(e,event_id,hit_prevented=result['hit_prevented'])
    if event_id is not None:e._passive_events[event_id].pop('continuation')
    return result['dealt']


def _resume_recipient_return(e,event):
    """Resume inside the existing reactive transaction and contribution scope."""
    import reactive_ability_events as REACTIVE
    def finish(staged,actor,target):
        frame=staged._passive_events[event['id']]['continuation']
        previous=getattr(staged,'_event_use_scopes',None)
        staged._event_use_scopes=frame['scopes']
        try:return _finish_recipient_return(staged,frame)
        finally:
            if previous is None:del staged._event_use_scopes
            else:staged._event_use_scopes=previous
    return REACTIVE.atomic_move(e,event['actor'],event['target'],finish)


def preflight_continuation(e,actor,*,ordinary_single):
    if not any(p.get('event')=='accuracy_resolved' for p in e._passive_listeners.get(actor,{}).values()):return
    if not ordinary_single or len(getattr(e,'_event_use_scopes',()))>1:
        raise ValueError('intermediate listener requires a standalone native move continuation')


def after_accuracy(e,**args):
    """Native producer continuation checkpoint, after payment and accuracy."""
    event_id=args['passive_event']
    ev=e._passive_events.get(event_id)
    import move_defense_reactions as DEFENSE
    if ev is not None:
        ev.update(hit=args['hit'],natural_roll=args['nat'],critical=args['crit'])
    import ability_interrupt_choices as ABILITY_INTERRUPTS
    if ev is None or not (DEFENSE.wants_boundary(ev) or ABILITY_INTERRUPTS.wants_boundary(ev) or any(p.get('event')=='accuracy_resolved' for p in ev['listener_profiles'].values())):
        return e._finish_move_resolution(**args)
    from root_resolution import fingerprint as request_fingerprint
    frame={'args':args,'scopes':list(getattr(e,'_event_use_scopes',()))}
    frame['fingerprint']=request_fingerprint(_continuation_facts(e,ev,frame))
    ev['continuation']=frame
    ev.update(phase='accuracy_boundary',hit=args['hit'],natural_roll=args['nat'],critical=args['crit'])
    DEFENSE.begin_boundary(e,ev,args)
    return deliver(e,event_id)


def _deliver_accuracy(e,event_id):
    from root_resolution import fingerprint as request_fingerprint
    ev=e._passive_events[event_id];frame=ev.get('continuation')
    if frame is None or request_fingerprint(_continuation_facts(e,ev,frame))!=frame['fingerprint']:
        raise ValueError('native continuation changed')
    for key,profile in ev['listener_profiles'].items():
        if profile.get('event')!='accuracy_resolved':continue
        receipt=(ev['actor'],key,ev['activation_id'])
        if receipt in e._passive_receipts:continue
        current=e._passive_listeners.get(ev['actor'],{}).get(key)
        if current!=profile:return _pending(e,ev,'subscription_definition_changed')
        status,reason=_deliver_policy(e,ev,key,profile)
        if status=='pending':return _pending(e,ev,reason)
        ev.setdefault('outcomes',{}).setdefault(key,{}).update(status=status,reason=reason,source_action_created=False)
        e._passive_receipts[receipt]={'event_id':event_id,'outcome':status}
    args=frame['args']
    if e._ruleset_move(args['attacker'],args['move_id'])!=args['move_id']:
        raise ValueError('selected move changed during reaction wait')
    # Drop the checkpoint before completion seals the final producer evidence.
    # The surrounding transaction restores it if the continuation fails.
    import move_defense_reactions as DEFENSE
    import ability_interrupt_choices as ABILITY_INTERRUPTS
    cancelled=(ev['actor'].fainted or ev['actor'].dead) and DEFENSE.cancel_waiting(e,ev)
    if cancelled:ABILITY_INTERRUPTS.cancel_waiting(e,ev)
    if not cancelled:
        DEFENSE.deliver_boundary(e,ev)
        ABILITY_INTERRUPTS.deliver_boundary(e,ev,frame['args'])
    if cancelled or not DEFENSE.routed(e,event_id):
        del ev['continuation'];ev['phase']='activated'
    ev.pop('reason',None)
    previous=getattr(e,'_event_use_scopes',None)
    e._event_use_scopes=frame['scopes']
    try:
        if cancelled:
            ev['continuation_cancelled']='actor_no_longer_eligible'
            complete(e,event_id,hit=args['hit'],natural=args['nat'],critical=args['crit'],dealt=0)
            import move_completion as COMPLETE
            COMPLETE.finish_target(e,args.get('completion_id'),args['attacker'],args['target'],
                                   hit=args['hit'],dealt=0,cancelled=True)
            return 0
        return e._finish_move_resolution(**args)
    finally:
        if previous is None:del e._event_use_scopes
        else:e._event_use_scopes=previous


STAGE_FIELDS={
    'attempt':{'move_id'},
    'accuracy':{'hit','natural_roll','critical'},
    'damage_request':{'amount'},
    'hp_loss':{'real_hp_loss','temp_hp_loss','damage_basis'},
    'resolved':{'effect_held_count'},
}
STAGE_NEXT={None:{'attempt'},'attempt':{'accuracy'},
            'accuracy':{'damage_request','resolved'},'damage_request':{'hp_loss'},
            'hp_loss':{'resolved'},'resolved':set()}


def observations(e,event_id):
    """Detached ordered producer facts, never reaction/execution authority."""
    from resolution_transaction import request_fingerprint
    ev=e._passive_events.get(event_id)
    if ev is None:raise ValueError('no actual source event')
    rows=ev.get('observations',[])
    previous=None;stage=None
    for index,row in enumerate(rows):
        if type(row) is not dict or set(row)!={'index','stage','producer','facts','previous','fingerprint'}:
            raise ValueError('invalid event observation shape')
        current=row['stage']
        if current not in STAGE_NEXT.get(stage,set()) or row['index']!=index or row['previous']!=previous:
            raise ValueError('event observation order changed')
        if type(row['facts']) is not dict or set(row['facts'])!=STAGE_FIELDS[current]:
            raise ValueError('event observation fields changed')
        payload={key:value for key,value in row.items() if key!='fingerprint'}
        if request_fingerprint(payload)!=row['fingerprint']:raise ValueError('event observation changed')
        previous=row['fingerprint'];stage=current
    return deepcopy(rows)


def _observe(e,event_id,stage,facts,producer):
    if event_id is None:return
    from resolution_transaction import request_fingerprint
    ev=e._passive_events[event_id]
    if ev['phase']!='activated':raise ValueError('producer event observations already closed')
    rows=observations(e,event_id)
    last=rows[-1] if rows else None
    if stage not in STAGE_NEXT.get(last['stage'] if last else None,set()) or set(facts)!=STAGE_FIELDS[stage]:
        raise ValueError('invalid native event stage transition')
    row={'index':len(rows),'stage':stage,'producer':producer,'facts':deepcopy(facts),
         'previous':last['fingerprint'] if last else None}
    row['fingerprint']=request_fingerprint(row)
    ev.setdefault('observations',[]).append(row)


def note_accuracy(e,event_id,hit,natural,critical):
    if type(hit) is not bool or type(critical) is not bool or (natural is not None and type(natural) is not int):
        raise ValueError('actual typed accuracy result required')
    _observe(e,event_id,'accuracy',{'hit':hit,'natural_roll':natural,'critical':critical},'Engine.use_move/accuracy')


def note_damage_request(e,event_id,amount):
    if event_id is None:return
    if type(amount) is not int or amount<0:raise ValueError('actual nonnegative damage request required')
    import ice_lake as ICE_LAKE
    ICE_LAKE.before_damage(e,event_id)
    _observe(e,event_id,'damage_request',{'amount':amount},'Engine.resolve_attack_damage')


def capture(c):
    return dict(hp=c.hp,temp_hp=c.temp_hp,fainted=c.fainted,dead=c.dead,injuries=c.injuries,abilities_suppressed=c.abilities_suppressed)

def interested(e,actor):
    return bool(e._passive_listeners.get(actor,{}))

def begin(e,actor,target,move,*,ordinary_single,move_mechanics=None,completion_id=None):
    """Called only inside use_move after real activation; not a public trigger assertion."""
    import move_defense_reactions as DEFENSE
    import ability_interrupt_choices as ABILITY_INTERRUPTS
    import ability_reaction_choices as ABILITY_REACTIONS
    import mindlock as MINDLOCK
    warning_interested=MINDLOCK.warning_interested(e)
    import ice_lake as ICE_LAKE
    import gleeful_interference as GLEEFUL
    import style_expert as STYLE
    import roughneck as ROUGHNECK,endure as ENDURE
    if not __import__('type_ace').close_quarters_interested(e,actor,move) and not ROUGHNECK.owns(actor,ROUGHNECK.CLASS) and ENDURE.known(e,target) is None and not GLEEFUL.interested(e,actor,move) and not ICE_LAKE.interested(e) and not ABILITY_REACTIONS.interested(e) and not interested(e,actor) and not ABILITY_INTERRUPTS.interested(e) and not DEFENSE.watch_interested(target,move) and not warning_interested and not STYLE.reaction_interested(e,target):
        return None
    e._passive_sequence+=1
    uid="passive-move-"+str(e._passive_sequence)
    ev=dict(id=uid,activation_id=uid,producer="Engine.use_move",phase="activated",
            actor=actor,target=target,source_ids=list(e._passive_listeners.get(actor,{})),move_id=move["id"],
            move_class=move["class"],ordinary_single=ordinary_single,
            mechanics_scope_supported=not bool(move_mechanics),
            hit=None,natural_roll=None,critical=None,dealt=None,
            raw_damage=None,resolved_damage=None,real_hp_loss=None,temp_hp_loss=None,
            dealt_basis="legacy_resolve_attack_damage_return_before_take_damage_cap",
            damage_basis="unknown_until_direct_primitive_observed",
            attack_observation=None,target_before=capture(target),
            owner_before=capture(actor),round=e.round_no,elapsed_seconds=e.elapsed_seconds,
            status="in_progress",source_choice=None)
    ev['completion_id']=completion_id
    # The capability at the real attack occurrence controls Warning. Preserve
    # it in this existing signed event rather than rereading a later holder.
    if warning_interested:ev[MINDLOCK.ATTACK_FACT]=MINDLOCK.attack_immunity(e,actor)
    ev['listener_profiles']=deepcopy(e._passive_listeners.get(actor,{}))
    e._passive_events[uid]=ev
    ICE_LAKE.watch_attack(e,ev)
    _observe(e,uid,'attempt',{'move_id':move['id']},'Engine.use_move/activated')
    DEFENSE.bind_event(e,ev,move,completion_id)
    ABILITY_INTERRUPTS.bind_event(e,ev,move,completion_id)
    ABILITY_REACTIONS.bind_event(e,ev)
    return uid

def note_attack(e,event_id,before,after,damage_request):
    if event_id is None:return
    ev=e._passive_events[event_id]
    if ev["phase"]!="activated":raise ValueError("attack observation already closed")
    ev["attack_observation"]=dict(before=before,after=after,damage_request=damage_request,
                                  producer="Engine.resolve_attack_damage/HEAVY.apply_attack_damage")
    import ice_lake as ICE_LAKE
    ICE_LAKE.note_injury(e,event_id,after['injuries']-before['injuries'])
    # Heavy HP loss can share that primitive. Do not relabel combined loss as damage.
    if before["injuries"]<5 and after["injuries"]<5:
        ev["real_hp_loss"]=before["hp"]-after["hp"]
        ev["temp_hp_loss"]=before["temp_hp"]-after["temp_hp"]
        ev["damage_basis"]="direct_attack_primitive_resource_delta"
    else:
        ev["damage_basis"]="attack_and_heavy_interaction_amount_unresolved"
    _observe(e,event_id,'hp_loss',{key:ev[key] for key in STAGE_FIELDS['hp_loss']},
             'Engine.resolve_attack_damage/HEAVY.apply_attack_damage')


def begin_recipient(e,parent,target,*,hit,token):
    """Observe an actual routed recipient without another activation or roll."""
    import move_defense_reactions as DEFENSE
    import world_entities as WORLD
    frame=parent['continuation']; args=frame['args']
    DEFENSE.require_recipient(e,token,parent['actor'],target,args['move'],parent['completion_id'])
    e._passive_sequence+=1
    uid='passive-move-'+str(e._passive_sequence)
    memo={id(actor):actor for actor in WORLD.actor_index(e).values()}
    ev=deepcopy({key:value for key,value in parent.items() if key not in (
        'continuation','defense_watch','observations','intent_fingerprint','reason','outcomes','source_choice',
        'ability_interrupt_watch','ability_interrupts','gleeful_interference')},memo)
    profiles={key:value for key,value in parent['listener_profiles'].items() if value.get('event')!='accuracy_resolved'}
    ev.update(id=uid,activation_id=uid,target=target,producer='Engine.use_move/defense-recipient',
        phase='activated',status='in_progress',source_ids=list(profiles),listener_profiles=deepcopy(profiles),
        target_before=capture(target),owner_before=capture(parent['actor']),
        hit=None,natural_roll=None,critical=None,dealt=None,raw_damage=None,resolved_damage=None,
        real_hp_loss=None,temp_hp_loss=None,attack_observation=None,source_choice=None,
        defense_parent=parent['id'],defense_token=token)
    e._passive_events[uid]=ev
    import ice_lake as ICE_LAKE
    ICE_LAKE.watch_attack(e,ev)
    _observe(e,uid,'attempt',{'move_id':ev['move_id']},'Engine.use_move/defense-recipient')
    note_accuracy(e,uid,hit,args['nat'],args['crit'])
    return ev

def _bind_intent(e, ev):
    """Seal producer observations; live eligibility may change during a wait."""
    import world_entities as W
    from resolution_transaction import bind_request_intent
    W.require_actors(e, ev['actor'], ev['target'])
    mutable = {'actor', 'target', 'status', 'reason', 'outcomes', 'source_choice', 'continuation',
               'intent_fingerprint'}
    intent = {key:value for key,value in ev.items() if key not in mutable}
    intent.update(actor_id=W.actor_id(ev['actor']), target_id=W.actor_id(ev['target']))
    bind_request_intent(ev, intent)


def complete(e,event_id,*,hit,natural,critical,dealt,held=0):
    if event_id is None:return
    ev=e._passive_events[event_id]
    if ev["phase"]!="activated":raise ValueError("event completion already recorded")
    accuracy=next((row['facts'] for row in observations(e,event_id) if row['stage']=='accuracy'),None)
    if accuracy!={'hit':hit,'natural_roll':natural,'critical':critical}:
        raise ValueError('completion disagrees with actual accuracy observation')
    _observe(e,event_id,'resolved',{'effect_held_count':held},'Engine.use_move/return')
    ev.update(phase="producer_return_boundary",effect_held_count=held,hit=hit,natural_roll=natural,critical=critical,
              dealt=dealt,target_after=capture(ev["target"]),owner_after=capture(ev["actor"]),status="observed")
    frame=ev.get('continuation')
    if frame is not None and frame.get('kind')=='recipient_return':
        from root_resolution import fingerprint
        frame['fingerprint']=fingerprint(_continuation_facts(e,ev,frame))
        ev['return_fingerprint']=frame['fingerprint']
    _bind_intent(e,ev)
    # Listener delivery occurs inside the producer, before finish_target and
    # record_return. Only its caller can resume a suspended activation after
    # the producer has returned its numeric result.
    deliver(e,event_id,_resume_activation=False)

def _pending(e,ev,reason):
    ev.update(status="pending",reason=reason)
    e._passive_pending=ev["id"]
    raise PassiveEventPending(ev["id"])

def deliver(e,event_id,*,_resume_activation=True):
    """Atomically deliver or retry one actual event; preserve completed prefixes."""
    import state_grants as G
    HEAVY.ensure_clear(e)
    ev=e._passive_events.get(event_id)
    if ev is None:raise ValueError('no actual source event')
    if e._passive_pending not in (None,event_id):
        raise PassiveEventPending(e._passive_pending)
    def attempt(staged,actor):
        # Retrying re-evaluates real source eligibility; it does not accept a
        # caller assertion that an unsupported choice has become implemented.
        if staged._passive_pending==event_id:staged._passive_pending=None
        try:
            event=staged._passive_events[event_id]
            import pass_moves as PASS, action_lifecycle as ACTION, move_completion as COMPLETE
            COMPLETE.validate_return_continuation(staged,event)
            with ACTION.resume_move(staged,event,enabled=_resume_activation), PASS.restored_scope(staged,event):
                if event['phase']=='accuracy_boundary':
                    result=_deliver_accuracy(staged,event_id)
                else:
                    result=_deliver(staged,event_id)
                    frame=event.get('continuation')
                    if _resume_activation and frame is not None and frame.get('kind')=='recipient_return':
                        native_result=_resume_recipient_return(staged,event)
                        completion=staged._move_completions[event['completion_id']]
                        if completion.get('activation_continuation'):result=native_result
                parent=event.get('defense_parent')
                if parent and staged._passive_events[parent]['phase']=='accuracy_boundary' and not getattr(staged,'_defense_finishing',False):
                    result=_deliver_accuracy(staged,parent)
                    event=staged._passive_events[parent]
                if _resume_activation and not getattr(staged,'_defense_finishing',False):
                    import move_activation as ACTIVATION
                    result=ACTIVATION.resume_after_event(staged,event,result)
            if _resume_activation:
                result=__import__('combat_move_reactions').resume_after_event(staged,event,result)
            return result
        except PassiveEventPending as pending:
            if staged._passive_pending!=pending.event_id or pending.event_id not in staged._passive_events:raise
            return None
    result=G.transition(e,ev['actor'],attempt,include_grid=e.grid is not None,include_rulings=True)
    if e._passive_pending is not None:raise PassiveEventPending(e._passive_pending)
    return result


def _deliver(e,event_id):
    """Internal staged delivery; effects and their receipts share one commit."""
    HEAVY.ensure_clear(e)
    ev=e._passive_events.get(event_id)
    if ev is None:raise ValueError("no actual source event")
    if ev["phase"]!="producer_return_boundary":raise ValueError("source event is incomplete")
    if e._passive_pending is not None:raise PassiveEventPending(e._passive_pending)
    observations(e,event_id)
    _bind_intent(e,ev)
    outcomes=ev.setdefault("outcomes",{})
    newly_delivered=False
    for rule_id in (() if ev.get("defense_routed") else ev["source_ids"]):
        key=(ev["actor"],rule_id,ev["activation_id"])
        if key in e._passive_receipts:continue
        if rule_id not in e._passive_listeners.get(ev["actor"],{}):
            return _pending(e,ev,"source_listener_no_longer_registered")
        profile=e._passive_listeners[ev['actor']][rule_id]
        if profile.get('kind')=='authored_policy':
            status,reason=_deliver_policy(e,ev,rule_id,profile)
            outcome=dict(outcomes.get(rule_id,{}),status=status,reason=reason,source_action_created=False)
            if status=='pending':
                outcomes[rule_id]=outcome
                return _pending(e,ev,reason)
            outcomes[rule_id]=outcome
            e._passive_receipts[key]={'event_id':event_id,'outcome':status}
            newly_delivered=True
            continue
        status,reason=PROFILES.eligibility(e,ev,rule_id)
        if status=="pending":return _pending(e,ev,reason)
        outcome=dict(status=status,reason=reason)
        import cheerleader as CHEER
        cheer_snapshot=CHEER.support_snapshot(e,ev["actor"]) if status=="eligible" else None
        if status=="eligible":
            outcome.update(status="applied",effect=PROFILES.apply(e,ev,rule_id),source_action_created=False)
        outcomes[rule_id]=outcome
        e._passive_receipts[key]={"event_id":event_id,"outcome":outcome["status"]}
        if cheer_snapshot is not None:
            CHEER.support(e,cheer_snapshot,[ev['actor']],{'kind':'passive_ability','source':rule_id,'event_id':event_id})
        newly_delivered=True
    ev["status"]="applied" if any(x["status"]=="applied" for x in outcomes.values()) else "inapplicable"
    return ev["status"] if newly_delivered else "already_delivered"

def choose(e,event_id,owner,source_rule,choice):
    """Bind authored decisions; native choices still require their own adapter."""
    ev=e._passive_events.get(event_id)
    if ev is None or ev["actor"] is not owner or source_rule not in ev["source_ids"]:
        raise ValueError("choice scope does not identify an actual owned source event")
    profile=e._passive_listeners.get(owner,{}).get(source_rule,{})
    if profile.get('kind')=='authored_policy':
        if type(choice) is not dict or set(choice)!={'decisions'} or type(choice['decisions']) is not dict:
            raise ValueError('authored listener choice accepts explicit decisions only')
        if (owner,source_rule,ev['activation_id']) in e._passive_receipts:
            raise ValueError('listener already delivered')
        import state_grants as G
        def apply(staged,actor):
            event=staged._passive_events[event_id]
            decisions=dict(event.get('source_choice') or {})
            decisions[source_rule]=deepcopy(choice['decisions']);event['source_choice']=decisions
            try:return deliver(staged,event_id)
            except PassiveEventPending as pending:
                if staged._passive_pending!=pending.event_id or pending.event_id not in staged._passive_events:raise
                return None
        result=G.transition(e,owner,apply,include_grid=e.grid is not None,include_rulings=True)
        if e._passive_pending is not None:raise PassiveEventPending(e._passive_pending)
        return result
    return {"status":"pending","reason":"source_choice_adapter_not_implemented",
            "event_id":event_id,"choice_applied":False}

def report_driver_pending(e,pending):
    e._passive_driver_result={"status":"incomplete","event_id":pending.event_id,
        "continuation_reified":bool(e._passive_events.get(pending.event_id,{}).get("continuation")),"automatic_resume":False}
    e.log("[수동 판단 필요] passive event "+pending.event_id+"; 전투 미완료", "common/passive-event")
