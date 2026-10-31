"""One Vitamin dose lifecycle with sourced stat, TP and frequency effects."""
from copy import deepcopy
HEART='item/하트-부스터'
PP='item/pp업'
SPECIAL=(HEART,PP)
STAT_BY_ITEM=dict(zip(('item/맥스업','item/타우린','item/사포닌','item/리보플라빈','item/키토산','item/알칼로이드'),('hp','atk','def','spa','spd','spe')))
STAT_ITEMS=set(STAT_BY_ITEM)
# The eight rows of the original Vitamin table retain their existing callers.
ALL_ITEMS=STAT_ITEMS|set(SPECIAL)
SUPPRESSANT='item/억제제'
SUPPRESSANT_BERRIES=dict(zip(('item/유석열매','item/시마열매','item/파비열매','item/로매열매','item/또뽀열매','item/토망열매'),('hp','atk','def','spa','spd','spe')))


def recorded_consent(e,target,owner):
 """A stored food choice keeps the trainer who consented when it was prepared.
 Current ownership is re-checked by owner_consent at the moment the choice is used,
 so a transfer after preparation survives save/restore and is refused at use time."""
 import world_entities as W
 W.require_actors(e,target)
 if target.kind!='pokemon':raise ValueError('stat suppression requires a Pokemon target')
 if owner is None:return None
 W.require_actors(e,owner)
 if owner.kind!='trainer':raise ValueError('stat suppression consent must identify a trainer')
 return owner.entity_id


def owner_consent(e,target,owner):
 import world_entities as W
 W.require_actors(e,target)
 if target.kind!='pokemon':raise ValueError('stat suppression requires a Pokemon target')
 if owner is None:return None
 W.require_actors(e,owner)
 if owner.kind!='trainer' or W.identity_field(e,target,'owner_id')!=owner.entity_id:
  raise ValueError('stat suppression consent must identify the actual current owner')
 return owner.entity_id


def _history_ids(rules,spec):
 result=[]
 history=spec.get('vitamins',[])
 if not isinstance(history,list) or any(not isinstance(name,str) or not name.strip() for name in history):raise ValueError('Vitamin consumption history must preserve actual named doses')
 for name in history:
  uid=rules.item_effects(name)[1].get('id')
  if uid not in ALL_ITEMS|{SUPPRESSANT} or rules._selected_rule(uid)!=uid:raise ValueError('Vitamin history requires an actual selected Vitamin, not another item')
  result.append(uid)
 return result


def validate(c):
 import common_checks as C
 records=c.spec.get('vitamin_special_uses',{})
 if not isinstance(records,dict) or set(records)-set(SPECIAL):raise ValueError('invalid special Vitamin dose history')
 ids=_history_ids(c.r,c.spec)
 if not records:return True
 for uid,row in records.items():
  if c.r._selected_rule(uid)!=uid or not isinstance(row,dict) or row.get('source')!=uid or row.get('actor_id')!=c.entity_id or ids.count(uid)!=1:raise ValueError('special Vitamin requires exactly one preserved actual dose')
  C.integer(row.get('applied_at'),'actual special Vitamin application time',0)
  if uid==PP:
   mid=row.get('move_id');base=row.get('base_frequency')
   if c.r.move_id(mid)!=mid or not isinstance(base,list) or len(base)!=2 or base[0] not in ('at_will','every_other_turn','daily','scene') or type(base[1])is not int or base[1]<1:raise ValueError('PP Up requires its actual selected move and original frequency')
   if base[0] in ('at_will','every_other_turn') and base[1]!=1:raise ValueError('unbounded or every-other-turn frequency has one source use unit')
   if 'effective' in row and (type(row['effective']) is not bool or row['effective']!=(base[0]!='at_will')):raise ValueError('PP Up effectiveness disagrees with its selected source frequency')
 return True


def frequency(actor,mid,base):
 if actor is None:return base
 record=actor.spec.get('vitamin_special_uses',{}).get(PP)
 if not record or record.get('move_id')!=mid:return base
 validate(actor)
 if list(base)!=record['base_frequency']:raise ValueError('selected move frequency changed since PP Up; explicit source composition required')
 kind,count=base
 return base if kind=='at_will' else ('at_will',1) if kind=='every_other_turn' else (kind,count+1)


def _prepare_base(e,target,uid,*,selected_stat=None,owner_consent_by=None):
 import move_state as M
 if uid not in ALL_ITEMS|{SUPPRESSANT} or e.r._selected_rule(uid)!=uid:raise ValueError('selected Vitamin required')
 if target.kind!='pokemon':raise ValueError('Vitamins require a Pokemon target')
 owner_id=None
 if uid==SUPPRESSANT:
  if selected_stat not in STAT_BY_ITEM.values():raise ValueError('Stat Suppressant requires one selected base stat')
  owner_id=owner_consent(e,target,owner_consent_by)
 elif selected_stat is not None or owner_consent_by is not None:raise ValueError('stat choice and owner consent apply only to Stat Suppressants')
 validate(target);state=M.vitamin_state(e.r,target.spec)
 return owner_id,state


def prepare_effect(e,user,target,uid,*,selected_move=None,selected_stat=None,owner_consent_by=None):
 import move_state as M,common_checks as C
 owner_id,state=_prepare_base(e,target,uid,selected_stat=selected_stat,owner_consent_by=owner_consent_by)
 history=_history_ids(e.r,target.spec)
 no_effect=state['occupied']>=state['capacity'] or (uid in SPECIAL and uid in history) or (uid==SUPPRESSANT and owner_id is None)
 mid=None;base=None
 if uid==PP and not no_effect:
  mid=e.r.move_id(selected_move)
  if mid is None or mid not in M.known(e.r,{'moves':M.owned_list(target.spec,'moves',target.moves,rules=target.r)}):raise ValueError('PP Up requires one actually learned selected move')
  import frequency as F
  base=F.move_frequency(e,mid,target)
  if base[0] not in ('at_will','every_other_turn','daily','scene'):raise ValueError('PP Up selected move frequency needs its source policy')
 elif selected_move is not None and uid!=PP:raise ValueError('selected move applies only to PP Up')
 if uid==HEART and not no_effect:C.integer(target.spec.get('tutor_points'),'actual remaining Tutor Points',0)
 stat=selected_stat if uid==SUPPRESSANT else STAT_BY_ITEM.get(uid)
 delta=-1 if uid==SUPPRESSANT else 1
 if stat is not None:
  effects,_=e.r.item_effects(uid)
  expected={'type':'stat_base_mod','stat':'chosen' if uid==SUPPRESSANT else stat,'value':delta,'target':'target','vitamin':True}
  if effects!=[expected] or type(effects[0]['value']) is not int or effects[0]['vitamin'] is not True:raise ValueError('selected stat Vitamin needs its reviewed exact effect')
  import effects as FX
  if uid!=SUPPRESSANT:FX.preflight_effects(e,user,target,effects,uid,consumer='items.use_item')
  bonuses=target.spec.get('vitamin_bonus',{})
  if not isinstance(bonuses,dict):raise ValueError('actual permanent Vitamin stat contributions required')
  for key,value in bonuses.items():
   if key not in STAT_BY_ITEM.values():raise ValueError('unknown permanent Vitamin stat contribution')
   C.integer(value,'permanent Vitamin stat contribution')
 return dict(uid=uid,owner_id=owner_id,no_effect=no_effect,mid=mid,base=base,stat=stat,delta=delta)


def apply_paid(se,st,su,plan,stock_receipt):
 """Apply the native Vitamin result after one actual stock payment."""
 import consumption_execution as EXECUTION
 receipt=EXECUTION.validate(su)[EXECUTION.payment_id(su,stock_receipt)]
 if receipt['outcome']!='paid' or stock_receipt['item_id']!=plan['uid']:
  raise ValueError('Vitamin needs its unused actual item payment')
 uid,owner_id,no_effect,mid,base,stat,delta=(plan[k] for k in ('uid','owner_id','no_effect','mid','base','stat','delta'))
 import world_entities as W
 if plan!=prepare_effect(se,su,st,uid,selected_move=mid,
     selected_stat=stat if uid==SUPPRESSANT else None,
     owner_consent_by=W.actor_index(se).get(owner_id) if owner_id is not None else None):
  raise ValueError('Vitamin effect plan changed before its paid application')
 if uid==SUPPRESSANT and owner_id is not None:
  import world_entities as W
  if owner_consent(se,st,W.actor_index(se).get(owner_id))!=owner_id:raise ValueError('actual owner choice changed before stat suppression')
 import consumption_execution as EXECUTION
 if EXECUTION.suppress_benefit(se,su,st,stock_receipt):return (0,0)
 if no_effect:
  EXECUTION.finish(su,stock_receipt,target_id=st.entity_id,outcome='no_effect')
  if uid==SUPPRESSANT and owner_id is None:
   se.log('    Stat Suppressant consumed: no effect without actual owner consent',uid)
   return {'status':'consumed','outcome':'no_effect','reason':'owner_consent_missing'}
  se.log('    Vitamin maximum or once-only dose reached: no effect',uid);return (0,0)
 record={'source':uid,'actor_id':st.entity_id,'applied_at':se.elapsed_seconds,'item_stock':stock_receipt}
 if uid==PP:record.update(move_id=mid,base_frequency=list(base),effective=base[0]!='at_will')
 elif uid==HEART:st.spec['tutor_points']+=2
 else:
  import growth_stats as GROWTH
  GROWTH.apply_vitamin(st,stat,source=uid,delta=delta)
  if st.spec.get('species'):
   from builder import record_allocation
   record_allocation(se.r,st.spec,'vitamin',item=uid,stat=stat,delta=delta,
                     source=uid,actor_id=st.entity_id,applied_at=se.elapsed_seconds,item_stock=stock_receipt,
                     **({'owner_id':owner_id} if uid==SUPPRESSANT else {}))
 st.spec.setdefault('vitamins',[]).append(uid)
 import vitamin_capacity as CAPACITY
 CAPACITY.record(se.r,st.spec,'vitamin',len(st.spec['vitamins']),item=uid)
 if uid in SPECIAL:st.spec.setdefault('vitamin_special_uses',{})[uid]=record
 EXECUTION.finish(su,stock_receipt,target_id=st.entity_id,outcome='applied',
                   results=[{'kind':'vitamin','id':st.entity_id+':vitamin:'+str(len(st.spec['vitamins']))}])
 validate(st)
 return (0,0) if uid==PP and base[0]=='at_will' else (1,0)

def consume(e,user,target,uid,*,selected_move=None,selected_stat=None,owner_consent_by=None,free=False,held_selection=None):
 import item_stock as STOCK,state_grants as G
 _prepare_base(e,target,uid,selected_stat=selected_stat,owner_consent_by=owner_consent_by)
 stock=STOCK.prepare(e,user,uid,held_selection=held_selection,allow_empty=True)
 if stock is None:return (0,0)
 if free and e.encounter_active:raise ValueError('a waived Vitamin cost requires an actual source of action permission')
 plan=prepare_effect(e,user,target,uid,selected_move=selected_move,selected_stat=selected_stat,owner_consent_by=owner_consent_by)
 if e.encounter_active and (user.injuries>=5 and not __import__('taskmaster').ignores_acting_loss(user)) and not free:
  raise ValueError('Vitamin Standard requires reviewed heavy-injury action composition')
 def apply(se,st,su):
  import turn as TURN
  if not TURN.spend(se,su,'free' if free else 'standard',uid):return (0,0)
  return apply_paid(se,st,su,plan,STOCK.debit(se,su,stock))
 return G.transition(e,target,apply,participants=(user,))
