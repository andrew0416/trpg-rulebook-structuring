"""Oracle source adapters over native acquisition, observation, rolls and effects."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import common_checks as C
import state_grants as G
import world_entities as W
import combat_timing as TIME
import frequency as F

CLASS='class/오라클';DIVINATION='feat/점술';SIGHT='feat/정체밝힘-시야'
SMALL='feat/작은-예언';MARK='feat/마크-오브-비전';PREVIEW='feat/2초-미리보기';PRESCIENCE='feat/예견'
PICKUP='ability/픽업-core';ILLUSION='ability/일루전'
SOURCE_SHA256='a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'
FEATURES={CLASS:(3003,3005),DIVINATION:(3007,3011),SIGHT:(3021,3025),SMALL:(3029,3033),MARK:(3035,3040),PREVIEW:(3042,3046),PRESCIENCE:(3048,3053)}
DEFINITIONS={u:{'span':list(s),'catalog_span':[2993,2993] if u==CLASS else list(s),
 'clause_id':'C04-111' if u==MARK else 'input/ch04-trainer-classes.md:'+str(s[0])+'-'+str(s[1]),
 'parent':None if u==CLASS else DIVINATION if u==SMALL else SIGHT if u==PRESCIENCE else CLASS,
 'minimum_rank':3 if u==CLASS else 4 if u in (SMALL,MARK) else 5 if u==PREVIEW else 6 if u==PRESCIENCE else 0,
 'stat_tags':['spd']} for u,s in FEATURES.items()}
CORE_CONTRACTS={PICKUP:{'type':'core_pickup','minimum_seconds':300,'die':20,'frequency':'daily'},
 ILLUSION:{'type':'core_illusion','maximum_marks':'focus_rank','action':'standard','appearance':'free_once_per_round','ends':'damaging_move_hit'}}
CORE_NAMES={PICKUP:'픽업 [Core p326]',ILLUSION:'일루전'}
EXTRACT='data/verification/oracle-core-source-excerpts.txt'
EXTRACT_SHA='0af21c9a5c753af07456485516b85304482a92cd61abd1ecf67a4af5f12c9049'


def records(actor,feature=None,active=False):
 import trainer_feature_acquisition as T
 return [r['static_acquisition'] for _,r,live in T._static_records(actor) if r['static_acquisition']['feature_id'] in FEATURES
  and (feature is None or r['static_acquisition']['feature_id']==feature) and (not active or live)]


def acquired(actor,feature=CLASS):
 rows=records(actor,feature,True)
 return rows[-1] if rows else None


def acquisition_snapshot(e,actor,feature,rank,selection):
 import skill_modifiers as SK,elemental_connection as EL
 if rank is not None or selection is not None:raise ValueError('Oracle has no ranks or acquisition selection')
 EL.choices(e,actor)
 parent=DEFINITIONS[feature]['parent']
 return {'rank':SK.rank(e.r,actor,'통찰')[2],
  'parents':[r['request_id'] for r in records(actor,parent,True)] if parent else [],
  'oracle_features':[r['request_id'] for r in records(actor,active=True)],
  'mystic':sum(EL.matches(x,EL.MYSTIC) for field in ('edges','feats') for x in actor.spec.get(field,[]))}


def qualification(actor,feature,snapshot,prerequisite_source):
 import acquisition_qualification as Q
 if prerequisite_source is not None or type(snapshot)is not dict or set(snapshot)!={'rank','parents','oracle_features','mystic'}:raise ValueError('actual Oracle acquisition observations required')
 C.integer(snapshot['rank'],'Perception prerequisite rank',1,6);C.integer(snapshot['mystic'],'Mystic Senses count',0,1)
 parent=DEFINITIONS[feature]['parent'];known={r['request_id'] for r in records(actor,parent)} if parent else set()
 allrows={r['request_id']:r['feature_id'] for r in records(actor)}
 if not set(snapshot['oracle_features'])<=set(allrows):raise ValueError('actual Oracle prerequisite receipts required')
 return Q.require(feature,'native','acquire',[
  Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),
  Q.check('parent','prerequisite',snapshot['mystic']==1 if feature==CLASS else bool(snapshot['parents']) and set(snapshot['parents'])<=known,'actual Mystic Senses or Oracle parent required'),
  Q.check('rank','prerequisite',snapshot['rank']>=DEFINITIONS[feature]['minimum_rank'],'printed Perception rank required'),
  Q.check('three_features','prerequisite',feature!=PREVIEW or len({allrows[x] for x in snapshot['oracle_features']})>=3,'three acquired Oracle Features required')])


def after_acquire(e,actor,feature,sid):
 G.stat(actor,'spd',1,sid,operation_id='acquisition_stat_tag')
 if feature in (CLASS,PREVIEW):
  value=CORE_NAMES[PICKUP] if feature==CLASS else '본능'
  G.grant(actor,'abilities',value,sid,'feature',rule_id=feature,owner_id=actor.entity_id,lifetime='while_owned')
  e.register_abilities_one(actor,value)


def validate_acquisition(actor,record,sid,active):
 if active and actor.spec.get(G.KEY,{}).get('stat_sources',{}).get('spd',{}).get('sources',{}).get(sid,{}).get('acquisition_stat_tag')!={'delta':1,'minimum':None}:raise ValueError('actual Oracle Special Defense tag required')


def require(e,actor,feature):
 W.require_actors(e,actor)
 if e.r._selected_rule(feature)!=feature or not acquired(actor,feature):raise ValueError('actual acquired Oracle Feature required: '+feature)
 __import__('trainer_feature_acquisition').validate_actor(actor)


def sight(actor):return bool(acquired(actor,SIGHT))


def instinct_bonus(actor,attacker=None,engine=None):
 if not __import__('ability_transitions').active(actor,'ability/본능'):return 0
 if engine is not None and attacker is not None and __import__('chronicler').defensive_ignored(engine,attacker,actor):return 0
 return 2


def validate_core_ability(rules,row):
 uid=row.get('id')
 if uid not in CORE_CONTRACTS or row.get('name')!=CORE_NAMES[uid] or row.get('native_contract')!=CORE_CONTRACTS[uid]:raise ValueError('exact Oracle Core ability contract required')
 if sha256((Path(rules.root)/EXTRACT).read_bytes()).hexdigest()!=EXTRACT_SHA:raise ValueError('reviewed Oracle English source changed')
 if sha256((Path(rules.root)/'input/ch04-trainer-classes.md').read_bytes()).hexdigest()!=SOURCE_SHA256:raise ValueError('Oracle source changed')
 return row


def registration(rules,name):
 for uid,label in CORE_NAMES.items():
  if name in (uid,label):
   if uid==ILLUSION:
    from source_context import verified_source
    verified_source(rules,{'file':'input/db/abilities.csv','sha256':'87efebd17b0a5fe09c9db060a16a8844cf41be53d65eb35716cf62f80a177fae'},label='existing Core Illusion R333')
    if sha256((Path(rules.root)/EXTRACT).read_bytes()).hexdigest()!=EXTRACT_SHA:raise ValueError('reviewed Core Illusion source changed')
   else:validate_core_ability(rules,rules.core_abilities[uid])
   if rules._selected_rule(uid)!=uid:raise ValueError('selected exact Oracle Core ability required')
   return {'name':label,'source_id':uid,'equivalent_source_ids':[uid]}
 return None


def pay(e,actor,source,action,*,ap=0,quota=None):
 import action_points as AP,turn as TURN
 if AP.available(actor)<ap:raise ValueError('available Oracle AP required')
 if quota and not F.activation_allowed(actor,source,quota,engine=e):raise ValueError('Oracle frequency exhausted')
 if not TURN.spend(e,actor,action,source):raise ValueError('Oracle requires '+action+' action')
 if ap:AP.charge(actor,ap)
 if quota:F.consume_activation(actor,source,quota,engine=e)


def extended(e,actor,source,seconds,reason,participants=()):
 C.integer(seconds,'observed Extended Action seconds',1);G._text(reason,'Extended Action observation')
 if e.encounter_active:raise ValueError('Extended Action requires noncombat time')
 pay(e,actor,source,'extended')
 return __import__('activity_jobs').run_fixed(e,actor,participants,seconds=seconds,source=source,context={'reason':reason})


def divination(e,actor,mode,*,seconds,reason,target=None):
 require(e,actor,DIVINATION)
 if mode not in ('augury','scrying'):raise ValueError('choose Augury or Scrying')
 import perception_observe as O
 binding=O.divination_target(e,actor,mode,target)
 def apply(se,a):
  quota={'kind':'daily','uses':3}
  if not F.activation_allowed(a,DIVINATION,quota,engine=se):raise ValueError('shared Divination Daily x3 exhausted')
  job=extended(se,a,DIVINATION,seconds,reason)
  if O.divination_target(se,a,mode,W.entity_index(se).get(binding.get('target_id')) if mode=='scrying' and binding['kind']=='item' else None)!=binding:raise ValueError('Divination target changed during Extended Action')
  result=O.divination_information(se,a,mode,binding)
  F.consume_activation(a,DIVINATION,quota,engine=se)
  return dict(result,activity=job)
 return G.transition(e,actor,apply,include_rulings=True)


def prophecies(actor):return [r for r in TIME.records(actor) if 'oracle_prophecy' in r]


def small(e,actor):
 require(e,actor,SMALL)
 if not e.encounter_active:raise ValueError('next owner turn requires an actual encounter')
 def apply(se,a):
  pay(se,a,SMALL,'swift',ap=1)
  face=replace_d20(se,a,se.d20(),'small_prophecy')
  row={'source':SMALL,'turn_owner':a,'turn_deadline':a.custom_conditions.get('combat_turn_serial',0)+1,
   'oracle_prophecy':{'face':face,'acquisition':acquired(a,SMALL)['request_id'],'owner_id':a.entity_id,'created_at':se.elapsed_seconds}}
  TIME.install(se,a,row)
  return deepcopy(row['oracle_prophecy'])
 return G.transition(e,actor,apply)


def choose_prophecy(e,owner,roller,*,willing=False,index=0):
 require(e,owner,SMALL);W.require_actors(e,roller)
 if type(willing)is not bool:raise ValueError('actual roller consent required')
 if owner is not roller and (not willing or not owner.side or owner.side!=roller.side):raise ValueError('self or willing ally required')
 rows=prophecies(owner);C.integer(index,'stored prophecy index',0,len(rows)-1)
 if 'oracle_prophecy_choice' in roller.spec:raise ValueError('one selected replacement for next actual d20')
 roller.spec['oracle_prophecy_choice']={'owner_id':owner.entity_id,'prophecy':deepcopy(rows[index]['oracle_prophecy']),'willing':willing or owner is roller}
 return deepcopy(roller.spec['oracle_prophecy_choice'])


def replace_d20(e,roller,face,purpose):
 """Called by actual single-d20 producers, before their arithmetic."""
 choice=roller.spec.get('oracle_prophecy_choice')
 if choice is None:return face
 W.require_actors(e,roller);C.integer(face,'actual single d20 face',1,20)
 owner=W.actor_index(e).get(choice['owner_id'])
 rows=[] if owner is None else [r for r in prophecies(owner) if r['oracle_prophecy']==choice['prophecy']]
 roller.spec.pop('oracle_prophecy_choice')
 if not rows or not acquired(owner,SMALL):return face
 if owner is not roller and (not choice['willing'] or owner.side!=roller.side):raise ValueError('stored prophecy lost willing ally')
 result=rows[0]['oracle_prophecy']['face']
 TIME.expire(e,owner,rows[0],ending='consumed',event={'kind':'single_d20_replaced','roller_id':roller.entity_id,'purpose':purpose,'original':face,'replacement':result})
 e.log('Small Prophecies '+purpose+': '+str(face)+' -> '+str(result),SMALL)
 return result


def marks(actor):return [r for r in TIME.records(actor) if 'oracle_mark' in r]


def mark_for(owner,target):return next((r for r in marks(target) if r['oracle_mark']['owner_id']==owner.entity_id),None)


def mark_payload(e,owner,target,effect,source,*,preflight=False):
 require(e,owner,MARK);W.require_actors(e,target)
 if source!=MARK or effect.get('owner_id')!=owner.entity_id or target.kind!='trainer':raise ValueError('Mark of Vision requires an actual Trainer')
 if preflight and getattr(e,'_oracle_mark_admission',None)!=(owner.entity_id,target.entity_id):raise ValueError('actual willing Bound AP Mark producer required')
 return {'owner_id':owner.entity_id,'target_id':target.entity_id,'acquisition':acquired(owner,MARK)['request_id']}


def mark(e,owner,target,*,willing,seconds,reason):
 require(e,owner,MARK);W.require_actors(e,target)
 if willing is not True or target.kind!='trainer':raise ValueError('actual willing Trainer required')
 if mark_for(owner,target):raise ValueError('each Mark requires a different Trainer')
 total=sum(mark_for(owner,c)is not None for c in W.actor_index(e).values())
 if total>=__import__('skill_modifiers').rank(e.r,owner,'통찰')[2]//2:raise ValueError('half Perception Rank Mark limit reached')
 def apply(se,a,t):
  extended(se,a,MARK,seconds,reason,() if t is a else (t,))
  instance=G.effect_source(a,{'source_id':MARK+':'+a.entity_id},'oracle-mark')
  se._oracle_mark_admission=(a.entity_id,t.entity_id)
  try:result=__import__('bound_ap').activate_effects(se,a,t,instance,amount=1,
   effects=[{'type':'oracle_mark','owner_id':a.entity_id,'until':'target_ends'}],ending_method='specified',source_ref=MARK)
  finally:del se._oracle_mark_admission
  return {'instance':instance,'status':result.status,'target_id':t.entity_id}
 return G.transition(e,owner,apply,participants=(target,),include_rulings=True)


def mark_access(e,target,owner,*,allow=None,end=False):
 W.require_actors(e,target,owner)
 if type(end)is not bool or allow is not None and type(allow)is not bool:raise ValueError('explicit Mark consent decision required')
 if mark_for(owner,target)is None:raise ValueError('actual Mark required')
 def apply(se,t,a):
  if end:
   TIME.expire(se,t,mark_for(a,t),ending='ended',event={'kind':'target_ends_mark','actor_id':t.entity_id})
   if a.spec.get('oracle_focus')==t.entity_id:a.spec.pop('oracle_focus')
   t.spec.get('oracle_sense_denials',{}).pop(a.entity_id,None)
  elif allow is not None:t.spec.setdefault('oracle_sense_denials',{})[a.entity_id]=not allow
  else:raise ValueError('choose temporary access or permanent end')
  return {'ended':end,'allowed':allow}
 return G.transition(e,target,apply,participants=(owner,))


def focus(e,owner,target=None):
 require(e,owner,MARK)
 if target is not None:
  W.require_actors(e,target)
  if mark_for(owner,target)is None:raise ValueError('actual Mark required for focus')
 owner.spec['oracle_focus']=None if target is None else target.entity_id
 return {'eyes_closed':target is not None,'target_id':owner.spec['oracle_focus']}


def read_mark(e,owner,target,*,senses=False):
 require(e,owner,MARK);W.require_actors(e,target)
 if mark_for(owner,target)is None:raise ValueError('actual Mark required')
 if senses:
  if owner.spec.get('oracle_focus')!=target.entity_id:raise ValueError('close eyes and focus on this one Mark')
  if target.spec.get('oracle_sense_denials',{}).get(owner.entity_id):return {'status':'denied','values':{}}
  return __import__('perception_observe').channel_information(e,target,sensory=True)
 here,there=(W.effective_location(e,c) for c in (owner,target))
 if here['kind']!='grid' or there['kind']!='grid' or here.get('map_id')!=there.get('map_id'):return {'status':'unknown','distance':None,'direction':None}
 dx=there['cell'][0]-here['cell'][0];dy=there['cell'][1]-here['cell'][1]
 return {'status':'observed','distance':max(abs(dx),abs(dy)),'direction':[0 if n==0 else 1 if n>0 else -1 for n in (dx,dy)],'precision':'rough'}


def dispel(e,actor):
 require(e,actor,SIGHT)
 import illusion_state as I,coat_effects as COAT,effect_instances as E
 here=W.effective_location(e,actor)
 if here['kind']!='grid':raise ValueError('actual Burst origin required')
 def inside(other):
  loc=W.effective_location(e,other)
  return loc['kind']=='grid' and loc.get('map_id')==here.get('map_id') and max(abs(loc['cell'][i]-here['cell'][i]) for i in (0,1))<=4
 def apply(se,a):
  pay(se,a,SIGHT,'standard');ended=[]
  for obj in list(getattr(se,'_physical_objects',{}).values()):
   if obj.get('kind')=='illusion' and obj.get('status')!='dismissed' and inside(obj):
    obj['status']='dismissed';obj['location']={'kind':'unknown'};ended.append(obj['id'])
  for c in W.actor_index(se).values():
   if not inside(c):continue
   if I.genjutsu_active(c):I.break_genjutsu(se,c,'Unveiled Sight Burst 4');ended.append(c.entity_id+':genjutsu')
   if I.ability_illusion_active(c):I.end_ability_illusion(se,c,'Unveiled Sight Burst 4');ended.append(c.entity_id+':illusion')
   for row in list(COAT.live(c)):
    if row['source'] in ('move/그림자분신','move/대타출동'):
     E.archive(se,c,row,state='expired',event={'kind':'coat_removed','source':SIGHT,'actor_id':a.entity_id});c.coats.remove(row);ended.append(row['id'])
  return {'source':SIGHT,'ended':ended}
 return G.transition(e,actor,apply,include_rulings=True)


def definition(rules):return {'frequency':{'kind':'scene','uses':1}}


def prepare(e,owner,event_id):
 require(e,owner,PRESCIENCE)
 evidence=__import__('ability_interrupt_choices').require_accuracy_interrupt(e,owner,PRESCIENCE,event_id)
 return {'source':PRESCIENCE,'event_id':event_id,'completion_id':evidence['completion_id'],'owner_id':owner.entity_id,
  'attacker_id':evidence['attacker'].entity_id,'move':__import__('move_defense_reactions')._move_facts(evidence['move'])}


def activate(e,owner,plan):
 if plan!=prepare(e,owner,plan['event_id']):raise ValueError('actual Prescience recipient plan required')
 event=e._passive_events[plan['event_id']]
 event.setdefault('oracle_prescience_misses',[]).append(owner.entity_id)
 return {'changed_to_miss':owner.entity_id}


def prescience_misses(e,event_id):
 """Resolve only the paid native recipient choice, including routed children."""
 event=getattr(e,'_passive_events',{}).get(event_id)
 if event is None:return set()
 if event.get('defense_parent') is not None:event=e._passive_events[event['defense_parent']]
 import ability_interrupt_choices as CHOICE
 expected=[r['owner_id'] for r in event.get(CHOICE.KEY,{}).get('attempts',[])
  if r['source']==PRESCIENCE and r['paid'] and r['outcome']=='activated']
 if event.get('oracle_prescience_misses',[])!=expected:raise ValueError('Prescience miss requires its actual paid recipient choice')
 return set(expected)


def pickup_category(face):
 C.integer(face,'Pickup d20 face',1,20)
 return next(name for hi,name in ((5,None),(7,'x_item'),(10,'berry'),(13,'poke_ball'),(16,'healing'),(17,'stone'),(18,'vitamin'),(19,'held'),(20,'tm')) if face<=hi)


def pickup(e,actor,*,seconds,reason,choose_item):
 W.require_actors(e,actor)
 if not __import__('ability_transitions').active(actor,PICKUP):raise ValueError('actual Core Pickup required')
 C.integer(seconds,'Core Pickup at least five minutes',300)
 if not callable(choose_item):raise ValueError('actual GM item choice provider required')
 def apply(se,a):
  quota={'kind':'daily','uses':1}
  if not F.activation_allowed(a,PICKUP,quota,engine=se):raise ValueError('Core Pickup daily use exhausted')
  job=extended(se,a,PICKUP,seconds,reason);face=replace_d20(se,a,se.d20(),'core_pickup');category=pickup_category(face)
  chosen=choose_item(category)
  if category is None:
   if chosen is not None:raise ValueError('Pickup 1-5 finds nothing')
   item=None
  else:
   item=__import__('perception_observe').pickup_item_choice(se,a,category,chosen,reason)
  F.consume_activation(a,PICKUP,quota,engine=se)
  return {'natural':face,'category':category,'item':item,'activity':job}
 return G.transition(e,actor,apply,include_rulings=True)


def withdraw(e,actor,feature):
 if feature==MARK:
  for target in W.actor_index(e).values():
   row=mark_for(actor,target)
   if row is not None:TIME.expire(e,target,row,ending='ended',event={'kind':'source_lost'})
  actor.spec.pop('oracle_focus',None)
 if feature==SMALL:
  for row in list(prophecies(actor)):TIME.expire(e,actor,row,ending='ended',event={'kind':'source_lost'})


def validate_world(e,index):
 for event_id in getattr(e,'_passive_events',{}):prescience_misses(e,event_id)
 for actor in index.values():
  for row in prophecies(actor):
   p=row['oracle_prophecy'];C.integer(p['face'],'stored actual d20 face',1,20)
   if p['owner_id']!=actor.entity_id or p['acquisition'] not in {r['request_id'] for r in records(actor,SMALL)} or row.get('turn_owner') is not actor:raise ValueError('actual Small Prophecies source and turn owner required')
  focus_id=actor.spec.get('oracle_focus')
  if focus_id is not None and (focus_id not in index or mark_for(actor,index[focus_id])is None):raise ValueError('one actual Mark focus required')
  for row in marks(actor):
   p=row['oracle_mark'];owner=index.get(p['owner_id'])
   if owner is None or p['target_id']!=actor.entity_id or actor.kind!='trainer' or p['acquisition'] not in {r['request_id'] for r in records(owner,MARK)}:raise ValueError('actual bound Mark source required')
   if 'ap_binding' not in row:raise ValueError('Mark must retain its actual one AP binding')
  __import__('perception_observe').validate_divination_facts(e,actor)
 return True
