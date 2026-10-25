"""Source-bound Hobbyist acquisition adapter over native receipts and grants."""
from copy import deepcopy
from contextvars import ContextVar
import acquisition_qualification as Q
import skill_modifiers as S

CLASS='class/하비스트';DILETTANTE='feat/딜레당트';DABBLER='feat/애호가';LOOK='feat/보고-배우기'
FEATURES={CLASS:(555,555),DILETTANTE:(558,565),DABBLER:(567,574),LOOK:(576,599)}
BOOK='a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'
GENERAL='b94e43349794836391501f9aac10009d20746bf946ea0c4b5ff3adf85e982d23'
CSV_SHA='4435ff1c462a211564c85d2c1c9a2ac6e7c790c7545e1ad7056d32888b2367bd'
SKILLS=('general education','perception')  # 통찰 is Perception, not 직감/Intuition.
RANK_EDGES={'edge/기본-스킬':(0,1,3),'edge/숙련-스킬':(2,3,4),'edge/전문-스킬':(6,4,5),'edge/달인-스킬':(12,5,6)}
SKILL_EDGES=(*RANK_EDGES,'edge/고난이도-스킬','edge/단정적인-경향','edge/스킬-향상','edge/거장')
EDGE_SKILLS={
 'edge/곡예사':(('곡예',3),),'edge/규토리-볼':(('생존',3),('기술학',4)),
 'edge/몬스터볼':(('기술학',3),),'edge/기본-요리':(('직감',3),),'edge/기본-무술':(('전투',3),),
 'edge/비스트-마스터':(('협박',3),),'edge/브리더':(('포켓몬학',3),),'edge/패기':(('교활',3),),
 'edge/보석-지식':(('오컬트학',3),),'edge/우아함':tuple((s,3) for s in ('매력','명령','교활','협박','직감')),
 'edge/원예가':(('일반 지식',3),('생존',3)),'edge/미용사':(('포켓몬학',3),),
 'edge/타고난-적성':(('직감',4),),'edge/설명':(('일반 지식',3),),'edge/협박하는-존재':(('협박',3),),
 'edge/강철의-정신':(('집중',3),),'edge/메딕-훈련':(('의학',3),),'edge/탑승-기량':(('곡예',3),('육상',3)),
 'edge/스프레이-제작자':(('의학',3),('기술학',3)),'edge/약삭빠름':(('은신',3),),
 'edge/수영-선수':(('육상',3),('생존',3)),'edge/예비-훈련':(('명령',3),)}
CORE_EDGE_SKILLS={**EDGE_SKILLS,
 'edge/부적-제작자':(('오컬트학',3),),'edge/고생물학자':(('포켓몬학',3),('생존',3)),
 'edge/챔피언-트레이너':(('명령',5),),'edge/육상-이니셔티브':(('육상',4),),
 'edge/나쁜-분위기':(('협박',5),),'edge/호감인':(('매력',3),),'edge/신뢰있는-아티스트':(('교활',3),),
 'edge/사기저하':(('협박',4),),'edge/전문적인-조종자':(('교활',4),),'edge/전문-트릭스터':(('은신',4),),
 'edge/번뜩이는-카리스마':(('매력',4),('교활',4)),'edge/킵업':(('곡예',5),),'edge/리더':(('명령',4),),
 'edge/날렵한-움직임':(('곡예',4),('은신',4)),'edge/원만함':(('매력',5),('집중',5)),
 'edge/스닉-트릭':(('은신',4),),'edge/스테미너':(('육상',5),('전투',5)),
 'edge/서바이벌-드라이브':(('생존',4),),'edge/투척-마스터리':(('곡예',4),),'edge/분발':(('집중',4),),
 'edge/은신-아츠':(('은신',5),),'edge/신비한-감각':(('직감',3),),
 'edge/포켓몬-심리학자':(('포켓몬학',3),('일반 지식',3)),'edge/파워-부스트':(('육상',5),),
 'edge/학자':(('일반 지식',5),),'edge/여행자':(('생존',3),),'edge/벽달리기':(('곡예',5),),
 'edge/몬스터볼-수리':(),'edge/기본-사이오닉':(),'edge/선택한-무기':(),'edge/원소-교감':()}
GENERAL_FEATURES={
 'feat/융통-명령':(637,641),'feat/지휘관의-목소리':(720,724),'feat/디펜더':(831,835),
 'feat/뛰어들기':(837,842),'feat/응급-처치-전문지식':(879,884),'feat/내가-도와줄게':(886,890),
 'feat/몬스터볼-장인':(892,895),'feat/포켓몬매니아':(897,901),'feat/압박':(643,647),
 'feat/퀵-스위치':(649,653),'feat/팔방미인':(909,913),'feat/종의-학자':(655,659),
 'feat/개인-지도':(661,666),'feat/기분전환':(869,873),'feat/민첩성-훈련':(696,700),
 'feat/잔혹성-훈련':(702,706),'feat/집중성-훈련':(708,712),'feat/영감성-훈련':(714,718)}
FEATURE_PARENTS={'feat/응급-처치-전문지식':('edge/메딕-훈련',),'feat/몬스터볼-장인':('edge/몬스터볼','edge/몬스터볼-수리')}
NEW_GENERAL_SKILLS={'feat/디펜더':(('육상',4),),'feat/뛰어들기':(('곡예',4),),
 'feat/응급-처치-전문지식':(('의학',5),),'feat/내가-도와줄게':(),
 'feat/몬스터볼-장인':(('기술학',5),),'feat/포켓몬매니아':(('포켓몬학',4),),'feat/팔방미인':()}
SCENE={'feat/결정적인-순간':'feat/지휘관의-목소리','feat/포획-테크닉':'feat/몬스터볼-장인',
 'feat/지구력':'edge/메딕-훈련','feat/술책':'feat/융통-명령','feat/화학전':'edge/스프레이-제작자','feat/깡다구':'feat/디펜더'}
AP_FEATURES={'feat/뉘앙스-공연':'edge/우아함','feat/왕복-여행':'feat/퀵-스위치','feat/이-맛이야':'edge/기본-요리',
 'feat/스타일은-영원하다':'edge/미용사','feat/코칭':'edge/수영-선수','feat/빠른-체조':'edge/곡예사'}
STATIC_DEFINITIONS={uid:{'clause_id':uid,'span':list(span),'catalog_span':list(span),'class_template':CLASS,
 'minimum_level':0,'skill':None,'ranked':uid==DILETTANTE,'max_rank':4,
 'source':{'file':'input/ch04-trainer-classes.md','sha256':BOOK}} for uid,span in FEATURES.items()}
STATIC_DEFINITIONS[CLASS]['catalog_span']=[538,538]
CHILD_KEY='hobbyist_provider'
_PAIR_IN_PROGRESS=ContextVar('hobbyist_actual_pair_in_progress',default=None)
_LEARNING_IN_PROGRESS=ContextVar('hobbyist_actual_learning_in_progress',default=None)


def source(rules,feature,edition,rank=None):
 import source_context as C
 if feature not in FEATURES or edition not in ('core','official_errata','local_csv'):raise ValueError('actual Core, official Hobbyist errata or retained CSV edition required')
 if rules._selected_rule(feature)!=feature:raise ValueError('selected Hobbyist definition required')
 C.verified_source(rules,{'file':'input/ch04-trainer-classes.md','sha256':BOOK},label='Hobbyist')
 result={'edition':edition,'feature':feature,'file':'input/ch04-trainer-classes.md','sha256':BOOK,'span':list(FEATURES[feature])}
 if edition=='official_errata':
  if feature!=CLASS:raise ValueError('official errata changes only the basic Hobbyist grant')
  authority={'file':'input/supp-errata.md','sha256':'90e533bde766c6ffe8fb480dd8e2478e5fddf3ed1fef9a7a1032070245622a3e'}
  C.verified_source(rules,authority,label='actual Hobbyist errata');result.update(authority,span=[446,446])
 if edition=='local_csv':
  C.verified_source(rules,{'file':'input/db/feats.csv','sha256':CSV_SHA},label='Hobbyist CSV')
  if feature==DILETTANTE and (type(rank)is not int or not 1<=rank<=4):raise ValueError('actual selected CSV Dilettante rank required')
  result.update(file='input/db/feats.csv',sha256=CSV_SHA,record=97 if feature==CLASS else 97+rank if feature==DILETTANTE else 102 if feature==DABBLER else 103,span=None)
 return result


def records(actor,feature=None,*,active=True):
 import trainer_feature_acquisition as T
 return [record for _,record in T.static_family_acquisitions(actor,FEATURES,feature,active=active)]


def acquired(actor,feature):
 rows=records(actor,feature)
 return rows[-1] if rows else None


def owned(actor,uid):return __import__('acquired_features').owned_rule_count(actor,uid)
def source_id(actor,feature,rank=None):return 'feature:'+actor.entity_id+':'+feature+(':rank:'+str(rank) if rank else '')


def acquisition_snapshot(engine,actor,feature,rank=None,selection=None):
 if type(selection)is not dict:raise ValueError('explicit immutable Hobbyist choices required')
 selection=deepcopy(selection);expected={'edition','edges'} if feature==CLASS else {'edition','edge','feature'} if feature==DILETTANTE else {'edition'}
 if set(selection)!=expected:raise ValueError('exact Hobbyist acquisition choices required')
 selected=source(engine.r,feature,selection['edition'],rank)
 if feature==DILETTANTE:
  if type(rank)is not int or not 1<=rank<=4:raise ValueError('Dilettante has exactly four ranks')
  for key,domain in (('edge',EDGE_SKILLS),('feature',GENERAL_FEATURES)):
   child=selection[key]
   if type(child)is not dict or set(child)!={'id','options','substitute'} or child['id'] not in domain or type(child['options'])is not dict:raise ValueError('one printed Dilettante Edge and General Feature pair required')
   if S.skill_id(engine.r.skill_policy,child['substitute'],required=True) not in SKILLS:raise ValueError('Dilettante substitutes only General Education or Perception (통찰)')
 elif rank is not None:raise ValueError('only Dilettante is Ranked')
 if feature==CLASS:
  if type(selection['edges'])is not list or len(selection['edges'])!=3:raise ValueError('Hobbyist grants exactly three qualified Skill Edges')
  for choice in selection['edges']:
   if type(choice)is not dict or set(choice)!={'id','choice'} or choice['id'] not in SKILL_EDGES:raise ValueError('actual Skill Edge selection required')
   if selection['edition']=='official_errata' and choice['id'] not in RANK_EDGES:raise ValueError('Hobbyist errata grants only rank-increasing Skill Edges')
 return {'skills':{s:S.rank(engine.r,actor,s)[2] for s in SKILLS},'parent':None if feature==CLASS else (acquired(actor,CLASS) or {}).get('request_id'),
         'rank_number':rank,'selection':selection,'source':selected}


def qualification(actor,feature,snapshot,prerequisite_source):
 if prerequisite_source is not None or type(snapshot)is not dict or set(snapshot)!={'skills','parent','rank_number','selection','source'}:raise ValueError('exact Hobbyist acquisition observations required')
 if set(snapshot['skills'])!=set(SKILLS) or any(type(v)is not int or v<1 for v in snapshot['skills'].values()):raise ValueError('actual declared Hobbyist skill ranks required')
 if snapshot['source']!=source(actor.r,feature,snapshot['selection']['edition'],snapshot['rank_number']):raise ValueError('Hobbyist immutable source changed')
 parent=snapshot['parent']
 if feature!=CLASS and not any(r['request_id']==parent for r in records(actor,CLASS,active=False)):raise ValueError('actual acquired Hobbyist parent receipt required')
 ranks=snapshot['skills'].values()
 checks=[Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),
  Q.check('skills','prerequisite',all(v>=3 for v in ranks) if feature==CLASS else True if feature==DILETTANTE else max(ranks)>=5,'Novice General Education and Perception, or Expert General Education/Perception required'),
  Q.check('parent','prerequisite',feature==CLASS or parent is not None,'actual Hobbyist parent required')]
 if feature==DILETTANTE:checks.append(Q.rank_limit('rank',snapshot['rank_number'],1,4,'Dilettante has exactly four ranks'))
 return Q.require(feature,actor.entity_id,'acquire',checks)


def acquire(engine,actor,feature=CLASS,*,request_id,selection,rank=None):
 return __import__('trainer_feature_acquisition').acquire_static(engine,actor,feature,acquisition_request_id=request_id,selection=selection,rank=rank)


def after_acquire(engine,actor,feature,sid):
 parent=acquired(actor,feature)
 if parent is None:raise ValueError('actual Hobbyist acquisition receipt required')
 if feature==CLASS:
  for i,choice in enumerate(parent['snapshot']['selection']['edges']):acquire_skill_edge(engine,actor,choice['id'],choice['choice'],sid+'/skill/'+str(i),sid)
 elif feature==DILETTANTE:
  # Native selection owners validate during the enclosing atomic pair commit.
  # Defer only this exact already-receipted pair's completeness, not qualification.
  token=_PAIR_IN_PROGRESS.set((actor.entity_id,parent['request_id'],parent['integrity']))
  try:
   for slot in ('edge','feature'):
    choice=parent['snapshot']['selection'][slot]
    acquire_child(engine,actor,parent,choice['id'],choice['options'],choice['substitute'],kind='dilettante',request_id=parent['request_id']+'/'+slot)
  finally:_PAIR_IN_PROGRESS.reset(token)
  validate_actor(actor)


def counts_as_general(rules,feature):
 if feature!=CLASS:return False
 source(rules,CLASS,'core');return True


def acquire_skill_edge(engine,actor,edge,choice,sid,parent_source):
 import state_grants as G
 if edge not in SKILL_EDGES or engine.r._selected_rule(edge)!=edge:raise ValueError('actual selected Skill Edge required')
 if edge in RANK_EDGES:
  import capture_techniques as C
  skill=S.skill_id(engine.r.skill_policy,choice,required=True)
  proof=C._skill_edge(engine.r,{'edge':edge,'skill':skill},actor.level,S.rank(engine.r,actor,skill)[2])
  payload={'kind':'rank','proof':proof}
  C.grant_skill_edge(engine,actor,proof,sid,hobbyist_skill_edge=payload,hobbyist_parent_source=parent_source)
  return deepcopy(payload)
 else:
  payload={'kind':'choice','choice':deepcopy(choice)}
  if edge=='edge/단정적인-경향' and (choice not in ('body','mind','spirit') or owned(actor,edge)):raise ValueError('one actual body, mind or spirit Categoric Inclination required')
  if edge=='edge/스킬-향상' and (type(choice)is not list or len(choice)!=2 or len({S.skill_id(engine.r.skill_policy,s,required=True) for s in choice})!=2):raise ValueError('Skill Enhancement needs two distinct skills')
  if edge=='edge/거장' and (actor.level<20 or S.rank(engine.r,actor,choice)[2]<6):raise ValueError('Virtuoso requires level20 and Master selected skill')
  if edge=='edge/고난이도-스킬' and (type(choice)is not dict or set(choice)!={'choice_id','skill','use','reason','approved'} or choice['approved'] is not True or S.rank(engine.r,actor,choice['skill'])[2]<3):raise ValueError('actual GM approved Novice Skill Stunt required')
 G._source(actor,sid,'feature',rule_id=edge,owner_id=actor.entity_id,lifetime='while_owned',tutor_points=0,hobbyist_skill_edge=payload,hobbyist_parent_source=parent_source)
 actor.spec.setdefault('edges',[]).append(edge)
 if edge=='edge/고난이도-스킬':__import__('skill_stunts').approve(engine,actor,**choice)
 elif edge not in RANK_EDGES:
  mapping=actor.spec.setdefault('edge_choices',{})
  if edge in ('edge/스킬-향상','edge/거장'):mapping.setdefault(edge,[]).append(deepcopy(choice))
  else:mapping[edge]=deepcopy(choice)
 __import__('acquisition_withdrawal').dependencies(engine,actor,sid,[parent_source])
 return deepcopy(payload)


def _seal(label,value):return __import__('trainer_feature_acquisition')._digest(label,value)


def _provider_rows(actor,active=True):
 state=actor.spec.get('state_grants',{})
 rows=[(sid,row,True) for sid,row in state.get('sources',{}).items()]
 if not active:rows.extend((e['source_id'],e['record'],False) for e in state.get('ended_sources',[]))
 return [(sid,row[CHILD_KEY],live) for sid,row,live in rows if CHILD_KEY in row]


def validate_provider(actor,row,active):
 if type(row)is not dict or set(row)!={'parent','provider','child','kind','substitute','options','prerequisite','prerequisite_count','integrity'} or row.get('integrity')!=_seal('hobbyist/provider/v1',{k:v for k,v in row.items() if k!='integrity'}):raise ValueError('Hobbyist provider integrity changed')
 parent=next((r for r in records(actor,active=False) if r['request_id']==row['parent']),None)
 if parent is None or parent['feature_id']!=row['provider']:raise ValueError('actual acquired Hobbyist provider receipt required')
 child=row['child']
 if row['kind']=='dilettante':
  slot='edge' if child.startswith('edge/') else 'feature'
  chosen=parent['snapshot']['selection'].get(slot)
  if parent['feature_id']!=DILETTANTE or chosen!={'id':child,'options':row['options'],'substitute':row['substitute']}:raise ValueError('Dilettante provider must name its actual immutable child selection')
 elif row['kind']=='look_and_learn':
  if parent['feature_id']!=LOOK or child not in {**SCENE,**AP_FEATURES} or row['substitute'] is not None:raise ValueError('actual Look and Learn child selection required')
  if row['prerequisite']!={**SCENE,**AP_FEATURES}[child] or row['prerequisite_count']!=1:raise ValueError('actual printed Look and Learn prerequisite required')
 else:raise ValueError('reviewed Hobbyist provider kind required')
 if active and not any(r['request_id']==row['parent'] for r in records(actor)):raise ValueError('Hobbyist child requires its still-acquired actual provider')
 return parent


def provider(actor,feature):
 rows=[(sid,row) for sid,row,_ in _provider_rows(actor) if row['child']==feature]
 if len(rows)>1:raise ValueError('one actual Hobbyist child source required')
 if rows:validate_provider(actor,rows[0][1],True)
 return rows[0] if rows else None


def skill_waived(actor,feature):
 found=provider(actor,feature)
 return found is not None and found[1]['kind']=='dilettante'


def waives_printed_skill(actor,feature,skill,minimum):
 """Only a listed child's printed skill prerequisite, never an arbitrary node."""
 printed=EDGE_SKILLS.get(feature,NEW_GENERAL_SKILLS.get(feature,()))
 return skill_waived(actor,feature) and (S.skill_id(actor.r.skill_policy,skill,required=True),minimum) in {(S.skill_id(actor.r.skill_policy,s,required=True),n) for s,n in printed}


DIRECT_SKILLS={
 'edge/비스트-마스터':('협박',),'edge/브리더':('포켓몬학',),'edge/패기':('교활',),
 'edge/우아함':('매력','명령','교활','협박','직감'),'edge/미용사':('일반 지식','포켓몬학'),
 'edge/설명':tuple(S.EDUCATION_SKILLS),'edge/탑승-기량':('곡예','육상'),'edge/약삭빠름':('은신',),
 'edge/수영-선수':('육상','생존'),'edge/예비-훈련':('명령',),'feat/압박':('협박',),
 'feat/포켓몬매니아':('포켓몬학',)}


def direct_skill(actor,feature,skill):
 """Called only where this exact source directly names a rank/check."""
 found=provider(actor,feature)
 if found is None or found[1]['kind']!='dilettante':return skill
 allowed=DIRECT_SKILLS.get(feature,())
 if feature=='feat/내가-도와줄게':allowed=tuple(actor.r.skill_policy['skills'])
 if S.skill_id(actor.r.skill_policy,skill,required=True) not in {S.skill_id(actor.r.skill_policy,s,required=True) for s in allowed}:return skill
 return found[1]['substitute']


def direct_rank(actor,feature,skill,*,effective=True):
 chosen=direct_skill(actor,feature,skill)
 return S.effective_rank(actor.r,actor,chosen) if effective else S.rank(actor.r,actor,chosen)[2]


def _non_skill(engine,actor,feature,options):
 result={'parents':{p:owned(actor,p) for p in FEATURE_PARENTS.get(feature,())}}
 if feature=='feat/지휘관의-목소리':result['orders']=__import__('focused_command').known_orders(actor)
 if feature=='feat/종의-학자':
  import pokemon_activities as P,world_entities as W
  family=options.get('family')
  if type(family)is not str or not family:raise ValueError('Species Savant actual selected evolution family required')
  result['family']=family
  result['pokemon']=[p.entity_id for p in W.actor_index(engine).values() if p.kind=='pokemon' and p.spec.get('trainer_id')==actor.entity_id and P._evolution_family(engine,p.spec.get('species'))==family]
 if feature=='feat/개인-지도':
  selected=options.get('moves')
  known=__import__('move_state').known(engine.r,actor.spec)
  if type(selected)is not list or len(selected)!=3 or len(set(selected))!=3 or not set(selected)<=set(known):raise ValueError('Personal Tutor requires three distinct actually known selected Moves')
  result['moves']=deepcopy(selected)
 return result


def general_snapshot(engine,actor,feature,selection):
 if selection is not None:raise ValueError('this General Feature has no acquisition choice')
 return {'skills':{s:S.rank(engine.r,actor,s)[2] for s in engine.r.skill_policy['skills']},
         'parents':{p:owned(actor,p) for p in FEATURE_PARENTS.get(feature,())}}


def general_qualification(actor,feature,snapshot,prerequisite_source):
 if prerequisite_source is not None or set(snapshot)!={'skills','parents'} or set(snapshot['skills'])!=set(actor.r.skill_policy['skills']) or set(snapshot['parents'])!=set(FEATURE_PARENTS.get(feature,())):raise ValueError('exact General Feature acquisition prerequisites required')
 if any(type(v)is not int or v<1 for v in snapshot['skills'].values()):raise ValueError('actual declared skill ranks required')
 checks=[Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required')]
 checks.extend(Q.check(p,'prerequisite',n==1,'actual General Feature Edge prerequisite required: '+p) for p,n in snapshot['parents'].items())
 skills=NEW_GENERAL_SKILLS[feature]
 passed=not skills or any(snapshot['skills'][S.skill_id(actor.r.skill_policy,s,required=True)]>=n for s,n in skills)
 if feature=='feat/팔방미인':passed=sum(n>=4 for n in snapshot['skills'].values())>=3
 checks.append(Q.check('skills','prerequisite',passed,'printed General Feature skill prerequisites required'))
 return Q.require(feature,actor.entity_id,'acquire',checks)


def child_qualification(actor,feature,snapshot,authority):
 if type(authority)is not dict or set(authority)!={'hobbyist_parent','kind'}:raise ValueError('exact acquired Hobbyist provider authority required')
 facts=snapshot.get('hobbyist_qualification')
 if type(facts)is not dict or set(facts)!={'non_skill','provider'}:raise ValueError('actual Hobbyist child acquisition observations required')
 proof=facts['provider'];parent=validate_provider(actor,proof,False)
 if (proof['parent'],proof['child'],proof['kind'])!=(authority['hobbyist_parent'],feature,authority['kind']):raise ValueError('child qualification belongs to another provider')
 checks=[Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required')]
 if authority['kind']=='dilettante':
  expected=FEATURE_PARENTS.get(feature,())
  if set(facts['non_skill']['parents'])!=set(expected):raise ValueError('all printed non-skill prerequisites must be observed')
  checks.extend(Q.check(p,'prerequisite',facts['non_skill']['parents'][p]==1,'all non-skill Dilettante prerequisites remain required: '+p) for p in expected)
  if feature=='feat/지휘관의-목소리':checks.append(Q.check('orders','prerequisite',len(set(facts['non_skill']['orders']))>=2,'two actually acquired Orders Features required'))
  if feature=='feat/종의-학자':checks.append(Q.check('family','prerequisite',len(set(facts['non_skill']['pokemon']))>=3,'three actually owned Pokemon in selected evolution family required'))
  checks.append(Q.check('skill','prerequisite',False,'printed skill prerequisites only'))
  return Q.evaluate(source_id=feature,provider=parent['request_id'],stage='acquire',checks=checks,waivers=[{
   'source_id':feature,'provider':parent['request_id'],'stage':'acquire','checks':['skill'],'reason':'actual chosen Dilettante rank waives only skill prerequisites'}])
 checks.append(Q.check('printed_parent','prerequisite',proof['prerequisite_count']==1,'actual printed Look and Learn prerequisite required'))
 return Q.require(feature,parent['request_id'],'acquire',checks)


def _child_snapshot(engine,actor,feature,options):
 # Preserve existing consumer snapshots where the consumer reads source choices.
 if feature in __import__('versatility').FEATURES:return __import__('versatility').acquisition_snapshot(engine,actor,feature,options.get('selection'))
 if feature in __import__('focused_command').FEATURES:return __import__('focused_command').acquisition_snapshot(engine,actor,feature)
 if feature==__import__('walk_it_off').FEATURE:return __import__('walk_it_off').acquisition_snapshot(engine,actor,options.get('selection'))
 if feature in __import__('juggler').DEFINITIONS:return __import__('juggler').acquisition_snapshot(engine,actor,feature,None,options.get('selection'))
 if feature in __import__('trickster').FEATURES:return __import__('trickster').acquisition_snapshot(engine,actor,feature,None,options.get('selection'))
 if feature=='feat/뉘앙스-공연':return {'selection':{'source_contract':'core_1.05'},'skills':{},'parents':{}}
 return {'selection':deepcopy(options.get('selection'))}


def acquire_child(engine,actor,parent,feature,options,substitute,*,kind,request_id):
 import state_grants as G,trainer_feature_acquisition as T,acquisition_withdrawal as W
 if type(options)is not dict:raise ValueError('native child acquisition options required')
 domain=EDGE_SKILLS if kind=='dilettante' and feature.startswith('edge/') else GENERAL_FEATURES if kind=='dilettante' else {**SCENE,**AP_FEATURES}
 if feature not in domain:raise ValueError('child outside actual provider domain')
 if provider(actor,feature) is not None or (feature in engine.r.selection.units and owned(actor,feature)):raise ValueError('Hobbyist does not waive child repeat/capacity restrictions')
 prerequisite=None if kind=='dilettante' else domain[feature]
 proof={'parent':parent['request_id'],'provider':parent['feature_id'],'child':feature,'kind':kind,'substitute':substitute,'options':deepcopy(options),
  'prerequisite':prerequisite,'prerequisite_count':0 if prerequisite is None else owned(actor,prerequisite)}
 proof['integrity']=_seal('hobbyist/provider/v1',proof);validate_provider(actor,proof,True)
 sid=source_id(actor,feature);parent_sid=source_id(actor,parent['feature_id'],parent['snapshot']['rank_number'])
 if feature.startswith('edge/'):
  if options:raise ValueError('listed Dilettante Edges have no acquisition choices')
  actor.spec.setdefault('edges',[]).append(feature)
  G._source(actor,sid,'feature',rule_id=feature,owner_id=actor.entity_id,lifetime='while_owned',tutor_points=0,**{CHILD_KEY:proof})
  W.dependencies(engine,actor,sid,[parent_sid])
  __import__('items').register_feats(engine,actor)
  __import__('class_move_grants').register_all(engine,actor)
  return {'source_id':sid,'provider':deepcopy(proof)}
 if feature in ('feat/개인-지도','feat/종의-학자'):
  G._source(actor,sid,'feature',rule_id=feature,owner_id=actor.entity_id,lifetime='while_owned',tutor_points=0,**{CHILD_KEY:proof})
  if feature=='feat/개인-지도':
   if set(options)!={'moves'}:raise ValueError('Personal Tutor needs its actual three-Move selection')
   result=T.acquire_personal_tutor(engine,actor,acquisition_request_id=request_id,selected_values=options['moves'],source_clause_id='C03-127',lifecycle_policy=deepcopy(T.LIFECYCLE_UNRESOLVED))
  else:
   if set(options)!={'selected_species','prerequisite_ids'}:raise ValueError('Species Savant needs its actual selected family and three owned Pokemon')
   result=__import__('class_passive_combat').acquire_species_savant(engine,actor,acquisition_request_id=request_id,**options)
   if not result.get('committed'):raise ValueError('Species Savant actual non-skill qualification is pending')
  W.dependencies(engine,actor,sid,[parent_sid]);return deepcopy(result)
 snapshot=_child_snapshot(engine,actor,feature,options)
 snapshot['hobbyist_qualification']={'non_skill':_non_skill(engine,actor,feature,options),'provider':proof}
 authority={'hobbyist_parent':parent['request_id'],'kind':kind};qualification=child_qualification(actor,feature,snapshot,authority)
 if qualification['status']!='qualified':raise ValueError(next(r['reason'] for r in qualification['checks'] if r['state'] in ('pending','denied')))
 # Capture Techniques is a table right, Chemical Warfare has a field-owned
 # definition. Neither acquires the original Class or a fabricated catalog ID.
 if feature in ('feat/포획-테크닉','feat/화학전'):
  if feature=='feat/포획-테크닉' and options!={'techniques':['거짓 타격','캐치 콤보']}:raise ValueError('Look and Learn grants only False Strike and Catch Combo')
  G._source(actor,sid,'feature',rule_id=LOOK,owner_id=actor.entity_id,lifetime='while_owned',tutor_points=0,**{CHILD_KEY:proof})
  result={'source_id':sid,'provider':deepcopy(proof)}
 else:
  record={'actor_id':actor.entity_id,'feature_id':feature,'source':T._static_source(engine.r,feature),'request_id':request_id,
   'prerequisite_source':authority,'snapshot':snapshot,'qualification':qualification}
  record['integrity']=_seal('trainer-feature/static-acquisition/v1',record)
  actor.spec.setdefault('feats',[]).append(feature)
  G._source(actor,sid,'feature',rule_id=feature,owner_id=actor.entity_id,lifetime='while_owned',tutor_points=0,static_acquisition=record,**{CHILD_KEY:proof})
  after_child(engine,actor,feature,sid,options);result=record
 W.dependencies(engine,actor,sid,[parent_sid])
 return deepcopy(result)


def after_child(engine,actor,feature,sid,options):
 import state_grants as G
 if feature in ('feat/디펜더','feat/기분전환'):G.stat(actor,'hp',1,sid,operation_id='acquisition_stat_tag')
 if feature=='feat/뛰어들기':G.stat(actor,'spe',1,sid,operation_id='acquisition_stat_tag')
 if feature in __import__('juggler').DEFINITIONS:__import__('juggler').after_acquire(engine,actor,feature,sid)
 if feature in __import__('roughneck').FEATURES:__import__('roughneck').after_acquire(engine,actor,feature,sid)
 if feature in __import__('athlete').FEATURES:G.stat(actor,__import__('athlete').STAT_TAG,1,sid,operation_id='acquisition_stat_tag')
 if feature in __import__('tumbler').FEATURES:__import__('tumbler').after_acquire(engine,actor,feature,sid)
 __import__('items').register_feats(engine,actor)


def look_and_learn(engine,actor,feature,*,request_id,seconds=None,reason=None,options=None):
 import state_grants as G,resolution_transaction as TX,turn as TURN,activity_jobs as JOBS
 parent=acquired(actor,LOOK)
 if parent is None:raise ValueError('actual acquired Look and Learn receipt required')
 category='scene' if feature in SCENE else 'ap' if feature in AP_FEATURES else None
 if category is None:raise ValueError('exact printed Look and Learn choice required')
 options={} if options is None else deepcopy(options);edition=parent['snapshot']['selection']['edition']
 if edition!='local_csv' and (type(seconds)is not int or seconds<1 or type(reason)is not str or not reason.strip()):raise ValueError('GM-established Look and Learn Extended duration and reason required')
 if edition=='local_csv' and (seconds is not None or reason is not None):raise ValueError('CSV Look and Learn is Always; do not invent Extended cost')
 intent={'parent':parent['request_id'],'feature':feature,'seconds':seconds,'reason':reason,'options':options}
 replay=TX.replay_result(actor.spec.get('hobbyist_learning_requests',{}),request_id,intent,fingerprint_field='intent')
 if replay is not None:return replay['result']
 if any(r['request']['feature'] in (SCENE if category=='scene' else AP_FEATURES) for r in actor.spec.get('hobbyist_learning_requests',{}).values()):raise ValueError('Look and Learn permits one Scene-list and one AP-list choice, lifetime total two')
 def apply(e,a):
  # Validate and acquire before time; the enclosing native transition rolls
  # everything back if the Extended job or any consumer registration fails.
  token=_LEARNING_IN_PROGRESS.set((a.entity_id,parent['request_id'],parent['integrity'],feature))
  try:result=acquire_child(e,a,parent,feature,options,None,kind='look_and_learn',request_id=request_id+'/learned')
  finally:_LEARNING_IN_PROGRESS.reset(token)
  if edition!='local_csv':
   if e.encounter_active:raise ValueError('Look and Learn Extended learning occurs outside combat')
   if not TURN.spend(e,a,'extended',LOOK):raise ValueError('Look and Learn Extended action permission required')
   JOBS.run_fixed(e,a,(),seconds=seconds,source=LOOK,context={'reason':reason})
  a.spec.setdefault('hobbyist_learning_requests',{})[request_id]={'intent':TX.request_fingerprint(intent),'request':deepcopy(intent),'result':deepcopy(result)}
  __import__('trainer_feature_acquisition').validate_actor(a)
  return result
 return G.transition(engine,actor,apply)


def dabbler_reward(engine,actor,level,*,request_id,edge=None,choice=None,stat=None):
 import trainer_milestone_rewards as M,state_grants as G,resolution_transaction as TX
 parent=acquired(actor,DABBLER)
 if parent is None:raise ValueError('actual acquired Dabbler required')
 M._admit(engine,actor);selected=actor.spec.get(M.KEY,{}).get('choices',{}).get(str(level))
 if type(level)is not int or level not in M.OPTIONS or selected is None:raise ValueError('Dabbler requires an observed and chosen 5/10/20/30/40 milestone')
 if selected['option']=='stats':
  if edge is None or stat is not None:raise ValueError('chosen bonus stats grant one qualified Dabbler Edge')
 elif stat not in ('atk','spa') or edge is not None or choice is not None:raise ValueError('chosen bonus Edge/Feature grants +2 Attack or Special Attack')
 intent={'parent':parent['request_id'],'level':level,'edge':edge,'choice':deepcopy(choice),'stat':stat,'milestone':deepcopy(selected)}
 replay=TX.replay_result(actor.spec.get('hobbyist_dabbler_rewards',{}),request_id,intent,fingerprint_field='intent')
 if replay is not None:return replay['result']
 if any(r['request']['level']==level for r in actor.spec.get('hobbyist_dabbler_rewards',{}).values()):raise ValueError('one Dabbler reward per milestone including retroactive choices')
 def apply(e,a):
  sid=source_id(a,DABBLER)
  if selected['option']=='stats':result=grant_qualified_edge(e,a,edge,choice,sid+'/milestone/'+str(level),sid)
  else:
   G.stat(a,stat,2,sid,operation_id='dabbler_milestone_'+str(level));result={'stat':stat,'delta':2}
  a.spec.setdefault('hobbyist_dabbler_rewards',{})[request_id]={'intent':TX.request_fingerprint(intent),'request':deepcopy(intent),'result':deepcopy(result)}
  validate_actor(a)
  return deepcopy(result)
 return G.transition(engine,actor,apply)


def grant_qualified_edge(engine,actor,edge,choice,sid,parent_sid):
 """Dabbler keeps ordinary qualification; it grants no prerequisite waiver."""
 if edge in SKILL_EDGES:return acquire_skill_edge(engine,actor,edge,choice,sid,parent_sid)
 return __import__('trainer_feature_acquisition').grant_qualified_core_edge(engine,actor,edge,choice,sid,parent_sid)


def validate_actor(actor):
 for sid,proof,live in _provider_rows(actor,False):
  validate_provider(actor,proof,live)
  if live:
   row=actor.spec['state_grants']['sources'][sid]
   if row.get('owner_id')!=actor.entity_id or row.get('lifetime')!='while_owned' or sid!=source_id(actor,proof['child']):raise ValueError('Hobbyist child ownership source changed')
   parent=next((r for r in records(actor,DILETTANTE) if r['request_id']==proof['parent']),None)
   pending=parent is not None and _PAIR_IN_PROGRESS.get()==(actor.entity_id,parent['request_id'],parent['integrity']) and proof['child']==parent['snapshot']['selection']['feature']['id'] and proof['child'] in ('feat/개인-지도','feat/종의-학자')
   if proof['child'] not in ('feat/포획-테크닉','feat/화학전') and not pending and owned(actor,proof['child'])!=1:raise ValueError('one actual acquired Hobbyist child required')
 sources=actor.spec.get('state_grants',{}).get('sources',{})
 for receipt in records(actor,CLASS):
  parent=source_id(actor,CLASS)
  for index,choice in enumerate(receipt['snapshot']['selection']['edges']):
   sid=parent+'/skill/'+str(index);row=sources.get(sid,{})
   grant=row.get('hobbyist_skill_edge',{})
   if row.get('owner_id')!=actor.entity_id or row.get('rule_id')!=choice['id'] or row.get('hobbyist_parent_source')!=parent:raise ValueError('Hobbyist must retain all three actually granted Skill Edge sources')
   if choice['id'] in RANK_EDGES:
    proof=grant.get('proof',{});skill=S.skill_id(actor.r.skill_policy,choice['choice'],required=True)
    expected=__import__('capture_techniques')._skill_edge(actor.r,{'edge':choice['id'],'skill':skill},proof.get('level'),proof.get('before'))
    if proof!=expected or row.get('skill_edge')!=proof or row.get('lifetime')!='permanent' or row.get('grants')!={'edges':[choice['id']]} or row.get('state_change',{}).get('after',{}).get('skills',{}).get(skill)!=proof['after']:raise ValueError('actual native Skill Edge transition evidence changed')
   elif grant!={'kind':'choice','choice':choice['choice']} or row.get('lifetime')!='while_owned':raise ValueError('actual selected Hobbyist Skill Edge choices changed')
 for receipt in records(actor,DILETTANTE):
  if _PAIR_IN_PROGRESS.get()==(actor.entity_id,receipt['request_id'],receipt['integrity']):continue
  for slot in ('edge','feature'):
   child=receipt['snapshot']['selection'][slot]['id'];found=provider(actor,child)
   if found is None or found[1]['parent']!=receipt['request_id']:raise ValueError('each Dilettante rank must retain both actual Edge and Feature acquisitions')
 validate_rewards(actor)
 return True


def validate_rewards(actor):
 import resolution_transaction as TX,trainer_milestone_rewards as M
 sources=actor.spec.get('state_grants',{}).get('sources',{})
 seen=set()
 for request_id,row in actor.spec.get('hobbyist_learning_requests',{}).items():
  if type(request_id)is not str or not request_id.strip() or type(row)is not dict or set(row)!={'intent','request','result'}:raise ValueError('exact actual Look and Learn request required')
  request=row['request']
  if set(request)!={'parent','feature','seconds','reason','options'} or row['intent']!=TX.request_fingerprint(request):raise ValueError('Look and Learn immutable request changed')
  parent=next((r for r in records(actor,LOOK,active=False) if r['request_id']==request['parent']),None)
  child=request['feature'];category='scene' if child in SCENE else 'ap' if child in AP_FEATURES else None
  if parent is None or category is None or category in seen:raise ValueError('one actual acquired choice in each Look and Learn lifetime category required')
  seen.add(category);edition=parent['snapshot']['selection']['edition']
  if edition=='local_csv':
   if request['seconds'] is not None or request['reason'] is not None:raise ValueError('CSV Look and Learn cannot invent Extended costs')
  elif type(request['seconds'])is not int or request['seconds']<1 or type(request['reason'])is not str or not request['reason'].strip():raise ValueError('actual Extended learning observation required')
  child_source=sources.get(source_id(actor,child))
  if child_source is None:child_source=next((r['record'] for r in actor.spec.get('state_grants',{}).get('ended_sources',[]) if r['source_id']==source_id(actor,child)),{})
  proof=child_source.get(CHILD_KEY)
  if proof is None or proof['parent']!=parent['request_id'] or proof['options']!=request['options']:raise ValueError('Look and Learn request must retain its actual acquired child source')
  expected=child_source.get('static_acquisition',{'source_id':source_id(actor,child),'provider':deepcopy(proof)})
  if row['result']!=expected:raise ValueError('Look and Learn result must be its actual native child acquisition receipt')
  if 'static_acquisition' in child_source and expected['request_id']!=request_id+'/learned':raise ValueError('Look and Learn child request identity changed')
 for sid,proof,_ in _provider_rows(actor):
  parent=next((r for r in records(actor,LOOK) if r['request_id']==proof['parent']),None)
  pending=parent is not None and _LEARNING_IN_PROGRESS.get()==(actor.entity_id,parent['request_id'],parent['integrity'],proof['child'])
  if proof['kind']=='look_and_learn' and not pending and not any(row['request']['feature']==proof['child'] and row['request']['parent']==proof['parent'] for row in actor.spec.get('hobbyist_learning_requests',{}).values()):raise ValueError('Look and Learn child requires its actual consumed learning request')
 seen=set()
 for request_id,row in actor.spec.get('hobbyist_dabbler_rewards',{}).items():
  if type(request_id)is not str or not request_id.strip() or type(row)is not dict or set(row)!={'intent','request','result'}:raise ValueError('exact actual Dabbler request required')
  request=row['request']
  if set(request)!={'parent','level','edge','choice','stat','milestone'} or row['intent']!=TX.request_fingerprint(request):raise ValueError('Dabbler immutable request changed')
  level=request['level'];parent=next((r for r in records(actor,DABBLER) if r['request_id']==request['parent']),None)
  chosen=actor.spec.get(M.KEY,{}).get('choices',{}).get(str(level))
  if parent is None or type(level)is not int or level not in M.OPTIONS or level in seen or chosen is None or request['milestone']!=chosen:raise ValueError('one Dabbler reward per actual observed chosen milestone required')
  seen.add(level);sid=source_id(actor,DABBLER)
  if chosen['option']=='stats':
   edge=request['edge'];grant=sources.get(sid+'/milestone/'+str(level),{})
   expected=grant.get('hobbyist_skill_edge',grant.get('core_edge_acquisition'))
   if edge is None or request['stat']is not None or grant.get('rule_id')!=edge or grant.get('hobbyist_parent_source',grant.get('core_edge_acquisition',{}).get('parent_source'))!=sid or row['result']!=expected:raise ValueError('Dabbler bonus Edge must be its actual qualified native grant')
  else:
   stat=request['stat'];operation='dabbler_milestone_'+str(level)
   operations=actor.spec['state_grants'].get('stat_sources',{})
   if request['edge']is not None or request['choice']is not None or stat not in ('atk','spa') or row['result']!={'stat':stat,'delta':2} or operations.get(stat,{}).get('sources',{}).get(sid,{}).get(operation)!={'delta':2,'minimum':None}:raise ValueError('Dabbler +2 must be its real source-owned stat operation')
   if any(operation in operations.get(other,{}).get('sources',{}).get(sid,{}) for other in ('atk','spa') if other!=stat):raise ValueError('one chosen Dabbler +2 stat per milestone required')


def preflight_revoke(actor,removed):
 """The book does not settle withdrawal of already granted rank increases."""
 for sid,row in actor.spec.get('state_grants',{}).get('sources',{}).items():
  if row.get('hobbyist_skill_edge',{}).get('kind')=='rank' and (sid in removed or row['hobbyist_parent_source'] in removed):
   raise ValueError('granted Hobbyist Skill Edge retention/removal requires an explicit reviewed GM withdrawal policy')
