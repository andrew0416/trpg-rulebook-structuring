"""Pair-specific willing surface-thought exchange, separate from Telepathy."""
from copy import deepcopy
import common_checks as C,state_grants as G,skill_modifiers as S
KEY='aura_pulse_state'
SOURCE='capability/파동술'


def text(value,label):
 if not isinstance(value,str) or not value.strip():raise ValueError(label+' required')
 return value


def validate(actor):
 row=actor.spec.get(KEY)
 if row is None:return None
 if not isinstance(row,dict) or row.get('source')!=SOURCE:raise ValueError('Aura Pulse state source mismatch')
 if actor.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Aura Pulse needs its own contract')
 if 'surface' not in row:raise ValueError('surface thought must be explicit, including unknown state')
 if not isinstance(row.get('open_to'),dict) or not isinstance(row.get('received'),list):raise ValueError('identified Aura Pulse relationships and receipts required')
 for uid,permission in row['open_to'].items():
  text(uid,'reader identity')
  if uid==actor.entity_id or not isinstance(permission,dict) or type(permission.get('allowed')) is not bool:raise ValueError('another identified reader and explicit willingness required')
  C.integer(permission.get('revision'),'willingness revision',1);text(permission.get('reason'),'willingness declaration reason')
 thought=row.get('surface')
 if thought is not None:
  if not isinstance(thought,dict):raise ValueError('observed surface thought required')
  text(thought.get('text'),'observed surface thought');text(thought.get('reason'),'thought observation reason');C.integer(thought.get('revision'),'thought revision',1)
 for number,message in enumerate(row['received'],1):
  if not isinstance(message,dict) or message.get('source')!=SOURCE or message.get('recipient_id')!=actor.entity_id:raise ValueError('actual sourced thought receipt required')
  C.integer(message.get('sequence'),'message sequence',number,number)
  text(message.get('sender_id'),'actual thought sender');text(message.get('text'),'projected thought')
  if message['sender_id']==actor.entity_id:raise ValueError('thought communication requires another actor')
 return row


def state(actor):
 row=validate(actor)
 if row is not None:return row
 import perception_observe as O
 actor.spec[KEY]={'source':SOURCE,'open_to':{},'surface':deepcopy(O.current_thought(actor)),'received':[]}
 return actor.spec[KEY]


def validate_world(engine,index):
 for actor in index.values():
  row=validate(actor)
  if row is None:continue
  identities=set(row['open_to'])|{x['sender_id'] for x in row['received']}
  if not identities<=set(index):raise ValueError('Aura Pulse relationship must resolve to actual actors')
 return True


def actual(engine,*actors):
 import world_entities as W
 index=W.actor_index(engine)
 if any(index.get(c.entity_id)is not c for c in actors):raise ValueError('actual Aura Pulse participants required')
 if len({id(c) for c in actors})!=len(actors):raise ValueError('Aura Pulse requires distinct participants')
 return index


def require_capability(actor):
 names={S.key(x) for x in G.effective_capabilities(actor)}
 if not names.intersection(S.key(x) for x in ('파동술','Aura Pulse',SOURCE)):raise ValueError('current Aura Pulse capability required')
 if actor.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Aura Pulse needs its own contract')


def willingness(engine,target,reader,allowed,*,reason):
 actual(engine,target,reader)
 if type(allowed)is not bool:raise ValueError('explicit voluntary willingness required')
 text(reason,'willingness declaration reason')
 def apply(e,c,other):
  row=state(c);old=row['open_to'].get(other.entity_id)
  permission={'allowed':allowed,'reason':reason,'revision':(old['revision'] if old else 0)+1}
  row['open_to'][other.entity_id]=permission;validate(c)
  e.gm._rec('Aura Pulse willingness',old,permission,reason,c)
  return deepcopy(permission)
 return G.transition(engine,target,apply,participants=(reader,))


def observe_thought(engine,target,thought,*,reason):
 import perception_observe as O
 return O.observe_thought(engine,target,thought,reason=reason)


def project(engine,sender,recipient,thought):
 import perception_communicate as COMM
 return COMM.native_pulse(engine,sender,recipient,thought)


def read(engine,reader,target):
 actual(engine,reader,target);require_capability(reader);row=validate(target)
 permission=row['open_to'].get(reader.entity_id) if row else None
 if not permission or not permission['allowed']:raise ValueError('target has not willingly opened their mind to this reader')
 if row['surface'] is None:return C.PendingDecision('current surface thought has not been observed')
 import perception_observe as OBSERVE
 sensed=OBSERVE.observe(engine,reader,target,OBSERVE.native(SOURCE,('파동술','Aura Pulse',SOURCE),provider='surface',information=('surface_thought',)))
 return {'source':SOURCE,'reader_id':reader.entity_id,'target_id':target.entity_id,'willingness_revision':permission['revision'],
         'surface_thought':sensed['values']['surface_thought'],'thought_revision':row['surface']['revision']}
