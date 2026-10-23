"""PTU119–128 Type Ace adapters on actual acquisition and native rule owners.

The class is a template. Only committed acquisitions provide permissions; a
completion ID is an observed native Move, never a caller-supplied hit flag.
"""
from copy import deepcopy
from pathlib import Path
import json
import common_checks as C
import state_grants as G

_data=json.loads((Path(__file__).resolve().parents[1]/'data/type-ace-definitions.json').read_text(encoding='utf8'))
DEFINITIONS=_data['features'];FEATURES={u:tuple(d['span']) for u,d in DEFINITIONS.items()}
TYPES=tuple(_data['types']);SKILLS=_data['skills']
CLASS='class/타입-에이스';REFRESH='feat/타입-리프레쉬';SYNC='feat/기술-싱크'
STRATAGEMS=frozenset(u for u,d in DEFINITIONS.items() if d.get('bound_ap'))
ENGLISH={d['english']:u for u,d in DEFINITIONS.items()}
KEY='type_ace_history'


def uid(name):
 return name if name in FEATURES else ENGLISH[name]


def records(actor,feature=None,active=False):
 import trainer_feature_acquisition as T
 return [r['static_acquisition'] for _,r,live in T._static_records(actor)
  if r['static_acquisition']['feature_id'] in FEATURES and (feature is None or r['static_acquisition']['feature_id']==feature) and (not active or live)]


def acquired(actor,feature,branch=None):
 rows=[r for r in records(actor,feature,True) if branch is None or r['snapshot']['branch']==branch]
 if len(rows)>1:raise ValueError('one exact acquired Type Ace branch required')
 return rows[0] if rows else None


def acquisition_snapshot(engine,actor,feature,branch):
 import skill_modifiers as S,world_entities as W,elemental_connection as E
 d=DEFINITIONS[feature]
 if d.get('branch') is True:
  if branch not in TYPES:raise ValueError('exact Type Ace acquired type required')
 else:
  if branch is not None:raise ValueError('type-specific Feature has a fixed branch')
  branch=d['branch']
 parent=d.get('parent',CLASS)
 parents=[] if feature==CLASS else [r['request_id'] for r in records(actor,parent,True) if r['snapshot']['branch']==branch]
 skill=actor.spec.get('type_link_skills',{}).get(branch)
 if skill not in SKILLS[branch]:raise ValueError('explicit reviewed Type Link skill required')
 result={'branch':branch,'skill':skill,'rank':rank(engine,actor,branch),'parents':parents}
 if feature==CLASS:
  result.update(pokemon=[{'id':p.entity_id,'types':list(p.types)} for p in W.actor_index(engine).values()
   if p.kind=='pokemon' and p.spec.get('trainer_id')==actor.entity_id],elemental=branch in E.choices(engine,actor))
 if feature==SYNC:result['features']=[r['request_id'] for r in records(actor,active=True)]
 return result


def qualification(actor,feature,snapshot,prerequisite_source):
 import acquisition_qualification as Q
 fields={'branch','skill','rank','parents'}|({'pokemon','elemental'} if feature==CLASS else set())|({'features'} if feature==SYNC else set())
 if prerequisite_source is not None or type(snapshot) is not dict or set(snapshot)!=fields:raise ValueError('exact Type Ace acquisition observations required')
 d=DEFINITIONS[feature];branch=snapshot['branch']
 if branch not in TYPES or d.get('branch') not in (True,branch):raise ValueError('matching Type Ace branch required')
 if snapshot['skill'] not in SKILLS[branch]:raise ValueError('reviewed Type Link skill required')
 C.integer(snapshot['rank'],'Type-linked skill rank',d.get('rank',0))
 if feature==CLASS:
  roster=snapshot['pokemon']
  if type(roster) is not list or len({r['id'] for r in roster})!=len(roster):raise ValueError('distinct owned Pokemon required')
  n=sum(branch in r['types'] for r in roster)
  if n<2 and not(snapshot['elemental'] is True and n>=1):raise ValueError('two matching Pokemon or Elemental Connection and one required')
 else:
  known={r['request_id'] for r in records(actor,d.get('parent',CLASS)) if r['snapshot']['branch']==branch}
  if not snapshot['parents'] or not set(snapshot['parents'])<=known:raise ValueError('actual matching Type Ace prerequisite required')
 if feature==SYNC:
  known={r['request_id'] for r in records(actor)}
  if len(set(snapshot['features']))<3 or not set(snapshot['features'])<=known:raise ValueError('three actual Type Ace Features required')
 return Q.require(feature,'native','acquire',[Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required')])


def trainer(engine,pokemon):
 import world_entities as W
 return W.actor_index(engine).get(pokemon.spec.get('trainer_id')) if pokemon.kind=='pokemon' else None


def owner(engine,pokemon,feature,branch=None):
 d=DEFINITIONS[feature];branch=branch or d.get('branch')
 a=trainer(engine,pokemon)
 return a if a is not None and acquired(a,feature,branch) and acquired(a,CLASS,branch) else None


def require(engine,a,p,feature,branch=None):
 import world_entities as W
 W.require_actors(engine,a,p)
 if owner(engine,p,feature,branch) is not a:raise ValueError('actual owned Pokemon and acquired Type Ace Feature required')
 return acquired(a,feature,branch)


def rank(engine,a,branch):
 return __import__('class_passive_combat').type_link_rank(engine,a,branch)


def clause(feature):
 a,b=FEATURES[feature];return 'input/ch04-trainer-classes.md:'+str(a)+'-'+str(b)


def sustained(engine,p,feature):
 import class_passive_combat as P
 return P._active(engine,p,feature)


def activate(engine,a,p,feature):
 """Use the existing single Stratagem slot and identified Bound AP."""
 import class_passive_combat as P,cheerleader as CHEER,turn as TURN,action_points as AP,temporary_ap as TEMP
 feature=uid(feature);require(engine,a,p,feature)
 if feature not in STRATAGEMS:raise ValueError('select a Type Ace Stratagem')
 d=DEFINITIONS[feature];branch=d['branch']
 restricted={'Iron Grit':'강철','Unconquerable':'드래곤','Sneak Attack':'악','Highlander':'드래곤','Incandescence':'불꽃','Debilitate':'독','Mindbreak':'에스퍼','Tough as Schist':'바위'}
 if d['english'] in restricted and restricted[d['english']] not in p.types:raise ValueError('printed Stratagem target type required')
 if d['english']=='Celerity':
  import movement_actions as M
  caps=M.capabilities(engine,p)
  if '비행' not in p.types and not(caps.get('sky',0) or caps.get('levitate',0)):raise ValueError('Flying or Sky/Levitate target required')
 @CHEER.order_activation(None)
 def apply(e,t,q):
  if not e.encounter_active or not q.on_field or q.fainted or q.captured:raise ValueError('available encounter Stratagem target required')
  order_delivery(e,t,q,feature)
  P._require_stratagem_slot(q)
  if AP.available(t)<2:raise ValueError('Stratagem requires two available AP')
  TEMP.preflight_binding(t,2,P.KIND)
  if d['action']=='free':__import__('action_lifecycle').triggered_free_action(e,t,feature)
  elif not TURN.spend(e,t,'standard',feature):raise ValueError('Stratagem Standard unavailable')
  state=P._state(q,create=True);state['serial']+=1;instance='class-passive:'+t.entity_id+':'+str(state['serial'])
  while instance in t.ap_account.identified_bindings(allow_missing=True):state['serial']+=1;instance='class-passive:'+t.entity_id+':'+str(state['serial'])
  t.ap_account.charge(2,mode='bind',instance_id=instance,temporary_binding_owner=P.KIND)
  row={'owner_id':t.entity_id,'target_id':q.entity_id,'instance':instance,'rule_id':feature,'clause_id':clause(feature),
   'acquisition_source':acquired(t,feature)['request_id'],'branch':branch,'lifetime':'sustained_2_ap_encounter'}
  state['sustains'][feature]=row
  G._source(q,instance,P.KIND,owner_id=t.entity_id,lifetime=row['lifetime'],rule_id=feature,clause_id=row['clause_id'],acquisition_source=row['acquisition_source'],sustain=True,tutor_points=0,branch=branch)
  if feature==uid('Iron Grit'):e.change_stage(q,'def',1)
  e.time_actors([t,q]);return row
 return G.transition(engine,a,apply,participants=(p,),include_rulings=True)


def withdraw(engine,a,feature):
 import class_passive_combat as P,world_entities as W
 for p in W.actor_index(engine).values():
  row=(P._state(p) or {}).get('sustains',{}).get(feature)
  if row and row['owner_id']==a.entity_id:P._unbind(engine,p,feature,a,row)


def _once(engine,p,key,frequency=None,consume=False):
 import frequency as F
 f=frequency or {'kind':'scene','uses':1}
 if not F.activation_allowed(p,key,f,engine=engine):raise ValueError('Type Ace target frequency already spent: '+key)
 if consume:F.consume_activation(p,key,f,engine=engine)


def _pay(engine,a,p,feature,*,per_pokemon=False,round_only=False):
 import frequency as F,action_lifecycle as A
 f=DEFINITIONS[feature]['frequency']
 if not F.activation_allowed(a,feature,f,engine=engine):raise ValueError('Type Ace Feature frequency exhausted')
 if per_pokemon:_once(engine,p,feature)
 if round_only:
  if any(r.get('ace_round_once')==feature for r in __import__('combat_timing').records(p)):raise ValueError('Type Ace once per round already used')
 A.triggered_free_action(engine,a,feature)
 F.consume_activation(a,feature,f,engine=engine)
 if per_pokemon:_once(engine,p,feature,consume=True)
 if round_only:_timed(engine,p,feature,ace_round_once=feature)


def _timed(engine,p,source,*,next_turn=False,this_turn=False,scene=False,**payload):
 import combat_timing as T
 record={'source':source,**payload,'encounter_end':True}
 if scene:record['scene_end']=True
 elif next_turn or this_turn:record.update(turn_owner=p,turn_deadline=p.custom_conditions.get('combat_turn_serial',0)+(1 if next_turn else 0))
 elif 'turn_deadline' not in record and 'count_deadline' not in record:record['count_deadline']=(engine.round_no+1,T.current(engine))
 return T.install(engine,p,record)


def _history(p,source,**facts):
 row={'source':source,**facts};p.spec.setdefault(KEY,[]).append(row);return row


def _extended(engine,a,p,feature,seconds,reason):
 import turn as TURN,pokemon_activities as P
 C.integer(seconds,'actual Extended activity seconds',1)
 if not isinstance(reason,str) or not reason.strip():raise ValueError('actual Extended activity reason required')
 P._outside(engine)
 if not TURN.spend(engine,a,'extended',feature):raise ValueError('Extended action unavailable')
 engine.advance_time(seconds,[a,p],source=feature)


def teach(engine,a,p,branch,ability,*,seconds,reason):
 require(engine,a,p,CLASS,branch)
 if ability not in ('last_chance','strategist'):raise ValueError('choose Last Chance or Type Strategist')
 if any(r['source']==CLASS for r in p.spec.get(KEY,[])):raise ValueError('Type Ace can target a Pokemon only once across all types')
 C.integer(p.spec.get('tutor_points'),'remaining Tutor Points',2)
 def apply(e,t,q):
  _extended(e,t,q,CLASS,seconds,reason)
  q.spec['tutor_points']-=2
  sid='type-ace-teaching:'+q.entity_id
  name='마지막기회' if ability=='last_chance' else '타입전략가'
  G.grant(q,'abilities',name,sid,'feature',owner_id=t.entity_id,lifetime='permanent',rule_id=CLASS,tutor_points=0)
  _history(q,CLASS,branch=branch,ability=ability,owner_id=t.entity_id,acquisition=acquired(t,CLASS,branch)['request_id'],point_cost=2)
  e.register_abilities(q)
  _irreversible(e,t,CLASS,branch,sid,reason)
  return sid
 return G.transition(engine,a,apply,participants=(p,))


def _irreversible(engine,a,feature,branch,event,reason):
 import acquisition_withdrawal as A
 sid=next(s for s,r,live in __import__('trainer_feature_acquisition')._static_records(a) if live and r['static_acquisition']['request_id']==acquired(a,feature,branch)['request_id'])
 A.irreversible(engine,a,sid,event_id=event,reason=reason)


def sync(engine,a,p,branch,*,seconds,**decision):
 require(engine,a,p,SYNC,branch);C.integer(p.spec.get('tutor_points'),'remaining Tutor Points',1)
 import move_type_sync as SY
 def apply(e,t,q):
  _extended(e,t,q,SYNC,seconds,decision.get('reason'))
  row=SY.observe(e,q,chosen_type=branch,**decision);q.spec['tutor_points']-=1
  _irreversible(e,t,SYNC,branch,row['id'],decision['reason']);return row
 return G.transition(engine,a,apply,participants=(p,))


def refresh(engine,a,p,branch,scene_move):
 import cheerleader as CHEER,action_points as AP,turn as T,frequency as F,pokemon_move_edges as EDGE
 require(engine,a,p,REFRESH,branch);mid=engine.r.move_id(scene_move)
 if mid not in p.moves:raise ValueError('actual known Scene Move required')
 chosen=EDGE.prepare(engine,p,engine.r.move(mid))
 if chosen['type']!=branch or F.move_frequency(engine,mid,p)[0]!='scene':raise ValueError('matching Scene Move required')
 @CHEER.order_activation(None)
 def apply(e,t,q):
  order_delivery(e,t,q,REFRESH)
  _once(e,q,REFRESH)
  if AP.available(t)<2:raise ValueError('Type Refresh requires two AP')
  if not T.spend(e,t,'standard',REFRESH):raise ValueError('Type Refresh Standard unavailable')
  AP.spend(t,2);F.restore_scene_use(e,q,mid)
  for move in q.moves:
   native=EDGE.prepare(e,q,e.r.move(move))
   if native['type']==branch and F.move_frequency(e,move,q)[0]=='every_other_turn':F.restore_eot(e,q,move)
  _once(e,q,REFRESH,consume=True);return True
 return G.transition(engine,a,apply,participants=(p,),include_rulings=True)


def extra_ordinary(engine,a,p,*,seconds,reason):
 feature=uid('Extra Ordinary');require(engine,a,p,feature)
 if '노말' not in p.types:raise ValueError('Normal Pokemon required')
 rows=[r for r in p.spec.get(KEY,[]) if r['source'] in (CLASS,feature) and r.get('branch')=='노말']
 if any(r['source']==feature for r in rows):raise ValueError('Extra Ordinary can target a Pokemon only once')
 import ability_transitions as AB
 known={kind for kind in ('last_chance','strategist') if '노말' in ability_branches(engine,p,kind)}
 if len(known)!=1:raise ValueError('actual Last Chance or Normal Strategist required')
 selected=({'last_chance','strategist'}-known).pop()
 def apply(e,t,q):
  _extended(e,t,q,feature,seconds,reason);sid='extra-ordinary:'+q.entity_id
  G.grant(q,'abilities','마지막기회' if selected=='last_chance' else '타입전략가',sid,'feature',owner_id=t.entity_id,lifetime='permanent',rule_id=feature)
  _history(q,feature,branch='노말',ability=selected,owner_id=t.entity_id,point_cost=0);e.register_abilities(q)
  _irreversible(e,t,feature,'노말',sid,reason);return sid
 return G.transition(engine,a,apply,participants=(p,))


def virtual_weather(engine,p):
 for name,weather in (('Sunlight Within','쾌청'),('Desert Heart','모래바람'),('Polar Vortex','싸라기눈'),('Fishbowl Technique','비')):
  if sustained(engine,p,uid(name)):return weather
 return None


def _buff(p,key):
 return sum(r.get(key,0) for r in __import__('combat_timing').records(p))


def all_rolls(p):return _buff(p,'ace_all_rolls')


def _stat_owner(engine,p,name):
 feature=uid(name);return owner(engine,p,feature)


def sneak(engine,a,t):
 if t.fainted or t.conditions.intersection({'풀죽음','잠듦','구속','넘어짐'}):return True
 # Nonmechanical surprise requires an explicit observation, not a default.
 return engine.rulings.decide({'type':'type_ace_sneak_attack','actor':a.name,'target':t.name,'text':'Is the actual target flanked, unaware, or otherwise not expecting this attack?'}) is True


def accuracy(engine,a,t,move,mm):
 result=all_rolls(a)+_buff(a,'ace_accuracy')
 row=sustained(engine,a,uid('Sneak Attack'))
 if row and sneak(engine,a,t):result+=2
 result-=_buff(t,'ace_zephyr') if __import__('class_passive_combat')._ranged(move) else 0
 mark=marked(engine,a)
 if mark and t is not mark and engine.adjacent(a,mark):
  tr=_stat_owner(engine,mark,'Face Me Whelp')
  if tr:result-=rank(engine,tr,'격투')//2
 return result


def damage_bonus(engine,a,t,move,mult):
 result=all_rolls(a)+sum(r.get('ace_damage',0) for r in __import__('combat_timing').records(a) if not r.get('ace_vortex') or '조이기' in a.conditions)
 if move['type'] in ability_branches(engine,a,'last_chance') and any(r.get('ability')=='last_chance' for r in a.spec.get(KEY,[])):result+=10 if a.hp*3<a.max_hp else 5
 row=sustained(engine,a,uid('Sneak Attack'))
 if row and sneak(engine,a,t):result+=rank(engine,row[0],'악')
 row=sustained(engine,a,uid('Mindbreak'))
 if row and move['type']=='에스퍼' and move['class']!='변화':result+=3*len(a.conditions.intersection({'악몽','혼란','저주','봉인','풀죽음','헤롱헤롱','난동','억압'}))
 if __import__('class_passive_combat')._ranged(move):result-=10*_buff(t,'ace_zephyr')
 marker=marked(engine,a)
 if marker and marker is not t and engine.adjacent(a,marker) and _stat_owner(engine,marker,'Face Me Whelp'):result-=10
 s=scope(engine,a,move)
 if s:result+=s.get('damage_penalty',0)
 return result


def damage_reduction(engine,a,t,move,mult):
 result=sum(r.get('ace_dr',0) for r in __import__('combat_timing').records(t) if not r.get('ace_strategist') or bool(ability_branches(engine,t,'strategist')))
 return result


def attack_stat(engine,a,move,current):
 current=__import__('pokemon_move_edges').mixed_damage_stat(engine,a,move,current)
 s=scope(engine,a,move)
 return a.staged('def') if s and s.get('feature')==uid('Assault Armor') else current


def effect_range(engine,a,move):
 result=0
 if move['type']=='강철' and _stat_owner(engine,a,'Polished Shine'):result+=2
 row=sustained(engine,a,uid('Mindbreak'))
 if row and move['type']=='에스퍼' and move['class']!='변화':result+=len(a.conditions.intersection({'악몽','혼란','저주','봉인','풀죽음','헤롱헤롱','난동','억압'}))
 return result


def initiative(engine,p):
 row=sustained(engine,p,uid('Celerity'))
 return rank(engine,row[0],'비행') if row else 0


def marked(engine,p):
 for r in __import__('combat_timing').records(p):
  if r.get('ace_marker'):return r['ace_marker']
 return None


def mark(engine,p,t):
 old=marked(engine,t)
 if old and old is not p:return False
 import combat_timing as T
 for r in list(T.records(t)):
  if r.get('ace_marker'):T.expire(engine,t,r,ending='replaced')
 _timed(engine,t,uid('Close Quarters Mastery'),ace_marker=p);return True


def defense_locked(engine,p,stat):
 return stat=='def' and sustained(engine,p,uid('Iron Grit')) is not None


def scope(engine,p,move):
 value=getattr(engine,'_type_ace_scope',None)
 if value is None:
  value=next((r['type_ace'] for r in reversed(getattr(engine,'_move_activation_scopes',())) if r['actor'] is p and r['move_id']==move['id'] and 'type_ace' in r),None)
 return value if value and value['pokemon'] is p and value['move_id']==move['id'] else None


def prepare(engine,p,move):
 s=scope(engine,p,move)
 if not s and not(move['type']=='고스트' and _buff(p,'ace_boo')):return move
 s=s or {};out=dict(move)
 if 'range' in s:out.update(range=s['range']['raw'],_class_move_range=deepcopy(s['range']))
 if s.get('type'):out['type']=s['type']
 if s.get('keywords'):out['keywords']=list(dict.fromkeys(list(move.get('keywords') or [])+s['keywords']))
 if s.get('feature')==uid('New Normal'):out['_type_ace_new_normal']=True
 if move['type']=='고스트' and _buff(p,'ace_boo'):
  out['_type_ace_boo']=True;out['keywords']=list(dict.fromkeys(list(out.get('keywords') or [])+['강타']))
 return out


def range_spec(engine,p,move,result):
 s=scope(engine,p,move)
 if s and s.get('chain_origin'):return {'raw':'3, 대상1','origin':3,'targets':1,'parsed':True}
 return deepcopy(s['range']) if s and 'range' in s else result


def use_move(engine,a,p,target,move,*,feature,aim=None,set_damage=False,choice=None):
 """Selected modifications still execute the actual learned Move once."""
 import weapon_actions as W,frequency as F,turn as TURN,pokemon_move_edges as EDGE
 feature=uid(feature);d=DEFINITIONS[feature];require(engine,a,p,feature)
 mid=engine.r.move_id(move);native=EDGE.prepare(engine,p,engine.r.move(mid));rng=W.range_spec(engine,native,p)
 if mid not in p.moves and mid!='struggle':raise ValueError('actual available Move required')
 name=d['english'];branch=d['branch'];s={'trainer':a,'pokemon':p,'feature':feature,'move_id':mid,'paid':False}
 if name=='Shocking Speed':return engine.use_priority_move(p,target,mid,shocking_speed=a)
 if name=='Brawler':
  if mid!='struggle':raise ValueError('Brawler requires Struggle Attack')
  s.update(type='격투',range={'raw':'파열 1, 친화','origin':'self','shape':'burst','size':1,'parsed':True},keywords=['친화'])
 elif name=='Fan The Flames':
  if native['type']!='불꽃' or rng.get('targets')!=1:raise ValueError('single-target Fire Move required')
  melee=rng.get('origin')=='melee';shape,size=('burst',1) if melee else ('cone',2)
  s['range']={'raw':'파열 1' if melee else '원뿔 2','origin':'self','shape':shape,'size':size,'parsed':True}
 elif name in ('Earthroil','Flood!'):
  if branch not in p.types or native['type']!=branch or native['class']=='변화':raise ValueError('matching typed Pokemon and damaging Move required')
  options={'Earthroil':('line','burst'),'Flood!':('line','close_blast')}
  if choice not in options[name]:raise ValueError('choose printed Line or Burst/Close Blast')
  s['range']={'raw':'직선 4' if choice=='line' else '파열 1' if choice=='burst' else '근접폭발 2','origin':'self','shape':choice,'size':4 if choice=='line' else 1 if choice=='burst' else 2,'parsed':True}
  if name=='Earthroil':s.update(keywords=['지면통과'],damage_penalty=-5 if rng.get('targets')==1 else 0)
 elif name=='Shocking Speed':
  if '전기' not in p.types or native['type']!='전기' or F.move_frequency(engine,mid,p)[0]!='at_will':raise ValueError('Electric Pokemon and At-Will Electric Move required')
  s['keywords']=['우선','우선(고급)']
 elif name=='Gale Strike':
  if native['type']!='비행' or native.get('ac') is None:raise ValueError('Flying Move with Accuracy Check required')
 elif name=='Assault Armor':
  if native['type']!='강철' or native['class']=='변화':raise ValueError('damaging Steel attack required')
 elif name=='Gneiss Aim':
  if native['type']!='바위' or native['class']=='변화':raise ValueError('damaging Rock Move required')
  s['keywords']=['강타']
 elif name=='New Normal':
  if native['type']!='노말' or native['class']=='변화' or new_normal_maximum(engine,native) is None:raise ValueError('conditional damaging Normal Move required')
 elif name=='Fountain of Life':
  if '물' not in p.types or native['type']!='물' or native['class']=='변화':raise ValueError('Water Pokemon damaging Water Move required')
  if type(choice) is not dict or set(choice)!={'penalty','status'}:raise ValueError('choose actual damage-roll penalty and one affliction to cure')
  s.update(penalty=choice['penalty'],status=choice['status'])
 else:raise ValueError('this Type Ace feature uses its own native producer')
 pending=[]
 def apply(e,t,q,b):
  if hasattr(e,'_type_ace_scope'):raise ValueError('nested selected Type Ace Move declaration')
  if name in ('Earthroil','Flood!'):s['pokemon_action']='shift';_pay(e,t,q,feature)
  elif name not in ('Assault Armor','Gneiss Aim','New Normal','Gale Strike','Fountain of Life'):_pay(e,t,q,feature)
  s['trainer']=t;s['pokemon']=q
  e._type_ace_scope=s
  before=q.move_uses.get(mid,0)
  try:
   result=e.use_move_on(q,b,mid,e.everyone,aim=aim,set_damage=set_damage)
   if q.move_uses.get(mid,0)==before:raise ValueError('native Type Ace Move activation refused')
   return result
  except Exception as error:
   import passive_events as PE,heavy_injury_adapter as H
   if type(error) is PE.PassiveEventPending and e._passive_pending==error.event_id:pending.append((type(error),error.event_id));return None
   if type(error) is H.HeavyPending and e._heavy_pending==error.event_id:pending.append((type(error),error.event_id));return None
   raise
  finally:del e._type_ace_scope
 result=G.transition(engine,a,apply,participants=(p,target),include_rulings=True,include_grid=engine.grid is not None)
 if pending:raise pending[0][0](pending[0][1])
 return result


def damage_choice(engine,p,move,db):
 s=scope(engine,p,move)
 if not s:return db
 name=DEFINITIONS[s['feature']]['english']
 if name not in ('Assault Armor','New Normal'):return db
 if not s['paid']:_pay(engine,s['trainer'],p,s['feature'],per_pokemon=name=='New Normal');s['paid']=True
 if name=='New Normal':
  db=min(14,db)
 return db


def new_normal_maximum(engine,move):
 # Core125 explicitly names the first three; the remaining bounds are the
 # selected Moves' printed upper values. The conditional DB owner supplies its
 # reviewed caps/replacements without evaluating a hypothetical combat state.
 names={'Return':9,'Wring Out':12,'Retaliate':14}
 value=names.get(move.get('eng'))
 policy=__import__('conditional_damage_base').policy(move)
 if policy is not None:
  values=[v for k,v in policy.items() if k in ('base','cap','replacement','damage_base','maximum') and type(v) is int]
  if values:value=max([value or 0,*values])
 # Source rows with a reviewed conditional replacement carry the upper DB in
 # mechanics. Narrative-only amounts are not silently interpreted as DBs.
 mechanics=engine.r.move_mech(move['id'])[0]
 values=[x['damage_base'] for x in mechanics.get('effects_exec',[]) if x.get('type')=='conditional_damage_base' and type(x.get('damage_base')) is int]
 if values:value=max([value or 0,*values])
 return min(14,value) if value is not None else None


def miss(engine,p,move,hit):
 s=scope(engine,p,move)
 if s and s.get('feature')==uid('Gneiss Aim') and not hit and not s['paid']:_pay(engine,s['trainer'],p,s['feature']);s['paid']=True


def accuracy_face(engine,p,t,move,mm,face,*,modifier,ac,evasion,automatic,cannot_hit,ac_rule):
 s=scope(engine,p,move)
 if not s or s['feature']!=uid('Gale Strike'):return face
 if 'gale_faces' not in s:
  second=engine.d20();s['gale_faces']=[face,second]
  answer=engine.rulings.decide({'type':'type_ace_gale_strike','unit':s['feature'],'actor':p.name,'faces':s['gale_faces'],'text':'Choose first or second actual Accuracy die.'})
  if answer not in ('first','second'):raise ValueError('explicit Gale Strike die selection required')
  chosen=face if answer=='first' else second;s['gale_selected']=chosen
  import combat_hit as HIT
  results=[HIT.resolve(natural=n,modifier=modifier,accuracy=ac,evasion=evasion,automatic=automatic,cannot_hit=cannot_hit or None,
   auto_miss_natural=ac_rule['auto_miss_natural'],auto_hit_natural=ac_rule['auto_hit_natural'])['hit'] for n in (face,second)]
  if not(all(results) and chosen==min(face,second)):_pay(engine,s['trainer'],p,s['feature'])
 return s['gale_selected']


def completion(engine,p,completion_id):
 row=getattr(engine,'_move_completions',{}).get(completion_id)
 if row is None or row['actor'] is not p or row['phase']!='complete' or not row['sealed'] or row['round']!=engine.round_no:raise ValueError('current actual completed whole Move required')
 return row


def _completed_targets(row,hit=True):
 import move_completion as M
 return [t for t in M.actual_recipients(row) if (r:=M.recipient_result(row,t)) and bool(r['hit'] and not r.get('cancelled'))==hit]


def react(engine,a,p,feature,completion_id,**options):
 """Actual after-Move choices; all hit and target facts come from completion."""
 feature=uid(feature);require(engine,a,p,feature);row=completion(engine,p,completion_id)
 name=DEFINITIONS[feature]['english'];move=row['move'];branch=DEFINITIONS[feature]['branch'];hits=_completed_targets(row)
 if any(r.get('completion_id')==completion_id and r['source']==feature for r in p.spec.get(KEY,[])):raise ValueError('Type Ace reaction already consumed this Move')
 if name not in ('Clever Ruse','Miasma','Devious','Mold the Earth') and move['type']!=branch:raise ValueError('matching actual Move type required')
 damaging=name in ('Black-Out Strike','Bigger and Boulder','Fountain of Life','Aqua Vortex','Chain Lightning','Cross-Pollinate')
 if damaging and move['class']=='변화':raise ValueError('actual damaging Move required')
 on_hit=name in ('Disruption Order','Black-Out Strike','Tyrant’s Roar','Vampirism','Bigger and Boulder','Fountain of Life','Aqua Vortex','Chain Lightning','Corrosive Blight','Psychic Resonance')
 if on_hit and not hits:raise ValueError('actual successful hit required')
 if name in ('Clever Ruse','Miasma') and (move['type']!=branch or (not _completed_targets(row,False) if name=='Miasma' else bool(hits))):raise ValueError('actual missed typed attack required')
 if name=='Disruption Order':options['x']=rank(engine,a,'벌레')//2
 if name=='Clever Ruse' and engine._active_turn_actor is not p:raise ValueError('Clever Ruse requires the actual own turn')
 def apply(e,t,q,*_):
  # Staged copies only: the completion row and every hit recipient are re-read from the staged engine.
  import world_entities as W
  index=W.actor_index(e);srow=completion(e,q,completion_id);shits=_completed_targets(srow);opts=_staged_options(index,options)
  _pay(e,t,q,feature,per_pokemon=name in ('Devious','New Normal','Fountain of Life'),round_only=name=='Clever Ruse')
  _history(q,feature,completion_id=completion_id)
  x=rank(e,t,branch)
  if name=='Disruption Order':
   for target in shits:_timed(e,target,feature,ace_disruption=True,accuracy_modifier=-opts['x'],statuses=['둔화'],turn_owner=q,turn_deadline=q.custom_conditions.get('combat_turn_serial',0)+1)
  elif name=='Clever Ruse':_ruse(e,q,opts)
  elif name=='Black-Out Strike':
   _once(e,t,feature+':scene',consume=True)
   for target in shits:
    target.injuries+=1;__import__('precise_actions').injury(e,target,1,feature);__import__('life').sync(e,target)
    if target.injuries>=3 or target.hp*4<=target.max_hp:__import__('life').faint(e,target)
    else:e.apply_status(target,'잠듦',source=feature,applied_by=q)
  elif name=='Tyrant’s Roar':
   for target in e.everyone:
    if target.side!=q.side and target.on_field and __import__('grid').cheb(q.pos,target.pos)<=2:
     e.apply_status(target,'둔화',source=feature,applied_by=q)
     for stat in ('atk','def','spa','spd','spe'):
      if target.stages[stat]>0:e.change_stage(target,stat,-1)
  elif name=='Arcane Favor':
   for target in e.everyone:
    if target.on_field and target.side==q.side:_timed(e,target,feature,ace_all_rolls=1)
  elif name=='Vampirism':
   target=opts.get('target',shits[0] if shits else None);stat=_stat(opts)
   if target not in shits or not e.adjacent(q,target):raise ValueError('actual adjacent Ghost hit recipient required')
   e.lose_hp(target,e.tick(target),source=feature);e.change_stage(target,stat,-1);e.change_stage(q,stat,1);__import__('temporary_hp').grant(e,q,e.tick(q),provenance={'feature':feature})
  elif name=='Corrosive Blight':
   for target in (h for h in shits if h.side!=q.side):_timed(e,target,feature,ace_blight=True)
  elif name=='Aqua Vortex':
   for target in srow['targets']:
    e.apply_status(target,'조이기',source=feature,applied_by=q)
    _timed(e,target,feature,scene=True,ace_vortex=True,ace_damage=-x)
  elif name=='Bigger and Boulder':_boulder(e,t,q,shits,opts,x)
  elif name in ('Devious','Cross-Pollinate','Arctic Zeal','Psychic Resonance','Force of Will','Miasma','Chain Lightning'):
   return _extra_move(e,t,q,feature,srow,opts)
  elif name=='Mold the Earth':return mold(e,t,q,srow,**opts)
  else:raise ValueError('this reaction uses its native incoming/action producer')
  return True
 return G.transition(engine,a,apply,participants=(p,*row['targets']),include_rulings=True,include_grid=engine.grid is not None)


def _staged_options(index,options):
 """Map caller-supplied live actors to their staged copies; other values pass through."""
 def convert(value):
  if hasattr(value,'entity_id'):return index[value.entity_id]
  if isinstance(value,list):return [convert(v) for v in value]
  if isinstance(value,tuple):return tuple(convert(v) for v in value)
  return value
 return {k:convert(v) for k,v in options.items()}

def _stat(options):
 stat=options.get('stat')
 if stat not in ('atk','def','spa','spd','spe'):raise ValueError('choose an exact Combat Stat')
 return stat


def _ruse(engine,p,options):
 choices=options.get('choices')
 if type(choices) is not list or len(choices)!=2 or len(set(choices))!=2 or not set(choices)<={'evasion','ignore_evasion','disengage'}:raise ValueError('choose two distinct Clever Ruse effects')
 if 'evasion' in choices:_timed(engine,p,uid('Clever Ruse'),ace_evasion=4)
 if 'ignore_evasion' in choices:_timed(engine,p,uid('Clever Ruse'),next_turn=True,ace_ignore_stat_evasion=True)
 if 'disengage' in choices:disengage(engine,p,options.get('path') or [options.get('destination')],mode=options.get('mode','land'),free=True)


def _extra_move(engine,a,p,feature,row,options):
 import action_lifecycle as A,move_completion as M,weapon_actions as W,frequency as F
 name=DEFINITIONS[feature]['english'];trigger=row['move'];hits=_completed_targets(row) if 'results' in row else []
 target=options.get('target',hits[0] if hits else row['targets'][0]);mid=engine.r.move_id(options.get('move')) if options.get('move') else None
 if name=='Arctic Zeal':
  if '얼음' not in p.types:raise ValueError('Ice Pokemon required')
  mid='move/흰안개';target=p
 elif name=='Psychic Resonance':
  if trigger['class']!='변화':raise ValueError('Psychic Status hit required')
  mid='move/앙코르'  # Core125 Encore; the printed Korean Move id is 앙코르
  if target not in hits or target.side==p.side:raise ValueError('actual Psychic triggering hit foe required')
 elif name=='Miasma':
  if mid not in ('move/연막','move/독가스'):raise ValueError('choose Smokescreen or Poison Gas')
 if name=='Chain Lightning':return chain(engine,a,p,row,options)
 if mid is None:raise ValueError('select actual additional Move')
 move=engine.r.move(mid);kws=set(move.get('keywords') or [])|set(engine.r.move_mech(mid)[0].get('header',{}).get('keywords') or [])
 if name=='Devious':
  original_kws=set(trigger.get('keywords') or [])|set(engine.r.move_mech(trigger['id'])[0].get('header',{}).get('keywords') or [])
  if '악' not in p.types or not original_kws.intersection({'사회적','Social'}):raise ValueError('Dark Pokemon actual Social Move required')
  if mid==trigger['id'] or not((move['type']=='악' and move['class']=='변화') or kws.intersection({'사회적','Social'})):raise ValueError('different naturally Dark Status or Social Move required')
 elif name=='Cross-Pollinate':
  if move['type']!='풀' or move['class']!='변화':raise ValueError('known Grass Status Move required')
 elif name=='Force of Will':
  def valid(m):return m['type']=='에스퍼' and m['class']=='변화' and any(token in str(m.get('range')) for token in ('축복','필드','함정','자신','Blessing','Field','Hazard','Self'))
  if mid==trigger['id']:raise ValueError('different additional Psychic Move required')
  if not valid(trigger) or not valid(move):raise ValueError('printed Psychic Status range required')
 if name not in ('Miasma','Arctic Zeal','Psychic Resonance','Fairy Lights') and mid not in p.moves:raise ValueError('actual Move List required')
 sid='type-ace-permission:'+feature+':'+p.entity_id
 if mid not in p.moves:G.grant_moves(p,[mid],sid,'feature',owner_id=a.entity_id,lifetime='scene',rule_id=feature,mode='permission')
 s={'trainer':a,'pokemon':p,'feature':feature,'move_id':mid,'paid':True,'extra_move':True,'permission_source':sid}
 if name=='Miasma':
  center=tuple(row['targets'][0].pos)
  if options.get('aim') is not None and tuple(options['aim'])!=center:raise ValueError('Miasma must center on actual triggering target')
  options=dict(options,aim=center)
  s.update(ignore_frequency=True,range={'raw':'폭발 3','origin':99,'shape':'blast','size':3,'parsed':True},miasma_center=center)
 previous=getattr(engine,'_type_ace_scope',None);engine._type_ace_scope=s
 try:
  # Blessing/Field ranges are not positional targets; the existing single-actor Move API creates them.
  if not W.range_spec(engine,move,p).get('parsed'):
   with A.move_grant(engine,p,p,mid,source=feature,kind='free') as grant:
    result=engine.use_move(p,p,mid,count_use=not s.get('ignore_frequency',False),free_action=True,_action_grant=grant,set_damage=options.get('set_damage',False))
  else:result=engine.use_move_on(p,target,mid,engine.everyone,aim=options.get('aim'),set_damage=options.get('set_damage',False))
  if name=='Arctic Zeal':
   for b in __import__('blessing_effects').live(p):
    if b['source']=='move/흰안개':b['arctic_zeal_owner']=p.entity_id
  return result
 finally:
  if previous is None:del engine._type_ace_scope
  else:engine._type_ace_scope=previous
  pending=any(r.get('actor') is p and r.get('move_id')==mid and r.get('activation_continuation') for r in getattr(engine,'_move_completions',{}).values())
  if not pending and sid in p.spec.get(G.KEY,{}).get('sources',{}):G.revoke(p,sid,engine=engine)


def after_move(engine,row):
 """Automatic source-owned passives read one actual activation completion."""
 p=row['actor'];move=row['move'];hits=_completed_targets(row)
 if row.get('type_ace_completed'):return
 row['type_ace_completed']=True
 if move['type']=='바위' and not hits and '바위' in p.types:
  gravel(engine,p,'actual_all_targets_missed')
 if sustained(engine,p,uid('Overload')) and move['type']=='전기':
  tr=sustained(engine,p,uid('Overload'))[0]
  selected=[t for t in hits if t.side!=p.side and engine.rulings.decide({'type':'type_ace_overload','actor':p.name,'target':t.name}) is True]
  for t in selected:engine.lose_hp(t,engine.tick(p)+rank(engine,tr,'전기'),source=uid('Overload'))
  if selected:engine.lose_hp(p,engine.tick(p),source=uid('Overload'))
 s=scope(engine,p,move)
 if s and s['feature']==uid('Arctic Zeal'):
  for b in __import__('blessing_effects').live(p):
   if b['source']=='move/흰안개':b['arctic_zeal']={'feature':s['feature'],'acquisition':acquired(s['trainer'],s['feature'])['request_id'],'owner_id':s['trainer'].entity_id,'pokemon_id':p.entity_id,'completion_id':row['id']}
 if move.get('_type_ace_boo'):
  for b in list(__import__('combat_timing').records(p)):
   if b.get('ace_boo'):__import__('combat_timing').expire(engine,p,b)
 if move['type'] in ability_branches(engine,p,'strategist'):
  for old in list(__import__('combat_timing').records(p)):
   if old.get('ace_strategist'):__import__('combat_timing').expire(engine,p,old,ending='refreshed')
  _timed(engine,p,CLASS,ace_strategist=True,ace_dr=10 if p.hp*3<p.max_hp else 5)
 if sustained(engine,p,uid('Haunting Curse')) and move['type']=='고스트':
  _curse_token(engine,p)
 if sustained(engine,p,uid('Close Quarters Mastery')) and move['type']=='격투':
  for t in hits:mark(engine,p,t)
 if sustained(engine,p,uid('Debilitate')) and move['type']=='독':
  for t in hits:
   if t.conditions.intersection({'독','맹독'}) or any(r.get('ace_blight') for r in __import__('combat_timing').records(t)):_timed(engine,t,uid('Debilitate'),accuracy_modifier=-2,ace_evasion=-2)
 for t in hits:
  for r in list(__import__('combat_timing').records(t)):
   if r.get('ace_blight'):
    engine.lose_hp(t,engine.tick(t),source=r['source'])
    if move['type']=='독':r['count_deadline']=(engine.round_no+1,__import__('combat_timing').current(engine))
 if sustained(engine,p,uid('Fey Trance')):
  import weapon_actions as W
  rng=W.range_spec(engine,move,p);kws=set(move.get('keywords') or [])|set(engine.r.move_mech(move['id'])[0].get('header',{}).get('keywords') or [])
  if rng.get('targets')==1 and (kws.intersection({'사회적','Social'}) or move['type']=='페어리' and move['class']=='변화'):
   for t in hits:
    if t.side==p.side:continue
    if __import__('frequency').activation_allowed(t,uid('Fey Trance'),{'kind':'scene','uses':1},engine=engine):
     _once(engine,t,uid('Fey Trance'),consume=True);engine.apply_status(t,'헤롱헤롱',source=uid('Fey Trance'),applied_by=p)
     __import__('action_resources').schedule(t,{'shift':1})
     _approach(engine,t,p)


def _approach(engine,p,t):
 import movement_actions as M
 if engine.adjacent(p,t):return
 answer=engine.rulings.decide({'type':'type_ace_fey_approach','actor':p.name,'target':t.name,'text':'Supply actual Shift mode and continuous mapped path towards target.'})
 if type(answer) is not dict or set(answer)!={'mode','path'}:raise ValueError('observed approach Shift mode and path required')
 last=answer['path'][-1] if answer['path'] else None
 point=last.get('position') if type(last) is dict else last
 last_height=last.get('altitude') if type(last) is dict else p.spec.get('_movement_altitude',0)
 target_height=t.spec.get('_movement_altitude',0)
 before=max(__import__('grid').cheb(p.pos,t.pos),abs(p.spec.get('_movement_altitude',0)-target_height))
 after=max(__import__('grid').cheb(tuple(point),t.pos),abs(last_height-target_height)) if point else before
 if not point or after>=before:raise ValueError('approach must move towards the infatuator in its actual plane')
 return M.follow_paid_path(engine,p,answer['path'],mode=answer['mode'],maximum_distance=M.distance_budget(engine,p,answer['mode']))


def frequency_exception(engine,p,mid):
 s=scope(engine,p,{'id':mid})
 return bool(s and s.get('ignore_frequency') and s.get('feature') in (uid('Miasma'),uid('Chain Lightning')))


def cleanup_permissions(engine,row):
 s=next((x.get('type_ace') for x in reversed(getattr(engine,'_move_activation_scopes',())) if x.get('completion_id')==row['id']),None)
 if not s:return
 sid=s.get('permission_source')
 if sid and sid in row['actor'].spec.get(G.KEY,{}).get('sources',{}):G.revoke(row['actor'],sid,engine=engine)


def evasion(engine,a,t,move):
 return evasion_extra(t)


def speed_evasion(engine,p):
 return int(bool(_stat_owner(engine,p,'Insectoid Utility') and __import__('movement_actions').capabilities(engine,p).get('sky',0)))


def evasion_extra(p):return _buff(p,'ace_evasion')


def ignore_stat_evasion(p):return bool(_buff(p,'ace_ignore_stat_evasion'))


def disengage(engine,p,path,*,mode='land',free=False):
 import movement_actions as M,turn as TURN,action_lifecycle as A
 if not path or not TURN.movement_permission(engine,p):raise ValueError('actual available Disengage path required')
 cap=M.distance_budget(engine,p,mode,as_slowed=True) if sustained(engine,p,uid('Celerity')) else min(M.distance_budget(engine,p,mode),1)
 if free:
  if not any(r.get('ace_round_once')==uid('Clever Ruse') for r in __import__('combat_timing').records(p)):raise ValueError('actual Clever Ruse activation required')
  A.record_action(engine,p,'free')
 elif not TURN.spend(engine,p,'shift','이탈',movement=True):raise ValueError('Disengage Shift unavailable')
 previous=getattr(engine,'_type_ace_disengage',None);engine._type_ace_disengage=p
 try:return M.follow_paid_path(engine,p,path,mode=mode,maximum_distance=cap)
 finally:
  if previous is None:del engine._type_ace_disengage
  else:engine._type_ace_disengage=previous


def _trip(engine,a,p,target,feature,options):
 import maneuver_opposed as M
 opts=dict(options.get('challenger_options') or {});opts['mods']=opts.get('mods',0)+rank(engine,a,'땅')//2
 config={'action_cost':'free','accuracy':'ordinary','opposed':'required','success':'check','geometry':{'range':max(1,__import__('grid').cheb(p.pos,target.pos)),'remote':True,'vertical':False},'requirements':[], 'challenger_skills':['전투'],'defender_skills':['전투','곡예'],'resistance_purpose':'resist_trip','challenger_purpose':None,'accuracy_class':'변화','opportunity':'other_adjacent'}
 cs=options.get('challenger_skill','전투');ds=options.get('defender_skill');fixed=options.get('fixed_accuracy')
 plans,prepared=M._prepare(engine,p,target,M.TRIP,(),cs,ds,fixed,opts,options.get('defender_options'),{'feature':feature,'acquisition':acquired(a,feature)['request_id']},config=config)
 def outcome(won):
  if won:engine.apply_status(target,'넘어짐',source=feature,applied_by=p)
  return won
 return M._run(engine,p,target,M.TRIP,6,plans,prepared,outcome,fixed,config=config)


def ability_branches(engine,p,kind):
 import ability_transitions as A
 identity='ability/마지막기회' if kind=='last_chance' else 'ability/타입전략가'
 if identity not in A.known(p) or not A.active(p,identity):return set()
 rows=[r['branch'] for r in p.spec.get(KEY,[]) if r.get('ability')==kind]
 if rows:return set(rows)
 selected=p.spec.get('ability_type_choices',{}).get(identity)
 if selected in TYPES:return {selected}
 return {'노말'} if kind=='last_chance' else set()


def ability_registration(engine,p,identity):
 # Generic Type Ace abilities have a parameterized type. Their effects use the
 # actual ability projection, so suppression/replacement immediately removes it.
 if identity=='ability/타입전략가':return True
 return identity=='ability/마지막기회' and any(r.get('ability')=='last_chance' for r in p.spec.get(KEY,[]))


def choose(engine,p,feature,**facts):
 a=owner(engine,p,feature)
 if a is None:return None
 if not __import__('frequency').activation_allowed(a,feature,DEFINITIONS[feature]['frequency'],engine=engine):return None
 answer=engine.rulings.decide({'type':'type_ace_choice','feature':feature,'actor':p.name,**facts})
 return a if answer is True else None


def incoming_multiplier(engine,a,p,move,mult):
 feature=uid('True Steel')
 reduction=0
 t=choose(engine,p,feature,trigger='actual_damaging_hit',attacker=a.name,move=move['id']) if '강철' in p.types and move['class']!='변화' else None
 if t:
  _pay(engine,t,p,feature)
  # Shared table and selected effectiveness modifier still own composition.
  # Engine.type_multiplier accepts a defender view; no actor type mutation.
  from copy import copy
  view=copy(p);view.spec=deepcopy(p.spec);view.types=['강철']
  mult=engine.type_multiplier(move['type'],view)[0]
  reduction=rank(engine,t,'강철')
 return {'multiplier':mult,'reduction':reduction}


def extra_authority(engine,p,target,mid,feature):
 allowed={'Devious','Cross-Pollinate','Arctic Zeal','Psychic Resonance','Force of Will','Miasma','Chain Lightning','Fairy Lights'}
 if feature not in FEATURES or DEFINITIONS[feature]['english'] not in allowed:return False
 s=scope(engine,p,{'id':mid})
 if not s or s.get('feature')!=feature or not s.get('extra_move'):return False
 require(engine,s['trainer'],p,feature)
 return True


def hazard_definition(rules,source,data):
 kinds={uid('Gravel Before Me'):'stealth_rock',uid('Bigger and Boulder'):'stealth_rock',uid('Mold the Earth'):'spikes',uid('Trail Blazer'):'fire'}
 if source not in kinds:return None
 __import__('trainer_feature_acquisition')._static_source(rules,source)
 row=next(dict(r) for r in data['moves'].values() if r['kind']==('spikes' if kinds[source] in ('spikes','fire') else 'stealth_rock'))
 row.update(kind=kinds[source],clause_id=clause(source),source_row_sha256=_data['source_sha256'],name='불길' if kinds[source]=='fire' else row['name'])
 return row


def _place_rock(engine,p,feature,*,cell=None,adjacent_to=None):
 import hazard_state as H,body_state as B,grid
 target=p if adjacent_to is None else adjacent_to
 if cell is None:cell=engine.rulings.decide({'type':'type_ace_stealth_rock_cell','feature':feature,'actor':p.name,'adjacent_to':target.name})
 cell=__import__('terrain_actions').point(cell)
 if not any(grid.cheb(cell,x)==1 for x in B.cells(target,require_complete=True)) or cell in B.cells(target,require_complete=True):raise ValueError('actual adjacent Stealth Rock placement required')
 return H._install_region(engine,p,feature,H._definition(engine.r,feature),{cell},__import__('world_entities').actor_index(engine))


def _boulder(engine,a,p,hits,options,x):
 import forced_movement as FM
 directions=options.get('pushes',{});cells=options.get('rocks',{})
 if set(directions)!=set(t.entity_id for t in hits) or set(cells)!={t.entity_id for t in hits if t.side!=p.side}:raise ValueError('actual push and adjacent rock choice for every hit target required')
 for t in hits:
  d=directions[t.entity_id]
  if type(d) is not dict or set(d)!={'direction','distance'}:raise ValueError('direction and actual push distance required')
  C.integer(d['distance'],'Boulder push',0,x//2)
  FM.displace(engine,p,t,direction=d['direction'],distance=d['distance'],source=uid('Bigger and Boulder'))
  _timed(engine,t,uid('Bigger and Boulder'),statuses=['취약'])
  if t.side!=p.side:_place_rock(engine,p,uid('Bigger and Boulder'),cell=cells[t.entity_id],adjacent_to=t)


def preserve_rock(engine,instance):
 if instance['kind']!='stealth_rock':return False
 import grid
 for p in engine.everyone:
  row=sustained(engine,p,uid('Tough as Schist'))
  if row and p.on_field and not p.fainted and p.side==instance['owner_side'] and grid.cheb(p.pos,instance['cell'])<=4:
   # Maintaining is the printed default, consuming needs the explicit choice.
   return engine.rulings.decide({'type':'type_ace_consume_rock','actor':p.name,'hazard_id':instance['id'],'text':'Consume this allied Stealth Rock on its normal trigger?'}) is not True
 return False


def foiling(engine,a,p,move,*,seconds,reason):
 feature=uid('Foiling Foliage');require(engine,a,p,feature)
 def apply(e,t,q):
  _extended(e,t,q,feature,seconds,reason)
  return __import__('move_state').select_foiling(e,t,q,move,reason=reason,feature=feature)
 return G.transition(engine,a,apply,participants=(p,))


def trail(engine,a,p,path,*,mode):
 feature=uid('Trail Blazer');require(engine,a,p,feature)
 if '불꽃' not in p.types:raise ValueError('Fire Pokemon required')
 def apply(e,t,q):
  import movement_actions as M,turn as TURN
  _pay(e,t,q,feature);_once(e,t,feature+':scene',consume=True)
  if not TURN.spend(e,q,'shift',feature,movement=True):raise ValueError('actual Trail Blazer Shift required')
  _timed(e,q,feature,this_turn=False,ace_trail=True,ace_trail_round=e.round_no,ace_trail_cells=[])
  return M.follow_paid_path(e,q,path,mode=mode,maximum_distance=M.distance_budget(e,q,mode))
 return G.transition(engine,a,apply,participants=(p,),include_grid=True,include_rulings=True)


def enter_cell(engine,p,cell):
 import hazard_state as H,field_effects as FIELD,world_entities as W
 for row in __import__('combat_timing').records(p):
  if row.get('ace_trail') and row['ace_trail_round']==engine.round_no and len(row['ace_trail_cells'])<8 and list(cell) not in row['ace_trail_cells']:
   if FIELD.touches_ground(p):
    feature=uid('Trail Blazer');H._install_region(engine,p,feature,H._definition(engine.r,feature),{tuple(cell)},W.actor_index(engine));row['ace_trail_cells'].append(list(cell))


def _fire_cells(engine):
 import hazard_state as H
 return {cell for cell,envelope in H.ensure(engine).items() if any(i['kind']=='fire' for i in envelope['instances'])}


def _footprint(p):
 import body_state as B
 try:return B.cells(p,require_complete=True)
 except ValueError:return {tuple(p.pos)} if p.pos is not None else set()


def fire_boundary(engine,p):
 import hazard_state as H,field_effects as FIELD
 if not _fire_cells(engine) or not FIELD.touches_ground(p):return
 for cell in _footprint(p):
  for instance in H.ensure(engine).get(cell,{}).get('instances',[]):
   if instance['kind']=='fire':engine.apply_status(p,'화상',source=instance['source_id'],applied_by=H._owner(engine,instance));return


def clear_fire(engine,row):
 if row['move']['type'] not in ('땅','바위','물'):return
 import hazard_state as H
 if not _fire_cells(engine):return
 cells=set(tuple(x) for x in row['move'].get('_effect_area_cells',[]))
 for t in row['targets']:cells.update(_footprint(t))
 H._remove(engine,[i['id'] for cell,envelope in H.ensure(engine).items() if cell in cells for i in envelope['instances'] if i['kind']=='fire'])


def incoming_reduction(engine,a,p,move,mult):
 result=0
 # Enduring Bloom and Deep Cold stay with class_actor_state_reactions (existing pending-reaction owner).
 row=sustained(engine,p,uid('Tough as Schist'))
 if row and mult>1 and move['type'] in ('물','풀','땅','격투','강철'):
  import hazard_state as H,grid
  choices=[i for env in H.ensure(engine).values() for i in env['instances'] if i['kind']=='stealth_rock' and i['owner_side']==p.side and grid.cheb(i['cell'],p.pos)<=4]
  selected=engine.rulings.decide({'type':'type_ace_tough_rock','actor':p.name,'hazard_ids':[i['id'] for i in choices]})
  if selected in [i['id'] for i in choices]:
   H._remove(engine,[selected]);_timed(engine,p,uid('Tough as Schist'),ace_dr=rank(engine,row[0],'바위'));result+=rank(engine,row[0],'바위')
 if '얼음' in p.types and mult>1 and move['type'] in ('격투','불꽃','바위','강철') and _stat_owner(engine,p,'Glacial Ice'):
  chosen=engine.rulings.decide({'type':'type_ace_arctic_guard','actor':p.name,'move':move['id']})
  if type(chosen) is str:
   __import__('action_lifecycle').record_action(engine,p,'free')
   __import__('blessing_effects').spend_arctic(engine,p,p,chosen,{'mode':'damage_reduction','move_id':move['id']})
   result+=engine.tick(p)
 return result


def fountain(engine,p,move,rolled):
 s=scope(engine,p,move)
 if not s or s['feature']!=uid('Fountain of Life'):return rolled
 n=s['penalty'];C.integer(n,'Fountain penalty',0,min(3*rank(engine,s['trainer'],'물'),rolled//2))
 if not s['paid']:
  _pay(engine,s['trainer'],p,s['feature'],per_pokemon=True);s['paid']=True
  __import__('temporary_hp').grant(engine,p,2*n,provenance={'feature':s['feature'],'rolled_damage':rolled,'penalty':n})
  if s.get('status'):
   if s['status'] not in __import__('status_sets').afflictions(p):raise ValueError('actual Status Affliction required')
   engine.cure_status(p,s['status'])
 return rolled-n


def _lights(p):
 rows=[r for r in __import__('combat_timing').records(p) if 'ace_lights' in r]
 return rows[-1] if rows else None


def special(engine,a,p,feature,**options):
 """Printed Pokemon action costs are paid by the actual Pokemon."""
 feature=uid(feature);require(engine,a,p,feature);name=DEFINITIONS[feature]['english']
 import turn as TURN,combat_timing as TIME,movement_actions as MOVE,temporary_hp as HP
 outer=options
 def apply(e,t,q,*_):
  import world_entities as W
  options=_staged_options(W.actor_index(e),outer)
  if name=='Fairy Lights':
   if '페어리' not in q.types or not TURN.spend(e,q,'standard',feature):raise ValueError('Fairy Pokemon Standard required')
   _pay(e,t,q,feature)
   for row in list(TIME.records(q)):
    if 'ace_lights' in row:TIME.expire(e,q,row,ending='replaced')
   return _timed(e,q,feature,scene=True,ace_lights=3,ace_light_positions=None,ace_light_created_turn=q.custom_conditions.get('combat_turn_serial',0),ace_light_created_actions=len(getattr(q,'_action_history',[])))
  if name=='Fairy Rite':
   target=options.get('target');C.integer(options.get('hp'),'Fairy Rite sacrifice',0,q.level)
   if '페어리' not in q.types or target is None or target.side!=q.side or not e.adjacent(q,target):raise ValueError('adjacent ally and Fairy Pokemon required')
   pool=_lights(q)
   if not TURN.spend(e,q,'standard',feature):raise ValueError('Fairy Rite Standard required')
   _pay(e,t,q,feature);n=options['hp']
   e.lose_hp(q,n,source=feature);e.heal(target,n,source_kind='feature')
   recipients=options.get('lights',[]);pool=_lights(q)
   if type(recipients) is not list or len(recipients)>(pool or {}).get('ace_lights',0):raise ValueError('actual available Fairy Lights required')
   for recipient in recipients:
    if recipient is not q and (recipient.side!=q.side or __import__('grid').cheb(q.pos,recipient.pos)>6):raise ValueError('light healing ally within six required')
    e.heal(recipient,e.tick(recipient),source_kind='feature');pool['ace_lights']-=1
   return n
  if name=='Zephyr Shield':
   action=options.get('action')
   if '비행' not in q.types or action not in ('standard','shift'):raise ValueError('Flying Pokemon Standard Interrupt or own-turn Shift required')
   if not TURN.spend(e,q,action,feature):raise ValueError('Zephyr Shield action unavailable')
   _pay(e,t,q,feature)
   row=_timed(e,q,feature,next_turn=True,ace_zephyr=1)
   if action=='standard':row['ace_skip_flying_setup']=q.custom_conditions.get('combat_turn_serial',0)+1
   return row
  if name=='Ghost Step':
   if '고스트' not in q.types or not TURN.spend(e,q,'shift',feature):raise ValueError('Ghost Pokemon Shift required')
   _pay(e,t,q,feature,per_pokemon=True)
   mode=options.get('mode');cap=MOVE.distance_budget(e,q,mode)
   q.on_field=False
   _history(q,feature,origin=list(q.pos),mode=mode,maximum=cap,turn=q.custom_conditions.get('combat_turn_serial',0),pending=True)
   if sustained(e,q,uid('Haunting Curse')):_curse_token(e,q)
   return True
  if name=='Psionic Sponge':
   target=options.get('target');mid=e.r.move_id(options.get('move'));m=e.r.move(mid)
   if '에스퍼' not in q.types or target is None or target.side!=q.side or __import__('grid').cheb(q.pos,target.pos)>rank(e,t,'에스퍼') or mid not in target.moves or mid in q.moves or m['type']!='에스퍼':raise ValueError('within-rank ally actual unowned Psychic Move required')
   if not TURN.spend(e,q,'shift',feature):raise ValueError('Psionic Sponge Shift required')
   _pay(e,t,q,feature,per_pokemon=True);sid='psionic-sponge:'+q.entity_id
   G.grant_moves(q,[mid],sid,'feature',owner_id=t.entity_id,lifetime='turn_end',rule_id=feature,mode='permission')
   return _timed(e,q,feature,this_turn=True,grant_source=sid)
  if name=='Haunting Curse':return curse(e,t,q,**options)
  if name in ('Clever Ruse','Miasma'):
   if not TURN.spend(e,q,'standard',feature):raise ValueError('deliberate Pokemon Standard required')
   _pay(e,t,q,feature,round_only=name=='Clever Ruse')
   if name=='Clever Ruse':return _ruse(e,q,options)
   # A deliberate Smokescreen/Poison Gas uses the same actual extra-Move owner.
   return _extra_move(e,t,q,feature,{'move':{'id':'deliberate'},'targets':[options['target']]},options)
  raise ValueError('select an actual special-action Type Ace producer')
 return G.transition(engine,a,apply,participants=tuple(x for x in (p,options.get('target'),*options.get('lights',[])) if x is not None),include_rulings=True,include_grid=engine.grid is not None)


def _curse_token(engine,p):
 row=sustained(engine,p,uid('Haunting Curse'))
 if row:row[1]['tokens']=row[1].get('tokens',0)+1


def curse(engine,a,p,*,target,cost,stats=None):
 feature=uid('Haunting Curse');row=sustained(engine,p,feature)
 C.integer(cost,'Haunting Curse token cost',1,4)
 if not row or row[1].get('tokens',0)<cost or target.side==p.side or __import__('grid').cheb(p.pos,target.pos)>6:raise ValueError('actual sustained tokens and foe within six required')
 import turn as TURN,action_lifecycle as A
 if p.fainted:
  # The printed fainting Free exception is intentionally local.
  if not any(r.get('ace_faint_curse') for r in __import__('combat_timing').records(p)):raise ValueError('actual current fainting boundary required')
  A.record_action(engine,p,'free')
 elif not TURN.spend(engine,p,'standard',feature):raise ValueError('Haunting Curse Pokemon Standard required')
 row[1]['tokens']-=cost
 if cost==1:
  if type(stats) is not list or len(stats)!=1 or any(s not in ('atk','def','spa','spd','spe') for s in stats):raise ValueError('choose one lost Combat Stage')
  for s in stats:engine.change_stage(target,s,-1)
 elif cost==2:engine.apply_status(target,'저주',source=feature,applied_by=p)
 elif cost==3:engine.apply_status(target,'억압',source=feature,applied_by=p)
 else:
  engine.apply_status(target,'잠듦',source=feature,applied_by=p);engine.apply_status(target,'악몽',source=feature,applied_by=p)
 return True


def ghost_hidden(p):return any(r.get('source')==uid('Ghost Step') and r.get('pending') for r in p.spec.get(KEY,[]))


def blocks_hit(engine,a,p,move):
 if ghost_hidden(p):return uid('Ghost Step')
 if _buff(p,'ace_zephyr') and '가루' in set(move.get('keywords') or []):return uid('Zephyr Shield')
 if any(r.get('ace_chitin_move')==move['id'] for r in __import__('combat_timing').records(p)):return uid('Chitin Shield')
 return None


def incoming_hit(engine,a,p,move,hit):
 feature=uid('Chitin Shield')
 t=choose(engine,p,feature,trigger='hit_status_move',move=move['id']) if hit and '벌레' in p.types and move['class']=='변화' else None
 if t:
  _pay(engine,t,p,feature,per_pokemon=True);_timed(engine,p,feature,scene=True,ace_chitin_move=move['id']);return False
 pool=_lights(p)
 if pool and pool['ace_lights']>0 and a.side!=p.side and __import__('grid').cheb(a.pos,p.pos)<=6:
  choice=engine.rulings.decide({'type':'type_ace_fairy_light','actor':p.name,'attacker':a.name,'text':'Spend a light: temporary_hp or fairy_wind.'})
  if choice in ('temporary_hp','fairy_wind'):
   pool['ace_lights']-=1
   if choice=='temporary_hp':__import__('temporary_hp').grant(engine,p,engine.tick(p),provenance={'feature':uid('Fairy Lights')})
   else:_extra_move(engine,trainer(engine,p),p,uid('Fairy Lights'),{'move':move,'targets':[a]}, {'move':'move/요정의바람','target':a})
 return hit


def after_damage(engine,a,p,move,dealt,crit):
 if '바위' in p.types and (crit or p.fainted):
  feature=uid('Gravel Before Me');t=choose(engine,p,feature,trigger='critical_or_faint')
  if t:_pay(engine,t,p,feature);_place_rock(engine,p,feature)


def return_from_ghost(engine,p):
 for r in p.spec.get(KEY,[]):
  if r['source']!=uid('Ghost Step') or not r.get('pending'):continue
  answer=engine.rulings.decide({'type':'type_ace_ghost_return','actor':p.name,'origin':r['origin'],'mode':r['mode'],'maximum':r['maximum'],'text':'Observed continuous reachable return path.'})
  if type(answer) is not list or not answer:raise ValueError('actual reachable Ghost Step return path required')
  import movement_actions as M,body_state as B,map_terrain as TERRAIN
  from copy import copy
  probe=copy(p);probe.spec=dict(p.spec);mode=r['mode'];spent=0;diagonals=getattr(p,'_diagonal_steps',0)
  for node in answer:
   if mode in ('sky','levitate'):
    if type(node) is not dict:raise ValueError('actual aerial return path required')
    point=M._point(node.get('position'));height=node.get('altitude');M._aerial_height(engine,probe,mode,height)
    segment=[{'position':probe.pos,'altitude':probe.spec.get('_movement_altitude',0)},node]
    cost=M.observed_path(engine,probe,segment)['distance']
   else:
    point=M._point(node);height=probe.spec.get('_movement_altitude',0)
    cost,diagonals=M.step_cost(probe.pos,point,diagonals);cost+=M.slow_terrain_penalty(engine,probe,point,mode,step=cost)
   if not TERRAIN.can_travel(engine,probe,point,mode,altitude=height) or not B.can_place(engine,probe,point,origin=probe.pos,altitude=height):raise ValueError('Ghost Step return path is blocked')
   spent+=cost
   if spent>r['maximum']:raise ValueError('Ghost Step return exceeds actual Shift reach')
   probe.pos=point;probe.spec['_movement_altitude']=height
  # This is reappearance, not travel through intermediate hazards/AoOs.
  p.pos=probe.pos;M.entry_mode(p,mode,altitude=probe.spec.get('_movement_altitude',0));p.on_field=True
  r['pending']=False;r['reappeared']=True
  __import__('effects_ext').on_enter_cell(engine,p,p.pos)


def start_turn(engine,p):
 return_from_ghost(engine,p)
 returned=[r for r in p.spec.get(KEY,[]) if r.get('reappeared')]
 # Core123 Boo!: reappearance after Ghost Step, or after the preparation phase of
 # Phantom Force / Shadow Force whose actual resolution happens this turn.
 setup=getattr(p,'setup_move',None)
 if returned or setup in ('move/고스트다이브','move/섀도다이브'):
  for r in returned:r.pop('reappeared')
  feature=uid('Boo!');t=choose(engine,p,feature,trigger='actual_ghost_reappearance' if returned else 'actual_setup_reappearance',**({} if returned else {'move':setup}))
  if t:_pay(engine,t,p,feature);_timed(engine,p,feature,this_turn=True,ace_boo=True)
 feature=uid('Simple Improvements');t=choose(engine,p,feature,trigger='gains_initiative') if '노말' in p.types else None
 if t:
  _pay(engine,t,p,feature,per_pokemon=True);x=rank(engine,t,'노말')
  _timed(engine,p,feature,this_turn=True,ace_all_rolls=x);__import__('temporary_hp').grant(engine,p,2*x,provenance={'feature':feature})


def setup_skip(engine,p,move):
 serial=p.custom_conditions.get('combat_turn_serial',0)
 return move['type']=='비행' and any(r.get('ace_skip_flying_setup')==serial for r in __import__('combat_timing').records(p))


def mold(engine,a,p,row,*,changes,geometry,reason):
 """The actual Ground Move supplies the extra Groundshaper footprint."""
 feature=uid('Mold the Earth');require(engine,a,p,feature)
 if row['move']['type']!='땅':raise ValueError('actual completed Ground Move required')
 import terrain_actions as T,hazard_state as H,world_entities as W,body_state as B
 if geometry=='move_area':
  cells={tuple(x) for x in row['move'].get('_effect_area_cells',[])}
  if not cells:raise ValueError('actual Move area cells required')
 elif geometry=='around_target':
  if len(row['targets'])!=1:raise ValueError('one actual targeted cell required')
  x,y=row['targets'][0].pos;cells={(x,y),(x+1,y),(x-1,y),(x,y+1),(x,y-1)}
 else:raise ValueError('choose actual Move area or targeted cell and cardinal neighbors')
 if not {T.point(c['cell']) for c in changes}<=cells:raise ValueError('Groundshaper changes outside actual Move scope')
 scope={'pokemon':p,'completion_id':row['id'],'allowed_cells':[list(x) for x in sorted(cells)],'feature':feature}
 old=getattr(engine,'_type_ace_terrain',None);engine._type_ace_terrain=scope
 try:receipt=T.shape(engine,p,changes,reason=reason)
 finally:
  if old is None:del engine._type_ace_terrain
  else:engine._type_ace_terrain=old
 hazard_cells={tuple(c['cell']) for c in receipt['changes'] if c['after']['rough'] or c['after']['slow']}
 if hazard_cells:H._install_region(engine,p,feature,H._definition(engine.r,feature),hazard_cells,W.actor_index(engine))
 return receipt


def terrain_scope(engine,p):
 s=getattr(engine,'_type_ace_terrain',None)
 if s is None:return None
 if s['pokemon'] is not p:raise ValueError('actual Type Ace Groundshaper owner required')
 require(engine,trainer(engine,p),p,uid('Mold the Earth'));completion(engine,p,s['completion_id'])
 return s


def _tornado(p):return next((r for r in __import__('combat_timing').records(p) if r.get('ace_tornado')),None)


def tornado(engine,a,p):
 feature=uid('Tornado Charge');require(engine,a,p,feature)
 import movement_actions as M
 if engine._active_turn_actor is not p or getattr(p,'_action_history',[]):raise ValueError('actual gains-initiative boundary before actions required')
 def apply(e,t,q):
  _pay(e,t,q,feature);_once(e,q,feature,frequency={'kind':'daily','uses':1},consume=True)
  caps=M.capabilities(e,q)
  row=_timed(e,q,feature,this_turn=True,ace_tornado=True,ace_movement_spent=0,ace_capabilities={k:M.distance_budget(e,q,k) for k in M.MODES if caps.get(k,0)>0},ace_additional_standards=2)
  q.budget['standard']+=2
  return row
 return G.transition(engine,a,apply,participants=(p,))


def action_permission(engine,p,kind,move,what):
 row=_tornado(p)
 if not row or kind!='standard':return True
 if what==uid('Zephyr Shield'):return True
 if move is None:return False
 native=__import__('pokemon_move_edges').prepare(engine,p,move)
 return native['type']=='비행' and __import__('frequency').move_frequency(engine,native['id'],p)[0] in ('at_will','every_other_turn')


def movement_allowance(p,mode,amount):
 row=_tornado(p)
 return min(amount,max(0,row['ace_capabilities'].get(mode,0)-row['ace_movement_spent'])) if row else amount


def moved(p,distance):
 row=_tornado(p)
 if row:row['ace_movement_spent']+=distance


def action_cost(engine,p,move,current):
 s=scope(engine,p,move)
 return s.get('pokemon_action',current) if s else current


def mark_departure(engine,p,destination):
 marker=marked(engine,p)
 if marker is None or not engine.adjacent(marker,p):return
 from copy import copy
 import body_state as B
 probe=copy(p);probe.spec=dict(p.spec);probe.pos=tuple(destination)
 if not B.adjacent(marker,probe):__import__('turn').trigger_aoo(engine,p,'Close Quarters mark departure',[marker])


def smite(engine,p,target,move,set_damage):
 s=scope(engine,p,move)
 if not(move.get('_type_ace_boo') or s and s['feature']==uid('Gneiss Aim')):return 0
 import arithmetic_policy as M
 amount=M.ratio(engine.roll_damage(p,target,move,False,set_damage),2)
 engine.take_damage(target,amount);return amount


def aoo(engine,p,target,grant):
 feature=uid('Smashing Punishment');t=choose(engine,p,feature,trigger='actual_marked_opportunity_attack',target=target.name) if '격투' in p.types and marked(engine,target) is p else None
 if not t:return engine.use_move(p,target,'struggle',count_use=False,free_action=True,_action_grant=grant)
 _pay(engine,t,p,feature)
 s={'trainer':t,'pokemon':p,'feature':feature,'move_id':'struggle','type':'격투','ace_aoo':True,'paid':True}
 old=getattr(engine,'_type_ace_scope',None);engine._type_ace_scope=s
 try:return engine.use_move(p,target,'struggle',count_use=False,free_action=True,_action_grant=grant)
 finally:
  if old is None:del engine._type_ace_scope
  else:engine._type_ace_scope=old


def aoo_outcome(engine,p,move):
 s=scope(engine,p,move)
 return bool(s and s.get('ace_aoo'))


def lockdown(engine,p,condition,source,applied_by):
 if condition!='마비' or condition not in p.conditions or applied_by is None:return False
 feature=uid('Lockdown');a=owner(engine,applied_by,feature)
 if a is None or source not in engine.r.moves:return False
 move=__import__('pokemon_move_edges').prepare(engine,applied_by,engine.r.move(source))
 if move['type']!='전기' or move['class']=='변화' or choose(engine,applied_by,feature,trigger='would_paralyze_already_paralyzed',target=p.name) is None:return False
 _pay(engine,a,applied_by,feature);_timed(engine,p,feature,statuses=['구속'],at_will_moves_only=True);return True


def up_execution(engine,a,p,completion_id,targets,*,options=None):
 feature=uid('Upheaval');require(engine,a,p,feature);row=completion(engine,p,completion_id)
 kws=set(row['move'].get('keywords') or [])
 terrain=[r for r in p.spec.get('groundshaper_history',[]) if r.get('seconds')==engine.elapsed_seconds]
 if not terrain and not kws.intersection({'지면통과','Groundsource'}):raise ValueError('actual Groundsource or Groundshaper activation required')
 eligible=set(row['targets']);cells={tuple(c['cell']) for r in terrain for c in r['changes']}
 eligible.update(t for t in engine.everyone if t.pos in cells)
 if not targets or not set(targets)<=eligible:raise ValueError('actual targeted or changed-cell Trip recipients required')
 _pay(engine,a,p,feature)
 return [_trip(engine,a,p,t,feature,(options or {}).get(t.entity_id,{})) for t in targets]


def chain(engine,a,p,row,options):
 import weapon_actions as W
 feature=uid('Chain Lightning');mid=row['move']['id'];hits=_completed_targets(row)
 if W.range_spec(engine,row['move'],p).get('targets')!=1 or len(hits)!=1:raise ValueError('actual damaging one-target Electric hit required')
 chain_targets=options.get('targets')
 if type(chain_targets) is not list or not 1<=len(chain_targets)<=2:raise ValueError('choose second and optional third Chain Lightning recipients')
 previous=hits[0];results=[]
 for index,t in enumerate(chain_targets):
  __import__('world_entities').require_actors(engine,t)
  if t is previous or __import__('grid').cheb(previous.pos,t.pos)>3 or index==1 and (t is hits[0] or t.side==p.side):raise ValueError('printed Chain Lightning target geometry required')
  sid='type-ace-chain:'+p.entity_id+':'+str(index)
  s={'trainer':a,'pokemon':p,'feature':feature,'move_id':mid,'paid':True,'extra_move':True,'ignore_frequency':True,'damage_penalty':-5*(index+1),'chain_origin':previous}
  old=getattr(engine,'_type_ace_scope',None);engine._type_ace_scope=s
  try:result=engine.use_move_on(p,t,mid,engine.everyone,set_damage=options.get('set_damage',False))
  finally:
   if old is None:del engine._type_ace_scope
   else:engine._type_ace_scope=old
  results.append(result)
  completed=next((r for r in reversed(list(engine._move_completions.values())) if r['actor'] is p and r['move']['id']==mid and r['phase']=='complete'),None)
  if completed is None or t not in _completed_targets(completed):break
  previous=t
 return results


def _cap(p,*names):
 values={str(x).removeprefix('capability/').lower() for x in G.effective_capabilities(p)}
 return any(x.lower() in values for x in names)


def status_immunity(engine,p,condition):
 if _stat_owner(engine,p,'Insectoid Utility') is None:return False
 if condition=='넘어짐' and _cap(p,'벽타기','Wallclimber'):return True
 if condition in ('둔화','구속'):
  import movement_actions as M
  return M.ordinary_terrain(engine,p,p.pos)
 return False


def push_immunity(engine,p):
 return _stat_owner(engine,p,'Insectoid Utility') is not None and _cap(p,'벽타기','Wallclimber')


def poison_applied(engine,p,condition,source,issuer):
 if condition!='독' or issuer is None or issuer.side==p.side or '독' not in issuer.types:return
 feature=uid('Potent Venom');a=choose(engine,issuer,feature,trigger='actual_poison_inflicted',target=p.name)
 if a is None:return
 stat=engine.rulings.decide({'type':'type_ace_potent_venom_stat','actor':issuer.name,'target':p.name})
 if stat not in ('atk','def','spa','spd','spe'):raise ValueError('explicit Potent Venom Combat Stat required')
 _pay(engine,a,issuer,feature)
 p.custom_conditions['type_ace_poison']={'stat':stat,'rank':rank(engine,a,'독'),'source':feature,'owner':a,'issuer':issuer,'acquisition':acquired(a,feature)['request_id']}


def condition_effects(p,condition,effects):
 row=p.custom_conditions.get('type_ace_poison') if condition=='독' and '독' in p.conditions else None
 return [dict(x,stat=row['stat']) if row and x.get('type')=='combat_stage' and x.get('while')=='afflicted' else x for x in effects]


def poison_loss(p):
 row=p.custom_conditions.get('type_ace_poison')
 return row['rank'] if row and '독' in p.conditions else 0


def gravel(engine,p,trigger):
 if '바위' not in p.types:return
 feature=uid('Gravel Before Me');a=choose(engine,p,feature,trigger=trigger)
 if a:_pay(engine,a,p,feature);_place_rock(engine,p,feature)


def faint_boundary(engine,p):
 if sustained(engine,p,uid('Haunting Curse')):
  _timed(engine,p,uid('Haunting Curse'),this_turn=True,ace_faint_curse=True)
  choice=engine.rulings.decide({'type':'type_ace_faint_curse','actor':p.name,'text':'Optional actual foe identity, token cost, and stat choices at this fainting boundary.'})
  if choice is not None:
   target=__import__('world_entities').actor_index(engine).get(choice.get('target_id'))
   curse(engine,trainer(engine,p),p,target=target,cost=choice.get('cost'),stats=choice.get('stats'))
  for r in list(__import__('combat_timing').records(p)):
   if r.get('ace_faint_curse'):__import__('combat_timing').expire(engine,p,r)
 gravel(engine,p,'actual_faint')


def order_delivery(engine,a,p,feature):
 import perception_communicate as COMM
 if not engine.encounter_active or not p.on_field or p.fainted or p.captured:raise ValueError('available actual Order recipient required')
 policy={'id':'type-ace-order:'+feature,'source':feature,'capabilities':[],'requirements':[],'mode':'auditory','range':None,'path':'auditory','medium':[],'consent':{'kind':'none'},'blockers':[],'connection':None,'frequency':{'kind':'at_will','uses':1},'retry':None,'distance_exceptions':[]}
 request='type-ace-order:'+a.entity_id+':'+str(len(getattr(engine,COMM.KEY,{}).get('attempts',[]))+1)
 result=COMM.send(engine,a,p,policy,'Type Ace Order: '+feature,request_id=request)
 if result['status']!='delivered':raise ValueError('Type Ace Order communication was not delivered: '+str(result.get('reason')))
 return result


def threaded_scope(engine,p):
 s=getattr(engine,'_type_ace_threaded',None)
 if s is None:return None
 if s['pokemon'] is not p:return None
 require(engine,s['trainer'],p,uid('Insectoid Utility'))
 if not __import__('precise_threadings').owned(p):raise ValueError('actual Threaded capability required')
 return s


def threaded_config(engine,p,source,config):
 if threaded_scope(engine,p) is None:return config
 import threaded as T
 if config is None:
  skills=['전투','육상'] if source=='maneuver/밀기' else ['전투','곡예']
  config={'action_cost':'standard','accuracy':'ordinary','opposed':'required','success':'check','geometry':{'range':1,'remote':False,'vertical':False},'requirements':[], 'challenger_skills':skills,'defender_skills':skills,'resistance_purpose':'resist_push' if source=='maneuver/밀기' else 'resist_trip','challenger_purpose':None,'accuracy_class':'변화','opportunity':'other_adjacent'}
 out=deepcopy(config);out.update(action_cost=T.parameters(p)['action_cost'],geometry={'range':T.parameters(p)['range'],'remote':True,'vertical':False})
 return out


def threaded_maneuver(engine,a,p,target,maneuver,**options):
 require(engine,a,p,uid('Insectoid Utility'));__import__('threaded').require(engine,p,target)
 if maneuver not in ('trip','push','grapple','disarm'):raise ValueError('printed Threaded combat maneuver required')
 def apply(e,t,q,b):
  if hasattr(e,'_type_ace_threaded'):raise ValueError('nested Threaded maneuver')
  e._type_ace_threaded={'trainer':t,'pokemon':q}
  try:
   if maneuver=='disarm':return __import__('turn').disarm(e,q,b,**options)
   if maneuver=='grapple':return __import__('grapple_state').initiate(e,q,b,**options)
   return getattr(__import__('physics_maneuvers'),maneuver)(e,q,b,**options)
  finally:del e._type_ace_threaded
 return G.transition(engine,a,apply,participants=(p,target),include_grid=True,include_rulings=True)


def tornado_shift(engine,a,p,path,*,mode):
 require(engine,a,p,uid('Tornado Charge'));row=_tornado(p)
 import action_lifecycle as A,movement_actions as M,turn as TURN
 if row is None or engine._active_turn_actor is not p or not A.ordinary_permission(engine,p) or not TURN.movement_permission(engine,p):raise ValueError('actual Tornado Charge turn movement required')
 history=list(getattr(p,'_action_history',[]))
 standards=sum(x=='standard' for x in history)
 if not 1<=standards<=2 or standards==row.get('ace_after_standard'):raise ValueError('one Shift between actual Tornado Standard actions required')
 row['ace_after_standard']=standards
 A.record_action(engine,p,'free')
 return M.follow_paid_path(engine,p,path,mode=mode,maximum_distance=M.distance_budget(engine,p,mode))


def zephyr_interrupt(engine,a,p,*,trigger,priority=0,payment='next'):
 require(engine,a,p,uid('Zephyr Shield'))
 if '비행' not in p.types:raise ValueError('actual Flying Pokemon required')
 if payment not in ('current','next'):raise ValueError('explicit native Standard Interrupt payment required')
 import initiative_interrupts as I
 return I.queue(engine,[{'id':'zephyr:'+p.entity_id,'actor_id':p.entity_id,'source':uid('Zephyr Shield'),'priority':priority,'mode':'reaction','payment':payment,'budget':{'standard':1},'clock':'none'}],trigger=trigger)


def arctic(engine,a,p,blessing_id,*,mode,target=None,stat=None):
 require(engine,a,p,uid('Arctic Zeal'))
 if '얼음' not in p.types:raise ValueError('actual Ice Pokemon required')
 if mode not in ('weaken','stage'):raise ValueError('printed Arctic Zeal Swift choice required')
 target=p if mode=='stage' else target
 __import__('world_entities').require_actors(engine,target)
 if mode=='weaken' and (target.side==p.side or __import__('grid').cheb(p.pos,target.pos)>5):raise ValueError('actual foe within five required')
 if mode=='stage' and stat not in ('def','spd'):raise ValueError('Defense or Special Defense choice required')
 def apply(e,t,q,b):
  if not __import__('turn').spend(e,q,'swift',uid('Arctic Zeal')):raise ValueError('Arctic Zeal Swift unavailable')
  __import__('blessing_effects').spend_arctic(e,q,b,blessing_id,{'mode':mode,'stat':stat})
  if mode=='stage':e.change_stage(q,stat,1)
  else:_timed(e,b,uid('Arctic Zeal'),ace_damage=-5,statuses=['둔화'])
  return True
 return G.transition(engine,a,apply,participants=(p,target),include_rulings=True)


def control_lights(engine,a,p,*,positions,seconds,reason):
 require(engine,a,p,uid('Fairy Lights'));pool=_lights(p)
 if pool is None or type(positions) is not list or len(positions)!=pool['ace_lights']:raise ValueError('one actual position per remaining Fairy Light required')
 import terrain_actions as T,grid
 points=[T.point(x) for x in positions]
 if engine.grid is None or any(not engine.grid.inside(q) or grid.cheb(p.pos,q)>6 for q in points):raise ValueError('Fairy Lights remain within six meters')
 C.integer(seconds,'actual Extended seconds',1)
 def apply(e,t,q):
  if not __import__('turn').spend(e,q,'extended',uid('Fairy Lights')):raise ValueError('Fairy Light control Extended unavailable')
  e.advance_time(seconds,[t,q],source=uid('Fairy Lights'))
  _lights(q)['ace_light_positions']=[list(x) for x in points]
  return light_projection(e,q)
 return G.transition(engine,a,apply,participants=(p,))


def light_projection(engine,p):
 pool=_lights(p)
 if pool is None or not pool['ace_lights'] or not p.on_field or p.captured:return None
 positions=(pool.get('ace_light_positions') or [list(p.pos)]*pool['ace_lights'])[:pool['ace_lights']]
 # A candle-comparable emitter has no printed numeric radius. The common scene
 # light owner receives its emitter cells without inventing a wider radius.
 positions=[tuple(x) for x in positions if __import__('grid').cheb(p.pos,x)<=6]
 return {'source':uid('Fairy Lights'),'owner_id':p.entity_id,'quality':'mild_candle','positions':positions,'cells':positions}


def isolated_dragon(engine,a,t,move):
 if move['type']!='드래곤' or not _stat_owner(engine,a,'Highlander'):return False
 import body_state as B
 return not any(c is not a and c is not t and c.on_field and not c.captured and min(__import__('grid').cheb(x,y) for x in B.cells(t,require_complete=True) for y in B.cells(c,require_complete=True))<=2 for c in engine.everyone)


def after_accuracy(engine,a,t,move,natural,hit):
 if hit and natural>=18 and isolated_dragon(engine,a,t,move):_timed(engine,t,uid('Highlander'),statuses=['둔화'])
 if hit and natural>=16 and move['class']!='변화' and any(r.get('ace_disruption') for r in __import__('combat_timing').records(t)):
  engine.apply_status(t,'풀죽음',source=uid('Disruption Order'),applied_by=a)


def end_turn(engine,p):
 row=sustained(engine,p,uid('Unconquerable'))
 if not row:return
 allowed=p.conditions.intersection({'화상','혼란','저주','헤롱헤롱','잠듦','마비','독','맹독'})
 if not allowed or not choose(engine,p,uid('Unconquerable'),trigger='end_of_turn_save'):return
 status=engine.rulings.decide({'type':'type_ace_unconquerable_cure','actor':p.name,'statuses':sorted(allowed)})
 if not isinstance(status,str) or status not in allowed:raise ValueError('choose one actual printed Unconquerable affliction')
 result=__import__('condition_recovery').saving_check(engine,p,None,17)
 if result['passed']:engine.cure_status(p,status)
 return result


def move_interested(engine,p,t=None):
 """Completion-time Fey Trance approach rulings can be rejected; stage the whole move."""
 return bool(sustained(engine,p,uid('Fey Trance')))


def hp_interested(engine,p):
 return '드래곤' in p.types and owner(engine,p,uid('This Will Not Stand')) is not None


def hp_changed(engine,p,before,maximum):
 if not hp_interested(engine,p) or not before*2>maximum>=p.hp*2:return
 feature=uid('This Will Not Stand')
 if not __import__('frequency').activation_allowed(p,feature,{'kind':'scene','uses':1},engine=engine):return
 t=choose(engine,p,feature,trigger='above_half_to_half_or_below')
 if not t:return
 _pay(engine,t,p,feature,per_pokemon=True)
 engine.apply_status(p,'난동',source=feature,applied_by=p)
 for stat in ('atk','spa','spe'):engine.change_stage(p,stat,1)


def maneuver_hit(engine,p,t,source):
 if source in ('maneuver/걸기','maneuver/밀기','maneuver/잡기','maneuver/붙잡기','maneuver/그래플') and '격투' in p.types and p.side!=t.side and sustained(engine,p,uid('Close Quarters Mastery')):mark(engine,p,t)


def range_actor(engine,p,move):
 s=scope(engine,p,move)
 return s['chain_origin'] if s and s.get('chain_origin') else p


def validate(engine):
 import world_entities as W
 index=W.actor_index(engine)
 for p in index.values():
  __import__('pokemon_move_edges').mixed_power(p)
  for r in p.spec.get(KEY,[]):
   if not isinstance(r,dict) or r.get('source') not in FEATURES:raise ValueError('actual Type Ace history source required')
   if r.get('ability'):
    a=index.get(r.get('owner_id'))
    if a is None or r.get('branch') not in TYPES or r.get('ability') not in ('last_chance','strategist'):raise ValueError('Type Ace teaching provenance required')
    if r.get('acquisition') and not any(x['request_id']==r['acquisition'] for x in records(a,r['source'])):raise ValueError('Type Ace teaching acquisition changed')
   if r.get('pending') and r['source']==uid('Ghost Step') and p.on_field:raise ValueError('Ghost Step pending actor must actually be off field')
  row=p.custom_conditions.get('type_ace_poison')
  if row:
   a=row.get('owner');issuer=row.get('issuer')
   if '독' not in p.conditions or row.get('source')!=uid('Potent Venom') or row.get('stat') not in ('atk','def','spa','spd','spe') or a not in index.values() or issuer not in index.values() or not any(x['request_id']==row.get('acquisition') for x in records(a,uid('Potent Venom'))):raise ValueError('actual sourced Potent Venom condition required')
   import skill_modifiers as S
   ordinary={v['rank'] for v in S._declared_ranks(engine.r)[0].values()}
   effects={v['effective_rank'] for v in engine.r.skill_policy.get('rank_effects',{}).values()}
   if C.integer(row.get('rank'),'acquired Potent Venom rank',1) not in ordinary|effects:raise ValueError('invalid acquired Potent Venom rank')
 return True


def status_interested(engine,condition,issuer):
 if issuer is None:return False
 return bool(condition in ('독','맹독') and owner(engine,issuer,uid('Potent Venom')) or condition=='마비' and owner(engine,issuer,uid('Lockdown')))
