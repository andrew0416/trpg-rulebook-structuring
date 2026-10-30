"""Bandages/Poultices: native inventory, clock, damage and rest (ch09:177-194)."""
from copy import copy
import common_checks as C
import arithmetic_policy as M
import injury_recovery as INJURY
import environmental_effects as ENVIRONMENT

LIFETIME=21600

def validate(c):
 """One attached-dressing history for trainers and Pokemon, including old saves.
 Physical/quantity payment receipts are optional in legacy records; when present
 they must describe the same whole dressings as the retained effect.
 """
 records=c.spec.get('bandages',[])
 if not isinstance(records,list):raise ValueError('bandages must be a list of attachment records')
 seen=set()
 for record in records:
  if not isinstance(record,dict):raise ValueError('bandage attachment must be a record')
  uid=record.get('id')
  if not isinstance(uid,str) or not uid.strip() or uid in seen:raise ValueError('bandage attachment identity must be unique')
  seen.add(uid)
  if record.get('item') not in ('붕대','파스'):raise ValueError('bandage attachment has another item source')
  source='item/'+record['item']
  if record.get('source_id',source)!=source:raise ValueError('bandage source identity disagrees with its item')
  count=C.integer(record.get('count'),'attached bandage count',1)
  start=C.integer(record.get('started_at'),'bandage application time',0)
  end=C.integer(record.get('expires_at'),'bandage expiry',start)
  C.integer(record.get('gap_count'),'bandage known-time boundary',0)
  for key in ('duration_reason','applied_by'):
   if not isinstance(record.get(key),str) or not record[key].strip():raise ValueError('bandage application requires '+key)
  deadline=start+LIFETIME;last=start
  rulings=record.get('time_rulings',[])
  if not isinstance(rulings,list):raise ValueError('bandage timing rulings must be a list')
  for ruling in rulings:
   if not isinstance(ruling,dict):raise ValueError('bandage timing ruling must be a record')
   at=C.integer(ruling.get('at'),'bandage timing ruling time',last)
   remaining=C.integer(ruling.get('remaining_seconds'),'ruled remaining bandage time',0,LIFETIME)
   if remaining>max(0,deadline-at):raise ValueError('bandage timing ruling cannot extend its known lifetime')
   if not isinstance(ruling.get('reason'),str) or not ruling['reason'].strip():raise ValueError('bandage timing ruling requires its reason')
   deadline=at+remaining;last=at
  if end!=deadline:raise ValueError('bandage expiry disagrees with its six-hour lifetime and timing rulings')
  status=record.get('status')
  if status not in ('active','lost','expired'):raise ValueError('unknown bandage attachment state')
  if 'timing_pending' in record and record['timing_pending']!='unknown_elapsed_interval':raise ValueError('unknown bandage pending time reason')
  if status=='active':
   if any(key in record for key in ('ended_at','ended_reason','injuries_healed')):raise ValueError('active bandage already has a terminal result')
  else:
   ended=C.integer(record.get('ended_at'),'bandage termination time',start)
   if status=='expired':
    if ended!=end or 'ended_reason' in record:raise ValueError('bandage expiry has a conflicting terminal result')
    C.integer(record.get('injuries_healed'),'bandage injuries healed',0,count)
   elif record.get('ended_reason') not in ('actual_hp_loss','damage_taken') or 'injuries_healed' in record:
    raise ValueError('lost bandage requires actual loss or damage and cannot heal injuries')
  stock=record.get('item_stock')
  if stock is not None:
   if not isinstance(stock,dict) or stock.get('item_id')!=source or stock.get('kind') not in ('quantity','held_instance','held_batch'):
    raise ValueError('bandage payment receipt has another item source')
   C.integer(stock.get('count'),'paid bandage count',count,count)
   if stock['kind']=='held_instance':
    if count!=1 or not isinstance(stock.get('instance_id'),str) or not stock['instance_id']:raise ValueError('one physical bandage requires its actual instance')
   if stock['kind']=='held_batch':
    items=stock.get('items')
    if not isinstance(items,list) or len(items)!=count:raise ValueError('bandage physical receipts disagree with the group count')
    instances=set()
    for item in items:
     if not isinstance(item,dict) or item.get('kind')!='held_instance' or item.get('item_id')!=source:raise ValueError('bandage physical group has another source')
     C.integer(item.get('count'),'one physical bandage receipt',1,1)
     instance=item.get('instance_id')
     if not isinstance(instance,str) or not instance or instance in instances:raise ValueError('bandage physical instance paid more than once')
     instances.add(instance)
 return records


def _live(c):return [x for x in c.spec.get('bandages',[]) if x.get('status')=='active']

def _break(e,c,reason):
 records=_live(c)
 for record in records:record.update(status='lost',ended_at=e.elapsed_seconds,ended_reason=reason)
 if records:e.log(c.name+': 붕대/파스 효과 소멸 ('+reason+')','item/붕대')
 c.spec.pop('rest_interval',None)

def on_hp_change(e,c,before,after):
 if after<before:_break(e,c,'actual_hp_loss')

def on_damage(e,c,amount):
 if amount>0:_break(e,c,'damage_taken')

def _certain(e,record):return record['gap_count']==len(e.unresolved_time_intervals)

def preflight_advance(e,c):
 validate(c)
 if _live(c):INJURY.healed_today(c);ENVIRONMENT.protected_injuries(c)

def advance(e,c):
 for record in _live(c):
  if not _certain(e,record):
   record['timing_pending']='unknown_elapsed_interval';continue
  if e.elapsed_seconds>=record['expires_at']:
   healed=0 if __import__('glitch_bender').benefits_blocked(c) else INJURY.heal(e,c,record['count'],source='bandage')
   record.update(status='expired',ended_at=record['expires_at'],injuries_healed=healed)
   import clock_invocations as CLOCK
   CLOCK.child(e,c,record,kind='bandage')

def apply(e,actor,*,target,item='붕대',count=1,minutes,reason,accepted=True,held_selection=None,resumable=False,request_id=None):
 import clock_invocations as CLOCK
 if type(resumable) is not bool:raise ValueError('explicit bandage clock mode required')
 if request_id is not None and not resumable:raise ValueError('bandage request identity requires resumable time')
 if target is None:raise ValueError('living Pokemon or trainer recipient required')
 if resumable:C.integer(minutes,'Extended action minutes',1)
 request=dict(target_id=target.entity_id,item=item,count=count,minutes=minutes,reason=reason,accepted=accepted,held_selection=held_selection)
 def finish(e,a,*others,plan,payment,clock):
  import world_entities as W
  recipient=W.actor_index(e)[plan['target_id']]
  if recipient.dead:raise ValueError('living bandage recipient required at application')
  result,stock_receipt,record=_finish_application(e,a,recipient,item=plan['item'],count=plan['count'],reason=plan['reason'],stock=plan['stock'],clock=clock)
  return result,stock_receipt,record
 if resumable and CLOCK.activity_request(e,request_id,'bandage_application',actor,[actor,target],minutes*60,'item/'+item,request) is not None:
  return CLOCK.run_activity(e,actor,[actor,target],request_id=request_id,kind='bandage_application',seconds=minutes*60,source='item/'+item,request=request,prepare=None,finish=finish)
 import pokemon_activities as P
 P._outside(e);P._text(reason,'GM Extended action duration reason');C.integer(minutes,'Extended action minutes',1);C.integer(count,'bandage count',1)
 if item not in ('붕대','파스'):raise ValueError('Bandages or Poultices required')
 if e.r._selected_rule('item/'+item)!='item/'+item:raise ValueError('selected bandage version needs its own policy')
 if target is None or target.kind not in ('pokemon','trainer') or target.dead:raise ValueError('living Pokemon or trainer recipient required')
 if type(accepted) is not bool:raise ValueError('recipient acceptance must be explicit')
 import item_stock as STOCK,state_grants as G
 validate(target)
 stock=STOCK.prepare(e,actor,'item/'+item,held_selection=held_selection,count=count)
 INJURY.healed_today(target)
 if not accepted:return {'activity':'apply_bandages','status':'refused'}
 if item=='파스':
  import food_effects as FOOD
  state=FOOD.herbal_preflight(e,target,'item/파스')
  if state['count']+count>=3:
   import combat_stage_sources as STAGES
   STAGES.prepared(target)
 if resumable:
  def prepare(e,a,*others):
   return dict(target_id=target.entity_id,item=item,count=count,reason=reason,stock=stock),None
  return CLOCK.run_activity(e,actor,[actor,target],request_id=request_id,kind='bandage_application',seconds=minutes*60,source='item/'+item,request=request,prepare=prepare,finish=finish)
 def commit(e,actor,target):
  clock=e.advance_time(minutes*60,[actor,target],source='item/'+item)
  return _finish_application(e,actor,target,item=item,count=count,reason=reason,stock=stock,clock=clock)[0]
 return G.transition(e,actor,commit,participants=(target,))


def _finish_application(e,actor,target,*,item,count,reason,stock,clock):
 import item_stock as STOCK,clock_invocations as CLOCK
 stock_receipt=STOCK.debit(e,actor,stock)
 target.spec.pop('rest_interval',None)
 records=target.spec.setdefault('bandages',[])
 record=dict(id='bandage-'+str(len(records)+1),item=item,source_id='item/'+item,count=count,started_at=e.elapsed_seconds,
  expires_at=e.elapsed_seconds+LIFETIME,gap_count=len(e.unresolved_time_intervals),status='active',
  duration_reason=reason,applied_by=actor.spec.get('id'),item_stock=stock_receipt)
 records.append(record)
 CLOCK.bind(e,clock,record,kind='bandage_application',owner_id=target.entity_id,step_id=record['id'])
 if item=='파스':
  import food_effects as FOOD
  for _ in range(count):FOOD.herbal_consumed(e,target,'item/파스')
 return {'activity':'apply_bandages','record':dict(record)},stock_receipt,record


def resolve_timing(e,actor,*,target,bandage_id,remaining_seconds,reason):
 """Explicit GM time correction only; cannot revive a damaged/expired dressing."""
 import pokemon_activities as P
 validate(target)
 P._text(reason,'GM timing reason');C.integer(remaining_seconds,'remaining bandage seconds',0,LIFETIME)
 record=next((x for x in _live(target) if x['id']==bandage_id),None)
 if not record or _certain(e,record):raise ValueError('an actual unresolved active bandage is required')
 if remaining_seconds>max(0,record['expires_at']-e.elapsed_seconds):raise ValueError('unknown elapsed time cannot extend the known remaining lifetime')
 record.setdefault('time_rulings',[]).append(dict(at=e.elapsed_seconds,remaining_seconds=remaining_seconds,reason=reason))
 record['expires_at']=e.elapsed_seconds+remaining_seconds;record['gap_count']=len(e.unresolved_time_intervals);record.pop('timing_pending',None)
 advance(e,target)
 return dict(record)

def rest_healing(e,c,*,previous,rest_id,blocks,block_minutes,fraction,heavy_threshold,caretaker=False):
 """Plan whole known rest blocks, with time-qualified coverage and injury threshold.
 Mixed coverage is deliberately unresolved, rather than inferred prorating.
 """
 validate(c)
 if type(caretaker)is not bool:raise ValueError('explicit native Caretaker rest contribution required')
 if caretaker and __import__('study_books').care_owner(e,c,rest_id) is None:raise ValueError('actual Caretaker shared rest scope required')
 from fractions import Fraction
 def amount(covered):
  rate=Fraction('1/8' if covered else fraction)+(Fraction(fraction) if caretaker else 0)
  return M.product(c.base_max_hp,str(rate))
 records=[] if __import__('glitch_bender').benefits_blocked(c) else _live(c)
 if not records:return blocks*amount(False) if c.injuries<heavy_threshold else 0
 if any(not _certain(e,x) for x in records):raise ValueError('bandage lifetime requires GM timing resolution before resting')
 carry=previous['carry_minutes'] if previous and rest_id is not None and previous['id']==rest_id else 0
 start=e.elapsed_seconds-carry*60;step=block_minutes*60
 injuries=c.injuries;protected=ENVIRONMENT.protected_injuries(c);spent=INJURY.healed_today(c);limit=e.r.mech('combat/resting')['pokemon_center']['max_injuries_removed_per_day']
 limit=__import__('csv_item_capability_contracts').daily_injury_heal(c,limit)+__import__('study_books').care_injury_bonus(e,c)
 expiries=sorted(records,key=lambda x:x['expires_at']);processed=set();projected=copy(c)
 for i in range(blocks):
  a=start+i*step;b=a+step
  for record in expiries:
   if record['id'] not in processed and record['expires_at']<=a:
    n=min(record['count'],max(0,injuries-protected),max(0,limit-spent));injuries-=n;spent+=n;processed.add(record['id'])
  covered=any(x['started_at']<=a and x['expires_at']>=b for x in records)
  intersects=any(x['started_at']<b and x['expires_at']>a for x in records)
  if intersects and not covered:raise ValueError('bandage changes inside a 30-minute rest block; partial-block healing needs GM ruling')
  projected.injuries=injuries
  if injuries<heavy_threshold:projected.hp=max(projected.hp,min(projected.max_hp,projected.hp+amount(covered)))
 return projected.hp-c.hp

ACTIVITIES={'apply_bandages':apply,'resolve_bandage_timing':resolve_timing}
