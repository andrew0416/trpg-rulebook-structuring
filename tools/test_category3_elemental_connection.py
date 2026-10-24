"""Elemental Connection fixed EX027 native skill targets and ownership."""
import hashlib,json,sys,unittest
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from grid import Grid
import elemental_connection as ELEM
import skill_feature_actions as SF
import items as ITEMS
class ElementalTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT))
 def actor(self,name,kind='trainer',types=None):
  return Combatant(self.r,{'id':name,'name':name,'kind':kind,'size':'medium','pos':(8,4),'level':30,'types':types or ['물'],'stats':{'hp':40,'atk':10,'def':10,'spa':10,'spd':10,'spe':5},'skills':{x:'숙련' for x in (*ELEM.SKILLS,'집중','육상','은신','곡예','포켓몬학','일반 지식')},'movement':{'land':6}})
 def setUp(self):
  self.e=Engine(self.r,seed=62);self.a=self.actor('A');self.p=self.actor('P','pokemon',['불꽃','비행']);self.other=self.actor('O','pokemon',['물'])
  self.a.spec['edges']=[ELEM.SOURCE];self.a.spec['edge_choices']={ELEM.SOURCE:'불꽃'}
  self.a.pos=(1,1);self.p.pos=(3,1);self.a.side='party';self.p.side='wild'
  self.e.everyone=[self.a,self.p,self.other];self.e.gm.everyone=self.e.everyone;self.e.grid=Grid(10,5)
 def roll(self,skill='매력',target=True,**options):
  if target is True:target=self.p
  return self.e.skill_roll(self.a,skill,skill_target=target,fixed=[3]*4,**options)
 def test_frozen_scope_matches_original(self):
  entry=next(e for e in json.loads((ROOT/'data/verification/category3-register.json').read_text('utf-8'))['entries'] if e['id']=='C3-EX-027')
  for a in entry['source_snapshot']['source_anchors']:
   lines=(ROOT/a['file']).read_text('utf-8-sig').splitlines();self.assertEqual('\n'.join(lines[a['start_line']-1:a['end_line']]),a['excerpt'])
 def test_exact_five_native_skills_receive_two(self):
  for skill in ELEM.SKILLS:self.assertEqual(self.roll(skill).total,14)
  for skill in ['집중','육상','포켓몬학']:self.assertEqual(self.roll(skill).total,12)
 def test_wrong_type_no_target_and_trainer_receive_nothing(self):
  for target in [None,self.other,self.actor('trainer',types=['불꽃'])]:self.assertEqual(self.roll(target=target).total,12)
 def test_actual_dual_type_matches_once_and_current_type_changes(self):
  self.assertEqual(self.roll().total,14);self.p.types=['물'];self.assertEqual(self.roll().total,12)
 def test_multiple_distinct_branches_apply_one_matching_type(self):
  self.a.spec['edges']=[ELEM.SOURCE,ELEM.SOURCE];self.a.spec['edge_choices'][ELEM.SOURCE]=['불꽃','물']
  self.assertEqual(self.roll().total,14);self.assertEqual(self.roll(target=self.other).total,14)
 def test_two_matching_branches_hold_without_rng(self):
  self.a.spec['edges']=[ELEM.SOURCE,ELEM.SOURCE];self.a.spec['edge_choices'][ELEM.SOURCE]=['불꽃','비행'];before=self.e.rng.getstate()
  self.assertEqual(self.e.skill_roll(self.a,'매력',skill_target=self.p,fixed=[3]*4).total,16)
  self.assertNotIn(ELEM.SOURCE_OBSERVATION,self.a.spec)
  self.assertEqual(before,self.e.rng.getstate())
 def test_multiple_matching_branches_hold_before_maneuver_standard(self):
  self.a.spec['edges']=[ELEM.SOURCE,ELEM.SOURCE];self.a.spec['edge_choices'][ELEM.SOURCE]=['불꽃','비행']
  self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20);before=self.e.rng.getstate()
  self.assertTrue(self.e.manipulate(self.a,self.p,'flirt',defender_skill='집중',fixed_accuracy=15,challenger_options={'fixed':[3]*4},defender_options={'fixed':[3]*4}))
  self.assertEqual(self.a.budget['standard'],0);self.assertEqual(before,self.e.rng.getstate())
 def test_branch_choice_validation(self):
  for choice in [None,'에러','None','unknown',['불꽃','물']]:
   self.a.spec['edge_choices'][ELEM.SOURCE]=choice
   with self.assertRaises(ValueError):self.roll()
  self.a.spec['edges']=[ELEM.SOURCE,ELEM.SOURCE];self.a.spec['edge_choices'][ELEM.SOURCE]=['불꽃','불꽃']
  with self.assertRaisesRegex(ValueError,'different'):self.roll()
 def test_mutual_exclusion_both_orders_aliases_and_no_partial_registration(self):
  for edges in [[ELEM.SOURCE,ELEM.MYSTIC],['Mystic Senses','Elemental Connection']]:
   self.a.spec['edges']=edges;before=(list(self.a.modifiers),list(self.a.registry))
   with self.assertRaisesRegex(ValueError,'mutually exclusive'):ITEMS.register_feats(self.e,self.a)
   self.assertEqual(before,(self.a.modifiers,self.a.registry))
   with self.assertRaisesRegex(ValueError,'mutually exclusive'):self.roll(skill='육상')
 def test_choice_without_ownership_and_pokemon_ownership_rejected(self):
  self.a.spec['edges']=[]
  with self.assertRaisesRegex(ValueError,'acquisition'):self.roll()
  self.a.spec['edges']=[ELEM.SOURCE];self.a.kind='pokemon'
  with self.assertRaisesRegex(ValueError,'trainer edge'):self.roll()
 def test_unselected_source_variant_rejected(self):
  original=self.r._selected_rule;self.r._selected_rule=lambda uid,*a,**kw:uid+'-alternate' if uid==ELEM.SOURCE else original(uid,*a,**kw)
  try:
   with self.assertRaisesRegex(ValueError,'variant'):self.roll()
  finally:self.r._selected_rule=original
 def test_registration_does_not_add_unconditional_bonus(self):
  ITEMS.register_feats(self.e,self.a);ITEMS.register_feats(self.e,self.a)
  self.assertEqual(self.roll().total,14);self.assertEqual(self.roll(target=self.other).total,12)
 def test_invalid_target_rejected_before_rng(self):
  before=self.e.rng.getstate()
  with self.assertRaises(ValueError):self.e.skill_roll(self.a,'매력',skill_target={'types':['불꽃']})
  self.assertEqual(before,self.e.rng.getstate())
 def test_native_dc_and_common_action_target(self):
  from unittest.mock import patch
  import composition_derive as COMPOSITION
  with patch.object(COMPOSITION,'derive',wraps=COMPOSITION.derive) as common:
   self.assertEqual(self.e.skill_check(self.a,'매력',14,fixed=[3]*4,skill_target=self.p),(True,14))
  self.assertTrue(any(any(row['source']==ELEM.SOURCE for row in call.args[1]) for call in common.call_args_list))
  self.assertTrue(self.e.common_action(self.a,'매력',14,mode='skill',fixed=[3]*4,skill_target=self.p).check.passed)
 def test_native_opposed_binds_target_and_preserves_defender_tie(self):
  self.assertTrue(self.e.opposed_check(self.a,'교활',self.p,'직감',challenger_options={'fixed':[3]*4},defender_options={'fixed':[3]*4}))
  self.assertFalse(self.e.opposed_check(self.p,'교활',self.a,'직감',challenger_options={'fixed':[3,3,4,4]},defender_options={'fixed':[3]*4}))
 def test_native_target_cannot_be_replaced_by_caller(self):
  before=self.e.rng.getstate()
  with self.assertRaisesRegex(ValueError,'differs'):self.e.opposed_check(self.a,'교활',self.other,'직감',challenger_options={'skill_target':self.p})
  with self.assertRaisesRegex(ValueError,'differs'):self.e.pokemon_activity(self.a,'pokemon_interaction',target=self.other,skill='매력',dc=14,skill_target=self.p)
  self.assertEqual(before,self.e.rng.getstate())
 def test_native_interaction_and_pokemon_education_substitution(self):
  self.assertTrue(self.e.pokemon_activity(self.a,'pokemon_interaction',target=self.p,skill='매력',dc=14,fixed=[3]*4)['check'].passed)
  self.a.spec['edges'].append('포켓몬 심리학자')
  result=self.e.pokemon_activity(self.a,'pokemon_interaction',target=self.p,skill='매력',dc=14,use_pokemon_education=True,fixed=[3]*4)
  self.assertFalse(result['check'].passed);self.assertEqual(result['check'].total,12)
 def test_native_befriend_real_disposition_and_standard(self):
  self.p.spec.update(wild=True,disposition='중립');self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
  result=self.e.pokemon_activity(self.a,'befriend',target=self.p,fixed=[2,2,3,3])
  self.assertTrue(result['check'].passed);self.assertEqual(result['check'].total,12);self.assertEqual(result['disposition'],'우호적');self.assertEqual(self.a.budget['standard'],0)
 def test_native_command_loyalty_real_target(self):
  self.p.spec.update(trainer_id='A',loyalty=1)
  result=self.e.pokemon_activity(self.a,'command_loyalty',target=self.p,fixed=[1,1,2,2]);self.assertTrue(result['obeys']);self.assertEqual(result['check'].total,8)
 def test_native_manipulate_receives_target_before_roll(self):
  self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
  self.assertTrue(self.e.manipulate(self.a,self.p,'flirt',defender_skill='집중',fixed_accuracy=15,challenger_options={'fixed':[3]*4},defender_options={'fixed':[3]*4}))
  self.assertIn('헤롱헤롱',self.p.conditions)
 def test_observed_skill_monkey_keeps_actual_target_and_bonus(self):
  self.a.spec['feats']=[SF.MONKEY];opts={'fixed':[3]*4,'roll_id':'elemental-roll','feature':SF.MONKEY,'feature_options':{'decision':lambda r:'invalid'},'skill_target':self.p}
  with self.assertRaisesRegex(ValueError,'boolean'):self.e.skill_roll(self.a,'매력',**opts)
  event=SF.event(self.e,self.a,'elemental-roll');self.assertEqual(event.first.total,14);self.assertIs(event.request[-1],self.p)
  opts['feature_options']={'decision':lambda r:False};opts['skill_target']=self.other
  with self.assertRaisesRegex(ValueError,'declaration'):self.e.skill_roll(self.a,'매력',**opts)
  opts['skill_target']=self.p;self.assertEqual(self.e.skill_roll(self.a,'매력',**opts).total,14)
 def test_native_interaction_observed_retry_preserves_same_target(self):
  self.a.spec['feats']=[SF.MONKEY];opts={'fixed':[3]*4,'roll_id':'activity-elemental','feature':SF.MONKEY,'feature_options':{'decision':lambda r:'bad'}}
  with self.assertRaisesRegex(ValueError,'boolean'):self.e.pokemon_activity(self.a,'pokemon_interaction',target=self.p,skill='매력',dc=14,**opts)
  opts['feature_options']={'decision':lambda r:False}
  same_id=self.actor('P','pokemon',['불꽃','비행'])
  with self.assertRaisesRegex(ValueError,'declaration'):self.e.pokemon_activity(self.a,'pokemon_interaction',target=same_id,skill='매력',dc=14,**opts)
  self.assertTrue(self.e.pokemon_activity(self.a,'pokemon_interaction',target=self.p,skill='매력',dc=14,**opts)['check'].passed)
 def test_snapshot_restores_target_reference_for_observed_retry(self):
  self.a.spec['feats']=[SF.MONKEY];opts={'fixed':[3]*4,'roll_id':'snapshot-elemental','feature':SF.MONKEY,'feature_options':{'decision':lambda r:'bad'},'skill_target':self.p}
  with self.assertRaises(ValueError):self.e.skill_roll(self.a,'매력',**opts)
  self.e.gm.snapshot('elemental');self.e.gm.restore('elemental');self.assertIs(SF.event(self.e,self.a,'snapshot-elemental').request[-1],self.p)
  opts['feature_options']={'decision':lambda r:False};self.assertEqual(self.e.skill_roll(self.a,'매력',**opts).total,14)

 def test_native_opposed_context_binds_actual_other_actor(self):
  result=self.e.common_action(self.a,None,None,mode='context',case='detect_lie',context={'purpose':'conceal actual fact','attempted_lie':True},target=self.p,defender_role='status_quo',challenger_options={'fixed':[3]*4},defender_options={'fixed':[3]*4})
  self.assertTrue(result.check.passed);self.assertEqual(result.basis['challenger_roll'].total,14)
 def test_third_party_persuasion_targets_evaluator_not_competing_speaker(self):
  opts=dict(mode='context',case='third_party_persuasion',context={'purpose':'persuade third party','third_party_evaluates_both':True},target=self.p,defender_role='status_quo',challenger_options={'fixed':[3]*4},defender_options={'fixed':[3]*4})
  result=self.e.common_action(self.a,None,None,**opts)
  self.assertEqual(result.basis['challenger_roll'].total,12)
  audience=self.actor('audience','pokemon',['불꽃']);self.e.everyone.append(audience)
  result=self.e.common_action(self.a,None,None,subject=audience,**opts)
  self.assertEqual(result.basis['challenger_roll'].total,14)
 def test_explicit_excluded_source_cannot_execute(self):
  old=self.r.selection.excluded.get(ELEM.SOURCE);self.r.selection.excluded[ELEM.SOURCE]='exclude_units'
  try:
   with self.assertRaisesRegex(ValueError,'Excluded rule'):self.roll()
  finally:
   if old is None:self.r.selection.excluded.pop(ELEM.SOURCE,None)
   else:self.r.selection.excluded[ELEM.SOURCE]=old

if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(ElementalTests))
 files=['data/content-source-identities.json','engine/ruleset.py','engine/elemental_connection.py','engine/skill_targets.py','engine/context_actions.py','engine/pokemon_activities.py','engine/combat_maneuvers.py','engine/maneuver_edges.py','engine/skill_maneuver_actions.py','engine/engine.py','engine/turn.py','engine/action_lifecycle.py','engine/action_points.py','engine/frequency.py','engine/combat_timing.py','engine/items.py','engine/skill_feature_actions.py','engine/skill_modifiers.py','engine/temporary_hp.py','engine/combat_social_edges.py','engine/effects.py','engine/effects_ext.py','engine/ap_roll_bonus.py','engine/gm_state.py','input/ch03-skills-edges-feats.md','input/ch07-combat.md','tools/test_category3_elemental_connection.py']
 files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['C3-EX-027'],'results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
 (ROOT/'output/category3-elemental-connection-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
