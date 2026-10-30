"""Selected Splash/Bounce movement composed with native Jump, paid path and Move completion."""
from copy import deepcopy,copy
import common_checks as C
import tumbler as T
import movement_actions as M
import world_entities as W
import root_resolution as R
KEY='jump_move_actions'

def source(rules,mid):
 if mid not in (T.SPLASH,T.BOUNCE):return None
 from source_context import verified_source
 verified_source(rules,{'file':'input/db/moves.csv','sha256':'ab83f872e5eca67a41db7d126b842f0165437e0fa70bb77ddad832a0b7396c93'},label='Splash/Bounce native movement')
 verified_source(rules,{'file':'source-audit/core-tumbler-moves.txt','sha256':'366a8b565864b3ee70b9d7e70d4bfee1a390675625193717c562969d5f4f963b'},label='Core Tumbler referenced Moves',source_root='source-audit')
 if rules._selected_rule(mid)!=mid:raise ValueError('selected Jump Move requires its own source contract')
 return mid

def mechanics(rules,mid,mm):
 if source(rules,mid) is None:return mm
 result=deepcopy(mm)
 expected=({'type':'movement_rule','pre_move':{'bonus':'+1 speed and jump'}},{'type':'grant_capability','capability':'높이뛰기 +1'}) if mid==T.BOUNCE else ({'type':'evasion_mod','value':2,'target':'self','until':"end of user's next turn"},{'type':'grant_capability','capability':'멀리뛰기 +1, 높이뛰기 +1','until':"end of user's next turn"},{'type':'free_maneuver','maneuver':'뛰기'},{'type':'grant_capability','capability':'멀리뛰기 +1'})
 for effect in result.get('effects_exec',[]):
  if effect['type'] in ('movement_rule','grant_capability','free_maneuver','evasion_mod') and {k:v for k,v in effect.items() if not k.startswith('_')} not in expected:raise ValueError('Jump Move movement declaration differs from its selected source')
 result['effects_exec']=[ef for ef in result.get('effects_exec',[]) if ef['type'] not in ('movement_rule','grant_capability','free_maneuver','evasion_mod')]
 return result

def current(actor,mid=None):
 rows=actor.spec.get(KEY,[])
 live=[r for r in rows if r['phase'] not in ('complete','aborted') and (mid is None or r['move_id']==mid)]
 if len(live)>1:raise ValueError('one actual Jump Move may be active')
 return live[0] if live else None

def movement_allowed(e,actor):
 import grapple_state as GRAPPLE
 if actor.custom_conditions.get(GRAPPLE.MARK) and not GRAPPLE.movement_permission(e,actor):raise ValueError('Grappled forbids Shift Actions and actions causing Shifts')


def _granted(e,actor,mid):
 """A live reviewed one-use grant (Metronome child) may declare a Move the actor has not learned."""
 return any(g[1] is actor and g[3]==mid for g in getattr(e,'_action_grants',()))

def declare(e,actor,target,mid,*,event_id,jump=None,path=None,destroy_hazards=False,attack=True,reason):
 W.require_actors(e,actor,target)
 movement_allowed(e,actor)
 if source(e.r,mid) is None:raise ValueError("only actual Splash/Bounce has this movement declaration")
 if (mid not in actor.moves and not _granted(e,actor,mid)) or type(event_id)is not str or not event_id or type(reason)is not str or not reason.strip():raise ValueError('learned Move and explicit Jump Move identity/reason required')
 if type(attack)is not bool or mid==T.SPLASH and not attack:raise ValueError('only Bounce has an optional attack choice')
 if type(destroy_hazards)is not bool:raise ValueError('explicit Bounce hazard choice required')
 if destroy_hazards and (mid!=T.BOUNCE or not T.acquired(actor,T.FLIP)):raise ValueError('Bounce hazard destruction requires Flip Out')
 if mid==T.SPLASH and (path is not None or actor is not target):raise ValueError('Splash is Self and uses one actual Jump')
 if mid==T.BOUNCE and (jump is None)==(path is None):raise ValueError('Bounce chooses a Shift path or one Jump')
 if jump is not None:
  if type(jump)is not dict or 'destination' not in jump or set(jump)&{'jump_id','_prepaid_move','reason_text','_wall_staged'}:raise ValueError('actual Jump choices required; source owns payment and identity')
  jump=deepcopy(jump);jump['destination']=M._point(jump['destination'])
 if path is not None:
  path=[M._point(point) for point in path]
  position=actor.pos;diagonals=getattr(actor,'_diagonal_steps',0)
  for point in path:_,diagonals=M.step_cost(position,point,diagonals);position=point
 intent={'actor_id':actor.entity_id,'target_id':target.entity_id,'move_id':mid,'event_id':event_id,'jump':jump,'path':path,'destroy_hazards':destroy_hazards,'attack':attack,'reason':reason,'round':e.round_no,'turn':actor.custom_conditions.get('combat_turn_serial',0)}
 rows=actor.spec.setdefault(KEY,[]);old=next((r for r in rows if r['event_id']==event_id),None)
 if old:
  if old['intent']!=intent:raise ValueError('Jump Move identity cannot change its original intent')
  return old
 if current(actor) is not None:raise ValueError('finish the actual paid Jump Move first')
 row={'event_id':event_id,'move_id':mid,'intent':intent,'integrity':R.fingerprint(intent),'phase':'declared','movement':{}}
 rows.append(row);return row

def range_actor(e,actor,move):
 row=current(actor,move['id'])
 if move['id']!=T.BOUNCE:return actor
 if row is None:raise ValueError('Bounce requires its actual movement declaration before payment')
 dest=row['intent']['jump']['destination'] if row['intent']['jump'] else row['intent']['path'][-1] if row['intent']['path'] else actor.pos
 projected=copy(actor);projected.pos=tuple(dest)
 return projected

def preflight(e,actor,target,move):
 if source(e.r,move['id']) is None:return
 movement_allowed(e,actor)
 row=current(actor,move['id'])
 if row is None or row['intent']['target_id']!=target.entity_id:raise ValueError('actual Splash/Bounce movement declaration required')
 if row['integrity']!=R.fingerprint(row['intent']):raise ValueError('Jump Move choices changed')
 if row['phase']!='declared':raise ValueError('resume the paid Jump Move instead of paying again')
 if row['intent']['round']!=e.round_no or row['intent']['turn']!=actor.custom_conditions.get('combat_turn_serial',0):raise ValueError('Jump Move declaration outlived its turn')
 if row['intent']['path'] is not None:
  position=actor.pos;diagonal=getattr(actor,'_diagonal_steps',0);distance=0
  for point in row['intent']['path']:
   cost,diagonal=M.step_cost(position,point,diagonal);distance+=cost;position=point
  import effects_ext as EXT
  if distance>M.distance_budget(e,actor,'land')+1:raise ValueError('Bounce Shift exceeds its actual speed plus one')

def bonus(actor):
 row=current(actor)
 return 1 if row and row['phase']=='moving' else 0

def _stored_suffix(args):
 """The restorable continuation copy: a consumed one-use grant handle (Metronome child) is runtime-only, so a marker
 that still reads as 'not an ordinary single use' replaces it."""
 suffix=dict(args)
 if suffix.get('_action_grant') is not None:suffix['_action_grant']='consumed_one_use_grant'
 return suffix

def _suffix_facts(args):
 """The paid continuation without its runtime grant handle (a Metronome child carries an object() grant)."""
 return __import__('move_defense_reactions')._move_facts({k:v for k,v in args.items() if k!='_action_grant'})

def prepaid(e,actor,token):
 row=current(actor)
 if token is None:return False
 if row is None or row['phase']!='moving' or token!=row['event_id'] or row.get('completion_id') not in getattr(e,'_move_completions',{}):raise ValueError('Jump must belong to its actual paid native Move')
 return True

def begin(e,actor,target,move,completion_id,args):
 if source(e.r,move['id']) is None:return None
 row=current(actor,move['id'])
 if row is None or row['phase']!='declared':raise ValueError('one actual unspent Jump Move declaration required')
 __import__('action_lifecycle').observe_resolution(e,actor,move['id'],{'event':'jump_move_started','event_id':row['event_id'],'completion_id':completion_id})
 row.update(phase='moving',completion_id=completion_id,suffix=_stored_suffix(args),suffix_fingerprint=R.fingerprint(_suffix_facts(args)))
 import combat_timing as TIME
 if move['id']==T.SPLASH:
  TIME.install(e,actor,{'source':T.SPLASH,'effect_contract':True,'evasion_modifier':2,'turn_owner':actor,'turn_deadline':actor.custom_conditions.get('combat_turn_serial',0)+1,'encounter_end':True,'jump_move_completion':completion_id})
 if move['id']==T.BOUNCE and T.acquired(actor,T.FLIP):
  TIME.install(e,actor,{'source':T.FLIP,'bounce_hazard_immunity':True,'turn_owner':actor,'turn_deadline':actor.custom_conditions.get('combat_turn_serial',0),'encounter_end':True,'jump_move_completion':completion_id})
 result=advance(e,actor,row)
 if isinstance(result,C.PendingDecision):
  frame=__import__('action_lifecycle').move_frame(e,e._move_completions[completion_id]);frame['deferred']=True
 return result

def advance(e,actor,row):
 import jump_actions as J,effects_ext as EXT,hazard_state as H
 intent=row['intent'];jump=intent['jump']
 actor._regular_shift_movement_used=True
 if jump is not None:
  previous=actor.spec.get('_jump_attempts',{}).get(row['event_id'])
  if previous and (previous.get('gm_consequence') or (previous.get('landed') and not previous.get('movement_pending') and not previous.get('fall_pending'))):
   quick=previous.get('quick_gymnastics')
   if T.quick_entry_waiting(e,quick):return C.PendingDecision('actual Quick Gymnastics entry effect must finish before Jump Move completion')
   result=T.quick_shift(e,actor,quick)
   if isinstance(result,C.PendingDecision):return result
   if previous.get('gm_consequence'):
    row['phase']='moved';return None
  else:
   opts=dict(jump);destination=opts.pop('destination')
   result=J.jump(e,actor,destination,jump_id=row['event_id'],reason_text=intent['reason'],_prepaid_move=row['event_id'],**opts)
   if isinstance(result,C.PendingDecision):return result
   previous=actor.spec.get('_jump_attempts',{}).get(row['event_id'])
   if T.quick_entry_waiting(e,previous.get('quick_gymnastics') if previous else None):return C.PendingDecision('actual Quick Gymnastics entry effect must finish before Jump Move completion')
 elif intent['path'] is not None:
  result=M.follow_paid_path(e,actor,intent['path'],mode='land',maximum_distance=M.distance_budget(e,actor,'land')+1,progress=row['movement'])
  if row['movement'].get('phase') in ('reaction_pending','entry_pending'):return C.PendingDecision('actual Bounce Shift effects must finish')
 if intent['destroy_hazards']:
  landing=actor.spec.get('_jump_attempts',{}).get(row['event_id']) if jump is not None else None
  x,y=landing['destination'] if landing and landing.get('landed') else actor.pos
  row['hazards_destroyed']=H.remove_cells(e,{(x+dx,y+dy) for dx in (-1,0,1) for dy in (-1,0,1)})
 row['phase']='moved'
 return None

def resume(e,actor,*,event_id):
 row=current(actor)
 if row is None or row['event_id']!=event_id or row['phase']!='moving':raise ValueError('actual pending paid Jump Move required')
 if row['suffix_fingerprint']!=R.fingerprint(_suffix_facts(row['suffix'])):raise ValueError('paid Jump Move continuation changed')
 import action_lifecycle as ACTION
 with ACTION.resolution(e,actor,row['move_id'],kind='move',_move_completion=row['completion_id']):
  result=advance(e,actor,row)
  if isinstance(result,C.PendingDecision):
   ACTION.move_frame(e,e._move_completions[row['completion_id']])['deferred']=True;return result
  return e._after_move_movement(**row['suffix'])

def completed(e,actor,move,completion_id):
 row=current(actor,move['id'])
 if row and row.get('completion_id')==completion_id:
  row['phase']='complete'
  frame=__import__('action_lifecycle').move_frame(e,e._move_completions[completion_id])
  if frame and frame['id']:
   for trigger in e._native_action_resolutions[frame['id']]['triggers']:
    if trigger['actor'] is actor and trigger['source']==move['id']:trigger['status']='completed'

def hazard_immune(actor):
 import combat_timing as TIME
 return any(r.get('bounce_hazard_immunity') for r in TIME.records(actor))

def validate_world(e,index):
 for actor in index.values():
  ids=set()
  for row in actor.spec.get(KEY,[]):
   intent=row['intent']
   if row['event_id'] in ids or row['integrity']!=R.fingerprint(intent) or intent['actor_id']!=actor.entity_id or intent['target_id'] not in index:raise ValueError('native Jump Move provenance changed')
   ids.add(row['event_id']);source(e.r,row['move_id'])
   if row['phase'] not in ('declared','moving','moved','complete','aborted'):raise ValueError('native Jump Move phase changed')
   if row['phase']!='declared':
    completion=getattr(e,'_move_completions',{}).get(row.get('completion_id'))
    if completion is None or completion['actor'] is not actor or completion['move_id']!=row['move_id']:raise ValueError('Jump Move lost its actual paid completion')
    suffix=row['suffix']
    if suffix['attacker'] is not actor or suffix['target'].entity_id!=intent['target_id'] or suffix['completion_id']!=row['completion_id'] or row['suffix_fingerprint']!=R.fingerprint(_suffix_facts(suffix)):raise ValueError('paid Jump Move continuation provenance changed')


def decline_attack(e,actor,target,move,completion_id):
 row=current(actor,move['id'])
 if row is None or row['move_id']!=T.BOUNCE or row['intent']['attack']:return False
 if row['phase']!='moved' or row['completion_id']!=completion_id:raise ValueError('Bounce attack decline needs actual paid completed movement')
 import move_completion as COMPLETE
 COMPLETE.finish_target(e,completion_id,actor,target,hit=False,dealt=0,cancelled=True)
 return True


def triggered_free_allowed(e,actor,request,source):
 row=current(actor,T.SPLASH)
 return bool(source==T.QUICK and request['source']==T.SPLASH and T.acquired(actor,T.QUICK) and row and row['phase']=='moving' and row['event_id'] in actor.spec.get('_jump_attempts',{}))

def interrupt_actions(e,request):
 if request['source']!=T.SPLASH:return ['standard']
 actor=request['actor'];row=next((r for r in actor.spec.get(KEY,[]) if r['event_id']==request['id']),None)
 jump=None if row is None else actor.spec.get('_jump_attempts',{}).get(row['event_id'])
 quick=None if jump is None else jump.get('quick_gymnastics')
 return ['shift']+(['free'] if quick is not None else [])
