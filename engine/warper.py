"""Printed Warper contracts over the native acquisition, movement and item owners."""
from copy import deepcopy
from functools import wraps
import common_checks as C
import state_grants as G
import world_entities as W
import combat_timing as TIME
import frequency as F

CLASS='class/공간도약자';SPACE='feat/공간-왜곡';GROUND='feat/지면-뒤틀기'
ENERGY='feat/이상한-힘';FARCAST='feat/파캐스트';WARPED='feat/왜곡된-전송';REALITY='feat/현실-비틀기'
TELEPORT='move/순간이동';SWITCH='move/사이드체인지';COAT='move/매직코트'
GRAVITY='move/중력';TRICK='move/트릭';HEAL_BLOCK='move/회복봉인'
PROBABILITY='ability/확률제어';TRANSPORTER='ability/트랜스포터-playtest'
SOURCE_SHA256='a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'
FEATURES={CLASS:(3249,3251),SPACE:(3253,3257),GROUND:(3259,3263),ENERGY:(3265,3269),FARCAST:(3271,3276),WARPED:(3278,3283),REALITY:(3285,3294)}
PARENTS={CLASS:(),SPACE:(CLASS,),GROUND:(CLASS,),ENERGY:(GROUND,SPACE),FARCAST:(SPACE,),WARPED:(FARCAST,),REALITY:(CLASS,)}
DEFINITIONS={u:{'span':list(s),'catalog_span':[3237,3237] if u==CLASS else list(s),'parents':list(PARENTS[u]),
 'clause_id':'C04-119' if u==FARCAST else 'C04-120' if u==REALITY else 'input/ch04-trainer-classes.md:'+str(s[0])+'-'+str(s[1]),
 'minimum_rank':{CLASS:3,FARCAST:5,WARPED:6,REALITY:5}.get(u,0),'stat_tags':['spe']} for u,s in FEATURES.items()}
CHOICE='warper_transfer_choice'


def registration(rules,name):
 if name not in (PROBABILITY,'확률제어','Probability Control'):return None
 from pathlib import Path
 import hashlib
 if rules._selected_rule(PROBABILITY)!=PROBABILITY:raise ValueError('selected exact Probability Control source required')
 if hashlib.sha256((Path(rules.root)/'input/db/abilities.csv').read_bytes()).hexdigest()!='87efebd17b0a5fe09c9db060a16a8844cf41be53d65eb35716cf62f80a177fae':raise ValueError('reviewed Probability Control source changed')
 effects=rules.ability_effects.get('확률제어',[])
 if [__import__('event_effects').semantic(x) for x in effects]!=[{'type':'reroll','roll':'any','trace':'supernatural'}]:raise ValueError('Probability Control extraction differs from reviewed native contract')
 return {'name':'확률제어','source_id':PROBABILITY,'equivalent_source_ids':[PROBABILITY]}


def policy(e):
 from pathlib import Path
 import hashlib,json
 document=json.loads((Path(e.r.root)/'data/warper-source-contracts.json').read_text(encoding='utf-8'))
 for file,digest in document['source_files'].items():
  if hashlib.sha256((Path(e.r.root)/file).read_bytes()).hexdigest()!=digest:raise ValueError('Warper reviewed source changed: '+file)
 return document


def records(a,feature=None,active=False):
 import trainer_feature_acquisition as T
 return [record for _, record in T.static_family_acquisitions(a, FEATURES, feature, active=active)]


def acquired(a,feature=CLASS):
 rows=records(a,feature,True)
 return rows[-1] if rows else None


def acquisition_snapshot(e,a,u,rank=None,selection=None):
 policy(e)
 if rank is not None or selection is not None:raise ValueError('Warper has no Ranked Features or acquisition selection')
 return {'rank':__import__('skill_modifiers').rank(e.r,a,'교활')[2],
  'psychic_connection':'에스퍼' in __import__('elemental_connection').choices(e,a),
  'parents':[r['request_id'] for r in records(a,active=True) if r['feature_id'] in PARENTS[u]]}


def qualification(a,u,snapshot,prerequisite_source):
 import acquisition_qualification as Q
 if prerequisite_source is not None or type(snapshot)is not dict or set(snapshot)!={'rank','psychic_connection','parents'}:raise ValueError('actual Warper acquisition observations required')
 # Acquisition already resolves declared ranks through skill_modifiers.rank.
 C.integer(snapshot['rank'],'Guile prerequisite rank',1)
 if type(snapshot['psychic_connection'])is not bool or type(snapshot['parents'])is not list:raise ValueError('actual Psychic Connection and parent observations required')
 known={r['request_id']:r['feature_id'] for r in records(a) if r['feature_id'] in PARENTS[u]}
 if not set(snapshot['parents'])<=set(known):raise ValueError('actual Warper parent receipts required')
 return Q.require(u,'native','acquire',[
  Q.check('trainer','prerequisite',a.kind=='trainer','actual Trainer required'),
  Q.check('parent','prerequisite',set(PARENTS[u])<={known[x] for x in snapshot['parents']},'all printed acquired Warper parents required'),
  Q.check('rank','prerequisite',snapshot['rank']>=DEFINITIONS[u]['minimum_rank'],'printed Guile rank required'),
  Q.check('connection','prerequisite',u!=CLASS or snapshot['psychic_connection'],'Psychic Elemental Connection required')])


def after_acquire(e,a,u,sid):
 # The accepted three pair projections already own their Speed and learned Moves.
 if u not in (SPACE,GROUND,ENERGY):G.stat(a,'spe',1,sid,operation_id='acquisition_stat_tag')
 if u==CLASS:
  G.grant(a,'abilities','확률제어',sid,'feature',rule_id=u,owner_id=a.entity_id,lifetime='while_owned');G.ensure_ability(e,a,'확률제어')
 if u in (SPACE,GROUND,ENERGY):
  __import__('static_feature_state_grants').register_all(e,a);__import__('class_move_grants').register_all(e,a)


def validate_acquisition(a,record,sid,active):
 if active and record['feature_id'] not in (SPACE,GROUND,ENERGY) and a.spec.get(G.KEY,{}).get('stat_sources',{}).get('spe',{}).get('sources',{}).get(sid,{}).get('acquisition_stat_tag')!={'delta':1,'minimum':None}:raise ValueError('actual Warper Speed tag required')


def require(e,a,u):
 policy(e)
 W.require_actors(e,a)
 if e.r._selected_rule(u)!=u or not acquired(a,u):raise ValueError('actual acquired Warper Feature required: '+u)
 if not a.on_field or a.captured or a.fainted:raise ValueError('available Warper actor required')


def pay(e,a,source,kind,*,ap=0,quota=None,uses=1,triggered=False):
 import action_points as AP,turn as TURN
 if AP.available(a)<ap:raise ValueError('available Warper AP required')
 if quota:
  _,cap=F.parse(quota)
  if uses>cap or not F.activation_allowed(a,source,dict(quota,uses=cap-uses+1),engine=e):raise ValueError('Warper activation frequency exhausted')
 # Triggered Free actions may answer the actual current action on another turn.
 if triggered:
  if kind!='free':raise ValueError('actual triggered Free action required')
  __import__('action_lifecycle').triggered_free_action(e,a,source)
 elif not TURN.spend(e,a,kind,source):raise ValueError('Warper requires '+kind+' action')
 if ap:AP.charge(a,ap)
 if quota:
  for _ in range(uses):F.consume_activation(a,source,quota,engine=e)


def transfer_choice(e,a,*,triple=False,partner=None,willing=False,touching=False,partner_destination=None,source=FARCAST,warped=False):
 if any(type(x)is not bool for x in (triple,willing,touching,warped)):raise ValueError('explicit transfer choices required')
 if source not in (FARCAST,TRANSPORTER):raise ValueError('select Core Farcast or the actual Transporter Ability')
 if source==FARCAST:require(e,a,FARCAST)
 elif not __import__('ability_transitions').active(a,TRANSPORTER):raise ValueError('actual selected Transporter Ability required')
 if not triple and partner is None:raise ValueError('select triple Teleporter, one touching partner, or both')
 if partner is not None:
  W.require_actors(e,partner)
  if partner is a or partner.kind not in ('trainer','pokemon') or willing is not True or touching is not True or not e.adjacent(a,partner) or not partner.on_field or partner.fainted or partner.captured:raise ValueError('one actually touching willing Trainer or Pokemon required')
  if partner_destination is None:raise ValueError('explicit actual partner destination required')
 if warped:require(e,a,WARPED)
 return {'source':source,'triple':triple,'partner_id':None if partner is None else partner.entity_id,
  'willing':willing,'touching':touching,'partner_destination':partner_destination,'warped':warped,'uses':int(triple)+int(partner is not None)}


def movement(e,a,result):
 choice=a.spec.get(CHOICE)
 if choice and choice['triple'] and result.get('teleport',0):result=dict(result,teleport=3*result['teleport'])
 return result


def transfer(e,a,destination,*,surface_contact,reason,altitude=0,gm_distance=None,sky_air_policy=None,triple=False,partner=None,willing=False,touching=False,partner_destination=None,source=FARCAST,warped=False,move=False):
 """Resolve the actual Move/capability first, then its optional paid followups."""
 import movement_actions as M
 if type(move)is not bool:raise ValueError('explicit Move versus Teleporter activation required')
 choice=transfer_choice(e,a,triple=triple,partner=partner,willing=willing,touching=touching,partner_destination=partner_destination,source=source,warped=warped) if triple or partner is not None else None
 if warped:require(e,a,WARPED)
 if move and warped:raise ValueError('Warped Transmission triggers on Teleporter or Ally Switch, not the Teleport Move')
 participants=() if partner is None else (partner,)
 def apply(se,c,*others):
  if warped and se._active_turn_actor is not c:raise ValueError('Warped Transmission requires own-turn Swift action')
  if CHOICE in c.spec:raise ValueError('one actual teleport activation at a time')
  if choice:c.spec[CHOICE]=deepcopy(choice)
  se._warper_transfer=True
  try:
   plan=M.teleport_plan(se,c,destination,surface_contact=surface_contact,altitude=altitude,reason_text=reason,gm_distance=gm_distance,sky_air_policy=sky_air_policy,ignore_actors=others)
   if isinstance(plan,C.PendingDecision):return plan
   partner_plan=None
   if others:
    t=others[0]
    _,distance=M._travel_geometry(se,t,partner_destination,altitude,gm_distance,ignore_actors=(c,))
    if distance>plan['budget']:raise ValueError('partner destination exceeds actual Teleporter allowance')
    # Both physical bodies must fit and keep the partner in contact at arrival.
    from grid import cheb
    if cheb(tuple(destination),tuple(partner_destination))>1:raise ValueError('partner must arrive adjacent to the teleporter')
    partner_plan={'mode':'teleport','path':(t.pos,tuple(partner_destination)),'distance':distance,'budget':plan['budget'],'origin_altitude':t.spec.get('_movement_altitude',0),'origin_underground':False,'parameters':dict(plan['parameters'])}
   if choice:pay(se,c,choice['source'],'free',quota={'kind':'daily','uses':3},uses=choice['uses'],triggered=True)
   if move:
    c.spec['warper_move_destination']=deepcopy(plan)
    try:result=se.use_move(c,c,TELEPORT)
    finally:c.spec.pop('warper_move_destination',None)
    if c.pos!=tuple(destination):raise ValueError('Teleport Move did not reach its actual chosen destination')
   else:result=M.teleport(se,c,destination,surface_contact=surface_contact,altitude=altitude,reason_text=reason,gm_distance=gm_distance,sky_air_policy=sky_air_policy)
   if not move and not result:raise ValueError('actual Teleporter shift action unavailable')
   if partner_plan:
    # Existing native transfer owns entry, position, altitude and any entry effects.
    se._teleport_passenger={'actor_id':others[0].entity_id,'carrier_id':c.entity_id,'plan':partner_plan}
    try:M.follow_paid_transfer(se,others[0],partner_plan)
    finally:se.__dict__.pop('_teleport_passenger',None)
   affected=warped_after(se,c,'teleporter') if warped else []
   return {'source':TELEPORT if move else 'capability/teleporter','position':c.pos,'farcast':deepcopy(choice),'partner_id':None if not others else others[0].entity_id,'warped_targets':affected}
  finally:
   c.spec.pop(CHOICE,None);se.__dict__.pop('_warper_transfer',None)
 return G.transition(e,a,apply,participants=participants,include_grid=e.grid is not None)


def warped_after(e,a,trigger):
 if trigger not in ('teleporter','ally_switch'):raise ValueError('actual Teleporter or Ally Switch completion required')
 require(e,a,WARPED)
 count=TIME.current(e)
 pay(e,a,WARPED,'swift',ap=2)
 targets=[]
 for t in W.actor_index(e).values():
  if t is a or not t.on_field or t.fainted or t.captured or not getattr(a,'side',None) or not getattr(t,'side',None) or t.side==a.side or not e.adjacent(a,t):continue
  stamp={'actor_id':a.entity_id,'trigger':trigger,'position':list(a.pos),'round':e.round_no,'count':count}
  TIME.install(e,t,{'source':WARPED,'evasion_modifier':-3,'count_deadline':(e.round_no+1,count),'warped_transmission':deepcopy(stamp)})
  TIME.install(e,t,{'source':WARPED,'turn_owner':a,'turn_deadline':a.custom_conditions['combat_turn_serial']+1,'warped_shift_protection':deepcopy(stamp)})
  targets.append(t.entity_id)
 return targets


def evasion(a):return sum(r.get('evasion_modifier',0) for r in TIME.records(a) if 'warped_transmission' in r)


def prevents_aoo(enemy,mover,why):
 return why=='인접 칸 밖으로 이동' and any(r.get('warped_shift_protection',{}).get('actor_id')==mover.entity_id for r in TIME.records(enemy))


def reality_event(e,a,*,choose,provide,apply_outcome,source='core'):
 """The GM provides the real world event; its native consumer commits the choice."""
 require(e,a,REALITY)
 if source not in ('core','local_csv515'):raise ValueError('explicit Core or local CSV515 Reality Bender source required')
 if not callable(provide) or not callable(apply_outcome):raise ValueError('actual GM event provider and world outcome consumer required')
 def apply(se,c):
  event=provide(se,c)
  if type(event)is not dict or set(event)!={'id','kind','outcomes','reason'}:raise ValueError('exact GM in-world random event required')
  G._text(event['id'],'actual in-world event identity');G._text(event['reason'],'GM event observation')
  if event['kind'] not in ('in_world_random','metronome'):raise ValueError('Reality Bender excludes gameplay dice')
  outcomes=event['outcomes']
  if type(outcomes)is not list or len(outcomes)<2 or source=='core' and len(outcomes)!=2:raise ValueError('Core GM must supply exactly two possible outcomes')
  if len({__import__('resolution_transaction').request_fingerprint(v) for v in outcomes})!=len(outcomes):raise ValueError('distinct possible outcomes required')
  C.integer(choose,'selected GM outcome index',0,len(outcomes)-1)
  pay(se,c,REALITY,'free',quota={'kind':'daily','uses':1})
  outcome=deepcopy(outcomes[choose]);result=apply_outcome(se,c,event['id'],outcome)
  if isinstance(result,C.PendingDecision) or result is None:raise ValueError('actual in-world event must consume its selected outcome')
  se.gm._rec('Reality Bender '+event['id'],event,{'selected':outcome,'result':result,'source_variant':source},event['reason'],c)
  return {'source':REALITY,'source_variant':source,'event_id':event['id'],'selected':outcome,'result':result}
 return G.transition(e,a,apply,include_rulings=True,include_grid=e.grid is not None)


def reality_item(e,a,item_id,target=None,*,instance_id,provide,source='core',**options):
 """Create one actual needed item and consume it in the same native operation."""
 require(e,a,REALITY);target=target or a;W.require_actors(e,target)
 if source not in ('core','local_csv515') or not callable(provide):raise ValueError('actual GM need/common-item provider and explicit source required')
 if any(k in options for k in ('held_selection','count','free','container_selection')):raise ValueError('one immediately consumed created item required')
 G._text(instance_id,'Reality Bender physical identity')
 def apply(se,c,t):
  import item_stock as STOCK,items as I
  admission=provide(se,c,t,item_id)
  if type(admission)is not dict or set(admission)!={'common','normally_possessed','needed_now','reason'} or any(admission[k]is not True for k in ('common','normally_possessed','needed_now')):raise ValueError('GM confirms common normally possessed item needed now')
  G._text(admission['reason'],'GM immediate item need')
  effects,header=se.r.item_effects(item_id);price=header.get('price')
  C.integer(price,'actual common item price',0,250 if source=='core' else 800)
  if STOCK.prepare(se,c,item_id,allow_empty=True) is not None:raise ValueError('Reality Bender requires none of the needed item available')
  if any(obj.get('owner_id')==c.entity_id and obj.get('item_rule_id')==item_id and not any(W.physical_lifecycle(obj)[k] for k in ('consumed','destroyed')) for obj in getattr(se,'_physical_objects',{}).values()):raise ValueError('an actual needed physical item remains available')
  if instance_id in W.entity_index(se):raise ValueError('new unique Reality Bender item identity required')
  pay(se,c,REALITY,'free',quota={'kind':'daily','uses':1})
  W.register_object(se,instance_id,location=W.location_of(c),reason=admission['reason'],kind='item_instance',item_rule_id=item_id,owner_id=c.entity_id,source=REALITY)
  obj=se._physical_objects[instance_id];obj['reality_bender']={'creator_id':c.entity_id,'source_variant':source,'need':deepcopy(admission),'immediate_use':True}
  I.equip_held(se,c,item_id,source_instance_id=instance_id)
  result=se.use_item(c,item_id,t,held_selection=instance_id,**options)
  if not W.physical_lifecycle(se._physical_objects[instance_id])['consumed']:raise ValueError('created item must be consumed immediately and cannot be stored')
  return {'source':REALITY,'source_variant':source,'instance_id':instance_id,'item_id':item_id,'result':result}
 return G.transition(e,a,apply,participants=(target,),include_rulings=True,include_grid=e.grid is not None)


def validate_world(e,index):
 for a in index.values():
  if CHOICE in a.spec and not getattr(e,'_warper_transfer',False):raise ValueError('transient Warper transfer choice escaped its native activation')
  for row in TIME.records(a):
   if 'warped_transmission' in row and (row.get('source')!=WARPED or row.get('evasion_modifier')!=-3 or row.get('count_deadline')!=(row['warped_transmission']['round']+1,row['warped_transmission']['count'])):raise ValueError('Warped Transmission full-round evasion lifetime changed')
   if 'warped_shift_protection' in row and (row.get('source')!=WARPED or row.get('turn_owner') is not index.get(row['warped_shift_protection']['actor_id'])):raise ValueError('Warped Transmission must retain its actual next-turn owner')
 for obj in getattr(e,'_physical_objects',{}).values():
  if 'reality_bender' in obj and not W.physical_lifecycle(obj)['consumed']:raise ValueError('Reality Bender cannot retain an unconsumed item for later')
 return True


def teleport_aoo_policy(e):
 return {'authority':'adopted_dataninja_faq_p18','teleport_provokes':False,'official_playtest':False,
  'historical_test':'MovementTests.test_teleport_leaving_adjacency_uses_existing_real_opportunity_attack'}


def arm_probability(e,a,target,*,purpose,decision,reroll_fixed=None):
 policy(e)
 W.require_actors(e,a,target)
 if not __import__('ability_transitions').active(a,PROBABILITY):raise ValueError('actual Probability Control Ability required')
 if target is not a and (not a.side or a.side!=target.side):raise ValueError('Probability Control only observes self or ally rolls')
 G._text(purpose,'actual native roll purpose')
 if not callable(decision):raise ValueError('actual observed-roll choice callback required')
 if not F.activation_allowed(a,PROBABILITY,{'kind':'scene','uses':1},engine=e):raise ValueError('Probability Control Scene frequency exhausted')
 # Live callbacks follow the existing save contract: data saves require fresh
 # authentication. The native consumer removes this offer before rolling again.
 e._native_roll_decisions={**getattr(e,'_native_roll_decisions',{}),a.entity_id:decision}
 return G.transition(e,a,lambda se,c:c.spec.update(native_roll_offer={'actor_id':target.entity_id,'purpose':purpose,'source':PROBABILITY,'fixed':deepcopy(reroll_fixed)}))


def _require_probability_provider(e,owner,target):
 W.require_actors(e,owner,target)
 if not __import__('ability_transitions').active(owner,PROBABILITY) or target is not owner and (not owner.side or target.side!=owner.side):raise ValueError('native reroll lost its actual self/ally provider')
 if not F.activation_allowed(owner,PROBABILITY,{'kind':'scene','uses':1},engine=e):raise ValueError('Probability Control Scene frequency exhausted')


def reroll(e,a,purpose,first,roll_again):
 for owner in W.actor_index(e).values():
  offer=owner.spec.get('native_roll_offer')
  if not offer:continue
  uid=owner.entity_id
  if offer['actor_id']!=a.entity_id or offer['purpose']!=purpose:continue
  _require_probability_provider(e,owner,a)
  callback=getattr(e,'_native_roll_decisions',{}).get(uid)
  if not callable(callback):raise ValueError('native reroll observation requires fresh live choice authentication after load')
  e._native_roll_deciding=True
  try:decision=callback(deepcopy(first))
  finally:e.__dict__.pop('_native_roll_deciding',None)
  if type(decision)is not bool:raise ValueError('observed native reroll choice must be explicit')
  owner.spec.pop('native_roll_offer')
  if not decision:return first
  _require_probability_provider(e,owner,a)
  result=roll_again(offer['fixed'])
  # A triggered Free action may occur inside an already issued damage receipt.
  # Authenticate that exact parent before paying, then retain only the one
  # additional action actually recorded by this source; no new attack epoch.
  import heavy_injury_adapter as HEAVY
  parents=[(token,row) for token,row in e._heavy_native_receipts.items() if row['attacker'] is owner]
  for token,row in parents:HEAVY.validate_native_receipt(e,token,owner,row['target'],{'id':row['move_id']})
  history=list(getattr(owner,'_action_history',[]));epoch=e._heavy_activation_sequence
  pay(e,owner,PROBABILITY,'free',quota={'kind':'scene','uses':1},triggered=True)
  if parents and (owner._action_history!=history+['free'] or e._heavy_activation_sequence!=epoch):raise ValueError('Probability Control must add only its actual triggered Free action')
  for token,row in parents:
   if e._heavy_native_receipts.get(token)is not row or row['history_length']!=len(history):raise ValueError('native Probability Control parent receipt changed')
   row['history_length']=len(owner._action_history)
  __import__('telepath').residue(e,owner,a,PROBABILITY,'native_roll:'+purpose)
  e.log('Probability Control: '+a.name+' '+purpose+' rerolled',PROBABILITY)
  return result
 return first


def discover_residue(e,observer,*,reason,observe):
 """A GM/perception observer discovers the existing live Psychic trace."""
 W.require_actors(e,observer);G._text(reason,'actual Psychic trace observation')
 if not callable(observe):raise ValueError('actual perception observation provider required')
 found=[]
 for target in W.actor_index(e).values():
  for effect in __import__('telepath').live(target,'psychic_residue'):
   answer=observe(e,observer,target,deepcopy(effect))
   if type(answer)is not bool:raise ValueError('explicit Psychic residue perception result required')
   if answer:found.append({'instance_id':effect['id'],'source':effect['source'],'actor_id':effect['effect']['caster_id'],'target_id':target.entity_id})
 e.gm._rec('Psychic residue discovery',None,found,reason,observer)
 return found


MOVES={TELEPORT:727,SWITCH:662,COAT:693}


def switch_interested(e,attacker,target):
 import combat_move_reactions as R
 for a in W.actor_index(e).values():
  choice=a.spec.get(R.CHOICES,{}).get(SWITCH)
  if choice and e._active_turn_actor is not None and a.side and e._active_turn_actor.side!=a.side and attacker is not a and attacker.side!=a.side and target.entity_id in (a.entity_id,choice['ally_id']) and R._ready(e,a,SWITCH):return True
 return False


def switch_choice(e,a,ally,willing,warped):
 W.require_actors(e,a,ally)
 if type(warped)is not bool:raise ValueError('explicit Warped Transmission choice required')
 if ally is a or willing is not True or not a.side or ally.side!=a.side:raise ValueError('actual willing ally required')
 distance=W.distance_known(a,ally)
 if distance is None or distance>6:raise ValueError('Ally Switch requires an ally within six metres range')
 if warped:require(e,a,WARPED)
 return {'target_id':a.entity_id,'warper':True,'ally_id':ally.entity_id,'willing':True,'warped':warped}


def direct_switch_choice(e,a):
 row=getattr(e,'_warper_switch',None)
 return row['choice'] if row and row['actor_id']==a.entity_id else None


def ally_switch(e,a,ally,*,willing,warped=False):
 """Ordinary own-turn Standard Move; its printed Interrupt is additional permission."""
 __import__('priority_actions')._owned_move(e,a,SWITCH)
 choice=switch_choice(e,a,ally,willing,warped)
 if not F.move_allowed(e,a,SWITCH,outside_combat=not e.encounter_active)[0]:raise ValueError('Ally Switch Scene frequency exhausted')
 if e.encounter_active and e._active_turn_actor is not a:raise ValueError('ordinary Ally Switch requires own turn; use its actual foe-turn Interrupt otherwise')
 def apply(se,c,t):
  if getattr(se,'_warper_switch',None):raise ValueError('one actual Ally Switch selection at a time')
  positions=(c.pos,t.pos);se._warper_switch={'actor_id':c.entity_id,'choice':deepcopy(choice)}
  try:
   se.use_move(c,c,SWITCH)
   if (c.pos,t.pos)!=(positions[1],positions[0]):raise ValueError('actual ordinary Ally Switch Move must exchange the chosen pair')
   return {'source':SWITCH,'position':c.pos,'ally_position':t.pos}
  finally:se.__dict__.pop('_warper_switch',None)
 return G.transition(e,a,apply,participants=(ally,),include_grid=e.grid is not None)


def mechanics(r,mid,mm):
 if mid not in MOVES:return mm
 if r.move(mid)['_source']['record_span']!=[MOVES[mid]]*2:raise ValueError('selected printed Psychic Move source changed')
 return dict(mm,effects_exec=[x for x in mm.get('effects_exec',[]) if x.get('type')=='grant_capability'])


def arm_move(e,a,mid,*,ally=None,willing=False,destination=None,surface_contact=None,reason=None,warped=False):
 import combat_move_reactions as R,priority_actions as P
 W.require_actors(e,a);P._owned_move(e,a,mid)
 if mid not in MOVES:raise ValueError('actual supported Psychic Interrupt Move required')
 if type(warped)is not bool or warped and mid!=SWITCH:raise ValueError('Warped Transmission only follows Ally Switch or actual Teleporter')
 choice={'target_id':a.entity_id,'warper':True}
 if mid==SWITCH:
  choice=switch_choice(e,a,ally,willing,warped)
 elif mid==TELEPORT:
  plan=__import__('movement_actions').teleport_plan(e,a,destination,surface_contact=surface_contact,reason_text=reason)
  if isinstance(plan,C.PendingDecision):return plan
  choice['plan']=plan
 if warped:require(e,a,WARPED)
 return G.transition(e,a,lambda se,c:c.spec.setdefault(R.CHOICES,{}).update({mid:deepcopy(choice)}))


def resolve_self_move(e,a,mid):
 """Effects of the actual paid native Move, never an effects[] declaration."""
 import movement_actions as M,combat_move_reactions as R
 event=R.current(e,a,mid)
 choice=event.get('warper_choice') if event else direct_switch_choice(e,a) if mid==SWITCH else None
 if mid==TELEPORT:
  plan=choice['plan'] if choice else a.spec.get('warper_move_destination')
  if plan is None:raise ValueError('Teleport Move needs its actual chosen legal destination')
  M.follow_paid_transfer(e,a,plan)
 elif mid==SWITCH:
  if not choice:raise ValueError('Ally Switch requires its actual selected willing ally')
  ally=W.actor_index(e)[choice['ally_id']]
  if not choice['willing'] or ally.side!=a.side or W.distance_known(a,ally)>6:raise ValueError('Ally Switch actual willing ally within six metres required')
  M.exchange_positions(e,a,ally,source=SWITCH)
  if choice['warped']:warped_after(e,a,'ally_switch')
 elif mid==COAT:
  if not event:raise ValueError('Magic Coat requires its actual no-damage-dice incoming Move')
 return True


def native_move(fn):
 @wraps(fn)
 def run(e,a,t,mid,*args,**kwargs):
  import combat_move_reactions as R
  interested=mid in MOVES or any(x.spec.get('native_roll_offer') or any(m in MOVES for m in x.spec.get(R.CHOICES,{})) for x in W.actor_index(e).values())
  if not interested or getattr(e,'_reactive_move_transaction',False):return fn(e,a,t,mid,*args,**kwargs)
  def apply(se,c,target):
   payload=G._stage_transition_payload(e,se,{'args':args,'kwargs':kwargs})
   return fn(se,c,target,mid,*payload['args'],**payload['kwargs'])
  return __import__('reactive_ability_events').atomic_move(e,a,t,apply)
 return run


def reaction(e,args):
 """Respond to the actual accuracy boundary, then reuse native recipient routing."""
 if not args['hit']:return
 import combat_move_reactions as R,move_completion as MC
 attacker,target,move=(args[k] for k in ('attacker','target','move'))
 completion=e._move_completions[args['completion_id']]
 checked=completion.setdefault('warper_reaction_checked',[])
 if target.entity_id in checked:return
 checked.append(target.entity_id)
 for a in list(W.actor_index(e).values()):
  for mid,choice in list(a.spec.get(R.CHOICES,{}).items()):
   if mid not in MOVES or attacker is a or not R._ready(e,a,mid):continue
   if mid==SWITCH:
    if e._active_turn_actor is None or not a.side or e._active_turn_actor.side==a.side or attacker.side==a.side or target.entity_id not in (a.entity_id,choice['ally_id']):continue
   elif target is not a:continue
   if mid==COAT and move.get('damage_base') not in (None,'--','-',''):continue
   event=R._observe(e,a,mid,attacker,target,move,'warper_about_to_hit',completion['id'])
   event['warper_choice']=deepcopy(choice);R._seal(event)
   R._run(e,a,a,event)
   if mid==SWITCH:
    replacement=W.actor_index(e)[choice['ally_id']] if target is a else a
    __import__('move_defense_reactions').source_route(e,args,replacement,{'source':mid,'actor_id':a.entity_id,'reaction_id':event['id'],'response_completion':event['result_completion']})
   elif mid==TELEPORT:
    # Area aim is immutable, retained by the outer native producer.
    bound=getattr(e,'_telepath_area_cells',None)
    area=__import__('weapon_actions').range_spec(e,move,attacker).get('shape')
    if area and bound is None:raise ValueError('Teleport reaction requires immutable actual native area cells')
    remained=bool(__import__('body_state').cells(target,require_complete=True).intersection({tuple(x) for x in bound})) if area else False
    args['hit']=remained
   else:
    proof={'user_id':a.entity_id,'target_id':attacker.entity_id,'move_id':move['id'],'trigger_completion':completion['id'],'coat_completion':event['result_completion']}
    old=getattr(e,'_warper_reflection',None);e._warper_reflection=proof
    try:
     import action_lifecycle as ACTION
     before=set(e._move_completions)
     with ACTION.move_grant(e,a,attacker,move['id'],source=COAT,kind='free') as grant:e.use_move(a,attacker,move['id'],count_use=False,free_action=True,_action_grant=grant)
     children=[r for k,r in e._move_completions.items() if k not in before and r['actor']is a and r['move_id']==move['id']]
     if len(children)!=1 or children[0]['phase']!='complete':raise ValueError('Magic Coat reflected Move must actually finish with reversed user and target')
     proof['result_completion']=children[0]['id'];completion['warper_reflection']=proof
    finally:
     if old is None:e.__dict__.pop('_warper_reflection',None)
     else:e._warper_reflection=old
    args['hit']=False
   return


def move_authority(e,a,target,mid,source):
 proof=getattr(e,'_warper_reflection',None)
 if source!=COAT:return False
 if not proof or (proof['user_id'],proof['target_id'],proof['move_id'])!=(a.entity_id,target.entity_id,mid):raise ValueError('Magic Coat only reflects its actual original Move and user')
 original=e._move_completions[proof['trigger_completion']];coat=e._move_completions[proof['coat_completion']]
 if original['actor']is not target or coat['actor']is not a or coat['move_id']!=COAT or coat['phase']!='complete' or original['move'].get('damage_base') not in (None,'--','-',''):raise ValueError('Magic Coat actual no-damage-dice source required')
 return True
