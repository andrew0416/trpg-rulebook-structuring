import arithmetic_policy as M
"""Source-selected food intake through real inventory, clock and healing.
Buff and herbal state reuse actor.buffs and the native extended-rest boundary.
"""
from copy import deepcopy
from pathlib import Path
import csv,hashlib,json
import effect_instances as INSTANCES
import common_checks as C
import roll_pools as POOLS
import turn as TURN
import action_lifecycle as ACTION
import equipment_item_contracts as EQUIPMENT

MEDICINE='ch09-equipment/모험-도구/약'
FOOD='ch09-equipment/모험-도구/음식'
DRINK_SOURCE='ch09-equipment/모험-도구/음료수'
GLUTTONY='ability/먹보-playtest'
CORE_GLUTTONY='ability/먹보'
CORE_BOUNDARY='core_gluttony_outside_boundary'
CORE_OBSERVATION='core_gluttony_quota_observation'
ENCOUNTER_RECEIPT='food_encounter'
DRINKS={'item/맛있는물':20,'item/나무열매쥬스':30,'item/미네랄사이다':30,'item/후르츠밀크':50,'item/튼튼밀크':80}
SNACKS={'item/초코바':{'kind':'heal','amount':5},'item/꿀':{'kind':'heal','amount':5},'item/먹다남은음식':{'kind':'turn_heal','denominator':16},'item/검은오물':{'kind':'turn_heal','denominator':8}}
CHEF_SNACK_IDS=frozenset({'item/짠맛-서프라이즈','item/매운맛-랩','item/신맛-캔디','item/떫은맛-웨이퍼','item/쓴맛-트리트','item/단맛-과자'})
SNACK_ITEMS=frozenset(SNACKS)|CHEF_SNACK_IDS|frozenset({'item/멘탈허브','item/하양허브','item/파워풀허브'})
HERBS={'item/힘의가루','item/힘의뿌리','item/만능가루','item/부활초','item/파스'}
BERRY_HEALS={'item/오랭열매':5,'item/자뭉열매':15}
BERRY_STAGES={'item/치리열매':'atk','item/용아열매':'def','item/캄라열매':'spe','item/야타비열매':'spa','item/규살열매':'spd'}
BERRY_IMMEDIATE=('berry_cure_any','berry_critical','berry_random_stage','berry_accuracy','berry_scene_move','berry_flavor')
BERRY_CHOICE='food_berry_choice'
BERRY_HIT_CHOICE='food_berry_hit_choice'
BERRY_PRIORITY_CHOICE='food_berry_priority_choice'
BERRY_POLICY_ITEMS=frozenset('item/'+name+'열매' for name in '리샘 랑사 스타 미클 과사 의문 자보 애터 악키 타라프 애슈 무화 위키 마고 아바 파야 라즈 블리 나나 서배 파인 메호키 자야 슈박 두리 루베'.split())
BERRY_CURES=dict(zip(('item/버치열매','item/유루열매','item/복슝열매','item/복분열매','item/배리열매','item/시몬열매','item/수숙열매','item/고스티열매','item/라부탐열매','item/노멜열매'),('마비','잠듦','독','화상','얼음','혼란','사슬묶기','난동','억압','헤롱헤롱')))
BERRY_TYPES=dict(zip(('item/오카열매','item/꼬시개열매','item/초나열매','item/린드열매','item/플카열매','item/로플열매','item/으름열매','item/슈캐열매','item/바코열매','item/야파열매','item/리체열매','item/루미열매','item/수불열매','item/하반열매','item/마코열매','item/바리비열매','item/카리열매'),('불꽃','물','전기','풀','얼음','격투','독','땅','비행','에스퍼','벌레','바위','고스트','드래곤','악','강철','노말')))
BABY_POLICIES={'book_xp20_level15','raw_training_level20','homebrew_initial_plus5'}
TRAINING_BABY_POLICIES={'raw_training_level20','homebrew_initial_plus5'}


import resolution_transaction as _FINGERPRINTS

def selected(e,uid):
 if e.r._selected_rule(uid)!=uid:raise ValueError('selected food source needs its own policy')


def _refreshment_definitions():
 common={'action':'extended','outside_combat':True,'limit':1,'gluttony_override':{'limit':2,'seconds':1800}}
 return {
  'korean_hour':dict(deepcopy(common),seconds=3600,reference='ch09:218-220',
   source={'file':'input/ch09-equipment.md','sha256':'b5aeb6b82af4b05fe0b369368f8b0181ed3b1d22079e8a86a1c4248e6cbf92d2'}),
  'english_half_hour':dict(deepcopy(common),seconds=1800,reference='core-1.05 LF8330-8334',
   source={'file':'source-audit/core-refreshments.txt','sha256':'15f3771817e6be667c720f43f95d2f581f65c34af3a7e69f2c54c99963126ccf'})}


def _refreshment_document(user,target,uid):
 definitions=_refreshment_definitions()
 return {'schema':1,'id':'native/ordinary-refreshment-intake','variants':[{
  'rule_id':DRINK_SOURCE,'source':definitions['korean_hour']['source'],
  'values':{'variant':{'$input':'source_text'},'definitions':definitions,
            'basis':{'user_id':user.entity_id,'target_id':target.entity_id,'item':uid}},
  'inputs':{'source_text':{'type':'string','authority':'gm','decision_kind':'source_conflict',
   'choices':list(definitions),'question':'Choose the complete Korean one-per-hour or English one-per-half-hour refreshment definition. Both retain actual Extended intake outside combat and the selected Gluttony override.'}}}]}


def _refreshment_resolution(e,user,target,uid,choice=None):
 import source_policy as POLICY
 import world_entities as WORLD
 from source_context import verified_source
 WORLD.require_actors(e,user,target)
 if uid not in DRINKS:raise ValueError('ordinary refreshment source choice requires an actual drink')
 selected(e,uid);selected(e,DRINK_SOURCE)
 result=POLICY.resolve(e.r,_refreshment_document(user,target,uid),
                       decisions={} if choice is None else {'source_text':choice})
 if result['status']=='PolicyValuesReady' and result['values']['variant']=='english_half_hour':
  verified_source(e.r,result['values']['definitions']['english_half_hour']['source'],
                  source_root='source-audit',label='English ordinary refreshments')
 return result


def refreshment_source_choices(e,user,target,uid):
 """Pure existing-source-policy query; pass its scoped choice as food_policy."""
 return _refreshment_resolution(e,user,target,uid)


def _refreshment_decision(e,user,target,uid,choice):
 from source_context import verified_source
 definitions=_refreshment_definitions()
 verified_source(e.r,definitions['korean_hour']['source'],label='Korean ordinary refreshments')
 basis={'user_id':user.entity_id,'target_id':target.entity_id,'item':uid}
 if choice is None:
  return {'variant':'korean_hour','definition':definitions['korean_hour'],
          'authority':'authored_default','basis':basis}
 result=_refreshment_resolution(e,user,target,uid,choice)
 if result['status']!='PolicyValuesReady':raise ValueError('complete scoped refreshment source decision required')
 variant=result['values']['variant']
 return {'variant':variant,'definition':result['values']['definitions'][variant],
         'authority':'gm','basis':basis,'choice':deepcopy(choice),'policy':result}


def herbal_state(actor):
 state=actor.spec.get('herbal_restoratives')
 if state is None:return {'source':MEDICINE,'count':0}
 if not isinstance(state,dict) or state.get('source')!=MEDICINE:raise ValueError('actual herbal consumption source required')
 if actor.r._selected_rule(MEDICINE)!=MEDICINE:raise ValueError('selected herbal history needs its own policy')
 count=C.integer(state.get('count'),'herbal count since Extended Rest',0)
 uses=state.get('uses',[])
 import consumption_history as HISTORY
 selected_uses=HISTORY.select(uses,source=MEDICINE)
 if selected_uses['count']!=count:raise ValueError('herbal count disagrees with actual consumption history')
 for index,use in enumerate(selected_uses['records'],1):
  if not isinstance(use,dict):raise ValueError('herbal use must be a sourced record')
  C.integer(use.get('count'),'herbal use sequence',index,index)
  if use.get('source')!=MEDICINE or use.get('item') not in HERBS:raise ValueError('herbal use has another source')
  if actor.r._selected_rule(use['item'])!=use['item']:raise ValueError('selected consumed herb needs its own history policy')
  if index==1:
   if 'buff_id' not in use or (use['buff_id'] is not None and (not isinstance(use['buff_id'],str) or not use['buff_id'])):raise ValueError('first herb requires its actual buff grant result')
  if index<3:
   if any(key in use for key in ('faces','stat','base_stage_delta')):raise ValueError('first two herbs have no random base-stage penalty')
  else:
   if __import__('study_books').herbal_protected(use):continue
   faces=use.get('faces')
   if not isinstance(faces,list) or not faces:raise ValueError('herbal penalty requires actual d6 faces')
   for face in faces:C.integer(face,'herbal penalty d6 face',1,6)
   if faces[-1]==6 or any(face!=6 for face in faces[:-1]):raise ValueError('herbal d6 rerolls only six until a stat is selected')
   if use.get('stat')!=('atk','def','spa','spd','spe')[faces[-1]-1]:raise ValueError('herbal selected stat disagrees with d6')
   C.integer(use.get('base_stage_delta'),'herbal base-stage penalty',-1,-1)
 return state

def validate_herbal(actor):
 """One history and source-owned penalty contract for both actor kinds."""
 state=herbal_state(actor)
 import combat_stage_sources as STAGES
 raw=actor.spec.get(STAGES.STATE,{})
 owned=raw.get('base',{}).get('herbal_restoratives') if isinstance(raw,dict) else None
 stages=STAGES.validate(actor) if 'herbal_restoratives' in actor.spec or owned is not None else None
 owned=(stages or {}).get('base',{}).get('herbal_restoratives')
 expected={}
 for use in state.get('uses',[])[2:]:
  if not __import__('study_books').herbal_protected(use):expected[use['stat']]=expected.get(use['stat'],0)-1
 if expected:
  if not isinstance(owned,dict) or owned.get('source')!=MEDICINE or owned.get('ends')!='extended_rest' or owned.get('deltas')!=expected:
   raise ValueError('herbal history and actual base-stage source disagree')
 elif owned is not None:raise ValueError('herbal base-stage penalty has no corresponding consumption')
 for buff in actor.buffs:
  if isinstance(buff,dict) and buff.get('source')==MEDICINE:
   if buff.get('item') not in HERBS or buff.get('effect')!={'kind':'save_bonus','amount':2}:
    raise ValueError('herbal Digestion Buff must retain its native +2 save benefit')
 return state


def herbal_gains_allowed(actor):
 state=herbal_state(actor)
 if state['count']<2:return True
 if actor.r._selected_rule(MEDICINE)!=MEDICINE:raise ValueError('selected herbal restriction needs its own policy')
 return False


def temp_hp_allowed(actor):
 import ability_state_projection as PROJECTION
 return not PROJECTION.temp_hp_blocked(actor) and herbal_gains_allowed(actor)

def gluttony(e,actor):
 return food_limits(e,actor) is not None


def food_limits(e,actor):
 import capacity_abilities as CAPACITY_ABILITIES
 return CAPACITY_ABILITIES.food_capacity(e,actor)


def _food_receipts(actor):
 receipts=actor.spec.get('food_consumption_receipts',[])
 if not isinstance(receipts,list) or any(not isinstance(row,dict) for row in receipts):raise ValueError('actual food consumption receipts required')
 for sequence,row in enumerate(receipts,1):
  C.integer(row.get('sequence'),'actual food receipt sequence',sequence,sequence)
 return receipts


def _quota_eligible(record):
 capacity=record.get(INSTANCES.KEY,{}).get('capacity',ordinary_capacity())
 return not capacity.get('scene_usage_exempt',False) and record.get('csv_food_source',{}).get('kind')!='dynamax_mushroom'


def _receipt_prefix(receipts,count):
 import root_resolution as ROOT
 C.integer(count,'observed food receipt prefix',0,len(receipts))
 return ROOT.fingerprint(receipts[:count])


def core_lesson_boundary(e,actor,source_id):
 """A completed outside lesson observes a prefix; it does not assign old encounter membership."""
 import state_grants as GRANTS
 source=actor.spec[GRANTS.KEY]['sources'][source_id]
 lesson=source.get('ability_lesson',{})
 if e.encounter_active or lesson.get('ability_id')!=CORE_GLUTTONY or lesson.get('completed_at')!=e.elapsed_seconds:
  raise ValueError('actual completed outside core Gluttony lesson required')
 receipts=_food_receipts(actor)
 actor.spec[CORE_BOUNDARY]={'source':CORE_GLUTTONY,'actor_id':actor.entity_id,
  'encounter_epoch':C.integer(getattr(e,'_party_encounter_epoch',0),'actual outside encounter epoch',0),
  'through_sequence':len(receipts),'receipts_fingerprint':_receipt_prefix(receipts,len(receipts)),
  'ability_source_id':source_id,'job_id':lesson['job_id'],'at':e.elapsed_seconds}


def _core_usage(e,actor):
 """Count all actual current exchanges, including those made while this Ability was absent."""
 epoch=C.integer(getattr(e,'_party_encounter_epoch',0),'actual encounter epoch',1)
 receipts=_food_receipts(actor);known=[];unknown=[]
 for index,row in enumerate(receipts,1):
  stamp=row.get(ENCOUNTER_RECEIPT)
  if ENCOUNTER_RECEIPT not in row:
   if _quota_eligible(row):unknown.append(index)
   continue
  if (not isinstance(stamp,dict) or set(stamp)!={'actor_id','encounter_epoch','eligible'}
      or stamp['actor_id']!=actor.entity_id or type(stamp['eligible']) is not bool
      or stamp['eligible']!=_quota_eligible(row)):
   raise ValueError('actual typed food encounter receipt required')
  if stamp['encounter_epoch'] is not None:C.integer(stamp['encounter_epoch'],'food exchange encounter epoch',1,epoch)
  if stamp['encounter_epoch']==epoch and stamp['eligible']:known.append(index)
 boundary=actor.spec.get(CORE_BOUNDARY)
 boundary_epoch=C.integer(boundary.get('encounter_epoch'),'outside lesson encounter boundary',0,epoch) if isinstance(boundary,dict) else epoch
 if isinstance(boundary,dict) and boundary_epoch<epoch:
  count=boundary.get('through_sequence')
  if (boundary.get('source')!=CORE_GLUTTONY or boundary.get('actor_id')!=actor.entity_id
      or boundary.get('receipts_fingerprint')!=_receipt_prefix(receipts,count)
      or not all(isinstance(boundary.get(key),str) and boundary[key] for key in ('ability_source_id','job_id'))):
   raise ValueError('actual outside core lesson receipt prefix changed')
  unknown=[index for index in unknown if index>count]
 observation=actor.spec.get(CORE_OBSERVATION)
 if isinstance(observation,dict):
  import capacity_abilities as CAPACITY
  observed_epoch=C.integer(observation.get('encounter_epoch'),'observed actual encounter epoch',1,epoch)
  count=observation.get('through_sequence');used=C.integer(observation.get('used'),'observed core food exchanges',0,3)
  if (observation.get('source')!=CORE_GLUTTONY or observation.get('source_reference')!=CAPACITY.CORE_SOURCE
      or observation.get('actor_id')!=actor.entity_id
      or observation.get('receipts_fingerprint')!=_receipt_prefix(receipts,count)
      or not isinstance(observation.get('reason'),str) or not observation['reason'].strip()
      or used<sum(row.get(ENCOUNTER_RECEIPT,{}).get('encounter_epoch')==observed_epoch
                  and _quota_eligible(row) for row in receipts[:count])):
   raise ValueError('actual current core Gluttony quota observation changed')
  if observed_epoch==epoch:
   return used+len([index for index in known if index>count]),any(index>count for index in unknown)
  # The old observation proves only that this prefix predates the later real encounter.
  unknown=[index for index in unknown if index>count]
 return len(known),bool(unknown)


def observe_core_gluttony_quota(e,actor,*,used,reason):
 """Record a present GM fact only when old receipts cannot prove current encounter membership."""
 import world_entities as WORLD,state_grants as GRANTS,capacity_abilities as CAPACITY
 WORLD.require_actors(e,actor)
 C.integer(used,'actual current encounter food exchanges',0,3)
 if not isinstance(reason,str) or not reason.strip():raise ValueError('actual current food quota observation reason required')
 def apply(staged,a):
  limits=food_limits(staged,a)
  if not staged.encounter_active or not limits or 'per_encounter' not in limits:
   raise ValueError('actual active core Gluttony encounter required')
  known,uncertain=_core_usage(staged,a)
  if used<known:raise ValueError('current observation cannot refill proven food exchanges')
  if not uncertain:raise ValueError('current food quota is already proven by native receipts')
  receipts=_food_receipts(a)
  record={'source':CORE_GLUTTONY,'source_reference':deepcopy(CAPACITY.CORE_SOURCE),'actor_id':a.entity_id,
   'encounter_epoch':staged._party_encounter_epoch,'through_sequence':len(receipts),
   'receipts_fingerprint':_receipt_prefix(receipts,len(receipts)),'used':used,'reason':reason,'at':staged.elapsed_seconds}
  a.spec[CORE_OBSERVATION]=record
  return deepcopy(record)
 return GRANTS.transition(e,actor,apply)


def buff_policy(rules):
 data=getattr(rules,'_food_buff_policy',None)
 if data is None:
  data=json.loads((Path(rules.root)/'data/food-buff-policy.json').read_text(encoding='utf-8'))
  _validate_chef_policy(rules,data)
  rules._food_buff_policy=data
 return data


def _validate_chef_policy(rules,data):
 if data.get('schema_version')!=2:raise ValueError('selected food policy schema changed')
 source=data.get('chef_source')
 if not isinstance(source,dict) or set(source)!={'file','file_sha256','columns'} or source['columns']!=[4,5,6,7]:raise ValueError('Chef source anchor changed')
 path=Path(rules.root)/source['file']
 if hashlib.sha256(path.read_bytes()).hexdigest()!=source['file_sha256']:raise ValueError('Chef source file changed')
 with path.open(encoding='utf-8-sig',newline='') as handle:rows=list(csv.reader(handle))
 policies=data.get('chef_snacks')
 if not isinstance(policies,dict) or set(policies)!=CHEF_SNACK_IDS:raise ValueError('Chef snack policy set changed')
 expected={'item/짠맛-서프라이즈':(4,'짠맛','received_attack',None,'temporary_hp'),
  'item/매운맛-랩':(5,'매운맛','attack','물리','bonus_damage'),
  'item/신맛-캔디':(6,'신맛','received_attack','물리','damage_reduction'),
  'item/떫은맛-웨이퍼':(7,'떫은맛','attack','특수','bonus_damage'),
  'item/쓴맛-트리트':(8,'쓴맛','received_attack','특수','damage_reduction'),
  'item/단맛-과자':(9,'단맛','self_activation',None,'timed_modifiers')}
 for uid,(record,flavor,trigger,attack_class,benefit_type) in expected.items():
  row=policies[uid]
  if set(row)!={'clause_id','recipe_id','record','cell_sha256','item_payload_authority','effect'} or row['item_payload_authority']!='recipe_row' or row['record']!=record or row['clause_id']!=f'C2CSV/input/db/class-data.csv:R{record}:recipe' or row['recipe_id']!='recipe/'+uid.split('/',1)[1]:raise ValueError('Chef source identity changed: '+uid)
  cells=[rows[record-1][column-1] for column in source['columns']]
  digest=_FINGERPRINTS.json_fingerprint(cells, sort_keys=False, compact=True, allow_nan=True)
  if digest!=row['cell_sha256']:raise ValueError('Chef source cells changed: '+uid)
  effect=row['effect'];benefit=effect.get('benefit',{})
  if effect.get('kind')!='chef_snack' or effect.get('flavor')!=flavor or effect.get('trigger')!=trigger or effect.get('attack_class')!=attack_class or benefit.get('type')!=benefit_type:raise ValueError('Chef executable policy changed: '+uid)
  if benefit_type in ('temporary_hp','bonus_damage','damage_reduction'):
   if benefit!={'type':benefit_type,'base':5,'liked':10}:raise ValueError('Chef numeric policy changed: '+uid)
  elif benefit!={'type':'timed_modifiers','evasion':4,'liked_accuracy':4,'lifetime':"end of user's next turn"}:raise ValueError('Chef timed policy changed')
  _,header=rules.item_effects(uid)
  if header.get('id')!=uid or header.get('category')!='음식' or header.get('use')!='consumable' or header.get('price')!=100:raise ValueError('Chef physical snack definition changed: '+uid)


def chef_effect(rules,uid):
 row=buff_policy(rules)['chef_snacks'].get(uid)
 return deepcopy(row['effect']) if row else None


def deferred_registration(rules,effect):
 # Acquiring Honey Paws registers ownership; only actual Honey intake creates
 # its independent effect. Unknown source payloads retain normal pending flow.
 source=effect.get('_rule_id','ability/'+str(effect.get('_ability')))
 row=buff_policy(rules)['capacity_exceptions'].get(source,{})
 expected=row.get('registration_effect')
 if expected is None or {k:v for k,v in effect.items() if not k.startswith('_')}!=expected:return False
 if rules._selected_rule(source)!=source:raise ValueError('selected Honey Paws registration source changed')
 return True


def ordinary_capacity():return {'bucket':'ordinary','source':FOOD,'scene_usage_exempt':False}


def capacity_from_source(rules,source):
 if rules._selected_rule(source)!=source:raise ValueError('capacity exception source changed')
 row=buff_policy(rules)['capacity_exceptions'].get(source)
 if row is None:raise ValueError('source-specific capacity exception required')
 return {'bucket':row['slot_bucket'],'source':source,'scene_usage_exempt':row['scene_usage_exempt']}


def validate_native(actor,buff,*,spent=False):
 if not INSTANCES.validate(buff,actor=actor,spent=spent):return False
 m=buff[INSTANCES.KEY]
 if buff.get('source') not in (FOOD,MEDICINE) or actor.r._selected_rule(buff['source'])!=buff['source']:raise ValueError('actual selected food producer required')
 uid=buff.get('item')
 import csv_item_food_contracts as CSV
 csv_choice=CSV.validate_native(actor,buff) if CSV.SELECTION in buff else None
 if not isinstance(uid,str) or (csv_choice is None and (actor.r.item_effects(uid)[1].get('id')!=uid or actor.r._selected_rule(uid)!=uid)):raise ValueError('actual source food identity required')
 effect_source=buff.get('effect_source')
 if not isinstance(effect_source,str) or (csv_choice is None and actor.r._selected_rule(effect_source)!=effect_source):raise ValueError('selected food effect definition required')
 definition=buff_policy(actor.r)['capacity_exceptions'].get(effect_source,{})
 if csv_choice is not None:
  if buff['source']!=FOOD:raise ValueError('CSV food needs the ordinary food producer')
  expected=CSV.effect(csv_choice)
 elif buff['source']==MEDICINE:
  expected={'kind':'save_bonus','amount':2} if effect_source==MEDICINE and uid in HERBS else None
 elif definition.get('item')==uid:expected=definition['effect']
 elif effect_source=='feat/경단':
  import chef_cooking as CHEF
  expected=CHEF.composite_expected(actor.r,buff)
 elif effect_source==uid:
  expected={'kind':'heal','amount':30} if uid=='item/나무열매쥬스' else snack_effect(actor.r,uid)
 else:expected=None
 if expected is None or buff['effect']!=expected:raise ValueError('food payload differs from its selected source definition')
 if m['kind']=='food_turn_healing':
  if spent or m['lifetime']!={'boundary':'encounter_end'} or m['capacity']!={'bucket':'none','source':buff['source']}:raise ValueError('ongoing food healing needs its encounter lifetime without a digestion slot')
  receipts=actor.spec.get('food_consumption_receipts',[])
  if not isinstance(receipts,list) or any(not isinstance(r,dict) for r in receipts):raise ValueError('typed food consumption history required')
  parents=[r for r in receipts if r.get('buff_id')==buff.get('buff_id')]
  if len(parents)!=1 or not _ongoing_parent_matches(parents[0],buff,uid,effect_source):raise ValueError('ongoing food effect lacks its actual consumed parent')
  if buff['effect'].get('kind')!='turn_heal':raise ValueError('typed food healing contribution required')
  C.integer(buff['effect'].get('denominator'),'food healing denominator',1)
  return True
 if m['kind']!='digestion' or m['lifetime']!=buff_policy(actor.r)['lifetime']:raise ValueError('selected Digestion Buff lifecycle required')
 cap=m['capacity']
 INSTANCES.text(cap.get('source'),'food capacity source')
 if cap.get('bucket')=='ordinary':
  if cap!=ordinary_capacity() or type(cap.get('scene_usage_exempt')) is not bool:raise ValueError('ordinary food capacity contract changed')
 elif cap!=capacity_from_source(actor.r,cap.get('source')) or type(cap.get('scene_usage_exempt')) is not bool:raise ValueError('source-exempt food capacity contract changed')
 transfer_origin=buff.get('food_transfer_origin')
 if len(m['ownership'])==1:
  if transfer_origin is not None:
   if cap.get('source')!='move/벌레먹기' or cap!=capacity_from_source(actor.r,'move/벌레먹기'):
    raise ValueError('copied food effect needs the Bug Bite capacity contract')
   if not isinstance(transfer_origin,dict) or set(transfer_origin)!={'source','holder_id','buff_id','receipt_sequence','receipt_scene','receipt_fingerprint'}:
    raise ValueError('typed consumed-food transfer origin required')
   if transfer_origin['source']!='move/벌레먹기' or not all(isinstance(transfer_origin[k],str) and transfer_origin[k] for k in ('holder_id','buff_id','receipt_fingerprint')):
    raise ValueError('consumed-food transfer origin identity required')
   C.integer(transfer_origin.get('receipt_sequence'),'consumed-food receipt sequence',1)
   C.integer(transfer_origin.get('receipt_scene'),'consumed-food receipt scene',0)
   if m.get('applied_by_actor_id')!=transfer_origin['holder_id']:
    raise ValueError('copied food effect and source holder disagree')
   expected_capacity=cap
  else:expected_capacity=capacity_from_source(actor.r,effect_source) if 'item' in definition else ordinary_capacity()
 else:
  if transfer_origin is not None:raise ValueError('live transfer cannot claim a consumed-food origin')
  for event in m['ownership'][1:]:
   if event['source']!='move/벌레먹기':raise ValueError('food transfer history needs its source-specific policy')
  expected_capacity=capacity_from_source(actor.r,m['ownership'][-1]['source'])
 if cap!=expected_capacity:raise ValueError('food capacity differs from actual acquisition or transfer source')
 effect=buff['effect'];kind=effect['kind']
 if kind in ('heal','save_bonus'):C.integer(effect.get('amount'),'food effect amount',1)
 elif kind=='turn_heal':C.integer(effect.get('denominator'),'food healing denominator',1)
 elif kind=='cure':INSTANCES.text(effect.get('status'),'food cure target')
 elif kind=='stat_suppression':
  if actor.kind!='pokemon':raise ValueError('Suppressant Berries require a Pokemon recipient')
  if effect!=snack_effect(actor.r,uid):raise ValueError('Suppressant Berry differs from its selected stat source')
 elif kind=='stage_change' or kind in (*BERRY_IMMEDIATE,'berry_reactive','berry_priority','berry_ingredient'):
  if effect!=snack_effect(actor.r,uid):raise ValueError('stage Berry differs from its exact printed stat source')
 elif kind=='type_resistance':
  INSTANCES.text(effect.get('move_type'),'food resistance type')
  if type(effect.get('requires_super_effective')) is not bool:raise ValueError('food resistance trigger must be explicit')
 elif kind=='chef_snack':
  if effect!=chef_effect(actor.r,uid):raise ValueError('Chef Digestion Buff differs from its exact recipe policy')
 elif kind=='chef_composite':
  import chef_cooking as CHEF
  CHEF.validate_composite(actor.r,buff)
  if _has_suppression(buff) and actor.kind!='pokemon':raise ValueError('Suppressant Berries require a Pokemon recipient')
 elif kind=='csv_food':
  if csv_choice is None:raise ValueError('exact CSV food source required')
 elif kind in ('herb_cure_volatile','herb_reset_lowered','herb_skip_setup'):
  if effect!=snack_effect(actor.r,uid):raise ValueError('Herb Digestion Buff differs from its exact selected source')
 else:raise ValueError('Digestion Buff payload needs its source-specific adapter')
 if 'berry' in effect and type(effect['berry']) is not bool:raise ValueError('food Berry classification must be boolean')
 import chef_cooking as CHEF
 CHEF.validate_buff_provenance(actor,buff)
 return True


def _ongoing_parent_matches(parent,buff,uid,effect_source):
 """An ongoing healing record descends from its own consumed receipt or from one Dumplings component."""
 parent_effect=parent.get('effect');benefit=parent.get('benefit')
 if parent.get('source')!=buff['source'] or not isinstance(benefit,dict):return False
 ids=[benefit.get('effect_id'),*[row.get('effect_id') for key in ('components','composite') for row in benefit.get(key,[]) if isinstance(row,dict)]]
 if buff['id'] not in ids:return False
 if parent_effect==buff['effect'] and parent.get('item')==uid and parent.get('effect_source')==effect_source:return True
 if not isinstance(parent_effect,dict) or parent_effect.get('kind')!='chef_composite' or parent.get('effect_source')!='feat/경단':return False
 return any(isinstance(part,dict) and part.get('item')==uid and part.get('effect')==buff['effect'] for part in parent_effect.get('components',[]))


def slots(actor):
 if not isinstance(actor.buffs,list):raise ValueError('legacy opaque buffs need an actual food-state observation')
 total=0
 for buff in actor.buffs:
  if isinstance(buff,dict) and INSTANCES.KEY in buff:
   validate_native(actor,buff)
   if buff[INSTANCES.KEY]['kind']!='digestion':raise ValueError('only stored Digestion Buffs occupy food slots')
   total+=buff[INSTANCES.KEY]['capacity']['bucket']=='ordinary'
  else:total+=1 # unknown legacy occupancy never silently becomes a free slot
 import csv_item_food_contracts as CSV
 return total+CSV.legacy_occupancy(actor)


def buff_capacity(e,actor):
 row=food_limits(e,actor)
 return row['stored'] if row else buff_policy(e.r)['ordinary_slot_limit']


def can_gain_buff(e,actor,*,capacity=None):
 INSTANCES.validate_actor(actor)
 occupied=slots(actor);capacity=capacity or ordinary_capacity()
 if not herbal_gains_allowed(actor):return False
 if capacity['bucket']=='source_exempt':return True
 limit=buff_capacity(e,actor)
 return limit is None or occupied<limit


def honey_source(e,actor,uid):
 if uid!='item/꿀' or actor.abilities_suppressed:return None
 import capacity_abilities as CAPACITY_ABILITIES
 for name in actor.abilities:
  if '꿀파기' not in name and name!='Honey Paws':continue
  registered=CAPACITY_ABILITIES.registration(e.r,name)
  source=registered['source_id'] if registered else e.r.selection.resolve_name(name,('ability/',))
  if source not in buff_policy(e.r)['capacity_exceptions'] or 'item' not in buff_policy(e.r)['capacity_exceptions'][source]:raise ValueError('selected Honey Paws needs its source policy')
  selected(e,source);return source
 return None

def _inventory(e,user,uid,held_selection=None):
 import item_stock as STOCK
 return STOCK.prepare(e,user,uid,held_selection=held_selection)


def _debit(e,user,stock):
 import item_stock as STOCK
 return STOCK.debit(e,user,stock)


def handles(uid):
 import csv_item_food_contracts as CSV
 return uid in CSV.ITEM_KINDS or uid in DRINKS or uid in SNACK_ITEMS or uid=='item/이유식' or (isinstance(uid,str) and uid.startswith('item/') and '열매' in uid)

def consume(e,user,target,uid,*,minutes=None,reason=None,count=1,accepted=True,policy=None,held_selection=None,container_selection=None,shell_batch_id=None,resumable=False,request_id=None,chef_batch_id=None):
 import pokemon_activities as P
 import movement_actions as MOVEMENT
 import clock_invocations as CLOCK
 import csv_item_food_contracts as CSV
 MOVEMENT.boundary(e,'consume_food')
 csv_choice=CSV.intake_choice(e.r,uid,None if uid in DRINKS else policy)
 if csv_choice is None:selected(e,uid)
 import chef_cooking as CHEF
 chef_batch=CHEF.batch_for_intake(e,user,uid,chef_batch_id) if chef_batch_id is not None else None
 if chef_batch is not None and (held_selection is not None or container_selection is not None or shell_batch_id is not None or csv_choice is not None):raise ValueError('a Chef batch unit is its own actual stock')
 contract=EQUIPMENT.food_intake(e.r,uid,snack_items=SNACK_ITEMS|frozenset(CSV.ITEM_KINDS),drink_items=DRINKS,
                                other_food_items={'item/이유식',CHEF.HEARTY_ITEM},forced_snack=shell_batch_id is not None or chef_batch is not None and chef_batch['kind']=='dumplings',source_selection=csv_choice)
 if type(resumable) is not bool:raise ValueError('explicit intake clock mode required')
 if request_id is not None and not resumable:raise ValueError('intake request identity requires resumable time')
 request=dict(target_id=target.entity_id,item=uid,minutes=minutes,reason=reason,count=count,accepted=accepted,
              policy=policy,held_selection=held_selection,container_selection=container_selection,shell_batch_id=shell_batch_id,chef_batch_id=chef_batch_id)
 def finish(e,a,*others,plan,payment,clock):
  import world_entities as W
  recipient=W.actor_index(e)[plan['target_id']]
  return _finish_intake(e,a,recipient,plan,payment)
 if resumable:
  C.integer(minutes,'Extended intake minutes',1)
  if CLOCK.activity_request(e,request_id,'food_intake',user,[user,target],minutes*60,uid,request) is not None:
   return CLOCK.run_activity(e,user,[user,target],request_id=request_id,kind='food_intake',seconds=minutes*60,
                            source=uid,request=request,prepare=None,finish=finish)
 shell_snack=shell_batch_id is not None
 if shell_snack and user is not target:raise ValueError('shell Snack belongs to its actual containing Shuckle')
 # ch07:61 forbids Extended Actions during combat. ch09:202/234
 # require Extended intake; holding the food does not change that cost.
 # Completed requests above remain historical queries, not new intake.
 selected(e,'combat/action-economy')
 P._outside(e)
 if policy is not None and uid!='item/이유식' and contract['kind']!='drink' and csv_choice is None:raise ValueError('exact food source policy required')
 if type(accepted) is not bool:raise ValueError('food acceptance must be boolean')
 if not accepted:return {'status':'refused'}
 C.integer(count,'food servings',1,1)
 if target.kind not in ('pokemon','trainer') or target.dead or target.fainted:raise ValueError('conscious food consumer required')
 if not TURN.can_act(e,user) or not ACTION.status_permission(e,user,'extended') or not ACTION.status_permission(e,target,'extended'):return False
 if minutes is None or reason is None:return C.PendingDecision('GM Extended food intake duration')
 C.integer(minutes,'Extended intake minutes',1);P._text(reason,'GM intake duration reason')
 import item_stock as STOCK
 key=STOCK.prepare(e,user,uid,held_selection=held_selection,container_selection=container_selection,shell_batch_id=shell_batch_id,source_selection=csv_choice,chef_batch_id=chef_batch_id)
 if contract['kind']=='drink':
  selected(e,DRINK_SOURCE);limits=food_limits(e,target)
  decision=_refreshment_decision(e,user,target,uid,policy)
  definition=decision['definition']
  window,limit=(limits['drink_seconds'],limits['drinks']) if limits else (definition['seconds'],definition['limit'])
  effective={'seconds':window,'limit':limit,'source':DRINK_SOURCE}
  if limits:
   import capacity_abilities as CAPACITY_ABILITIES
   effective['source']=CAPACITY_ABILITIES.registration(e.r,limits['name'])['source_id']
  when=e.elapsed_seconds+minutes*60;gap=len(e.unresolved_time_intervals)
  history=target.spec.get('drink_history',[])
  if not isinstance(history,list):raise ValueError('actual drink intake history required')
  import consumption_history as HISTORY
  recent=HISTORY.select(history,source=DRINK_SOURCE,when=when,seconds=window,gap_count=gap)
  if recent['uncertain']:return C.PendingDecision('unknown elapsed time prevents exact drink-limit decision')
  if recent['count']>=limit:raise ValueError('drink intake limit has not reset')
  plan=dict(kind='drink',gap_count=gap,refreshment_policy={'ordinary':decision,'effective':effective})
 elif contract['kind']=='snack':
  selected(e,FOOD)
  effect=deepcopy(chef_batch['payload']) if chef_batch is not None else CSV.effect(csv_choice) if csv_choice is not None else {'kind':'heal','amount':DRINKS[uid]} if shell_snack else snack_effect(e.r,uid)
  if effect is None:return C.PendingDecision('Snack effect needs its source-specific consumer before intake')
  if uid=='item/검은오물' and (target.kind!='pokemon' or '독' not in target.types):raise ValueError('Black Sludge snack requires actual Poison-type Pokemon')
  honey=honey_source(e,target,uid);capacity=capacity_from_source(e.r,honey) if honey else ordinary_capacity()
  if honey:effect=deepcopy(buff_policy(e.r)['capacity_exceptions'][honey]['effect'])
  if not can_gain_buff(e,target,capacity=capacity):raise ValueError('recipient cannot gain another Digestion Buff')
  plan=dict(kind='snack',effect=effect,capacity=capacity,shell_snack=shell_snack,csv_food_source=csv_choice,chef_batch=CHEF.intake_provenance(chef_batch,user) if chef_batch is not None else None)
 elif chef_batch is not None and chef_batch['kind']=='hearty_meal':
  if contract['limit_bucket']!='independent':raise ValueError('Hearty Meal must remain outside snack and drink limits')
  if target.kind!='trainer':raise ValueError('Hearty Meals are consumed by Trainers')
  if target.spec.get(CHEF.MEAL) is not None:raise ValueError('a Trainer may only be under the effect of one Hearty Meal at a time')
  pending=CHEF.hearty_freshness(e,chef_batch,when=e.elapsed_seconds+minutes*60)
  if pending is not None:return pending
  plan=dict(kind='hearty_meal',chef_batch={'batch_id':chef_batch['id'],'cook_id':chef_batch['created_by'],'created_at':chef_batch['created_at'],'gap_count':chef_batch['gap_count'],'taste':deepcopy(chef_batch['taste'])},intake_contract=contract)
 else:
  pending=_prepare_baby(target,policy)
  if pending is not None:return pending
  if contract['limit_bucket']!='independent':raise ValueError('other food must remain outside snack and drink limits')
  plan=dict(kind='baby',policy=policy,intake_contract=contract)
 plan.update(target_id=target.entity_id,item=uid,stock=key,reason=reason)
 def prepare(e,a,*others):return deepcopy(plan),_start_intake(e,a,plan)
 if resumable:
  return CLOCK.run_activity(e,user,[user,target],request_id=request_id,kind='food_intake',seconds=minutes*60,
                           source=uid,request=request,prepare=prepare,finish=finish)
 payment=_start_intake(e,user,plan)
 e.advance_time(minutes*60,[user,target])
 return _finish_intake(e,user,target,plan,payment)[0]


def _start_intake(e,user,plan):
 if plan['kind']!='snack':return None
 # Shell removal is paid at intake start; other stock is paid at completion.
 if plan['shell_snack']:return _debit(e,user,plan['stock'])
 import item_maturation as MATURATION
 MATURATION.intake_started(e,user,plan['stock'])
 return None


def _finish_intake(e,user,target,plan,payment):
 import consumption_execution as EXECUTION
 if target.dead or target.fainted:raise ValueError('conscious food consumer required at completion')
 uid=plan['item'];kind=plan['kind']
 if kind in ('drink','snack'):selected(e,DRINK_SOURCE if kind=='drink' else FOOD)
 if kind=='snack' and not can_gain_buff(e,target,capacity=plan['capacity']):
  raise ValueError('recipient cannot gain another Digestion Buff')
 stock_receipt=payment if payment is not None else _debit(e,user,plan['stock'])
 ACTION.record_action(e,target,'extended')
 if kind=='drink':
  record={'item_stock':stock_receipt,'source':DRINK_SOURCE,'item':uid,'at':e.elapsed_seconds,
          'gap_count':plan['gap_count'],'given_by':user.spec.get('id'),'duration_reason':plan['reason']}
  # The authenticated native plan pins the producing choice.  Do not resolve
  # against a later profile, or fabricate a choice for an older pending plan.
  if 'refreshment_policy' in plan:record['refreshment_policy']=deepcopy(plan['refreshment_policy'])
  target.spec.setdefault('drink_history',[]).append(record)
  healed=e.heal(target,DRINKS[uid],source_kind='ordinary_item')
  EXECUTION.finish(user,stock_receipt,target_id=target.entity_id,outcome='applied',
                   results=[{'kind':'drink_intake','id':target.entity_id+':drink:'+str(len(target.spec['drink_history']))}])
  result={'status':'consumed','item':uid,'healed':healed,'at':e.elapsed_seconds}
 elif kind=='snack':
  record=grant_buff(e,target,uid,plan['effect'],source=FOOD,capacity=plan['capacity'],source_selection=plan.get('csv_food_source'),provenance=plan.get('chef_batch'))
  record['item_stock']=stock_receipt
  EXECUTION.finish(user,stock_receipt,target_id=target.entity_id,outcome='applied',results=[{'kind':'digestion_buff','id':record['id']}])
  result={'status':'digestion_buff_gained','item':uid,'buff_id':record['id'],'at':e.elapsed_seconds,'item_stock':stock_receipt}
 elif kind=='hearty_meal':
  import chef_cooking as CHEF
  result=CHEF.eat_hearty_meal(e,user,target,plan,stock_receipt)
  EXECUTION.finish(user,stock_receipt,target_id=target.entity_id,outcome='applied',results=[{'kind':'hearty_meal','id':target.entity_id+':hearty-meal:'+str(result['at'])}])
  record=target.spec[CHEF.MEAL]
 else:
  policy=plan['policy']
  eligibility=_baby_eligibility(target,policy)
  record={'item_stock':stock_receipt,'source':uid,'policy':policy,'day':target.spec.get('frequency_state',{}).get('day',0),
          'level_when_fed':target.level,'eligibility':eligibility,
          'eligible_when_fed':target.level<=eligibility['maximum_level'],
          'at':e.elapsed_seconds,'consumed':False,'intake_contract':deepcopy(plan['intake_contract'])}
  target.spec['baby_food']=record
  result={'status':'consumed','item':uid,'policy':policy,'eligible':record['eligible_when_fed']}
 joy=__import__('study_books').joy_consumed(e,user,target,plan)
 if joy:result['joy_of_cooking_healed']=joy
 return result,stock_receipt,record


def grant_buff(e,actor,uid,effect,*,source,capacity=None,source_selection=None,provenance=None):
 capacity=capacity or ordinary_capacity()
 prepared=__import__('study_books').herbal_provider(e,actor) if source==MEDICINE and uid in HERBS else None
 if prepared is not None and prepared['repeat_food_buff']:
  if capacity['bucket']!='source_exempt' and slots(actor)>=buff_capacity(e,actor):return None
 elif not can_gain_buff(e,actor,capacity=capacity):return None
 buff=INSTANCES.create(e,actor,kind='digestion',source=source,payload=effect,capacity=capacity,lifetime=buff_policy(e.r)['lifetime'])
 buff['item']=uid
 buff['effect_source']=capacity['source'] if 'item' in buff_policy(e.r)['capacity_exceptions'].get(capacity['source'],{}) else MEDICINE if source==MEDICINE else uid
 if provenance is not None:
  if not isinstance(provenance,dict):raise ValueError('typed chef provenance required')
  for key,value in provenance.items():buff[key]=deepcopy(value)
 if source_selection is not None:
  import csv_item_food_contracts as CSV
  buff[CSV.SELECTION]=CSV.validate_choice(e.r,source_selection,uid)
 validate_native(actor,buff)
 actor.buffs.append(buff);return buff

def get_buff(actor,buff_id):
 candidates=[b for b in actor.buffs if isinstance(b,dict) and b.get('id')==buff_id]
 if len(candidates)!=1:raise ValueError('one actual acquired Digestion Buff required')
 buff=candidates[0]
 validate_native(actor,buff)
 if buff.get('source') not in (FOOD,MEDICINE):raise ValueError('buff producer needs source-specific consumer')
 return buff

def consumption_allowed(e,actor,buff):
 selected(e,buff['source'])
 if e.encounter_active:C.integer(getattr(e,'_party_encounter_epoch',0),'actual food encounter epoch',1)
 import csv_item_food_contracts as CSV
 csv_choice=CSV.validate_native(actor,buff) if CSV.SELECTION in buff else None
 if csv_choice is None:selected(e,buff['item'])
 protected=csv_choice is not None and csv_choice['kind']=='dynamax_mushroom'
 if protected and not CSV.designated_form_authorized(e,actor,buff):raise ValueError('Dynamax Mushroom requires its actual designated native form entry')
 import ability_target_limits as TARGET_LIMITS
 if not protected and TARGET_LIMITS.blocked(e,actor,'food_buff'):raise ValueError('Unnerve forbids Digestion Buff consumption')
 for key in ('food_buff_consumed','lim:food_buff_consumed'):C.integer(actor.counters.get(key,0),'actual food consumption counter',0)
 receipts=actor.spec.get('food_consumption_receipts',[])
 if not isinstance(receipts,list) or any(not isinstance(x,dict) for x in receipts):raise ValueError('actual food consumption receipts required')
 if any(x.get('buff_id')==buff['id'] for x in receipts):raise ValueError('Digestion Buff already consumed')
 exempt=buff.get(INSTANCES.KEY,{}).get('capacity',ordinary_capacity()).get('scene_usage_exempt',False)
 limits=food_limits(e,actor)
 if not protected and not exempt and limits:
  if 'per_encounter' in limits and e.encounter_active:
   used,uncertain=_core_usage(e,actor)
   if used>=limits['per_encounter']:raise ValueError('core Gluttony encounter Digestion Buff quota reached')
   if uncertain:raise ValueError('actual current core Gluttony quota observation required for legacy food receipts')
  elif 'per_scene' in limits and actor.counters.get('lim:food_buff_consumed',0)>=limits['per_scene']:
   raise ValueError('Gluttony scene Digestion Buff quota reached')

def consumed_this_scene(e,actor):
 """Read actual exchanges in the existing frequency scene, never a lifetime flag."""
 import frequency as FREQ
 FREQ.validate(actor)
 scene=actor.spec.get('frequency_state',{}).get('scene',0)
 receipts=actor.spec.get('food_consumption_receipts',[])
 if not isinstance(receipts,list) or any(not isinstance(x,dict) for x in receipts):raise ValueError('actual food consumption receipts required')
 found=False
 for receipt in receipts:
  # Old saves without a scene cannot prove which narrative scene consumed it.
  if 'scene' not in receipt:continue
  consumed_scene=C.integer(receipt['scene'],'food consumption scene',0,scene)
  C.integer(receipt.get('sequence'),'food consumption sequence',1)
  if any(not isinstance(receipt.get(k),str) or not receipt[k] for k in ('buff_id','source','item','producer')):raise ValueError('actual sourced food consumption receipt required')
  if consumed_scene==scene:found=True
 return found


def move_allowed(e,actor,move,mm):
 # Custap authorizes the native loan without spending food in _prepare.
 # Exchange only inside its actual Move, after native action entry has checked
 # prior choices; new Chef trigger offers remain for the real caller.
 priority_berry(e,actor,move['id'],commit=True)
 restrictions=mm.get('effects_exec',[])+[x for x in actor.registry if x.get('type')=='usage_restriction']
 if not any(x.get('type')=='usage_restriction' and 'food buff' in str(x.get('only_if','')) for x in restrictions):return True
 selected(e,move['id'])
 if consumed_this_scene(e,actor):return True
 e.log(f"  {actor.name} {move['name']}: 이번 장면에 음식 버프를 소비하지 않음 → 사용 불가",'effect/usage_restriction')
 return False


def remove_buff(e,actor,buff,*,producer='food_action'):
 # One actual resource exchange receipt feeds every consumer. It is not a
 # generic rollback snapshot: the exchange and its later benefit are distinct.
 if get_buff(actor,buff['id']) is not buff:raise ValueError('actual acquired buff identity changed before consumption')
 consumption_allowed(e,actor,buff)
 receipts=actor.spec.get('food_consumption_receipts',[])
 if not isinstance(receipts,list):raise ValueError('actual food consumption receipts required')
 if any(x.get('buff_id')==buff['id'] for x in receipts):raise ValueError('Digestion Buff already consumed')
 import frequency as FREQ
 receipt={'sequence':len(receipts)+1,'buff_id':buff['id'],'source':buff['source'],'item':buff['item'],'effect':deepcopy(buff['effect']),'producer':producer,'at':e.elapsed_seconds,'round':e.round_no,'scene':FREQ.state(actor)['scene'],'benefit':None}
 if 'item_stock' in buff:receipt['item_stock']=deepcopy(buff['item_stock'])
 if 'food_transfer_origin' in buff:receipt['food_transfer_origin']=deepcopy(buff['food_transfer_origin'])
 if 'csv_food_source' in buff:receipt['csv_food_source']=deepcopy(buff['csv_food_source'])
 if 'csv_legacy_origin' in buff:receipt['csv_legacy_origin']=deepcopy(buff['csv_legacy_origin'])
 if actor.spec.get(BERRY_CHOICE,{}).get('buff_id')==buff['id']:receipt['berry_choices']=deepcopy(actor.spec[BERRY_CHOICE]['choices'])
 for key in ('taste_assignment','chef_batch','chef_provenance'):
  if key in buff:receipt[key]=deepcopy(buff[key])
 metadata=INSTANCES.consumed(buff,actor,e.elapsed_seconds)
 if metadata is not None:
  receipt[INSTANCES.KEY]=metadata;receipt['effect_source']=buff['effect_source']
 receipt[ENCOUNTER_RECEIPT]={'actor_id':actor.entity_id,
  'encounter_epoch':C.integer(getattr(e,'_party_encounter_epoch',0),'actual food encounter epoch',1) if e.encounter_active else None,
  'eligible':_quota_eligible(receipt)}
 actor.buffs.remove(buff)
 actor.counters['food_buff_consumed']=actor.counters.get('food_buff_consumed',0)+1
 if not buff.get(INSTANCES.KEY,{}).get('capacity',ordinary_capacity()).get('scene_usage_exempt',False):actor.counters['lim:food_buff_consumed']=actor.counters.get('lim:food_buff_consumed',0)+1
 actor.spec.setdefault('food_consumption_receipts',[]).append(receipt)
 for key in ('food_save_choice','food_hit_choice','food_move_choice',BERRY_CHOICE,BERRY_HIT_CHOICE,BERRY_PRIORITY_CHOICE,*CHEF_CHOICE_KEYS):
  if actor.spec.get(key,{}).get('buff_id')==buff['id']:actor.spec.pop(key)
 import class_actor_state_actions as CLASS_STATE_ACTIONS
 CLASS_STATE_ACTIONS.observe_food_buff_consumed(e,actor,receipt)
 if producer!='actual_attack':
  import chef_cooking as CHEF
  CHEF.apply_taste_bonus(e,actor,buff,receipt)
 return receipt


def _consumer_effect(buff):
 """The payload that decides a trade-in path: one trigger-bound Dumplings component or the buff itself."""
 effect=buff['effect']
 if effect.get('kind')!='chef_composite':return effect
 import chef_cooking as CHEF
 trigger=CHEF.trigger_component(buff)
 return trigger if trigger is not None else effect


def _immediate_parts(buff):
 """Immediate payloads as (item,effect) pairs; a trigger-bound composite is not traded in here."""
 effect=buff['effect']
 if effect.get('kind')!='chef_composite':return [(buff['item'],effect)]
 import chef_cooking as CHEF
 if CHEF.trigger_component(buff) is not None:raise ValueError('this composite Digestion Buff is traded in through its trigger-bound ingredient')
 return [(part['item'],part['effect']) for part in CHEF.immediate_components(buff)]


def _immediate_part_preflight(e,actor,buff,effect,*,item=None,ignore_conditions=False,owner_consent_by=None):
 if effect.get('kind') not in ('heal','turn_heal','cure','stage_change','stat_suppression','herb_cure_volatile','herb_reset_lowered','native_consumable',*BERRY_IMMEDIATE):raise ValueError('this Digestion Buff needs its own actual save/hit benefit event')
 if effect['kind']=='stage_change' and effect!=snack_effect(e.r,item or buff['item']):raise ValueError('exact stage Berry source required')
 choice=actor.spec.get(BERRY_CHOICE,{})
 choices=choice.get('choices',{}) if choice.get('buff_id')==buff['id'] else {}
 if effect['kind']=='berry_cure_any':
  import boss_transitions as BOSS
  condition=choices.get('condition')
  if condition is None:return C.PendingDecision('Lum Berry needs the one actual status to cure')
  if BOSS.condition_variant(actor,condition) not in actor.conditions:raise ValueError('Lum Berry needs the selected actual status')
 elif effect['kind']=='berry_scene_move':
  import frequency as FREQ
  mid=choices.get('move_id')
  if mid is None:return C.PendingDecision('Leppa Berry needs the one actual spent Scene Move to restore')
  if FREQ.preflight_restore_move_use(e,actor,mid)[1]!='scene':raise ValueError('Leppa Berry restores only a Scene Move')
 elif effect['kind']=='berry_critical' and not e.encounter_active:return C.PendingDecision('Lansat Berry requires its actual encounter lifetime')
 elif effect['kind']=='berry_flavor':
  if _flavor_disposition(actor,effect['flavor'])=='disliked' and 'flavor_edition' not in choices:return C.PendingDecision('Disliked Treat Berry needs explicit kr_book instead-Confusion or core_en_1_05 healing-plus-Confusion source selection')
  if choices.get('flavor_edition')=='core_en_1_05':_berry_en_source(e.r)
 if effect['kind']=='berry_random_stage' and not ignore_conditions and actor.hp*4>actor.base_max_hp:raise ValueError('Starf Berry requires HP at most one quarter true maximum')
 if effect['kind']=='native_consumable':
  import chef_cooking as CHEF,herb_mushroom_rules as HERB
  uid=item or buff['item']
  if effect!=CHEF.preserves_effect(e.r,uid,effect.get('origin_body')):raise ValueError('exact preserved native effect required')
  if uid in HERB.MUSHROOMS:CHEF._validate_origin_body(e,uid,effect['origin_body'])
  else:
   herbal_preflight(e,actor,uid)
   effs,_=e.r.item_effects(uid)
   __import__('effects').preflight_effects(e,actor,actor,effs,uid,consumer='items.use_item')
 if effect['kind'] in ('herb_cure_volatile','herb_reset_lowered'):
  import herb_mushroom_rules as HERB
  HERB.immediate_preflight(e,actor,dict(buff,item=item or buff['item'],effect=effect))
 if effect['kind']=='stat_suppression':
  import vitamin_moves as V
  if V.owner_consent(e,actor,owner_consent_by) is None:return C.PendingDecision('Suppressant Berry needs the actual current owner choice before its effect')
 if effect.get('berry') and effect['kind']!='stat_suppression' and not ignore_conditions:
  import boss_transitions as BOSS
  condition_ok=(effect['kind']=='cure' and BOSS.condition_variant(actor,effect['status']) in actor.conditions) or effect['kind']=='berry_cure_any' and BOSS.condition_variant(actor,choices.get('condition')) in actor.conditions
  if actor.hp*2>actor.base_max_hp and not condition_ok:raise ValueError('Berry requires HP at most half true maximum or its curable status')
 if effect['kind']=='turn_heal' and not e.encounter_active:return C.PendingDecision('turn healing needs actual encounter timing')
 return None


def immediate_preflight(e,actor,buff,*,ignore_conditions=False,owner_consent_by=None):
 consumption_allowed(e,actor,buff)
 if owner_consent_by is not None and not _has_suppression(buff):raise ValueError('owner suppression choice requires a Suppressant Berry')
 for item,effect in _immediate_parts(buff):
  pending=_immediate_part_preflight(e,actor,buff,effect,item=item,ignore_conditions=ignore_conditions,owner_consent_by=owner_consent_by)
  if pending is not None:return pending
 import combat_stage_sources as STAGES
 STAGES.validate(actor)
 if not isinstance(actor.spec.get('food_consumption_receipts',[]),list):raise ValueError('actual food consumption receipts required')
 return buff


def _apply_immediate(e,actor,buff,effect,reason,receipt,result,owner_consent_by,*,item=None,effect_source=None):
 item=buff['item'] if item is None else item
 effect_source=buff['effect_source'] if effect_source is None else effect_source
 if effect['kind']=='heal':result['healed']=e.heal(actor,effect['amount'],source_kind='ordinary_item')
 elif effect['kind']=='stage_change':
  before=actor.stages[effect['stat']]
  e.change_stage(actor,effect['stat'],effect['delta'])
  result.update(stat=effect['stat'],requested_delta=effect['delta'],actual_delta=actor.stages[effect['stat']]-before)
 elif effect['kind']=='berry_random_stage':
  import combat_stage_sources as STAGES
  stat=e.rng.choice(STAGES.STATS)
  before=actor.stages[stat];e.change_stage(actor,stat,effect['delta'])
  result.update(stat=stat,requested_delta=effect['delta'],actual_delta=actor.stages[stat]-before)
 elif effect['kind']=='berry_cure_any':
  condition=receipt['berry_choices']['condition']
  import boss_transitions as BOSS
  stored=BOSS.condition_variant(actor,condition);before=stored in actor.conditions
  e.cure_status(actor,condition);result.update(condition=condition,cured=before and stored not in actor.conditions)
 elif effect['kind']=='berry_scene_move':
  import frequency as FREQ
  mid=receipt['berry_choices']['move_id'];owner,kind=FREQ.preflight_restore_move_use(e,actor,mid)
  before=owner.move_uses[mid];FREQ.restore_scene_use(e,actor,mid)
  result.update(move_id=mid,restored=before-owner.move_uses[mid],frequency_owner_id=owner.entity_id)
 elif effect['kind']=='berry_accuracy':
  import effects as FX
  before=actor.accuracy_stage
  FX.h_accuracy_mod(e,actor,actor,{'type':'accuracy_mod','value':effect['delta']},{'source_id':item})
  result.update(requested_delta=effect['delta'],actual_delta=actor.accuracy_stage-before)
 elif effect['kind']=='berry_flavor':
  disposition=_flavor_disposition(actor,effect['flavor']);edition=receipt.get('berry_choices',{}).get('flavor_edition')
  heal=disposition!='disliked' or edition=='core_en_1_05'
  result.update(disposition=disposition,flavor=effect['flavor'],edition=edition or 'agreeing_printed_effect')
  result['healed']=e.heal(actor,M.ratio(actor.base_max_hp,6 if disposition=='liked' else 8),source_kind='ordinary_item') if heal else 0
  result['confusion_applied']=bool(e.apply_status(actor,'혼란',source=item,applied_by=actor)) if disposition=='disliked' else False
 elif effect['kind']=='berry_critical':
  import state_grants as G,combat_timing as TIMING
  source=G.effect_source(actor,{'source_id':item,'effect_occurrence':buff['id']},'critical')
  G._source(actor,source,'effect',owner_id=actor.entity_id,rule_id=item,lifetime='encounter_end')
  modifier={'type':'crit_range','delta':effect['delta']}
  G.apply_owned(e,actor,source,lambda:actor.modifiers.append(modifier))
  TIMING.install(e,actor,{'source':item,'effect_contract':True,'berry_critical':True,'buff_id':buff['id'],'receipt_sequence':receipt['sequence'],'grant_source':source,'encounter_end':True})
  result.update(delta=effect['delta'],grant_source=source,until='encounter_end')
 elif effect['kind']=='cure':
  import boss_transitions as BOSS
  stored=BOSS.condition_variant(actor,effect['status'])
  before=stored in actor.conditions;e.cure_status(actor,effect['status']);result['cured']=before and stored not in actor.conditions
 elif effect['kind'] in ('herb_cure_volatile','herb_reset_lowered'):
  import herb_mushroom_rules as HERB
  result.update(HERB.immediate_commit(e,actor,dict(buff,item=item,effect=effect)))
 elif effect['kind']=='native_consumable':
  import herb_mushroom_rules as HERB
  if item in HERB.MUSHROOMS:result.update(HERB.apply_mushroom(e,actor,item,effect['origin_body']['plan']))
  else:
   import items as ITEMS
   effs,header=e.r.item_effects(item)
   result['native_result']=ITEMS.apply_immediate_effects(e,actor,actor,item,effs,header)
 elif effect['kind']=='stat_suppression':
  import growth_stats as GROWTH,vitamin_moves as V
  owner_id=V.owner_consent(e,actor,owner_consent_by)
  GROWTH.apply_vitamin(actor,effect['stat'],source=item,delta=-1)
  if actor.spec.get('species'):
   from builder import record_allocation
   record_allocation(e.r,actor.spec,'stat_suppression',source=item,item=item,
                     actor_id=actor.entity_id,owner_id=owner_id,stat=effect['stat'],delta=-1,
                     applied_at=e.elapsed_seconds,buff_id=buff['id'],item_stock=receipt.get('item_stock'))
  result.update(stat=effect['stat'],delta=-1,owner_id=owner_id)
 else:
  if INSTANCES.KEY in buff:
   ongoing=INSTANCES.create(e,actor,kind='food_turn_healing',source=buff['source'],payload=effect,capacity={'bucket':'none','source':buff['source']},lifetime={'boundary':'encounter_end'})
   ongoing.update(item=item,effect_source=effect_source,buff_id=buff['id'],action_reason=reason)
   result['effect_id']=ongoing['id']
  else:
   # Preserve imported legacy state without inventing its past origin/policy.
   ongoing={'source':buff['source'],'item':buff['item'],'buff_id':buff['id'],'denominator':effect['denominator'],'action_reason':reason}
  actor.spec.setdefault('food_turn_healing',[]).append(ongoing)
  result['until']='encounter_end'
 return result


def _apply_composite_rest(e,actor,buff,receipt,reason,owner_consent_by=None):
 """After a trigger-bound trade-in, the other Dumplings ingredient effects apply at once."""
 import chef_cooking as CHEF
 rows=[]
 for part in CHEF.immediate_components(buff):
  row={'item':part['item'],'kind':part['effect']['kind']}
  _apply_immediate(e,actor,buff,part['effect'],reason,receipt,row,owner_consent_by,item=part['item'],effect_source=part['item'])
  rows.append(row)
 return rows


def _berry_composite_preflight(e,actor,buff,owner_consent_by=None):
 if buff['effect'].get('kind')!='chef_composite':return None
 import chef_cooking as CHEF
 for part in CHEF.immediate_components(buff):
  if part['effect']['kind'] in BERRY_IMMEDIATE:
   pending=_immediate_part_preflight(e,actor,buff,part['effect'],item=part['item'],owner_consent_by=owner_consent_by)
   if pending is not None:return pending
 return None


def immediate_commit(e,actor,buff,*,producer,reason,ignore_conditions=False,owner_consent_by=None):
 checked=immediate_preflight(e,actor,buff,ignore_conditions=ignore_conditions,owner_consent_by=owner_consent_by)
 if isinstance(checked,C.PendingDecision):raise ValueError(str(checked))
 parts=_immediate_parts(buff);receipt=remove_buff(e,actor,buff,producer=producer)
 result={'status':'consumed','buff_id':buff['id'],'receipt':receipt['sequence']}
 if buff['effect'].get('kind')=='chef_composite':
  rows=[]
  for item,effect in parts:
   row={'item':item,'kind':effect['kind']}
   _apply_immediate(e,actor,buff,effect,reason,receipt,row,owner_consent_by,item=item,effect_source=item)
   rows.append(row)
  result['components']=rows
 else:_apply_immediate(e,actor,buff,parts[0][1],reason,receipt,result,owner_consent_by)
 receipt['benefit']=dict(result)
 return result


STUFF_CHEEKS='move/볼가득넣기'
CHEF_ATTACK_CHOICE='food_chef_attack_choice'
CHEF_RECEIVED_CHOICE='food_chef_received_attack_choice'
CHEF_CHOICE_KEYS=(CHEF_ATTACK_CHOICE,CHEF_RECEIVED_CHOICE)


def _chef_payload(buff):
 """The Chef Snack payload: the buff itself or the one Chef Snack ingredient of a Dumplings composite."""
 effect=buff['effect']
 if effect.get('kind')=='chef_snack':return effect
 if effect.get('kind')=='chef_composite':
  parts=[part['effect'] for part in effect['components'] if part['effect'].get('kind')=='chef_snack']
  if len(parts)==1:return parts[0]
 raise ValueError('Chef Digestion Buff payload required')


def _flavor_disposition(actor,flavor):
 if actor.kind!='pokemon':return 'neutral'
 import nature_state as NATURE
 nature=NATURE.describe(actor.r,actor.spec.get('nature'))
 if nature is None:return 'neutral'
 clean=lambda value:None if value is None else value.replace(' ','')
 flavor=clean(flavor)
 if clean(nature['likes'])==flavor:return 'liked'
 if clean(nature['dislikes'])==flavor:return 'disliked'
 return 'neutral'


def _chef_value(actor,effect):
 disposition=_flavor_disposition(actor,effect['flavor'])
 benefit=effect['benefit']
 return benefit.get('liked') if disposition=='liked' and 'liked' in benefit else benefit.get('base'),disposition


def _chef_apply_dislike(e,actor,buff,disposition):
 if disposition!='disliked':return False
 return bool(e.apply_status(actor,'난동',source=buff['item'],applied_by=actor))


def _chef_prepare(e,actor,buff,owner_consent_by=None):
 effect=_chef_payload(buff);trigger=effect['trigger']
 if trigger=='self_activation':return _chef_activate_sweet(e,actor,buff,owner_consent_by)
 key=CHEF_ATTACK_CHOICE if trigger=='attack' else CHEF_RECEIVED_CHOICE
 if key in actor.spec:raise ValueError('one optional Chef Digestion Buff choice per attack role required')
 actor.spec[key]={'buff_id':buff['id'],'item':buff['item'],'trigger':trigger}
 if _has_suppression(buff):actor.spec[key]['owner_id']=owner_consent_by.entity_id
 return {'status':'prepared_for_actual_'+trigger,'buff_id':buff['id'],'item':buff['item']}


def _chef_activate_sweet(e,actor,buff,owner_consent_by=None):
 if not e.encounter_active:return C.PendingDecision("Chef next-turn modifiers require an actual encounter turn boundary")
 effect=_chef_payload(buff);benefit=effect['benefit']
 if effect['trigger']!='self_activation' or benefit.get('type')!='timed_modifiers':raise ValueError('selected Chef buff is not self-activated')
 consumption_allowed(e,actor,buff)
 import combat_timing as TIMING
 serial=C.integer(actor.custom_conditions.get('combat_turn_serial',0),'actual owner turn serial',0)
 disposition=_flavor_disposition(actor,effect['flavor'])
 receipt=remove_buff(e,actor,buff,producer='chef_self_activation')
 effect_id='chef-snack:'+actor.entity_id+':'+str(receipt['sequence'])
 record={'source':buff['item'],'effect_contract':True,'chef_snack':True,'effect_id':effect_id,
         'buff_id':buff['id'],'turn_owner':actor,'turn_deadline':serial+1,'encounter_end':True,
         'evasion_modifier':benefit['evasion']}
 if disposition=='liked':record['accuracy_modifier']=benefit['liked_accuracy']
 TIMING.install(e,actor,record)
 rampage=_chef_apply_dislike(e,actor,buff,disposition)
 receipt['benefit']={'kind':'timed_modifiers','effect_id':effect_id,'evasion':benefit['evasion'],
                     'accuracy':benefit['liked_accuracy'] if disposition=='liked' else 0,
                     'disposition':disposition,'rampage_applied':rampage,'until':benefit['lifetime']}
 receipt['benefit']['composite']=_apply_composite_rest(e,actor,buff,receipt,'Chef self-activation',owner_consent_by)
 return {'status':'consumed','buff_id':buff['id'],**receipt['benefit']}


def _chef_choice(actor,key,trigger,move):
 choice=actor.spec.get(key)
 if choice is None:return None
 if not isinstance(choice,dict) or set(choice) not in ({'buff_id','item','trigger'},{'buff_id','item','trigger','owner_id'}) or choice.get('trigger')!=trigger:raise ValueError('typed Chef attack choice required')
 buff=get_buff(actor,choice.get('buff_id'));payload=_chef_payload(buff)
 if choice['item']!=buff['item'] or payload.get('kind')!='chef_snack' or payload.get('trigger')!=trigger:raise ValueError('Chef attack choice changed before consumption')
 if ('owner_id' in choice)!=_has_suppression(buff):raise ValueError('Chef composite owner choice differs from its Suppressant Berry')
 attack_class=payload.get('attack_class')
 if attack_class is not None and move.get('class')!=attack_class:return None
 return {'buff_id':buff['id'],'item':buff['item'],'trigger':trigger,**({'owner_id':choice['owner_id']} if 'owner_id' in choice else {}),
         'benefit_type':payload['benefit']['type']}


def chef_attack_preflight(e,attacker,target,move,*,temporary_hp_plans=None):
 """Validate both optional selections before damage RNG; mismatched classes stay armed."""
 outgoing=_chef_choice(attacker,CHEF_ATTACK_CHOICE,'attack',move)
 incoming=_chef_choice(target,CHEF_RECEIVED_CHOICE,'received_attack',move)
 if temporary_hp_plans is None:temporary_hp_plans={}
 for actor,plan in ((attacker,outgoing),(target,incoming)):
  if plan is None:continue
  buff=get_buff(actor,plan['buff_id']);consumption_allowed(e,actor,buff)
  pending=_berry_composite_preflight(e,actor,buff,_suppression_choice_owner(e,actor,plan))
  if pending is not None:raise ValueError(str(pending))
  if _has_suppression(buff):
   import vitamin_moves as V
   if V.owner_consent(e,actor,_suppression_choice_owner(e,actor,plan)) is None:raise ValueError('Chef composite requires its actual current owner consent')
  value,disposition=_chef_value(actor,_chef_payload(buff))
  if plan['benefit_type']=='temporary_hp':
   import temporary_hp as TEMP_HP
   TEMP_HP.ensure_certain(e,actor)
   plan['blocked_reason']=TEMP_HP.blocked_reason(actor)
  plan.update(value=value,disposition=disposition)
  import chef_cooking as CHEF
  grants=[(value,'food')] if plan['benefit_type']=='temporary_hp' else []
  pending=CHEF.taste_bonus_preflight(e,actor,buff,temporary_hp_grants=grants,
   temporary_hp_plan=temporary_hp_plans.setdefault(id(actor),{}))
  if pending is not None:raise ValueError(str(pending))
 return {'outgoing':outgoing,'incoming':incoming}


def _chef_commit_one(e,actor,other,move,plan):
 buff=get_buff(actor,plan['buff_id']);effect=_chef_payload(buff);value,disposition=_chef_value(actor,effect)
 if value!=plan['value'] or disposition!=plan['disposition']:raise ValueError('Chef taste state changed during the attack')
 owner=_suppression_choice_owner(e,actor,plan)
 receipt=remove_buff(e,actor,buff,producer='actual_attack')
 benefit={'kind':plan['benefit_type'],'amount':value,'disposition':disposition,'move_id':move['id'],
          'move_class':move['class'],'other_actor_id':other.entity_id}
 if plan['benefit_type']=='temporary_hp':
  import temporary_hp as TEMP_HP
  receipt['benefit']=benefit
  benefit['blocked_reason']=TEMP_HP.blocked_reason(actor)
  benefit['gained']=TEMP_HP.grant(e,actor,value,
   contribution_source=TEMP_HP.food_source(actor,'food',receipt),
   provenance={'source':buff['item'],'receipt_sequence':receipt['sequence'],'buff_id':buff['id']})
 rampage=_chef_apply_dislike(e,actor,buff,disposition);benefit['rampage_applied']=rampage
 receipt['benefit']=benefit
 benefit['composite']=_apply_composite_rest(e,actor,buff,receipt,'Chef attack trade-in',owner)
 import chef_cooking as CHEF
 benefit['taste_bonus']=CHEF.apply_taste_bonus(e,actor,buff,receipt)
 return benefit


def chef_attack_commit(e,attacker,target,move,plan,*,damage_reduction_allowed):
 if type(damage_reduction_allowed) is not bool:raise ValueError('explicit attack damage-reduction availability required')
 outgoing=plan.get('outgoing');incoming=plan.get('incoming')
 if outgoing is None and incoming is None:return {'bonus_damage':0,'damage_reduction':0,'temporary_hp':0,'receipts':[]}
 import state_grants as GRANTS
 def apply(staged,a,*participants):
  t=a if target is attacker else participants[0]
  current=chef_attack_preflight(staged,a,t,move);rows=[];bonus=dr=temp=0
  if outgoing is not None:
   now=current['outgoing']
   if now is None or any(now[k]!=outgoing[k] for k in ('buff_id','item','trigger','benefit_type','value','disposition')):raise ValueError('Chef outgoing choice changed during the attack')
   row=_chef_commit_one(staged,a,t,move,now);rows.append(row);bonus=row['amount']
  if incoming is not None:
   now=current['incoming']
   if now is None or any(now[k]!=incoming[k] for k in ('buff_id','item','trigger','benefit_type','value','disposition')):raise ValueError('Chef incoming choice changed during the attack')
   if now['benefit_type']=='damage_reduction' and not damage_reduction_allowed:return {'bonus_damage':bonus,'damage_reduction':0,'temporary_hp':0,'receipts':rows}
   row=_chef_commit_one(staged,t,a,move,now);rows.append(row)
   if now['benefit_type']=='damage_reduction':dr=row['amount']
   elif now['benefit_type']=='temporary_hp':temp=row['gained']
  return {'bonus_damage':bonus,'damage_reduction':dr,'temporary_hp':temp,'receipts':rows}
 participants=() if target is attacker else (target,)
 return GRANTS.transition(e,attacker,apply,participants=participants)


def validate_actor_state(actor):
 import csv_item_food_contracts as CSV
 CSV.validate_actor(actor)
 import herb_mushroom_rules as HERB
 HERB.validate_power_herb_choice(actor)
 choice=actor.spec.get(BERRY_CHOICE)
 if choice is not None:
  if type(choice) is not dict or set(choice)!={'buff_id','choices'}:raise ValueError('typed actual Berry choices required')
  _berry_choices(get_buff(actor,choice['buff_id']),choice['choices'])
 for key,kind in ((BERRY_HIT_CHOICE,'berry_reactive'),(BERRY_PRIORITY_CHOICE,'berry_priority')):
  row=actor.spec.get(key)
  if row is None:continue
  allowed={'buff_id'} if key==BERRY_HIT_CHOICE else {'buff_id','move_id'}
  if type(row) is not dict or set(row) not in (allowed,allowed|{'owner_id'}):raise ValueError('typed actual Berry event selection required')
  buff=get_buff(actor,row['buff_id'])
  if _consumer_effect(buff)['kind']!=kind:raise ValueError('Berry event selection changed its native payload')
  if ('owner_id' in row)!=_has_suppression(buff):raise ValueError('Berry event owner selection differs from its actual Suppressant component')
  if key==BERRY_PRIORITY_CHOICE and row['move_id'] not in actor.moves:raise ValueError('Custap selection needs an actual owned Move')
 chosen=[]
 for key,trigger in ((CHEF_ATTACK_CHOICE,'attack'),(CHEF_RECEIVED_CHOICE,'received_attack')):
  choice=actor.spec.get(key)
  if choice is None:continue
  if not isinstance(choice,dict) or set(choice) not in ({'buff_id','item','trigger'},{'buff_id','item','trigger','owner_id'}) or choice.get('trigger')!=trigger:raise ValueError('typed Chef attack choice required')
  buff=get_buff(actor,choice.get('buff_id'));payload=_chef_payload(buff)
  if choice['item']!=buff['item'] or payload.get('kind')!='chef_snack' or payload.get('trigger')!=trigger:raise ValueError('Chef choice and actual Digestion Buff disagree')
  if ('owner_id' in choice)!=_has_suppression(buff):raise ValueError('Chef composite owner choice differs from its Suppressant Berry')
  if 'owner_id' in choice:INSTANCES.text(choice['owner_id'],'Chef composite owner identity')
  if buff['id'] in chosen:raise ValueError('one Chef Digestion Buff cannot fill two attack roles')
  chosen.append(buff['id'])
 import combat_timing as TIMING
 for record in TIMING.records(actor):
  if record.get('berry_critical'):
   _validate_critical_berry(actor,record)
   continue
  if record.get('csv_sweet'):
   _validate_csv_sweet(actor,record)
   continue
  if not record.get('chef_snack'):continue
  allowed={'source','effect_contract','chef_snack','effect_id','buff_id','turn_owner','turn_deadline','encounter_end','evasion_modifier','accuracy_modifier','owned_statuses','installing'}
  if set(record)-allowed or record.get('source')!='item/단맛-과자' or record.get('effect_contract') is not True or record.get('turn_owner') is not actor or record.get('encounter_end') is not True or record.get('evasion_modifier')!=4:raise ValueError('typed Chef Sweet Confection lifetime required')
  C.integer(record.get('turn_deadline'),'Chef Sweet Confection turn deadline',1)
  if record.get('accuracy_modifier',0) not in (0,4):raise ValueError('Chef Sweet Confection accuracy contribution changed')
  if not isinstance(record.get('effect_id'),str) or not record['effect_id'].startswith('chef-snack:'+actor.entity_id+':'):raise ValueError('Chef timed effect identity changed')
  receipts=[row for row in actor.spec.get('food_consumption_receipts',[]) if row.get('buff_id')==record.get('buff_id')]
  if len(receipts)!=1 or receipts[0].get('producer')!='chef_self_activation':raise ValueError('Chef timed effect lacks one self-activation receipt')
  benefit=receipts[0].get('benefit')
  if not isinstance(benefit,dict) or benefit.get('kind')!='timed_modifiers' or benefit.get('effect_id')!=record['effect_id'] or benefit.get('evasion')!=4 or benefit.get('accuracy')!=record.get('accuracy_modifier',0) or benefit.get('until')!="end of user's next turn":raise ValueError('Chef timed effect and receipt disagree')
 import chef_cooking as CHEF
 CHEF.validate_actor(actor)
 return True


def _berry_choices(buff,choices):
 if type(choices) is not dict:raise ValueError('explicit Berry choice mapping required')
 effect=buff['effect'];parts=[p['effect'] for p in effect['components']] if effect.get('kind')=='chef_composite' else [effect]
 allowed=set()
 if any(p['kind']=='berry_cure_any' for p in parts):allowed.add('condition')
 if any(p['kind']=='berry_scene_move' for p in parts):allowed.add('move_id')
 if any(p['kind']=='berry_flavor' for p in parts):allowed.add('flavor_edition')
 if set(choices)-allowed:raise ValueError('Berry choice has no corresponding actual ingredient effect')
 for value in choices.values():INSTANCES.text(value,'selected actual Berry target')
 if 'flavor_edition' in choices and choices['flavor_edition'] not in ('kr_book','core_en_1_05'):raise ValueError('exact printed Treat Berry edition required')
 return deepcopy(choices)


def _validate_critical_berry(actor,record):
 allowed={'source','effect_contract','berry_critical','buff_id','receipt_sequence','grant_source','encounter_end','owned_statuses','installing'}
 if set(record)-allowed or record.get('source')!='item/랑사열매' or record.get('effect_contract') is not True or record.get('berry_critical') is not True or record.get('encounter_end') is not True:raise ValueError('actual Lansat encounter lifetime required')
 receipts=[r for r in actor.spec.get('food_consumption_receipts',[]) if r.get('buff_id')==record.get('buff_id') and r.get('sequence')==record.get('receipt_sequence')]
 if len(receipts)!=1:raise ValueError('Lansat critical range needs its actual consumed parent')
 receipt=receipts[0];benefit=receipt.get('benefit',{})
 rows=[benefit,*benefit.get('components',[]),*benefit.get('composite',[])]
 matching=[r for r in rows if r.get('grant_source')==record.get('grant_source') and r.get('delta')==1 and r.get('until')=='encounter_end']
 if len(matching)!=1:raise ValueError('Lansat critical range differs from its actual receipt')
 effects=[receipt['effect']] if receipt['effect'].get('kind')!='chef_composite' else [p['effect'] for p in receipt['effect']['components'] if p['item']==record['source']]
 if snack_effect(actor.r,record['source']) not in effects:raise ValueError('Lansat receipt has another source payload')
 import state_grants as G
 source=record['grant_source'];row=G.state(actor)['sources'].get(source,{})
 modifiers=[m for m in actor.modifiers if m.get(G.TAG)==source]
 if row.get('rule_id')!=record['source'] or row.get('owner_id')!=actor.entity_id or row.get('lifetime')!='encounter_end' or modifiers!=[{'type':'crit_range','delta':1,G.TAG:source}]:raise ValueError('Lansat critical contribution lost its source ownership')


def _validate_csv_sweet(actor,record):
 allowed={'source','effect_contract','csv_sweet','effect_id','buff_id','turn_owner','turn_deadline','encounter_end','evasion_modifier','owned_statuses','installing'}
 if set(record)-allowed or record.get('source')!='item/단맛-과자' or record.get('effect_contract') is not True or record.get('turn_owner') is not actor or record.get('encounter_end') is not True:raise ValueError('typed CSV Sweet lifetime required')
 C.integer(record.get('turn_deadline'),'CSV Sweet turn deadline',1)
 receipts=[r for r in actor.spec.get('food_consumption_receipts',[]) if r.get('buff_id')==record.get('buff_id')]
 if len(receipts)!=1 or receipts[0].get('producer')!='sweet_self_activation':raise ValueError('CSV Sweet needs one actual self-activation receipt')
 import csv_item_food_contracts as CSV
 CSV.validate_native(actor,receipts[0])
 benefit=receipts[0].get('benefit',{})
 expected=2 if benefit.get('disposition')=='liked' else 1
 if benefit.get('disposition') not in ('neutral','liked','disliked') or benefit.get('kind')!='timed_modifiers' or benefit.get('until')!='end_of_next_turn' or benefit.get('evasion')!=expected or record.get('evasion_modifier')!=expected or record.get('effect_id')!='csv-sweet:'+record.get('buff_id','') or benefit.get('effect_id')!=record.get('effect_id') or record.get('accuracy_modifier',0)!=0:raise ValueError('CSV Sweet receipt and timed effect disagree')


def validate_world(engine,index):
 import csv_item_food_contracts as CSV
 CSV.validate_world(engine,index)
 import chef_cooking as CHEF
 CHEF.validate_world(engine,index)
 for actor in index.values():
  validate_actor_state(actor)
  for key in (*CHEF_CHOICE_KEYS,'food_hit_choice','food_move_choice',BERRY_HIT_CHOICE,BERRY_PRIORITY_CHOICE):
   choice=actor.spec.get(key,{})
   if 'owner_id' in choice:
    import vitamin_moves as V
    if V.owner_consent(engine,actor,index.get(choice['owner_id'])) is None:raise ValueError('food choice needs its actual current owner')
  import combat_timing as TIMING
  for record in TIMING.records(actor):
   if record.get('chef_snack') and index.get(record['turn_owner'].entity_id) is not record['turn_owner']:raise ValueError('Chef timed effect turn owner is missing')
 return True

def _has_suppression(buff):
 effect=buff['effect']
 return effect.get('kind')=='stat_suppression' or effect.get('kind')=='chef_composite' and any(part['effect'].get('kind')=='stat_suppression' for part in effect['components'])


def _suppression_choice_owner(e,actor,choice=None):
 import world_entities as W
 choice=actor.spec.get('food_move_choice',{}) if choice is None else choice
 return W.actor_index(e).get(choice.get('owner_id'))


def move_consumption_plan(e,actor,move_id):
 if move_id!=STUFF_CHEEKS:raise ValueError('source-specific Move consumption producer required')
 selected(e,move_id)
 if not actor.buffs:return None
 choice=actor.spec.get('food_move_choice')
 if choice is not None:
  if choice.get('move_id')!=move_id:raise ValueError('Digestion Buff choice belongs to another Move')
  buff=get_buff(actor,choice.get('buff_id'))
 elif len(actor.buffs)==1:
  candidate=actor.buffs[0]
  if not isinstance(candidate,dict):raise ValueError('actual acquired Digestion Buff required')
  buff=get_buff(actor,candidate.get('id'))
 else:raise ValueError('choose one actual Digestion Buff before this Move')
 pending=immediate_preflight(e,actor,buff,ignore_conditions=True,owner_consent_by=_suppression_choice_owner(e,actor))
 if isinstance(pending,C.PendingDecision):raise ValueError(str(pending))
 return buff


def move_consumption_commit(e,actor,move_id):
 buff=move_consumption_plan(e,actor,move_id)
 if buff is None:return None
 return immediate_commit(e,actor,buff,producer=move_id,reason='source Move exchanges actual food buff',ignore_conditions=True,owner_consent_by=_suppression_choice_owner(e,actor))


def consume_buff(e,actor,*,buff_id,action_kind=None,action_reason=None,save_condition=None,move_id=None,legacy_reason=None,owner_consent_by=None,berry_choices=None):
 if legacy_reason is not None:
  if any(v is not None for v in (action_kind,action_reason,save_condition,move_id,owner_consent_by,berry_choices)):raise ValueError('reconcile the observed legacy source before choosing its native consumer')
  import csv_item_food_contracts as CSV
  return CSV.adopt_legacy(e,actor,buff_id,reason=legacy_reason)
 buff=get_buff(actor,buff_id)
 if _has_suppression(buff):
  import vitamin_moves as V,world_entities as W,state_grants as GRANTS
  owner_id=V.owner_consent(e,actor,owner_consent_by)
  return GRANTS.transition(e,actor,lambda staged,a:_consume_buff(staged,a,buff_id=buff_id,action_kind=action_kind,action_reason=action_reason,save_condition=save_condition,move_id=move_id,owner_consent_by=W.actor_index(staged).get(owner_id),berry_choices=berry_choices))
 if owner_consent_by is not None:raise ValueError('owner suppression choice requires a Suppressant Berry')
 if berry_choices is None and buff['effect'].get('kind') not in ('chef_snack','chef_composite','stage_change','herb_cure_volatile','herb_reset_lowered','herb_skip_setup','berry_reactive','berry_priority',*BERRY_IMMEDIATE):return _consume_buff(e,actor,buff_id=buff_id,action_kind=action_kind,action_reason=action_reason,save_condition=save_condition,move_id=move_id)
 import state_grants as GRANTS
 return GRANTS.transition(e,actor,lambda staged,a:_consume_buff(staged,a,buff_id=buff_id,action_kind=action_kind,action_reason=action_reason,save_condition=save_condition,move_id=move_id,berry_choices=berry_choices))


def _consume_buff(e,actor,*,buff_id,action_kind=None,action_reason=None,save_condition=None,move_id=None,owner_consent_by=None,berry_choices=None):
 import movement_actions as MOVEMENT
 MOVEMENT.boundary(e,'consume_food_buff')
 buff=get_buff(actor,buff_id);consumption_allowed(e,actor,buff)
 import chef_cooking as CHEF
 pending=CHEF.taste_bonus_preflight(e,actor,buff)
 if pending is not None:return pending
 if berry_choices is not None:
  choices=_berry_choices(buff,berry_choices)
  prior=actor.spec.get(BERRY_CHOICE)
  if prior is not None and prior['buff_id']!=buff_id:raise ValueError('one actual selected Berry buff at a time')
  actor.spec[BERRY_CHOICE]={'buff_id':buff_id,'choices':choices}
 effect=_consumer_effect(buff)
 if _has_suppression(buff):
  import vitamin_moves as V
  if V.owner_consent(e,actor,owner_consent_by) is None:return C.PendingDecision('Suppressant Berry needs the actual current owner choice before its effect')
 if effect['kind']=='berry_ingredient':return C.PendingDecision('Poffin Ingredient is consumed as an actual physical cooking input, not a combat benefit')
 if effect['kind'] in ('chef_snack','type_resistance','herb_skip_setup','berry_reactive','berry_priority'):
  pending=_berry_composite_preflight(e,actor,buff,owner_consent_by)
  if pending is not None:return pending
 if effect['kind'] in ('berry_reactive','berry_priority'):
  if any(v is not None for v in (action_kind,action_reason,save_condition)):raise ValueError('Berry event is exchanged only in its actual native hit or Priority Move')
  key=BERRY_HIT_CHOICE if effect['kind']=='berry_reactive' else BERRY_PRIORITY_CHOICE
  if key in actor.spec:raise ValueError('one selected actual Berry event buff at a time')
  row={'buff_id':buff_id}
  if effect['kind']=='berry_priority':
   if move_id not in actor.moves:raise ValueError('Custap Berry requires one actual owned selected Move')
   if actor.hp*4>actor.base_max_hp:raise ValueError('Custap Berry requires HP at most one quarter true maximum')
   row['move_id']=move_id
  elif move_id is not None:raise ValueError('reactive Berry has no chosen outgoing Move')
  if _has_suppression(buff):row['owner_id']=owner_consent_by.entity_id
  actor.spec[key]=row
  return {'status':'prepared_for_actual_hit' if key==BERRY_HIT_CHOICE else 'prepared_for_actual_priority','buff_id':buff_id,**({'move_id':move_id} if move_id is not None else {})}
 if effect['kind']=='herb_skip_setup':
  if any(value is not None for value in (action_kind,action_reason,save_condition)):raise ValueError('Power Herb is exchanged within its actual Set-Up Move')
  import herb_mushroom_rules as HERB
  return HERB.prepare_power_herb(e,actor,buff,move_id,owner_consent_by)
 if effect['kind']=='csv_food':
  if effect.get('contract_kind')!='sweet_confection_homebrew':raise ValueError('this CSV Digestion Buff needs its actual designated native consumer')
  if any(value is not None for value in (action_kind,action_reason,save_condition,move_id)):raise ValueError('CSV Sweet uses its own self-activation consumer')
  import csv_item_food_contracts as CSV
  return CSV.activate_sweet(e,actor,buff_id)
 if effect['kind']=='chef_snack':
  if any(value is not None for value in (action_kind,action_reason,save_condition,move_id)):raise ValueError('Chef Digestion Buff uses only its exact attack or self-activation consumer')
  return _chef_prepare(e,actor,buff,owner_consent_by)
 if move_id is not None:
  if move_id!=STUFF_CHEEKS or action_kind is not None or action_reason is not None or save_condition is not None:raise ValueError('source Move choice adds no separate action or saving event')
  selected(e,move_id)
  if 'food_move_choice' in actor.spec:raise ValueError('one actual Move food choice at a time')
  pending=immediate_preflight(e,actor,buff,ignore_conditions=True,owner_consent_by=owner_consent_by)
  if isinstance(pending,C.PendingDecision):return pending
  actor.spec['food_move_choice']={'move_id':move_id,'buff_id':buff_id}
  if _has_suppression(buff):actor.spec['food_move_choice']['owner_id']=owner_consent_by.entity_id
  return {'status':'prepared_for_actual_move','move_id':move_id,'buff_id':buff_id}
 if effect['kind']=='save_bonus':
  if action_kind is not None or action_reason is not None:raise ValueError('exchange during an actual save adds no separate invented action')
  if not isinstance(save_condition,str) or not save_condition:raise ValueError('actual saving-check condition to receive the optional buff required')
  if save_condition!='네트' and not any(x.get('type')=='save' for x in e.r.condition_effects(save_condition)):raise ValueError('native saving-check consumer required')
  if 'food_save_choice' in actor.spec:raise ValueError('a selected food buff already awaits its actual save')
  actor.spec['food_save_choice']={'buff_id':buff_id,'condition':save_condition}
  return {'status':'prepared_for_actual_save','buff_id':buff_id,'condition':save_condition}
 if save_condition is not None:raise ValueError('selected buff does not modify saves')
 if effect['kind']=='type_resistance':
  if action_kind is not None or action_reason is not None:raise ValueError('type berry is exchanged within an actual hit, with no separately invented action')
  if 'food_hit_choice' in actor.spec:raise ValueError('one selected actual-hit Digestion Buff choice required')
  actor.spec['food_hit_choice']={'buff_id':buff_id}
  if _has_suppression(buff):actor.spec['food_hit_choice']['owner_id']=owner_consent_by.entity_id
  return {'status':'prepared_for_actual_hit','buff_id':buff_id,'type':effect['move_type']}
 pending=immediate_preflight(e,actor,buff,owner_consent_by=owner_consent_by)
 if isinstance(pending,C.PendingDecision):return pending
 if action_kind is None or action_reason is None:return C.PendingDecision('GM action timing and cost for trading in this Digestion Buff')
 if action_kind not in ('free','swift','standard'):raise ValueError('explicit supported GM Digestion Buff action kind required')
 if not isinstance(action_reason,str) or not action_reason.strip():raise ValueError('GM Digestion Buff action reason required')
 if e.encounter_active and (actor.injuries>=5 and not __import__('taskmaster').ignores_acting_loss(actor)) and (action_kind=='standard' or (action_kind=='swift' and getattr(actor,'budget',{}).get('swift',0)<=0)):raise ValueError('food action needs reviewed heavy Standard composition')
 if not TURN.spend(e,actor,action_kind,'만복 버프 소비',sleep_cure=(effect['kind']=='cure' and effect['status']=='잠듦')):return False
 return immediate_commit(e,actor,buff,producer='food_action',reason=action_reason,owner_consent_by=owner_consent_by)


def save_preflight(e,actor,condition):
 choice=actor.spec.get('food_save_choice')
 if not choice or choice['condition']!=condition:return None
 buff=get_buff(actor,choice['buff_id']);consumption_allowed(e,actor,buff)
 if buff['effect']!={'kind':'save_bonus','amount':2}:raise ValueError('selected save Digestion Buff changed')
 return buff

def save_bonus(e,actor,condition):
 buff=save_preflight(e,actor,condition)
 if buff is None:return 0
 receipt=remove_buff(e,actor,buff,producer='saving_check');receipt['benefit']={'save_condition':condition,'bonus':buff['effect']['amount']};return buff['effect']['amount']

def turn_start(e,actor):
 plans=[]
 for record in actor.spec.get('food_turn_healing',[]):
  selected(e,record['source']);selected(e,record['item'])
  if INSTANCES.KEY in record:
   validate_native(actor,record);denominator=record['effect']['denominator']
  else:denominator=C.integer(record.get('denominator'),'legacy food healing denominator',1)
  plans.append(denominator)
 for denominator in plans:e.heal(actor,M.ratio(actor.base_max_hp,denominator),source_kind='ordinary_item')

def end_encounter(actor):actor.spec.pop('food_turn_healing',None)

def herbal_preflight(e,actor,uid):
 if uid not in HERBS:return None
 selected(e,MEDICINE);selected(e,uid)
 state=deepcopy(validate_herbal(actor))
 prepared=__import__('study_books').herbal_provider(e,actor)
 if prepared is not None:
  if prepared['repeat_food_buff'] or state['count']==0:buff_capacity(e,actor)
  return state
 if state['count']>=2:
  import combat_stage_sources as STAGES
  STAGES.prepared(actor)
 else:
  buff_capacity(e,actor)
  C.integer(actor.spec.get('food_buff_sequence',0),'food buff sequence',0)
 return state

def herbal_consumed(e,actor,uid):
 state=herbal_preflight(e,actor,uid)
 if state is None:return
 state['count']+=1
 result={'count':state['count'],'source':MEDICINE,'item':uid}
 prepared=__import__('study_books').herbal_provider(e,actor)
 if prepared is not None:result.update(study_book=deepcopy(prepared['provider']),repeat_food_buff=prepared['repeat_food_buff'])
 if state['count']==1 or prepared is not None and prepared['repeat_food_buff']:
  buff=grant_buff(e,actor,uid,{'kind':'save_bonus','amount':2},source=MEDICINE)
  result['buff_id']=buff['id'] if buff else None
 elif state['count']>=3 and prepared is None:
  faces=[row['face'] for row in POOLS.recursive(e.rng,1,repeat=True)]
  stat=('atk','def','spa','spd','spe')[faces[-1]-1]
  import combat_stage_sources as STAGES
  STAGES.add_base(actor,'herbal_restoratives',stat,-1,source=MEDICINE,ends='extended_rest')
  result.update(faces=faces,stat=stat,base_stage_delta=-1)
 state.setdefault('uses',[]).append(result)
 actor.spec['herbal_restoratives']=state
 return result

def extended_rest(e,actor):
 validate_herbal(actor)
 import combat_stage_sources as STAGES
 STAGES.end_source(actor,ends='extended_rest')
 actor.spec.pop('herbal_restoratives',None)


def _berry_en_source(rules):
 import chef_cooking as CHEF
 from source_context import verified_source
 source=CHEF.definitions(rules)['berry_source']['core_en_source']
 verified_source(rules,source,label='PTU Core 1.05 Treat Berries and Poffin Mixer',source_root='source-audit')
 return deepcopy(source)


def snack_effect(rules,uid):
 if uid in BERRY_POLICY_ITEMS:
  import chef_cooking as CHEF
  source=CHEF.definitions(rules)['berry_source'];path=Path(rules.root)/source['file']
  if hashlib.sha256(path.read_bytes()).hexdigest()!=source['sha256']:raise ValueError('reviewed Berry source file changed')
  lo,hi=source['lines'];excerpt='\n'.join(path.read_text(encoding='utf-8').splitlines()[lo-1:hi])
  if hashlib.sha256(excerpt.encode()).hexdigest()!=source['excerpt_sha256'] or rules._selected_rule(uid)!=uid:raise ValueError('reviewed Berry source table changed')
  return deepcopy(source['effects'][uid])
 import vitamin_moves as V
 if uid in V.SUPPRESSANT_BERRIES:
  effects,_=rules.item_effects(uid);stat=V.SUPPRESSANT_BERRIES[uid]
  if effects!=[{'type':'stat_base_mod','stat':stat,'value':-1,'note':'영양제 역(트레이너 허가)'}] or type(effects[0]['value']) is not int:raise ValueError('Suppressant Berry needs its reviewed exact stat effect')
  return {'kind':'stat_suppression','stat':stat,'value':-1,'berry':True}
 import herb_mushroom_rules as HERB
 if uid in HERB.SNACK_HERBS:return HERB.snack_effect(rules,uid)
 if uid in SNACKS:return deepcopy(SNACKS[uid])
 if uid in CHEF_SNACK_IDS:return chef_effect(rules,uid)
 if uid in BERRY_HEALS:return {'kind':'heal','amount':BERRY_HEALS[uid],'berry':True}
 if uid in BERRY_STAGES:
  effects,_=rules.item_effects(uid);stat=BERRY_STAGES[uid]
  if rules._selected_rule(uid)!=uid or [x for x in effects if x.get('type')=='stage_change']!=[{'type':'stage_change','stat':stat,'delta':1,'target':'target'}] or any(x.get('type') not in ('stage_change','tag') for x in effects):raise ValueError('stage Berry needs its reviewed exact native stat effect')
  return {'kind':'stage_change','stat':stat,'delta':1,'berry':True}
 if uid in BERRY_CURES:return {'kind':'cure','status':BERRY_CURES[uid],'berry':True}
 if uid in BERRY_TYPES:return {'kind':'type_resistance','move_type':BERRY_TYPES[uid],'requires_super_effective':uid!='item/카리열매','berry':True}
 return None

def salty_hit_pending(e,actor,*,attacker):
 if attacker is actor or getattr(attacker,"side",None) is None or getattr(actor,"side",None) is None or attacker.side==actor.side or not actor.spec.get('food_hit_choice'):return False
 buff=get_buff(actor,actor.spec['food_hit_choice']['buff_id'])
 if _consumer_effect(buff)['kind']!='type_resistance':return False
 import chef_cooking as CHEF
 bonus=CHEF.bonus_plan(e,actor,buff)
 return bonus is not None and bonus['kind']=='temporary_hp'


def _hit_resistance_buff(actor,move_type,multiplier,*,attacker):
 choice=actor.spec.get('food_hit_choice')
 if not choice:return None
 buff=get_buff(actor,choice['buff_id']);effect=_consumer_effect(buff)
 if effect['kind']!='type_resistance':raise ValueError('selected hit-trigger buff changed')
 if attacker is actor or getattr(attacker,"side",None) is None or getattr(actor,"side",None) is None or attacker.side==actor.side:return None
 if move_type!=effect['move_type'] or (effect['requires_super_effective'] and multiplier<=1):return None
 return buff


def hit_resistance_preflight(e,actor,move_type,multiplier,*,attacker,temporary_hp_plan):
 buff=_hit_resistance_buff(actor,move_type,multiplier,attacker=attacker)
 if buff is None:return
 consumption_allowed(e,actor,buff)
 import chef_cooking as CHEF
 pending=CHEF.taste_bonus_preflight(e,actor,buff,temporary_hp_grants=[],temporary_hp_plan=temporary_hp_plan)
 if pending is not None:raise ValueError(str(pending))


def hit_resistance(e,actor,move_type,multiplier,*,attacker):
 buff=_hit_resistance_buff(actor,move_type,multiplier,attacker=attacker)
 if buff is None:return 0
 consumption_allowed(e,actor,buff)
 owner=_suppression_choice_owner(e,actor,actor.spec['food_hit_choice'])
 pending=_berry_composite_preflight(e,actor,buff,owner)
 if pending is not None:raise ValueError(str(pending))
 if _has_suppression(buff):
  import vitamin_moves as V
  if V.owner_consent(e,actor,owner) is None:raise ValueError('type Berry composite needs its actual current owner consent')
 receipt=remove_buff(e,actor,buff,producer='actual_hit');receipt['benefit']={'move_type':move_type,'resistance_steps':1}
 receipt['benefit']['composite']=_apply_composite_rest(e,actor,buff,receipt,'type Berry hit',owner)
 return 1


def berry_after_hit(e,attacker,target,move,event,damage_receipt):
 """Observe only the native finalized application, never a damage preview.

 The actual hit is already committed at this boundary. The selected trade-in,
 its native response and every composite benefit form one atomic exchange.
 """
 choice=target.spec.get(BERRY_HIT_CHOICE)
 if choice is None or attacker is target:return None
 buff=get_buff(target,choice['buff_id']);effect=_consumer_effect(buff)
 if effect['kind']!='berry_reactive':raise ValueError('actual hit Berry payload changed')
 if event.get('attacker') is not attacker or event.get('target') is not target or event.get('move')!=move:raise ValueError('Berry reaction needs the actual native hit participants')
 if damage_receipt.get('source')!=move['id'] or damage_receipt.get('damage_class')!=move['class']:raise ValueError('Berry reaction needs the actual finalized Move receipt')
 actual_type=event.get('actual_damage_type')
 multiplier=event.get('effective_type_multiplier',event.get('damage_formula',{}).get('multiplier'))
 if effect.get('attack_class') is not None and effect['attack_class']!=move['class']:return None
 if effect['trigger']=='super_effective_hit':
  if not isinstance(actual_type,str) or multiplier is None:
   e.log('    의문열매: 실제 효과배수 근거 없음, 미선택 버프 유지(중립 상성으로 추정하지 않음)','item/의문열매')
   return None
  if multiplier<=1:return None
 if effect['trigger']=='received_damage':
  if attacker.side==target.side:return None
  native=damage_receipt.get('native_damage',{})
  if max(0,native.get('amount_after_temporary_hp',damage_receipt.get('net_hp_loss',0)))+max(0,damage_receipt.get('net_temporary_hp_loss',0))<=0:return None
 if target.dead or target.fainted:return None
 import state_grants as G
 def apply(staged,actor,foe):
  current=actor.spec.get(BERRY_HIT_CHOICE)
  if current!=choice:raise ValueError('actual hit Berry choice changed before exchange')
  selected_buff=get_buff(actor,current['buff_id']);payload=_consumer_effect(selected_buff)
  consumption_allowed(staged,actor,selected_buff)
  owner=_suppression_choice_owner(staged,actor,current)
  if _has_suppression(selected_buff):
   import vitamin_moves as V
   if V.owner_consent(staged,actor,owner) is None:raise ValueError('reactive Berry composite needs its actual current owner choice')
  pending=_berry_composite_preflight(staged,actor,selected_buff,owner)
  if pending is not None:raise ValueError(str(pending))
  if payload.get('action')=='free':ACTION.triggered_free_action(staged,actor,selected_buff['item'])
  receipt=remove_buff(staged,actor,selected_buff,producer='actual_berry_hit')
  benefit={'kind':'berry_reactive','move_id':move['id'],'move_class':move['class'],'actual_damage_type':actual_type,
           'multiplier':multiplier,'attacker_id':foe.entity_id,'damage_receipt':deepcopy(damage_receipt)}
  if payload['benefit']=='temporary_hp':
   import temporary_hp as TEMP
   benefit.update(kind='temporary_hp',amount=M.ratio(actor.base_max_hp,payload['denominator']))
   receipt['benefit']=benefit
   benefit['gained']=TEMP.grant(staged,actor,benefit['amount'],
    contribution_source=TEMP.food_source(actor,'food',receipt),
    provenance={'source':selected_buff['item'],'receipt_sequence':receipt['sequence'],'buff_id':selected_buff['id']})
  elif payload['benefit']=='attacker_hp_loss':
   amount=M.ratio(foe.base_max_hp,payload['denominator']);before=foe.hp
   staged.lose_hp(foe,amount,source=selected_buff['item'],loss_kind='loss')
   benefit.update(requested_loss=amount,actual_hp_loss=before-foe.hp)
  else:
   before=actor.stages[payload['stat']];staged.change_stage(actor,payload['stat'],payload['delta'])
   benefit.update(stat=payload['stat'],requested_delta=payload['delta'],actual_delta=actor.stages[payload['stat']]-before)
  benefit['composite']=_apply_composite_rest(staged,actor,selected_buff,receipt,'actual Berry hit',owner)
  receipt['benefit']=benefit
  return deepcopy(benefit)
 return G.transition(e,target,apply,participants=(attacker,))


def priority_berry(e,actor,move_id,*,commit=False):
 """Preflight the loan; exchange once inside its actual native Move."""
 choice=actor.spec.get(BERRY_PRIORITY_CHOICE)
 if choice is None or choice['move_id']!=move_id:return None
 if commit:
  import initiative_interrupts as INTERRUPTS
  current=INTERRUPTS.frame(e)
  if current is None:return None
  loan=getattr(e,INTERRUPTS.KEY)['loans'].get(current['loan_id'])
  if loan is None or loan['source']!='item/애슈열매':return None
  if (not getattr(e,'_native_move_resolution_depth',0) or current['actor'] is not actor
      or e._active_turn_actor is not actor or current['mode']!='borrow_turn'
      or current['status']!='open' or loan['actor'] is not actor
      or loan['status']!='owed' or loan['due_round']!=e.round_no):
   raise ValueError('Custap exchange requires its actual current-round native Priority loan')
 buff=get_buff(actor,choice['buff_id']);effect=_consumer_effect(buff)
 if effect['kind']!='berry_priority' or move_id not in actor.moves:raise ValueError('Custap needs its actual selected owned Move')
 if actor.hp*4>actor.base_max_hp:raise ValueError('Custap Berry requires HP at most one quarter true maximum')
 consumption_allowed(e,actor,buff);owner=_suppression_choice_owner(e,actor,choice)
 if _has_suppression(buff):
  import vitamin_moves as V
  if V.owner_consent(e,actor,owner) is None:raise ValueError('Custap composite needs its actual current owner choice')
 pending=_berry_composite_preflight(e,actor,buff,owner)
 if pending is not None:raise ValueError(str(pending))
 if not commit:return 'item/애슈열매'
 receipt=remove_buff(e,actor,buff,producer='actual_priority_move')
 receipt['benefit']={'kind':'ordinary_priority','move_id':move_id,'composite':_apply_composite_rest(e,actor,buff,receipt,'actual ordinary Priority Move',owner)}
 return 'item/애슈열매'

def _prepare_baby(target,policy):
 if policy is None:return C.PendingDecision('Baby Food book and raw inventory source policies require explicit selection')
 if policy not in BABY_POLICIES:raise ValueError('explicit supported Baby Food source policy required')
 if target.kind!='pokemon':raise ValueError('Baby Food recipient must be a Pokemon')
 if policy=='homebrew_initial_plus5':_baby_eligibility(target,policy)
 previous=target.spec.get('baby_food')
 if previous and not previous.get('consumed') and (previous['policy'] in TRAINING_BABY_POLICIES or previous['day']==target.spec.get('frequency_state',{}).get('day',0)):
  return C.PendingDecision('repeated Baby Food source stacking is not defined')
 return None


def _baby_eligibility(target,policy):
 if policy=='book_xp20_level15':return {'kind':'maximum_level','maximum_level':15}
 if policy=='raw_training_level20':return {'kind':'maximum_level','maximum_level':20}
 import pokemon_progression as PROGRESSION
 PROGRESSION.validate(target.spec)
 progression=target.spec.get(PROGRESSION.LEVEL_STATE)
 if not isinstance(progression,dict):raise ValueError('homebrew Baby Food requires the actual Pokemon initial-level anchor')
 initial=progression['initial_level']
 return {'kind':'initial_level_window','initial_level':initial,'maximum_level':initial+5,
         'clause_id':'C2CSV/inventory:94:7'}


def consume_baby(e,user,target,uid,key,minutes,reason,policy):
 pending=_prepare_baby(target,policy)
 if pending is not None:return pending
 e.advance_time(minutes*60,[user,target])
 return _finish_intake(e,user,target,dict(kind='baby',policy=policy,item=uid,stock=key,reason=reason),None)[0]

def baby_xp(rules,spec,amount):
 record=spec.get('baby_food')
 if not record or record['policy']!='book_xp20_level15' or record['day']!=spec.get('frequency_state',{}).get('day',0) or spec['level']>15:return amount
 if rules._selected_rule(record['source'])!=record['source']:raise ValueError('Baby Food source changed after actual intake')
 M.validate_source(rules)
 return M.increase(amount,'0.2',quantity='experience',base_id='actual_xp_award',stage='baby_food',source='item/이유식') if amount>0 else amount

def baby_training_plan(e,target,amount):
 record=target.spec.get('baby_food')
 if not record or record['policy'] not in TRAINING_BABY_POLICIES or record.get('consumed') or not record['eligible_when_fed']:return False
 expected=_baby_eligibility(target,record['policy']);observed=record.get('eligibility')
 if ((observed is not None and observed!=expected)
     or (record['policy']=='homebrew_initial_plus5' and observed!=expected)):
  raise ValueError('Baby Food eligibility source changed after actual intake')
 selected(e,record['source'])
 # Native level growth needs the same allocation/source checks before time.
 import downtime as DT
 probe=deepcopy(target.spec);DT.gain_exp(e.r,probe,amount)
 extra=max(0,DT.exp_for_level(e.r,probe['level']+1)-probe.get('exp',DT.exp_for_level(e.r,probe['level'])))
 DT.gain_exp(e.r,probe,extra,source_kind='level_grant')
 return True

def finish_baby_training(e,target,extra_level):
 if not extra_level:return
 import downtime as DT
 DT.gain_exp_combatant(e,target,'to next level')
 target.spec['baby_food']['consumed']=True


def honey_thief_connection(rules,name,effect):
 # Connection grants a Move, but this source's HP trigger requires actual theft.
 if name not in ('꿀도둑','ability/꿀도둑'):return False
 import temporary_hp as TEMP
 TEMP.policy(rules)
 if rules._selected_rule('ability/꿀도둑')!='ability/꿀도둑':raise ValueError('selected Honey Thief source needs its own producer')
 semantic={k:v for k,v in effect.items() if not k.startswith('_')}
 if isinstance(semantic.get('effect'),dict):semantic['effect']={k:v for k,v in semantic['effect'].items() if not k.startswith('_')}
 if semantic!={'type':'connection','move':'벌레먹기','effect':{'type':'temp_hp','value':'tick'}}:raise ValueError('Honey Thief extraction differs from its reviewed transfer trigger')
 return True


def theft_condition(holder):
 if holder.buffs:return True
 import frequency as FREQ
 scene=FREQ.state(holder)['scene']
 receipts=holder.spec.get('food_consumption_receipts',[])
 if not isinstance(receipts,list):raise ValueError('actual food consumption receipts required')
 if any(row.get('scene')==scene and INSTANCES.KEY in row for row in receipts):return True
 return False


def honey_thief_after_transfer(engine,receiver,previous,buff,source):
 if source!='move/벌레먹기' or receiver.abilities_suppressed:return
 if not any(name in ('꿀도둑','ability/꿀도둑') for name in receiver.abilities):return
 selected(engine,'ability/꿀도둑')
 import temporary_hp as TEMP
 gained=TEMP.grant(engine,receiver,engine.tick(receiver))
 if gained:
  receiver.custom_conditions[TEMP.STATE]['grant_source']='ability/꿀도둑'
  receiver.custom_conditions[TEMP.STATE]['grant_event']={'kind':'food_effect_transfer','effect_id':buff['id'],'from_actor_id':previous.entity_id,'move_source':source}
 engine.log('    Honey Thief: actual stolen food effect '+buff['id'],'ability/꿀도둑')


def _transfer_receipt_fingerprint(receipt):
 import root_resolution as ROOT
 return ROOT.fingerprint(receipt)


def _transfer_candidates(e,recipient,holder,source):
 selected(e,source)
 if source!='move/벌레먹기':raise ValueError('source-specific food transfer required')
 if recipient is holder:raise ValueError('food transfer requires distinct holders')
 if not isinstance(holder.buffs,list):raise ValueError('actual food effect list required')
 candidates=[]
 for row in holder.buffs:
  if not isinstance(row,dict) or INSTANCES.KEY not in row:raise ValueError('actual typed food effect required')
  buff=get_buff(holder,row.get('id'))
  import csv_item_food_contracts as CSV
  if not CSV.transferable(holder,buff):continue
  candidates.append({'kind':'live','buff_id':buff['id'],'record':buff})
 import frequency as FREQ
 scene=FREQ.state(holder)['scene']
 receipts=holder.spec.get('food_consumption_receipts',[])
 if not isinstance(receipts,list) or any(not isinstance(row,dict) for row in receipts):raise ValueError('actual food consumption receipts required')
 for receipt in receipts:
  if receipt.get('scene')!=scene or INSTANCES.KEY not in receipt:continue
  validate_native(holder,receipt,spent=True)
  import csv_item_food_contracts as CSV
  if not CSV.transferable(holder,receipt):continue
  candidates.append({'kind':'consumed','buff_id':receipt['buff_id'],'record':receipt})
 return candidates


def choose_transfer(e,recipient,holder,buff_id,*,reason):
 """Bind one real live/consumed target effect before an ambiguous Bug Bite."""
 if not isinstance(reason,str) or not reason.strip():raise ValueError('food transfer choice reason required')
 candidates=_transfer_candidates(e,recipient,holder,'move/벌레먹기')
 matches=[row for row in candidates if row['buff_id']==buff_id]
 if len(matches)!=1:raise ValueError('one actual target food effect required')
 if 'food_theft_choice' in recipient.spec:raise ValueError('one actual food transfer choice at a time')
 recipient.spec['food_theft_choice']={'source':'move/벌레먹기','holder_id':holder.entity_id,'buff_id':buff_id,'kind':matches[0]['kind'],'reason':reason}
 return deepcopy(recipient.spec['food_theft_choice'])


def transfer_live_preflight(e,recipient,holder,source):
 candidates=_transfer_candidates(e,recipient,holder,source)
 if not candidates:return None
 choice=recipient.spec.get('food_theft_choice')
 if choice is None:
  if len(candidates)!=1:raise ValueError('choose one actual live or consumed food effect before Bug Bite')
  chosen=candidates[0]
 else:
  if not isinstance(choice,dict) or choice.get('source')!=source or choice.get('holder_id')!=holder.entity_id:
   raise ValueError('food transfer choice belongs to another source or holder')
  matches=[row for row in candidates if row['buff_id']==choice.get('buff_id') and row['kind']==choice.get('kind')]
  if len(matches)!=1:raise ValueError('selected food transfer effect changed before the hit')
  chosen=matches[0]
 if not can_gain_buff(e,recipient,capacity=capacity_from_source(e.r,source)):raise ValueError('recipient cannot acquire transferred food effect')
 if chosen['kind']=='live' and any(row.get('buff_id')==chosen['buff_id'] for row in recipient.spec.get('food_consumption_receipts',[])):raise ValueError('transferred food effect was already consumed')
 return {'kind':chosen['kind'],'buff_id':chosen['buff_id']}


def transfer_live(e,recipient,holder,source):
 plan=transfer_live_preflight(e,recipient,holder,source)
 if plan is None:return None
 import state_grants as G
 def apply(engine,receiver,previous):
  if plan['kind']=='live':
   buff=get_buff(previous,plan['buff_id'])
   INSTANCES.transfer(engine,previous,receiver,buff,source=source,capacity=capacity_from_source(engine.r,source))
   previous.buffs.remove(buff);receiver.buffs.append(buff)
   for key in ('food_save_choice','food_hit_choice','food_move_choice',BERRY_CHOICE,BERRY_HIT_CHOICE,BERRY_PRIORITY_CHOICE,*CHEF_CHOICE_KEYS):
    if previous.spec.get(key,{}).get('buff_id')==plan['buff_id']:previous.spec.pop(key)
  else:
   import frequency as FREQ
   scene=FREQ.state(previous)['scene']
   matches=[row for row in previous.spec.get('food_consumption_receipts',[])
            if row.get('buff_id')==plan['buff_id'] and row.get('scene')==scene and INSTANCES.KEY in row]
   if len(matches)!=1:raise ValueError('consumed food receipt changed before transfer')
   receipt=matches[0];validate_native(previous,receipt,spent=True)
   buff=INSTANCES.create(engine,receiver,kind='digestion',source=receipt['source'],payload=receipt['effect'],
       capacity=capacity_from_source(engine.r,source),lifetime=buff_policy(engine.r)['lifetime'],applied_by=previous)
   buff.update(item=receipt['item'],effect_source=receipt['effect_source'],food_transfer_origin={
       'source':source,'holder_id':previous.entity_id,'buff_id':receipt['buff_id'],
       'receipt_sequence':receipt['sequence'],'receipt_scene':receipt['scene'],
       'receipt_fingerprint':_transfer_receipt_fingerprint(receipt)})
   if 'csv_food_source' in receipt:buff['csv_food_source']=deepcopy(receipt['csv_food_source'])
   validate_native(receiver,buff);receiver.buffs.append(buff)
  receiver.spec.pop('food_theft_choice',None)
  validate_native(receiver,buff)
  honey_thief_after_transfer(engine,receiver,previous,buff,source)
  engine.log(f"    {previous.name} -> {receiver.name}: food effect {buff['id']} ({plan['kind']})",source)
  return buff['id']
 return G.transition(e,recipient,apply,participants=(holder,))


def validate_transfer_world(engine,index):
 """Cross-check copied live effects against the immutable consumed receipt."""
 for actor in index.values():
  records=[(buff,False) for buff in actor.buffs]
  records.extend((receipt,True) for receipt in actor.spec.get('food_consumption_receipts',[]))
  for buff,spent in records:
   if not isinstance(buff,dict) or 'food_transfer_origin' not in buff:continue
   validate_native(actor,buff,spent=spent)
   origin=buff['food_transfer_origin'];holder=index.get(origin['holder_id'])
   if holder is None:raise ValueError('consumed-food source holder is missing')
   matches=[row for row in holder.spec.get('food_consumption_receipts',[])
            if row.get('buff_id')==origin['buff_id'] and row.get('sequence')==origin['receipt_sequence']]
   if len(matches)!=1:raise ValueError('consumed-food source receipt is missing or ambiguous')
   receipt=matches[0];validate_native(holder,receipt,spent=True)
   if receipt.get('scene')!=origin['receipt_scene'] or _transfer_receipt_fingerprint(receipt)!=origin['receipt_fingerprint']:
    raise ValueError('consumed-food source receipt changed')
   if (buff['source'],buff['item'],buff['effect_source'],buff['effect'])!=(receipt['source'],receipt['item'],receipt['effect_source'],receipt['effect']):
    raise ValueError('copied food payload differs from the consumed source receipt')
 return True

