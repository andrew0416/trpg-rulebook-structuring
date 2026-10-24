"""Reviewed consumable attacks use shared accuracy, stock and status producers."""
import common_checks as C
import confusion_attacks as CONFUSION
DREAM_SOURCES=('item/꿈안개','item/꿈안개-1')
import pester_balls as PESTER
SOURCES=(*DREAM_SOURCES,*PESTER.SOURCES)


def prepare(engine,r):
 import body_modes as BODY_MODES
 BODY_MODES.require_targetable(r.target,engine=engine)
 if r.source_id in PESTER.SOURCES:return PESTER.prepare(engine,r)
 import world_entities as W,body_state as B,dream_state as D
 if r.source_id not in SOURCES or engine.r._selected_rule(r.source_id)!=r.source_id:raise ValueError('selected consumable attack needs its own source contract')
 if r.free or r.count!=1 or any(x is not None for x in (r.duration_minutes,r.duration_reason,r.food_policy,r.selected_move,r.shell_batch_id)):raise ValueError('Dream Mist requires one Standard Action item application')
 if r.fixed_accuracy is not None:C.integer(r.fixed_accuracy,'Dream Mist accuracy d20',1,20)
 index=W.actor_index(engine)
 if any(index.get(c.entity_id)is not c for c in (r.user,r.target)):raise ValueError('actual item attack participants required')
 if r.user is r.target or not r.user.on_field or not r.target.on_field or r.target.captured or r.target.dead:raise ValueError('actual distinct on-field target required')
 if not B.in_range(engine,r.user,r.target,B.melee_reach(r.user)):raise ValueError('Dream Mist is a Melee Status Attack')
 if engine.encounter_active and (r.user.injuries>=5 and not __import__('taskmaster').ignores_acting_loss(r.user)):raise ValueError('heavy-injury Standard item attack needs reviewed action composition')
 D.validate(r.target)
 CONFUSION.preflight(engine,r.user,attack(r))
 import invisibility_state as INV,blender_state as BLEND,effects_ext as EXT
 INV.accuracy_penalty(engine,r.target);BLEND.evasion(engine,r.target,attack(r));EXT.validate_combat_edges(engine,r.user)


def attack(r):
 # Original PDF302 gives Melee/Status/AC6, but no elemental type.
 return {'id':r.source_id,'name':'꿈안개','class':'변화','type':None,'ac':6,'range':'근접, 대상1','keywords':[]}


def consume(engine,r):
 if r.source_id in PESTER.SOURCES:return PESTER.consume(engine,r)
 import action_lifecycle as ACTION
 with ACTION.resolution(engine,r.user,r.source_id,kind="item_attack"):
  return _consume(engine,r)

def _consume(engine,r):
 import item_stock as STOCK,state_grants as G,turn as TURN,precise_actions as PRECISE
 stock=STOCK.prepare(engine,r.user,r.source_id,held_selection=r.held_selection,container_selection=r.container_selection)
 def pay(e,c):
  if not TURN.spend(e,c,'standard','꿈안개'):return None
  return STOCK.debit(e,c,stock)
 payment=G.transition(engine,r.user,pay)
 if payment is None:return (0,0)
 move=attack(r);CONFUSION.observe_action(engine,r.user,move)
 event=PRECISE.attacked(engine,r.user,r.target,move,producer='item_attack')
 # Payment precedes an actual observed roll; do not roll back this event.
 hit,natural,_=engine.accuracy_check(r.user,r.target,move,fixed_roll=r.fixed_accuracy)
 PRECISE.accuracy(event,hit)
 import dream_state as DREAM,field_effects as FIELD
 from copy import deepcopy
 serial_before=r.target.spec.get(DREAM.KEY,{}).get('serial',0)
 deferred_before=deepcopy(FIELD._pending(r.target))
 applied=bool(engine.apply_status(r.target,'잠듦',source=r.source_id,applied_by=r.user)) if hit else False
 if applied:DREAM.bind_mist(engine,r.user,payment,r.target,source=r.source_id,serial_before=serial_before,deferred_before=deferred_before)
 result={'source':r.source_id,'target_id':r.target.entity_id,'hit':hit,'natural':natural,'status_applied':applied,'payment':payment}
 engine.log('    Dream Mist: '+('sleep applied' if applied else 'hit without new sleep' if hit else 'miss'),r.source_id)
 return result
