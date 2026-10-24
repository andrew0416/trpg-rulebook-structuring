"""Finite manual ability producers for shared source-owned effect instances."""
from copy import deepcopy
import common_checks as C
import event_effects as N
import effect_instances as E

HISTORY='manual_effect_activations'
SEQUENCE='manual_effect_activation_sequence'


def registration(rules,name):
 selected=__import__('warper').registration(rules,name)
 if selected is not None:return selected
 selected=__import__('telepath').registration(rules,name)
 if selected is not None:return selected
 selected=__import__('telekinetic').ability_registration(rules,name)
 if selected is not None:return selected
 selected=__import__('sage').registration(rules,name)
 if selected is not None:return selected
 import hex_maniac as HEX
 selected=HEX.ability_registration(rules,name)
 if selected is not None:return selected
 import blessing_effects as BLESSINGS
 blessing=BLESSINGS.registration(rules,name)
 if blessing is not None:return blessing
 import ability_native_actions as NATIVE
 native=NATIVE.registration(rules,name)
 if native is not None:return native
 for uid,row in N.policy(rules)['sources'].items():
  act=row.get('manual_activation')
  if act is None or name not in act['aliases']:continue
  chosen=name if name in act['equivalent_source_ids'] else act['equivalent_source_ids'][0]
  if rules._selected_rule(chosen)!=chosen:raise ValueError('manual ability selected source changed')
  return {'name':act['name'],'source_id':chosen,'equivalent_source_ids':list(act['equivalent_source_ids'])}
 return None


def deferred_registration(rules,effect):
 if __import__('warper').registration(rules,effect.get('_rule_id') or effect.get('_ability')):return True
 if __import__('telepath').registration(rules,effect.get('_rule_id') or effect.get('_ability')):return True
 if __import__('telekinetic').ability_registration(rules,effect.get('_rule_id') or effect.get('_ability')):return True
 if __import__('sage').registration(rules,effect.get('_rule_id') or effect.get('_ability')):return True
 if __import__('hex_maniac').ability_registration(rules,effect.get('_rule_id') or effect.get('_ability')):return True
 import blessing_effects as BLESSINGS
 if BLESSINGS.deferred_registration(rules,effect):return True
 import ability_native_actions as NATIVE
 if NATIVE.deferred_registration(rules,effect):return True
 import ability_reveals as REVEALS
 if REVEALS.deferred_registration(rules,effect):return True
 row=N.definition(rules,effect.get('_rule_id'))
 return bool(row and row.get('manual_activation') and N.same_payload(N.semantic(effect),row['raw']))


def validate_receipt(actor,receipt):
 if not isinstance(receipt,dict):raise ValueError('actual manual activation receipt required')
 row=N.definition(actor.r,receipt.get('source'))
 if row is None or not row.get('manual_activation'):raise ValueError('reviewed manual activation source required')
 seq=C.integer(receipt.get('sequence'),'manual ability sequence',1)
 if receipt.get('id')!=receipt.get('giver_id','')+':effect-grant:'+str(seq):raise ValueError('manual activation identity mismatch')
 for key in ('giver_id','holder_id','effect_id'):E.text(receipt.get(key),'manual activation '+key)
 if receipt['giver_id']==receipt['holder_id']:raise ValueError('adjacent ally source cannot target itself')
 C.integer(receipt.get('at'),'actual activation time',0);C.integer(receipt.get('scene'),'actual paid Scene',0)
 C.integer(receipt.get('used'),'actual activation use',1,row['manual_activation']['frequency']['uses'])
 if receipt.get('action')!=row['manual_activation']['action']:raise ValueError('manual source action changed')


def validate_effect(actor,record):
 receipt=record.get('activation');validate_receipt(actor,receipt)
 if receipt['holder_id']!=actor.entity_id or receipt['effect_id']!=record['id'] or receipt['source']!=record['source'] or receipt['at']!=record['at']:raise ValueError('held effect and paid activation disagree')
 if record[E.KEY].get('applied_by_actor_id')!=receipt['giver_id']:raise ValueError('effect applying actor and source payer disagree')


def validate_world(engine,index):
 import ability_native_actions as NATIVE
 NATIVE.validate_world(engine,index)
 import ability_reveals as REVEALS
 REVEALS.validate_world(engine,index)
 all_effects={}
 for c in index.values():
  for record in N.live(c)+c.spec.get(N.HISTORY,[]):
   if 'activation' in record:
    validate_effect(c,record);all_effects[record['id']]=record
 matched=set()
 for giver in index.values():
  history=giver.spec.get(HISTORY,[])
  if not isinstance(history,list):raise ValueError('manual activation history must be a list')
  sequence=C.integer(giver.spec.get(SEQUENCE,0),'manual activation sequence',0)
  if len(history)!=sequence:raise ValueError('manual activation sequence and history disagree')
  periods={}
  for i,receipt in enumerate(history,1):
   validate_receipt(giver,receipt)
   if receipt['giver_id']!=giver.entity_id or receipt['sequence']!=i or receipt['at']>engine.elapsed_seconds:raise ValueError('manual activation owner/order/time invalid')
   record=all_effects.get(receipt['effect_id'])
   if record is None or not N.same_payload(record.get('activation'),receipt):raise ValueError('actual paid activation has no matching held or consumed effect')
   if record['id'] in matched:raise ValueError('effect cannot be issued by two activations')
   matched.add(record['id'])
   name=N.definition(engine.r,receipt['source'])['manual_activation']['name'];key=(receipt['scene'],name)
   periods[key]=periods.get(key,0)+1
   if periods[key]!=receipt['used']:raise ValueError('manual ability aliases must share one Scene usage pool')
   state=giver.spec.get('frequency_state',{})
   if receipt['scene']>state.get('scene',-1):raise ValueError('activation is ahead of its Scene clock')
   if receipt['scene']==state.get('scene'):
    quota=state.get('activations',{}).get('ability:'+name,{})
    if quota.get('kind')!='scene' or quota.get('period')!=receipt['scene'] or quota.get('used',0)<receipt['used']:raise ValueError('manual ability has no actual paid source frequency')
 if matched!=set(all_effects):raise ValueError('held manual effect has no original giver receipt')


def activate(engine,actor,ability,target):
 if __import__('telepath').registration(engine.r,ability):return __import__('telepath').gentle(engine,actor,ability,target)
 if __import__('telekinetic').ability_registration(engine.r,ability):return __import__('telekinetic').activate_interference(engine,actor,ability,target)
 if __import__('sage').registration(engine.r,ability):return __import__('sage').activate_ability(engine,actor,ability,target)
 if __import__('hex_maniac').ability_registration(engine.r,ability):return __import__('hex_maniac').activate_ability(engine,actor,ability,target)
 import move_state as MOVES,world_entities as W,state_grants as G,partial_entities as PARTIAL
 import mindlock as MINDLOCK
 blocked=MINDLOCK.gentle_block(engine,actor,ability,target)
 if blocked is not None:return blocked
 import blessing_effects as BLESSINGS
 if BLESSINGS.registration(engine.r,ability) is not None:
  return BLESSINGS.activate(engine,actor,ability,target)
 import ability_native_actions as NATIVE
 if NATIVE.registration(engine.r,ability) is not None:
  return NATIVE.activate(engine,actor,ability,target)
 import ability_reveals as REVEALS
 if REVEALS.registration(engine.r,ability) is not None:
  targets=target if isinstance(target,(list,tuple)) else (target,)
  return REVEALS.activate(engine,actor,ability,targets)
 reg=registration(engine.r,ability)
 if reg is None:raise ValueError('reviewed manual ability source required')
 source=reg['source_id'];row=N.definition(engine.r,source);act=row['manual_activation']
 PARTIAL.require_complete(actor,'manual ability source');PARTIAL.require_complete(target,'manual ability target')
 index=W.actor_index(engine)
 if index.get(actor.entity_id) is not actor or index.get(target.entity_id) is not target:raise ValueError('manual ability needs actual registered actors')
 if actor.abilities_suppressed or not any((registration(engine.r,a) or {}).get('name')==reg['name'] for a in actor.abilities):raise ValueError('actual unsuppressed acquired ability required')
 if target is actor or not getattr(actor,'side',None) or actor.side!=getattr(target,'side',None):raise ValueError('one actual ally other than the user required')
 from grid import cheb
 if not engine.adjacent(actor,target):raise ValueError('actual adjacent ally position required')
 effects=engine.r.ability_effects.get(reg['name'],[])
 if len(effects)!=1 or not N.same_payload(N.semantic(effects[0]),row['raw']):raise ValueError('manual ability extraction differs from its reviewed source')
 E.validate_world(engine,index)
 def apply(e,giver,holder):
  import frequency as F,turn as TURN
  key='ability:'+reg['name']
  if not F.activation_allowed(giver,key,act['frequency'],engine=e):raise ValueError('manual ability Scene frequency exhausted')
  if not TURN.spend(e,giver,act['action'],reg['name']):raise ValueError('manual ability action unavailable')
  F.consume_activation(giver,key,act['frequency'],engine=e)
  state=F.state(giver);sequence=C.integer(giver.spec.get(SEQUENCE,0),'manual ability sequence',0)+1
  receipt={'id':giver.entity_id+':effect-grant:'+str(sequence),'sequence':sequence,'giver_id':giver.entity_id,'holder_id':holder.entity_id,'effect_id':holder.entity_id+':effect:'+str(C.integer(holder.spec.get(E.SEQUENCE,0),'effect sequence',0)+1),'source':source,'at':e.elapsed_seconds,'scene':state['scene'],'used':state['activations'][key]['used'],'action':act['action']}
  giver.spec[SEQUENCE]=sequence;giver.spec.setdefault(HISTORY,[]).append(receipt)
  N.grant(e,holder,row['raw'],source,applied_by=giver,activation=receipt)
  E.validate_world(e,W.actor_index(e))
  return deepcopy(receipt)
 return G.transition(engine,actor,apply,participants=(target,))
