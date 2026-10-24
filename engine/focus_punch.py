"""Focus Punch: one Priority Limited reservation over shared turns and actual attacks.

The human chose the original game's user-hit subject. PTU's single-hit 25%
threshold and delayed Shift/attack remain; this is not an invented edition.
"""
from copy import deepcopy
from pathlib import Path
import json
import state_grants as G
SOURCE='move/힘껏펀치';KEY='focus_punch_actions'


def policy(rules):
 row=json.loads((Path(rules.root)/'data/focus-punch-policy.json').read_text(encoding='utf8'))
 from source_context import verified_source
 verified_source(rules,{'file':'input/db/moves.csv','sha256':row['source_sha256']},label='Focus Punch')
 verified_source(rules,{'file':row['core_extract'],'sha256':row['core_sha256']},label='core Focus Punch',source_root='source-audit')
 if row['source']!=SOURCE or row['csv_record']!=195 or rules._selected_rule(SOURCE)!=SOURCE:raise ValueError('exact selected Focus Punch source required')
 return row


def actions(actor):return actor.spec.get(KEY,[])
def pending(e):return [(a,r) for a in __import__('world_entities').actor_index(e).values() for r in actions(a) if r['phase'] in ('declared','resolving') and r['round']==e.round_no]


def path_choice(path,mode):
 import movement_actions as MOVE
 if mode not in MOVE.MODES or type(path) not in (tuple,list):raise ValueError('actual optional Shift path and movement mode required')
 if mode not in ('sky','levitate','shadow_surface'):return [MOVE._point(p) for p in path]
 from physical_limits import number
 result=[]
 for p in path:
  if type(p)is not dict or set(p) not in ({'position','altitude'},{'position','altitude','gm_distance'}):raise ValueError('actual aerial position, altitude and optional measured distance required')
  node=dict(p,position=MOVE._point(p['position']),altitude=number(p['altitude'],'actual Shift altitude',minimum=0))
  if 'gm_distance' in p:node['gm_distance']=number(p['gm_distance'],'actual measured Shift distance',minimum=0)
  result.append(node)
 return result


def declaration(e,actor,target=None,*,request_id,path=(),mode='land',reason):
 import world_entities as W,initiative_interrupts as I,priority_actions as PRIORITY,frequency as F,turn as TURN,movement_actions as MOVE
 W.require_actors(e,actor,*([target] if target is not None else []));policy(e.r)
 if not isinstance(request_id,str) or not request_id.strip() or not isinstance(reason,str) or not reason.strip():raise ValueError('actual Focus Punch declaration identity and reason required')
 points=path_choice(path,mode)
 intent={'target_id':target.entity_id if target is not None else None,'path':points,'mode':mode,'reason':reason}
 prior=next((r for r in actions(actor) if r['request_id']==request_id),None)
 if prior is not None:
  if prior['intent']!=intent:raise ValueError('Focus Punch replay cannot change intent')
  return deepcopy(prior)
 trigger=I.between_trigger(e)
 if trigger['schedule_cursor']!=0 or any(r['round']==e.round_no for r in actions(actor)) or any(c['round']==e.round_no for c in e._turn_closures):raise ValueError('Focus Punch is declared once at the actual round start')
 if PRIORITY.classify(e.r,SOURCE)!={'variant':'limited','move_id':SOURCE} or SOURCE not in actor.moves:raise ValueError('actual learned Priority Limited Focus Punch required')
 if __import__('vision_impairment').accuracy_level(e,actor)=='total':raise ValueError('Total Blindness prohibits Priority declaration')
 if not F.move_allowed(e,actor,SOURCE)[0]:raise ValueError('Focus Punch frequency unavailable')
 def apply(staged,a,*targets):
  request={'id':request_id,'actor_id':a.entity_id,'source':SOURCE,'priority':0,'mode':'reaction','payment':'next','budget':{'standard':1},'clock':'none'}
  queued=I.queue(staged,[request],trigger=I.between_trigger(staged));I.begin(staged,queued['window_id'],request_id)
  if not TURN.spend(staged,a,'standard',SOURCE):raise ValueError('Focus Punch declaration requires its Standard action')
  I.finish(staged)
  row={'request_id':request_id,'intent':deepcopy(intent),'round':staged.round_no,'source':SOURCE,'window_id':queued['window_id'],'damage_sequence':staged._heavy_sequence,'phase':'declared','shift_progress':{},'completion_id':None,'cancellation_event':None}
  row['declaration_fingerprint']=__import__('root_resolution').fingerprint({k:row[k] for k in ('request_id','intent','round','source','window_id','damage_sequence')})
  a.spec.setdefault(KEY,[]).append(row);staged.gm._rec('Focus Punch declaration',None,row,reason,a)
  return deepcopy(row)
 return G.transition(e,actor,apply,participants=(() if target is None else (target,)),include_rulings=True)


def active(e,actor):return next((r for r in reversed(actions(actor)) if r['round']==e.round_no and r['phase'] in ('declared','resolving')),None)


def authority(e,actor,target,move_id,source):
 row=active(e,actor)
 return bool(source==SOURCE and move_id==SOURCE and row and row['phase']=='resolving' and row.get('release_choice',{}).get('target_id')==target.entity_id)


def require_release(e,actor,move_id):
 if move_id==SOURCE and not (active(e,actor) and active(e,actor)['phase']=='resolving'):raise ValueError('Focus Punch requires its round-start declaration and round-end release')


def mechanics(rules,mid,mm):
 if mid!=SOURCE:return mm
 policy(rules);return {}


def begin_move(e,row):
 if row['move_id']!=SOURCE:return
 source=active(e,row['actor'])
 if source is None or source['phase']!='resolving':raise ValueError('actual Focus Punch release required')
 if source['completion_id'] not in (None,row['id']):raise ValueError('one native attack per Focus Punch declaration')
 source['completion_id']=row['id']


def cancellation(e,actor,row):
 for key,event in getattr(e,'_heavy_events',{}).items():
  if event['target'] is not actor or event['round']!=row['round'] or int(key.rsplit('-',1)[1])<=row['damage_sequence']:continue
  damage=event.get('focus_punch_damage')
  if damage is None:continue
  if damage.get('boundary')!='native_damage_after_cap_before_temporary_hp_and_hp_replacement' or type(damage.get('amount'))is not int or not 0<=damage['amount']<=event['amount'] or damage.get('maximum_hp')!=event['before']['real_max_hp']:raise ValueError('actual native Focus Punch damage observation changed')
  if damage['amount']*4>=damage['maximum_hp']:return key
 return None


def choose(e,actor,*,use,target=None,path=(),mode='land',request_id,reason):
 import world_entities as W,movement_actions as MOVE,initiative_schedule as S
 W.require_actors(e,actor,*([target] if target is not None else []))
 if type(use)is not bool or not isinstance(request_id,str) or not request_id.strip() or not isinstance(reason,str) or not reason.strip():raise ValueError('explicit Focus Punch round-end use or decline required')
 selected={'request_id':request_id,'use':use,'target_id':target.entity_id if target else None,'path':path_choice(path,mode),'mode':mode,'reason':reason}
 previous=next((r['release_choice'] for r in actions(actor) if r.get('release_choice',{}).get('request_id')==request_id),None)
 if previous is not None:
  if previous!=selected:raise ValueError('Focus Punch release replay cannot change intent')
  return deepcopy(previous)
 row=active(e,actor)
 if row is None or row['phase']!='declared' or row.get('release_choice') is not None:raise ValueError('one undecided actual Focus Punch declaration required')
 S.preflight_end_round(e)
 if e._active_turn_actor is not None or e.round_start_seconds is None:raise ValueError('Focus Punch choice requires the actual round-end boundary')
 if use:
  if target is None or target.dead or target.fainted or not target.on_field:raise ValueError('actual usable round-end Focus Punch target required')
 elif target is not None or path:raise ValueError('declined Focus Punch has no target or Shift')
 row['release_choice']=selected;row['release_fingerprint']=__import__('root_resolution').fingerprint(selected)
 e.gm._rec('Focus Punch round-end choice',None,selected,reason,actor)
 return deepcopy(selected)


def finish_round(e):
 import movement_actions as MOVE,action_lifecycle as ACTION,world_entities as W
 index=W.actor_index(e)
 for actor,row in pending(e):
  if row['completion_id'] is not None:
   completed=e._move_completions[row['completion_id']]
   if completed['phase']!='complete':raise ValueError('resume the actual pending Focus Punch attack first')
   row['phase']='complete';continue
  cancelled=cancellation(e,actor,row)
  if cancelled or actor.fainted or actor.dead or not actor.on_field:
   row['phase']='cancelled';row['cancellation_event']=cancelled;continue
  choice=row.get('release_choice')
  if choice is None:return __import__('common_checks').PendingDecision('At round end choose whether to use Focus Punch, its current target and optional Shift; declaration alone does not use the Move.')
  if not choice['use']:row['phase']='declined';continue
  target=index[choice['target_id']]
  if target.fainted or target.dead or not target.on_field:raise ValueError('selected round-end Focus Punch target is no longer usable')
  row['phase']='resolving'
  if choice['path']:
   maximum=MOVE.capabilities(e,actor).get(choice['mode'],0)
   MOVE.follow_paid_path(e,actor,choice['path'],mode=choice['mode'],maximum_distance=maximum,progress=row['shift_progress'])
   if row['shift_progress'].get('phase') in ('entry_pending','reaction_pending'):return __import__('common_checks').PendingDecision('complete the actual Focus Punch Shift interruption before resuming its retained path')
   cancelled=cancellation(e,actor,row)
   if cancelled:row['phase']='cancelled';row['cancellation_event']=cancelled;continue
  with ACTION.move_grant(e,actor,target,SOURCE,source=SOURCE,kind='free') as grant:
   e.use_move(actor,target,SOURCE,count_use=True,free_action=True,_action_grant=grant)
  if row['completion_id'] is None:raise ValueError('Focus Punch must create its actual native attack')
  if e._move_completions[row['completion_id']]['phase']=='complete':row['phase']='complete'


def end_round(e):
 actor,row=pending(e)[0];target=__import__('world_entities').actor_index(e).get(row.get('release_choice',{}).get('target_id'),actor)
 return __import__('reactive_ability_events').atomic_move(e,actor,target,lambda staged,a,t:staged._end_round())


def validate_world(e,index):
 for actor in index.values():
  requests=set()
  for row in actions(actor):
   if row.get('source')!=SOURCE or row.get('phase') not in ('declared','resolving','complete','cancelled','declined') or row['request_id'] in requests or (row['intent'].get('target_id') is not None and row['intent']['target_id'] not in index):raise ValueError('actual sourced Focus Punch declaration required')
   requests.add(row['request_id'])
   if row.get('declaration_fingerprint')!=__import__('root_resolution').fingerprint({k:row[k] for k in ('request_id','intent','round','source','window_id','damage_sequence')}):raise ValueError('Focus Punch actual declaration intent changed')
   window=getattr(e,'_initiative_interrupts',{}).get('windows',{}).get(row['window_id'])
   request=next((x for x in window['requests'] if x['id']==row['request_id']),None) if window else None
   if request is None or request['source']!=SOURCE or request['actor'] is not actor or request['status']!='completed' or request['receipt']['actions']!=['standard'] or request['receipt']['round']!=row['round']:raise ValueError('Focus Punch needs its actual paid Priority Limited declaration')
   choice=row.get('release_choice')
   if choice is not None and (row.get('release_fingerprint')!=__import__('root_resolution').fingerprint(choice) or type(choice.get('use'))is not bool or (choice['use'] and choice.get('target_id') not in index)):raise ValueError('actual Focus Punch round-end choice changed')
   if row['phase'] in ('resolving','complete') and (choice is None or choice['use'] is not True):raise ValueError('Focus Punch requires its explicit round-end use choice')
   if row['phase']=='declined' and (choice is None or choice['use'] is not False):raise ValueError('actual Focus Punch decline required')
   if row['completion_id'] is not None:
    move=getattr(e,'_move_completions',{}).get(row['completion_id'])
    if move is None or move['actor'] is not actor or move['move_id']!=SOURCE or move['round']!=row['round']:raise ValueError('Focus Punch actual release completion changed')
   if row['phase']=='complete' and (row['completion_id'] is None or move['phase']!='complete'):raise ValueError('Focus Punch cannot complete without native attack')
   if row['cancellation_event'] is not None and cancellation(e,actor,row)!=row['cancellation_event']:raise ValueError('Focus Punch cancellation requires one actual qualifying hit to its user')


def reaction_origin(e,event_id,*,live):
 event=getattr(e,'_passive_events',{}).get(event_id)
 if event is None or event.get('producer')!='Engine.use_move' or event.get('move_id')!=SOURCE:return None
 actor=event['actor'];rows=[r for r in actions(actor) if r['completion_id']==event.get('completion_id') and r['round']==event['round']]
 if len(rows)!=1:return None
 row=rows[0];move=getattr(e,'_move_completions',{}).get(row['completion_id'])
 if move is None or move['actor'] is not actor or move['move_id']!=SOURCE:return None
 if live and (row['phase']!='resolving' or event['phase']!='accuracy_boundary' or e._active_turn_actor is not None):return None
 return {'source':SOURCE,'actor_id':actor.entity_id,'request_id':row['request_id'],'completion_id':row['completion_id'],'declaration_fingerprint':row['declaration_fingerprint']}


from contextlib import contextmanager
@contextmanager
def damage_scope(e,target):
 if active(e,target) is None:
  yield None;return
 previous=getattr(target,'_focus_punch_damage_observation',None)
 observed={};target._focus_punch_damage_observation=observed
 try:yield observed
 finally:
  if previous is None:del target._focus_punch_damage_observation
  else:target._focus_punch_damage_observation=previous


def observe_damage(target,amount):
 observed=getattr(target,'_focus_punch_damage_observation',None)
 if observed is not None:
  if observed:raise ValueError('one native HP leaf per Focus Punch damage observation')
  observed.update(amount=amount,maximum_hp=target.base_max_hp,boundary='native_damage_after_cap_before_temporary_hp_and_hp_replacement')
