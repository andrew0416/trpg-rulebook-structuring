"""Actual sleep episodes, observed dreams and source-restricted viewing."""
from copy import deepcopy
import common_checks as C,state_grants as G,skill_modifiers as S
KEY='dream_sleep_state'
SOURCE='capability/꿈읽기'
MIST_SOURCES=('item/꿈안개','item/꿈안개-1')


def validate(actor):
 row=actor.spec.get(KEY)
 if row is None:return None
 if not isinstance(row,dict) or 'active' not in row:raise ValueError('explicit dream sleep episode envelope required')
 C.integer(row.get('serial'),'sleep episode serial',1)
 active=row['active']
 if active is not None:
  if not isinstance(active,dict) or active.get('serial')!=row['serial'] or 'dream' not in active:raise ValueError('current sleep episode identity mismatch')
  if '잠듦' not in actor.conditions:raise ValueError('awake actor cannot retain an active dream episode')
  if active.get('source') is not None and (not isinstance(active['source'],str) or not active['source']):raise ValueError('explicit sleep source or unknown required')
  mist=active.get('mist')
  if mist is not None:
   # Only the native Dream Mist item attack writes this address of its applied payment.
   if (not isinstance(mist,dict) or set(mist)!={'payer_id','stock_receipt_id'} or active.get('source') not in MIST_SOURCES
       or any(not isinstance(mist[k],str) or not mist[k] for k in mist) or not active.get('episode_id')):
    raise ValueError('Dream Mist sleep proof must name its actual applied payment')
  if active['dream'] is not None:
   dream=active['dream']
   if not isinstance(dream,dict) or dream.get('source')!=SOURCE or any(not isinstance(dream.get(k),str) or not dream[k].strip() for k in ('content','reason')):raise ValueError('sourced observed dream required')
 return row


def applied(actor,source):
 previous=actor.spec.get(KEY,{});serial=previous.get('serial',0)+1
 import state_episodes as EPISODES
 if previous.get('active'):cured(actor)
 actual_source=source if isinstance(source,str) and source else None
 episode=EPISODES.start(actor,family='dream_sleep',source=actual_source,native_ref={'field':KEY,'serial':serial})
 actor.spec[KEY]={'serial':serial,'active':{'serial':serial,'source':actual_source,'dream':None,'episode_id':episode}}


def bind_mist(engine,user,payment,target,*,source,serial_before,deferred_before=()):
 """Native Dream Mist item attack only: link its paid stock to the sleep episode it applied.

 A source label alone (apply_status, GM state, legacy save) is not proof that Dream Mist
 caused the current sleep; only this exact applied payment lets Dream Reader share it.
 """
 import consumption_execution as EXECUTION,field_effects as FIELD
 if source not in MIST_SOURCES:raise ValueError('Dream Mist source required')
 active=(target.spec.get(KEY) or {}).get('active')
 new_sleep=bool(active and active['serial']==serial_before+1 and active.get('source')==source and '잠듦' in target.conditions)
 deferred=[(n,row) for n,row in enumerate(FIELD._pending(target)) if row not in deferred_before
           and row['condition']=='잠듦' and row['source']==source and row['applied_by_id']==user.entity_id]
 if not new_sleep and not deferred:return None
 if len(deferred)>1:raise ValueError('one actual deferred Dream Mist application required')
 rows=[row for row in EXECUTION.validate(user).values() if row['item_stock'] is payment]
 if len(rows)!=1 or rows[0]['outcome']!='paid' or rows[0]['item_stock'].get('item_id')!=source:
  raise ValueError('actual original Dream Mist stock payment required')
 receipt_id=rows[0]['receipt_id']
 if not new_sleep:
  n,pending=deferred[0]
  def defer(e,t,u):
   paid=EXECUTION.validate(u)[receipt_id]
   proof={'payer_id':u.entity_id,'stock_receipt_id':receipt_id,'serial_before':serial_before}
   FIELD._pending(t)[n]['dream_mist']=proof
   EXECUTION.defer(u,paid['item_stock'],target_id=t.entity_id,results=_deferred_result(t,FIELD._pending(t)[n]))
   validate_deferred(e,t,FIELD._pending(t)[n])
   return deepcopy(proof)
  return G.transition(engine,target,defer,participants=(user,))
 episode_id=active['episode_id']
 def apply(e,t,u):
  current=t.spec[KEY]['active']
  paid=EXECUTION.validate(u)[receipt_id]
  EXECUTION.finish(u,paid['item_stock'],target_id=t.entity_id,outcome='applied',
                   results=[{'kind':'dream_sleep_episode','id':episode_id}])
  current['mist']={'payer_id':u.entity_id,'stock_receipt_id':receipt_id}
  validate(t)
  return deepcopy(current['mist'])
 return G.transition(engine,target,apply,participants=(user,))


def _deferred_result(target,pending):
 import resolution_transaction as TX
 return [{'kind':'dream_deferred_sleep','id':TX.request_fingerprint({'target_id':target.entity_id,'pending':pending})}]


def validate_deferred(engine,target,pending):
 """Validate the actual paid hit that owns this delayed sleep, before resuming it."""
 if 'dream_mist' not in pending:return None
 proof=pending['dream_mist']
 import consumption_execution as EXECUTION,world_entities as W
 if (not isinstance(proof,dict) or set(proof)!={'payer_id','stock_receipt_id','serial_before'}
     or any(not isinstance(proof[k],str) or not proof[k] for k in ('payer_id','stock_receipt_id'))
     or pending['condition']!='잠듦' or pending['source'] not in MIST_SOURCES
     or proof['payer_id']!=pending['applied_by_id']):
  raise ValueError('actual deferred Dream Mist payment required')
 C.integer(proof['serial_before'],'prior Dream Mist sleep serial',0)
 payer=W.actor_index(engine).get(proof['payer_id'])
 receipt=EXECUTION.validate(payer).get(proof['stock_receipt_id']) if payer is not None else None
 if (not receipt or receipt['outcome']!='deferred' or receipt['target_id']!=target.entity_id
     or receipt['item_stock'].get('item_id')!=pending['source']
     or receipt['results']!=_deferred_result(target,pending)):
  raise ValueError('deferred Dream Mist lost its actual paid hit')
 return payer,receipt


def finish_deferred(engine,target,pending,*,applied=False,serial_before=None):
 observed=validate_deferred(engine,target,pending)
 if observed is None:return
 import consumption_execution as EXECUTION
 payer,receipt=observed;proof=pending['dream_mist']
 active=(target.spec.get(KEY) or {}).get('active')
 linked=bool(applied and active and serial_before==proof['serial_before']
             and active['serial']==serial_before+1 and active['source']==pending['source']
             and '잠듦' in target.conditions)
 def finish(e,t,u):
  import field_effects as FIELD
  kept=[row for row in FIELD._pending(t) if row!=pending]
  if kept:t.custom_conditions[FIELD.DEFERRED]=kept
  else:t.custom_conditions.pop(FIELD.DEFERRED,None)
  paid=EXECUTION.validate(u)[receipt['receipt_id']]
  results=[{'kind':'dream_sleep_episode','id':active['episode_id']}] if linked else []
  EXECUTION.finish(u,paid['item_stock'],target_id=t.entity_id,outcome='applied' if linked else 'no_effect',results=results)
  if linked:
   t.spec[KEY]['active']['mist']={k:proof[k] for k in ('payer_id','stock_receipt_id')}
   validate(t)
 return G.transition(engine,target,finish,participants=(payer,))


def mist_proven(engine,target,active):
 """The current episode was applied by an actual paid Dream Mist item attack."""
 import consumption_execution as EXECUTION,world_entities as W
 mist=active.get('mist') if active else None
 if mist is None or active.get('source') not in MIST_SOURCES:return False
 payer=W.actor_index(engine).get(mist['payer_id'])
 if payer is None:return False
 row=EXECUTION.validate(payer).get(mist['stock_receipt_id'])
 return bool(row and row['outcome']=='applied' and row['target_id']==target.entity_id
             and row['item_stock'].get('item_id')==active['source']
             and row['results']==[{'kind':'dream_sleep_episode','id':active.get('episode_id')}])


def cured(actor,*,episode_id=None):
 import state_episodes as EPISODES
 current=actor.spec.get(KEY,{}).get('active')
 if current is None:return
 if episode_id is not None and current.get('episode_id')!=episode_id:
  EPISODES.require(actor,episode_id,family='dream_sleep')
  return # An old episode reply cannot cure a newer sleep.
 identity=current.get('episode_id')
 if identity is None:
  identity=EPISODES.start(actor,family='dream_sleep',source=current.get('source'),native_ref={'field':KEY,'serial':current['serial']})
  current['episode_id']=identity
 EPISODES.require(actor,identity,family='dream_sleep')
 EPISODES.end(actor,identity,cause='sleep_cured',cleanup=lambda:actor.spec[KEY].__setitem__('active',None))


def actual(engine,*actors):
 import world_entities as W
 index=W.actor_index(engine)
 if any(index.get(c.entity_id)is not c for c in actors):raise ValueError('actual dream participants required')


def observe(engine,target,content,*,reason):
 actual(engine,target)
 if '잠듦' not in target.conditions:raise ValueError('sleeping dream subject required')
 if any(not isinstance(x,str) or not x.strip() for x in (content,reason)):raise ValueError('current dream content and observation reason required')
 validate(target)
 def apply(e,c):
  if not c.spec.get(KEY,{}).get('active'):applied(c,None) # Legacy sleep does not prove Dream Mist.
  c.spec[KEY]['active']['dream']={'source':SOURCE,'content':content,'reason':reason}
  validate(c);e.gm._rec('dream observation',None,c.spec[KEY],reason,c)
  return deepcopy(c.spec[KEY])
 return G.transition(engine,target,apply)


def read(engine,reader,target,*,share=False):
 actual(engine,reader,target)
 if type(share)is not bool:raise ValueError('explicit dream sharing choice required')
 names={S.key(x) for x in G.effective_capabilities(reader)}
 if not names.intersection(S.key(x) for x in ('꿈읽기','Dream Reader',SOURCE)):raise ValueError('current Dream Reader capability required')
 if reader.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Dream Reader needs its own contract')
 blocked={S.key(x) for x in G.effective_capabilities(target)}
 if blocked.intersection(S.key(x) for x in ('정신봉인','Mindlock','capability/정신봉인')):
  if target.r._selected_rule('capability/정신봉인')!='capability/정신봉인':raise ValueError('selected Mindlock needs its own contract')
  raise ValueError('Mindlock prevents dream reading and sharing')
 if '잠듦' not in target.conditions:raise ValueError('sleeping dream subject required')
 row=validate(target);active=row['active'] if row else None
 if share and not mist_proven(engine,target,active):raise ValueError('sharing requires this actual sleep episode to originate from Dream Mist')
 if active is None or active['dream'] is None:return C.PendingDecision('current dream content has not been observed')
 return {'source':SOURCE,'reader_id':reader.entity_id,'target_id':target.entity_id,'sleep_serial':active['serial'],'sleep_source':active['source'],
         'content':active['dream']['content'],'mode':'brief_moving_image' if share else 'private_dream_reading'}
