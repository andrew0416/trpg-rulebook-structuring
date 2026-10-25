"""PTK ch04:2203-2253 Athlete: trained stats, Coaching and Adrenaline Rush on existing owners.

The class is a template. Committed static acquisitions own the printed
prerequisites (Novice Athletics plus one listed Edge; Training Regime;
Expert Athletics) and each [+HP] tag. The class Extended action (one hour of
exercise) selects the two trained stats whose default combat stage is +1
(combat_stage_sources base source). Coaching is an armed 1 AP triggered Free
Action answered at the actual maneuver attempt (opposed-check bonus die,
doubled Sprint, automatic Attack of Opportunity hit, loyalty-free automatic
Intercept), once per Pokemon per Scene. Adrenaline Rush records the actual
HP crossing to half or below and the Trainer answers it as a triggered Free
Action limited to three per day and once per Scene.

Training Regime reads the current two trained stats; its five passive bonuses
use the native maneuver, Intercept, Move completion and Sprint owners.
"""
from copy import deepcopy
from pathlib import Path
import json
import common_checks as C
import state_grants as G

_data=json.loads((Path(__file__).resolve().parents[1]/'data/athlete-definitions.json').read_text(encoding='utf8'))
DEFINITIONS=_data['features']
FEATURES={u:tuple(d['span']) for u,d in DEFINITIONS.items()}
CLASS='class/운동선수';REGIME='feat/훈련-상황';COACHING='feat/코칭';ADRENALINE='feat/아드레날린-러시'
ENGLISH={d['english']:u for u,d in DEFINITIONS.items()}
SKILL=_data['skill'];RANKS=_data['ranks'];EDGES=tuple(_data['prerequisite_edges'])
STAT_TAG=_data['stat_tag'];TRAINED=_data['trained_stats']
COACHING_SKILLS=tuple(_data['coaching_skills']);BRANCHES=tuple(_data['coaching_branches'])
COACHING_QUOTA={'kind':'scene','uses':DEFINITIONS[COACHING]['frequency']['uses']}
ADRENALINE_DAILY=dict(DEFINITIONS[ADRENALINE]['frequency']);ADRENALINE_SCENE=dict(DEFINITIONS[ADRENALINE]['scene_frequency'])
TRAINED_KEY='athlete_trained_stats'          # trainer.spec: the two current trained stats (default +1 CS)
TRAINED_HISTORY='athlete_training_history'   # trainer.spec: ended trained-stat selections
BASE_PREFIX='athlete-training:'              # combat_stage_sources base key: prefix + trainer id
COACHING_ARMED='athlete_coaching_armed'      # pokemon.spec: accepted next Coaching trigger (branch, skill)
COACHING_PENDING='_athlete_coaching_pending' # pokemon.custom_conditions: opposed maneuver declared, cost not yet paid
COACHING_ACTIVE='_athlete_coaching_active'   # pokemon.custom_conditions: paid opposed bonus for the running maneuver
COACHING_HISTORY='athlete_coaching_history'  # trainer.spec: paid Coaching receipts
ADRENALINE_TRIGGER='athlete_adrenaline_trigger'  # trainer.spec: pending printed trigger (HP to half or below)
ADRENALINE_HISTORY='athlete_adrenaline_history'  # trainer.spec: Adrenaline Rush receipts


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


def acquired(actor,feature,*,exclude=()):
 if feature in exclude:return None
 rows=records(actor,feature,True)
 if len(rows)>1:raise ValueError('one exact acquired Athlete Feature required')
 return rows[0] if rows else None


def _rank(engine,actor):
 import skill_modifiers as S
 return S.rank(engine.r,actor,SKILL)[2]


def _owned_edges(actor):
 import acquired_features as A
 return [edge for edge in EDGES if A.owned_rule_count(actor,edge)]


def acquisition_snapshot(engine,actor,feature,rank=None):
 d=DEFINITIONS[feature]
 if rank is not None:raise ValueError('this Athlete Feature is not Ranked')
 if feature==CLASS:
  return {'athletics':_rank(engine,actor),'edges':_owned_edges(actor),'parents':[]}
 snapshot={'parents':[r['request_id'] for r in records(actor,CLASS,True)],'athletics':_rank(engine,actor)}
 if d.get('prerequisites'):
  snapshot['prerequisites']={p:[r['request_id'] for r in records(actor,p,True)] for p in d['prerequisites']}
 return snapshot


def qualification(actor,feature,snapshot,prerequisite_source):
 import acquisition_qualification as Q
 d=DEFINITIONS[feature]
 fields=({'athletics','edges','parents'} if feature==CLASS else {'athletics','parents'})|({'prerequisites'} if d.get('prerequisites') else set())
 if prerequisite_source is not None or type(snapshot) is not dict or set(snapshot)!=fields:raise ValueError('exact Athlete acquisition observations required')
 C.integer(snapshot['athletics'],'Athlete Athletics rank',0)
 if type(snapshot['parents']) is not list:raise ValueError('Athlete acquisition parents must be a list')
 checks=[Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required')]
 if feature==CLASS:
  edges=snapshot['edges']
  if type(edges) is not list or len(set(edges))!=len(edges) or any(e not in EDGES for e in edges):raise ValueError('Athlete prerequisite Edge observations must be printed alternatives')
  checks.append(Q.check('athletics','prerequisite',snapshot['athletics']>=RANKS['novice'],'printed Novice Athletics required'))
  checks.append(Q.check('edge','prerequisite',len(edges)>=d['edge_alternatives'],'one actual acquired printed Edge required: Athletic Initiative, Mounted Prowess, Power Boost, Stamina or Swimmer'))
 else:
  known={r['request_id'] for r in records(actor,CLASS)}
  checks.append(Q.check('class','prerequisite',bool(snapshot['parents']) and set(snapshot['parents'])<=known,'actual acquired Athlete class required'))
  for p in d.get('prerequisites',[]):
   owned={r['request_id'] for r in records(actor,p)}
   listed=snapshot['prerequisites'].get(p) if type(snapshot['prerequisites']) is dict else None
   checks.append(Q.check(p,'prerequisite',bool(listed) and set(listed)<=owned,'actual acquired '+DEFINITIONS[p]['english']+' required'))
  requirement=d.get('skill_requirement')
  if requirement:
   checks.append(Q.check('athletics','prerequisite',snapshot['athletics']>=requirement['rank'],'printed Expert Athletics required'))
 return Q.require(feature,'native','acquire',checks)


def require(engine,actor,feature=CLASS):
 import world_entities as W
 W.require_actors(engine,actor)
 hobbyist=feature==COACHING and __import__('hobbyist').provider(actor,feature) is not None
 if actor.kind!='trainer' or (acquired(actor,CLASS) is None and not hobbyist) or (feature!=CLASS and acquired(actor,feature) is None):
  raise ValueError('actual acquired Athlete Feature required: '+feature)
 return acquired(actor,feature)


def _owned_pokemon(engine,trainer,pokemon):
 import world_entities as W
 W.require_actors(engine,trainer,pokemon)
 if pokemon.kind!='pokemon' or W.identity_field(engine,pokemon,'owner_id')!=trainer.entity_id:raise ValueError('actual owned Pokemon required')


def trainer_of(engine,actor,feature=CLASS,*,exclude=()):
 import world_entities as W
 if actor.kind=='trainer':return actor if acquired(actor,feature,exclude=exclude) and (acquired(actor,CLASS,exclude=exclude) or (feature==COACHING and not exclude and __import__('hobbyist').provider(actor,feature))) else None
 index=W.actor_index(engine)
 if index.get(actor.entity_id) is not actor:return None
 owner=index.get(W.identity_field(engine,actor,'owner_id',index=index))
 if owner is None or owner.kind!='trainer' or acquired(owner,feature,exclude=exclude) is None:return None
 if acquired(owner,CLASS,exclude=exclude) is None and not (feature==COACHING and not exclude and __import__('hobbyist').provider(owner,feature)):return None
 return owner


# ---------------------------------------------------------------- trained stats (class Extended action)
def _base_key(actor):
 return BASE_PREFIX+actor.entity_id


def trained_stats(actor):
 """The current trained stats of an Athlete, or [] (validates the record shape)."""
 import combat_stage_sources as CS
 row=actor.spec.get(TRAINED_KEY)
 if row is None:return []
 if (type(row) is not dict or set(row)!={'stats','acquisition','clause_id','at','seconds','job_id','reason'} or row['clause_id']!=clause(CLASS)
   or type(row['stats']) is not list or len(row['stats'])!=TRAINED['count'] or len(set(row['stats']))!=len(row['stats'])
   or any(s not in CS.STATS or s in TRAINED['excluded'] for s in row['stats']) or row['seconds']!=TRAINED['exercise_seconds']):
  raise ValueError('invalid Athlete trained-stat record')
 return list(row['stats'])


def _install(t,stats):
 import combat_stage_sources as CS
 key=_base_key(t)
 CS.end_source(t,ends=key)
 for stat in stats:CS.add_base(t,key,stat,TRAINED['default_stage'],source=CLASS,ends=key)


def regime(actor,stat):
 """Only a living acquisition and a currently trained stat enable a passive."""
 return (actor.kind=='trainer' and acquired(actor,CLASS) is not None
  and acquired(actor,REGIME) is not None and stat in trained_stats(actor))


def regime_source(rules):
 """S-001: the Korean six DR and original Core five DR are selectable."""
 from source_context import verified_source
 if rules._selected_rule(REGIME,supports_versions=True)!=REGIME:raise ValueError('selected Training Regime required')
 version=rules.ruleset.unit_versions.get(REGIME,'ptk')
 versions={'ptk':6,'ptu-core-1.05':5}
 if version not in versions:raise ValueError('unknown Training Regime source version')
 verified_source(rules,{'file':'input/ch04-trainer-classes.md','sha256':_data['source_sha256']},label='Training Regime')
 if version=='ptu-core-1.05':
  verified_source(rules,{'file':'source-audit/ptu-core-1.05.pdf','sha256':'e5e0371031601c3ad0a04056771c17599a2d8826e5a5102ccd37f9b368108907'},label='Core Training Regime p155',source_root='source-audit')
 return {'version':version,'intercept_reduction':versions[version]}


def maneuver_accuracy(engine,actor,move):
 """The producer's current accuracy event also covers included-cost maneuvers."""
 events=getattr(engine,'_precision_events',[])
 row=events[-1] if events else {}
 actual=(getattr(engine,'_athlete_maneuver_accuracy',None) is actor
  and row.get('actor') is actor and row.get('source')==move['id']
  and row.get('producer')=='combat_maneuver' and row.get('round')==engine.round_no and row.get('result')=='activated')
 return 2 if actual and regime(actor,'atk') else 0


def resist_maneuver(engine,target,source,plans):
 """SM.prepare binds this bonus only to the actual target's resisting pool."""
 if not regime(target,'spd'):return
 for actor,skill,options in plans:
  if actor is target:
   C.integer(options.get('mods',0),'maneuver modifier')
   options['mods']=options.get('mods',0)+2


def intercept_reduction(engine,target,event):
 """Require the real recipient token; intercepted=True alone is not evidence."""
 if not regime(target,'def') or not event or event.get('target') is not target:return 0
 token=event.get('athlete_defense_token')
 if token is None:return 0
 import move_defense_reactions as D
 if not D.require_damage_receipt(engine,token,event['attacker'],target,event['move']):return 0
 defense=D._defense(engine,engine._passive_events[token[0]])
 if not any(a.get('actor_id')==target.entity_id and a.get('source') in (D.MELEE,D.RANGED)
   and a.get('paid')is True and a.get('outcome')=='intercepted' for a in defense['attempts']):return 0
 return regime_source(engine.r)['intercept_reduction']


def begin_move(engine,actor,move,completion):
 """Record the optional Special Attack choice once for this native Move."""
 if not regime(actor,'spa') or move['class'] not in ('물리','특수'):return
 import class_move_grants as MOVES
 allowed={'move/'+name for names in MOVES.RANKED['feat/육상-기술'].values() for name in names}
 if move['id'] not in allowed:return
 row=engine._move_completions[completion]
 if row['actor'] is not actor or row['move_id']!=move['id']:raise ValueError('actual Athlete Move completion required')
 if 'athlete_regime' not in row:
  answer=engine.rulings.decide({'type':'training_regime_special_attack','unit':REGIME,'actor':actor.name,'move_id':move['id'],'text':'Add half the current Special Attack Stat to this damaging Athlete Move (not with Twisted Power)?'})
  if answer is not None and type(answer)is not bool:raise ValueError('explicit Training Regime Special Attack choice required')
  row['athlete_regime']={'enabled':answer is True,'source':REGIME,'request_id':acquired(actor,REGIME)['request_id']}
 move['_athlete_regime_completion']=completion
 for target_move in row['target_moves'].values():target_move['_athlete_regime_completion']=completion


def move_bonus(engine,actor,move):
 token=move.get('_athlete_regime_completion')
 if token is None:return 0
 row=getattr(engine,'_move_completions',{}).get(token)
 if row is None or row['actor'] is not actor or row['move_id']!=move['id']:raise ValueError('actual Training Regime Move receipt required')
 if not row.get('athlete_regime',{}).get('enabled') or not regime(actor,'spa'):return 0
 return __import__('arithmetic_policy').ratio(actor.staged('spa'),2)


def _end_training(e,t,*,cause):
 import combat_stage_sources as CS
 previous=trained_stats(t)
 CS.end_source(t,ends=_base_key(t))
 if previous:
  t.spec.setdefault(TRAINED_HISTORY,[]).append(dict(deepcopy(t.spec[TRAINED_KEY]),ended_at=e.elapsed_seconds,cause=cause))
  t.spec.pop(TRAINED_KEY)
  e.log('  '+t.name+': 운동선수 훈련 스탯 종료 ('+cause+')',CLASS)


def exercise(engine,trainer,stats,*,reason):
 """One hour of exercise (Extended, outside combat): choose two trained stats other than HP; replaces the previous two."""
 import combat_stage_sources as CS,pokemon_activities as P
 require(engine,trainer,CLASS);_text(reason,'exercise reason')
 if type(stats) is not list or len(stats)!=TRAINED['count'] or len(set(stats))!=len(stats) or any(s not in CS.STATS or s in TRAINED['excluded'] for s in stats):
  raise ValueError('two distinct trained stats other than HP required')
 P._outside(engine)
 def apply(e,t):
  import turn as TURN,activity_jobs as JOBS
  if not TURN.spend(e,t,DEFINITIONS[CLASS]['action'],CLASS):raise ValueError('Athlete exercise Extended action unavailable')
  job=JOBS.run_fixed(e,t,(),seconds=TRAINED['exercise_seconds'],source=CLASS,context={'stats':list(stats),'reason':reason})
  _end_training(e,t,cause='exercise')
  _install(t,stats)
  t.spec[TRAINED_KEY]={'stats':list(stats),'acquisition':acquired(t,CLASS)['request_id'],'clause_id':clause(CLASS),'at':e.elapsed_seconds,
   'seconds':TRAINED['exercise_seconds'],'job_id':job['job_id'],'reason':reason}
  e.log('  '+t.name+': 1시간 운동 → 훈련 스탯 '+'/'.join(stats)+' (기본 전투단계 +'+str(TRAINED['default_stage'])+')',CLASS)
  return deepcopy(t.spec[TRAINED_KEY])
 return G.transition(engine,trainer,apply)


# ---------------------------------------------------------------- Coaching
def armed(pokemon):
 row=pokemon.spec.get(COACHING_ARMED)
 if row is None:return None
 if (type(row) is not dict or set(row)!={'trainer_id','acquisition','clause_id','branch','skill','armed_at'} or row['clause_id']!=clause(COACHING)
   or row['branch'] not in BRANCHES or (row['skill'] is None)!=(row['branch']!='opposed')):raise ValueError('invalid Coaching arming receipt')
 return row


def _canonical_skill(engine,skill):
 import skill_modifiers as S
 allowed={S.skill_id(engine.r.skill_policy,x,required=True):x for x in COACHING_SKILLS}
 identity=S.skill_id(engine.r.skill_policy,skill,required=True) if type(skill) is str and skill.strip() else None
 if identity not in allowed:raise ValueError('Coaching opposed bonus applies to Acrobatics, Athletics, Combat or Stealth')
 return allowed[identity]


def arm_coaching(engine,trainer,pokemon,branch,skill=None):
 """Accept the next eligible Coaching trigger for one owned Pokemon; spends nothing yet."""
 require(engine,trainer,COACHING);_owned_pokemon(engine,trainer,pokemon)
 if branch not in BRANCHES:raise ValueError('Coaching branch must be opposed, sprint, opportunity or intercept')
 if branch=='opposed':skill=_canonical_skill(engine,skill)
 elif skill is not None:raise ValueError('only the opposed Coaching branch names a skill')
 def apply(e,t,q):
  q.spec[COACHING_ARMED]={'trainer_id':t.entity_id,'acquisition':acquired(t,COACHING)['request_id'],'clause_id':clause(COACHING),'branch':branch,'skill':skill,'armed_at':e.elapsed_seconds}
  return deepcopy(q.spec[COACHING_ARMED])
 return G.transition(engine,trainer,apply,participants=(pokemon,))


def disarm_coaching(engine,trainer,pokemon):
 import world_entities as W
 W.require_actors(engine,trainer,pokemon)
 row=armed(pokemon)
 if row is None or row['trainer_id']!=trainer.entity_id:raise ValueError('actual armed Coaching by this Trainer required')
 def apply(e,t,q):
  q.spec.pop(COACHING_ARMED);return True
 return G.transition(engine,trainer,apply,participants=(pokemon,))


def _coaching_key(pokemon):
 return COACHING+':'+pokemon.entity_id


def coaching_ready(engine,pokemon,branch):
 """The armed Trainer when the printed trigger could be answered now for this branch (read-only)."""
 import world_entities as W,action_points as AP,frequency as F,turn as TURN,action_lifecycle as A,body_modes as BODY
 if getattr(pokemon,'kind',None)!='pokemon':return None
 row=armed(pokemon)
 if row is None or row['branch']!=branch:return None
 index=W.actor_index(engine)
 if index.get(pokemon.entity_id) is not pokemon:return None
 trainer=index.get(row['trainer_id'])
 if trainer is None or trainer.kind!='trainer' or W.identity_field(engine,pokemon,'owner_id',index=index)!=trainer.entity_id:return None
 if trainer_of(engine,pokemon,COACHING) is not trainer or not any(r['request_id']==row['acquisition'] for r in records(trainer,COACHING,True)):return None
 if AP.available(trainer)<DEFINITIONS[COACHING]['ap']:return None
 if not F.activation_allowed(trainer,_coaching_key(pokemon),COACHING_QUOTA,engine=engine):return None
 if not TURN.can_act(engine,trainer) or not A.status_permission(engine,trainer,'free',new_action=True) or not BODY.permits(trainer,'free'):return None
 return trainer


def _history(actor,key):
 rows=actor.spec.get(key,[])
 if type(rows) is not list:raise ValueError('Athlete producer history must be a list')
 return rows


def _pay_coaching(engine,trainer,pokemon,branch,facts):
 """The actual trigger: pay 1 AP and the triggered Free Action, once per Scene per Pokemon."""
 import action_points as AP,frequency as F,action_lifecycle as A
 row=armed(pokemon)
 key=_coaching_key(pokemon)
 if not F.activation_allowed(trainer,key,COACHING_QUOTA,engine=engine):raise ValueError('Coaching was already used for this Pokemon this Scene')
 A.triggered_free_action(engine,trainer,COACHING)
 AP.spend(trainer,DEFINITIONS[COACHING]['ap'])
 F.consume_activation(trainer,key,COACHING_QUOTA,engine=engine)
 pokemon.spec.pop(COACHING_ARMED)
 receipt={'id':COACHING+':'+trainer.entity_id+':'+str(len(_history(trainer,COACHING_HISTORY))+1),'pokemon_id':pokemon.entity_id,'branch':branch,'skill':row['skill'],
  'round':engine.round_no,'at':engine.elapsed_seconds,'scene':F.state(trainer)['scene'],'acquisition':row['acquisition'],'clause_id':clause(COACHING),'facts':deepcopy(facts)}
 trainer.spec.setdefault(COACHING_HISTORY,[]).append(receipt)
 engine.log('  '+trainer.name+': 코칭 ('+branch+') → '+pokemon.name+' (1 AP, 자유 행동)',COACHING)
 return deepcopy(receipt)


def _marker(pokemon,key):
 row=pokemon.custom_conditions.get(key)
 if row is None:return None
 if type(row) is not dict or set(row)!={'trainer_id','source','skill','round','at'}:raise ValueError('invalid Coaching maneuver marker')
 return row


def coaching_prepare(engine,actor,source,plans):
 """skill_maneuver_actions.prepare: an armed opposed Coaching applies to this actual maneuver declaration."""
 if getattr(actor,'kind',None)!='pokemon':return None
 actor.custom_conditions.pop(COACHING_PENDING,None)
 if _marker(actor,COACHING_ACTIVE) is not None or not plans:return None
 trainer=coaching_ready(engine,actor,'opposed')
 if trainer is None:return None
 import skill_modifiers as S
 row=armed(actor)
 if S.skill_id(engine.r.skill_policy,plans[0][1])!=S.skill_id(engine.r.skill_policy,row['skill']):return None
 actor.custom_conditions[COACHING_PENDING]={'trainer_id':trainer.entity_id,'source':source,'skill':row['skill'],'round':engine.round_no,'at':engine.elapsed_seconds}
 return deepcopy(actor.custom_conditions[COACHING_PENDING])


def coaching_commit(engine,actor):
 """After the maneuver's own action cost: pay the declared Coaching and keep its bonus die for this maneuver."""
 if getattr(actor,'kind',None)!='pokemon':return None
 pending=_marker(actor,COACHING_PENDING)
 if pending is None:return None
 actor.custom_conditions.pop(COACHING_PENDING)
 trainer=coaching_ready(engine,actor,'opposed')
 if trainer is None or trainer.entity_id!=pending['trainer_id']:raise ValueError('Coaching is no longer available for this maneuver')
 receipt=_pay_coaching(engine,trainer,actor,'opposed',{'source':pending['source'],'skill':pending['skill']})
 actor.custom_conditions[COACHING_ACTIVE]={k:pending[k] for k in ('trainer_id','source','skill','round','at')}
 return receipt


def coaching_end(actor):
 if getattr(actor,'custom_conditions',None) is None:return
 actor.custom_conditions.pop(COACHING_PENDING,None);actor.custom_conditions.pop(COACHING_ACTIVE,None)


def coaching_dice(engine,c,skill):
 """Engine skill-roll hook: one bonus d6 for the declared opposed maneuver check of a coached Pokemon."""
 if getattr(c,'kind',None)!='pokemon':return 0
 marker=_marker(c,COACHING_ACTIVE) or _marker(c,COACHING_PENDING)
 if marker is None:return 0
 import skill_modifiers as S
 return 1 if S.skill_id(engine.r.skill_policy,skill)==S.skill_id(engine.r.skill_policy,marker['skill']) else 0


def coach_sprint(engine,pokemon):
 """movement_actions.sprint: an armed sprint Coaching doubles this Sprint instead of +50%."""
 trainer=coaching_ready(engine,pokemon,'sprint')
 if trainer is None:return None
 state=pokemon.custom_conditions.get('질주')
 if type(state) is not dict:return None
 receipt=_pay_coaching(engine,trainer,pokemon,'sprint',{'sprint_round':state.get('round'),'source_policy':state.get('source_policy')})
 state['coaching']={'trainer_id':trainer.entity_id,'receipt_id':receipt['id']}
 return receipt


def sprint_rate(engine,actor):
 """Coaching and a Speed-trained Athlete replace +50% by +100%; never add."""
 state=getattr(actor,'custom_conditions',{}).get('질주')
 return '1' if type(state) is dict and (state.get('coaching') or regime(actor,'spe')) else '0.5'


def opportunity(engine,pokemon,mover,run):
 """turn.trigger_aoo: an armed opportunity Coaching makes this actual Attack of Opportunity hit automatically."""
 trainer=coaching_ready(engine,pokemon,'opportunity')
 if trainer is None:return run()
 receipt=_pay_coaching(engine,trainer,pokemon,'opportunity',{'mover_id':mover.entity_id})
 previous=getattr(engine,'_athlete_aoo_scope',None)
 engine._athlete_aoo_scope={'pokemon':pokemon,'mover':mover,'receipt_id':receipt['id']}
 try:return run()
 finally:
  if previous is None:del engine._athlete_aoo_scope
  else:engine._athlete_aoo_scope=previous


def aoo_outcome(engine,attacker,move):
 scope=getattr(engine,'_athlete_aoo_scope',None)
 return bool(scope and scope['pokemon'] is attacker and move.get('id')=='struggle')


def coach_intercept(engine,pokemon,target,source):
 """move_defense_reactions: an armed intercept Coaching pays at the paid Intercept attempt; the skill check then succeeds."""
 trainer=coaching_ready(engine,pokemon,'intercept')
 if trainer is None:return None
 return _pay_coaching(engine,trainer,pokemon,'intercept',{'source':source,'protected_id':target.entity_id})


# ---------------------------------------------------------------- Adrenaline Rush
def adrenaline_trigger(trainer):
 row=trainer.spec.get(ADRENALINE_TRIGGER)
 if row is None:return None
 if (type(row) is not dict or set(row)!={'round','at','before_hp','hp','max_hp','acquisition','clause_id'} or row['clause_id']!=clause(ADRENALINE)
   or not row['before_hp']*2>row['max_hp']>=row['hp']*2):raise ValueError('invalid Adrenaline Rush trigger record')
 return row


def hp_changed(engine,c,before,maximum):
 """HP producers: record the printed trigger when an Athlete is reduced from above half to half or below."""
 if getattr(c,'kind',None)!='trainer' or type(before) is not int or type(maximum) is not int:return
 if not before*2>maximum>=c.hp*2:return
 receipt=acquired(c,ADRENALINE)
 if receipt is None:return
 c.spec[ADRENALINE_TRIGGER]={'round':engine.round_no,'at':engine.elapsed_seconds,'before_hp':before,'hp':c.hp,'max_hp':maximum,'acquisition':receipt['request_id'],'clause_id':clause(ADRENALINE)}
 engine.log('  '+c.name+': 체력이 최대의 절반 이하 → 아드레날린 러시 발동 가능',ADRENALINE)


def _scene_key():
 return ADRENALINE+':scene'


def adrenaline_rush(engine,trainer,*,cure=()):
 """Triggered Free Action: +1 CS in each trained stat, cure up to two current afflictions, a Tick of temporary HP."""
 import frequency as F,status_sets as STATUS
 require(engine,trainer,ADRENALINE)
 record=adrenaline_trigger(trainer)
 if record is None:raise ValueError('Adrenaline Rush requires its actual printed trigger: HP reduced to half or below')
 if record['round']!=engine.round_no or record['at']!=engine.elapsed_seconds:raise ValueError('Adrenaline Rush trigger lapsed')
 if type(cure) not in (list,tuple) or any(type(x) is not str or not x.strip() for x in cure):raise ValueError('Adrenaline Rush cure choices must name current status afflictions')
 names=[STATUS.normalize(x) for x in cure]
 if (len(names)>DEFINITIONS[ADRENALINE]['cure_limit'] or len(set(names))!=len(names)
   or any(n not in STATUS.afflictions(trainer) for n in names)):raise ValueError('up to two actual current status afflictions may be cured')
 if not F.activation_allowed(trainer,ADRENALINE,ADRENALINE_DAILY,engine=engine):raise ValueError('Adrenaline Rush daily uses exhausted')
 if not F.activation_allowed(trainer,_scene_key(),ADRENALINE_SCENE,engine=engine):raise ValueError('Adrenaline Rush was already used this Scene')
 def apply(e,t):
  import action_lifecycle as A,temporary_hp as HP
  A.triggered_free_action(e,t,ADRENALINE)
  F.consume_activation(t,ADRENALINE,ADRENALINE_DAILY,engine=e);F.consume_activation(t,_scene_key(),ADRENALINE_SCENE,engine=e)
  stats=trained_stats(t);before_stages={s:t.stages[s] for s in stats}
  for stat in stats:e.change_stage(t,stat,DEFINITIONS[ADRENALINE]['stage_delta'])
  cured=[]
  for name in names:
   if e.cure_status(t,name) is False or name in t.conditions:raise ValueError('Adrenaline Rush could not cure '+name)
   cured.append(name)
  use_id=ADRENALINE+':'+t.entity_id+':'+str(len(_history(t,ADRENALINE_HISTORY))+1)
  tick=e.tick(t);temp_before=t.temp_hp
  gained=HP.grant(e,t,tick,provenance={'source':ADRENALINE,'owner_id':t.entity_id,'use_id':use_id})
  receipt={'id':use_id,'trigger':deepcopy(record),'round':e.round_no,'at':e.elapsed_seconds,'scene':F.state(t)['scene'],
   'daily_period':deepcopy(F.activation_period(F.state(t),'daily')),'stats':stats,'stages_before':before_stages,'stages_after':{s:t.stages[s] for s in stats},
   'cured':cured,'tick':tick,'temp_before':temp_before,'temp_gained':gained,'acquisition':record['acquisition'],'clause_id':clause(ADRENALINE)}
  t.spec.pop(ADRENALINE_TRIGGER)
  t.spec.setdefault(ADRENALINE_HISTORY,[]).append(receipt)
  e.log('  '+t.name+': 아드레날린 러시 — 훈련 스탯 +1, 치유 '+str(cured)+', 임시 체력 +'+str(gained),ADRENALINE)
  return deepcopy(receipt)
 return G.transition(engine,trainer,apply)


# ---------------------------------------------------------------- lifecycle hooks
def withdraw(engine,trainer,rule_id):
 """Retraining an Athlete source ends what it alone justified."""
 if rule_id not in FEATURES:return
 import world_entities as W
 index=W.actor_index(engine)
 if rule_id==CLASS:_end_training(engine,trainer,cause='retrained:'+CLASS)
 if rule_id in (CLASS,COACHING):
  for c in index.values():
   if c.kind!='pokemon':continue
   row=armed(c)
   if row is not None and row['trainer_id']==trainer.entity_id:c.spec.pop(COACHING_ARMED)
   for key in (COACHING_PENDING,COACHING_ACTIVE):
    marker=_marker(c,key)
    if marker is not None and marker['trainer_id']==trainer.entity_id:c.custom_conditions.pop(key)
 if rule_id in (CLASS,ADRENALINE):trainer.spec.pop(ADRENALINE_TRIGGER,None)


# ---------------------------------------------------------------- validation
def validate(engine):
 import world_entities as W,combat_stage_sources as CS,trainer_feature_acquisition as T
 index=W.actor_index(engine)
 for actor in index.values():
  stats=trained_stats(actor)
  key=_base_key(actor)
  state=actor.spec.get(CS.STATE)
  base=state['base'].get(key) if isinstance(state,dict) and isinstance(state.get('base'),dict) else None
  if stats:
   row=actor.spec[TRAINED_KEY]
   if actor.kind!='trainer' or acquired(actor,CLASS) is None or not any(r['request_id']==row['acquisition'] for r in records(actor,CLASS)):
    raise ValueError('Athlete trained stats lost their class acquisition')
   if base is None or base.get('source')!=CLASS or base.get('ends')!=key or base.get('deltas')!={s:TRAINED['default_stage'] for s in stats}:
    raise ValueError('trained-stat default combat stages disagree with the Athlete record')
  elif base is not None:raise ValueError('orphan Athlete trained-stat stage source')
  if actor.kind=='trainer':
   for sid,row,live in T._static_records(actor):
    record=row['static_acquisition']
    if not live or record['feature_id'] not in FEATURES:continue
    operation=actor.spec.get(G.KEY,{}).get('stat_sources',{}).get(STAT_TAG,{}).get('sources',{}).get(sid,{}).get('acquisition_stat_tag')
    if operation!={'delta':1,'minimum':None}:raise ValueError('actual source-owned Athlete HP stat tag required')
   for row in _history(actor,COACHING_HISTORY):
    if type(row) is not dict or row.get('clause_id')!=clause(COACHING) or row.get('branch') not in BRANCHES:raise ValueError('invalid Coaching history')
   for row in _history(actor,ADRENALINE_HISTORY):
    if type(row) is not dict or row.get('clause_id')!=clause(ADRENALINE):raise ValueError('invalid Adrenaline Rush history')
   trigger=adrenaline_trigger(actor)
   if trigger is not None and acquired(actor,ADRENALINE) is None:raise ValueError('Adrenaline Rush trigger lost its acquisition')
  elif TRAINED_KEY in actor.spec or ADRENALINE_TRIGGER in actor.spec:raise ValueError('Athlete Trainer state on a non-Trainer')
  if actor.kind=='pokemon':
   row=armed(actor)
   if row is not None:
    owner=index.get(row['trainer_id'])
    if owner is None or owner.kind!='trainer' or W.identity_field(engine,actor,'owner_id',index=index)!=owner.entity_id or acquired(owner,COACHING) is None:
     raise ValueError('Coaching arming lost its Athlete owner')
    if not any(r['request_id']==row['acquisition'] for r in records(owner,COACHING)):raise ValueError('Coaching arming provenance changed')
   for marker_key in (COACHING_PENDING,COACHING_ACTIVE):
    marker=_marker(actor,marker_key)
    if marker is not None:
     owner=index.get(marker['trainer_id'])
     if owner is None or owner.kind!='trainer' or acquired(owner,COACHING) is None:raise ValueError('Coaching maneuver marker lost its Athlete owner')
 for row in getattr(engine,'_move_completions',{}).values():
  if 'athlete_regime' not in row:continue
  choice=row['athlete_regime'];actor=row['actor']
  import class_move_grants as MOVES
  allowed={'move/'+name for names in MOVES.RANKED['feat/육상-기술'].values() for name in names}
  if (type(choice)is not dict or set(choice)!={'enabled','source','request_id'} or type(choice['enabled'])is not bool
    or choice['source']!=REGIME or row['move_id'] not in allowed or row['move']['class'] not in ('물리','특수')
    or not any(r['request_id']==choice['request_id'] for r in records(actor,REGIME))):
   raise ValueError('actual Training Regime Move choice and acquisition required')
 return True
