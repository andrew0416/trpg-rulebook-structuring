"""PTK ch04:2131-2197 Survivalist whole-class template and its four remaining book clauses.

survivalist_features keeps terrain mastery, the terrain-bound +2, Plains Runner, Surefooted
and Cave Dweller sight (C04-090/C04-092 owners). This module adds the static acquisition
template for the class and its five Features, Trapper tools and their Hazard instances
(ch04:2156-2164), Wilderness Guide one-full-round orders (ch04:2166-2175), Adaptive
Geography as-if terrain for one turn (C04-093) and the remaining Terrain Talent effects
(C04-094). Lifetimes use combat_timing, frequencies use frequency, trap instances use
hazard_state, transactions use state_grants; nothing here overwrites actual world terrain.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import common_checks as C
import contest_features as F
import survivalist_features as V

_data=json.loads((Path(__file__).resolve().parents[1]/'data/survivalist-definitions.json').read_text(encoding='utf-8-sig'))
CLASS='class/생존가';NATURAL='feat/내추럴-파이터';TRAPPER='feat/트래퍼';GUIDE='feat/야생-가이드';TALENT='feat/지형-재능';ADAPTIVE='feat/지리-적응'
DEFINITIONS=_data['features']
STATIC_DEFINITIONS={CLASS:_data['class_definition'],**DEFINITIONS}
FEATURES=tuple(STATIC_DEFINITIONS)
TERRAINS=tuple(_data['terrains'])
TALENTS=_data['talents']['effects']
TRAPS=DEFINITIONS[TRAPPER]['traps']
BRANCHES=DEFINITIONS[GUIDE]['branches']
CYCLE=tuple(DEFINITIONS[ADAPTIVE]['cycle'])
ENVIRON=_data['environ_labels']
TOOLS='_survivalist_trap_tools'          # trainer.spec: consumable Trapper tools and their deployment receipts
GUIDE_HISTORY='_survivalist_guide_history'  # trainer.spec: Wilderness Guide activation receipts
TRAP_KIND=DEFINITIONS[TRAPPER]['hazard_kind']
DEPLOY_RULING=DEFINITIONS[TRAPPER]['deploy_action_ruling']['prompt_type']
DEPLOY_ACTIONS=tuple(DEFINITIONS[TRAPPER]['deploy_action_ruling']['choices'])
PUSH='maneuver/밀기';TRIP='maneuver/걸기';OPPORTUNITY='maneuver/기회-공격'
WEATHER_ALIASES={'snow':'hail'}


def _text(value,label):
 if type(value) is not str or not value.strip():raise ValueError(label+' required')
 return value


def definitions(rules):
 """Verify the printed Korean excerpts and catalog spans once per Rules instance."""
 cached=getattr(rules,'_survivalist_class_definitions',None)
 if cached is not None:return cached
 root=Path(rules.root);source=root/_data['source_file']
 if hashlib.sha256(source.read_bytes()).hexdigest()!=_data['source_sha256']:raise ValueError('Survivalist source file changed')
 lines=source.read_text(encoding='utf-8-sig').split('\n')
 def excerpt(span):return '\n'.join(lines[span[0]-1:span[1]])
 for uid,row in STATIC_DEFINITIONS.items():
  if hashlib.sha256(excerpt(row['span']).encode('utf-8')).hexdigest()!=row['excerpt_sha256']:raise ValueError('Survivalist printed clause changed: '+uid)
  unit=rules.selection.units.get(uid,{}).get('source',{})
  if unit.get('lines')!=row['catalog_span'] or unit.get('sha256')!=_data['source_sha256']:raise ValueError('Survivalist catalog source differs from the reviewed clause: '+uid)
 table=_data['talents']
 if hashlib.sha256(excerpt(table['span']).encode('utf-8')).hexdigest()!=table['excerpt_sha256']:raise ValueError('Terrain Talents table changed')
 if set(TALENTS)!=set(TERRAINS) or set(CYCLE)!=set(TERRAINS) or set(ENVIRON)!=set(TERRAINS):raise ValueError('Survivalist terrain tables disagree')
 rules._survivalist_class_definitions=_data
 return _data


# ---------------------------------------------------------------- acquisition template
def records(actor,feature=None,active=False):
 import trainer_feature_acquisition as T
 return [r['static_acquisition'] for _,r,live in T._static_records(actor)
  if r['static_acquisition']['feature_id'] in FEATURES and (feature is None or r['static_acquisition']['feature_id']==feature) and (not active or live)]


def acquired(actor,feature,rank=None):
 rows=[r for r in records(actor,feature,True) if rank is None or r['snapshot'].get('rank_number')==rank]
 if len(rows)>1:raise ValueError('one exact acquired Survivalist Feature required')
 return rows[0] if rows else None


def acquisition_snapshot(engine,actor,feature,rank=None):
 import skill_modifiers as S
 definitions(engine.r)
 if feature==TALENT:
  if rank not in (1,2):raise ValueError('explicit Terrain Talent rank 1 or 2 required')
 elif rank is not None:raise ValueError('this Survivalist Feature is not Ranked')
 snapshot={'survival':S.rank(engine.r,actor,'생존')[2],'parents':[] if feature==CLASS else [r['request_id'] for r in records(actor,CLASS,True)]}
 if feature==TALENT:
  snapshot['rank_number']=rank
  snapshot['previous']=None if rank==1 else (acquired(actor,TALENT,1) or {}).get('request_id')
  snapshot['mastered_terrains']=list(V.selected(engine,actor)) if F.owned(actor,CLASS) else []
 if feature==ADAPTIVE:
  snapshot['survivalist_features']=[r['request_id'] for r in records(actor,active=True)]
 return snapshot


def qualification(actor,feature,snapshot,prerequisite_source):
 import acquisition_qualification as Q
 d=STATIC_DEFINITIONS[feature]
 fields={'survival','parents'}|({'rank_number','previous','mastered_terrains'} if feature==TALENT else set())|({'survivalist_features'} if feature==ADAPTIVE else set())
 if prerequisite_source is not None or type(snapshot) is not dict or set(snapshot)!=fields:raise ValueError('exact Survivalist acquisition observations required')
 C.integer(snapshot['survival'],'Survival rank',0)
 known={r['request_id'] for r in records(actor,CLASS)}
 if feature!=CLASS and (not isinstance(snapshot['parents'],list) or not snapshot['parents'] or not set(snapshot['parents'])<=known):raise ValueError('Survivalist prerequisite required: actual acquired class')
 checks=[Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),
  Q.check('survival','prerequisite',snapshot['survival']>=d['survival_rank'],'printed Survival rank required')]
 if feature==TALENT:
  C.integer(snapshot['rank_number'],'Terrain Talent rank',1,2)
  if snapshot['rank_number']==2:
   prior=next((r for r in records(actor,TALENT) if r['request_id']==snapshot['previous']),None)
   if prior is None or prior['snapshot'].get('rank_number')!=1:raise ValueError('actual first Terrain Talent rank required')
  elif snapshot['previous'] is not None:raise ValueError('first Terrain Talent rank has no prior rank')
  mastered=snapshot['mastered_terrains']
  if not isinstance(mastered,list) or any(t not in TERRAINS for t in mastered) or len(set(mastered))!=len(mastered):raise ValueError('actual mastered Survivalist terrains required')
  need=d['mastered_terrains_per_rank']*snapshot['rank_number']
  checks.append(Q.check('terrains','prerequisite',len(mastered)>=need,'Terrain Talent rank requires '+str(need)+' mastered terrains'))
 if feature==ADAPTIVE:
  ids=snapshot['survivalist_features'];actual={r['request_id'] for r in records(actor)}
  if not isinstance(ids,list) or len(set(ids))!=len(ids) or not set(ids)<=actual:raise ValueError('actual acquired Survivalist Feature receipts required')
  checks.append(Q.check('features','prerequisite',len(ids)>=d['survivalist_features'],'four acquired Survivalist Features required'))
 return Q.require(feature,'native','acquire',checks)


def _require(e,a,uid):
 """Actual conscious class owner with every owned child's printed prerequisite, plus the used Feature."""
 definitions(e.r)
 V.feature_count(e,a)
 if not F.owned(a,uid):raise ValueError('acquired source required: '+uid)
 F.require(e,a,uid)


def adjacent(a,b):
 i=CYCLE.index(a);return b in (CYCLE[(i-1)%len(CYCLE)],CYCLE[(i+1)%len(CYCLE)])


# ---------------------------------------------------------------- Adaptive Geography (C04-093)
def _adaptive_rows(actor):
 import combat_timing as T
 return [r for r in T.records(actor) if r.get('adaptive_geography') is not None]


def as_if(engine,actor):
 """The live one-turn as-if choice of this actor, never the actual world terrain."""
 rows=_adaptive_rows(actor)
 if not rows:return None
 if len(rows)>1:raise ValueError('one Adaptive Geography choice per turn required')
 return rows[0]['adaptive_geography']


def effective_terrains(engine,actor,terrains):
 row=as_if(engine,actor)
 values=tuple(terrains)
 if row is None or row['actual_terrain'] not in values:return values
 return tuple(dict.fromkeys(row['as_if_terrain'] if t==row['actual_terrain'] else t for t in values))


def effective_cell_terrains(engine,actor,types):
 """Naturewalk reads an observed cell as the adjacent as-if terrain during the chosen turn."""
 if not isinstance(types,list):return types
 row=as_if(engine,actor)
 if row is None or row['actual_terrain'] not in types:return types
 return list(dict.fromkeys(row['as_if_terrain'] if t==row['actual_terrain'] else t for t in types))


def effective_environment(engine,actor):
 env=V.current_environment(engine,actor)
 if env is None:return None
 row=as_if(engine,actor)
 return dict(env,terrains=effective_terrains(engine,actor,env['terrains']),adaptive_geography=deepcopy(row))


def environ_as_if(engine,actor,environ):
 """Environ keyword Moves select the as-if biome; the actual biome stays in the selection."""
 row=as_if(engine,actor)
 if row is None or ENVIRON[row['actual_terrain']]!=environ:return environ,None
 return ENVIRON[row['as_if_terrain']],{'actual_environ':environ,'as_if_environ':ENVIRON[row['as_if_terrain']],'owner_id':row['owner_id'],'subject_id':row['subject_id'],'round':row['round'],'turn_serial':row['turn_serial']}


def environ_selection_actual(selection):
 row=selection.get('adaptive_geography')
 if row is None:return selection['environ']
 if (type(row) is not dict or set(row)!={'actual_environ','as_if_environ','owner_id','subject_id','round','turn_serial'}
     or row['as_if_environ']!=selection['environ'] or row['actual_environ'] not in ENVIRON.values()):raise ValueError('prepared Environ as-if selection changed')
 actual=next(k for k,v in ENVIRON.items() if v==row['actual_environ']);chosen=next(k for k,v in ENVIRON.items() if v==row['as_if_environ'])
 if not adjacent(actual,chosen):raise ValueError('prepared Environ as-if terrain is not adjacent')
 return row['actual_environ']


def adaptive_geography(e,a,*,terrain_name,reason,target=None,actual_terrain=None):
 import state_grants as G
 _text(reason,'GM Adaptive Geography reason')
 subject=a if target is None else target
 if subject is not a and (subject.kind!='pokemon' or subject.spec.get('trainer_id')!=a.spec.get('id')):raise ValueError('Adaptive Geography targets you or your own Pokemon')
 def apply(staged,actor,*others):
  import frequency as FREQ,action_lifecycle as ACTION,combat_timing as T
  who=others[0] if others else actor
  _require(staged,actor,ADAPTIVE)
  if who is not actor:F.owner(actor,who)
  if _adaptive_rows(who):raise ValueError('Adaptive Geography already shaped this turn')
  if not staged.encounter_active or getattr(staged,'_active_turn_actor',None) is not who or getattr(who,'_action_history',[]):
   raise ValueError('Adaptive Geography triggers only as you or your Pokemon gain Initiative, before any action of that turn')
  env=V.current_environment(staged,who)
  if env is None:raise ValueError('actual current terrain required for Adaptive Geography')
  chosen=V.terrain(terrain_name)
  if actual_terrain is None:
   candidates=[t for t in env['terrains'] if adjacent(t,chosen)]
   if len(candidates)!=1:raise ValueError('choose one actual current terrain adjacent to the as-if terrain on the printed cycle')
   actual=candidates[0]
  else:
   actual=V.terrain(actual_terrain)
   if actual not in env['terrains'] or not adjacent(actual,chosen):raise ValueError('as-if terrain must be adjacent to an actual current terrain on the printed cycle')
  freq=DEFINITIONS[ADAPTIVE]['frequency']
  if not FREQ.activation_allowed(actor,ADAPTIVE,freq,engine=staged):raise ValueError('Adaptive Geography Scene frequency exhausted')
  ACTION.triggered_free_action(staged,actor,ADAPTIVE)
  FREQ.consume_activation(actor,ADAPTIVE,freq,engine=staged)
  serial=C.integer(who.custom_conditions.get('combat_turn_serial',0),'actual owner turn serial',0)
  payload={'owner_id':actor.entity_id,'subject_id':who.entity_id,'actual_terrain':actual,'as_if_terrain':chosen,'round':staged.round_no,'turn_serial':serial,'environment_source':env['source'],'reason':reason}
  T.install(staged,who,{'source':ADAPTIVE,'turn_owner':who,'turn_deadline':serial,'encounter_end':True,'adaptive_geography':payload})
  staged.log('  '+actor.name+': 지리 적응 → '+who.name+' '+actual+'에서 '+chosen+'처럼 이번 턴 행동',ADAPTIVE)
  return deepcopy(payload)
 return G.transition(e,a,apply,participants=() if subject is a else (subject,))


# ---------------------------------------------------------------- Wilderness Guide (ch04:2166-2175)
def _guide_rows(actor):
 import combat_timing as T
 return [r for r in T.records(actor) if r.get('wilderness_guide') is not None]


def _branches(actor):
 return {r['wilderness_guide']['branch'] for r in _guide_rows(actor)}


def _allies(engine,actor):
 import world_entities as W
 if getattr(actor,'side',None) is None:raise ValueError('Wilderness Guide requires an actual side')
 return [t for t in W.actor_index(engine).values() if t is not actor and t.kind in ('trainer','pokemon') and t.side==actor.side
         and getattr(t,'on_field',True) and not t.captured and not t.fainted]


def wilderness_guide(e,a,*,terrain_name,reason):
 import state_grants as G
 _text(reason,'GM Wilderness Guide reason')
 _require(e,a,GUIDE)
 allies=_allies(e,a)
 if not allies:raise ValueError('Wilderness Guide requires an actual ally on the field')
 def apply(staged,actor,*targets):
  import frequency as FREQ,turn as TURN,combat_timing as T
  _require(staged,actor,GUIDE)
  if not staged.encounter_active or not getattr(actor,'on_field',True):raise ValueError('Wilderness Guide requires an actual encounter turn')
  env=effective_environment(staged,actor)
  if env is None:raise ValueError('GM current environment required for Wilderness Guide')
  terrain=V.terrain(terrain_name)
  if terrain not in env['terrains']:raise ValueError('Wilderness Guide terrain must be the actual current terrain')
  branch=next(name for name,row in BRANCHES.items() if terrain in row['terrains'])
  if any(_guide_rows(t) for t in targets):raise ValueError('overlapping Wilderness Guide needs an explicit composition policy')
  freq=DEFINITIONS[GUIDE]['frequency']
  if not FREQ.activation_allowed(actor,GUIDE,freq,engine=staged):raise ValueError('Wilderness Guide Scene frequency exhausted')
  count=T.current(staged)
  if not TURN.spend(staged,actor,'standard','야생 가이드: '+terrain):raise ValueError('Wilderness Guide Standard Action unavailable')
  FREQ.consume_activation(actor,GUIDE,freq,engine=staged)
  sequence=len(actor.spec.get(GUIDE_HISTORY,[]))+1
  receipt={'sequence':sequence,'source':GUIDE,'owner_id':actor.entity_id,'terrain':terrain,'branch':branch,'round':staged.round_no,'count':count,
   'seconds':staged.elapsed_seconds,'reason':reason,'allies':[t.entity_id for t in targets],'environment_source':env['source'],'as_if':deepcopy(env.get('adaptive_geography'))}
  actor.spec.setdefault(GUIDE_HISTORY,[]).append(receipt)
  row=BRANCHES[branch]
  for t in targets:
   record={'source':GUIDE,'count_deadline':(staged.round_no+1,count),'encounter_end':True,
    'wilderness_guide':{'owner_id':actor.entity_id,'sequence':sequence,'branch':branch,'terrain':terrain,'round':staged.round_no,'count':count}}
   if row.get('evasion'):record.update(effect_contract=True,evasion_modifier=row['evasion'])
   if row.get('damage_reduction'):record.update(effect_contract=True,damage_reduction=row['damage_reduction'])
   T.install(staged,t,record)
  staged.log('  '+actor.name+': 야생 가이드 ('+terrain+') → '+', '.join(t.name for t in targets)+' 1라운드',GUIDE)
  return deepcopy(receipt)
 return G.transition(e,a,apply,participants=tuple(allies))


def ignores_hazards(engine,actor):
 return GUIDE if 'mountain_cave' in _branches(actor) else None


def low_light_sight(engine,actor):
 return 'mountain_cave' in _branches(actor)


def ignored_ability_evasion(engine,attacker,target):
 """Evasion that a desert/tundra-guided attacker ignores: the foe's printed Sand Veil/Snow Cloak passives."""
 if 'desert_tundra' not in _branches(attacker) or target.side==attacker.side:return 0
 row=BRANCHES['desert_tundra'];ids=set(row['ignored_abilities']);names=set(row['ignored_ability_names'])
 total=0
 for effect in getattr(target,'registry',[]):
  if not isinstance(effect,dict) or effect.get('type')!='evasion_mod' or type(effect.get('value')) is not int:continue
  if effect.get('_rule_id') in ids or effect.get('_ability') in names:total+=effect['value']
 return total


def accuracy_bonus(engine,attacker,target,move):
 if 'urban' not in _branches(attacker) or move.get('id') not in BRANCHES['urban']['maneuvers']:return 0
 return BRANCHES['urban']['maneuver_bonus']


def maneuver_skill_options(engine,actor,source,options):
 if 'urban' not in _branches(actor) or source not in BRANCHES['urban']['maneuvers']:return options
 import composition_derive as COMPOSITION
 out=dict(options or {});extra=out.get('mods',0);C.integer(extra,'maneuver modifier')
 out['mods']=COMPOSITION.derive(extra,[{'id':GUIDE,'source':GUIDE,'value':BRANCHES['urban']['maneuver_bonus']}],[{'law':'add','contributors':[GUIDE]}])['value']
 return out


# ---------------------------------------------------------------- Terrain Talent effects (C04-094)
def talent_set(engine,actor):
 """Verified chosen talents of a conscious Survivalist; an unconscious trainer projects no static talent effect."""
 if actor.kind!='trainer' or actor.dead or actor.fainted or actor.hp<=0 or not F.owned(actor,V.SURVIVALIST) or not F.owned(actor,V.TALENT):return ()
 return V.talents(engine,actor)


def talent_projection(actor):
 """Engine-free read of the chosen talents for capability/jump/breath projections; consumers with an engine verify through talent_set."""
 if actor.kind!='trainer' or not F.owned(actor,V.SURVIVALIST) or not F.owned(actor,V.TALENT):return ()
 record=actor.spec.get('_survivalist_talents')
 if not isinstance(record,dict) or record.get('source')!=V.TALENT or record.get('rank')!=actor.spec.get('feat_ranks',{}).get(V.TALENT):return ()
 values=record.get('terrains')
 if not isinstance(values,(list,tuple)) or any(v not in TERRAINS for v in values):return ()
 if V.CSV_STATE in actor.spec:
  state=actor.spec[V.CSV_STATE]
  if not isinstance(state,dict) or state.get('active') is None:return ()
 return tuple(values)


def capability_contributions(actor):
 """Forest Ranger and a grassland/forest Wilderness Guide round grant the Stealth Capability."""
 if actor.kind not in ('trainer','pokemon'):return []
 values=[]
 if 'forest' in talent_projection(actor):values.append(TALENTS['forest']['capability'])
 if 'grassland_forest' in _branches(actor):values.append(BRANCHES['grassland_forest']['stealth_capability'])
 return list(dict.fromkeys(values))


def movement(engine,actor,values,*,talents=None):
 """Deep Diver Swim equals Overland; a Wilderness Guide round adds +2 Overland or +2 Swim."""
 result=dict(values)
 if 'ocean' in (talent_set(engine,actor) if talents is None else talents):
  import trainer_capabilities as TRAINER
  C.integer(result.get('land'),'actual land movement',0)
  result['swim']=TRAINER.swimming(actor,result['land'],base_swim=result['land'])
 for branch in _branches(actor):
  row=BRANCHES[branch]
  if row.get('land'):
   C.integer(result.get('land'),'actual land movement',0);result['land']+=row['land']
  if row.get('swim') and result.get('swim',0)>0:result['swim']+=row['swim']
 return result


def breath_seconds(actor,medium,engine=None):
 if medium!='water':return 0
 talents=talent_set(engine,actor) if engine is not None else talent_projection(actor)
 if 'ocean' not in talents:return 0
 import skill_modifiers as S
 return 60*TALENTS['ocean']['breath_minutes_per_survival_rank']*S.effective_rank(actor.r,actor,'생존')


def jump_bonus(actor):
 bonus=TALENTS['urban']['jump'] if 'urban' in talent_projection(actor) else 0
 return {'high_jump':bonus,'long_jump':bonus}


def weather_hp_immune(engine,actor,weather):
 if 'desert_tundra' in _branches(actor):return GUIDE
 talents=talent_set(engine,actor);weather=WEATHER_ALIASES.get(weather,weather)
 for terrain in ('tundra','desert'):
  if terrain in talents and weather in TALENTS[terrain]['weather_immune']:return TALENT+':'+terrain
 return None


def status_immune(engine,actor,condition,source):
 talents=talent_set(engine,actor)
 if 'tundra' in talents and condition in TALENTS['tundra']['status_immune']:return TALENT+':tundra'
 if 'desert' in talents and source in TALENTS['desert']['move_effect_immune']:return TALENT+':desert'
 return None


def damage_reduction(engine,attacker,target,move):
 talents=talent_set(engine,target);total=0
 for terrain in ('tundra','desert'):
  row=TALENTS[terrain]['damage_reduction']
  if terrain in talents and move.get('type')==row['type']:total+=row['value']
 return total


def poison_hp_immune(engine,actor):
 return 'wetland' in talent_set(engine,actor)


def poison_stage_delta(engine,actor,condition,delta):
 if condition!='독' or type(delta) is not int or delta>=0 or 'wetland' not in talent_set(engine,actor):return delta
 return -min(abs(delta),TALENTS['wetland']['poison_stage_loss'])


def stealth_rock_immune(engine,actor):
 return 'cave' in talent_set(engine,actor)


def evasion_bonus(engine,target,attacker,move):
 """Traceur: half the Survival rank against Push, Trip and Attack of Opportunity."""
 if 'urban' not in talent_set(engine,target):return 0
 scope=getattr(engine,'_opportunity_attack',None)
 opportunity=(isinstance(scope,dict) and scope.get('source')==OPPORTUNITY and scope.get('attacker_id')==attacker.entity_id and scope.get('target_id')==target.entity_id)
 if move.get('id') not in (PUSH,TRIP) and not opportunity:return 0
 import skill_modifiers as S
 return S.effective_rank(engine.r,target,'생존')//2


# ---------------------------------------------------------------- Trapper (ch04:2156-2164)
def _tools(actor):
 rows=actor.spec.get(TOOLS,[])
 if not isinstance(rows,list):raise ValueError('Trapper tools must be a list')
 return rows


def _tool(actor,tool_id):
 _text(tool_id,'Trapper tool identity')
 rows=[row for row in _tools(actor) if isinstance(row,dict) and row.get('id')==tool_id]
 if len(rows)!=1:raise ValueError('actual owned Trapper tool required: '+tool_id)
 return rows[0]


def hazard_definition(rules,source_id,data):
 if not isinstance(source_id,str) or not source_id.startswith(TRAPPER+'#'):return None
 parts=source_id.split('#')
 if len(parts)!=3 or parts[1] not in TRAPS or parts[2] not in TRAPS[parts[1]]['terrains']:raise ValueError('actual Trapper trap identity required')
 definitions(rules);row=DEFINITIONS[TRAPPER]
 return {'clause_id':row['clause_id'],'source_row_sha256':row['excerpt_sha256'],'name':TRAPS[parts[1]]['korean'],'kind':TRAP_KIND,'trigger':'enter_cell','trigger_range':0,'slow':False}


def _placement(engine,actor,cells):
 import body_state as BODY
 from grid import cheb
 spec=DEFINITIONS[TRAPPER]['placement']
 if engine.grid is None:raise ValueError('Trapper Hazards require an actual map')
 if not isinstance(cells,(list,tuple)):raise ValueError('Trapper placement requires an explicit cell list')
 points=[]
 for value in cells:
  if not isinstance(value,(list,tuple)) or len(value)!=2:raise ValueError('Trapper placement requires explicit coordinate pairs')
  point=tuple(C.integer(x,'Trapper cell coordinate') for x in value)
  if not engine.grid.inside(point):raise ValueError('Trapper placement cell lies outside the map')
  points.append(point)
 if len(points)!=spec['cells'] or len(set(points))!=len(points):raise ValueError('Trapper tool creates exactly %d distinct metres of Hazard'%spec['cells'])
 origins=BODY.cells(actor,require_complete=True)
 if any(min(cheb(origin,point) for origin in origins)>spec['within'] for point in points):raise ValueError('Trapper Hazard cell is outside %d metres'%spec['within'])
 for point in points:
  if not any(other!=point and cheb(other,point)==1 for other in points):raise ValueError('every Trapper Hazard metre must be adjacent to another')
 return points


def create_trap_tool(e,a,*,tool_id,terrain_name,minutes,reason):
 import state_grants as G
 _text(tool_id,'Trapper tool identity');_text(reason,'GM Extended Action reason');C.integer(minutes,'GM Extended Action minutes',1)
 def apply(staged,actor):
  import frequency as FREQ,action_lifecycle as ACTION,pokemon_activities as P
  _require(staged,actor,TRAPPER);P._outside(staged)
  if any(row.get('id')==tool_id for row in _tools(actor)):raise ValueError('duplicate Trapper tool identity')
  env=V.current_environment(staged,actor);terrain=V.terrain(terrain_name)
  if env is None or terrain not in env['terrains']:raise ValueError('Trapper tool terrain must be the actual current terrain')
  kind=next(name for name,row in TRAPS.items() if terrain in row['terrains'])
  freq=DEFINITIONS[TRAPPER]['frequency']
  if not FREQ.activation_allowed(actor,TRAPPER,freq,engine=staged):raise ValueError('Trapper daily frequency exhausted')
  if not ACTION.status_permission(staged,actor,'extended'):raise ValueError('Extended Action permission unavailable')
  FREQ.consume_activation(actor,TRAPPER,freq,engine=staged)
  paid=deepcopy(FREQ.state(actor)['activations'][TRAPPER]);started=staged.elapsed_seconds
  staged.advance_time(minutes*60,[actor]);ACTION.record_action(staged,actor,'extended')
  record={'id':tool_id,'source':TRAPPER,'owner_id':actor.entity_id,'terrain':terrain,'kind':kind,'created_day':FREQ.state(actor)['day'],
   'started_seconds':started,'created_seconds':staged.elapsed_seconds,'minutes':minutes,'reason':reason,'frequency':paid,'environment_source':env['source'],'status':'ready','used':None}
  actor.spec.setdefault(TOOLS,[]).append(record)
  staged.log('  '+actor.name+': 트래퍼 도구 제작 '+tool_id+' ('+TRAPS[kind]['korean']+', '+terrain+')',TRAPPER)
  return deepcopy(record)
 return G.transition(e,a,apply)


def tool_usable(actor,tool):
 import frequency as FREQ
 if tool['status']!='ready':return 'Trapper tool already used'
 if FREQ.state(actor)['day']!=tool['created_day']:return 'Trapper tool lost all effect: not used on the day it was created'
 return None


def deploy_trap_tool(e,a,*,tool_id,cells,reason):
 import state_grants as G
 _text(reason,'GM Trapper deployment reason')
 _require(e,a,TRAPPER);tool=_tool(a,tool_id)
 problem=tool_usable(a,tool)
 if problem:raise ValueError(problem)
 if not e.encounter_active:raise ValueError('Trapper Hazards require an actual encounter')
 _placement(e,a,cells)
 answer=e.rulings.decide({'type':DEPLOY_RULING,'actor':a.name,'tool_id':tool_id,'text':DEFINITIONS[TRAPPER]['deploy_action_ruling']['question']})
 if answer is None:return C.PendingDecision('GM ruling '+DEPLOY_RULING+' ('+'|'.join(DEPLOY_ACTIONS)+') required: the printed Trapper text gives no deployment action cost')
 if answer not in DEPLOY_ACTIONS:raise ValueError('Trapper deployment action ruling must be one of '+', '.join(DEPLOY_ACTIONS))
 def apply(staged,actor):
  import hazard_state as H,turn as TURN,world_entities as W
  _require(staged,actor,TRAPPER);live=_tool(actor,tool_id)
  problem=tool_usable(actor,live)
  if problem:raise ValueError(problem)
  index=W.actor_index(staged)
  if index.get(actor.entity_id) is not actor or not getattr(actor,'on_field',True) or actor.captured:raise ValueError('actual on-field Trapper required')
  if not staged.encounter_active:raise ValueError('Trapper Hazards require an actual encounter')
  points=_placement(staged,actor,cells)
  if not TURN.spend(staged,actor,answer,'트래퍼 도구 사용: '+tool_id):raise ValueError('Trapper deployment action unavailable')
  source_id=TRAPPER+'#'+live['kind']+'#'+live['terrain']
  region=H._install_region(staged,actor,source_id,hazard_definition(staged.r,source_id,None),set(points),index)
  live['status']='used'
  live['used']={'seconds':staged.elapsed_seconds,'round':staged.round_no,'region_id':region,'cells':[list(p) for p in sorted(points)],'action':answer,'ruling':DEPLOY_RULING,'reason':reason}
  return deepcopy(live)
 return G.transition(e,a,apply,include_grid=True)


def hazard_entry(engine,actor,cell,instances):
 """Resolve Trapper Hazards on an entering foe and return the remaining instances."""
 import hazard_state as H,movement_actions as M
 mine=[row for row in instances if row['kind']==TRAP_KIND]
 if not mine:return instances
 for instance in mine:
  if instance['trigger']!='enter_cell' or not H._hostile(instance,actor):continue
  _,kind,terrain=instance['source_id'].split('#');trap=TRAPS[kind];owner=H._owner(engine,instance)
  if terrain in M.naturewalk_terrains(engine,actor):
   engine.log('    %s: %s 자연걸음으로 %s 효과 면역'%(actor.name,terrain,instance['name']),TRAPPER);continue
  duration=DEFINITIONS[TRAPPER]['slow_duration']
  if trap.get('replaces_slow'):
   H._dispatch(engine,owner,actor,instance,[{'type':'apply_status','status':trap['status'],'target':'target','duration':duration}])
  else:
   H._slow(engine,owner,actor,instance)
   if trap.get('status'):H._dispatch(engine,owner,actor,instance,[{'type':'apply_status','status':trap['status'],'target':'target','duration':duration}])
   if trap.get('stages'):H._dispatch(engine,owner,actor,instance,[{'type':'stage_change','stat':stat,'delta':delta,'target':'target'} for stat,delta in trap['stages'].items()])
  H._remove(engine,[instance['id']])
  engine.log('    %s: %s 발동 후 파괴'%(actor.name,instance['name']),TRAPPER)
 return [row for row in instances if row['kind']!=TRAP_KIND]


# ---------------------------------------------------------------- validation
def _validate_tools(engine,actor,index):
 import frequency as FREQ
 ids=set();rows=_tools(actor)
 if rows and actor.kind!='trainer':raise ValueError('Trapper tools belong to trainers')
 for row in rows:
  if type(row) is not dict or set(row)!={'id','source','owner_id','terrain','kind','created_day','started_seconds','created_seconds','minutes','reason','frequency','environment_source','status','used'}:raise ValueError('exact Trapper tool receipt required')
  _text(row['id'],'Trapper tool identity')
  if row['id'] in ids:raise ValueError('duplicate Trapper tool identity')
  ids.add(row['id'])
  if row['source']!=TRAPPER or row['owner_id']!=actor.entity_id or row['terrain'] not in TERRAINS or row['kind'] not in TRAPS or row['terrain'] not in TRAPS[row['kind']]['terrains']:raise ValueError('Trapper tool provenance changed')
  C.integer(row['created_day'],'Trapper tool day',0);started=C.integer(row['started_seconds'],'Trapper tool start',0);finished=C.integer(row['created_seconds'],'Trapper tool completion',0)
  minutes=C.integer(row['minutes'],'Trapper Extended Action minutes',1);_text(row['reason'],'Trapper tool reason')
  if finished-started!=minutes*60 or finished>engine.elapsed_seconds or row['created_day']>FREQ.state(actor)['day']:raise ValueError('Trapper tool clock receipt changed')
  if type(row['frequency']) is not dict or row['frequency'].get('kind')!='daily':raise ValueError('Trapper daily activation receipt changed')
  if row['status'] not in ('ready','used') or (row['status']=='used')!=(row['used'] is not None):raise ValueError('Trapper tool status changed')
  if row['used'] is not None:
   used=row['used']
   if type(used) is not dict or set(used)!={'seconds','round','region_id','cells','action','ruling','reason'} or used['action'] not in DEPLOY_ACTIONS or used['ruling']!=DEPLOY_RULING:raise ValueError('Trapper deployment receipt changed')
   C.integer(used['seconds'],'Trapper deployment time',finished);C.integer(used['round'],'Trapper deployment round',0);_text(used['region_id'],'Trapper region');_text(used['reason'],'Trapper deployment reason')
   if type(used['cells']) is not list or len(used['cells'])!=DEFINITIONS[TRAPPER]['placement']['cells']:raise ValueError('Trapper deployment cells changed')


def _validate_guide_history(engine,actor):
 rows=actor.spec.get(GUIDE_HISTORY,[])
 if not isinstance(rows,list):raise ValueError('Wilderness Guide history must be a list')
 if rows and actor.kind!='trainer':raise ValueError('Wilderness Guide history belongs to trainers')
 for n,row in enumerate(rows,1):
  if type(row) is not dict or set(row)!={'sequence','source','owner_id','terrain','branch','round','count','seconds','reason','allies','environment_source','as_if'}:raise ValueError('exact Wilderness Guide receipt required')
  if row['sequence']!=n or row['source']!=GUIDE or row['owner_id']!=actor.entity_id or row['branch'] not in BRANCHES or row['terrain'] not in BRANCHES[row['branch']]['terrains']:raise ValueError('Wilderness Guide receipt provenance changed')
  C.integer(row['round'],'Wilderness Guide round',0);C.integer(row['count'],'Wilderness Guide initiative count');_text(row['reason'],'Wilderness Guide reason')
  if C.integer(row['seconds'],'Wilderness Guide time',0)>engine.elapsed_seconds or type(row['allies']) is not list or not row['allies']:raise ValueError('Wilderness Guide receipt changed')


def _validate_records(engine,actor,index):
 for record in _guide_rows(actor):
  row=record['wilderness_guide']
  if type(row) is not dict or set(row)!={'owner_id','sequence','branch','terrain','round','count'} or row['branch'] not in BRANCHES or row['terrain'] not in BRANCHES[row['branch']]['terrains']:raise ValueError('Wilderness Guide record changed')
  owner=index.get(row['owner_id'])
  if owner is None or owner.kind!='trainer' or owner is actor:raise ValueError('Wilderness Guide record owner changed')
  history=owner.spec.get(GUIDE_HISTORY,[])
  if not any(isinstance(h,dict) and h.get('sequence')==row['sequence'] and h.get('branch')==row['branch'] and actor.entity_id in h.get('allies',[]) for h in history):raise ValueError('Wilderness Guide record has no owner receipt')
  branch=BRANCHES[row['branch']]
  if record.get('evasion_modifier',0)!=branch.get('evasion',0) or record.get('damage_reduction',0)!=branch.get('damage_reduction',0):raise ValueError('Wilderness Guide numeric projection changed')
 rows=_adaptive_rows(actor)
 if len(rows)>1:raise ValueError('one Adaptive Geography choice per turn required')
 for record in rows:
  row=record['adaptive_geography']
  if type(row) is not dict or set(row)!={'owner_id','subject_id','actual_terrain','as_if_terrain','round','turn_serial','environment_source','reason'}:raise ValueError('Adaptive Geography record changed')
  if row['subject_id']!=actor.entity_id or record.get('turn_owner') is not actor or row['actual_terrain'] not in TERRAINS or row['as_if_terrain'] not in TERRAINS or not adjacent(row['actual_terrain'],row['as_if_terrain']):raise ValueError('Adaptive Geography as-if terrain changed')
  owner=index.get(row['owner_id'])
  if owner is None or owner.kind!='trainer' or (owner is not actor and actor.spec.get('trainer_id')!=owner.spec.get('id')):raise ValueError('Adaptive Geography owner changed')


def validate_world(engine,index=None):
 import world_entities as W
 index=W.actor_index(engine) if index is None else index
 for actor in index.values():
  _validate_tools(engine,actor,index);_validate_guide_history(engine,actor);_validate_records(engine,actor,index)
 return True
