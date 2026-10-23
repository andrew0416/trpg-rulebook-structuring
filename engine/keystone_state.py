"""Identified Odd Keystones and paid, persistent Pokemon-specific links."""
from copy import deepcopy
import common_checks as C, state_grants as G, skill_modifiers as S
import world_entities as W
KEY='keystone_links'
MARK='odd_keystone'
SOURCE='capability/쐐기돌-점멸'

def text(v,label):
 if not isinstance(v,str) or not v.strip():raise ValueError(label+' required')
 return v

def actual(e,c):
 if W.actor_index(e).get(c.entity_id) is not c:raise ValueError('actual registered participant required')

def capable(c):
 from builder import species_lookup
 if c.kind!='pokemon' or species_lookup(c.r,c.spec['species'])['name']!='화강돌':raise ValueError('Keystone Warp requires Spiritomb')
 if c.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Keystone Warp needs its own contract')
 names={S.key(x) for x in G.effective_capabilities(c)}
 if not names.intersection(S.key(x) for x in ('쐐기돌 점멸','Keystone Warp',SOURCE)):raise ValueError('current Keystone Warp capability required')

def validate(c):
 rows=c.spec.get(KEY)
 if rows is None:return
 if not isinstance(rows,dict):raise ValueError('identified Keystone links required')
 if rows and c.kind!='pokemon':raise ValueError('Keystone links belong to an actual Pokemon')
 for uid,row in rows.items():
  text(uid,'Keystone identity')
  if not isinstance(row,dict) or row.get('source')!=SOURCE or row.get('stone_id')!=uid or row.get('pokemon_id')!=c.entity_id:raise ValueError('sourced Keystone link identity mismatch')
  text(row.get('collector_id'),'collector');text(row.get('reason'),'link reason')
  C.integer(row.get('paid_tutor_points'),'link cost',2,2)
  C.integer(row.get('balance_before'),'previous Tutor Points',2)
  if type(row.get('balance_after'))is not int or row['balance_after']!=row['balance_before']-2:raise ValueError('Keystone Tutor Point receipt mismatch')

def validate_world(e,index):
 objects=getattr(e,'_physical_objects',{})
 for uid,obj in objects.items():
  mark=obj.get(MARK)
  if mark is None:continue
  if not isinstance(mark,dict) or mark.get('source')!=SOURCE:raise ValueError('Odd Keystone source required')
  text(mark.get('reason'),'Odd Keystone observation')
  collector=index.get(mark.get('collector_id'))
  if collector is None or collector.kind!='trainer':raise ValueError('actual Keystone collector required')
  if mark.get('original_for') is not None:
   original=index.get(mark['original_for'])
   if original is None or original.kind!='pokemon':raise ValueError('original Keystone Pokemon must resolve')
 for c in index.values():
  validate(c)
  for uid,row in c.spec.get(KEY,{}).items():
   obj=objects.get(uid);mark=obj.get(MARK) if obj else None
   if not mark or mark['collector_id']!=row['collector_id'] or mark.get('original_for')==c.entity_id:raise ValueError('linked additional Keystone must resolve to its observed collected body')
 return True

def observe(e,collector,stone_id,*,reason,original_for=None):
 actual(e,collector);text(reason,'Keystone observation reason')
 if collector.kind!='trainer':raise ValueError('trainer collector required')
 obj=getattr(e,'_physical_objects',{}).get(stone_id)
 if obj is None:raise ValueError('register the actual physical stone first')
 W.require_usable_object(obj)
 if MARK in obj:raise ValueError('existing Keystone provenance cannot be overwritten')
 if original_for is not None:actual(e,original_for);capable(original_for)
 def apply(se,sc):
  target=se._physical_objects[stone_id]
  target[MARK]={'source':SOURCE,'collector_id':sc.entity_id,'original_for':original_for.entity_id if original_for else None,'reason':reason}
  validate_world(se,W.actor_index(se));se.gm._rec('Odd Keystone '+stone_id,None,target[MARK],reason,sc)
  return deepcopy(target[MARK])
 return G.transition(e,collector,apply)

def link(e,c,stone_id,*,collector,reason):
 actual(e,c);actual(e,collector);capable(c);text(reason,'link reason')
 validate_world(e,W.actor_index(e))
 obj=getattr(e,'_physical_objects',{}).get(stone_id)
 if obj is None:raise ValueError('actual collected Keystone required')
 W.require_usable_object(obj);mark=obj.get(MARK)
 if not mark or mark['collector_id']!=collector.entity_id or mark.get('original_for')==c.entity_id:raise ValueError('additional stone collected by this trainer required')
 if stone_id in c.spec.get(KEY,{}):raise ValueError('Keystone already linked; no repeated Tutor Point payment')
 from pokemon_teaching import _balance
 before=_balance(c.spec)
 if before<2:raise ValueError('Keystone link costs two Tutor Points')
 def apply(se,sc):
  row={'source':SOURCE,'stone_id':stone_id,'pokemon_id':sc.entity_id,'collector_id':collector.entity_id,'paid_tutor_points':2,'balance_before':before,'balance_after':before-2,'reason':reason}
  sc.spec['tutor_points']=before-2;sc.spec.setdefault(KEY,{})[stone_id]=row
  validate_world(se,W.actor_index(se));se.gm._rec('Keystone link',None,row,reason,sc)
  return deepcopy(row)
 return G.transition(e,c,apply)

def links(e,c):
 actual(e,c);validate_world(e,W.actor_index(e))
 return [{'link':deepcopy(row),'object':deepcopy(e._physical_objects[uid])} for uid,row in c.spec.get(KEY,{}).items()]


def warp(e,c,stone_id,*,reason):
 """Grounded mapped Keystone Warp; unresolved geometry never spends an action."""
 import movement_actions as MOVE,turn as TURN,body_state as BODY
 actual(e,c);capable(c);text(reason,'Keystone destination observation')
 validate_world(e,W.actor_index(e));MOVE.boundary(e,'keystone_warp')
 if stone_id not in c.spec.get(KEY,{}):raise ValueError('destination must be synchronized with this Pokemon')
 obj=e._physical_objects[stone_id];W.require_usable_object(obj)
 loc=W.effective_location(e,obj);origin=W.location_of(c)
 if loc['kind']!='grid' or origin['kind']!='grid' or loc.get('map_id')!=origin.get('map_id'):
  return C.PendingDecision('Keystone Warp needs actual positions on the same map')
 if obj.get('carrier_id') or obj.get('equipped_by'):
  return C.PendingDecision('arrival at a carried Keystone requires resolved body overlap and carrier geometry')
 if c.spec.get('_movement_altitude',0)!=0 or c.spec.get('_burrow',{}).get('underground'):
  return C.PendingDecision('Keystone altitude or underground arrival geometry is not established')
 if e.grid is None:return C.PendingDecision('Keystone destination map required')
 destination=tuple(loc['cell'])
 if e.grid.blocked(c.pos,destination):return C.PendingDecision('Keystone Warp through blocking terrain needs source adjudication')
 destination,distance=MOVE._travel_geometry(e,c,destination,0,None)
 if distance>10:raise ValueError('linked Keystone is beyond ten metres')
 shape=BODY.offsets(c)
 if shape is None:return C.PendingDecision('complete Spiritomb body geometry required')
 occupied={(destination[0]+dx,destination[1]+dy) for dx,dy in shape}
 if any(not e.grid.inside(x) or x in e.grid.blocking for x in occupied):raise ValueError('Keystone arrival body does not fit')
 for other in e.everyone:
  if other is not c and other.on_field and not other.captured and not other.fainted and other.spec.get('_movement_altitude',0)==0 and occupied.intersection(BODY.cells(other,require_complete=True)):
   raise ValueError('Keystone arrival overlaps an actual body')
 if e.encounter_active and (c.injuries>=5 and not __import__('taskmaster').ignores_acting_loss(c)):return C.PendingDecision('heavy-injury Standard Keystone action needs reviewed action composition')
 if not c.on_field or c.captured or not TURN.movement_permission(e,c):return False
 if not TURN.spend(e,c,'standard','쐐기돌 점멸'):return False
 if not MOVE.departure(e,c,destination,0):return False
 before=c.pos;c.pos=destination;c.airborne=False;c.spec['_movement_altitude']=0
 row={'source':SOURCE,'stone_id':stone_id,'origin':before,'destination':destination,'distance':distance,'reason':reason}
 e.log(c.name+': 쐐기돌 점멸 '+str(distance)+'m → '+stone_id,SOURCE)
 import effects_ext as EXT
 EXT.on_enter_cell(e,c,destination)
 return row
