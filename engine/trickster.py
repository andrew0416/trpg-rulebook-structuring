"""PTU 1.05 Trickster: acquired choices and adapters to the native state owners.

The Core source is primary. Explicit KR/CSV choices keep their own printed
restrictions. A declaration is never a completed hit or an opportunity attack.
"""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import hashlib,json
import common_checks as C
import frequency as F
import state_grants as G
import combat_timing as TIME

CLASS='class/트릭스터';BAG='feat/온갖-수단';STACK='feat/짜여진-판'
FLOURISH='feat/과장된-동작';ENCORE='feat/앙코르-공연';SLEIGHT='feat/술책'
MIND='mind_games';ESCAPE='escape_artist';SHELL='shell_game';IMPROMPTU='impromptu_trick'
TECHNIQUES=(MIND,ESCAPE,SHELL,IMPROMPTU)
SOURCE_SHA256='a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'
FEATURES={CLASS:(1033,1035),BAG:(1037,1042),STACK:(1044,1055),FLOURISH:(1057,1063),ENCORE:(1065,1073),SLEIGHT:(1075,1078)}
DEFINITIONS={u:{'span':list(s),'catalog_span':[1020,1020] if u==CLASS else [1075,1082] if u==SLEIGHT else list(s),
 'clause_id':{FLOURISH:'C04-044',ENCORE:'C04-045',SLEIGHT:'C04-046'}.get(u,'input/ch04-trainer-classes.md:'+str(s[0])+'-'+str(s[1])),
 'ranked':u==BAG,'max_rank':2,'guile':{CLASS:3,STACK:4,ENCORE:5,SLEIGHT:6}.get(u,0),
 'feature_count':{ENCORE:3,SLEIGHT:4}.get(u,0)} for u,s in FEATURES.items()}
CSV={STACK:'C2CSV/input/db/feats.csv:R157:main',FLOURISH:'C2CSV/input/db/feats.csv:R158:main',ENCORE:'C2CSV/input/db/feats.csv:R159:main',
 MIND:'C2CSV/input/db/class-data.csv:R21:technique',ESCAPE:'C2CSV/input/db/class-data.csv:R22:technique',SHELL:'C2CSV/input/db/class-data.csv:R23:technique',IMPROMPTU:'C2CSV/input/db/class-data.csv:R24:technique'}
GROUPS=(('악몽','저주','씨앗상태','씨뿌리기','화상','독'),('마비','얼음','조이기','잠듦'),('혼란','난동','억압','헤롱헤롱'))
STACK_KEY='_trickster_stacked';FIRST_SAVE='_trickster_first_save';EXTRA='_trickster_encore_standard'


def install(rules):
 contract=json.loads((Path(rules.root)/'data/trickster-source-contract.json').read_text(encoding='utf-8'))
 for file,sha in contract['source_files'].items():
  if hashlib.sha256((Path(rules.root)/file).read_bytes()).hexdigest()!=sha:raise ValueError('Trickster source changed: '+file)
 # This is the selected Ability's printed keyword, not a category invented
 # from damage reduction or the name of a defensive maneuver.
 rows=json.loads((Path(rules.root)/'output/entities/abilities.json').read_text(encoding='utf-8'))
 rules.trickster_defensive={r['id'] for r in rows if '방어적' in r.get('effect','') or 'Defensive' in r.get('effect','')}


def records(actor,feature=None,active=False):
 import trainer_feature_acquisition as T
 return [record for _, record in T.static_family_acquisitions(actor, FEATURES, feature, active=active)]


def acquired(actor,feature):
 rows=records(actor,feature,True)
 if len(rows)>1 and feature!=BAG:raise ValueError('one exact acquired Trickster Feature required')
 return rows[-1] if rows else None


def acquisition_snapshot(engine,actor,feature,rank=None,selection=None):
 import skill_modifiers as S
 selection={} if selection is None else deepcopy(selection)
 if type(selection) is not dict or set(selection)-{'source','techniques','technique_sources'}:raise ValueError('exact Trickster source and Technique choices required')
 source=selection.get('source','core')
 allowed=('core','kr',CSV.get(feature))
 if feature==BAG:allowed=('core','kr','C2CSV/input/db/feats.csv:R'+str(154+rank)+':main') if rank in (1,2) else ()
 if source not in allowed or source is None:raise ValueError('explicit reviewed Trickster source required')
 selection['source']=source
 result={'guile':S.rank(engine.r,actor,'교활')[2],
  'parents':[] if feature==CLASS else [r['request_id'] for r in records(actor,CLASS,True)],
  'features':[r['request_id'] for r in records(actor,active=True)],'selection':selection}
 if feature==BAG:
  if rank not in (1,2):raise ValueError('Bag of Tricks requires rank 1 or 2')
  values=selection.get('techniques')
  if type(values) is not list or len(values)!=2 or any(v not in TECHNIQUES for v in values):raise ValueError('each Bag of Tricks rank selects two real Techniques')
  origins=selection.setdefault('technique_sources',{})
  if type(origins) is not dict or set(origins)-set(values) or any(v not in ('core','kr',CSV.get(k)) for k,v in origins.items()):raise ValueError('reviewed source for each actual selected Technique required')
  result.update(rank_number=rank,previous=None if rank==1 else next((r['request_id'] for r in records(actor,BAG,True) if r['snapshot']['rank_number']==1),None))
 elif rank is not None or set(selection)-{'source'}:raise ValueError('this Trickster Feature has no rank or Technique selection')
 return result


def qualification(actor,feature,snapshot,prerequisite_source):
 import acquisition_qualification as Q
 fields={'guile','parents','features','selection'}|({'rank_number','previous'} if feature==BAG else set())
 if prerequisite_source is not None or type(snapshot) is not dict or set(snapshot)!=fields:raise ValueError('exact Trickster acquisition observations required')
 C.integer(snapshot['guile'],'actual Guile rank',1,6)
 known={r['request_id'] for r in records(actor)}
 if type(snapshot['features']) is not list or len(set(snapshot['features']))!=len(snapshot['features']) or not set(snapshot['features'])<=known:raise ValueError('actual Trickster Feature acquisition receipts required')
 checks=[Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),
  Q.check('guile','prerequisite',snapshot['guile']>=DEFINITIONS[feature]['guile'],'printed Guile rank required')]
 if feature!=CLASS:
  parents={r['request_id'] for r in records(actor,CLASS)}
  checks.append(Q.check('class','prerequisite',bool(snapshot['parents']) and set(snapshot['parents'])<=parents,'actual acquired Trickster class required'))
 checks.append(Q.check('features','prerequisite',len(snapshot['features'])>=DEFINITIONS[feature]['feature_count'],'printed number of Trickster Features required'))
 if feature==BAG:
  C.integer(snapshot['rank_number'],'Bag rank',1,2)
  if snapshot['rank_number']==2:
   checks.append(Q.check('rank','prerequisite',any(r['request_id']==snapshot['previous'] and r['snapshot']['rank_number']==1 for r in records(actor,BAG)),'actual first Bag rank required'))
  elif snapshot['previous'] is not None:raise ValueError('first Bag rank has no predecessor')
  values=snapshot['selection'].get('techniques')
  if type(values) is not list or len(values)!=2 or any(v not in TECHNIQUES for v in values):raise ValueError('two explicit Technique choices required')
 return Q.require(feature,'native','acquire',checks)


def technique(actor,name):
 rows=[r for r in records(actor,BAG,True) if name in r['snapshot']['selection']['techniques']]
 if not rows:return None
 origins={r['snapshot']['selection'].get('technique_sources',{}).get(name,r['snapshot']['selection']['source'] if r['snapshot']['selection']['source'] in ('core','kr') else CSV[name]) for r in rows}
 if len(origins)!=1:raise ValueError('different acquired sources for this Technique require explicit selection')
 return {'feature':rows[-1],'source':origins.pop()}


def source(actor,feature):
 row=acquired(actor,feature)
 if row is None:raise ValueError('actual acquired Trickster Feature required: '+feature)
 return row['snapshot']['selection']['source']


def owner(engine,pokemon,feature=CLASS,*,tech=None):
 if pokemon.kind!='pokemon':return None
 import world_entities as W
 matches=[]
 for trainer in W.actor_index(engine).values():
  if trainer.kind!='trainer' or not acquired(trainer,feature):continue
  if pokemon.spec.get('trainer_id') is not None:
   if trainer.spec.get('id')!=pokemon.spec['trainer_id']:continue
   if pokemon.spec.get('trainer') is not None and pokemon.spec['trainer']!=trainer.name:raise ValueError('conflicting actual Pokemon ownership')
  elif pokemon.spec.get('trainer')!=trainer.name:continue
  if tech is None or technique(trainer,tech):matches.append(trainer)
 if len(matches)>1:raise ValueError('unambiguous actual Trickster owner required')
 return matches[0] if matches else None


def require(engine,trainer,pokemon,feature=CLASS,*,tech=None):
 import world_entities as W
 W.require_actors(engine,trainer,pokemon)
 if not engine.encounter_active or owner(engine,pokemon,feature,tech=tech) is not trainer:raise ValueError('actual acquired owner of this Pokemon and Trickster source required')
 if not pokemon.on_field or pokemon.fainted or pokemon.captured:raise ValueError('available actual Pokemon required')
 if not __import__('turn').can_act(engine,trainer):raise ValueError('Trickster owner cannot act')
 return trainer


def _charge(e,t,feature,*,ap=0,quota=None,action='free'):
 import action_points as AP,action_lifecycle as A,turn as TURN
 if ap and AP.available(t)<ap:raise ValueError('Trickster requires available AP')
 if quota and not F.activation_allowed(t,feature,quota,engine=e):raise ValueError('Trickster frequency exhausted')
 if action=='free':A.triggered_free_action(e,t,feature)
 elif not TURN.spend(e,t,action,feature):raise ValueError('Trickster action unavailable')
 if ap:AP.spend(t,ap)
 if quota:F.consume_activation(t,feature,quota,engine=e)


def _completion(e,p,token):
 row=getattr(e,'_move_completions',{}).get(token)
 if not row or row['actor'] is not p or row['phase']!='complete' or not row['sealed']:raise ValueError('actual completed whole Move required')
 if row['round']!=e.round_no or row.get('trickster_scene')!=F.state(p)['scene']:raise ValueError('actual current Trickster trigger required')
 if getattr(e,'_trickster_trigger',None)!=token:raise ValueError('Trickster requires the immediate completed Move')
 return row


def _hit(e,p,target,token):
 row=_completion(e,p,token)
 import move_completion as COMPLETE
 actual=COMPLETE.recipient_result(row,target)
 if target.side is None or p.side is None or p.side==target.side or not actual or not actual['hit'] or actual.get('cancelled'):raise ValueError('actual completed hit on a foe required')
 events=[uid for uid,r in row.get('native_returns',{}).items() if r['facts']['recipient_id']==target.entity_id]
 if events:COMPLETE.require_hit_return(e,events[-1],target)
 elif target.entity_id in row.get('received',{}) or any(v.get('completion_id')==token and v.get('target') is target for v in getattr(e,'_passive_events',{}).values()):raise ValueError('actual native recipient return required')
 return row


def begin_move(e,row):
 e._trickster_trigger=None
 p=row['actor'];row['trickster_scene']=F.state(p)['scene']
 row['trickster_conditions_before']={c.entity_id:sorted(c.conditions) for c in row['targets']}
 row['trickster_stages_before']={c.entity_id:dict(c.stages) for c in row['targets']}
 row['trickster_sleight']=sleight_scope(e,p,row['move'])
 frame=row.get('native_action_frame',{})
 row['trickster_encore_action']=bool(frame.get('trickster_encore_action',False))


def after_move(e,row):
 # The completed row itself is the durable event; optional choices use public
 # entry points. Do not pay AP or silently select a branch during resolution.
 if row['phase']=='complete':
  row['trickster_completed']=True;e._trickster_trigger=row['id']


def accuracy_hit(e,p,target,move,completion,natural,critical):
 # The native recipient producer has already resolved accuracy and reactions.
 if not flourish_applies(e,p,target,move):return
 row=e._move_completions[completion]
 if row['actor'] is not p or row['move_id']!=move['id']:raise ValueError('actual Flourish recipient producer required')
 row.setdefault('trickster_accuracy',{})[target.entity_id]={'natural':natural,'critical':critical}


def hazard_trigger(e,p,target,instance):
 if p is None or owner(e,p) is None or p.side==target.side:return
 rows=p.custom_conditions.setdefault('_trickster_hazard_events',{})
 token='trickster-hazard:'+p.entity_id+':'+str(len(rows)+1)
 rows[token]={'id':token,'pokemon':p,'target':target,'instance_id':instance['id'],'source':instance['source_id'],'round':e.round_no,'scene':F.state(p)['scene'],'complete':True}
 e._trickster_trigger=token
 return token


def _trigger(e,p,target,token):
 current=getattr(e,'_trickster_trigger',None)
 if current!=token and not (isinstance(current,tuple) and token in current):raise ValueError('Trickster requires the immediate actual completed trigger')
 if token.startswith('trickster-hazard:'):
  row=p.custom_conditions.get('_trickster_hazard_events',{}).get(token)
  if not row or row['pokemon'] is not p or row['target'] is not target or not row['complete'] or row['round']!=e.round_no or row['scene']!=F.state(p)['scene']:raise ValueError('actual resolved Pokemon Hazard trigger required')
  return row
 row=_hit(e,p,target,token)
 if row['move']['class']!='변화':raise ValueError('Trickster requires a Status-Class Move hit')
 return row


def maneuver_context(e,p,target):
 row=getattr(e,'_trickster_maneuver',None)
 if row is None:return None
 if row['pokemon'] is not p or row['target'] is not target:raise ValueError('Trickster maneuver target/source changed')
 require(e,row['trainer'],p);_trigger(e,p,target,row['trigger'])
 return row


def action_recorded(e,kind,source):
 if kind!='free' or source not in (*FEATURES,*TECHNIQUES):e._trickster_trigger=None


def maneuver_spend(e,p,target):
 row=maneuver_context(e,p,target)
 if row is None:return False
 if not row.get('paid'):
  event=_trigger(e,p,target,row['trigger'])
  key=target.entity_id
  if key in event.get('trickster_maneuvers',[]):raise ValueError('Trickster trigger already consumed for this foe')
  _charge(e,row['trainer'],CLASS,ap=1)
  __import__('action_lifecycle').triggered_free_action(e,p,CLASS)
  event.setdefault('trickster_maneuvers',[]).append(key);row['paid']=True
 return True


def maneuver(e,trainer,pokemon,target,trigger,kind,choice,**options):
 require(e,trainer,pokemon);_trigger(e,pokemon,target,trigger)
 if kind not in ('dirty_trick','manipulate'):raise ValueError('choose Dirty Trick or Manipulate')
 if 'fixed_accuracy' in options:raise ValueError('Trickster has automatic accuracy, no invented roll')
 previous=getattr(e,'_trickster_maneuver',None)
 if previous is not None:raise ValueError('finish the actual Trickster maneuver before nesting another')
 e._trickster_maneuver={'trainer':trainer,'pokemon':pokemon,'target':target,'trigger':trigger,'kind':kind}
 try:return getattr(__import__('combat_maneuvers'),kind)(e,pokemon,target,choice,**options)
 finally:del e._trickster_maneuver


def stacked_deck(e,trainer,pokemon,target,completion,condition):
 require(e,trainer,pokemon,STACK);row=_hit(e,pokemon,target,completion)
 if condition not in set().union(*map(set,GROUPS)) or condition not in target.conditions:raise ValueError('choose an actual printed condition on the hit foe')
 key=STACK+':target:'+target.entity_id
 def apply(staged,t,p,v):
  if not F.activation_allowed(v,key,{'kind':'scene','uses':1},engine=staged):raise ValueError('Stacked Deck affected this foe this Scene')
  _charge(staged,t,STACK,ap=1);F.consume_activation(v,key,{'kind':'scene','uses':1},engine=staged)
  group=next(i for i,values in enumerate(GROUPS) if condition in values)
  rec={'source':STACK,'trainer':t,'pokemon':p,'condition':condition,'group':group,'completion':completion,'consumed':False}
  v.custom_conditions.setdefault(STACK_KEY,[]).append(rec)
  if group==2:TIME.install(staged,v,{'source':STACK,'manual_end':True,'trickster_condition':condition,'accuracy_modifier':-2,'evasion_modifier':-2,'effect_contract':True})
  return {'status':'applied','condition':condition,'group':group}
 return G.transition(e,trainer,apply,participants=(pokemon,target),include_rulings=True)


def condition_ended(e,actor,condition):
 for rec in list(TIME.records(actor)):
  if rec.get('trickster_condition')==condition:TIME.expire(e,actor,rec)
 for key in (STACK_KEY,FIRST_SAVE):
  if key in actor.custom_conditions:
   actor.custom_conditions[key]=[r for r in actor.custom_conditions[key] if r['condition']!=condition]
   if not actor.custom_conditions[key]:actor.custom_conditions.pop(key)


def loss(e,actor,before,source,*,condition=None):
 if actor.hp>=before or not actor.custom_conditions.get(STACK_KEY):return
 conditions={__import__('status_sets').normalize(source.removeprefix('condition/'))}
 # Seeded is a real linked Move condition, not a bare status flag. Its HP
 # consumer supplies the creating Move source; keep that source attribution.
 linked=[r for r in __import__('condition_instances').records(actor) if r['source']==source and r.get('effect',{}).get('condition')]
 # Seeded measures and heals its own loss before the separate additional loss.
 if condition is None and any(r['effect'].get('operation')=='seed_drain' for r in linked):return
 conditions.update(r['effect']['condition'] for r in linked)
 if condition is not None:conditions.add(condition)
 for row in list(actor.custom_conditions.get(STACK_KEY,[])):
  if row['group']==0 and row['condition'] in conditions and row['condition'] in actor.conditions:
   e.lose_hp(actor,5,source=STACK)


def save_penalty(actor,condition):
 return -4 if any(r['condition']==condition and not r.get('consumed') for r in actor.custom_conditions.get(FIRST_SAVE,[])) else 0


def saved(e,actor,condition,passed):
 for row in actor.custom_conditions.get(FIRST_SAVE,[]):
  if row['condition']==condition and not row.get('consumed'):row['consumed']=True
 if not passed:return
 for row in actor.custom_conditions.get(STACK_KEY,[]):
  if row['group']==1 and row['condition']==condition and not row['consumed']:
   row['consumed']=True;e.apply_status(actor,'넘어짐');e.apply_status(actor,'둔화')


def flourish_applies(e,p,target,move):
 return bool(move and move.get('class')=='변화' and p.side is not None and target.side is not None and p.side!=target.side and owner(e,p,FLOURISH))


def flourish(e,trainer,pokemon,completion,choice,*,stat=None):
 require(e,trainer,pokemon,FLOURISH);row=_completion(e,pokemon,completion)
 import move_completion as MC
 targets=[t for t in MC.actual_recipients(row) if MC.recipient_result(row,t)['hit'] and not MC.recipient_result(row,t).get('cancelled') and t.side!=pokemon.side]
 critical=[t for t in targets if row.get('trickster_accuracy',{}).get(t.entity_id,{}).get('critical') and row['trickster_accuracy'][t.entity_id]['natural'] is not None]
 if row['move']['class']!='변화' or not critical:raise ValueError('actual natural-roll Status critical required')
 if row.get('trickster_flourish'):raise ValueError('this actual Flourish critical was already resolved')
 if choice not in ('first_save','stage','temporary_hp'):raise ValueError('choose one printed Flourish outcome')
 conditions={t.entity_id:[c for c in t.conditions if c not in row['trickster_conditions_before'].get(t.entity_id,[])] for t in targets}
 mm,_=e.r.move_mech(row['move_id'])
 lowered={x['stat'] for x in mm.get('stage_changes_exec',[]) if x.get('delta',0)<0 and x.get('target')!='self'}
 lowered|={x['stat'] for x in mm.get('effects_exec',[]) if x.get('type')=='stage_change' and x.get('delta',0)<0 and x.get('target')!='self'}
 if choice=='stage' and stat not in lowered:raise ValueError('choose a stat actually lowered by this Move')
 saved_conditions={uid:[c for c in values if any(x.get('type')=='save' for x in e.r.condition_effects(c)) or c=='혼란' and __import__('confusion_attacks').core(e)] for uid,values in conditions.items()}
 if choice=='first_save' and not any(saved_conditions.values()):raise ValueError('Move must actually inflict a condition with a save')
 def apply(staged,t,p,*foes):
  actual=staged._move_completions[completion];actual['trickster_flourish']=choice
  if choice=='temporary_hp':__import__('temporary_hp').grant(staged,p,staged.tick(p),provenance={'source':FLOURISH,'completion':completion})
  for v in foes:
   if choice=='stage':__import__('effects').apply_stage_changes(staged,p,v,{stat:-1},source_id=FLOURISH)
   elif choice=='first_save':
    for condition in saved_conditions[v.entity_id]:
     v.custom_conditions.setdefault(FIRST_SAVE,[]).append({'source':FLOURISH,'condition':condition,'completion':completion,'consumed':False})
  return {'status':'applied','choice':choice}
 return G.transition(e,trainer,apply,participants=(pokemon,*targets),include_rulings=True)


def encore(e,trainer,pokemon,completion,choice,*,stat=None,cells=None):
 require(e,trainer,pokemon,ENCORE);row=_completion(e,pokemon,completion)
 if row['move']['class']!='변화' or any(t.side is not None and t.side!=pokemon.side for t in row['targets']):raise ValueError('Encore requires a Status Move not targeting foes')
 if row.get('trickster_encore_action') or row.get('trickster_encore'):raise ValueError('Encore cannot trigger itself or replay a completed choice')
 if choice not in ('stage','standard','hazard','weather','blessing'):raise ValueError('choose one of five printed Encore outcomes')
 if choice=='stage':
  if stat not in ('atk','def','spa','spd','spe'):raise ValueError('actual Combat Stage stat required')
  rises=__import__('stage_change_history').rises_since_turn_start(pokemon)
  if any(source(trainer,ENCORE)!='core' or ev['stat']==stat for ev in rises):raise ValueError('Encore stat already rose in the printed turn window')
 def apply(staged,t,p):
  actual=staged._move_completions[completion]
  if choice=='hazard':__import__('hazard_state').extend_from_completion(staged,p,actual,cells)
  elif choice=='weather':__import__('weather_state').extend_from_completion(staged,p,actual,2)
  elif choice=='blessing':__import__('blessing_effects').extend_from_completion(staged,p,actual,1)
  elif choice=='stage':staged.change_stage(p,stat,1)
  else:
   if p.custom_conditions.get(EXTRA,{}).get('round')==staged.round_no:raise ValueError('one second Standard in this round required')
   p.custom_conditions[EXTRA]={'round':staged.round_no,'completion':completion,'used':False,'trainer':t}
  _charge(staged,t,ENCORE,quota={'kind':'daily','uses':3});actual['trickster_encore']=choice
  return {'status':'applied','choice':choice}
 return G.transition(e,trainer,apply,participants=(pokemon,),include_rulings=True,include_grid=True)


def native_frame_required(e,p,source):
 row=p.custom_conditions.get(EXTRA)
 escape=getattr(e,'_trickster_escape',None)
 return (bool(row and not row['used'] and row['round']==e.round_no) or
  bool(escape and escape['pokemon'] is p and escape['move_id']==source))


def extra_standard(e,p,kind,move):
 row=p.custom_conditions.get(EXTRA)
 if kind!='standard' or not row or row['used'] or row['round']!=e.round_no:return False
 budget=getattr(p,'budget',None)
 if budget is None or budget.get('standard',0)>0:return False
 frames=getattr(e,'_native_action_stack',[])
 frame=frames[-1] if frames and frames[-1]['actor'] is p else None
 if move is not None:
  if not frame or frame['kind']!='move' or frame['source']!=move['id']:
   raise ValueError('Encore second Standard requires the actual native Move action boundary')
  frequency=F.move_frequency(e,move['id'],p)[0]
 else:
  uid=frame['source'] if frame else None
  unit=e.r.units.get(uid,{})
  metadata=unit.get('mech',{}).get('data',{})
  if not uid or e.r._selected_rule(uid)!=uid or metadata.get('frequency') is None:
   raise ValueError('Encore second Standard requires an actual sourced At-Will action declaration')
  frequency=F.parse(metadata['frequency'])[0]
 if frequency!='at_will':raise ValueError('Encore second Standard allows At-Will only')
 row['used']=True
 frame['trickster_encore_action']=True
 __import__('action_lifecycle').record_action(e,p,'standard',_triggered_source=ENCORE)
 return True


def mind_games(e,trainer,pokemon,target,completion,*,replace=None,with_condition=None):
 require(e,trainer,pokemon,tech=MIND);row=_hit(e,pokemon,target,completion)
 if not __import__('combat_social_edges').social(pokemon,row['move']):raise ValueError('Mind Games requires an actual Social Move hit')
 key=MIND+':target:'+target.entity_id
 volatile=GROUPS[2]
 if (replace is None)!=(with_condition is None) or replace is not None and (replace not in volatile or with_condition not in volatile or replace==with_condition or replace not in target.conditions):raise ValueError('choose one actual listed volatile condition and a different listed replacement')
 count=TIME.current(e)
 def apply(staged,t,p,v):
  if not F.activation_allowed(v,key,{'kind':'scene','uses':1},engine=staged):raise ValueError('Mind Games already affected this foe this Scene')
  _charge(staged,t,MIND,quota={'kind':'scene','uses':2});F.consume_activation(v,key,{'kind':'scene','uses':1},engine=staged)
  TIME.install(staged,v,{'source':BAG,'statuses':['취약'],'count_deadline':(staged.round_no+1,count),'encounter_end':True,'trickster_technique':MIND})
  if replace is not None:
   staged.cure_status(v,replace)
   previous=getattr(staged,'_inflictor',None);staged._inflictor=p
   try:staged.apply_status(v,with_condition)
   finally:staged._inflictor=previous
  return {'status':'applied','replacement':with_condition}
 return G.transition(e,trainer,apply,participants=(pokemon,target),include_rulings=True)


def escape_artist(e,trainer,pokemon,target,move_id,destination,**options):
 require(e,trainer,pokemon,tech=ESCAPE)
 move=e.r.move(move_id)
 if move['class']!='변화' or not e.adjacent(pokemon,target) or pokemon.side==target.side:raise ValueError('Escape Artist requires an adjacent foe targeted by a Status Move')
 key=ESCAPE+':pokemon:'+pokemon.entity_id
 # Native move and movement both run in one transaction; invalid destination,
 # unavailable Move/frequency or a failed native continuation cannot spend AP.
 def apply(staged,t,p,v):
  if not F.activation_allowed(p,key,{'kind':'scene','uses':1},engine=staged):raise ValueError('Escape Artist was used for this Pokemon this Scene')
  _charge(staged,t,ESCAPE,ap=1);F.consume_activation(p,key,{'kind':'scene','uses':1},engine=staged)
  staged._trickster_escape={'pokemon':p,'target':v,'move_id':move['id'],'source':ESCAPE}
  try:
   previous=set(getattr(staged,'_move_completions',{}))
   staged.use_move_on(p,v,move['id'],staged.everyone,**options)
   _new_completion(staged,p,move['id'],previous)
   return __import__('turn').disengage(staged,p,destination,_trickster_escape=True)
  finally:del staged._trickster_escape
 return G.transition(e,trainer,apply,participants=(pokemon,target),include_rulings=True,include_grid=True)


def prevents_aoo(e,p):
 row=getattr(e,'_trickster_escape',None)
 stack=getattr(e,'_native_action_stack',[])
 return bool(row and row['pokemon'] is p and stack and stack[-1]['actor'] is p and stack[-1]['source']==row['move_id'])


def shell_game(e,trainer,pokemon,kind,destinations,*,placement=None):
 require(e,trainer,pokemon,tech=SHELL)
 scope=technique(trainer,SHELL)['source']
 if placement is not None:
  row=_completion(e,pokemon,placement)
  if not row['move'].get('_hazard_cells'):raise ValueError('Shell Game Free use requires actual Hazard placement')
 elif scope!='core':raise ValueError('selected KR/CSV Shell Game requires the printed placement trigger')
 def apply(staged,t,p):
  result=__import__('hazard_state').relocate_allied(staged,t,p,kind,destinations,source=scope)
  _charge(staged,t,SHELL,quota={'kind':'scene','uses':2},action='free' if placement is not None else 'standard')
  return result
 return G.transition(e,trainer,apply,participants=(pokemon,),include_rulings=True,include_grid=True)


def sleight_scope(e,p,move):
 row=getattr(e,'_trickster_sleight',None)
 return bool(row and row['pokemon'] is p and row['move_id']==move['id'] and move['class']=='변화')


def bypass(e,p,target,move):
 return bool(sleight_scope(e,p,move) and p.side is not None and target.side is not None and p.side!=target.side)


def ignores_defensive(e,target,ability):
 row=getattr(e,'_trickster_sleight',None)
 if not row or not bypass(e,row['pokemon'],target,e.r.move(row['move_id'])):return False
 import ability_transitions as A
 uid=A.ability_id(e.r,ability)
 return e.r._selected_rule(uid)==uid and uid in e.r.trickster_defensive


def set_contains(e,target,field,value):
 """Read the real set owners; Sleight does not erase item/GM contributions."""
 if not hasattr(target,field):return False
 members=getattr(target,field)
 if not isinstance(members,(set,frozenset)):raise ValueError('actual immunity set required: '+field)
 if value not in members:return False
 row=target.spec.get(G.KEY,{}).get('sets',{}).get(field)
 if row is None or value in row['base']:return True
 for source,values in row['sources'].items():
  if value in values and not (source.startswith('ability:') and ignores_defensive(e,target,source.removeprefix('ability:'))):return True
 return False


def sleight(e,trainer,pokemon,*,move_id,target=None,aim=None,trigger=None,request_id=None,**options):
 require(e,trainer,pokemon,SLEIGHT)
 move=e.r.move(move_id)
 if move['class']!='변화' or move['id'] not in {e.r.resolve_move(x) for x in pokemon.moves}:raise ValueError('Sleight requires an actual learned Status Move')
 if trigger is None:raise ValueError('actual initiative interrupt boundary required')
 import initiative_interrupts as I
 request_id=request_id or 'sleight:'+pokemon.entity_id+':'+str(e.round_no)+':'+str(len(getattr(e,'_move_completions',{})))
 def apply(staged,t,p,*actual):
  foe=actual[0] if actual else None
  result=I.queue(staged,[{'id':request_id,'actor_id':p.entity_id,'source':SLEIGHT,'priority':0,'mode':'borrow_turn','payment':'future_turn','budget':None,'clock':'owner_turn','settlement_clock':'none'}],trigger=trigger)
  if result['status']=='pending':raise ValueError('Sleight requires a fully specified actual interrupt boundary')
  _charge(staged,t,SLEIGHT,quota={'kind':'scene','uses':2})
  I.begin(staged,result['window_id'],request_id)
  staged._trickster_sleight={'trainer':t,'pokemon':p,'move_id':move['id']}
  try:
   previous=set(getattr(staged,'_move_completions',{}))
   if __import__('blessing_effects').definition(staged.r,move['id']) is not None:
    if aim is not None or foe not in (None,p):raise ValueError('Blessing Move uses its actual creator as native activation anchor')
    staged.use_move(p,p,move['id'],**options)
   elif aim is None:staged.use_move_on(p,foe or p,move['id'],staged.everyone,**options)
   else:staged.use_move_on(p,foe or p,move['id'],staged.everyone,aim=aim,**options)
   _new_completion(staged,p,move['id'],previous)
   if getattr(p,'budget',{}).get('standard',1)!=0:raise ValueError('Sleight must actually use its Standard for the Status Move')
   I.finish(staged)
  finally:del staged._trickster_sleight
  return {'status':'applied','window':result['window_id']}
 return G.transition(e,trainer,apply,participants=(pokemon,*((target,) if target is not None else ())),include_rulings=True,include_grid=True)


def impromptu(e,p,target,why):
 trainer=owner(e,p,tech=IMPROMPTU)
 if trainer is None:return False
 answer=e.rulings.decide({'type':'trickster_impromptu','unit':BAG,'actor':trainer.name,'pokemon':p.name,'target':target.name,'why':why,'text':'Select an actually learned Hazard Move or At-Will/EOT Status Move, or decline.'})
 if answer is None or answer is False:return False
 if type(answer) is not dict or set(answer)-{'move_id','aim'} or 'move_id' not in answer:raise ValueError('explicit Impromptu Move and actual aim required')
 require(e,trainer,p,tech=IMPROMPTU)
 move=e.r.move(answer['move_id']);mid=move['id']
 if mid not in {e.r.resolve_move(x) for x in p.moves}:raise ValueError('Impromptu requires an actual learned Move')
 keywords=__import__('effects_ext').keywords_for(p,move)
 hazard=bool(keywords.intersection(('Hazard','함정')))
 if not hazard and not (move['class']=='변화' and F.move_frequency(e,mid,p)[0] in ('at_will','every_other_turn')):raise ValueError('Impromptu allows Hazard OR At-Will/EOT Status Move')
 allowed,reason=F.move_allowed(e,p,mid)
 if not allowed:raise ValueError(reason)
 _charge(e,trainer,IMPROMPTU,ap=1)
 e._trickster_impromptu={'pokemon':p,'target':target,'move_id':mid}
 try:
  previous=set(getattr(e,'_move_completions',{}))
  options={k:v for k,v in answer.items() if k!='move_id'}
  e.use_move_on(p,target,mid,e.everyone,**options)
  _new_completion(e,p,mid,previous)
 finally:del e._trickster_impromptu
 return True


def _new_completion(e,p,mid,previous):
 rows=[r for uid,r in getattr(e,'_move_completions',{}).items() if uid not in previous and r['actor'] is p and r['move_id']==mid]
 if len(rows)!=1 or rows[0]['phase']!='complete' or not rows[0]['sealed']:raise ValueError('Trickster requires the actual Move to complete')
 return rows[0]


def impromptu_scope(e,p,move=None):
 row=getattr(e,'_trickster_impromptu',None)
 event=getattr(e,'_opportunity_attack',None)
 return bool(row and row['pokemon'] is p and (move is None or row['move_id']==move['id']) and event and event.get('attacker_id')==p.entity_id and event.get('target_id')==row['target'].entity_id)
