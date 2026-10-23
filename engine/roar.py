"""Roar's declared Shift choices over the existing round-end Set-Up owner."""
from copy import deepcopy
import common_checks as C
SOURCE='move/울부짖기'
SETUP={'type':'set_up_move','declare':'no actions this round','resolve':'at round end: shift and use'}


def mechanics(rules,source,mechanics):
 if source=='move/부르짖기':
  from source_context import verified_source
  verified_source(rules,{'file':'input/db/moves.csv','sha256':'ab83f872e5eca67a41db7d126b842f0165437e0fa70bb77ddad832a0b7396c93'},label='Noble Roar English correction PTU402')
  return {'effects_exec':[{'type':'stage_change','stat':stat,'delta':-1,'target':'target'} for stat in ('atk','spa')]}
 if source!=SOURCE:return mechanics
 from source_context import verified_source
 verified_source(rules,{'file':'input/db/moves.csv','sha256':'ab83f872e5eca67a41db7d126b842f0165437e0fa70bb77ddad832a0b7396c93'},label='Roar')
 if rules._selected_rule(source)!=source:raise ValueError('selected Roar source changed')
 return {'effects_exec':[dict(SETUP),{'type':'roar_retreat','target':'target'}]}


def choose(engine,actor,*,shift,retreats,reason,shift_mode='land'):
 import world_entities as W
 W.require_actors(engine,actor)
 if not isinstance(reason,str) or not reason.strip() or type(shift) not in (list,tuple) or type(retreats) is not dict:
  raise ValueError('actual Roar Shift and target retreat choices required')
 import movement_actions as MOVE
 if shift_mode not in MOVE.MODES:raise ValueError('actual Roar user movement mode required')
 actor.spec['roar_choices']={'shift':deepcopy(shift),'shift_mode':shift_mode,'retreats':deepcopy(retreats),'reason':reason}


def bind_ball(engine,target,ball_id,*,reason):
 import world_entities as W
 W.require_actors(engine,target)
 owner=W.actor_index(engine).get(target.spec.get('trainer_id'))
 ball=getattr(engine,'_physical_objects',{}).get(ball_id)
 if not isinstance(reason,str) or not reason.strip() or owner is None or ball is None or ball.get('kind')!='item_instance' or ball.get('owner_id')!=owner.entity_id:
  raise ValueError('actual owned Pokemon, registered owner Ball and observation reason required')
 W.require_usable_object(ball)
 header=engine.r.item_effects(ball.get('item_rule_id'))[1]
 if header.get('use')!='ball':raise ValueError('registered item must be an actual Poke Ball')
 for actor in W.actor_index(engine).values():
  if actor is not target and actor.spec.get('home_ball',{}).get('ball_id')==ball_id:raise ValueError('one Ball cannot belong to two Pokemon')
 target.spec['home_ball']={'ball_id':ball_id,'owner_id':owner.entity_id,'reason':reason}
 engine.gm._rec('home Ball '+target.entity_id,None,target.spec['home_ball'],reason)


def shift(engine,actor):
 import movement_actions as MOVE
 row=actor.spec.get('roar_choices')
 if row is None:raise ValueError('Roar requires explicit round-end Shift and retreat choices')
 mode=row.get('shift_mode','land')
 MOVE.follow_paid_path(engine,actor,row['shift'],mode=mode,maximum_distance=MOVE.capabilities(engine,actor).get(mode,0))


def retreat(engine,actor,target):
 import movement_actions as MOVE,world_entities as W,body_state as BODY
 row=actor.spec.get('roar_choices',{}).get('retreats',{}).get(target.entity_id)
 if type(row) is not dict or set(row)-{'path','mode','ball_id'} or not {'path','mode'}<=set(row):raise ValueError('actual Roar recipient Shift choice required')
 speeds=MOVE.capabilities(engine,target);mode=row['mode'];speed=speeds.get(mode,0)
 if mode not in MOVE.MODES or speed<=0:raise ValueError('actual usable Roar movement capability required')
 # The caller must identify unavailable capabilities explicitly via the shared
 # environment/movement capability owner, rather than silently selecting Land.
 if speed<max(speeds.get(m,0) for m in MOVE.MODES):raise ValueError('Roar uses the highest usable movement capability')
 origin=target.pos;previous=origin
 distance=lambda a,b:max(abs(a[0]-b[0]),abs(a[1]-b[1]))
 owner=W.actor_index(engine).get(target.spec.get('trainer_id'))
 if not row['path']:
  alternatives=[(origin[0]+x,origin[1]+y) for x,y in ((1,0),(-1,0),(0,1),(0,-1))]
  if any(distance(p,actor.pos)>distance(origin,actor.pos) and BODY.can_place(engine,target,p,origin=origin) for p in alternatives):raise ValueError('Roar requires an actual retreat when movement away is possible')
 for point in row['path']:
  point=tuple(point.get('position')) if type(point)is dict else tuple(point)
  if distance(point,actor.pos)<distance(previous,actor.pos):raise ValueError('Roar Shift must move away from its user')
  if owner and distance(point,owner.pos)>distance(previous,owner.pos):
   alternatives=[(previous[0]+x,previous[1]+y) for x,y in ((1,0),(-1,0),(0,1),(0,-1))]
   if any(distance(p,actor.pos)>=distance(previous,actor.pos) and distance(p,owner.pos)<distance(previous,owner.pos) and BODY.can_place(engine,target,p,origin=previous) for p in alternatives):
    raise ValueError('Roar must shift towards its actual Trainer when possible')
  previous=point
 MOVE.follow_paid_path(engine,target,row['path'],mode=mode,maximum_distance=speed)
 if owner is not None:
  ball=getattr(engine,'_physical_objects',{}).get(row.get('ball_id'))
  binding=target.spec.get('home_ball',{})
  if ball is None or binding.get('ball_id')!=row.get('ball_id') or binding.get('owner_id')!=owner.entity_id or ball.get('owner_id')!=owner.entity_id:raise ValueError('owned Roar target requires its own registered Poke Ball')
  W.require_usable_object(ball)
  location=owner.pos if ball.get('carrier_id')==owner.entity_id else W.grid_cell(ball)
  if distance(target.pos,location)<=6:
   import combat_state_lifecycle as RECOVERY
   RECOVERY.recall(engine,target)
 engine.log(target.name+': Roar Shift '+str(origin)+' -> '+str(target.pos),SOURCE)


def effect(engine,actor,target,effect,context):
 if context.get('source_id')!=SOURCE:raise ValueError('native Roar Move effect required')
 return retreat(engine,actor,target)
