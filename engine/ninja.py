"""Core Ninja acquisitions and calls into shared weapons, crafting and movement."""
from copy import deepcopy
import common_checks as C
import state_grants as G

CLASS='class/닌자';ARSENAL='feat/닌자의-무기고';POISON='feat/독극-무기'
GENJUTSU='feat/환술';UTILITY='feat/유틸리티-드롭';STEP='feat/무중력-스텝';KINJUTSU='feat/금술'
SOURCE_SHA256='a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'
FEATURES={CLASS:(2951,2953),ARSENAL:(2955,2958),POISON:(2960,2965),GENJUTSU:(2967,2971),UTILITY:(2973,2978),STEP:(2980,2984),KINJUTSU:(2986,2990)}
DEFINITIONS={u:{'span':list(s),'catalog_span':[2939,2939] if u==CLASS else list(s),
 'clause_id':'input/ch04-trainer-classes.md:'+str(s[0])+'-'+str(s[1]),'stat_tags':['spe'],
 'parent':None if u==CLASS else ARSENAL if u==UTILITY else POISON if u==KINJUTSU else CLASS,
 'minimum_stealth':3 if u==CLASS else 6 if u==KINJUTSU else 5 if u in (UTILITY,STEP) else 4 if u in (POISON,GENJUTSU) else 0}
 for u,s in FEATURES.items()}
TOOLS={'item/연막탄':'move/연막','item/마름쇠':'move/압정뿌리기','item/독-마름쇠':'move/독압정'}


def records(actor,feature=None,active=False):
 import trainer_feature_acquisition as T
 return [record for _, record in T.static_family_acquisitions(actor, FEATURES, feature, active=active)]


def acquired(actor,feature):
 rows=records(actor,feature,True)
 return rows[-1] if rows else None


def acquisition_snapshot(e,actor,feature,rank,selection):
 import skill_modifiers as SK
 if rank is not None or selection is not None:raise ValueError('Core Ninja Features have no ranks or acquisition choices')
 parent=DEFINITIONS[feature]['parent']
 return {'stealth':SK.rank(e.r,actor,'은신')[2],'combat':SK.rank(e.r,actor,'전투')[2],
  'parents':[r['request_id'] for r in records(actor,parent,True)] if parent else []}


def qualification(actor,feature,snapshot,prerequisite_source):
 import acquisition_qualification as Q
 if prerequisite_source is not None or type(snapshot)is not dict or set(snapshot)!={'stealth','combat','parents'}:raise ValueError('actual Ninja acquisition observations required')
 for name in ('stealth','combat'):C.integer(snapshot[name],'actual Ninja '+name+' rank',1,6)
 parent=DEFINITIONS[feature]['parent'];known={r['request_id'] for r in records(actor,parent)} if parent else set()
 return Q.require(feature,'native','acquire',[
  Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),
  Q.check('parent','prerequisite',parent is None or bool(snapshot['parents']) and set(snapshot['parents'])<=known,'actual acquired Ninja parent required'),
  Q.check('stealth','prerequisite',snapshot['stealth']>=DEFINITIONS[feature]['minimum_stealth'],'printed Stealth rank required'),
  Q.check('combat','prerequisite',feature!=CLASS or snapshot['combat']>=3,'Novice Combat required')])


def after_acquire(e,actor,feature,sid):
 # Arsenal's Speed tag is the existing adopted Dataninja erratum, p17.
 G.stat(actor,'spe',1,sid,operation_id='acquisition_stat_tag')
 if feature in (CLASS,KINJUTSU):__import__('class_move_grants').register_all(e,actor)
 if feature==STEP:
  G.register_feature_effect(e,actor,actor,'무중력 스텝',STEP,0,{'type':'grant_ability','grant_ability':'틈새포착'})


def validate_acquisition(actor,record,sid,active):
 if active and actor.spec.get(G.KEY,{}).get('stat_sources',{}).get('spe',{}).get('sources',{}).get(sid,{}).get('acquisition_stat_tag')!={'delta':1,'minimum':None}:
  raise ValueError('actual Ninja Speed stat tag required')


def require(e,actor,feature):
 __import__('world_entities').require_actors(e,actor)
 if e.r._selected_rule(feature)!=feature or not acquired(actor,feature):raise ValueError('actual acquired Ninja Feature required: '+feature)
 __import__('trainer_feature_acquisition').validate_actor(actor)


def craft(e,actor,item,*,event_id,reason,instance_id,seconds):
 require(e,actor,ARSENAL)
 if item not in ('item/해독제',*TOOLS):raise ValueError('one of four printed Ninja tools required')
 key=e.r.item_effects(item)[1]['id']
 C.integer(seconds,'observed Extended crafting duration in seconds',120)
 recipe={'id':'ninja/'+item,'source':ARSENAL,'output':{'item_id':item,'key':key},'seconds':seconds,
  'requirements':[{'id':'arsenal','condition':{'kind':'owned','fields':['feats'],'names':[ARSENAL]},'reason':'actual acquired Ninja Arsenal'}],
  'materials':[{'id':'money','options':[{'kind':'value','category':'닌자 도구','amount':100,'scrap':False,'money':True}]}]}
 return __import__('crafting_recipes').craft(e,actor,recipe,reason=reason,event_id=event_id,
  product_policy={'mode':'create','instance_ids':[instance_id],'owner_id':actor.entity_id,'state':'intact','attachments':[]})


def weapon_attack(e,actor,target,move_id,*,poison_type=False,**options):
 require(e,actor,POISON)
 if type(poison_type)is not bool:raise ValueError('explicit Poison damage type choice required')
 import weapon_actions as W,action_points as AP
 move=W.prepare(e,actor,e.r.move(e.r.move_id(move_id)),options.get('weapon_id'))
 if not move.get('_weapon_attack'):raise ValueError('Poison Weapons requires an actual equipped Weapon Attack')
 if AP.available(actor)<1:raise ValueError('Poison Weapons requires 1 AP')
 def apply(se,sa,st):
  before=len(getattr(sa,'_action_history',()))
  se._ninja_poison={'actor_id':sa.entity_id,'move_id':move['id'],'poison_type':poison_type}
  try:
   result=se.use_move(sa,st,move['id'],**options)
   if len(getattr(sa,'_action_history',()))>before:
    __import__('action_lifecycle').record_action(se,sa,'free');AP.charge(sa,1)
   return result
  finally:se.__dict__.pop('_ninja_poison',None)
 return G.transition(e,actor,apply,participants=(target,),include_rulings=True,include_grid=e.grid is not None)


def project_weapon(e,actor,move):
 frame=getattr(e,'_ninja_poison',None)
 if frame and frame['actor_id']==actor.entity_id and frame['move_id']==move['id']:
  if not move.get('_weapon_attack'):raise ValueError('actual Poison Weapons attack authority lost')
  # Native Move projections retain live target references in _actual_targets.
  move=dict(move,_ninja_poison=True)
  if frame['poison_type']:move['type']='독'
 return move


def poison_hit(e,actor,target,move,natural):
 if move.get('_ninja_poison') and natural is not None and natural>=16:
  e.apply_status(target,'독',source=POISON,applied_by=actor)


def utility_shift(e,actor,path,item,*,held_selection=None,mode='land'):
 require(e,actor,UTILITY)
 if item not in TOOLS:raise ValueError('Utility Drop uses an actual Smoke Ball, Caltrops or Toxic Caltrops item')
 import movement_actions as MOVE,item_stock as STOCK,turn as TURN
 if not isinstance(path,(list,tuple)) or not path:raise ValueError('actual Shift path required')
 if mode in ('sky','levitate','shadow_surface'):path=deepcopy(path)
 else:
  path=[MOVE._point(point) for point in path]
  for a,b in zip([actor.pos]+path,path):MOVE.step_cost(a,b,0)
 STOCK.prepare(e,actor,item,held_selection=held_selection)
 if not e.encounter_active or e._active_turn_actor is not actor:raise ValueError('Utility Drop requires the actual Shift turn')
 def apply(se,sa):
  allowance=MOVE.distance_budget(se,sa,mode)
  if not TURN.spend(se,sa,'swift',UTILITY):raise ValueError('Utility Drop requires Swift Action')
  if not TURN.spend(se,sa,'shift','이동',movement=True):raise ValueError('Utility Drop requires Shift Action')
  se._utility_drop={'actor_id':sa.entity_id,'item':item,'held_selection':held_selection,'cells':[],'distance':0,'paid':False}
  try:
   result=MOVE.follow_paid_path(se,sa,path,mode=mode,maximum_distance=allowance,action_owner=sa)
   result['utility_cells']=deepcopy(se._utility_drop['cells']);return result
  finally:se.__dict__.pop('_utility_drop',None)
 return G.transition(e,actor,apply,include_grid=True,include_rulings=True)


def departed(e,actor,origin,*,distance):
 frame=getattr(e,'_utility_drop',None)
 if not frame or frame['actor_id']!=actor.entity_id or origin==actor.pos:return
 previous=frame['distance'];frame['distance']+=distance
 if previous>=8:return
 frame['cell']=tuple(origin)
 # The item caller is available only inside a real, completed native Shift step.
 e.use_item(actor,frame['item'],free=True,held_selection=None if frame['paid'] else frame['held_selection'])
 frame=e._utility_drop;frame['cells'].append(list(origin));frame.pop('cell')


def utility_authority(e,request):
 frame=getattr(e,'_utility_drop',None)
 return bool(frame and frame['actor_id']==request.user.entity_id and frame['item']==request.source_id and request.free and 'cell' in frame)


def utility_item(e,request,*,consume=False):
 frame=e._utility_drop;actor=request.user;mid=TOOLS[request.source_id]
 expected_selection=None if frame['paid'] else frame['held_selection']
 if request.target is not actor or request.count!=1 or request.held_selection!=expected_selection:raise ValueError('actual Utility Drop item request changed')
 import item_stock as STOCK,consumption_execution as EXEC,frequency as F
 stock=None if frame['paid'] else STOCK.prepare(e,actor,request.source_id,held_selection=request.held_selection)
 if not consume:return None
 if not frame['paid']:
  # Caltrops' ordinary adapter activates its internal Move. Smoke Ball does not.
  if mid!='move/연막':
   if not F.move_allowed(e,actor,mid)[0]:raise ValueError('Utility Drop internal item Move frequency exhausted')
   F.consume_move(e,actor,mid)
  frame['payment']=STOCK.debit(e,actor,stock);frame['paid']=True
  __import__('action_lifecycle').record_action(e,actor,'free')
 cell=frame['cell']
 if mid=='move/연막':
  import smoke_regions as SMOKE,smoke_balls as BALL
  result=SMOKE.apply(e,actor,{'_area_aim':cell,'_effect_area_cells':[cell]},BALL.ZONE,request.source_id,UTILITY)
 else:
  import hazard_state as H,world_entities as W
  result=H._install_region(e,actor,mid,H.policy(e.r)['moves'][mid],[cell],W.actor_index(e))
 EXEC.finish(actor,frame['payment'],target_id=actor.entity_id,outcome='applied',results=[{'kind':'utility_drop','id':UTILITY}])
 return result
