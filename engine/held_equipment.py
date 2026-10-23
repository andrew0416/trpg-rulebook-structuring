"""Authoritative held slots; rule identity is not physical instance identity.

A legacy item view is available only for zero/one held entry. Unknown capacity
loss and identical-item stacking are observable pending states, never drops.
"""
from copy import deepcopy
KEY='held_equipment'
SOURCES=('ability/배달부','ability/배달새','ability/배달부-2')

def registration(rules,name):
 if name not in (*SOURCES,'배달부','배달새'):return None
 import json
 from pathlib import Path
 rows={x['id']:x for x in json.loads((Path(rules.root)/'output/entities/abilities.json').read_text(encoding='utf8')) if x.get('id') in SOURCES}
 if set(rows)!=set(SOURCES):raise ValueError('two-held exact source definitions missing')
 keys=('name','eng','frequency','effect','trigger','target','keyword','effect_primary','effect2','effect_additions')
 if any(rows['ability/배달부'].get(k)!=rows['ability/배달부-2'].get(k) for k in keys):raise ValueError('Handyman duplicate source equivalence changed; review required')
 uid=name if name in SOURCES else 'ability/'+name
 if rules._selected_rule(uid)!=uid:raise ValueError('selected two-held variant needs its actual source contract')
 expected=[{'type':'rule','held_items_max':2}]
 if rules.ability_effects.get(rows[uid]['name'])!=expected:raise ValueError('two-held effect source changed; review required')
 equivalent=['ability/배달부','ability/배달부-2'] if uid!='ability/배달새' else [uid]
 return {'name':rows[uid]['name'],'source_id':uid,'equivalent_source_ids':equivalent}


def _legacy(actor):
 return actor.__dict__.get('item',actor.spec.get('item'))


def entries(actor):
 if KEY in actor.spec:return actor.spec[KEY]
 name=_legacy(actor)
 return [] if not name else [{'slot_id':'held:1','name':name,'instance_id':None,'registration_key':None,'identity_evidence':'legacy_slot'}]


def any_held(actor):return bool(entries(actor))


def single(actor):
 rows=entries(actor)
 if len(rows)>1:raise ValueError('two actual held items require an explicit instance selection')
 return rows[0]['name'] if rows else None


def initialize(actor):
 if KEY not in actor.spec:actor.spec[KEY]=deepcopy(entries(actor))
 sync_legacy(actor)


def sync_legacy(actor):
 rows=actor.spec[KEY]
 if len(rows)<=1:actor.spec['item']=rows[0]['name'] if rows else None
 else:actor.spec.pop('item',None)
 actor.__dict__.pop('item',None)


def set_single(actor,name):
 if name is not None and (not isinstance(name,str) or not name.strip()):raise ValueError('held item is an explicit name or None')
 initialize(actor);rows=entries(actor)
 if len(rows)>1:raise ValueError('cannot overwrite two actual held instances through the single-item compatibility view')
 if rows and rows[0]['name']==name:return
 if rows and rows[0].get('weapon_key'):raise ValueError('external weapon must be removed through its equipment owner')
 rows[:]=[] if name is None else [{'slot_id':'held:1','name':name,'instance_id':None,'registration_key':None,'identity_evidence':'legacy_slot'}]
 sync_legacy(actor)


def capacity(actor):
 active=[]
 if not actor.abilities_suppressed:
  for name in actor.abilities:
   source=registration(actor.r,name)
   if source:active.append(source['source_id'])
 import csv_item_capability_contracts as CSV
 intrinsic=CSV.tinkerer_weapon(actor)
 if intrinsic and intrinsic.get('uses_held_slot'):
  return {'maximum':0,'sources':['C2CSV/item-data:92:5'],'count':len(entries(actor))}
 return {'maximum':2 if active else 1,'sources':active,'count':len(entries(actor))}


def deferred_registration(rules,effect):
 if 'ability/'+str(effect.get('_ability')) not in SOURCES:return False
 if {k:v for k,v in effect.items() if not k.startswith('_')}!={'type':'rule','held_items_max':2}:return False
 source=effect.get('_rule_id','ability/'+effect['_ability'])
 if rules._selected_rule(source)!=source:raise ValueError('selected two-held variant needs reviewed registration')
 return True


def pending(actor):
 state=capacity(actor);issues=[]
 if state['count']>state['maximum']:issues.append({'kind':'capacity_lost','actual_count':state['count'],'maximum':state['maximum'],'resolution':'retain actual objects; explicit disposition required'})
 unresolved=[r['slot_id'] for r in entries(actor) if r.get('effects_pending')]
 if unresolved:issues.append({'kind':'identical_effect_stacking','slots':unresolved,'resolution':'same-rule objects are distinct; stacking is not stated by capacity source'})
 return issues


def require_resolved(actor):
 issues=pending(actor)
 if issues:raise ValueError('held equipment has unresolved source state: '+str(issues))


def select(actor,selection=None):
 rows=entries(actor)
 if selection is None:
  if len(rows)>1:raise ValueError('select one actual held slot/instance')
  return rows[0] if rows else None
 matching=[r for r in rows if selection in (r['slot_id'],r.get('instance_id'),r.get('registration_key'))]
 if len(matching)!=1:raise ValueError('selection does not identify one actual held entry')
 return matching[0]


def prepare(actor,name,item_id,instance_id=None,slot_id=None):
 rows=entries(actor)
 matching=[r for r in rows if (slot_id is not None and r['slot_id']==slot_id) or (instance_id is not None and r.get('instance_id')==instance_id)]
 if not matching and slot_id is None:
  matching=[r for r in rows if r['name']==name and (instance_id is None or not r.get('registration_key') and r.get('instance_id') in (None,instance_id))]
 if len(matching)>1:raise ValueError('ambiguous legacy held entry needs an explicit slot')
 if matching:
  row=matching[0]
  if row.get('weapon_key'):raise ValueError('actual held slot is occupied by an external weapon')
  if row['name']!=name or instance_id is not None and row.get('instance_id') not in (None,instance_id):raise ValueError('held destination already contains another actual object')
  return row
 if len(rows)>=capacity(actor)['maximum']:raise ValueError('no available actual held-item slot')
 slot_id=slot_id or next('held:'+str(i) for i in (1,2) if not any(r['slot_id']=='held:'+str(i) for r in rows))
 if not isinstance(slot_id,str) or not slot_id.strip():raise ValueError('held slot needs a stable identity')
 return {'slot_id':slot_id,'name':name,'item_id':item_id,'instance_id':instance_id,'registration_key':None,'identity_evidence':'registered_instance' if instance_id else 'legacy_slot'}


def commit(actor,row,*,item_id,instance_id,registration_key,effects_pending=False):
 initialize(actor)
 actual=next((x for x in entries(actor) if x['slot_id']==row['slot_id']),None)
 if actual is None:entries(actor).append(row)
 else:row=actual
 row.update(item_id=item_id,instance_id=instance_id,registration_key=registration_key,identity_evidence='registered_instance' if instance_id else 'legacy_slot')
 if effects_pending:row['effects_pending']=True
 else:row.pop('effects_pending',None)
 sync_legacy(actor)


def remove(actor,selection):
 initialize(actor);row=select(actor,selection)
 if row is not None:entries(actor).remove(row)
 sync_legacy(actor)
 return row


def validate(actor):
 rows=entries(actor)
 if not isinstance(rows,list) or len(rows)>2:raise ValueError('held equipment is an explicit list of at most two slots')
 slots=set();instances=set()
 for row in rows:
  if not isinstance(row,dict) or not isinstance(row.get('slot_id'),str) or not row['slot_id'] or not isinstance(row.get('name'),str) or not row['name']:raise ValueError('held entry requires actual slot identity and item name')
  if row['slot_id'] in slots:raise ValueError('duplicate held slot identity')
  slots.add(row['slot_id']);uid=row.get('instance_id')
  if uid is not None:
   if not isinstance(uid,str) or not uid or uid in instances:raise ValueError('duplicate/invalid physical held instance')
   instances.add(uid)
  key=row.get('registration_key')
  if row.get('weapon_key'):
   weapon=actor.custom_conditions.get('equipped_weapons',{}).get(row['weapon_key'])
   if not weapon or weapon['weapon'].get('instance_id')!=uid or weapon['weapon']['name']!=row['name'] or key is not None:raise ValueError('held external weapon and equipped ledger disagree')
  if key is not None:
   registered=getattr(actor,'_item_reg',{}).get(key)
   if not registered or registered.get('instance_id')!=uid or registered.get('name',key)!=row['name']:raise ValueError('held entry and actual effect registration disagree')
 if actor.kind=='pokemon':
  for weapon_key,record in actor.custom_conditions.get('equipped_weapons',{}).items():
   bound=[row for row in rows if row.get('weapon_key')==weapon_key]
   weapon=record['weapon']
   if weapon.get('living_actor'):
    if bound:raise ValueError('Living Weapon actor must not be a held item clone')
    continue  # Actual actor relation/projection is checked by living_weapon.validate_world.
   if (len(bound)!=1 or not weapon.get('instance_id')
       or bound[0].get('instance_id')!=weapon['instance_id'] or bound[0]['name']!=weapon['name']):
    raise ValueError('equipped Pokemon weapon requires exactly one matching actual held slot')
 if KEY in actor.spec and 'item' in actor.spec and (len(rows)>1 or actor.spec['item']!=(rows[0]['name'] if rows else None)):raise ValueError('legacy item alias disagrees with authoritative held entries')
 return True
