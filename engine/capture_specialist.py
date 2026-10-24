"""Capture Specialist techniques at the existing native event boundaries.

Acquisition receipts own source choices. Actions own payment and physical balls;
this module only supplies the class-specific permissions and consequences.
"""
from copy import deepcopy
from contextlib import contextmanager
import common_checks as C
import capture_techniques as CT
import trainer_feature_acquisition as TFA
import acquired_features as ACQUIRED
import state_grants as G
import action_lifecycle as ACTION
import action_points as AP
import frequency as F
import world_entities as W

CORE='core_105'
CSV='csv'
SEPT='official_sep2015'
MAY='official_may2015'
GOTTA='feat/포켓몬-넌-내-꺼야'
MOMENTUM='feat/포획-추진력'
TABLE='ch04-trainer-classes/입문-클래스/포획전문가'
CURVE_CASE='capture/curve-ball-and-suppression-case'
TECHNIQUE_ROWS={'포획 스킬':7,'커브볼':8,'약화 투척':9,'빠른 투구':10,'덫':11,
                '작업 도구':12,'캐치 콤보':13,'거짓 타격':14,'끝없는 추격':15}
FILES={
 'input/ch09-equipment.md':'b5aeb6b82af4b05fe0b369368f8b0181ed3b1d22079e8a86a1c4248e6cbf92d2',
 'input/db/class-data.csv':'5d75c059fc17c7d37293c8a3bc6cb9f1a53f51e9361daee7f5ef9cb35e411c82',
 'input/db/feats.csv':'4435ff1c462a211564c85d2c1c9a2ac6e7c790c7545e1ad7056d32888b2367bd',
 'input/db/inventory.csv':'e3e6d81649d8d12ae1e610db838e6ea615c077cd634c682429042c545b3bd3f4',
 'input/supp-errata.md':'90e533bde766c6ffe8fb480dd8e2478e5fddf3ed1fef9a7a1032070245622a3e',
}
OFFICIAL={MAY:('official-may2015.pdf','b1314908e4adbfee09042c58f08a36046b5f59a09de196425aa469b43232232d'),
 SEPT:('official-sep2015.pdf','846c23a90f26d7deb7a86117622378bc60dc7c729a9a6b1e747ea67d4a1c6caf')}

def official_source(rules,variant):
 import source_context as S
 name,digest=OFFICIAL[variant]
 row={'file':'source-audit/'+name,'sha256':digest}
 S.verified_source(rules,row,label='official Capture source',source_root='source-audit')
 return row

def _file(rules,path):
 import source_context as S
 row={'file':path,'sha256':FILES[path]}
 S.verified_source(rules,row,label='Capture Specialist source variant')
 return row

def technique_source(rules,name,variant):
 if variant==CORE:return dict(CT.SOURCE,span=[405,407],name=name)
 if variant==CSV:return dict(_file(rules,'input/db/class-data.csv'),record=TECHNIQUE_ROWS[name],field='technique')
 if (name,variant) in (('덫',SEPT),('작업 도구',MAY)):
  return dict(official_source(rules,variant),official=variant)
 raise ValueError('select an actual printed Capture technique source variant')

def technique(actor,name,*,required=False):
 CT.validate_actor(actor)
 choices=[p['choice'] for r in CT._rows(actor) for p in r['selection']['proofs'] if p['choice']['technique']==name]
 if not choices:
  if required:raise ValueError('actual acquired '+CT.TECHNIQUES[name]+' required')
  return None
 choice=choices[0];variant=choice.get('source_variant',CORE)
 technique_source(actor.r,name,variant)
 return variant

def feature_snapshot(actor,feature,selection):
 import captured_momentum as CM
 snapshot=CM.acquisition_snapshot(actor)
 if selection is not None:
  if type(selection)is not dict or set(selection)!={'source_variant'}:raise ValueError('one explicit Capture Feature source selection required')
  variant=selection['source_variant']
  if variant not in ((CORE,CSV,SEPT) if feature==GOTTA else (CORE,CSV)):
   raise ValueError('select an actual Capture Feature source variant')
  if variant==CSV:_file(actor.r,'input/db/feats.csv')
  if variant==SEPT:official_source(actor.r,variant)
  snapshot['selection']=deepcopy(selection)
 return snapshot

def feature_qualification(actor,feature,snapshot,prerequisite_source):
 import captured_momentum as CM,acquisition_qualification as Q
 selection=snapshot.get('selection')
 stripped={k:v for k,v in snapshot.items() if k!='selection'}
 CM.qualification(actor,stripped,prerequisite_source)
 # The parent's immutable receipts prove the acquisition-time rank.
 if selection is not None:
  variant=selection.get('source_variant') if type(selection)is dict else None
  allowed=(CORE,CSV,SEPT) if feature==GOTTA else (CORE,CSV)
  if set(selection)!={'source_variant'} or variant not in allowed:raise ValueError('Capture Feature source selection changed')
  if variant==CSV:_file(actor.r,'input/db/feats.csv')
  if variant==SEPT:official_source(actor.r,variant)
 return Q.require(feature,'native','acquire',[Q.check('advanced_capture_rank','prerequisite',snapshot['rank']>=(3 if feature==GOTTA else 2),'Advanced Capture rank '+str(3 if feature==GOTTA else 2)+' required')])

def feature_variant(actor,feature):
 TFA.validate_actor(actor)
 rows=[r['static_acquisition'] for _,r,active in TFA._static_records(actor) if active and r['static_acquisition']['feature_id']==feature]
 if ACQUIRED.owned_rule_count(actor,feature) and not rows:raise ValueError('Capture Feature requires its actual acquisition source')
 return rows[0]['snapshot'].get('selection',{}).get('source_variant',CORE) if rows else None

def _quota(engine,actor,key,kind,uses=1):
 frequency={'kind':kind,'uses':uses}
 if kind=='turn':
  owner=getattr(engine,'_active_turn_actor',None)
  if owner is None:raise ValueError('actual turn required for shared Curve Ball quota')
  frequency['turn_owner_id']=owner.entity_id
 if not F.activation_allowed(actor,key,frequency,engine=engine):raise ValueError(key+' frequency exhausted')
 return frequency

def _charge(engine,actor,source,amount=0):
 if AP.available(actor)<amount:raise ValueError('insufficient AP for '+source)
 ACTION.triggered_free_action(engine,actor,source)
 if amount:AP.spend(actor,amount)

def attach_case(engine,trainer,case_id,ball_id,*,reason):
 """Attach the actual possessed Case to this one physical ball."""
 import missed_ball_body as B
 W.require_actors(engine,trainer);W._text(reason,'actual Suppression Case attachment reason')
 _file(engine.r,'input/db/inventory.csv')
 ball=B.physical(engine,trainer,ball_id)
 case=getattr(engine,'_physical_objects',{}).get(case_id)
 if not case or case.get('owner_id')!=trainer.entity_id or '제압' not in engine.r.items_mech.get(case.get('item_rule_id'),{}).get('name',''):
  raise ValueError('actual owned Suppression Case item instance required')
 W.require_usable_object(case)
 if W.distance_known(case,trainer)!=0 or W.distance_known(ball,trainer)!=0:raise ValueError('actual Case and ball must be at their owner')
 if any(o.get('suppression_case',{}).get('case_id')==case_id for o in engine._physical_objects.values()):raise ValueError('same Case is already attached to a ball')
 def apply(e,a):
  e._physical_objects[ball_id]['suppression_case']={'case_id':case_id,'owner_id':a.entity_id,'reason':reason,
   'source':_file(e.r,'input/db/inventory.csv'),'record':36}
  return deepcopy(e._physical_objects[ball_id]['suppression_case'])
 return G.transition(engine,trainer,apply)

def ball_plan(engine,trainer,*,curve_ball=False,suppression_case=None,standard=True,physical_plan=None):
 if type(curve_ball)is not bool:raise ValueError('explicit optional Curve Ball choice required')
 variant=technique(trainer,'커브볼',required=curve_ball) if curve_ball else None
 case=None
 if suppression_case is not None:
  _file(engine.r,'input/db/inventory.csv')
  uid=(physical_plan or {}).get('instance_id')
  ball=getattr(engine,'_physical_objects',{}).get(uid,{})
  attached=ball.get('suppression_case',{})
  case=getattr(engine,'_physical_objects',{}).get(suppression_case)
  if attached.get('case_id')!=suppression_case or attached.get('owner_id')!=trainer.entity_id or not case or case.get('owner_id')!=trainer.entity_id:
   raise ValueError('actual Suppression Case attached to this physical ball required')
  W.require_usable_object(case)
  if attached.get('source')!=_file(engine.r,'input/db/inventory.csv') or attached.get('record')!=36:raise ValueError('actual Case attachment source changed')
  case={'case_id':suppression_case,'ball_id':uid,'source':deepcopy(attached)}
 if variant==CSV and not standard:raise ValueError('CSV Curve Ball requires a Standard Action throw')
 if case is not None and not standard:raise ValueError('Suppression Case requires a Standard Action throw')
 quota=_quota(engine,trainer,CURVE_CASE,'turn') if variant==CSV or case is not None else None
 return {'curve':variant,'case':deepcopy(case),'quota':quota} if curve_ball or case is not None else None

def ball_hit(engine,trainer,target,record,plan):
 """The native caller has established an actual ball hit, before its function."""
 if plan is None:return
 if not record.get('hit') or record.get('target')!=target.entity_id:raise ValueError('actual hit by this thrown ball required')
 if plan['curve']:technique(trainer,'커브볼',required=True)
 if plan['quota']:
  if not F.activation_allowed(trainer,CURVE_CASE,plan['quota'],engine=engine):raise ValueError('shared Curve Ball and Suppression Case frequency exhausted')
  F.consume_activation(trainer,CURVE_CASE,plan['quota'],engine=engine)
 move=deepcopy(engine.r.move('struggle'))
 if plan['case'] is not None:move['type']='전기'
 # This is damage as though a Struggle hit, not a second accuracy/action/Move use.
 damage=engine.roll_damage(trainer,target,move,set_damage=False)
 extra=0
 if plan['case'] is not None and plan['curve']:
  import skill_modifiers as SK
  extra=2*SK.effective_rank(engine.r,trainer,'기술학')
 damage+=extra
 before=target.hp
 engine._capture_ball_damage=(trainer,target,record)
 try:engine.take_damage(target,damage)
 finally:vars(engine).pop('_capture_ball_damage',None)
 record['curve_damage']={'source_variant':plan['curve'],'case':deepcopy(plan['case']),
  'type':move['type'],'requested':damage,'technical_bonus':extra,'before_hp':before,'after_hp':target.hp,'applications':1}

def observe_release_ball(engine,trainer,pokemon,ball_id,*,reason):
 """GM observes an existing off-field owned Pokemon's actual containing ball."""
 import missed_ball_body as B
 W.require_actors(engine,trainer,pokemon);W._text(reason,'actual containing ball observation reason')
 if pokemon.kind!='pokemon' or pokemon.spec.get('trainer_id')!=trainer.entity_id or pokemon.on_field:raise ValueError('actual owned off-field Pokemon required')
 B.physical(engine,trainer,ball_id)
 def apply(e,a,p):
  if any(o.get('contained_pokemon',{}).get('pokemon_id')==p.entity_id for o in e._physical_objects.values()):raise ValueError('one actual containing ball required')
  e._physical_objects[ball_id]['contained_pokemon']={'pokemon_id':p.entity_id,'owner_id':a.entity_id,'reason':reason}
 return G.transition(engine,trainer,apply,participants=(pokemon,))

def release_plan(engine,trainer,pokemon,options):
 import missed_ball_body as B,capability_actions as CAP,body_state as BODY
 if type(options)is not dict or not {'ball_id','target_id','curve_ball'}<=set(options) or set(options)-{'ball_id','target_id','curve_ball','suppression_case','fixed_accuracy','bounce'}:
  raise ValueError('one actual release ball, hit target and optional Curve choice required')
 target=W.actor_index(engine).get(options['target_id'])
 if target is not None:W.require_actors(engine,target)
 elif options['target_id'] is not None or options.get('bounce') is None or options['curve_ball'] or options.get('suppression_case'):
  raise ValueError('actual hit target or observed Bounce Shot landing required')
 ball=B.physical(engine,trainer,options['ball_id'])
 if ball.get('contained_pokemon',{}).get('pokemon_id')!=pokemon.entity_id or ball['contained_pokemon'].get('owner_id')!=trainer.entity_id:
  raise ValueError('actual observed containing ball for this released Pokemon required')
 if target is not None and not BODY.in_range(engine,trainer,target,CAP.throwing_range(engine,trainer,category='poke_ball')):raise ValueError('release ball target outside actual throwing range')
 if options.get('fixed_accuracy') is not None:C.integer(options['fixed_accuracy'],'release ball accuracy',1,20)
 plan=ball_plan(engine,trainer,curve_ball=options['curve_ball'],suppression_case=options.get('suppression_case'),
  physical_plan={'instance_id':options['ball_id']},standard=True)
 if options.get('bounce') is not None:
  __import__('juggler').bounce_plan(engine,trainer,target,options['bounce'],function='release')
  return plan or {}
 if plan is None:raise ValueError('release throw requires its actual selected Curve or attached Case')
 return plan

def release_hit(engine,trainer,pokemon,options):
 target=W.actor_index(engine).get(options['target_id'])
 plan=release_plan(engine,trainer,pokemon,options)
 move={'id':'ball','name':'release ball','class':'변화','type':'노말','ac':6}
 hit,natural=True,None
 if target is not None:hit,natural,_=engine.accuracy_check(trainer,target,move,fixed_roll=options.get('fixed_accuracy'),situational=tools_accuracy(engine,trainer,'ball'))
 record={'hit':hit,'target':None if target is None else target.entity_id,'physical_instance_id':options['ball_id'],'accuracy_natural':natural,'function':'release'}
 if hit and plan:ball_hit(engine,trainer,target,record,plan)
 ball=engine._physical_objects[options['ball_id']]
 bounce=None if options.get('bounce') is None else __import__('juggler').bounce_plan(engine,trainer,target,options['bounce'],function='release')
 W._set_object_location(ball,W.location_of(target) if target is not None else {'kind':'grid','cell':bounce['landing']})
 record['function_order']=(['throw'] if bounce is not None else [])+(['accuracy'] if target is not None else [])+(['damage'] if hit and plan else [])+(['landing'] if bounce is not None else [])
 if bounce is not None:
  if target is not None and tuple(target.pos)!=tuple(bounce['landing']):raise ValueError('release throw hit/landing must match its actual target position')
  __import__('juggler').pay(engine,trainer,__import__('juggler').BOUNCE,'free',0)
  if bounce['timing']=='after':__import__('juggler').bounce_physical(engine,trainer,ball,bounce,record)
 ball.pop('contained_pokemon');record['function_order'].append('release')
 record['release_position']=list(W.location_of(ball)['cell'])
 if bounce is not None and bounce['timing']=='before':__import__('juggler').bounce_physical(engine,trainer,ball,bounce,record)
 return record

def escaped(engine,trainer,target,attempt):
 if not technique(trainer,'약화 투척'):return
 if attempt.get('hit') and attempt.get('captured') is False and attempt.get('status')=='failed_capture':
  attempt['devitalizing']={'state':'ready','actor_id':trainer.entity_id,'target_id':target.entity_id,
   'round':engine.round_no,'at':engine.elapsed_seconds,'physical_instance_id':attempt['physical_instance_id']}
  _seal(attempt['devitalizing'])

def _seal(row):
 row['fingerprint']=__import__('root_resolution').fingerprint({k:v for k,v in row.items() if k!='fingerprint'})
 return row

def _verify(row):
 if row.get('fingerprint')!=__import__('root_resolution').fingerprint({k:v for k,v in row.items() if k!='fingerprint'}):raise ValueError('actual Capture Specialist event changed')

def devitalize(engine,trainer,*,attempt_id,choice,stat=None,composition=None):
 target_id=trainer.spec.get('capture_attempts',{}).get(attempt_id,{}).get('target')
 target=W.actor_index(engine).get(target_id);W.require_actors(engine,trainer,target)
 def apply(e,a,t):
  technique(a,'약화 투척',required=True)
  attempt=a.spec.get('capture_attempts',{}).get(attempt_id,{})
  event=attempt.get('devitalizing',{})
  if event:_verify(event)
  if (event.get('state')!='ready' or event.get('actor_id')!=a.entity_id or event.get('target_id')!=t.entity_id or
      event.get('round')!=e.round_no or event.get('at')!=e.elapsed_seconds or attempt.get('captured') or
      not attempt.get('hit') or attempt.get('status')!='failed_capture' or event.get('physical_instance_id')!=attempt.get('physical_instance_id')):
   raise ValueError('actual current escape from this trainer ball required')
  if choice not in ('slowed','stat','save') or (choice=='stat')!=(stat is not None):raise ValueError('choose exactly one Devitalizing alternative')
  if stat is not None and stat not in ('atk','def','spa','spd','spe','acc','eva'):raise ValueError('actual selected combat stat required')
  old=t.spec.get('capture_next_save',[])
  if choice=='save' and old:
   if type(composition)is not dict or set(composition)!={'mode','reason'} or composition['mode'] not in ('add','replace') or not composition['reason']:raise ValueError('same next-Save penalties require explicit GM add/replace composition')
  elif composition is not None:raise ValueError('composition belongs only to overlapping next-Save penalties')
  _charge(e,a,TABLE,1)
  if choice=='slowed':e.apply_status(t,'둔화',source=TABLE,applied_by=a)
  elif choice=='stat':__import__('effects').apply_stage_changes(e,a,t,{stat:-1},source_id=TABLE)
  else:
   if composition and composition['mode']=='replace':
    for row in old:
     issuer=W.actor_index(e).get(row['actor_id'])
     prior=issuer.spec.get('capture_attempts',{}).get(row['attempt_id'],{}).get('devitalizing',{}) if issuer else {}
     _verify(prior)
     if prior.get('state')!='used' or prior.get('choice')!='save' or prior.get('target_id')!=t.entity_id or prior.get('save_consumed'):
      raise ValueError('actual issued next Save penalty required for replacement')
     prior['save_consumed']='replaced';_seal(prior)
    old=[]
   t.spec['capture_next_save']=[*old,{'actor_id':a.entity_id,'attempt_id':attempt_id,'amount':-3,'composition':deepcopy(composition)}]
  event.update(state='used',choice=choice,stat=stat)
  _seal(event)
  return deepcopy(event)
 return G.transition(engine,trainer,apply,participants=(target,),include_rulings=True)

def save_penalty(engine,actor):
 rows=actor.spec.get('capture_next_save',[])
 if not rows:return 0
 index=W.actor_index(engine)
 for row in rows:
  owner=index.get(row['actor_id'])
  if owner is None or row.get('amount')!=-3:raise ValueError('Devitalizing next Save origin changed')
  event=owner.spec.get('capture_attempts',{}).get(row['attempt_id'],{}).get('devitalizing',{})
  _verify(event)
  if event.get('state')!='used' or event.get('choice')!='save' or event.get('target_id')!=actor.entity_id or event.get('save_consumed'):raise ValueError('actual issued next Save penalty required')
  event['save_consumed']=True;_seal(event)
 actor.spec.pop('capture_next_save')
 actor.spec.setdefault('capture_save_history',[]).append({'rows':deepcopy(rows),'round':engine.round_no,'at':engine.elapsed_seconds})
 return sum(row['amount'] for row in rows)

def fast_pitch(engine,trainer,target,ball_name='몬스터볼',**options):
 import initiative_interrupts as I
 W.require_actors(engine,trainer,target);technique(trainer,'빠른 투구',required=True)
 def apply(e,a,t):
  technique(a,'빠른 투구',required=True)
  if AP.available(a)<1:raise ValueError('insufficient AP for Fast Pitch')
  loan=None
  if e._active_turn_actor is not a:
   request={'id':'capture-fast-pitch-'+str(len(getattr(e,I.KEY,{}).get('windows',{}))+1),'actor_id':a.entity_id,'source':TABLE,'priority':0,
    'mode':'borrow_turn','payment':'future_turn','budget':None,'clock':'owner_turn','settlement_clock':'none'}
   loan=I.queue(e,[request],trigger=I.between_trigger(e));I.begin(e,loan['window_id'],request['id'])
  AP.spend(a,1)
  before=a.spec.get('capture_attempt_serial',0)
  result=e.throw_ball(a,t,ball_name,**options)
  if a.spec.get('capture_attempt_serial',0)==before:raise ValueError('Fast Pitch needs its actual legal throw')
  return {'captured':result,'loan':loan}
 return G.transition(engine,trainer,apply,participants=(target,),include_rulings=True,include_grid=engine.grid is not None)

def _gotta_variant(trainer,choice):
 # Existing imported Collector sheets keep their separately selected legacy
 # consumer. They cannot acquire a new digit-swap or CSV passive by import.
 actual=any(active and row['static_acquisition']['feature_id']==GOTTA for _,row,active in TFA._static_records(trainer))
 if not actual:
  if choice:raise ValueError('actual acquired Gotta Catch Em All reversal required')
  return None
 return feature_variant(trainer,GOTTA)

def gotta_preflight(engine,trainer,procedure,choice):
 variant=_gotta_variant(trainer,choice)
 if choice is not None and type(choice)is not bool:raise ValueError('explicit optional Gotta Catch Em All reversal required')
 if variant==CSV and procedure.sides!=20:raise ValueError('CSV Gotta requires d20 capture')
 if not choice:return
 if variant not in (CORE,CSV):raise ValueError('actual acquired matching Gotta reversal required')
 if (variant==CORE and procedure.sides!=100) or (variant==CSV and procedure.sides!=20):raise ValueError('Gotta reversal requires its matching capture procedure')
 _quota(engine,trainer,GOTTA,'daily' if variant==CORE else 'scene',3 if variant==CORE else 1)
 if variant==CORE:
  import turn
  if not turn.can_act(engine,trainer) or not ACTION.ordinary_permission(engine,trainer) or not ACTION.status_permission(engine,trainer,'swift'):
   raise ValueError('Gotta digit swap needs a legal Swift Action')
  budget=getattr(trainer,'budget',None)
  if budget is not None and budget.get('swift',0)<1:raise ValueError('reserve a Swift Action for the Core digit swap')

def gotta_roll(engine,trainer,natural,procedure,choice):
 variant=_gotta_variant(trainer,choice)
 if choice is not None and type(choice)is not bool:raise ValueError('explicit optional Gotta Catch Em All reversal required')
 if not variant:
  if choice:raise ValueError('actual acquired Gotta Catch Em All required')
  return natural,0
 if variant==SEPT:
  if choice:raise ValueError('official Collector uses its separate stack choice')
  return natural,0
 if not choice:return natural,3 if variant==CSV else 0
 if (variant==CORE and procedure.sides!=100) or (variant==CSV and procedure.sides!=20):raise ValueError('Gotta reversal requires its matching capture procedure')
 frequency=_quota(engine,trainer,GOTTA,'daily' if variant==CORE else 'scene',3 if variant==CORE else 1)
 import turn
 if variant==CORE:
  if not turn.spend(engine,trainer,'swift','Gotta Catch Em All'):raise ValueError('Gotta digit swap needs a Swift Action')
  changed=natural if natural==100 else (natural%10)*10+natural//10
  # Swapping 01 produces 10, not natural 100; 10 produces numerical 1.
  changed=10 if natural==1 else changed
 else:
  _charge(engine,trainer,GOTTA)
  changed=natural if natural==1 else 21-natural
 F.consume_activation(trainer,GOTTA,frequency,engine=engine)
 return changed,3 if variant==CSV else 0

def arm_knockout(engine,trainer,target,*,choice,ball_name='몬스터볼',ball_options=None):
 name={'false_strike':'거짓 타격','catch_combo':'캐치 콤보'}.get(choice)
 if name is None:raise ValueError('choose False Strike or Catch Combo')
 W.require_actors(engine,trainer,target);technique(trainer,name,required=True)
 if not target.spec.get('wild',target.side=='wild') or target.spec.get('trainer_id'):raise ValueError('actual unowned wild target required')
 if ball_options is not None and type(ball_options)is not dict:raise ValueError('actual ball options required')
 def apply(e,a,t):
  a.spec.setdefault('capture_knockout_choices',{})[t.entity_id]={'choice':choice,'ball_name':ball_name,
   'ball_options':deepcopy(ball_options or {}),'round':e.round_no,'at':e.elapsed_seconds}
 return G.transition(engine,trainer,apply,participants=(target,))

def _knockout_owner(engine,attacker,target,name):
 if not target.spec.get('wild',target.side=='wild') or target.spec.get('trainer_id') or target.captured:return None
 owners=[a for a in W.actor_index(engine).values() if a.kind=='trainer' and
  (attacker is a or attacker.kind=='pokemon' and attacker.spec.get('trainer_id')==a.entity_id) and
  a.spec.get('capture_knockout_choices',{}).get(target.entity_id,{}).get('choice')==name]
 if len(owners)>1:raise ValueError('one actual Capture knockout owner required')
 if not owners:return None
 a=owners[0];choice=a.spec['capture_knockout_choices'][target.entity_id]
 if choice['round']!=engine.round_no or choice['at']!=engine.elapsed_seconds:return None
 return a

def replace_knockout(engine,target,before,proposed):
 if before<=0 or proposed>0:return proposed
 scopes=[x for x in getattr(engine,'_attack_history_scopes',{}).values() if x['target'] is target]
 ball=getattr(engine,'_capture_ball_damage',None)
 if not scopes and not (ball and ball[1] is target and ball[2].get('hit')):return proposed
 attacker=scopes[-1]['attacker'] if scopes else ball[0]
 owner=_knockout_owner(engine,attacker,target,'false_strike')
 if owner is None or not technique(owner,'거짓 타격'):return proposed
 frequency=_quota(engine,owner,TABLE+'/false-strike','scene',2)
 _charge(engine,owner,TABLE)
 F.consume_activation(owner,TABLE+'/false-strike',frequency,engine=engine)
 owner.spec['capture_knockout_choices'].pop(target.entity_id)
 target.spec.setdefault('capture_knockout_history',[]).append({'choice':'false_strike','attacker_id':attacker.entity_id,
  'trainer_id':owner.entity_id,'before':before,'proposed':proposed,'after':1,'round':engine.round_no,'at':engine.elapsed_seconds})
 return 1

def after_attack(engine,attacker,target,move,receipt,native_context):
 if native_context is None or target.hp>0 or not target.fainted or attacker.kind!='pokemon':return
 owner=_knockout_owner(engine,attacker,target,'catch_combo')
 if owner is None or not technique(owner,'캐치 콤보'):return
 frequency=_quota(engine,owner,TABLE+'/catch-combo','daily')
 choice=owner.spec['capture_knockout_choices'].pop(target.entity_id)
 _charge(engine,owner,TABLE);F.consume_activation(owner,TABLE+'/catch-combo',frequency,engine=engine)
 event={'trainer_id':owner.entity_id,'attacker_id':attacker.entity_id,'target_id':target.entity_id,
  'source':move['id'],'receipt':deepcopy(receipt),'round':engine.round_no,'at':engine.elapsed_seconds,'state':'resolving'}
 target.spec.setdefault('capture_knockout_history',[]).append(event)
 engine._capture_combo=event
 try:
  event['captured']=engine.throw_ball(owner,target,choice['ball_name'],**choice['ball_options'])
  event['state']='resolved'
 except ValueError as error:
  # The attack KO and triggered Free use are already native facts. A rejected
  # optional throw cannot rewind that attack or fabricate a successful ball.
  event.update(state='rejected',captured=False,reason=str(error))
 finally:vars(engine).pop('_capture_combo',None)

def combo_allowed(engine,trainer,target):
 event=getattr(engine,'_capture_combo',None)
 return bool(event and event['state']=='resolving' and event['trainer_id']==trainer.entity_id and
  event['target_id']==target.entity_id and event['round']==engine.round_no and event['at']==engine.elapsed_seconds and
  event in target.spec.get('capture_knockout_history',[]) and event['receipt']['before']['hp']>0 and event['receipt']['after']['hp']<=0)


TOOLS={'hand_net':{'name':'수제 그물','line':759,'ac':6},
       'weighted_net':{'name':'투망','line':760,'ac':8},
       'glue_cannon':{'name':'끈적포','line':758,'ac':8},
       'lasso':{'name':'Lasso','line':405,'ac':None}}

def observe_tool(engine,actor,object_id,*,tool,reason,hp=None,shots=None):
 """Observe an owned, real two-handed tool; observation never buys an item.

The book supplies no Lasso attack procedure. Its physical restraint is an
explicit GM fact, consumed by Snare without inventing such a procedure.
"""
 W.require_actors(engine,actor)
 if tool not in TOOLS or not isinstance(reason,str) or not reason.strip():raise ValueError('actual capture tool and observation reason required')
 if tool!='lasso':_file(engine.r,'input/ch09-equipment.md')
 obj=getattr(engine,'_physical_objects',{}).get(object_id)
 if not obj or obj.get('owner_id')!=actor.entity_id or W.distance_known(obj,actor)!=0:raise ValueError('actual owned capture tool at its user required')
 W.require_physical_access(obj)
 if tool in ('hand_net','weighted_net'):
  C.integer(hp,'actual net durability',1)
  if hp not in ((50,100,200) if tool=='hand_net' else (50,80,150)):raise ValueError('select the actual printed net durability')
 elif hp is not None:raise ValueError('durability belongs only to a physical net')
 if tool=='glue_cannon':C.integer(shots,'actual loaded Glue Cannon shots',0,3)
 elif shots is not None:raise ValueError('shots belong only to Glue Cannon')
 import items
 occupied=items.equipment_options(actor,slots=('주요손','반대손'))
 if occupied or any(o.get('capture_tool',{}).get('holder_id')==actor.entity_id for o in getattr(engine,'_physical_objects',{}).values() if o is not obj):raise ValueError('capture tool needs both actually available hands')
 def apply(e,a):
  actual=e._physical_objects[object_id]
  if tool in ('hand_net','weighted_net'):
   __import__('physical_object_attacks').configure(e,a,object_id,max_hp=hp,reduction=0,minimum_damage=0,
    source='input/ch09-equipment.md:'+str(TOOLS[tool]['line']),reason=reason)
  actual.update(capture_tool={'kind':tool,'holder_id':a.entity_id,'source':'input/ch09-equipment.md' if tool!='lasso' else CT.SOURCE['file'],
   'line':TOOLS[tool]['line'],'reason':reason,'hp':hp,'shots':shots,'history':[]})
  _seal(actual['capture_tool'])
  return deepcopy(actual)
 return G.transition(engine,actor,apply)

def _tool(engine,actor,object_id):
 obj=getattr(engine,'_physical_objects',{}).get(object_id)
 if not obj or obj.get('owner_id')!=actor.entity_id or obj.get('capture_tool',{}).get('holder_id')!=actor.entity_id:raise ValueError('actual held capture tool required')
 W.require_usable_object(obj)
 if W.distance_known(obj,actor)!=0:raise ValueError('actual capture tool must be at its holder')
 if __import__('items').equipment_options(actor,slots=('주요손','반대손')):raise ValueError('actual capture tool needs both available hands')
 row=obj['capture_tool']
 _verify(row)
 if row['kind']!='lasso':_file(engine.r,'input/ch09-equipment.md')
 if row['hp'] is not None and obj[__import__('physical_object_attacks').FIELD]['hp']<=0:raise ValueError('broken net cannot restrain')
 return obj,row

def tools_accuracy(engine,actor,tool):
 variant=technique(actor,'작업 도구')
 if variant is None:return 0
 if tool=='cap_cannon':return 2 if variant==MAY else 0
 if tool not in ('ball','hand_net','lasso','weighted_net','glue_cannon'):raise ValueError('Tools of Trade applies only to its actual tools')
 return 2

@ACTION.resolved_native('actor',TABLE,'capture_tool')
def use_tool(engine,actor,target,object_id,*,fixed_accuracy=None,aim=None):
 W.require_actors(engine,actor,target)
 obj,row=_tool(engine,actor,object_id);kind=row['kind']
 if target.kind!='pokemon' or target.fainted or target.captured or target.dead:raise ValueError('actual conscious Pokemon tool target required')
 import body_state as BODY,turn
 if kind=='hand_net':
  if not BODY.in_range(engine,actor,target,BODY.melee_reach(actor)):raise ValueError('actual Hand Net target outside melee reach')
 elif type(aim)is not dict or set(aim)!=({'reachable','reason','ac'} if kind=='lasso' else {'reachable','reason'}) or aim['reachable'] is not True or not isinstance(aim['reason'],str) or not aim['reason'].strip():
  raise ValueError('observe actual tool reach; source specifies no metric range')
 if kind=='lasso':C.integer(aim['ac'],'explicit GM Lasso attack AC',0,20)
 if kind=='hand_net' and target.spec.get('size') not in ('극소형','소형','Tiny','Small'):raise ValueError('Hand Net requires an actually Small Pokemon')
 if kind=='glue_cannon' and row['shots']<=0:raise ValueError('Glue Cannon is empty')
 if fixed_accuracy is not None:C.integer(fixed_accuracy,'capture tool accuracy',1,20)
 if any(x.get('capture_restraint',{}).get('target_id')==target.entity_id for x in engine._physical_objects.values()):raise ValueError('overlapping physical capture tools need an explicit composition ruling')
 move={'id':TABLE,'name':TOOLS[kind]['name'],'ac':aim['ac'] if kind=='lasso' else TOOLS[kind]['ac'],'class':'변화','type':'노말'}
 if not turn.spend(engine,actor,'standard',move['name']):return False
 if kind=='glue_cannon':row['shots']-=1
 hit,natural,_=engine.accuracy_check(actor,target,move,fixed_roll=fixed_accuracy,situational=tools_accuracy(engine,actor,kind))
 event={'actor_id':actor.entity_id,'target_id':target.entity_id,'hit':hit,'natural':natural,'round':engine.round_no,'at':engine.elapsed_seconds,'kind':kind,'aim':deepcopy(aim),'tools_accuracy':tools_accuracy(engine,actor,kind)}
 row['history'].append(event)
 _seal(row)
 if hit:
  obj['capture_restraint']=dict(deepcopy(event),state='active')
  _seal(obj['capture_restraint'])
  if kind in ('weighted_net','glue_cannon'):engine.apply_status(target,'둔화',source=TABLE,applied_by=actor)
  if kind=='glue_cannon' and natural==20:
   engine.cure_status(target,'둔화');engine.apply_status(target,'구속',source=TABLE,applied_by=actor)
   engine.apply_status(target,'수렁',source=TABLE,applied_by=actor)
 return deepcopy(event)

def observe_lasso(engine,actor,target,object_id,*,reason):
 W.require_actors(engine,actor,target);obj,row=_tool(engine,actor,object_id)
 if row['kind']!='lasso' or not isinstance(reason,str) or not reason.strip():raise ValueError('actual Lasso restraint and reason required')
 if W.distance_known(actor,target) is None:raise ValueError('actual encountered Lasso target required')
 def apply(e,a,t):
  actual,_=_tool(e,a,object_id)
  actual['capture_restraint']={'actor_id':a.entity_id,'target_id':t.entity_id,'kind':'lasso','state':'active',
   'reason':reason,'round':e.round_no,'at':e.elapsed_seconds}
  _seal(actual['capture_restraint'])
  return deepcopy(actual['capture_restraint'])
 return G.transition(engine,actor,apply,participants=(target,))

def restraints(engine,target):
 result=[]
 for obj in getattr(engine,'_physical_objects',{}).values():
  row=obj.get('capture_restraint',{})
  if row.get('state')!='active' or row.get('target_id')!=target.entity_id:continue
  _verify(row)
  if obj.get('destroyed') or obj.get('disabled') or obj.get('consumed'):continue
  W.require_usable_object(obj)
  tool=obj.get('capture_tool',{})
  _verify(tool)
  if tool.get('hp') is not None and obj[__import__('physical_object_attacks').FIELD]['hp']<=0:continue
  if row.get('kind')=='glue_cannon' and '구속' not in target.conditions:continue
  result.append((obj,row))
 return result

def snared(engine,actor,target):
 import wild_equipment as WILD,net_capsule as NET
 if WILD.pending(target) or NET.active(target) is not None or restraints(engine,target):return True
 # Core also includes a Pokemon actually drawn into this encounter by Bait.
 if technique(actor,'덫')==CSV:return False
 for holder in W.actor_index(engine).values():
  for bait in holder.spec.get('placed_bait',{}).values():
   if bait.get('status')=='encountered' and bait.get('target_id')==target.entity_id:return True
 return False

def net_modifier(engine,target,procedure):
 return (-20 if procedure.sides==100 else 4) if any(row['kind'] in ('hand_net','weighted_net') for _,row in restraints(engine,target)) else 0

def arm_pursuit(engine,trainer,pokemon,target,*,movement_mode=None,set_damage=False):
 W.require_actors(engine,trainer,pokemon,target);technique(trainer,'끝없는 추격',required=True)
 if pokemon.kind!='pokemon' or pokemon.spec.get('trainer_id')!=trainer.entity_id or not pokemon.on_field or pokemon.captured:raise ValueError('one of your actually on-field Pokemon required')
 if target.side==trainer.side:raise ValueError('Relentless Pursuit requires an actual foe')
 def apply(e,a,p,t):
  a.spec.setdefault('capture_pursuit_choices',{})[t.entity_id]={'pokemon_id':p.entity_id,'movement_mode':movement_mode,'set_damage':set_damage,'round':e.round_no}
 return G.transition(engine,trainer,apply,participants=(pokemon,target))

def move_authority(engine,actor,target,move_id,source):
 if source!=TABLE:return False
 event=getattr(engine,'_capture_pursuit',None)
 if not event or event['pokemon_id']!=actor.entity_id or event['target_id']!=target.entity_id or move_id!='struggle' or event['phase']!='attack':raise ValueError('Relentless Pursuit requires its actual native foe escape')
 trainer=W.actor_index(engine).get(event['trainer_id'])
 if trainer is None or actor.spec.get('trainer_id')!=trainer.entity_id or not actor.on_field:raise ValueError('Relentless Pursuit lost its actual owned on-field Pokemon')
 technique(trainer,'끝없는 추격',required=True)
 return True

def shift_grant(engine,actor,kind,*,movement=False):
 event=getattr(engine,'_capture_pursuit',None)
 if not event or event['pokemon_id']!=actor.entity_id or event['phase']!='shift':return False
 if kind!='shift' or not movement or event.get('shift_used'):raise ValueError('Relentless grants exactly one actual Shift movement')
 if not ACTION.status_permission(engine,actor,'shift') or not __import__('body_modes').permits(actor,'shift'):return False
 event['shift_used']=True;ACTION.record_action(engine,actor,'shift')
 return True

def before_escape(engine,owner,target,source,*,kind,request_id):
 if kind!='repel':return
 __import__('repels').validate_escape(engine,target,request_id)
 for trainer in list(W.actor_index(engine).values()):
  choice=trainer.spec.get('capture_pursuit_choices',{}).get(target.entity_id)
  if not choice or choice['round']!=engine.round_no or not technique(trainer,'끝없는 추격'):continue
  pokemon=W.actor_index(engine).get(choice['pokemon_id'])
  if pokemon is None or pokemon.spec.get('trainer_id')!=trainer.entity_id or not pokemon.on_field or pokemon.fainted:continue
  import turn,body_state as BODY
  if not turn.can_act(engine,pokemon) or not turn.movement_permission(engine,pokemon):continue
  if AP.available(trainer)<2:continue
  trainer.spec['capture_pursuit_choices'].pop(target.entity_id)
  _charge(engine,trainer,TABLE,2)
  event={'trainer_id':trainer.entity_id,'pokemon_id':pokemon.entity_id,'target_id':target.entity_id,'origin':tuple(target.pos),
   'escape_source':source,'request_id':request_id,'round':engine.round_no,'phase':'shift','shift_used':False}
  trainer.spec.setdefault('capture_pursuit_history',[]).append(event)
  engine._capture_pursuit=event
  try:
   engine.approach(pokemon,target,movement_mode=choice['movement_mode'])
   event['after_shift']=tuple(pokemon.pos)
   if not BODY.in_range(engine,pokemon,target,BODY.melee_reach(pokemon)):
    event.update(phase='complete',result='out_of_range');continue
   event['phase']='attack'
   before=set(getattr(engine,'_move_completions',{}))
   with ACTION.move_grant(engine,pokemon,target,'struggle',source=TABLE,kind='free') as token:
    engine.use_move(pokemon,target,'struggle',free_action=True,count_use=False,_action_grant=token,set_damage=choice['set_damage'])
   completions=[r for uid,r in engine._move_completions.items() if uid not in before and r['actor'] is pokemon and r['move_id']=='struggle']
   if len(completions)!=1:raise ValueError('actual Relentless Struggle completion required')
   result=__import__('move_completion').recipient_result(completions[0],target)
   hit=bool(result and result.get('hit') and not result.get('cancelled'))
   if hit:engine.apply_status(target,'넘어짐',source=TABLE,applied_by=pokemon)
   event.update(phase='complete',completion_id=completions[0]['id'],hit=hit)
  except ValueError as error:
   event.update(phase='complete',result='rejected_after_payment',reason=str(error))
  finally:vars(engine).pop('_capture_pursuit',None)

def validate_world(engine,index):
 for obj in getattr(engine,'_physical_objects',{}).values():
  tool=obj.get('capture_tool')
  if tool:
   _verify(tool)
   if tool.get('kind') not in TOOLS or tool.get('holder_id') not in index or obj.get('owner_id')!=tool['holder_id']:raise ValueError('actual Capture tool owner/holding observation changed')
   if tool.get('hp') is not None:
    profile=obj.get(__import__('physical_object_attacks').FIELD,{}).get('profile',{})
    if profile.get('max_hp')!=tool['hp'] or profile.get('source')!='input/ch09-equipment.md:'+str(TOOLS[tool['kind']]['line']):raise ValueError('actual sourced net durability owner required')
 for actor in index.values():
  for attempt in actor.spec.get('capture_attempts',{}).values():
   event=attempt.get('devitalizing')
   if event:
    _verify(event)
    if event['actor_id']!=actor.entity_id or event['target_id']!=attempt.get('target') or event['physical_instance_id']!=attempt.get('physical_instance_id') or not attempt.get('hit') or attempt.get('captured') or attempt.get('status')!='failed_capture':
     raise ValueError('Devitalizing origin must retain the actual escaped ball')
  save_rows=actor.spec.get('capture_next_save',[])
  if len({(row.get('actor_id'),row.get('attempt_id')) for row in save_rows})!=len(save_rows):raise ValueError('same Devitalizing escape cannot issue duplicate next Save penalties')
  for row in save_rows:
   owner=index.get(row.get('actor_id'))
   if owner is None:raise ValueError('next Save needs its actual Devitalizing owner')
   event=owner.spec.get('capture_attempts',{}).get(row.get('attempt_id'),{}).get('devitalizing',{})
   _verify(event)
   if event.get('choice')!='save' or event.get('state')!='used' or event.get('save_consumed') or event.get('target_id')!=actor.entity_id or row.get('amount')!=-3:raise ValueError('next Save needs its actual one-shot issued event')
 return True
