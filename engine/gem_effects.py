"""Type Gem source adapter; actual stock and event instances remain shared."""
import event_effects as N
import common_checks as C
import effect_instances as E


def definition(rules,source):
 row=N.definition(rules,source)
 return row if row is not None and row.get('item_stock_required') else None


def slots(actor):return ('held',) if actor.kind=='pokemon' else ('반대손','장신구')


def validate_receipt(record):
 stock=record.get('item_stock')
 if not isinstance(stock,dict) or stock.get('kind') not in ('quantity','held_instance') or stock.get('item_id')!=record['source']:raise ValueError('Gem needs its exact actual stock receipt')
 C.integer(stock.get('count'),'one consumed Gem',1,1)
 if stock['kind']=='held_instance':E.text(stock.get('instance_id'),'consumed physical Gem identity')
 elif 'instance_id' in stock:raise ValueError('quantity stock cannot fabricate a physical Gem')


def validate_world_receipt(engine,actor,record,index):
 validate_receipt(record);stock=record['item_stock']
 if stock['kind']=='held_instance':
  obj=getattr(engine,'_physical_objects',{}).get(stock['instance_id'])
  if not isinstance(obj,dict) or obj.get('item_rule_id')!=record['source']:raise ValueError('Gem references missing actual consumed object')
  receipt=obj.get('consumed',{})
  if receipt!={'source':record['source'],'by_actor_id':actor.entity_id,'at':record['at']}:raise ValueError('physical Gem consumption and effect origin disagree')
  for other in index.values():
   rows=N.live(other)+other.spec.get(N.HISTORY,[])
   if any(r is not record and r.get('item_stock',{}).get('instance_id')==stock['instance_id'] for r in rows):raise ValueError('one physical Gem cannot create multiple effects')


def consume(engine,actor,source,*,held_selection=None):
 import item_stock as STOCK,turn as TURN,state_grants as G
 row=definition(engine.r,source)
 if row is None:raise ValueError('reviewed Type Gem source required')
 effects,header=engine.r.item_effects(source)
 if len(effects)!=1 or not N.same_payload(N.semantic(effects[0]),row['raw']):raise ValueError('selected Gem producer differs from reviewed definition')
 N.validate_actor(actor)
 STOCK.prepare(engine,actor,source,held_selection=held_selection,equipment_slots=slots(actor))
 def apply(e,a):
  stock=STOCK.prepare(e,a,source,held_selection=held_selection,equipment_slots=slots(a))
  if not TURN.spend(e,a,'free','consume Type Gem'):return {'status':'not_used'}
  paid=STOCK.debit(e,a,stock)
  if __import__('consumption_execution').suppress_benefit(e,a,a,paid):
   return {'status':'consumed','outcome':'no_effect','item_stock':paid,'source':source}
  N.grant(e,a,row['raw'],source,item_stock=paid)
  record=N.live(a)[-1]
  return {'status':'stored_effect','effect_id':record['id'],'item_stock':paid,'source':source}
 return G.transition(engine,actor,apply)
