"""Actual same-trigger Snatch responses on the existing ordered native window.

Ordering is not a rule deciding the winner of two successful replacements.
Multiple successes wait for an explicit GM occurrence decision; no default
first/last winner and no invented Snatch-on-Snatch trigger.
"""
from copy import deepcopy
from contextlib import contextmanager
import combat_move_reactions as R
import initiative_interrupts as I
import passive_events as P
import world_entities as W
import state_grants as G
import move_completion as MC

ORDER='snatch_response_order'
PLAN='snatch_responses'


def _armed(e,target):
 return [a for a in W.actor_index(e).values()
         if a.spec.get(R.CHOICES,{}).get(R.SNATCH,{}).get('target_id')==target.entity_id]


def order(e,target,responders,*,reason):
 P.ensure_clear(e);W.require_actors(e,target,*responders)
 G._text(reason,'explicit simultaneous Snatch order reason')
 ids=[a.entity_id for a in responders]
 if len(ids)<2 or len(ids)!=len(set(ids)) or set(ids)!={a.entity_id for a in _armed(e,target)}:
  raise ValueError('exact explicit simultaneous Snatch responder order required')
 row={'target_id':target.entity_id,'actor_ids':ids,'reason':reason}
 def apply(se,owner):
  owner.spec[ORDER]=deepcopy(row)
  return deepcopy(row)
 return G.transition(e,target,apply)


def _record(e,row):
 plan=row.get(PLAN)
 if plan is None:return None
 if type(plan)is not dict or set(plan)!={'event_id','window_id','selection'}:
  raise ValueError('actual Snatch response window binding required')
 event=e._passive_events.get(plan['event_id'])
 window=getattr(e,I.KEY,{}).get('windows',{}).get(plan['window_id'])
 if (event is None or event['actor'] is not row['actor'] or event['target'] is not row['actor']
     or event.get('completion_id')!=row['id'] or window is None):
  raise ValueError('Snatch response window lost its original Self trigger')
 if not R._self_move(e,row['actor'],row['move']):
  raise ValueError('Snatch responses require the actual original printed Self Move')
 requests=window['requests']
 if not requests or len({x['actor'].entity_id for x in requests})!=len(requests):
  raise ValueError('distinct actual Snatch responders required')
 native=[]
 for request in requests:
  owner=request['actor'];reaction=R._event(owner,request['id'])
  if (request['source']!=R.SNATCH or request.get('move_id')!=R.SNATCH or reaction is None
      or reaction['completion_id']!=row['id'] or reaction['attacker_id']!=row['actor'].entity_id
      or reaction['target_id']!=row['actor'].entity_id or reaction['kind']!='self_move'):
   raise ValueError('Snatch queue request belongs to another actual trigger')
  R.validate_event(e,owner,reaction);native.append((owner,reaction,request))
 matched={r['id'] for a in W.actor_index(e).values() for r in a.spec.get(R.EVENTS,{}).values()
          if r['source']==R.SNATCH and r['completion_id']==row['id']}
 if matched!={r['id'] for _,r,_ in native}:
  raise ValueError('Snatch window omitted or duplicated an actual response')
 selected=plan['selection']
 if selected is not None:
  if type(selected)is not dict or set(selected)!={'reaction_id','reason'}:
   raise ValueError('explicit actual Snatch recipient decision required')
  G._text(selected['reason'],'actual Snatch recipient decision reason')
  winners=_successful(e,native)
  if (window['cursor']!=len(requests) or len(winners)<2
      or selected['reaction_id'] not in {r['id'] for _,r,_ in winners}):
   raise ValueError('Snatch recipient decision does not match multiple completed successes')
 routes=[state['source_route'] for state in row.get('defense',{}).values()
         if state.get('source_route',{}).get('source')==R.SNATCH]
 if routes:
  winners=_successful(e,native)
  expected=(winners[0][1]['id'] if len(winners)==1 else
            selected['reaction_id'] if selected is not None else None)
  if (window['cursor']!=len(requests) or len(routes)!=1 or expected is None
      or routes[0]['reaction_id']!=expected):
   raise ValueError('Snatch applied recipient differs from its actual response decision')
 return plan,window,native


def _successful(e,native):
 winners=[]
 for owner,reaction,request in native:
  if request['status']!='completed' or reaction['status']!='complete':continue
  response=e._move_completions[reaction['result_completion']]
  target=W.actor_index(e)[reaction['attacker_id']]
  received=MC.recipient_result(response,target)
  if received and received['hit'] and not received.get('cancelled'):
   winners.append((owner,reaction,request))
 return winners


def validate(e,index):
 for actor in index.values():
  selected=actor.spec.get(ORDER)
  if selected is not None:
   if (type(selected)is not dict or set(selected)!={'target_id','actor_ids','reason'}
       or selected['target_id']!=actor.entity_id or type(selected['actor_ids'])is not list
       or len(selected['actor_ids'])<2 or len(selected['actor_ids'])!=len(set(selected['actor_ids']))
       or any(uid not in index for uid in selected['actor_ids'])):
    raise ValueError('actual simultaneous Snatch order actors required')
   G._text(selected['reason'],'actual simultaneous Snatch order reason')
 for row in getattr(e,'_move_completions',{}).values():
  if PLAN in row:_record(e,row)


def require_window(e,event,window_id):
 row=e._move_completions[event['completion_id']]
 bound=_record(e,row)
 if bound is None or bound[0]['window_id']!=window_id:
  raise ValueError('Snatch requires its actual ordered native response window')
 plan,window,native=bound
 if (window['cursor']>=len(native) or native[window['cursor']][1]['id']!=event['id']
     or event['source']!=R.SNATCH):
  raise ValueError('only the next actual Snatch response may execute')


@contextmanager
def _without_responder_scopes(e,responders):
 """Scopes captured from a suspended Snatch response are not live while the next queued response runs."""
 scopes=getattr(e,'_event_use_scopes',None)
 stale=[] if scopes is None else [s for s in scopes if any(s.get('actor') is r for r in responders)]
 if not stale:
  yield;return
 e._event_use_scopes=[s for s in scopes if not any(s is x for x in stale)]
 try:yield
 finally:e._event_use_scopes=scopes


def _queue(e,args,candidates):
 actor=args['attacker'];row=e._move_completions[args['completion_id']]
 ids={a.entity_id for a in candidates};choice=actor.spec.get(ORDER)
 if len(candidates)>1:
  if choice is None or set(choice['actor_ids'])!=ids:
   raise ValueError('exact explicit simultaneous Snatch order required before response payment')
  by_id={a.entity_id:a for a in candidates};candidates=[by_id[uid] for uid in choice['actor_ids']]
 R.snatch_preflight(e,args)
 reactions=[(a,R._observe(e,a,R.SNATCH,actor,actor,args['move'],'self_move',row['id'])) for a in candidates]
 parent=e._active_turn_actor;outer=I.frame(e)
 trigger=({'kind':'reaction','window_id':outer['window_id'],'request_id':outer['request_id']} if outer else
          {'kind':'turn','actor_id':parent.entity_id,'serial':parent.custom_conditions.get('combat_turn_serial',0),'round':e.round_no})
 requests=[{'id':r['id'],'actor_id':a.entity_id,'source':R.SNATCH,'move_id':R.SNATCH,
            'priority':0,'mode':'reaction','payment':'next','budget':{'standard':1},'clock':'none'}
           for a,r in reactions]
 queued=I.queue(e,requests,trigger=trigger,order=[r['id'] for _,r in reactions])
 if queued['status'] not in ('queued','already_queued'):
  raise ValueError('actual explicit Snatch order was not admitted')
 row=e._move_completions[args['completion_id']]
 row[PLAN]={'event_id':args['passive_event'],'window_id':queued['window_id'],'selection':None}
 row['actor'].spec.pop(ORDER,None)
 return _record(e,row)


def react(e,args):
 import body_state as BODY,move_defense_reactions as D
 actor,target,move=(args[k] for k in ('attacker','target','move'))
 row=e._move_completions[args['completion_id']]
 if not R.snatch_interested(e,actor,target) and PLAN not in row:return
 if actor is not target or not R._self_move(e,actor,move):return
 bound=_record(e,row)
 if D.routed(e,args['passive_event']):
  state=D._defense(e,e._passive_events[args['passive_event']])
  if state.get('source_route',{}).get('source')==R.SNATCH:return
  D.require_snatch_route(e,args)
 if bound is None:
  # Old completed single-response saves retain their existing proof and API.
  old=[(a,r) for a in W.actor_index(e).values() for r in a.spec.get(R.EVENTS,{}).values()
       if r['source']==R.SNATCH and r['completion_id']==row['id']]
  if old:
   if len(old)!=1 or old[0][1]['status']!='complete':
    raise ValueError('actual original Snatch response must complete')
   owner,reaction=old[0];R.validate_event(e,owner,reaction)
   received=MC.recipient_result(e._move_completions[reaction['result_completion']],actor)
   if received and received['hit'] and not received.get('cancelled'):
    D.source_route(e,args,owner,{'source':R.SNATCH,'actor_id':owner.entity_id,
     'reaction_id':reaction['id'],'response_completion':reaction['result_completion']})
   return
  candidates=[a for a in _armed(e,actor) if BODY.in_range(e,a,actor,6) and R._ready(e,a,R.SNATCH)]
  if not candidates:return
  bound=_queue(e,args,candidates)
 plan,window,native=bound
 while window['cursor']<len(window['requests']):
  owner,reaction,request=native[window['cursor']]
  if reaction['status']=='resolving':raise ValueError('actual retained Snatch response has not returned')
  if not BODY.in_range(e,owner,actor,6) or not R._ready(e,owner,R.SNATCH):
   reaction['status']='unavailable';R._seal(reaction)
   I.decline(e,window['id'],reaction['id'],source=R.SNATCH,reason='actual responder no longer eligible or in range')
  else:
   with _without_responder_scopes(e,[o for o,_,_ in native]):R._run(e,owner,actor,reaction,window_id=window['id'])
  row=e._move_completions[args['completion_id']]
  plan,window,native=_record(e,row)
 winners=_successful(e,native)
 if not winners:return
 if len(winners)==1:owner,reaction,_=winners[0]
 elif plan['selection'] is None:
  return P._pending(e,e._passive_events[args['passive_event']],'actual_simultaneous_snatch_recipient')
 else:
  owner,reaction,_=next(x for x in winners if x[1]['id']==plan['selection']['reaction_id'])
 D.source_route(e,args,owner,{'source':R.SNATCH,'actor_id':owner.entity_id,
  'reaction_id':reaction['id'],'response_completion':reaction['result_completion']})


def choose(e,event_id,recipient,*,reason):
 """Resolve this observed multiple-success occurrence, never a global default."""
 W.require_actors(e,recipient);G._text(reason,'actual simultaneous Snatch adjudication')
 event=e._passive_events.get(event_id)
 if (event is None or e._passive_pending!=event_id or event['phase']!='accuracy_boundary'
     or event.get('reason')!='actual_simultaneous_snatch_recipient'):
  raise ValueError('actual simultaneous Snatch recipient choice required')
 row=e._move_completions[event['completion_id']];bound=_record(e,row)
 if bound is None:raise ValueError('actual ordered Snatch response window required')
 plan,window,native=bound;winners=_successful(e,native)
 choices=[r for owner,r,_ in winners if owner is recipient]
 if window['cursor']!=len(native) or len(winners)<2 or len(choices)!=1 or plan['selection'] is not None:
  raise ValueError('one undecided actual successful Snatch recipient required')
 selection={'reaction_id':choices[0]['id'],'reason':reason};pending=[]
 def apply(se,owner):
  actual=se._move_completions[row['id']][PLAN]
  actual['selection']=deepcopy(selection)
  try:return P.deliver(se,event_id)
  except Exception as error:
   if G.record_native_pending(se,error,pending):return None
   raise
 result=G.transition(e,recipient,apply,include_grid=e.grid is not None,include_rulings=True)
 if pending:
  exception,identity=pending[0];raise exception(identity)
 return result

