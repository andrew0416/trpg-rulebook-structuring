"""Native X-item category/lifetime and the Medic exception (PTK ch09:132-173)."""
import common_checks as C
import combat_timing as TIMING
X_ITEMS={'item/플러스파워','item/디펜드업','item/스페셜파워','item/스페셜가드','item/스피드업','item/크리티컬-커터','item/잘-맞히기','item/이펙트가드'}
# Exact native sources supported by the ordinary medicine application path.
# Other consumables (Vitamins, bandages, jewels) retain their own admission.
HELD_CONSUMABLES = X_ITEMS | {'item/'+name for name in (
 '상처약','좋은상처약','고급상처약','해독제','마비치료제','화상치료제',
 '얼음상태치료제','만병통치제','회복약','기력의조각',
 '힘의가루','힘의뿌리','만능가루','부활초')}
MEDIC='edge/메딕-훈련'
MEDICINE='ch09-equipment/모험-도구/약'

def selected(e,uid):
 if e.r._selected_rule(uid)!=uid or e.r._selected_rule(MEDICINE)!=MEDICINE:raise ValueError('selected medicine source requires its own use policy')

def preflight(e,target,uid):
 selected(e,uid)
 if uid=='item/이펙트가드' and e.encounter_active and getattr(e,'_active_turn_actor',None) is target:
  return C.PendingDecision('Guard Spec applied partway through recipient turn needs explicit five-turn counting ruling')
 return None

def medic(e,user,target):
 # The edge specifies another target. ch09 explicitly grants its exception
 # to both restorative and X-item application in that context.
 if user is target:return False
 names=[x for key in ('edges','feats','features') for x in user.spec.get(key,[])]
 has=any(str(x).removeprefix('edge/').removeprefix('feat/').replace(' ','').replace('-','').lower() in ('메딕훈련','medictraining') for x in names)
 if not has:return False
 if user.kind!='trainer':raise ValueError('Medic Training requires an acquired trainer edge')
 if e.r._selected_rule(MEDIC)!=MEDIC:raise ValueError('selected Medic Training needs its own application policy')
 import skill_modifiers as SKILL
 if not __import__('hobbyist').skill_waived(user,MEDIC) and SKILL.rank(e.r,user,'의학')[2]<3:raise ValueError('Medic Training requires Novice Medicine')
 return True

def special_apply(e,target,uid):
 if uid not in ('item/크리티컬-커터','item/이펙트가드'):return False
 record={'source':uid,'x_item':True,'encounter_end':True}
 if uid=='item/크리티컬-커터':record['crit_range_delta']=2
 else:
  record.update(prevent_stage_loss=True,turn_owner=target,turn_deadline=target.custom_conditions.get('combat_turn_serial',0)+5)
 TIMING.install(e,target,record)
 return True

def blocks_stage_loss(e,target,delta):
 if delta>=0:return False
 active=[x for x in TIMING.records(target) if x.get('x_item') and x.get('prevent_stage_loss')]
 if not active:return False
 for record in active:selected(e,record['source'])
 return True

def crit_delta(actor):
 records=[x for x in TIMING.records(actor) if x.get('x_item') and x.get('crit_range_delta')]
 for record in records:
  if actor.r._selected_rule(record['source'])!=record['source']:raise ValueError('selected X-item critical source changed while active')
 return sum(x['crit_range_delta'] for x in records)

def end_encounter(e,actor):
 for record in list(TIMING.records(actor)):
  if record.get('x_item') and record.get('encounter_end'):TIMING.expire(e,actor,record)


def blocked_condition_stage(e,actor,condition,stat,delta):
 if not blocks_stage_loss(e,actor,delta):return False
 actor.custom_conditions.setdefault('blocked_condition_stages',{}).setdefault(condition,[]).append([stat,delta])
 return True

def consume_blocked_condition_stage(actor,condition,stat,delta):
 records=actor.custom_conditions.get('blocked_condition_stages',{})
 values=records.get(condition,[])
 if [stat,delta] not in values:return False
 values.remove([stat,delta])
 if not values:records.pop(condition,None)
 if not records:actor.custom_conditions.pop('blocked_condition_stages',None)
 return True
