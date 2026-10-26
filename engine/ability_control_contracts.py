"""Selected CSV controls: native geometry, clocks, statuses and payments."""
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
import csv,hashlib,io,json
import combat_timing as TIME
import state_grants as G
import world_entities as W

ARENA='ability/개미지옥-playtest'
SHADOW='ability/그림자밟기'
ANCHOR='ability/닻'
DAZZLING='ability/비비드바디'
MAGNET='ability/자력-playtest'
TAIL='ability/테일아머'
ROWS={ARENA:13,SHADOW:31,ANCHOR:82,DAZZLING:213,MAGNET:337,TAIL:624,
      'ability/닻-2':538,'ability/비비드바디-2':544}
COPIES={'ability/닻-2':ANCHOR,'ability/비비드바디-2':DAZZLING}
NAMES={ARENA:'개미지옥 [Playtest]',SHADOW:'그림자밟기',ANCHOR:'닻',
       DAZZLING:'비비드바디',MAGNET:'자력 [Playtest]',TAIL:'테일아머'}
ENGLISH={ARENA:'Arena Trap',SHADOW:'Shadow Tag',ANCHOR:'Anchored',
         DAZZLING:'Dazzling',MAGNET:'Magnet Pull',TAIL:'Armor Tail'}
CSV_SHA='87efebd17b0a5fe09c9db060a16a8844cf41be53d65eb35716cf62f80a177fae'
TAG='ability_control'
EDITION='ability_control_editions'
HISTORY='ability_control_history'
ATTACK='ability_control_attack'

@lru_cache(maxsize=1)
def _catalog(raw,extracted):
 if hashlib.sha256(raw).hexdigest()!=CSV_SHA:raise ValueError('control ability CSV source changed')
 rows=list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
 entries={r['id']:r for r in json.loads(extracted)}
 for uid,n in ROWS.items():
  row=rows[n-1];entry=entries[uid];canonical=COPIES.get(uid,uid)
  if (entry['name'],entry['frequency'],entry['effect'],entry['eng'])!=(row[0],row[1],row[2],row[7]):raise ValueError('selected control differs from CSV')
  if entry['_source'].get('file')!='db/abilities.csv' or entry['_source'].get('record_span')!=[n,n]:raise ValueError('control source row changed')
  if row[0]!=NAMES[canonical] or row[7]!=ENGLISH[canonical]:raise ValueError('control source identity changed')
  if uid in COPIES and row!=rows[ROWS[canonical]-1]:raise ValueError('control copy is no longer identical')
 return entries

def registration(rules,value):
 if value not in ROWS and value not in NAMES.values() and value not in ENGLISH.values():return None
 root=Path(rules.root)
 _catalog((root/'input/db/abilities.csv').read_bytes(),(root/'output/entities/abilities.json').read_bytes())
 uid=value if value in ROWS else next(k for k in NAMES if value in (NAMES[k],ENGLISH[k]))
 if rules._selected_rule(uid)!=uid:raise ValueError('exact selected control ability required')
 canonical=COPIES.get(uid,uid)
 return {'name':NAMES[canonical],'source_id':uid,'equivalent_source_ids':[canonical,*[k for k,v in COPIES.items() if v==canonical]]}

def _owns(actor,uid):return __import__('ability_transitions').active(actor,uid)
def _available(actor):return actor.on_field and not actor.captured and not actor.fainted and not actor.dead

def _anchor(engine,actor):
 key=actor.spec.get('ability_control_anchor')
 if key is None:return None
 obj=getattr(engine,'_physical_objects',{}).get(key)
 if obj is None or obj.get(TAG)!={'source':ANCHOR,'owner_id':actor.entity_id,'size':'medium','targetable':False,'cover':False}:raise ValueError('actual Anchored token required')
 return obj

def register(engine,actor,value):
 reg=registration(engine.r,value)
 if reg is None:return False
 if COPIES.get(reg['source_id'],reg['source_id'])==ANCHOR:
  if actor.spec.get('ability_control_anchor') is None:
   key=actor.entity_id+':anchor'
   W.register_object(engine,key,location=W.location_of(actor),owner_id=actor.entity_id,source=ANCHOR,reason='actual Anchored Medium token')
   engine._physical_objects[key][TAG]={'source':ANCHOR,'owner_id':actor.entity_id,'size':'medium','targetable':False,'cover':False}
   actor.spec['ability_control_anchor']=key
  _anchor(engine,actor)
 scope=actor.spec.get(ATTACK)
 if scope is not None:
  if not isinstance(scope,dict) or scope.get('status') not in ('open','closed'):raise ValueError('actual control attack scope required')
  if scope['status']=='open':_attack(engine,actor,None)
 return True

def object_movable(obj):return obj.get(TAG,{}).get('source')!=ANCHOR
def object_targetable(obj):return object_movable(obj)

def _distance(actor,other,position=None,altitude=None):
 import body_state as BODY
 from grid import cheb
 first=BODY.at_position(actor,position)
 second={W.grid_cell(other)} if isinstance(other,dict) else BODY.at_position(other)
 left=actor.spec.get('_movement_altitude',0) if altitude is None else altitude
 right=0 if isinstance(other,dict) else other.spec.get('_movement_altitude',0)
 return max(min(cheb(a,b) for a in first for b in second),abs(left-right))

def _live(actor,kind=None):return [r for r in TIME.records(actor) if TAG in r and (kind is None or r[TAG]['kind']==kind)]

def _install(engine,holder,owner,uid,kind,*,statuses=(),payload=None,**clock):
 history=owner.spec.setdefault(HISTORY,[])
 key=owner.entity_id+':control:'+str(len(history)+1)
 tag={'id':key,'kind':kind,'owner_id':owner.entity_id,'holder_id':holder.entity_id,'source':uid,'payload':deepcopy(payload or {})}
 history.append(deepcopy(tag))
 return TIME.install(engine,holder,dict(id=key,source=uid,at=engine.elapsed_seconds,statuses=list(statuses),**{TAG:tag},**clock))

def edition(actor,uid):return actor.spec.get(EDITION,{}).get(uid,'csv-playtest')

def _immune(engine,target,selected):
 if '비행' in target.types:return True
 speeds=__import__('movement_actions').capabilities(engine,target,environment=False)
 threshold=4 if selected=='core-1.05' else 1
 return any(speeds.get(k,0)>=threshold for k in ('sky','levitate')) or speeds.get('burrow',0)>=4

def refresh(engine):
 """Observe real placement/source/life boundaries; preserve independent statuses."""
 actors=list(W.actor_index(engine).values())
 for owner in actors:
  for aura in list(_live(owner,'arena')):
   if not _available(owner) or not _owns(owner,ARENA):TIME.expire(engine,owner,aura);continue
   eligible={t.entity_id:t for t in actors if _available(t) and t.side!=owner.side and _distance(owner,t)<=5 and not _immune(engine,t,aura[TAG]['payload']['edition'])}
   for target in actors:
    held=[r for r in _live(target,'arena_recipient') if r[TAG]['payload'].get('aura_id')==aura['id']]
    if target.entity_id not in eligible:
     for row in held:TIME.expire(engine,target,row)
    elif not held:
     statuses=['둔화'] if aura[TAG]['payload']['edition']=='core-1.05' else ['둔화','수렁']
     _install(engine,target,owner,ARENA,'arena_recipient',statuses=statuses,payload={'aura_id':aura['id']},manual_end=True,encounter_end=True)
 for target in actors:
  for row in list(_live(target,'arena_recipient')):
   owner=next((x for x in actors if x.entity_id==row[TAG]['owner_id']),None)
   if owner is None or not any(r['id']==row[TAG]['payload']['aura_id'] for r in _live(owner,'arena')):TIME.expire(engine,target,row)

def can_place(engine,actor,position,*,altitude=None):
 if _owns(actor,ANCHOR) and _available(actor):
  token=_anchor(engine,actor)
  if token is not None and _distance(actor,token,position,altitude)>3:return False
 for row in _live(actor):
  data=row[TAG];p=data['payload']
  if data['kind']=='shadow':
   from grid import cheb
   if max(cheb(tuple(position),tuple(p['cell'])),abs((actor.spec.get('_movement_altitude',0) if altitude is None else altitude)-p['altitude']))>5:return False
  if data['kind']=='magnet':
   owner=W.actor_index(engine).get(data['owner_id'])
   if owner is None:raise ValueError('actual Magnet Pull user required')
   distance=_distance(actor,owner,position,altitude)
   if 'maximum' in p and distance>p['maximum'] or 'minimum' in p and distance<p['minimum']:return False
 return True

def _pay(engine,actor,uid,action,frequency):
 import frequency as F,turn as T
 key='ability:'+NAMES[uid]
 if not F.activation_allowed(actor,key,frequency,engine=engine,action_actor=actor):raise ValueError('control ability frequency exhausted')
 if not T.spend(engine,actor,action,NAMES[uid]):raise ValueError('control ability action unavailable')
 F.consume_activation(actor,key,frequency,engine=engine,action_actor=actor)

def activate(engine,actor,value,target):
 reg=registration(engine.r,value)
 if reg is None:raise ValueError('selected control ability required')
 uid=COPIES.get(reg['source_id'],reg['source_id'])
 subject,options=target if isinstance(target,tuple) and len(target)==2 and isinstance(target[1],dict) else (target,{})
 W.require_actors(engine,actor,subject)
 def apply(e,user,other):
  if not _owns(user,uid):raise ValueError('actual active control ability required')
  if options.get('mode')=='edition':
   if uid not in (ARENA,MAGNET) or other is not user or set(options)!={'mode','edition'} or options['edition'] not in ('core-1.05','csv-playtest'):raise ValueError('exact reviewed control edition required')
   if e.encounter_active or _live(user):raise ValueError('select control edition before encounter')
   user.spec.setdefault(EDITION,{})[uid]=options['edition']
   return {'source':uid,'edition':options['edition']}
  if not e.encounter_active or e.grid is None or not _available(user) or not _available(other):raise ValueError('actual mapped combat participants required')
  selected=edition(user,uid)
  if uid==ARENA:
   if other is not user or set(options)-{'mode'}:raise ValueError('Arena Trap affects its own aura')
   mode=options.get('mode','start')
   if mode=='end':
    if not _live(user,'arena'):raise ValueError('actual Arena Trap aura required')
    if not __import__('turn').spend(e,user,'free',NAMES[uid]):raise ValueError('control ability action unavailable')
    for row in list(_live(user,'arena')):TIME.expire(e,user,row)
   elif mode=='start':
    if _live(user,'arena'):raise ValueError('Arena Trap already active')
    _pay(e,user,uid,'free',{'kind':'scene','uses':1})
    _install(e,user,user,uid,'arena',payload={'edition':selected},manual_end=True,encounter_end=True)
   else:raise ValueError('Arena Trap start or end required')
   refresh(e)
  elif uid==SHADOW:
   if other is user or options or _distance(user,other)>1:raise ValueError('Shadow Tag requires one adjacent other creature')
   _pay(e,user,uid,'free',{'kind':'scene','uses':1})
   _install(e,other,user,uid,'shadow',statuses=['둔화','수렁'],payload={'cell':list(other.pos),'altitude':other.spec.get('_movement_altitude',0)},turn_owner=other,turn_deadline=other.custom_conditions.get('combat_turn_serial',0)+5)
  elif uid==DAZZLING:
   if other.side==user.side or options or _distance(user,other)>1:raise ValueError('Dazzling requires one adjacent enemy')
   _pay(e,user,uid,'swift',{'kind':'scene','uses':2})
   row=_install(e,other,user,uid,'dazzling',scene_end=True)
   sid=row['id'];G._source(other,sid,'effect',owner_id=user.entity_id,rule_id=uid,lifetime='scene_end')
   G.numeric(other,'initiative_bonus',-10,sid);row['grant_source']=sid
  elif uid==MAGNET:
   allowed={'choices','direction','distance'}
   choices=options.get('choices')
   valid={'maximum','minimum'} if selected=='core-1.05' else {'displace','maximum','minimum'}
   if set(options)-allowed or not isinstance(choices,list) or len(set(choices))!=len(choices) or not set(choices)<=valid or len(choices) not in ((1,2) if selected=='core-1.05' else (2,)):raise ValueError('Magnet Pull requires exact distinct selected options')
   if other.kind!='pokemon' or other is user or '강철' not in other.types or selected!='core-1.05' and _distance(user,other)>6:raise ValueError('Magnet Pull requires actual Steel Pokemon in source range')
   if 'displace' not in choices and set(options)-{'choices'}:raise ValueError('displacement options require selected displacement')
   if 'displace' in choices:
    distance=options.get('distance');limit=max(0,6-other.weight_class)
    if type(distance)is not int or not 0<=distance<=limit or options.get('direction') not in ('toward','away'):raise ValueError('Magnet Pull displacement exceeds weight bound')
    dx=(other.pos[0]>user.pos[0])-(other.pos[0]<user.pos[0]);dy=(other.pos[1]>user.pos[1])-(other.pos[1]<user.pos[1])
    if not dx and not dy:raise ValueError('distinct displacement direction required')
   _pay(e,user,uid,'swift',{'kind':'at_will'} if selected=='core-1.05' else {'kind':'scene','uses':3})
   if 'displace' in choices:
    sign=-1 if options['direction']=='toward' else 1
    __import__('forced_movement').displace(e,user,other,direction=(sign*dx,sign*dy),distance=distance,source=uid)
   p={k:(8 if selected=='core-1.05' else 6) if k=='maximum' else 3 for k in choices if k!='displace'}
   _install(e,other,user,uid,'magnet',payload=p,turn_owner=user,turn_deadline=user.custom_conditions.get('combat_turn_serial',0)+1)
  elif uid==TAIL:
   if other is not user or set(options)!={'aim'}:raise ValueError('Armor Tail requires exact ranged Blast aim')
   import area_targets as AREA
   move={'id':uid,'range':'4, 폭발 3','_class_move_range':{'origin':4,'targets':None,'shape':'blast','size':3,'parsed':True}}
   area=AREA.cells(e,user,AREA.bind(e,user,move,options['aim']))
   count=TIME.current(e)
   _pay(e,user,uid,'swift',{'kind':'at_will'})
   _install(e,user,user,uid,'tail',payload={'cells':[list(q) for q in sorted(area)]},count_deadline=(e.round_no+1,count))
  elif uid==ANCHOR:
   if other is not user or set(options)-{'cell','move_id','target_id'} or 'cell' not in options:raise ValueError('Anchored requires token cell and optional actual attack')
   import area_targets as AREA
   cell=AREA.point(options['cell']);obj=_anchor(e,user)
   if not e.grid.inside(cell) or _distance(user,dict(location={'kind':'grid','cell':cell}))>3:raise ValueError('anchor relocation exceeds 3m')
   if ('move_id' in options)!=('target_id' in options):raise ValueError('Anchored immediate attack requires actual move and target')
   victim=W.actor_index(e).get(options.get('target_id')) if 'target_id' in options else None
   if 'target_id' in options and victim is None:raise ValueError('actual Anchored attack target required')
   _pay(e,user,uid,'swift',{'kind':'at_will'})
   W.observe_location(e,obj,dict(W.location_of(obj),cell=cell),reason='paid Anchored token relocation',source=uid)
   if victim is not None:
    if user.budget.get('standard',0)<=0:raise ValueError('Anchored immediate attack requires remaining action')
    user.spec[ATTACK]={'source':uid,'kind':'anchor','move_id':options['move_id'],'target_id':victim.entity_id,'cell':list(cell),'round':e.round_no,'turn_serial':user.custom_conditions.get('combat_turn_serial',0),'action_index':len(user._action_history)-1,'status':'open'}
    import passive_events as PASSIVE
    try:result=e.use_move(user,victim,options['move_id'])
    except PASSIVE.PassiveEventPending as pending:return {'source':uid,'pending_event_id':pending.event_id}
    if not isinstance(result,__import__('common_checks').PendingDecision):user.spec[ATTACK]['status']='closed'
  return {'source':uid,'operation':uid.split('/',1)[1],'edition':selected}
 result=(G.transition(engine,actor,lambda e,user:apply(e,user,user),include_grid=True,include_rulings=True) if subject is actor else G.transition(engine,actor,apply,participants=(subject,),include_grid=True,include_rulings=True))
 if 'pending_event_id' in result:raise __import__('passive_events').PassiveEventPending(result['pending_event_id'])
 return result

def admit(engine,actor,kind,*,trigger=None):
 if kind not in ('priority','interrupt'):raise ValueError('actual action declaration kind required')
 for row in _live(actor,'dazzling'):
  owner=(trigger or {}).get('owner')
  if kind=='priority' or owner is not None and owner.entity_id==row[TAG]['owner_id']:
   raise ValueError('Dazzling prohibits this '+kind+' declaration')
 import body_state as BODY
 ordinary=getattr(engine,'_active_turn_actor',None) is actor and __import__('initiative_interrupts').frame(engine) is None
 if ordinary:return
 for owner in W.actor_index(engine).values():
  if owner.side==actor.side:continue
  for row in _live(owner,'tail'):
   if BODY.at_position(actor).intersection(tuple(q) for q in row[TAG]['payload']['cells']):
    raise ValueError('Armor Tail prohibits out-of-turn '+kind+' declaration')

def crossing(engine,actor,origin,destination):
 refresh(engine)
 if isinstance(actor,dict) or tuple(origin)==tuple(destination):return
 import body_state as BODY,turn as T
 before=BODY.at_position(actor,origin);after=BODY.at_position(actor,destination)
 for owner in list(W.actor_index(engine).values()):
  if owner.side==actor.side or not _available(owner):continue
  for row in list(_live(owner,'tail')):
   cells={tuple(q) for q in row[TAG]['payload']['cells']}
   if bool(before.intersection(cells))==bool(after.intersection(cells)) or not T.can_aoo(engine,owner):continue
   owner.spec[ATTACK]={'source':TAIL,'kind':'tail_aoo','effect_id':row['id'],'move_id':'struggle','target_id':actor.entity_id,'round':engine.round_no,'status':'open'}
   try:T.trigger_aoo(engine,actor,'Armor Tail Blast boundary',[owner])
   finally:owner.spec[ATTACK]['status']='closed'

def _attack(engine,actor,move):
 row=actor.spec.get(ATTACK)
 marker=move.get('_ability_control_attack') if move else None
 if row is None or row.get('status')!='open':
  if marker is not None:raise ValueError('control attack scope has ended')
  return None
 if row['round']!=engine.round_no or not _owns(actor,row['source']):raise ValueError('actual active control attack source required')
 if move is not None and move.get('id')!=row['move_id']:return None
 if marker is not None and marker!=row:raise ValueError('control attack declaration changed')
 if row['kind']=='tail_aoo':
  pair=getattr(engine,'_opportunity_attack',None)
  if not pair or pair.get('attacker_id')!=actor.entity_id or pair.get('target_id')!=row['target_id'] or not any(r['id']==row['effect_id'] for r in _live(actor,'tail')):raise ValueError('actual Armor Tail opportunity attack required')
 else:
  token=_anchor(engine,actor);history=getattr(actor,'_action_history',[]);index=row.get('action_index')
  if (row['kind']!='anchor' or list(W.grid_cell(token))!=row['cell'] or token.get('provenance')!={'reason':'paid Anchored token relocation','source':ANCHOR} or
      type(index)is not int or not 0<=index<len(history) or history[index]!='swift' or row.get('turn_serial')!=actor.custom_conditions.get('combat_turn_serial',0)):
   raise ValueError('actual paid Anchored relocation and Swift action required')
  for completed in getattr(engine,'_move_completions',{}).values():
   if completed['actor'] is actor and completed['phase']=='complete' and completed['move'].get('_ability_control_attack')==row:
    if marker is not None:raise ValueError('Anchored attack scope has already completed')
    return None
 return row

def prepare_move(engine,actor,move):
 row=_attack(engine,actor,move)
 if row is None:return move
 out=dict(move,_ability_control_attack=deepcopy(row))
 if row['kind']=='anchor':
  out['class']='물리';out['range']='근접, 대상 1'
  out['_class_move_range']={'origin':1,'targets':1,'parsed':True,'raw':'근접, 대상 1'}
 return out

def attack_origin(engine,actor,move):
 row=_attack(engine,actor,move)
 return tuple(row['cell']) if row and row['kind']=='anchor' else None

def ignores_range(engine,actor,move):
 row=_attack(engine,actor,move)
 return bool(row and row['kind']=='tail_aoo')

def require_target(engine,actor,target,move):
 row=_attack(engine,actor,move)
 if row and row['target_id']!=target.entity_id:raise ValueError('control attack requires its actual declared target')

def damage_dice(engine,actor,move,set_damage=False):
 row=_attack(engine,actor,move)
 if not row or row['kind']!='anchor':return 0
 return 7 if set_damage else engine.roll_expr('2d6',actor=actor,purpose='damage')[0]

def after_move(engine,actor,move):
 row=actor.spec.get(ATTACK)
 if row and row.get('status')=='open' and row.get('move_id')==move.get('id'):row['status']='closed'

def prepare_struggle(engine,actor,move,choice):
 previous=move.get('_armor_tail_struggle')
 if previous is None and not (isinstance(choice,dict) and 'ability' in choice):return None
 if choice is None:choice={'ability':TAIL,'type':'에스퍼'}
 if choice!={'ability':TAIL,'type':'에스퍼'} or move.get('id')!='struggle' or move.get('_weapon_attack') or not _owns(actor,TAIL):raise ValueError('Armor Tail requires explicit ordinary Psychic Struggle choice')
 expected={'source':TAIL,'actor_id':actor.entity_id}
 if previous is not None and previous!=expected:raise ValueError('Armor Tail Struggle source changed')
 return dict(move,type='에스퍼',_armor_tail_struggle=expected)

def validate_world(engine,index):
 kinds={'arena':ARENA,'arena_recipient':ARENA,'shadow':SHADOW,'magnet':MAGNET,'dazzling':DAZZLING,'tail':TAIL}
 for actor in index.values():
  scope=actor.spec.get(ATTACK)
  if scope is not None and (not isinstance(scope,dict) or scope.get('status') not in ('open','closed')):raise ValueError('actual control attack scope required')
  if scope and scope['status']=='open' and _attack(engine,actor,None) is None:raise ValueError('control attack scope has already completed')
  for uid,value in actor.spec.get(EDITION,{}).items():
   if uid not in (ARENA,MAGNET) or value not in ('core-1.05','csv-playtest'):raise ValueError('reviewed control edition required')
  if actor.spec.get('ability_control_anchor') is not None:
   token=_anchor(engine,actor)
   if token['owner_id']!=actor.entity_id:raise ValueError('anchor owner mismatch')
   if _available(actor) and _owns(actor,ANCHOR) and _distance(actor,token)>3:raise ValueError('Anchored owner exceeds token tether')
  history=actor.spec.get(HISTORY,[])
  if not isinstance(history,list):raise ValueError('actual control producer history required')
  for i,tag in enumerate(history,1):
   if tag.get('id')!=actor.entity_id+':control:'+str(i) or tag.get('owner_id')!=actor.entity_id or tag.get('holder_id') not in index or kinds.get(tag.get('kind'))!=tag.get('source'):raise ValueError('control producer identity changed')
  for row in _live(actor):
   tag=row[TAG];owner=index.get(tag.get('owner_id'))
   if owner is None or tag not in owner.spec.get(HISTORY,[]) or tag.get('holder_id')!=actor.entity_id or row['id']!=tag['id'] or row['source']!=tag['source']:raise ValueError('control effect has no actual source producer')
   kind=tag['kind'];p=tag['payload']
   if kind=='shadow' and (row.get('turn_owner') is not actor or type(row.get('turn_deadline'))is not int or set(p)!={'cell','altitude'}):raise ValueError('Shadow Tag target clock changed')
   if kind=='magnet' and (row.get('turn_owner') is not owner or type(row.get('turn_deadline'))is not int or not set(p)<={'maximum','minimum'}):raise ValueError('Magnet Pull owner clock changed')
   if kind=='dazzling':
    ledger=actor.spec.get(G.KEY,{}).get('numbers',{}).get('initiative_bonus',{}).get('sources',{})
    if row.get('grant_source')!=row['id'] or ledger.get(row['id'])!=-10 or not row.get('scene_end'):raise ValueError('Dazzling actual initiative grant changed')
   if kind=='tail' and (not row.get('count_deadline') or not p.get('cells') or any(not engine.grid.inside(tuple(q)) for q in p['cells'])):raise ValueError('Armor Tail native count/area changed')
