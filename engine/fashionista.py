"""PTK ch04:1984-2044 Fashionista: chosen skills, Fashionista recipes and their actual equipment consumers.

The class is a template. Committed static acquisitions own the two chosen
Fashionista Skills and each Feature's printed rank prerequisites. Consumers
read live acquisitions: Dashing Makeover (bound AP item projection), Style is
Eternal (armed held-item retention), Accessorize (second accessory slot),
Parfumier (incense Move while actively held), Versatile Wardrobe (Chic
storage, Swift swap, Choice-item suppression) and Dress to Impress (one-round
projection of the stored items).
"""
from copy import deepcopy
from pathlib import Path
import json
import common_checks as C
import state_grants as G

_data=json.loads((Path(__file__).resolve().parents[1]/'data/fashionista-definitions.json').read_text(encoding='utf8'))
DEFINITIONS=_data['features'];RECIPES=tuple(_data['recipes']);SKILLS=tuple(_data['skills']);RANKS=_data['ranks']
FEATURES={u:tuple(d['span']) for u,d in DEFINITIONS.items()}
CLASS='class/패셔니스타';MAKEOVER='feat/근사한-단장';STYLE='feat/스타일은-영원하다';ACCESSORIZE='feat/액세서리-장식'
PARFUMIER='feat/조향사';WARDROBE='feat/다용도-옷장';DRESS='feat/인상적인-복장'
ENGLISH={d['english']:u for u,d in DEFINITIONS.items()}
CHOICE_ITEMS=tuple(_data['choice_items'])
CHOICES='fashionista_skill_choices'      # trainer.spec: the two printed skills chosen when the class is taken
MAKEOVER_KEY='fashionista_makeover'      # target.spec: the one live Dashing Makeover projection
STYLE_ARMED='fashionista_style_armed'    # pokemon.spec: accepted next Style is Eternal trigger
CHIC='fashionista_chic'                  # pokemon.spec: Versatile Wardrobe state
INCENSE='fashionista_incense'            # physical object: Parfumier Move choice made when crafted
WARDROBE_HOLDER='wardrobe_holder_id'     # physical object: stored (not equipped) in a Chic wardrobe slot
INCENSE_PREFIX='fashionista-incense:'
MAKEOVER_PREFIX='fashionista-makeover:'
DRESS_PREFIX='fashionista-dress:'
INERT_EFFECTS=('trainer_slot','rule','restriction','tag','limit','craft','gm')


def uid(name):
 return name if name in FEATURES else ENGLISH[name]


def clause(feature):
 return DEFINITIONS[feature]['clause_id']


def _text(value,label):
 if type(value) is not str or not value.strip():raise ValueError(label+' required')
 return value


# ---------------------------------------------------------------- acquisition
def records(actor,feature=None,active=False):
 import trainer_feature_acquisition as T
 return [r['static_acquisition'] for _,r,live in T._static_records(actor)
  if r['static_acquisition']['feature_id'] in FEATURES and (feature is None or r['static_acquisition']['feature_id']==feature) and (not active or live)]


def acquired(actor,feature,*,exclude=()):
 if feature in exclude:return None
 rows=records(actor,feature,True)
 if len(rows)>1:raise ValueError('one exact acquired Fashionista Feature required')
 return rows[0] if rows else None


def chosen_skills(actor,*,exclude=()):
 """The two printed skills chosen by the committed class acquisition."""
 row=acquired(actor,CLASS,exclude=exclude)
 return list(row['snapshot']['skills']) if row is not None else []


def _rank(engine,actor,skill):
 import skill_modifiers as S
 return S.rank(engine.r,actor,skill)[2]


def _choices(actor):
 value=actor.spec.get(CHOICES)
 if (type(value) is not list or len(value)!=_data['chosen_skills'] or len(set(value))!=len(value)
   or any(v not in SKILLS for v in value)):
  raise ValueError('explicit Fashionista skill choice required: two distinct printed skills in '+CHOICES)
 return list(value)


def acquisition_snapshot(engine,actor,feature,rank=None):
 d=DEFINITIONS[feature]
 if rank is not None:raise ValueError('this Fashionista Feature is not Ranked')
 if feature==CLASS:
  skills=_choices(actor)
  return {'skills':skills,'ranks':{s:_rank(engine,actor,s) for s in skills},'parents':[]}
 parents=[r['request_id'] for r in records(actor,CLASS,True)]
 skills=chosen_skills(actor)
 snapshot={'parents':parents,'skills':skills,'ranks':{s:_rank(engine,actor,s) for s in skills}}
 if d.get('prerequisites'):
  snapshot['prerequisites']={p:[r['request_id'] for r in records(actor,p,True)] for p in d['prerequisites']}
 return snapshot


def qualification(actor,feature,snapshot,prerequisite_source):
 import acquisition_qualification as Q
 d=DEFINITIONS[feature]
 fields={'skills','ranks','parents'}|({'prerequisites'} if d.get('prerequisites') else set())
 if prerequisite_source is not None or type(snapshot) is not dict or set(snapshot)!=fields:raise ValueError('exact Fashionista acquisition observations required')
 skills=snapshot['skills'];ranks=snapshot['ranks']
 if type(skills) is not list or type(ranks) is not dict or set(ranks)!=set(skills):raise ValueError('Fashionista skill observations must match the chosen skills')
 for value in ranks.values():C.integer(value,'Fashionista skill rank',0)
 checks=[Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required')]
 if feature==CLASS:
  checks.append(Q.check('skills','prerequisite',len(skills)==_data['chosen_skills'] and len(set(skills))==len(skills) and all(s in SKILLS for s in skills),'two distinct printed Fashionista skills required'))
  checks.append(Q.check('novice','prerequisite',all(ranks[s]>=RANKS['novice'] for s in skills),'printed Novice rank required in both chosen Fashionista skills'))
 else:
  known={r['request_id'] for r in records(actor,CLASS)}
  checks.append(Q.check('class','prerequisite',bool(snapshot['parents']) and set(snapshot['parents'])<=known,'actual acquired Fashionista class required'))
  checks.append(Q.check('chosen','prerequisite',skills==chosen_skills(actor),'Fashionista skills must be the committed class choice'))
  for p in d.get('prerequisites',[]):
   owned={r['request_id'] for r in records(actor,p)}
   listed=snapshot['prerequisites'].get(p) if type(snapshot['prerequisites']) is dict else None
   checks.append(Q.check(p,'prerequisite',bool(listed) and set(listed)<=owned,'actual acquired '+DEFINITIONS[p]['english']+' required'))
  requirement=d.get('skill_requirement')
  if requirement:
   count=sum(ranks[s]>=requirement['rank'] for s in skills)
   label={4:'Adept',5:'Expert'}.get(requirement['rank'],str(requirement['rank']))
   checks.append(Q.check('skill_rank','prerequisite',count>=requirement['count'],'printed '+label+' rank in '+str(requirement['count'])+' Fashionista skill(s) required'))
 return Q.require(feature,'native','acquire',checks)


def require(engine,actor,feature=CLASS):
 import world_entities as W
 W.require_actors(engine,actor)
 if actor.kind!='trainer' or acquired(actor,CLASS) is None or (feature!=CLASS and acquired(actor,feature) is None):
  raise ValueError('actual acquired Fashionista Feature required: '+feature)
 return acquired(actor,feature)


def _owned_pokemon(engine,trainer,pokemon):
 import world_entities as W
 W.require_actors(engine,trainer,pokemon)
 if pokemon.kind!='pokemon' or pokemon.spec.get('trainer_id')!=trainer.entity_id:raise ValueError('actual owned Pokemon required')


def trainer_of(engine,actor,feature=CLASS,*,exclude=()):
 import world_entities as W
 if actor.kind=='trainer':return actor if acquired(actor,feature,exclude=exclude) and acquired(actor,CLASS,exclude=exclude) else None
 owner=W.actor_index(engine).get(actor.spec.get('trainer_id'))
 if owner is None or owner.kind!='trainer' or acquired(owner,CLASS,exclude=exclude) is None or acquired(owner,feature,exclude=exclude) is None:return None
 return owner


# ---------------------------------------------------------------- recipes
def recipe_row(recipe_id):
 row=next((r for r in RECIPES if r['id']==recipe_id),None)
 if row is None:raise ValueError('printed Fashionista recipe required: '+str(recipe_id))
 return row


def recipe(engine,trainer,recipe_id,*,seconds):
 """Declaration for crafting_recipes; the Extended duration is an explicit GM fact."""
 row=recipe_row(recipe_id);C.integer(seconds,'actual Extended crafting seconds',1)
 declaration={k:deepcopy(v) for k,v in row.items() if k in ('id','source','output','requirements','materials')}
 declaration['seconds']=seconds
 import crafting_recipes as RECIPES_CORE
 return RECIPES_CORE.declaration(declaration)


def qualifies(engine,trainer,recipe_id):
 """Printed requirements, chosen Fashionista skill and a selected output rule; never a payment."""
 import crafting_recipes as RECIPES_CORE
 row=recipe_row(recipe_id)
 if acquired(trainer,CLASS) is None:return False
 skill=row.get('fashionista_skill')
 if skill is not None and skill not in chosen_skills(trainer):return False
 try:
  for requirement in row['requirements']:
   if not RECIPES_CORE._observe(engine,trainer,requirement['condition'],set()):return False
  RECIPES_CORE._selected(engine,row['output']['item_id'])
  if engine.r.item_effects(row['output']['key'])[1].get('id')!=row['output']['item_id']:return False
 except (ValueError,KeyError):
  return False   # excluded/unselected output variants are not craftable in this ruleset
 return True


def craftable(engine,trainer):
 import world_entities as W
 W.require_actors(engine,trainer)
 return [row['id'] for row in RECIPES if qualifies(engine,trainer,row['id'])]


def craft(engine,trainer,recipe_id,*,seconds,reason,count=1,inputs=None,product_policy=None,event_id=None,incense_move=None):
 """Craft one printed Fashionista recipe through the shared crafting owners.

 Parfumier: when the maker owns Parfumier and the recipe is an Incense Held Item,
 the printed Sweet Scent / Aromatic Mist choice binds to each actual crafted instance.
 """
 require(engine,trainer);row=recipe_row(recipe_id);_text(reason,'crafting reason')
 if not qualifies(engine,trainer,recipe_id):raise ValueError('Fashionista recipe requirements are not met: '+recipe_id)
 declaration=recipe(engine,trainer,recipe_id,seconds=seconds)
 parfumier=acquired(trainer,PARFUMIER) if row.get('incense') else None
 mid=None
 if parfumier is not None:
  mid=engine.r.move_id(incense_move) if isinstance(incense_move,str) else None
  if mid not in DEFINITIONS[PARFUMIER]['moves']:raise ValueError('Parfumier chooses Sweet Scent or Aromatic Mist when crafting an Incense')
  if product_policy is None:raise ValueError('Parfumier choice binds to actual crafted Incense instances; declare the physical product')
 elif incense_move is not None:raise ValueError('only a Parfumier crafting an Incense chooses a Move')
 def apply(e,t):
  import crafting_recipes as RECIPES_CORE
  result=RECIPES_CORE.craft(e,t,declaration,count=count,inputs=inputs,reason=reason,product_policy=product_policy,event_id=event_id)
  if mid is not None:
   for identity in result['product_instance_ids']:
    obj=e._physical_objects[identity]
    choice={'move_id':mid,'maker_id':t.entity_id,'acquisition':parfumier['request_id'],'clause_id':clause(PARFUMIER),'production_id':result['production_id'],'at':e.elapsed_seconds}
    if obj.get(INCENSE) not in (None,choice):raise ValueError('crafted Incense already carries another Parfumier choice')
    obj[INCENSE]=choice
   e.log('  '+t.name+': 조향사 향로 기술 선택 '+mid,PARFUMIER)
  return result
 return G.transition(engine,trainer,apply)


# ---------------------------------------------------------------- Parfumier
def incense_choice(obj):
 choice=obj.get(INCENSE) if isinstance(obj,dict) else None
 if choice is None:return None
 if type(choice) is not dict or set(choice)!={'move_id','maker_id','acquisition','clause_id','production_id','at'} or choice['move_id'] not in DEFINITIONS[PARFUMIER]['moves'] or choice['clause_id']!=clause(PARFUMIER):
  raise ValueError('invalid Parfumier Incense choice')
 origin=obj.get('crafting_origin')
 if type(origin) is not dict or origin.get('maker_id')!=choice['maker_id'] or origin.get('production_id')!=choice['production_id']:raise ValueError('Parfumier choice lost its crafting provenance')
 return choice


def incense_expected(engine,pokemon,*,exclude=()):
 """(maker, move_id, instance_id) while the active held Incense carries its own Trainer's Parfumier choice."""
 import held_equipment as HELD,world_entities as W
 if pokemon.kind!='pokemon':return None
 registrations=getattr(pokemon,'_item_reg',{})
 for row in HELD.entries(pokemon):
  identity=row.get('instance_id');key=row.get('registration_key')
  if identity is None or key is None or key not in registrations:continue
  choice=incense_choice(getattr(engine,'_physical_objects',{}).get(identity))
  if choice is None:continue
  maker=W.actor_index(engine).get(choice['maker_id'])
  if maker is None or pokemon.spec.get('trainer_id')!=maker.entity_id or trainer_of(engine,maker,PARFUMIER,exclude=exclude) is None:continue
  if any(r['request_id']==choice['acquisition'] for r in records(maker,PARFUMIER)) is False:continue
  return maker,choice['move_id'],identity
 return None


def _incense_sources(actor):
 return {sid:row for sid,row in actor.spec.get(G.KEY,{}).get('sources',{}).items() if sid.startswith(INCENSE_PREFIX)}


def reconcile_incense(engine,pokemon,*,exclude=()):
 """Grant or revoke the chosen Incense Move for one Pokemon's actual active held slot."""
 if pokemon.kind!='pokemon':return None
 expected=incense_expected(engine,pokemon,exclude=exclude);current=_incense_sources(pokemon)
 if expected is None:
  for sid in list(current):G.revoke(pokemon,sid,engine=engine)
  return None
 maker,mid,identity=expected;sid=INCENSE_PREFIX+pokemon.entity_id+':'+identity
 for other in list(current):
  if other!=sid:G.revoke(pokemon,other,engine=engine)
 row=current.get(sid)
 if row is not None and (row.get('grants',{}).get('moves')!=[mid] or row.get('owner_id')!=maker.entity_id or row.get('rule_id')!=PARFUMIER):
  G.revoke(pokemon,sid,engine=engine);row=None
 if row is None:
  G.grant_moves(pokemon,[mid],sid,'item',owner_id=maker.entity_id,lifetime='equipped',rule_id=PARFUMIER,tutor_points=0,mode='learned')
  G.state(pokemon)['sources'][sid].update(fashionista_incense={'instance_id':identity,'clause_id':clause(PARFUMIER)})
  engine.log('  '+pokemon.name+': 향로 활성 — 기술 목록에 '+mid+' 추가',PARFUMIER)
 return sid


def reconcile_owned_incense(engine,trainer,*,exclude=()):
 import world_entities as W
 for c in W.actor_index(engine).values():
  if c.kind=='pokemon' and c.spec.get('trainer_id')==trainer.entity_id:reconcile_incense(engine,c,exclude=exclude)


# ---------------------------------------------------------------- item helpers
def effect_semantics(engine,item_id):
 """Normalized printed effects of one selected item rule, without slot/rule rows."""
 import items as I
 effects,header=engine.r.item_effects(item_id)
 if effects is None or header.get('id')!=item_id:raise ValueError('selected item rule required: '+str(item_id))
 rows=set()
 for effect in effects:
  if not isinstance(effect,dict) or effect.get('type') in INERT_EFFECTS:continue
  rows.add(json.dumps(I.normalize(effect),ensure_ascii=False,sort_keys=True))
 return rows


def shares_effects(engine,first,second):
 return bool(effect_semantics(engine,first)&effect_semantics(engine,second))


def _accessory_registrations(actor):
 return [(key,row) for key,row in getattr(actor,'_item_reg',{}).items() if '장신구' in row.get('slots',[]) and not row.get('projection')]


def accessory_slot(engine,actor,item_id,effects,options,occupied,registrations):
 """Accessorize: admit the second accessory slot item when the pair is printed-legal."""
 if actor.kind!='trainer' or ['장신구'] not in options or '장신구' not in occupied:return None
 if trainer_of(engine,actor,ACCESSORIZE) is None:return None
 worn=_accessory_registrations(actor)
 if len(worn)!=1:return None
 other=worn[0][1]
 if other.get('item_id')==item_id:
  engine.log('  '+actor.name+': 액세서리 장식 — 같은 타입의 장신구 두 개는 불가 ('+item_id+')',ACCESSORIZE);return None
 if shares_effects(engine,other['item_id'],item_id):
  engine.log('  '+actor.name+': 액세서리 장식 — 효과를 공유하는 장신구 쌍은 불가 ('+other['item_id']+', '+item_id+')',ACCESSORIZE);return None
 engine.log('  '+actor.name+': 액세서리 장식 — 두 번째 장신구 슬롯 사용 '+item_id,ACCESSORIZE)
 return ['장신구']


def validate_projection(projection):
 if type(projection) is not dict or set(projection)!={'source_id','registration_key','owner_id','rule_id','lifetime','clause_id'}:
  raise ValueError('exact Fashionista item projection required')
 for key,value in projection.items():_text(value,'projection '+key)
 if projection['rule_id'] not in (MAKEOVER,DRESS) or not projection['source_id'].startswith((MAKEOVER_PREFIX,DRESS_PREFIX)):raise ValueError('unknown item projection source')
 return projection


def _can_equip(engine,target,item_id):
 import items as I
 effects,header=engine.r.item_effects(item_id)
 if effects is None:raise ValueError('selected item rule required: '+str(item_id))
 if target.kind=='trainer':
  if '포켓몬 전용' in str(header.get('desc','')) or any(isinstance(e,dict) and e.get('type')=='restriction' and e.get('only')=='pokemon' for e in effects):return False
  return bool(I.item_slot_options(header,effects)) or (header.get('use')=='equipment' and bool(header.get('slot')))
 return header.get('use')=='held' or header.get('category')=='포켓몬 도구'


# ---------------------------------------------------------------- Dashing Makeover
def makeover_record(actor):
 row=actor.spec.get(MAKEOVER_KEY)
 if row is None:return None
 if type(row) is not dict or set(row)!={'source_id','registration_key','owner_id','item_id','recipe_id','acquisition','clause_id','ap','at','effects','reason'} or row['clause_id']!=clause(MAKEOVER) or row['ap']!=DEFINITIONS[MAKEOVER]['ap']:
  raise ValueError('invalid Dashing Makeover record')
 return row


def makeover(engine,trainer,target,item_id,*,recipe_id,seconds,reason):
 """2 AP bound Extended action: the target gains the chosen craftable item's effects without a slot."""
 import action_points as AP,world_entities as W,pokemon_activities as P
 require(engine,trainer,MAKEOVER);W.require_actors(engine,target);_text(reason,'Dashing Makeover reason')
 d=DEFINITIONS[MAKEOVER]
 if target.kind not in d['targets']:raise ValueError('Dashing Makeover targets one Trainer or Pokemon')
 row=recipe_row(recipe_id)
 if row['output']['item_id']!=item_id or not qualifies(engine,trainer,recipe_id):raise ValueError('Dashing Makeover projects only an Equipment or Held Item you can currently craft')
 C.integer(seconds,'actual Extended Dashing Makeover seconds',1)
 if makeover_record(target) is not None:raise ValueError('a target may be under the effect of only one Dashing Makeover at a time')
 if not _can_equip(engine,target,item_id):raise ValueError('the target could not normally equip that item')
 if any(r.get('item_id')==item_id for r in getattr(target,'_item_reg',{}).values()):raise ValueError('the target already benefits from that item')
 P._outside(engine)
 if AP.available(trainer)<d['ap']:raise ValueError('Dashing Makeover requires two available AP')
 sid=MAKEOVER_PREFIX+trainer.entity_id+':'+target.entity_id
 if sid in trainer.spec.get('ap_bound',{}) if isinstance(trainer.spec.get('ap_bound'),dict) else False:raise ValueError('Dashing Makeover AP binding identity already reserved')
 def apply(e,t,*ps):
  import turn as TURN,activity_jobs as JOBS,items as I
  q=ps[0] if ps else t
  if not TURN.spend(e,t,d['action'],MAKEOVER):raise ValueError('Dashing Makeover Extended action unavailable')
  JOBS.run_fixed(e,t,tuple(ps),seconds=seconds,source=MAKEOVER,context={'target_id':q.entity_id,'item_id':item_id,'recipe_id':recipe_id,'reason':reason})
  AP.charge(t,d['ap'],mode='bind',instance_id=sid)
  key='makeover:'+t.entity_id
  projection={'source_id':sid,'registration_key':key,'owner_id':t.entity_id,'rule_id':MAKEOVER,'lifetime':'bound_ap','clause_id':clause(MAKEOVER)}
  n=I.register_item(e,q,item_id,projection=projection)
  if key not in getattr(q,'_item_reg',{}):raise ValueError('Dashing Makeover projection was refused by the item owner')
  q.spec[MAKEOVER_KEY]={'source_id':sid,'registration_key':key,'owner_id':t.entity_id,'item_id':item_id,'recipe_id':recipe_id,
   'acquisition':acquired(t,MAKEOVER)['request_id'],'clause_id':clause(MAKEOVER),'ap':d['ap'],'at':e.elapsed_seconds,'effects':n,'reason':reason}
  e.log('  '+t.name+': 근사한 단장 → '+q.name+' '+item_id+' (효과 '+str(n)+'개, 2 AP 지속)',MAKEOVER)
  return deepcopy(q.spec[MAKEOVER_KEY])
 return G.transition(engine,trainer,apply,participants=(target,) if target is not trainer else ())


def _release_makeover(e,t,q,record,*,cause):
 import items as I,action_points as AP
 if record['registration_key'] in getattr(q,'_item_reg',{}):I.unregister_item(e,q,registration_key=record['registration_key'])
 AP.release_binding(t,record['source_id'],expected_amount=record['ap'])
 q.spec.pop(MAKEOVER_KEY)
 t.spec.setdefault('fashionista_makeover_history',[]).append(dict(deepcopy(record),target_id=q.entity_id,ended_at=e.elapsed_seconds,cause=cause))
 e.log('  '+t.name+': 근사한 단장 종료 ('+cause+') '+q.name,MAKEOVER)


def end_makeover(engine,trainer,target,*,event_id):
 """ch06 bound AP without a printed ending: the owner ends it as an own-turn Free Action."""
 import world_entities as W,action_lifecycle as A,turn as TURN
 W.require_actors(engine,trainer,target);_text(event_id,'Dashing Makeover ending event')
 record=makeover_record(target)
 if record is None or record['owner_id']!=trainer.entity_id:raise ValueError('actual live Dashing Makeover by this Trainer required')
 if any(row.get('event_id')==event_id for row in trainer.spec.get('fashionista_makeover_history',[])):raise ValueError('Dashing Makeover ending event already used')
 if engine.encounter_active and engine._active_turn_actor is not trainer:raise ValueError('bound AP release is an own-turn Free Action')
 def apply(e,t,*ps):
  q=ps[0] if ps else t
  if e.encounter_active:
   if not TURN.spend(e,t,'free',MAKEOVER):raise ValueError('Free action unavailable')
  else:
   if not TURN.can_act(e,t) or not A.ordinary_permission(e,t) or not A.status_permission(e,t,'free'):raise ValueError('Free action unavailable')
   A.record_action(e,t,'free')
  live=makeover_record(q)
  _release_makeover(e,t,q,live,cause='released:'+event_id)
  t.spec['fashionista_makeover_history'][-1]['event_id']=event_id
  return deepcopy(t.spec['fashionista_makeover_history'][-1])
 return G.transition(engine,trainer,apply,participants=(target,) if target is not trainer else ())


# ---------------------------------------------------------------- Style is Eternal
def armed(pokemon):
 row=pokemon.spec.get(STYLE_ARMED)
 if row is None:return None
 if type(row) is not dict or set(row)!={'trainer_id','acquisition','clause_id','armed_at'} or row['clause_id']!=clause(STYLE):raise ValueError('invalid Style is Eternal arming receipt')
 return row


def arm_style(engine,trainer,pokemon):
 """Accept the next eligible Style is Eternal trigger for one owned Pokemon; spends nothing yet."""
 require(engine,trainer,STYLE);_owned_pokemon(engine,trainer,pokemon)
 def apply(e,t,q):
  q.spec[STYLE_ARMED]={'trainer_id':t.entity_id,'acquisition':acquired(t,STYLE)['request_id'],'clause_id':clause(STYLE),'armed_at':e.elapsed_seconds}
  return deepcopy(q.spec[STYLE_ARMED])
 return G.transition(engine,trainer,apply,participants=(pokemon,))


def disarm_style(engine,trainer,pokemon):
 import world_entities as W
 W.require_actors(engine,trainer,pokemon)
 row=armed(pokemon)
 if row is None or row['trainer_id']!=trainer.entity_id:raise ValueError('actual armed Style is Eternal by this Trainer required')
 def apply(e,t,q):
  q.spec.pop(STYLE_ARMED);return True
 return G.transition(engine,trainer,apply,participants=(pokemon,))


def _style_key(pokemon):
 return STYLE+':'+pokemon.entity_id


def style_ready(engine,pokemon):
 """The armed Trainer when the printed trigger could be answered now (read-only)."""
 import world_entities as W,action_points as AP,frequency as F,turn as TURN,action_lifecycle as A
 if pokemon.kind!='pokemon':return None
 row=armed(pokemon)
 if row is None:return None
 trainer=W.actor_index(engine).get(row['trainer_id'])
 if trainer is None or trainer.kind!='trainer' or pokemon.spec.get('trainer_id')!=trainer.entity_id:return None
 if trainer_of(engine,pokemon,STYLE) is not trainer or not any(r['request_id']==row['acquisition'] for r in records(trainer,STYLE)):return None
 if AP.available(trainer)<DEFINITIONS[STYLE]['ap']:return None
 if not F.activation_allowed(trainer,_style_key(pokemon),{'kind':'scene','uses':1}):return None
 if not TURN.can_act(engine,trainer) or not A.status_permission(engine,trainer,'free',new_action=True):return None
 return trainer


def protection(engine,holder,row,operation):
 """equipment_protection: an armed Style is Eternal retains the Pokemon's held item.

 Printed trigger operations: theft/transfer, exchange (Trick family), Disarm and an
 enemy drop effect (Knock Off, queried as effect_drop). A voluntary drop by the
 holder is not a removal effect and never consumes the Feature.
 """
 if operation not in DEFINITIONS[STYLE]['operations'] or not row.get('held'):return None
 trainer=style_ready(engine,holder)
 if trainer is None:return None
 return {'status':'blocked','source':STYLE,'holder_id':holder.entity_id,'trainer_id':trainer.entity_id,'equipment':row['key']}


def keep(engine,holder,status,*,operation,source):
 """The actual trigger: pay 1 AP and the triggered Free Action once per Scene per Pokemon."""
 import world_entities as W,action_points as AP,frequency as F,action_lifecycle as A
 if type(status) is not dict or status.get('source')!=STYLE or status.get('holder_id')!=holder.entity_id:raise ValueError('Style is Eternal status required')
 trainer=W.actor_index(engine).get(status.get('trainer_id'))
 if style_ready(engine,holder) is not trainer or trainer is None:raise ValueError('Style is Eternal is no longer available for this Pokemon')
 def apply(e,t,q):
  key=_style_key(q);declaration={'kind':'scene','uses':1}
  if not F.activation_allowed(t,key,declaration,engine=e):raise ValueError('Style is Eternal was already used for this Pokemon this Scene')
  A.triggered_free_action(e,t,STYLE)
  AP.spend(t,DEFINITIONS[STYLE]['ap'])
  F.consume_activation(t,key,declaration,engine=e)
  q.spec.pop(STYLE_ARMED,None)
  receipt={'pokemon_id':q.entity_id,'operation':operation,'source':source,'equipment':status.get('equipment'),'round':e.round_no,'at':e.elapsed_seconds,
   'acquisition':acquired(t,STYLE)['request_id'],'clause_id':clause(STYLE)}
  t.spec.setdefault('fashionista_style_history',[]).append(receipt)
  e.log('  '+t.name+': 스타일은 영원하다 — '+q.name+'의 지니는 도구 유지 ('+str(source)+')',STYLE)
  return deepcopy(receipt)
 return G.transition(engine,trainer,apply,participants=(holder,))


# ---------------------------------------------------------------- Versatile Wardrobe
def chic(pokemon):
 row=pokemon.spec.get(CHIC)
 if row is None:return None
 if (type(row) is not dict or set(row)!={'version','owner_id','acquisition','clause_id','at','point_cost','reason','slots','suppression','swaps'}
   or row['version']!=1 or row['clause_id']!=clause(WARDROBE) or set(row['slots'])!=set(DEFINITIONS[WARDROBE]['wardrobe_slots'])):
  raise ValueError('invalid Chic state')
 return row


def make_chic(engine,trainer,pokemon,*,seconds,reason):
 """At-Will Extended action: the owned Pokemon loses two Tutor Points and becomes Chic."""
 import pokemon_activities as P,pokemon_teaching as TEACH
 require(engine,trainer,WARDROBE);_owned_pokemon(engine,trainer,pokemon);P._trainer(trainer);P._pokemon(pokemon)
 d=DEFINITIONS[WARDROBE];C.integer(seconds,'actual Extended Versatile Wardrobe seconds',1);_text(reason,'Versatile Wardrobe reason')
 if chic(pokemon) is not None:raise ValueError('the Pokemon is already Chic')
 if TEACH._balance(pokemon.spec)<d['tutor_points']:raise ValueError('target needs two actual Tutor Points')
 P._outside(engine)
 def apply(e,t,q):
  import turn as TURN,activity_jobs as JOBS,trainer_retraining as RETRAINING
  if not TURN.spend(e,t,d['action'],WARDROBE):raise ValueError('Versatile Wardrobe Extended action unavailable')
  JOBS.run_fixed(e,t,(q,),seconds=seconds,source=WARDROBE,context={'pokemon_id':q.entity_id,'reason':reason})
  TEACH._debit_points(q.spec,d['tutor_points'])
  q.spec[CHIC]={'version':1,'owner_id':t.entity_id,'acquisition':acquired(t,WARDROBE)['request_id'],'clause_id':clause(WARDROBE),'at':e.elapsed_seconds,
   'point_cost':d['tutor_points'],'reason':reason,'slots':{slot:None for slot in d['wardrobe_slots']},'suppression':None,'swaps':[]}
  RETRAINING.irreversible(e,t,WARDROBE,event_id='versatile-wardrobe:'+t.entity_id+':'+q.entity_id+':'+str(e.elapsed_seconds),reason='completed permanent Chic transformation: '+q.entity_id)
  e.log('  '+t.name+': 다용도 옷장 → '+q.name+' 시크 (가르침 포인트 -2)',WARDROBE)
  return deepcopy(q.spec[CHIC])
 return G.transition(engine,trainer,apply,participants=(pokemon,))


def _require_chic(engine,pokemon):
 import world_entities as W
 W.require_actors(engine,pokemon)
 row=chic(pokemon)
 if pokemon.kind!='pokemon' or row is None:raise ValueError('actual Chic Pokemon required')
 return row


def _slot(row,slot_id):
 if slot_id not in row['slots']:raise ValueError('printed Chic wardrobe slot required')
 return row['slots'][slot_id]


def wardrobe_items(engine,pokemon):
 """Item rule identities currently in the active held slot and the wardrobe slots."""
 import held_equipment as HELD
 found=[]
 for entry in HELD.entries(pokemon):
  if entry.get('weapon_key'):continue
  found.append(entry.get('item_id') or engine.r.item_effects(entry['name'])[1].get('id'))
 row=chic(pokemon)
 if row is not None:
  found.extend(stored['item_id'] for stored in row['slots'].values() if stored is not None)
 return found


def _wardrobe_constraints(engine,pokemon,item_ids):
 """Chic Pokemon never hold several items of one type or repeated effects."""
 seen=[]
 for item_id in item_ids:
  for other in seen:
   if other==item_id:raise ValueError('a Chic Pokemon may not have multiple items of the same type: '+item_id)
   if shares_effects(engine,other,item_id):raise ValueError('a Chic Pokemon may not have items with repeated effects: '+other+', '+item_id)
  seen.append(item_id)
 return True


def wardrobe_holds(engine,pokemon,instance_id):
 row=chic(pokemon) if pokemon.kind=='pokemon' else None
 if row is None or instance_id is None:return False
 obj=getattr(engine,'_physical_objects',{}).get(instance_id)
 return (any(stored is not None and stored['instance_id']==instance_id for stored in row['slots'].values())
   and isinstance(obj,dict) and obj.get(WARDROBE_HOLDER)==pokemon.entity_id)


def _stored_entry(engine,obj,slot_id,reason,at):
 name=getattr(engine.r,'items_mech',{}).get(obj['item_rule_id'],{}).get('name') or obj['item_rule_id']
 return {'instance_id':None,'item_id':obj['item_rule_id'],'name':name,'slot_id':slot_id,'stored_at':at,'reason':reason}


def store(engine,pokemon,instance_id,slot_id,*,reason):
 """Outside combat: place one actually possessed held item into an empty wardrobe slot (no effect, not equipped).

 The active held item may be stored too; the Choice-item suppression never starts from storage.
 """
 import world_entities as W,pokemon_activities as P,held_equipment as HELD
 row=_require_chic(engine,pokemon);_text(reason,'wardrobe storage reason');P._outside(engine)
 if _slot(row,slot_id) is not None:raise ValueError('that wardrobe slot is occupied')
 W.entity_identity(engine,instance_id,kind='item_instance')
 obj=engine._physical_objects[instance_id];W.require_physical_access(obj)
 if obj.get(WARDROBE_HOLDER) is not None:raise ValueError('item is already stored in a wardrobe')
 active=next((entry for entry in HELD.entries(pokemon) if entry.get('instance_id')==instance_id),None)
 if obj.get('equipped_by') not in (None,pokemon.entity_id) or (obj.get('equipped_by')==pokemon.entity_id and active is None):raise ValueError('item is equipped by another actor')
 if obj.get('carrier_id') not in (None,pokemon.entity_id) or pokemon.entity_id not in (obj.get('owner_id'),obj.get('carrier_id'),obj.get('equipped_by')):
  raise ValueError('the Chic Pokemon must actually possess the stored item')
 header=engine.r.item_effects(obj['item_rule_id'])[1]
 if header.get('use')!='held' and header.get('category')!='포켓몬 도구':raise ValueError('wardrobe slots carry Held Items only')
 others=[x for x in wardrobe_items(engine,pokemon)]
 if active is not None:others.remove(obj['item_rule_id'])
 _wardrobe_constraints(engine,pokemon,[*others,obj['item_rule_id']])
 def apply(e,q):
  import items as I
  o=e._physical_objects[instance_id]
  if active is not None:I.unregister_item(e,q,registration_key=active['registration_key'],wardrobe=True)
  o.pop('equipped_by',None);o[WARDROBE_HOLDER]=q.entity_id;o['wardrobe_slot']=slot_id;W._set_object_location(o,{'kind':'unknown'})
  entry=_stored_entry(e,o,slot_id,reason,e.elapsed_seconds);entry['instance_id']=instance_id
  q.spec[CHIC]['slots'][slot_id]=entry
  e.log('  '+q.name+': 옷장 보관 '+slot_id+' ← '+o['item_rule_id'],WARDROBE)
  return deepcopy(entry)
 return G.transition(engine,pokemon,apply)


def release(engine,pokemon,slot_id,*,reason):
 """Outside combat: take one stored item out of the wardrobe (possession unchanged, still not equipped)."""
 import pokemon_activities as P
 row=_require_chic(engine,pokemon);_text(reason,'wardrobe release reason');P._outside(engine)
 stored=_slot(row,slot_id)
 if stored is None:raise ValueError('that wardrobe slot is empty')
 def apply(e,q):
  o=e._physical_objects[stored['instance_id']];o.pop(WARDROBE_HOLDER,None);o.pop('wardrobe_slot',None)
  q.spec[CHIC]['slots'][slot_id]=None
  return {'released':stored['instance_id'],'slot_id':slot_id}
 return G.transition(engine,pokemon,apply)


def _suppress(e,q,stored):
 """Printed note: swapping a Choice item into the active slot suppresses the Chic Pokemon for the rest of combat."""
 st=q.spec[CHIC]
 if st['suppression'] is not None or e.immune_to(q,'억압'):return False
 st['suppression']={'item_id':stored['item_id'],'instance_id':stored['instance_id'],'round':e.round_no,'at':e.elapsed_seconds,'source':WARDROBE,'clause_id':clause(WARDROBE)}
 q.conditions.add('억압')
 e.log('  '+q.name+': 선택 도구 전환 → 전투 종료까지 억압',WARDROBE)
 return True


def swap(engine,pokemon,slot_id):
 """Swift action on the Chic Pokemon's own turn: exchange the active held item with one wardrobe slot."""
 import held_equipment as HELD
 row=_require_chic(engine,pokemon)
 stored=_slot(row,slot_id)
 if not engine.encounter_active or engine._active_turn_actor is not pokemon:raise ValueError('the wardrobe swap is a Swift action on the Chic Pokemon own turn')
 held=[entry for entry in HELD.entries(pokemon)]
 if len(held)>1:raise ValueError('two actual held items require an explicit held-slot policy before a wardrobe swap')
 active=held[0] if held else None
 if stored is None and active is None:raise ValueError('nothing to swap')
 if active is not None and (active.get('instance_id') is None or active.get('weapon_key') or active.get('registration_key') is None):
  raise ValueError('the active held item must be an actual registered physical instance')
 choice_item=stored is not None and stored['item_id'] in CHOICE_ITEMS
 def apply(e,q):
  import turn as TURN,items as I
  if not TURN.spend(e,q,DEFINITIONS[WARDROBE]['swap_action'],WARDROBE):raise ValueError('wardrobe swap Swift action unavailable')
  st=q.spec[CHIC];out=None
  if active is not None:
   I.unregister_item(e,q,registration_key=active['registration_key'],wardrobe=True)
   o=e._physical_objects[active['instance_id']];o.pop('equipped_by',None);o[WARDROBE_HOLDER]=q.entity_id;o['wardrobe_slot']=slot_id
   import world_entities as W
   W._set_object_location(o,{'kind':'unknown'})
   out=_stored_entry(e,o,slot_id,'swapped out of the active held slot',e.elapsed_seconds);out['instance_id']=active['instance_id']
  st['slots'][slot_id]=out
  if stored is not None:
   o=e._physical_objects[stored['instance_id']];o.pop(WARDROBE_HOLDER,None);o.pop('wardrobe_slot',None)
   resolved={'can receive 억압':not e.immune_to(q,'억압')} if choice_item else None
   I.register_item(e,q,stored['item_id'],source_instance_id=stored['instance_id'],as_held=True,resolved_conditions=resolved)
   if not any(x.get('instance_id')==stored['instance_id'] for x in HELD.entries(q)):raise ValueError('swapped item did not acquire the actual held slot')
   if choice_item:_suppress(e,q,stored)
  st['swaps'].append({'slot_id':slot_id,'in':stored['instance_id'] if stored else None,'out':out['instance_id'] if out else None,'round':e.round_no,'at':e.elapsed_seconds})
  e.log('  '+q.name+': 옷장 교환 '+slot_id+' (활성 ← '+str(stored['item_id'] if stored else None)+', 보관 ← '+str(out['item_id'] if out else None)+')',WARDROBE)
  return deepcopy(st['swaps'][-1])
 return G.transition(engine,pokemon,apply)


def encounter_suppressed(actor):
 row=actor.spec.get(CHIC) if getattr(actor,'kind',None)=='pokemon' else None
 return bool(isinstance(row,dict) and row.get('suppression'))


def retain_condition(engine,actor,condition):
 return condition=='억압' and engine.encounter_active and encounter_suppressed(actor)


def move_allowed(engine,actor,move):
 import frequency as F
 if encounter_suppressed(actor) and F.move_frequency(engine,move['id'],actor)[0]!='at_will':
  return False,'시크 선택 도구 억압: 전투 종료까지 임의 빈도 기술만 사용 가능'
 return True,''


def end_encounter(engine,actors):
 for actor in actors:
  row=actor.spec.get(CHIC)
  if isinstance(row,dict) and row.get('suppression'):
   import condition_instances as CONDITIONS
   row['suppression']=None
   if not CONDITIONS.records(actor,'억압'):actor.conditions.discard('억압')
   engine.log('  '+actor.name+': 시크 선택 도구 억압 종료 (전투 종료)',WARDROBE)


# ---------------------------------------------------------------- Dress to Impress
def dress_record(pokemon):
 import combat_timing as T
 return next((r for r in T.records(pokemon) if r.get('source')==DRESS),None)


def dress_to_impress(engine,trainer,pokemon,*,communication=None):
 """Scene x2 Standard action: the own Chic Pokemon gains every stored item's effects for one round, once per Scene per Pokemon."""
 import action_lifecycle as A
 require(engine,trainer,DRESS);_owned_pokemon(engine,trainer,pokemon)
 row=chic(pokemon)
 if row is None:raise ValueError('Dress to Impress targets your actual Chic Pokemon')
 stored=[entry for entry in row['slots'].values() if entry is not None]
 if not stored:raise ValueError('the Chic Pokemon has no stored wardrobe items')
 if not engine.encounter_active:raise ValueError('Dress to Impress requires an active encounter')
 if dress_record(pokemon) is not None:raise ValueError('Dress to Impress is already active for this Pokemon')
 d=DEFINITIONS[DRESS]
 import cheerleader as CHEER
 @CHEER.order_activation(DRESS)
 def apply(e,t,q):
  import frequency as F,turn as TURN,combat_timing as T,items as I
  if not F.activation_allowed(t,DRESS,d['frequency'],engine=e):raise ValueError('Dress to Impress Scene frequency exhausted')
  if not F.activation_allowed(t,DRESS+':'+q.entity_id,d['per_pokemon'],engine=e):raise ValueError('Dress to Impress may target a Pokemon only once per Scene')
  count=T.current(e)
  import order_actions as ORDERS
  delivery=ORDERS.delivery(e,t,q,DRESS,communication=communication)
  ORDERS.spend(e,t,DRESS,action=d['action'],subject=q.entity_id,communication=delivery)
  F.consume_activation(t,DRESS,d['frequency'],engine=e);F.consume_activation(t,DRESS+':'+q.entity_id,d['per_pokemon'],engine=e)
  keys=[];installed=[]
  for entry in stored:
   if any(r.get('item_id')==entry['item_id'] and not r.get('projection') for r in getattr(q,'_item_reg',{}).values()):
    raise ValueError('the Chic Pokemon already benefits from that item: '+entry['item_id'])
   sid=DRESS_PREFIX+q.entity_id+':'+entry['instance_id'];key='dress:'+entry['slot_id']
   projection={'source_id':sid,'registration_key':key,'owner_id':t.entity_id,'rule_id':DRESS,'lifetime':'round','clause_id':clause(DRESS)}
   # A projected Choice item never enters the active slot, so the printed suppression (and its conditional stage boost) does not start here.
   resolved={'can receive 억압':False} if entry['item_id'] in CHOICE_ITEMS else None
   n=I.register_item(e,q,entry['item_id'],projection=projection,resolved_conditions=resolved)
   if key not in getattr(q,'_item_reg',{}):raise ValueError('Dress to Impress projection was refused by the item owner: '+entry['item_id'])
   keys.append(key);installed.append({'slot_id':entry['slot_id'],'instance_id':entry['instance_id'],'item_id':entry['item_id'],'effects':n})
  record={'source':DRESS,'count_deadline':(e.round_no+1,count),'encounter_end':True,
   'fashionista_dress':{'owner_id':t.entity_id,'acquisition':acquired(t,DRESS)['request_id'],'clause_id':clause(DRESS),'registration_keys':keys,'items':installed,'round':e.round_no,'count':count}}
  T.install(e,q,record)
  e.log('  '+t.name+': 인상적인 복장 → '+q.name+' 보관 도구 '+str(len(installed))+'개 한 라운드 활성',DRESS)
  return deepcopy(record['fashionista_dress'])
 return G.transition(engine,trainer,apply,participants=(pokemon,),include_rulings=True)


def dress_expired(engine,pokemon,record):
 """combat_timing: the one-round projections end with their record."""
 import items as I
 facts=record.get('fashionista_dress')
 for key in facts.get('registration_keys',[]) if isinstance(facts,dict) else []:
  if key in getattr(pokemon,'_item_reg',{}):I.unregister_item(engine,pokemon,registration_key=key)


# ---------------------------------------------------------------- lifecycle hooks
def after_acquire(engine,trainer):
 reconcile_owned_incense(engine,trainer)


def withdraw(engine,trainer,rule_id):
 """Retraining a Fashionista source ends what it alone justified, for every affected actor."""
 if rule_id not in FEATURES:return
 import world_entities as W,items as I
 exclude=(rule_id,)
 index=W.actor_index(engine)
 if rule_id in (CLASS,MAKEOVER):
  for c in index.values():
   record=makeover_record(c)
   if record is not None and record['owner_id']==trainer.entity_id:_release_makeover(engine,trainer,c,record,cause='retrained:'+rule_id)
 if rule_id in (CLASS,STYLE):
  for c in index.values():
   if c.kind=='pokemon' and armed(c) is not None and armed(c)['trainer_id']==trainer.entity_id:c.spec.pop(STYLE_ARMED)
 if rule_id in (CLASS,ACCESSORIZE):
  worn=_accessory_registrations(trainer)
  if len(worn)>1:
   for key,_ in worn[1:]:I.unregister_item(engine,trainer,registration_key=key)
 if rule_id in (CLASS,PARFUMIER):reconcile_owned_incense(engine,trainer,exclude=exclude)


# ---------------------------------------------------------------- validation
def validate(engine):
 import world_entities as W,combat_timing as T,action_points as AP,held_equipment as HELD
 index=W.actor_index(engine);objects=getattr(engine,'_physical_objects',{})
 for actor in index.values():
  record=makeover_record(actor)
  if record is not None:
   owner=index.get(record['owner_id'])
   if owner is None or owner.kind!='trainer' or acquired(owner,MAKEOVER) is None:raise ValueError('Dashing Makeover lost its Fashionista owner')
   if not any(r['request_id']==record['acquisition'] for r in records(owner,MAKEOVER)):raise ValueError('Dashing Makeover acquisition provenance changed')
   registration=getattr(actor,'_item_reg',{}).get(record['registration_key'])
   if registration is None or registration.get('item_id')!=record['item_id'] or registration.get('state_source')!=record['source_id'] or registration.get('projection',{}).get('source_id')!=record['source_id']:
    raise ValueError('Dashing Makeover projection registration changed')
   if record['source_id'] not in actor.spec.get(G.KEY,{}).get('sources',{}):raise ValueError('Dashing Makeover projection lost its live source')
   bound=owner.spec.get('ap_bound')
   if not isinstance(bound,dict) or bound.get(record['source_id'])!=record['ap']:raise ValueError('Dashing Makeover lost its bound AP reservation')
   if record['source_id']!=MAKEOVER_PREFIX+owner.entity_id+':'+actor.entity_id:raise ValueError('Dashing Makeover identity changed')
  if actor.kind=='trainer':
   bound=actor.spec.get('ap_bound')
   if isinstance(bound,dict):
    for sid in bound:
     if sid.startswith(MAKEOVER_PREFIX):
      target=index.get(sid.split(':')[-1])
      live=makeover_record(target) if target is not None else None
      if live is None or live['source_id']!=sid:raise ValueError('orphan Dashing Makeover AP reservation')
   worn=_accessory_registrations(actor)
   if len(worn)>1:
    if len(worn)>DEFINITIONS[ACCESSORIZE]['accessory_slots'] or trainer_of(engine,actor,ACCESSORIZE) is None:raise ValueError('two accessory slot items require Accessorize')
    _wardrobe_constraints(engine,actor,[row['item_id'] for _,row in worn])
  for key,registration in getattr(actor,'_item_reg',{}).items():
   projection=registration.get('projection')
   if projection is None:continue
   validate_projection(projection)
   if registration.get('slots') or registration.get('held_slot') is not None or registration.get('instance_id') is not None:raise ValueError('item projection must not occupy a physical slot')
   if projection['rule_id']==MAKEOVER and (makeover_record(actor) or {}).get('registration_key')!=key:raise ValueError('orphan Dashing Makeover projection')
   if projection['rule_id']==DRESS and key not in ((dress_record(actor) or {}).get('fashionista_dress',{}).get('registration_keys',[])):raise ValueError('orphan Dress to Impress projection')
  if actor.kind=='pokemon':
   row=armed(actor)
   if row is not None:
    owner=index.get(row['trainer_id'])
    if owner is None or owner.kind!='trainer' or actor.spec.get('trainer_id')!=owner.entity_id or acquired(owner,STYLE) is None:raise ValueError('Style is Eternal arming lost its Fashionista owner')
   st=chic(actor)
   if st is not None:
    owner=index.get(st['owner_id'])
    if owner is None or owner.kind!='trainer' or not any(r['request_id']==st['acquisition'] for r in records(owner,WARDROBE)):raise ValueError('Chic state lost its Versatile Wardrobe provenance')
    for slot_id,stored in st['slots'].items():
     if stored is None:continue
     if type(stored) is not dict or set(stored)!={'instance_id','item_id','name','slot_id','stored_at','reason'} or stored['slot_id']!=slot_id:raise ValueError('invalid wardrobe slot entry')
     obj=objects.get(stored['instance_id'])
     if not isinstance(obj,dict) or obj.get('kind')!='item_instance' or obj.get('item_rule_id')!=stored['item_id'] or obj.get(WARDROBE_HOLDER)!=actor.entity_id or obj.get('wardrobe_slot')!=slot_id or obj.get('equipped_by') is not None:
      raise ValueError('wardrobe slot lost its actual stored item')
     if any(entry.get('instance_id')==stored['instance_id'] for entry in HELD.entries(actor)):raise ValueError('stored wardrobe item cannot also be the active held item')
    _wardrobe_constraints(engine,actor,wardrobe_items(engine,actor))
    if st['suppression'] is not None:
     if not engine.encounter_active or '억압' not in actor.conditions:raise ValueError('Chic Choice-item suppression requires an active encounter and the Suppressed condition')
   expected=incense_expected(engine,actor)
   current=_incense_sources(actor)
   if expected is None:
    if current:raise ValueError('Incense Move grant is not justified by the active held Incense')
   else:
    sid=INCENSE_PREFIX+actor.entity_id+':'+expected[2]
    if set(current)!={sid} or current[sid].get('grants',{}).get('moves')!=[expected[1]] or current[sid].get('owner_id')!=expected[0].entity_id:
     raise ValueError('Incense Move grant disagrees with the active held Incense')
   dress=dress_record(actor)
   if dress is not None:
    facts=dress.get('fashionista_dress')
    if type(facts) is not dict or facts.get('owner_id') not in index or chic(__import__('native_order_transfer').origin(engine,actor,dress)) is None:raise ValueError('invalid Dress to Impress record')
    if any(key not in getattr(actor,'_item_reg',{}) for key in facts.get('registration_keys',[])):raise ValueError('Dress to Impress projection missing')
 for identity,obj in objects.items():
  holder_id=obj.get(WARDROBE_HOLDER) if isinstance(obj,dict) else None
  if holder_id is None:continue
  holder=index.get(holder_id)
  if holder is None or not wardrobe_holds(engine,holder,identity):raise ValueError('stored item is not listed by its Chic wardrobe')
  if isinstance(obj,dict) and obj.get(INCENSE) is not None:incense_choice(obj)
 return True
