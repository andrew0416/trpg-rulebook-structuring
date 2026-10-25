"""Rogue's seven independent acquisitions and source-specific hit consumers."""
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
from hashlib import sha256
import common_checks as C
import state_grants as G
import combat_timing as T
import frequency as F
import move_completion as MC

CLASS='class/로그'
CUT='feat/극악무도'
DIRTY='feat/치사한-싸움'
UNEXPECTED='feat/불시의-공격'
UNDERHAND='feat/음흉한-작전'
STREET='feat/거리의-싸움꾼'
STRIKE='feat/악당의-타격'
AMBUSH='ability/매복'
PLAYTEST='ability/매복-playtest'
CRUELTY='ability/잔인'
ABILITIES=(AMBUSH,PLAYTEST,CRUELTY)
SKILLS=__import__('class_move_grants').SKILL_DOMAINS[CLASS]
SOURCE_SHA256='a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'
DEFINITIONS={
 CLASS:{'span':(2604,2606),'catalog_span':(2595,2595),'parents':[],'rank':3,'count':2},
 CUT:{'span':(2608,2612),'parents':[CLASS],'rank':0,'count':0},
 DIRTY:{'span':(2614,2619),'parents':[CLASS],'rank':4,'count':1},
 UNEXPECTED:{'span':(2621,2625),'parents':[CLASS],'rank':4,'count':2},
 UNDERHAND:{'span':(2627,2631),'parents':[CLASS],'rank':5,'count':1,'choices':ABILITIES},
 STREET:{'span':(2633,2637),'parents':[UNEXPECTED],'rank':5,'count':2},
 STRIKE:{'span':(2639,2646),'parents':[UNDERHAND,STREET],'rank':0,'count':0}}
FEATURES={u:d['span'] for u,d in DEFINITIONS.items()}
MOVES=('move/속여때리기','move/도둑질','move/따라가때리기','move/기습','move/승부굳히기','move/보복')
WEAPONS=('소형 근접무기','단거리 사격무기')


def records(a,feature,active=False):
 import trainer_feature_acquisition as A
 return [record for _, record in A.static_acquisitions(a, feature, active=active)]


def owns(a,feature):
 return a.kind=='trainer' and bool(__import__('acquired_features').owned_rule_count(a,feature))


def acquired(a,feature):
 if not owns(a,feature):return None
 __import__('trainer_feature_acquisition').validate_actor(a)
 rows=records(a,feature,True)
 if len(rows)!=1:raise ValueError('one actual Rogue Feature acquisition required: '+feature)
 if any(not owns(a,parent) for parent in DEFINITIONS[feature]['parents']):raise ValueError('actual acquired Rogue prerequisite required')
 return rows[0]


def acquisition_snapshot(e,a,feature,branch=None):
 d=DEFINITIONS[feature]
 if feature==UNDERHAND:
  if branch not in ABILITIES:raise ValueError('choose Core Ambush, Playtest Ambush, or Cruelty explicitly')
  if owns(a,feature):raise ValueError('Underhanded Tactics has one Ability choice')
 elif branch is not None:raise ValueError('this Rogue Feature has no selection')
 parents={}
 for parent in d['parents']:
  row=acquired(a,parent)
  if row is None:raise ValueError('actual Rogue prerequisite required: '+parent)
  parents[parent]=row['request_id']
 result={'parents':parents,'ranks':{skill:__import__('skill_modifiers').rank(e.r,a,skill)[2] for skill in SKILLS}}
 if feature==UNDERHAND:result['branch']=branch
 return result


def qualification(a,feature,snapshot,prerequisite_source):
 import acquisition_qualification as Q
 d=DEFINITIONS[feature]
 fields={'parents','ranks'}|({'branch'} if feature==UNDERHAND else set())
 if prerequisite_source is not None or type(snapshot) is not dict or set(snapshot)!=fields or set(snapshot['parents'])!=set(d['parents']) or set(snapshot['ranks'])!=set(SKILLS):raise ValueError('exact Rogue acquisition observations required')
 for parent,request in snapshot['parents'].items():
  if not any(row['request_id']==request for row in records(a,parent)):raise ValueError('actual historical Rogue prerequisite required')
 for rank in snapshot['ranks'].values():C.integer(rank,'Rogue skill rank',0)
 if feature==UNDERHAND and snapshot['branch'] not in ABILITIES:raise ValueError('printed Rogue Ability choice required')
 return Q.require(feature,'native','acquire',[
  Q.check('trainer','prerequisite',a.kind=='trainer','actual trainer required'),
  Q.check('rogue_skills','prerequisite',sum(v>=d['rank'] for v in snapshot['ranks'].values())>=d['count'],'printed Rogue skill ranks required')])


def after_acquire(e,a,feature,sid,branch=None):
 if feature not in (UNEXPECTED,STREET):G.stat(a,'atk',1,sid,operation_id='acquisition_stat_tag')
 if feature==CLASS:__import__('class_move_grants').register_all(e,a)
 if feature in (CLASS,UNEXPECTED,STREET):__import__('items').register_feats(e,a)
 if feature==UNDERHAND:
  label={AMBUSH:'매복',PLAYTEST:'매복 [Playtest]',CRUELTY:'잔인'}[branch]
  if e.r.selection.resolve_name(label,('ability/',))!=branch:raise ValueError('selected Rogue Ability identity differs from acquisition')
  G.grant(a,'abilities',label,sid,'feature',owner_id=a.entity_id,lifetime='while_owned',rule_id=feature,tutor_points=0)
  e.register_abilities_one(a,label)


def rank(e,a):return max(__import__('skill_modifiers').rank(e.r,a,skill)[2] for skill in SKILLS)


def cutthroat(e,a,weapon):
 if weapon.get('kind') not in WEAPONS or not owns(a,CUT):return False
 if e.r._selected_rule(CUT)!=CUT:raise ValueError('selected Cutthroat needs its source adapter')
 return acquired(a,CUT) is not None


def weapon_move(e,a,move,weapon_id):
 """Optional conversion needs the actual selected equipped physical weapon."""
 prior=move.get('_rogue_cutthroat')
 if prior is None and (weapon_id is None or move.get('id') not in MOVES or not owns(a,CUT)):return None
 if move.get('id') not in MOVES:raise ValueError('Cutthroat requires an actual Rogue Move')
 key=prior['weapon'] if prior is not None else weapon_id
 candidates=[(k,row) for k,row in a.custom_conditions.get('equipped_weapons',{}).items() if key in (k,row['weapon']['name'],row.get('instance_id'))]
 if len(candidates)!=1:raise ValueError('choose one actual equipped Cutthroat weapon')
 key,row=candidates[0];weapon=row['weapon']
 if prior is not None and weapon_id not in (None,key,weapon['name'],row.get('instance_id')):raise ValueError('prepared Cutthroat weapon choice cannot be changed')
 if not cutthroat(e,a,weapon):raise ValueError('Cutthroat requires Small Melee or Short Ranged weapon')
 import move_state as MS,living_weapon as LW,wielder_capability as W,weapon_actions as WA,turn as TURN
 if move['id'] not in __import__('move_capabilities').learned_ids(a):raise ValueError('Cutthroat requires an actually learned Rogue Move')
 if not LW.require_weapon(e,a,weapon):W.require_weapon(e,a,weapon)
 raw=deepcopy(move)
 keywords=[word.strip() for word in move.get('range','').split(',') if any(key in word for key in ('우선','방해','발동조건','반응'))]
 raw['range']='WR, 대상 1'+(' , '+', '.join(keywords) if keywords else '')
 out=WA.adapt_weapon_move(e,a,raw,key,weapon)
 out['_rogue_cutthroat']={'source':CUT,'weapon':key}
 return out


def disarm_skills(e,a,item_name):
 if not owns(a,CUT):return set()
 import turn as TURN
 chosen=TURN.disarm_equipment(e,a,item_name)
 if chosen is None or chosen[1]!='weapon':return set()
 row=a.custom_conditions.get('equipped_weapons',{}).get(chosen[0])
 if row is None or not cutthroat(e,a,row['weapon']):return set()
 return {__import__('skill_modifiers').skill_id(e.r.skill_policy,skill,required=True) for skill in SKILLS}


def hit(e,a,t,completion_id,*,weapon=False,resuming=False):
 __import__('world_entities').require_actors(e,a,t)
 row=getattr(e,MC.KEY,{}).get(completion_id)
 if row is None or row['actor'] is not a or row['phase']!='complete' or not row['sealed']:raise ValueError('actual completed Rogue attack required')
 if row['round']!=e.round_no or row['seconds']!=e.elapsed_seconds or row.get('rogue_turn_serial')!=a.custom_conditions.get('combat_turn_serial',0) or row.get('rogue_scene')!=F.state(a)['scene']:raise ValueError('immediate current attack completion required')
 if a.side==t.side:raise ValueError('actual enemy hit required')
 result=MC.recipient_result(row,t)
 if t not in MC.actual_recipients(row) or not result or not result['hit'] or result.get('cancelled') or result.get('hit_prevented'):raise ValueError('actual nonprevented hit recipient required')
 events=[event for event in getattr(e,'_passive_events',{}).values() if event.get('completion_id')==row['id'] and event.get('target') is t]
 if events:
  event=events[-1];MC.require_hit_return(e,event['id'],t);move=MC.event_move(e,event)
 else:move=row.get('target_moves',{}).get(t.entity_id,row['move'])
 if not resuming and row.get('rogue_action_history')!=list(getattr(a,'_action_history',[])):raise ValueError('immediate Rogue follow-up cannot follow another action')
 if weapon:
  if not move.get('_weapon_attack'):raise ValueError('Dirty Fighting requires the actual prepared Weapon Attack')
 elif move['id'] not in MOVES:raise ValueError('Scoundrel Strike requires a Rogue Move')
 return row,move


@contextmanager
def dirty_scope(e,a,t,completion_id):
 if acquired(a,DIRTY) is None:raise ValueError('actual Dirty Fighting acquisition required')
 pending=a.custom_conditions.get(__import__('skill_maneuver_actions').ACTIVE,'')
 row,move=hit(e,a,t,completion_id,weapon=True,resuming=pending.startswith('maneuver/치사한-짓:'))
 context={'actor':a,'target':t,'completion':row['id']}
 previous=getattr(e,'_rogue_dirty',None)
 if previous is not None:raise ValueError('nested Dirty Fighting declaration')
 e._rogue_dirty=context
 try:yield
 finally:del e._rogue_dirty


def dirty_context(e,a,t):
 row=getattr(e,'_rogue_dirty',None)
 return row if row is not None and row['actor'] is a and row['target'] is t else None


def dirty_fighting(e,a,t,completion_id,trick,**options):
 with dirty_scope(e,a,t,completion_id):return e.dirty_trick(a,t,trick,**options)


def dirty_spend(e,a,t,trick):
 import action_points as AP,turn as TURN
 context=dirty_context(e,a,t)
 if context is None:return TURN.spend(e,a,'standard','치사한 짓: '+trick)
 if AP.available(a)<1:raise ValueError('Dirty Fighting requires one available AP')
 row=getattr(e,MC.KEY)[context['completion']]
 if a.entity_id in row.get('rogue_dirty_used',[]):raise ValueError('this attack already triggered Dirty Fighting')
 if not TURN.spend(e,a,'swift',DIRTY):return False
 AP.spend(a,1);row.setdefault('rogue_dirty_used',[]).append(a.entity_id)
 return True


def scoundrel_strike(e,a,t,completion_id,*,ability=None):
 def apply(se,actor,target):
  import ability_transitions as AB,turn as TURN
  if acquired(actor,STRIKE) is None:raise ValueError('actual Scoundrel Strike acquisition required')
  row,move=hit(se,actor,target,completion_id)
  choices=[uid for uid in ABILITIES if uid in AB.known(actor)]
  chosen=ability if ability is not None else choices[0] if len(choices)==1 else None
  if chosen not in choices:raise ValueError('choose an actually possessed Ambush or Cruelty Ability')
  target_key=STRIKE+':'+target.entity_id
  daily={'kind':'daily','uses':3};scene={'kind':'scene','uses':1}
  if not F.activation_allowed(actor,STRIKE,daily,engine=se) or not F.activation_allowed(actor,target_key,scene,engine=se):raise ValueError('Scoundrel Strike frequency exhausted')
  count=T.current(se);amount=2*max(__import__('skill_modifiers').effective_rank(se.r,actor,skill) for skill in SKILLS)
  if not TURN.spend(se,actor,'swift',STRIKE):raise ValueError('Scoundrel Strike requires a Swift action')
  F.consume_activation(actor,STRIKE,daily,engine=se);F.consume_activation(actor,target_key,scene,engine=se)
  se.lose_hp(target,amount,source=STRIKE)
  record={'source':STRIKE,'count_deadline':(se.round_no+1,count),'origin_completion':row['id']}
  if chosen in (AMBUSH,PLAYTEST):record.update(statuses=['둔화'],forbidden_actions=['attack_of_opportunity'],all_roll_modifier=-2)
  else:record['rogue_cruelty']=5
  T.install(se,target,record)
  return {'completion_id':row['id'],'target_id':target.entity_id,'loss':amount,'ability':chosen}
 return G.transition(e,a,apply,participants=(t,),include_rulings=True)


def after_move(e,row):
 """One actual damaging attack per recipient; prevented hits do not trigger."""
 if row['move_id'] in MOVES or row['move'].get('_weapon_attack'):
  actor=row['actor'];row['rogue_turn_serial']=actor.custom_conditions.get('combat_turn_serial',0)
  row['rogue_scene']=F.state(actor)['scene'];row['rogue_action_history']=list(getattr(actor,'_action_history',[]))
 ambush=row.get('rogue_ambush');targets=MC.actual_recipients(row)
 damaging=row['move'].get('class') in ('물리','특수')
 if row.get('rogue_followups_applied'):return
 if not ambush and not (damaging and any(r.get('rogue_cruelty') for target in targets for r in T.records(target))):return
 row['rogue_followups_applied']=True
 for target in targets:
  result=MC.recipient_result(row,target)
  if not result['hit'] or result.get('cancelled') or result.get('hit_prevented'):continue
  if damaging:_cruelty_loss(e,target,origin_completion=row['id'])
  if ambush:
   e.apply_status(target,'풀죽음',applied_by=row['actor'],source=ambush)
   if ambush==PLAYTEST:T.install(e,target,{'source':PLAYTEST,'count_deadline':(e.round_no+1,T.current(e)),'accuracy_modifier':-2})


def _cruelty_loss(e,target,*,origin_completion=None):
 amount=0
 for record in list(T.records(target)):
  loss=record.get('rogue_cruelty',0)
  if loss and (origin_completion is None or record.get('origin_completion')!=origin_completion):
   e.lose_hp(target,loss,source=STRIKE);amount+=loss
 return amount


def after_grapple_attack(e,relation_id,history_index):
 """Consume the signed native grappling Struggle, including a zero-damage hit."""
 import grapple_state as GRAPPLE
 event=GRAPPLE.completed_attack_event(e,relation_id,history_index)
 entry=GRAPPLE._state(e)['relations'][relation_id]['history'][history_index]
 previous=entry.get('attack_followups',{}).get('rogue_cruelty')
 if previous is not None:return deepcopy(previous)
 amount=_cruelty_loss(e,event['target']) if event['result']=='damaging_hit' and not event.get('hit_prevented') else 0
 result={'event_id':event['id'],'hp_loss':amount}
 GRAPPLE.record_attack_followup(e,relation_id,history_index,'rogue_cruelty',result)
 return result


def begin_move(e,row):
 scope=getattr(e,'_rogue_ambush',None)
 if scope and scope['actor'] is row['actor'] and scope['move_id']==row['move_id']:
  row['rogue_ambush']=scope['ability']


def validate_core_ability(rules,row):
 expected={'type':'ambush_priority','maximum_base':6,'range':'melee','on_hit':'flinch'}
 if row.get('id')!=AMBUSH or row.get('name')!='매복' or row.get('native_contract')!=expected:raise ValueError('reviewed Core Ambush definition required')
 source=row['source'];official=row['official_source']
 if source['file']!='ch04-trainer-classes.md' or source['lines']!=[2631,2631] or sha256((Path(rules.root)/'input'/source['file']).read_bytes()).hexdigest()!=SOURCE_SHA256:raise ValueError('Rogue Core Ambush reference changed')
 if sha256((Path(rules.root)/official['extract']).read_bytes()).hexdigest()!=official['sha256']:raise ValueError('Core Ambush original source extract changed')


def prepare_ambush(e,a,move,ability):
 import ability_transitions as AB,weapon_actions as WA,initiative_interrupts as I
 if ability not in (AMBUSH,PLAYTEST) or e.r._selected_rule(ability)!=ability or not AB.active(a,ability):raise ValueError('explicit active Core or Playtest Ambush required')
 if move.get('class') not in ('물리','특수') or type(move.get('damage_base')) is not int or move['damage_base']>6:raise ValueError('Ambush requires printed Damage Base 6 or less')
 if ability==AMBUSH and WA.range_spec(e,move,a).get('origin')!='melee':raise ValueError('Core Ambush requires a Melee Move')
 if ability==PLAYTEST:T.current(e)
 _,_,due=I._loan_location(e,a)
 if due!=e.round_no:raise ValueError('Ambush Priority requires an unacted current round turn')
 if not F.activation_allowed(a,ability,{'kind':'scene','uses':1},engine=e):raise ValueError('Ambush scene frequency exhausted')
 return ability


def prepare_move(e,actor,move):
 scope=getattr(e,'_rogue_ambush',None)
 if not scope or scope['actor'] is not actor or scope['move_id']!=move['id']:return move
 out=deepcopy(move)
 if '우선' not in out.get('range',''):out['range']=out.get('range','')+', 우선'
 return out
