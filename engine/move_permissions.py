"""Exact source temporary use permissions, distinct from learned move slots."""
from pathlib import Path
from copy import deepcopy
import hashlib,json


def policies(rules):
 return json.loads((Path(rules.root)/'data/category2-move-permission-policy.json').read_text(encoding='utf8'))['policies']


def registration(rules,name):
 rows=policies(rules)
 matches=[(uid,row) for uid,row in rows.items() if name in (uid,row['name'])]
 if not matches:return None
 uid,row=matches[0]
 actual=next((x for x in json.loads((Path(rules.root)/'output/entities/abilities.json').read_text(encoding='utf8')) if x.get('id')==uid),None)
 if actual is None or {k:actual.get(k) for k in row['definition']}!=row['definition']:raise ValueError('temporary move permission source changed; review required')
 if rules._selected_rule(uid)!=uid:raise ValueError('selected permission source requires a distinct policy')
 return {'name':row['name'],'source_id':uid,'permission_mode':row['mode']}


def deferred_registration(rules,effect):
 row=policies(rules).get(effect.get('_rule_id'))
 return row is not None and effect.get('type') in ('form_change','grant_move')


def form_policy(rules,source):
 row=policies(rules).get(source)
 if row is None or row['mode']!='scene_form':return None
 registration(rules,source)
 return row


def preflight_grant(engine,actor,effect,source,ctx=None):
 if policies(engine.r).get(source,{}).get('mode')=='mounted_turn':raise ValueError('Rider move permission requires its native mount and turn selection')
 row=form_policy(engine.r,source)
 if row is None:return None
 import state_grants as G
 if G.move_grants(engine.r,effect)!=[engine.r.move_id(n) for n in row['moves']]:raise ValueError('temporary form permission must use the full exact source move list')
 marker=(ctx or {}).get('form_permission_activation')
 if marker!=source or actor.custom_conditions.get('_form_permission_activation')!=source:raise ValueError('temporary form moves require the native paid form activation')
 return row


def activate_form(engine,actor,ability):
 """Pay the actual Scene/Swift activation and own form plus use permissions."""
 reg=registration(engine.r,ability)
 if reg is None:raise ValueError('actual form permission ability required')
 uid=reg['source_id'];row=form_policy(engine.r,uid)
 if row is None:raise ValueError('this source requires its separate mount/turn selection adapter')
 if not any(registration(engine.r,a) and registration(engine.r,a)['name']==reg['name'] for a in actor.abilities):raise ValueError('actual acquired form ability required')
 if actor.abilities_suppressed:raise ValueError('suppressed ability cannot activate')
 import state_grants as G
 def apply(e,c):
  import frequency as F,turn as TURN,combat_timing as TIMING,effects_ext as EXT
  key='ability:'+reg['name']
  if not F.activation_allowed(c,key,row['definition']['frequency'],engine=e):raise ValueError('form ability scene frequency exhausted')
  active=[x for x in TIMING.records(c) if x.get('permission_ability')==reg['name']]
  if active:raise ValueError('form permission is already active')
  if not TURN.spend(e,c,'swift',reg['name']):raise ValueError('form activation requires its Swift action')
  F.consume_activation(c,key,row['definition']['frequency'],engine=e)
  scene=c.spec['frequency_state']['scene'];grant_source=key+':form:'+str(scene)
  G.scalar(c,'form','달마모드',grant_source)
  ctx={'source_id':uid,'form_permission_activation':uid,'permission_source':grant_source,'attacker':c,'target':c,'engine':e}
  c.custom_conditions['_form_permission_activation']=uid
  try:EXT.h_grant_move(e,c,c,{'type':'grant_move','moves':row['moves']},ctx)
  finally:c.custom_conditions.pop('_form_permission_activation',None)
  TIMING.install(e,c,{'source':uid,'grant_source':grant_source,'permission_ability':reg['name'],'scene_only':True})
  return {'source':uid,'grant_source':grant_source,'moves':list(row['moves']),'ends':'scene_end'}
 return G.transition(engine,actor,apply)


def end_ability(engine,actor,canonical):
 import combat_timing as TIMING
 for row in list(TIMING.records(actor)):
  if row.get('permission_ability')==canonical:TIMING.expire(engine,actor,row)


RIDER='찬란한라이더'


def activate_rider(engine,actor,move_id):
 """Borrow one actual mount's learned move through this rider's current turn."""
 import move_state as M,world_entities as W,state_grants as G
 reg=next((registration(engine.r,value) for value in actor.abilities if registration(engine.r,value) and registration(engine.r,value)['name']==RIDER),None)
 if reg is None or actor.abilities_suppressed:raise ValueError('actual unsuppressed Splendorous Rider required')
 if not engine.encounter_active or getattr(engine,'_active_turn_actor',None) is not actor:raise ValueError('Rider activation requires its actual current turn')
 mount=W.actor_index(engine).get(actor.spec.get('mount_id'))
 if mount is None or mount is actor:raise ValueError('actual currently mounted Pokemon required')
 mid=engine.r.move_id(move_id)
 if mid is None or mid not in M.known(engine.r,{'moves':M.owned_list(mount.spec,'moves',mount.moves)}):raise ValueError('chosen move must be learned by the actual mount')
 if mid in M.known(engine.r,{'moves':M.owned_list(actor.spec,'moves',actor.moves)}):raise ValueError('Rider may select only a move the user has not learned')
 def apply(e,c,donor):
  import frequency as F,turn as TURN,combat_timing as TIMING
  uid=reg['source_id'];row=policies(e.r)[uid];key='ability:'+RIDER
  if not F.activation_allowed(c,key,row['definition']['frequency'],engine=e):raise ValueError('Rider scene frequency exhausted')
  for other in TIMING.records(c):
   if other.get('permission_ability')==RIDER:raise ValueError('existing Rider selection must finish its turn before another selection')
  if any(F.state(c)[field]!=F.state(donor)[field] for field in ('day','scene')):raise ValueError('Rider and mount frequency calendars must agree')
  if not TURN.spend(e,c,'swift',RIDER):raise ValueError('Rider activation requires its Swift action')
  F.consume_activation(c,key,row['definition']['frequency'],engine=e)
  serial=c.custom_conditions.get('combat_turn_serial',0);grant_source=key+':turn:'+str(F.state(c)['scene'])+':'+str(F.state(c)['turn'])
  G.grant_moves(c,[mid],grant_source,'effect',owner_id=c.entity_id,lifetime='user_turn_end',rule_id=uid,mode='permission')
  G.state(c)['sources'][grant_source]['shared_move_frequency']={'mount_id':donor.entity_id,'move_id':mid,'source':uid}
  TIMING.install(e,c,{'source':uid,'grant_source':grant_source,'permission_ability':RIDER,'turn_owner':c,'turn_deadline':serial})
  return {'source':uid,'move_id':mid,'frequency_owner':donor.entity_id,'ends':'user_turn_end'}
 return G.transition(engine,actor,apply,participants=(mount,))


def frequency_owner(engine,actor,move_id):
 """An active Rider use keeps its donor pool even if another source overlaps."""
 require_native_move(engine,actor,move_id)
 rows=[row['shared_move_frequency'] for row in actor.spec.get('state_grants',{}).get('sources',{}).values() if row.get('move_mode')=='permission' and row.get('shared_move_frequency',{}).get('move_id')==move_id]
 if not rows:return actor
 if len({row['mount_id'] for row in rows})!=1:raise ValueError('borrowed move has conflicting frequency owners')
 import world_entities as W,move_state as M
 mount=W.actor_index(engine).get(rows[0]['mount_id'])
 if mount is None or mount is actor:raise ValueError('borrowed move frequency owner missing')
 if actor.spec.get('mount_id')!=mount.entity_id:raise ValueError('borrowed move requires its actual current mount')
 if move_id not in M.known(engine.r,{'moves':M.owned_list(mount.spec,'moves',mount.moves)}):raise ValueError('mount no longer knows borrowed move')
 if M.ability_registration(engine.r,rows[0]['source'])['name']!=RIDER:raise ValueError('borrowed frequency source mismatch')
 return mount


def require_native_move(engine,actor,move_id):
 """Recheck Wired's live device permission without changing ordinary sources."""
 import special_entities as SPECIAL
 if SPECIAL.prime_instance(engine.r,move_id) is not None:
  SPECIAL.validate_prime_world(engine)
  if move_id not in SPECIAL.validate_prime_spec(engine.r,actor.spec,moves=actor.moves,complete=True):raise ValueError('actual Prime Hidden Power source ownership required')
 import wired_capability as WIRED
 return WIRED.require_native_move(engine,actor,move_id)


