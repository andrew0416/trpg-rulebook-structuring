"""PTK ch04:2325-2378 Hunter: class Ability choice, Surprise!, Hunter's Reflexes, Don't Look Away and Pack Master on existing owners.

The class is a template. Committed static acquisitions own the printed
prerequisites (Novice Survival and Stealth; Adept Stealth or Survival; Adept
or Expert both; Pack Tactics) and each [+Speed] tag. The class choice (Teamwork
or Pack Hunt) is the acquired branch whose Ability the Trainer gains as a
source-owned grant. Pack Tactics and Finisher keep their existing owners
(feature_ability_lessons, effects.passive_damage_mods) and are acquirable here
so the printed prerequisite chain is real.

The four Features implemented here consume the Teamwork and Pack Hunt
Abilities, whose printed combat effects had no engine consumer before this
module: Teamwork is the +2 accuracy for allies' melee attacks against a foe
adjacent to the holder, and Pack Hunt is the triggered free AC 5 physical
attack (a Tick of HP on a hit) after an ally damages an adjacent foe with a
melee attack. Both are implemented as consumers of the actual Ability
ownership (ability_transitions.active); their completion credit stays in the
Ability ledger.

Surprise! is armed in advance for one foe and paid (Swift action, 1 or 2 AP by
attack identity, once per target per Scene) at the Trainer's actual accuracy
roll when the printed trigger holds; the second die is rolled there and the
better result finalizes the attack; both hitting Flinches the target.
Hunter's Reflexes raises the per-round Attack of Opportunity limit to three
for the Hunter and their Pokemon, and makes the Hunter's own attacks count as
adjacent for their Pokemon's Teamwork and as melee for triggering their
Pokemon's Pack Hunt. Don't Look Away answers the recorded Attack of
Opportunity hit (the Hunter or their Pokemon with Pack Hunt or Teamwork) as a
1 AP triggered Free Action once per round: a Tick of HP loss and Slowed for one
round. Pack Master rewrites Teamwork for the Hunter and their Pokemon with
Teamwork (allies targeting the foe, melee or not) and gives +2 accuracy / +5
damage against a foe successfully hit with Pack Hunt until the end of the
attacker's next turn.
"""
from copy import deepcopy
from pathlib import Path
import json
import common_checks as C
import state_grants as G

_data=json.loads((Path(__file__).resolve().parents[1]/'data/hunter-definitions.json').read_text(encoding='utf8'))
DEFINITIONS=_data['features']
FEATURES={u:tuple(d['span']) for u,d in DEFINITIONS.items()}
CLASS='class/헌터';TACTICS='feat/집단-전술';SURPRISE='feat/서프라이즈';REFLEXES='feat/헌터의-반사신경'
FINISHER='feat/피니셔';LOOK_AWAY='feat/한눈-팔지-마';PACK_MASTER='feat/무리-주인'
ENGLISH={d['english']:u for u,d in DEFINITIONS.items()}
SKILLS=tuple(_data['skills']);RANKS=_data['ranks'];STAT_TAG=_data['stat_tag']
TEAMWORK=_data['abilities']['teamwork'];PACK_HUNT=_data['abilities']['pack_hunt']
CLASS_CHOICES=tuple(_data['class_choices'])
TEAMWORK_RULE=_data['teamwork'];PACK_HUNT_RULE=_data['pack_hunt_attack']
OPPORTUNITY=_data['opportunity_limit'];SURPRISE_RULE=_data['surprise'];LOOK_AWAY_RULE=_data['dont_look_away'];PACK_MASTER_RULE=_data['pack_master']
SURPRISE_QUOTA={'kind':SURPRISE_RULE['frequency']['kind'],'uses':SURPRISE_RULE['frequency']['uses']}
SURPRISE_ARMED='hunter_surprise_armed'        # trainer.spec: accepted next Surprise! trigger (one foe)
SURPRISE_HISTORY='hunter_surprise_history'    # trainer.spec: paid Surprise! receipts
LOOK_AWAY_TRIGGER='hunter_look_away_trigger'  # trainer.spec: pending printed trigger (an AoO hit)
LOOK_AWAY_HISTORY='hunter_look_away_history'  # trainer.spec: Don't Look Away receipts
PACK_HUNT_TRIGGER='hunter_pack_hunt_trigger'  # holder.spec: pending Pack Hunt trigger (ally melee damage to an adjacent foe)
PACK_HUNT_HISTORY='hunter_pack_hunt_history'  # holder.spec: Pack Hunt attack receipts
OPPORTUNITY_USES='hunter_opportunity_uses'    # actor.spec: {'round','round_started','used'} Attacks of Opportunity this round
PACK_MASTER_KEY='hunter_pack_master'          # combat_timing record payload: per-foe +2 accuracy / +5 damage
SURPRISE_PROMPT='hunter_surprise_unaware'


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
 return [r['static_acquisition'] for _,r,live in T._static_records(actor)
  if r['static_acquisition']['feature_id'] in FEATURES and (feature is None or r['static_acquisition']['feature_id']==feature) and (not active or live)]


def acquired(actor,feature,*,exclude=()):
 if feature in exclude:return None
 rows=records(actor,feature,True)
 if len(rows)>1:raise ValueError('one exact acquired Hunter Feature required')
 return rows[0] if rows else None


def class_ability(actor):
 """The canonical Ability chosen with the live class acquisition, or None."""
 row=acquired(actor,CLASS)
 return row['snapshot']['branch'] if row else None


def _rank(engine,actor,skill):
 import skill_modifiers as S
 return S.rank(engine.r,actor,skill)[2]


def _canonical_branch(engine,branch):
 import ability_transitions as A
 if type(branch) is not str or not branch.strip():raise ValueError('Hunter class choice must name Teamwork or Pack Hunt')
 try:canonical=A.ability_id(engine.r,branch)
 except Exception as exc:raise ValueError('Hunter class choice must name Teamwork or Pack Hunt') from exc
 if canonical not in CLASS_CHOICES:raise ValueError('Hunter class choice must name Teamwork or Pack Hunt')
 if branch!=canonical:raise ValueError('Hunter class choice must be the exact Ability identity: '+canonical)
 return canonical


def acquisition_snapshot(engine,actor,feature,branch=None,rank=None):
 d=DEFINITIONS[feature]
 if rank is not None:raise ValueError('this Hunter Feature is not Ranked')
 ranks={'survival':_rank(engine,actor,SKILLS[0]),'stealth':_rank(engine,actor,SKILLS[1])}
 if feature==CLASS:
  if records(actor,CLASS,True):raise ValueError('Hunter class is already acquired; one Ability choice per Trainer')
  return {'branch':_canonical_branch(engine,branch),'parents':[],**ranks}
 if branch is not None:raise ValueError('this Hunter Feature has no acquired branch')
 snapshot={'parents':[r['request_id'] for r in records(actor,CLASS,True)],**ranks}
 if d.get('prerequisites'):
  snapshot['prerequisites']={p:[r['request_id'] for r in records(actor,p,True)] for p in d['prerequisites']}
 return snapshot


def qualification(actor,feature,snapshot,prerequisite_source):
 import acquisition_qualification as Q
 d=DEFINITIONS[feature]
 fields={'survival','stealth','parents'}|({'branch'} if feature==CLASS else set())|({'prerequisites'} if d.get('prerequisites') else set())
 if prerequisite_source is not None or type(snapshot) is not dict or set(snapshot)!=fields:raise ValueError('exact Hunter acquisition observations required')
 C.integer(snapshot['survival'],'Hunter Survival rank',0);C.integer(snapshot['stealth'],'Hunter Stealth rank',0)
 if type(snapshot['parents']) is not list:raise ValueError('Hunter acquisition parents must be a list')
 checks=[Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required')]
 if feature==CLASS:
  if snapshot['branch'] not in CLASS_CHOICES:raise ValueError('Hunter class choice must name Teamwork or Pack Hunt')
  if snapshot['parents']:raise ValueError('Hunter class acquisition has no parents')
  checks.append(Q.check('survival','prerequisite',snapshot['survival']>=RANKS['novice'],'printed Novice Survival required'))
  checks.append(Q.check('stealth','prerequisite',snapshot['stealth']>=RANKS['novice'],'printed Novice Stealth required'))
 else:
  known={r['request_id'] for r in records(actor,CLASS)}
  checks.append(Q.check('class','prerequisite',bool(snapshot['parents']) and set(snapshot['parents'])<=known,'actual acquired Hunter class required'))
  for p in d.get('prerequisites',[]):
   owned={r['request_id'] for r in records(actor,p)}
   listed=snapshot['prerequisites'].get(p) if type(snapshot['prerequisites']) is dict else None
   checks.append(Q.check(p,'prerequisite',bool(listed) and set(listed)<=owned,'actual acquired '+DEFINITIONS[p]['english']+' required'))
  alternatives=d.get('skill_alternatives')
  if alternatives:
   checks.append(Q.check('skill','prerequisite',max(snapshot['survival'],snapshot['stealth'])>=alternatives['rank'],'printed Adept Stealth or Survival required'))
  for skill,minimum in d.get('skill_requirements',{}).items():
   label={3:'Novice',4:'Adept',5:'Expert'}[minimum]+' '+{'생존':'Survival','은신':'Stealth'}[skill]
   checks.append(Q.check(skill,'prerequisite',snapshot['survival' if skill=='생존' else 'stealth']>=minimum,'printed '+label+' required'))
 return Q.require(feature,'native','acquire',checks)


def after_acquire(engine,trainer,feature,source_id,branch):
 """Inside the acquisition transaction: the printed [+Speed] tag and, for the class, the chosen Ability grant.
 Pack Tactics' tag is owned by the existing static_feature_state_grants projection, reconciled here instead."""
 import ability_transitions as A
 if feature==TACTICS:
  import static_feature_state_grants as STATIC
  STATIC.register_all(engine,trainer)
 else:G.stat(trainer,STAT_TAG,1,source_id,operation_id='acquisition_stat_tag')
 if feature==CLASS:
  canonical=_canonical_branch(engine,branch)
  G.grant(trainer,'abilities',A.label(engine.r,canonical),source_id,'feature',owner_id=trainer.entity_id,lifetime='while_owned',rule_id=CLASS,tutor_points=0)
  engine.log('  '+trainer.name+': 헌터 — '+A.label(engine.r,canonical)+' 특성 획득',CLASS)


def require(engine,actor,feature=CLASS):
 import world_entities as W
 W.require_actors(engine,actor)
 if actor.kind!='trainer' or acquired(actor,CLASS) is None or (feature!=CLASS and acquired(actor,feature) is None):
  raise ValueError('actual acquired Hunter Feature required: '+feature)
 return acquired(actor,feature)


def covered(engine,actor,feature=CLASS,*,exclude=()):
 """The Hunter whose live class and Feature cover this actor (the Trainer or an owned Pokemon), or None."""
 import world_entities as W
 if getattr(actor,'kind',None)=='trainer':return actor if acquired(actor,feature,exclude=exclude) and acquired(actor,CLASS,exclude=exclude) else None
 if getattr(actor,'kind',None)!='pokemon':return None
 index=W.actor_index(engine)
 if index.get(actor.entity_id) is not actor:return None
 owner=index.get(W.identity_field(engine,actor,'owner_id',index=index))
 if owner is None or owner.kind!='trainer' or acquired(owner,CLASS,exclude=exclude) is None or acquired(owner,feature,exclude=exclude) is None:return None
 return owner


def _owned_by(engine,pokemon,trainer,index=None):
 import world_entities as W
 return getattr(pokemon,'kind',None)=='pokemon' and W.identity_field(engine,pokemon,'owner_id',index=index)==trainer.entity_id


def _present(c):
 return c.on_field and not c.fainted and not c.captured


def _ability(actor,ability):
 import ability_transitions as A
 return getattr(actor,'kind',None) in ('trainer','pokemon') and A.active(actor,ability)


def _melee(move):
 import reactive_ability_events as R
 return R._melee(move)


def _history(actor,key):
 rows=actor.spec.get(key,[])
 if type(rows) is not list:raise ValueError('Hunter producer history must be a list')
 return rows


# ---------------------------------------------------------------- Attacks of Opportunity (Hunter's Reflexes)
def opportunity_limit(engine,c):
 return OPPORTUNITY['reflexes'] if covered(engine,c,REFLEXES) is not None else OPPORTUNITY['default']


def _opportunity_row(engine,c):
 row=c.spec.get(OPPORTUNITY_USES)
 if row is None:return None
 if type(row) is not dict or set(row)!={'round','round_started','used'} or type(row['used']) is not int or row['used']<0:raise ValueError('invalid Attack of Opportunity use record')
 return row if row['round']==engine.round_no and row['round_started']==engine.round_start_seconds else None


def opportunity_exhausted(engine,c):
 """turn.can_aoo: the ordinary single Attack of Opportunity, or the Hunter's Reflexes limit of three this round."""
 limit=opportunity_limit(engine,c)
 if limit<=OPPORTUNITY['default']:return bool(getattr(c,'aoo_used',False))
 row=_opportunity_row(engine,c)
 return (row['used'] if row else 0)>=limit


def note_opportunity(engine,c):
 """turn.trigger_aoo: count this actual Attack of Opportunity for the round."""
 row=_opportunity_row(engine,c)
 if row is None:row={'round':engine.round_no,'round_started':engine.round_start_seconds,'used':0}
 row['used']+=1
 c.spec[OPPORTUNITY_USES]=row
 return row['used']


def opportunity(engine,attacker,mover,run):
 """turn.trigger_aoo: scope the actual Attack of Opportunity so its hit can be recorded for Don't Look Away."""
 previous=getattr(engine,'_hunter_aoo_scope',None)
 engine._hunter_aoo_scope={'attacker_id':attacker.entity_id,'mover_id':mover.entity_id}
 try:return run()
 finally:
  if previous is None:del engine._hunter_aoo_scope
  else:engine._hunter_aoo_scope=previous


def _is_opportunity(engine,attacker,target,move):
 scope=getattr(engine,'_hunter_aoo_scope',None)
 return bool(scope and move.get('id')=='struggle' and scope['attacker_id']==getattr(attacker,'entity_id',None) and scope['mover_id']==getattr(target,'entity_id',None))


# ---------------------------------------------------------------- Teamwork and Pack Master accuracy/damage consumers
def teamwork_bonus(engine,attacker,target,move):
 """Teamwork (+2): an ally's melee attack against a foe adjacent to the holder; the Hunter's own attacks count as adjacent
 for their Pokemon's Teamwork (Hunter's Reflexes); any ally attack counts for a Pack Master Hunter or their Pokemon."""
 import world_entities as W
 if getattr(attacker,'kind',None) not in ('trainer','pokemon') or getattr(target,'kind',None) not in ('trainer','pokemon'):return 0
 if getattr(attacker,'side',None) is None or getattr(target,'side',None) is None or attacker.side==target.side:return 0
 index=W.actor_index(engine)
 if index.get(attacker.entity_id) is not attacker or index.get(target.entity_id) is not target:return 0
 melee=_melee(move)
 reflexes=covered(engine,attacker,REFLEXES) if attacker.kind=='trainer' else None
 for holder in index.values():
  if holder is attacker or holder is target or getattr(holder,'side',None)!=attacker.side or not _present(holder) or not _ability(holder,TEAMWORK):continue
  if not engine.adjacent(holder,target):continue
  if melee:return TEAMWORK_RULE['accuracy']
  if reflexes is not None and _owned_by(engine,holder,reflexes,index):return TEAMWORK_RULE['accuracy']
  if covered(engine,holder,PACK_MASTER) is not None:return TEAMWORK_RULE['accuracy']
 return 0


def pack_master_records(actor,foe=None):
 import combat_timing as T
 rows=[]
 for r in T.records(actor):
  p=r.get(PACK_MASTER_KEY)
  if p is None:continue
  if type(p) is not dict or set(p)!={'foe_id','accuracy','damage','owner_id','use_id','acquisition','clause_id'} or p['clause_id']!=clause(PACK_MASTER):raise ValueError('invalid Pack Master bonus record')
  if foe is None or p['foe_id']==foe.entity_id:rows.append(r)
 return rows


def pack_master_bonus(engine,attacker,target,kind):
 if getattr(attacker,'kind',None) not in ('trainer','pokemon') or getattr(target,'entity_id',None) is None:return 0
 return sum(r[PACK_MASTER_KEY][kind] for r in pack_master_records(attacker,target))


def accuracy(engine,attacker,target,move,mm):
 """Engine accuracy hook: Teamwork and the Pack Master per-foe bonus."""
 return teamwork_bonus(engine,attacker,target,move)+pack_master_bonus(engine,attacker,target,'accuracy')


def damage_bonus(engine,attacker,target,move):
 """Engine damage-roll hook: the Pack Master per-foe bonus."""
 return pack_master_bonus(engine,attacker,target,'damage')


def _pack_master_buff(engine,attacker,foe,trainer,use_id):
 """Replace (never stack) this attacker's Pack Master bonus against the foe: until the end of the attacker's next turn."""
 import combat_timing as T
 for r in pack_master_records(attacker,foe):T.expire(engine,attacker,r,ending='replaced')
 record={'source':PACK_MASTER,PACK_MASTER_KEY:{'foe_id':foe.entity_id,'accuracy':PACK_MASTER_RULE['accuracy'],'damage':PACK_MASTER_RULE['damage'],
  'owner_id':trainer.entity_id,'use_id':use_id,'acquisition':acquired(trainer,PACK_MASTER)['request_id'],'clause_id':clause(PACK_MASTER)},
  'turn_owner':attacker,'turn_deadline':attacker.custom_conditions.get('combat_turn_serial',0)+1,'encounter_end':True}
 T.install(engine,attacker,record)
 engine.log('  '+attacker.name+': 무리 주인 — '+foe.name+' 상대 명중 +2 / 데미지 +5 (다음 턴 종료까지)',PACK_MASTER)
 return record


# ---------------------------------------------------------------- Pack Hunt (Ability consumer) and its trigger producer
def pack_hunt_trigger(holder):
 row=holder.spec.get(PACK_HUNT_TRIGGER)
 if row is None:return None
 if type(row) is not dict or set(row)!={'round','at','ally_id','foe_id','move_id','melee','reflexes'}:raise ValueError('invalid Pack Hunt trigger record')
 return row


def after_damage(engine,attacker,target,move,dealt):
 """Engine hit producer: an ally's melee attack damaged a foe; every adjacent Pack Hunt holder may answer.
 The Hunter's own attacks count as melee for their Pokemon's Pack Hunt (Hunter's Reflexes)."""
 import world_entities as W
 if type(dealt) is not int or dealt<=0 or getattr(attacker,'kind',None) not in ('trainer','pokemon') or getattr(target,'kind',None) not in ('trainer','pokemon'):return
 if getattr(attacker,'side',None) is None or getattr(target,'side',None) is None or attacker.side==target.side:return
 index=W.actor_index(engine)
 if index.get(attacker.entity_id) is not attacker or index.get(target.entity_id) is not target:return
 melee=_melee(move)
 reflexes=covered(engine,attacker,REFLEXES) if attacker.kind=='trainer' else None
 for holder in index.values():
  if holder is attacker or holder is target or getattr(holder,'side',None)!=attacker.side or not _present(holder) or not _ability(holder,PACK_HUNT):continue
  if not engine.adjacent(holder,target):continue
  counted_melee=melee or (reflexes is not None and _owned_by(engine,holder,reflexes,index))
  if not counted_melee:continue
  holder.spec[PACK_HUNT_TRIGGER]={'round':engine.round_no,'at':engine.elapsed_seconds,'ally_id':attacker.entity_id,'foe_id':target.entity_id,
   'move_id':move.get('id'),'melee':melee,'reflexes':bool(not melee)}
  engine.log('  '+holder.name+': 무리사냥 발동 가능 ('+attacker.name+'의 근접 피해 → '+target.name+')',PACK_HUNT)


def pack_hunt(engine,holder):
 """Triggered Free Action: the AC 5 physical attack against the foe; a hit costs it a Tick of HP (Pack Master bonus follows)."""
 import world_entities as W
 W.require_actors(engine,holder)
 if not _ability(holder,PACK_HUNT):raise ValueError('actual Pack Hunt Ability required')
 record=pack_hunt_trigger(holder)
 if record is None:raise ValueError('Pack Hunt requires its actual printed trigger: an ally damaged an adjacent foe with a melee attack')
 if record['round']!=engine.round_no or record['at']!=engine.elapsed_seconds:raise ValueError('Pack Hunt trigger lapsed')
 index=W.actor_index(engine)
 foe=index.get(record['foe_id'])
 if foe is None or not _present(foe) or getattr(foe,'side',None) is None or getattr(holder,'side',None) is None or foe.side==holder.side:raise ValueError('Pack Hunt foe is no longer an actual target')
 if not engine.adjacent(holder,foe):raise ValueError('Pack Hunt attack requires the adjacent foe')
 def apply(e,h,f):
  import action_lifecycle as A
  A.triggered_free_action(e,h,PACK_HUNT)
  move=deepcopy(PACK_HUNT_RULE['move'])
  hit,natural,_=e.accuracy_check(h,f,move)
  before=f.hp;temp_before=f.temp_hp
  if hit:e.lose_tick_hp(f,PACK_HUNT_RULE['hp_loss_ticks'],source=PACK_HUNT)
  use_id=PACK_HUNT+':'+h.entity_id+':'+str(len(_history(h,PACK_HUNT_HISTORY))+1)
  receipt={'id':use_id,'trigger':deepcopy(record),'round':e.round_no,'at':e.elapsed_seconds,'foe_id':f.entity_id,'hit':bool(hit),'natural':natural,
   'hp_before':before,'hp_after':f.hp,'temp_before':temp_before,'temp_after':f.temp_hp,'pack_master':None}
  trainer=covered(e,h,PACK_MASTER)
  if hit and trainer is not None:receipt['pack_master']=_pack_master_buff(e,h,f,trainer,use_id)[PACK_MASTER_KEY]['use_id']
  h.spec.pop(PACK_HUNT_TRIGGER)
  h.spec.setdefault(PACK_HUNT_HISTORY,[]).append(receipt)
  e.log('  '+h.name+': 무리사냥 AC5 물리 공격 → '+f.name+(' 명중 (소량 체력 손실)' if hit else ' 빗나감'),PACK_HUNT)
  return deepcopy(receipt)
 return G.transition(engine,holder,apply,participants=(foe,),include_rulings=True)


# ---------------------------------------------------------------- Surprise!
def armed_surprise(trainer):
 row=trainer.spec.get(SURPRISE_ARMED)
 if row is None:return None
 if type(row) is not dict or set(row)!={'target_id','acquisition','clause_id','armed_at'} or row['clause_id']!=clause(SURPRISE):raise ValueError('invalid Surprise! arming receipt')
 return row


def arm_surprise(engine,trainer,target):
 """Accept the next eligible Surprise! trigger against one foe; spends nothing yet."""
 import world_entities as W
 require(engine,trainer,SURPRISE)
 W.require_actors(engine,trainer,target)
 if target is trainer or getattr(target,'kind',None) not in ('trainer','pokemon') or target.side==trainer.side:raise ValueError('Surprise! must name an actual foe')
 def apply(e,t,q):
  t.spec[SURPRISE_ARMED]={'target_id':q.entity_id,'acquisition':acquired(t,SURPRISE)['request_id'],'clause_id':clause(SURPRISE),'armed_at':e.elapsed_seconds}
  return deepcopy(t.spec[SURPRISE_ARMED])
 return G.transition(engine,trainer,apply,participants=(target,))


def disarm_surprise(engine,trainer):
 import world_entities as W
 W.require_actors(engine,trainer)
 if armed_surprise(trainer) is None:raise ValueError('actual armed Surprise! required')
 def apply(e,t):
  t.spec.pop(SURPRISE_ARMED);return True
 return G.transition(engine,trainer,apply)


def _surprise_key(target):
 return SURPRISE+':'+target.entity_id


def surprise_cost(move):
 """1 AP for a Poke Ball, Hand Net, Weighted Net, Glue Cannon or Struggle Attack; otherwise 2 AP."""
 if move.get('id') in SURPRISE_RULE['discount_move_ids']:return SURPRISE_RULE['ap']['discount']
 if move.get('_weapon_attack',{}).get('source') in SURPRISE_RULE['discount_item_ids']:return SURPRISE_RULE['ap']['discount']
 return SURPRISE_RULE['ap']['full']


def surprise_trigger(engine,trainer,target):
 """The printed trigger: the foe does not anticipate the attack (explicit observation) or is adjacent to the Hunter's
 Pokemon with Pack Hunt or Teamwork. Never a default."""
 import world_entities as W
 index=W.actor_index(engine)
 for p in index.values():
  if p is target or not _owned_by(engine,p,trainer,index) or not _present(p):continue
  if (_ability(p,PACK_HUNT) or _ability(p,TEAMWORK)) and engine.adjacent(p,target):return {'basis':'pack_adjacent','pokemon_id':p.entity_id}
 answer=engine.rulings.decide({'type':SURPRISE_PROMPT,'unit':SURPRISE,'actor':trainer.name,'target':target.name,'text':'Does the actual target fail to anticipate this attack?'})
 if answer is True:return {'basis':'unaware'}
 return None


def surprise_ready(engine,attacker,target,move,*,shared_roll=None):
 """The arming when the Trainer's actual attack on the armed foe can pay Surprise! now (read-only)."""
 import world_entities as W,action_points as AP,frequency as F,turn as TURN,action_lifecycle as A,body_modes as BODY
 if getattr(attacker,'kind',None)!='trainer' or shared_roll is not None:return None
 row=armed_surprise(attacker)
 if row is None or row['target_id']!=getattr(target,'entity_id',None):return None
 index=W.actor_index(engine)
 if index.get(attacker.entity_id) is not attacker or index.get(target.entity_id) is not target:return None
 if covered(engine,attacker,SURPRISE) is None or not any(r['request_id']==row['acquisition'] for r in records(attacker,SURPRISE,True)):return None
 if AP.available(attacker)<surprise_cost(move):return None
 if not F.activation_allowed(attacker,_surprise_key(target),SURPRISE_QUOTA,engine=engine):return None
 if not TURN.can_act(engine,attacker) or not A.status_permission(engine,attacker,'swift',new_action=True) or not BODY.permits(attacker,'swift'):return None
 trigger=surprise_trigger(engine,attacker,target)
 if trigger is None:return None
 return dict(row,trigger=trigger,cost=surprise_cost(move))


def accuracy_face(engine,attacker,target,move,mm,face,*,modifier,ac,evasion,automatic,cannot_hit,ac_rule,shared_roll=None):
 """Engine accuracy hook: pay the armed Surprise! at the actual roll, roll the second die and keep the better result."""
 plan=surprise_ready(engine,attacker,target,move,shared_roll=shared_roll)
 if plan is None:return face
 import turn as TURN,action_points as AP,frequency as F,combat_hit as HIT
 if not TURN.spend(engine,attacker,SURPRISE_RULE['action'],SURPRISE):
  engine.log('  '+attacker.name+': 서프라이즈! 신속 행동 불가 → 발동 없음',SURPRISE)
  return face
 AP.spend(attacker,plan['cost'])
 F.consume_activation(attacker,_surprise_key(target),SURPRISE_QUOTA,engine=engine)
 second=engine.d20()
 results=[HIT.resolve(natural=n,modifier=modifier,accuracy=ac,evasion=evasion,automatic=automatic,cannot_hit=cannot_hit or None,
  auto_miss_natural=ac_rule['auto_miss_natural'],auto_hit_natural=ac_rule['auto_hit_natural'])['hit'] for n in (face,second)]
 chosen=face if results[0] and not results[1] else second if results[1] and not results[0] else max(face,second)
 use_id=SURPRISE+':'+attacker.entity_id+':'+str(len(_history(attacker,SURPRISE_HISTORY))+1)
 receipt={'id':use_id,'target_id':target.entity_id,'move_id':move.get('id'),'cost':plan['cost'],'trigger':plan['trigger'],'faces':[face,second],'results':results,
  'chosen':chosen,'both_hit':all(results),'round':engine.round_no,'at':engine.elapsed_seconds,'scene':F.state(attacker)['scene'],'acquisition':plan['acquisition'],'clause_id':clause(SURPRISE)}
 attacker.spec.pop(SURPRISE_ARMED)
 attacker.spec.setdefault(SURPRISE_HISTORY,[]).append(receipt)
 engine._hunter_surprise_scope={'trainer':attacker,'target':target,'use_id':use_id,'both_hit':all(results)}
 engine.log('  '+attacker.name+': 서프라이즈! ('+str(plan['cost'])+' AP, 신속 행동) 명중 주사위 '+str(face)+'/'+str(second)+' → '+str(chosen)+(' (둘 다 명중)' if all(results) else ''),SURPRISE)
 return chosen


def _record_look_away(engine,attacker,target):
 """An actual Attack of Opportunity hit by the Hunter or their Pokemon with Pack Hunt or Teamwork."""
 if attacker.kind=='trainer':trainer=covered(engine,attacker,LOOK_AWAY)
 elif _ability(attacker,PACK_HUNT) or _ability(attacker,TEAMWORK):trainer=covered(engine,attacker,LOOK_AWAY)
 else:trainer=None
 if trainer is None:return
 trainer.spec[LOOK_AWAY_TRIGGER]={'round':engine.round_no,'at':engine.elapsed_seconds,'attacker_id':attacker.entity_id,'target_id':target.entity_id,
  'acquisition':acquired(trainer,LOOK_AWAY)['request_id'],'clause_id':clause(LOOK_AWAY)}
 engine.log('  '+trainer.name+': 기회 공격 적중 → 한눈 팔지 마 발동 가능',LOOK_AWAY)


def after_accuracy(engine,attacker,target,move,natural,hit):
 """Engine accuracy hook after the result: Surprise! Flinch when both dice hit; Attack of Opportunity hits for Don't Look Away."""
 scope=getattr(engine,'_hunter_surprise_scope',None)
 if scope is not None and scope['trainer'] is attacker and scope['target'] is target:
  del engine._hunter_surprise_scope
  if scope['both_hit'] and hit:engine.apply_status(target,SURPRISE_RULE['flinch'],source=SURPRISE,applied_by=attacker)
 if hit and _is_opportunity(engine,attacker,target,move):_record_look_away(engine,attacker,target)


# ---------------------------------------------------------------- Don't Look Away
def look_away_trigger(trainer):
 row=trainer.spec.get(LOOK_AWAY_TRIGGER)
 if row is None:return None
 if type(row) is not dict or set(row)!={'round','at','attacker_id','target_id','acquisition','clause_id'} or row['clause_id']!=clause(LOOK_AWAY):raise ValueError('invalid Don\'t Look Away trigger record')
 return row


def _timed(engine,c,source,**payload):
 import combat_timing as T
 record={'source':source,**payload,'encounter_end':True}
 record['count_deadline']=(engine.round_no+1,T.current(engine))
 return T.install(engine,c,record)


def dont_look_away(engine,trainer):
 """1 AP triggered Free Action, once per round: the foe hit by the Attack of Opportunity loses a Tick and is Slowed for one round."""
 import world_entities as W,action_points as AP
 require(engine,trainer,LOOK_AWAY)
 record=look_away_trigger(trainer)
 if record is None:raise ValueError('Don\'t Look Away requires its actual printed trigger: an Attack of Opportunity hit')
 if record['round']!=engine.round_no or record['at']!=engine.elapsed_seconds:raise ValueError('Don\'t Look Away trigger lapsed')
 if any(r.get('round')==engine.round_no and r.get('round_started')==engine.round_start_seconds for r in _history(trainer,LOOK_AWAY_HISTORY)):
  raise ValueError('Don\'t Look Away was already triggered this round')
 if AP.available(trainer)<LOOK_AWAY_RULE['ap']:raise ValueError('Don\'t Look Away requires 1 AP')
 index=W.actor_index(engine)
 foe=index.get(record['target_id'])
 if foe is None or getattr(foe,'kind',None) not in ('trainer','pokemon') or foe.side==trainer.side:raise ValueError('Don\'t Look Away foe is no longer an actual target')
 def apply(e,t,f):
  import action_lifecycle as A
  A.triggered_free_action(e,t,LOOK_AWAY)
  AP.spend(t,LOOK_AWAY_RULE['ap'])
  before=f.hp;temp_before=f.temp_hp
  e.lose_tick_hp(f,LOOK_AWAY_RULE['hp_loss_ticks'],source=LOOK_AWAY)
  timed=_timed(e,f,LOOK_AWAY,statuses=[LOOK_AWAY_RULE['status']])
  use_id=LOOK_AWAY+':'+t.entity_id+':'+str(len(_history(t,LOOK_AWAY_HISTORY))+1)
  receipt={'id':use_id,'trigger':deepcopy(record),'round':e.round_no,'round_started':e.round_start_seconds,'at':e.elapsed_seconds,'foe_id':f.entity_id,
   'hp_before':before,'hp_after':f.hp,'temp_before':temp_before,'temp_after':f.temp_hp,'slowed':LOOK_AWAY_RULE['status'] in f.conditions,
   'count_deadline':list(timed['count_deadline']),'acquisition':record['acquisition'],'clause_id':clause(LOOK_AWAY)}
  t.spec.pop(LOOK_AWAY_TRIGGER)
  t.spec.setdefault(LOOK_AWAY_HISTORY,[]).append(receipt)
  e.log('  '+t.name+': 한눈 팔지 마 (1 AP, 자유 행동) → '+f.name+' 소량 체력 손실, 1라운드 둔화',LOOK_AWAY)
  return deepcopy(receipt)
 return G.transition(engine,trainer,apply,participants=(foe,),include_rulings=True)


# ---------------------------------------------------------------- lifecycle hooks
def withdraw(engine,trainer,rule_id):
 """Retraining a Hunter source ends what it alone justified."""
 if rule_id not in FEATURES:return
 import world_entities as W,combat_timing as T
 index=W.actor_index(engine)
 if rule_id in (CLASS,SURPRISE):trainer.spec.pop(SURPRISE_ARMED,None)
 if rule_id in (CLASS,LOOK_AWAY):trainer.spec.pop(LOOK_AWAY_TRIGGER,None)
 if rule_id in (CLASS,PACK_MASTER):
  for c in index.values():
   for r in pack_master_records(c):
    if r[PACK_MASTER_KEY]['owner_id']==trainer.entity_id:T.expire(engine,c,r,ending='withdrawn')


# ---------------------------------------------------------------- validation
def validate(engine):
 import world_entities as W,trainer_feature_acquisition as T,ability_transitions as A
 index=W.actor_index(engine)
 for actor in index.values():
  if actor.kind=='trainer':
   for sid,row,live in T._static_records(actor):
    record=row['static_acquisition']
    if not live or record['feature_id'] not in FEATURES:continue
    operation=actor.spec.get(G.KEY,{}).get('stat_sources',{}).get(STAT_TAG,{}).get('sources',{}).get(sid,{}).get('acquisition_stat_tag')
    if record['feature_id']!=TACTICS and operation!={'delta':1,'minimum':None}:raise ValueError('actual source-owned Hunter Speed stat tag required')
    if record['feature_id']==CLASS:
     granted=row.get('grants',{}).get('abilities',[])
     if [A.ability_id(engine.r,x) for x in granted]!=[record['snapshot']['branch']]:raise ValueError('Hunter class Ability grant disagrees with the acquired choice')
   armed=armed_surprise(actor)
   if armed is not None:
    if acquired(actor,SURPRISE) is None or not any(r['request_id']==armed['acquisition'] for r in records(actor,SURPRISE)):raise ValueError('Surprise! arming lost its acquisition')
    if armed['target_id'] not in index:raise ValueError('Surprise! arming names a missing foe')
   trigger=look_away_trigger(actor)
   if trigger is not None and acquired(actor,LOOK_AWAY) is None:raise ValueError('Don\'t Look Away trigger lost its acquisition')
   for row in _history(actor,SURPRISE_HISTORY):
    if type(row) is not dict or row.get('clause_id')!=clause(SURPRISE):raise ValueError('invalid Surprise! history')
   for row in _history(actor,LOOK_AWAY_HISTORY):
    if type(row) is not dict or row.get('clause_id')!=clause(LOOK_AWAY):raise ValueError('invalid Don\'t Look Away history')
  elif any(key in actor.spec for key in (SURPRISE_ARMED,SURPRISE_HISTORY,LOOK_AWAY_TRIGGER,LOOK_AWAY_HISTORY)):raise ValueError('Hunter Trainer state on a non-Trainer')
  if OPPORTUNITY_USES in actor.spec:_opportunity_row(engine,actor)
  pending=pack_hunt_trigger(actor)
  if pending is not None and not _ability(actor,PACK_HUNT):raise ValueError('Pack Hunt trigger without the actual Ability')
  for row in _history(actor,PACK_HUNT_HISTORY):
   if type(row) is not dict or 'trigger' not in row:raise ValueError('invalid Pack Hunt history')
  for r in pack_master_records(actor):
   owner=index.get(r[PACK_MASTER_KEY]['owner_id'])
   if owner is None or owner.kind!='trainer' or covered(engine,actor,PACK_MASTER) is not owner:raise ValueError('Pack Master bonus lost its Hunter owner')
   if not any(x['request_id']==r[PACK_MASTER_KEY]['acquisition'] for x in records(owner,PACK_MASTER)):raise ValueError('Pack Master bonus provenance changed')
 return True
