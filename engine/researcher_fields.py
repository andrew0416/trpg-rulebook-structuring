"""PTK ch04:2076-2128 Researcher Fields of Study: Apothecary, Artificer, Botany,
Chemistry, Climatology, Paleontology and Pokemon Caretaking Features.

The class template (researcher_features: acquired field pairs, Pusher/Skill
Trainer pushed skills, Relic Crown) is the owner of field membership. This
module binds each remaining printed Feature to its existing producers and
consumers: crafting recipes, item use, dowsing, moves and attack math, weather
state, teaching/learning, fossil and egg creation, poke-edge teaching and
growth allocation. Features are owned sheet entries (feats list); every use
re-validates the printed prerequisites against the actual sheet.
"""
from copy import deepcopy
from contextvars import ContextVar
from pathlib import Path
import json
import csv
import io
import common_checks as C
import researcher_features as RF
import contest_features as FEATURES
import skill_modifiers as S
import state_grants as G

_data=json.loads((Path(__file__).resolve().parents[1]/'data/researcher-fields-definitions.json').read_text(encoding='utf8'))


def _install_book_prerequisites(policy):
 """Fill only the three published Books prerequisites, never a policy overlay.

 These are executable prerequisite metadata, not copied source prose. Every
 native acquisition/use below verifies the authenticated originals and exact
 CSV records before relying on this adapter. Existing conflicting fields hold.
 """
 additions={
  'reviewed_sources':{
   'core_en':{'file':'source-audit/ptu-core-1.05.pdf','sha256':'e5e0371031601c3ad0a04056771c17599a2d8826e5a5102ccd37f9b368108907'},
   'local_csv':{'file':'input/db/feats.csv','sha256':'4435ff1c462a211564c85d2c1c9a2ac6e7c790c7545e1ad7056d32888b2367bd'},
   'may2015':{'file':'source-audit/official-may2015.pdf','sha256':'b1314908e4adbfee09042c58f08a36046b5f59a09de196425aa469b43232232d'}},
  'csv_records':{'feat/폭넓은-지식':323,'feat/책벌레':324,'feat/이해-완료':325},
  'clauses':{'general':'C04-081'},
  'features':{
   'feat/폭넓은-지식':{'english':'Breadth of Knowledge','field':'general','span':[2071,2073],
       'action':'static','prerequisites':{'skills':[['일반 지식',3]]}},
   'feat/책벌레':{'english':'Bookworm','field':'general','span':[2071,2073],
       'book_source':'may2015','action':'static','prerequisites':{'feats':['feat/폭넓은-지식']}},
   'feat/이해-완료':{'english':'Well Read','field':'general','span':[2071,2073],
       'book_source':'may2015','action':'static','prerequisites':{'feats':['feat/책벌레'],'skills':[['일반 지식',5]]}}}}
 for field,entries in additions.items():
  destination=policy.setdefault(field,{})
  if type(destination)is not dict:raise ValueError('Researcher Books metadata mapping required')
  for key,value in entries.items():
   if key in destination and json.dumps(destination[key],sort_keys=True,ensure_ascii=False,allow_nan=False)!=json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False):
    raise ValueError('reviewed Researcher Books metadata changed: '+field+'/'+key)
   destination.setdefault(key,deepcopy(value))


_install_book_prerequisites(_data)
DEFINITIONS=_data['features'];CLAUSES=_data['clauses'];RANKS=_data['ranks']
SOURCE=_data['rule_source']
assert SOURCE==RF.SOURCE
ENGLISH={d['english']:u for u,d in DEFINITIONS.items()}
KEY='researcher_fields'            # trainer.spec: patches, blends, artificer, chemistry, climatology, uses
APOTHECARY='feat/약사';PATCH='feat/임시-치료';TECHNIQUES='feat/의학-테크닉';BLEND='feat/약-혼합'
CRYSTAL='feat/수정-기능공';RESONANCE='feat/수정-공명';RAINBOW='feat/무지갯빛';FISTFUL='feat/한줌의-힘'
SEED_BAG='feat/씨앗-가방';TOP_TIER='feat/최상급-열매';HERB_LORE='feat/허브-지식'
CHEMIST='feat/화학자';WARFARE='feat/화학전';CAUSTIC='feat/산성-화학반응';PLAYING_GOD='feat/신-놀이'
CLIMATOLOGY='feat/기후학';TEMPERATURE='feat/온도-조절';WEATHER_SYSTEMS='feat/기상-시스템';EXTREME='feat/기상-이변'
FOSSIL_RESTORATION='feat/화석-복원';ANCIENT='feat/고대-유산';GENETIC='feat/유전-기억';BOND='feat/선사의-결속'
PUSHER='feat/후원자';SPECIAL='feat/이건-특별해-난-알아';SKILL_TRAINER='feat/스킬-트레이너';REBALANCE='feat/리밸런스'
PATCH_PREFIX='patch:';BLEND_PREFIX='blend:'
CLIMATOLOGY_PREFIX='researcher-climatology:';SEED_PREFIX='researcher-seed:'
EGG_MARK='researcher_playing_god';FOSSIL_MARK='researcher_fossil_restoration';QUALITY_MARK='researcher_special_quality'
FOSSIL_AUTHORITY='fossil_birth_authority_version'
WEATHER_NAMES={'hail':'싸라기눈','rain':'비','sandstorm':'모래바람','sunny':'쾌청'}


BREADTH='feat/폭넓은-지식';BOOKWORM='feat/책벌레';WELL_READ='feat/이해-완료';ECHOES='feat/미래의-메아리'
LIVE_LEARN='feat/오래-살고-볼일';INSTANT='feat/즉각적인-분석'
WITCH='feat/마녀-사냥꾼';MENTAL='feat/정신-저항'
OVERCLOCK='feat/오버클럭';EFFICIENT='feat/효율-설치'
STATIC_DEFINITIONS={u:{'clause_id':CLAUSES[d['field']],'span':d.get('span',[2047,2128]),'minimum_level':0,'skill':None,
 'ranked':bool(d.get('ranked')),'max_rank':d.get('ranked',1)} for u,d in DEFINITIONS.items() if u in (BREADTH,BOOKWORM,WELL_READ)}


def _book_prerequisite_sources(rules):
 from source_context import verified_source
 authority=_data['reviewed_sources']
 content=verified_source(rules,authority['local_csv'],label='Researcher Books prerequisites')
 rows=list(csv.reader(io.StringIO(content.decode('utf-8-sig'),newline='')))
 expected=((323,'폭넓은 지식','초보일반지식'),(324,'책벌레','폭넓은지식'),
           (325,'이해 완료','책벌레,전문일반지식'))
 for number,title,prerequisite in expected:
  if len(rows)<number:raise ValueError('actual General Research Field CSV record required')
  row=rows[number-1]
  if (len(row)<5 or row[0]!=title or row[1]!='[일반 지식 연구 분야]'
      or ''.join(row[2].split())!=prerequisite or row[3]!='항상' or not row[4].strip()):
   raise ValueError('reviewed General Research Field CSV record changed')
 # Both original sources are already authenticated inputs. Native code owns
 # the reviewed book/CSV distinction; no extracted body is fabricated here.
 for key in ('core_en','may2015'):
  verified_source(rules,authority[key],label='Researcher Books English authority',source_root='source-audit')

def static_source(rules,feature):
 return _source_authority(rules,feature,'book')


def acquisition_snapshot(engine,actor,feature,rank,selection):
 """Snapshot ordinary prerequisites before the new Feature exists."""
 d=DEFINITIONS[feature]
 selected=selection or {'edition':'book'}
 if type(selected)is not dict or set(selected)-{'edition','edges','psionic_edition','replacement_feature'} or selected.get('edition') not in ('book','local_csv'):
  raise ValueError('exact Researcher acquisition selection required')
 RF.researcher(engine,actor,d['field'])
 parents={p:bool(owns(actor,p)) for p in d.get('prerequisites',{}).get('feats',())}
 if feature==ECHOES and selected['edition']=='local_csv':parents[BREADTH]=bool(owns(actor,BREADTH))
 import pokemon_activities as P
 for edge in d.get('prerequisites',{}).get('edges',()):
  if edge!='pokebot_training':P._feature(engine,actor,'basic_balls' if edge=='poke_ball_crafter' else edge)
 skills=set(S.EDUCATION_SKILLS)
 pre=d.get('prerequisites',{})
 for skill,n in [*pre.get('skills',[]),*pre.get('all_skills',[]),*(item for options in pre.get('rank_skills',{}).values() for item in options)]:skills.add(skill)
 stunt=__import__('skill_stunts').for_dowsing(engine,actor) if pre.get('dowsing_stunt') else None
 return {'selection':deepcopy(selection),'source':source(engine,feature,selected['edition']),
  'skills':{s:_rank(engine,actor,s) for s in skills},'parents':parents,'dowsing_stunt':stunt,
  'edges':list(actor.spec.get('edges',[])),'fields':list(RF.research_fields(actor)),
  'rank_number':rank,'level':actor.level}


def qualification(actor,feature,snapshot,prerequisite_source):
 import acquisition_qualification as Q
 if prerequisite_source is not None or type(snapshot)is not dict or set(snapshot)!={'selection','source','skills','parents','edges','fields','rank_number','level','dowsing_stunt'}:
  raise ValueError('exact observed Researcher acquisition required')
 selected=(snapshot['selection'] or {'edition':'book'})['edition'];d=DEFINITIONS[feature];pre=d.get('prerequisites',{})
 if snapshot['source']!=_source_authority(actor.r,feature,selected):raise ValueError('Researcher acquisition authority changed')
 skills=pre.get('skills',[])
 if selected=='local_csv' and feature in (OVERCLOCK,EFFICIENT):skills=[['기술학',4]]
 checks=[Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),
  Q.check('field','prerequisite',d['field'] in snapshot['fields'],'actual acquired Researcher field required'),
  Q.check('skills','prerequisite',not skills or any(snapshot['skills'][s]>=n for s,n in skills),'printed Education rank required'),
  Q.check('all_skills','prerequisite',all(snapshot['skills'][s]>=n for s,n in pre.get('all_skills',[])),'every printed Education rank required'),
  Q.check('parents','prerequisite',all(snapshot['parents'].values()),'actual parent Researcher Features required')]
 if pre.get('dowsing_stunt'):checks.append(Q.check('dowsing_stunt','prerequisite',snapshot['dowsing_stunt'] is True,'actual approved Occult Dowsing Skill Stunt required'))
 elif snapshot['dowsing_stunt'] is not None:raise ValueError('this Researcher prerequisite has no Dowsing waiver')
 expected=set(pre.get('feats',[]))|({BREADTH} if feature==ECHOES and selected=='local_csv' else set())
 if set(snapshot['parents'])!=expected:raise ValueError('exact historical Researcher parents required')
 for number,options in pre.get('rank_skills',{}).items():
  if int(number)<=snapshot['rank_number']:checks.append(Q.check('rank'+number,'prerequisite',any(snapshot['skills'][s]>=n for s,n in options),'printed ranked skill prerequisite required'))
 for edge in pre.get('edges',[]):
  aliases={'pokebot_training':('edge/포켓봇-훈련','feat/포켓봇-훈련'),'poke_ball_crafter':('edge/몬스터볼',),'green_thumb':('edge/원예가',),'gem_lore':('edge/보석-지식',),'repel_crafter':('edge/스프레이-제작자',),'paleontologist':('edge/고생물학자',)}
  if edge not in aliases:raise ValueError('reviewed Researcher prerequisite Edge mapping required: '+edge)
  checks.append(Q.check(edge,'prerequisite',any(uid in snapshot['edges'] for uid in aliases[edge]),'actual printed prerequisite Edge required'))
 return Q.require(feature,'native','acquire',checks)


def after_acquire(engine,actor,feature,source_id):
 import trainer_feature_acquisition as T
 record=next(r for sid,r in T.static_acquisitions(actor,feature) if sid==source_id)
 selected=record['snapshot']['selection'] or {'edition':'book'}
 actor.spec.setdefault('researcher_editions',{})[feature]=deepcopy(record['snapshot']['source'])
 if feature==BREADTH:
  choices=selected.get('edges')
  if type(choices)is not list or len(choices)!=3:raise ValueError('Breadth of Knowledge requires exactly three eligible Education Edges')
  for i,edge in enumerate(choices):_grant_education_edge(engine,actor,edge,source_id+'/edge/'+str(i),source_id)


def _grant_education_edge(engine,actor,choice,sid,parent,*,education_only=True):
 import hobbyist as H,trainer_feature_acquisition as T,capture_techniques as CAP
 if type(choice)is not dict or set(choice)!={'id','choice'}:raise ValueError('exact normally qualified Edge choice required')
 edge=choice['id'];value=choice['choice']
 if edge in H.RANK_EDGES:
  skill=S.skill_id(engine.r.skill_policy,value,required=True)
  if education_only and skill not in S.EDUCATION_SKILLS:raise ValueError('Breadth rank Edge requires an Education skill')
  proof=CAP._skill_edge(engine.r,{'edge':edge,'skill':skill},actor.level,_rank(engine,actor,skill))
  CAP.grant_skill_edge(engine,actor,proof,sid,researcher_parent=parent)
  __import__('acquisition_withdrawal').dependencies(engine,actor,sid,[parent])
 elif edge in H.SKILL_EDGES:
  if edge=='edge/고난이도-스킬':
   if type(value)is not dict or S.skill_id(engine.r.skill_policy,value.get('skill'),required=True) not in S.EDUCATION_SKILLS:raise ValueError('Breadth Skill Stunt requires its actual Education skill')
  elif edge=='edge/스킬-향상':
   if type(value)is not list or len(value)!=2 or any(S.skill_id(engine.r.skill_policy,s,required=True) not in S.EDUCATION_SKILLS for s in value):raise ValueError('Breadth Skill Enhancement requires two Education skills')
   old={S.skill_id(engine.r.skill_policy,s,required=True) for pair in actor.spec.get('edge_choices',{}).get(edge,[]) for s in pair}
   if old.intersection(S.skill_id(engine.r.skill_policy,s,required=True) for s in value):raise ValueError('ordinary Skill Enhancement cannot apply twice to the same skill')
  elif edge=='edge/거장':
   if S.skill_id(engine.r.skill_policy,value,required=True) not in S.EDUCATION_SKILLS:raise ValueError('Breadth Virtuoso requires an Education skill')
   if value in actor.spec.get('edge_choices',{}).get(edge,[]):raise ValueError('ordinary Virtuoso must choose a different skill')
  else:raise ValueError('Breadth requires an individually selected Education Skill Edge')
  # The existing executor validates ordinary acquisition and owns the exact
  # choice/native skill consumer; its parent source need not be a Hobbyist.
  H.acquire_skill_edge(engine,actor,edge,value,sid,parent)
 elif edge in H.CORE_EDGE_SKILLS:
  pre=H.CORE_EDGE_SKILLS[edge]
  if education_only and not any(S.skill_id(engine.r.skill_policy,s,required=True) in S.EDUCATION_SKILLS for s,n in pre):raise ValueError('Breadth Edge must have an Education prerequisite')
  T.grant_qualified_core_edge(engine,actor,edge,value,sid,parent)
 else:raise ValueError('selected Edge needs its ordinary acquisition owner')


def validate_acquisition(actor,record,source_id,active):
 feature=record['feature_id'];selection=record['snapshot']['selection']
 if active and actor.spec.get('researcher_editions',{}).get(feature)!=record['snapshot']['source']:raise ValueError('Researcher actual acquired edition projection changed')


def _source_authority(rules,feature,edition):
 """An explicit source choice changes only the reviewed delta, not ownership."""
 from source_context import verified_source
 if edition not in ('book','local_csv'):raise ValueError('reviewed Researcher edition required: book or local_csv')
 if feature in (BREADTH,BOOKWORM,WELL_READ):_book_prerequisite_sources(rules)
 if rules._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Researcher field variant needs a sourced adapter')
 if edition=='book':
  key=DEFINITIONS[feature].get('book_source')
  authority=_data['reviewed_sources'][key] if key else {'file':_data['source_file'],'sha256':_data['source_sha256']}
  verified_source(rules,authority,label='Book Researcher',source_root='source-audit' if authority['file'].startswith('source-audit/') else 'input')
  return dict(authority,edition=edition,clause_id=clause(feature))
 authority=_data['reviewed_sources']['local_csv']
 verified_source(rules,authority,label='local CSV Researcher')
 record=_data['csv_records'].get(feature)
 if record is None:raise ValueError('this Book Feature has no identical local CSV record: '+feature)
 identity='C2CSV/input/db/feats.csv:R'+str(record)+':main'
 rules.ruleset.require({'id':identity,'source':{'file':'db/feats.csv','record_span':[record,record]}})
 return dict(authority,edition=edition,clause_id=identity,record=record)


def source(engine,feature,edition='book'):
 return _source_authority(engine.r,feature,edition)


def _edition(engine,trainer,feature):
 row=trainer.spec.get('researcher_editions',{}).get(feature)
 edition='book' if row is None else row.get('edition')
 if row is not None and row!=source(engine,feature,edition):raise ValueError('actual selected Researcher source changed')
 return edition


def study_points(engine,trainer):
 """AP-like study drain uses the same actual extended-rest recovery epoch."""
 qualify(engine,trainer,BOOKWORM,available=False);edition=_edition(engine,trainer,BOOKWORM)
 other=sum(owns(trainer,uid) for uid,d in DEFINITIONS.items() if d['field']=='general' and uid!=BOOKWORM)
 maximum=2*other if edition=='local_csv' else 2+other
 import recovery_receipts as RECOVERY
 epoch=sorted(uid for uid,row in RECOVERY.validate(trainer).items() if row['intent'].get('source')=='gameplay/action-points' and row['intent'].get('resource')=='ap_removed' and row['intent'].get('policy')=='qualified_extended_rest' and row['eligibility'].get('eligible'))
 rows=(state(trainer) or {}).get('study_drains',[])
 spent=sum(row['amount'] for row in rows if row['rest_epoch']==epoch)
 if type(spent)is not int or spent<0 or spent>maximum:raise ValueError('actual Study Point drain exceeds the acquired Bookworm pool')
 return {'maximum':maximum,'drained':spent,'available':maximum-spent,'rest_epoch':epoch,'authority':source(engine,BOOKWORM,edition)}


def _drain_study(engine,trainer,source_id):
 pool=study_points(engine,trainer)
 if not pool['available']:raise ValueError('Bookworm Study Points exhausted until an actual Extended Rest')
 row={'amount':1,'source_id':source_id,'rest_epoch':pool['rest_epoch'],'authority':pool['authority'],'at':engine.elapsed_seconds}
 state(trainer,create=True).setdefault('study_drains',[]).append(row);return row



def uid(name):
 return name if name in DEFINITIONS else ENGLISH[name]


def clause(feature):
 return CLAUSES[DEFINITIONS[feature]['field']]


def _text(value,label):
 if type(value) is not str or not value.strip():raise ValueError(label+' required')
 return value


def _rank(e,actor,skill):
 return S.rank(e.r,actor,skill)[2]


def owns(trainer,feature):
 if feature==WARFARE and __import__('hobbyist').provider(trainer,feature) is not None:return True
 return trainer.kind=='trainer' and FEATURES.owned(trainer,feature)


def feature_rank(trainer,feature):
 d=DEFINITIONS[feature]
 if not d.get('ranked'):return 1
 ranks=trainer.spec.get('feat_ranks',{})
 if not isinstance(ranks,dict):raise ValueError('acquired feature ranks must be a mapping')
 value=ranks.get(feature,1)
 if type(value) is not int or not 1<=value<=d['ranked']:raise ValueError('actual acquired '+d['english']+' rank 1..'+str(d['ranked'])+' required')
 return value


def qualify(e,trainer,feature,*,edition=None,available=True):
 """Printed prerequisites against the actual sheet: field, parent Features, Edges and skill ranks."""
 import pokemon_activities as P
 d=DEFINITIONS[feature]
 if feature==WARFARE and __import__('hobbyist').provider(trainer,WARFARE) is not None:
  FEATURES.conscious_trainer(trainer);RF.source(e)
  return d
 RF.require(e,trainer,feature,d['field'],static=feature==PUSHER,available=available)
 pre=d.get('prerequisites',{})
 for parent in pre.get('feats',()):qualify(e,trainer,parent,available=available)
 for edge in pre.get('edges',()):
  if edge=='pokebot_training':
   if not any(FEATURES.owned(trainer,uid) for uid in ('edge/포켓봇-훈련','feat/포켓봇-훈련')):raise ValueError('Engineer requires actual Pokebot Training')
  else:P._feature(e,trainer,'basic_balls' if edge=='poke_ball_crafter' else edge)
 skills=pre.get('skills')
 selected=edition or trainer.spec.get('researcher_editions',{}).get(feature,{}).get('edition','book')
 if feature in (BREADTH,BOOKWORM,WELL_READ):_source_authority(e.r,feature,selected)
 if selected=='local_csv' and feature in (OVERCLOCK,EFFICIENT):skills=[['기술학',4]]
 if skills and not any(_rank(e,trainer,skill)>=rank for skill,rank in skills):
  raise ValueError(d['english']+' requires its printed skill rank: '+' or '.join(skill+' '+str(rank) for skill,rank in skills))
 for skill,rank in pre.get('all_skills',()):
  if _rank(e,trainer,skill)<rank:raise ValueError(d['english']+' requires every printed skill rank')
 if selected=='local_csv' and feature==ECHOES:qualify(e,trainer,BREADTH,available=available)
 if 'rank_skills' in pre:
  rank=feature_rank(trainer,feature)
  for number in range(1,rank+1):
   options=pre['rank_skills'][str(number)]
   if not any(_rank(e,trainer,skill)>=value for skill,value in options):
    raise ValueError(d['english']+' rank '+str(number)+' requires its printed skill rank')
 if pre.get('dowsing_stunt'):
  import skill_stunts as STUNTS
  if not STUNTS.for_dowsing(e,trainer):raise ValueError(d['english']+' requires the approved Dowsing Skill Stunt')
 return d


def state(trainer,create=False):
 st=trainer.spec.get(KEY)
 if st is None:
  if not create:return None
  st={'version':1,'patches':{},'blends':{},'artificer':[],'chemistry':{'exposures':[],'warfare':None},
      'climatology':{'temperature_control':None,'extreme':[]},'eggs':[],'special_quality':[],'held_shard':None,'fistful':None,'rainbow':[],'genetic_memory':{},'rebalanced':[],'fossils':[]}
  trainer.spec[KEY]=st
 if type(st) is not dict or st.get('version')!=1:raise ValueError('unsupported Researcher field state')
 return st


def _outside(e):
 if e.encounter_active:raise ValueError('this Researcher Extended action runs outside an active encounter')


def _extended(e,t,feature,seconds,participants=()):
 """Outside combat: the printed Extended action with its actual GM duration."""
 import turn as TURN
 C.integer(seconds,'actual Extended action seconds',1)
 if not TURN.spend(e,t,'extended',feature):raise ValueError(DEFINITIONS[feature]['english']+' Extended action unavailable')
 e.advance_time(seconds,[t,*participants],source=SOURCE)


def _inventory(trainer):
 inv=trainer.spec.setdefault('items',{})
 if not isinstance(inv,dict):raise ValueError('actual item inventory mapping required')
 return inv


def _owned_count(trainer,key,count=1):
 inv=_inventory(trainer)
 available=C.integer(inv.get(key,0),'owned item count',0)
 if available<count:raise ValueError('insufficient owned items: '+key)
 return key


def _owned_pokemon(e,trainer,pokemon):
 import world_entities as W
 W.require_actors(e,trainer,pokemon)
 if pokemon.kind!='pokemon' or pokemon.spec.get('trainer_id')!=trainer.entity_id:raise ValueError('actual owned Pokemon required')


def _ap(trainer,amount):
 import action_points as AP
 if AP.available(trainer)<amount:raise ValueError('requires '+str(amount)+' available AP')


def _free_action(e,t,feature):
 import action_lifecycle as A
 if e.encounter_active:A.triggered_free_action(e,t,feature)
 else:
  import turn as TURN
  if not TURN.can_act(e,t) or not A.ordinary_permission(e,t) or not A.status_permission(e,t,'free'):raise ValueError('Free Action unavailable')
  A.record_action(e,t,'free')


def _swift(e,t,feature):
 import action_lifecycle as A,turn as TURN
 if e.encounter_active:
  if not TURN.spend(e,t,'swift',feature):raise ValueError(DEFINITIONS[feature]['english']+' Swift action unavailable')
 else:
  if not TURN.can_act(e,t) or not A.ordinary_permission(e,t) or not A.status_permission(e,t,'swift'):raise ValueError('Swift action unavailable')
  A.record_action(e,t,'swift')


# ---------------------------------------------------------------- Apothecary
def _medicine(e,name):
 """(item_id, header, effects, kind) for a restorative ('약' non-X, non-Vitamin) or X item."""
 import restorative_items as RESTORATIVE
 effs,header=e.r.item_effects(name)
 if effs is None or header.get('id') is None:raise ValueError('actual sourced item required: '+str(name))
 uid_=header['id']
 if e.r._selected_rule(uid_)!=uid_:raise ValueError('selected item variant needs its own medicine policy')
 if uid_ in RESTORATIVE.X_ITEMS:return uid_,header,effs,'x'
 vitamin=any(isinstance(x,dict) and x.get('type')=='stat_base_mod' and x.get('vitamin') for x in effs)
 if header.get('category')!='약' or vitamin or uid_ not in RESTORATIVE.HELD_CONSUMABLES:raise ValueError('actual restorative medicine required: '+str(name))
 return uid_,header,effs,'restorative'


def _signature(effs):
 parts=[]
 for x in effs:
  if not isinstance(x,dict) or x.get('type') in ('tag','rule','limit','restriction','gm'):continue
  parts.append(x.get('type')+(':'+str(x['status']) if x.get('status') is not None else ''))
 return tuple(sorted(parts))


def _component(e,trainer,name):
 """A named medicine, a Patch or a Blend currently owned by the trainer."""
 st=state(trainer)
 if isinstance(name,str) and name.startswith(PATCH_PREFIX):
  row=(st or {}).get('patches',{}).get(name)
  if row is None:raise ValueError('actual owned Patch item required: '+name)
  uid_,header,effs,kind=_medicine(e,row['source_item'])
  return {'key':name,'item_id':uid_,'kind':kind,'effects':effs,'signature':_signature(effs),'extended_only':True,'patch':True}
 uid_,header,effs,kind=_medicine(e,name)
 return {'key':name,'item_id':uid_,'kind':kind,'effects':effs,'signature':_signature(effs),'extended_only':False,'patch':False}


def _apply_effects(e,user,target,effs,label):
 """Same consumer as items._use_immediate_item after payment: native cures/revives, then the shared runner."""
 import effects as FX,status_sets as STATUS_SETS,arithmetic_policy as M
 ctx={'attacker':user,'target':target,'hit':True,'nat':None,'engine':e,'who':target}
 run=[];done=0
 for raw in effs:
  if not isinstance(raw,dict):continue
  x=dict(raw);t=x.get('type')
  if t in ('tag','restriction','rule','limit','trainer_slot'):continue
  if t=='heal' and 'amount' not in x and 'value' in x:x['amount']=x.pop('value')
  if t=='revive':
   if not target.fainted:continue
   hp=x.get('hp',1);value=M.ratio(target.base_max_hp,2) if hp=='max_hp/2' else int(hp) if isinstance(hp,int) else M.ratio(target.base_max_hp,2)
   if e.revive(target,max(1,value)):done+=1
   continue
  if t=='stage_reset':
   for stat,value in list(target.stages.items()):
    if value<0:target.stages[stat]=0
   done+=1;continue
  if t=='cure_status' and isinstance(x.get('status'),str) and x['status'] in ('persistent all','volatile all','any one','all'):
   cls='persistent' if 'persistent' in x['status'] else 'volatile' if 'volatile' in x['status'] else None
   for cond in STATUS_SETS.afflictions(target):
    if cls is None or e.r.condition_class(cond)==cls:
     e.cure_status(target,cond);done+=1
     if x['status']=='any one':break
   continue
  x.setdefault('target','target');run.append(x)
 if run:
  applied,_=FX.run_effects(e,user,target,run,ctx,label);done+=applied
 return done


def patch_cure(engine,trainer,item,*,seconds,reason):
 """Extended: extract one owned restorative item into three Patch items usable only as Extended actions."""
 import world_entities as W
 W.require_actors(engine,trainer);qualify(engine,trainer,PATCH);_text(reason,'Patch Cure reason');_outside(engine)
 uid_,header,effs,kind=_medicine(engine,item)
 if kind!='restorative':raise ValueError('Patch Cure extracts a restorative item, not an X item')
 key=_owned_count(trainer,item)
 def apply(e,t):
  _extended(e,t,PATCH,seconds)
  inv=_inventory(t);inv[key]-=1
  patch=PATCH_PREFIX+uid_
  inv[patch]=inv.get(patch,0)+DEFINITIONS[PATCH]['patches_per_item']
  st=state(t,create=True)
  st['patches'].setdefault(patch,{'source_item':item,'item_id':uid_,'feature':PATCH,'clause_id':clause(PATCH),'extended_only':True,'made':[]})['made'].append({'at':e.elapsed_seconds,'reason':reason})
  e.log('  '+t.name+': 임시 치료 - '+item+' → 임시 회복도구 x3',SOURCE)
  return {'patch':patch,'count':inv[patch],'source_item':uid_}
 return G.transition(engine,trainer,apply,include_rulings=True)


def apply_patch(engine,user,patch,target,*,seconds,reason,medical_techniques=False):
 """Extended-only Patch application with the source item's effects; optional Medical Techniques Swift (1 AP)."""
 import world_entities as W
 W.require_actors(engine,user,target);_text(reason,'Patch application reason');_outside(engine)
 FEATURES.conscious_trainer(user)
 row=(state(user) or {}).get('patches',{}).get(patch)
 if row is None:raise ValueError('actual owned Patch item required: '+str(patch))
 _owned_count(user,patch)
 uid_,header,effs,kind=_medicine(engine,row['source_item'])
 if medical_techniques:
  qualify(engine,user,TECHNIQUES);_ap(user,DEFINITIONS[TECHNIQUES]['ap'])
 if target.dead:raise ValueError('actual living recipient required')
 def apply(e,u,q):
  import action_points as AP
  _extended(e,u,PATCH,seconds,participants=(q,) if q is not u else ())
  _inventory(u)[patch]-=1
  done=_apply_effects(e,u,q,effs,'item/'+patch)
  result={'patch':patch,'applied':done,'medical_techniques':None}
  if medical_techniques:
   _swift(e,u,TECHNIQUES);AP.spend(u,DEFINITIONS[TECHNIQUES]['ap'])
   rank=S.effective_rank(e.r,u,'의학')
   amount=e.tick(q)+rank
   e.heal(q,amount,source_kind='feature')
   result['medical_techniques']={'heal':amount,'tick':e.tick(q),'medicine_rank':rank}
   e.log('  '+u.name+': 의학 테크닉 - 추가 회복 '+str(amount),SOURCE)
  return result
 return G.transition(engine,user,apply,participants=(target,) if target is not user else (),include_rulings=True)


def medicinal_blend(engine,trainer,first,second,*,seconds,reason):
 """Extended: combine two restorative items with different effects, or one restorative and one X item."""
 import world_entities as W
 W.require_actors(engine,trainer);qualify(engine,trainer,BLEND);_text(reason,'Medicinal Blend reason');_outside(engine)
 a=_component(engine,trainer,first);b=_component(engine,trainer,second)
 kinds=sorted([a['kind'],b['kind']])
 if kinds==['restorative','restorative']:
  if a['signature']==b['signature']:raise ValueError('two restorative items must not share the same effect (e.g. 상처약 and 좋은상처약)')
 elif kinds!=['restorative','x']:raise ValueError('Medicinal Blend takes two restorative items or one restorative item and one X item')
 if a['key']==b['key']:_owned_count(trainer,a['key'],2)
 else:_owned_count(trainer,a['key']);_owned_count(trainer,b['key'])
 def apply(e,t):
  _extended(e,t,BLEND,seconds)
  inv=_inventory(t);inv[a['key']]-=1;inv[b['key']]-=1
  key=BLEND_PREFIX+a['item_id']+'+'+b['item_id']
  inv[key]=inv.get(key,0)+1
  st=state(t,create=True)
  st['blends'].setdefault(key,{'components':[a['item_id'],b['item_id']],'feature':BLEND,'clause_id':clause(BLEND),'extended_only':a['extended_only'] or b['extended_only'],'made':[]})['made'].append({'at':e.elapsed_seconds,'reason':reason,'inputs':[a['key'],b['key']]})
  if (a['extended_only'] or b['extended_only']) and not st['blends'][key]['extended_only']:raise ValueError('blend identity already exists with another use policy')
  e.log('  '+t.name+': 약 혼합 - '+a['key']+' + '+b['key'],SOURCE)
  return {'blend':key,'extended_only':st['blends'][key]['extended_only'],'components':[a['item_id'],b['item_id']]}
 return G.transition(engine,trainer,apply,include_rulings=True)


def apply_blend(engine,user,blend,target,*,reason,seconds=None):
 """Use a Blend: both component effects; a Patch-derived blend only as an Extended action."""
 import world_entities as W,turn as TURN
 W.require_actors(engine,user,target);_text(reason,'blend application reason');FEATURES.conscious_trainer(user)
 row=(state(user) or {}).get('blends',{}).get(blend)
 if row is None:raise ValueError('actual owned Blend item required: '+str(blend))
 _owned_count(user,blend)
 parts=[_medicine(engine,uid_) for uid_ in row['components']]
 if row['extended_only']:_outside(engine)
 if target.dead:raise ValueError('actual living recipient required')
 def apply(e,u,q):
  if row['extended_only']:_extended(e,u,BLEND,seconds,participants=(q,) if q is not u else ())
  else:
   if seconds is not None:raise ValueError('an ordinary blend is applied as a Standard action, not a timed Extended action')
   if not TURN.spend(e,u,'standard',BLEND):raise ValueError('blend application Standard action unavailable')
  _inventory(u)[blend]-=1
  done=sum(_apply_effects(e,u,q,effs,'item/'+blend) for _,_,effs,_ in parts)
  return {'blend':blend,'applied':done,'extended_only':row['extended_only']}
 return G.transition(engine,user,apply,participants=(target,) if target is not user else (),include_rulings=True)


# ---------------------------------------------------------------- Artificer
def _shard_types(e,color):
 import crafting_resources as RESOURCES
 if color not in RESOURCES.SHARDS:raise ValueError('actual shard color required')
 return RESOURCES.SHARDS[color]


def craft_artificer(engine,trainer,item,*,color,move_type,minutes,reason):
 """Crystal Artificer: Type Booster / Type Brace from four same-colour shards; type among the colour's three."""
 import world_entities as W,crafting_recipes as RECIPES,pokemon_activities as P
 W.require_actors(engine,trainer);qualify(engine,trainer,CRYSTAL);_text(reason,'crafting reason');_outside(engine)
 recipe=DEFINITIONS[CRYSTAL]['recipes'].get(item)
 if recipe is None:raise ValueError('Crystal Artificer recipe required: 타입부스터 or 타입깁스')
 if move_type not in _shard_types(engine,color):raise ValueError('product type must be one of the shard colour types')
 C.integer(minutes,'GM crafting minutes',1)
 source,aliases,prerequisites=P.FEATURES['gem_lore']
 declaration={'id':'researcher:artificer:'+item,'source':SOURCE,'output':{'item_id':recipe['item_id'],'key':item},
  'requirements':[{'id':'permission','condition':{'kind':'all','conditions':[
     {'kind':'owned','fields':['classes','feats'],'names':['class/연구원','연구원','Researcher']},
     {'kind':'owned','fields':['edges'],'names':[source,*aliases]}]},'reason':'acquired Researcher class and Gem Lore required'}],
  'materials':[{'id':'shard','options':[{'kind':'shard','color':color,'amount':recipe['shards']}]}],'seconds':minutes*60}
 def apply(e,t):
  result=RECIPES.perform(e,t,declaration,reason=reason,operation='craft_artificer')
  state(t,create=True)['artificer'].append({'item':item,'item_id':recipe['item_id'],'color':color,'type':move_type,'at':e.elapsed_seconds,'feature':CRYSTAL,'clause_id':clause(CRYSTAL)})
  return dict(result,color=color,type=move_type)
 return G.transition(engine,trainer,apply,include_rulings=True)


def dowsing_bonus(e,actor):
 """Crystal Resonance: +3d6 to the Dowsing shard pool (consumed by crafting_activities._dowse)."""
 if actor.kind!='trainer' or not owns(actor,RESONANCE):return 0
 import skill_stunts as STUNTS
 if not STUNTS.for_dowsing(e,actor):return 0   # the printed Skill Stunt (Dowsing) prerequisite is not met: no bonus, ordinary dowsing proceeds
 qualify(e,actor,RESONANCE)
 return DEFINITIONS[RESONANCE]['dowsing_bonus_dice']


def _wearing(e,trainer,item_id):
 import items as ITEMS
 for record in getattr(trainer,'_item_reg',{}).values():
  if record.get('item_id')==item_id and ITEMS.equipment_benefit_active(trainer,record):return True
 return False


def rainbow_light(engine,trainer):
 """2 AP Standard: a one-round rainbow; every ally's effect range +3 while it lasts."""
 import world_entities as W,turn as TURN,combat_timing as T
 W.require_actors(engine,trainer);d=qualify(engine,trainer,RAINBOW)
 if not engine.encounter_active:raise ValueError('Rainbow Light is a Standard action in an active encounter')
 if not _wearing(engine,trainer,d['prerequisites']['wearing']):raise ValueError('Rainbow Light requires wearing the actual Rainbow Gem')
 _ap(trainer,d['ap'])
 if any(r.get('source')==RAINBOW for r in T.records(trainer)):raise ValueError('a rainbow is already active')
 def apply(e,t):
  import action_points as AP
  if not TURN.spend(e,t,d['action'],RAINBOW):raise ValueError('Rainbow Light Standard action unavailable')
  AP.spend(t,d['ap'])
  serial=t.custom_conditions.get('combat_turn_serial',0)
  row={'source':RAINBOW,'turn_owner':t,'turn_start_deadline':serial+d['rounds'],'encounter_end':True,
   'researcher_rainbow':{'trainer_id':t.entity_id,'round':e.round_no,'effect_range':d['ally_effect_range'],'clause_id':clause(RAINBOW)}}
  T.install(e,t,row);e.time_actors([t])
  state(t,create=True)['rainbow'].append({'round':e.round_no,'at':e.elapsed_seconds})
  e.log('  '+t.name+': 무지갯빛 - 1라운드 동안 동료 효과 범위 +3',SOURCE)
  return deepcopy(row['researcher_rainbow'])
 return G.transition(engine,trainer,apply,include_rulings=True)


def _is_ally(trainer,actor):
 if actor is trainer:return True
 if actor.spec.get('trainer_id')==trainer.entity_id:return True
 return getattr(trainer,'side',None) is not None and getattr(actor,'side',None)==trainer.side


def effect_range_bonus(engine,attacker,move):
 """Rainbow Light for allies of the active rainbow's trainer; Primal Cloak is an owned item modifier."""
 if attacker is None or not move:return 0
 import combat_timing as T,world_entities as W
 total=0
 for c in W.actor_index(engine).values():
  if c.kind!='trainer':continue
  for row in T.records(c):
   if row.get('source')==RAINBOW and _is_ally(c,attacker):total+=row['researcher_rainbow']['effect_range']
 return total


def hold_shard(engine,trainer,color,hand):
 """Place one owned shard into the main or off hand (Swift in combat), ready for Fistful of Force."""
 import world_entities as W,turn as TURN,crafting_resources as RESOURCES
 W.require_actors(engine,trainer);FEATURES.conscious_trainer(trainer);_shard_types(engine,color)
 if hand not in ('주요손','반대손'):raise ValueError('shard must be held in the main hand (주요손) or off hand (반대손)')
 RESOURCES.validate(trainer)
 if C.integer(trainer.spec.get('shards',{}).get(color,0),'owned shards',0)<1:raise ValueError('owned shard of that colour required')
 def apply(e,t):
  st=state(t,create=True)
  if st['held_shard'] is not None:raise ValueError('a shard is already held; use or release it first')
  if e.encounter_active and not TURN.spend(e,t,'swift','조각 쥐기'):raise ValueError('retrieving a shard needs a Swift action')
  t.spec['shards'][color]-=1
  st['held_shard']={'color':color,'hand':hand,'at':e.elapsed_seconds}
  return deepcopy(st['held_shard'])
 return G.transition(engine,trainer,apply)


def fistful_of_force(engine,trainer,target,everyone,*,move_type,aim=None,set_damage=False):
 """Scene, Standard: destroy the held shard and use Judgement of one of its colour types, adding Occult rank x3 instead of Special Attack."""
 import world_entities as W,frequency as F,initiative_interrupts as I
 W.require_actors(engine,trainer,target);d=qualify(engine,trainer,FISTFUL)
 st=state(trainer)
 held=None if st is None else st['held_shard']
 if held is None:raise ValueError('Fistful of Force requires a shard in the main or off hand')
 if move_type not in _shard_types(engine,held['color']):raise ValueError('Judgement type must be one of the held shard colour types')
 if not engine.encounter_active:raise ValueError('Fistful of Force is a Standard attack in an active encounter')
 mid=d['move'];pending=[]
 def apply(e,t,*others):
  if not F.activation_allowed(t,FISTFUL,d['frequency'],engine=e):raise ValueError('Fistful of Force was already used this scene')
  allowed,reason=F.move_allowed(e,t,mid,outside_combat=False)
  if not allowed:raise ValueError('Judgement frequency refuses the attack: '+str(reason))
  sid='researcher-fistful:'+t.entity_id+':'+str(e.round_no)+':'+str(t.custom_conditions.get('combat_turn_serial',0))
  G.grant_moves(t,[mid],sid,'feature',owner_id=t.entity_id,lifetime='turn',rule_id=SOURCE,mode='permission')
  rank=S.effective_rank(e.r,t,'오컬트학')
  s=state(t);s['fistful']={'move':mid,'type':move_type,'occult_rank':rank,'shard':deepcopy(s['held_shard']),'source':sid,'round':e.round_no}
  s['held_shard']=None
  F.consume_activation(t,FISTFUL,d['frequency'],engine=e)
  try:
   primary=others[0] if others else t
   result=e.use_move_on(t,primary,mid,list(e.everyone),aim=aim,set_damage=set_damage)
  except Exception as error:
   import passive_events as PASSIVE,heavy_injury_adapter as HEAVY
   if (type(error) is PASSIVE.PassiveEventPending and e._passive_pending==error.event_id
       and error.event_id in e._passive_events):pending.append((PASSIVE.PassiveEventPending,error.event_id))
   elif (type(error) is HEAVY.HeavyPending and e._heavy_pending==error.event_id
         and error.event_id in e._heavy_events):pending.append((HEAVY.HeavyPending,error.event_id))
   else:raise
   result=None
  finally:
   s['fistful']=None;G.revoke(t,sid,engine=e)
  e.log('  '+t.name+': 한줌의 힘 - '+held['color']+' 조각 파괴, 심판의뭉치('+move_type+')',SOURCE)
  return {'result':result,'type':move_type,'shard':held,'attack_bonus':rank*3}
 result=G.transition(engine,trainer,apply,participants=(target,) if target is not trainer else (),include_rulings=True,include_grid=engine.grid is not None)
 if pending:
  exception,event_id=pending[0]
  raise exception(event_id)
 return result


def prepare_move(engine,attacker,move,*,target=None):
 """Keep the paid Fistful selection on each native recipient and resumed Move."""
 if attacker.kind!='trainer' or not isinstance(move,dict):return move
 st=attacker.spec.get(KEY)
 pending=None if st is None else st.get('fistful')
 if pending is not None and move.get('id')==pending['move']:
  marker={'attack_value':pending['occult_rank']*3,'type':pending['type'],'source':pending['source']}
 else:
  import move_activation as ACTIVATION
  scope=ACTIVATION.current_scope(engine,attacker,target,move.get('id'))
  row=None if scope is None else getattr(engine,'_move_completions',{}).get(scope.get('completion_id'))
  if row is None or row['actor'] is not attacker or row['move_id']!=move.get('id'):return move
  marker=row['move'].get('_researcher_fistful')
  if marker is None:return move
 return dict(move,type=marker['type'],_researcher_fistful=deepcopy(marker))


def attack_stat_value(engine,attacker,move,value):
 """Damage: Fistful of Force adds Occult rank x3 instead of the Special Attack stat."""
 marker=move.get('_researcher_fistful') if isinstance(move,dict) else None
 if marker is None:return value
 return marker['attack_value']


# ---------------------------------------------------------------- Botany
def _seed_moves(rank):
 result=[]
 for number in range(1,rank+1):result.extend(DEFINITIONS[SEED_BAG]['moves'][str(number)])
 return result


def _seed_sources(actor):
 return {sid:row for sid,row in actor.spec.get(G.KEY,{}).get('sources',{}).items() if sid.startswith(SEED_PREFIX)}


def seed_bag(engine,trainer,pokemon,move,*,seconds,reason):
 """X/day (two per rank) Extended: harvest one listed Move from a willing Grass Pokemon that knows it, until the day ends."""
 import world_entities as W,frequency as F,pokemon_entities as ENTITIES
 W.require_actors(engine,trainer,pokemon);d=qualify(engine,trainer,SEED_BAG);_text(reason,'Seed Bag reason');_outside(engine)
 rank=feature_rank(trainer,SEED_BAG)
 mid=engine.r.move_id(move)
 if mid is None or mid not in _seed_moves(rank):raise ValueError('Seed Bag harvests only the printed powder/spore/seed Moves of its acquired rank')
 if pokemon.kind!='pokemon' or '풀' not in pokemon.types:raise ValueError('a willing Grass-type Pokemon is required')
 if pokemon.fainted or pokemon.dead:raise ValueError('a conscious willing Pokemon is required')
 if ENTITIES.effective_loyalty_value(pokemon,engine=engine,required=True)<2:raise ValueError('a willing Pokemon (GM loyalty 2 or more) is required')
 if mid not in pokemon.moves:raise ValueError('the Pokemon must actually know that Move')
 if mid in trainer.moves:raise ValueError('Seed Bag cannot add a Move already on your Move list')
 frequency={'kind':'daily','uses':d['daily_uses_per_rank']*rank}
 def apply(e,t,q):
  if not F.activation_allowed(t,SEED_BAG,frequency,engine=e):raise ValueError('Seed Bag daily uses (two per rank) exhausted')
  _extended(e,t,SEED_BAG,seconds,participants=(q,))
  day=t.spec.get('frequency_state',{}).get('day',0)
  sid=SEED_PREFIX+t.entity_id+':'+mid
  G.grant_moves(t,[mid],sid,'feature',owner_id=t.entity_id,lifetime='while_owned',rule_id=SOURCE,mode='learned')
  G.state(t)['sources'][sid].update(researcher_seed={'day':day,'pokemon_id':q.entity_id,'feature':SEED_BAG,'clause_id':clause(SEED_BAG),'at':e.elapsed_seconds,'rank':rank})
  F.consume_activation(t,SEED_BAG,frequency,engine=e)
  e.log('  '+t.name+': 씨앗 가방 - '+q.name+'에게서 '+mid+' 수확 (오늘 하루)',SOURCE)
  return {'move':mid,'source':sid,'day':day,'rank':rank}
 return G.transition(engine,trainer,apply,participants=(pokemon,),include_rulings=True)


def new_day(actor):
 """frequency.new_day: harvested Seed Bag Moves last only the rest of their day."""
 for sid,row in list(_seed_sources(actor).items()):
  day=actor.spec.get('frequency_state',{}).get('day',0)
  if row.get('researcher_seed',{}).get('day')!=day:G.revoke(actor,sid)


# Top Tier Berries (feat/최상급-열매) tiers and the Master soil quality +1 are owned by crafting_activities._top_tier /
# cultivation_harvest's 'botany' contribution; this module only lists the Feature and its prerequisites.


def herb_lore(engine,trainer,product,*,option,minutes,reason):
 """Herb Lore: Energy Powder, Heal Powder or Poultice from the printed ingredients and yields."""
 import world_entities as W,crafting_recipes as RECIPES
 W.require_actors(engine,trainer);qualify(engine,trainer,HERB_LORE);_text(reason,'Herb Lore reason');_outside(engine)
 recipe=DEFINITIONS[HERB_LORE]['recipes'].get(product)
 if recipe is None:raise ValueError('Herb Lore makes 힘의가루, 만능가루 or 파스')
 C.integer(option,'Herb Lore ingredient option',0,len(recipe['options'])-1);C.integer(minutes,'GM crafting minutes',1)
 chosen=recipe['options'][option]
 rows=chosen['items'] if 'items' in chosen else [[chosen['item'],chosen['item_id'],chosen['count']]]
 groups=[{'id':'ingredient'+str(i),'options':[{'kind':'item','item_id':item_id,'key':key,'amount':count}]} for i,(key,item_id,count) in enumerate(rows)]
 RECIPES._selected(engine,recipe['item_id'])
 if engine.r.item_effects(product)[1].get('id')!=recipe['item_id']:raise ValueError('selected product identity changed')
 def apply(e,t):
  plan=RECIPES.prepare_materials(e,t,groups)
  _extended(e,t,HERB_LORE,minutes*60)
  paid=RECIPES.pay_materials(e,t,plan['payments'])
  inv=_inventory(t);inv[product]=inv.get(product,0)+chosen['yield']
  e.log('  '+t.name+': 허브 지식 - '+product+' x'+str(chosen['yield']),SOURCE)
  return {'item':product,'item_id':recipe['item_id'],'count':chosen['yield'],'materials':paid,'feature':HERB_LORE}
 return G.transition(engine,trainer,apply,include_rulings=True)


# ---------------------------------------------------------------- Chemistry
def craft_chemistry(engine,trainer,item,*,minutes,reason,scrap_value=0):
 """Chemist: X items / Dire Hit / Guard Spec (100) and Pester Balls (50) with the Chemistry Set."""
 import world_entities as W,crafting_recipes as RECIPES,crafting_resources as RESOURCES
 W.require_actors(engine,trainer);qualify(engine,trainer,CHEMIST);_text(reason,'crafting reason');_outside(engine)
 recipe=DEFINITIONS[CHEMIST]['recipes'].get(item)
 if recipe is None:raise ValueError('Chemistry recipe required')
 qualify(engine,trainer,recipe['requires'])
 C.integer(minutes,'GM crafting minutes',1)
 header=engine.r.item_effects(recipe['item_id'])[1]
 if header.get('id')!=recipe['item_id']:raise ValueError('selected recipe output changed')
 key=engine.r.selection.units[recipe['item_id']]['title'].split(' [')[0]
 category=RESOURCES.item_kind(header)
 tool='item/화학-세트-1'

 declaration={'id':'researcher:chemistry:'+recipe['item_id'],'source':SOURCE,'output':{'item_id':recipe['item_id'],'key':key},
  'requirements':[{'id':'permission','condition':{'kind':'owned','fields':['classes','feats'],'names':['class/연구원','연구원','Researcher']},'reason':'acquired Researcher class required'},
   {'id':'tool','condition':{'kind':'tool','item_id':tool,'names':['화학 세트'],'instance_id':None},'reason':'required equipment is not accessible: 화학 세트'}],
  'materials':[{'id':'cost','options':[{'kind':'value','category':category,'amount':recipe['cost'],'scrap':True,'money':True}]}],'seconds':minutes*60}
 def apply(e,t):
  return RECIPES.perform(e,t,declaration,inputs={'cost':{'option':0,'scrap_value':scrap_value}},reason=reason,operation='craft_chemistry')
 return G.transition(engine,trainer,apply,include_rulings=True)


def chemical_warfare(engine,trainer):
 """Scene x2 Free Action declared before your Pester Ball throw: Blast 2 affects everyone in its 2x2 area."""
 import world_entities as W,frequency as F
 W.require_actors(engine,trainer);d=qualify(engine,trainer,WARFARE)
 def apply(e,t):
  st=state(t,create=True)
  if st['chemistry']['warfare'] is not None:raise ValueError('Chemical Warfare is already declared for the next Pester Ball')
  if not F.activation_allowed(t,WARFARE,d['frequency'],engine=e):raise ValueError('Chemical Warfare was already used twice this scene')
  _free_action(e,t,WARFARE);F.consume_activation(t,WARFARE,d['frequency'],engine=e)
  st['chemistry']['warfare']={'round':e.round_no,'at':e.elapsed_seconds,'burst':d['burst'],'clause_id':clause(WARFARE)}
  return deepcopy(st['chemistry']['warfare'])
 return G.transition(engine,trainer,apply,include_rulings=True)


def _blast_targets(engine,center,size):
 import world_entities as W,body_state as BODY
 if engine.grid is None:return []
 cells=set(engine.grid.ranged_blast(tuple(center),size))
 result=[]
 for c in W.actor_index(engine).values():
  if not c.on_field or c.fainted or c.captured:continue
  try:occupied=set(BODY.cells(c))
  except ValueError:occupied={tuple(c.pos)} if getattr(c,'pos',None) is not None else set()
  if occupied & cells:result.append(c)
 return result


def pester_hit(engine,user,target,source,*,hit,status_applied):
 """pester_balls._consume: Chemical Warfare Blast and the Caustic Chemistry exposure record."""
 if user.kind!='trainer' or not (owns(user,WARFARE) or owns(user,CAUSTIC)):return None
 st=state(user,create=True)
 import pester_balls as PESTER
 warfare=st['chemistry']['warfare'];extra=[]
 if warfare is not None:
  if not (warfare['round']==engine.round_no and engine.encounter_active):
   st['chemistry']['warfare']=None
  else:
   st['chemistry']['warfare']=None
   if hit:
    center=getattr(target,'pos',None)
    for other in _blast_targets(engine,center,warfare['burst']) if center is not None else []:
     if other is target:continue
     applied=False
     if not PESTER.projection(engine,other)['immune']:
      applied=bool(engine.apply_status(other,PESTER.VARIANTS[source],source=source,applied_by=user))
     extra.append({'target_id':other.entity_id,'status_applied':applied})
    engine.log('    화학전: 오물탄 폭발 2 → 추가 대상 '+str(len(extra)),SOURCE)
 if hit:
  st['chemistry']['exposures'].append({'kind':'pester','source':source,'round':engine.round_no,'at':engine.elapsed_seconds,
   'targets':[target.entity_id,*[row['target_id'] for row in extra]],'extra':extra,'caustic_used':False})
 return extra


def spray_exposure(engine,user,target,source,*,hit):
 """repels._record: a direct Repel spray on a Pokemon is a Caustic Chemistry trigger."""
 if user.kind!='trainer' or target is user or not hit or target.kind!='pokemon' or not owns(user,CAUSTIC):return
 st=state(user,create=True)
 st['chemistry']['exposures'].append({'kind':'spray','source':source,'round':engine.round_no,'at':engine.elapsed_seconds,'targets':[target.entity_id],'extra':[],'caustic_used':False})


def caustic_chemistry(engine,trainer,*,fixed=None):
 """1 AP Swift after your Pester Ball hit or Repel spray: Technology roll; every exposed target loses that much HP, once per target per scene."""
 import world_entities as W,frequency as F
 W.require_actors(engine,trainer);d=qualify(engine,trainer,CAUSTIC);_ap(trainer,d['ap'])
 st=state(trainer)
 rows=[row for row in ((st or {}).get('chemistry',{}).get('exposures',[])) if not row['caustic_used']]
 if not rows:raise ValueError('Caustic Chemistry needs your actual Pester Ball hit or Repel spray this turn')
 row=rows[-1]
 if row['round']!=engine.round_no or row['at']!=engine.elapsed_seconds:raise ValueError('Caustic Chemistry follows the exposure in the same turn')
 index=W.actor_index(engine)
 targets=[index[tid] for tid in row['targets'] if tid in index]
 if not targets:raise ValueError('exposed targets are no longer actual')
 def apply(e,t,*qs):
  import action_points as AP
  _swift(e,t,CAUSTIC);AP.spend(t,d['ap'])
  roll=e.skill_roll(t,'기술학',fixed=fixed)
  results=[]
  for q in qs:
   key=CAUSTIC+':'+q.entity_id
   if not F.activation_allowed(t,key,{'kind':'scene','uses':d['per_target_scene']},engine=e):
    results.append({'target_id':q.entity_id,'hp_loss':0,'skipped':'already affected this scene'});continue
   e.lose_hp(q,roll.total,source=CAUSTIC);F.consume_activation(t,key,{'kind':'scene','uses':d['per_target_scene']},engine=e)
   results.append({'target_id':q.entity_id,'hp_loss':roll.total})
  state(t)['chemistry']['exposures'][[r is row for r in state(t)['chemistry']['exposures']].index(True) if any(r is row for r in state(t)['chemistry']['exposures']) else -1]['caustic_used']=True
  e.log('  '+t.name+': 산성 화학반응 - 기술학 굴림 '+str(roll.total),SOURCE)
  return {'roll':roll.total,'faces':list(roll.faces),'targets':results}
 return G.transition(engine,trainer,apply,participants=tuple(targets),include_rulings=True)


def _species(e,name):
 from builder import species_lookup
 return species_lookup(e.r,name)


def _basic_abilities(e,species_name):
 ls=e.r.learnsets.get(species_name,{})
 abilities=ls.get('abilities',{}) if isinstance(ls,dict) else {}
 return list(abilities.get('기본 특성',[])),list(abilities.get('숨겨진 특성',[]))


def playing_god(engine,trainer,*,species,nature,ability,gender,upgrades,seconds,reason,request_id):
 """Extended, 3500: an artificial egg of one listed species hatching in a day at level 5 with the chosen nature/basic Ability and Technology-rank upgrades."""
 import world_entities as W,pokemon_activities as P,pokemon_entities as ENTITIES,crafting_resources as RESOURCES,nature_state as NATURE
 W.require_actors(engine,trainer);d=qualify(engine,trainer,PLAYING_GOD);_text(reason,'Playing God reason');_text(request_id,'Playing God request');_outside(engine)
 if species not in d['species']:raise ValueError('Playing God creates only the eight printed species')
 sp=_species(engine,species)
 if NATURE.describe(engine.r,nature) is None:raise ValueError('known selected nature required')
 basic,hidden=_basic_abilities(engine,sp['name'])
 if ability not in basic:raise ValueError('choose one of the species basic Abilities: '+', '.join(basic))
 __import__('creation_egg').birth_gender(engine,sp['id'],gender)
 P._tool(trainer,d['tool'])
 rank=S.effective_rank(engine.r,trainer,'기술학')
 if not isinstance(upgrades,list) or len(upgrades)!=rank:raise ValueError('choose exactly one upgrade per Technology rank ('+str(rank)+')')
 counts={'shiny_contest':0,'inheritance_move':0,'base_stat':0}
 ls=engine.r.learnsets.get(sp['name'],{});pool=[]
 for raw in [*ls.get('egg',[]),*ls.get('tutor',[])]:
  import re
  mid=engine.r.move_id(re.sub(r'\s*\(N\)','',str(raw),flags=re.I))
  if mid and mid not in pool:pool.append(mid)
 from builder import STATS
 for row in upgrades:
  if type(row) is not dict or row.get('kind') not in counts:raise ValueError('upgrade kinds: shiny_contest, inheritance_move, base_stat')
  counts[row['kind']]+=1
  if counts[row['kind']]>d['upgrades'][row['kind']]['max']:raise ValueError('upgrade limit exceeded: '+row['kind'])
  if row['kind']=='shiny_contest':
   if row.get('contest_stat') not in ('근사함','아름다움','귀여움','슬기로움','강인함'):raise ValueError('shiny upgrade names one contest stat')
  elif row['kind']=='inheritance_move':
   mid=engine.r.move_id(row.get('move'))
   if mid is None or mid not in pool:raise ValueError('inheritance upgrade takes a Move from the species Egg or Tutor list')
   row['move']=mid
  elif row['kind']=='base_stat':
   if row.get('stat') not in STATS:raise ValueError('base stat upgrade names a stat')
 moves=[row['move'] for row in upgrades if row['kind']=='inheritance_move']
 if len(set(moves))!=len(moves):raise ValueError('inheritance upgrades must name distinct Moves')
 cost=RESOURCES.prepare_cost(trainer,'약',d['cost'],0)
 def apply(e,t):
  prior=next((row for row in state(t,create=True)['eggs'] if row['request_id']==request_id),None)
  if prior is not None:
   if prior['intent']!={'species':sp['id'],'nature':nature,'ability':ability,'gender':gender,'upgrades':upgrades}:raise ValueError('Playing God replay cannot change its intent')
   return deepcopy(prior)
  _extended(e,t,PLAYING_GOD,seconds)
  RESOURCES.pay_cost(t,cost)
  serial=len(state(t)['eggs'])+1
  egg=ENTITIES.prepare_egg(e,t,{'id':'playing-god/'+t.entity_id+'/'+str(serial),'species':sp['id'],'source':SOURCE,'hatched':False,
   'hatch_level':d['birth_level'],'produced_at':e.elapsed_seconds,
   EGG_MARK:{'feature':PLAYING_GOD,'clause_id':clause(PLAYING_GOD),'maker_id':t.entity_id,'nature':nature,'ability':ability,'gender':gender,
    'upgrades':deepcopy(upgrades),'technology_rank':rank,'hatch_seconds':d['hatch_seconds'],'cost':d['cost'],'request_id':request_id}})
  t.spec.setdefault('eggs',[]).append(egg)
  row={'request_id':request_id,'intent':{'species':sp['id'],'nature':nature,'ability':ability,'gender':gender,'upgrades':deepcopy(upgrades)},'egg_entity_id':egg['entity_id'],'at':e.elapsed_seconds}
  state(t)['eggs'].append(row)
  e.log('  '+t.name+': 신 놀이 - '+species+' 인공알 제작 (3500원, 하루 뒤 부화)',SOURCE)
  return deepcopy(row)
 return G.transition(engine,trainer,apply,include_rulings=True)


def hatch_artificial(engine,trainer,egg_entity_id,*,name,reason):
 """After one day: the artificial egg hatches at level 5 with its chosen nature, Ability and upgrades."""
 import world_entities as W,pokemon_entities as ENTITIES,creation_egg as E,pokemon_party as PARTY,pokemon_activities as P
 W.require_actors(engine,trainer);_text(reason,'hatch reason');_outside(engine)
 def apply(e,t):
  import move_state as M,growth_stats as GROWTH,arithmetic_policy as ARITH
  entry=ENTITIES.egg_index(e).get(egg_entity_id)
  if entry is None or entry[0] is not t or entry[1]['hatched'] or EGG_MARK not in entry[1]:raise ValueError('actual unhatched Playing God egg owned by this trainer required')
  egg=entry[1];facts=egg[EGG_MARK]
  if e.elapsed_seconds-egg['produced_at']<facts['hatch_seconds']:raise ValueError('the artificial egg hatches after one day')
  P._trainer(t)
  level=egg['hatch_level'];sp=_species(e,egg['species'])
  evidence=M.current_natural_evidence(e.r,{'species':egg['species'],'level':level})
  natural=[mid for mid,rows in evidence.items() if any(row['kind']=='level_up' for row in rows)]
  inherited=[row['move'] for row in facts['upgrades'] if row['kind']=='inheritance_move']
  shiny=[row for row in facts['upgrades'] if row['kind']=='shiny_contest']
  selected={'gender':facts['gender'],'nature':facts['nature'],'abilities':[facts['ability']],'moves':natural[-6:],'special_appearance':bool(shiny),'inheritance_moves':inherited}
  import pokemon_progression as PROGRESSION
  tutor_points=1+ARITH.ratio(level,5)   # pokemon_progression initial balance for a known level
  pokemon,selected=E.construct(e,t,egg,name=name,birth_level=level,tutor_points=tutor_points,selected=selected,extra={'playing_god_egg_entity_id':egg['entity_id']})
  spec=pokemon.spec
  for row in facts['upgrades']:
   if row['kind']=='base_stat':
    GROWTH.apply_vitamin(pokemon,row['stat'],source=SOURCE)
    spec.setdefault('researcher_vitamin_equivalents',[]).append({'feature':PLAYING_GOD,'stat':row['stat'],'counts_as_vitamin':True,'clause_id':clause(PLAYING_GOD)})
  if shiny:spec['researcher_contest_introduction']={'stat':shiny[0]['contest_stat'],'dice':DEFINITIONS[PLAYING_GOD]['upgrades']['shiny_contest']['contest_bonus_dice'],'feature':PLAYING_GOD,'clause_id':clause(PLAYING_GOD)}
  spec[EGG_MARK]=deepcopy(facts)
  placement=PARTY.preflight_hatch(e,t,pokemon,egg)
  E.commit_birth(e,t,egg,pokemon,selected,reason=reason,placement=placement)
  e.log('  '+t.name+': 신 놀이 인공알 부화 - '+name+' (레벨 '+str(level)+')',SOURCE)
  return {'pokemon':pokemon,'egg_entity_id':egg['entity_id'],'upgrades':deepcopy(facts['upgrades']),'tutor_points':spec['tutor_points']}
 return G.transition(engine,trainer,apply,include_rulings=True)


def vitamin_equivalents(spec):
 """Playing God base-stat upgrades count against the Vitamin allowance like consumed doses."""
 rows=spec.get('researcher_vitamin_equivalents',[])
 if not isinstance(rows,list) or any(not isinstance(r,dict) or r.get('feature')!=PLAYING_GOD or not r.get('counts_as_vitamin') for r in rows):
  raise ValueError('Playing God Vitamin-equivalent records must name their feature')
 return len(rows)


def introduction_bonus_dice(engine,pokemon,stat):
 """Read the actual birth grant; later ownership does not change its source."""
 row=pokemon.spec.get('researcher_contest_introduction')
 if row is None:return 0
 import world_entities as W,pokemon_entities as ENTITIES
 W.require_actors(engine,pokemon)
 source(engine,PLAYING_GOD)
 identity=pokemon.spec.get('playing_god_egg_entity_id')
 entry=ENTITIES.egg_index(engine).get(identity)
 egg=None if entry is None else entry[1]
 facts=pokemon.spec.get(EGG_MARK)
 if (pokemon.kind!='pokemon' or egg is None or egg.get('source')!=SOURCE
     or pokemon.spec.get('egg_entity_id')!=identity or egg.get('hatched') is not True
     or egg.get('pokemon_id')!=pokemon.entity_id or type(facts)is not dict
     or facts.get('feature')!=PLAYING_GOD or facts.get('clause_id')!=clause(PLAYING_GOD)
     or egg.get(EGG_MARK)!=facts):
  raise ValueError('Playing God contest bonus requires its actual birth source')
 upgrades=facts.get('upgrades')
 if type(upgrades)is not list or any(type(item)is not dict for item in upgrades):
  raise ValueError('Playing God contest bonus requires actual birth upgrades')
 shiny=[item for item in upgrades if item.get('kind')=='shiny_contest']
 if (len(shiny)!=1 or shiny[0].get('contest_stat') not in ('근사함','아름다움','귀여움','슬기로움','강인함')
     or pokemon.spec.get('special_appearance') is not True
     or egg.get('gm_hatch_details',{}).get('special_appearance') is not True):
  raise ValueError('Playing God contest bonus requires the shiny birth')
 expected={'stat':shiny[0]['contest_stat'],
  'dice':DEFINITIONS[PLAYING_GOD]['upgrades']['shiny_contest']['contest_bonus_dice'],
  'feature':PLAYING_GOD,'clause_id':clause(PLAYING_GOD)}
 if type(row)is not dict or row!=expected:
  raise ValueError('Playing God contest bonus differs from its actual birth grant')
 return expected['dice'] if expected['stat']==stat else 0


# ---------------------------------------------------------------- Climatology
def _climatology_sources(actor):
 return {sid:row for sid,row in actor.spec.get(G.KEY,{}).get('sources',{}).items() if sid.startswith(CLIMATOLOGY_PREFIX)}


def activate_climatology(engine,trainer):
 """Static: the qualified Climatology trainer owns the Overcoat Ability while the Feature is held."""
 import world_entities as W
 W.require_actors(engine,trainer);d=qualify(engine,trainer,CLIMATOLOGY)
 def apply(e,t):
  sid=CLIMATOLOGY_PREFIX+t.entity_id
  if sid in _climatology_sources(t):return sid
  G.grant(t,'abilities',d['ability'],sid,'feature',owner_id=t.entity_id,lifetime='while_owned',rule_id=SOURCE,tutor_points=0)
  G.state(t)['sources'][sid].update(researcher_climatology={'feature':CLIMATOLOGY,'clause_id':clause(CLIMATOLOGY)})
  e.register_abilities_one(t,d['ability'])
  return sid
 return G.transition(engine,trainer,apply,include_rulings=True)


def release_climatology(engine,trainer):
 """Losing Climatology (retraining, class loss) ends the Ability grant."""
 for sid in list(_climatology_sources(trainer)):G.revoke(trainer,sid,engine=engine)


def _trainer_of(engine,actor):
 import world_entities as W
 if actor is None:return None
 if actor.kind=='trainer':return actor
 owner=W.actor_index(engine).get(actor.spec.get('trainer_id'))
 return owner if owner is not None and owner.kind=='trainer' else None


def temperature_control(engine,trainer,*,replace_weather_id=None):
 """1 AP Free Action: the next Move/Ability weather coexists, replacing one explicitly selected occurrence if two exist."""
 import world_entities as W,weather_state as WEATHER
 W.require_actors(engine,trainer);d=qualify(engine,trainer,TEMPERATURE);_ap(trainer,d['ap'])
 current=getattr(engine,WEATHER.KEY,None)   # read-only: never create the weather envelope while refusing
 if not (current and current.get('active')):raise ValueError('Temperature Control needs a non-standard weather already in effect')
 records=[current['active'],*current.get('layers',[])]
 if len(records)==2:
  if type(replace_weather_id) is not int or replace_weather_id not in {row['id'] for row in records}:
   raise ValueError('Temperature Control requires the actual weather occurrence to replace')
 elif len(records)>2:raise ValueError('Temperature Control requires at most two coexisting weather occurrences')
 elif replace_weather_id is not None:raise ValueError('a replacement occurrence is selected only when two weathers coexist')
 def apply(e,t):
  import action_points as AP
  st=state(t,create=True)
  pending=st['climatology']['temperature_control']
  if pending is not None and pending['turn_serial']==t.custom_conditions.get('combat_turn_serial',0):raise ValueError('Temperature Control is already declared')
  _free_action(e,t,TEMPERATURE);AP.spend(t,d['ap'])
  st['climatology']['temperature_control']={'round':e.round_no,'at':e.elapsed_seconds,'turn_serial':t.custom_conditions.get('combat_turn_serial',0),'clause_id':clause(TEMPERATURE)}
  if replace_weather_id is not None:st['climatology']['temperature_control']['replace_weather_id']=replace_weather_id
  return deepcopy(st['climatology']['temperature_control'])
 return G.transition(engine,trainer,apply,include_rulings=True)


def temperature_control_layer(engine,actor,record):
 """weather_state.set_weather: a declared Temperature Control layers the new Move/Ability weather instead of replacing."""
 import weather_state as WEATHER,world_entities as WORLD
 if not engine.encounter_active:return None
 if record['origin']!='move' and not str(record['source_id']).startswith('ability/'):return None
 declarations=[]
 for owner in WORLD.actor_index(engine).values():
  if owner.kind!='trainer':continue
  st=owner.spec.get(KEY)
  pending=None if st is None else st['climatology']['temperature_control']
  if pending is not None and pending['turn_serial']==owner.custom_conditions.get('combat_turn_serial',0):declarations.append((owner,st,pending))
 if not declarations:return None
 if len(declarations)>1:raise ValueError('multiple Temperature Control declarations need an explicit resolution order')
 owner,st,pending=declarations[0]
 s=WEATHER.state(engine)
 if not s['active']:return None
 records=[s['active'],*s.get('layers',[])]
 if len(records)>1:
  replaced=next((row for row in records if row['id']==pending.get('replace_weather_id')),None)
  if len(records)!=2 or replaced is None:raise ValueError('Temperature Control replacement occurrence changed before its trigger')
  weather_ended(engine,replaced)
  __import__('weather_blessings').retire(engine,replaced,TEMPERATURE,'replaced by Temperature Control')
  s['history'].append(dict(replaced,ended_round=engine.round_no,end_source=TEMPERATURE,end_reason='replaced by Temperature Control'))
  if replaced is s['active']:
   s['active']=s['layers'].pop(0)
   WEATHER._sync_primary(engine)
  else:s['layers'].remove(replaced)
 st['climatology']['temperature_control']=None
 s['sequence']+=1
 layer=dict(record,id=s['sequence'],actor_id=actor.entity_id if actor is not None else None,
  temperature_control={'trainer_id':owner.entity_id,'feature':TEMPERATURE,'clause_id':clause(TEMPERATURE),'coexists_with':s['active']['id']})
 s.setdefault('layers',[]).append(layer)
 import ability_state_projection as PROJECTION
 PROJECTION.weather_changed(engine)
 engine.log('Weather '+record['weather']+' layered by Temperature Control beside '+s['active']['weather'],SOURCE)
 return deepcopy(layer)


def promote_layer(engine):
 """weather_state.boundary: when the older weather ends, a Temperature Control layer continues as the active weather."""
 import weather_state as WEATHER
 s=getattr(engine,WEATHER.KEY,None)
 if not s or not s.get('layers') or not any('temperature_control' in layer for layer in s['layers']):return False
 old=s['active']
 if old is not None:
  weather_ended(engine,old)
  s['history'].append(dict(old,ended_round=engine.round_no,end_source=WEATHER.RULE,end_reason='duration expired'))
 s['active']=s['layers'].pop(0)
 WEATHER._sync_primary(engine)
 import ability_state_projection as PROJECTION
 PROJECTION.weather_changed(engine)
 engine.log('Weather '+s['active']['weather']+' continues after the earlier weather expired (Temperature Control)',SOURCE)
 return True


def learning_routes(engine,pokemon,mid):
 """Printed routes: species Level-Up list (any level), species TM list and species Tutor list."""
 import re
 from builder import species_lookup
 if pokemon.spec.get('species') is None:return []
 name=species_lookup(engine.r,pokemon.spec['species'])['name'];ls=engine.r.learnsets.get(name,{});routes=[]
 if any(engine.r.move_id(row.get('move'))==mid for row in ls.get('level_up',[]) if isinstance(row,dict)):routes.append('level_up')
 for raw in ls.get('tm',[]):
  match=re.fullmatch(r'\s*([A-Za-z]?)([0-9]+)\s+(.+?)\s*',str(raw))
  if match and engine.r.move_id(match.group(3))==mid:routes.append('tm');break
 if any(engine.r.move_id(re.sub(r'\s*\(N\)','',str(x),flags=re.I))==mid for x in ls.get('tutor',[])):routes.append('tutor')
 if any(engine.r.move_id(x)==mid for x in ls.get('egg',[])):routes.append('egg')
 return routes


def _teach_feature_move(engine,trainer,pokemon,feature,mid,*,seconds,reason,allowed_routes,free_routes,frequency=None,fossil=False,route=None,details=None):
 """Shared Extended teaching for Weather Systems, Ancient Heritage and Genetic Memory: two Tutor Points unless a free route applies."""
 import world_entities as W,pokemon_teaching as TEACH,pokemon_activities as P,frequency as F
 W.require_actors(engine,trainer,pokemon);d=qualify(engine,trainer,feature);_text(reason,'teaching reason');_outside(engine)
 _owned_pokemon(engine,trainer,pokemon);P._pokemon(pokemon)
 if fossil and not pokemon.spec.get('fossil_egg_id'):raise ValueError(d['english']+' targets your Pokemon restored from a fossil')
 routes=[r for r in learning_routes(engine,pokemon,mid) if r in allowed_routes]
 if route is not None:
  if route not in routes:raise ValueError('the Pokemon cannot learn that Move by the '+route+' route')
  routes=[route]
 if not routes:raise ValueError('target cannot learn that Move by '+', '.join(allowed_routes))
 cost=0 if any(r in free_routes for r in routes) else d['tutor_points']
 if TEACH._balance(pokemon.spec)<d['tutor_points']:raise ValueError('target needs two actual Tutor Points')
 def apply(e,t,q):
  import move_state as M,learning_grant as LEARNING,activity_jobs as JOBS
  if frequency is not None and not F.activation_allowed(t,feature,frequency,engine=e):raise ValueError(d['english']+' daily frequency exhausted')
  if mid in M.known(e.r,q.spec):raise ValueError('Pokemon already learned that move')
  candidate=deepcopy(q.spec)
  LEARNING.learn_moves(e.r,candidate,candidates=[mid],selected=[mid],method='feature',source=SOURCE,reason=reason,provider=t.entity_id,paid_tp=cost,
   details={'researcher_feature':feature,'learning_routes':routes,'seconds':seconds,**(details or {})})
  moves=candidate['moves']
  M.record_natural_opportunities(e.r,candidate,reason='completed '+d['english']+' teaching')
  M.validate_spec(e.r,candidate,require_routes=True)
  import turn as TURN
  if not TURN.spend(e,t,'extended',feature):raise ValueError(d['english']+' Extended action unavailable')
  JOBS.run_fixed(e,t,(q,),seconds=seconds,source=SOURCE,context={'move_id':mid,'feature':feature})   # the fixed job advances the actual clock
  if frequency is not None:F.consume_activation(t,feature,frequency,engine=e)
  for field in ('move_learning','move_learning_log',M.HISTORY,'move_type_sync'):
   if field in candidate:q.spec[field]=candidate[field]
  G.set_baseline(q,'moves',moves)
  if cost:TEACH._debit_points(q.spec,cost)
  e.log('  '+t.name+': '+d['english']+' - '+q.name+' learns '+mid+' ('+str(cost)+' TP)',SOURCE)
  return {'move':mid,'point_cost':cost,'routes':routes,'seconds':seconds,'classification':M.describe(e.r,q.spec)['classifications'][mid]}
 return G.transition(engine,trainer,apply,participants=(pokemon,),include_rulings=True)


def weather_systems(engine,trainer,pokemon,move,*,seconds,reason):
 d=DEFINITIONS[WEATHER_SYSTEMS];mid=engine.r.move_id(move)
 if mid is None or mid not in d['moves']:raise ValueError('Weather Systems teaches Hail, Rain Dance, Sandstorm or Sunny Day')
 return _teach_feature_move(engine,trainer,pokemon,WEATHER_SYSTEMS,mid,seconds=seconds,reason=reason,allowed_routes=d['learning_routes'],free_routes=['level_up'])


def extreme_weather(engine,trainer):
 """Daily x3 Free Action when you or your Pokemon just created a weather: that weather gains its printed extreme effect."""
 import world_entities as W,frequency as F,weather_state as WEATHER
 W.require_actors(engine,trainer);d=qualify(engine,trainer,EXTREME)
 if not engine.encounter_active:raise ValueError('Extreme Weather follows a weather created in an active encounter')
 s=getattr(engine,WEATHER.KEY,None) or {'active':None}   # read-only precheck
 candidates=[r for r in ([s['active']] if s['active'] else [])+s.get('layers',[]) if r.get('started_round')==engine.round_no and r.get('origin')=='move']
 own={trainer.entity_id}|{c.entity_id for c in W.actor_index(engine).values() if c.spec.get('trainer_id')==trainer.entity_id}
 candidates=[r for r in candidates if r.get('actor_id') in own and 'researcher_extreme' not in r and r['weather'] in d['effects']]
 if not candidates:raise ValueError('Extreme Weather needs a weather you or your Pokemon created this round')
 record=candidates[-1]
 def apply(e,t):
  if not F.activation_allowed(t,EXTREME,d['frequency'],engine=e):raise ValueError('Extreme Weather daily uses exhausted')
  _free_action(e,t,EXTREME);F.consume_activation(t,EXTREME,d['frequency'],engine=e)
  live=next(r for r in ([WEATHER.state(e)['active']] if WEATHER.state(e)['active'] else [])+WEATHER.state(e).get('layers',[]) if r['id']==record['id'])
  live['researcher_extreme']={'trainer_id':t.entity_id,'feature':EXTREME,'clause_id':clause(EXTREME),'round':e.round_no,'at':e.elapsed_seconds,'statuses':[]}
  state(t,create=True)['climatology']['extreme'].append({'weather_id':live['id'],'weather':live['weather'],'round':e.round_no})
  for c in list(W.actor_index(e).values()):_extreme_status(e,c,live)
  e.log('  '+t.name+': 기상 이변 - '+WEATHER_NAMES.get(live['weather'],live['weather']),SOURCE)
  return deepcopy(live['researcher_extreme'])
 return G.transition(engine,trainer,apply,include_rulings=True)


def _extreme_records(engine):
 import weather_state as WEATHER
 s=getattr(engine,WEATHER.KEY,None)
 if not s:return []
 return [r for r in ([s['active']] if s.get('active') else [])+s.get('layers',[]) if 'researcher_extreme' in r]


def _extreme_status(engine,actor,record):
 effect=DEFINITIONS[EXTREME]['effects'][record['weather']]
 if 'status' not in effect or not actor.on_field or actor.fainted or actor.dead:return
 if any(t in effect['exempt_types'] for t in actor.types):return
 facts=record['researcher_extreme']
 if effect['status'] in actor.conditions:return
 import world_entities as W
 owner=W.actor_index(engine).get(facts['trainer_id'])
 # A lapsed fixed-duration status is reapplied at each turn start while the extreme weather lasts.
 if engine.apply_status(actor,effect['status'],source=EXTREME,applied_by=owner) and actor.entity_id not in facts['statuses']:facts['statuses'].append(actor.entity_id)


def weather_turn_start(engine,actor):
 """turn.weather_turn_start: rain slows and sun suppresses newcomers while the extreme weather lasts."""
 for record in _extreme_records(engine):_extreme_status(engine,actor,record)


def weather_damaged(engine,actor,weather):
 """turn._weather_turn_start_one after the tick loss: hail -5 damage rolls, sandstorm -2 accuracy for that actor."""
 for record in _extreme_records(engine):
  if record['weather']!=weather:continue
  effect=DEFINITIONS[EXTREME]['effects'][weather].get('damaged')
  if not effect:continue
  actor.custom_conditions['researcher_extreme_weather']={'weather':weather,'weather_id':record['id'],**effect,'source':EXTREME}


def _extreme_penalty(engine,actor,key):
 row=actor.custom_conditions.get('researcher_extreme_weather')
 if not isinstance(row,dict):return 0
 if not any(r['id']==row['weather_id'] for r in _extreme_records(engine)):
  actor.custom_conditions.pop('researcher_extreme_weather',None);return 0
 return row.get(key,0)


def damage_roll_modifier(engine,attacker):
 return _extreme_penalty(engine,attacker,'damage_roll')


def accuracy_modifier(engine,attacker):
 return _extreme_penalty(engine,attacker,'accuracy')


def weather_ended(engine,record):
 """weather_state.clear/boundary: the extreme effects end with their weather."""
 facts=record.get('researcher_extreme') if isinstance(record,dict) else None
 if facts is None:return
 import world_entities as W
 index=W.actor_index(engine)
 effect=DEFINITIONS[EXTREME]['effects'][record['weather']]
 for actor in index.values():
  row=actor.custom_conditions.get('researcher_extreme_weather')
  if isinstance(row,dict) and row.get('weather_id')==record['id']:actor.custom_conditions.pop('researcher_extreme_weather',None)
  if 'status' in effect and actor.entity_id in facts['statuses'] and effect['status'] in actor.conditions:engine.cure_status(actor,effect['status'])
 facts['ended_round']=engine.round_no


# ---------------------------------------------------------------- Paleontology
def fossil_restoration(engine,trainer,*,fossil_id,seconds,reason,hatch_details=None):
 """Extended restoration you perform: the hatched Pokemon has two fewer Tutor Points and a second basic Ability (or a GM hidden Ability)."""
 import world_entities as W,creation_fossil as FOSSIL
 W.require_actors(engine,trainer);d=qualify(engine,trainer,FOSSIL_RESTORATION);_text(reason,'restoration reason');_outside(engine)
 record=trainer.spec.get('fossils',{}).get(fossil_id)
 if not record or record.get('status')!='fossil':raise ValueError('unconsumed owned fossil instance required')
 def apply(e,t):
  st=state(t,create=True)
  st['fossils'].append({'fossil_id':fossil_id,'status':'pending','at':e.elapsed_seconds,'reason':reason})
  _extended(e,t,FOSSIL_RESTORATION,seconds)
  return FOSSIL.restore_native(e,t,fossil_id=fossil_id,hatch_details=hatch_details)
 return G.transition(engine,trainer,apply,include_rulings=True)


def _pending_fossil(trainer,fossil_id):
 st=trainer.spec.get(KEY)
 if st is None:return None
 return next((row for row in st.get('fossils',[]) if row['fossil_id']==fossil_id and row['status']=='pending'),None)


def fossil_restoration_declaration(engine,owner,fossil_id,declaration):
 """creation_fossil.restore_native: a declared Fossil Restoration lowers the birth Tutor Points by two (never below zero)."""
 pending=_pending_fossil(owner,fossil_id)
 if pending is None:return declaration
 value=deepcopy(declaration);base=value['hatch']['tutor_points'];delta=DEFINITIONS[FOSSIL_RESTORATION]['tutor_point_delta']
 value['hatch']['tutor_points']=max(0,base+delta)
 pending['tutor_points']={'native':base,'printed_delta':delta,'birth':value['hatch']['tutor_points'],'deficit':max(0,-(base+delta))}
 return value


def fossil_restoration_mark(engine,owner,fossil_id,egg):
 pending=_pending_fossil(owner,fossil_id)
 if pending is None:return
 egg[FOSSIL_MARK]={'trainer_id':owner.entity_id,'feature':FOSSIL_RESTORATION,'clause_id':clause(FOSSIL_RESTORATION),'tutor_points':deepcopy(pending['tutor_points']),'second_basic_ability':True,'gm_hidden_ability':None}
 pending.update(status='restored',egg_entity_id=egg['entity_id'])
 pending[FOSSIL_AUTHORITY]=1;pending['gm_hidden_ability']=None


def fossil_restoration_record(engine,egg,*,allow_legacy_pending=False):
 """Only the original completed restoration event authorizes the birth exception."""
 import world_entities as W,pokemon_entities as ENTITIES,creation_fossil as FOSSIL
 entry=ENTITIES.egg_index(engine).get(egg.get('entity_id'))
 if entry is None or entry[1] is not egg:raise ValueError('Fossil Restoration authority needs the actual registered egg')
 fossil=ENTITIES.egg_fossil(engine,egg);restorer=W.actor_index(engine).get(egg.get('restored_by'))
 if restorer is None or restorer.kind!='trainer':raise ValueError('Fossil Restoration authority needs the original restorer')
 st=state(restorer);records=[] if st is None else st.get('fossils',[])
 if type(records) is not list or any(type(row) is not dict for row in records):raise ValueError('Fossil Restoration authority needs actual event records')
 matches=[row for row in records if row.get('fossil_id')==fossil['id'] or row.get('egg_entity_id')==egg['entity_id']]
 if FOSSIL_MARK not in egg and not matches:return None
 facts=egg.get(FOSSIL_MARK)
 if type(facts) is not dict or len(matches)!=1:raise ValueError('Fossil Restoration authority needs its matching completed event')
 record=matches[0]
 if record.get('status')!='restored' or record.get('fossil_id')!=fossil['id'] or record.get('egg_entity_id')!=egg['entity_id']:
  raise ValueError('Fossil Restoration authority lost its completed fossil/egg event')
 contract=fossil.get(FOSSIL.CONTRACT,{})
 # Completed pre-interpretation producers retain their actual1/0/deficit1 basis.
 # No current default retroactively reallocates a hatched child's balance.
 expected=FOSSIL.native(legacy=FOSSIL.BIRTH_BASIS not in contract.get('request',{}));base=expected['hatch']['tutor_points'];delta=DEFINITIONS[FOSSIL_RESTORATION]['tutor_point_delta']
 points={'native':base,'printed_delta':delta,'birth':max(0,base+delta),'deficit':max(0,-(base+delta))}
 expected['hatch']['tutor_points']=points['birth']
 for observed in (record.get('tutor_points'),facts.get('tutor_points')):
  if type(observed) is not dict or set(observed)!=set(points):raise ValueError('Fossil Restoration authority needs its actual Tutor Point facts')
  for key in points:C.integer(observed[key],'Fossil Restoration '+key+' Tutor Points')
 if egg.get('source')!=FOSSIL.SOURCE or fossil.get('restored_by')!=restorer.entity_id or contract.get('request',{}).get('declaration')!=expected or egg.get(FOSSIL.BIRTH)!=expected['hatch'] or record.get('tutor_points')!=points:
  raise ValueError('Fossil Restoration authority disagrees with source or birth Tutor Points')
 chosen=facts.get('gm_hidden_ability')
 wanted={'trainer_id':restorer.entity_id,'feature':FOSSIL_RESTORATION,'clause_id':clause(FOSSIL_RESTORATION),'tutor_points':points,'second_basic_ability':True,'gm_hidden_ability':chosen}
 if facts!=wanted or facts.get('second_basic_ability') is not True:
  raise ValueError('Fossil Restoration authority facts disagree with the original event')
 if FOSSIL_AUTHORITY in record and (type(record[FOSSIL_AUTHORITY]) is not int or record[FOSSIL_AUTHORITY]!=1 or 'gm_hidden_ability' not in record):
  raise ValueError('Fossil Restoration authority schema needs its explicit GM selection field')
 if 'gm_hidden_ability' in record and chosen!=record['gm_hidden_ability']:
  raise ValueError('Fossil Restoration authority facts disagree with the original event')
 C.integer(record.get('at'),'Fossil Restoration event time',0,egg['produced_at']-1);_text(record.get('reason'),'Fossil Restoration event reason')
 if chosen is not None:
  basic,hidden=_basic_abilities(engine,_species(engine,egg['species'])['name'])
  if type(chosen) is not dict or set(chosen)!= {'ability','reason','at'} or len(basic)!=1 or chosen.get('ability') not in hidden:
   raise ValueError('Fossil Restoration authority needs the actual GM hidden Ability choice')
  _text(chosen['reason'],'Fossil Restoration GM choice reason');C.integer(chosen['at'],'Fossil Restoration GM choice time',egg['produced_at'],engine.elapsed_seconds)
  if 'gm_hidden_ability' not in record and not allow_legacy_pending:
   raise ValueError('legacy Fossil Restoration choice requires explicit GM confirmation with confirm_legacy=True')
 confirmation=record.get('legacy_hidden_ability_confirmation')
 if confirmation is not None:
  if type(confirmation) is not dict or set(confirmation)!={'trainer_id','ability','reason','at'} or record.get(FOSSIL_AUTHORITY)!=1 or chosen is None or confirmation.get('ability')!=chosen['ability']:
   raise ValueError('Fossil Restoration legacy confirmation disagrees with the retained GM choice')
  _text(confirmation['trainer_id'],'Fossil Restoration legacy confirming owner');confirmer=W.actor_index(engine).get(confirmation['trainer_id'])
  if confirmer is None or confirmer.kind!='trainer':raise ValueError('Fossil Restoration legacy confirmation needs its actual confirming owner')
  _text(confirmation['reason'],'Fossil Restoration legacy confirmation reason');C.integer(confirmation['at'],'Fossil Restoration legacy confirmation time',chosen['at'],engine.elapsed_seconds)
 return record


def choose_hidden_ability(engine,trainer,egg_entity_id,*,ability,reason,confirm_legacy=False):
 """GM choice, or explicit confirmation of the same retained legacy choice, for Fossil Restoration."""
 import world_entities as W,pokemon_entities as ENTITIES
 W.require_actors(engine,trainer);_text(reason,'GM hidden Ability reason')
 if type(confirm_legacy) is not bool:raise ValueError('explicit boolean legacy Fossil Restoration confirmation required')
 def apply(e,t):
  entry=ENTITIES.egg_index(e).get(egg_entity_id)
  if entry is None or FOSSIL_MARK not in entry[1]:raise ValueError('actual unhatched Fossil Restoration egg required')
  egg=entry[1]
  if egg['hatched']:owned=confirm_legacy and _trainer_of(e,W.actor_index(e).get(egg.get('pokemon_id'))) is t
  else:owned=entry[0] is t
  if not owned:raise ValueError('actual owned legacy Fossil Restoration egg or hatched child required' if confirm_legacy else 'actual unhatched Fossil Restoration egg required')
  record=fossil_restoration_record(e,egg,allow_legacy_pending=confirm_legacy);basic,hidden=_basic_abilities(e,_species(e,egg['species'])['name'])
  if confirm_legacy:
   chosen=egg[FOSSIL_MARK]['gm_hidden_ability']
   if FOSSIL_AUTHORITY in record or 'gm_hidden_ability' in record or chosen is None:raise ValueError('only an unconfirmed actual legacy Fossil Restoration choice can be confirmed')
   if ability!=chosen['ability']:raise ValueError('legacy Fossil Restoration confirmation must retain exactly the existing GM Ability')
   record[FOSSIL_AUTHORITY]=1;record['gm_hidden_ability']=deepcopy(chosen)
   record['legacy_hidden_ability_confirmation']={'trainer_id':t.entity_id,'ability':ability,'reason':reason,'at':e.elapsed_seconds}
   e.gm._rec('Fossil Restoration legacy hidden Ability confirmation',None,ability,reason,t)
   return deepcopy(egg[FOSSIL_MARK])
  if 'legacy_hidden_ability_confirmation' in record:raise ValueError('confirmed legacy Fossil Restoration choice cannot be reset')
  if len(basic)!=1:raise ValueError('the species already has two basic Abilities; no hidden Ability choice applies')
  if ability not in hidden:raise ValueError('GM must choose one of the species hidden Abilities: '+', '.join(hidden))
  egg[FOSSIL_MARK]['gm_hidden_ability']={'ability':ability,'reason':reason,'at':e.elapsed_seconds}
  record[FOSSIL_AUTHORITY]=1
  record['gm_hidden_ability']=deepcopy(egg[FOSSIL_MARK]['gm_hidden_ability'])
  e.gm._rec('Fossil Restoration hidden Ability',None,ability,reason,t)
  return deepcopy(egg[FOSSIL_MARK])
 return G.transition(engine,trainer,apply,include_rulings=True)


def fossil_birth_details(engine,owner,egg,details):
 """creation_fossil._hatch: the restored Pokemon is born with both basic Abilities, or one basic plus the GM-chosen hidden Ability."""
 if fossil_restoration_record(engine,egg) is None:return details
 facts=egg[FOSSIL_MARK]
 if type(details) is not dict:raise ValueError('GM hatch details must be a mapping')
 basic,hidden=_basic_abilities(engine,_species(engine,egg['species'])['name'])
 if len(basic)>=2:expected=basic[:2]
 else:
  chosen=facts.get('gm_hidden_ability')
  if chosen is None:raise ValueError('single-basic-Ability species needs the GM-chosen hidden Ability before hatching (choose_hidden_ability)')
  expected=[*basic,chosen['ability']]
 given=details.get('abilities')
 if given and sorted(given)!=sorted(expected):raise ValueError('Fossil Restoration birth Abilities must be exactly '+', '.join(expected))
 return dict(details,abilities=list(expected))


def ancient_heritage(engine,trainer,pokemon,*,seconds,reason):
 d=DEFINITIONS[ANCIENT]
 result=_teach_feature_move(engine,trainer,pokemon,ANCIENT,d['move'],seconds=seconds,reason=reason,allowed_routes=['level_up','tm','tutor','egg'],free_routes=['level_up'],fossil=True)
 return result


def ancient_heritage_active(engine,pokemon):
 record=pokemon.spec.get('move_learning',{}).get(DEFINITIONS[ANCIENT]['move'])
 if not isinstance(record,dict) or record.get('researcher_feature')!=ANCIENT:return False
 owner=_trainer_of(engine,pokemon)
 return owner is not None and owns(owner,ANCIENT)


def choose_ancient_power_class(engine,pokemon,damage_class):
 """Static Ancient Heritage: before using Ancient Power, declare physical or special for an 18+ roll."""
 import world_entities as W
 W.require_actors(engine,pokemon)
 if damage_class not in DEFINITIONS[ANCIENT]['static']['choice']:raise ValueError('choose 물리 or 특수')
 if not ancient_heritage_active(engine,pokemon):raise ValueError('Ancient Heritage Ancient Power with its owning Researcher required')
 pokemon.spec['researcher_ancient_power_choice']=damage_class
 return damage_class


def after_accuracy(engine,attacker,move,natural):
 """use_move_on after the accuracy roll: Ancient Power at 18+ takes the declared damage class."""
 if not isinstance(move,dict) or move.get('id')!=DEFINITIONS[ANCIENT]['move'] or attacker.kind!='pokemon':return move
 choice=attacker.spec.pop('researcher_ancient_power_choice',None)
 if choice is None or natural is None or natural<DEFINITIONS[ANCIENT]['static']['threshold']:return move
 if not ancient_heritage_active(engine,attacker):return move
 engine.log('    고대 유산: 18+ 원시의힘 → '+choice+' 데미지',SOURCE)
 return dict(move,**{'class':choice},_researcher_ancient_heritage=choice)


def genetic_memory(engine,trainer,pokemon,move,*,route,seconds,reason):
 """Daily x2 Extended: a fossil Pokemon learns any Egg-list or Tutor-list Move for two Tutor Points; once per route per Pokemon; the Egg route is outside the TM/Tutor pool."""
 d=DEFINITIONS[GENETIC];mid=engine.r.move_id(move)
 if mid is None:raise ValueError('actual selected Move required')
 if route not in d['routes']:raise ValueError('Genetic Memory route is egg or tutor')
 st=state(trainer)
 used=(st or {}).get('genetic_memory',{}).get(pokemon.entity_id,{})
 if route in used:raise ValueError('Genetic Memory already used the '+route+' route on this Pokemon')
 result=_teach_feature_move(engine,trainer,pokemon,GENETIC,mid,seconds=seconds,reason=reason,allowed_routes=d['routes'],free_routes=[],frequency=d['frequency'],fossil=True,route=route,
  details={'genetic_memory_route':route,'outside_pool_limit':route=='egg'})
 state(trainer,create=True)['genetic_memory'].setdefault(pokemon.entity_id,{})[route]={'move':mid,'at':engine.elapsed_seconds}
 return dict(result,route=route)


def pool_exempt(spec,mid):
 """move_state: a Genetic Memory Egg-route Move is not counted against the TM/Tutor pool limit."""
 record=spec.get('move_learning',{}).get(mid)
 return isinstance(record,dict) and record.get('researcher_feature')==GENETIC and record.get('genetic_memory_route')=='egg'


# ---------------------------------------------------------------- Prehistoric Bond relics
def relic_definition(name):
 if not isinstance(name,str):return None
 for stat,row in DEFINITIONS[BOND]['relics'].items():
  if name.startswith(row['prefix']):return stat,row
 return None


def craft_relic(engine,trainer,pokemon,*,relic,minutes,tie_reason=None):
 """Prehistoric Bond: one held item from the remains, keyed to the restored individual's highest nature-adjusted base stat."""
 if relic not in DEFINITIONS[BOND]['relics']:raise ValueError('relic stat required: hp, atk, def, spa, spd or spe')
 qualify(engine,trainer,BOND)
 return RF.craft_relic(engine,trainer,pokemon,relic=relic,minutes=minutes,tie_stat=relic,tie_reason=tie_reason)


def relic_effects(stat):
 return {'hp':[{'type':'save_mod','value':2}],
  'atk':[{'type':'crit_range_mod','value':1,'moves':'damaging'}],
  'def':[{'type':'rule','note':'선사 면도칼: 데미지 근접 공격으로 맞았을 때 반응으로 공격자 소량 체력 손실 (researcher_fields.relic_after_hit)'}],
  'spa':[{'type':'effect_range_mod','value':1,'target':'self'}],
  'spd':[{'type':'damage_reduction','value':5,'target':'self','vs':'ranged'}],
  'spe':[{'type':'rule','note':'띠 유물: 변화기에 대해 +2 회피 (researcher_fields.evasion_bonus)'}]}[stat]


def set_razors_reaction(engine,pokemon,enabled):
 """Standing declaration: the holder uses its reaction on each qualifying melee hit."""
 import world_entities as W
 W.require_actors(engine,pokemon)
 if type(enabled) is not bool:raise ValueError('explicit reaction policy required')
 pokemon.spec['researcher_razors_reaction']=enabled
 return enabled


def _held_relic(engine,pokemon,stat):
 import held_equipment as HELD,items as ITEMS
 HELD.validate(pokemon);matches=[]
 for held in HELD.entries(pokemon):
  name=held['name'];row=relic_definition(name)
  if row is None or row[0]!=stat or held.get('effects_pending'):continue
  registered=getattr(pokemon,'_item_reg',{}).get(held.get('registration_key'))
  if registered is None or not ITEMS.equipment_benefit_active(pokemon,registered):continue
  effects=RF.relic_effects(engine,pokemon,name)
  if effects is not None and effects[0]:matches.append(name)
 if len(matches)>1:raise ValueError('multiple active relic effect sources need an explicit stacking policy')
 return matches[0] if matches else None


def relic_after_hit(engine,attacker,target,move,dealt):
 """Prehistoric Razors: after a damaging melee hit, the holder's reaction makes the attacker lose a Tick."""
 if type(dealt) is not int or dealt<=0 or move.get('class') not in ('물리','특수') or '근접' not in str(move.get('range','')):return None
 if getattr(target,'kind',None)!='pokemon':return None
 if not getattr(attacker,'side',None) or not getattr(target,'side',None) or attacker.side==target.side:return None
 name=_held_relic(engine,target,'def')
 if name is None or not target.spec.get('researcher_razors_reaction'):return None
 if attacker is target or attacker.fainted:return None
 import turn as TURN
 if not TURN.can_act(engine,target):return None
 loss=engine.tick_loss(attacker)
 engine.lose_hp(attacker,loss,source=name)
 target.spec.setdefault('researcher_relic_reactions',[]).append({'relic':name,'attacker_id':attacker.entity_id,'move_id':move.get('id'),'hp_loss':loss,'round':engine.round_no})
 engine.log('    선사 면도칼: '+attacker.name+' 소량의 체력 손실 '+str(loss),SOURCE)
 return loss


def evasion_bonus(engine,target,move):
 """Relic Sash: +2 Evasion against Status Moves."""
 if target is None or not isinstance(move,dict) or move.get('class')!='변화':return 0
 if getattr(target,'kind',None)!='pokemon' or _held_relic(engine,target,'spe') is None:return 0
 return 2


# ---------------------------------------------------------------- Pokemon Caretaking
_PUSHER_ACQUISITION=ContextVar('pusher_acquisition',default=None)


def _pusher_edge(rules,edge):
 import poke_edge_variants as V
 row=V.resolve(rules,edge)
 if row is not None:return row['policy']
 return rules.selection.resolve_name(edge,('poke_edge/',)) if isinstance(edge,str) and not edge.startswith('poke_edge/') else edge


def pusher_funds(e,trainer,target,edge):
 """Pusher automatically grants only its nine listed, qualifying Poke Edges."""
 if getattr(trainer,'kind',None)!='trainer' or not owns(trainer,PUSHER):return None
 if getattr(target,'kind',None)!='pokemon' or target.spec.get('trainer_id')!=trainer.entity_id:return None
 try:resolved=_pusher_edge(e.r,edge)
 except Exception:return None
 if resolved not in DEFINITIONS[PUSHER]['free_poke_edges']:return None
 qualify(e,trainer,PUSHER)
 return resolved


def pusher_acquiring(e,trainer,target,source=None):
 """Only this native acquisition scope may omit ordinary teaching requirements."""
 current=_PUSHER_ACQUISITION.get()
 if current is None or current[:2]!=(trainer.entity_id,target.entity_id):return False
 return (source is None or source==current[2]) and pusher_funds(e,trainer,target,current[2])==current[2]


def pusher_receipt(rules,receipt):
 """Retain nominal native costs and old funding history; expose actual zero payment."""
 row=receipt.get('pusher')
 if row is None:return receipt['point_cost']
 if type(row) is not dict or row.get('feature')!=PUSHER or row.get('clause_id')!=clause(PUSHER):raise ValueError('actual Pusher source receipt required')
 _text(row.get('trainer_id'),'historical Pusher provider')
 if row.get('trainer_id')!=receipt.get('trainer_id') or type(row.get('net_point_cost')) is not int or row['net_point_cost']!=0:raise ValueError('actual Pusher provider and zero payment required')
 if receipt.get('source') not in DEFINITIONS[PUSHER]['free_poke_edges'] or type(row.get('edge')) is not str or not row['edge'].strip():raise ValueError('Pusher receipt must name its actual listed Edge')
 if rules is not None and _pusher_edge(rules,row['edge'])!=receipt['source']:raise ValueError('Pusher receipt Edge source changed')
 C.integer(receipt.get('point_cost'),'nominal Pusher native Edge cost',1)
 if 'acquisition' in row:
  if row['acquisition']!='automatic' or type(row.get('seconds')) is not int or row['seconds']!=0 or receipt.get('training_source')!=PUSHER:raise ValueError('actual automatic Pusher acquisition required')
 refund=receipt.get('refund',{})
 if type(refund) is not dict:raise ValueError('actual Pusher refund receipt required')
 if row.get('acquisition')=='automatic' and receipt.get('status')=='refunded' and 'net_points' not in refund:raise ValueError('actual automatic Pusher zero refund required')
 if 'net_points' in refund and (type(refund['net_points']) is not int or refund['net_points']!=0):raise ValueError('Pusher cannot refund unspent Tutor Points')
 return 0


def teach_funded(engine,trainer,target,edge,native):
 """Resolve a static grant through the native Edge's choices and qualification.
 native(engine,trainer,target) runs on the staged subjects."""
 import pokemon_teaching as TEACH
 import poke_edge_variants as V
 resolved=pusher_funds(engine,trainer,target,edge)
 if resolved is None:raise ValueError('actual qualifying Pusher acquisition required')
 definition=V.resolve(engine.r,edge) or V.resolve(engine.r,resolved)
 cost=definition.get('tutor_cost',definition.get('point_cost',1)) if definition is not None else 1
 C.integer(cost,'nominal native Pusher Edge cost',1)
 def apply(e,q,t):
  before=TEACH._balance(q.spec);q.spec['tutor_points']=before+cost
  token=_PUSHER_ACQUISITION.set((t.entity_id,q.entity_id,resolved))
  try:result=native(e,t,q)
  finally:_PUSHER_ACQUISITION.reset(token)
  receipts=q.spec.get('learned_poke_edges',[])
  if not receipts or receipts[-1].get('source')!=resolved or receipts[-1].get('point_cost')!=cost:raise ValueError('Pusher funding requires the actual native Poke Edge receipt')
  if TEACH._balance(q.spec)!=before:raise ValueError('Pusher funding must leave the Tutor Point balance unchanged')
  receipts[-1]['training_source']=PUSHER
  receipts[-1]['pusher']={'trainer_id':t.entity_id,'feature':PUSHER,'clause_id':clause(PUSHER),'edge':edge,'net_point_cost':0,'acquisition':'automatic','seconds':0}
  pusher_receipt(e.r,receipts[-1])
  e.log('  '+t.name+': 후원자 - '+q.name+' '+str(edge)+' 가르침 포인트 없이 획득',SOURCE)
  return dict(result,point_cost=0,pusher_net_point_cost=0,seconds=0)
 return G.transition(engine,target,apply,participants=(trainer,))


def special_uses(e,trainer):
 rank=S.effective_rank(e.r,trainer,'포켓몬학')
 return max(0,rank-2)


def special_quality(engine,trainer,egg_entity_id,*,quality,reason):
 """Free Action on one of your hatching eggs: the GM-decided special quality; once per Pokemon Education rank above Untrained."""
 import world_entities as W,pokemon_entities as ENTITIES
 W.require_actors(engine,trainer);qualify(engine,trainer,SPECIAL);_text(quality,'GM-decided special quality');_text(reason,'reason')
 def apply(e,t):
  st=state(t,create=True)
  if len(st['special_quality'])>=special_uses(e,t):raise ValueError("This One's Special may be activated once per Pokemon Education rank above Untrained")
  entry=ENTITIES.egg_index(e).get(egg_entity_id)
  if entry is None or entry[0] is not t or entry[1]['hatched']:raise ValueError('actual unhatched egg owned by this trainer required')
  egg=entry[1]
  if QUALITY_MARK in egg:raise ValueError('this egg already has its special quality')
  _free_action(e,t,SPECIAL)
  egg[QUALITY_MARK]={'quality':quality,'trainer_id':t.entity_id,'feature':SPECIAL,'clause_id':clause(SPECIAL),'reason':reason,'at':e.elapsed_seconds}
  st['special_quality'].append({'egg_entity_id':egg['entity_id'],'quality':quality,'at':e.elapsed_seconds})
  e.gm._rec('special quality',None,quality,reason,t)
  return deepcopy(egg[QUALITY_MARK])
 return G.transition(engine,trainer,apply,include_rulings=True)


def birth_quality(engine,egg,pokemon):
 """creation_egg.commit_birth: the hatched Pokemon carries its GM-decided special quality."""
 facts=egg.get(QUALITY_MARK)
 if facts is not None:pokemon.spec['special_quality']=deepcopy(facts)


def rebalance(engine,trainer,pokemon,*,option,stats,investment,seconds,reason,request_id):
 """Extended, 2 TP, once per Pokemon: +1 all / +2 two / +3 one base stat, then redistribute the stat points."""
 import world_entities as W,pokemon_teaching as TEACH,growth_stats as GROWTH
 from builder import STATS
 W.require_actors(engine,trainer,pokemon);d=qualify(engine,trainer,REBALANCE);_text(reason,'Re-Balancing reason');_text(request_id,'request');_outside(engine)
 _owned_pokemon(engine,trainer,pokemon)
 if option not in d['options']:raise ValueError('Re-Balancing option: all_plus_one, two_plus_two or one_plus_three')
 rule=d['options'][option]
 if 'all' in rule:
  if stats:raise ValueError('all_plus_one names no stats')
  deltas=dict.fromkeys(STATS,rule['all'])
 else:
  if not isinstance(stats,list) or len(stats)!=rule['count'] or len(set(stats))!=len(stats) or any(s not in STATS for s in stats):raise ValueError('choose exactly '+str(rule['count'])+' distinct base stats')
  deltas={s:rule['delta'] for s in stats}
 if pokemon.spec.get('researcher_rebalance') is not None:raise ValueError('a Pokemon may be targeted by Re-Balancing only once')
 if TEACH._balance(pokemon.spec)<d['tutor_points']:raise ValueError('target needs two actual Tutor Points')
 if not isinstance(investment,dict) or set(investment)!=set(STATS):raise ValueError('explicit redistributed investment for every stat required')
 def apply(e,t,q):
  _extended(e,t,REBALANCE,seconds,participants=(q,))
  old_stats=deepcopy(q.spec['stats']);old_hp=q.hp;old_max=max(1,q.base_max_hp)
  if q.spec.get('form_allocations'):raise ValueError('Re-Balancing of a multi-form allocation needs its explicit form migration')
  current=GROWTH.project_actor(e,q)   # the tracked allocation before the new base source exists
  q.spec['researcher_rebalance']={'feature':REBALANCE,'clause_id':clause(REBALANCE),'trainer_id':t.entity_id,'option':option,'deltas':deltas,'at':e.elapsed_seconds,'request_id':request_id}
  from builder import species_lookup
  from actor_templates import has_soulless
  import pokemon_stat_edges as EDGES
  nature=q.spec.get('nature')
  plan=GROWTH.compose(species_lookup(e.r,q.spec['species'])['base_stats'],investment,points=sum(current['permanent']['investment'].values()),nature=nature,rules=e.r,
   excluded=('hp',) if has_soulless(q.spec) else (),relation_exempt=EDGES.exemptions(e.r,q.spec),
   base_sources=EDGES.base_sources(e.r,q.spec),point_sources=EDGES.point_sources(e.r,q.spec))
  vitamins=current['permanent']['contributions']['vitamins']
  baseline={stat:plan['stats'][stat]+vitamins[stat] for stat in STATS}
  effective=G.prepare_stat_baseline(q,baseline)
  q.spec['stats']=deepcopy(baseline);q.stats=deepcopy(effective);G.commit_stat_baseline(q)
  q.spec.setdefault('allocation_migrations',[]).append({'kind':'rebalance','species':q.spec['species'],'level':q.level,'previous_nature':nature,'nature':nature,
   'previous_stats':old_stats,'source':SOURCE,'reason':'Re-Balancing: '+reason,'plan':deepcopy(plan),'growth_event_offset':len(q.spec.get('growth_investment_events',[])),'researcher_rebalance':deepcopy(deltas)})
  import arithmetic_policy as M,bandages as BANDAGES
  maximum=q.base_max_hp;proposed=M.ratio(old_hp*maximum,old_max)
  q.hp=max(0,min(maximum,proposed));BANDAGES.on_hp_change(e,q,old_hp,q.hp)
  q._state_revision=getattr(q,'_state_revision',0)+1
  TEACH._debit_points(q.spec,d['tutor_points'])
  state(t,create=True)['rebalanced'].append({'pokemon_id':q.entity_id,'option':option,'deltas':deltas,'at':e.elapsed_seconds})
  e.log('  '+t.name+': 리밸런스 - '+q.name+' 기본 스탯 '+str(deltas)+', 스탯 재분배',REBALANCE)
  return {'pokemon_id':q.entity_id,'deltas':deltas,'stats':deepcopy(q.spec['stats']),'projection':GROWTH.project_actor(e,q)}
 return G.transition(engine,trainer,apply,participants=(pokemon,),include_rulings=True)


def base_sources(rules,spec):
 """pokemon_stat_edges.base_sources: the Re-Balancing base stat bonus of this individual."""
 row=spec.get('researcher_rebalance')
 if row is None:return []
 from builder import STATS
 if type(row) is not dict or row.get('feature')!=REBALANCE or type(row.get('deltas')) is not dict or set(row['deltas'])-set(STATS):raise ValueError('invalid Re-Balancing record')
 return [{'source':SOURCE,'values':{stat:row['deltas'].get(stat,0) for stat in STATS}}]


# ---------------------------------------------------------------- validation
def validate(engine):
 import world_entities as W,weather_state as WEATHER
 index=W.actor_index(engine)
 for actor in index.values():
  st=actor.spec.get(KEY)
  if st is not None:
   if actor.kind!='trainer':raise ValueError('Researcher field state requires a trainer')
   if type(st) is not dict or st.get('version')!=1:raise ValueError('exact Researcher field state required')
   inv=actor.spec.get('items',{})
   for key,row in st['patches'].items():
    if not key.startswith(PATCH_PREFIX) or row.get('feature')!=PATCH or row.get('item_id')!=key[len(PATCH_PREFIX):]:raise ValueError('invalid Patch item record')
    C.integer(inv.get(key,0),'owned Patch count',0)
   for key,row in st['blends'].items():
    if not key.startswith(BLEND_PREFIX) or row.get('feature')!=BLEND or len(row.get('components',[]))!=2 or type(row.get('extended_only')) is not bool:raise ValueError('invalid Blend item record')
    C.integer(inv.get(key,0),'owned Blend count',0)
   held=st.get('held_shard')
   if held is not None and (held.get('color') not in __import__('crafting_resources').SHARDS or held.get('hand') not in ('주요손','반대손')):raise ValueError('invalid held shard record')
   for row in st['chemistry']['exposures']:
    if row.get('kind') not in ('pester','spray') or type(row.get('targets')) is not list or type(row.get('caustic_used')) is not bool:raise ValueError('invalid Caustic exposure record')
  for sid,row in _climatology_sources(actor).items():
   if actor.kind!='trainer' or sid!=CLIMATOLOGY_PREFIX+actor.entity_id or row.get('grants',{}).get('abilities')!=[DEFINITIONS[CLIMATOLOGY]['ability']]:raise ValueError('invalid Climatology Ability grant')
   if not owns(actor,CLIMATOLOGY):raise ValueError('Climatology Ability grant lost its Feature')
  for sid,row in _seed_sources(actor).items():
   facts=row.get('researcher_seed')
   if actor.kind!='trainer' or type(facts) is not dict or facts.get('day')!=actor.spec.get('frequency_state',{}).get('day',0) or row.get('grants',{}).get('moves',[])!=[sid.split(':')[-1]]:
    raise ValueError('Seed Bag Move grant is not justified by the current day')
  if actor.kind=='pokemon':
   base_sources(engine.r,actor.spec);vitamin_equivalents(actor.spec)
   row=actor.spec.get('researcher_extreme_weather')
   if row is not None and not isinstance(row,dict):raise ValueError('invalid extreme weather marker')
 for record in _extreme_records(engine):
  facts=record['researcher_extreme']
  if type(facts) is not dict or facts.get('trainer_id') not in index or record['weather'] not in DEFINITIONS[EXTREME]['effects']:raise ValueError('invalid Extreme Weather record')
 s=getattr(engine,WEATHER.KEY,None)
 if s:
  for layer in s.get('layers',[]):
   facts=layer.get('temperature_control')
   if facts is not None and (facts.get('trainer_id') not in index or not s.get('active')):raise ValueError('Temperature Control layer without its coexisting weather')
 return True
