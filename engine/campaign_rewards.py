"""Explicit GM rewards, real purchases and one-observation luck receipts.
No skill/accuracy modifiers affect the source's separate luck d20. No amount
recommendation creates a hard cap; unspecified lottery success stays unresolved.
"""
from copy import deepcopy
from pathlib import Path
import json,hashlib
import common_checks as C
import roll_pools as POOLS
from arithmetic import exact
SOURCE='ch11-running-the-game/샘플-스타팅-포켓몬-리스트/돈-문제'
CURRENCY_SOURCE='input/ch11-running-the-game.md:1351-1353'
POINTS_PER_DOLLAR=50
SALON_SOURCE='definition/패셔니스타'
SALON_SERVICES={'스타일리시한 단장':'definition/흔한-2','정교한 가장':'definition/희귀한-2'}
SALON_PRICE=1000
KINDS=('battle','berry','ball','healing','stone','vitamin','held','tm')
import resolution_transaction as _FINGERPRINTS

def text(v,n):
 if not isinstance(v,str) or not v.strip():raise ValueError(n+' required')
 return v
def source(e):
 if e.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected reward source requires its own policy')
def base(e,actor,*,reward_source=True):
 if reward_source:source(e)
 if actor.kind!='trainer':raise ValueError('actual trainer recipient required')
 uid=text(actor.spec.get('id'),'actual trainer identity')
 actors=getattr(e.gm,'everyone',[])
 if sum(c is actor for c in actors)!=1 or any(c is not actor and c.spec.get('id')==uid for c in actors):raise ValueError('actual unique registered trainer required')
 import effect_contracts as EC, passive_events as PE, heavy_injury_adapter as H, league_runtime as L
 EC.ensure_clear(e);PE.ensure_clear(e);H.ensure_clear(e);L.check_boundary(e,'campaign_reward')
 if e.encounter_active or e._active_turn_actor is not None:raise ValueError('campaign reward requires completed encounter and action')
def item(e,key):
 if isinstance(key,str) and key.startswith('TM'):
  import pokemon_teaching as T
  row=T.catalog(e.r)['machines'].get(key)
  if not row or row['kind']!='TM':raise ValueError('actual selected TM identity required')
  return key, row.get('price')
 effects,h=e.r.item_effects(key)
 if not h.get('id'):raise ValueError('actual selected item identity required')
 # Existing inventory consumers use the catalogue display name or canonical ID.
 uid=h['id'];name=e.r.items_mech.get(uid,{}).get('name') or uid
 # A chosen identity must not become an unresolved display-name choice again.
 candidates=[candidate for candidate in e.r.selection.names.get(name,())
             if candidate.startswith(('item/','augment/'))]
 if len(candidates)>1:name=uid
 return name,h.get('price')
def policy_hash(row):return _FINGERPRINTS.json_fingerprint(row, sort_keys=True, compact=False, allow_nan=True)
def policy(e):
 source(e);row=getattr(e,'_campaign_reward_policy',None)
 if not row or row.get('source')!=SOURCE:raise ValueError('explicit GM reward policy required')
 for values in row['pools'].values():
  for name in values:item(e,name)
 for name in row['lottery_choices']:item(e,name)
 return row
def events(e):return getattr(e,'_campaign_reward_events',{})
def fresh(e,actor,event_id):
 base(e,actor);text(event_id,'actual reward event identity')
 if event_id in events(e):raise ValueError('reward event already observed or consumed')
def put(e,key,row):
 if not hasattr(e,'_campaign_reward_events'):e._campaign_reward_events={}
 e._campaign_reward_events[key]=row
 return row
def owned(e,actor,key,kind):
 base(e,actor);row=events(e).get(key)
 if not row or row.get('owner')!=actor.spec['id'] or row.get('kind')!=kind or row.get('source')!=SOURCE:raise ValueError('actual owned event receipt required')
 return row
def amount(v,name='amount'):return C.integer(v,name,0)
def balances(actor,money=0,items=None,credit=None):
 amount(actor.spec.get('money',0),'actual money')
 for k in items or {}:amount(actor.spec.get('items',{}).get(k,0),'actual item count')
 if credit:
  for merchant in credit:amount(actor.spec.get('store_credit',{}).get(merchant,0),'actual store credit')
def pay(actor,*,money=0,items=None,credit=None):
 if money:actor.spec['money']=actor.spec.get('money',0)+money
 for k,v in (items or {}).items():actor.spec.setdefault('items',{})[k]=actor.spec.get('items',{}).get(k,0)+v
 for k,v in (credit or {}).items():actor.spec.setdefault('store_credit',{})[k]=actor.spec.get('store_credit',{}).get(k,0)+v
def configure(e,actor,*,pools,merchant,reason,spend_basis,lottery_success=None,lottery_choices=(),luck_table=None):
 base(e,actor);text(reason,'GM adopted example or modified table/pool reason');text(merchant,'actual promotion merchant')
 if spend_basis not in ('cash','price'):raise ValueError('GM program must explicitly choose cash spent or purchase price as its qualifying basis')
 if not isinstance(pools,dict) or set(pools)!=set(KINDS):raise ValueError('each adopted reward category requires a concrete GM item pool')
 resolved={}
 for k,values in pools.items():
  if not isinstance(values,(list,tuple)) or not values:raise ValueError('nonempty explicit reward pool required')
  values=[item(e,n)[0] for n in values]
  if len(values)!=len(set(values)):raise ValueError('duplicate pool would change random weighting')
  resolved[k]=values
 data=json.loads((Path(e.r.root)/'data/campaign-reward-policy.json').read_text(encoding='utf8'))
 table=list(data['luck_table'] if luck_table is None else luck_table)
 if len(table)!=20 or any(k not in ('none','money',*KINDS) for k in table):raise ValueError('GM table must specify each actual d20 face')
 if lottery_success is not None:
  if not isinstance(lottery_success,(list,tuple)) or len(set(lottery_success))!=len(lottery_success) or any(type(n)is not int or not 1<=n<=20 for n in lottery_success):raise ValueError('explicit distinct lottery winning faces required')
  lottery_success=list(lottery_success)
 choices=[item(e,k)[0] for k in lottery_choices]
 if len(choices)!=len(set(choices)):raise ValueError('distinct lottery choices required')
 if lottery_success and not choices:raise ValueError('winning lottery requires concrete GM chosen ball/healing reward options')
 row={'source':SOURCE,'pools':resolved,'table':table,'merchant':merchant,'reason':reason,'spend_basis':spend_basis,'lottery_success':lottery_success,'lottery_choices':choices,'lottery_minimum':data['purchase_lottery_example_minimum'],'punch':data['punch_example'],'cash_die':data['cash_die'],'cash_multiplier':data['cash_multiplier']}
 e._campaign_reward_policy=row
 return deepcopy(row)
def grant(e,actor,*,event_id,kind,reason,money=0,items=None,credits=None):
 fresh(e,actor,event_id);text(reason,'GM actual reward/difficulty or donor reason')
 if kind not in ('gym','contest','family','side_job','service_sale'):raise ValueError('explicit sourced reward context required')
 amount(money);planned={}
 for k,v in (items or {}).items():
  amount(v,'reward count');name,_=item(e,k);planned[name]=planned.get(name,0)+v
 credits=deepcopy(credits or {})
 for k,v in credits.items():text(k,'coupon/credit merchant');amount(v,'credit value')
 balances(actor,money,planned,credits)
 row={'kind':'grant','context':kind,'owner':actor.spec['id'],'source':SOURCE,'money':money,'items':planned,'credits':credits,'reason':reason,'status':'paid'}
 pay(actor,money=money,items=planned,credit=credits);put(e,event_id,row)
 return deepcopy(row)
def purchase(e,actor,*,event_id,merchant,items,reason,credit=0,unit_prices=None,price_currency='point',ball_shop_id=None):
 import ball_shop_availability as BALLS
 return BALLS.purchase(e,actor,ball_shop_id=ball_shop_id,event_id=event_id,merchant=merchant,items=items,reason=reason,credit=credit,unit_prices=unit_prices,price_currency=price_currency)
def _purchase(e,actor,*,event_id,merchant,items,reason,credit=0,unit_prices=None,price_currency='point'):
 fresh(e,actor,event_id);text(merchant,'actual merchant');text(reason,'actual purchase/price agreement');amount(credit,'redeemed credit')
 # This explicitly adopts the source's optional dollar quotation for this sale.
 # Money, credit, catalogue prices and promotion thresholds remain integer points.
 if price_currency not in ('point','dollar'):raise ValueError('explicit point or dollar price currency required')
 if price_currency=='dollar' and unit_prices is None:raise ValueError('explicit GM agreed dollar unit prices required')
 if not isinstance(items,dict) or not items:raise ValueError('actual purchased inventory required')
 planned={};prices={};quoted={};total=0
 if unit_prices is not None and set(unit_prices)!=set(items):raise ValueError('agreed price must identify each purchased item')
 for key,n in items.items():
  C.integer(n,'purchased count',1);name,catalog_price=item(e,key)
  price=catalog_price if unit_prices is None else unit_prices[key]
  if price_currency=='dollar':
   try:native=exact(price)
   except (ValueError,ArithmeticError) as exc:raise ValueError('finite exact dollar unit price required') from exc
   value=native*POINTS_PER_DOLLAR
   if native<0 or value.denominator!=1:raise ValueError('dollar unit price must equal nonnegative whole points without rounding')
   price=value.numerator;quoted[name]=str(native)
  amount(price,'actual unit price')
  if name in planned:raise ValueError('same canonical item repeated')
  planned[name]=n;prices[name]=price;total+=price*n
 balances(actor,0,planned,{merchant:credit})
 if credit>total or credit>actor.spec.get('store_credit',{}).get(merchant,0) or actor.spec.get('money',0)<total-credit:raise ValueError('insufficient actual money or merchant credit')
 p=getattr(e,'_campaign_reward_policy',None)
 if p is not None:p=policy(e)
 row={'source':SOURCE,'kind':'purchase','owner':actor.spec['id'],'merchant':merchant,'items':planned,'unit_prices':prices,'price':total,'cash_spent':total-credit,'credit_spent':credit,'reason':reason,'policy':deepcopy(p),'status':'paid','promotion_consumed':False,'lottery_event':None}
 if price_currency=='dollar':row['quotation']={'source':CURRENCY_SOURCE,'unit':'dollar','points_per_unit':POINTS_PER_DOLLAR,'unit_prices':quoted,'total':str(exact(total)/POINTS_PER_DOLLAR),'settlement_unit':'point','credit_unit':'point'}
 actor.spec['money']=actor.spec.get('money',0)-(total-credit)
 if credit:actor.spec['store_credit'][merchant]-=credit
 pay(actor,items=planned);put(e,event_id,row)
 return deepcopy(row)
def salon(e,actor,*,event_id,provider,target,service,document,reason,context=None,decisions=None):
 """Buy an explicitly authored service; ch11 supplies price and lifetime only.

 The GM registers the chosen service's entire definition with the existing
 source-policy API. No class feature, item or numerical benefit is inferred
 from the service name. Every declared contribution must use the recipient's
 next actual extended-rest milestone through the native lifetime consumer.
 """
 import world_entities as WORLD,source_policy as POLICY
 import source_policy_state as STATE,effect_lifetimes as LIFE
 import effect_lifetime_policy as LIFETIME,state_grants as GRANTS
 def plan(engine,payer,salon_provider,recipient):
  base(engine,payer,reward_source=False);text(event_id,'actual service event identity')
  if event_id in events(engine):raise ValueError('service event already observed or consumed')
  text(reason,'GM adopted service definition and actual availability reason')
  WORLD.require_actors(engine,salon_provider,recipient)
  if salon_provider.kind!='trainer' or recipient.kind not in ('trainer','pokemon'):
   raise ValueError('actual NPC salon provider and trainer or Pokemon recipient required')
  if service not in SALON_SERVICES:raise ValueError('exact ch11 salon service required; no feature alias')
  for uid in (SALON_SOURCE,SALON_SERVICES[service]):
   if engine.r.select_source_definition(uid)['selected_id']!=uid:
    raise ValueError('selected salon source requires its own service policy')
  prepared=POLICY.resolve(engine.r,document,context=context,decisions=decisions,
   _state_reader=lambda specs:STATE.read(engine,salon_provider,recipient,specs))
  authored=prepared['authored_source']
  if not authored or authored['title']!=service:
   raise ValueError('explicit registered definition of the chosen salon service required')
  if prepared['status']!='PolicyValuesReady':return prepared
  values=prepared['values']
  if set(values)!={'effects'} or not isinstance(values['effects'],list) or not values['effects']:
   raise ValueError('salon service requires its actual nonempty native effects')
  for effect in values['effects']:
   if (not isinstance(effect,dict) or effect.get('target')!='target'
       or effect.get('until')!={'event':'extended_rest','owner':'target','after':1}
       or any(key in effect for key in ('duration','while','repeat'))):
    raise ValueError('each salon contribution must end at the recipient next extended rest')
   prepared_effect=LIFE.prepare(engine,salon_provider,recipient,effect,prepared['selected_id'])
   if not prepared_effect or LIFETIME.KEY not in prepared_effect:
    raise ValueError('salon effect needs an existing native lifetime consumer')
  balances(payer)
  if payer.spec.get('money',0)<SALON_PRICE:raise ValueError('insufficient actual salon payment')
  return prepared
 prepared=plan(e,actor,provider,target)
 if prepared['status']!='PolicyValuesReady':return prepared
 def apply(engine,payer,salon_provider,recipient):
  if plan(engine,payer,salon_provider,recipient)!=prepared:
   raise ValueError('adopted salon definition changed before payment')
  # Receiving/providing this service is an actual interruption of a rest bout.
  import downtime as DOWNTIME,combat_timing as TIMING
  for participant in {payer,salon_provider,recipient}:DOWNTIME.interrupt_rest(participant)
  execution=POLICY.execute_effects(engine,salon_provider,recipient,document,
   context=context,decisions=decisions)
  if execution['status']!='PolicyEffectsCompleted' or any(row['status']!='completed' for row in execution['outcomes']):
   raise ValueError('actual salon effects must complete before payment')
  receipts={row['receipt'] for row in execution['outcomes']}
  installed=[record for record in TIMING.records(recipient) if record.get('effect_receipt') in receipts]
  if (len(installed)!=len(prepared['values']['effects'])
      or any(record.get('source')!=prepared['selected_id'] for record in installed)):
   raise ValueError('every salon effect needs its actual recipient lifetime contribution')
  row={'kind':'salon','source':SALON_SOURCE,'service_source':SALON_SERVICES[service],
   'owner':payer.entity_id,'provider':salon_provider.entity_id,'recipient':recipient.entity_id,
   'service':service,'price':SALON_PRICE,'cash_spent':SALON_PRICE,'reason':reason,
   'definition_source':prepared['selected_id'],'definition_hash':prepared['definition_hash'],
   'execution_id':execution['execution_id'],'occurrences':[record['effect_occurrence'] for record in installed],
   'status':'paid'}
  pay(payer,money=-SALON_PRICE);put(engine,event_id,row)
  return deepcopy(row)
 return GRANTS.transition(e,actor,apply,participants=(provider,target),include_grid=e.grid is not None)
def receipt_policy(e,row):
 current=policy(e)
 if row.get('policy')!=current:raise ValueError('source or GM policy changed after the actual purchase/observation')
 return current
def promotion(e,actor,*,purchase_id):
 row=owned(e,actor,purchase_id,'purchase');p=receipt_policy(e,row)
 if row['promotion_consumed']:raise ValueError('purchase promotion already consumed')
 if row['merchant']!=p['merchant']:raise ValueError('purchase is not from participating merchant')
 config=p['punch'];merchant=p['merchant'];prior=actor.spec.get('promotion_punches',{}).get(merchant,0);amount(prior,'actual accumulated punches')
 carry=actor.spec.get('promotion_spend_remainders',{}).get(merchant,0);amount(carry,'unpunched actual spend')
 qualified=row['cash_spent'] if p['spend_basis']=='cash' else row['price']
 new_punches,remainder=divmod(carry+qualified,config['spend_per_punch']);punches=prior+new_punches;cycles,left=divmod(punches,config['punches_per_credit']);value=cycles*config['credit']
 balances(actor,credit={merchant:value});actor.spec.setdefault('promotion_punches',{})[merchant]=left;actor.spec.setdefault('promotion_spend_remainders',{})[merchant]=remainder;pay(actor,credit={merchant:value});row['promotion_consumed']=True;row['promotion_result']={'punches':left,'credit':value}
 return deepcopy(row['promotion_result'])
def luck(e,actor,*,event_id,reason,fixed=None,fixed_cash=None):
 fresh(e,actor,event_id);text(reason,'GM actual occasion of inventory need');p=policy(e)
 if fixed is not None:C.integer(fixed,'observed luck d20',1,20)
 if fixed_cash is not None:C.integer(fixed_cash,'observed cash d4',1,4)
 balances(actor,items={k:1 for values in p['pools'].values() for k in values})
 row=put(e,event_id,{'kind':'luck','source':SOURCE,'owner':actor.spec['id'],'reason':reason,'policy':deepcopy(p),'status':'observing','rolls':[]})
 face=e.roll_d20(actor,'luck',fixed=fixed);row['rolls'].append({'die':20,'value':face});kind=p['table'][face-1];row['category']=kind
 if kind=='money':
  value=POOLS.die(e.rng,p['cash_die'],fixed=fixed_cash);row['rolls'].append({'die':p['cash_die'],'value':value});row['money']=value*p['cash_multiplier'];pay(actor,money=row['money'])
 elif kind!='none':
  choices=p['pools'][kind];index=e.rng.randrange(len(choices));name=choices[index];row['pool_index']=index;row['item']=name;pay(actor,items={name:1})
 row['status']='paid';return deepcopy(row)
def lottery(e,actor,*,event_id,purchase_id,fixed=None):
 fresh(e,actor,event_id);purchase_row=owned(e,actor,purchase_id,'purchase');p=receipt_policy(e,purchase_row)
 if p['lottery_success'] is None:return C.PendingDecision('GM must choose lottery success before any luck observation')
 if purchase_row['merchant']!=p['merchant'] or (purchase_row['cash_spent'] if p['spend_basis']=='cash' else purchase_row['price'])<p['lottery_minimum']:raise ValueError('actual qualifying purchase required')
 if purchase_row['lottery_event'] is not None:raise ValueError('purchase lottery already observed')
 if fixed is not None:C.integer(fixed,'observed lottery d20',1,20)
 balances(actor,items={k:1 for k in p['lottery_choices']})
 row=put(e,event_id,{'kind':'lottery','source':SOURCE,'owner':actor.spec['id'],'purchase_id':purchase_id,'policy':deepcopy(p),'status':'observing'});purchase_row['lottery_event']=event_id
 face=e.roll_d20(actor,'lottery',fixed=fixed);row['face']=face;row['status']='awaiting_choice' if face in p['lottery_success'] else 'lost'
 return deepcopy(row)
def claim_lottery(e,actor,*,event_id,item_name):
 row=owned(e,actor,event_id,'lottery');p=receipt_policy(e,row)
 if row['status']!='awaiting_choice':raise ValueError('unconsumed actual winning lottery required')
 name,_=item(e,item_name)
 if name not in p['lottery_choices']:raise ValueError('actual permitted prize selection required')
 balances(actor,items={name:1});pay(actor,items={name:1});row.update(status='paid',item=name)
 return deepcopy(row)
def wager(e,actor,*,event_id,opponent,stakes,consents,reason):
 fresh(e,actor,event_id);base(e,opponent);text(reason,'mutual actual wager terms')
 parties=[actor,opponent];ids=[x.spec['id'] for x in parties]
 if actor is opponent or set(stakes)!=set(ids) or set(consents)!=set(ids) or any(v is not True for v in consents.values()):raise ValueError('both actual parties must agree to their exact stakes')
 for c in parties:
  C.integer(stakes[c.spec['id']],'agreed stake',1);balances(c)
  if c.spec.get('money',0)<stakes[c.spec['id']]:raise ValueError('actual stake funds required')
 row={'kind':'wager','source':SOURCE,'owner':actor.spec['id'],'parties':parties,'stakes':deepcopy(stakes),'consents':deepcopy(consents),'reason':reason,'after_league_sequence':len(getattr(e,'_league_outcomes',{})),'status':'escrowed'}
 for c in parties:c.spec['money']-=stakes[c.spec['id']]
 put(e,event_id,row);return {'event_id':event_id,'status':'escrowed','stakes':deepcopy(stakes)}
def settle_wager(e,actor,*,event_id,encounter_id):
 row=owned(e,actor,event_id,'wager')
 import league_consequences as L
 L.source(e);match=getattr(e,'_league_outcomes',{}).get(encounter_id)
 if row['status']!='escrowed' or not match or match['status']!='settled' or match['sequence']<=row['after_league_sequence']:raise ValueError('unconsumed wager and later actual settled League result required')
 trainers={p:match['actors'][k] for p,role,k in match['bindings'] if role=='trainer'}
 if set(trainers.values())!=set(row['parties']):raise ValueError('wager parties do not match actual contest participants')
 winner=trainers[match['winner']];balances(winner);value=sum(row['stakes'].values());pay(winner,money=value)
 row.update(status='paid',encounter_id=encounter_id,winner=winner.spec['id'],payout=value)
 return {'status':'paid','winner':winner.spec['id'],'payout':value}
def perform(e,actor,activity,**options):
 if activity=='observe_ball_shop':
  import ball_shop_availability as BALLS
  return BALLS.observe(e,actor,**options)
 if activity=='league_result':
  base(e,actor,reward_source=False)
  import league_consequences as L
  return L.result(e,actor,**options)
 actions={'configure':configure,'grant':grant,'purchase':purchase,'salon':salon,'promotion':promotion,'luck':luck,'lottery':lottery,'claim_lottery':claim_lottery,'wager':wager,'settle_wager':settle_wager}
 if activity not in actions:raise ValueError('unsupported campaign reward operation')
 return actions[activity](e,actor,**options)

