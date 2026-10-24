"""Source-bound Combat Move reactions over native action, damage and completion owners."""
from copy import deepcopy
import root_resolution as R
import state_grants as G
SOURCES={'move/받아던지기':227,'move/카운터':186,'move/패스트가드':209,'move/스카이어퍼':219,'move/기습':72,'move/따라가때리기':67,'move/숟가락휘기':687}
SOURCES.update(__import__('warper').MOVES)
VITAL='move/받아던지기';COUNTER='move/카운터';GUARD='move/패스트가드';UPPER='move/스카이어퍼'
SUCKER='move/기습';PURSUIT='move/따라가때리기'
KINESIS='move/숟가락휘기'
CHOICES='combat_move_reaction_choices';EVENTS='combat_move_reaction_events'

def selected(r,mid):
 import priority_actions as P
 move=P._move(r,mid)
 if mid not in SOURCES or move['_source']['record_span']!=[SOURCES[mid]]*2:raise ValueError('exact printed Combat Move reaction required')
 return move

def _ready(e,a,mid):
 import priority_actions as P,frequency as F,turn as T,action_resources as A
 selected(e.r,mid);P._owned_move(e,a,mid)
 return a.on_field and not a.fainted and not a.captured and T.can_act(e,a) and not A.pending(a) and F.move_allowed(e,a,mid,outside_combat=not e.encounter_active)[0]

def _opponents(left,right):
 a=getattr(left,'side',None);b=getattr(right,'side',None)
 return left is not right and a is not None and b is not None and a!=b


def _protects(e,actor,target,mid):
 if actor is target:return True
 side=getattr(actor,'side',None)
 if side is None or side!=getattr(target,'side',None):return False
 if mid==GUARD:return e.adjacent(actor,target)
 import world_entities as W
 distance=W.distance_known(actor,target)
 return distance is not None and distance<=6


def arm(e,a,mid,*,protect=None,weapon_id=None,overload=False):
 """Choose the next printed reaction before its actual trigger; no fabricated hit."""
 import world_entities as W
 W.require_actors(e,a);selected(e.r,mid)
 import priority_actions as P
 P._owned_move(e,a,mid)
 if protect is not None and mid not in (GUARD,KINESIS):raise ValueError('only sourced protective reactions choose an ally')
 if type(overload)is not bool or overload and mid!=KINESIS:raise ValueError('Overload choice belongs to Kinesis')
 if overload:__import__('telekinetic').require(e,a,__import__('telekinetic').OVERLOAD)
 if weapon_id is not None:
  if mid not in (SUCKER,PURSUIT):raise ValueError('weapon choice belongs to Rogue reaction Move')
  __import__('weapon_actions').prepare(e,a,e.r.move(mid),weapon_id)
 target=protect or a;W.require_actors(e,target)
 if mid==KINESIS and not _protects(e,a,target,mid):raise ValueError('Kinesis requires self or an observed ally within six metres')
 if mid==GUARD and not _protects(e,a,target,mid):raise ValueError('Quick Guard requires self or an observed adjacent ally')
 if mid==GUARD and any(x is not a and x.spec.get(CHOICES,{}).get(GUARD,{}).get('target_id')==target.entity_id for x in e.everyone):raise ValueError('choose one actual Quick Guard responder for this target')
 return G.transition(e,a,lambda se,c:c.spec.setdefault(CHOICES,{}).update({mid:{'target_id':target.entity_id,**({'weapon_id':weapon_id} if weapon_id is not None else {}),**({'overload':overload} if mid==KINESIS else {})}}))

def _seal(row):row['fingerprint']=R.fingerprint({k:v for k,v in row.items() if k!='fingerprint'})

def _observe(e,a,mid,attacker,target,move,kind,completion=None):
 import action_lifecycle as A
 turn_owner=e._active_turn_actor
 if turn_owner is None:raise ValueError('actual active turn owner required for a Combat Move reaction')
 native=A.observe_resolution(e,attacker,move['id'],{'combat_move_reaction':mid,'reactor_id':a.entity_id,'target_id':target.entity_id,'kind':kind,'turn_owner_id':turn_owner.entity_id})
 for observation in native['triggers']:
  if observation['actor'] is attacker and observation['source']==move['id']:observation['status']='completed'
 rows=a.spec.setdefault(EVENTS,{})
 uid='combat-reaction:'+a.entity_id+':'+str(len(rows)+1)
 row={'id':uid,'source':mid,'actor_id':a.entity_id,'attacker_id':attacker.entity_id,'turn_owner_id':turn_owner.entity_id,'target_id':target.entity_id,'trigger_move':move['id'],'kind':kind,'native_action_id':native['id'],'completion_id':completion,'round':e.round_no,'status':'ready','result_completion':None,'hp_loss':0}
 choice=a.spec.get(CHOICES,{}).get(mid,{})
 if mid in __import__('warper').MOVES:row['warper_choice']=deepcopy(choice)
 if 'weapon_id' in choice:row['weapon_id']=choice['weapon_id']
 if mid==KINESIS:row['overload']=choice['overload']
 rows[uid]=row;a.spec.get(CHOICES,{}).pop(mid,None);_seal(row)
 return row

def _event(a,request):return a.spec.get(EVENTS,{}).get(request)

def validate_request(e,window,row):
 a=row['actor'];event=_event(a,row['id']);selected(e.r,row['source'])
 if event is None or event['source']!=row.get('move_id') or row['source']!=row['move_id'] or event['actor_id']!=a.entity_id or row['budget']!={'standard':1} or row['mode']!='reaction' or row['payment']!='next' or row['clock']!='none':raise ValueError('Combat Move reaction lost its native source and Standard cost')
 validate_event(e,a,event)
 if window['trigger']['owner'].entity_id!=event['turn_owner_id']:raise ValueError('reaction has another suspended attacking owner')

def authorize_request(e,a,row,evidence):
 request=dict(row,actor=a);validate_request(e,{'trigger':evidence},request)
 event=_event(a,row['id'])
 if event['round']!=e.round_no or event['status'] not in ('ready','resolving'):raise ValueError('Combat Move reaction already resolved or lapsed')

def current(e,a,mid):
 import initiative_interrupts as I
 frame=I.selected_move_frame(e,a)
 if frame is None:return None
 row=frame[1]
 return _event(a,row['id']) if row.get('source')==mid and mid in SOURCES else None

def mechanics(r,mid,mm):
 if mid not in SOURCES:return mm
 selected(r,mid)
 if mid in __import__('warper').MOVES:return mm
 result=deepcopy(mm);result['effects_exec']=[]
 if mid in (VITAL,COUNTER):result['never_miss']=True
 return result

def bind(e,a,move,mm):
 mid=move['id']
 if mid not in SOURCES:return move,mm
 event=current(e,a,mid)
 if event is None:
  if mid==__import__('warper').TELEPORT and a.spec.get('warper_move_destination'):return move,mm
  if mid==__import__('warper').SWITCH and __import__('warper').direct_switch_choice(e,a):return dict(move,range='자신'),mm
  if mid not in (UPPER,PURSUIT):raise ValueError('this Move requires its actual armed native reaction trigger')
  return move,mm
 if mid==COUNTER:
  move=dict(move,damage_base='variable')
  mm=dict(mm,effects_exec=[{'type':'hp_loss','target':'target','value':2*event['hp_loss']}],never_miss=True)
 elif mid==GUARD:move=dict(move,range='자신')
 elif mid==PURSUIT:move=dict(move,damage_base=8,range=move['range']+', 방해')
 elif mid in __import__('warper').MOVES:move=dict(move,range='자신')
 return move,mm

def _finish_response(e,a,event,completion):
 import initiative_interrupts as I
 if completion['actor'] is not a or completion['move_id']!=event['source'] or completion['phase']!='complete':raise ValueError('reaction requires its actual completed native Move')
 event=_event(a,event['id']);event['result_completion']=completion['id'];event['status']='complete'
 event.pop('pending_event_id',None);event.pop('pending_completion_id',None);_seal(event)
 I.finish(e)
 return completion


def _run(e,a,t,event,*,continuation=None):
 import initiative_interrupts as I,passive_events as P
 parent=e._active_turn_actor
 if parent is None or parent.entity_id!=event['turn_owner_id']:raise ValueError('reaction must immediately answer its actual suspended turn owner')
 if continuation is not None:capture_context(e,event,continuation)
 raw={'kind':'turn','actor_id':parent.entity_id,'serial':parent.custom_conditions['combat_turn_serial'],'round':e.round_no}
 request={'id':event['id'],'actor_id':a.entity_id,'source':event['source'],'move_id':event['source'],'priority':0,'mode':'reaction','payment':'next','budget':{'standard':1},'clock':'none'}
 queued=I.queue(e,[request],trigger=raw)
 I.begin(e,queued['window_id'],event['id'])
 event=_event(a,event['id']);event['status']='resolving';_seal(event)
 before=set(getattr(e,'_move_completions',{}))
 try:e.use_move(a,a if event['source']==GUARD else t,event['source'],weapon_id=event.get('weapon_id'))
 except P.PassiveEventPending as pending:
  rows=[r for k,r in e._move_completions.items() if k not in before and r['actor'] is a]
  if e._passive_pending!=pending.event_id or len(rows)!=1 or rows[0]['move_id']!=event['source']:raise
  event=_event(a,event['id']);event['pending_event_id']=pending.event_id;event['pending_completion_id']=rows[0]['id'];_seal(event)
  raise
 rows=[r for k,r in e._move_completions.items() if k not in before and r['actor'] is a]
 if len(rows)!=1:raise ValueError('reaction requires exactly one actual native Move')
 result=_finish_response(e,a,event,rows[0])
 if continuation is not None:e._native_action_resolutions[event['native_action_id']].get('combat_move_continuations',{}).pop(event['id'],None)
 return result


def before_recipient(e,attacker,target,move,hit,completion):
 """Real accuracy and actual recipient: optional Quick Guard, Counter, Vital Throw."""
 import reactive_ability_events as A,attack_damage_history as H
 if hit:
  for reactor in e.everyone:
   choice=reactor.spec.get(CHOICES,{}).get(GUARD)
   if not choice or choice['target_id']!=target.entity_id or not _protects(e,reactor,target,GUARD):continue
   keywords=str(move.get('range',''))+' '+str(move.get('keywords',[]))
   if not any(k in keywords for k in ('우선','방해','Priority','Interrupt')) or not _ready(e,reactor,GUARD):continue
   event=_observe(e,reactor,GUARD,attacker,target,move,'accuracy',completion)
   _run(e,reactor,reactor,event)
   return False
  if COUNTER in target.spec.get(CHOICES,{}) and move.get('class')=='물리' and _ready(e,target,COUNTER):
   row=_observe(e,target,COUNTER,attacker,target,move,'damage',completion)
   row['history_start']=len(H.records(target));_seal(row)
 if VITAL in target.spec.get(CHOICES,{}) and A._melee(move) and e._ordinary_turn_rounds.get(target)!=e.round_no and _ready(e,target,VITAL):
  _observe(e,target,VITAL,attacker,target,move,'targeted',completion)
 return hit

def kinesis_accuracy(e,attacker,target,move,hit):
 """Suspend the actual about-to-hit attack; return the original roll penalty."""
 if not hit:return 0
 import initiative_interrupts as I
 for actor in e.everyone:
  choice=actor.spec.get(CHOICES,{}).get(KINESIS)
  if not choice or choice['target_id']!=target.entity_id or not _protects(e,actor,target,KINESIS) or not _ready(e,actor,KINESIS):continue
  if choice['overload'] and (e._active_turn_actor is not actor or I.frame(e) is not None or e._ordinary_turn_rounds.get(actor)!=e.round_no):raise ValueError('Kinesis Overload Swift requires the reactor own ordinary turn')
  event=_observe(e,actor,KINESIS,attacker,target,move,'accuracy')
  _run(e,actor,target,event)
  event=_event(actor,event['id'])
  if choice['overload']:__import__('telekinetic').kinesis_overload(e,actor,event)
  return -4
 return 0

def resistance(e,attacker,target,move):
 return int(any(row['source']==COUNTER and row['status']=='ready' and row['attacker_id']==attacker.entity_id and row['trigger_move']==move['id'] and row['round']==e.round_no for row in target.spec.get(EVENTS,{}).values()))

def after_move(e,completion):
 import move_completion as M,world_entities as W,attack_damage_history as H,body_state as B
 index=W.actor_index(e)
 for actor in list(index.values()):
  for row in list(actor.spec.get(EVENTS,{}).values()):
   if row['completion_id']!=completion['id'] or row['status']!='ready' or row['source'] not in (COUNTER,VITAL):continue
   target=index[row['attacker_id']]
   if actor.fainted or not actor.on_field or not target.on_field or not B.in_range(e,actor,target,1):row['status']='unavailable';_seal(row);continue
   if row['source']==COUNTER:
    actual=M.recipient_result(completion,actor)
    history=H.records(actor)[row['history_start']:]
    row['hp_loss']=sum(max(0,r['receipt']['net_hp_loss']) for r in history if r['attacker_id']==target.entity_id and r['receipt']['source']==row['trigger_move'] and r['round']==row['round'])
    if not actual or not actual['hit']:row['status']='unavailable';_seal(row);continue
    _seal(row)
   _run(e,actor,target,row)

def initiation(e,attacker,target,move,*,continuation):
 """The native Move has paid its action, before Bounce/Fly/Sky Drop preparation."""
 if SUCKER in target.spec.get(CHOICES,{}) and _opponents(attacker,target) and move.get('class') in ('물리','특수') and e.adjacent(attacker,target) and _ready(e,target,SUCKER):
  event=_observe(e,target,SUCKER,attacker,target,move,'initiation')
  _run(e,target,attacker,event,continuation=continuation)
  if attacker.fainted:
   __import__('frequency').consume_move(e,attacker,move['id']);attacker.last_move=move['id']
   return True
 if move['id'] not in ('move/뛰어오르기','move/공중날기','move/프리폴'):return False
 if attacker.setup_move==move['id']:return False
 import body_state as B
 for actor in e.everyone:
  if UPPER not in actor.spec.get(CHOICES,{}) or actor is attacker or not B.in_range(e,actor,attacker,1) or not _ready(e,actor,UPPER):continue
  event=_observe(e,actor,UPPER,attacker,attacker,move,'initiation')
  result=_run(e,actor,attacker,event,continuation=continuation)
  import move_completion as COMPLETE
  received=COMPLETE.recipient_result(result,attacker)
  if received and received['hit'] and not received.get('cancelled'):
   for scope in getattr(e,'_setup_move_scopes',[]):
    if scope['actor_id']==attacker.entity_id and scope['move_id']==move['id']:scope['interrupted_by_sky_uppercut']=True
   import frequency as F
   F.consume_move(e,attacker,move['id']);attacker.last_move=move['id']
   return True
 return False

def validate_event(e,a,row):
 facts={k:v for k,v in row.items() if k!='fingerprint'}
 if row.get('fingerprint')!=R.fingerprint(facts) or row['actor_id']!=a.entity_id or row['source'] not in SOURCES:raise ValueError('native Combat Move reaction evidence changed')
 native=getattr(e,'_native_action_resolutions',{}).get(row['native_action_id'])
 if native is None or native['actor'].entity_id!=row['attacker_id'] or native['source']!=row['trigger_move']:raise ValueError('reaction requires its actual triggering native action')
 observed={'combat_move_reaction':row['source'],'reactor_id':a.entity_id,'target_id':row['target_id'],'kind':row['kind'],'turn_owner_id':row['turn_owner_id']}
 if not any(observed in t['observations'] for t in native['triggers'] if t['actor'].entity_id==row['attacker_id'] and t['source']==row['trigger_move']):raise ValueError('reaction source and recipient differ from native trigger observation')
 if row['completion_id'] is not None:
  original=getattr(e,'_move_completions',{}).get(row['completion_id'])
  if original is None or original['actor'].entity_id!=row['attacker_id'] or original['move_id']!=row['trigger_move']:raise ValueError('reaction lost its original Move completion')
 if row.get('pending_completion_id') is not None:
  response=getattr(e,'_move_completions',{}).get(row['pending_completion_id'])
  pending=e._passive_events.get(row.get('pending_event_id'))
  if row['status']!='resolving' or response is None or response['actor'] is not a or response['move_id']!=row['source'] or pending is None:raise ValueError('reaction lost its actual suspended response')
 _context(e,row);_escape_context(e,row)
 if row['result_completion'] is not None:
  result=getattr(e,'_move_completions',{}).get(row['result_completion'])
  if result is None or result['actor'] is not a or result['move_id']!=row['source'] or result['phase']!='complete':raise ValueError('reaction lost its actual response Move')

def validate(e):
 import world_entities as W
 index=W.actor_index(e)
 for a in index.values():
  for mid,choice in a.spec.get(CHOICES,{}).items():
   selected(e.r,mid)
   if mid in __import__('warper').MOVES:
    if choice.get('warper')is not True or choice.get('target_id')!=a.entity_id:raise ValueError('actual Psychic Interrupt choice required')
    continue
   if set(choice)-{'target_id','weapon_id','overload'} or 'target_id' not in choice or choice['target_id'] not in index:raise ValueError('reaction choice actual target missing')
   if ('overload' in choice)!=(mid==KINESIS) or mid==KINESIS and type(choice['overload'])is not bool:raise ValueError('actual Kinesis Overload choice required')
   if 'weapon_id' in choice and (mid not in (SUCKER,PURSUIT) or not isinstance(choice['weapon_id'],str)):raise ValueError('actual Rogue reaction weapon required')
  for row in a.spec.get(EVENTS,{}).values():validate_event(e,a,row)


def interested(e):
 return any(a.spec.get(CHOICES) or any(r['status'] in ('ready','resolving') for r in a.spec.get(EVENTS,{}).values()) for a in e.everyone)


def _find(e,identity):
 for a in e.everyone:
  row=_event(a,identity)
  if row is not None:return a,row
 raise ValueError('actual native Combat Move reaction required')


def _context_facts(context):
 import move_defense_reactions as DEFENSE
 frame=context['frame']
 return DEFENSE._move_facts({k:v for k,v in context.items() if k not in ('fingerprint','frame')} | {'frame':{k:frame[k] for k in ('actor','source','kind','id')}})


def capture_context(e,row,args):
 """Keep the actual paid producer suffix in its existing native action record."""
 import world_entities as W
 native=e._native_action_resolutions[row['native_action_id']]
 frame=e._native_action_stack[-1]
 if frame['id']!=native['id'] or frame['actor'] is not args['attacker'] or frame['source']!=args['move_id']:raise ValueError('actual paid Move frame required')
 memo={id(a):a for a in W.actor_index(e).values()}
 values=dict(args);values['_action_grant']=None if args['_action_grant'] is None else True
 context={'args':deepcopy(values,memo),'frame':frame,
  'setup_scopes':deepcopy(list(getattr(e,'_setup_move_scopes',())),memo),
  'activation_scopes':deepcopy(list(getattr(e,'_move_activation_scopes',())),memo),
  'event_scopes':deepcopy(list(getattr(e,'_event_use_scopes',())),memo),
  'history':list(args['attacker']._action_history),'round':e.round_no,'seconds':e.elapsed_seconds}
 context['fingerprint']=R.fingerprint(_context_facts(context))
 native.setdefault('combat_move_continuations',{})[row['id']]=context


def _context(e,row):
 native=e._native_action_resolutions[row['native_action_id']]
 context=native.get('combat_move_continuations',{}).get(row['id'])
 if context is None:return None
 frame=context['frame'];args=context['args']
 if (context['fingerprint']!=R.fingerprint(_context_facts(context)) or frame['id']!=native['id'] or
     frame['actor'] is not native['actor'] or frame['source']!=native['source'] or frame['kind']!='move' or
     args['attacker'] is not native['actor'] or args['move_id']!=row['trigger_move'] or
     context['round']!=e.round_no or context['seconds']!=e.elapsed_seconds or
     args['attacker']._action_history[:len(context['history'])]!=context['history']):raise ValueError('paid native reaction continuation changed')
 return context


def resume_frame(e,identity):
 actor,row=_find(e,identity);validate_event(e,actor,row)
 context=_context(e,row)
 if context is None or row['status']!='complete' or e._active_turn_actor is None or e._active_turn_actor.entity_id!=row['turn_owner_id']:raise ValueError('completed response and actual suspended owner required')
 return context['frame']


def pending_setup(e,actor,scope):
 for a in e.everyone:
  for row in a.spec.get(EVENTS,{}).values():
   if row['source']!=UPPER or row['attacker_id']!=actor.entity_id or row['status']!='resolving' or row.get('pending_event_id')!=e._passive_pending:continue
   context=_context(e,row)
   if context is not None and scope in context['setup_scopes']:return True
 return False


def pending_for_completion(e,identity):
 return any(row['completion_id']==identity and row['status']=='resolving' and row.get('pending_event_id')==e._passive_pending
  for a in e.everyone for row in a.spec.get(EVENTS,{}).values())


def resume_after_event(e,event,result):
 """Existing passive delivery has returned; finish the response, then its caller."""
 import initiative_interrupts as I,move_completion as M,passive_events as P,action_lifecycle as A
 frame=I.frame(e)
 if frame is None:return result
 actor=frame['actor'];row=_event(actor,frame['request_id'])
 if row is None or row['status']!='resolving' or not row.get('pending_completion_id'):return result
 completion=e._move_completions[row['pending_completion_id']]
 if completion['phase']!='complete' or event.get('completion_id')!=completion['id']:return result
 context=_context(e,row);escape=_escape_context(e,row)
 _finish_response(e,actor,row,completion);row=_event(actor,row['id'])
 if escape is not None:
  owner=__import__('world_entities').actor_index(e)[escape['owner_id']]
  with A.resolution(e,owner,row['trigger_move'],kind='escape',_escape_reaction=row['id']):
   e._native_action_resolutions[row['native_action_id']].get('escape_continuations',{}).pop(row['id'],None)
   if escape['kind']=='party':return __import__('party_actions').resume_escape(e,owner,escape['request_id'])
  return __import__('repels').resume_escape(e,owner,escape['request_id'])
 if context is not None:
  previous={key:getattr(e,key,None) for key in ('_setup_move_scopes','_move_activation_scopes','_event_use_scopes')}
  e._setup_move_scopes=context['setup_scopes'];e._move_activation_scopes=context['activation_scopes']
  e._event_use_scopes=context['event_scopes']
  try:
   with A.resolution(e,context['args']['attacker'],row['trigger_move'],kind='move',_combat_reaction=row['id']):
    e._native_action_resolutions[row['native_action_id']].get('combat_move_continuations',{}).pop(row['id'],None)
    attacker=context['args']['attacker'];received=M.recipient_result(completion,attacker)
    if (row['source']==UPPER and received and received['hit'] and not received.get('cancelled')) or (row['source']==SUCKER and attacker.fainted):
     import frequency as F
     F.consume_move(e,attacker,row['trigger_move']);attacker.last_move=row['trigger_move'];result=0
    else:result=e._continue_move_after_payment(**context['args'])
  finally:
   e._native_action_resolutions[row['native_action_id']].get('combat_move_continuations',{}).pop(row['id'],None)
   for key,value in previous.items():
    if value is None:vars(e).pop(key,None)
    else:setattr(e,key,value)
  return result
 if row['completion_id'] is not None:
  original=e._move_completions[row['completion_id']]
  after_move(e,original)
  parents=[p for p in e._passive_events.values() if p.get('completion_id')==original['id'] and p.get('continuation',{}).get('kind')=='recipient_return']
  if parents:
   if len(parents)!=1:raise ValueError('one actual parent recipient return required')
   return P.deliver(e,parents[0]['id'])
  native=A.move_frame(e,original)
  if native is not None and e._native_action_resolutions[native['id']]['phase']=='interrupted':
   with A.resolution(e,original['actor'],original['move_id'],kind='move',_move_completion=original['id']):pass
 return result


def movement(e,actor,values):
 if current(e,actor,PURSUIT) is None:return values
 import movement_actions as M
 return {key:value+5 if key in M.MODES and value>0 else value for key,value in values.items()}


def _escape_facts(context):
 return {key:value for key,value in context.items() if key not in ('frame','fingerprint')} | {'frame_id':context['frame']['id']}


def _escape_context(e,row):
 native=e._native_action_resolutions[row['native_action_id']]
 context=native.get('escape_continuations',{}).get(row['id'])
 if context is None:return None
 frame=context['frame'];owner=__import__('world_entities').actor_index(e).get(context['owner_id'])
 if (context['fingerprint']!=R.fingerprint(_escape_facts(context)) or owner is None or frame['id']!=native['id'] or
     frame['actor'] is not owner or frame['source']!=row['trigger_move'] or frame['kind']!='escape' or
     native['actor'] is not owner or native['source']!=row['trigger_move'] or context['target_id']!=row['target_id'] or
     context['round']!=e.round_no or context['seconds']!=e.elapsed_seconds or
     list(getattr(owner,'_action_history',[]))[:len(context['history'])]!=context['history']):raise ValueError('actual native escape continuation changed')
 if context['kind']=='party':__import__('party_actions').validate_escape(e,owner,context['request_id'])
 elif context['kind']=='repel':__import__('repels').validate_escape(e,owner,context['request_id'])
 else:raise ValueError('reviewed native escape owner required')
 return context


def resume_escape_frame(e,request):
 rows=[row for actor in e.everyone for row in actor.spec.get(EVENTS,{}).values() if row['id']==request]
 if len(rows)!=1:raise ValueError('one actual escape response required')
 context=_escape_context(e,rows[0])
 if context is None:raise ValueError('actual retained native escape frame required')
 return context['frame']


def before_escape(e,owner,target,source,*,kind,request_id):
 """Native paid recall or observed flee, before displacement; never a fake Move."""
 import action_lifecycle as A,weapon_actions as WEAPONS,body_state as B
 if not target.on_field or target.fainted:return
 stack=getattr(e,'_native_action_stack',[])
 join=bool(stack and stack[-1]['actor'] is owner and stack[-1]['source']==source and stack[-1]['kind']=='escape')
 with A.resolution(e,owner,source,kind='escape',join=join) as frame:
  __import__('capture_specialist').before_escape(e,owner,target,source,kind=kind,request_id=request_id)
  for actor in list(e.everyone):
   choice=actor.spec.get(CHOICES,{}).get(PURSUIT)
   if not choice or not _opponents(actor,target) or not _ready(e,actor,PURSUIT):continue
   move=WEAPONS.prepare(e,actor,e.r.move(PURSUIT),choice.get('weapon_id'))
   reach=WEAPONS.range_spec(e,move,actor).get('origin');reach=B.melee_reach(actor) if reach=='melee' else reach
   if not B.in_range(e,actor,target,reach,move=move):continue
   event=_observe(e,actor,PURSUIT,owner,target,{'id':source},'escape')
   context={'kind':kind,'owner_id':owner.entity_id,'target_id':target.entity_id,'request_id':request_id,
    'frame':frame,'round':e.round_no,'seconds':e.elapsed_seconds,'history':list(getattr(owner,'_action_history',[]))}
   context['fingerprint']=R.fingerprint(_escape_facts(context))
   native=e._native_action_resolutions[event['native_action_id']]
   native.setdefault('escape_continuations',{})[event['id']]=context
   _escape_context(e,event)
   _run(e,actor,target,event)
   e._native_action_resolutions[event['native_action_id']].get('escape_continuations',{}).pop(event['id'],None)
