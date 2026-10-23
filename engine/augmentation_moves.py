"""Observed Experimental Designs choices tied to real installed augmentations."""
from copy import deepcopy
SOURCE='feat/프로토-디자인'
PREFIX='augmentation-move:'
CHOICES={'enhanced_sight','smart_vision','synthetic_muscle','embedded_weaponry','wired_reflexes','medical_nanobots','dermal_plating','thermal_optic_camouflage'}


def projection(e,row,index,registry):
 history=row.get('experimental_designs',[])
 if not isinstance(history,list) or len(history)>2:raise ValueError('Experimental Designs may affect one target at most twice')
 previous=getattr(e,'_physical_objects',{}).get(row['id'],{}).get('experimental_designs',[])
 if history[:len(previous)]!=previous:raise ValueError('Experimental Designs application history cannot be erased or rewritten')
 if not history:return []
 if e.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Experimental Designs source required')
 if type(row.get('augmentation_active'))is not bool:raise ValueError('upgraded augmentation activation must be explicitly observed')
 actual=getattr(e,'_physical_objects',{}).get(row['id'],{})
 previous=actual.get('experimental_designs',[])
 if history[:len(previous)]!=previous:raise ValueError('Experimental Designs application history cannot be erased or rewritten')
 installs={x['instance_id']:x for x in row['installations']};ids=set();grants=[]
 for record in history:
  if not isinstance(record,dict) or record.get('source_id')!=SOURCE or record.get('actor_id')!=row['actor_id'] or record.get('choice') not in CHOICES:raise ValueError('actual target and source-specific Experimental Designs choice required')
  for field in ('id','creator_id','instance_id','reason'):
   if not isinstance(record.get(field),str) or not record[field]:raise ValueError('complete Experimental Designs application provenance required')
  if record['id'] in ids:raise ValueError('duplicate Experimental Designs application identity')
  ids.add(record['id'])
  if record['instance_id'] not in registry:raise ValueError('actual augmentation instance history required')
  inst=installs.get(record['instance_id'])
  if inst and inst['augmentation_id']!=record.get('augmentation_id'):raise ValueError('upgraded augmentation source identity changed')
  if record['choice']=='smart_vision':
   if record.get('augmentation_id')!='smart_vision':raise ValueError('Feint upgrade requires actual Smart Vision')
   if inst and row['augmentation_active']:grants.append({'source_id':PREFIX+row['id']+':'+record['id'],'move_id':e.r.move_id('페인트'),'rule_id':SOURCE,'instance_id':record['instance_id']})
  if record['choice']=='synthetic_muscle':
   if record.get('augmentation_id')!='synthetic_muscle':raise ValueError('Improved Synthetic Muscle requires its actual installed Synthetic Muscle')
   import csv_item_contract_policy as CSV
   CSV.definition(e.r,clause_id='C2CSV/item-data:178:5')
   if inst and row['augmentation_active']:grants.append({'source_id':PREFIX+row['id']+':'+record['id'],'capability':'개선된 인조 근육','rule_id':'C2CSV/item-data:178:5','instance_id':record['instance_id']})
 return grants


def sync(e):
 import world_entities as W,special_entities as S,state_grants as G
 index=W.actor_index(e);desired={uid:{} for uid in index}
 registry=getattr(e,'_physical_objects',{})
 for row in registry.values():
  if row.get('kind')!='augmentation_set':continue
  for grant in projection(e,row,index,registry):desired[row['actor_id']][grant['source_id']]=grant
 for uid,c in index.items():
  existing=c.spec.get('state_grants',{}).get('sources',{})
  for key in list(existing):
   if key.startswith(PREFIX) and key not in desired[uid]:G.revoke(c,key,engine=e)
  for key,grant in desired[uid].items():
   if 'capability' in grant:
    G.grant(c,'capabilities',grant['capability'],key,'augmentation',lifetime='installed_augmentation',rule_id=grant['rule_id'])
   else:
    source=G._source(c,key,'augmentation',owner_id=None,lifetime='installed_augmentation',rule_id=SOURCE,tutor_points=0,move_mode='learned')
    source['move_slot_policy']={'rule_id':SOURCE,'selected_move':grant['move_id'],'instance_id':grant['instance_id']}
    G.grant_moves(c,[grant['move_id']],key,'augmentation',lifetime='installed_augmentation',rule_id=SOURCE)


def observe_upgrade(e,owner,target,*,augmentation_set_id,instance_id,application_id,active,reason,choice='smart_vision'):
 import contest_features as FEATURES,special_entities as S
 import world_entities as W
 W.require_actors(e,owner,target)
 if owner.kind!='trainer' or not FEATURES.owned(owner,SOURCE):raise ValueError('actual acquired Experimental Designs creator required')
 if target is not owner and not (target.kind=='pokemon' and target.spec.get('trainer_id')==owner.entity_id):raise ValueError('Experimental Designs target must be you or your Pokemon')
 row=deepcopy(getattr(e,'_physical_objects',{}).get(augmentation_set_id))
 if not row or row.get('kind')!='augmentation_set' or row.get('actor_id')!=target.entity_id:raise ValueError('actual target augmentation state required')
 inst=next((x for x in row['installations'] if x['instance_id']==instance_id),None)
 if choice not in ('smart_vision','synthetic_muscle') or inst is None or inst['augmentation_id']!=choice:raise ValueError('actual matching installed upgrade augmentation required')
 record={'id':application_id,'source_id':SOURCE,'actor_id':target.entity_id,'creator_id':owner.entity_id,'instance_id':instance_id,'augmentation_id':choice,'choice':choice,'reason':reason}
 row.setdefault('experimental_designs',[]).append(record);row['augmentation_active']=active
 return S.observe(e,row,reason=reason)
