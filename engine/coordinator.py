"""Coordinator: source-bound acquisition and native Contest/Move consumers.

Core and local translated source choices stay in the shared acquisition receipt.
Created Moves encode their immutable template and Contest choices in their ID;
permanent learning, quota, actions and effects retain their existing owners.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import base64
import json

import common_checks as C
import contest_features as CF
import skill_modifiers as SK
import state_grants as G
import world_entities as W
import frequency as F

CLASS='class/코디네이터'
DIRECTOR='feat/결단력-있는-감독자'
ADAPTABLE='feat/적응성-있는-공연'
FLEXIBLE='feat/유연한-대비'
INNOVATION='feat/혁신'
NUANCED='feat/뉘앙스-공연'
RELIABLE='feat/신뢰의-공연'
FEATURES={CLASS:(480,482),DIRECTOR:(484,489),ADAPTABLE:(491,495),FLEXIBLE:(497,501),INNOVATION:(503,507),NUANCED:(509,513),RELIABLE:(515,519)}
PARENTS={CLASS:('edge/우아함',),DIRECTOR:(CLASS,),ADAPTABLE:(CLASS,),FLEXIBLE:(ADAPTABLE,),INNOVATION:(ADAPTABLE,),NUANCED:(CLASS,),RELIABLE:(NUANCED,)}
MIN_RANK={CLASS:3,FLEXIBLE:4,NUANCED:5,RELIABLE:6}
CLAUSES={DIRECTOR:'C04-019',NUANCED:'C04-020',RELIABLE:'C04-021'}
CSV={u:'C2CSV/input/db/feats.csv:R'+str(i)+':main' for i,u in enumerate(FEATURES,90)}
STATIC_DEFINITIONS={u:{'span':list(span),'catalog_span':[466,466] if u==CLASS else list(span),'clause_id':CLAUSES.get(u,'input/ch04-trainer-classes.md:'+str(span[0])+'-'+str(span[1]))} for u,span in FEATURES.items()}
STATS={'근사함':'atk','강인함':'def','아름다움':'spa','슬기로움':'spd','귀여움':'spe'}
PREFIX='move/innovation:'
MIX_PREFIX='move/adaptable:'
POLICY='data/coordinator-source-contract.json'
POLICY_SHA='451aa825379f2780e64dc526ed431f4b99eb62f100c91d324cadfab4840d4fa4'


def policy(rules):
 content=(Path(__file__).resolve().parents[1]/POLICY).read_bytes()
 if sha256(content).hexdigest()!=POLICY_SHA:raise ValueError('reviewed Coordinator source interpretation changed')
 document=json.loads(content)
 if document.get('schema')!=1 or set(document['source_choices'])!={'core_1.05','local_csv','ptk_literal'}:raise ValueError('reviewed Coordinator source choices required')
 return document


def source(rules,choice='core_1.05',feature=CLASS):
 from source_context import verified_source
 p=policy(rules)
 if choice not in p['source_choices'] or feature not in FEATURES:raise ValueError('explicit Coordinator source contract required')
 verified_source(rules,p['body'],label='Coordinator body')
 if choice=='core_1.05':verified_source(rules,p['core'],label='Coordinator English Core',source_root='source-audit')
 if choice=='local_csv':
  verified_source(rules,p['feats_csv'],label='Coordinator local CSV')
  verified_source(rules,p['class_data_csv'],label='Coordinator class CSV')
  # Registry locators are not necessarily native RuleUnit identities.
  # Exact CSV bytes/ordinal remain authority; catalogued identities stay selected.
  if CSV[feature] in rules.selection.units and rules._selected_rule(CSV[feature])!=CSV[feature]:raise ValueError('exact selected local Coordinator CSV source required')
 if rules._selected_rule(feature)!=feature:raise ValueError('selected Coordinator Feature requires its own source adapter')
 if feature==DIRECTOR and choice=='ptk_literal':raise ValueError('literal Korean Director prerequisite is unprinted; select the explicit Core or CSV contract')
 return deepcopy(p['source_choices'][choice])


def static_source(rules,feature):
 p=policy(rules)
 from source_context import verified_source
 verified_source(rules,p['body'],label='Coordinator acquisition')
 if rules._selected_rule(feature)!=feature:raise ValueError('selected Coordinator acquisition source required')
 return dict(deepcopy(p['body']),clause_id=STATIC_DEFINITIONS[feature]['clause_id'],span=list(FEATURES[feature]),
  source_choices=deepcopy(p['source_choices']),core_reference=deepcopy(p['core']),csv_reference=deepcopy(p['feats_csv']))


def records(actor,feature=None,active=True):
 import trainer_feature_acquisition as T
 return [r['static_acquisition'] for _,r,live in T._static_records(actor) if r['static_acquisition']['feature_id'] in FEATURES and (feature is None or r['static_acquisition']['feature_id']==feature) and (live or not active)]


def contract(actor,feature=CLASS):
 rows=records(actor,feature)
 return rows[-1]['snapshot']['selection']['source_contract'] if rows else 'local_csv'


def acquisition_snapshot(engine,actor,feature,rank=None,selection=None):
 if rank is not None:raise ValueError('Coordinator Features are not Ranked')
 selection={'source_contract':'core_1.05'} if selection is None else deepcopy(selection)
 if type(selection)is not dict or set(selection)!={'source_contract'}:raise ValueError('one exact Coordinator source selection required')
 source(engine.r,selection['source_contract'],feature)
 parents={}
 for parent in PARENTS[feature]:
  rows=records(actor,parent)
  if not CF.owned(actor,parent):raise ValueError('acquired Coordinator prerequisite required: '+parent)
  parents[parent]=rows[-1]['request_id'] if rows else parent
 return {'selection':selection,'skills':{s:SK.rank(engine.r,actor,s)[2] for s in CF.SKILLS},'parents':parents}


def qualification(actor,feature,snapshot,prerequisite_source):
 import acquisition_qualification as Q
 if prerequisite_source is not None or type(snapshot)is not dict or set(snapshot)!={'selection','skills','parents'}:raise ValueError('exact Coordinator acquisition observations required')
 selection=snapshot['selection']
 if type(selection)is not dict or set(selection)!={'source_contract'}:raise ValueError('exact Coordinator source choice required')
 source(actor.r,selection['source_contract'],feature)
 if type(snapshot['skills'])is not dict or set(snapshot['skills'])!=set(CF.SKILLS):raise ValueError('actual Coordinator acquisition skills required')
 for n in snapshot['skills'].values():C.integer(n,'acquired Coordinator skill rank',1,8)
 if type(snapshot['parents'])is not dict or set(snapshot['parents'])!=set(PARENTS[feature]):raise ValueError('printed Coordinator parent set required')
 historical={r['request_id']:r['feature_id'] for r in records(actor,active=False)}
 for parent,ref in snapshot['parents'].items():
  if not (ref==parent and CF.owned(actor,parent) or historical.get(ref)==parent):raise ValueError('actual Coordinator prerequisite receipt required')
 checks=[Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),Q.check('skills','prerequisite',max(snapshot['skills'].values())>=MIN_RANK.get(feature,1),'printed Coordinator skill rank required')]
 return Q.require(feature,'native','acquire',checks)


def require(engine,trainer,feature):
 CF.conscious_trainer(trainer);CF.require(engine,trainer,feature)
 selected=source(engine.r,contract(trainer,feature),feature)
 for parent in PARENTS[feature]:
  if parent in FEATURES:require(engine,trainer,parent)
  else:CF.require(engine,trainer,parent)
 if max(SK.rank(engine.r,trainer,s)[2] for s in CF.SKILLS)<MIN_RANK.get(feature,1):raise ValueError('printed Coordinator skill prerequisite required')
 return selected


def _encode(prefix,row):
 return prefix+base64.urlsafe_b64encode(json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).decode().rstrip('=')


def _decode(mid,prefix):
 if not isinstance(mid,str) or not mid.startswith(prefix):return None
 try:row=json.loads(base64.urlsafe_b64decode(mid[len(prefix):]+'='*(-len(mid[len(prefix):])%4)))
 except Exception as exc:raise ValueError('invalid Coordinator Move identity') from exc
 if type(row)is not dict or _encode(prefix,row)!=mid:raise ValueError('canonical Coordinator Move identity required')
 return row


def innovation_instance(rules,mid):
 row=_decode(mid,PREFIX)
 if row is None:return None
 if set(row)!={'trainer_id','name','template','contest_type','contest_effect','source_contract'}:raise ValueError('exact Innovation Move identity required')
 if any(type(row[k])is not str or not row[k].strip() or row[k]!=row[k].strip() for k in ('trainer_id','name','contest_effect')):raise ValueError('actual Innovation creator/name/effect required')
 if type(row['template'])is not int or not 1<=row['template']<=4 or row['contest_type'] not in STATS:raise ValueError('printed Innovation template/type required')
 source(rules,row['source_contract'],INNOVATION)
 # A Contest reader exposes the same selected effect declaration as combat.
 from contest import ContestRules
 cr=rules if isinstance(rules,ContestRules) else getattr(rules,'_coordinator_contest_reader',None)
 if cr is None or cr.root!=rules.root or cr.ruleset is not rules.ruleset:
  cr=ContestRules(rules.root,ruleset=rules.ruleset)
  rules._coordinator_contest_reader=cr
 if row['contest_effect'] not in cr.mech('contest/effects'):raise ValueError('one of the selected 22 Contest Effects required')
 return row


def definition(rules,mid,row):
 template=row['template'];p=source(rules,row['source_contract'],INNOVATION)
 frequency={1:'장면',2:'장면x2',3:('임의' if p['innovation3_frequency']=='turn' else '턴1회'),4:'장면'}[template]
 return {'id':mid,'name':row['name'],'eng':None,'type':'노말','class':'물리' if template==3 else '변화',
  'damage_base':4 if template==3 else None,'ac':4 if template==3 else None,'frequency':frequency,
  'range':{1:'자신',2:'6, 대상 1',3:'근접, 대상 1',4:'자신, 파열 2'}[template],
  'effect':'Innovation template '+str(template),'contest':row['contest_type']+' - '+row['contest_effect'],
  'homebrew':False,'innovation_instance':deepcopy(row)}


def mechanics(rules,row):
 stat=STATS[row['contest_type']];template=row['template']
 effects=[]
 if template==2:effects=[{'type':'stage_change','stat':stat,'delta':-2,'target':'target'}]
 if template==4:effects=[{'type':'stage_change','stat':stat,'delta':1,'target':'target'}]
 return rules.flatten_effects(effects)


def validate_spec(rules,spec):
 mids=[rules.move_id(m) for m in spec.get('moves',[]) if m!='struggle']
 created=[mid for mid in mids if innovation_instance(rules,mid) is not None]
 if len(created)>1:raise ValueError('Pokemon can know only one Innovation Move at a time')
 for mid in created:
  if spec.get('move_learning',{}).get(mid,{}).get('source')!=INNOVATION:raise ValueError('actual permanent Innovation learning receipt required')
 for mid,receipt in spec.get('move_learning',{}).items():
  if not mid.startswith(PREFIX) or receipt.get('source')!=INNOVATION:continue
  row=innovation_instance(rules,mid)
  if receipt.get('paid_tp')!=1 or receipt.get('teacher_id')!=row['trainer_id'] or receipt.get('innovation')!=row:raise ValueError('Innovation permanent learning provenance changed')
 return created


def _extended(e,t,feature,seconds):
 import turn as TURN
 C.integer(seconds,'actual Extended action seconds',1)
 if e.encounter_active:raise ValueError('Coordinator Extended action requires noncombat time')
 if not F.activation_allowed(t,feature,{'kind':'daily'},engine=e):raise ValueError('Coordinator Daily use exhausted')
 if not TURN.spend(e,t,'extended',feature):raise ValueError('Coordinator Extended action unavailable')
 F.consume_activation(t,feature,{'kind':'daily'},engine=e)


def innovate(engine,trainer,pokemon,*,name,template,contest_type,contest_effect,seconds,reason):
 W.require_actors(engine,trainer,pokemon);require(engine,trainer,INNOVATION)
 if pokemon.kind!='pokemon':raise ValueError('Innovation targets a Pokemon')
 if type(reason)is not str or not reason.strip():raise ValueError('actual Innovation learning reason required')
 row={'trainer_id':trainer.entity_id,'name':name,'template':template,'contest_type':contest_type,'contest_effect':contest_effect,'source_contract':contract(trainer,INNOVATION)}
 mid=_encode(PREFIX,row);innovation_instance(engine.r,mid)
 def apply(e,t,p):
  import pokemon_teaching as TEACH,learning_grant as LEARNING,activity_jobs as JOBS
  if validate_spec(e.r,p.spec):raise ValueError('Pokemon already knows an Innovation Move; forget it explicitly first')
  if TEACH._balance(p.spec)<1:raise ValueError('Innovation requires one actual Tutor Point')
  candidate=deepcopy(p.spec)
  result=LEARNING.learn_moves(e.r,candidate,candidates=[mid],selected=[mid],method='feature',source=INNOVATION,reason=reason,provider=t.entity_id,paid_tp=1,details={'innovation':deepcopy(row)})
  _extended(e,t,INNOVATION,seconds)
  JOBS.run_fixed(e,t,(p,),seconds=seconds,source=INNOVATION,context={'move_id':mid})
  TEACH._debit_points(p.spec,1)
  for field in ('move_learning','move_learning_log'):p.spec[field]=candidate[field]
  G.set_baseline(p,'moves',candidate['moves'])
  e.log('  '+p.name+': '+name+' 영구 학습, TP1',INNOVATION)
  return result
 return G.transition(engine,trainer,apply,participants=(pokemon,))


def flexible(engine,trainer,pokemon,*,from_stat,to_stat,dice,seconds,reason):
 W.require_actors(engine,trainer,pokemon);require(engine,trainer,FLEXIBLE)
 C.integer(dice,'reallocated Poffin d6 units',1,2)
 if from_stat not in STATS or to_stat not in STATS or from_stat==to_stat:raise ValueError('two distinct printed Contest Stats required')
 if type(reason)is not str or not reason.strip():raise ValueError('actual preparation reason required')
 def apply(e,t,p):
  import poffin_state as P,activity_jobs as JOBS
  values=P.available(p,engine=e)
  if values.count(from_stat)<dice:raise ValueError('not enough Poffin-derived dice in the chosen stat')
  old=p.spec.get('flexible_preparations')
  if old and old['day']==p.spec.get('frequency_state',{}).get('day',0):raise ValueError('multiple simultaneous Flexible providers require explicit adjudication')
  _extended(e,t,FLEXIBLE,seconds)
  JOBS.run_fixed(e,t,(p,),seconds=seconds,source=FLEXIBLE,context={'from_stat':from_stat,'to_stat':to_stat,'dice':dice})
  row={'source':FLEXIBLE,'trainer_id':t.entity_id,'pokemon_id':p.entity_id,'source_contract':contract(t,FLEXIBLE),'from_stat':from_stat,'to_stat':to_stat,'dice':dice,'day':p.spec.get('frequency_state',{}).get('day',0),'at':e.elapsed_seconds,'reason':reason}
  row['sha256']=__import__('resolution_transaction').request_fingerprint(row)
  p.spec['flexible_preparations']=row
  return deepcopy(row)
 return G.transition(engine,trainer,apply,participants=(pokemon,))


def flexible_projection(pokemon,values,engine=None):
 row=pokemon.spec.get('flexible_preparations')
 if row is None:return values
 if type(row)is not dict or row.get('sha256')!=__import__('resolution_transaction').request_fingerprint({k:v for k,v in row.items() if k!='sha256'}):raise ValueError('Flexible preparation evidence changed')
 source(pokemon.r,row['source_contract'],FLEXIBLE)
 if row['source']!=FLEXIBLE or row['pokemon_id']!=pokemon.entity_id or row['from_stat'] not in STATS or row['to_stat'] not in STATS:raise ValueError('actual Flexible target and stats required')
 C.integer(row['dice'],'reallocated Poffin dice',1,2)
 if row['day']!=pokemon.spec.get('frequency_state',{}).get('day',0):return values
 values=list(values)
 # Apply to current-owner availability; a transfer cannot resurrect unavailable Poffins.
 for _ in range(min(row['dice'],values.count(row['from_stat']))):values.remove(row['from_stat']);values.append(row['to_stat'])
 return tuple(values)


def adaptable_instance(rules,mid):
 row=_decode(mid,MIX_PREFIX)
 if row is None:return None
 if set(row)!={'type_move','effect_move','source_contract'} or row['type_move']==row['effect_move']:raise ValueError('two distinct actual Adaptable Moves required')
 source(rules,row['source_contract'],ADAPTABLE)
 if any(value.startswith(MIX_PREFIX) for value in (row['type_move'],row['effect_move'])):raise ValueError('Adaptable uses known actual Moves, not another composite')
 for key in ('type_move','effect_move'):
  if rules.move(row[key])['id']!=row[key]:raise ValueError('canonical Adaptable constituent required')
 return row


def adaptable_definition(rules,mid,row):
 type_move=rules.move(row['type_move']);effect_move=rules.move(row['effect_move'])
 stat=rules.move_contest(row['type_move'])[0];effect=rules.move_contest(row['effect_move'])[1]
 return dict(type_move,id=mid,name=type_move['name']+' / '+effect_move['name'],contest=stat+' - '+effect,adaptable_instance=deepcopy(row))


def contest_round(ce):
 states=[s for s in (getattr(ce,'_standard_run',None),getattr(ce,'_paired_run',None),getattr(ce,'_festival_run',None)) if s and s.get('phase')!='complete']
 if len(states)!=1 or type(states[0].get('round'))is not int:raise ValueError('Adaptable needs the actual current Contest round')
 return states[0],states[0]['round']


def adaptable_plan(ce,c,moves):
 if type(moves)not in (tuple,list) or len(moves)!=2:raise ValueError('select ordered type/effect Moves')
 e,p,t,_,_=ce._feature_binding(c)
 CF.owner(t,p);require(e,t,ADAPTABLE)
 state,round_no=contest_round(ce)
 known={ce.r.move(m)['id'] for m in c.moves}
 ids=[ce.r.move(m)['id'] for m in moves]
 if len(set(ids))!=2 or not set(ids)<=known:raise ValueError('Adaptable requires two distinct actual known Moves')
 uid=t.entity_id
 uses=getattr(ce,'_adaptable_uses',{})
 if uid in uses:raise ValueError('Adaptable already used once in this Contest')
 if not F.activation_allowed(t,ADAPTABLE,{'kind':'scene'},engine=e):raise ValueError('Adaptable Scene use exhausted')
 choice=contract(t,ADAPTABLE);source(ce.r,choice,ADAPTABLE)
 row={'type_move':ids[0],'effect_move':ids[1],'source_contract':choice}
 mid=_encode(MIX_PREFIX,row);adaptable_instance(ce.r,mid)
 return {'move_id':mid,'trainer':t,'pokemon':p,'engine':e,'round':round_no,'contest_id':state['id'],'moves':ids,'choice':choice}


def contest_preflight(ce,c,mid):
 uses=getattr(ce,'_adaptable_uses',{})
 state=None
 if uses:
  state,round_no=contest_round(ce)
  for row in uses.values():
   if row['pokemon'] is c and row['contest_id']==state['id'] and round_no==row['round']+1:
    if source(ce.r,row['choice'],ADAPTABLE)['adaptable_lock']=='all_moves' or mid in row['moves']:raise ValueError('Adaptable next-round Move restriction')
 mixed=adaptable_instance(ce.r,mid)
 if mixed:
  permit=getattr(ce,'_adaptable_plan',None)
  binding=ce._native_intro_bindings.get(c)
  if not permit or permit['move_id']!=mid or binding is not None and permit['pokemon'] is not binding[1]:raise ValueError('actual Adaptable performance producer required')
  known={ce.r.move(m)['id'] for m in c.moves}
  if not {mixed['type_move'],mixed['effect_move']}<=known:raise ValueError('Adaptable actual learned constituents changed')
 return mixed


def contest_commit(ce,c,plan):
 if plan is None:return
 t=plan['trainer'];e=plan['engine']
 require(e,t,ADAPTABLE)
 CF.trigger_free_action(e,t,ADAPTABLE);F.consume_activation(t,ADAPTABLE,{'kind':'scene'},engine=e)
 row={'pokemon':c,'trainer_id':t.entity_id,'round':plan['round'],'contest_id':plan['contest_id'],'moves':list(plan['moves']),'choice':plan['choice']}
 if not hasattr(ce,'_adaptable_uses'):ce._adaptable_uses={}
 ce._adaptable_uses[t.entity_id]=row


def arm_nuanced(engine,trainer,pokemon,*,decision):
 W.require_actors(engine,trainer,pokemon);CF.owner(trainer,pokemon);require(engine,trainer,NUANCED)
 if not callable(decision):raise ValueError('actual post-miss Nuanced choice required')
 engine._coordinator_nuanced_decisions={**getattr(engine,'_coordinator_nuanced_decisions',{}),trainer.entity_id:decision}
 return G.transition(engine,trainer,lambda e,t:t.spec.update(nuanced_offer={'source':NUANCED,'pokemon_id':pokemon.entity_id}))


def begin_move(engine,completion):
 actor=completion['actor'];mid=completion['move_id']
 offers=[t for t in W.actor_index(engine).values() if t.spec.get('nuanced_offer',{}).get('pokemon_id')==actor.entity_id]
 if len(offers)>1:raise ValueError('Nuanced needs one actual owner')
 if offers:
  t=offers[0];CF.owner(t,actor);require(engine,t,NUANCED)
  kind=F.move_frequency(engine,mid,actor)[0]
  if kind in ('scene','daily','every_other_turn'):
   completion['nuanced']={'trainer':t,'move_id':mid,'kind':kind,'source_contract':contract(t,NUANCED)}
 row=innovation_instance(engine.r,mid)
 if row:completion['innovation']=deepcopy(row)
 boon=actor.spec.get('innovation_attack_boon')
 if boon and boon['move_id']==mid:
  if boon['turn']!=actor.custom_conditions.get('combat_turn_serial',0):raise ValueError('Boon attack declaration expired')
  completion['innovation_attack_boon']=deepcopy(boon)
  boon['completion_id']=completion['id']


def after_move(engine,completion):
 actor=completion['actor'];row=completion.get('innovation')
 if row and row['template']==1 and not completion.get('innovation_applied'):
  results=list(completion['results'].values())
  if any(r['hit'] and not r.get('cancelled') for r in results):
   actor.spec.setdefault('innovation_boons',[]).append({'move_id':completion['move_id'],'contest_type':row['contest_type'],'remaining':3,'completion_id':completion['id'],'scene':F.state(actor)['scene']})
  completion['innovation_applied']=True
 if row and row['template']==3 and not completion.get('innovation_surge_applied'):
  natural=[ev['natural_roll'] for ev in getattr(engine,'_passive_events',{}).values() if ev.get('completion_id')==completion['id'] and ev.get('natural_roll') is not None]
  matching=contest_dice(engine,actor,row['contest_type'])
  if any(__import__('combat_precision_features').effect_natural(engine,actor,completion['move'],n)>=18 for n in natural):engine.change_stage(actor,STATS[row['contest_type']],1)
  completion['innovation_surge_applied']=True
 if actor.spec.get('innovation_attack_boon',{}).get('completion_id')==completion['id']:actor.spec.pop('innovation_attack_boon',None)
 plan=completion.get('nuanced')
 if not plan or completion.get('nuanced_decided'):return
 target_results=[__import__('move_completion').recipient_result(completion,t) for t in completion['targets']]
 if not target_results or any(not r or r.get('cancelled') or r['hit'] or r.get('hit_prevented') for r in target_results):return
 mm,_=engine.r.move_mech(plan['move_id'])
 effects=mm.get('effects_exec',[])
 if any(x.get('type') in ('execute','activation_check','move_failure','one_hit_ko') or x.get('keyword')=='Execute' for x in effects) or '일격' in str(completion['move'].get('effect','')):return
 completion['nuanced_pending']=True
 callback=getattr(engine,'_coordinator_nuanced_decisions',{}).get(plan['trainer'].entity_id)
 if callable(callback):
  chosen=callback({'completion_id':completion['id'],'pokemon_id':actor.entity_id,'move_id':plan['move_id'],'all_targets_missed':True})
  if type(chosen)is not bool:raise ValueError('explicit Nuanced decision required')
  decide_nuanced(engine,plan['trainer'],completion['id'],chosen)


def decide_nuanced(engine,trainer,completion_id,decision):
 W.require_actors(engine,trainer)
 if type(decision)is not bool:raise ValueError('explicit post-miss Nuanced choice required')
 def apply(e,t):
  import action_points as AP,move_permissions as MP,move_completion as MC
  c=e._move_completions[completion_id];plan=c.get('nuanced');actor=c['actor']
  if not plan or plan['trainer'] is not t or c['phase']!='complete' or not c.get('nuanced_pending'):raise ValueError('actual whole-move miss observation required')
  if c.get('nuanced_decided'):
   if c['nuanced_decided']['accepted']!=decision:raise ValueError('Nuanced replay cannot change its decision')
   return deepcopy(c['nuanced_decided'])
  results=[MC.recipient_result(c,x) for x in c['targets']]
  if not results or any(not r or r['hit'] or r.get('cancelled') or r.get('hit_prevented') for r in results):raise ValueError('all actual targets must have missed')
  CF.owner(t,actor);require(e,t,NUANCED)
  if decision:
   if AP.available(t)<1:raise ValueError('Nuanced requires 1 AP')
   CF.trigger_free_action(e,t,NUANCED);AP.spend(t,1)
   owner=MP.frequency_owner(e,actor,plan['move_id']);kind=plan['kind']
   if kind=='scene':F.restore_scene_use(e,actor,plan['move_id'])
   elif kind=='every_other_turn':F.restore_eot(e,actor,plan['move_id'])
   elif kind=='daily':
    st=F.state(owner);owner.move_uses[plan['move_id']]=max(0,owner.move_uses.get(plan['move_id'],0)-1);owner.spec['move_uses']=dict(owner.move_uses)
    if plan['move_id'] in st['moves']:st.setdefault('restored_move_occurrences',{})[plan['move_id']]=deepcopy(st['moves'][plan['move_id']])
    st['moves'].pop(plan['move_id'],None)
  c['nuanced_decided']={'accepted':decision,'ap':1 if decision else 0};t.spec.pop('nuanced_offer',None)
  return deepcopy(c['nuanced_decided'])
 return G.transition(engine,trainer,apply)


def contest_dice(engine,pokemon,stat):
 import poffin_state as P
 combat=STATS[stat];value=min(3,__import__('arithmetic_policy').ratio(pokemon.stats[combat],10))+P.available(pokemon,engine=engine).count(stat)
 owner=P.current_owner(engine,pokemon)
 if owner is not None and CF.owned(owner,CF.STYLE):value+=CF.style_stat_dice(engine,owner,pokemon).get(stat,0)
 return value


def prepare(engine,actor,move):
 row=move.get('innovation_instance')
 if not row:return move
 if actor.kind!='pokemon' or move['id'] not in actor.moves:raise ValueError('actual Pokemon learned Innovation Move required')
 validate_spec(engine.r,actor.spec)
 if row['template']==3:
  import struggle_capabilities as STRUGGLE
  base=engine.r.move('struggle')
  choice=actor.spec.get('innovation_struggle_choice')
  for marker in ('_struggle_capability','_telekinetic_struggle'):
   if marker in move:base[marker]=deepcopy(move[marker])
  base=STRUGGLE.prepare(engine,actor,base,choice)
  base=__import__('weapon_actions').prepare(engine,actor,base)
  base=__import__('pokemon_move_edges').prepare(engine,actor,base)
  # Every native ordinary Struggle modification stays on the prepared copy.
  for key,value in move.items():
   if key in ('id','name','frequency','contest','innovation_instance'):base[key]=value
  base['innovation_instance']=deepcopy(row)
  return base
 return move


def selected_targets(engine,actor,move,candidates,primary):
 row=move.get('innovation_instance')
 if not row or row['template']!=4:return candidates
 return [t for t in candidates if t is not actor and actor.side and t.side==actor.side]


def effect_range(engine,actor,move):
 row=move.get('innovation_instance')
 return (contest_dice(engine,actor,row['contest_type'])//2 if row and row['template']==3 else 0)+attack_boon(actor,move,'아름다움')


def damage_bonus(engine,actor,move):
 row=move.get('innovation_instance')
 if not row or row['template']!=3:return 0
 p=source(engine.r,row['source_contract'],INNOVATION)
 if p['innovation3_damage']=='up_to_5':return C.integer(actor.spec.get('innovation_damage_bonus'),'literal chosen Innovation bonus',0,5)
 return 5


def attack_boon(actor,move,stat):
 row=actor.spec.get('innovation_attack_boon')
 return 3 if row and row['contest_type']==stat and row['move_id']==move.get('id') and row['turn']==actor.custom_conditions.get('combat_turn_serial',0) else 0


def spend_boon(engine,pokemon,*,move_id,attack_move=None):
 import turn as TURN,combat_timing as TIME
 W.require_actors(engine,pokemon)
 row=innovation_instance(engine.r,move_id)
 if row is None or row['template']!=1:raise ValueError('actual created Boon Move required')
 if engine._active_turn_actor is not pokemon:raise ValueError('Boon requires its Pokemon own turn')
 def apply(e,p):
  pools=[x for x in p.spec.get('innovation_boons',[]) if x['move_id']==move_id and x['scene']==F.state(p)['scene'] and x['remaining']>0]
  if not pools:raise ValueError('no unspent Contest Boon')
  stat=row['contest_type']
  if stat in ('아름다움','근사함','슬기로움'):
   if any(c['actor'] is p and c['phase'] not in ('complete','interrupted') for c in getattr(e,'_move_completions',{}).values()):raise ValueError('Boon attack declaration must precede actual accuracy')
   if attack_move is None or e.r.move_id(attack_move) not in p.moves:raise ValueError('attack-declaration Boon needs its actual learned attack')
   mid=e.r.move_id(attack_move)
   if e.r.move(mid)['class'] not in ('물리','특수'):raise ValueError('Boon requires an actual attack declaration')
   if p.spec.get('innovation_attack_boon'):raise ValueError('one declared Boon per attack; overlapping providers need adjudication')
  elif attack_move is not None:raise ValueError('this Boon has no attack declaration')
  if stat=='강인함' and getattr(p,'_action_history',[]):raise ValueError('Tough Boon must be used at the start of a turn')
  if not TURN.spend(e,p,'swift',INNOVATION):raise ValueError('Boon Swift action unavailable')
  pools[0]['remaining']-=1
  if stat=='귀여움':TIME.install(e,p,{'source':INNOVATION,'innovation_boon':stat,'effect_contract':True,'evasion_modifier':3,'count_deadline':[e.round_no+1,TIME.current(e)]})
  elif stat=='강인함':TIME.install(e,p,{'source':INNOVATION,'innovation_boon':stat,'turn_owner':p,'turn_deadline':p.custom_conditions.get('combat_turn_serial',0),'innovation_prevent_loss':True})
  else:p.spec['innovation_attack_boon']={'source':INNOVATION,'contest_type':stat,'move_id':mid,'turn':p.custom_conditions.get('combat_turn_serial',0),'boon_move_id':move_id}
  return {'source':INNOVATION,'contest_type':stat,'remaining':pools[0]['remaining']}
 return G.transition(engine,pokemon,apply)


def prevent_loss(engine,actor,source_id):
 import combat_timing as TIME
 if not any(r.get('innovation_prevent_loss') for r in TIME.records(actor)):return False
 import condition_instances as CONDITIONS
 # Callers retain concrete cause IDs; an unrelated generic HP setting is excluded.
 source_text=str(source_id).lower()
 if 'condition/'+str(source_id).removeprefix('condition/') in engine.r.units or source_id=='혼란 자해':return True
 return source_id in ('condition/독','condition/맹독','condition/화상','독','맹독','화상') or any(x in source_text for x in ('recoil','반동','weather','날씨','모래바람','싸라기눈','폭설','status/'))


def damage_offer(engine,pokemon):
 rows=[t for t in W.actor_index(engine).values() if t.spec.get('coordinator_damage_offer',{}).get('pokemon_id')==pokemon.entity_id]
 if len(rows)>1:raise ValueError('one actual Coordinator damage provider required')
 return rows[0] if rows else None


def arm_damage(engine,trainer,pokemon,*,decision):
 W.require_actors(engine,trainer,pokemon);CF.owner(trainer,pokemon);require(engine,trainer,CLASS)
 if not callable(decision):raise ValueError('actual observed Damage Roll decision required')
 if any(t.spec.get('native_roll_offer',{}).get('actor_id')==pokemon.entity_id for t in W.actor_index(engine).values()):raise ValueError('independent simultaneous reroll providers require adjudication')
 key=CLASS+(':'+pokemon.entity_id if source(engine.r,contract(trainer,CLASS),CLASS)['coordinator_scene']=='per_pokemon' else '')
 if not F.activation_allowed(trainer,key,{'kind':'scene'},engine=engine):raise ValueError('Coordinator Scene use exhausted')
 engine._coordinator_damage_decisions={**getattr(engine,'_coordinator_damage_decisions',{}),trainer.entity_id:decision}
 return G.transition(engine,trainer,lambda e,t:t.spec.update(coordinator_damage_offer={'source':CLASS,'pokemon_id':pokemon.entity_id,'source_contract':contract(t,CLASS)}))


def capture_pool(engine,result):
 collector=getattr(engine,'_coordinator_damage_pools',None)
 if collector is not None:collector.append(deepcopy(result))
 return result


def _identity(value):
 if type(value)is float:
  if not __import__('math').isfinite(value):raise ValueError('finite actual Coordinator observation required')
  return {'native_float_hex':value.hex()}
 if hasattr(value,'entity_id'):return {'native_actor_id':value.entity_id}
 if hasattr(value,'_passive_events') and hasattr(value,'r'):return {'native_engine':True}
 if isinstance(value,dict):return {k:_identity(v) for k,v in value.items()}
 if isinstance(value,(list,tuple)):return [_identity(v) for v in value]
 if isinstance(value,(set,frozenset)):return sorted((_identity(v) for v in value),key=__import__('root_resolution').canonical)
 return value


def _damage_seal(row):
 return __import__('root_resolution').fingerprint(_identity({k:v for k,v in row.items() if k!='sha256'}))


def _prefix_facts(engine,row):
 prefix=row['prefix'];receipts=[]
 for token in prefix['completion_receipts']:
  receipt=engine._effect_dispatch_receipts.get(token)
  if receipt is None:raise ValueError('actual completed effect prefix receipt missing')
  receipts.append(_identity({k:receipt[k] for k in ('source_id','occurrence','actor','target','effect','status')}))
 return {'actor_id':row['actor_id'],'target_id':row['target_id'],'move_id':row['move_id'],'event_id':row['event_id'],'substitute':_identity(prefix['substitute']),'receipts':sorted(receipts,key=__import__('root_resolution').canonical)}


def recipient_prefix(engine,event_id,attacker,target,move_id,prefix=None):
 event=engine._passive_events.get(event_id)
 if event is None:return None
 if prefix is not None:
  if damage_offer(engine,attacker) is None:return None
  row={'actor_id':attacker.entity_id,'target_id':target.entity_id,'move_id':move_id,'event_id':event_id,'prefix':prefix}
  row['sha256']=__import__('root_resolution').fingerprint(_prefix_facts(engine,row));event['coordinator_recipient_prefix']=row
  return prefix
 row=event.get('coordinator_recipient_prefix')
 if row is None:return None
 if (row['sha256']!=__import__('root_resolution').fingerprint(_prefix_facts(engine,row)) or row['actor_id']!=attacker.entity_id or row['target_id']!=target.entity_id or row['move_id']!=move_id or row['event_id']!=event_id):raise ValueError('native Coordinator recipient prefix changed')
 return row['prefix']


def calculate_damage(engine,attacker,target,move,crit,set_damage,event,precision_facts):
 native=engine._passive_events.get(event.get('passive_event'))
 provider=damage_offer(engine,attacker)
 cached=None if native is None else native.get('coordinator_damage')
 if cached is not None:
  if cached.get('sha256')!=_damage_seal(cached) or cached['actor_id']!=attacker.entity_id or cached['target_id']!=target.entity_id or cached['move_id']!=move['id']:raise ValueError('actual observed Coordinator damage instance changed')
  memo={id(a):a for a in W.actor_index(engine).values()};memo[id(engine)]=engine
  event.update(deepcopy(cached['reaction_event'],memo));precision_facts.update(deepcopy(cached['precision_facts']))
  return choose_damage(engine,native,cached,event)
 if provider is None:return engine.roll_damage(attacker,target,move,crit,set_damage,_reaction_event=event,_precision_observation=precision_facts)
 if native is None:raise ValueError('Coordinator needs its actual native accuracy continuation')
 CF.owner(provider,attacker);require(engine,provider,CLASS)
 if set_damage:raise ValueError('Coordinator rerolls a Damage Roll, not Set Damage')
 engine._coordinator_damage_pools=[]
 try:
  first=engine.roll_damage(attacker,target,move,crit,set_damage,_reaction_event=event,_precision_observation=precision_facts)
  pools=engine._coordinator_damage_pools
 finally:engine.__dict__.pop('_coordinator_damage_pools',None)
 if not pools:return first
 row={'source':CLASS,'source_contract':contract(provider,CLASS),'trainer_id':provider.entity_id,'actor_id':attacker.entity_id,'target_id':target.entity_id,'move_id':move['id'],'event_id':native['id'],'first_damage':first,'pools':pools,'precision_facts':deepcopy(precision_facts),'reaction_event':deepcopy(event,{**{id(a):a for a in W.actor_index(engine).values()},id(engine):engine}),'scene':F.state(provider)['scene']}
 row['sha256']=_damage_seal(row);native['coordinator_damage']=row
 return choose_damage(engine,native,row,event)


def choose_damage(engine,native,row,event):
 import passive_events as P,observed_resolution as OBS,roll_pools as POOLS,combat_damage as DAMAGE
 index=W.actor_index(engine);trainer=index[row['trainer_id']];actor=index[row['actor_id']]
 if row.get('decision') is not None:
  event.update(row.get('selected_event',{}))
  return row['chosen_damage']
 callback=getattr(engine,'_coordinator_damage_decisions',{}).get(trainer.entity_id)
 preview={'event_id':native['id'],'move_id':row['move_id'],'pokemon_id':actor.entity_id,'first_damage':row['first_damage'],'pools':deepcopy(row['pools'])}
 try:
  if not callable(callback):raise ValueError('Coordinator observed Damage Roll requires fresh decision authentication after load')
  chosen=callback(preview)
  if type(chosen)is not bool:raise ValueError('explicit Coordinator Damage Roll choice required')
 except Exception as error:
  native['coordinator_choice_error']=str(error);native.update(status='pending',reason='coordinator_damage_pending');engine._passive_pending=native['id'];raise P.PassiveEventPending(native['id']) from error
 if not chosen:
  row.update(decision=False,chosen_damage=row['first_damage']);row['sha256']=_damage_seal(row);trainer.spec.pop('coordinator_damage_offer',None)
  return row['first_damage']
 try:
  CF.owner(trainer,actor);require(engine,trainer,CLASS)
  key=CLASS+(':'+actor.entity_id if source(engine.r,row['source_contract'],CLASS)['coordinator_scene']=='per_pokemon' else '')
  if not F.activation_allowed(trainer,key,{'kind':'scene'},engine=engine):raise ValueError('Coordinator Scene use exhausted')
  if row['scene']!=F.state(trainer)['scene']:raise ValueError('observed Coordinator Scene changed')
  __import__('contest').ContestEngine._stage_feature_cost(engine,trainer,0,CLASS)
 except Exception as error:
  native['coordinator_choice_error']=str(error);native.update(status='pending',reason='coordinator_damage_pending');engine._passive_pending=native['id'];raise P.PassiveEventPending(native['id']) from error
 # Reroll exactly the observed dice; retain every actual source modifier and
 # recompute the shared defense/scaling formula before any HP application.
 rerolled=[POOLS.pool(engine.rng,p['count'],sides=p['sides'],offset=p['offset']) for p in row['pools']]
 delta=sum(p['total'] for p in rerolled)-sum(p['total'] for p in row['pools'])
 formula=event['coordinator_formula'];dice=formula['dice']+delta
 total=dice+formula['attack']+formula['modifiers']
 new_fountain=__import__('type_ace').fountain(engine,actor,event['move'],total)
 defended=DAMAGE.defend(dice=dice,attack=formula['attack'],modifiers=formula['modifiers']+(new_fountain-total),defense=formula['defense'],reduction=formula['reduction'])
 normal=event['damage_formula'];normal['after_defense']=defended['after_defense']
 damage=DAMAGE.scale(after_defense=defended['after_defense'],type_multiplier=normal['multiplier'],other_multiplier=normal['other_multiplier'],adjustment=normal['adjustment'])
 resisted_mult=__import__('damage_reactions').resistance_multiplier(engine,normal['multiplier'])
 event.update(damage=damage,resisted_damage=None if resisted_mult is None else DAMAGE.scale(after_defense=defended['after_defense'],type_multiplier=resisted_mult,other_multiplier=normal['other_multiplier'],adjustment=normal['adjustment']))
 CF.trigger_free_action(engine,trainer,CLASS);F.consume_activation(trainer,key,{'kind':'scene'},engine=engine)
 row.update(decision=True,chosen_damage=damage,rerolled_pools=rerolled)
 row['selected_event']={'damage':event['damage'],'resisted_damage':event['resisted_damage'],'damage_formula':deepcopy(normal)}
 row['sha256']=_damage_seal(row)
 trainer.spec.pop('coordinator_damage_offer',None)
 engine.log('  '+actor.name+': Coordinator Damage Roll '+str(row['first_damage'])+' → '+str(damage),CLASS)
 return damage


def restore_damage_choice(engine,trainer,*,decision):
 W.require_actors(engine,trainer)
 if not callable(decision):raise ValueError('fresh Coordinator decision callback required')
 engine._coordinator_damage_decisions={**getattr(engine,'_coordinator_damage_decisions',{}),trainer.entity_id:decision}
 pending=engine._passive_pending
 if pending is None or engine._passive_events[pending].get('coordinator_damage',{}).get('trainer_id')!=trainer.entity_id:raise ValueError('actual pending Coordinator observation required')
 return __import__('passive_events').deliver(engine,pending)


def validate_world(engine,index):
 for actor in index.values():
  validate_spec(engine.r,actor.spec)
  if actor.spec.get('flexible_preparations'):
   import poffin_state as P
   flexible_projection(actor,P.history(actor),engine)
 for event in engine._passive_events.values():
  row=event.get('coordinator_damage')
  if row is None:continue
  if row.get('sha256')!=_damage_seal(row) or row['event_id']!=event['id'] or row['actor_id']!=event['actor'].entity_id or row['target_id']!=event['target'].entity_id or row['move_id']!=event['move_id'] or row['trainer_id'] not in index:raise ValueError('source-bound Coordinator damage observation changed')
  source(engine.r,row['source_contract'],CLASS)
 return True


def arm_tough_boon(engine,pokemon,move_id):
 W.require_actors(engine,pokemon)
 row=innovation_instance(engine.r,move_id)
 if not row or row['template']!=1 or row['contest_type']!='강인함':raise ValueError('actual Tough Boon required')
 if engine._active_turn_actor is pokemon:raise ValueError('arm Tough Boon before its actual turn starts')
 return G.transition(engine,pokemon,lambda e,p:p.spec.update(innovation_start_boon=move_id))


def start_turn(engine,pokemon):
 boon=pokemon.spec.get('innovation_attack_boon')
 if boon and boon['turn']!=pokemon.custom_conditions.get('combat_turn_serial',0):pokemon.spec.pop('innovation_attack_boon',None)
 mid=pokemon.spec.pop('innovation_start_boon',None)
 if mid is not None:
  engine._coordinator_start_boon_actor=pokemon
  try:spend_boon(engine,pokemon,move_id=mid)
  finally:engine.__dict__.pop('_coordinator_start_boon_actor',None)


def start_action_allowed(engine,actor,kind):
 return kind=='swift' and getattr(engine,'_coordinator_start_boon_actor',None) is actor and engine._active_turn_actor is actor and getattr(actor,'_turn_start_decisions_pending',False)


def range_spec(move,original):
 if not move.get('innovation_instance'):return original
 return __import__('custom_species').parse_range(move['range'])


def validate_contest(ce,known):
 uses=getattr(ce,'_adaptable_uses',{})
 if type(uses)is not dict:raise ValueError('actual Adaptable Contest ledger required')
 for uid,row in uses.items():
  if row.get('pokemon') not in known or row.get('trainer_id')!=uid or type(row.get('round'))is not int or row['round']<0 or type(row.get('contest_id'))is not str:raise ValueError('actual Adaptable Contest observation required')
  if len(set(row['moves']))!=2 or any(ce.r.move(m)['id']!=m for m in row['moves']):raise ValueError('actual Adaptable constituents required')
  source(ce.r,row['choice'],ADAPTABLE)
 plan=getattr(ce,'_adaptable_plan',None)
 if plan:
  if plan['pokemon'] not in [x[1] for x in ce._native_intro_bindings.values()]:raise ValueError('actual native Adaptable Pokemon required')
  adaptable_instance(ce.r,plan['move_id'])


def prevent_effect_loss(engine,actor,recipient,effect,context):
 if recipient is not actor:return False
 move=context.get('move',{})
 if not move.get('id'):return False
 canonical=engine.r.move(move['id'])
 if '반동' not in str(canonical.get('effect','')) and effect.get('keyword') not in ('Recoil','반동'):return False
 return any(r.get('innovation_prevent_loss') for r in __import__('combat_timing').records(actor))


def contest_skip(ce,contestant):
 uses=getattr(ce,'_adaptable_uses',{})
 if not uses:return False
 state,round_no=contest_round(ce)
 for row in uses.values():
  if row['pokemon'] is contestant and row['contest_id']==state['id'] and round_no==row['round']+1 and source(ce.r,row['choice'],ADAPTABLE)['adaptable_lock']=='all_moves':
   row['skipped_round']=round_no
   ce.log('  '+contestant.name+': 다음 라운드 모든 기술 사용 금지, 공연 없음',ADAPTABLE)
   return True
 return False
