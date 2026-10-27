"""PTK Pokemon activities, using the native Engine dice, action and time paths.

GM-supplied facts (compatibility, accessible equipment, wild disposition) are
explicit world state. No random encounter, capture, loyalty change or completion
is inferred from a successful unrelated check. Sources: ch03 and ch05.
"""
import arithmetic_policy as M
from copy import deepcopy
import common_checks as C
import skill_modifiers as SKILL
import turn as TURN

FEATURES={
 'gem_lore':('edge/보석-지식',('보석 지식','Gem Lore'),(('오컬트학',3),)),
 'green_thumb':('edge/원예가',('원예가','Green Thumb'),(('일반 지식',3),('생존',3))),
 'basic_cooking':('edge/기본-요리',('기본 요리','Basic Cooking'),(('직감',3),)),
 'repel_crafter':('edge/스프레이-제작자',('스프레이 제작자','Repel Crafter'),(('의학',3),('기술학',3))),
 'basic_balls':('edge/몬스터볼',('몬스터볼','Basic Balls'),(('기술학',3),)),
 'apricorn_balls':('edge/규토리-볼',('규토리 볼','Apricorn Balls'),(('생존',3),('기술학',4))),
 'repair':('edge/몬스터볼-수리',('몬스터볼 수리','Poké Ball Repair'),()),
 'beast':('edge/비스트-마스터',('비스트 마스터','Beast Master'),(('협박',3),)),
 'breeder':('edge/브리더',('브리더','Breeder'),(('포켓몬학',3),)),
 'groomer':('edge/미용사',('미용사','Groomer'),(('포켓몬학',3),)),
 'paleontologist':('edge/고생물학자',('고생물학자','Paleontologist'),(('포켓몬학',3),('생존',3))),
 'mounted':('edge/탑승-기량',('탑승 기량','Mounted Prowess'),(('곡예',3),('육상',3))),
 'psychologist':('edge/포켓몬-심리학자',('포켓몬 심리학자','PokéPsychologist'),(('포켓몬학',3),('일반 지식',3))),
 'reserves':('edge/예비-훈련',('예비 훈련','Train the Reserves'),(('명령',3),)),
 'maniac':('feat/포켓몬매니아',('포켓몬매니아','PokéManiac'),(('포켓몬학',4),)),
 'ball_crafter':('feat/몬스터볼-장인',('몬스터볼 장인','Poké Ball Crafter'),(('기술학',5),)),
}
DISPOSITIONS=('매우 적대적','적대적','두려움','중립','우호적','매우 우호적')
DISPOSITION_DC=(30,15,8,12,15,None)
DISPOSITION_SOURCE='ch05-pokemon/포켓몬-성향'
DISPOSITION_KR={'file':'input/ch05-pokemon.md','sha256':'bdfb5d39fec8fede32cac615a7788301336aaceefc46079c8ed7014ea76d174b'}
DISPOSITION_EN={'file':'source-audit/pokemon-relationships-fishing-core-1.05.txt','sha256':'9d49406f11a1cf694ea6c376c2aa142a1f7e43a03abd6d7471a6884316bc024f'}
REPAIR_CSV='C2CSV/input/db/edges.csv:R17:main'
MANIAC='feat/포켓몬매니아'
MANIAC_BOOK='input/ch03-skills-edges-feats.md:897-901'
MANIAC_CSV='C2CSV/input/db/feats.csv:R49:main'

def pokemaniac_source(rules,selection=None):
 """Only the two reviewed source contracts; no automatic CSV precedence."""
 from source_context import verified_source
 if selection is not None and (type(selection)is not dict or set(selection)!={'edition'} or selection['edition'] not in ('core','local_csv')):raise ValueError('exact reviewed Pokemaniac edition selection required')
 edition='core' if selection is None else selection['edition']
 if rules._selected_rule(MANIAC)!=MANIAC or any(uid in rules.ruleset.unit_versions for uid in (MANIAC,MANIAC_BOOK,MANIAC_CSV)):raise ValueError('selected Pokemaniac source needs its own activity policy')
 authority={'file':'input/ch03-skills-edges-feats.md','sha256':'b94e43349794836391501f9aac10009d20746bf946ea0c4b5ff3adf85e982d23'}
 verified_source(rules,authority,label='Pokemaniac')
 if edition=='local_csv':
  authority={'file':'input/db/feats.csv','sha256':'4435ff1c462a211564c85d2c1c9a2ac6e7c790c7545e1ad7056d32888b2367bd'}
  verified_source(rules,authority,label='local CSV Pokemaniac')
  rules.ruleset.require({'id':MANIAC_CSV,'source':{'file':'db/feats.csv','record_span':[49,49]}})
  return dict(authority,edition=edition,clause_id=MANIAC_CSV,record=49)
 return dict(authority,edition=edition,clause_id=MANIAC_BOOK,span=[897,901])

def pokemaniac_snapshot_source(rules,snapshot):
 source=pokemaniac_source(rules,snapshot.get('selection'))
 # Historical Book declarations/receipts have no additional source choice.
 if 'source' in snapshot:
  if snapshot['source']!=source:raise ValueError('actual acquired Pokemaniac source changed')
 elif snapshot.get('selection') is not None:raise ValueError('actual Pokemaniac source selection receipt required')
 return source

def _text(value,name):
 if not isinstance(value,str) or not value.strip():raise ValueError(name+' required')
 return value

def _trainer(actor):
 if actor.kind!='trainer':raise ValueError('trainer required')
 if actor.dead or actor.fainted or actor.hp<=0:raise ValueError('conscious trainer required')

def _owner(actor,target):
 _text(actor.spec.get('id'),'trainer identity')
 _text(target.spec.get('trainer_id'),'Pokemon trainer identity')
 if target.spec['trainer_id']!=actor.spec['id']:raise ValueError('Pokemon belongs to a different trainer')

def _pokemon(target):
 if target is None or target.kind!='pokemon':raise ValueError('Pokemon target required')

def _rank(e,actor,skill):return SKILL.rank(e.r,actor,skill)[2]

def _feature(e,actor,name,required=True):
 _trainer(actor);uid,aliases,prerequisites=FEATURES[name]
 owned=actor.spec.get('feats' if uid.startswith('feat/') else 'edges',[])
 present=any(x==uid or x in aliases for x in owned)
 if name=='repair' and not present and REPAIR_CSV in owned:
  uid=REPAIR_CSV;present=True
 if not present:
  if required:raise ValueError('acquired feature required: '+uid)
  return False
 if e.r._selected_rule(uid)!=uid:raise ValueError('selected feature version needs its own activity policy')
 if prerequisites and not __import__('hobbyist').skill_waived(actor,uid) and not any(_rank(e,actor,s)>=r for s,r in prerequisites):raise ValueError('feature prerequisite not established: '+uid)
 if name=='repair' and not (_feature(e,actor,'basic_balls',False) or _feature(e,actor,'apricorn_balls',False)):raise ValueError('Poke Ball Repair requires the acquired Basic Balls or Apricorn Balls crafting edge')
 return True

def _tool(actor,*names):
 inv=actor.spec.get('items',{})
 for name in names:
  value=inv.get(name,0)
  if type(value) is int and value>0:return name
 # Access may be shared workshop equipment rather than inventory possession.
 access=actor.spec.get('accessible_equipment',[])
 for name in names:
  if name in access:return name
 raise ValueError('required equipment is not accessible: '+names[0])

def _preflight(e,actor,skill,options):
 opts=dict(options)
 p=e._prepare_skill_roll(actor,skill,**opts)
 if opts.get('fixed') is not None:opts['fixed']=p[3]
 if opts.get('fixed_penalties') is not None:opts['fixed_penalties']=p[4]
 return opts

def _check(e,actor,skill,dc,options,*,action=None,seconds=0,time_actors=None,context=None,target=None):
 """Bind paid activity cost to the observed native skill event for resumption."""
 if target is not None:
  import skill_targets as TARGETS
  options=TARGETS.bind(e,options,target)
 if options.get('feature') is None:
  options=_preflight(e,actor,skill,options)
  if action and not TURN.spend(e,actor,action,'포켓몬 전문활동'):return C.PendingDecision('required action unavailable')
  if seconds:e.advance_time(seconds,time_actors or [actor])
  return __import__('skill_feature_actions').resolve_check(e,actor,skill,dc,e.skill_roll(actor,skill,**options),options)
 import skill_feature_actions as SF
 roll_id=options.get('roll_id');_text(roll_id,'identified activity skill roll')
 if context is None:raise ValueError('observed activity feature needs concrete activity context')
 basis={'actor_id':actor.spec['id'],'context':deepcopy(context),'skill':SKILL.skill_id(e.r.skill_policy,skill),'dc':dc,'action':action,'seconds':seconds}
 runs=getattr(e,'_pokemon_activity_skill_runs',{});old=runs.get(roll_id)
 if old is not None and (old['actor'] is not actor or old['basis']!=basis):raise ValueError('cannot replace the activity behind an observed skill roll')
 if old is not None and old.get('closed'):raise ValueError('activity skill result already consumed')
 options=_preflight(e,actor,skill,options)
 if old is None:
  if SF.event(e,actor,roll_id) is not None:raise ValueError('observed roll already belongs to another action')
  if action and not TURN.spend(e,actor,action,'포켓몬 전문활동'):return C.PendingDecision('required action unavailable')
  if seconds:e.advance_time(seconds,time_actors or [actor])
  old={'actor':actor,'basis':deepcopy(basis),'closed':False}
  if not hasattr(e,'_pokemon_activity_skill_runs'):e._pokemon_activity_skill_runs={}
  e._pokemon_activity_skill_runs[roll_id]=old
 result=SF.sequence(e,'pokemon-activity:'+roll_id,basis,[(actor,skill,options)],lambda rolls:SF.resolve_check(e,actor,skill,dc,rolls[0],options))
 old['closed']=True
 return result


def _outside(e):
 if e.encounter_active:raise ValueError('timed downtime activity cannot run inside an active encounter')

def perform(e,actor,activity,**options):
 # These concrete Pokemon routes enforce their own actual source/owner gates.
 import researcher_fields as RESEARCH
 automatic=activity=='teach_edge' and RESEARCH.pusher_funds(e,actor,options.get('target'),options.get('edge')) is not None
 if not automatic and activity!='resolve_disobedience' and (actor.kind!='pokemon' or activity not in ('command_move','plant_berry','harvest_berry')):_trainer(actor)
 fn=ACTIVITIES.get(activity)
 if fn is None:raise ValueError('unsupported Pokemon activity: '+str(activity))
 return fn(e,actor,**options)


def repair_ball(e,actor,*,ball_id,**roll):
 """ch03:359-361. Broken-on-failed-capture instance, one irreversible attempt."""
 _feature(e,actor,'repair');_tool(actor,'몬스터볼 공구함','Poké Ball Tool Box')
 import repair_restore as REPAIR
 return REPAIR.finish_ball(e,actor,ball_id=ball_id,roll=roll)

def breed(e,actor,*,pair,task_id,phase,compatible=None,**roll):
 import state_grants as G
 if not isinstance(pair,(list,tuple)) or len(pair)!=2:raise ValueError('two distinct compatible Pokemon required')
 return G.transition(e,actor,lambda se,sa,*ps:_breed(se,sa,pair=list(ps),task_id=task_id,phase=phase,compatible=compatible,**roll),participants=pair)


def _breed(e,actor,*,pair,task_id,phase,compatible=None,**roll):
 """ch03:377-379. Each accepted phase advances four actual hours."""
 _outside(e);_feature(e,actor,'breeder');_text(task_id,'breeding task id')
 if not isinstance(pair,(list,tuple)) or len(pair)!=2 or pair[0] is pair[1]:raise ValueError('two distinct compatible Pokemon required')
 for target in pair:_pokemon(target)
 import creation_egg as CREATION
 CREATION.parent_snapshot(e,pair)
 identity=[_text(t.spec.get('id'),'Pokemon identity') for t in pair]
 if len(set(identity))!=2:raise ValueError('distinct Pokemon identities required')
 records=actor.spec.get('breeding_tasks',{});previous=records.get(task_id)
 if phase=='check':
  if previous is not None:raise ValueError('breeding task already checked')
  if compatible is not True:raise ValueError('GM-established compatible pair required')
  check=_check(e,actor,__import__('hobbyist').direct_skill(actor,'edge/브리더','포켓몬학'),12,roll,seconds=4*3600,time_actors=[actor,*pair],context=('breed',task_id,identity))
  record={'pair':identity,'status':'waiting_four_hours' if check.passed else 'failed','check_total':check.total,'checked_at':e.elapsed_seconds}
  actor.spec.setdefault('breeding_tasks',{})[task_id]=record
  return {'activity':'breed','check':check,'status':record['status'],'egg':None}
 if phase!='finish':raise ValueError('breeding phase must be check or finish')
 if roll:raise ValueError('egg production phase has no additional skill check')
 if not previous or list(previous['pair'])!=identity or previous['status']!='waiting_four_hours':raise ValueError('successful unchanged breeding task required')
 import pokemon_entities as EGGS
 egg=EGGS.prepare_egg(e,actor,{'id':task_id,'parents':identity,'produced_at':e.elapsed_seconds+4*3600,'hatched':False,'source':'edge/브리더'})
 import activity_jobs as JOBS
 JOBS.run_fixed(e,actor,pair,seconds=4*3600,source='edge/브리더',job_id='breeding-finish:'+actor.entity_id+':'+task_id)
 previous['status']='egg_produced'
 actor.spec.setdefault('eggs',[]).append(egg)
 return {'activity':'breed','status':'egg_produced','egg':deepcopy(egg)}

def pokemon_interaction(e,actor,*,target,skill,dc,use_pokemon_education=False,**roll):
 """ch03:536-538. Optional substitution for these four skills only."""
 _pokemon(target);C.integer(dc,'DC')
 canonical=SKILL.skill_id(e.r.skill_policy,skill,required=True)
 if use_pokemon_education:
  _feature(e,actor,'psychologist')
  eligible={SKILL.skill_id(e.r.skill_policy,s,required=True) for s in ('매력','교활','협박','직감')}
  if canonical not in eligible:raise ValueError('this interaction skill cannot be replaced by Pokemon Education')
  skill='포켓몬학'
 check=_check(e,actor,skill,dc,roll,target=target,context=('pokemon_interaction',target.spec.get('id'),use_pokemon_education))
 return {'activity':'pokemon_interaction','skill':skill,'check':check}

def _audience(actor,target,group_id=None):
 identity=_text(actor.spec.get('id'),'trainer identity')
 if group_id is None:return 'trainer:'+identity
 _text(group_id,'GM group identity')
 members=target.spec.get('disposition_groups',{}).get(group_id)
 if not isinstance(members,list) or identity not in members:raise ValueError('trainer must belong to the GM-established disposition audience')
 return 'group:'+group_id

def _befriend_source(e,actor,target,audience,performer,disposition,choice=None):
 from source_context import verified_source
 import source_policy as POLICY
 verified_source(e.r,DISPOSITION_KR,label='wild disposition KR')
 verified_source(e.r,DISPOSITION_EN,source_root='source-audit',label='wild disposition EN')
 document={'schema':1,'id':'native/wild-disposition-source','variants':[{
  'rule_id':DISPOSITION_SOURCE,'source':DISPOSITION_KR,
  'values':{'interpretation':{'$input':'interpretation'},'actor_id':actor.entity_id,
   'target_id':target.entity_id,'audience':audience,'performer':performer,
   'initial_disposition':disposition,'english_source':DISPOSITION_EN},
  'inputs':{'interpretation':{'type':'string','authority':'gm','decision_kind':'source_conflict',
   'choices':['kr_one_step','en_hostile_to_neutral'],
   'question':'Choose the complete KR one-step disposition rule or EN Hostile-to-Neutral rule; all other checks, actions and relationships are shared.'}}}]}
 return POLICY.resolve(e.r,document,decisions={} if choice is None else {'interpretation':choice})


def befriend(e,actor,*,target,use_pokemon_education=False,use_mystic_senses=False,group_id=None,friendship_performer=None,friendship_audience=None,source_choice=None,source_query=False,**roll):
 """ch05:717-738. State belongs to one trainer or an explicit GM audience."""
 _pokemon(target)
 if not target.spec.get('wild',False) or target.captured:raise ValueError('wild Pokemon required')
 if type(use_mystic_senses) is not bool:raise ValueError('Mystic Senses choice must be boolean')
 if use_mystic_senses:
  if use_pokemon_education or friendship_performer is not None:raise ValueError('choose one friendship skill substitution')
  import elemental_connection as ELEMENTAL
  ELEMENTAL.require_mystic(e,actor)
 failure_subject='trainer:'+_text(actor.spec.get('id'),'trainer identity')
 if friendship_performer is not None:
  _pokemon(friendship_performer);_owner(actor,friendship_performer)
  if friendship_audience is None:return C.PendingDecision('GM must identify whether the friendship concerns the Pokemon performer or an explicit group')
  failure_subject='pokemon:'+_text(friendship_performer.spec.get('id'),'performer identity')
  if friendship_audience=='performer':
   if group_id is not None:raise ValueError('performer relationship cannot also select a group')
   audience=failure_subject
  elif friendship_audience=='group':
   audience=_audience(actor,target,group_id)
   if group_id is None or friendship_performer.spec['id'] not in target.spec.get('disposition_groups',{}).get(group_id,[]):raise ValueError('GM group must explicitly include the performer and trainer')
  else:raise ValueError('unsupported GM friendship relationship; trainer disposition is not implicitly improved')
 else:
  if friendship_audience is not None:raise ValueError('friendship relationship requires a Pokemon performer')
  audience=_audience(actor,target,group_id)
 import pokemon_entities as ENTITIES
 disposition=ENTITIES.disposition_projection(target,audience)['value']
 if disposition not in DISPOSITIONS:raise ValueError('GM-selected disposition required')
 if e.r._selected_rule(DISPOSITION_SOURCE)!=DISPOSITION_SOURCE:raise ValueError('selected disposition source needs its own activity policy')
 if type(source_query)is not bool or source_query and source_choice is not None:raise ValueError('choose a source query or one scoped source decision')
 if source_query:return _befriend_source(e,actor,target,audience,failure_subject,disposition)
 if source_choice is None:
  source={'interpretation':'kr_one_step','authority':'authored_default','source':DISPOSITION_KR}
 else:
  source=_befriend_source(e,actor,target,audience,failure_subject,disposition,source_choice)
  if source['status']!='PolicyValuesReady':raise ValueError('complete scoped disposition source decision required')
 interpretation=source.get('interpretation',source.get('values',{}).get('interpretation'))
 index=DISPOSITIONS.index(disposition)
 if index==5:return {'activity':'befriend','status':'already_very_friendly','captured':False,'audience':audience}
 if failure_subject in target.spec.get('befriend_failures',[]):raise ValueError('retry requires GM permission after changed circumstances')
 skill='직감' if use_mystic_senses else '매력'
 if use_pokemon_education:_feature(e,actor,'psychologist');skill='포켓몬학'
 if friendship_performer is not None:
  if use_pokemon_education:raise ValueError('contest friendship cannot combine Pokemon Education substitution')
  from contest_features import friendship_check
  check=friendship_check(e,actor,friendship_performer,target,dc=DISPOSITION_DC[index],roll_options=roll)
 else:check=_check(e,actor,skill,DISPOSITION_DC[index],roll,action='standard',target=target,context=('befriend',target.spec.get('id'),audience,disposition))
 if isinstance(check,C.PendingDecision):return check
 if check.passed:disposition='중립' if index==1 and interpretation=='en_hostile_to_neutral' else DISPOSITIONS[index+1]
 else:target.spec.setdefault('befriend_failures',[]).append(failure_subject)
 target.spec.setdefault('dispositions',{})[audience]=disposition
 ENTITIES.record_disposition(e,target,audience=audience,before=DISPOSITIONS[index],after=disposition,reason=f'native {skill} check succeeded' if check.passed else f'native {skill} check failed; retry locked',performer=failure_subject,check_total=check.total)
 target.spec['disposition_history'][-1]['source_decision']=deepcopy(source)
 return {'activity':'befriend','skill':skill,'check':check,'disposition':disposition,'captured':False,'audience':audience,'source_decision':deepcopy(source)}

def disposition_ruling(e,actor,*,target,disposition,reason,allow_retry=False,group_id=None,group_members=None,friendship_performer=None,friendship_audience=None):
 """Explicit GM relationship and changed-circumstance retry, for one performer."""
 _pokemon(target);_text(reason,'GM decision reason')
 import pokemon_entities as ENTITIES
 ENTITIES.validate_dispositions(target)
 if not target.spec.get('wild',False) or target.captured:raise ValueError('wild Pokemon disposition observation required')
 if disposition not in DISPOSITIONS or type(allow_retry) is not bool:raise ValueError('invalid GM disposition decision')
 performer_id='trainer:'+_text(actor.spec.get('id'),'trainer identity')
 if friendship_performer is not None:
  _pokemon(friendship_performer);_owner(actor,friendship_performer)
  roster=[*getattr(e,'everyone',[]),*getattr(e,'_time_actors',[]),*getattr(e.gm,'everyone',[])]
  for subject in (actor,friendship_performer,target):
   matches={id(a):a for a in roster if a.spec.get('id')==subject.spec.get('id')}
   if subject.r is not e.r or not subject.spec.get('id') or len(matches)!=1 or next(iter(matches.values())) is not subject:raise ValueError('actual uniquely registered GM friendship participants required')
  if friendship_performer is target:raise ValueError('a friendship subject cannot be its own wild target')
  if friendship_audience not in ('performer','group'):raise ValueError('explicit GM performer or group relationship required')
  performer_id='pokemon:'+_text(friendship_performer.spec.get('id'),'performer identity')
 elif friendship_audience is not None:raise ValueError('friendship relationship requires an actual Pokemon performer')
 if friendship_audience=='performer' and (group_id is not None or group_members is not None):raise ValueError('performer relationship cannot also select a group')
 if group_members is not None:
  _text(group_id,'GM group identity')
  if not isinstance(group_members,list) or not group_members or len(set(group_members))!=len(group_members):raise ValueError('distinct nonempty GM group members required')
  for member in group_members:_text(member,'GM group member identity')
  if actor.spec.get('id') not in group_members:raise ValueError('acting trainer must belong to the GM group')
  previous_members=target.spec.get('disposition_groups',{}).get(group_id)
  if previous_members is not None and previous_members!=group_members:raise ValueError('changing audience membership requires a new GM group identity')
 if friendship_audience=='performer':audience=performer_id
 elif group_members is not None:audience='group:'+group_id
 else:audience=_audience(actor,target,group_id)
 if friendship_audience=='group':
  members=group_members if group_members is not None else target.spec.get('disposition_groups',{}).get(group_id,[])
  if group_id is None or friendship_performer.spec['id'] not in members:raise ValueError('GM group must explicitly include the performer and trainer')
 previous=target.spec.get('dispositions',{}).get(audience,target.spec.get('disposition'))
 # All declarations are validated before any relationship or retry is changed.
 if group_members is not None:target.spec.setdefault('disposition_groups',{})[group_id]=list(group_members)
 target.spec.setdefault('dispositions',{})[audience]=disposition
 if allow_retry:target.spec['befriend_failures']=[x for x in target.spec.get('befriend_failures',[]) if x!=performer_id]
 ENTITIES.record_disposition(e,target,audience=audience,before=previous,after=disposition,reason=reason,performer=performer_id,retry_allowed=allow_retry)
 e.r.rulings.record('pokemon_disposition',str(target.spec.get('id',target.name))+':'+audience,previous,disposition,reason,'scene')
 if allow_retry:e.r.rulings.record('pokemon_befriend_retry',str(target.spec.get('id',target.name))+':'+performer_id,'failed','permitted',reason,'scene')
 return {'activity':'disposition_ruling','disposition':disposition,'retry_allowed':allow_retry,'retry_performer':performer_id if allow_retry else None,'captured':False,'audience':audience}


def pokemaniac(e,actor,*,target,**roll):
 """One native check/cost owner for the Book and independent CSV49."""
 _feature(e,actor,'maniac');_pokemon(target)
 import state_grants as G,world_entities as WORLD,pokemon_entities as ENTITIES
 import trainer_feature_acquisition as ACQUISITION
 WORLD.require_actors(e,actor,target)
 records=ACQUISITION.static_acquisitions(actor,MANIAC,active=True)
 if len(records)>1:raise ValueError('one actual Pokemaniac source required')
 source=pokemaniac_snapshot_source(e.r,records[0][1]['snapshot']) if records else pokemaniac_source(e.r)
 missing=[x for x in ('nature',) if target.spec.get(x) is None]
 if missing:return C.PendingDecision('GM target information missing: '+','.join(missing))
 C.integer(target.level,'Pokemon level',1)
 _text(target.spec['nature'],'Pokemon nature')
 if not isinstance(target.types,(list,tuple)) or any(not isinstance(value,str) or not value for value in target.types):raise ValueError('Pokemon types must be identity text')
 if not isinstance(target.abilities,(list,tuple)) or any(not isinstance(value,str) or not value for value in target.abilities):raise ValueError('Pokemon abilities must be identity text')
 info={'level':target.level,'types':list(target.types),'nature':target.spec['nature'],'abilities':list(target.abilities)}
 dc=10;origin=None
 if source['edition']=='local_csv':
  origin=ENTITIES.origin_information(e,target)
  if isinstance(origin,C.PendingDecision):return origin
  info.update(special=origin['special'],original_species_changes=deepcopy(origin['changes']))
  C.integer(actor.level,'Trainer level',1,50);M.validate_source(e.r)
  dc=M.ceil_ratio(target.level-actor.level,5)+10
 # The existing observed-roll owner rejects replacing either source or facts
 # after an already paid first roll, including a pending helper/reroll choice.
 context=('pokemaniac',target.spec['id'],source,info,origin)
 check=G.transition(e,actor,lambda se,sa,st:_check(se,sa,__import__('hobbyist').direct_skill(sa,MANIAC,'포켓몬학'),dc,roll,action='standard',context=context),participants=(target,))
 if isinstance(check,C.PendingDecision):return check
 return {'activity':'pokemaniac','check':check,'information':info if check.passed else None}

def observe_pokemon_origin(e,actor,*,target,special,original_species,changes,reason):
 import pokemon_entities as ENTITIES,world_entities as WORLD
 WORLD.require_actors(e,actor,target)
 return ENTITIES.observe_origin(e,target,special=special,original_species=original_species,changes=changes,reason=reason)

ACTIVITIES={'observe_pokemon_origin':observe_pokemon_origin,'repair_ball':repair_ball,'breed':breed,'pokemon_interaction':pokemon_interaction,
 'befriend':befriend,'disposition_ruling':disposition_ruling,'pokemaniac':pokemaniac}


RODS={'낡은낚싯대':'old','좋은낚싯대':'good','대단한낚싯대':'super',
      'Old Rod':'old','Good Rod':'good','Super Rod':'super'}
FISHING_SOURCE='ch05-pokemon/낚시'

def fishing(e,actor,*,phase,rod=None,attachment=None,target=None,roll_d20=None,escape_d20=None,habitat=None,choice=None,random_choice=False,source_policy=None,party=None,level_match_reason=None,cause=None,lost=None,reason=None,**roll):
 import state_grants as G,world_entities as WORLD
 if party is not None and not isinstance(party,list):raise ValueError('actual comparable trainer party required')
 participants=([target] if target is not None else [])+list(party or [])
 WORLD.require_actors(e,actor,*participants)
 if e.r._selected_rule(FISHING_SOURCE)!=FISHING_SOURCE:
  raise ValueError('selected fishing source needs its own activity policy')
 return G.transition(e,actor,lambda se,sa,*st:_fishing(se,sa,phase=phase,rod=rod,
  attachment=attachment,target=st[0] if target is not None else None,roll_d20=roll_d20,
  escape_d20=escape_d20,habitat=habitat,choice=choice,random_choice=random_choice,source_policy=source_policy,
  party=list(st[1:] if target is not None else st) if party is not None else None,
  level_match_reason=level_match_reason,cause=cause,lost=lost,reason=reason,**roll),participants=participants)

def _fishing(e,actor,*,phase,rod=None,attachment=None,target=None,roll_d20=None,escape_d20=None,habitat=None,choice=None,random_choice=False,source_policy=None,party=None,level_match_reason=None,cause=None,lost=None,reason=None,book_stats=None,**roll):
 """ch05 five-minute or explicitly selected ch09 fifteen-minute attraction.
 Bait is attached/reserved until its sourced loss; a landed fish is not captured.
 """
 _outside(e)
 import encounter_candidates as CANDIDATES
 if type(random_choice) is not bool:raise ValueError('explicit random selection flag required')
 if phase!='select' and (choice is not None or random_choice):raise ValueError('species selection is a separate hooked encounter decision')
 if phase!='start' and habitat is not None:raise ValueError('regional fishing habitat is fixed for this session')
 state=actor.spec.get('fishing_session')
 source=source_policy
 if source is None:source=state.get('source',FISHING_SOURCE) if state and phase!='start' else FISHING_SOURCE
 if source not in (FISHING_SOURCE,'item/미끼'):raise ValueError('known fishing source policy required')
 if source=='item/미끼':CANDIDATES.equipment(e.r,'미끼')
 if phase not in ('reel','lure_loss') and (party is not None or level_match_reason is not None):raise ValueError('party comparison belongs to the actual hooked target')
 if phase!='lure_loss' and (cause is not None or lost is not None or reason is not None):raise ValueError('possible lure loss needs its own observed event')
 if phase=='start':
  if roll or roll_d20 is not None or escape_d20 is not None or target is not None:raise ValueError('starting fishing does not roll or select a target')
  if state and state['status'] in ('waiting','hooked'):raise ValueError('finish or abandon the current fishing session first')
  if state and state['attachment']=='루어' and state['status']=='escaped' and 'lure_loss' not in state:raise ValueError('resolve possible lure loss after the actual escape first; historical escape alone does not establish retained or lost stock')
  if rod not in RODS:raise ValueError('known fishing rod required')
  _tool(actor,rod)
  if attachment not in ('미끼','루어'):raise ValueError('bait or reusable lure required')
  inv=actor.spec.get('items',{})
  if type(inv.get(attachment)) is not int or inv[attachment]<1:raise ValueError('owned bait/lure required')
  pool=CANDIDATES.fishing_pool(e.r,habitat) if habitat is not None else None
  if source=='item/미끼' and pool is None:raise ValueError('ch09 fishing requires the actual regional candidates')
  profile=CANDIDATES.equipment(e.r,attachment)
  actor.spec['fishing_session']={'source':source,'rod':rod,'attachment':attachment,'unit_price':profile['price'],'misses':0,'status':'waiting'}
  if pool is not None:actor.spec['fishing_session']['regional_candidates']=pool
  return deepcopy(actor.spec['fishing_session'])
 if not state:raise ValueError('fishing session must be started')
 if state.get('source',FISHING_SOURCE)!=source:raise ValueError('fishing session belongs to another source policy')
 CANDIDATES.equipment(e.r,state['attachment'])
 if rod is not None or attachment is not None:raise ValueError('cannot change rod or attachment mid-session')
 _tool(actor,state['rod']);inv=actor.spec.get('items',{})
 if inv.get(state['attachment'],0)<1:raise ValueError('reserved fishing attachment unavailable')
 pool=state.get('regional_candidates')
 if pool is not None:CANDIDATES.validate_pool(e.r,pool)
 if phase=='select':
  if state['status']!='hooked' or pool is None:raise ValueError('hooked regional fishing session required before species selection')
  if target is not None or roll or roll_d20 is not None or escape_d20 is not None:raise ValueError('species selection does not roll a bite or reel check')
  if source=='item/미끼' and (choice is not None or not random_choice):raise ValueError('ch09 attraction requires actual random regional selection')
  state['regional_selection']=CANDIDATES.select(e,pool,choice=choice,random_choice=random_choice,previous=state.get('regional_selection'))
  return deepcopy(state)
 if phase=='wait':
  if state['status']!='waiting':raise ValueError('no waiting fishing session')
  if target is not None or roll or escape_d20 is not None:raise ValueError('bite check is not the subsequent Athletics check')
  if roll_d20 is not None:C.integer(roll_d20,'bite d20',1,20)
  bonus=WILD_EQUIPMENT.tools_bonus(e,actor,'attraction')
  e.advance_time(900 if source=='item/미끼' else 300,[actor]);face=e.roll_d20(actor,'fishing_bite',fixed=roll_d20)
  if face+bonus>=15:state['status']='hooked'
  else:
   state['misses']+=1
   if state['attachment']=='미끼' and state['misses']>=3:
    inv['미끼']-=1;state['status']='bait_consumed'
  return dict(deepcopy(state),bite_roll=face,bite_bonus=bonus,bite_total=face+bonus,captured=False)
 if phase=='lure_loss':
  if roll or roll_d20 is not None or escape_d20 is not None:raise ValueError('observed possible lure loss does not roll a new check')
  return WILD_EQUIPMENT.lure_loss(e,actor,state,target=target,cause=cause,lost=lost,reason=reason,party=party,level_match_reason=level_match_reason)
 if phase!='reel' or state['status']!='hooked':raise ValueError('hooked Pokemon required before reeling')
 if roll_d20 is not None:raise ValueError('reeling does not repeat the bite roll')
 WILD_EQUIPMENT._wild(e,target)
 if pool is not None:CANDIDATES.require_target(e.r,pool,state.get('regional_selection'),target)
 identity=_text(target.spec.get('id'),'hooked Pokemon identity')
 if state.get('target_id') is not None and state['target_id']!=identity:raise ValueError('cannot replace the Pokemon already hooked in this fishing session')
 if source=='item/미끼' and state.get('target_id') is None:
  comparison=WILD_EQUIPMENT.comparable_party(e,actor,target,party,level_match_reason)
 else:
  if party is not None or level_match_reason is not None:raise ValueError('party comparison already belongs to the actual hooked occurrence')
  comparison={}
 rod_kind=RODS[state['rod']]
 if rod_kind!='super':
  if target.spec.get('evolved') is not False:raise ValueError('unevolved target must be explicitly established for this rod')
  if rod_kind=='old' and (target.level>10 or target.spec.get('size') not in ('Small','작음','소형')):raise ValueError('Old Rod requires an unevolved Small Pokemon of level10 or less')
 if escape_d20 is not None:C.integer(escape_d20,'escape d20',1,20)
 if source==FISHING_SOURCE:
  from source_context import verified_source
  verified_source(e.r,DISPOSITION_EN,source_root='source-audit',label='fishing failed-reel lure loss EN clarification')
 options=dict(roll);options['mods']=options.get('mods',0)+WILD_EQUIPMENT.tools_bonus(e,actor,'fishing_reel')
 check=_check(e,actor,'육상',8,options,context=('fishing_reel',target.spec.get('id'),state['rod'],state['attachment']))
 state=actor.spec['fishing_session'];inv=actor.spec['items']
 state.update(comparison)
 state['target_id']=identity
 escaped=None
 target.spec['fishing']=True
 if check.passed:
  state['status']='landed'
  __import__('study_books').fished(e,actor,target,book_stats)
 else:
  if state['attachment']=='미끼':
   escaped=True;inv['미끼']-=1;state['status']='bait_lost'
  else:
   face=e.roll_d20(actor,'fishing_escape',fixed=escape_d20)
   escaped=face<=10
   state['reel_failure']={'target_id':identity,'rod':state['rod'],'attachment':'루어',
    'check_total':check.total,'dc':8,'escape_d20':face,'escaped':escaped,'at':e.elapsed_seconds,'source':source}
   if escaped:
    state['status']='escaped'
    if source==FISHING_SOURCE:
     before=inv['루어'];inv['루어']-=1
     state['lure_loss']={**deepcopy(state['reel_failure']),'cause':'escaped','lost':True,
      'reason':'failed Athletics; actual secondary d20 <=10 takes the lure',
      'stock_before':before,'stock_after':inv['루어'],'english_source':deepcopy(DISPOSITION_EN)}
 return dict(deepcopy(state),check=check,escaped=escaped,captured=False)


def command_loyalty(e,actor,*,target,use_intimidate=False,dc_override=None,gm_failure=None,**roll):
 return _command_loyalty(e,actor,target=target,use_intimidate=use_intimidate,dc_override=dc_override,gm_failure=gm_failure,roll=roll)


def _command_loyalty(e,actor,*,target,use_intimidate=False,dc_override=None,gm_failure=None,roll=None,legendary_control=False):
 """ch05:563-643. Loyalty is GM-maintained; failure never picks a random victim."""
 _pokemon(target)
 _owner(actor,target)
 import world_entities as WORLD
 WORLD.require_actors(e,actor,target)
 pending=loyalty_pending(e,target,legendary_control=legendary_control)
 if pending is not None:return pending
 loyalty=command_loyalty_value(e,target,legendary_control=legendary_control);C.integer(loyalty,'effective GM loyalty',0)
 roll={} if roll is None else roll
 if use_intimidate:_feature(e,actor,'beast')
 if loyalty>=2:
  if dc_override is not None or roll:raise ValueError('ordinary loyalty2+ does not require an obedience check')
  return {'activity':'command_loyalty','obeys':True,'check':None}
 dc=20 if loyalty==0 else 8
 if dc_override is not None:
  C.integer(dc_override,'GM initial obedience DC',dc)
  if loyalty!=0 or not target.spec.get('initial_disobedience'):raise ValueError('higher initial DC applies only to the GM-established loyalty0 case')
  dc=dc_override
 if gm_failure is not None:
  if not isinstance(gm_failure,dict) or gm_failure.get('kind') not in ('idle','action'):raise ValueError('GM failure decision must be idle or an explicit action')
  _text(gm_failure.get('reason'),'GM disobedience reason')
  if gm_failure['kind']=='action':_text(gm_failure.get('action'),'GM action');_text(gm_failure.get('target'),'GM target')
 skill=__import__('hobbyist').direct_skill(actor,'edge/비스트-마스터','협박') if use_intimidate else '명령'
 check=_check(e,actor,skill,dc,roll,target=target,context=('command_loyalty',target.spec.get('id'),use_intimidate))
 return {'activity':'command_loyalty','obeys':check.passed,'check':check,
         'failure':deepcopy(gm_failure) if not check.passed and gm_failure else C.PendingDecision('GM chooses disobedient action and target') if not check.passed else None}


def experience_training(e,actor,*,targets,**options):
 """Commit the whole hour, every target and trainer quota as one graph."""
 if not isinstance(targets,(list,tuple)) or not targets or len(targets)>6:raise ValueError('one to six distinct Pokemon required')
 import state_grants as G
 if options.get('book_target') is not None and not any(options['book_target'] is target for target in targets):raise ValueError('one actual owned training participant required')
 def apply(se,sa,*st):
  copied=G._stage_transition_payload(e,se,options)
  return _experience_training(se,sa,targets=list(st),**copied)
 return G.transition(e,actor,apply,participants=tuple(targets))


def _csv_training_source(rules,provider,cache_name,label):
 """Verify one provider-specific CSV substitution without mixing sites."""
 import json,hashlib,csv,io
 from pathlib import Path
 from source_context import verified_source
 root=Path(rules.root).resolve()
 raw=root.joinpath('data/training-source-policies.json').read_bytes()
 identity=(str(root),hashlib.sha256(raw).hexdigest())
 policy=getattr(rules,cache_name,None)
 if policy is not None and getattr(rules,cache_name+'_identity',None)!=identity:
  raise ValueError(label+' definition or root changed; review required')
 if policy is None:
  policy=json.loads(raw.decode('utf-8'))[provider]['csv_target_limit']
 content=verified_source(rules,policy,label=label+' CSV')
 rows=list(csv.reader(io.StringIO(content.decode('utf-8-sig'))))
 if rows[policy['record']-1]!=policy['cells']:raise ValueError(label+' source record changed')
 selected=rules.select_source_definition(policy['source'],source={'file':policy['file'],'sha256':policy['sha256']})
 if selected['selected_id']!=policy['source']:raise ValueError(label+' CSV replacement needs its own policy')
 if selected['source'].get('record_span')!=[policy['record'],policy['record']]:raise ValueError(label+' CSV source record identity mismatch')
 setattr(rules,cache_name,deepcopy(policy))
 setattr(rules,cache_name+'_identity',identity)
 return deepcopy(policy)



def _groomer_csv_source(rules):
 return _csv_training_source(rules,'groomer','_groomer_csv_policy','Groomer')


def _beast_csv_source(rules):
 return _csv_training_source(rules,'beast_master','_beast_csv_policy','Beast Master')


def _experience_training(e,actor,*,targets,use_intimidate=False,from_grooming=False,from_training=False,safe=None,bonus_skill=None,grooming_policy=None,beast_policy=None,use_reserves=False,pushed_skills=None,type_manual=None,book_target=None,**unused):
 """Native one-hour training and sourced Beast Master substitution (ch05:229-236).
 Special feat/edge teaching is a separate application; this grants XP only.
 """
 import downtime as DT
 import pokemon_progression as PROGRESSION
 PROGRESSION.source(e.r,PROGRESSION.TRAINING)
 PROGRESSION.validate(actor.spec)
 for target in targets:PROGRESSION.validate(target.spec)
 import world_entities as WORLD
 WORLD.require_actors(e,actor,*targets)
 if unused:raise ValueError('experience training does not make a skill check')
 import training_eligibility as ELIGIBILITY
 eligibility=ELIGIBILITY.experience_plan(e,actor,targets,use_intimidate=use_intimidate,use_reserves=use_reserves,
  from_grooming=from_grooming,from_training=from_training,safe=safe,bonus_skill=bonus_skill,grooming_policy=grooming_policy,beast_policy=beast_policy)
 skill=eligibility['skill'];rank=eligibility['rank'];limit=eligibility['target_limit'];xp_rank=eligibility['xp_rank']
 selected_policy=eligibility['grooming_policy'];selected_beast=eligibility['beast_policy'];rank_plans=eligibility['rank_plans']
 import training_rewards as REWARDS
 value=REWARDS.policy(eligibility,3600,[{'id':'experience','source':PROGRESSION.TRAINING,'kind':'xp','formula':REWARDS.native_xp_formula()}],identity='native:experience-training')
 result=REWARDS.execute(e,actor,targets,value,safe=safe,from_grooming=from_grooming,from_training=from_training,
  pushed_skills=pushed_skills,type_manual=type_manual,_eligibility=eligibility,_pushed_source='experience_training')
 book_bonus=__import__('study_books').training_bonus(e,actor,targets,book_target)
 awards=[row['base_award'] for row in result['awards'][0]['outputs']]
 return {'activity':'experience_training','skill':skill,'rank':rank,'limit':limit,'xp_rank':xp_rank,'grooming_policy':selected_policy if from_grooming else None,'beast_policy':selected_beast,'awards':awards,'rank_plans':deepcopy(rank_plans),'eligibility':deepcopy(eligibility),'reward_record_id':result['reward_record_id'],'study_book':book_bonus}

ACTIVITIES.update(fishing=fishing,command_loyalty=command_loyalty,experience_training=experience_training)



def groom(e,actor,*,targets,pushed_skills=None,safe=None):
 """Commit the hour, all credits and follow-up training effects together."""
 if not isinstance(targets,(list,tuple)) or not targets or len(targets)>6:raise ValueError('one to six distinct Pokemon required')
 import state_grants as G
 return G.transition(e,actor,lambda se,sa,*st:_groom(se,sa,targets=list(st),pushed_skills=pushed_skills,safe=safe),participants=tuple(targets))


def _groom(e,actor,*,targets,pushed_skills=None,safe=None):
 """ch03:387-389: native hour, own 1..6 Pokemon, training credit and day bonus.
 Subsequent chosen training features retain their own acquisition/cost checks.
 """
 import world_entities as WORLD
 WORLD.require_actors(e,actor,*targets)
 _outside(e);_feature(e,actor,'groomer');_tool(actor,'미용사 킷',"Groomer's Kit")
 import training_eligibility as ELIGIBILITY
 eligibility=ELIGIBILITY.prepare(e,actor,targets,ELIGIBILITY.native('groom'),safe=safe)
 import training_rewards as REWARDS,activity_jobs as JOBS
 value=REWARDS.policy(eligibility,3600,[{'id':'completed-grooming','source':'edge/미용사','kind':'credit','publication':'grooming','policy':JOBS.training_policy()},
  {'id':'introduction','source':'edge/미용사','kind':'groom','intro_dice':1}],identity='native:grooming-rewards')
 result=REWARDS.execute(e,actor,targets,value,safe=safe,pushed_skills=pushed_skills,_eligibility=eligibility,_pushed_source='edge/미용사')
 return {'activity':'groom','groomed':[t.spec.get('id',t.name) for t in targets],'intro_dice':1,'day':eligibility['day'],'eligibility':deepcopy(eligibility),'reward_record_id':result['reward_record_id']}


def fossil(e,actor,*,phase,fossil_id=None,skill='포켓몬학',site=None,dc=None,minutes=None,discovery=None,hatch_details=None,**roll):
 """ch05:748-756. GM-selected deposits/results; Paleontologist restoration.
 Search DC15/18/25 are guidance, not a guarantee that an ordinary cave has fossils.
 """
 _outside(e)
 if SKILL.skill_id(e.r.skill_policy,skill,required=True) not in {SKILL.skill_id(e.r.skill_policy,s) for s in ('포켓몬학','생존')}:raise ValueError('fossil activity uses Pokemon Education or Survival')
 if phase=='restore':
  import creation_fossil as RESTORATION
  return RESTORATION.restore_native(e,actor,fossil_id=fossil_id,hatch_details=hatch_details,**roll)
 if phase=='search':
  if not isinstance(site,dict) or type(site.get('fossils_present')) is not bool:raise ValueError('GM-established site and fossil availability required')
  _text(site.get('name'),'fossil site name');C.integer(dc,'GM fossil DC');C.integer(minutes,'GM afternoon search duration',1)
  qualified=max(_rank(e,actor,'포켓몬학'),_rank(e,actor,'생존'))>=4 or _feature(e,actor,'paleontologist',False)
  if discovery is not None:
   if not qualified or not site['fossils_present']:raise ValueError('fossil discovery requires a qualified searcher and a fossil-bearing site')
   if not isinstance(discovery,dict):raise ValueError('GM discovery details required')
   _text(discovery.get('id'),'fossil instance identity')
   if discovery.get('species') not in e.r.species:raise ValueError('known fossil species required')
   if discovery['id'] in actor.spec.get('fossils',{}):raise ValueError('fossil instance already exists')
   import pokemon_entities as EGGS
   discovered=EGGS.prepare_fossil(e,actor,discovery['id'],dict(deepcopy(discovery),status='fossil',source_site=deepcopy(site)))
  check=_check(e,actor,skill,dc,roll,seconds=minutes*60,context=('fossil_search',site,discovery))
  result=None
  if check.passed and discovery:
   result=discovered
   actor.spec.setdefault('fossils',{})[discovery['id']]=result
  return {'activity':'fossil','phase':phase,'check':check,'fossil':deepcopy(result),'qualified':qualified}
 _feature(e,actor,'paleontologist')
 record=actor.spec.get('fossils',{}).get(fossil_id)
 if not record or record.get('status')!='fossil':raise ValueError('unconsumed owned fossil instance required')
 import pokemon_entities as EGGS
 planned=EGGS.prepare_fossil(e,actor,fossil_id,record)
 if phase=='identify':
  check=_check(e,actor,skill,10,roll,context=('fossil_identify',fossil_id))
  record=actor.spec['fossils'][fossil_id]
  record.clear();record.update(planned)
  if check.passed:record['identified']=True
  return {'activity':'fossil','phase':phase,'check':check,'species':record['species'] if check.passed else None}
 raise ValueError('unknown fossil operation')

ACTIVITIES.update(groom=groom,fossil=fossil)



def mounting(e,actor,*,target,phase,skill='곡예',gm_mountable=None,dc=10,**roll):
 import control_mount as MOUNT
 return MOUNT.native(e,actor,target=target,phase=phase,skill=skill,gm_mountable=gm_mountable,dc=dc,**roll)


def _mounting_native(e,actor,*,target,phase,skill='곡예',gm_mountable=None,dc=10,**roll):
 """ch03:528-530, ch05:787. Automatic boarding is distinct from retention.
 Movement sharing and damage-trigger production belong to the mounted-movement
 extension; this entry resolves an explicitly declared boarding/retention action.
 """
 _pokemon(target)
 import world_entities as WORLD
 WORLD.require_mount_target(e,actor,target)
 if SKILL.skill_id(e.r.skill_policy,skill,required=True) not in {SKILL.skill_id(e.r.skill_policy,s) for s in ('곡예','육상')}:raise ValueError('mounting uses Acrobatics or Athletics')
 _text(target.spec.get('id'),'mount identity');C.integer(dc,'mounting DC')
 prowess=_feature(e,actor,'mounted',False)
 if phase=='mount':
  if gm_mountable is not True:raise ValueError('GM must establish size, strength and equipment permit mounting')
  if actor.spec.get('mount_id'):raise ValueError('actor is already mounted')
  if dc!=10:raise ValueError('ordinary boarding DC is10; other procedure requires its own policy')
  if prowess:
   if roll:raise ValueError('automatic boarding does not roll dice or spend roll resources')
   if not TURN.spend(e,actor,'standard','포켓몬 탑승'):return C.PendingDecision('required action unavailable')
   check=None;passed=True
  else:
   check=_check(e,actor,skill,10,roll,action='standard',context=('mounting',phase,target.spec.get('id')))
   if isinstance(check,C.PendingDecision):return check
   passed=check.passed
  if passed:actor.spec['mount_id']=target.spec['id']
 elif phase=='retain':
  if gm_mountable is not None:raise ValueError('retention does not replace GM mounting admission')
  if actor.spec.get('mount_id')!=target.spec['id']:raise ValueError('actor must be riding this Pokemon')
  options=dict(roll);options['mods']=options.get('mods',0)+(3 if prowess else 0)
  actual_skill=__import__('hobbyist').direct_skill(actor,'edge/탑승-기량',skill) if prowess else skill
  check=_check(e,actor,actual_skill,dc,options,context=('mounting',phase,target.spec.get('id')));passed=check.passed
  if not passed:actor.spec.pop('mount_id',None)
 else:raise ValueError('mount phase must be mount or retain')
 return {'activity':'mounting','phase':phase,'check':check,'passed':passed,'automatic':phase=='mount' and prowess,'retention_bonus':3 if phase=='retain' and prowess else 0}

ACTIVITIES.update(mounting=mounting)



def observe_ball(e,actor,*,attempt_id,condition,reason):
 import state_grants as G
 return G.transition(e,actor,lambda se,sa:_observe_ball(se,sa,attempt_id=attempt_id,condition=condition,reason=reason),include_rulings=True)

def _observe_ball(e,actor,*,attempt_id,condition,reason):
 """Bind GM-observed physical outcome to a real native throw. No forged free ball."""
 _text(reason,'GM observed ball condition reason')
 attempt=actor.spec.get('capture_attempts',{}).get(attempt_id)
 if not isinstance(attempt,dict):raise ValueError('real capture attempt required')
 if condition=='broken':
  if attempt.get('status')!='failed_capture' or not attempt.get('hit') or attempt.get('captured'):raise ValueError('repair record requires a failed capture and observed broken ball')
  record={'item':attempt['item'],'ball_kind':attempt['ball_kind'],'cause':'failed_capture','capture_attempt_id':attempt_id,'status':'broken','gm_reason':reason}
  import csv_item_physical_contracts as CSV_ITEMS
  ball=CSV_ITEMS.cannon_attempt_ball(e,actor,attempt)
  if ball is not None:
   ball['disabled']=True;ball['ball_integrity']={'intact':False,'source':'pokemon/capture-rate','basis':'GM observed failed-capture breakage','reason':reason};record['physical_instance_id']=ball['id']
  actor.spec.setdefault('broken_balls',{})[attempt_id]=record;attempt['status']='broken'
  return {'activity':'observe_ball','ball_id':attempt_id,'status':'broken'}
 if condition=='recovered_intact':
  if attempt.get('status') not in ('failed_capture','recoverable_on_ground'):raise ValueError('unclaimed intact thrown ball required')
  import csv_item_physical_contracts as CSV_ITEMS
  recovered=CSV_ITEMS.recover_cannon_ball(e,actor,attempt)
  if isinstance(recovered,C.PendingDecision):return recovered
  if not recovered:
   inv=actor.spec.setdefault('items',{});inv[attempt['item']]=inv.get(attempt['item'],0)+1
  attempt['status']='recovered_intact';attempt['gm_reason']=reason
  return {'activity':'observe_ball','ball_id':attempt_id,'status':'recovered_intact','physical_instance_id':attempt.get('physical_instance_id')}
 raise ValueError('explicit broken or recovered_intact observation required')

ACTIVITIES.update(observe_ball=observe_ball)



def command_loyalty_value(e,pokemon,*,legendary_control=False):
 import mega_forms as MEGA,pokemon_entities as ENTITIES,legendary_commands as LEGENDARY
 return 0 if MEGA.uncontrolled(e,pokemon) or not legendary_control and LEGENDARY.uncontrolled(e,pokemon) else ENTITIES.effective_loyalty_value(pokemon,engine=e)


def loyalty_pending(e,pokemon,*,legendary_control=False):
 if pokemon.kind!='pokemon' or not pokemon.spec.get('trainer_id'):return None
 import legendary_commands as LEGENDARY
 pending=LEGENDARY.pending(e,pokemon)
 if pending is not None:return pending
 if command_loyalty_value(e,pokemon,legendary_control=legendary_control) is None:return C.PendingDecision('GM observation of loyalty for the current trainer relationship')
 return None


def obedience_gate(e,pokemon,target,move_id,*,action_grant=None):
 """One-use authority for a declared low-loyalty owned Pokemon command.
 Wild Pokemon without an owner and explicit native reactive grants are not
 treated as trainer commands. An internal chained activation must itself hold
 the native action grant; a caller's free_action/count_use flag is insufficient.
 """
 for receipt in getattr(e,'_obedience_receipts',[]):
  if receipt.get('pack_mon') and not receipt['used'] and receipt['pokemon'] is pokemon and receipt['target'] is target and receipt['move_id']==move_id:
   import pack_mon as PACK
   authority=receipt['pack_mon']
   current=PACK.authorize(e,receipt['trainer'],pokemon,source_choice=authority['source_choice'])
   if current!=authority:raise ValueError('Pack Mon authority changed after declaration')
   receipt['used']=True;return True
 if pokemon.kind!='pokemon' or not pokemon.spec.get('trainer_id'):return True
 grants=getattr(e,'_action_grants',[])
 if action_grant is not None and any(g[0] is action_grant and g[1] is pokemon and g[2] is target and g[3]==move_id for g in grants):return True
 for receipt in getattr(e,'_obedience_receipts',[]):
  if receipt.get('gm_disobedience') and not receipt['used'] and receipt['pokemon'] is pokemon and receipt['target'] is target and receipt['move_id']==move_id and receipt['trainer'].entity_id==pokemon.spec['trainer_id']:
   receipt['used']=True;return True
 pending=loyalty_pending(e,pokemon)
 if pending is not None:return pending
 if command_loyalty_value(e,pokemon)>=2:return True
 for receipt in getattr(e,'_obedience_receipts',[]):
  if not receipt['used'] and receipt['pokemon'] is pokemon and receipt['target'] is target and receipt['move_id']==move_id and receipt['trainer'].spec.get('id')==pokemon.spec['trainer_id']:
   receipt['used']=True;return True
 e.log('    친밀도0/1: 현재 명령의 복종 판정 또는 명시 GM 행동이 필요 → 기술 보류','pokemon/loyalty')
 return False


def _execute_command(e,trainer,pokemon,target,move_id,options,*,pack_mon=False,gm_disobedience=False):
 receipt={'trainer':trainer,'pokemon':pokemon,'target':target,'move_id':move_id,'used':False}
 if pack_mon:receipt['pack_mon']=deepcopy(pack_mon)
 if gm_disobedience:receipt['gm_disobedience']=True
 receipts=getattr(e,'_obedience_receipts',None)
 temporary=receipts is None
 if receipts is None:e._obedience_receipts=[];receipts=e._obedience_receipts
 receipts.append(receipt)
 try:return e.use_move(pokemon,target,move_id,**options)
 finally:
  receipts[:]=[r for r in receipts if r is not receipt]
  if temporary and not receipts:e.__dict__.pop('_obedience_receipts',None)


def command_move(e,actor,*,pokemon,target,move_id,obedience_options=None,control_application=None,**move_options):
 if control_application is not None:
  import state_grants as G,world_entities as WORLD
  WORLD.require_actors(e,actor,pokemon,target)
  # Native waits keep the paid prefix; their existing producer owns resumption.
  pending=[]
  def apply(se,sa,sp,st):
   try:return _command_move(se,sa,pokemon=sp,target=st,move_id=move_id,obedience_options=obedience_options,control_application=control_application,**move_options)
   except Exception as error:
    if G.record_native_pending(se,error,pending):return None
    raise
  result=G.transition(e,actor,apply,participants=(pokemon,target),include_grid=e.grid is not None,include_rulings=True)
  if pending:
   exception,event_id=pending[0];raise exception(event_id)
  return result
 return _command_move(e,actor,pokemon=pokemon,target=target,move_id=move_id,obedience_options=obedience_options,**move_options)


def _command_move(e,actor,*,pokemon,target,move_id,obedience_options=None,control_application=None,pack_mon_source_choice=None,**move_options):
 """Declare a real move, then resolve obedience before any accuracy/frequency cost."""
 import action_lifecycle as ACTION
 import frequency as FREQ
 _pokemon(pokemon)
 pack_mon=actor.kind=='pokemon'
 if pack_mon:
  import pack_mon as PACK
  decision=PACK.authorize(e,actor,pokemon,source_choice=pack_mon_source_choice)
  if obedience_options or control_application is not None:raise ValueError('Pack Mon obedience does not use trainer loyalty or control-tool options')
 else:
  if pack_mon_source_choice is not None:raise ValueError('Pack Mon source choice requires a Pokemon commander')
  _owner(actor,pokemon)
 import exhaust_moves as EXHAUST
 EXHAUST.require_command(e,pokemon)
 if pokemon.spec.get('pending_disobedience'):return C.PendingDecision('resolve the previous disobedient action before issuing another command')
 if getattr(e,'_league_runtime',None) is not None:raise ValueError('attached League owns command scheduling; its command adapter must submit this declaration')
 if pokemon.dead or pokemon.fainted:raise ValueError('conscious commanded Pokemon required')
 if move_id!='struggle' and e.r.move_id(move_id) not in {e.r.move_id(x) for x in pokemon.moves}:raise ValueError('commanded move is not learned')
 resolved=e._ruleset_move(pokemon,move_id)
 if resolved is None:return C.PendingDecision('selected move unavailable')
 move=e.r.move(resolved);mm,_=e.r.move_mech(resolved)
 kind=TURN.action_kind_of_move(e,pokemon,move,mm)
 if not ACTION.ordinary_permission(e,pokemon) or not ACTION.status_permission(e,pokemon,kind):return C.PendingDecision('commanded Pokemon action unavailable')
 allowed,reason=FREQ.move_allowed(e,pokemon,resolved,
  outside_combat=not e.encounter_active and e._active_turn_actor is None)
 if not allowed:return C.PendingDecision(reason)
 if move_options.keys()-{'situational','set_damage','roll_id'}:raise ValueError('command cannot bypass native cost or frequency')
 if 'roll_id' in move_options:
  import ap_roll_bonus as AP
  AP.bonus(e,pokemon,move_options['roll_id'],'accuracy')
 options=dict(obedience_options or {})
 if control_application is not None:
  import legendary_commands as LEGENDARY
  permission=LEGENDARY.control_permission(e,actor,pokemon,target,resolved,control_application)
  if isinstance(permission,C.PendingDecision):return permission
 if not pack_mon:
  settings={k:options.pop(k) for k in ('use_intimidate','dc_override','gm_failure') if k in options}
  decision=_command_loyalty(e,actor,target=pokemon,legendary_control=control_application is not None,roll=options,**settings)
  if isinstance(decision,C.PendingDecision):return decision
  if control_application is not None:LEGENDARY.consume_control(e,pokemon,control_application)
 if not decision['obeys']:
  import state_fields as F
  pokemon.spec['pending_disobedience']={'trainer_id':actor.spec['id'],'commanded_move':resolved,'commanded_target':target.spec.get('id',target.name),'failure_id':F.new_id('failed-command')}
  return {'activity':'command_move','status':'disobedient','obedience':decision,'move_result':None}
 result=_execute_command(e,actor,pokemon,target,resolved,move_options,pack_mon=decision if pack_mon else False)
 return {'activity':'command_move','status':'submitted','obedience':decision,'move_result':result}


def _validate_gm_resolution(pokemon,resolution):
 import resolution_transaction as TX
 fields={'id','pokemon_id','trainer_id','failed_command','choice','completion_ids','move_result','sha256'}
 if type(resolution)is not dict or set(resolution)!=fields:raise ValueError('exact GM native resolution evidence required')
 if resolution['sha256']!=TX.request_fingerprint({k:v for k,v in resolution.items() if k!='sha256'}):raise ValueError('GM native resolution evidence changed')
 for key in ('id','pokemon_id','trainer_id'):_text(resolution[key],'GM resolution '+key)
 if resolution['pokemon_id']!=pokemon.entity_id:raise ValueError('GM resolution belongs to another Pokemon')
 ids=resolution['completion_ids']
 if type(ids)is not list or not ids or any(type(uid)is not str or not uid for uid in ids) or len(ids)!=len(set(ids)):raise ValueError('nonempty distinct actual GM completion identities required')
 choice=resolution['choice'];failed=resolution['failed_command']
 if type(choice)is not dict or set(choice)!={'move_id','target_id','options'} or type(choice['options'])is not dict or choice['options'].keys()-{'situational','set_damage','roll_id'}:raise ValueError('exact native GM choice required')
 _text(choice['move_id'],'GM move');_text(choice['target_id'],'GM target')
 if type(failed)is not dict or failed.get('trainer_id')!=resolution['trainer_id']:raise ValueError('actual prior GM authority required')
 _text(failed.get('failure_id'),'original failed command or C128 GM occurrence')
 if resolution['move_result'] is not None and type(resolution['move_result'])is not int:raise ValueError('native GM scalar result required')


def validate_disobedience_actor(pokemon):
 pending=pokemon.spec.get('pending_disobedience')
 if pending is None:return True
 if pokemon.kind!='pokemon' or type(pending)is not dict:raise ValueError('actual Pokemon failed-command state required')
 _text(pending.get('trainer_id'),'failed-command Trainer')
 if pending.get('gm_resolution') is not None:
  resolution=pending['gm_resolution'];_validate_gm_resolution(pokemon,resolution)
  if resolution['failed_command']!={k:v for k,v in pending.items() if k!='gm_resolution'}:raise ValueError('GM resolution belongs to another failed-command occurrence')
 return True


def validate_disobedience_world(e,actors):
 rows=getattr(e,'_move_completions',{})
 for pokemon in actors.values():
  validate_disobedience_actor(pokemon)
  resolution=pokemon.spec.get('pending_disobedience',{}).get('gm_resolution')
  if resolution is None:continue
  trainer=actors.get(resolution['trainer_id']);choice=resolution['choice'];target=actors.get(choice['target_id'])
  if trainer is None or trainer.kind!='trainer' or pokemon.spec.get('trainer_id')!=trainer.entity_id or target is None:raise ValueError('actual current GM resolution participants required')
  for uid in resolution['completion_ids']:
   row=rows.get(uid)
   if row is None or row['actor'] is not pokemon or row['move_id']!=choice['move_id'] or target not in row['targets'] or row.get('gm_disobedience_resolution') is not resolution:
    raise ValueError('GM resolution requires its own actual producer completion')
 for row in rows.values():
  resolution=row.get('gm_disobedience_resolution')
  if resolution is None:continue
  _validate_gm_resolution(row['actor'],resolution)
  if row['id'] not in resolution['completion_ids'] or row['move_id']!=resolution['choice']['move_id'] or resolution['choice']['target_id'] not in {t.entity_id for t in row['targets']}:raise ValueError('native completion and original GM choice disagree')
 return True


def _bind_gm_resolution(e,actor,pokemon,pending,choice,created,result):
 import state_fields as F,resolution_transaction as TX
 pending.setdefault('failure_id',F.new_id('gm-consequence'))
 resolution={'id':F.new_id('gm-resolution'),'pokemon_id':pokemon.entity_id,'trainer_id':actor.entity_id,
  'failed_command':deepcopy({k:v for k,v in pending.items() if k!='gm_resolution'}),'choice':choice,
  'completion_ids':created,'move_result':result if type(result)is int else None}
 resolution['sha256']=TX.request_fingerprint(resolution)
 pending['gm_resolution']=resolution;pokemon.spec['pending_disobedience']=pending
 for uid in created:e._move_completions[uid]['gm_disobedience_resolution']=resolution
 return resolution


def resolve_disobedience(e,actor,*,pokemon,target=None,move_id=None,decision,reason,**move_options):
 """Explicit GM action; C03-128 also permits forcing an uncontrolled Mega."""
 _pokemon(pokemon);_owner(actor,pokemon);_text(reason,'GM disobedience reason')
 import mega_forms as MEGA,world_entities as WORLD
 WORLD.require_actors(e,actor,pokemon)
 if actor.kind!='trainer':raise ValueError('trainer required')
 # ch07:21 preserves the Pokemon turn when its trainer faints; a failed
 # command's GM consequence is not a fresh command from that trainer.
 pending=pokemon.spec.get('pending_disobedience')
 if pending is None and MEGA.uncontrolled(e,pokemon):
  pending={'trainer_id':actor.entity_id,'authority':'C03-128','mega_grant_source':pokemon.spec[MEGA.KEY]['grant_source']}
 if not pending or pending.get('trainer_id')!=actor.spec['id']:raise ValueError('unresolved failed command required')
 validate_disobedience_world(e,WORLD.actor_index(e))
 if decision=='idle':
  if pending.get('gm_resolution'):raise ValueError('the GM-selected native action already started; finish its existing continuation')
  if target is not None or move_id is not None or move_options:raise ValueError('idle choice does not execute a move')
  pokemon.spec.pop('pending_disobedience',None);e.r.rulings.record('pokemon_disobedience',pokemon.spec.get('id',pokemon.name),pending,'idle',reason,'once')
  return {'activity':'resolve_disobedience','status':'idle'}
 if decision!='action' or target is None or move_id is None:raise ValueError('GM must choose idle or a concrete action and target')
 WORLD.require_actors(e,target)
 if move_options.keys()-{'situational','set_damage','roll_id'}:raise ValueError('GM disobedience action retains native cost and frequency')
 continuation=pending.get('gm_resolution')
 if continuation is not None:
  resolved='struggle' if move_id=='struggle' else e.r.move_id(move_id)
  choice={'move_id':resolved,'target_id':target.entity_id,'options':deepcopy(move_options)}
  if continuation['choice']!=choice:raise ValueError('finish the existing GM-selected native action before changing its choice')
  rows=getattr(e,'_move_completions',{})
  if any(rows[uid]['phase'] not in ('complete','interrupted') for uid in continuation['completion_ids']):
   return C.PendingDecision('finish the existing native GM move continuation',declaration=deepcopy(continuation))
  result=continuation['move_result']
  if any(rows[uid]['phase']=='interrupted' for uid in continuation['completion_ids']):
   pokemon.spec.pop('pending_disobedience',None)
   e.r.rulings.record('pokemon_disobedience',pokemon.entity_id,pending,'interrupted',reason,'once')
   return {'activity':'resolve_disobedience','status':'interrupted','move_result':result,'completion_ids':list(continuation['completion_ids'])}
 else:
  if move_id!='struggle' and e.r.move_id(move_id) not in {e.r.move_id(x) for x in pokemon.moves}:raise ValueError('GM-selected move must still be learned')
  resolved=e._ruleset_move(pokemon,move_id)
  if resolved is None:return C.PendingDecision('GM-selected move unavailable')
  choice={'move_id':resolved,'target_id':target.entity_id,'options':deepcopy(move_options)}
  before=set(getattr(e,'_move_completions',{}));uses=dict(pokemon.move_uses);actions=len(getattr(pokemon,'_action_history',[]))
  try:result=_execute_command(e,actor,pokemon,target,resolved,move_options,gm_disobedience=True)
  except BaseException:
   created=[uid for uid,row in getattr(e,'_move_completions',{}).items() if uid not in before and row['actor'] is pokemon and row['move_id']==resolved and target in row['targets']]
   if created:_bind_gm_resolution(e,actor,pokemon,pending,choice,created,None)
   raise
  rows=getattr(e,'_move_completions',{})
  created=[uid for uid,row in rows.items() if uid not in before and row['actor'] is pokemon and row['move_id']==resolved and target in row['targets']]
  if created and any(rows[uid]['phase']!='complete' for uid in created):
   _bind_gm_resolution(e,actor,pokemon,pending,choice,created,result)
   if all(rows[uid]['phase'] in ('complete','interrupted') for uid in created):
    pokemon.spec.pop('pending_disobedience',None)
    e.r.rulings.record('pokemon_disobedience',pokemon.entity_id,pending,'interrupted',reason,'once')
    return {'activity':'resolve_disobedience','status':'interrupted','move_result':result,'completion_ids':created}
   return C.PendingDecision('finish the existing native GM move continuation',declaration=deepcopy(pending['gm_resolution']))
  if isinstance(result,C.PendingDecision):return result
  if not created and pokemon.move_uses==uses and len(getattr(pokemon,'_action_history',[]))==actions:
   return {'activity':'resolve_disobedience','status':'refused','move_result':result}
 pokemon.spec.pop('pending_disobedience',None)
 e.r.rulings.record('pokemon_disobedience',pokemon.spec.get('id',pokemon.name),pending,{'move_id':resolved,'target':target.spec.get('id',target.name)},reason,'once')
 return {'activity':'resolve_disobedience','status':'submitted','move_result':result}

ACTIVITIES.update(command_move=command_move,resolve_disobedience=resolve_disobedience)



def hatch_fossil(e,actor,*,egg_id,name,ready,reason,details):
 import state_grants as G
 return G.transition(e,actor,lambda se,sa:_hatch_fossil(se,sa,egg_id=egg_id,name=name,ready=ready,reason=reason,details=details))


def _hatch_fossil(e,actor,*,egg_id,name,ready,reason,details):
 """ch05:748-750: actual level10 Combatant, with GM-established hatch facts.
 The section specifies no universal hatch duration, gender/nature/ability/move
 algorithm or fixed shiny chance for fossils; those choices stay explicit.
 """
 _outside(e);_text(reason,'GM hatch timing reason');_text(name,'hatched Pokemon name')
 if ready is not True:raise ValueError('GM must establish that this fossil egg is ready to hatch')
 eggs=[x for x in actor.spec.get('eggs',[]) if x.get('id')==egg_id]
 if len(eggs)!=1 or eggs[0].get('hatched') or eggs[0].get('source')!='edge/고생물학자':raise ValueError('unhatched fossil egg instance required')
 import pokemon_entities as EGGS
 egg=eggs[0];EGGS.validate_egg(e,actor,egg);fossil_record=EGGS.egg_fossil(e,egg)
 if not fossil_record or fossil_record.get('status')!='restored_to_egg':raise ValueError('actual restored fossil producer required')
 import creation_fossil as RESTORATION
 return RESTORATION._hatch(e,actor,egg,name=name,ready=ready,reason=reason,details=details)

ACTIVITIES.update(hatch_fossil=hatch_fossil)


COLLECTOR_FEAT='feat/포켓몬-넌-내-꺼야'
COLLECTOR_REVISION='supp-errata/포획-메커니즘-변경'

def collector_eligible(e,trainer,required=False):
 """Errata:771-775, with ch04:376-386 acquisition prerequisites."""
 import capture_techniques as CT,capture_specialist as CS
 if CT._rows(trainer):
  variant=CS.feature_variant(trainer,COLLECTOR_FEAT)
  if variant==CS.SEPT:
   CS.official_source(e.r,CS.SEPT)
   C.integer(trainer.spec.get('collector_stacks',0),'collector stacks',0)
   return True
  if required:raise ValueError('Collector requires the actually acquired official September source')
  return False
 owned=trainer.spec.get('feats',[])
 acquired=COLLECTOR_FEAT in owned or '포켓몬 넌 내 꺼야' in owned
 if not acquired:
  if required:raise ValueError('acquired Gotta Catch Em All feat required')
  return False
 # Core's daily digit swap and the errata's static stacks are separate versions.
 revision=e.r.selection.units[COLLECTOR_REVISION]
 if not e.r.ruleset.allows(revision)[0]:
  if required:raise ValueError('collector stacks require the selected capture errata')
  return False
 for uid in (COLLECTOR_REVISION,COLLECTOR_FEAT):
  if e.r._selected_rule(uid)!=uid:raise ValueError('selected collector version needs its own policy: '+uid)
 advanced='feat/고급-포획-테크닉'
 if advanced not in owned and '고급 포획 테크닉' not in owned:raise ValueError('acquired Advanced Capture Techniques required')
 for uid in (advanced,'class/포획전문가'):
  if e.r._selected_rule(uid)!=uid:raise ValueError('selected acquisition version needs its own collector policy: '+uid)
 rank=trainer.spec.get('feat_ranks',{}).get(advanced)
 C.integer(rank,'Advanced Capture Techniques rank',3,4)
 classes=trainer.spec.get('classes',[])+owned
 if not any(x in classes for x in ('class/포획전문가','포획전문가')):raise ValueError('Capture Specialist class acquisition required')
 physical=[_rank(e,trainer,s) for s in ('곡예','육상','은신','생존')]
 social=[_rank(e,trainer,s) for s in ('교활','통찰')]
 if max(physical)<3 or max(social)<3:raise ValueError('Capture Specialist prerequisite skills required')
 if sum(r>=5 for r in physical+social)<(3 if rank==4 else 2):raise ValueError('Advanced Capture Techniques expert skill prerequisites required')
 C.integer(trainer.spec.get('collector_stacks',0),'collector stacks',0)
 return True

def collector_choice(choice,stacks):
 """One explicit optional choice; never combine bonus with complete reroll."""
 if choice is None:return {'kind':'none','cost':0}
 if not isinstance(choice,dict):raise ValueError('collector choice must be a dictionary or None')
 kind=choice.get('kind')
 if kind=='bonus' and set(choice)=={'kind','stacks'}:
  cost=C.integer(choice['stacks'],'collector bonus stacks',1,3)
 elif kind=='reroll' and set(choice)=={'kind'}:cost=3
 else:raise ValueError('choose either bonus stacks or a complete reroll')
 if cost>stacks:raise ValueError('insufficient collector stacks')
 return {'kind':kind,'cost':cost}

def _evolution_family(e,species):
 """Connected native learnset evolution families, including sibling branches."""
 import re
 from builder import species_lookup
 sp=species_lookup(e.r,species);family={sp['name']}
 known={row['name'] for row in e.r.species.values()}
 if sp['name'] not in e.r.learnsets:raise ValueError('evolution family source is unresolved')
 groups=[]
 for name,ls in e.r.learnsets.items():
  group={name};parsed=set();valid=bool(ls.get('evolution'))
  for entry in ls.get('evolution',[]):
   match=re.match(r'\s*\d+\s*-\s*(.+)',str(entry))
   parts=match.group(1).split() if match else []
   member=next((' '.join(parts[:n]) for n in range(len(parts),0,-1) if ' '.join(parts[:n]) in known),None)
   if member is not None:parsed.add(member)
   else:valid=False
  group.update(parsed);groups.append((group,valid and name in parsed))
 changed=True
 while changed:
  changed=False
  for group,valid in groups:
   if group & family:
    if not valid:raise ValueError('evolution family source is missing or not fully parsed')
    if not group<=family:family.update(group);changed=True
 return family

def collector_new_family(e,trainer,target):
 """Current ownership, not historical caught_species; runs before capture."""
 from builder import species_lookup
 _text(trainer.spec.get('id'),'collector trainer identity')
 if not target.spec.get('wild',getattr(target,'side',None)=='wild'):return False
 family=_evolution_family(e,target.spec.get('species'))
 everyone=list(e.gm.everyone or [])+list(e.everyone or [])
 for owned in everyone:
  if owned is target or owned.kind!='pokemon' or owned.spec.get('trainer_id')!=trainer.spec['id']:continue
  if _evolution_family(e,owned.spec.get('species')) & family:return False
 return True

import crafting_activities as CRAFTING
ACTIVITIES.update(CRAFTING.ACTIVITIES)

import bandages as BANDAGES
ACTIVITIES.update(BANDAGES.ACTIVITIES)

import pokemon_requests as REQUESTS
ACTIVITIES.update(REQUESTS.ACTIVITIES)

import wild_equipment as WILD_EQUIPMENT
ACTIVITIES.update(WILD_EQUIPMENT.ACTIVITIES)

import net_capsule as NET_CAPSULE
ACTIVITIES.update(NET_CAPSULE.ACTIVITIES)

# Source-specific owned roster and machine/edge teaching entrypoints.
import pokemon_party as PARTY
import pokemon_teaching as TEACHING
ACTIVITIES.update(party_transfer=PARTY.transfer,party_policy=PARTY.configure,party_place=PARTY.place,party_registry=PARTY.registry,
                  register_machine=TEACHING.register_machine,teach_machine=TEACHING.teach_machine,teach_edge=TEACHING.teach_edge)

import pokemon_intelligence as INTELLIGENCE
ACTIVITIES.update(configure_intelligence=INTELLIGENCE.configure,assign_intelligence_skills=INTELLIGENCE.assign)

ACTIVITIES.update(register_owned_reserve=PARTY.register_reserve)

import pokemon_understanding as UNDERSTANDING
import regional_pokemon as REGIONAL
ACTIVITIES.update(UNDERSTANDING.ACTIVITIES)
ACTIVITIES.update(REGIONAL.ACTIVITIES)


def observe_egg(e,actor,*,egg_id,reason,parents=()):
 import pokemon_entities as EGGS
 return EGGS.observe_egg(e,actor,egg_id=egg_id,reason=reason,parents=parents)

ACTIVITIES.update(observe_egg=observe_egg)


def observe_tutor_points(e,actor,*,target,balance,reason):
 import pokemon_progression as P
 return P.observe_balance(e,target,balance=balance,reason=reason)

ACTIVITIES['observe_tutor_points']=observe_tutor_points


def observe_pokemon_xp(e,actor,*,target,total,reason):
 import pokemon_progression as P
 return P.observe_xp(e,target,total=total,reason=reason)

ACTIVITIES['observe_pokemon_xp']=observe_pokemon_xp

import feature_ability_lessons as ABILITY_LESSONS
ACTIVITIES['teach_feature_ability']=ABILITY_LESSONS.teach


import item_maturation as MATURATION
ACTIVITIES['collect_matured_item']=MATURATION.collect

import chef_cooking as CHEF
ACTIVITIES['cook_chef_food']=CHEF.cook
ACTIVITIES['serve_chef_food']=CHEF.serve
