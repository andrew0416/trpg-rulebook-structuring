"""Book Channeler adapters; connections, observations, effects and resources keep their native owners."""
from copy import deepcopy
import common_checks as C
import state_grants as G
import world_entities as W
import frequency as F
import combat_timing as TIME

CLASS='class/교감자';SENSES='feat/감각-공유';SYNC='feat/전투-동기화';SPIRIT='feat/스피릿-부스트'
CONDUIT='feat/힘의-전달';PAIN='feat/고통-약화';SOOTHE='feat/완화하는-연결'
SOURCE_SHA256='a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'
FEATURES={CLASS:(2834,2837),SENSES:(2839,2843),SYNC:(2845,2849),SPIRIT:(2851,2861),CONDUIT:(2863,2870),PAIN:(2872,2876),SOOTHE:(2878,2882)}
DEFINITIONS={u:{'span':list(span),'catalog_span':[2822,2822] if u==CLASS else list(span),
 'clause_id':'C04-106' if u==CLASS else 'C04-107' if u==SENSES else 'input/ch04-trainer-classes.md:'+str(span[0])+'-'+str(span[1]),
 'parent':None if u==CLASS else PAIN if u==SOOTHE else CLASS,
 'minimum_rank':6 if u==SOOTHE else 5 if u==PAIN else 4 if u==CONDUIT else 3 if u==CLASS else 0} for u,span in FEATURES.items()}
STATS=('atk','def','spa','spd','spe')


def records(actor,feature=None,active=False):
 import trainer_feature_acquisition as T
 return [r['static_acquisition'] for _,r,live in T._static_records(actor) if r['static_acquisition']['feature_id'] in FEATURES
  and (feature is None or r['static_acquisition']['feature_id']==feature) and (not active or live)]


def acquired(actor,feature=CLASS):
 rows=records(actor,feature,True)
 return rows[-1] if rows else None


def acquisition_snapshot(e,actor,feature):
 import skill_modifiers as SK,elemental_connection as ELEMENTAL
 ELEMENTAL.choices(e,actor)
 parent=DEFINITIONS[feature]['parent']
 return {'rank':SK.rank(e.r,actor,'직감')[2],
  'parents':[r['request_id'] for r in records(actor,parent,True)] if parent else [],
  'mystic':sum(ELEMENTAL.matches(x,ELEMENTAL.MYSTIC) for field in ('edges','feats') for x in actor.spec.get(field,[]))}


def qualification(actor,feature,snapshot,prerequisite_source):
 import acquisition_qualification as Q
 if prerequisite_source is not None or type(snapshot)is not dict or set(snapshot)!={'rank','parents','mystic'}:raise ValueError('exact Channeler acquisition observations required')
 C.integer(snapshot['rank'],'actual Intuition prerequisite rank',1);C.integer(snapshot['mystic'],'actual Mystic Senses acquisitions',0,1)
 parent=DEFINITIONS[feature]['parent'];known={r['request_id'] for r in records(actor,parent)} if parent else set()
 return Q.require(feature,'native','acquire',[
  Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),
  Q.check('parent','prerequisite',snapshot['mystic']==1 if feature==CLASS else bool(snapshot['parents']) and set(snapshot['parents'])<=known,'actual Mystic Senses or acquired Channeler parent required'),
  Q.check('rank','prerequisite',snapshot['rank']>=DEFINITIONS[feature]['minimum_rank'],'printed Intuition rank required')])


def require(e,actor,feature):
 W.require_actors(e,actor)
 if e.r._selected_rule(feature)!=feature or acquired(actor,feature)is None:raise ValueError('actual acquired Channeler Feature required: '+feature)
 __import__('trainer_feature_acquisition').validate_actor(actor)
 if getattr(e,'_league_runtime',None)is not None:raise ValueError('Channeling is not League Legal')


def rank(e,actor):return __import__('skill_modifiers').effective_rank(e.r,actor,'직감')


def pay(e,actor,source,action,ap=0,quota=None):
 import action_points as AP,turn as TURN
 if AP.available(actor)<ap:raise ValueError('Channeler requires available AP')
 if quota and not F.activation_allowed(actor,source,quota,engine=e):raise ValueError('Channeler frequency exhausted')
 if not TURN.spend(e,actor,action,source):raise ValueError('Channeler requires its available '+action+' action')
 if ap:AP.charge(actor,ap)
 if quota:F.consume_activation(actor,source,quota,engine=e)


def policy(rules):
 return {'declaration':{'id':'native:'+CLASS,'source':CLASS,'capabilities':[],'requirements':[],
  'mode':'aura','range':{'metric':'chebyshev','maximum':20},'path':None,'medium':[],'consent':{'kind':'none'},'blockers':[],
  'connection':{'maximum':{'skill':'직감','effective':True},'lifetime':{}},
  'frequency':{'kind':'at_will','uses':1},'retry':None,'distance_exceptions':[]}}


def raw_link(e,actor,target):
 import perception_communicate as COMM
 return COMM._state(e)['connections'].get(COMM._pair(CLASS,actor.entity_id,target.entity_id))


def imprints(actor):return [row for row in TIME.records(actor) if row.get('channel_imprint')]


def imprint_for(e,owner,target):
 return next((row for row in imprints(target) if row['channel_imprint']['owner_id']==owner.entity_id),None)


def link_ending(e,actor,target,row):
 if acquired(actor)is None:return 'source_lost'
 if actor.fainted or actor.hp<=0:return 'channeler_fainted'
 if target.dead or target.captured:return 'target_unavailable'
 if imprint_for(e,actor,target)is None:
  a=W.effective_location(e,actor);b=W.effective_location(e,target)
  if a['kind']=='grid' and b['kind']=='grid':
   if a.get('map_id')!=b.get('map_id') or W.distance_known({'location':a},{'location':b})>20:return 'channel_distance'
 return None


def connected(e,actor,target):
 row=raw_link(e,actor,target)
 return row is not None and row['status']=='live' and link_ending(e,actor,target,row)is None


def participants(e,actor):
 return [c for c in W.actor_index(e).values() if c.kind=='pokemon' and connected(e,actor,c)]


def target(e,actor,pokemon):
 W.require_actors(e,actor,pokemon)
 if pokemon.kind!='pokemon' or not connected(e,actor,pokemon):raise ValueError('actual Channeled Pokemon required')
 return pokemon


def channel(e,actor,pokemon,*,roll_options=None):
 require(e,actor,CLASS);W.require_actors(e,actor,pokemon)
 if pokemon.kind!='pokemon' or pokemon.dead or pokemon.captured:raise ValueError('actual available Pokemon required')
 import pokemon_entities as P,perception_communicate as COMM
 disposition=P.disposition_projection(pokemon,'trainer:'+actor.entity_id)
 if not disposition['known']:raise ValueError('actual Pokemon disposition toward the Channeler required')
 if connected(e,actor,pokemon):raise ValueError('Pokemon is already Channeled')
 if len(participants(e,actor))>=rank(e,actor):raise ValueError('Channeler Intuition connection limit reached')
 a=W.effective_location(e,actor);b=W.effective_location(e,pokemon)
 if a['kind']!='grid' or b['kind']!='grid' or a.get('map_id')!=b.get('map_id'):raise ValueError('observed actual Channeling distance required')
 if W.distance_known({'location':a},{'location':b})>20:raise ValueError('Channeling requires target within twenty metres')
 hostile=disposition['value'] in ('매우 적대적','적대적')
 if roll_options and not hostile:raise ValueError('nonhostile Channeling has no Intuition check')
 def apply(staged,c,p):
  pay(staged,c,CLASS,'swift');check=None
  if hostile:
   options={} if roll_options is None else deepcopy(roll_options)
   if set(options)-{'fixed','roll_id'}:raise ValueError('native Channeling roll options only')
   check=staged.skill_check(c,'직감',15,skill_target=p,**options)
   if not check[0]:return {'source':CLASS,'status':'failed','check':check}
  link=COMM.establish(staged,c,p,policy(staged.r)['declaration'])
  return {'source':CLASS,'status':'channeled','link':deepcopy(link),'check':check,'knowledge':__import__('perception_observe').channel_information(staged,p)}
 return G.transition(e,actor,apply,participants=(pokemon,))


def stop(e,actor,pokemon):
 require(e,actor,CLASS);target(e,actor,pokemon)
 def apply(staged,c,p):
  import action_lifecycle as ACTION,perception_communicate as COMM
  ACTION.triggered_free_action(staged,c,CLASS)
  return COMM.disconnect(staged,c,p,CLASS,reason='Channeler freely ends Channeling')
 return G.transition(e,actor,apply,participants=(pokemon,))


def link_closed(e,actor,target,reason):
 row=imprint_for(e,actor,target)
 if row:TIME.expire(e,target,row,ending='ended',event={'kind':'channel_ended','reason':reason})
 for focus in list(TIME.records(actor)):
  if focus.get('channel_focus',{}).get('target_id')==target.entity_id:TIME.expire(e,actor,focus,ending='channel_ended')


def imprint_ended(e,pokemon,record):
 owner=W.actor_index(e)[record['channel_imprint']['owner_id']]
 for row in list(TIME.records(owner)):
  if row.get('channel_focus',{}).get('target_id')==pokemon.entity_id:TIME.expire(e,owner,row,ending='imprint_ended')
 __import__('perception_communicate').boundary(e,'reconcile')


def communicate(e,sender,recipient,fields,*,request_id):
 W.require_actors(e,sender,recipient)
 owner,other=(sender,recipient) if sender.kind=='trainer' else (recipient,sender)
 require(e,owner,CLASS);target(e,owner,other)
 if type(fields)is not list or not fields or len(set(fields))!=len(fields) or not set(fields)<={'intentions','emotions','motivations'}:raise ValueError('Channeling communicates only actual intentions, emotions and motivations')
 facts=__import__('perception_observe').channel_information(e,sender)
 message={field:facts[field] for field in fields}
 return __import__('perception_communicate').publish_linked(e,sender,recipient,CLASS,message,request_id=request_id)


def validate_result(e,result):
 if result.get('operation')!='linked_information' or type(result.get('message'))is not dict:raise ValueError('actual Channeler information exchange required')
 payload=result['message'].get('information')
 if type(payload)is not dict or not payload or not set(payload)<={'intentions','emotions','motivations'}:raise ValueError('Channeler information rights changed')


def imprint_payload(e,actor,pokemon,effect,source):
 if source!=SENSES or effect.get('type')!='channel_imprint' or effect.get('owner_id')!=actor.entity_id:raise ValueError('actual Shared Senses producer required')
 if acquired(actor,SENSES)is None or pokemon.kind!='pokemon':raise ValueError('actual acquired Shared Senses and Pokemon required')
 return {'owner_id':actor.entity_id,'target_id':pokemon.entity_id,'acquisition_request':acquired(actor,SENSES)['request_id']}


def preflight_imprint(e,actor,pokemon,effect,source):
 payload=imprint_payload(e,actor,pokemon,effect,source)
 if getattr(e,'_channel_imprint_admission',None)!=(actor.entity_id,pokemon.entity_id):raise ValueError('Shared Senses requires its actual Bound AP producer')
 target(e,actor,pokemon)
 if imprint_for(e,actor,pokemon):raise ValueError('Pokemon is already Imprinted by this Channeler')
 return payload


def imprint(e,actor,pokemon):
 require(e,actor,SENSES);target(e,actor,pokemon)
 if imprint_for(e,actor,pokemon):raise ValueError('Pokemon is already Imprinted by this Channeler')
 def apply(staged,c,p):
  import bound_ap as BOUND
  pay(staged,c,SENSES,'swift')
  instance=G.effect_source(c,{'source_id':SENSES+':'+c.entity_id},'channel-imprint')
  effect={'type':'channel_imprint','owner_id':c.entity_id,'target':'target','while':{'owner':'target','communication_source':CLASS,'sender_id':c.entity_id}}
  staged._channel_imprint_admission=(c.entity_id,p.entity_id)
  try:result=BOUND.activate_effects(staged,c,p,instance,amount=1,effects=[effect],ending_method='specified',source_ref=SENSES)
  finally:del staged._channel_imprint_admission
  return {'source':SENSES,'instance':instance,'status':result.status}
 return G.transition(e,actor,apply,participants=(pokemon,))


def release_imprint(e,actor,pokemon):
 require(e,actor,SENSES)
 W.require_actors(e,actor,pokemon)
 row=imprint_for(e,actor,pokemon)
 if row is None:raise ValueError('actual Shared Senses imprint required')
 def apply(staged,c,p):
  pay(staged,c,SENSES,'free')
  TIME.expire(staged,p,imprint_for(staged,c,p),ending='ended',event={'kind':'manual_bound_ap_release'})
  return {'source':SENSES,'target_id':p.entity_id,'released_ap':1}
 return G.transition(e,actor,apply,participants=(pokemon,))


def focus(e,actor,pokemon):
 require(e,actor,SENSES);target(e,actor,pokemon)
 if imprint_for(e,actor,pokemon)is None:raise ValueError('actual Imprinted Pokemon required')
 period=['round',e.round_no] if e.encounter_active else ['seconds',e.elapsed_seconds//10]
 old=next((row for row in TIME.records(actor) if row.get('channel_focus_selection')),None)
 if old and old['channel_focus_selection']['period']==period and old['channel_focus_selection']['target_id']!=pokemon.entity_id:
  raise ValueError('Shared Senses permits one selected Pokemon per round')
 def apply(staged,c,p):
  for row in list(TIME.records(c)):
   if row.get('channel_focus') or row.get('channel_focus_selection'):TIME.expire(staged,c,row,ending='focus_changed')
  value={'target_id':p.entity_id,'period':period}
  TIME.install(staged,c,{'source':SENSES,'channel_focus_selection':deepcopy(value),'manual_end':True})
  TIME.install(staged,c,{'source':SENSES,'channel_focus':value,'manual_end':True})
  return deepcopy(value)
 return G.transition(e,actor,apply,participants=(pokemon,))


def read_senses(e,actor):
 require(e,actor,SENSES)
 row=next((r for r in TIME.records(actor) if r.get('channel_focus')),None)
 if row is None:raise ValueError('select one actual Imprinted Pokemon to concentrate on')
 pokemon=W.actor_index(e)[row['channel_focus']['target_id']];target(e,actor,pokemon)
 if imprint_for(e,actor,pokemon)is None:raise ValueError('focused Pokemon is no longer Imprinted')
 return __import__('perception_observe').channel_information(e,pokemon,sensory=True)



def synchronize(e,actor):
 require(e,actor,SYNC)
 chosen=participants(e,actor)
 if not chosen:raise ValueError('Battle Synchronization requires actual Channeled Pokemon')
 if any(row.get('channel_sync') is not None for row in TIME.records(actor)):raise ValueError('Battle Synchronization is already active')
 count=TIME.current(e)
 def apply(staged,c,*pokemon):
  pay(staged,c,SYNC,'standard',quota={'kind':'scene','uses':3})
  TIME.install(staged,c,{'source':SYNC,'channel_sync':{},'channel_sync_hits':[],
   'count_deadline':(staged.round_no+1,count),'encounter_end':True,'acquisition_request':acquired(c,SYNC)['request_id']})
  __import__('cheerleader').complete_native_order(staged,c,list(pokemon),SYNC)
  return {'source':SYNC,'targets':[p.entity_id for p in pokemon]}
 return G.transition(e,actor,apply,participants=chosen,include_rulings=True)


def hit(e,pokemon,foe,identity):
 if pokemon.kind!='pokemon' or not getattr(pokemon,'side',None) or not getattr(foe,'side',None) or pokemon.side==foe.side:return
 for owner in W.actor_index(e).values():
  if owner.kind!='trainer' or not connected(e,owner,pokemon):continue
  for row in TIME.records(owner):
   if row.get('channel_sync') is None or identity in row['channel_sync_hits']:continue
   if acquired(owner,SYNC)is None:continue
   row['channel_sync_hits'].append(identity)
   row['channel_sync'][foe.entity_id]=row['channel_sync'].get(foe.entity_id,0)+1


def completion_hit(e,row,original):
 import move_completion as COMPLETE
 for recipient in COMPLETE.actual_recipients(row):
  if recipient.entity_id!=original.entity_id and original.entity_id not in row.get('defense',{}):continue
  try:result=COMPLETE.recipient_result(row,recipient)
  except KeyError:continue
  if result and result['hit'] and not result['cancelled'] and not result.get('hit_prevented'):
   hit(e,row['actor'],recipient,'move:'+row['id']+':'+recipient.entity_id)


def synchronized_bonus(e,pokemon,foe):
 if pokemon.kind!='pokemon' or not getattr(pokemon,'side',None) or not getattr(foe,'side',None) or pokemon.side==foe.side:return 0
 return sum(row['channel_sync'].get(foe.entity_id,0) for owner in W.actor_index(e).values()
  if owner.kind=='trainer' and connected(e,owner,pokemon) and acquired(owner,SYNC)
  for row in TIME.records(owner) if row.get('channel_sync') is not None)


def intercept_permitted(e,pokemon,ally):
 return ally.kind=='pokemon' and any(owner.kind=='trainer' and connected(e,owner,pokemon) and connected(e,owner,ally) for owner in W.actor_index(e).values())


def spirit(e,actor,pokemon,donor,*,stat=None):
 require(e,actor,SPIRIT);target(e,actor,pokemon);target(e,actor,donor)
 values={s:donor.staged(s) for s in STATS};best=[s for s in STATS if values[s]==max(values.values())]
 if stat is None and len(best)==1:stat=best[0]
 if stat not in best:raise ValueError('choose one actual highest non-HP Combat Stat, explicitly on a tie')
 import class_passive_combat as P,cheerleader as CHEER
 @CHEER.order_activation(SPIRIT)
 def apply(staged,c,p,d):
  if not staged.encounter_active or not p.on_field or p.fainted or p.captured:raise ValueError('available encounter Stratagem target required')
  P._require_stratagem_slot(p)
  __import__('temporary_ap').preflight_binding(c,2,'class_passive_combat')
  if __import__('action_points').available(c)<2:raise ValueError('Spirit Boost requires two available AP')
  pay(staged,c,SPIRIT,'standard')
  state=P._state(p,create=True);state['serial']+=1
  instance='class-passive:'+c.entity_id+':channeler:'+str(state['serial'])
  while instance in c.ap_account.identified_bindings(allow_missing=True):
   state['serial']+=1;instance='class-passive:'+c.entity_id+':channeler:'+str(state['serial'])
  c.ap_account.charge(2,mode='bind',instance_id=instance,temporary_binding_owner='class_passive_combat')
  choice={'donor_id':donor.entity_id,'stats':values,'selected':stat,'at':staged.elapsed_seconds}
  choice['integrity']=__import__('resolution_transaction').request_fingerprint(choice)
  row={'owner_id':c.entity_id,'target_id':p.entity_id,'instance':instance,'rule_id':SPIRIT,
   'clause_id':DEFINITIONS[SPIRIT]['clause_id'],'acquisition_source':acquired(c,SPIRIT)['request_id'],
   'channeler_choice':choice,'lifetime':'sustained_2_ap_encounter'}
  state['sustains'][SPIRIT]=row
  G._source(p,instance,P.KIND,owner_id=c.entity_id,lifetime=row['lifetime'],rule_id=SPIRIT,
   clause_id=row['clause_id'],acquisition_source=row['acquisition_source'],sustain=True,tutor_points=0,channeler_choice=deepcopy(choice))
  return (1,0)
 return G.transition(e,actor,apply,participants=(pokemon,donor),include_rulings=True)


def validate_spirit(rules,row):
 __import__('trainer_feature_acquisition')._static_source(rules,SPIRIT)
 choice=row.get('channeler_choice')
 if type(choice)is not dict or set(choice)!={'donor_id','stats','selected','at','integrity'}:raise ValueError('actual Spirit Boost selected-stat evidence required')
 if choice['integrity']!=__import__('resolution_transaction').request_fingerprint({k:v for k,v in choice.items() if k!='integrity'}):raise ValueError('Spirit Boost selection evidence changed')
 if type(choice['stats'])is not dict or set(choice['stats'])!=set(STATS) or any(type(v)is not int or v<1 for v in choice['stats'].values()):raise ValueError('five actual non-HP Combat Stats required')
 if choice['selected'] not in STATS or choice['stats'][choice['selected']]!=max(choice['stats'].values()):raise ValueError('Spirit Boost must select a highest Combat Stat')
 if row.get('clause_id')!=DEFINITIONS[SPIRIT]['clause_id']:raise ValueError('Spirit Boost source changed')


def spirit_bonus(e,pokemon,kind,move=None):
 active=__import__('class_passive_combat')._active(e,pokemon,SPIRIT)
 if active is None:return 0
 owner,row=active;stat=row['channeler_choice']['selected'];damage_class=None if move is None else move.get('class')
 if kind=='initiative' and stat=='spe':return rank(e,owner)
 if kind=='damage' and (stat,damage_class) in (('atk','물리'),('spa','특수')):return rank(e,owner)
 if kind=='reduction' and (stat,damage_class) in (('def','물리'),('spd','특수')):return rank(e,owner)
 return 0


def conduit(e,actor,first,second,*,mode,stat=None,coat_id=None,give_move=None,restore_move=None):
 require(e,actor,CONDUIT);target(e,actor,first);target(e,actor,second)
 if first is second:raise ValueError('Power Conduit requires two distinct Channeled Pokemon')
 if mode not in ('stages','coat','move'):raise ValueError('choose one printed Power Conduit effect')
 if mode=='stages':
  if stat not in STATS or any(v is not None for v in (coat_id,give_move,restore_move)):raise ValueError('Power Conduit swaps one non-HP Combat Stage')
  __import__('combat_stage_sources').prepare_assignment(first,{stat:second.stages[stat]});__import__('combat_stage_sources').prepare_assignment(second,{stat:first.stages[stat]})
 elif mode=='coat':
  if any(v is not None for v in (stat,give_move,restore_move)):raise ValueError('Power Conduit Coat transfer has no other choice')
  __import__('coat_effects').preflight_one(e,first,second,coat_id,source=CONDUIT)
 else:
  if stat is not None or coat_id is not None:raise ValueError('Power Conduit Move recovery has no other choice')
  give_move=e.r.move_id(give_move);restore_move=e.r.move_id(restore_move)
  if give_move not in first.moves or restore_move not in second.moves:raise ValueError('actual known donor and recipient Moves required')
  if not __import__('perception_communicate')._willing(e,actor,first,CONDUIT):raise ValueError('actual willing Power Conduit donor required')
  if F.move_frequency(e,give_move,first)[0] not in ('scene','daily'):raise ValueError('donate one Scene or Daily Move use')
  F.preflight_forfeit_move(e,first,give_move,source=CONDUIT)
  if F.move_frequency(e,restore_move,second)[0]!='scene':raise ValueError('only an already used Scene Move can be restored')
  usage_owner=__import__('move_permissions').frequency_owner(e,second,restore_move)
  if usage_owner.move_uses.get(restore_move,0)<1 or not F.scene_move_was_used(usage_owner,restore_move):raise ValueError('recipient Scene Move must actually have been used')
  if not F.activation_allowed(second,CONDUIT,{'kind':'scene','uses':1},engine=e):raise ValueError('Power Conduit restores each Pokemon only once per Scene')
 def apply(staged,c,a,b):
  pay(staged,c,CONDUIT,'swift',2)
  if mode=='stages':
   import combat_stage_sources as CS
   left=CS.prepare_assignment(a,{stat:b.stages[stat]});right=CS.prepare_assignment(b,{stat:a.stages[stat]})
   CS.commit_assignment(a,left);CS.commit_assignment(b,right)
  elif mode=='coat':__import__('coat_effects').transfer_one(staged,a,b,coat_id,source=CONDUIT)
  else:
   F.forfeit_move(staged,a,give_move,source=CONDUIT)
   F.restore_scene_use(staged,b,restore_move);F.consume_activation(b,CONDUIT,{'kind':'scene','uses':1},engine=staged)
  return {'source':CONDUIT,'mode':mode,'from':a.entity_id,'to':b.entity_id}
 return G.transition(e,actor,apply,participants=(first,second))


def soothing(e,actor,allocation):
 require(e,actor,SOOTHE)
 if type(allocation)is not dict or not allocation or any(type(v)is not int or v<0 for v in allocation.values()) or sum(allocation.values())!=5:raise ValueError('distribute exactly five integral Soothing Connection points')
 index=W.actor_index(e);chosen=[]
 for uid in allocation:
  if uid not in index:raise ValueError('actual Channeled healing recipient required')
  chosen.append(target(e,actor,index[uid]))
 def apply(staged,c,*pokemon):
  pay(staged,c,SOOTHE,'standard',quota={'kind':'daily','uses':2})
  return {'source':SOOTHE,'healing':{p.entity_id:__import__('life').heal(staged,p,staged.tick(p)*allocation[p.entity_id],source_kind='feature') for p in pokemon}}
 return G.transition(e,actor,apply,participants=chosen)


def pain_interested(e,pokemon):
 return pokemon.kind=='pokemon' and any(c.kind=='trainer' and acquired(c,PAIN) and connected(e,c,pokemon) for c in W.actor_index(e).values())


def replace_attack(e,attacker,pokemon,amount,move,actual_type):
 if not pain_interested(e,pokemon) or move.get('class') not in ('물리','특수') or pokemon.fainted:return None
 import temporary_hp as HP,effects_ext as EXT,turn as TURN,action_lifecycle as ACTION
 HP.ensure_certain(e,pokemon)
 amount=EXT.cap_damage(e,pokemon,amount)
 remaining=max(0,amount-pokemon.temp_hp)
 proposed=__import__('endure').replace_hp(e,pokemon,pokemon.hp,pokemon.hp-remaining,source='attack_damage',loss_kind='damage',preview=True)
 if __import__('taskmaster').conscious(pokemon,hp=proposed):return None
 if actual_type!='None' and actual_type not in e.r.mech('combat/type-chart')['attack_vs_defense']:raise ValueError('Pain Dampening requires the actual resolved attack Type')
 for owner in W.actor_index(e).values():
  if owner.kind!='trainer' or acquired(owner,PAIN)is None or not connected(e,owner,pokemon) or not TURN.can_act(e,owner):continue
  if not F.activation_allowed(owner,PAIN,{'kind':'scene','uses':2},engine=e):continue
  choice=e.rulings.decide({'type':'pain_dampening','unit':PAIN,'actor':owner.name,'target':pokemon.name,
   'text':'Choose Channeled Pokemon including the triggering Pokemon to replace this damaging attack, or decline.',
   'trigger':{'attacker_id':attacker.entity_id,'target_id':pokemon.entity_id,'move_id':move['id'],'damage':amount,'actual_type':actual_type},
   'choices':[p.entity_id for p in participants(e,owner)]})
  if choice in (None,False):continue
  if type(choice)is not list or not choice or len(set(choice))!=len(choice) or pokemon.entity_id not in choice:raise ValueError('Pain Dampening must choose distinct Pokemon including its actual triggering Pokemon')
  index=W.actor_index(e)
  if any(uid not in index for uid in choice):raise ValueError('actual Pain Dampening recipients required')
  selected=[target(e,owner,index[uid]) for uid in choice]
  resisted=sum(e.type_multiplier(actual_type,p)[0]<1 for p in selected)
  loss=max(0,amount-resisted*rank(e,owner))//len(selected)
  ACTION.triggered_free_action(e,owner,PAIN);F.consume_activation(owner,PAIN,{'kind':'scene','uses':2},engine=e)
  before={p.entity_id:p.hp for p in selected}
  for p in selected:e.lose_hp(p,loss,source=PAIN)
  result={'source':PAIN,'owner_id':owner.entity_id,'trigger_id':pokemon.entity_id,'actual_type':actual_type,'original_damage':amount,
   'resistant_count':resisted,'intuition':rank(e,owner),'recipients':list(choice),'loss_each':loss,'before':before,'after':{p.entity_id:p.hp for p in selected}}
  e.gm._rec('Pain Dampening attack replacement',None,deepcopy(result),'actual damaging attack would faint a Channeled Pokemon',owner)
  return result
 return None


def withdraw(e,actor,feature):
 import perception_communicate as COMM,class_passive_combat as P
 for pokemon in W.actor_index(e).values():
  row=raw_link(e,actor,pokemon)
  if feature==CLASS and row and row['status']=='live':COMM._close(e,row,'source_lost')
  if feature==SENSES:link_closed(e,actor,pokemon,'source_lost')
  state=P._state(pokemon);spirit=None if state is None else state['sustains'].get(SPIRIT)
  if feature==SPIRIT and spirit and spirit['owner_id']==actor.entity_id:P._unbind(e,pokemon,SPIRIT,actor,spirit)
 if feature==SYNC:
  for row in list(TIME.records(actor)):
   if row.get('channel_sync') is not None:TIME.expire(e,actor,row,ending='source_lost')


def validate_world(e,index):
 for pokemon in index.values():
  for row in imprints(pokemon):
   value=row['channel_imprint'];owner=index.get(value.get('owner_id'))
   if owner is None or value.get('target_id')!=pokemon.entity_id or acquired(owner,SENSES)is None or value.get('acquisition_request')!=acquired(owner,SENSES)['request_id']:raise ValueError('actual acquired Shared Senses owner and target required')
   if not row.get('ap_binding') or row['ap_binding']['owner'] is not owner:raise ValueError('Shared Senses requires its actual one-AP binding')
  for row in TIME.records(pokemon):
   if row.get('channel_sync') is not None:
    if acquired(pokemon,SYNC)is None or row.get('acquisition_request')!=acquired(pokemon,SYNC)['request_id']:raise ValueError('Battle Synchronization acquisition changed')
    for uid,count in row['channel_sync'].items():
     if uid not in index:raise ValueError('actual synchronized foe required')
     C.integer(count,'actual synchronized hit count',1)
   if row.get('channel_focus'):
    uid=row['channel_focus']['target_id']
    if uid not in index or imprint_for(e,pokemon,index[uid])is None:raise ValueError('Shared Senses concentration requires an actual imprint')
 return True


def native_move(fn):
 from functools import wraps
 @wraps(fn)
 def run(e,attacker,target,*args,**kwargs):
  if not any(c.kind=='trainer' and acquired(c) for c in W.actor_index(e).values()) or getattr(e,'_reactive_move_transaction',False):return fn(e,attacker,target,*args,**kwargs)
  def staged(staged,a,t):
   payload=G._stage_transition_payload(e,staged,{'args':args,'kwargs':kwargs})
   return fn(staged,a,t,*payload['args'],**payload['kwargs'])
  return __import__('reactive_ability_events').atomic_move(e,attacker,target,staged)
 return run
