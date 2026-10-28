"""Aura Guardian source adapters over actual acquisitions, grants and native Moves."""
from copy import deepcopy
from hashlib import sha256
import state_grants as G
import common_checks as C

CLASS='class/파동술사';READER='feat/파동-감지자';POWER='feat/파동의-힘'
SWORD='feat/육체와-영혼의-칼';AMBIENT='feat/주위의-파동';MASTERY='feat/파동-통달'
STORM='ability/파동바람';STORM_TEST='ability/파동바람-playtest';SCRAPPY='ability/배짱'
SOURCE_SHA256='a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'
FEATURES={CLASS:(2781,2783),READER:(2785,2789),POWER:(2791,2796),SWORD:(2798,2803),AMBIENT:(2805,2813),MASTERY:(2815,2819)}
MOVES={CLASS:('move/판별','move/진공파','move/발경'),MASTERY:('move/파동탄','move/기합구슬','move/드레인펀치','move/힘껏펀치')}
DEFINITIONS={u:{'span':list(span),'catalog_span':[2767,2767] if u==CLASS else list(span),
 'clause_id':'C04-061' if u==SWORD else 'input/ch04-trainer-classes.md:'+str(span[0])+'-'+str(span[1]),
 'parent':READER if u==AMBIENT else None if u==CLASS else CLASS,'ranked':u==POWER,
 'minimum_rank':5 if u in (AMBIENT,MASTERY) else 4 if u==SWORD else 0,
 'stat_tags':['atk','spa']} for u,span in FEATURES.items()}


def records(actor,feature=None,active=False):
 import trainer_feature_acquisition as T
 return [record for _, record in T.static_family_acquisitions(actor, FEATURES, feature, active=active)]


def acquired(actor,feature):
 rows=records(actor,feature,True)
 return rows[-1] if rows else None


def acquisition_snapshot(e,actor,feature,rank,selection):
 import skill_modifiers as SK,elemental_connection as ELEMENTAL
 if type(selection)is not dict:raise ValueError('explicit Aura Guardian stat tag and printed choices required')
 expected={'stat'}|({'moves'} if feature in MOVES else {'ability'} if feature==POWER else set())
 if set(selection)!=expected or selection['stat'] not in ('atk','spa'):raise ValueError('printed Aura Guardian selection and Attack or Special Attack stat tag required')
 chosen=deepcopy(selection)
 if feature in MOVES:
  import class_move_grants as MOVE
  chosen['moves']=MOVE._pair(e.r,chosen['moves'],MOVES[feature])
 if feature==POWER:
  allowed=[SCRAPPY,e.r._selected_rule(STORM)]
  if chosen['ability'] not in allowed:raise ValueError('select exact Scrappy or selected Aura Storm identity')
  if any(r['snapshot']['selection']['ability']==chosen['ability'] for r in records(actor,POWER,True)):raise ValueError('distinct Power of Aura Ability per rank required')
 parent=DEFINITIONS[feature]['parent']
 return {'rank':SK.rank(e.r,actor,'직감')[2], 'rank_number':rank if feature==POWER else None,
  'parents':[r['request_id'] for r in records(actor,parent,True)] if parent else [],
  'elemental':list(ELEMENTAL.choices(e,actor)) if feature==CLASS else [],'selection':chosen}


def qualification(actor,feature,snapshot,prerequisite_source):
 import acquisition_qualification as Q
 if prerequisite_source is not None or type(snapshot)is not dict or set(snapshot)!={'rank','rank_number','parents','elemental','selection'}:raise ValueError('exact Aura Guardian acquisition observations required')
 C.integer(snapshot['rank'],'actual Intuition prerequisite rank',1)
 d=DEFINITIONS[feature];parent=d['parent'];known={r['request_id'] for r in records(actor,parent)} if parent else set()
 selection=snapshot['selection'];expected={'stat'}|({'moves'} if feature in MOVES else {'ability'} if feature==POWER else set())
 if type(selection)is not dict or set(selection)!=expected or selection['stat'] not in ('atk','spa'):raise ValueError('printed Aura Guardian selection required')
 if feature in MOVES:
  if type(selection['moves'])is not list or len(selection['moves'])!=2 or len(set(selection['moves']))!=2 or not set(selection['moves'])<=set(MOVES[feature]):raise ValueError('exact two printed Aura Guardian Moves required')
 if feature==POWER:
  C.integer(snapshot['rank_number'],'Power of Aura rank',1,2)
  if selection['ability'] not in (SCRAPPY,STORM,STORM_TEST) or actor.r._selected_rule(selection['ability'])!=selection['ability']:raise ValueError('actual selected Aura Ability required')
 elif snapshot['rank_number'] is not None:raise ValueError('unranked Aura Guardian Feature')
 minimum=5 if feature==POWER and snapshot['rank_number']==2 else d['minimum_rank']
 return Q.require(feature,'native','acquire',[
  Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),
  Q.check('parent','prerequisite','격투' in snapshot['elemental'] if feature==CLASS else bool(snapshot['parents']) and set(snapshot['parents'])<=known,'actual Fighting Elemental Connection or acquired parent required'),
  Q.check('rank','prerequisite',snapshot['rank']>=minimum,'printed Intuition rank required')])


def after_acquire(e,actor,feature,sid):
 row=G.state(actor)['sources'][sid]['static_acquisition'];selection=row['snapshot']['selection']
 G.stat(actor,selection['stat'],1,sid,operation_id='acquisition_stat_tag')
 if feature in MOVES:
  actor.spec.setdefault('feature_choices',{})[feature]=list(selection['moves'])
  __import__('class_move_grants').register_all(e,actor)
 if feature==POWER:
  actor.spec.setdefault('feature_choices',{}).setdefault(POWER,[]).append(selection['ability'])
  __import__('acquired_feature_projections').register_all(e,actor)


def validate_acquisition(actor,record,sid,active):
 if not active:return
 feature=record['feature_id'];selection=record['snapshot']['selection']
 if actor.spec.get(G.KEY,{}).get('stat_sources',{}).get(selection['stat'],{}).get('sources',{}).get(sid,{}).get('acquisition_stat_tag')!={'delta':1,'minimum':None}:raise ValueError('actual source-owned Aura stat tag required')
 if feature in MOVES and actor.spec.get('feature_choices',{}).get(feature)!=selection['moves']:raise ValueError('Aura learned Move selection changed')
 if feature==POWER:
  chosen=actor.spec.get('feature_choices',{}).get(feature,[]);rank=record['snapshot']['rank_number']
  if len(chosen)<rank or chosen[rank-1]!=selection['ability']:raise ValueError('Aura rank Ability selection changed')


def require(e,actor,feature):
 __import__('world_entities').require_actors(e,actor)
 if e.r._selected_rule(feature)!=feature or acquired(actor,feature)is None:raise ValueError('actual acquired Aura Guardian Feature required: '+feature)
 __import__('trainer_feature_acquisition').validate_actor(actor)


def _swift(e,actor,source,ap):
 import action_points as AP,turn as TURN
 if AP.available(actor)<ap:raise ValueError('Aura Guardian requires available AP')
 if not TURN.spend(e,actor,'swift',source):raise ValueError('Aura Guardian requires available Swift Action')
 if ap:AP.charge(actor,ap)


def _grant_scene(e,actor,source,capabilities):
 import combat_timing as TIME
 sid=G.effect_source(actor,{'source_id':source},'aura-capabilities')
 for cap in capabilities:G.grant(actor,'capabilities',cap,sid,'effect',owner_id=actor.entity_id,lifetime='scene',rule_id=source)
 TIME.install(e,actor,{'source':source,'grant_source':sid,'aura_capabilities':list(capabilities),'encounter_end':True})
 return sid


def activate_reader(e,actor):
 require(e,actor,READER)
 def apply(staged,c):
  _swift(staged,c,READER,2)
  caps=['파동 감지']
  if __import__('skill_modifiers').rank(staged.r,c,'직감')[2]>=4:caps.append('파동술')
  return {'source':READER,'grant_source':_grant_scene(staged,c,READER,caps),'capabilities':caps}
 return G.transition(e,actor,apply)


def blessing(actor):
 rows=[r for r in __import__('combat_timing').records(actor) if r.get('aura_blessing')]
 if len(rows)>1:raise ValueError('only one Aura Blessing may be held')
 return rows[0] if rows else None


def begin_move(e,actor,target,move,completion):
 row=e._move_completions[completion]
 if row['actor'] is not actor or row['move_id']!=move['id']:raise ValueError('actual native Aura Move origin required')
 __import__('athlete').begin_move(e,actor,move,completion)
 if acquired(actor,SWORD) and 'aura_sword' not in row and move['id'] in (*MOVES[CLASS],*MOVES[MASTERY]) and move['class'] in ('물리','특수') and actor.side!=target.side and e.adjacent(actor,target):
  answer=e.rulings.decide({'type':'sword_of_body_and_soul','unit':SWORD,'actor':actor.name,'target':target.name,'move_id':move['id'],'text':'Spend 2 AP and a Swift Action; choose physical or special damage, or decline.'})
  if answer not in (None,False):
   if answer not in ('물리','특수'):raise ValueError('Sword requires Physical or Special damage choice')
   _swift(e,actor,SWORD,2)
   row['aura_sword']={'class':answer,'request_id':acquired(actor,SWORD)['request_id'],'target_id':target.entity_id,'source':SWORD}
  else:row['aura_sword']=None
 if row.get('aura_sword'):
  move['_aura_sword']=completion;row['target_moves'][target.entity_id]['_aura_sword']=completion
 conditional_power=__import__('pokemon_move_edges').official_incandescence_power(e,actor,move)
 if (active_ability(actor,'ability/트위스트파워') or conditional_power) and move['class'] in ('물리','특수'):
  if 'twisted_power' not in row:
   from source_context import verified_source
   verified_source(e.r,{'file':'input/db/abilities.csv','sha256':'87efebd17b0a5fe09c9db060a16a8844cf41be53d65eb35716cf62f80a177fae'},label='Twisted Power R422')
   blocked=row.get('aura_sword') or row.get('athlete_regime',{}).get('enabled') or (__import__('pokemon_move_edges').incandescence_bound(e,actor,move) and not conditional_power)
   answer=False if blocked else e.rulings.decide({'type':'twisted_power','unit':'ability/트위스트파워','actor':actor.name,'move_id':move['id'],'text':'Add half the other attack stat to this actual Move damage?'})
   if answer is not None and type(answer)is not bool:raise ValueError('explicit Twisted Power choice required')
   row['twisted_power']=answer is True
  move['_twisted_power_completion']=completion;row['target_moves'][target.entity_id]['_twisted_power_completion']=completion

 if acquired(actor,AMBIENT) and 'ambient_aura_decided' not in row and aura_keyword(e,actor,move):
  row['ambient_aura_decided']=True
  if blessing(actor) is not None:return
  import frequency as F,aura_pulse as PULSE
  if not F.activation_allowed(actor,AMBIENT,{'kind':'scene','uses':2},engine=e):return
  if not any(__import__('skill_modifiers').key(v) in ('파동술','aurapulse','capability/파동술') for v in G.effective_capabilities(actor)):return
  answer=e.rulings.decide({'type':'ambient_aura','unit':AMBIENT,'actor':actor.name,'move_id':move['id'],'text':'Spend a Swift Action to gain one Aura Blessing?'})
  if answer in (None,False):return
  if answer is not True:raise ValueError('explicit Ambient Aura activation required')
  PULSE.require_capability(actor);_swift(e,actor,AMBIENT,0)
  F.consume_activation(actor,AMBIENT,{'kind':'scene','uses':2},engine=e)
  __import__('combat_timing').install(e,actor,{'source':AMBIENT,'aura_blessing':True,'manual_end':True,'completion_id':completion,'acquisition_request':acquired(actor,AMBIENT)['request_id']})


def aura_keyword(e,actor,move):
 return '파동' in __import__('effects_ext').keywords_for(actor,move) or '파동' in str(move.get('range','')).split(', ')


def sword(e,actor,move):
 uid=move.get('_aura_sword')
 if uid is None:return None
 row=getattr(e,'_move_completions',{}).get(uid)
 if row is None or row['actor'] is not actor or row['move_id']!=move['id'] or not row.get('aura_sword'):raise ValueError('actual native Sword of Body and Soul receipt required')
 return row['aura_sword']


def damage_move(e,actor,move):
 selected=sword(e,actor,move)
 return dict(move,**{'class':selected['class']}) if selected else move


def attack_stat(e,actor,move,current):
 if sword(e,actor,move):return actor.staged('atk')+actor.staged('spa')
 current+=__import__('athlete').move_bonus(e,actor,move)
 token=move.get('_twisted_power_completion')
 if token is not None:
  row=getattr(e,'_move_completions',{}).get(token)
  if row is None or row['actor'] is not actor or row['move_id']!=move['id']:raise ValueError('actual Twisted Power Move required')
  conditional_power=__import__('pokemon_move_edges').official_incandescence_power(e,actor,move)
  if row.get('twisted_power') and (active_ability(actor,'ability/트위스트파워') or conditional_power):
   if conditional_power and __import__('pokemon_move_edges').mixed_power(actor):return current
   return current+__import__('arithmetic_policy').ratio(actor.staged('spa' if move['class']=='물리' else 'atk'),2)
 return current


def active_ability(actor,uid):
 unit=actor.r.selection.units.get(uid)
 import ability_transitions as ABILITIES
 return bool(unit and any(ABILITIES.ability_id(actor.r,value)==uid for value in actor.abilities) and ABILITIES.active(actor,uid))


def storm_bonus(e,actor,move):
 if active_ability(actor,STORM_TEST):return 3*actor.injuries
 if active_ability(actor,STORM) and aura_keyword(e,actor,move):return 3*actor.injuries+(3 if actor.hp*2<=actor.base_max_hp else 0)
 return 0


def scrappy_multiplier(e,actor,target,damage_type,mult):
 if damage_type not in ('노말','격투') or '고스트' not in target.types or not active_ability(actor,SCRAPPY):return mult
 import type_state as TYPES
 steps=0
 for kind in target.types:
  if kind=='고스트':continue
  value=TYPES.matchup(e.r,damage_type,kind)
  if value==0:return 0.0
  steps+=1 if value>1 else -1 if value<1 else 0
 return e.r.mech('combat/type-effectiveness')['multiplier_by_net_steps'][str(max(-3,min(3,steps)))]


def spend_blessing(e,actor,choice,*,target=None,status=None):
 require(e,actor,AMBIENT);token=blessing(actor)
 if token is None:raise ValueError('one actual Aura Blessing required')
 if choice not in ('barrier','cure','blindsense'):raise ValueError('printed Aura Blessing option required')
 target=actor if target is None else target
 __import__('world_entities').require_actors(e,target)
 if choice=='barrier':
  from grid import cheb
  if status is not None or target.side!=actor.side or cheb(actor.pos,target.pos)>5:raise ValueError('Aura barrier requires self or ally within five metres')
 elif target is not actor:raise ValueError('Aura cure and Blindsense affect only self')
 if choice=='cure':
  if status not in __import__('status_sets').afflictions(actor,'volatile'):raise ValueError('one current Volatile Status Affliction required')
 elif status is not None:raise ValueError('only Aura cure selects an affliction')
 def apply(staged,c,t):
  import combat_timing as TIME,action_lifecycle as ACTION
  held=blessing(c);ACTION.triggered_free_action(staged,c,AMBIENT)
  if choice=='barrier':
   rank=__import__('skill_modifiers').effective_rank(staged.r,c,'직감')
   record=__import__('effect_lifetimes').prepare(staged,c,t,{'type':'damage_reduction','value':rank*3,'until':"end of user's next turn"},AMBIENT)
   record['aura_barrier']=held['completion_id'];TIME.install(staged,t,record)
  elif choice=='cure':staged.cure_status(c,status)
  else:_grant_scene(staged,c,AMBIENT,['맹인 감각'])
  result={'source':AMBIENT,'completion_id':held['completion_id'],'choice':choice,'target_id':t.entity_id,'status':status}
  c.spec.setdefault('aura_blessing_spends',[]).append(result);TIME.records(c).remove(held)
  return result
 return G.transition(e,actor,apply,participants=(target,))


def before_damage(e,attacker,target,move):
 for owner in list(__import__('world_entities').actor_index(e).values()):
  if blessing(owner) is None:continue
  answer=e.rulings.decide({'type':'aura_blessing_interrupt','unit':AMBIENT,'actor':owner.name,'target':target.name,'move_id':move['id'],'text':'Spend an Aura Blessing before this damage, or decline.'})
  if answer in (None,False):continue
  if type(answer)is not dict or set(answer)-{'choice','target_id','status'} or 'choice' not in answer:raise ValueError('printed Aura Blessing Interrupt choice required')
  recipient=__import__('world_entities').actor_index(e).get(answer.get('target_id',owner.entity_id))
  if recipient is None:raise ValueError('actual Aura Blessing target required')
  spend_blessing(e,owner,answer['choice'],target=recipient,status=answer.get('status'))


def validate_world(e,index):
 for actor in index.values():
  held=blessing(actor)
  if held is not None:
   row=getattr(e,'_move_completions',{}).get(held.get('completion_id'))
   if row is None or row['actor'] is not actor or not row.get('ambient_aura_decided') or not any(r['request_id']==held.get('acquisition_request') for r in records(actor,AMBIENT)):raise ValueError('Aura Blessing requires actual acquired native Aura Move')
  for row in getattr(e,'_move_completions',{}).values():
   selected=row.get('aura_sword')
   if selected and row['actor'] is actor:
    if selected.get('class') not in ('물리','특수') or selected.get('source')!=SWORD or selected.get('target_id') not in index or not any(r['request_id']==selected.get('request_id') for r in records(actor,SWORD)):raise ValueError('actual Sword acquisition and selected damage class required')


def validate_core_ability(rules,row):
 expected={'type':'aura_damage_bonus','per_injury':3,'half_hp_bonus':3,'keyword':'파동'}
 if row.get('id')!=STORM or row.get('name')!='파동바람' or row.get('native_contract')!=expected:raise ValueError('exact core Aura Storm contract required')
 source=row['source'];official=row['official_source']
 if source.get('file')!='ch04-trainer-classes.md' or source.get('lines')!=[2796,2796] or source.get('sha256')!=SOURCE_SHA256:raise ValueError('core Aura Storm source reference changed')
 from source_context import verified_source
 verified_source(rules,{'file':'input/ch04-trainer-classes.md','sha256':SOURCE_SHA256},label='Aura Storm')
 if official.get('extract')!='source-audit/core-aura-storm.txt' or source.get('additional_snapshots')!={official['extract']:official['sha256']}:raise ValueError('Aura Storm English source changed')
 verified_source(rules,{'file':official['extract'],'sha256':official['sha256']},label='core Aura Storm',source_root='source-audit')


def native_move(fn):
 from functools import wraps
 @wraps(fn)
 def run(engine,attacker,target,*args,**kwargs):
  import partial_entities as P
  P.require_complete(attacker,'Aura native Move attacker');P.require_complete(target,'Aura native Move target')
  interested=__import__('athlete').regime(attacker,'spa') or any(acquired(attacker,u) for u in (SWORD,AMBIENT)) or active_ability(attacker,'ability/트위스트파워') or __import__('type_ace').sustained(engine,attacker,'feat/작열') or any(blessing(a) for a in __import__('world_entities').actor_index(engine).values())
  if not interested or getattr(engine,'_reactive_move_transaction',False):return fn(engine,attacker,target,*args,**kwargs)
  def staged(e,a,t):
   payload=G._stage_transition_payload(engine,e,{'args':args,'kwargs':kwargs})
   return fn(e,a,t,*payload['args'],**payload['kwargs'])
  return __import__('reactive_ability_events').atomic_move(engine,attacker,target,staged)
 return run


def move_definition(rules,move):
 if move['id']!='move/발경':return move
 source=move.get('_source',{})
 if source.get('file')!='db/moves.csv' or source.get('record_span')!=[196,196] or move.get('eng')!='Force Palm' or move.get('range')!='근접, 대상 1':raise ValueError('exact core Force Palm source/header required')
 from source_context import verified_source
 verified_source(rules,{'file':'input/db/moves.csv','sha256':'ab83f872e5eca67a41db7d126b842f0165437e0fa70bb77ddad832a0b7396c93'},label='Force Palm')
 verified_source(rules,{'file':'source-audit/core-force-palm.txt','sha256':FORCE_PALM_SHA256},label='core Force Palm Aura header',source_root='source-audit')
 return dict(move,range='근접, 대상 1, 파동',_core_aura_header={'source':'source-audit/core-force-palm.txt','sha256':FORCE_PALM_SHA256})

FORCE_PALM_SHA256='3cf5f0c8a12187cc8c1b1c0e4ce6f7a8ac3bff8273bd080ee1f5c7b5ceec993f'
