"""Fortress source choices over native acquisition, marks, AP and equipment."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import csv
import common_checks as C
import state_grants as G
import combat_timing as TIME
import world_entities as W

CLASS='supp-fantasy/포트리스'
SLOW='feat/느림-또는-안정';BASTION='feat/튼튼한-수호자';SHIELD='feat/방패소지자'
IRON='feat/철벽';GUARDIAN='feat/가디언의-심판';WILL='feat/막을-수-없는-의지'
BOOK_SHA='a51f5d6592bc1ff12b380f47398db93426b53c58c210810f5041b29eb64b2266'
CSV_SHA='4435ff1c462a211564c85d2c1c9a2ac6e7c790c7545e1ad7056d32888b2367bd'
FEATURES={CLASS:(747,749),SLOW:(751,755),BASTION:(757,761),SHIELD:(763,767),IRON:(769,773),GUARDIAN:(775,780),WILL:(782,786)}
PARENTS={CLASS:(),SLOW:(CLASS,),BASTION:(CLASS,),SHIELD:(BASTION,),IRON:(CLASS,),GUARDIAN:(CLASS,),WILL:(SLOW,)}
DEFINITIONS={u:{'span':list(s),'catalog_span':[738,787] if u==CLASS else list(s),
 'clause_id':'FAN-'+str(96+i).zfill(3),'class_template':CLASS,'minimum_level':0,'skill':None,
 'source':{'file':'input/supp-fantasy.md','sha256':BOOK_SHA}} for i,(u,s) in enumerate(FEATURES.items())}
ABILITY_ALIASES={'배틀무장':'전투무장','Battle Armor':'전투무장','Analytic':'애널라이즈'}
GUARDIAN_SCOPES=('korean_own_mark','original_english_any_mark')


def records(a,u=None,active=False):
 import trainer_feature_acquisition as T
 return [r for _,r in T.static_family_acquisitions(a,FEATURES,u,active=active)]


def acquired(a,u=CLASS):
 rows=records(a,u,True)
 return rows[-1] if rows else None


def source(r,u,edition):
 from source_context import verified_source
 if u not in FEATURES or edition not in ('supplement','local_csv'):raise ValueError('exact Fortress source edition required')
 if r._selected_rule(u)!=u or u in r.ruleset.unit_versions:raise ValueError('selected Fortress source needs its exact adapter')
 verified_source(r,{'file':'input/supp-fantasy.md','sha256':BOOK_SHA},label='Fortress supplement')
 out={'edition':edition,'file':'input/supp-fantasy.md','sha256':BOOK_SHA,'span':list(FEATURES[u])}
 if edition=='local_csv':
  verified_source(r,{'file':'input/db/feats.csv','sha256':CSV_SHA},label='Fortress CSV')
  row=566+tuple(FEATURES).index(u)
  with (Path(r.root)/'input/db/feats.csv').open(encoding='utf-8-sig',newline='') as stream:cells=list(csv.reader(stream))[row-1]
  r.ruleset.require({'id':f'C2CSV/input/db/feats.csv:R{row}:main','source':{'file':'db/feats.csv','record_span':[row,row]}})
  out.update(file='input/db/feats.csv',sha256=CSV_SHA,row=row,cells_sha256=sha256(__import__('json').dumps(cells,ensure_ascii=False,separators=(',',':')).encode()).hexdigest())
 return out


def static_source(r,u):
 source(r,u,'supplement')
 actual=r.selection.units[u]['source']
 if actual.get('file')!='supp-fantasy.md' or actual.get('lines')!=DEFINITIONS[u]['catalog_span'] or actual.get('sha256')!=BOOK_SHA:raise ValueError('exact Fortress catalog source required')
 return dict(DEFINITIONS[u]['source'],clause_id=DEFINITIONS[u]['clause_id'],span=list(FEATURES[u]))


def ability(r,value):
 value=ABILITY_ALIASES.get(value,value)
 import acquired_feature_projections as P
 choices=[(printed,P._ability(r,printed)) for printed in ('애널라이즈','전투무장')]
 matches=[printed for printed,(uid,title) in choices if value in (printed,uid,title)]
 if len(matches)!=1:raise ValueError('printed Analytic or Battle Armor choice required')
 return matches[0]


def acquisition_snapshot(e,a,u,rank,selection):
 import skill_modifiers as S
 keys={'edition','ability'} if u==SLOW else {'edition','mark_scope'} if u==GUARDIAN else {'edition'}
 if rank is not None or type(selection)is not dict or set(selection)!=keys and not (u==GUARDIAN and set(selection)=={'edition'}):raise ValueError('explicit Fortress edition and printed acquisition choices required')
 chosen=deepcopy(selection)
 if u==SLOW:chosen['ability']=ability(e.r,chosen['ability'])
 if u==GUARDIAN:
  chosen.setdefault('mark_scope','korean_own_mark')
  if chosen['mark_scope'] not in GUARDIAN_SCOPES:raise ValueError('explicit S001 Guardian Mark scope required')
 return {'selection':chosen,'source':source(e.r,u,chosen['edition']),
  'skills':{s:S.rank(e.r,a,s)[2] for s in ('전투','집중')},
  'parents':[r['request_id'] for r in records(a,active=True) if r['feature_id'] in PARENTS[u]]}


def qualification(a,u,snapshot,prerequisite_source):
 import acquisition_qualification as Q
 if prerequisite_source is not None or type(snapshot)is not dict or set(snapshot)!={'selection','source','skills','parents'}:raise ValueError('actual Fortress acquisition observations required')
 choice=snapshot['selection']
 keys={'edition','ability'} if u==SLOW else {'edition','mark_scope'} if u==GUARDIAN else {'edition'}
 if type(choice)is not dict or set(choice)!=keys or snapshot['source']!=source(a.r,u,choice['edition']):raise ValueError('immutable Fortress edition and acquisition choices required')
 if u==SLOW and ability(a.r,choice['ability'])!=choice['ability']:raise ValueError('canonical Fortress ability choice required')
 if u==GUARDIAN and choice['mark_scope'] not in GUARDIAN_SCOPES:raise ValueError('immutable S001 Guardian Mark scope required')
 skills=snapshot['skills']
 if type(skills)is not dict or set(skills)!={'전투','집중'}:raise ValueError('actual Combat and Focus ranks required')
 for v in skills.values():C.integer(v,'Fortress prerequisite skill rank',1)
 known={r['request_id']:r['feature_id'] for r in records(a)}
 if type(snapshot['parents'])is not list or len(set(snapshot['parents']))!=len(snapshot['parents']) or not set(snapshot['parents'])<=known.keys():raise ValueError('actual acquired Fortress parents required')
 minimum=4 if u==IRON else 5 if u in (GUARDIAN,WILL) else 0
 return Q.require(u,'native','acquire',[
  Q.check('trainer','prerequisite',a.kind=='trainer','actual Trainer required'),
  Q.check('parents','prerequisite',set(PARENTS[u])<={known[k] for k in snapshot['parents']},'all printed Fortress parents required'),
  Q.check('ranks','prerequisite',min(skills.values())>=3 if u==CLASS else max(skills.values())>=minimum,'printed Combat and Focus prerequisite ranks required')])


def prepare_acquire(e,a,choice):
 a.spec.setdefault('feature_choices',{})[SLOW]=[choice['ability']]
 __import__('acquired_feature_projections').register_all(e,a)


def after_acquire(e,a,u,sid):
 # Iron's existing fixed-pair projection already owns its Defense tag.
 if u!=IRON:G.stat(a,'def',1,sid,operation_id='acquisition_stat_tag')
 if u==SLOW:__import__('acquired_feature_projections').register_all(e,a)
 if u==IRON:
  __import__('static_feature_state_grants').register_all(e,a)
  __import__('class_move_grants').register_all(e,a)
 if u==WILL:
  name=e.r.selection.units[e.r.selection.resolve_name('절제력',('ability/',))]['title']
  G.grant(a,'abilities',name,sid,'feature',rule_id=u,owner_id=a.entity_id,lifetime='while_owned');G.ensure_ability(e,a,name)


def validate_acquisition(a,r,sid,active):
 if not active:return
 if r['feature_id']!=IRON and a.spec.get(G.KEY,{}).get('stat_sources',{}).get('def',{}).get('sources',{}).get(sid,{}).get('acquisition_stat_tag')!={'delta':1,'minimum':None}:raise ValueError('actual Fortress Defense tag required')
 if r['feature_id']==SLOW and a.spec.get('feature_choices',{}).get(SLOW)!=[r['snapshot']['selection']['ability']]:raise ValueError('immutable acquired Fortress ability required')


def require(e,a,u):
 W.require_actors(e,a)
 receipt=acquired(a,u)
 if receipt is None or not a.on_field or a.fainted or a.captured:raise ValueError('available actual Fortress acquisition required: '+u)
 source(e.r,u,receipt['snapshot']['selection']['edition'])
 return receipt


def rank(e,a,skill=None):
 import skill_modifiers as S
 if skill is not None and skill not in ('전투','집중'):raise ValueError('choose printed Combat or Focus')
 if skill is None:raise ValueError('explicit Combat or Focus choice required')
 return S.rank(e.r,a,skill)[2]


def markers(e,target):
 return [r for r in TIME.records(target) if r.get('ace_marker')]


def marker(e,target):
 rows=markers(e,target)
 if len(rows)>1:raise ValueError('multiple native Mark relations; use markers collection')
 return rows[0] if rows else None


def replace_mark(e,owner,target,source_id,**payload):
 # Fighting Ace and Fortress use the same native Mark relation and expiry owner.
 for old in list(TIME.records(target)):
  if old.get('ace_marker'):TIME.expire(e,target,old,ending='replaced')
 return TIME.install(e,target,dict(source=source_id,ace_marker=owner,encounter_end=True,**payload))


def end_turn(e,a,completion_id):
 if completion_id is None:return
 require(e,a,CLASS)
 row=getattr(e,'_move_completions',{}).get(completion_id)
 if row is None or row['actor'] is not a or row['phase']!='complete' or not row['sealed']:raise ValueError('actual complete Fortress attack required')
 if row.get('fortress_marked'):raise ValueError('this Fortress attack was already marked')
 if row['move_id']!='struggle' and not row['move'].get('_weapon_attack'):raise ValueError('actual Struggle or weapon attack required')
 events=[r for r in row.get('native_returns',{}).values()]
 serial=a.custom_conditions.get('combat_turn_serial',0)
 if row['turn_serial']!=serial or row['round']!=e.round_no or any(r['facts']['turn_serial']!=serial for r in events):raise ValueError('attack must belong to this actual owner turn')
 enemies=[t for t in row['targets'] if t is not a and a.side is not None and t.side is not None and a.side!=t.side]
 if not enemies or not any(e.adjacent(a,t) for t in enemies):raise ValueError('end turn adjacent to an actual targeted enemy')
 __import__('action_lifecycle').triggered_free_action(e,a,CLASS)
 for t in row['targets']:
  replace_mark(e,a,t,CLASS,fortress_mark=True,turn_owner=a,turn_deadline=serial+1)
 row['fortress_marked']=True


def accuracy(e,a,t):
 row=next((r for r in markers(e,a) if r.get('fortress_mark')),None)
 if row and row.get('fortress_mark') and row['ace_marker'] is not t and a.side is not None and row['ace_marker'].side is not None and a.side!=row['ace_marker'].side:
  import skill_modifiers as S
  return -S.rank(e.r,row['ace_marker'],'집중')[2]
 return 0


def _pay(e,a,u,action,amount=0):
 import turn,action_points as AP
 if AP.available(a)<amount:raise ValueError('available Fortress AP required')
 if not turn.spend(e,a,action,u):raise ValueError('Fortress requires '+action+' action')


def binding(e,a,identity):
 matches=[r for r in TIME.records(a) if r.get('fortress_binding')==identity]
 if len(matches)!=1 or a.spec.get('ap_bound',{}).get(identity)!=matches[0]['fortress_amount']:raise ValueError('actual Fortress AP reservation required')
 return matches[0]


def end_binding(e,a,row):
 a.ap_account.release_binding(row['fortress_binding'],expected_amount=row['fortress_amount'])
 TIME.expire(e,a,row,ending='ended')
 return True


def sustain(e,a,*,request_id,skill,stacking=None):
 require(e,a,BASTION);W._text(request_id,'Fortress binding')
 rank(e,a,skill)
 if stacking is not None and stacking not in ('add','maximum','minimum'):raise ValueError('explicit native Bastion composition law required')
 if any(r.get('fortress_bastion') for r in TIME.records(a)):raise ValueError('one actual Stalwart Bastion binding required')
 __import__('temporary_ap').preflight_binding(a,2,'fortress')
 def apply(se,owner):
  _pay(se,owner,BASTION,'standard',2)
  identity='fortress:'+owner.entity_id+':'+request_id
  owner.ap_account.charge(2,mode='bind',instance_id=identity,temporary_binding_owner='fortress')
  TIME.install(se,owner,{'source':BASTION,'fortress_bastion':skill,'fortress_binding':identity,'fortress_amount':2,'manual_end':True,
   **({'fortress_bastion_stacking':{'operator':stacking}} if stacking else {})})
  return {'instance_id':identity,'amount':2}
 return G.transition(e,a,apply)


def end(e,a,identity):
 row=binding(e,a,identity)
 def apply(se,owner):
  _pay(se,owner,row['source'],'free')
  return end_binding(se,owner,binding(se,owner,identity))
 return G.transition(e,a,apply)


def damage_reduction(e,target):
 import composition_derive as COMPOSITION
 contributions=[];laws=set()
 for a in W.actor_index(e).values():
  for row in TIME.records(a):
   if not row.get('fortress_bastion') or not acquired(a,BASTION) or not a.on_field or a.fainted:continue
   import body_state as BODY
   cardinal=False
   if e.grid is not None and a.pos is not None and target.pos is not None:
    left=BODY.cells(a);right=BODY.cells(target)
    cardinal=any(abs(x-u)+abs(y-v)==1 for x,y in left for u,v in right)
   if target is a or e.grid is not None and a.side is not None and a.side==target.side and cardinal:
    contributions.append({'id':row['fortress_binding'],'source':BASTION,'value':rank(e,a,row['fortress_bastion'])})
    if 'fortress_bastion_stacking' in row:laws.add(row['fortress_bastion_stacking']['operator'])
 if len(contributions)>1 and len(laws)!=1:raise COMPOSITION.CompositionPending('overlapping identical Bastion source needs one explicit GM composition law')
 contributions.sort(key=lambda row:row['id'])
 if not contributions:return shield_bonus(e,target)[1]
 ids=[row['id'] for row in contributions]
 steps=[{'law':'add','contributors':[ids[0]]}]
 if len(ids)>1:steps.append({'law':next(iter(laws)),'contributors':ids[1:]})
 return COMPOSITION.derive(0,contributions,steps,rounding='exact')['value']+shield_bonus(e,target)[1]


def shield_record(e,a,instance_id):
 import items
 rows=[r for r in getattr(a,'_item_reg',{}).values() if r.get('instance_id')==instance_id and r.get('item_id') in SHIELDS]
 if len(rows)!=1 or not items.equipment_benefit_active(a,rows[0]):raise ValueError('actual equipped usable physical shield required')
 if e.r._selected_rule(rows[0]['item_id'])!=rows[0]['item_id']:raise ValueError('selected printed shield required')
 obj=getattr(e,'_physical_objects',{}).get(instance_id)
 if obj is None or obj.get('equipped_by')!=a.entity_id:raise ValueError('actual equipped shield identity required')
 W.require_usable_object(obj)
 return rows[0]


# Exact printed core entries. The legacy local "small shield" is not silently
# renamed or treated as an equivalent definition (+1 and unconditional DR).
SHIELDS={'item/경방패':(2,4,10),'item/중방패':(2,6,15)}
EQUIPMENT_SHA='b5aeb6b82af4b05fe0b369368f8b0181ed3b1d22079e8a86a1c4248e6cbf92d2'
SHIELD_PARENT='ch09-equipment/장비/손-장비'


def shield_definition(r,name):
 aliases={'경방패':'item/경방패','Light Shield':'item/경방패','중방패':'item/중방패','Heavy Shield':'item/중방패'}
 uid=aliases.get(name,name)
 if uid not in SHIELDS:return None
 __import__('source_context').verified_source(r,{'file':'input/ch09-equipment.md','sha256':EQUIPMENT_SHA},label='printed core shields')
 line=762 if uid=='item/경방패' else 763
 r.ruleset.require({'id':uid,'source':{'file':'ch09-equipment.md','lines':[line,line]}})
 return [{'type':'trainer_slot','slot':'반대손'}],{'id':uid,'name':uid[5:],'trainer_slot':'반대손','source':{'file':'input/ch09-equipment.md','sha256':EQUIPMENT_SHA,'span':[line,line]},'price':3000 if line==762 else 4500}


def install_shields(r):
 """Use the existing derived catalog path; never weaken physical admission."""
 from ruleset import source_unit
 try:
  if r._selected_rule(SHIELD_PARENT)!=SHIELD_PARENT:return ()
 except ValueError:return ()
 parent=r.selection.units[SHIELD_PARENT]['source']
 if parent.get('file')!='ch09-equipment.md' or parent.get('lines')!=[753,766] or parent.get('sha256')!=EQUIPMENT_SHA:raise ValueError('exact printed core hand equipment parent required')
 for uid in SHIELDS:
  effects,header=shield_definition(r,uid)
  origin=header['source']
  unit={'id':uid,'title':header['name'],'kind':'entity:item','source':{'file':'ch09-equipment.md','lines':origin['span'],'sha256':EQUIPMENT_SHA},'tags':[]}
  if uid not in r.selection.units:r.selection.register_derived(unit,(SHIELD_PARENT,))
  elif r.selection.units[uid]!=source_unit(unit):raise ValueError('printed shield source identity changed')
  definition={'id':uid,'name':header['name'],'header':header,'effects':effects,'coverage':'full'}
  old=r.items_mech.get(uid)
  if old is not None and old!=definition:raise ValueError('printed shield cannot replace a catalog identity')
  r.items_mech[uid]=definition
 return tuple(SHIELDS)


def ready_shield(e,a,instance_id,*,ally=None,request_id):
 receipt=require(e,a,SHIELD);shield_record(e,a,instance_id);W._text(request_id,'Shield Bearer request')
 if ally is not None:
  W.require_actors(e,ally)
  if ally is a or a.side is None or ally.side!=a.side or not e.adjacent(a,ally):raise ValueError('one actual adjacent ally required')
 if any(r.get('fortress_shield') for r in TIME.records(a)):raise ValueError('one live Shield Bearer readiness required')
 bound=receipt['snapshot']['selection']['edition']=='supplement'
 if bound:__import__('temporary_ap').preflight_binding(a,1,'fortress')
 def apply(se,owner,*participants):
  actual=participants[0] if participants else None
  _pay(se,owner,SHIELD,'swift',1)
  identity='shield-bearer:'+owner.entity_id+':'+request_id
  payload={'source':SHIELD,'fortress_shield':instance_id,'fortress_ally':actual,
   'turn_owner':owner,'turn_deadline':owner.custom_conditions.get('combat_turn_serial',0)+1}
  if bound:
   owner.ap_account.charge(1,mode='bind',instance_id=identity,temporary_binding_owner='fortress')
   payload.update(fortress_binding=identity,fortress_amount=1)
  else:owner.ap_account.charge(1)
  TIME.install(se,owner,payload)
  return {'instance_id':identity,'shield_id':instance_id,'bound':bound}
 return G.transition(e,a,apply,participants=(() if ally is None else (ally,)))


def shield_bonus(e,target):
 if e is None:return (0,0)
 evasion=0;reduction=0
 for a in W.actor_index(e).values():
  for row in TIME.records(a):
   if not row.get('fortress_shield') or not acquired(a,SHIELD):continue
   try:reg=shield_record(e,a,row['fortress_shield'])
   except ValueError:continue
   ally=row['fortress_ally'];recipient=ally if ally is not None else a
   if recipient is not target or ally is not None and not e.adjacent(a,ally):continue
   base,ready,dr=SHIELDS[reg['item_id']]
   evasion+=ready;reduction+=dr
 return evasion,reduction


def ordinary_shield(e,target):
 # While the shield is readied, its ordinary passive is replaced, never added.
 if e is None:return 0
 ready={r['fortress_shield'] for a in W.actor_index(e).values() for r in TIME.records(a) if r.get('fortress_shield')}
 import items
 return sum(SHIELDS[r['item_id']][0] for r in getattr(target,'_item_reg',{}).values() if r.get('item_id') in SHIELDS and r.get('instance_id') not in ready and items.equipment_benefit_active(target,r))


def ending(e,a,row):
 if row.get('fortress_binding') and row['fortress_binding'] in a.spec.get('ap_bound',{}):a.ap_account.release_binding(row['fortress_binding'],expected_amount=row['fortress_amount'])


def guardian_mark(e,a,target):
 receipt=acquired(a,GUARDIAN);rows=markers(e,target)
 if receipt is None or not rows:return False
 choice=receipt['snapshot']['selection']['mark_scope']
 return choice=='original_english_any_mark' or choice=='korean_own_mark' and any(row['ace_marker'] is a for row in rows)


def weapon_attack(e,a,target,move_id,*,skill,stacking=None,**options):
 require(e,a,GUARDIAN);rank(e,a,skill)
 if options.get('set_damage'):raise ValueError('Guardian modifies an actual Damage Roll, not Set Damage')
 if not guardian_mark(e,a,target):raise ValueError('actual Marked foe within the acquired Guardian source scope required')
 if a.side is None or target.side is None or a.side==target.side:raise ValueError('actual marked foe required')
 if stacking is not None and stacking not in ('add','maximum','minimum'):raise ValueError('explicit native composition law required')
 move=__import__('weapon_actions').prepare(e,a,e.r.move(move_id),options.get('weapon_id'))
 if not move.get('_weapon_attack') or move.get('class') not in ('물리','특수'):raise ValueError('actual damaging Weapon attack required')
 pending=[]
 def apply(se,actor,foe):
  if actor.custom_conditions.get('fortress_guardian_attack'):raise ValueError('one actual Guardian attack scope required')
  actor.custom_conditions['fortress_guardian_attack']={'target':foe,'skill':skill,'move_id':move_id,'paid':False,'stacking':stacking}
  staged_options=G._stage_transition_payload(e,se,options)
  try:result=se.use_move_on(actor,foe,move_id,se.everyone,**staged_options)
  except Exception as error:
   if G.record_native_pending(se,error,pending):return None
   actor.custom_conditions.pop('fortress_guardian_attack',None)
   raise
  actor.custom_conditions.pop('fortress_guardian_attack',None)
  return result
 result=G.transition(e,a,apply,participants=(target,),include_rulings=True,include_grid=e.grid is not None)
 if pending:
  exception,event_id=pending[0];raise exception(event_id)
 return result


def begin_move(e,row):
 scope=row['actor'].custom_conditions.get('fortress_guardian_attack')
 if scope and scope['move_id']==row['move_id'] and scope['target'] in row['targets']:
  if scope.get('completion_id',row['id'])!=row['id']:raise ValueError('one actual Guardian Move completion required')
  scope['completion_id']=row['id']


def event_interested(e,a,t,move):
 scope=a.custom_conditions.get('fortress_guardian_attack')
 return bool(scope and scope['target'] is t and scope['move_id']==move['id'] and move.get('_weapon_attack') and acquired(a,GUARDIAN))


def guardian_hit(e,a,t,move,completion_id,*,passive_event=None,defense_token=None):
 scope=a.custom_conditions.get('fortress_guardian_attack')
 if not scope or scope['move_id']!=move['id']:return
 row=getattr(e,'_move_completions',{}).get(completion_id)
 original=scope['target']
 if defense_token is None and t is not original:return
 if defense_token is not None:
  parent=getattr(e,'_passive_events',{}).get(defense_token[0])
  if parent is not None and parent['target'] is not original:return
 if row is None or scope.get('completion_id')!=completion_id or row['actor'] is not a or row['move_id']!=move['id'] or row['phase']!='targets' or original not in row['targets'] or original.entity_id not in row['started'] or original.entity_id in row['results']:raise ValueError('actual native Guardian hit occurrence required')
 child=None
 if defense_token is None and original.entity_id in row.get('defense',{}):raise ValueError('actual native Guardian recipient producer required')
 event=getattr(e,'_passive_events',{}).get(passive_event)
 if event is None or event['actor'] is not a or event['target'] is not t or event['move_id']!=move['id'] or event['completion_id']!=completion_id or event.get('hit') is not True or event['phase']!='activated':raise ValueError('actual observed Guardian native hit required')
 if defense_token is not None:
  import move_defense_reactions as DEFENSE
  DEFENSE.require_recipient(e,defense_token,a,t,move,completion_id)
  child=getattr(e,'_passive_events',{}).get(passive_event)
  parent=getattr(e,'_passive_events',{}).get(defense_token[0])
  if child is None or parent is None or parent['target'] is not original:return
  if child.get('defense_parent')!=parent['id'] or child['actor'] is not a or child['target'] is not t or child['move_id']!=move['id'] or child['completion_id']!=completion_id or child.get('hit') is not True:raise ValueError('actual Guardian defense recipient event required')
  # Retain the declared choice when it still receives the attack. A redirect
  # may adopt only its unique eligible actual recipient, never an arbitrary one.
  index=W.actor_index(e);plans=row['defense'][original.entity_id]['recipients']
  eligible=[index[p['actor_id']] for p in plans if p['hit'] and guardian_mark(e,a,index[p['actor_id']])]
  if original in eligible:
   if t is not original:return
  elif len(eligible)>1:raise ValueError('Guardian needs an explicit recipient choice for multiple redirected marked foes')
  elif t not in eligible:return
 elif t is not original:return
 if not move.get('_weapon_attack') or not guardian_mark(e,a,t):return
 occurrence=row['id']+':'+t.entity_id
 if scope['paid']:
  if scope['hit_occurrence']!=occurrence:raise ValueError('Guardian cannot consume another hit occurrence')
  return
 import frequency as F
 others=[r for r in TIME.records(t) if 'fortress_guardian' in r and r.get('fortress_guardian_owner') is not a]
 if others and scope['stacking'] is None:raise __import__('composition_derive').CompositionPending('overlapping identical Guardian source needs its explicit GM ruling')
 quota={'kind':'scene','uses':2}
 if not F.activation_allowed(a,GUARDIAN,quota,engine=e):raise ValueError('Guardian scene frequency exhausted')
 _pay(e,a,GUARDIAN,'swift');F.consume_activation(a,GUARDIAN,quota,engine=e)
 for old in list(TIME.records(t)):
  if old.get('fortress_guardian_owner') is a:TIME.expire(e,t,old,ending='replaced')
 TIME.install(e,t,{'source':GUARDIAN,'fortress_guardian':rank(e,a,scope['skill']),'fortress_guardian_owner':a,'effect_occurrence':occurrence+':guardian',
  **({'fortress_stacking':{'operator':scope['stacking']}} if scope['stacking'] else {}),
  'count_deadline':(e.round_no+1,TIME.current(e)),'encounter_end':True})
 scope.update(paid=True,hit_occurrence=occurrence,recipient=t,hit_event=event['id'],recipient_event=None if child is None else child['id'])


def guardian_damage(e,a,t,move,event):
 scope=a.custom_conditions.get('fortress_guardian_attack')
 if event is None or not scope or scope.get('recipient',scope['target']) is not t or scope['move_id']!=move['id']:return 0
 # Pay the triggered Swift before native Heavy receipt issuance, not mid-formula.
 row=getattr(e,'_move_completions',{}).get(scope.get('completion_id'))
 if row is None or not scope['paid'] or scope['hit_occurrence']!=row['id']+':'+t.entity_id or event.get('attacker') is not a or event.get('target') is not t or not move.get('_weapon_attack') or not guardian_mark(e,a,t):raise ValueError('actual paid Guardian native hit required')
 return a.staged('def')


def outgoing_penalty(a):
 return -__import__('combat_modifiers').incoming_derivation(a,'fortress_guardian',stacking_key='fortress_stacking')['value']


def completed(e,row):
 scope=row['actor'].custom_conditions.get('fortress_guardian_attack')
 if scope and scope['move_id']==row['move_id'] and scope['target'] in row['targets']:
  row['actor'].custom_conditions.pop('fortress_guardian_attack',None)


def before_revoke(e,a,sources):
 removed={r['feature_id'] for sid,r in __import__('trainer_feature_acquisition').static_family_acquisitions(a,FEATURES,active=True) if sid in sources}
 for target in W.actor_index(e).values():
  for row in list(TIME.records(target)):
   if target is a and row.get('source') in removed or CLASS in removed and row.get('fortress_mark') and row.get('ace_marker') is a or GUARDIAN in removed and row.get('fortress_guardian_owner') is a:
    TIME.expire(e,target,row,ending='source_withdrawn')


def _shield_shift(e,a,target,mode,options,*,maximum_distance=None,preflight=False):
 """Adapt actual native Shift observations, never a caller-granted movement."""
 import movement_actions as M
 if mode not in M.MODES:raise ValueError('actual native movement mode required')
 if options is not None and type(options)is not dict:raise ValueError('actual native movement observations required')
 options=dict(options or {})
 allowed={'burrow':{'path','diggable','surface','reason_text'},
  'teleport':{'destination','surface_contact','altitude','reason_text','gm_distance','sky_air_policy'},
  'sky':{'destination','altitude','reason_text','gm_distance'},
  'levitate':{'destination','altitude','reason_text','gm_distance'}}
 if set(options)-allowed.get(mode,{'blindness_options'}):raise ValueError('only actual native movement observations may be supplied')
 if mode in ('land','swim'):
  if preflight:return None
  if maximum_distance is None:return e.approach(a,target,movement_mode=mode,**options)
  # Mapped steps have integral costs; a preceding measured flight may not.
  return e._approach(a,target,reach=1,movement_mode=mode,maximum_distance=__import__('math').floor(maximum_distance),**options)
 if mode=='burrow':
  path=options.pop('path',None)
  plan=M.burrow_plan(e,a,path,maximum_distance=maximum_distance,**options)
  if preflight or isinstance(plan,C.PendingDecision):return plan
  return e.burrow_move(a,path,**options)
 destination=options.pop('destination',None)
 if mode=='teleport':
  plan=M.teleport_plan(e,a,destination,maximum_distance=maximum_distance,**options)
  if preflight or isinstance(plan,C.PendingDecision):return plan
  return e.teleport(a,destination,**options)
 M.reason(options.get('reason_text'));M._aerial_height(e,a,mode,options.get('altitude'),destination=destination)
 _,distance=M._travel_geometry(e,a,destination,options.get('altitude'),options.get('gm_distance'))
 allowance=M.distance_budget(e,a,mode)
 if maximum_distance is not None:allowance=min(allowance,maximum_distance)
 if distance>allowance:raise ValueError('Shield Bearer cannot exceed its normal movement')
 if preflight:return {'distance':distance,'mode':mode}
 return e.aerial_move(a,destination,mode=mode,**options)


def follow_shift(e,a,ally,target,*,request_id,movement_mode='land',ally_movement_mode=None,
 ally_options=None,follow_options=None,payment='next'):
 """Observe the ally's actual paid Shift, then use the native Shift Interrupt.

 No caller-supplied "the ally shifted" flag, granted budget or invented path
 authorizes this action. Both movements use ordinary terrain/body/AoO owners.
 """
 require(e,a,SHIELD);W.require_actors(e,ally,target);W._text(request_id,'Shield Bearer follow request')
 rows=[r for r in TIME.records(a) if r.get('fortress_shield') and r.get('fortress_ally') is ally]
 if len(rows)!=1 or e._active_turn_actor is not ally or not e.adjacent(a,ally):raise ValueError('actual adjacent protected ally own-turn Shift required')
 shield_record(e,a,rows[0]['fortress_shield'])
 if payment not in ('current','next'):raise ValueError('explicit native Interrupt payment required')
 ally_mode=movement_mode if ally_movement_mode is None else ally_movement_mode
 def apply(se,actor,friend,destination):
  import initiative_interrupts as I,movement_actions as M
  before=len(getattr(friend,'_action_history',[]))
  movement=_shield_shift(se,friend,destination,ally_mode,ally_options)
  if not movement or isinstance(movement,C.PendingDecision) or not movement['distance']:return {'ally':movement,'follow':None}
  if getattr(friend,'_action_history',[])[before:]!=['shift']:raise ValueError('one actual paid ally Shift required')
  if se.adjacent(actor,friend):return {'ally':movement,'follow':None}
  normal,_=se.move_profile(actor,movement_mode=movement_mode)
  row=next(r for r in TIME.records(actor) if r.get('fortress_shield') and r.get('fortress_ally') is friend)
  used=row.get('fortress_follow_distance',0)
  allowance=max(0,normal-used)
  if allowance==0:raise ValueError('Shield Bearer cannot exceed its normal movement')
  plan=_shield_shift(se,actor,friend,movement_mode,follow_options,maximum_distance=allowance,preflight=True)
  if isinstance(plan,C.PendingDecision):raise ValueError('native Shield follow awaits: '+str(plan))
  queued=I.queue(se,[{'id':request_id,'actor_id':actor.entity_id,'source':SHIELD,'priority':0,'mode':'reaction','payment':payment,'budget':{'shift':1},'clock':'none'}],trigger={'kind':'turn','actor_id':friend.entity_id,'serial':friend.custom_conditions['combat_turn_serial'],'round':se.round_no})
  I.begin(se,queued['window_id'],request_id)
  result=_shield_shift(se,actor,friend,movement_mode,follow_options,maximum_distance=allowance)
  if isinstance(result,C.PendingDecision):raise ValueError('native Shield follow awaits: '+str(result))
  I.finish(se)
  # Native transitions rebind records; never retain a stale timing dictionary.
  row=next(r for r in TIME.records(actor) if r.get('fortress_shield') and r.get('fortress_ally') is friend)
  row['fortress_follow_distance']=used+(0 if not result else result['distance'])
  return {'ally':movement,'follow':result}
 return G.transition(e,a,apply,participants=(ally,target),include_grid=True,include_rulings=True)


def validate_world(e,index):
 for a in index.values():
  marks=markers(e,a)
  if any(r.get('fortress_mark') for r in marks) and len(marks)>1:raise ValueError('one native Fortress Mark relation per target required')
  scope=a.custom_conditions.get('fortress_guardian_attack')
  if scope and scope.get('paid'):
   original=scope.get('target');target=scope.get('recipient',original);row=getattr(e,'_move_completions',{}).get(scope.get('completion_id'))
   if (not acquired(a,GUARDIAN) or original is None or target is None or index.get(target.entity_id)is not target or
       row is None or row['actor'] is not a or row['move_id']!=scope.get('move_id') or
       row['phase']=='complete' or original not in row['targets'] or original.entity_id not in row['started'] or
       scope.get('hit_occurrence')!=row['id']+':'+target.entity_id):
    raise ValueError('paid Guardian requires its actual native recipient occurrence')
   child_id=scope.get('recipient_event')
   hit=getattr(e,'_passive_events',{}).get(scope.get('hit_event'))
   if scope.get('hit_event') is not None and (hit is None or hit['actor'] is not a or hit['target'] is not target or hit['move_id']!=scope['move_id'] or hit['completion_id']!=row['id'] or hit.get('hit') is not True):raise ValueError('paid Guardian requires its observed native hit')
   if child_id is not None:
    child=getattr(e,'_passive_events',{}).get(child_id)
    parent=None if child is None else getattr(e,'_passive_events',{}).get(child.get('defense_parent'))
    state=row.get('defense',{}).get(original.entity_id,{})
    if (child is None or parent is None or parent['target'] is not original or parent['actor'] is not a or
        child['target'] is not target or child['actor'] is not a or child['move_id']!=scope['move_id'] or
        child['completion_id']!=row['id'] or child.get('hit') is not True or
        state.get('children',{}).get(target.entity_id)!=child_id or
        not any(p['actor_id']==target.entity_id and p['hit'] for p in state.get('recipients',[]))):
     raise ValueError('paid Guardian requires its actual defense recipient receipt')
   elif target is not original:raise ValueError('redirected Guardian requires its native child event')
  for row in TIME.records(a):
   if row.get('fortress_binding'):
    binding(e,a,row['fortress_binding'])
    if row.get('source') not in (BASTION,SHIELD) or not acquired(a,row['source']):raise ValueError('actual acquired Fortress binding owner required')
    expected=2 if row['source']==BASTION else 1
    if row['fortress_amount']!=expected:raise ValueError('printed Fortress AP amount required')
   if row.get('fortress_bastion'):
    rank(e,a,row['fortress_bastion'])
    if row.get('source')!=BASTION or not row.get('manual_end') or not row.get('fortress_binding'):raise ValueError('actual sustained Bastion required')
    if 'fortress_bastion_stacking' in row and (type(row['fortress_bastion_stacking'])is not dict or set(row['fortress_bastion_stacking'])!={'operator'} or row['fortress_bastion_stacking']['operator'] not in ('add','maximum','minimum')):raise ValueError('explicit native Bastion composition law changed')
   if row.get('fortress_shield'):
    ally=row.get('fortress_ally')
    if ally is not None and index.get(ally.entity_id)is not ally:raise ValueError('actual Shield Bearer ally relation required')
    if row.get('source')!=SHIELD or not acquired(a,SHIELD) or row.get('turn_owner') is not a:raise ValueError('actual acquired Shield Bearer timing owner required')
    __import__('physical_limits').number(row.get('fortress_follow_distance',0),'actual Shield Bearer follow distance',minimum=0)
   if row.get('fortress_mark') and (row['source']!=CLASS or index.get(row['ace_marker'].entity_id)is not row['ace_marker'] or not acquired(row['ace_marker'],CLASS) or row.get('turn_owner') is not row['ace_marker']):raise ValueError('actual Fortress Mark owner required')
   if 'fortress_guardian' in row:
    owner=row.get('fortress_guardian_owner')
    if owner is None or index.get(owner.entity_id)is not owner or not acquired(owner,GUARDIAN) or row.get('source')!=GUARDIAN:raise ValueError('actual Guardian penalty owner required')
    C.integer(row['fortress_guardian'],'printed Guardian damage penalty',1)
