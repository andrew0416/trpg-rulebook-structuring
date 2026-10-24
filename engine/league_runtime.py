"""Restricted actual League driver; no-action trainers, native Struggle Pokemon.
Source ordering ch07:21,27-28,74; no-action example110. Runtime subset only.
"""
from contextlib import contextmanager
import copy
import initiative as INIT
import league_agenda as A
import heavy_injury_adapter as H

class LeaguePending(RuntimeError):pass

def check_boundary(e,operation):
 s=getattr(e,'_league_runtime',None)
 if s is None:return
 if s['pending']:raise LeaguePending(s['pending']['reason'])
 if not getattr(e,'_league_dispatch',False):
  raise ValueError('League driver owns '+operation+' while attached')

def check_action(e,actor,target,move_id):
 s=getattr(e,'_league_runtime',None)
 if s is None:return
 if s['pending']:raise LeaguePending(s['pending']['reason'])
 allowed=s.get('executing_intent')
 if (not getattr(e,'_league_dispatch',False) or allowed is None
     or allowed['kind']!='use_move' or s['actors'][allowed['actor_id']] is not actor
     or s['actors'][allowed['target_id']] is not target or allowed['move_id']!=move_id):
  raise ValueError('action does not match active League intent')

@contextmanager
def _dispatch(e):
 old=getattr(e,'_league_dispatch',False);e._league_dispatch=True
 try:yield
 finally:e._league_dispatch=old

def _able(c):
 return not c.dead and not c.fainted and c.on_field and not c.captured

def _observation(e,actors):
 out={}
 for key,c in actors.items():
  value=INIT.value(e.r,c,engine=e)
  if value.unresolved or type(value.value) is not int:
   raise ValueError('initiative derivation unresolved: '+key)
  out[key]={'initiative':value.value,'able':_able(c),
            'availability':(c.dead,c.fainted,c.on_field,c.captured)}
 return out

def _interaction_issues(e,actors):
 issues=[]
 for field in ('weather','field','grid','zones','zone_cells','_smoke_regions','hazards','hazards_nogrid',
               'delayed','zone_rules','taunt','condition_params','_action_grants'):
  if getattr(e,field,None):issues.append('unsupported interaction: '+field)
 for field in ('formulas','mech','effects','situational','answers','provider'):
  value=getattr(e.rulings,field,None)
  if field=='answers':value=[row for row in value if row['key']!='initiative_tie_order']
  if value:issues.append('unsupported ruling: '+field)
 if any(e.rulings.hooks.values()):issues.append('unsupported ruling hooks')
 for key,c in actors.items():
  if c.dead or c.captured or not c.on_field:issues.append(key+':dead/captured/withdrawn roster outside current lifecycle subset')
  if c.hp<=0 and not c.fainted and not __import__('taskmaster').conscious(c):issues.append(key+':HP requires consistent faint state')
  for field in ('registry','ability_triggers','modifiers','abilities','custom_conditions',
                'buffs','coats','blessings','item','shield','next_attack','reflect','setup_move',
                'locked_move','form','form_rule','damage_cap','type_override_next','pending_action_loss'):
   value=getattr(c,field,None)
   if field=='custom_conditions' and isinstance(value,dict):
    # The native owner-turn clock is bookkeeping, not an optional phase effect.
    serial=value.get('combat_turn_serial',0)
    if type(serial)is not int or serial<0:issues.append(key+':invalid owner turn clock')
    marker=value.get('blessing_ignore_turn_open')
    if 'blessing_ignore_turn_open' in value and (marker is not True or e._active_turn_actor is not c):
     issues.append(key+':invalid native open-turn marker')
    value={k:v for k,v in value.items() if k not in ('combat_turn_serial','blessing_ignore_turn_open')}
   if value:issues.append(key+':unsupported '+field)
  if c.conditions-{'기절'}:issues.append(key+':turn hook/status phase composition unsupported')
 return issues

def _hold(e,reason,*,category='runtime_scope_pending',evidence=None):
 s=e._league_runtime
 s['pending']={'reason':reason,'category':category,'evidence':evidence}
 s['agenda']=A.hold(s['agenda'],reason,str(evidence or category))
 return status(e)

def _roster_matches(e):
 roster=list(e._league_runtime['actors'].values())
 expected={id(c) for c in roster}
 return all(len(current)==len(roster) and {id(c) for c in current}==expected
            for current in (getattr(e,'everyone',[]),e.gm.everyone))

def _check(e):
 s=e._league_runtime
 if s['pending']:raise LeaguePending(s['pending']['reason'])
 if e._heavy_pending:
  return _hold(e,'unresolved heavy event',category='engine_effect_pending',evidence=e._heavy_pending)
 if not _roster_matches(e):
  return _hold(e,'roster changed; fixed-roster runtime subset cannot continue')
 try:now=_observation(e,s['actors'])
 except ValueError as ex:return _hold(e,str(ex))
 if now!=s['baseline']:
  return _hold(e,'initiative or availability changed',evidence={'before':s['baseline'],'after':now})
 issues=_interaction_issues(e,s['actors'])
 if issues:return _hold(e,'interaction outside supported phase placement',evidence=issues)
 if e.round_no!=s['round_no'] or e.round_start_seconds!=s['round_start']:
  return _hold(e,'Engine round boundary drift')
 return None

def _intent(raw,actor_id,trainer):
 if type(raw) is not dict or raw.get('kind') not in ('no_action','use_move'):
  raise ValueError('typed no_action/use_move intent required')
 allowed={'kind'} if raw['kind']=='no_action' else {'kind','move_id','target_id','set_damage'}
 if set(raw)!=allowed:raise ValueError('intent fields must match supported shape')
 if raw['kind']=='use_move':
  if type(raw['move_id']) is not str or type(raw['target_id']) is not str or type(raw['set_damage']) is not bool:
   raise ValueError('move intent requires string identities and boolean set_damage')
 result=copy.deepcopy(raw);result['actor_id']=actor_id
 return result

def start(e,pairs,*,mode):
 """Select explicit League mode. Pairs are caller eligibility/controller bindings."""
 if mode!='league':raise ValueError('explicit League mode required')
 if getattr(e,'_league_runtime',None) is not None:raise ValueError('League driver already attached')
 if e.round_start_seconds is not None or e._active_turn_actor is not None:raise ValueError('League start requires no open round/turn')
 H.ensure_clear(e)
 actors={};bindings=[]
 for player,trainer,pokemon in pairs:
  if type(player) is not str or not player or trainer.kind!='trainer' or pokemon.kind!='pokemon':
   raise ValueError('player text and trainer/Pokemon roles required')
  for role,c in [('trainer',trainer),('pokemon',pokemon)]:
   key=player+':'+role
   if key in actors or c in actors.values():raise ValueError('duplicate participant identity')
   actors[key]=c;bindings.append((player,role,key))
 if not actors:raise ValueError('nonempty supplied League roster required')
 e._league_runtime=None
 return _start_round(e,actors,tuple(bindings))

def _start_round(e,actors,bindings,encounter_id=None):
 import league_consequences as OUTCOME
 OUTCOME.source(e)
 baseline=_observation(e,actors)
 participants=tuple(A.Participant(key,player,A.Role(role),baseline[key]['initiative'],baseline[key]['able']) for player,role,key in bindings)
 agenda=A.create('round:'+str(e.round_no+1),participants)
 s={'actors':actors,'bindings':bindings,'baseline':baseline,'agenda':agenda,
    'intents':{},'close_receipts':[],'pending':None,'completed':False,
    'round_no':e.round_no+1,'round_start':e.elapsed_seconds,
    'executing_intent':None,'source_phase_claim':'resolution hook placement is restricted engineering integration'}
 e._league_runtime=s
 s['encounter_id']=encounter_id if encounter_id is not None else OUTCOME.begin(e,actors,bindings)
 if any(reason!='initiative tie requires separate interpretation' for reason in agenda.pending):
  return _hold(e,'participant profile unsupported',evidence=agenda.pending)
 issues=_interaction_issues(e,actors)
 if issues:return _hold(e,'interaction outside supported phase placement',evidence=issues)
 e.everyone=e.gm.everyone=list(actors.values())
 import initiative_schedule as SCHEDULE
 common=SCHEDULE.prepare(e,list(actors.values()),source='gm/league-runtime-phase-layout',
    bindings=[{'slot':key,'actor_id':actors[key].entity_id,'role':role} for player,role,key in bindings],
    layout=[{'id':A.Phase.DECLARE.value,'roles':['trainer'],'reverse':True,'declaration':True},
            {'id':A.Phase.TRAINERS.value,'roles':['trainer'],'reverse':False,'declaration':False},
            {'id':A.Phase.POKEMON.value,'roles':['pokemon'],'reverse':False,'declaration':False}],
    order_groups=[['trainer'],['pokemon']])
 if common['status']=='pending':
  return _hold(e,'initiative tie requires explicit common order decision',evidence=common)
 s['agenda']=A.create(agenda.round_id,participants,resolved_order=e._initiative_schedule['order'])
 with _dispatch(e):e.start_round(list(actors.values()))
 checked=_check(e)
 return checked or status(e)

def status(e):
 s=e._league_runtime
 if s is None:return dict(status='not_attached',next=None,pending=None)
 return dict(status='incomplete' if s['pending'] else 'round_complete' if s['completed'] else 'ready',
             next=A.expected(s['agenda']),pending=copy.deepcopy(s['pending']),round=e.round_no,
             engine_turn_closures=len(s['close_receipts']),agenda_exhausted=s['agenda'].phase==A.Phase.EXHAUSTED)

def declare(e,actor_id,intent):
 held=_check(e)
 if held:return held
 s=e._league_runtime
 if s['agenda'].phase!=A.Phase.DECLARE or A.expected(s['agenda'])[1]!=actor_id:
  raise ValueError('not this trainer declaration position')
 typed=_intent(intent,actor_id,True)
 if typed['kind']!='no_action':
  return _hold(e,'trainer intent lacks League permission/cost contract; unsupported, not a global prohibition')
 import initiative_schedule as SCHEDULE
 SCHEDULE.declare(e,s['actors'][actor_id],typed)
 s['intents'][actor_id]=typed
 p=next(p for p in s['agenda'].participants if p.actor_id==actor_id)
 s['agenda']=A.declare(s['agenda'],actor_id,'declare:'+actor_id,'immutable intent',
                       disposition='declaration_recorded' if p.able else 'unavailable_recorded')
 return status(e)

def execute_next(e,*,pokemon_intent=None):
 held=_check(e)
 if held:return held
 s=e._league_runtime;agenda=s['agenda'];next_slot=A.expected(agenda)
 if next_slot is None or agenda.phase==A.Phase.DECLARE:raise ValueError('no resolution slot available')
 phase,key=next_slot;c=s['actors'][key]
 if phase==A.Phase.TRAINERS:
  if pokemon_intent is not None:raise ValueError('trainer execution cannot replace declaration')
  intent=s['intents'][key]
 else:
  intent=_intent(pokemon_intent,key,False)
  if intent['kind']=='use_move':
   if intent['target_id'] not in s['actors'] or s['actors'][intent['target_id']].kind!='pokemon':
    return _hold(e,'Pokemon attack target outside supported League Pokemon roster')
   target=s['actors'][intent['target_id']]
   if target is c or not _able(target):
    return _hold(e,'self or incapacitated target outside supported native attack profile')
   if intent['move_id']!='struggle':
    return _hold(e,'move permission/effects beyond native Struggle profile')
   if not _able(c):return _hold(e,'incapacitated Pokemon cannot execute action',category='source_action_prohibited')
  s['intents'][key]=intent
 if e._active_turn_actor is not None:return _hold(e,'unexpected open Engine turn')
 closures=len(e._turn_closures);used=c.move_uses.get('struggle',0)
 s['executing_intent']=intent
 try:
  with _dispatch(e):
   e.start_of_turn(c)
   if e._active_turn_actor is not c or e._ordinary_turn_rounds.get(c)!=e.round_no:
    return _hold(e,'Engine turn ownership not established')
   held=_check(e)
   if held:return held
   if intent['kind']=='use_move':
    target=s['actors'][intent['target_id']]
    e.use_move(c,target,intent['move_id'],set_damage=intent['set_damage'])
    if c.move_uses.get('struggle',0)!=used+1:
     return _hold(e,'move did not establish observed use; refusal semantics not inferred')
   held=_check(e)
   if held:return held
   e.end_of_turn(c)
  held=_check(e)
  if held:return held
 except H.HeavyPending as ex:
  return _hold(e,'unresolved heavy event',category='engine_effect_pending',evidence=ex.event_id)
 except Exception as ex:
  _hold(e,'execution exception; partial state preserved',evidence=type(ex).__name__)
  raise
 finally:s['executing_intent']=None
 evidence=e._turn_closures[closures:]
 if e._active_turn_actor is not None or len(evidence)!=1 or evidence[0]['actor'] is not c or evidence[0]['round']!=e.round_no:
  return _hold(e,'missing unique Engine close_turn evidence')
 s['close_receipts'].append({'actor':c,'actor_id':key,'round':e.round_no,'closure_sequence':evidence[0]['sequence'],
                            'intent':copy.deepcopy(intent),'actual_standard_claim':False})
 p=next(p for p in agenda.participants if p.actor_id==key)
 s['agenda']=A.acknowledge(agenda,key,'close:'+key,str(evidence[0]['sequence']),
                         disposition='resolution_acknowledged' if p.able else 'unavailable_recorded')
 return status(e)

def complete_round(e):
 if e._league_runtime['completed']:raise ValueError('round already completed')
 held=_check(e)
 if held:return held
 s=e._league_runtime
 if s['completed']:raise ValueError('round already completed')
 if s['agenda'].phase!=A.Phase.EXHAUSTED or len(s['close_receipts'])!=len(s['actors']) or e._active_turn_actor is not None:
  raise ValueError('all Engine turns must be closed before League round completion')
 with _dispatch(e):e.end_round()
 s['completed']=True;s['closed_elapsed']=e.elapsed_seconds
 return status(e)

def next_round(e):
 s=e._league_runtime
 if s['pending']:raise LeaguePending(s['pending']['reason'])
 if not s['completed'] or e.round_start_seconds is not None or e._active_turn_actor is not None:
  raise ValueError('previous League round not closed')
 if e._heavy_pending:raise LeaguePending(e._heavy_pending)
 if not _roster_matches(e):return _hold(e,'roster changed between rounds; supplied binding must not be restored silently')
 return _start_round(e,s['actors'],s['bindings'],s['encounter_id'])

def finish(e):
 # Explicit caller end after a completed round; no automatic victory policy.
 s=e._league_runtime
 if s['pending'] or e._heavy_pending:raise LeaguePending('unresolved League/effect event')
 if not s['completed'] or e.round_start_seconds is not None or e._active_turn_actor is not None:
  raise ValueError('explicit League end requires a completed Engine round')
 if not _roster_matches(e):return _hold(e,'roster changed before explicit end; unresolved binding preserved')
 import league_consequences as OUTCOME
 OUTCOME.preflight_end(e,s['encounter_id'])
 result=status(e)
 with _dispatch(e):e.end_encounter()
 encounter_id=OUTCOME.finish(e,s['encounter_id'])
 e._league_runtime=None
 return dict(status='encounter_ended_by_caller',round=result['round'],winner=None,encounter_id=encounter_id)
