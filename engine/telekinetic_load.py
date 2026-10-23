"""Remote object placement shares the ordinary load/check state, not body placement."""
from copy import deepcopy,copy
import common_checks as C,state_grants as G,skill_modifiers as S
import capability_actions as LOAD,world_entities as W
SOURCE='capability/염력'

def require(e,c):
 if W.actor_index(e).get(c.entity_id)is not c:raise ValueError('actual Telekinetic actor required')
 if e.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Telekinetic source needs its own contract')
 names={S.key(x) for x in G.effective_capabilities(c)}
 if not names.intersection(S.key(x) for x in ('염력','Telekinetic',SOURCE)):raise ValueError('current Telekinetic capability required')

def table(c):
 import tk_mastery as MASTERY
 rank=MASTERY.focus(c);C.integer(rank,'Focus rank',1)
 values=LOAD.policy(c)['weight_limits_kg']
 if str(rank) not in values:raise ValueError('Focus rank lacks published weight limits')
 return deepcopy(values[str(rank)])

def validate(c):
 state=c.spec.get('_carried_load')
 if not state or state.get('mode','physical')!='telekinetic':return
 if state.get('source')!=SOURCE:raise ValueError('Telekinetic load source required')
 if state.get('blocked_actions'):raise ValueError('physical hand restrictions cannot be inferred for remote objects')
 if not isinstance(state.get('reason'),str) or not state['reason'].strip():raise ValueError('Telekinetic load observation required')
 ids=[]
 for row in state['objects']:
  if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not row['id']:raise ValueError('actual remote object identity required')
  LOAD.number(row.get('weight_kg'),'remote object weight',minimum=0);ids.append(row['id'])
 if len(set(ids))!=len(ids):raise ValueError('duplicate Telekinetic object')
 if type(state.get('failure_pending'))is not bool:raise ValueError('explicit remote load check state required')

def validate_world(e,index):
 objects=getattr(e,'_physical_objects',{})
 for c in index.values():
  validate(c);state=c.spec.get('_carried_load',{})
  if state.get('mode')!='telekinetic':continue
  for item in state['objects']:
   obj=objects.get(item['id'])
   if obj is None or obj.get('telekinetic_holder_id')!=c.entity_id or obj.get('carrier_id') or obj.get('equipped_by') or obj.get('weight_kg')!=item['weight_kg']:raise ValueError('remote load and actual independent object disagree')
   W.require_usable_object(obj)
 for uid,obj in objects.items():
  holder=obj.get('telekinetic_holder_id')
  if holder is None:continue
  c=index.get(holder);st=c.spec.get('_carried_load',{}) if c else {}
  if st.get('mode')!='telekinetic' or uid not in {r['id'] for r in st['objects']}:raise ValueError('remote object has no matching actual holder load')
 return True

def range_check(e,c,obj):
 a=W.location_of(c);b=W.location_of(obj)
 if a['kind']!='grid' or b['kind']!='grid' or a.get('map_id')!=b.get('map_id'):raise ValueError('actual same-map Telekinetic positions required')
 if c.spec.get('_movement_altitude',0):raise ValueError('remote vertical distance requires additional world geometry')
 dx,dy=(abs(a['cell'][i]-b['cell'][i]) for i in (0,1))
 if max(dx,dy)+min(dx,dy)//2>8:raise ValueError('remote object beyond eight metres')

def lift(e,c,object_ids,*,action_cost,reason,boundary_band=None):
 require(e,c)
 if not isinstance(reason,str) or not reason.strip():raise ValueError('explicit GM activity cost and world observation reason required')
 if action_cost not in ('standard','shift','extended'):raise ValueError('explicit GM action cost required for unspecified lifting activity')
 if not isinstance(object_ids,(list,tuple)) or not object_ids or any(not isinstance(x,str) or not x for x in object_ids) or len(set(object_ids))!=len(object_ids):raise ValueError('distinct actual remote objects required')
 if c.spec.get('_carried_load',{}).get('objects'):raise ValueError('release existing load before selecting another complete remote load')
 records=[]
 for uid in object_ids:
  obj=getattr(e,'_physical_objects',{}).get(uid)
  if obj is None:raise ValueError('actual remote object must already exist')
  W.require_usable_object(obj);range_check(e,c,obj)
  if obj.get('carrier_id') or obj.get('equipped_by') or obj.get('telekinetic_holder_id'):raise ValueError('object already held; no implicit disarm')
  LOAD.number(obj.get('weight_kg'),'actual remote weight',minimum=0);records.append({'id':uid,'weight_kg':obj['weight_kg']})
 state={'mode':'telekinetic','source':SOURCE,'objects':records,'blocked_actions':[],'boundary_band':boundary_band,'reason':reason,'checked_round':None,'failure_pending':False}
 probe=copy(c);probe.spec=dict(c.spec,_carried_load=state);validate(probe);LOAD.load(probe)
 def apply(se,sc):
  import turn as TURN
  if not TURN.spend(se,sc,action_cost,'염력 운반'):raise ValueError('cannot pay declared lifting action')
  sc.spec['_carried_load']=deepcopy(state)
  for uid in object_ids:se._physical_objects[uid]['telekinetic_holder_id']=sc.entity_id
  validate_world(se,W.actor_index(se));se.gm._rec('Telekinetic load',None,state,reason,sc)
  return LOAD.load(sc)
 return G.transition(e,c,apply)

def release(e,c,*,reason):
 if W.actor_index(e).get(c.entity_id)is not c:raise ValueError('actual remote holder required')
 state=c.spec.get('_carried_load',{})
 if state.get('mode')!='telekinetic':raise ValueError('actual remote load required')
 return LOAD.set_carried(e,c,[],reason)


def move_objects(e,c,paths,*,action_cost,maximum_distance,reason):
 """Move identified remote bodies through explicit paths under declared GM timing."""
 require(e,c);validate_world(e,W.actor_index(e))
 state=c.spec.get('_carried_load',{})
 if state.get('mode')!='telekinetic' or not state.get('objects'):raise ValueError('actual remote load required')
 if state['failure_pending']:raise ValueError('resolve failed remote carrying check first')
 if not isinstance(reason,str) or not reason.strip():raise ValueError('explicit GM movement timing and distance reason required')
 if action_cost not in ('standard','shift','extended'):raise ValueError('explicit GM movement action cost required')
 LOAD.number(maximum_distance,'GM declared remote movement allowance',minimum=0)
 if not isinstance(paths,dict) or not paths:raise ValueError('identified remote object paths required')
 held={x['id'] for x in state['objects']}
 if not set(paths)<=held:raise ValueError('only actual held remote objects may move')
 if e.grid is None:raise ValueError('actual mapped remote paths required')
 prepared={}
 for uid,path in paths.items():
  obj=e._physical_objects[uid];range_check(e,c,obj)
  if not isinstance(path,(list,tuple)) or len(path)<2:raise ValueError('remote path must include origin and destination')
  import movement_actions as MOVE
  points=tuple(MOVE._point(x) for x in path)
  if points[0]!=W.location_of(obj)['cell']:raise ValueError('path must start at actual object position')
  distance=0;diagonals=0
  for before,after in zip(points,points[1:]):
   dx,dy=abs(after[0]-before[0]),abs(after[1]-before[1])
   if max(dx,dy)!=1:raise ValueError('remote movement path must be continuous')
   if not e.grid.inside(after) or e.grid.blocked(before,after):raise ValueError('remote object cannot pass through blocked path')
   if dx and dy:distance+=1+diagonals%2;diagonals+=1
   else:distance+=1
   probe=dict(obj);W._set_object_location(probe,dict(W.location_of(obj),cell=after));range_check(e,c,probe)
  if distance>maximum_distance:raise ValueError('remote path exceeds declared movement allowance')
  prepared[uid]={'path':points,'distance':distance}
 def apply(se,sc):
  import turn as TURN
  if not TURN.spend(se,sc,action_cost,'염력 물체 이동'):raise ValueError('cannot pay declared remote movement action')
  for uid,row in prepared.items():
   obj=se._physical_objects[uid];before=W.location_of(obj)
   W._set_object_location(obj,dict(before,cell=row['path'][-1]))
   se.gm._rec('Telekinetic object movement '+uid,before,W.location_of(obj),reason,sc)
  validate_world(se,W.actor_index(se))
  return {'source':SOURCE,'actor_id':sc.entity_id,'objects':deepcopy(prepared),'action_cost':action_cost,'maximum_distance':maximum_distance,'reason':reason}
 return G.transition(e,c,apply)
