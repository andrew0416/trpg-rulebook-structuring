"""Printed Provocateur declarations and adapters to shared acquisition/action/effect owners."""
from copy import deepcopy
import combat_timing as TIME
import state_grants as G
import frequency as F
import common_checks as C

CLASS='class/선동가';PUSH='feat/반응유도';QUICK='feat/눈치-빠름';MIXED='feat/엇갈린-메시지'
POWER='feat/강력한-자극';FIDDLE='feat/사기-같은-플레이';GAZE='feat/매혹적인-응시';DEMO='edge/사기저하'
SOURCE_SHA256='a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'
SKILLS=('매력','교활','협박');EDGES=('edge/신뢰있는-아티스트','edge/협박하는-존재','edge/호감인')
MOVES=('move/초롱초롱눈동자','move/비밀이야기','move/째려보기','move/천사의키스','move/도발','move/트집','move/악마의키스')
FEATURES={CLASS:(2539,2541),PUSH:(2543,2547),QUICK:(2549,2553),MIXED:(2555,2559),POWER:(2561,2572),FIDDLE:(2574,2586),GAZE:(2588,2592)}
DEFINITIONS={uid:{'span':list(span),'catalog_span':[2530,2530] if uid==CLASS else list(span),
 'clause_id':{PUSH:'C04-101',FIDDLE:'C04-102',GAZE:'C04-103'}.get(uid,'input/ch04-trainer-classes.md:'+str(span[0])+'-'+str(span[1])),
 'stat_tag':'spe','parent':None if uid==CLASS else POWER if uid==FIDDLE else QUICK if uid==GAZE else CLASS,
 'skills':SKILLS,'minimum_rank':5 if uid in (FIDDLE,GAZE) else 4 if uid in (QUICK,MIXED,POWER) else 0,
 'skill_count':2 if uid in (MIXED,POWER,GAZE) else 1 if uid in (QUICK,FIDDLE) else 0,
 'selection':{'original':DEMO,'original_required_if_absent':True,'duplicate_replacement':'optional_qualified_edge'} if uid==PUSH else None}
 for uid,span in FEATURES.items()}
QUOTA={'kind':'scene','uses':3}
POWER_EFFECTS=({'no_critical':True},{'no_effect_range':True},{'statuses':['둔화']},{'evasion_modifier':-3},{'accuracy_modifier':-3},{'ally_damage_penalty':-10},{'save_modifier':-3})


def records(actor,feature=None,active=False):
 import trainer_feature_acquisition as T
 return [record for _, record in T.static_family_acquisitions(actor, FEATURES, feature, active=active)]


def acquired(actor,feature):
 rows=records(actor,feature,True)
 if len(rows)>1:raise ValueError('one actual Provocateur acquisition required')
 return rows[0] if rows else None


def _owned(actor,uid):
 import acquired_features as A
 return A.owned_rule_count(actor,uid)>0


def acquisition_snapshot(engine,actor,feature,selection=None):
 import skill_modifiers as S
 d=DEFINITIONS[feature]
 result={'skills':{name:S.rank(engine.r,actor,name)[2] for name in SKILLS},
  'parents':[r['request_id'] for r in records(actor,d['parent'],True)] if d['parent'] else [],
  'edges':[uid for uid in EDGES if _owned(actor,uid)]}
 if feature!=PUSH:
  if selection is not None:raise ValueError('this Provocateur Feature has no acquisition selection')
  return result
 if type(selection) is not dict or set(selection)-{'edge','requirements','edge_choices'} or 'edge' not in selection:
  raise ValueError('Push Buttons requires explicit Edge selection (None only if Demoralize is already owned)')
 edge=selection['edge'];already=_owned(actor,DEMO)
 result.update(selection=deepcopy(selection),demoralize_already_owned=already,edge_qualification=None)
 if edge is None:
  if not already:raise ValueError('Push Buttons must grant Demoralize when it is absent')
  return result
 if type(edge) is not str or not edge.startswith('edge/') or edge not in engine.r.selection.units:
  raise ValueError('choose an actual selected Edge')
 if _owned(actor,edge):raise ValueError('selected replacement Edge is already owned')
 if not already and edge!=DEMO:raise ValueError('replacement Edge requires already owned Demoralize')
 if edge==DEMO:
  if selection.get('requirements') or selection.get('edge_choices'):raise ValueError('Demoralize has no additional selection')
 else:
  import quick_npc as NPC
  result['edge_qualification']=NPC._requirements(actor,edge,selection.get('requirements'))
  if result['edge_qualification'].get('status')!='PolicyValuesReady':raise ValueError('replacement Edge prerequisites are not satisfied')
 return result


def qualification(actor,feature,snapshot,prerequisite_source):
 import acquisition_qualification as Q
 d=DEFINITIONS[feature]
 expected={'skills','parents','edges'}|({'selection','demoralize_already_owned','edge_qualification'} if feature==PUSH else set())
 if prerequisite_source is not None or type(snapshot) is not dict or set(snapshot)!=expected:raise ValueError('exact Provocateur acquisition observations required')
 if set(snapshot['skills'])!=set(SKILLS):raise ValueError('three printed Provocateur skills required')
 for value in snapshot['skills'].values():C.integer(value,'Provocateur skill rank',1)
 checks=[Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required')]
 if feature==CLASS:
  checks.append(Q.check('edge','prerequisite',bool(snapshot['edges']) and set(snapshot['edges'])<=set(EDGES),'one printed social Edge required'))
 else:
  known={r['request_id'] for r in records(actor,d['parent'])}
  checks.append(Q.check('parent','prerequisite',bool(snapshot['parents']) and set(snapshot['parents'])<=known,'actual acquired prerequisite '+d['parent']+' required'))
  checks.append(Q.check('skills','prerequisite',sum(v>=d['minimum_rank'] for v in snapshot['skills'].values())>=d['skill_count'],'printed Provocateur skill ranks required'))
 if feature==PUSH:
  selected=snapshot['selection']['edge'];qual=snapshot['edge_qualification']
  if selected not in (None,DEMO) and (snapshot['demoralize_already_owned'] is not True or not qual or qual.get('status')!='PolicyValuesReady'):
   raise ValueError('actual qualified replacement Edge evidence required')
 return Q.require(feature,'native','acquire',checks)


def _grant_edge(actor,source_id,choice):
 edge=choice['edge']
 if edge is None:return
 row=G.state(actor)['sources'][source_id];edge_source='feature:'+actor.entity_id+':'+edge
 if row.get('provocateur_edge') is not None or _owned(actor,edge) or edge_source in G.state(actor)['sources']:
  raise ValueError('Push Buttons Edge grant requires an unowned Edge and unused current source')
 actor.spec.setdefault('edges',[]).append(edge);row['provocateur_edge']=edge
 G._source(actor,edge_source,'feature',owner_id=actor.entity_id,rule_id=edge,lifetime='while_owned',tutor_points=0)
 row.setdefault('effect_sources',[]).append(edge_source)
 if choice.get('edge_choices'):actor.spec.setdefault('edge_choices',{})[edge]=deepcopy(choice['edge_choices'])


def _current_demoralize(actor):
 import trainer_feature_acquisition as T,acquired_features as A
 state=actor.spec.get(G.KEY,{})
 source_id='feature:'+actor.entity_id+':'+PUSH;row=state.get('sources',{}).get(source_id,{})
 receipt=row.get('provocateur_demoralize_adoption')
 if receipt is None:return None
 if type(receipt) is not dict:raise ValueError('actual current Demoralize adoption receipt required')
 T._text(receipt.get('request_id'),'current Demoralize adoption request')
 payload={'request_id':receipt['request_id'],'actor_id':actor.entity_id,'feature_id':PUSH,'edge':DEMO,
  'source_id':source_id,'source':T._static_source(actor.r,PUSH),
  'parent_acquisition_request':row.get('static_acquisition',{}).get('request_id')}
 if receipt!=dict(payload,integrity=T._digest('provocateur/current-demoralize-grant/v1',payload)):
  raise ValueError('current Demoralize adoption provenance changed')
 child_id='feature:'+actor.entity_id+':'+DEMO;child=state.get('sources',{}).get(child_id,{})
 if (actor.kind!='trainer' or A.owned_rule_count(actor,PUSH)!=1 or A.owned_rule_count(actor,DEMO)!=1 or row.get('kind')!='feature' or
  row.get('owner_id')!=actor.entity_id or row.get('rule_id')!=PUSH or row.get('lifetime')!='while_owned' or
  row.get('provocateur_edge')!=DEMO or row.get('effect_sources',[]).count(child_id)!=1 or
  child.get('kind')!='feature' or child.get('owner_id')!=actor.entity_id or child.get('rule_id')!=DEMO or child.get('lifetime')!='while_owned'):
  raise ValueError('current Demoralize adoption requires its actual connected owned sources')
 return receipt


def adopt_demoralize(engine,actor,*,adoption_request_id):
 """Grant the mandatory Edge now, without inventing historical acquisition."""
 import trainer_feature_acquisition as T,trainer_retraining as RETRAINING,world_entities as WORLD,acquired_features as A
 WORLD.require_actors(engine,actor);source=T._static_source(engine.r,PUSH);T.validate_actor(actor)
 T._text(adoption_request_id,'current Demoralize adoption request')
 if actor.kind!='trainer' or A.owned_rule_count(actor,PUSH)!=1:raise ValueError('actual current Push Buttons owner required')
 source_id='feature:'+actor.entity_id+':'+PUSH;state=actor.spec.get(G.KEY,{})
 if source_id not in state.get('sources',{}) and any(entry['source_id']==source_id for entry in state.get('ended_sources',[])):
  raise ValueError('ended Push Buttons source cannot adopt a current grant')
 existing=_current_demoralize(actor)
 if existing is not None:
  if existing['request_id']!=adoption_request_id:raise ValueError('current Demoralize adoption replay cannot change request')
  return deepcopy(existing)
 if _owned(actor,DEMO):raise ValueError('independent Demoralize is already owned; no current grant to adopt')
 def apply(staged,trainer):
  parent=RETRAINING.owned_source(staged,trainer,PUSH);row=G.state(trainer)['sources'][parent]
  payload={'request_id':adoption_request_id,'actor_id':trainer.entity_id,'feature_id':PUSH,'edge':DEMO,
   'source_id':parent,'source':source,'parent_acquisition_request':row.get('static_acquisition',{}).get('request_id')}
  receipt=dict(payload,integrity=T._digest('provocateur/current-demoralize-grant/v1',payload))
  _grant_edge(trainer,parent,{'edge':DEMO})
  G._source(trainer,parent,'feature',provocateur_demoralize_adoption=receipt)
  T.validate_actor(trainer);_current_demoralize(trainer)
  return deepcopy(receipt)
 return G.transition(engine,actor,apply)


def after_acquire(engine,actor,feature,source_id):
 if feature!=MIXED:G.stat(actor,'spe',1,source_id,operation_id='acquisition_stat_tag')
 if feature==PUSH:
  _grant_edge(actor,source_id,G.state(actor)['sources'][source_id]['static_acquisition']['snapshot']['selection'])
 if feature==CLASS:
  import class_move_grants as MOVES_OWNER
  MOVES_OWNER.register_all(engine,actor)
 elif feature==MIXED:
  import static_feature_state_grants as STATIC
  STATIC.register_all(engine,actor)
 import items
 items.register_feats(engine,actor)


def waive_demoralize(actor):
 row=acquired(actor,PUSH)
 return bool((row and row['snapshot']['selection']['edge']==DEMO) or _current_demoralize(actor))


def before_revoke(actor,row):
 edge=row.get('provocateur_edge')
 if edge is not None:
  actor.spec['edges'].remove(edge);actor.spec.get('edge_choices',{}).pop(edge,None)


def preflight(engine,actor,target,move):
 if acquired(actor,POWER) and move['id'] in MOVES:TIME.current(engine)


def begin_move(engine,row):
 actor=row['actor'];mid=row['move_id']
 row['provocateur_scene']=actor.spec.get('frequency_state',{}).get('scene',0)
 if acquired(actor,POWER) and mid in MOVES:row['provocateur_count']=TIME.current(engine)
 if acquired(actor,PUSH) and __import__('combat_social_edges').social(actor,row['move']):
  st=F.state(actor)
  row['provocateur_frequency_before']={'count':actor.move_uses.get(mid),'last':deepcopy(st['moves'].get(mid))}


def after_target(engine,row,target,result):
 actor=row['actor'];mid=row['move_id']
 if result.get('cancelled') or not acquired(actor,POWER) or mid not in MOVES:return
 rec={'source':POWER,'effect_contract':True,'count_deadline':(row['round']+1,row['provocateur_count']),
  'encounter_end':True,'provocateur':{'kind':'power','move_id':mid,'completion_id':row['id']},'attacker':actor}
 index=MOVES.index(mid)
 rec.update(deepcopy(POWER_EFFECTS[index]))
 TIME.install(engine,target,rec)


def after_move(engine,row):
 import move_completion as COMPLETE
 if not row.get('provocateur_power_done'):
  row['provocateur_power_done']=True
  for target in COMPLETE.actual_recipients(row):after_target(engine,row,target,COMPLETE.recipient_result(row,target))
 before=row.get('provocateur_frequency_before')
 if before is None or row.get('provocateur_frequency_finalized'):return
 row['provocateur_frequency_finalized']=True
 results=[COMPLETE.recipient_result(row,t) for t in COMPLETE.actual_recipients(row)]
 if not any(not v.get('cancelled') for v in results) or any(v['hit'] and not v.get('cancelled') for v in results):return
 actor=row['actor'];mid=row['move_id'];st=F.state(actor)
 # The completion preserves every actual use/target. Only the frequency ledger is refunded.
 if before['count'] is None:actor.move_uses.pop(mid,None)
 else:actor.move_uses[mid]=before['count']
 actor.spec['move_uses']=dict(actor.move_uses)
 if before['last'] is None:st['moves'].pop(mid,None)
 else:st['moves'][mid]=deepcopy(before['last'])


def refunded_latest(engine,actor,mid):
 rows=[r for r in getattr(engine,'_move_completions',{}).values() if r['actor'] is actor and r['move_id']==mid]
 import move_completion as COMPLETE
 results=[COMPLETE.recipient_result(rows[-1],t) for t in COMPLETE.actual_recipients(rows[-1])] if rows else []
 return bool(rows and rows[-1].get('provocateur_frequency_finalized') and any(not v.get('cancelled') for v in results) and not any(v['hit'] and not v.get('cancelled') for v in results))


def blocked(actor,key):
 return any(r.get(key) for r in TIME.records(actor))


def demoralize_threshold(actor,crit_min):
 return crit_min-2 if acquired(actor,PUSH) else crit_min-1


def critical_tick(engine,actor,target,move,ctx):
 if ctx.get('hit') and ctx.get('crit') and acquired(actor,PUSH) and __import__('combat_social_edges').social(actor,move):
  engine.lose_tick_hp(target,1,source=PUSH)


def _live(engine,actor,feature):
 import world_entities as W
 W.require_actors(engine,actor)
 if not acquired(actor,feature):raise ValueError('actual acquired '+feature+' required')
 if not engine.encounter_active:raise ValueError('active encounter required')


def _spend(engine,actor,feature,kind):
 import turn as TURN
 if not F.activation_allowed(actor,feature,QUOTA,engine=engine):raise ValueError('Provocateur Scene frequency exhausted')
 if not TURN.spend(engine,actor,kind,feature):raise ValueError('Provocateur action unavailable')
 F.consume_activation(actor,feature,QUOTA,engine=engine)


def quick_wit(engine,actor,target,*,move_id=None,manipulation=None,**options):
 _live(engine,actor,QUICK)
 if (move_id is None)==(manipulation is None):raise ValueError('choose one learned Social Move or Manipulate')
 if not F.activation_allowed(actor,QUICK,QUOTA,engine=engine):raise ValueError('Provocateur Scene frequency exhausted')
 if manipulation is not None:
  # Keep the maneuver owner's observed roll/cost continuation; do not roll it back in an outer transaction.
  return __import__('combat_maneuvers').manipulate(engine,actor,target,manipulation,_provocateur_quick=True,**options)
 move=engine.r.move(move_id);move_id=move['id']
 if move_id not in {engine.r.resolve_move(x) for x in actor.moves} or not __import__('combat_social_edges').social(actor,move):raise ValueError('actual learned Social Move required')
 allowed,reason=F.move_allowed(engine,actor,move_id)
 if not allowed:raise ValueError(reason)
 forbidden={'count_use','free_action','_activation','_shared_accuracy','_action_grant','_field_activation'}
 if forbidden.intersection(options):raise ValueError('Quick Wit preserves native Move frequency and activation authority')
 previous=getattr(engine,'_provocateur_quick',None);engine._provocateur_quick=(actor,move_id)
 try:return engine.use_move_on(actor,target,move_id,engine.everyone,**options)
 finally:
  if previous is None:del engine._provocateur_quick
  else:engine._provocateur_quick=previous


def quick_scope(engine,actor,move):
 return bool(move and getattr(engine,'_provocateur_quick',None)==(actor,move['id']) and acquired(actor,QUICK))


def quick_committed(engine,actor,move):
 if quick_scope(engine,actor,move):F.consume_activation(actor,QUICK,QUOTA,engine=engine)


def _hit(engine,actor,target,completion_id):
 row=getattr(engine,'_move_completions',{}).get(completion_id)
 if not row or row['phase']!='complete' or row['actor'] is not actor or row['move_id'] not in MOVES:
  raise ValueError('actual completed qualifying Move hit required')
 if row.get('provocateur_scene')!=F.state(actor)['scene'] or row['round']!=engine.round_no:
  raise ValueError('Fiddle trigger must be an actual hit in the current scene and round')
 import move_completion as COMPLETE
 actual=COMPLETE.recipient_result(row,target)
 if not actual or not actual['hit'] or actual.get('cancelled'):raise ValueError('actual hit recipient required')
 events=[uid for uid,r in row.get('native_returns',{}).items() if r['facts']['recipient_id']==target.entity_id]
 pending=[event for event in getattr(engine,'_passive_events',{}).values() if event.get('completion_id')==row['id'] and event.get('target') is target]
 if events:COMPLETE.require_hit_return(engine,events[-1],target)
 elif pending or target.entity_id in row.get('received',{}):raise ValueError('actual native hit return required')
 return row


def fiddle(engine,actor,target,completion_id,*,move_choice=None,ability_choice=None,accept=True):
 _live(engine,actor,FIDDLE);row=_hit(engine,actor,target,completion_id);mid=row['move_id']
 import move_completion as COMPLETE,condition_instances as CONDITIONS,ability_transitions as ABILITIES
 if type(accept) is not bool:raise ValueError('explicit optional choice required')
 if not accept:return {'status':'cancelled'}
 targets=[t for t in COMPLETE.actual_recipients(row) if COMPLETE.recipient_result(row,t)['hit'] and not COMPLETE.recipient_result(row,t).get('cancelled')]
 selections={}
 for t in targets:
  selected_move=move_choice.get(t.entity_id) if isinstance(move_choice,dict) else move_choice
  selected_ability=ability_choice.get(t.entity_id) if isinstance(ability_choice,dict) else ability_choice
  if mid==MOVES[5] and len(ABILITIES.known(t))>1 and selected_ability is None:
   return {'status':'cancelled','reason':'optional ability was not selected'}
  if mid==MOVES[1]:
   selected_move=engine.r.move(selected_move)['id'] if selected_move is not None else None
   used={r['move_id'] for r in getattr(engine,'_move_completions',{}).values() if r['actor'] is t and r.get('provocateur_scene')==F.state(t)['scene'] and (r['started'] or r.get('activation')=='empty_area_field')}
   if selected_move not in used:raise ValueError('choose a Move the actual target used this Scene')
  elif selected_move is not None:raise ValueError('this Fiddle effect has no Move choice')
  if mid!=MOVES[5] and selected_ability is not None:raise ValueError('this Fiddle effect has no Ability choice')
  if mid==MOVES[0] and not engine.immune_to(t,'헤롱헤롱'):CONDITIONS.prepare(engine,t,'헤롱헤롱',applied_by=actor)
  selections[t.entity_id]=(selected_move,selected_ability)
 if mid==MOVES[4]:TIME.current(engine)
 per=FIDDLE+':'+mid
 if not F.activation_allowed(actor,per,{'kind':'scene','uses':1},engine=engine):raise ValueError('this Fiddle Move effect was used this Scene')
 def apply(e,a,*victims):
  import effects as FX
  if mid==MOVES[5]:
   for t in victims:
    ABILITIES.select(e,a,t,FIDDLE,ability=selections[t.entity_id][1],reason='Fiddle optional selected Ability')
    ABILITIES.preflight(e,a,t,{'type':'ability_transition','contract':FIDDLE},FIDDLE)
  _spend(e,a,FIDDLE,'swift');F.consume_activation(a,per,{'kind':'scene','uses':1},engine=e)
  for t in victims:
   selected_move,selected_ability=selections[t.entity_id]
   rec={'source':FIDDLE,'effect_contract':True,'scene_end':True,
    'provocateur':{'kind':'fiddle','move_id':mid,'completion_id':completion_id},'attacker':a}
   if mid==MOVES[0]:
    if not e.immune_to(t,'헤롱헤롱'):
     CONDITIONS.grant(e,t,'헤롱헤롱',source=FIDDLE,applied_by=a)
     rec['uncurable_infatuation']=True;TIME.install(e,t,rec)
   elif mid==MOVES[1]:CONDITIONS.grant(e,t,'사슬묶기',source=FIDDLE,parameters={'move_id':selected_move},applied_by=a)
   elif mid==MOVES[2]:e.change_stage(t,'def',-1);e.change_stage(t,'spd',-2)
   elif mid==MOVES[3]:
    if '혼란' in t.conditions:rec['confusion_opportunities']=True;TIME.install(e,t,rec)
   elif mid==MOVES[4]:
    rec.pop('scene_end');rec.update(count_deadline=(e.round_no+1,TIME.current(e)),encounter_end=True,next_damage_dice='3d8+10');TIME.install(e,t,rec)
   elif mid==MOVES[5]:FX.run_effects(e,a,t,[{'type':'ability_transition','contract':FIDDLE}],{'hit':True,'nat':None},FIDDLE)
   else:rec['evasion_modifier']=-2;TIME.install(e,t,rec)
   a.spec.setdefault('provocateur_fiddle_history',[]).append({'source':FIDDLE,'completion_id':completion_id,'target_id':t.entity_id,'move_id':mid,'scene':F.state(a)['scene'],'move_choice':selected_move,'ability_choice':selected_ability})
  return {'status':'applied','move_id':mid,'targets':[t.entity_id for t in victims]}
 return G.transition(engine,actor,apply,participants=tuple(targets),include_rulings=True)


def retain_condition(actor,condition):
 return condition=='헤롱헤롱' and blocked(actor,'uncurable_infatuation')


def cured(engine,actor,condition):
 if condition=='혼란':
  for r in list(TIME.records(actor)):
   if r.get('confusion_opportunities'):TIME.expire(engine,actor,r)


def confusion_hit(engine,actor):
 if '혼란' in actor.conditions and blocked(actor,'confusion_opportunities'):
  __import__('turn').trigger_aoo(engine,actor,'사기 같은 플레이: 혼란 자해')


def damage_modifier(engine,actor,target,move,*,actual_hit=False):
 penalty=sum(r.get('ally_damage_penalty',0) for r in TIME.records(actor)
  if r.get('attacker') is not target and r.get('attacker') is not None and r['attacker'].side is not None and target.side==r['attacker'].side)
 if not actual_hit or move.get('class') not in ('물리','특수'):return penalty
 # This hook is in the actual damage roll, after hit. Misses and Status Moves never consume it.
 for rec in list(TIME.records(target)):
  if rec.get('next_damage_dice'):
   import roll_pools as POOLS
   faces=[POOLS.die(engine.rng,8) for _ in range(3)];penalty+=sum(faces)+10
   target.spec.setdefault('provocateur_damage_history',[]).append({'source':FIDDLE,'completion_id':rec['provocateur']['completion_id'],'attacker_id':actor.entity_id,'move_id':move['id'],'faces':faces,'total':sum(faces)+10})
   TIME.expire(engine,target,rec,ending='consumed',event={'kind':'successful_damaging_hit'})
 return penalty


def gaze(engine,actor,kind,*,aim):
 _live(engine,actor,GAZE)
 import combat_maneuvers as M,area_targets as AREA,action_points as AP
 kind=M.MANIP_ALIASES.get(kind,kind)
 if kind not in M.MANIPULATIONS:raise ValueError('choose one actual Manipulate effect')
 if actor.side is None:raise ValueError('actual friend and foe sides required')
 move={'id':GAZE,'_area_aim':aim,'_class_move_range':{'shape':'cone','size':2,'origin':'self'}}
 targets=AREA.targets(engine,actor,move,[c for c in engine.everyone if c.side is not None and c.side!=actor.side])
 if not targets:raise ValueError('Cone 2 must contain actual foes')
 count=TIME.current(engine)
 for t in targets:
  if kind=='flirt':M.flirt_existing(engine,actor,t)
 if AP.available(actor)<2:raise ValueError('Enchanting Gaze requires 2 AP')
 def apply(e,a,*foes):
  import turn as TURN
  if not TURN.spend(e,a,'standard',GAZE):raise ValueError('Enchanting Gaze Standard action unavailable')
  AP.spend(a,2)
  results=[]
  for t in foes:
   results.append(M._manipulate_outcome(e,a,t,kind,M.MANIPULATIONS[kind][1],count))
  a.spec.setdefault('provocateur_gaze_history',[]).append({'source':GAZE,'kind':kind,'targets':[t.entity_id for t in foes],'round':e.round_no,'ap':2})
  return results
 return G.transition(engine,actor,apply,participants=tuple(targets),include_rulings=True)


def validate(engine,index):
 for actor in index.values():
  for uid in FEATURES:
   record=acquired(actor,uid)
   if record is None:continue
   sid='feature:'+actor.entity_id+':'+uid
   stat=actor.spec.get(G.KEY,{}).get('stat_sources',{}).get('spe',{}).get('sources',{}).get(sid,{})
   operation='feature_count' if uid==MIXED else 'acquisition_stat_tag'
   if stat.get(operation)!={'delta':1,'minimum':None}:raise ValueError('Provocateur source-owned Speed tag required')
   if uid==PUSH:
    source=actor.spec[G.KEY]['sources'][sid];selected=record['snapshot']['selection']['edge']
    if source.get('provocateur_edge')!=selected or (selected is not None and actor.spec.get('edges',[]).count(selected)!=1):raise ValueError('Push Buttons optional Edge projection changed')
  for rec in TIME.records(actor):
   if 'provocateur' not in rec:continue
   fact=rec['provocateur'];row=getattr(engine,'_move_completions',{}).get(fact['completion_id'])
   if not row or row['actor'] is not rec['attacker'] or row['move_id']!=fact['move_id'] or __import__('move_completion').recipient_result(row,actor) is None:
    raise ValueError('Provocateur effect requires actual Move completion and recipient')
   common={'source','effect_contract','provocateur','attacker','owned_statuses','installing'}
   if fact['kind']=='power':
    expected=POWER_EFFECTS[MOVES.index(fact['move_id'])]
    if rec['source']!=POWER or set(rec)!=common|{'count_deadline','encounter_end'}|set(expected) or any(rec.get(k)!=v for k,v in expected.items()) or rec['count_deadline']!=(row['round']+1,row['provocateur_count']) or rec['encounter_end'] is not True:
     raise ValueError('Powerful Motivator effect or full-round lifetime changed')
   elif fact['kind']=='fiddle':
    keys={MOVES[0]:'uncurable_infatuation',MOVES[3]:'confusion_opportunities',MOVES[4]:'next_damage_dice',MOVES[6]:'evasion_modifier'}
    key=keys.get(fact['move_id']);value={MOVES[0]:True,MOVES[3]:True,MOVES[4]:'3d8+10',MOVES[6]:-2}.get(fact['move_id'])
    expected=common|{key}|({'count_deadline','encounter_end'} if fact['move_id']==MOVES[4] else {'scene_end'})
    if rec['source']!=FIDDLE or key is None or set(rec)!=expected or rec[key]!=value:raise ValueError('Fiddle effect payload changed')
    if fact['move_id']==MOVES[4]:
     if rec['count_deadline']!=(row['round']+1,row['provocateur_count']) or rec['encounter_end'] is not True:raise ValueError('Fiddle Taunt full-round lifetime changed')
    elif rec['scene_end'] is not True:raise ValueError('Fiddle Scene lifetime changed')
    if not any(h['completion_id']==row['id'] and h['target_id']==actor.entity_id for h in rec['attacker'].spec.get('provocateur_fiddle_history',[])):raise ValueError('Fiddle actual activation receipt required')
   else:raise ValueError('known Provocateur effect family required')

 return True
