"""Printed Tumbler adapters; shared acquisition, grants, movement and turn owners hold state."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import state_grants as G
import common_checks as C

CLASS='class/텀블러';AERIAL='feat/공중곡예사';QUICK='feat/빠른-체조';FLIP='feat/열광'
DEATH='feat/위에서-내려온-죽음';REFLEX='feat/빠른-반사신경';BURST='feat/급가속';ACROBAT='edge/곡예사'
ACE='move/제비반환';SPLASH='move/튀어오르기';ACROBATICS='move/애크러뱃';BOUNCE='move/뛰어오르기'
SOURCE_SHA256='a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'
FEATURES={CLASS:(2718,2720),AERIAL:(2722,2726),QUICK:(2728,2733),FLIP:(2735,2743),DEATH:(2745,2749),REFLEX:(2751,2755),BURST:(2757,2762)}
DEFINITIONS={uid:{'span':list(span),'catalog_span':[2709,2709] if uid==CLASS else list(span),
 'clause_id':'C04-105' if uid==BURST else 'input/ch04-trainer-classes.md:'+str(span[0])+'-'+str(span[1]),
 'stat_tag':'spe','parent':ACROBAT if uid==CLASS else AERIAL if uid in (FLIP,DEATH) else CLASS,
 'minimum_rank':6 if uid==BURST else 5 if uid in (DEATH,REFLEX) else 4 if uid==FLIP else 3 if uid==CLASS else 0}
 for uid,span in FEATURES.items()}

def records(actor,feature=None,active=False):
 import trainer_feature_acquisition as T
 return [record for _, record in T.static_family_acquisitions(actor, FEATURES, feature, active=active)]

def acquired(actor,feature):
 rows=records(actor,feature,True)
 if len(rows)>1:raise ValueError('one actual Tumbler acquisition required')
 return rows[0] if rows else None

def acquisition_snapshot(e,actor,feature):
 import skill_modifiers as SK,acquired_features as A
 return {'rank':SK.rank(e.r,actor,'곡예')[2],'acrobat':A.owned_rule_count(actor,ACROBAT),
  'parents':[r['request_id'] for r in records(actor,DEFINITIONS[feature]['parent'],True)],
  'features':[r['request_id'] for r in records(actor,active=True)]}

def qualification(actor,feature,snapshot,prerequisite_source):
 import acquisition_qualification as Q
 if prerequisite_source is not None or type(snapshot)is not dict or set(snapshot)!={'rank','acrobat','parents','features'}:
  raise ValueError('exact Tumbler acquisition observations required')
 C.integer(snapshot['rank'],'Acrobatics skill rank',1);C.integer(snapshot['acrobat'],'Acrobat ownership',0,1)
 d=DEFINITIONS[feature];known={r['request_id'] for r in records(actor,d['parent'])}
 all_known={r['request_id'] for r in records(actor)}
 if len(snapshot['features'])!=len(set(snapshot['features'])) or not set(snapshot['features'])<=all_known:raise ValueError('distinct actual Tumbler Feature receipts required')
 checks=[Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),
 Q.check('parent','prerequisite',snapshot['acrobat']==1 if feature==CLASS else bool(snapshot['parents']) and set(snapshot['parents'])<=known,'actual acquired prerequisite '+d['parent']+' required'),
 Q.check('rank','prerequisite',snapshot['rank']>=d['minimum_rank'],'printed Acrobatics rank required')]
 if feature==BURST:checks.append(Q.check('features','prerequisite',len(snapshot['features'])>=5,'five distinct Tumbler Features required'))
 return Q.require(feature,'native','acquire',checks)

def after_acquire(e,actor,feature,sid):
 if feature!=DEATH:G.stat(actor,'spe',1,sid,operation_id='acquisition_stat_tag')
 if feature==AERIAL:G.grant_moves(actor,[ACE,SPLASH],sid,'feature',owner_id=actor.entity_id,lifetime='while_owned',rule_id=feature,tutor_points=0)
 if feature==DEATH:
  import class_move_grants as MOVES,static_feature_state_grants as STATIC
  MOVES.register_all(e,actor);STATIC.register_all(e,actor)
 if feature in (CLASS,REFLEX):
  uid=e.r._selected_rule('ability/도주' if feature==CLASS else 'ability/회피')
  if uid not in (('ability/도주','ability/도주-playtest') if feature==CLASS else ('ability/회피',)):raise ValueError('selected Tumbler Ability needs its reviewed contract')
  name=e.r.selection.units[uid]['title'];G.grant(actor,'abilities',name,sid,'feature',owner_id=actor.entity_id,lifetime='while_owned',rule_id=feature)
  G.ensure_ability(e,actor,name)

def validate_core_ability(rules,row):
 expected={'type':'movement_immunity','statuses':['둔화','구속','수렁'],'shift_aoo':False}
 if row.get('id')!='ability/도주' or row.get('name')!='도주' or row.get('native_contract')!=expected:raise ValueError('exact core Run Away contract required')
 source=row['source'];official=row['official_source']
 if source.get('file')!='ch04-trainer-classes.md' or source.get('lines')!=[2719,2719] or source.get('sha256')!=SOURCE_SHA256:raise ValueError('core Run Away Tumbler reference changed')
 from source_context import verified_source
 verified_source(rules,{'file':'input/ch04-trainer-classes.md','sha256':SOURCE_SHA256},label='Tumbler Run Away')
 if official.get('extract')!='source-audit/core-run-away.txt' or source.get('additional_snapshots')!={official['extract']:official['sha256']}:raise ValueError('core Run Away auxiliary source changed')
 verified_source(rules,{'file':official['extract'],'sha256':official['sha256']},label='core Run Away',source_root='source-audit')


def run_away(actor,condition=None):
 import ability_transitions as AB
 for uid,statuses in (('ability/도주',('둔화','구속','수렁')),('ability/도주-playtest',('수렁',))):
  if uid in actor.r.selection.units and actor.r.selection.units[uid]['title'] in actor.abilities and AB.active(actor,uid) and (condition is None or condition in statuses):return uid
 return None

def immune(actor):
 import combat_timing as TIME
 return any(r.get('tumbler_quick') for r in TIME.records(actor))

def quick_offer(e,actor,origin):
 """Only native hit, paid jump and standing-up producers call this adapter."""
 if not acquired(actor,QUICK):return None
 import action_points as AP,action_lifecycle as ACTION,combat_timing as TIME
 if AP.available(actor)<1:return None
 choice=e.rulings.decide({'type':'quick_gymnastics','unit':QUICK,'actor':actor.name,'origin':deepcopy(origin),'text':'Quick Gymnastics: spend 1 AP, optionally Shift up to 2 metres?'})
 if choice in (None,False):return None
 if choice is True:choice={'path':[]}
 if type(choice)is not dict or set(choice)!={'path'} or type(choice['path'])is not list:raise ValueError('Quick Gymnastics needs an explicit movement path')
 import movement_actions as M
 path=[M._point(p) for p in choice['path']]
 jump=actor.spec.get('_jump_attempts',{}).get(origin.get('jump_id')) if origin['kind']=='jump' else None
 position=jump['destination'] if jump and not jump.get('failed') else actor.pos
 diagonal=getattr(actor,'_diagonal_steps',0);total=0
 for point in path:
  cost,diagonal=M.step_cost(position,point,diagonal);total+=cost;position=point
 if total>2:raise ValueError('Quick Gymnastics Shift exceeds two metres')
 if origin['kind']=='stand_up':ACTION.record_action(e,actor,'free')
 else:ACTION.triggered_free_action(e,actor,QUICK)
 AP.charge(actor,1)
 record={'source':QUICK,'tumbler_quick':True,'origin':deepcopy(origin),'path':path,'movement':{},
  'turn_owner':actor,'turn_deadline':actor.custom_conditions.get('combat_turn_serial',0)+1,'encounter_end':True}
 TIME.install(e,actor,record)
 return record

def quick_shift(e,actor,record):
 if record is None or record.get('shift_done'):return
 import combat_timing as TIME,movement_actions as M
 if record not in TIME.records(actor):raise ValueError('actual active Quick Gymnastics permission required')
 if record['path']:
  M.follow_paid_path(e,actor,record['path'],mode='land',maximum_distance=2,progress=record['movement'])
  if record['movement'].get('phase') in ('entry_pending','reaction_pending'):return __import__('common_checks').PendingDecision('finish the actual Quick Gymnastics movement effect before its remaining path')
 record['shift_done']=True

def hit(e,actor,target,move,completion_id,hit,passive_event):
 if not acquired(actor,QUICK):return True
 row=getattr(e,'_move_completions',{}).get(completion_id)
 if row is None or row['actor'] is not actor or target not in row['targets'] and not any(r.get('actor_id')==target.entity_id for st in row.get('defense',{}).values() for r in st.get('recipients',[])):raise ValueError('actual native attack completion required')
 if 'tumbler_hit_offer' not in row and hit and actor is not target:
  row['tumbler_hit_offer']=True
  row['tumbler_hit_effect']=quick_offer(e,actor,{'kind':'hit','completion_id':completion_id,'move_id':move['id'],'target_id':target.entity_id})
 result=quick_shift(e,actor,row.get('tumbler_hit_effect'))
 if isinstance(result,__import__('common_checks').PendingDecision):
  import passive_events as P
  event=getattr(e,'_passive_events',{}).get(passive_event)
  if event is None or event['completion_id']!=completion_id or event['actor'] is not actor:raise ValueError('actual original hit continuation required for pending Quick Gymnastics movement')
  return P._pending(e,event,'quick_gymnastics_movement_pending')
 pending=row.pop('tumbler_attack_aoo',None) if hit or len(row['started'])==len(row['targets']) else None
 if pending is not None and not immune(actor):
  import turn as TURN,world_entities as W
  index=W.actor_index(e);TURN.trigger_aoo(e,actor,pending['why'],[index[uid] for uid in pending['enemies']])
 return __import__('turn').can_act(e,actor)

def defer_attack_aoo(e,actor,why):
 if not acquired(actor,QUICK):return False
 import turn as TURN
 actor.spec['_quick_gymnastics_attack_aoo']={'why':why,'enemies':[c.entity_id for c in TURN.adjacent_enemies(e,actor)]}
 return True

def burst_offer(e,actor):
 if not acquired(actor,BURST) or not e.encounter_active or not __import__('turn').can_act(e,actor):return
 import frequency as F,initiative as I,initiative_schedule as S,combat_timing as TIME,action_lifecycle as ACTION
 if not F.activation_allowed(actor,BURST,{'kind':'scene','uses':1},engine=e):return
 value=I.value(e.r,actor,engine=e)
 if value.unresolved:raise ValueError('Burst of Speed needs actual resolved initiative')
 answer=e.rulings.decide({'type':'burst_of_speed','unit':BURST,'actor':actor.name,'initiative':value.value,'text':'Choose an extra turn count at most half your Initiative, or decline.'})
 if answer is None or answer is False:return
 C.integer(answer,'Burst of Speed initiative count')
 if answer>value.value/2 or answer>TIME.current(e):raise ValueError('Burst of Speed count must be no more than half Initiative and still ahead this round')
 ACTION.triggered_free_action(e,actor,BURST)
 S.grant_extra_turn(e,actor,source=BURST,count=answer,initiative=value.value)
 F.consume_activation(actor,BURST,{'kind':'scene','uses':1},engine=e)


def pass_proof(e,actor):
 row=acquired(actor,FLIP)
 if row is None or ACE not in actor.moves:raise ValueError('Flip Out and actual learned Aerial Ace required')
 return {'source':FLIP,'actor_id':actor.entity_id,'request_id':row['request_id'],'round':e.round_no,'no_critical_test':True}

def validate_pass(e,actor_id,proof,round_no):
 import world_entities as W
 actor=W.actor_index(e).get(actor_id)
 if actor is None or proof!=dict(pass_proof(e,actor),round=round_no):raise ValueError('actual acquired Flip Out Pass provenance changed')
 return True

def choose_acrobatics(e,actor,*,activate,reason):
 import world_entities as W
 W.require_actors(e,actor)
 if not acquired(actor,FLIP) or ACROBATICS not in actor.moves:raise ValueError('actual Flip Out and learned Acrobatics required')
 if type(activate)is not bool or not isinstance(reason,str) or not reason.strip():raise ValueError('explicit Acrobatics bonus choice and reason required')
 actor.spec['tumbler_acrobatics_choice']={'activate':activate,'reason':reason,'turn':actor.custom_conditions.get('combat_turn_serial',0),'round':e.round_no}

def project_acrobatics(e,actor,move):
 choice=actor.spec.get('tumbler_acrobatics_choice')
 if move['id']!=ACROBATICS or choice is None:return move
 if not acquired(actor,FLIP) or choice['round']!=e.round_no or choice['turn']!=actor.custom_conditions.get('combat_turn_serial',0):raise ValueError('Acrobatics choice outlived its actual turn')
 return dict(move,_tumbler_acrobatics_bonus=choice['activate'])

def acrobatics_itemless(actor,move):
 return bool(move.get('_tumbler_acrobatics_bonus') and acquired(actor,FLIP))


def begin_move(e,row):
 pending=row['actor'].spec.pop('_quick_gymnastics_attack_aoo',None)
 if pending is not None:row['tumbler_attack_aoo']=pending

def after_move(e,row):
 pending=row.pop('tumbler_attack_aoo',None)
 if pending is not None and not immune(row['actor']):
  import turn as TURN,world_entities as W
  index=W.actor_index(e);TURN.trigger_aoo(e,row['actor'],pending['why'],[index[uid] for uid in pending['enemies']])


def before_maneuver(e,actor,attack,event):
 if not acquired(actor,QUICK) or event.get('tumbler_quick_decided'):return
 import skill_maneuver_actions as SM
 if SM.completed_attack_event(e,actor,attack) is not event:raise ValueError('actual native maneuver accuracy hit required')
 effect=quick_offer(e,actor,{'kind':'maneuver','event_id':event['id'],'source':attack['id']})
 event['tumbler_quick_decided']=True;event['tumbler_quick_effect']=effect

def after_maneuver(e,actor,attack):
 import skill_maneuver_actions as SM
 event=SM.completed_attack_event(e,actor,attack)
 if event is None:return
 if acquired(actor,QUICK) and not event.get('tumbler_quick_decided'):before_maneuver(e,actor,attack,event)
 return quick_shift(e,actor,event.get('tumbler_quick_effect'))


def after_grapple_attack(e,relation_id,history_index):
 import grapple_state as GRAPPLE
 event=GRAPPLE.completed_attack_event(e,relation_id,history_index);entry=GRAPPLE._state(e)['relations'][relation_id]['history'][history_index]
 if 'tumbler_quick' in entry.get('attack_followups',{}):return entry['attack_followups']['tumbler_quick']
 actor=event['actor'];effect=None
 if event['result']=='damaging_hit' and not event.get('hit_prevented') and acquired(actor,QUICK):
  effect=quick_offer(e,actor,{'kind':'grapple','relation_id':relation_id,'history_index':history_index,'event_id':event['id']})
  quick_shift(e,actor,effect)
 return GRAPPLE.record_attack_followup(e,relation_id,history_index,'tumbler_quick',{'event_id':event['id'],'activated':effect is not None})


def resume_shift(e,actor):
 import combat_timing as TIME,world_entities as W
 W.require_actors(e,actor)
 if not acquired(actor,QUICK):raise ValueError('actual acquired Quick Gymnastics required')
 rows=[r for r in TIME.records(actor) if r.get('tumbler_quick') and not r.get('shift_done') and r.get('movement',{}).get('phase') in ('entry_pending','reaction_pending')]
 if len(rows)!=1:raise ValueError('one actual pending Quick Gymnastics movement required')
 record=rows[0];origin=record['origin']
 if e._active_turn_actor is not actor or actor.custom_conditions.get('combat_turn_serial',0)+1!=record['turn_deadline']:raise ValueError('resume Quick Gymnastics only during its actual triggering turn')
 if origin['kind']=='hit':raise ValueError('resume the original native hit so its remaining effects keep their order')
 return quick_shift(e,actor,record)


def quick_entry_waiting(e,record):
 if record is None:return False
 progress=record.get('movement',{})
 return progress.get('phase') in ('entry_pending','reaction_pending') and __import__('action_lifecycle').pending_resolution_effects(e,{'effects':progress.get('effects',[])})
