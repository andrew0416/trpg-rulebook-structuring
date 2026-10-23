"""Explicit requirement-to-unit mapping. Missing semantics remain visible."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
GROUPS={
'composition.derive':'capability_grant capability_grant_or_increment capability_value_addition conditional_skill_grant nonstacking_by_target skill_rank_addition skill_rank_transition',
'acquisition.qualification':'ability_choice acquisition_prerequisite_substitution allocated_stat_prerequisite bounded_distinct_repeat capability_choice category_choice creation_phase_predicate distinct_choices distinct_repeat generation_choice move_choice movement_choice owner_feature_predicate ranked_acquisition repeat_acquisition stat_choice type_choice weapon_choice',
'acquisition.receipt':'choice_record gift_grant one_time_resource_grant patron_relation per_rank_resource_spend retained_investment',
'acquisition.withdrawal':'conditional_refund',
'roll_context.plan':'contest_skill_substitution derived_skill_substitution dice_pool_adjustment effective_rank_override helper_formula_override opposed_roll_bonus opposed_skill_substitution purpose_bonus purpose_match purpose_roll_bonus purpose_skill_bonus purpose_skill_substitution resource_bonus_replacement roll_bonus_from_max_rank roll_total_addition scoped_effective_rank skill_bonus skill_set_bonus skill_substitution substitution_prohibition target_skill_substitution training_skill_substitution',
'roll_context.plan effects.lifetime':'timed_dice_bonus',
'roll_context.resolve':'automatic_success skill_dc skill_roll',
'crafting.recipe':'recipe_permission regional_service resource_cost_substitution',
'crafting.product atomic_transition.commit':'craft_or_apply inventory_transaction material_spend',
'activity.job':'activity_credit extended_check timed_activity',
'activity.clock':'activity_time',
'cultivation.growth':'cultivation_permission growth_time world_site',
'object_lifecycle.identity':'body_eligibility body_size_predicate condition_category_query equipped_predicate keyword_predicate species_rank_comparison species_stat_sum target_predicate',
'object_lifecycle.lifecycle':'object_damage_state spawn_entity',
'repair.restore object_lifecycle.lifecycle':'repair_or_destroy',
'control.remote':'obedience',
 'training.eligibility':'multi_target_training owner_dependent_limit training_limit',
 'training.rewards':'training_xp_formula xp_bonus',
 'creation.egg':'breeding_eligibility',
 'perception.observe':'identification',
 'control.vehicle':'control_eligibility machine_permission vehicle_control',
 'events.dispatch':'attempt_event post_action_event relation_event_delivery training_event critical_event hit_event',
 'growth.stats':'allocated_bonus_points base_relation_exemption base_stat_addition level_one_points_provenance restricted_bonus_allocation',
 'growth.milestones':'evolution_branch_choice evolution_prohibition evolution_recalculation level_transition skill_background_change',
 'learning.grant':'ability_grant move_grant move_learning natural_ability_choice',
 'learning.slots':'alternate_learnset learning_provenance linked_move_query natural_route slot_exemption slot_reservation',
 'combat.hit':'accuracy_override action_accuracy_override action_range_override attack_range_override critical_range_addition keyword_evasion range_modifier status_move_critical',
 'combat.damage':'context_damage_reduction damage_cause_predicate',
 'effects.apply':'condition_apply shock_immunity',
 'effects.recovery':'condition_remove item_heal_bonus temporary_hp',
 'effects.lifetime':'duration_override',
 'roll_context.plan effects.apply':'condition_save_modifier',
 'roll_context.plan effects.lifetime effects.apply':'timed_save_modifier',
 'initiative.derive':'rank_derived_initiative',
 'resources.actions':'action_cost action_cost_override conditional_resource_spend equipment_action_cost recipient_action_cost_exception shared_turn_budget',
 'resources.frequency events.dispatch':'success_gated_frequency',
 'movement.permission':'movement_bonus movement_distance_override movement_path_permission rank_based_breath_limit rank_based_distance',
 'maneuvers.grapple':'grapple_outcome_choice',
 'perception.communicate':'information_delivery',
 'perception.observe movement.permission':'range_addition_from_rank',
 'network.connection':'digital_participation network_participation',
 'repair.breach':'breach_patch',
 'repair.restore':'vehicle_hp_repair',
 'environment.derive':'home_environment_baseline interval_allocation interval_capability_grant'
}
GIFTS={
'action_permission':['resources.actions'],'action_prohibition':['resources.actions'],'component_substitution':['crafting.recipe'],
'condition_immunity':['effects.apply'],'dice_reroll':['roll_context.resolve'],'edge_grant':['acquisition.receipt'],
'entity_detection':['perception.observe'],'environment_modifier':['environment.derive'],'equipment_modifier':['composition.derive'],
'forced_movement':['movement.forced'],'identification':['perception.observe'],'injury_provenance':['effects.apply','acquisition.receipt'],
'move_grant':['learning.grant'],'move_immunity':['effects.apply'],'opponent_modifier':['roll_context.plan'],
'opposed_bonus':['roll_context.plan'],'purpose_modifier':['roll_context.plan'],'recovery_rate':['effects.recovery'],
'regional_recovery':['effects.recovery','environment.derive'],'relation_channel':['perception.communicate'],
'resource_bonus_replacement':['roll_context.plan'],'scene_detection':['perception.observe'],
 'target_modifier':['roll_context.plan'],'terrain_override':['environment.derive'],'world_information':['perception.observe','source_policy.adjudication']}
CROSS={
'discovery-acquisition-provenance':['acquisition.qualification','acquisition.receipt','acquisition.withdrawal'],
'discovery-retraining-dependency':['acquisition.withdrawal','atomic_transition.commit'],
'discovery-acquisition-scoped-substitution':['acquisition.qualification','roll_context.plan'],
'discovery-temporary-grant':['acquisition.receipt','composition.reconcile','effects.lifetime'],
'discovery-gift-replacement':['acquisition.qualification','acquisition.receipt','atomic_transition.replay'],
'discovery-minor-gift-scope':['source_policy.selection','scripting.load']}

def main():
 path=ROOT/'data/verification/category2-edge-work-plan.json';data=json.loads(path.read_text(encoding='utf-8'));d=data['foundation_discovery']
 assert d['denominator'] is None,'Frozen mappings cannot be silently regenerated'
 unit_ids={r['id'] for r in d['foundation_unit_drafts']['units']}
 opmap={}
 for units,ops in GROUPS.items():
  for op in ops.split():
   assert op not in opmap,op
   opmap[op]=units.split()
 from edge_foundation_unit_assignments import reviewed_assignments
 search=json.loads((ROOT/'data/verification/edge-name-search-candidates.json').read_text(encoding='utf-8'))
 reviewed=reviewed_assignments(d,search)
 mapped=[];pending=[]
 for req in d['candidate_contract_graph']['requirements']:
  ref=req['ref'];units=None;basis=None
  if '/operation/' in ref:
   op=req['requirement'];assert op in opmap,'Unmapped operation: '+op
   units=opmap[op];basis='Explicit operation semantics; raw definition and limits remain attached to original requirement.'
  elif ref.endswith('/acquisition'):
   units=['source_policy.selection','acquisition.qualification','acquisition.receipt','acquisition.withdrawal','scripting.load','scripting.execute'];basis='Repeated source-selected acquisition/provider/choice/removal/script-binding contract, including GM permission for Gifts.'
  elif ref.endswith('/gift-outcome'):
   families=req['requirement']['family_candidates'];units=sorted({u for family in families for u in GIFTS[family]});basis='Reviewed Minor Gift effect families with original inputs, outcome and limits retained; no invented GM result.'
  elif ref in CROSS:units=CROSS[ref];basis='Explicit cross-cutting source dependency.'
  elif ref in reviewed:units=reviewed[ref];basis='Individually reviewed consumer/source obligation; unit assignment distinguishes outcome, trigger, resource and lifetime.'
  if units:
   assert set(units)<=unit_ids,(ref,units)
   mapped.append({'requirement_ref':ref,'unit_ids':units,'mapping_basis':basis,'status':'semantic assignment reviewed; execution acceptance not certified'})
  else:pending.append(ref)
 d['unit_requirement_mapping']={'mapped':mapped,'pending_requirement_refs':pending,'validation':{'requirements':len(mapped)+len(pending),'mapped':len(mapped),'pending':len(pending),'dangling_units':0,'duplicate_requirements':len(mapped)!=len({r['requirement_ref'] for r in mapped}),'execution_certified':False},'next':'Review consumer, named-reference, original-PDF and alias obligations individually; no keyword default assignment.'}
 path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(d['unit_requirement_mapping']['validation'])
if __name__=='__main__':main()
