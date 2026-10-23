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
 if share and (not active or active['source'] not in MIST_SOURCES):raise ValueError('sharing requires this actual sleep episode to originate from Dream Mist')
 if active is None or active['dream'] is None:return C.PendingDecision('current dream content has not been observed')
 return {'source':SOURCE,'reader_id':reader.entity_id,'target_id':target.entity_id,'sleep_serial':active['serial'],'sleep_source':active['source'],
         'content':active['dream']['content'],'mode':'brief_moving_image' if share else 'private_dream_reading'}
