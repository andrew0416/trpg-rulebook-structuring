"""PTK ch04:1932-1982 Chronicler: records, archives and their actual consumers.

The class is a template. Committed static acquisitions own archives; a
provisional record observes an actual actor, a witnessed Move or the present
place, and an Extended archival binds it to an owned archive. Consumers read
live archives: Profile skill bonus, Technique evasion, Travel ability and
Perception bonus, Archive Tutor, Targeted Profiling and Cinematic Analysis.
"""
from copy import deepcopy
from pathlib import Path
import json
import re
import common_checks as C
import state_grants as G

_data=json.loads((Path(__file__).resolve().parents[1]/'data/chronicler-definitions.json').read_text(encoding='utf8'))
DEFINITIONS=_data['features'];ARCHIVES=_data['archives'];RECORD_KINDS=tuple(_data['record_kinds'])
FEATURES={u:tuple(d['span']) for u,d in DEFINITIONS.items()}
CLASS='class/기록자';TRAINING='feat/자료보관-훈련';TUTOR='feat/자료보관-가르침'
PROFILING='feat/대상-프로파일링';PARTY='feat/관측-파티';CINEMATIC='feat/시네마틱-분석'
ANALYSES=DEFINITIONS[CINEMATIC]['analyses']
PERCEPTION=_data['perception_skill']
ENGLISH={d['english']:u for u,d in DEFINITIONS.items()}
KEY='chronicler'                      # trainer.spec: records, archives, tutoring, analyses
CHOICES='chronicler_archive_choices'  # trainer.spec: {'class/기록자':'profile','feat/자료보관-훈련:1':'technique',...}
TRAVEL_ABILITY='chronicler_travel_ability'  # trainer.spec: printed Keen Eye or Perception choice
PLACE='chronicler_place'              # actor.spec: GM observed current place
PRIORITY='chronicler_priority'        # ally.spec: pending Situational Awareness entitlement
TRAVEL_PREFIX='chronicler-travel:'
PERCEPTION_ABILITY='ability/감지'
PERCEPTION_PLAYTEST='ability/감지-playtest'
ARCHIVE_OF_KIND={kind:name for name,row in ARCHIVES.items() for kind in row['record_kinds']}
CSV_RECORD='C2CSV/input/db/feats.csv:R308:main'
CSV_TUTOR='C2CSV/input/db/feats.csv:R311:main'
CSV_SHA='4435ff1c462a211564c85d2c1c9a2ac6e7c790c7545e1ad7056d32888b2367bd'


def _edition(rules,value,expected):
 if value is None:return None
 if value!=expected:raise ValueError('exact reviewed Chronicler source edition required')
 from source_context import verified_source
 number=308 if expected==CSV_RECORD else 311
 rules.ruleset.require({'id':value,'source':{'file':'db/feats.csv','record_span':[number,number]}})
 verified_source(rules,{'file':'input/db/feats.csv','sha256':CSV_SHA,'record_span':[number,number]},label='Chronicler CSV')
 return value


def uid(name):
 return name if name in FEATURES else ENGLISH[name]


def clause(feature):
 return DEFINITIONS[feature]['clause_id']


def _text(value,label):
 if type(value) is not str or not value.strip():raise ValueError(label+' required')
 return value


# ---------------------------------------------------------------- acquisition
def records(actor,feature=None,active=False):
 import trainer_feature_acquisition as T
 return [record for _, record in T.static_family_acquisitions(actor, FEATURES, feature, active=active)]


def acquired(actor,feature,rank=None):
 rows=[r for r in records(actor,feature,True) if rank is None or r['snapshot'].get('rank_number')==rank]
 if feature==TRAINING and rank is None:return rows
 if len(rows)>1:raise ValueError('one exact acquired Chronicler Feature required')
 return rows[0] if rows else None


def choice_key(feature,rank=None):
 return feature+':'+str(rank) if feature==TRAINING else feature


def owned_archives(actor,*,exclude=(),active=True):
 """Archives granted by committed acquisitions: class choice plus each Archival Training rank."""
 result={}
 for row in records(actor,active=active):
  if row['feature_id'] not in (CLASS,TRAINING) or row['feature_id'] in exclude:continue
  archive=row['snapshot'].get('archive')
  if archive in result:raise ValueError('duplicate acquired Chronicler archive')
  result[archive]={'request_id':row['request_id'],'feature':row['feature_id'],'rank':row['snapshot'].get('rank_number'),'travel_ability':row['snapshot'].get('travel_ability')}
 return result


def _travel_ability(rules,name):
 """Printed Keen Eye/Perception choice resolved against the selected Ability catalog."""
 # The class's bilingual 통찰 (Perception) is not the CSV's 통찰 (Frisk).
 perception_names={'통찰','Perception','감지','감지 [Playtest]',PERCEPTION_ABILITY,PERCEPTION_PLAYTEST}
 if name not in (*ARCHIVES['travel']['abilities'],*perception_names):raise ValueError('choose the printed Keen Eye or Perception Ability for the Travel Archive')
 requested='감지' if name in ('통찰','Perception') else name
 import move_state as M
 registration=M.ability_registration(rules,requested)
 if registration is not None:return registration['name']
 from ruleset import UnresolvedRuleSelection,ExcludedRuleSelection
 try:
  selected=rules.selection.resolve(requested) if requested.startswith('ability/') else rules.selection.resolve_name(requested,('ability/',))
  rules.selection.require_supported_version(selected)
 except (UnresolvedRuleSelection,ExcludedRuleSelection,ValueError,KeyError) as error:
  raise ValueError('selected '+name+' Ability variant required in the current ruleset for the Travel Archive: '+str(error)) from error
 title=rules.selection.units[selected].get('title')
 if not isinstance(title,str) or not title.strip():raise ValueError('selected Travel Archive Ability has no catalog title')
 if name in perception_names:perception_definition(rules,selected)
 return title


def validate_core_perception(rules,row):
 """The bilingual class reference supplies identity; the core excerpt supplies its full effect."""
 from source_context import verified_source
 contract={'type':'ally_area_shift','action':'shift','payment':'next','damaging_only':False}
 if (row.get('id')!=PERCEPTION_ABILITY or row.get('name')!='감지' or row.get('eng')!='Perception'
     or row.get('frequency')!='임의' or row.get('native_contract')!=contract or row.get('effects')!=[]):
  raise ValueError('reviewed core Perception definition required')
 source=row['source'];official=row['official_source']
 if (source.get('file')!='ch04-trainer-classes.md' or source.get('lines')!=[1945,1947]
     or source.get('sha256')!=_data['source_sha256']
     or source.get('additional_snapshots')!={official['extract']:official['sha256']}
     or official.get('extract')!='source-audit/core-perception.txt'):
  raise ValueError('core Perception exact bilingual source boundary required')
 verified_source(rules,{'file':'input/'+source['file'],'sha256':source['sha256']},label='Chronicler Perception reference')
 text=verified_source(rules,{'file':official['extract'],'sha256':official['sha256']},label='core Perception',source_root='source-audit').decode('utf8')
 if text!='Ability: Perception\nAt-Will – Shift Action, Interrupt Trigger: An ally uses an area-of-effect attack that would hit you Effect: You may Shift to remove yourself from the areaof-effect.\n':
  raise ValueError('complete core Perception excerpt required')


def perception_definition(rules,source):
 """Keep the explicit core and Playtest Perception identities and costs separate."""
 if source not in (PERCEPTION_ABILITY,PERCEPTION_PLAYTEST) or rules._selected_rule(source)!=source:
  raise ValueError('exact selected Perception Ability source required')
 if source==PERCEPTION_ABILITY:
  row=rules.core_abilities[source];validate_core_perception(rules,row)
  return row['native_contract']
 from source_context import verified_source
 verified_source(rules,{'file':'input/db/abilities.csv','sha256':'87efebd17b0a5fe09c9db060a16a8844cf41be53d65eb35716cf62f80a177fae'},label='Playtest Perception')
 unit=rules.selection.units[source]
 expected=[{'type':'evasion_mod','value':1,'target':'self'},
           {'type':'reaction','trigger':"about to be hit by ally's damaging AoE",'effect':'free shift out before resolution'}]
 if (unit.get('eng')!='Perception' or unit.get('title')!='감지 [Playtest]'
     or unit['source'].get('record_span')!=[10,10] or rules.ability_effects.get(unit['title'])!=expected):
  raise ValueError('complete exact Playtest Perception source and effects required')
 return {'type':'ally_area_shift','action':'free','payment':None,'damaging_only':True}


def acquisition_snapshot(engine,actor,feature,rank=None):
 import skill_modifiers as S
 d=DEFINITIONS[feature]
 if feature==TRAINING:
  if rank not in (1,2):raise ValueError('explicit Archival Training rank 1 or 2 required')
 elif rank is not None:raise ValueError('this Chronicler Feature is not Ranked')
 snapshot={'perception':S.rank(engine.r,actor,PERCEPTION)[2],'parents':[] if feature==CLASS else [r['request_id'] for r in records(actor,CLASS,True)]}
 if feature==TRAINING:
  snapshot['rank_number']=rank
  snapshot['previous']=None if rank==1 else (acquired(actor,TRAINING,1) or {}).get('request_id')
 if feature in (CLASS,TRAINING):
  archive=actor.spec.get(CHOICES,{}).get(choice_key(feature,rank))
  if archive not in ARCHIVES:raise ValueError('explicit Chronicler archive choice required: '+choice_key(feature,rank))
  if archive in owned_archives(actor):raise ValueError('that Chronicler archive is already owned')
  snapshot['archive']=archive
  if archive=='travel':
   printed=actor.spec.get(TRAVEL_ABILITY);_travel_ability(engine.r,printed);snapshot['travel_ability']=printed
 if 'archive' in d:
  owned=owned_archives(actor).get(d['archive'])
  snapshot['archive_source']=None if owned is None else owned['request_id']
 if feature==CINEMATIC:snapshot['features']=[r['request_id'] for r in records(actor,active=True)]
 return snapshot


def qualification(actor,feature,snapshot,prerequisite_source):
 import acquisition_qualification as Q
 d=DEFINITIONS[feature]
 fields={'perception','parents'}|({'rank_number','previous'} if feature==TRAINING else set())|({'archive'} if feature in (CLASS,TRAINING) else set())|({'archive_source'} if 'archive' in d else set())|({'features'} if feature==CINEMATIC else set())
 if type(snapshot) is dict and feature in (CLASS,TRAINING) and snapshot.get('archive')=='travel':fields=fields|{'travel_ability'}
 if prerequisite_source is not None or type(snapshot) is not dict or set(snapshot)!=fields:raise ValueError('exact Chronicler acquisition observations required')
 if 'travel_ability' in snapshot:_travel_ability(actor.r,snapshot['travel_ability'])
 C.integer(snapshot['perception'],'Perception rank',0)
 known={r['request_id'] for r in records(actor,CLASS)}
 if feature!=CLASS and (not snapshot['parents'] or not set(snapshot['parents'])<=known):raise ValueError('actual acquired Chronicler class required')
 if feature==TRAINING:
  C.integer(snapshot['rank_number'],'Archival Training rank',1,2)
  if snapshot['rank_number']==2:
   prior=next((r for r in records(actor,TRAINING) if r['request_id']==snapshot['previous']),None)
   if prior is None or prior['snapshot'].get('rank_number')!=1:raise ValueError('actual first Archival Training rank required')
  elif snapshot['previous'] is not None:raise ValueError('first Archival Training rank has no prior rank')
 if feature in (CLASS,TRAINING) and snapshot['archive'] not in ARCHIVES:raise ValueError('printed Chronicler archive required')
 if 'archive' in d:
  owners={r['request_id'] for r in records(actor) if r['feature_id'] in (CLASS,TRAINING) and r['snapshot'].get('archive')==d['archive']}
  if snapshot['archive_source'] not in owners:raise ValueError('actual owned '+ARCHIVES[d['archive']]['english']+' required')
 if feature==CINEMATIC:
  actual={r['request_id'] for r in records(actor)}
  if len(set(snapshot['features']))<d['class_features'] or not set(snapshot['features'])<=actual:raise ValueError('four actual Chronicler Features required')
 return Q.require(feature,'native','acquire',[
  Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),
  Q.check('perception','prerequisite',snapshot['perception']>=d['rank'],'printed Perception rank required')])


def require(engine,actor,feature=CLASS):
 import world_entities as W
 W.require_actors(engine,actor)
 if actor.kind!='trainer' or acquired(actor,CLASS) is None or (feature!=CLASS and not acquired(actor,feature)):
  raise ValueError('actual acquired Chronicler Feature required: '+feature)
 return acquired(actor,feature) if feature!=TRAINING else acquired(actor,TRAINING)


def _owned_pokemon(engine,trainer,pokemon):
 import world_entities as W
 W.require_actors(engine,trainer,pokemon)
 if pokemon.kind!='pokemon' or pokemon.spec.get('trainer_id')!=trainer.entity_id:raise ValueError('actual owned Pokemon required')


def trainer_of(engine,actor):
 import world_entities as W
 if actor.kind=='trainer':return actor if acquired(actor,CLASS) else None
 owner=W.actor_index(engine).get(actor.spec.get('trainer_id'))
 return owner if owner is not None and owner.kind=='trainer' and acquired(owner,CLASS) else None


# ---------------------------------------------------------------- record state
def state(actor,create=False):
 st=actor.spec.get(KEY)
 if st is None:
  if not create:return None
  st={'version':1,'sequence':0,'records':{},'archives':{name:[] for name in ARCHIVES},'tutoring':[],'analyses':[]}
  actor.spec[KEY]=st
 if type(st) is not dict or st.get('version')!=1:raise ValueError('unsupported Chronicler state')
 return st


def archived(actor,archive):
 """Subjects (entity, Move or place identities) currently in one owned archive."""
 st=state(actor)
 if st is None or archive not in owned_archives(actor):return set()
 return {st['records'][rid]['subject'] for rid in st['archives'][archive]}


def _record(actor,record_id):
 st=state(actor)
 row=None if st is None else st['records'].get(record_id)
 if row is None:raise ValueError('actual Chronicler record required')
 return row


def current_place(actor):
 row=actor.spec.get(PLACE)
 if row is None:return None
 if type(row) is not dict or set(row)!={'place_id','reason','at','source'} or row['source']!='gm/chronicler_place':raise ValueError('invalid observed place')
 _text(row['place_id'],'observed place identity');C.integer(row['at'],'place observation time',0)
 return row['place_id']


def observe_place(engine,actor,place_id,*,reason):
 """GM world fact: the actor is now at this narrative place (None leaves it)."""
 import world_entities as W
 W.require_actors(engine,actor);_text(reason,'place observation reason')
 if place_id is not None:_text(place_id,'place identity')
 def apply(e,c):
  old=deepcopy(c.spec.get(PLACE))
  if place_id is None:c.spec.pop(PLACE,None)
  else:c.spec[PLACE]={'place_id':place_id,'reason':reason,'at':e.elapsed_seconds,'source':'gm/chronicler_place'}
  e.gm._rec('chronicler place',old,c.spec.get(PLACE),reason,c)
  reconcile_travel(e,c)
  return deepcopy(c.spec.get(PLACE))
 return G.transition(engine,actor,apply,include_rulings=True)


def _subject(engine,trainer,kind,target):
 import world_entities as W
 if kind not in RECORD_KINDS:raise ValueError('record one actual Pokemon, Trainer, Move or place')
 if kind in ('pokemon','trainer'):
  index=W.require_actors(engine,target)
  if target is trainer or target.kind!=kind:raise ValueError('actual other '+kind+' subject required')
  return target.entity_id
 if kind=='move':
  mid=engine.r.move_id(target) if isinstance(target,str) else None
  if mid is None or mid in getattr(engine.r,'excluded_moves',{}):raise ValueError('actual selected Move required')
  if not any(row.get('move_id')==mid and row.get('phase')=='complete' for row in getattr(engine,'_move_completions',{}).values()):
   raise ValueError('a Move record requires an actually witnessed Move use')
  return mid
 _text(target,'place identity')
 if current_place(trainer)!=target:raise ValueError('a place record requires the actual present place')
 return target


def _preflight_record(engine,trainer,kind,target,reason,request_id,edition):
 import action_points as AP
 require(engine,trainer);_text(reason,'record reason');_text(request_id,'record request')
 subject=_subject(engine,trainer,kind,target)
 st=state(trainer)
 prior=None if st is None else next((row for row in st['records'].values() if row['request_id']==request_id),None)
 if prior is not None:
  if (prior['kind'],prior['subject'],prior.get('edition'))!=(kind,subject,edition):raise ValueError('record replay cannot change its intent')
  return subject,prior
 if edition is None and AP.available(trainer)<DEFINITIONS[CLASS]['ap']:raise ValueError('Record requires one available AP')
 return subject,None


def _commit_record(e,t,kind,subject,reason,request_id,edition):
 import action_points as AP,turn as TURN,action_lifecycle as A
 action=DEFINITIONS[CLASS]['action']
 if e.encounter_active:
  if not TURN.spend(e,t,action,CLASS):raise ValueError('Record Swift action unavailable')
 else:
  # Outside an encounter the Swift Record is an ordinary action; a stale round budget does not constrain it.
  if not TURN.can_act(e,t) or not A.ordinary_permission(e,t) or not A.status_permission(e,t,action):raise ValueError('Record Swift action unavailable')
  A.record_action(e,t,action)
 if edition is None:AP.spend(t,DEFINITIONS[CLASS]['ap'])
 st=state(t,create=True);st['sequence']+=1
 row={'id':'chronicler-record:'+t.entity_id+':'+str(st['sequence']),'kind':kind,'subject':subject,'at':e.elapsed_seconds,
  'round':e.round_no,'reason':reason,'request_id':request_id,'status':'provisional','archive':None,'archived_at':None,
  'source':CLASS,'clause_id':clause(CLASS),'acquisition':acquired(t,CLASS)['request_id']}
 if edition is not None:row['edition']=edition
 st['records'][row['id']]=row
 e.log('  '+t.name+': 기록 '+kind+' '+str(subject),CLASS)
 return deepcopy(row)


def record(engine,trainer,target,*,kind,reason,request_id,edition=None):
 """1 AP Swift Record of an actual subject on the Chronicler's own turn or outside combat."""
 edition=_edition(engine.r,edition,CSV_RECORD)
 subject,prior=_preflight_record(engine,trainer,kind,target,reason,request_id,edition)
 if prior is not None:return deepcopy(prior)
 participants=(target,) if kind in ('pokemon','trainer') else ()
 def apply(e,t,*_):return _commit_record(e,t,kind,subject,reason,request_id,edition)
 return G.transition(engine,trainer,apply,participants=participants,include_rulings=True)


def record_interrupt(engine,trainer,target,*,kind,reason,request_id,trigger,payment='next',priority=0,edition=None):
 """Off-turn Record through the native reaction window, paying its Swift now or next turn."""
 import initiative_interrupts as I
 edition=_edition(engine.r,edition,CSV_RECORD)
 subject,prior=_preflight_record(engine,trainer,kind,target,reason,request_id,edition)
 if prior is not None:return deepcopy(prior)
 if payment not in ('current','next'):raise ValueError('explicit native Swift Interrupt payment required')
 request={'id':'chronicler-record:'+trainer.entity_id+':'+request_id,'actor_id':trainer.entity_id,'source':CLASS,'priority':priority,
  'mode':'reaction','payment':payment,'budget':{'swift':1},'clock':'none'}
 participants=(target,) if kind in ('pokemon','trainer') else ()
 def apply(e,t,*_):
  # One staged graph: the reaction window, its Swift payment and the record commit or roll back together.
  queued=I.queue(e,[request],trigger=trigger)
  if queued.get('status') not in ('queued','already_queued'):raise ValueError('Record Interrupt declaration pending: '+str(queued))
  I.begin(e,queued['window_id'],request['id'])
  row=_commit_record(e,t,kind,subject,reason,request_id,edition)
  I.finish(e)
  return row
 return G.transition(engine,trainer,apply,participants=participants,include_rulings=True)


def archive(engine,trainer,record_id,*,seconds,reason):
 """Extended action: bind one provisional record to the owned archive of its kind."""
 import pokemon_activities as P,turn as TURN
 require(engine,trainer);row=_record(trainer,record_id)
 C.integer(seconds,'actual Extended archival seconds',1);_text(reason,'archival reason')
 if row['status']!='provisional':raise ValueError('record is already archived')
 name=ARCHIVE_OF_KIND[row['kind']]
 if name not in owned_archives(trainer):raise ValueError('actual owned '+ARCHIVES[name]['english']+' required')
 if row['subject'] in archived(trainer,name):raise ValueError('subject is already in that archive')
 P._outside(engine)
 def apply(e,t):
  if not TURN.spend(e,t,'extended',CLASS):raise ValueError('Extended archival action unavailable')
  e.advance_time(seconds,[t],source=CLASS)
  st=state(t);entry=st['records'][record_id]
  entry.update(status='archived',archive=name,archived_at=e.elapsed_seconds,archive_source=owned_archives(t)[name]['request_id'],archival_reason=reason)
  st['archives'][name].append(record_id)
  import world_entities as W
  for c in W.actor_index(e).values():
   if c is t or c.spec.get('trainer_id')==t.entity_id:reconcile_travel(e,c)
  return deepcopy(entry)
 return G.transition(engine,trainer,apply,include_rulings=True)


# ---------------------------------------------------------------- passive consumers
def profile_bonus(engine,actor,skill,target):
 """+2 on the five printed social checks against an archived Profile subject."""
 if target is None or actor.kind!='trainer' or getattr(target,'entity_id',None) is None:return ()
 import skill_modifiers as S
 canonical=S.skill_id(engine.r.skill_policy,skill)
 if canonical not in {S.skill_id(engine.r.skill_policy,name) for name in ARCHIVES['profile']['skills']}:return ()
 if acquired(actor,CLASS) is None or target.entity_id not in archived(actor,'profile'):return ()
 return ((CLASS,ARCHIVES['profile']['skill_bonus'],'Profile Archive subject '+target.entity_id),)


def evasion_bonus(engine,target,move,attacker=None):
 """You and your Pokemon: +2 Evasion against Moves in the Technique Archive."""
 if target is None or not isinstance(move,dict):return 0
 owner=trainer_of(engine,target)
 if owner is None or move.get('id') not in archived(owner,'technique'):return 0
 return ARCHIVES['technique']['evasion_bonus']


def travel_grant_expected(engine,actor,*,exclude=()):
 """(trainer, ability, rule_id) when the actor is in an archived Travel place, else None."""
 owner=trainer_of(engine,actor)
 if owner is None or CLASS in exclude:return None
 archives=owned_archives(owner,exclude=exclude)
 travel=archives.get('travel')
 if travel is None:return None
 if actor is not owner and (PARTY in exclude or not acquired(owner,PARTY)):return None
 place=current_place(actor)
 if place is None or place not in archived(owner,'travel'):return None
 return owner,_travel_ability(engine.r,travel['travel_ability']),(travel['feature'] if actor is owner else PARTY)


def _travel_sources(actor):
 # Read-only: never create the grant store for an actor that has none.
 return {sid:row for sid,row in actor.spec.get(G.KEY,{}).get('sources',{}).items() if sid.startswith(TRAVEL_PREFIX)}


def reconcile_travel(engine,actor,*,exclude=()):
 """Grant or revoke the chosen Travel Archive Ability for one actor's present place."""
 expected=travel_grant_expected(engine,actor,exclude=exclude)
 current=_travel_sources(actor)
 if expected is None:
  for sid in list(current):G.revoke(actor,sid,engine=engine)
  return None
 owner,ability,rule_id=expected
 sid=TRAVEL_PREFIX+owner.entity_id+':'+actor.entity_id
 for other in list(current):
  if other!=sid:G.revoke(actor,other,engine=engine)
 row=current.get(sid)
 if row is not None and (row.get('grants',{}).get('abilities')!=[ability] or row.get('rule_id')!=rule_id or row.get('owner_id')!=owner.entity_id):
  G.revoke(actor,sid,engine=engine);row=None
 if row is None:
  G.grant(actor,'abilities',ability,sid,'feature',owner_id=owner.entity_id,lifetime='while_owned' if actor is owner else 'your_pokemon',rule_id=rule_id,tutor_points=0)
  G.state(actor)['sources'][sid].update(chronicler_travel={'place_id':current_place(actor),'clause_id':clause(rule_id)})
  engine.register_abilities_one(actor,ability)
 return sid


def environment_perception_bonus(engine,observer,skill):
 """+2 to Perception checks that notice the environment while in an archived place."""
 import skill_modifiers as S
 if S.skill_id(engine.r.skill_policy,skill)!=S.skill_id(engine.r.skill_policy,PERCEPTION):return 0
 return ARCHIVES['travel']['perception_bonus'] if travel_grant_expected(engine,observer) is not None else 0


def withdraw(engine,trainer,rule_id):
 """Retraining a Chronicler source ends the Travel grants it justified, for every actor."""
 if rule_id not in FEATURES:return
 import world_entities as W
 for c in W.actor_index(engine).values():
  if c is trainer or c.spec.get('trainer_id')==trainer.entity_id:reconcile_travel(engine,c,exclude=(rule_id,))


def after_acquire(engine,trainer):
 import world_entities as W
 for c in W.actor_index(engine).values():
  if c is trainer or c.spec.get('trainer_id')==trainer.entity_id:reconcile_travel(engine,c)


# ---------------------------------------------------------------- Archive Tutor
def learning_routes(engine,pokemon,mid):
 """Current Level Up plus species TM/Tutor routes, with native Type Sync permissions."""
 import move_state as M
 from builder import species_lookup
 routes=[]
 if any(row['kind']=='level_up' for row in M.current_natural_evidence(engine.r,pokemon.spec).get(mid,[])):routes.append('level_up')
 if pokemon.spec.get('species') is not None:
  ls=engine.r.learnsets.get(species_lookup(engine.r,pokemon.spec['species'])['name'],{})
  for raw in ls.get('tm',[]):
   match=re.fullmatch(r'\s*([A-Za-z]?)([0-9]+)\s+(.+?)\s*',str(raw))
   if match and engine.r.move_id(match.group(3))==mid:routes.append('tm');break
  if any(engine.r.move_id(re.sub(r'\s*\(N\)','',str(name),flags=re.I))==mid for name in ls.get('tutor',[])):routes.append('tutor')
 import type_sync as SYNC,pokemon_teaching as TEACH
 for method in ('tm','tutor'):
  permission=SYNC.learning_permission(engine.r,pokemon.spec,mid,method)
  if permission is False:routes=[route for route in routes if route!=method]
  elif permission is True and method not in routes:
   if method=='tutor' or any(engine.r.move_id(row['move_name'])==mid for row in TEACH.catalog(engine.r)['machines'].values()):
    routes.append(method)
 return routes


def _technique_record(engine,trainer,pokemon,mid):
 if mid not in archived(trainer,'technique'):raise ValueError('actual archived Technique Move record required')
 routes=learning_routes(engine,pokemon,mid)
 if not routes:raise ValueError('target cannot learn that Move by Level Up, TM or Tutor')
 st=state(trainer)
 return next(rid for rid in st['archives']['technique'] if st['records'][rid]['subject']==mid),routes


def tutor(engine,trainer,pokemon,move_id,*,seconds,reason,replace=None,tutoring_policy=None,edition=None):
 """Daily Extended teaching of an archived Move for two Tutor Points."""
 import frequency as F,pokemon_activities as P,pokemon_teaching as TEACH,world_entities as W
 edition=_edition(engine.r,edition,CSV_TUTOR)
 require(engine,trainer,TUTOR);W.require_actors(engine,pokemon);P._trainer(trainer);P._pokemon(pokemon)
 d=DEFINITIONS[TUTOR];C.integer(seconds,'actual Extended teaching seconds',1);_text(reason,'teaching reason')
 if not pokemon.spec.get('trainer_id'):raise ValueError('Archive Tutor targets an owned Pokemon')
 mid=engine.r.move_id(move_id)
 if mid is None:raise ValueError('actual selected Move required')
 record_id,routes=_technique_record(engine,trainer,pokemon,mid)
 if TEACH._balance(pokemon.spec)<d['tutor_points']:raise ValueError('target needs two actual Tutor Points')
 st=state(trainer)
 other=pokemon.spec['trainer_id']!=trainer.entity_id
 previous=[row for row in st['tutoring'] if row['pokemon_id']==pokemon.entity_id]
 if previous and (other or edition is not None or any(row.get('edition')==CSV_TUTOR for row in previous)):
  raise ValueError('this Pokemon may be targeted by the selected Archive Tutor source only once')
 P._outside(engine)
 def apply(e,t,q):
  import move_state as M,learning_grant as LEARNING,turn as TURN,activity_jobs as JOBS,trainer_retraining as RETRAINING
  # Frequency reads bind the session ledger, so they stay inside the staged graph.
  if not F.activation_allowed(t,TUTOR,d['frequency'],engine=e):raise ValueError('Archive Tutor daily frequency exhausted')
  if t.spec.get('frequency_state',{}).get('day',0)!=q.spec.get('frequency_state',{}).get('day',0):raise ValueError('teaching calendars must agree')
  old=e.r.move_id(replace) if replace is not None else None;baseline=M.known(e.r,q.spec)
  if mid in baseline:raise ValueError('Pokemon already learned that move')
  if replace is not None and old not in baseline:raise ValueError('explicit replacement must name an actually learned permanent move')
  admission=TEACH.tutor_admission(e.r,mid,q.level,policy=tutoring_policy)
  candidate=deepcopy(q.spec)
  if old is not None:
   import move_type_sync as MOVE_SYNC
   MOVE_SYNC.forget_spec(e.r,candidate,old,at=e.elapsed_seconds,reason=reason)
  candidate['moves']=[m for m in candidate.get('moves',[]) if e.r.move_id(m)!=old]
  details={'archive_record':record_id,'learning_routes':routes,'archive_tutor_admission':admission,'seconds':seconds}
  if edition is not None:details['archive_tutor_edition']={'source':edition,'teacher_id':t.entity_id,'pokemon_id':q.entity_id,'owner_id':q.spec['trainer_id']}
  LEARNING.learn_moves(e.r,candidate,candidates=[mid],selected=[mid],method='feature',source=TUTOR,reason=reason,provider=t.entity_id,
   paid_tp=d['tutor_points'],replaced=old,details=details)
  moves=candidate['moves']
  M.record_natural_opportunities(e.r,candidate,reason='completed Archive Tutor teaching')
  M.validate_spec(e.r,candidate,require_routes=True)   # only CSV311's own permanent lesson is outside the taught quota
  if not TURN.spend(e,t,'extended',TUTOR):raise ValueError('Archive Tutor Extended action unavailable')
  JOBS.run_fixed(e,t,(q,),seconds=seconds,source=TUTOR,context={'move_id':mid,'record_id':record_id})
  F.consume_activation(t,TUTOR,d['frequency'],engine=e)
  for field in ('move_learning','move_learning_log',M.HISTORY,'move_type_sync'):
   if field in candidate:q.spec[field]=candidate[field]
  G.set_baseline(q,'moves',moves);TEACH._debit_points(q.spec,d['tutor_points'])
  row={'pokemon_id':q.entity_id,'owner_id':q.spec['trainer_id'],'other_owner':other,'move_id':mid,'record_id':record_id,'routes':routes,
   'point_cost':d['tutor_points'],'at':e.elapsed_seconds,'reason':reason,'acquisition':acquired(t,TUTOR)['request_id'],'clause_id':clause(TUTOR)}
  if edition is not None:row['edition']=edition
  state(t)['tutoring'].append(row)
  RETRAINING.irreversible(e,t,TUTOR,event_id='archive-tutor:'+t.entity_id+':'+q.entity_id+':'+mid+':'+str(e.elapsed_seconds),reason='completed permanent Archive Tutor teaching: '+mid)
  return {'activity':'archive_tutor','move':mid,'replaced':old,'point_cost':d['tutor_points'],'routes':routes,'seconds':seconds,
   'classification':M.describe(e.r,q.spec)['classifications'][mid]}
 return G.transition(engine,trainer,apply,participants=(pokemon,))


def tutor_pool_exempt(rules,spec,mid):
 """CSV311 exempts this permanent own-Pokemon lesson from the taught quota, not six known Moves."""
 record=spec.get('move_learning',{}).get(mid,{})
 if type(record)is not dict:return False
 proof=record.get('archive_tutor_edition')
 if proof is None:return False
 if (type(proof)is not dict or set(proof)!={'source','teacher_id','pokemon_id','owner_id'}
     or record.get('source')!=TUTOR or record.get('method')!='feature' or record.get('paid_tp')!=2
     or record.get('lifetime')!='permanent' or record.get('learning_contract')!=1
     or not record.get('archive_record') or proof.get('teacher_id')!=record.get('teacher_id')
     or proof.get('pokemon_id')!=spec.get('id')
     or not all(type(proof.get(key))is str and proof[key] for key in ('teacher_id','pokemon_id','owner_id'))):
  raise ValueError('CSV Archive Tutor exemption requires actual permanent learning provenance')
 _edition(rules,proof['source'],CSV_TUTOR)
 # A forgotten receipt cannot exempt a later unrelated source-owned grant.
 permanent=list(spec.get('moves',[]))+list(spec.get('state_grants',{}).get('legacy',{}).get('moves',[]))
 return proof['teacher_id']==proof['owner_id'] and any(rules.move_id(raw)==mid for raw in permanent)


# ---------------------------------------------------------------- Targeted Profiling
def order_delivery(engine,a,p,feature):
 import perception_communicate as COMM
 if not engine.encounter_active or not p.on_field or p.fainted or p.captured:raise ValueError('available actual Order recipient required')
 policy={'id':'chronicler-order:'+feature,'source':feature,'capabilities':[],'requirements':[],'mode':'auditory','range':None,'path':'auditory','medium':[],'consent':{'kind':'none'},'blockers':[],'connection':None,'frequency':{'kind':'at_will','uses':1},'retry':None,'distance_exceptions':[]}
 request='chronicler-order:'+a.entity_id+':'+str(len(getattr(engine,COMM.KEY,{}).get('attempts',[]))+1)
 result=COMM.send(engine,a,p,policy,'Chronicler Order: '+feature,request_id=request)
 if result['status']!='delivered':raise ValueError('Chronicler Order communication was not delivered: '+str(result.get('reason')))
 return result


def profiling_record(pokemon):
 import combat_timing as T
 return next((r for r in T.records(pokemon) if r.get('source')==PROFILING),None)


def profile_order(engine,trainer,pokemon,*,communication=None):
 """2 AP Standard Order: the Pokemon's next turn treats archived Profile subjects as Mold Breaker targets with +2 Accuracy."""
 import action_points as AP,turn as TURN,combat_timing as T,cheerleader as CHEER
 require(engine,trainer,PROFILING)
 import commander as COMMANDER
 if not (COMMANDER.transformed_target(engine,trainer,pokemon) or COMMANDER.leadership_target(engine,trainer,pokemon)):
  _owned_pokemon(engine,trainer,pokemon)
 d=DEFINITIONS[PROFILING]
 @CHEER.order_activation(PROFILING)
 def apply(e,t,q):
  if not e.encounter_active or not q.on_field or q.fainted or q.captured:raise ValueError('available actual Order recipient required')
  import order_actions as ORDERS
  delivery=order_delivery(e,t,q,PROFILING) if communication is None else ORDERS.delivery(e,t,q,PROFILING,communication=communication)
  if profiling_record(q) is not None:raise ValueError('Targeted Profiling is already pending for this Pokemon')
  if AP.available(t)<d['ap']:raise ValueError('Targeted Profiling requires two available AP')
  import order_actions as ORDERS
  ORDERS.spend(e,t,PROFILING,action=d['action'],subject=q.entity_id,communication=delivery)
  AP.spend(t,d['ap'])
  serial=q.custom_conditions.get('combat_turn_serial',0)
  if e._active_turn_actor is q:raise ValueError('an Order targets a Pokemon outside its own open turn')
  row={'source':PROFILING,'turn_owner':q,'turn_deadline':serial+1,'encounter_end':True,
   'chronicler_profiling':{'owner_id':t.entity_id,'acquisition':acquired(t,PROFILING)['request_id'],'clause_id':clause(PROFILING),
    'issued_round':e.round_no,'issued_serial':serial,'active_serial':serial+1}}
  T.install(e,q,row);e.time_actors([t,q])
  return deepcopy(row['chronicler_profiling'])
 return G.transition(engine,trainer,apply,participants=(pokemon,),include_rulings=True)


def _profiling_owner(engine,attacker,target):
 if attacker is None or target is None:return None
 row=profiling_record(attacker)
 if row is None:return None
 facts=row['chronicler_profiling']
 if not __import__('native_order_transfer').on_eligible_turn(engine,attacker,row,facts['active_serial']):return None
 import world_entities as W
 owner=W.actor_index(engine).get(facts['owner_id'])
 if owner is None or getattr(target,'entity_id',None) not in archived(owner,'profile'):return None
 return owner


def accuracy_bonus(engine,attacker,target,move):
 return DEFINITIONS[PROFILING]['accuracy_bonus'] if _profiling_owner(engine,attacker,target) is not None else 0


def defensive_ignored(engine,attacker,target,move=None):
 """Shared selected native defensive-Ability bypass, including Targeted Profiling."""
 if _profiling_owner(engine,attacker,target) is not None or __import__('commander_orders').ignore_defensive(engine,attacker,target):return True
 if attacker is None or target is None:return False
 if __import__('typed_defensive_bypass').active_sources(engine,attacker,target,move):return True
 attacker_side,target_side=getattr(attacker,'side',None),getattr(target,'side',None)
 if not attacker_side or not target_side or attacker_side==target_side:return False
 import ability_transitions as ABILITIES
 for effect in attacker.registry:
  if effect.get('type')!='ignore_effects' or effect.get('ignore_abilities') not in ('defensive','defensive (all enemies)'):continue
  source=effect.get('_rule_id','')
  if __import__('typed_defensive_bypass').handles(source):continue
  if not source.startswith('ability/'):continue
  if engine.r._selected_rule(source)!=source:continue
  raw={k:v for k,v in effect.items() if not k.startswith('_')}
  title=engine.r.selection.units[source]['title']
  if not ABILITIES.active(attacker,title):continue
  if raw not in engine.r.ability_effects.get(title,[]):continue
  restriction=effect.get('moves')
  if restriction is not None:
   if move is None:continue
   import effects_ext as EXT
   mechanics,_=engine.r.move_mech(move['id'])
   if EXT.effective_type(engine,attacker,target,move,mechanics,consume=False)!=restriction:continue
  return True
 return False


# ---------------------------------------------------------------- Cinematic Analysis
def _analysis_preflight(engine,trainer,kind):
 require(engine,trainer,CINEMATIC)
 if kind not in ANALYSES:raise ValueError('known Cinematic Analysis effect required')


def _analysis_allowed(engine,trainer,kind):
 """Frequency reads bind the session ledger: call only inside the staged graph."""
 import frequency as F
 if not F.activation_allowed(trainer,CINEMATIC,DEFINITIONS[CINEMATIC]['frequency'],engine=engine):raise ValueError('Cinematic Analysis daily frequency exhausted')
 if not F.activation_allowed(trainer,CINEMATIC+':'+kind,{'kind':'scene','uses':ANALYSES[kind]['scene']},engine=engine):raise ValueError(ANALYSES[kind]['english']+' was already used this scene')


def _archived_record(trainer,record_id,archive):
 row=_record(trainer,record_id)
 if row['status']!='archived' or row['archive']!=archive:raise ValueError('actual archived '+ARCHIVES[archive]['english']+' record required')
 return row


def _consume_analysis(e,t,kind,record_id,**facts):
 import frequency as F,action_lifecycle as A
 _analysis_allowed(e,t,kind)
 A.triggered_free_action(e,t,CINEMATIC)
 F.consume_activation(t,CINEMATIC,DEFINITIONS[CINEMATIC]['frequency'],engine=e)
 F.consume_activation(t,CINEMATIC+':'+kind,{'kind':'scene','uses':ANALYSES[kind]['scene']},engine=e)
 row={'kind':kind,'record_id':record_id,'round':e.round_no,'at':e.elapsed_seconds,'clause_id':ANALYSES[kind]['clause_id'],
  'acquisition':acquired(t,CINEMATIC)['request_id'],**facts}
 state(t)['analyses'].append(row)
 return row


def _ally(engine,trainer,actor):
 import world_entities as W
 W.require_actors(engine,trainer,actor)
 if actor is trainer:return True
 owned=actor.spec.get('trainer_id')==trainer.entity_id
 same_side=trainer.side is not None and actor.side==trainer.side
 if not (owned or same_side):raise ValueError('actual ally required')
 return False


def character_study(engine,trainer,*,record_id,actor,target,skill,dc,purpose,reason,perception_fixed=None,**roll_options):
 """Replace an ally's or own social check against the recorded subject with the Chronicler's Perception check."""
 import roll_context as RC,skill_modifiers as S
 _analysis_preflight(engine,trainer,'character_study');_text(reason,'Character Study reason')
 row=_archived_record(trainer,record_id,'profile')
 import world_entities as W
 W.require_actors(engine,target)
 if target.entity_id!=row['subject']:raise ValueError('the triggered check must target the actual recorded subject')
 _ally(engine,trainer,actor)
 if S.skill_id(engine.r.skill_policy,skill) not in {S.skill_id(engine.r.skill_policy,name) for name in ARCHIVES['profile']['skills']}:
  raise ValueError('Character Study replaces only Charm, Command, Guile, Intimidate or Intuition checks')
 C.integer(dc,'DC')
 triggered=RC.plan(engine,actor,skill,purpose=purpose,target=target,**roll_options)
 def apply(e,t,a,other):
  analysis=_consume_analysis(e,t,'character_study',record_id,actor_id=a.entity_id,target_id=other.entity_id,skill=triggered['requested_skill'],purpose=purpose,dc=dc,reason=reason)
  roll=e.skill_roll(t,PERCEPTION,skill_target=other,roll_id=roll_options.get('roll_id'),fixed=perception_fixed)
  sf=__import__('skill_feature_actions');identity=sf._observed(e,t,roll,roll_options)[0] if t.entity_id in getattr(e,'_let_me_help_offers',{}) else roll_options.get('roll_id')
  result=__import__('skill_feature_actions').resolve_check(e,t,PERCEPTION,dc,roll,roll_options)
  if identity is not None:
   observed=sf.event(e,t,identity)
   if observed is not None and observed.final is not None:roll=observed.final
  analysis.update(perception_total=roll.total,passed=result.passed)
  return {'triggered':{'actor_id':a.entity_id,'skill':triggered['requested_skill'],'purpose':purpose,'dc':dc,'rolled':False},
   'replacement':{'actor_id':t.entity_id,'skill':PERCEPTION,'total':roll.total,'faces':list(roll.faces),'passed':result.passed,'margin':result.margin}}
 participants=(target,) if actor is trainer else (actor,target)
 outcome=G.transition(engine,trainer,lambda e,t,*ps:apply(e,t,t if actor is trainer else ps[0],ps[-1]),participants=participants,include_rulings=True)
 return outcome


def recreation(engine,trainer,pokemon,move_id):
 """As the Pokemon takes initiative: perform one archived learnable Move as if listed, once per Move per day."""
 import frequency as F,combat_timing as T
 _analysis_preflight(engine,trainer,'recreation');_owned_pokemon(engine,trainer,pokemon)
 mid=engine.r.move_id(move_id)
 if mid is None:raise ValueError('actual selected Move required')
 record_id,routes=_technique_record(engine,trainer,pokemon,mid)
 if mid in pokemon.moves:raise ValueError('that Move is already on the actual Move List')
 if not engine.encounter_active or engine._active_turn_actor is not pokemon or getattr(pokemon,'_action_history',[]):
  raise ValueError('Recreation triggers as your Pokemon gains initiative, before it acts')
 daily={'kind':'daily','uses':ANALYSES['recreation']['move_daily']}
 def apply(e,t,q):
  if not F.activation_allowed(t,CINEMATIC+':recreation:'+mid,daily,engine=e):raise ValueError('that Move was already chosen for Recreation today')
  serial=q.custom_conditions.get('combat_turn_serial',0)
  sid='chronicler-recreation:'+q.entity_id+':'+str(e.round_no)+':'+str(serial)
  analysis=_consume_analysis(e,t,'recreation',record_id,pokemon_id=q.entity_id,move_id=mid,routes=routes,permission_source=sid)
  F.consume_activation(t,CINEMATIC+':recreation:'+mid,daily,engine=e)
  G.grant_moves(q,[mid],sid,'feature',owner_id=t.entity_id,lifetime='turn',rule_id=CINEMATIC,mode='permission')
  T.install(e,q,{'source':CINEMATIC,'turn_owner':q,'turn_deadline':serial,'grant_source':sid,'encounter_end':True,
   'chronicler_recreation':{'owner_id':t.entity_id,'move_id':mid,'record_id':record_id,'clause_id':ANALYSES['recreation']['clause_id']}})
  e.time_actors([t,q])
  return {'move':mid,'permission_source':sid,'routes':routes,'analysis':deepcopy(analysis)}
 return G.transition(engine,trainer,apply,participants=(pokemon,),include_rulings=True)


def situational_awareness(engine,trainer,ally,*,record_id):
 """Analyze the present place's record, as an Interrupt if needed: one ally may make its next action Priority (Advanced)."""
 _analysis_preflight(engine,trainer,'situational_awareness')
 row=_archived_record(trainer,record_id,'travel')
 if current_place(trainer)!=row['subject']:raise ValueError('Situational Awareness analyzes only the record of the present place')
 if _ally(engine,trainer,ally):raise ValueError('choose an actual ally other than yourself')
 if ally.fainted or ally.captured:raise ValueError('available ally required')
 if not engine.encounter_active:raise ValueError('Priority entitlement requires an active encounter')
 if ally.spec.get(PRIORITY) is not None:raise ValueError('ally already holds a pending Priority entitlement')
 def apply(e,t,a):
  analysis=_consume_analysis(e,t,'situational_awareness',record_id,ally_id=a.entity_id,place_id=row['subject'])
  token={'source':CINEMATIC,'owner_id':t.entity_id,'record_id':record_id,'place_id':row['subject'],'granted_round':e.round_no,'at':e.elapsed_seconds,
   'ally_turn_serial':a.custom_conditions.get('combat_turn_serial',0),'variant':ANALYSES['situational_awareness']['priority'],'clause_id':ANALYSES['situational_awareness']['clause_id']}
  a.spec[PRIORITY]=token
  return deepcopy(token)
 return G.transition(engine,trainer,apply,participants=(ally,),include_rulings=True)


def consume_priority(engine,actor,trainer):
 """priority_actions producer: spend the pending Advanced entitlement for this actual declaration."""
 import world_entities as W
 W.require_actors(engine,actor,trainer)
 token=actor.spec.get(PRIORITY)
 if type(token) is not dict or token.get('source')!=CINEMATIC or token.get('owner_id')!=trainer.entity_id:
  raise ValueError('actual pending Situational Awareness entitlement from this Chronicler required')
 if actor.custom_conditions.get('combat_turn_serial',0)!=token['ally_turn_serial']:raise ValueError('Situational Awareness entitlement lapsed with the ally turn')
 actor.spec.pop(PRIORITY)
 return deepcopy(token)


def start_turn(engine,actor):
 """An ordinary turn is the ally's next action: an unused entitlement lapses."""
 token=actor.spec.get(PRIORITY)
 if token is None:return
 import initiative_interrupts as I
 current=I.frame(engine)
 if current and current.get('mode')=='borrow_turn' and current.get('actor') is actor:return
 actor.spec.pop(PRIORITY)
 engine.log('  '+actor.name+': 상황 인식 우선 권한 소멸 (일반 턴 시작)',CINEMATIC)


# ---------------------------------------------------------------- validation
def validate(engine):
 import world_entities as W,combat_timing as T
 index=W.actor_index(engine)
 for actor in index.values():
  for mid,lesson in actor.spec.get('move_learning',{}).items():
   if type(lesson)is not dict or 'archive_tutor_edition' not in lesson:continue
   tutor_pool_exempt(engine.r,actor.spec,mid)
   proof=lesson['archive_tutor_edition'];teacher=index.get(proof['teacher_id'])
   if teacher is not None:
    history=(state(teacher) or {}).get('tutoring',[])
    matches=[row for row in history if row.get('pokemon_id')==actor.entity_id and row.get('move_id')==mid
     and row.get('record_id')==lesson.get('archive_record') and row.get('edition')==proof['source']
     and row.get('owner_id')==proof['owner_id'] and row.get('other_owner')==(proof['owner_id']!=proof['teacher_id'])]
    if len(matches)!=1:raise ValueError('CSV Archive Tutor learning differs from actual teacher history')
  st=actor.spec.get(KEY)
  if st is not None:
   # A retrained class keeps its record history; the acquisition provenance below still binds each record.
   if actor.kind!='trainer' or not records(actor,CLASS):raise ValueError('Chronicler records require an actual Chronicler acquisition')
   if type(st) is not dict or set(st)!={'version','sequence','records','archives','tutoring','analyses'} or st['version']!=1:raise ValueError('exact Chronicler state required')
   C.integer(st['sequence'],'Chronicler record sequence',0)
   archives=owned_archives(actor)
   for rid,row in st['records'].items():
    if type(row) is not dict or set(row)-{'archive_source','archival_reason','edition'}!={'id','kind','subject','at','round','reason','request_id','status','archive','archived_at','source','clause_id','acquisition'} or row['id']!=rid:raise ValueError('exact Chronicler record required')
    if 'edition' in row:_edition(engine.r,row['edition'],CSV_RECORD)
    if row['kind'] not in RECORD_KINDS or row['source']!=CLASS or row['clause_id']!=clause(CLASS) or row['status'] not in ('provisional','archived'):raise ValueError('invalid Chronicler record')
    C.integer(row['at'],'record time',0,engine.elapsed_seconds);_text(row['reason'],'record reason');_text(row['request_id'],'record request')
    if not any(r['request_id']==row['acquisition'] for r in records(actor,CLASS)):raise ValueError('record acquisition provenance changed')
    if row['status']=='archived':
     # A retrained archive keeps its historical records; archived() already hides them from consumers.
     if row['archive']!=ARCHIVE_OF_KIND[row['kind']] or rid not in st['archives'][row['archive']]:raise ValueError('archived record outside its archive list')
     C.integer(row['archived_at'],'archival time',row['at'],engine.elapsed_seconds)
    elif row['archive'] is not None or any(rid in ids for ids in st['archives'].values()):raise ValueError('provisional record cannot be listed in an archive')
   for name,ids in st['archives'].items():
    if name not in ARCHIVES or type(ids) is not list or len(set(ids))!=len(ids):raise ValueError('invalid Chronicler archive list')
    subjects=[st['records'][rid]['subject'] for rid in ids if rid in st['records']]
    if len(subjects)!=len(ids) or len(set(subjects))!=len(subjects):raise ValueError('archive lists an unknown or repeated record')
   for row in st['tutoring']:
    if type(row) is not dict or row.get('clause_id')!=clause(TUTOR) or type(row.get('other_owner')) is not bool:raise ValueError('invalid Archive Tutor history')
    if 'edition' in row:_edition(engine.r,row['edition'],CSV_TUTOR)
   for target in {row['pokemon_id'] for row in st['tutoring'] if row.get('edition')==CSV_TUTOR}:
    if sum(row['pokemon_id']==target for row in st['tutoring'])!=1:raise ValueError('CSV Archive Tutor target can be taught only once across source editions')
   for row in st['analyses']:
    if type(row) is not dict or row.get('kind') not in ANALYSES or row.get('clause_id')!=ANALYSES[row.get('kind')]['clause_id']:raise ValueError('invalid Cinematic Analysis history')
  if PLACE in actor.spec:current_place(actor)
  token=actor.spec.get(PRIORITY)
  if token is not None:
   if type(token) is not dict or token.get('source')!=CINEMATIC or token.get('owner_id') not in index or index[token['owner_id']].kind!='trainer':raise ValueError('invalid Situational Awareness entitlement')
   if acquired(index[token['owner_id']],CINEMATIC) is None:raise ValueError('Situational Awareness entitlement lost its Chronicler owner')
  for sid,row in _travel_sources(actor).items():
   expected=travel_grant_expected(engine,actor)
   if expected is None or sid!=TRAVEL_PREFIX+expected[0].entity_id+':'+actor.entity_id or row.get('grants',{}).get('abilities')!=[expected[1]] or row.get('rule_id')!=expected[2]:
    raise ValueError('Travel Archive Ability grant is not justified by the present archived place')
  for row in T.records(actor):
   if row.get('source')==PROFILING:
    facts=row.get('chronicler_profiling')
    if type(facts) is not dict or facts.get('owner_id') not in index or row.get('turn_owner') is not __import__('native_order_transfer').clock_owner(engine,actor,row) or row.get('turn_deadline')!=facts.get('active_serial'):raise ValueError('invalid Targeted Profiling record')
    if acquired(index[facts['owner_id']],PROFILING) is None:raise ValueError('Targeted Profiling lost its Chronicler owner')
   if row.get('source')==CINEMATIC:
    facts=row.get('chronicler_recreation')
    if type(facts) is not dict or row.get('grant_source') not in G.state(actor)['sources'] or row.get('turn_owner') is not actor:raise ValueError('invalid Recreation permission record')
 return True
