"""DOMAIN070 actual inventory/time/rest/damage integration."""
from copy import deepcopy
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'));sys.path.insert(0,str(ROOT/'tools'))
import test_category3_pokemon_activities as _fixture_test_category3_pokemon_activities
from engine import Rules
import bandages as B
import downtime as D
import injury_recovery as I
import effects_ext as EXT
import common_checks as C
class BandageTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
 setUp=_fixture_test_category3_pokemon_activities.PokemonActivityTests.setUp
 actor=_fixture_test_category3_pokemon_activities.PokemonActivityTests.actor
 act=_fixture_test_category3_pokemon_activities.PokemonActivityTests.act
 state=_fixture_test_category3_pokemon_activities.PokemonActivityTests.state
 def apply(self,target=None,item='붕대',count=1):
  self.a.spec['items'][item]=self.a.spec['items'].get(item,0)+count
  return self.e.use_item(self.a,item,target or self.p,duration_minutes=1,duration_reason='GM Extended application duration',count=count)
 def status(self,target=None):return (target or self.p).spec['bandages'][-1]['status']
 def test_source_scope_unchanged(self):
  r=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8-sig'))
  for x in r['entries']:
   if x['id']=='DOMAIN-070':
    for a in x['source_snapshot']['anchors']:
     text='\n'.join((ROOT/a['file']).read_text(encoding='utf-8-sig').splitlines()[a['start']-1:a['end']]);self.assertEqual(text,a['excerpt'])
 def test_native_item_requires_duration_before_stock_or_time_and_extended_not_standard(self):
  self.a.spec['items']['붕대']=1;before=self.state();self.assertIsInstance(self.e.use_item(self.a,'붕대',self.p),C.PendingDecision);self.assertEqual(before,self.state())
  r=self.e.use_item(self.a,'붕대',self.p,duration_minutes=2,duration_reason='GM duration')
  self.assertEqual(self.a.spec['items']['붕대'],0);self.assertEqual(self.e.elapsed_seconds,120);self.assertEqual(r['record']['expires_at'],21720);self.assertFalse(getattr(self.p,"pending_action_loss",None))
 def test_item_id_inventory_resolves_to_same_actual_consumable(self):
  self.a.spec['items']['item/붕대']=1
  self.e.use_item(self.a,'item/붕대',self.p,duration_minutes=1,duration_reason='GM duration');self.assertEqual(self.a.spec['items']['item/붕대'],0);self.assertEqual(self.status(),'active')
 def test_refusal_invalid_quantity_missing_inventory_and_combat_do_not_spend(self):
  self.a.spec['items']['붕대']=1;before=self.state();self.e.use_item(self.a,'붕대',self.p,accepted=False,duration_minutes=1,duration_reason='GM duration');self.assertEqual(before,self.state())
  for kw in ({'count':2},{'minutes':0},{'reason':''}):
   opts={'target':self.p,'minutes':1,'reason':'GM duration'};opts.update(kw)
   with self.assertRaises(ValueError):self.act('apply_bandages',**opts)
   self.assertEqual(before,self.state())
  self.e.encounter_active=True
  with self.assertRaises(ValueError):self.act('apply_bandages',target=self.p,minutes=1,reason='GM duration')
 def test_two_bandages_double_natural_heal_only_once_and_30min_boundary(self):
  self.p.hp=1;self.apply(count=2);D.rest(self.e,self.p,29,rest_id='r');self.assertEqual(self.p.hp,1)
  D.rest(self.e,self.p,1,rest_id='r');self.assertEqual(self.p.hp,1+self.p.base_max_hp//8)
 def test_six_hour_boundary_removes_injury_without_rest_and_once(self):
  self.p.injuries=2;self.apply();self.e.advance_time(21599);self.assertEqual(self.p.injuries,2);self.assertEqual(self.status(),'active')
  self.e.advance_time(1);self.assertEqual(self.p.injuries,1);self.assertEqual(self.status(),'expired');self.e.advance_time(21600);self.assertEqual(self.p.injuries,1)
 def test_multiple_injury_recovery_shares_three_limit_with_other_sources(self):
  self.p.injuries=6;I.heal(self.e,self.p,2,source='natural');self.apply(count=4);self.e.advance_time(21600)
  self.assertEqual(self.p.injuries,3);self.assertEqual(I.healed_today(self.p),3);self.assertEqual(self.p.spec['bandages'][-1]['injuries_healed'],1)
  self.assertEqual(I.heal(self.e,self.p,1,source='pokemon_center'),0)
 def test_ordinary_hp_loss_breaks_and_cannot_heal_injury_at_original_expiry(self):
  self.p.injuries=1;self.p.hp=40;self.apply();self.e.lose_hp(self.p,1);self.assertEqual(self.status(),'lost');self.e.advance_time(21600);self.assertEqual(self.p.injuries,1)
 def test_attack_damage_fully_absorbed_by_temporary_hp_still_breaks(self):
  self.apply();self.e.gm.set_temp_hp(self.p,10,'GM effect',duration_seconds=3600);hp=self.p.hp
  self.e.take_damage(self.p,1);self.assertEqual(self.p.hp,hp);self.assertEqual(self.status(),'lost')
 def test_loss_fully_absorbed_preserves_but_unpreventable_actual_loss_breaks(self):
  self.apply();self.e.gm.set_temp_hp(self.p,10,'GM effect',duration_seconds=3600);hp=self.p.hp
  self.e.lose_hp(self.p,1);self.assertEqual(self.status(),'active');self.assertEqual(self.p.hp,hp);self.assertEqual(self.p.temp_hp,9)
  # ch07:623 and the adopted temp_first loss policy consume the remaining bonus HP first.
  self.e.lose_hp(self.p,self.p.temp_hp+1,unpreventable=True);self.assertEqual(self.status(),'lost')
  self.assertEqual(self.p.temp_hp,0);self.assertEqual(self.p.hp,hp-1)
 def test_zero_damage_and_healing_do_not_break(self):
  self.p.hp=20;self.apply();self.e.take_damage(self.p,0);self.e.heal(self.p,1);self.assertEqual(self.status(),'active')
 def test_successful_heal_ball_never_reduces_above_injury_cap_or_breaks_bandage(self):
  self.p.injuries=2;self.p.hp=self.p.base_max_hp;hp=self.p.hp;self.assertGreater(hp,self.p.max_hp);self.apply();self.a.spec['items']['힐볼']=1
  self.assertTrue(self.e.throw_ball(self.a,self.p,'힐볼',fixed_accuracy=20,fixed_capture=20))
  self.assertEqual(self.p.hp,hp);self.assertEqual(self.p.injuries,2);self.assertEqual(self.status(),'active');self.assertEqual(self.a.spec['items']['힐볼'],0)
 def test_successful_heal_ball_uses_actual_healing_without_removing_injuries(self):
  self.p.injuries=1;self.p.hp=1;self.p.conditions.update({'독','화상'});self.apply();self.a.spec['items']['힐볼']=1
  self.assertTrue(self.e.throw_ball(self.a,self.p,'힐볼',fixed_accuracy=20,fixed_capture=20))
  self.assertEqual(self.p.hp,self.p.max_hp);self.assertEqual(self.p.injuries,1);self.assertEqual(self.status(),'active');self.assertEqual(self.p.conditions,{'독','화상'})
 def test_native_hp_share_breaks_both_before_regaining_hp(self):
  self.apply(self.p);self.apply(self.q);self.p.hp=40;self.q.hp=20;EXT.h_hp_share(self.e,self.p,self.q,{},{});self.assertEqual(self.status(self.p),'lost');self.assertEqual(self.status(self.q),'lost')
 def test_gm_hp_setting_faint_revive_reduction_and_injury_ceiling(self):
  for mutation in (lambda:self.e.gm.set_hp(self.p,delta=-1,reason='fall'),lambda:self.e.gm.faint(self.p,'GM faint'),lambda:self.e.gm.revive(self.p,1,'HP setting')):
   self.p.hp=self.p.base_max_hp;self.p.conditions.clear();self.p.injuries=0;self.apply();mutation();self.assertEqual(self.status(),'lost')
  self.p.hp=self.p.base_max_hp;self.p.conditions.clear();self.p.injuries=0;self.apply()
  self.e.gm.set_injuries(self.p,delta=2,reason='GM injury')
  self.assertEqual(self.p.hp,self.p.base_max_hp);self.assertLess(self.p.max_hp,self.p.hp);self.assertEqual(self.status(),'active')
 def test_rest_expiry_uses_old_healing_ceiling_and_does_not_retroactively_heal(self):
  self.p.injuries=1;self.p.hp=1;oldcap=self.p.max_hp;self.apply();D.rest(self.e,self.p,360,rest_id='rest')
  self.assertEqual(self.p.injuries,0);self.assertEqual(self.p.hp,oldcap)
  D.rest(self.e,self.p,30,rest_id='rest');self.assertEqual(self.p.hp,oldcap+self.p.base_max_hp//16)
 def test_heavy_injury_does_not_retroactively_grant_first_six_hours(self):
  self.p.injuries=5;self.p.hp=1;self.apply(count=2);D.rest(self.e,self.p,420)
  self.assertEqual(self.p.injuries,3);self.assertEqual(self.p.hp,1+2*(self.p.base_max_hp//16))
 def test_unknown_time_requires_explicit_ruling_and_cannot_extend_lifetime(self):
  self.p.injuries=1;r=self.apply();bid=r['record']['id'];self.e.advance_time(600);self.e.unresolved_time_intervals.append({'reason':'GM unknown travel duration'})
  before=self.state()
  with self.assertRaises(ValueError):D.rest(self.e,self.p,30)
  self.assertEqual(before,self.state())
  with self.assertRaises(ValueError):self.act('resolve_bandage_timing',target=self.p,bandage_id=bid,remaining_seconds=21600,reason='cannot extend')
  self.act('resolve_bandage_timing',target=self.p,bandage_id=bid,remaining_seconds=0,reason='GM observed six hours passed');self.assertEqual(self.p.injuries,0)
 def test_partial_30minute_coverage_stays_pending_before_time_or_healing(self):
  self.apply();self.e.advance_time(60);before=self.state()
  with self.assertRaises(ValueError):D.rest(self.e,self.p,360)
  self.assertEqual(before,self.state())
 def test_actual_suffocation_injury_survives_bandage_expiry_and_only_breathing_heals_it(self):
  self.p.injuries=2;self.apply(count=3);self.e.advance_time(21539)
  self.e.observe_breathing(self.p,air_available=False,medium='airless',reason='GM sealed airless space',timing_policy='grace_boundary')
  self.e.advance_time(60);self.assertEqual(self.p.injuries,3);self.e.advance_time(1)
  self.assertEqual(self.status(),'expired');self.assertEqual(self.p.injuries,1);self.assertEqual(self.p.spec['bandages'][-1]['injuries_healed'],2);self.assertEqual(I.healed_today(self.p),2)
  self.e.observe_breathing(self.p,air_available=True,medium='air',reason='GM restored breathable air');self.assertEqual(self.p.injuries,0);self.assertEqual(I.healed_today(self.p),2)
 def test_trainers_and_poultices_use_same_effect_with_revised_herbal_history(self):
  self.a.hp=1;self.a.spec['loyalty']=3;self.a.injuries=1;self.apply(self.a,item='파스');D.rest(self.e,self.a,30)
  self.assertEqual(self.a.hp,1+self.a.base_max_hp//8);self.assertEqual(self.a.spec['loyalty'],3)
  import food_effects as FOOD
  self.assertEqual(FOOD.validate_herbal(self.a)['count'],1);self.assertNotIn('bitter_medicine_history',self.a.spec)
  self.assertEqual(self.a.buffs[0]['effect'],{'kind':'save_bonus','amount':2})
if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(BandageTests))
 files=['engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/combat_social_edges.py','engine/net_capsule.py','engine/trainer_capabilities.py','engine/skill_feature_actions.py','engine/researcher_features.py','engine/precise_actions.py','engine/wild_equipment.py','engine/skill_modifiers.py','engine/common_action_checks.py','engine/environmental_effects.py','engine/jump_actions.py','engine/context_actions.py','engine/pokemon_requests.py','engine/combat_timing.py','engine/combat_maneuvers.py','data/context-check-policy.json','data/cultivation-policy.json','engine/bandages.py','engine/engine.py','engine/items.py','engine/downtime.py','engine/gm_state.py','engine/life.py','engine/heavy_injury_adapter.py','engine/heavy_standard_adapter.py','engine/effects_ext.py','engine/injury_recovery.py','engine/rest_intervals.py','engine/pokemon_activities.py','data/core-rules.json','data/items-mech.json','data/items-reviewed.json','data/rulesets.json','output/ruleunits.jsonl','input/ch09-equipment.md','tools/test_category3_bandages.py']
 files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['DOMAIN-070'],'completion':'review pending; mixed half-hour and unknown time kept explicit','results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
 (ROOT/'output/category3-bandage-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
