"""Restricted Standard-use consequence candidate; no generic action commit policy."""
import copy, random, re, math
from rulings import Rulings
import heavy_injury_adapter as H
import heavy_injury_kernel as K


def equipment_context(engine,actor):
 """The manual producer proves occurrence, this only bounds loss interactions."""
 failures=H.passive_prefix_failures(engine,actor,actor,require_actor_budget=True)
 from pathlib import Path
 if type(engine.r.root) is type(Path()) and engine.r.root.is_absolute():
  failures=[x for x in failures if x!='rules:nonpassive_state:root']
 if not engine.encounter_active or engine._active_turn_actor is not actor:
  failures.append('no_actual_own_combat_turn')
 for field in ('abilities','ability_triggers','buffs','coats','blessings','damage_cap','form_rule','form'):
  if getattr(actor,field,None):failures.append('actor:'+field)
 for field in ('feats','features','edges'):
  if actor.spec.get(field):failures.append('actor.spec:'+field)
 for owner in (engine.rulings,engine.r.rulings):
  if any(owner.hooks.values()) or any(getattr(owner,k,None) for k in ('formulas','mech','effects','provider')):
   failures.append('external_rule_observer')
 for name in ('log','lose_hp','marker_injuries','check_fainted'):
  if name in vars(engine):failures.append('overridden_engine_method:'+name)
 return failures


def finish_equipment(engine,actor,before,outcome,pre_context):
 """Finish an actually paid manual Standard, preserving ambiguous consequences.

 The caller commits this event with the equipment transaction, then raises
 HeavyPending outside it. A completed equip/give/drop is never erased or replayed
 to resolve an unchosen marker/fainting or resource-order interpretation.
 """
 import temporary_hp as TEMP
 import taskmaster as TASK
 if TASK.ignores_acting_loss(actor):return None
 TEMP.ensure_certain(engine,actor)
 after=H.observe(actor)
 failures=list(dict.fromkeys(pre_context+equipment_context(engine,actor)))
 if before!=after:failures.append('equipment_changed_actor_resources_or_condition')
 if not actor._action_history or actor._action_history[-1]!='standard':
  failures.append('actual_standard_payment_missing')
 engine._heavy_sequence+=1
 identity='heavy-equipment-'+str(engine._heavy_sequence)
 event=K.Event(identity,K.Kind.ACTION_TAKEN,H._kernel_state(before),H._kernel_state(after),
  action=K.Action.STANDARD,paid_resource=K.Action.STANDARD,in_combat=True,
  context=K.Context.UNKNOWN if failures else K.Context.NO_OTHER_INTERACTIONS,
  prevention_or_cap=None if failures else False)
 proposal=K.evaluate(K.Snapshot(event.after),event)
 packet=dict(event_id=identity,kind='action_taken',producer='manual_equipment.actual_standard',
  attacker=actor,target=actor,before=copy.deepcopy(before),observed_after=after,
  outcome=copy.deepcopy(outcome),status='pending',issues=failures+[proposal.reason],
  continuation_reified=True,unexecuted_remainder=None,
  occurrence_evidence=dict(round=engine.round_no,action_history_length=len(actor._action_history)))
 engine._heavy_events[identity]=packet
 if proposal.status=='ready' and not failures:
  final=proposal.snapshot.state
  TEMP.absorb(engine,actor,actor.temp_hp-final.temporary_hp)
  actor.hp=final.hp
  import bandages as BANDAGES
  BANDAGES.on_hp_change(engine,actor,after['hp'],actor.hp)
  packet.update(status='applied',heavy_consequence=dict(kind='hp_loss',amount=proposal.loss,
   before=after,after=H.observe(actor),recursive_attack=False,
   order_claim='actual manual action leaves HP/temporary HP/injuries/conditions unchanged; local loss commutes'))
 else:engine._heavy_pending=identity
 engine.log('[중상 장비] '+identity+': '+packet['status'],'common/heavy-injury')
 return identity

def _plain_json(value):
 kind=type(value)
 if kind in (str,int,bool,type(None)):return True
 if kind is float:return math.isfinite(value)
 if kind is list:return all(_plain_json(x) for x in value)
 if kind is dict:return all(type(k) is str and _plain_json(v) for k,v in value.items())
 return False

def _public_data_failures(actor,target,move,mm,public_inputs):
 failures=[]
 if (type(public_inputs) is not dict or type(public_inputs.get('situational')) is not int
     or any(type(public_inputs.get(k)) is not bool for k in ('set_damage','count_use','free_action'))):
  failures.append('nonplain_public_move_inputs')
 for label,c in [('actor',actor),('target',target)]:
  for field in ('stats','stages','move_uses'):
   value=getattr(c,field,None)
   if type(value) is not dict or any(type(k) is not str or type(v) is not int for k,v in value.items()):
    failures.append(label+':nonplain_'+field)
  for field in ('hp','temp_hp','injuries','level','accuracy_stage','evasion_mod','damage_reduction'):
   if type(getattr(c,field,None)) is not int:failures.append(label+':nonplain_'+field)
  for field in ('dead','captured','on_field','abilities_suppressed'):
   if type(getattr(c,field,None)) is not bool:failures.append(label+':nonplain_'+field)
  # Native builder sheets contain passive tuples/sets (for example movement
  # capabilities); they are not arbitrary object or numeric-subclass callbacks.
  if type(c.spec) is not dict or not H._passive(c.spec):failures.append(label+':nonplain_spec')
  for field in ('types','abilities','moves'):
   value=getattr(c,field,None)
   if type(value) is not list or any(type(x) is not str for x in value):failures.append(label+':nonplain_'+field)
  if type(c.conditions) is not set or any(type(x) is not str for x in c.conditions):failures.append(label+':nonplain_conditions')
 source_move=H.single_target_move_data(move,target)
 if source_move is None or not _plain_json(source_move) or not _plain_json(mm):failures.append('nonplain_move_data')
 return failures

def _independent_native_standard(engine,actor,target,move,mm,ordinary_single,public_inputs):
 """Certify the actual HP-independent native suffix, not an action exemption."""
 import initiative_interrupts as INTERRUPTS,world_entities as WORLD
 prepared_difference={}
 def result(failures):
  return dict(failures=list(dict.fromkeys(failures)),upper_damage=None,
   checked=['actual_native_standard_and_selected_interrupt','exact_hp_independent_native_move',
    'no_native_hp_observer_or_retaliation','loss_preserves_injuries_and_life_permission'],
   context='native_standard_hp_loss_commutes' if not failures else 'unresolved_activation_context',
   prepared_difference=prepared_difference)
 failures=_public_data_failures(actor,target,move,mm,public_inputs)
 native=getattr(engine,'_heavy_native_types',())
 if (len(native)!=3 or type(engine) is not native[0] or type(engine.r) is not native[1]
     or any(type(c) is not native[2] or c.r is not engine.r for c in (actor,target))):
  failures.append('noncanonical_runtime_type')
 if failures:return result(failures)
 if not ordinary_single:
  import move_activation as ACTIVATION
  # use_move_on owns a frame even for one target. Its existing verify() has
  # consumed index one before this diagnostic; neither shared dictionaries nor
  # a copied completion receipt can replace this live producer/lifetime.
  singles=[scope for scope in getattr(engine,'_move_activation_scopes',())
   if scope['actor'] is actor and scope['move_id']==move.get('id')
   and scope['primary'] is target and scope['targets']==(target,)
   and scope['index']==1 and scope['accuracy'] is None
   and scope['activation'] in ({},{'started':True})
   and scope['profile']==ACTIVATION._profile(engine)
   and scope['lifetime']==ACTIVATION._lifetime(engine)
   and not any(scope.get(key) for key in ('prepaid_pass','paid_resolution','type_ace','martial_artist','style_expert','stat_maneuver'))]
  ordinary_single=len(singles)==1
 if (not ordinary_single or actor is target or not engine.encounter_active
     or engine._active_turn_actor is not actor or engine.round_start_seconds is None
     or actor.fainted or actor.dead or actor.captured or not actor.on_field):
  failures.append('actual_conscious_native_standard_missing')
 selected=INTERRUPTS.selected_move_frame(engine,actor)
 if actor.hp<=0 and selected is None:failures.append('nonpositive_actor_has_no_actual_selected_interrupt')
 passive=H.passive_prefix_failures(engine,actor,target,require_actor_budget=True)
 from pathlib import Path
 if type(engine.r.root) is type(Path()) and engine.r.root.is_absolute():
  passive=[item for item in passive if item!='rules:nonpassive_state:root']
 if selected is not None and __import__('enduring_soul').conscious(actor):
  window=getattr(engine,INTERRUPTS.KEY)['windows'][selected[0]['window_id']]
  __import__('enduring_soul').authorize_request(engine,actor,selected[1],window['trigger'])
  passive=[item for item in passive if item!='actor:nonpassive_state:_enduring_not_yet_live']
 failures.extend(passive)
 if failures:return result(failures)
 raw=dict(move);actual_targets=raw.pop('_actual_targets',None)
 expected=engine.r.move(move.get('id'))
 if (move.get('id') not in ('struggle','move/몸통박치기') or raw!=expected
     or actual_targets!=(target,) or mm not in ({},{'push':{'meters':2}})
     or (move.get('id')=='struggle' and mm!={})
     or (move.get('id')=='move/몸통박치기' and mm!={'push':{'meters':2}})):
  failures.append('not_reviewed_hp_independent_native_suffix')
  prepared_difference.update(move={key:[raw.get(key),expected.get(key)]
   for key in raw.keys()|expected.keys() if raw.get(key)!=expected.get(key)},mechanics=copy.deepcopy(mm))
 for owner in (engine.rulings,engine.r.rulings):
  if type(owner) is not Rulings:failures.append('noncanonical_rulings_type')
  # These exact units are never read by either reviewed suffix: no capture is
  # performed and both actual actors are required to have no conditions below.
  # Keep every formula/effect/hook, and any other mech override, unresolved.
  unrelated={'pokemon/capture-rate','condition/마비','condition/풀죽음','condition/헤롱헤롱'}
  if (any(owner.hooks.values()) or set(owner.mech)-unrelated
      or any(getattr(owner,k,None) for k in ('formulas','effects','situational','provider'))):
   failures.append('external_native_observer')
 for obj,names in ((engine,('lose_hp','_lose_hp','marker_injuries','check_fainted','accuracy_check','roll_damage','damage_base','d20','roll_expr','type_multiplier','formula','log')),
                   (engine.r,('move','move_mech','mech','formula'))):
  if any(name in vars(obj) for name in names):failures.append('overridden_native_method')
 for c in (actor,target):
  import temporary_hp as TEMP
  if not H.inert_turn_bookkeeping(engine,c):
   failures.append('native_suffix_custom_condition')
  for field in ('abilities','ability_triggers','registry','modifiers','conditions','buffs','coats','blessings','item','shield',
                'next_attack','reflect','damage_cap','form_rule','form','setup_move','locked_move'):
   if getattr(c,field,None):failures.append('native_suffix_interaction:'+field)
  if c.spec.get('feats') or c.spec.get('features') or c.spec.get('edges'):
   failures.append('native_suffix_actor_feature')
  if any(c.stages.values()) or c.damage_reduction:failures.append('native_suffix_nonplain_stats')
 if target.injuries:failures.append('target_resource_interactions')
 if type(engine.log_lines) is not list or any(type(line) is not str for line in engine.log_lines):
  failures.append('noncanonical_log_sink')
 if type(engine.rng) is not random.Random:failures.append('unknown_rng_provider')
 elif set(vars(engine.rng))!={'gauss_next'} or type(vars(engine.rng)['gauss_next']) not in (type(None),int,float):
  failures.append('rng_instance_state_not_native')
 for obj in (engine,engine.r,actor,target,engine.rulings,engine.r.rulings):
  if any(callable(value) for value in vars(obj).values()):failures.append('instance_callback')
 if move.get('type') in actor.types:failures.append('native_suffix_stab_bound_not_reviewed')
 if failures:return result(failures)
 df=engine.r.mech('combat/damage-formula')
 stages=engine.r.mech('combat/combat-stage-multipliers')['multiplier_by_stage']
 if (move.get('class')!='물리' or df['attack_stat_by_class'].get('물리')!='atk'
     or df['defense_stat_by_class'].get('물리')!='def' or stages.get('0')!=1):
  failures.append('native_damage_bound_semantics_changed')
 if move.get('id')=='struggle' and actor.kind!='pokemon':
  entry=engine.r.mech('combat/damage-chart')['by_damage_base'][str(move['damage_base'])]
  dice=re.fullmatch(r'(\d+)d(\d+)(?:\+(\d+))?',entry['dice'])
  upper=None if dice is None else max(2*entry['set']['mid'],2*(int(dice[1])*int(dice[2])+int(dice[3] or 0)))+actor.stats['atk']-target.stats['def']
  if upper is None or 2*upper>=target.base_max_hp or 2*(target.hp-upper)<=target.base_max_hp:
   failures.append('target_marker_faint_or_massive_not_excluded')
 for field in ('weather','field','zones','zone_cells','hazards','hazards_nogrid','delayed','taunt','zone_rules'):
  if getattr(engine,field,None):failures.append('native_suffix_field:'+field)
 index=WORLD.actor_index(engine);trainer=index.get(actor.spec.get('trainer_id'))
 source=selected[1]['source'] if selected else None
 import trainer_feature_acquisition as ACQUISITIONS
 parent=ACQUISITIONS.STATIC_FEATURES.get(source,{}).get('class_template')
 for c in index.values():
  if c.kind!='trainer':continue
  allowed={source} if c is trainer and source is not None else set()
  classes={parent} if c is trainer and parent is not None else set()
  if (set(c.spec.get('feats',()))-allowed or c.spec.get('features') or c.spec.get('edges')
      or set(c.spec.get('classes',()))-classes):failures.append('other_trainer_native_interaction')
 before=H.observe(actor);state=H._kernel_state(before);final=K._subtract(state,state.injuries)
 if state.injuries<5 or state.injuries>=10 or K._crosses_marker(state,final):
  failures.append('native_loss_changes_injury_boundary')
 if actor.hp>0 and final.hp<=0:failures.append('native_loss_opens_a_new_faint_boundary')
 if engine.death_enabled and not engine.friendly_battle:
  from rulings import calc
  threshold=calc(engine.r.mech('combat/injuries')['death']['hp_non_friendly'],{'max_hp':actor.base_max_hp})
  if final.hp<=threshold:failures.append('native_loss_crosses_death_boundary')
 return result(failures)


def diagnose(engine,actor,target,move,mm,ordinary_single,*,public_inputs=None):
 import temporary_hp as TEMP_HP
 TEMP_HP.ensure_certain(engine,actor)
 TEMP_HP.ensure_certain(engine,target)
 independent=_independent_native_standard(engine,actor,target,move,mm,ordinary_single,public_inputs)
 if not independent['failures']:return independent
 prefix_failures=_public_data_failures(actor,target,move,mm,public_inputs)+H.passive_prefix_failures(engine,actor,target,require_actor_budget=True)
 if prefix_failures:
  return dict(failures=prefix_failures,upper_damage=None,checked=['plain_public_data_checked'],
   context='unresolved_activation_context',native_suffix_failures=independent['failures'],
   prepared_difference=independent['prepared_difference'])
 base=H.certify_native_context(engine,actor,target,move,mm,ordinary_single=ordinary_single)
 failures=[x for x in base.failures if x!='attacker_standard_heavy_consequence_unresolved']
 for name in ('accuracy_check','damage_base','d20','roll_expr','formula','log'):
  if name in vars(engine):failures.append('overridden_engine_method:'+name)
 if type(engine.rng) is not random.Random:failures.append('unknown_rng_provider')
 elif (type(vars(engine.rng)) is not dict or set(vars(engine.rng))!={'gauss_next'}
       or type(vars(engine.rng)['gauss_next']) not in (type(None),int,float)):
  # Random's only normal instance cache is gauss_next. Any method shadow or
  # injected state is outside this certificate, even a noncallable override.
  failures.append('rng_instance_state_not_native')
 for label,obj in [('engine',engine),('rules',engine.r),('actor',actor),('target',target),('rulings',engine.rulings),('rules.rulings',engine.r.rulings)]:
  if any(callable(v) for v in vars(obj).values()):failures.append(label+':instance_callback')
 if type(engine.rulings) is not Rulings or type(engine.r.rulings) is not Rulings:
  failures.append('noncanonical_rulings_type')
 for label,c in [('actor',actor),('target',target)]:
  native_types=getattr(engine,'_heavy_native_types',None)
  if not native_types or type(c) is not native_types[2]:failures.append(label+':unknown_actor_class')
  if any(x in vars(c) for x in ('staged','evasion')):failures.append(label+':overridden_stats')
  if c.types or any(c.stages.values()) or c.damage_reduction:failures.append(label+':nonplain_stats')
 if target.injuries or target.temp_hp:failures.append('target_resource_interactions')
 upper=None
 df=engine.r.mech('combat/damage-formula')
 stages=engine.r.mech('combat/combat-stage-multipliers')['multiplier_by_stage']
 if (move.get('class')!='물리' or df['attack_stat_by_class'].get('물리')!='atk'
     or df['defense_stat_by_class'].get('물리')!='def' or stages.get('0')!=1):
  failures.append('native_damage_bound_semantics_changed')
 # Native Struggle has fixed DB. This is an upper bound on both set and dice
 # damage, including critical dice duplication; it consumes no random draw.
 if move.get('id')=='struggle' and type(move.get('damage_base')) is int:
  entry=engine.r.mech('combat/damage-chart')['by_damage_base'][str(move['damage_base'])]
  m=re.fullmatch(r'(\d+)d(\d+)(?:\+(\d+))?',entry['dice'])
  if m:
   n,d,bonus=int(m[1]),int(m[2]),int(m[3] or 0)
   upper=max(2*entry['set']['mid'],2*(n*d+bonus))+actor.stats['atk']-target.stats['def']
   upper=max(0,upper)
 if upper is None or 2*upper>=target.base_max_hp or 2*(target.hp-upper)<=target.base_max_hp:
  failures.append('target_marker_faint_or_massive_not_excluded')
 before=H.observe(actor)
 ev=K.Event('diagnostic',K.Kind.ACTION_TAKEN,H._kernel_state(before),H._kernel_state(before),
  action=K.Action.STANDARD,paid_resource=K.Action.STANDARD,in_combat=bool(engine.encounter_active),
  context=K.Context.NO_OTHER_INTERACTIONS,prevention_or_cap=False)
 proposal=K.evaluate(K.Snapshot(ev.after),ev)
 if proposal.status!='ready':failures.append(proposal.reason)
 return dict(failures=list(dict.fromkeys(failures)),upper_damage=upper,
  checked=[x for x in base.checked if x!='attacker-not-heavy']+['heavy_actor_stable_local_loss','no_active_log_observer','native_standard_use','actor_resource_independent_accuracy_damage_frequency',
   'target_no_marker_faint_massive_for_all_damage_rolls','unmodified_random_provider'],
  context='restricted_confluent_standard_use' if not failures else 'unresolved_activation_context',
  native_suffix_failures=independent['failures'],prepared_difference=independent['prepared_difference'])


def diagnose_empty_field(engine,actor,move,mm,effects,ordinary_single,*,public_inputs=None):
 """Certify only an exact, zero-damage native field activation.

 The actual field handlers run before ``finish``; any actor-state change then
 becomes a preserved pending event. This pre-certificate merely proves that the
 activation has no creature target, accuracy roll, damage or authored effect.
 """
 import area_targets as AREA
 import effects as FX
 import effects_ext as EXT
 failures=[]
 native=getattr(engine,'_heavy_native_types',())
 if (type(public_inputs) is not dict or type(public_inputs.get('situational')) is not int
     or any(type(public_inputs.get(k)) is not bool
            for k in ('set_damage','count_use','free_action'))):
  failures.append('nonplain_public_move_inputs')
 for field in ('stats','stages','move_uses','budget'):
  value=getattr(actor,field,None)
  if type(value) is not dict or any(type(k) is not str or type(v) is not int
                                    for k,v in value.items()):
   failures.append('actor:nonplain_'+field)
 for field in ('hp','temp_hp','injuries','level','accuracy_stage','evasion_mod','damage_reduction'):
  if type(getattr(actor,field,None)) is not int:failures.append('actor:nonplain_'+field)
 for field,value in vars(actor).items():
  if field=='r':
   if value is not engine.r:failures.append('actor:foreign_rules_reference')
  elif field=='last_target':
   if (value is not None and (type(native) is not tuple or len(native)!=3
       or type(value) is not native[2] or value.r is not engine.r)):
    failures.append('actor:noncanonical_last_target')
  elif not H._passive(value):failures.append('actor:nonpassive_state:'+field)
 if not _plain_json(list(effects)):failures.append('nonplain_empty_field_effects')
 if (type(native) is not tuple or len(native)!=3 or type(engine) is not native[0]
     or type(engine.r) is not native[1] or type(actor) is not native[2]
     or actor.r is not engine.r):
  failures.append('noncanonical_runtime_type')
 for name in ('d20','roll_expr','formula','log'):
  if name in vars(engine):failures.append('overridden_engine_method:'+name)
 for name in ('move','move_mech','mech','formula'):
  if name in vars(engine.r):failures.append('overridden_rules_method:'+name)
 if type(engine.rng) is not random.Random:failures.append('unknown_rng_provider')
 if (move.get('id')!='move/날려버리기' or move.get('damage_base') is not None
     or tuple(move.get('_actual_targets',()))):
  failures.append('not_exact_zero_damage_targetless_whirlwind')
 native_effects=AREA.empty_field_effects(mm)
 if native_effects!=list(effects):failures.append('empty_field_authority_or_effects_changed')
 if (FX.HANDLERS.get('destroy_hazards') is not EXT.h_destroy_hazards
     or FX.HANDLERS.get('clear_field') is not EXT.h_clear_field):
  failures.append('noncanonical_empty_field_handler')
 if (not engine.encounter_active or engine._active_turn_actor is not actor
     or engine.round_start_seconds is None):
  failures.append('ordinary_active_combat_context_missing')
 if ordinary_single is not True:failures.append('not_ordinary_single_activation')
 if actor.dead or actor.hp<=0 or actor.captured or not actor.on_field:
  failures.append('actor_not_ordinary_conscious_on_field')
 for field in ('abilities','conditions','buffs','coats','blessings'):
  if getattr(actor,field,None):failures.append('actor:'+field)
 if not H.inert_turn_bookkeeping(engine,actor):
  failures.append('actor:custom_conditions')
 for field in ('abilities','feats','edges','item'):
  if actor.spec.get(field):failures.append('actor:spec.'+field)
 before=H.observe(actor)
 event=K.Event('diagnostic-empty-field',K.Kind.ACTION_TAKEN,H._kernel_state(before),
  H._kernel_state(before),action=K.Action.STANDARD,paid_resource=K.Action.STANDARD,
  in_combat=bool(engine.encounter_active),context=K.Context.NO_OTHER_INTERACTIONS,
  prevention_or_cap=False)
 proposal=K.evaluate(K.Snapshot(event.after),event)
 if proposal.status!='ready':failures.append(proposal.reason)
 failures=list(dict.fromkeys(failures))
 return dict(failures=failures,upper_damage=0,
  checked=['canonical_targetless_runtime','exact_native_empty_field_authority',
   'zero_accuracy_zero_damage','canonical_field_handlers','actor_state_observed_after_effects'],
  context='restricted_confluent_targetless_standard' if not failures else 'unresolved_activation_context')

def validate(engine,token):
 receipt=engine._heavy_standard_receipts.get(token)
 if receipt is None:raise ValueError('standard-use receipt absent, expired or consumed')
 a=receipt['actor']
 if (receipt['epoch']!=engine._heavy_standard_sequence or receipt['round']!=engine.round_no
     or engine._active_turn_actor is not a
     or receipt['move_uses']!=a.move_uses.get(receipt['move']['id'],0)
     or receipt['history_length']!=len(a._action_history)):
  raise ValueError('standard-use identity or activation epoch mismatch')
 return receipt

def hold(engine,token,packet,reason):
 engine._heavy_standard_receipts.pop(token,None)
 packet['status']='pending';packet['issues']=list(dict.fromkeys(packet.get('issues',[])+[reason]))
 engine._heavy_pending=packet['event_id']
 engine.log('[중상 보류] '+packet['event_id']+': Standard 사용 및 손실 처리 조건 미확정','common/heavy-injury')
 raise H.HeavyPending(packet['event_id'])

def observe_activation(engine,token):
 receipt=validate(engine,token);a=receipt['actor'];target=receipt['action_target']
 if receipt.get('targetless'):
  diagnostic=diagnose_empty_field(engine,a,receipt['move'],receipt['mm'],
   receipt['field_effects'],receipt['ordinary_single'],
   public_inputs=(receipt.get('pre_context') or {}).get('public_inputs'))
 else:
  diagnostic=diagnose(engine,a,target,receipt['move'],receipt['mm'],receipt['ordinary_single'],public_inputs=(receipt.get('pre_context') or {}).get('public_inputs'))
 pre=receipt.get('pre_context')
 if pre is None:
  diagnostic['failures'].append('pre_reservation_context_missing')
 else:
  diagnostic['failures']=list(dict.fromkeys(diagnostic['failures']+pre['diagnostic']['failures']))
  if pre['before']!=H.observe(a):diagnostic['failures'].append('actor_changed_before_observed_activation')
 diagnostic['context']=diagnostic['context'] if not diagnostic['failures'] else 'unresolved_activation_context'

 event_id='heavy-standard-'+str(receipt['epoch'])
 receipt['event_id']=event_id;receipt['before']=H.observe(a)
 receipt['target_before']=None if target is None else H.observe(target)
 packet=dict(event_id=event_id,kind='action_taken' if not diagnostic['failures'] else 'activation_observed',
  producer='Engine.use_move.native_standard',attacker=a,target=a,action_target=target,
  before=copy.deepcopy(receipt['before']),observed_after=H.observe(a),move=H.copy_move(engine,receipt['move']),
  status='in_progress',semantic_commit_proven=not diagnostic['failures'],
  actual_action_count=1 if not diagnostic['failures'] else None,
  occurrence_evidence=dict(frequency_count=receipt['move_uses'],round=receipt['round'],
   action_history_length=receipt['history_length']),context_evidence=diagnostic,
  issues=diagnostic['failures'],continuation_reified=False,
  unexecuted_remainder='accuracy and native move outcome; no automatic continuation',
  phase_claim='local confluence only; observed activation is not a general source commit phase')
 engine._heavy_events[event_id]=packet
 if diagnostic['failures']:hold(engine,token,packet,'semantic_commit_or_confluence_unresolved')
 return event_id

def finish(engine,token,*,hit,dealt):
 if token is None:return
 receipt=validate(engine,token);a=receipt['actor'];target=receipt['action_target']
 import temporary_hp as TEMP_HP
 TEMP_HP.ensure_certain(engine,a)
 if target is not None:TEMP_HP.ensure_certain(engine,target)
 packet=engine._heavy_events[receipt['event_id']]
 if packet['status']!='in_progress':raise ValueError('Standard event already resolved')
 after=H.observe(a);target_after=None if target is None else H.observe(target);packet['observed_after']=after
 packet['outcome']=dict(hit=bool(hit),dealt=dealt,target_before=receipt['target_before'],target_after=target_after)
 if packet['context_evidence']['context']=='native_standard_hp_loss_commutes':
  if after!=receipt['before']:hold(engine,token,packet,'actor_resource_changed_during_move')
  identity=packet['event_id'];amount=a.injuries
  # The certified orders agree. Use the real loss owner so temp-HP provenance,
  # marker/life hooks and the source-owned faint deferral stay authoritative.
  engine._heavy_standard_receipts.pop(token)
  engine.lose_hp(a,amount,source='heavily_injured_standard')
  packet=engine._heavy_events[identity]
  packet.update(status='applied',continuation_reified=True,unexecuted_remainder=None,
   heavy_consequence=dict(kind='hp_loss',amount=amount,before=after,after=H.observe(a),
    recursive_attack=False,order_claim='certified HP-independent native suffix commutes with loss'))
  return
 if (target is not None and (target_after['injuries']!=receipt['target_before']['injuries']
     or target_after['hp']<=0 or target_after['conditions'])):
  hold(engine,token,packet,'target_outcome_exceeded_independent_context')
 if after!=receipt['before']:hold(engine,token,packet,'actor_resource_changed_during_move')
 event=K.Event(packet['event_id'],K.Kind.ACTION_TAKEN,H._kernel_state(receipt['before']),H._kernel_state(after),
  action=K.Action.STANDARD,paid_resource=K.Action.STANDARD,in_combat=True,
  context=K.Context.NO_OTHER_INTERACTIONS,prevention_or_cap=False)
 proposal=K.evaluate(K.Snapshot(event.after),event)
 if proposal.status!='ready':hold(engine,token,packet,proposal.reason)
 engine._heavy_standard_receipts.pop(token)
 TEMP_HP.absorb(engine,a,a.temp_hp-proposal.snapshot.state.temporary_hp)
 a.hp=proposal.snapshot.state.hp
 import bandages as BANDAGES
 BANDAGES.on_hp_change(engine,a,after["hp"],a.hp)
 packet['status']='applied';packet['unexecuted_remainder']=None
 packet['heavy_consequence']=dict(kind='hp_loss',amount=proposal.loss,before=after,after=H.observe(a),
   recursive_attack=False,order_claim='actor-resource-independent native use commutes with local loss')
 engine.log('[중상] '+packet['event_id']+': 실제 Standard 사용, 합류가 확인된 체력 손실 '+str(proposal.loss),'common/heavy-injury')
