"""Acquired Minor Gifts, with current source selection and recorded GM approval.
Only the named check permissions/bonuses are granted. No action, automatic
success, divine patron, or other Gift is inferred from a caller's context.
"""
from copy import deepcopy
from pathlib import Path
import json
import acquisition_qualification as QUALIFICATION
import acquired_features as ACQUIRED
import arithmetic_policy as M
import common_checks as C
import skill_modifiers as S
import blessing_skill_rules as ADVANCED

SLEEP='gift/조심스런-수면'
STAGE='gift/눈부신-무대'
ROYAL='gift/왕족의-특권'
COMPASSION='gift/자애로운-연민'
TWISTED='gift/트위스트-폼'
BRANDED='feat/시종'
BRAND_SOURCE='supp-blessings/시종'
BASE='supp-blessings/전설의-기프트/'
SOURCES={SLEEP:BASE+'하급-만신전-기프트/지라치',STAGE:BASE+'하급-만신전-기프트/메로엣타',
 ROYAL:BASE+'하급-만신전-기프트/디안시',COMPASSION:BASE+'고등-만신전-기프트/뮤'}
CSV_COMPASSION='gift/마이너-기프트-자애로운-연민'
TRUTH='gift/마이너-기프트-진실된-영웅'
IDEALS='gift/마이너-기프트-이상적-영웅'
# These CSV records have their own selected source, even when mechanics agree.
SOURCES.update({uid:uid for uid in (CSV_COMPASSION,TRUTH,IDEALS)})
SOURCES.update({uid:uid for uid in ADVANCED.GIFTS})
_STATIC_POLICY=json.loads((Path(__file__).resolve().parents[1]/'data/static-feature-state-grants-policy.json').read_text(encoding='utf-8'))
SOURCES.update({row['owner_id']:row['owner_id'] for row in _STATIC_POLICY['rules'].values()
                if str(row.get('owner_id','')).startswith('gift/')})
SOURCES['gift/축복받은-회복력']='gift/축복받은-회복력'
_CONTEXT_POLICY=json.loads((Path(__file__).resolve().parents[1]/'data/blessing-context-skill-policy.json').read_text(encoding='utf-8'))
if _CONTEXT_POLICY.get('schema_version')!=1:raise ValueError('unsupported blessing context-skill policy')
CONTEXT_RULES={row['gift']:row for row in _CONTEXT_POLICY['rules']}
if len(CONTEXT_RULES)!=len(_CONTEXT_POLICY['rules']):raise ValueError('duplicate blessing context-skill gift')
for gift,row in CONTEXT_RULES.items():
 if not isinstance(row.get('clause_id'),str) or not row['clause_id'].startswith('C2CSV/input/db/class-data.csv:R'):raise ValueError('source-bound CSV blessing clause required')
 if type(row.get('record')) is not int or type(row.get('bonus')) is not int:raise ValueError('numeric CSV blessing policy required')
 if not all(isinstance(x,str) and x for x in (*row.get('skills',()),*row.get('purposes',()),*row.get('always_skills',()))):raise ValueError('named blessing skill and purpose policy required')
 SOURCES[gift]=gift
PURPOSE_BONUSES={
 COMPASSION:(('직감','매력'),('understand_emotions','comfort'),3),
 CSV_COMPASSION:(('직감','매력'),('understand_emotions','comfort'),3),
 TRUTH:(('직감',),('detect_lies',),3),
 IDEALS:(('직감',),('discern_beliefs',),3),
}
PURPOSES={'imminent_danger','singing','dancing'} | ADVANCED.CONTEXT_PURPOSES | {p for _,purposes,_ in PURPOSE_BONUSES.values() for p in purposes} | {p for row in CONTEXT_RULES.values() for p in row['purposes']}
SOCIAL=('협박','교활','매력')
CSV_SOURCE='db/class-data.csv'
PREREQUISITES={
 'gift/축복받은-회복력':(10,'gift/축복받은-힘',7),
 'gift/위대한-존재의-통찰력':(11,'gift/고대의-지혜',3),
 'gift/메이저-기프트-진실의-눈':(28,'gift/마이너-기프트-조심스런-수면',27),
 'gift/메이저-기프트-순수-호흡':(44,'gift/마이너-기프트-식물-직감',43),
 'gift/메이저-기프트-꿈의-전조':(99,'gift/마이너-기프트-드림-마스터리',97),
 'gift/메이저-기프트-접속-시각화':(164,'gift/마이너-기프트-사보타지-직감',161),
}
RANK_ONE={ADVANCED.ANCIENT_WISDOM:3,ADVANCED.PARAGON:5}
IN_MY_NAME='feat/나의-이름으로'
SIGNER='supp-blessings/계약자'
# supp-blessings:821 prints Intimidate twice; retain both red and blue.
SHARDS=ADVANCED.SHARDS
INSIGHT='gift/위대한-존재의-통찰력'
# Exact CSV granting domains; these do not impose a continuing patron relation.
GRANTING_PATRONS={
 'gift/마이너-기프트-재앙-탐지':(21,('세레비',)),
 'gift/마이너-기프트-조심스런-수면':(27,('지라치',)),
 'gift/메이저-기프트-진실의-눈':(28,('지라치',)),
 'gift/마이너-기프트-로얄-하트':(30,('라티아스', '라티오스')),
 'gift/마이너-기프트-지식의-샘':(36,('유크시',)),
 'gift/마이너-기프트-식물-직감':(43,('쉐이미',)),
 'gift/메이저-기프트-순수-호흡':(44,('쉐이미',)),
 'gift/마이너-기프트-정의의-영혼':(46,('코바르온', '테라키온', '비리디온', '케르디오')),
 'gift/마이너-기프트-구름-읽기':(49,('토네로스', '랜드로스', '볼트로스')),
 'gift/마이너-기프트-눈부신-무대':(52,('메로엣타',)),
 'gift/마이너-기프트-왕족의-특권':(55,('디안시',)),
 'gift/마이너-기프트-자애로운-연민':(58,('뮤',)),
 'gift/마이너-기프트-완벽한-타이밍':(86,('디아루가',)),
 'gift/마이너-기프트-공간인식':(89,('펄기아',)),
 'gift/마이너-기프트-데스-센스':(93,('기라티나',)),
 'gift/마이너-기프트-드림-마스터리':(97,('크레세리아', '다크라이')),
 'gift/마이너-기프트-벌컨의-직감':(104,('히드런',)),
 'gift/마이너-기프트-창조주의-손':(109,('레지기가스',)),
 'gift/마이너-기프트-진실된-영웅':(120,('레시라무',)),
 'gift/마이너-기프트-이상적-영웅':(124,('제크로무',)),
 'gift/마이너-기프트-균형의-영웅':(128,('큐레무',)),
 'gift/마이너-기프트-세계뱀의-포옹':(142,('지가르데',)),
 'gift/마이너-기프트-외계인-얼굴':(151,('미싱노 (코즈믹 호러)',)),
 'gift/마이너-기프트-이단자-탐지':(156,('미싱노 (타락한 창조주)',)),
 'gift/마이너-기프트-사보타지-직감':(161,('미싱노 (네트워크 보안의 새로운 신)',)),
 'gift/메이저-기프트-접속-시각화':(164,('미싱노 (네트워크 보안의 새로운 신)',)),
}


def _text(value,label):
 if not isinstance(value,str) or not value.strip():raise ValueError('nonempty '+label+' required')
 return value


def _selected(e,gift):
 source=SOURCES[gift]
 if e.r._selected_rule(source)!=source:raise ValueError('selected Minor Gift source requires its own policy')
 return source


def _actual(e,actor):
 if actor.r is not e.r or actor.kind!='trainer':raise ValueError('actual trainer in this rule context required')
 uid=_text(actor.spec.get('id'),'trainer identity')
 actors=[*getattr(e,'everyone',[]),*getattr(e,'_time_actors',[]),*getattr(e.gm,'everyone',[])]
 matches={id(a):a for a in actors if a.spec.get('id')==uid}
 if len(matches)!=1 or next(iter(matches.values())) is not actor:raise ValueError('unique registered trainer identity required')
 return uid


def acquired(actor,gift):
 values=actor.spec.get('gifts',[])
 if not isinstance(values,(list,tuple)):raise ValueError('actual acquired Gift list required')
 aliases={S.key(gift),S.key(gift.split('/')[-1])}
 count=sum(S.key(x) in aliases for x in values)
 if count>1:raise ValueError('duplicate Gift aliases are not extra acquisitions')
 return count==1


def _source(actor,source,*,record=None):
 selected=actor.r.select_source_definition(source)
 if selected['selected_id']!=source:raise ValueError('exact prerequisite source required: '+source)
 origin=selected['source']
 if record is not None and (origin.get('file')!=CSV_SOURCE or origin.get('record_span')!=[record,record]):
  raise ValueError('exact CSV Blessing prerequisite source required: '+source)
 return deepcopy(origin)


def _qualification(actor,gift,configuration=None,*,stored=None):
 """Keep acquisition facts; later loss is not an invented retention rule."""
 if gift in ('gift/축복받은-회복력','gift/위대한-존재의-통찰력'):
  import native_acquisition_adapters as NATIVE
  native=NATIVE.blessing_qualification(actor,gift,stored=stored)
  if native is not None:return native
 if gift not in PREREQUISITES and gift not in RANK_ONE:return None
 own_record=PREREQUISITES[gift][0] if gift in PREREQUISITES else RANK_ONE[gift]
 own_source=_source(actor,gift,record=own_record)
 role=configuration.get('role') if isinstance(configuration,dict) else None
 if gift in PREREQUISITES:
  role=None
  _,required,record=PREREQUISITES[gift]
  source=_source(actor,required,record=record)
  if stored is None:
   count=int(acquired(actor,required))
   # R7 ownership is explicit existing sheet state; its unfinished move effect
   # is neither granted nor certified by confirming the dependent R10.
   approved=approval(actor,required) if count and required in SOURCES else None
  else:count=stored.get('count');approved=stored.get('approved')
  rank=None;maximum=1
  permitted_approval=True if required in SOURCES else None
 else:
  if role not in ('messiah','contractor'):raise ValueError('actual Blessing acquisition role required')
  required=IN_MY_NAME if role=='messiah' else SIGNER
  source=_source(actor,required)
  if source.get('file')!='supp-blessings.md' or source.get('lines')!=([282,283] if role=='messiah' else [248,270]):
   raise ValueError('reviewed rank-one Blessing prerequisite source required')
  if stored is None:
   count=ACQUIRED.owned_rule_count(actor,required)
   rank=ACQUIRED.feature_rank(actor,required) if count and role=='messiah' else None
  else:count=stored.get('count');rank=stored.get('rank')
  approved=None;permitted_approval=None;maximum=4 if role=='messiah' else 1
 if type(count) is not int or (rank is not None and type(rank) is not int):
  raise ValueError('whole actual prerequisite ownership and rank required')
 if gift in RANK_ONE and role=='messiah' and rank!=count:
  raise ValueError('actual acquired prerequisite rank required: '+required)
 if (gift not in RANK_ONE or role=='contractor') and rank is not None:
  raise ValueError('unexpected prerequisite rank')
 result=QUALIFICATION.require(gift,'native','acquisition',[
  QUALIFICATION.check('owned','prerequisite',1<=count<=maximum,'actual Blessing prerequisite required: '+required),
  QUALIFICATION.check('approval','prerequisite',approved is permitted_approval,'actual approved Blessing prerequisite required: '+required)])
 record={'schema':1,'clause_id':'C2CSV/input/db/class-data.csv:R'+str(own_record)+':blessing',
  'gift_source':own_source,'required':required,'source':source,'role':role,
  'count':count,'rank':rank,'approved':approved,'qualification':result}
 if stored is not None and stored!=record:raise ValueError('Blessing acquisition prerequisite snapshot changed')
 return record


def _approval_header(actor,gift,record):
 uid=_text(actor.spec.get('id'),'trainer identity');source=SOURCES[gift]
 if not isinstance(record,dict) or record.get('actor_id')!=uid or record.get('gift')!=gift or record.get('source')!=source or record.get('gm_approved') is not True:
  raise ValueError('named Gift requires recorded actual GM permission')
 _text(record.get('reason'),'GM permission reason')


def _patron_fact(e,value):
 if value is None:return {'kind':'historical_unknown','value':None,'species':None}
 _text(value,'granting patron')
 import world_entities as WORLD
 patron=WORLD.actor_index(e).get(value)
 if patron is not None:
  if patron.kind!='pokemon':raise ValueError('granting patron actor must be a Pokemon')
  species=e.r.species.get(patron.spec.get('species'),{}).get('name')
  _text(species,'actual granting patron species')
  if species=='미싱노':
   aspect=patron.spec.get('gift_patron_aspect')
   if aspect is not None:species+=' ('+_text(aspect,'MissingNo granting aspect')+')'
  return {'kind':'actor','value':value,'species':species}
 from builder import species_lookup
 try:species=species_lookup(e.r,value)['name']
 except KeyError:
  if value.startswith('미싱노'):species=value
  else:return {'kind':'historical_unknown','value':value,'species':None}
 return {'kind':'declared_species','value':value,'species':species}


def _patron_authority(actor,gift,fact,waivers):
 record,allowed=GRANTING_PATRONS[gift]
 source=_source(actor,gift,record=record)
 if not isinstance(fact,dict) or set(fact)!={'kind','value','species'}:
  raise ValueError('exact granting patron fact required')
 if fact['kind']=='historical_unknown':
  if fact['value'] is not None:_text(fact['value'],'historical patron reference')
  if fact['species'] is not None:raise ValueError('unknown historical patron cannot invent provenance')
  passed=None
 elif fact['kind'] in ('actor','declared_species'):
  _text(fact['value'],'granting patron identity');_text(fact['species'],'granting patron species')
  passed=fact['species'] in allowed
 else:raise ValueError('known granting patron evidence kind required')
 result=QUALIFICATION.evaluate(source_id=gift,provider='native',stage='gift_confirmation',
  checks=[QUALIFICATION.check('granting_patron','prerequisite',passed,'granting patron contradicts selected Gift source')],waivers=waivers)
 if result['status']=='denied':raise ValueError('granting patron contradicts selected Gift source')
 return {'schema':1,'gift_source':source,'granting_patron':deepcopy(fact),'waivers':deepcopy(waivers),
  'qualification':result,'history':'GM declared already acquired Gift; granting patron unknown' if passed is None else 'declared granting patron'}


def _sealed(value):
 import resolution_transaction as TX
 return dict(value,sha256=TX.request_fingerprint(value))


def _read_patron_authority(actor,gift,record):
 stored=record.get('patron_authority')
 if not isinstance(stored,dict):raise ValueError('explicit granting patron confirmation required for legacy Gift')
 expected=_sealed(_patron_authority(actor,gift,stored.get('granting_patron'),stored.get('waivers')))
 if stored!=expected:raise ValueError('granting patron receipt or source changed')
 return deepcopy(stored)


def _insight_choice(actor,requested=None):
 choices=actor.spec.get('gift_choices',{})
 if not isinstance(choices,dict):raise ValueError('Gift choices must be a mapping')
 choice=choices.get(INSIGHT) if requested is None else requested
 if not isinstance(choice,dict) or set(choice)!={'role'} or choice['role'] not in ('메시아','계약자'):
  raise ValueError('exact acquired Insight role required')
 return deepcopy(choice)


def _insight_authority(actor,choice):
 return _sealed({'source':_source(actor,INSIGHT,record=11),'configuration':choice,
  'cost_source':_source(actor,SIGNER) if choice['role']=='계약자' else None})


def confirmed_insight_role(actor):
 record=actor.spec.get('_blessing_gift_approvals',{}).get(INSIGHT,{})
 stored=record.get('configuration')
 if not isinstance(stored,dict) or stored!=_insight_choice(actor):
  raise ValueError('Insight acquisition role changed or needs explicit legacy confirmation')
 if record.get('role_authority')!=_insight_authority(actor,stored):
  raise ValueError('Insight confirmed role authority changed')
 return stored['role']


def confirm(e,actor,gift,*,reason,configuration=None):
 """Record GM permission for a declared already-acquired Gift, not new acquisition."""
 if gift not in SOURCES:raise ValueError('supported exact Minor Gift required')
 uid=_actual(e,actor);_text(reason,'GM permission reason');source=_selected(e,gift)
 if not acquired(actor,gift):raise ValueError('actual acquired Gift required before confirmation')
 records=actor.spec.get('_blessing_gift_approvals',{})
 if not isinstance(records,dict):raise ValueError('Gift approvals must be a mapping')
 previous=records.get(gift)
 requalify=isinstance(previous,dict) and (
  gift in (*PREREQUISITES,*RANK_ONE) and 'acquisition' not in previous or
  gift in GRANTING_PATRONS and 'patron_authority' not in previous or
  gift==INSIGHT and 'role_authority' not in previous)
 if gift in records:
  if not requalify:raise ValueError('Gift acquisition permission already recorded')
  _approval_header(actor,gift,previous)
 authority={}
 if isinstance(configuration,dict) and 'authority' in configuration:
  authority=configuration['authority'];configuration={k:v for k,v in configuration.items() if k!='authority'} or None
  if gift not in GRANTING_PATRONS or not isinstance(authority,dict) or set(authority)!={'waivers'}:
   raise ValueError('exact scoped Gift authority waiver declaration required')
 patron=None
 if gift in GRANTING_PATRONS:
  if requalify and 'patron_authority' in previous:
   if authority:raise ValueError('existing granting patron authority must be preserved')
   patron=_read_patron_authority(actor,gift,previous)
  else:
   patrons=actor.spec.get('gift_patrons',{})
   if not isinstance(patrons,dict):raise ValueError('Gift patrons must be a mapping')
   patron=_sealed(_patron_authority(actor,gift,_patron_fact(e,patrons.get(gift)),authority.get('waivers',[])))
 insight=_insight_choice(actor,configuration) if gift==INSIGHT else None
 if gift=='gift/축복받은-회복력':
  import class_passive_combat as PASSIVE
  prepared=None;resilience=PASSIVE.prepare_resilience(e,actor,configuration)
 else:
  prepared=ADVANCED.prepare_configuration(e,actor,gift,None if insight is not None else configuration);resilience=None
 stored=previous.get('acquisition') if requalify else None
 acquisition=_qualification(actor,gift,configuration,stored=stored)
 if requalify and prepared is not None and actor.spec.get(ADVANCED.CONFIGURATION,{}).get(gift)!=prepared:
  raise ValueError('existing Blessing acquisition choices must be preserved during confirmation')
 if requalify and insight is not None and isinstance(previous.get('configuration'),dict) and previous['configuration']!=insight:
  raise ValueError('existing Insight role must be preserved during confirmation')
 if requalify and resilience is not None and previous.get('configuration')!=resilience:
  raise ValueError('existing Blessing acquisition choices must be preserved during confirmation')
 record={'actor_id':uid,'gift':gift,'source':source,'gm_approved':True,'reason':reason}
 if acquisition is not None:record['acquisition']=acquisition
 if patron is not None:record['patron_authority']=patron
 if requalify:record['previous_approval']=deepcopy(previous)
 if insight is not None:
  record['configuration']=insight
  record['role_authority']=_insight_authority(actor,insight)
 if resilience is not None:record['configuration']=resilience
 # Finish every validation before any confirmation or choice is written.
 if not requalify:ADVANCED.store_configuration(actor,prepared)
 if insight is not None:actor.spec.setdefault('gift_choices',{})[gift]=deepcopy(insight)
 if resilience is not None:actor.spec.setdefault('class_passive_choices',{})[gift]=deepcopy(resilience)
 actor.spec.setdefault('_blessing_gift_approvals',{})[gift]=record
 e.gm._rec('마이너 기프트 GM 허가',None,record,reason,actor)
 return deepcopy(record)


def approval(actor,gift):
 """Read the common acquisition receipt from an actor-only state projection."""
 if not acquired(actor,gift):return False
 source=SOURCES[gift]
 if actor.kind!='trainer' or actor.r._selected_rule(source)!=source:
  raise ValueError('selected acquired trainer Gift source required')
 records=actor.spec.get('_blessing_gift_approvals',{})
 if not isinstance(records,dict):raise ValueError('Gift approvals must be a mapping')
 record=records.get(gift)
 _approval_header(actor,gift,record)
 if gift in GRANTING_PATRONS:_read_patron_authority(actor,gift,record)
 if gift==INSIGHT:confirmed_insight_role(actor)
 if gift in (*PREREQUISITES,*RANK_ONE):
  acquisition=record.get('acquisition')
  if not isinstance(acquisition,dict):raise ValueError('actual acquisition prerequisite confirmation required: '+gift)
  configuration=None
  if gift in RANK_ONE:
   configurations=actor.spec.get(ADVANCED.CONFIGURATION,{})
   if not isinstance(configurations,dict) or not isinstance(configurations.get(gift),dict):raise ValueError('actual Blessing acquisition configuration required')
   configuration=configurations[gift].get('values')
  _qualification(actor,gift,configuration,stored=acquisition)
 return True


def require(e,actor,gift):
 if not acquired(actor,gift):return False
 _actual(e,actor)
 return approval(actor,gift)


def validate_sleep_check(e,actor,skill,context=None):
 if '잠듦' not in actor.conditions:return
 context=ADVANCED.shared_context(context)
 source='condition/잠듦'
 if e.r._selected_rule(source)!=source:raise ValueError('selected sleep condition needs its own check policy')
 advanced=ADVANCED.validate_sleep_check(e,actor,skill,context)
 if advanced is not None:return advanced
 eligible=isinstance(context,dict) and set(context)=={'purpose','reason'} and context.get('purpose')=='imminent_danger'
 if not eligible or S.skill_id(e.r.skill_policy,skill)!='perception' or not require(e,actor,SLEEP):
  raise ValueError('sleep permits only an acquired Watchful Sleep check for imminent danger')
 _text(context['reason'],'GM imminent danger reason')
 # This neither wakes the actor nor grants a Standard/Shift/Free action.
 return SOURCES[SLEEP]


def shard_item(e,actor,name):
 """Native item registration may equip one actually owned shard as Accessory."""
 advanced=ADVANCED.shard_item(e,actor,name)
 if advanced is not None:return advanced
 names={colour+'조각':colour for colour in SHARDS}
 canonical=name.removeprefix('item/') if isinstance(name,str) else name
 if canonical not in names or not acquired(actor,ROYAL):return None
 require(e,actor,ROYAL)
 return ADVANCED._owned_shard_item(e,actor,canonical)


def _region(e,actor,context):
 # A terrain can establish mountain; forest does not disprove a volcanic region.
 import survivalist_features as SURVIVALIST
 env=SURVIVALIST.current_environment(e,actor)
 mountain=env is not None and 'mountain' in env.get('terrains',())
 declared=context.get('region') if isinstance(context,dict) else None
 purpose=context.get('purpose') if isinstance(context,dict) else None
 legacy={'mountain_region':'mountain','volcanic_region':'volcanic'}.get(purpose)
 if declared is not None:
  ADVANCED.shared_context(context)
  kind=declared['kind']
  if kind=='other' and (mountain or legacy):raise ValueError('explicit region contradicts observed mountain or volcanic region')
  return kind if kind!='other' else None
 if legacy:return legacy
 return 'mountain' if mountain else None


def modifiers(e,actor,skill,context=None):
 owned={gift:require(e,actor,gift) for gift in (STAGE,ROYAL,*PURPOSE_BONUSES,*CONTEXT_RULES) if acquired(actor,gift)}
 if not owned:return twisted_modifiers(e,actor,skill)
 # Preserve both source receipts; the exact CSV consumer owns an aliased effect.
 for supplement,csv in ((STAGE,ADVANCED.DAZZLING_STAGE),(ROYAL,ADVANCED.ROYAL_PRIVILEGE)):
  if owned.get(supplement) and ADVANCED._owned_record(e,actor,csv) is not None:
   owned[supplement]=False
 canonical=S.skill_id(e.r.skill_policy,skill)
 purpose=context.get('purpose') if isinstance(context,dict) else None
 if purpose in PURPOSES:_text(context.get('reason'),'GM check context reason')
 sources=list(twisted_modifiers(e,actor,skill))
 if owned.get(STAGE) and purpose in ('singing','dancing') and canonical in {S.skill_id(e.r.skill_policy,s) for s in SOCIAL}:
  rank=max(S.effective_rank(e.r,actor,s) for s in SOCIAL)
  sources.append((SOURCES[STAGE],M.ratio(rank,2),STAGE+': '+purpose))
 if owned.get(ROYAL):
  shard=ADVANCED._royal_modifier(e,actor,canonical)
  if shard is not None:
   value,colour=shard
   sources.append((SOURCES[ROYAL],value,ROYAL+': '+colour))
 if owned.get(COMPASSION) and owned.get(CSV_COMPASSION):
  raise ValueError('Compassion source representations are not two separate acquisitions')
 for gift,(skills,purposes,bonus) in PURPOSE_BONUSES.items():
  if owned.get(gift) and purpose in purposes and canonical in {S.skill_id(e.r.skill_policy,s) for s in skills}:
   sources.append((SOURCES[gift],bonus,gift+': '+purpose))
 for gift,row in CONTEXT_RULES.items():
  if not owned.get(gift):continue
  scoped={S.skill_id(e.r.skill_policy,s) for s in row['skills']}
  always={S.skill_id(e.r.skill_policy,s) for s in row['always_skills']}
  region=_region(e,actor,context) if row.get('regions') and canonical in scoped else None
  eligible=canonical in always or (region in row['regions'] if row.get('regions') else purpose in row['purposes']) and (not scoped or canonical in scoped)
  if eligible:
   detail=region or ('all '+skill if canonical in always and purpose not in row['purposes'] else purpose)
   sources.append((gift,row['bonus'],row['clause_id']+': '+str(detail)))
 return tuple(sources)


def _branded(actor):
 values=actor.spec.get('feats',[])
 if not isinstance(values,(list,tuple)):raise ValueError('actual acquired Feature list required')
 aliases={S.key(x) for x in (BRANDED,'시종','Branded')}
 count=sum(S.key(x) in aliases for x in values)
 if count!=1:raise ValueError('one actual Branded Feature required')
 for source in (BRAND_SOURCE,TWISTED):
  if actor.r._selected_rule(source)!=source:raise ValueError('selected Brand source needs its own policy')


def _twisted_record(actor):
 if not acquired(actor,TWISTED):return None
 if actor.kind!='trainer':raise ValueError('Twisted Form requires a trainer')
 _branded(actor)
 record=actor.spec.get('_twisted_form')
 if not isinstance(record,dict) or record.get('actor_id')!=actor.spec.get('id') or record.get('source')!=TWISTED or record.get('parent_source')!=BRAND_SOURCE or record.get('gm_approved') is not True:
  raise ValueError('Twisted Form needs the recorded actual branded contract')
 for field in ('brander_id','appearance','contract','reason'):_text(record.get(field),field)
 values=record.get('granted_types')
 basic=set(actor.r.mech('combat/type-chart')['attack_vs_defense'])-{'에러','None'}
 if not isinstance(values,(list,tuple)) or not values or len(values)!=len(set(values)) or any(v not in basic for v in values):
  raise ValueError('actual elemental typing at the branded acquisition required')
 return record


def confirm_twisted_form(e,actor,brander,*,appearance,contract,reason):
 """Record this acquired Brand, its supernatural contract and actual type grant.

 The grant is the typing held by the real brander at acquisition, not a live
 remote-copy link to future battle transformations. No new Feature is granted.
 """
 uid=_actual(e,actor)
 if not acquired(actor,TWISTED):raise ValueError('actual acquired Twisted Form required')
 _branded(actor)
 for name,value in [('appearance',appearance),('contract',contract),('reason',reason)]:_text(value,name)
 if actor.spec.get('_twisted_form') is not None:raise ValueError('Branded acquisition already recorded; no free reselection')
 if brander is actor or brander.r is not e.r:raise ValueError('distinct actual supernatural brander required')
 bid=_text(brander.spec.get('id'),'brander identity')
 actors=[*getattr(e,'everyone',[]),*getattr(e,'_time_actors',[]),*getattr(e.gm,'everyone',[])]
 matches={id(a):a for a in actors if a.spec.get('id')==bid}
 if len(matches)!=1 or next(iter(matches.values())) is not brander:raise ValueError('unique registered brander required')
 values=list(brander.types)
 basic=set(e.r.mech('combat/type-chart')['attack_vs_defense'])-{'에러','None'}
 if not values or len(values)!=len(set(values)) or any(v not in basic for v in values):raise ValueError('actual brander elemental types required')
 record={'actor_id':uid,'brander_id':bid,'source':TWISTED,'parent_source':BRAND_SOURCE,
  'gm_approved':True,'granted_types':values,'appearance':appearance,'contract':contract,'reason':reason}
 actor.spec['_twisted_form']=record
 e.gm._rec('트위스트 폼 계약·외형·타입',None,record,reason,actor)
 return deepcopy(record)


def actual_types(actor,base_types):
 """Read-only native type projection. The backing list contains no Gift grant."""
 record=_twisted_record(actor)
 if record is None:return base_types
 return list(dict.fromkeys([*base_types,*record['granted_types']]))


def twisted_modifiers(e,actor,skill):
 record=_twisted_record(actor)
 if record is None:return ()
 _actual(e,actor)
 canonical=S.skill_id(e.r.skill_policy,skill)
 values={S.skill_id(e.r.skill_policy,k):v for k,v in [('협박',4),('매력',-4),('교활',-4)]}
 return ((TWISTED,values[canonical],record['appearance']),) if canonical in values else ()

