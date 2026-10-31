"""Source-specific machine learning and completed-training consumers.

Machine identities are actual owned instances backed by inventory. TP is a
current, explicit sheet resource; missing history is never unspent TP. The
PTK cap and natural-list rules stay separate from training-feature permission.
"""
from copy import deepcopy
from pathlib import Path
import json,re
import common_checks as C
import skill_modifiers as S
import world_entities as W
from builder import species_lookup

MACHINES='ch09-equipment/포켓몬-도구/기술머신과-비전머신'
TABLE='ch09-equipment/포켓몬-도구/기술머신-표'
MOVES='ch05-pokemon/포켓몬-관리하기/기술'
POINTS='ch05-pokemon/레벨-업/가르침-포인트'
EDGE='poke_edge/스킬-향상'

def source(rules,*ids):
 for uid in ids:
  if rules._selected_rule(uid)!=uid:raise ValueError('selected teaching source needs its own policy: '+uid)

def catalog(rules):
 source(rules,MACHINES,TABLE)
 return json.loads((Path(rules.root)/'data/pokemon-machines.json').read_text(encoding='utf-8'))

def _text(value,name):
 if not isinstance(value,str) or not value.strip():raise ValueError(name+' required')
 return value

def _pokemon(e,actor,target):
 W.require_actors(e,actor,target)
 import pokemon_activities as P
 import researcher_fields as RESEARCH
 if not RESEARCH.pusher_acquiring(e,actor,target):P._trainer(actor);P._outside(e)
 P._pokemon(target);P._owner(actor,target)
 _text(target.spec.get('id'),'actual Pokemon identity')
 if target.spec.get('frequency_state',{}).get('day',0)!=actor.spec.get('frequency_state',{}).get('day',0):raise ValueError('teaching calendars must agree')

def _balance(spec):
 value=spec.get('tutor_points')
 C.integer(value,'actual remaining Tutor Points',0)
 return value

def _debit_points(spec,cost):
 """Settle the actual cost against current TP inside the caller's transition.

 The native consumer owns source, qualification, time and its payment receipt.
 Read after training/reconciliation so intervening refunds remain available.
 """
 C.integer(cost,'actual Tutor Point cost',0)
 balance=_balance(spec)
 if balance<cost:raise ValueError('insufficient actual remaining Tutor Points')
 spec['tutor_points']=balance-cost

def _known(rules,spec):
 result=[]
 for value in spec.get('moves',[]):
  if value=='struggle':continue
  mid=rules.move_id(value)
  if mid is None or mid in result:raise ValueError('distinct selected known moves required')
  result.append(mid)
 return result

def natural_moves(rules,spec):
 import move_state as MOVES_STATE
 return MOVES_STATE.natural_moves(rules,spec)


def classifications(rules,spec):
 """Use the shared source-aware occupancy and retained natural history."""
 import move_state as MOVES_STATE
 return MOVES_STATE.validate_spec(rules,spec,require_routes=True)['classifications']


def register_machine(e,actor,*,instance_id,code):
 """Bind one owned inventory unit; this never creates/buys a machine."""
 W.require_actors(e,actor)
 import pokemon_activities as P
 P._trainer(actor);P._outside(e);_text(actor.spec.get('id'),'machine owner identity');_text(instance_id,'physical machine identity')
 rows=catalog(e.r)['machines']
 if code not in rows:raise ValueError('source table does not establish that machine identity')
 machines=actor.spec.get('teaching_machines',{})
 if instance_id in machines:raise ValueError('physical machine identity already registered')
 count=actor.spec.get('items',{}).get(code,0)
 C.integer(count,'owned machine inventory count',0)
 claimed=sum(r.get('code')==code and r.get('status')=='owned' for r in machines.values())
 if claimed>=count:raise ValueError('no unclaimed actual inventory machine')
 record={'id':instance_id,'owner_id':actor.spec['id'],'code':code,'status':'owned','source':rows[code]['source']}
 actor.spec.setdefault('teaching_machines',{})[instance_id]=record
 return deepcopy(record)

def _machine_move(rules,spec,code,row):
 import type_sync as TYPE_SYNC
 mid=rules.move_id(row['move_name'])
 if mid:
  permission=TYPE_SYNC.learning_permission(rules,spec,mid,row['kind'].lower())
  if permission is False:raise ValueError('GM Type Sync exception forbids this machine')
  if permission is True:return mid
 import underdog_lessons as LESSONS
 if LESSONS.learning_permission(rules,spec,mid,row['kind'].lower(),machine=row):return mid
 sp=species_lookup(rules,spec['species']);ls=rules.learnsets.get(sp['name'],{})
 expected=('A' if row['kind']=='HM' else '')+str(row['number'])
 listed=[]
 for raw in ls.get('tm',[]):
  match=re.fullmatch(r'\s*([A-Za-z]?)([0-9]+)\s+(.+?)\s*',str(raw))
  if match and match.group(1).upper()+str(int(match.group(2)))==expected:listed.append(match.group(3))
 if not listed:raise ValueError('species is not compatible with this actual machine')
 table_mid=rules.move_id(row['move_name']);mids={rules.move_id(name) for name in listed}
 if not table_mid or None in mids or mids!={table_mid}:raise ValueError('machine table and species source identity conflict; a source resolution is required')
 return table_mid

def _hm_policy(rules,binding,decision=None):
 document=json.loads((Path(rules.root)/'data/hm-teaching-policy.json').read_text(encoding='utf-8'))
 document['variants'][0]['values']['binding']=binding
 return rules.resolve_source_policy(document,decisions={} if decision is None else {'hm_points':decision})


def hm_teaching_policy(e,actor,*,target,instance_id,decision=None):
 _pokemon(e,actor,target)
 record=actor.spec.get('teaching_machines',{}).get(instance_id)
 row=catalog(e.r)['machines'].get(record.get('code')) if isinstance(record,dict) else None
 if not row or row['kind']!='HM' or record.get('status')!='owned' or record.get('owner_id')!=actor.entity_id:raise ValueError('actual owned HM instance required')
 return _hm_policy(e.r,{'teacher_id':actor.entity_id,'target_id':target.entity_id,'instance_id':instance_id,'machine':record['code']},decision)


def validate_hm_record(rules,spec,record):
 binding={'teacher_id':record.get('teacher_id'),'target_id':spec.get('id'),'instance_id':record.get('instance_id'),'machine':record.get('machine')}
 policy=_hm_policy(rules,binding,record.get('hm_cost_decision'))
 if policy.get('status')!='PolicyValuesReady' or record.get('hm_cost_policy')!=policy or record.get('paid_tp')!=policy['values']['point_cost']:
  raise ValueError('completed HM learning requires its actual scoped source interpretation')


def teach_machine(e,actor,*,target,instance_id,replace=None,hm_decision=None):
 """Commit source, slots, time, points and machine use as one actor graph."""
 import state_grants as GRANTS
 return GRANTS.transition(e,target,lambda staged_e,staged_target,staged_actor:
  _teach_machine(staged_e,staged_actor,target=staged_target,instance_id=instance_id,replace=replace,hm_decision=hm_decision),participants=(actor,))


def _teach_machine(e,actor,*,target,instance_id,replace=None,hm_decision=None):
 """All resource, source and slot checks precede the actual one-hour cost."""
 _pokemon(e,actor,target);source(e.r,MACHINES,MOVES,POINTS)
 record=actor.spec.get('teaching_machines',{}).get(instance_id)
 if not record or record.get('status')!='owned' or record.get('owner_id')!=actor.spec['id']:raise ValueError('actual unconsumed owned machine instance required')
 rows=catalog(e.r)['machines'];row=rows.get(record['code'])
 if not row or record.get('source')!=row['source']:raise ValueError('machine source binding changed')
 inventory=actor.spec.get('items',{});count=inventory.get(record['code'],0)
 C.integer(count,'owned machine inventory count',1)
 reserved=sum(x.get('code')==record['code'] and x.get('status')=='owned' for x in actor.spec['teaching_machines'].values())
 if count<reserved:raise ValueError('registered machine inventory is no longer present')
 day=actor.spec.get('frequency_state',{}).get('day',0)
 if row['kind']=='HM' and record.get('used_day')==day:raise ValueError('this physical HM was already used today')
 mid=_machine_move(e.r,target.spec,record['code'],row)
 import move_state as MOVES_STATE
 MOVES_STATE.validate_spec(e.r,target.spec,moves=target.moves,abilities=target.abilities,require_routes=True)
 classes=MOVES_STATE.classifications(e.r,target.spec,require_routes=True)
 if mid in classes:raise ValueError('Pokemon already knows that move')
 replacing=e.r.move_id(replace) if replace is not None else None
 if replace is not None and replacing not in classes:raise ValueError('explicit replacement must be an actually known permanent move')
 is_natural=mid in natural_moves(e.r,target.spec)
 hm_policy=None
 if row['kind']=='HM':
  hm_policy=hm_teaching_policy(e,actor,target=target,instance_id=instance_id,decision=hm_decision)
  if hm_policy['status']!='PolicyValuesReady':raise ValueError('HM Tutor Point interpretation requires the explicit scoped decision from hm_teaching_policy()')
 elif hm_decision is not None:raise ValueError('HM interpretation cannot change a TM cost')
 # PTU p300 waives the extra point for replacing a TM Move with another TM.
 # The shared taught-slot classification does not establish that provenance.
 previous=target.spec.get('move_learning',{}).get(replacing,{})
 point_cost=hm_policy['values']['point_cost'] if hm_policy is not None else 0 if replacing is not None and classes[replacing]=='taught' and previous.get('method')=='tm' else 1
 if _balance(target.spec)<point_cost:raise ValueError('insufficient actual Tutor Points')
 candidate=__import__('world_entities').spec_copy(target)
 if replacing is not None:
  import move_type_sync as MOVE_SYNC
  MOVE_SYNC.forget_spec(e.r,candidate,replacing,at=e.elapsed_seconds,reason='completed physical machine replacement')
  __import__('ace_trainer').forget_spec(e.r,candidate,replacing,at=e.elapsed_seconds,reason='completed physical machine replacement')
 moves=[m for m in candidate.get('moves',[]) if e.r.move_id(m)!=replacing]
 candidate['moves']=moves
 import learning_grant as LEARNING
 LEARNING.learn_moves(e.r,candidate,candidates=[mid],selected=[mid],method=row['kind'].lower(),
  source=MACHINES,reason='completed physical machine teaching',provider=actor.entity_id,paid_tp=point_cost,
  replaced=replacing,details={'machine':record['code'],'instance_id':instance_id,'natural':is_natural,
   **({'hm_cost_policy':hm_policy,'hm_cost_decision':deepcopy(hm_decision)} if hm_policy is not None else {})})
 moves=candidate['moves']
 MOVES_STATE.record_natural_opportunities(e.r,candidate,reason='completed machine learning state')
 MOVES_STATE.validate_spec(e.r,candidate,require_routes=True)
 import activity_jobs as JOBS
 JOBS.run_fixed(e,actor,(target,),seconds=3600,source=MACHINES,context={'instance_id':instance_id})
 for field in ('move_learning','move_learning_log',MOVES_STATE.HISTORY,'move_type_sync','signature_techniques'):
  if field in candidate:target.spec[field]=candidate[field]
 if 'signature_techniques' in candidate:target.spec['tutor_points']=candidate['tutor_points']
 import state_grants as GRANTS
 GRANTS.set_baseline(target,'moves',moves)
 _debit_points(target.spec,point_cost)
 if row['kind']=='TM':inventory[record['code']]-=1;record['status']='consumed'
 else:record['used_day']=day
 return {'activity':'teach_machine','move':mid,'replaced':replacing,'point_cost':point_cost,'machine':record['code'],'seconds':3600,'natural':is_natural}

def preflight_level(rules,spec):
 import move_state as MOVES_STATE
 MOVES_STATE.validate_history(rules,spec)
 import pokemon_progression as PROGRESSION
 PROGRESSION.prepare_level(rules,spec)
 if spec.get('move_learning'):source(rules,MOVES);natural_moves(rules,spec)

def on_level(rules,spec):
 """Native level-up event: award each fifth level and release natural slots."""
 import pokemon_progression as PROGRESSION
 PROGRESSION.award_level(rules,spec)
 import move_state as MOVES_STATE
 MOVES_STATE.record_natural_opportunities(rules,spec,reason='actual level-up opportunity')
 import growth_milestones as MILESTONES
 MILESTONES.offer_inheritance(rules,spec)

def training_safety(safe):
 import training_sessions
 training_sessions.require_safety(safe)


def edge_training_hour(e,actor,target,source,application,*,safe):
 """Pay the ordinary Poke Edge hour through the common job owner."""
 import researcher_fields as RESEARCH
 if RESEARCH.pusher_acquiring(e,actor,target,source):return None
 training_safety(safe)
 import activity_jobs as JOBS
 return JOBS.run_fixed(e,actor,(target,),seconds=3600,source=source,
  context={'safe':True,'application':application})


def credit_mode(from_grooming,from_training):
 if type(from_grooming) is not bool or type(from_training) is not bool or (from_grooming and from_training):raise ValueError('choose at most one actual training credit source')
 return from_grooming or from_training


def training_credit(e,actor,target,application,*,from_training=False):
 """Completed ordinary or grooming hour funds distinct native consumers."""
 import pokemon_activities as P
 _pokemon(e,actor,target)
 if from_training:
  import training_sessions as SESSIONS
  return SESSIONS.credit(e,actor,target,application)
 P._feature(e,actor,'groomer')
 _text(application,'training application identity')
 row=target.spec.get('training_credit',{});day=actor.spec.get('frequency_state',{}).get('day',0)
 if type(row) is not dict:raise ValueError('completed training credit must be a record')
 C.integer(day,'current training day',0);C.integer(row.get('day'),'completed training day',0)
 C.integer(row.get('hours'),'completed training hours',1)
 if row.get('safe') is not True:raise ValueError('completed grooming requires recorded safe environment')
 if row.get('source')!='edge/미용사' or row.get('trainer_id')!=actor.spec['id'] or row['day']!=day:raise ValueError('actual completed grooming training hour required')
 C.integer(row.get('completed_at'),'completed training timestamp',0)
 if row['completed_at']>e.elapsed_seconds:raise ValueError('training hour has not actually finished')
 applications=row.get('applications',[])
 if type(applications) is not list or any(type(value) is not str or not value.strip() for value in applications) or len(set(applications))!=len(applications):
  raise ValueError('distinct completed training applications required')
 if application in applications:raise ValueError('this training application already consumed its completed hour')
 import activity_jobs as JOBS
 receipt=JOBS.credit(e,actor,target,credit_id=row.get('credit_id'),application=application,family='training_hour',minimum_seconds=row['hours']*3600)
 if (receipt['end'],receipt['day'],receipt['source'],receipt['job_id'])!=(row['completed_at'],row['day'],row['source'],row.get('job_id')):
  raise ValueError('grooming projection does not match its completed job receipt')
 return row

def consume_credit(target,application,*,from_training=False):
 if from_training:
  import training_sessions as SESSIONS
  return SESSIONS.consume(target,application)
 import activity_jobs as JOBS
 JOBS.consume(target,target.spec['training_credit']['credit_id'],application)
 target.spec['training_credit'].setdefault('applications',[]).append(application)

def teach_edge(e,actor,*,target,edge,skill=None,stat=None,capability=None,move_id=None,growth=None,lesson=None,ability=None,negative_decision=None,from_grooming=False,from_training=False,safe=None,_pusher_funded=False):
 import researcher_fields as RESEARCH
 if not _pusher_funded and RESEARCH.pusher_funds(e,actor,target,edge) is not None:
  credit_mode(from_grooming,from_training)
  return RESEARCH.teach_funded(e,actor,target,edge,lambda se,so,st:teach_edge(se,so,target=st,edge=edge,skill=skill,stat=stat,capability=capability,move_id=move_id,growth=growth,lesson=lesson,ability=ability,negative_decision=negative_decision,safe=safe,_pusher_funded=True))
 import pokemon_move_edges as MOVE_EDGES
 if edge==MOVE_EDGES.OFFICIAL_MIXED:
  if any(x is not None for x in (skill,stat,capability,move_id,growth,lesson,ability,negative_decision)) or from_grooming or from_training:raise ValueError('official Mixed Power uses its actual completed teaching hour without choices')
  return MOVE_EDGES.teach_official_mixed_power(e,actor,target,safe=safe)
 if edge in (MOVE_EDGES.MIXED_POWER,'Mixed Power'):
  if any(x is not None for x in (skill,stat,capability,move_id,growth,lesson,ability,negative_decision)) or from_grooming or from_training:raise ValueError('Mixed Power uses its actual completed teaching hour without choices')
  return MOVE_EDGES.teach_mixed_power(e,actor,target,safe=safe)
 import mixed_sweeper as MIXED
 if edge in MIXED.ALIASES:
  if any(x is not None for x in (skill,stat,capability,move_id,lesson,ability,negative_decision)):raise ValueError('chapter Mixed Sweeper selects bonus investment only')
  return MIXED.teach(e,actor,target,growth=growth,from_grooming=from_grooming,from_training=from_training,safe=safe)
 import telepathy as TELEPATHY
 edge=TELEPATHY.ALIASES.get(edge,edge)
 import tremorsense as TREMOR
 edge=TREMOR.ALIASES.get(edge,edge)
 import precise_threadings as PRECISE
 edge=PRECISE.ALIASES.get(edge,edge)
 import ability_mastery as ABILITY_MASTERY
 edge=ABILITY_MASTERY.ALIASES.get(edge,edge)
 import advanced_connection as CONNECTION
 edge=CONNECTION.ALIASES.get(edge,edge)
 if ability is not None or edge in (ABILITY_MASTERY.SOURCE,CONNECTION.SOURCE):
  import poke_edge_variants as VARIANTS
  variant=VARIANTS.resolve(e.r,edge)
  if variant is None or variant['field']!='ability':raise ValueError('explicit Ability belongs to source-selected Ability Mastery')
  return VARIANTS.teach(e,actor,target,variant,skill=skill,stat=stat,capability=capability,move_id=move_id,growth=growth,lesson=lesson,ability=ability,negative_decision=negative_decision,from_grooming=from_grooming,from_training=from_training,safe=safe)
 import underdog_lessons as LESSONS
 edge=LESSONS.ALIASES.get(edge,edge)
 if lesson is not None or edge==LESSONS.SOURCE:
  import poke_edge_variants as VARIANTS
  variant=VARIANTS.resolve(e.r,edge)
  if variant is None or variant['field']!='lesson':raise ValueError('explicit final evolution lesson belongs to Underdog Lessons')
  return VARIANTS.teach(e,actor,target,variant,skill=skill,stat=stat,capability=capability,move_id=move_id,growth=growth,lesson=lesson,negative_decision=negative_decision,from_grooming=from_grooming,from_training=from_training,safe=safe)
 import underdog_edges as UNDERDOG
 edge=UNDERDOG.ALIASES.get(edge,edge)
 if growth is not None or negative_decision is not None:
  import poke_edge_variants as VARIANTS
  variant=VARIANTS.resolve(e.r,edge)
  if variant is None or variant['field']!='growth':raise ValueError('explicit bonus investment belongs to a source-selected growth Edge')
  return VARIANTS.teach(e,actor,target,variant,skill=skill,stat=stat,capability=capability,move_id=move_id,growth=growth,negative_decision=negative_decision,from_grooming=from_grooming,from_training=from_training,safe=safe)
 import tk_mastery as TK_MASTERY
 if edge in TK_MASTERY.ALIASES:
  if any(x is not None for x in (skill,stat,capability,move_id)):raise ValueError('TK Mastery has no acquisition choice')
  import poke_edge_variants as VARIANTS
  variant=VARIANTS.resolve(e.r,TK_MASTERY.SOURCE)
  return VARIANTS.teach(e,actor,target,variant,from_grooming=from_grooming,from_training=from_training,safe=safe)
 import invisibility_edge as INVISIBILITY_EDGE
 if edge in INVISIBILITY_EDGE.ALIASES:
  if any(x is not None for x in (skill,stat,capability,move_id)):raise ValueError('Extended Invisibility has no acquisition choice')
  return INVISIBILITY_EDGE.teach(e,actor,target=target,from_grooming=from_grooming,from_training=from_training,safe=safe)
 import poke_edge_variants as VARIANTS
 variant=VARIANTS.resolve(e.r,edge)
 if variant is not None:
  return VARIANTS.teach(e,actor,target,variant,skill=skill,capability=capability,stat=stat,move_id=move_id,from_grooming=from_grooming,from_training=from_training,safe=safe)
 import ranged_struggle as RANGED
 if edge in RANGED.ALIASES:
  if skill is not None or stat is not None or move_id is not None:raise ValueError('ranged Struggle selects one capability only')
  return RANGED.teach(e,actor,target=target,capability=capability,from_grooming=from_grooming,from_training=from_training,safe=safe)
 import pokemon_move_edges as MOVE_EDGES
 if edge in MOVE_EDGES.ALIASES:
  if skill is not None or stat is not None or capability is not None:raise ValueError('Accuracy Training selects a Move only')
  return MOVE_EDGES.teach(e,actor,target=target,move_id=move_id,from_grooming=from_grooming,from_training=from_training,safe=safe)
 if move_id is not None:raise ValueError('this Poke Edge does not select a Move')
 import pokemon_capability_edges as CAP_EDGES
 if edge in CAP_EDGES.ALIASES:
  if skill is not None or stat is not None:raise ValueError('capability Poke Edge selects one capability')
  return CAP_EDGES.teach(e,actor,target=target,edge=edge,capability=capability,from_grooming=from_grooming,from_training=from_training,safe=safe)
 if capability is not None:raise ValueError('this Poke Edge does not select a capability')
 import pokemon_stat_edges as STAT_EDGES
 if edge in STAT_EDGES.ALIASES:
  if skill is not None:raise ValueError('Attack Conflict selects a stat, not a skill')
  return STAT_EDGES.teach(e,actor,target=target,stat=stat,from_grooming=from_grooming,from_training=from_training,safe=safe)
 if stat is not None:raise ValueError('this Poke Edge does not select a stat')
 import state_grants as G
 return G.transition(e,target,lambda se,st,sa:_teach_edge(se,sa,target=st,edge=edge,skill=skill,from_grooming=from_grooming,from_training=from_training,safe=safe),participants=(actor,))


def _teach_edge(e,actor,*,target,edge,skill,from_grooming=False,from_training=False,safe=None):
 """Skill Improvement consumer, separate from Groomer's permission to train.

Other Poke Edge policies register their own acquisition/effect consumers; this
function never treats unknown edge text as an executable generic setter.
"""
 _pokemon(e,actor,target)
 if edge not in (EDGE,'스킬 향상','Skill Improvement'):raise ValueError('Poke Edge needs its own acquisition and effect consumer')
 source(e.r,EDGE,POINTS)
 sid=S.skill_id(e.r.skill_policy,skill,required=True);application=EDGE+':'+sid
 if credit_mode(from_grooming,from_training):training_credit(e,actor,target,application,from_training=from_training)
 if _balance(target.spec)<1:raise ValueError('Skill Improvement costs one Tutor Point')
 import pokemon_skill_edges as EDGES
 EDGES.validate(e.r,target.spec)
 learned=EDGES.active(target.spec)
 import acquisition_qualification as Q
 Q.require(EDGE,actor.entity_id,'teaching',[Q.check('distinct_skill','repeat',not any(r.get('source')==EDGE and r.get('skill')==sid for r in learned),'Skill Improvement requires a different skill on each acquisition')])
 import researcher_features as RF
 native=RF.native_plan(e,target,skill)
 if native.get('pushed'):raise ValueError('temporary pushed skill must be separated before permanent skill acquisition')
 rank,flat=EDGES.skill_pool(e.r,target.spec,sid)
 sp=species_lookup(e.r,target.spec['species'])
 values=[v['rank'] for k,v in e.r.species_skills.get(sp['name'],{}).items() if S.skill_id(e.r.skill_policy,k)==sid]
 Q.require(EDGE,actor.entity_id,'teaching',[Q.check('species_rank','prerequisite',len(values)==1 and rank<=values[0],'Skill Improvement requires a skill at or below species default rank')])
 if not (from_grooming or from_training):
  edge_training_hour(e,actor,target,EDGE,application,safe=safe)
 EDGES.set_pool(e.r,target.spec,sid,rank+1,flat)
 _debit_points(target.spec,1)
 target.spec.setdefault('learned_poke_edges',[]).append({'source':EDGE,'status':'active','trainer_id':actor.entity_id,'skill':sid,'rank_before':rank,'point_cost':1,'training_source':'edge/미용사' if from_grooming else 'input/ch05-pokemon.md:229' if from_training else 'input/ch05-pokemon.md:274','completed_at':e.elapsed_seconds})
 refunded=EDGES.refund_excess(e.r,target.spec,reason='completed permanent Skill Improvement training')
 if credit_mode(from_grooming,from_training):consume_credit(target,application,from_training=from_training)
 return {'activity':'teach_edge','edge':EDGE,'skill':sid,'rank':EDGES.skill_pool(e.r,target.spec,sid)[0],'point_cost':1,'refunded_points':len(refunded),'seconds':0 if (from_grooming or from_training) else 3600}


MENTOR='class/멘토'
MOVE_TUTOR='feat/기술-가르침'
EGG_TUTOR='feat/교배-가르침'
MENTOR_SKILLS=('매력','직감','협박','포켓몬학')


def _acquired_feature(actor,uid):
 from acquired_features import _names,_resolve
 prefix='class/' if uid.startswith('class/') else 'feat/'
 names=_names(actor,prefix)
 values=list(actor.spec.get('feats',[]))+(list(actor.spec.get('classes',[])) if prefix=='class/' else [])
 return uid in {_resolve(actor,v,prefix,names) for v in values if v in names}


def select_mentor_skills(e,actor,skills,*,reason):
 W.require_actors(e,actor)
 import mentor as MENTOR_FULL
 bound=MENTOR_FULL.acquired(actor,MENTOR)
 if bound is not None:
  original=bound['snapshot']['skills']
  if list(skills)!=original:raise ValueError('Mentor acquisition choices cannot change')
  _text(reason,'Mentor skill selection reason')
  return list(original)
 import mentor_csv as CSV_MENTOR
 if CSV_MENTOR.has_receipt(actor):
  original=CSV_MENTOR.receipt(actor)['selection']['values']
  if list(skills)!=original:raise ValueError('CSV Mentor acquisition choices cannot change')
  _text(reason,'Mentor skill selection reason')
  return list(original)
 source(e.r,MENTOR)
 if actor.kind!='trainer' or not _acquired_feature(actor,MENTOR):raise ValueError('actual acquired Mentor feature required')
 _text(reason,'Mentor skill selection reason')
 if not isinstance(skills,(list,tuple)) or len(skills)!=2 or len(set(skills))!=2 or any(v not in MENTOR_SKILLS for v in skills):raise ValueError('select two distinct Mentor skills')
 if any(S.rank(e.r,actor,v)[2]<3 for v in skills):raise ValueError('both selected Mentor skills must be Novice or better')
 if 'mentor_skills' in actor.spec and actor.spec['mentor_skills']!=list(skills):raise ValueError('acquired Mentor skill choices cannot be silently replaced')
 actor.spec['mentor_skills']=list(skills)
 actor.spec['mentor_skill_selection']={'source':MENTOR,'reason':reason}
 return list(skills)


def tutor_admission(rules,move_id,level,*,policy=None):
 """Selected PTK tutoring errata, ch05:134-138; never a learning grant."""
 import frequency as F
 source(rules,MOVES)
 C.integer(level,'actual tutoring level',1,100)
 mid=rules.move_id(move_id)
 if mid is None:raise ValueError('selected actual tutoring move required')
 move=rules.move(mid);db=move.get('damage_base');raw_frequency=move.get('frequency')
 proof=None
 if policy not in (None,'kr_errata','core','official_sep2015'):raise ValueError('reviewed source-specific tutoring policy required')
 if policy in ('core','official_sep2015'):
  import mentor as MENTOR_FULL
  from hashlib import sha256
  data=MENTOR_FULL.contract(rules);proof=deepcopy(data['core' if policy=='core' else 'official_sep2015'])
  if sha256((Path(rules.root)/proof['file']).read_bytes()).hexdigest()!=proof['sha256']:
   raise ValueError('actual selected tutoring source changed')
 if level<30 and policy!='core':
  if not isinstance(raw_frequency,str) or not raw_frequency.strip():
   raise ValueError('tutoring restriction requires sourced move frequency')
  kind,_=F.parse(raw_frequency)
  allowed={'at_will','every_other_turn'}|({'scene'} if level>=20 else set())
  if kind not in allowed:raise ValueError('tutoring restriction: move frequency exceeds level allowance')
  if db is None and move.get('class')=='변화':pass
  elif type(db) is not int or db<0:
   raise ValueError('tutoring restriction: variable damage base requires an explicit source-backed policy')
  elif db>((7 if policy=='official_sep2015' else 6) if level<20 else 9):
   raise ValueError('tutoring restriction: damage base exceeds level allowance')
 result={'source':MOVES,'move_id':mid,'learned_at_level':level,'damage_base':db,'frequency':raw_frequency}
 if policy in ('core','official_sep2015'):result.update(policy=policy,source_proof=proof)
 return result


def mentor_effect_ranks(rules,actor,skills):
 """Observe rank effects now; preserve their native inputs for later learning validation."""
 ranks=[S.effective_rank(rules,actor,v) for v in skills]
 if ranks==[S.rank(rules,actor,v)[2] for v in skills]:return ranks,None
 import trainer_feature_acquisition as A
 aliases={S.key(name) for uid,p in rules.skill_policy.get('rank_effects',{}).items() for name in (uid,*p['aliases'])}
 snapshot={'teacher_id':actor.entity_id,'mentor_skills':list(skills),'level':actor.level,'skills':deepcopy(actor.spec.get('skills',{})),
  'edges':[v for v in actor.spec.get('edges',[]) if S.key(v) in aliases],
  'edge_choices':{k:deepcopy(v) for k,v in actor.spec.get('edge_choices',{}).items() if S.key(k) in aliases}}
 return ranks,dict(snapshot,integrity_id=A._digest('mentor/rank-observation/v1',snapshot))


def validate_mentor_ranks(rules,record):
 skills=record.get('mentor_skills');ranks=record.get('mentor_skill_ranks')
 ordinary={v['rank'] for v in S._declared_ranks(rules)[0].values()}
 effects={v['effective_rank'] for v in rules.skill_policy.get('rank_effects',{}).values()}
 bound='mentor_acquisition_evidence' in record
 if bound:__import__('mentor').validate_teaching_evidence(rules,record)
 if not isinstance(skills,list) or len(skills)!=2 or len(set(skills))!=2 or any(v not in MENTOR_SKILLS for v in skills) or not isinstance(ranks,list) or len(ranks)!=2 or any(type(v)is not int or v<(1 if bound else 3) or v not in ordinary|effects for v in ranks):
  raise ValueError('Mentor natural exception requires both actual selected skill ranks')
 witness=record.get('mentor_rank_evidence')
 if witness is None:
  if any(v not in ordinary for v in ranks):raise ValueError('Mentor effect rank requires historical owned rank-effect evidence')
  return ranks
 import trainer_feature_acquisition as A
 if type(witness)is not dict or set(witness)!={'teacher_id','mentor_skills','level','skills','edges','edge_choices','integrity_id'}:
  raise ValueError('Mentor historical rank-effect evidence required')
 snapshot={k:deepcopy(v) for k,v in witness.items() if k!='integrity_id'}
 if witness['integrity_id']!=A._digest('mentor/rank-observation/v1',snapshot) or snapshot['teacher_id']!=record.get('teacher_id') or snapshot['mentor_skills']!=skills:
  raise ValueError('Mentor historical rank-effect observation changed')
 C.integer(snapshot['level'],'historical Mentor level',1)
 if type(snapshot['skills'])is not dict or type(snapshot['edges'])is not list or type(snapshot['edge_choices'])is not dict:
  raise ValueError('Mentor historical rank-effect inputs required')
 from types import SimpleNamespace
 historical=SimpleNamespace(kind='trainer',level=snapshot['level'],spec=snapshot)
 if any(S.rank(rules,historical,v)[2]<(1 if bound else 3) for v in skills) or [S.effective_rank(rules,historical,v) for v in skills]!=ranks:
  raise ValueError('Mentor ranks differ from historical owned rank-effect evidence')
 return ranks


def teach_feature(e,actor,*,target,move_id,feature,seconds,reason,replace=None,mentor_ancestor=None):
 """Native Mentor/Tutor routes with source-specific eligibility and occupancy."""
 import mentor_csv as CSV_MENTOR
 if feature==MENTOR and CSV_MENTOR.has_receipt(actor):feature=CSV_MENTOR.SOURCE
 if feature not in (MENTOR,MOVE_TUTOR,EGG_TUTOR,CSV_MENTOR.SOURCE):raise ValueError('reviewed teaching feature required')
 if mentor_ancestor is not None and feature!=CSV_MENTOR.SOURCE:raise ValueError('ancestor choice belongs to exact CSV Mentor')
 C.integer(seconds,'GM-established Extended activity duration seconds',1);_text(reason,'teaching duration and application reason')
 import state_grants as G
 return G.transition(e,target,lambda se,st,sa:_teach_feature(se,sa,target=st,move_id=move_id,feature=feature,seconds=seconds,reason=reason,replace=replace,mentor_ancestor=mentor_ancestor),participants=(actor,))


def _teach_feature(e,actor,*,target,move_id,feature,seconds,reason,replace,mentor_ancestor=None):
 import pokemon_activities as P,move_state as M,frequency as F,world_entities as W
 W.require_actors(e,actor,target);P._trainer(actor);P._pokemon(target);P._outside(e)
 import mentor_csv as CSV_MENTOR
 if feature==MENTOR and CSV_MENTOR.has_receipt(actor):feature=CSV_MENTOR.SOURCE
 csv_mentor=feature==CSV_MENTOR.SOURCE
 import mentor as MENTOR_FULL
 variant=MENTOR_FULL.teaching_variant(actor,feature) if not csv_mentor else 'local_csv'
 bound=None if csv_mentor else MENTOR_FULL.acquired(actor,feature)
 if feature==EGG_TUTOR and variant=='local_csv':raise ValueError('CSV109 edits the actual EggList through its source-specific entry')
 if feature==MOVE_TUTOR and variant in ('local_translation','local_csv') and target.spec.get('trainer_id')!=actor.entity_id:
  raise ValueError('selected local Move Tutor effect requires your own Pokemon')
 source(e.r,MENTOR,MOVES,POINTS,*([] if csv_mentor else [feature]))
 if not _acquired_feature(actor,MENTOR) or not _acquired_feature(actor,MENTOR if csv_mentor else feature):raise ValueError('actual acquired teaching feature required')
 skills=actor.spec.get('mentor_skills')
 if not isinstance(skills,list) or len(skills)!=2 or len(set(skills))!=2 or any(v not in MENTOR_SKILLS for v in skills):raise ValueError('actual selected Mentor skills required')
 ordinary_ranks=[S.rank(e.r,actor,v)[2] for v in skills]
 if bound is None and min(ordinary_ranks)<3:raise ValueError('both Mentor skills require Novice rank')
 if bound is None and feature not in (MENTOR,CSV_MENTOR.SOURCE) and max(ordinary_ranks)<5:raise ValueError('Move Tutor requires an Expert Mentor skill')
 if feature==EGG_TUTOR and not _acquired_feature(actor,MOVE_TUTOR):raise ValueError('Egg Tutor requires actual acquired Move Tutor')
 if feature==EGG_TUTOR and target.spec.get('egg_tutor_history'):raise ValueError('Egg Tutor may affect this Pokemon only once')
 if actor.spec.get('frequency_state',{}).get('day',0)!=target.spec.get('frequency_state',{}).get('day',0):raise ValueError('teaching calendars must agree')
 cost=1 if feature in (MENTOR,CSV_MENTOR.SOURCE) else 2;frequency='하루x3' if feature in (MENTOR,CSV_MENTOR.SOURCE) else '하루'
 if feature==MOVE_TUTOR and variant=='local_csv':frequency='하루x2'
 native_source=MENTOR if csv_mentor else feature
 if _balance(target.spec)<cost:raise ValueError('insufficient actual Tutor Points')
 if not F.activation_allowed(actor,native_source,frequency,engine=e):raise ValueError('teaching feature daily frequency exhausted')
 mid=e.r.move_id(move_id)
 if mid is None or mid in getattr(e.r,'excluded_moves',{}):raise ValueError('selected actual teaching move required')
 sp=species_lookup(e.r,target.spec['species']);ls=e.r.learnsets.get(sp['name'],{})
 csv_plan=None
 if csv_mentor:
  csv_plan=CSV_MENTOR.prepare(e,actor,target,mid,ancestor=mentor_ancestor)
  cost=csv_plan['mentor_csv_proof']['point_cost']
 elif feature==MENTOR:
  ranks,rank_evidence=mentor_effect_ranks(e.r,actor,skills)
  opportunities=M.current_natural_evidence(e.r,dict(target.spec,level=min(100,target.level+sum(ranks)))).get(mid,[])
  if not any(row['kind'] in ('level_up','n_tutor') for row in opportunities):raise ValueError('Mentor move exceeds both-skill level allowance or is not (N)')
 elif feature==MOVE_TUTOR:
  listed={e.r.move_id(re.sub(r'\s*\(N\)','',str(v),flags=re.I)) for v in ls.get('tutor',[])}
  import type_sync as TYPE_SYNC
  permission=TYPE_SYNC.learning_permission(e.r,target.spec,mid,'tutor')
  if permission is False:raise ValueError('GM Type Sync exception forbids this Tutor move')
  import underdog_lessons as LESSONS
  if mid not in listed and permission is not True and not LESSONS.learning_permission(e.r,target.spec,mid,'tutor'):raise ValueError('move is absent from actual species Tutor List')
 elif mid not in set(MENTOR_FULL.individual_egg_list(e.r,target.spec)):raise ValueError('move is absent from actual species or source-scoped individual Egg List')
 admission=tutor_admission(e.r,mid,target.level,policy=MENTOR_FULL.teaching_policy(actor))
 old=e.r.move_id(replace) if replace is not None else None;baseline=M.known(e.r,target.spec)
 if mid in baseline:raise ValueError('Pokemon already learned that move')
 if replace is not None and old not in baseline:raise ValueError('explicit replacement must name an actually learned permanent move')
 record={'method':'mentor_csv' if csv_mentor else 'mentor' if feature==MENTOR else 'tutor' if feature==MOVE_TUTOR else 'egg','source':native_source,'paid_tp':cost,'teacher_id':actor.entity_id,'species_id':sp['id'],'learned_at_level':target.level,'reason':reason,'seconds':seconds}
 record['tutoring_admission']=admission
 if bound is not None:record['mentor_acquisition_evidence']=deepcopy(bound)
 if feature==MENTOR:record.update(mentor_skills=list(skills),mentor_skill_ranks=list(ranks))
 if feature==MENTOR and rank_evidence is not None:record['mentor_rank_evidence']=rank_evidence
 if csv_mentor:record.update(csv_plan,mentor_source_clause=CSV_MENTOR.SOURCE)
 if feature==MENTOR and target.spec.get('type_sync'):record['type_sync_id']=target.spec['type_sync']['history'][-1]['id']
 candidate=__import__('world_entities').spec_copy(target)
 if old is not None:
  import move_type_sync as MOVE_SYNC
  MOVE_SYNC.forget_spec(e.r,candidate,old,at=e.elapsed_seconds,reason=reason)
  __import__('ace_trainer').forget_spec(e.r,candidate,old,at=e.elapsed_seconds,reason=reason)
 moves=[m for m in candidate.get('moves',[]) if e.r.move_id(m)!=old]
 candidate['moves']=moves
 import learning_grant as LEARNING
 details={k:v for k,v in record.items() if k not in ('method','source','paid_tp','teacher_id','species_id','learned_at_level','reason')}
 LEARNING.learn_moves(e.r,candidate,candidates=[mid],selected=[mid],method=record['method'],source=native_source,
  reason=reason,provider=actor.entity_id,paid_tp=cost,details=details,replaced=old)
 moves=candidate['moves'];record=candidate['move_learning'][mid]
 M.record_natural_opportunities(e.r,candidate,reason='completed source-specific teaching')
 M.validate_spec(e.r,candidate,require_routes=True)
 if feature==EGG_TUTOR:candidate.setdefault('egg_tutor_history',[]).append({'move_id':mid,**deepcopy(record)})
 import turn as TURN
 if not TURN.spend(e,actor,'extended',feature):raise ValueError('teaching requires the actual Extended action permission')
 import activity_jobs as JOBS
 JOBS.run_fixed(e,actor,(target,),seconds=seconds,source=native_source,context={'move_id':mid})
 F.consume_activation(actor,native_source,frequency,engine=e)
 for field in ('move_learning','move_learning_log',M.HISTORY,'egg_tutor_history','move_type_sync','signature_techniques'):
  if field in candidate:target.spec[field]=candidate[field]
 if 'signature_techniques' in candidate:target.spec['tutor_points']=candidate['tutor_points']
 import state_grants as G
 G.set_baseline(target,'moves',moves);_debit_points(target.spec,cost)
 import trainer_retraining as RETRAINING
 RETRAINING.irreversible(e,actor,native_source,
  event_id='teaching:'+actor.entity_id+':'+target.entity_id+':'+native_source+':'+mid+':'+str(e.elapsed_seconds),
  reason='completed permanent Move teaching to '+target.entity_id+': '+mid)
 return {'activity':'teach_feature','move':mid,'replaced':old,'point_cost':cost,'source':feature,'seconds':seconds,'classification':M.describe(e.r,target.spec)['classifications'][mid]}
