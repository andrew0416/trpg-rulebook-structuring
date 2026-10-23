"""Shared sourced daily production into an actual reusable Collection Jar."""
from copy import deepcopy
import common_checks as C,state_grants as G,skill_modifiers as S,frequency as F
KEY='capability_products'
DEFINITIONS={
 'capability/꿈안개':{'aliases':('꿈안개','Dream Mist'),'item':'item/꿈안개','price':500,'minimum_level':20,'plants':False},
 'capability/우유짜기':{'aliases':('우유짜기','Milk Collection'),'item':'item/튼튼밀크','minimum_level':20,'plants':False},
 'capability/꿀모으기':{'aliases':('꿀모으기','Honey Gather'),'item':'item/꿀','minimum_level':1,'plants':True},
}
DAILY={'kind':'daily','uses':1}


def definition(rules,source):
 if source not in DEFINITIONS or rules._selected_rule(source)!=source:raise ValueError('selected production capability needs its own contract')
 return DEFINITIONS[source]


def _item_header(rules,definition):
 # Product identity belongs to the actual capability source, not a display-name match.
 header=rules.item_effects(definition['item'])[1]
 if header.get('id')!=definition['item']:raise ValueError('production requires its exact sourced product item')
 return header


def catalog(rules):
 result=[]
 for source in DEFINITIONS:
  d=definition(rules,source);header=_item_header(rules,d)
  result.append({'source':source,'item_id':header['id'],'price':d.get('price',header.get('price')),
                 'minimum_level':d['minimum_level'],'frequency':dict(DAILY),'action':'extended',
                 'container':'Collection Jar','living_plants_required':d['plants'],
                 'shop_availability':{'kind':'occasional','shop':'occult','guaranteed_stock':False} if source=='capability/꿈안개' else None})
 return result


def validate(actor):
 rows=actor.spec.get(KEY,{})
 if not isinstance(rows,dict):raise ValueError('identified capability production receipts required')
 for uid,row in rows.items():
  if not isinstance(row,dict) or row.get('id')!=uid or row.get('producer_id')!=actor.entity_id:raise ValueError('actual product and producer identity required')
  d=definition(actor.r,row.get('source'))
  if row.get('item_id')!=_item_header(actor.r,d).get('id'):raise ValueError('produced item does not match capability source')
  for key in ('collector_id','container_id','reason'):
   if not isinstance(row.get(key),str) or not row[key].strip():raise ValueError('actual product '+key+' required')
  C.integer(row.get('level'),'production level',d['minimum_level'],100)
  C.integer(row.get('started_at'),'production start',0);C.integer(row.get('at'),'production end',row['started_at']+60)
  C.integer(row.get('minutes'),'observed production minutes',1)
  if row['at']-row['started_at']!=row['minutes']*60:raise ValueError('production duration mismatch')
  if type(row.get('living_plants')) is not bool or (d['plants'] and not row['living_plants']):raise ValueError('Honey Gather needs observed living plant environment')
 return rows


def validate_world(engine,index):
 for actor in index.values():
  for uid,row in validate(actor).items():
   if row['collector_id'] not in index:raise ValueError('actual product collector missing')
   obj=getattr(engine,'_physical_objects',{}).get(row['container_id'],{})
   portion=obj.get('item_contents',{}).get('portions',{}).get(uid,{})
   if portion.get('item_id')!=row['item_id'] or portion.get('source')!=row['source'] or portion.get('loaded_at')!=row['at'] or portion.get('loaded_by')!=row['collector_id']:raise ValueError('capability product must retain actual bottled portion')
 return True


def collect(engine,producer,source,*,holder,container_selection,minutes,reason,living_plants=False):
 import world_entities as W,item_containers as J,pokemon_activities as P,turn as TURN
 index=W.actor_index(engine)
 if any(index.get(c.entity_id)is not c for c in (producer,holder)):raise ValueError('actual production and container actors required')
 if producer.kind!='pokemon':raise ValueError('this source produces through a Pokemon capability')
 d=definition(engine.r,source)
 item_id=_item_header(engine.r,d)['id']
 if producer.level<d['minimum_level']:raise ValueError('production capability requires level20')
 names={S.key(x) for x in G.effective_capabilities(producer)}
 if not names.intersection(S.key(x) for x in (*d['aliases'],source)):raise ValueError('current production capability required')
 C.integer(minutes,'GM Extended production minutes',1)
 if not isinstance(reason,str) or not reason.strip():raise ValueError('actual production duration/environment reason required')
 if type(living_plants)is not bool or (d['plants'] and not living_plants):raise ValueError('Honey Gather needs observed living plant environment')
 P._outside(engine)
 def apply(e,p,h):
  validate(p);jar=J.empty_body(e,h,container_selection)
  if not F.activation_allowed(p,source,DAILY,engine=e):raise ValueError('production capability daily use exhausted')
  e.preflight_advance_time(minutes*60,[p,h])
  if not TURN.spend(e,p,'extended',source):raise ValueError('actual Extended production action not admitted')
  F.consume_activation(p,source,DAILY,engine=e)
  start=e.elapsed_seconds;e.advance_time(minutes*60,[p,h])
  rows=p.spec.setdefault(KEY,{})
  uid=p.entity_id+':capability-product:'+str(len(rows)+1)
  item=item_id
  row={'id':uid,'source':source,'producer_id':p.entity_id,'collector_id':h.entity_id,'container_id':jar['id'],'item_id':item,'level':p.level,'started_at':start,'at':e.elapsed_seconds,'minutes':minutes,'living_plants':living_plants,'reason':reason}
  rows[uid]=row
  stock={'kind':'capability_product','item_id':item,'count':1,'producer_id':p.entity_id,'product_id':uid}
  J.deposit(e,h,container_selection,item_id=item,stock=stock,source=source,reason=reason,product_id=uid)
  validate(p);J.validate_world(e,W.actor_index(e));validate_world(e,W.actor_index(e))
  e.gm._rec('capability product',None,row,reason,p)
  return deepcopy(row)
 return G.transition(engine,producer,apply,participants=(holder,))
