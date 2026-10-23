"""Shared plant identity, source-defined yield, container choice and harvest history.

A plant's existence is distinct from permission to cultivate its species. GM
observations can record an existing plant without inventing that permission.
Elapsed world time and narrative day/session clocks remain separate authorities.
"""
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import json
import common_checks as C

SOURCE='ch09-equipment/모험-도구/규토리-나무열매-허브'
PLANTER='item/나무열매플랜터'
MULCH='item/비료'


def policy(rules,name):
 cache=getattr(rules,'_cultivation_state_policies',None)
 if cache is None:cache={};rules._cultivation_state_policies=cache
 if name not in cache:cache[name]=json.loads((Path(rules.root)/('data/'+name+'-policy.json')).read_text(encoding='utf-8'))
 return cache[name]


def _berry_growth(tier):
 return {'tier':tier,'die':4 if tier==3 else 3,'offset':-tier}


def crop(rules,name):
 if not isinstance(name,str) or not name.strip():raise ValueError('named source plant required')
 data=policy(rules,'cultivation')
 if name in data['berries']:
  tier=data['berries'][name]['tier']
  return dict(_berry_growth(tier),kind='berry')
 if name=='흉내허브':
  import csv_item_food_contracts as CSV
  row=CSV.definition(rules,'item/흉내허브')
  if row is None or row['kind']!='mirror_herb' or rules._selected_rule(row['item_id'])!=row['item_id']:raise ValueError('exact selected Mirror Herb growth source required')
  # The CSV says it grows like tier-2 Berries; it remains an herb. This
  # supplies growth/yield for existing observations, no planting permission.
  return dict(_berry_growth(2),kind='herb')
 if name in data['apricorns']:return {'kind':'apricorn','die':2,'offset':-2}
 if name in data['herbs']:return dict(data['herbs'][name],kind='herb')
 # ch09:264 specifies this yield. Top Tier Berries does not grant its
 # cultivation; only an independently observed existing plant is admitted.
 if name=='향기버섯':return {'kind':'herb','die':4,'offset':-3}
 raise ValueError('plant species has no reviewed harvest source')


def plant_crop(rules,name,identity=None):
 """Separate an identified organism from a reviewed yield table.

 External growth declarations may carry a GM-observed actual seed species and
 kind. This supplies identity only: no duration, yield or harvest entitlement.
 """
 if identity is not None:
  if type(identity) is not dict or set(identity)!={'species','kind','seed_source','reason'}:raise ValueError('explicit observed plant identity required')
  for value in identity.values():
   if type(value) is not str or not value.strip():raise ValueError('named plant species/kind and GM seed evidence required')
  if identity['species']!=name:raise ValueError('observed plant species and declaration disagree')
  source=identity['seed_source']
  if source!=SOURCE and not source.startswith('item/'):raise ValueError('actual seed source required')
  if rules._selected_rule(source)!=source:raise ValueError('selected observed seed source changed')
 try:reviewed=crop(rules,name)
 except ValueError as exc:
  if str(exc)!='plant species has no reviewed harvest source' or identity is None:raise
  return {'kind':identity['kind'],'harvest_policy':'pending'}
 if identity is not None and identity['kind']!=reviewed['kind']:raise ValueError('observed identity cannot replace reviewed plant classification')
 return reviewed


def harvest_pending(plant):return plant.get('crop',{}).get('harvest_policy')=='pending'


def item_source(rules,name,identity=None):
 if identity is not None and plant_crop(rules,name,identity).get('harvest_policy')=='pending':return identity['seed_source']
 if name in policy(rules,'cultivation')['apricorns']:return SOURCE
 uid=rules.item_effects(name)[1].get('id')
 if not uid:raise ValueError('actual plant item identity required')
 if identity is not None and identity['seed_source']!=uid:raise ValueError('observed seed cannot replace reviewed item identity')
 return uid


def variant(rules,name):
 data=policy(rules,'planter')
 if name not in data['variants']:raise ValueError('explicit retained planter source policy required')
 return data['variants'][name],data['common']


def validate_mulch(actor,plant):
 import cultivation_growth as GROWTH
 return GROWTH.validate_fertilizers(actor,plant)


def mulch_bonus(actor,plant,day,soil):
 validate_mulch(actor,plant)
 import cultivation_growth as GROWTH
 return GROWTH.soil_bonus(plant,soil,day)


def apply_mulch(engine,actor,plant_id,*,soil_quality=0,reason):
 """Apply one owned unit to an actual plant; source gives no action duration.

This state adapter records application, not permission to take a free action.
Selected Korean day boundary is the existing narrative daily epoch.
"""
 import cultivation_growth as GROWTH
 return GROWTH.fertilize(engine,actor,plant_id,soil_quality=soil_quality,reason=reason)


def validate(actor):
 plants=actor.spec.get('plants',{})
 if not isinstance(plants,dict):raise ValueError('plants must be identified records')
 if not plants:return plants
 if actor.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected plant source needs its own state policy')
 slots=defaultdict(list)
 for pid,p in plants.items():
  if not isinstance(pid,str) or not pid.strip() or not isinstance(p,dict) or p.get('id')!=pid:raise ValueError('plant identity and mapping key must agree')
  identity=p.get('growth',{}).get('definition',{}).get('plant_identity')
  expected=plant_crop(actor.r,p.get('berry'),identity)
  if p.get('crop')!=expected:raise ValueError('plant yield must match its actual species source')
  for field in ('die','offset','tier','rank'):
   if field in p['crop']:C.integer(p['crop'][field],'source plant '+field)
  uid=item_source(actor.r,p['berry'],identity)
  if actor.r._selected_rule(uid)!=uid:raise ValueError('selected plant item source changed')
  C.integer(p.get('planted_at'),'actual planting time',0)
  C.integer(p.get('planted_session'),'actual planting session',0)
  if type(p.get('soft_soil')) is not bool:raise ValueError('actual soft-soil observation required')
  slot=p.get('planter_slot')
  if slot is not None:
   C.integer(slot,'actual planter slot',0);variant(actor.r,p.get('planter_policy'))
   if actor.r._selected_rule(PLANTER)!=PLANTER:raise ValueError('selected planter source changed')
   import physical_planter as PHYSICAL
   if PHYSICAL.KEY not in p:slots[slot].append(p)
  elif p.get('planter_policy') is not None:raise ValueError('outdoor plant cannot claim container protection')
  last=p.get('last_harvest_day')
  if last is not None:C.integer(last,'last actual harvest day',0)
  provenance=p.get('provenance')
  if provenance is not None:
   if not isinstance(provenance,dict) or provenance.get('source')!=SOURCE or provenance.get('item_source')!=uid:raise ValueError('plant provenance requires exact rule and crop sources')
   if provenance.get('origin')=='planted':
    C.integer(provenance.get('seed_count'),'actual planted seed count',1,1)
    if not isinstance(provenance.get('inventory_key'),str) or not provenance['inventory_key']:raise ValueError('actual planted inventory key required')
   elif provenance.get('origin')=='observed':
    if not isinstance(provenance.get('reason'),str) or not provenance['reason'].strip():raise ValueError('observed plant needs GM evidence')
   else:raise ValueError('actual plant provenance kind required')
  validate_mulch(actor,p)
  import cultivation_growth as GROWTH
  GROWTH.validate_stored(actor,p)
  if 'harvest_history' not in p:
   if provenance is not None:raise ValueError('sourced plant must retain its harvest history')
   continue # typed legacy observations retain unknown history
  rows=p['harvest_history']
  if not isinstance(rows,list):raise ValueError('harvest history must be records')
  if harvest_pending(p) and (rows or p.get('harvest_policy') is not None or last is not None):raise ValueError('unreviewed plant retains pending harvest policy; no fabricated yield history')
  previous=p.get('history_start_day')
  if previous is not None:C.integer(previous,'observed harvest history baseline',0)
  for sequence,row in enumerate(rows,1):
   if not isinstance(row,dict) or row.get('source')!=SOURCE or row.get('plant_id')!=pid:raise ValueError('harvest must retain its plant and source')
   C.integer(row.get('sequence'),'harvest sequence',sequence,sequence)
   if 'harvest_definition' in row:
    import cultivation_harvest as HARVEST
    HARVEST.validate_receipt(actor,p,row,rows[:sequence-1])
    previous=row['day']
    continue
   day=C.integer(row.get('day'),'actual harvest day',0)
   if previous is not None and day<=previous:raise ValueError('one harvest attempt per plant and increasing actual day')
   previous=day
   C.integer(row.get('at'),'harvest time',p['planted_at'])
   session=C.integer(row.get('session'),'harvest session',p['planted_session'])
   if slot is None or p['planter_policy']=='book-literal':
    if row['at']-p['planted_at']<policy(actor.r,'cultivation')['maturity_seconds']:raise ValueError('harvest preceded actual two-day maturity')
   elif session-p['planted_session']<variant(actor.r,p['planter_policy'])[0]['maturity_sessions']:raise ValueError('harvest preceded selected session maturity')
   face=C.integer(row.get('face'),'actual harvest die face',1,expected['die'])
   for key in ('soil_base','site_bonus','feature_bonus','amount','inventory_before','inventory_after'):
    C.integer(row.get(key),'harvest '+key,0 if key in ('amount','inventory_before','inventory_after') else None)
   if row['feature_bonus'] not in (0,1):raise ValueError('reviewed Botany soil contribution is zero or one')
   if row.get('feature_source')!=('input/ch04-trainer-classes.md:2097' if row['feature_bonus'] else None):raise ValueError('harvest feature contribution needs its actual source')
   if type(row.get('protected')) is not bool or row['protected']!=(slot is not None):raise ValueError('harvest container protection disagrees with plant')
   if type(row.get('environment_allows_growth')) is not bool:raise ValueError('actual harvest environment required')
   if not row['protected'] and not row['environment_allows_growth']:raise ValueError('outdoor harvest cannot ignore blocked growth')
   site=variant(actor.r,p['planter_policy'])[1]['soil_quality_bonus'] if slot is not None else int(p['soft_soil'])
   if row['site_bonus']!=site or (slot is not None and row['soil_base']!=0):raise ValueError('harvest site contribution disagrees with source')
   mulch=row.get('mulch_bonus',0);C.integer(mulch,'harvest mulch bonus',0)
   applications=row.get('mulch_applications',[])
   if not isinstance(applications,list) or len(set(applications))!=len(applications):raise ValueError('distinct actual mulch applications required')
   history=p.get('mulch_applications',[])
   for seq in applications:
    C.integer(seq,'harvest mulch application',1,len(history))
    if history[seq-1]['day']!=day:raise ValueError('expired mulch cannot affect this harvest day')
   if mulch!=min(len(applications),max(0,2-row['soil_base']-site)):raise ValueError('harvest mulch exceeds actual source/soil cap')
   amount=max(0,face+expected['offset']+row['soil_base']+site+row['feature_bonus']+mulch)
   if row['amount']!=amount or row['inventory_after']-row['inventory_before']!=amount or row.get('inventory_key')!=p['berry']:raise ValueError('harvest receipt yield and inventory disagree')
  if last!=previous:raise ValueError('last harvest day disagrees with retained attempts')
 for slot,occupants in slots.items():
  choice=occupants[0]['planter_policy'];selected,_=variant(actor.r,choice)
  import crafting_activities as A
  key=A._inventory(actor,'나무열매플랜터',slot+1)
  if selected['max_owned'] is not None and actor.spec['items'][key]>selected['max_owned']:raise ValueError('selected planter ownership limit exceeded')
  if any(p['planter_policy']!=choice for p in occupants) or len(occupants)>selected['capacity_per_planter']:raise ValueError('planter occupancy exceeds its retained selected source capacity')
 return plants


def record_harvest(actor,plant,receipt):
 # The caller owns admission, observed dice and the atomic graph commit.
 plant.setdefault('history_start_day',plant.get('last_harvest_day'))
 rows=plant.setdefault('harvest_history',[])
 rows.append(dict(receipt,source=SOURCE,plant_id=plant['id'],sequence=len(rows)+1))
 plant['last_harvest_day']=receipt['day']
 actor.spec['items'][receipt['inventory_key']]=receipt['inventory_after']
 return rows[-1]


def observe(engine,actor,*,plant_id,berry,planted_at,last_harvest_day,reason,
            planter_slot=None,planter_policy=None,soft_soil=False,planted_session=None):
 """GM observation of an existing plant, not a cultivation entitlement."""
 if not isinstance(reason,str) or not reason.strip():raise ValueError('GM plant observation reason required')
 if not isinstance(plant_id,str) or not plant_id.strip():raise ValueError('actual plant identity required')
 validate(actor)
 if plant_id in actor.spec.get('plants',{}):raise ValueError('existing plant cannot be replaced to erase its harvest history')
 C.integer(planted_at,'observed planting time',0,engine.elapsed_seconds)
 if planted_session is None:planted_session=engine.session_epoch
 C.integer(planted_session,'observed planting session',0,engine.session_epoch)
 if last_harvest_day is not None:C.integer(last_harvest_day,'observed last harvest day',0,actor.spec.get('frequency_state',{}).get('day',0))
 plant={'id':plant_id,'berry':berry,'crop':crop(engine.r,berry),'planter_slot':planter_slot,'planter_policy':planter_policy,'soft_soil':soft_soil,'planted_at':planted_at,'planted_session':planted_session,'last_harvest_day':last_harvest_day,'history_start_day':last_harvest_day,'harvest_history':[],
        'provenance':{'origin':'observed','source':SOURCE,'item_source':item_source(engine.r,berry),'reason':reason}}
 import state_grants as G
 def apply(e,c):
  c.spec.setdefault('plants',{})[plant_id]=deepcopy(plant);validate(c)
  if planter_slot is not None:
   import crafting_activities as A
   key=A._inventory(c,'나무열매플랜터',planter_slot+1)
   selected,_=variant(c.r,planter_policy)
   if selected['max_owned'] is not None and c.spec['items'][key]>selected['max_owned']:raise ValueError('selected planter ownership limit exceeded')
  e.gm._rec('식물 관측',None,plant,reason,c)
  return deepcopy(plant)
 return G.transition(engine,actor,apply)
