"""Native carrying constraints, real movement/actions, and small-object range."""
import sys,json,hashlib,re,unittest
from copy import deepcopy
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine,Rules,Combatant
from grid import Grid
import capability_actions as CAP
import common_checks as C
import turn as TURN
class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
    def setUp(self):
        self.e=Engine(self.rules,seed=394)
        self.a=self.actor('a');self.b=self.actor('b')
        self.a.pos=(1,2);self.b.pos=(12,2);self.a.side='a';self.b.side='b'
        self.e.grid=Grid(25,8);self.e.everyone=[self.a,self.b]
        self.e.gm.everyone=[self.a,self.b]
    def actor(self,name):
        return Combatant(self.rules,{'id':name,'name':name,'kind':'trainer','size':'Medium','level':20,'stats':{'hp':40,'atk':20,'def':20,'spa':20,'spd':20,'spe':20},'skills':{'육상':'미숙'},'movement':{'land':6,'power':6},'moves':['move/화염방사'],'items':{'돌':2}})
    def carry(self,weight,**kw):
        return self.e.gm.set_carried_objects(self.a,[{'id':'crate','weight_kg':weight}],'GM weighed the crate',**kw)
    def turn(self):
        self.e.start_round([self.a,self.b]);self.e.start_of_turn(self.a)
    def test_all_sixteen_rows_match_original_table_without_dc_substitution(self):
        lines=(ROOT/'input/ch06-gameplay.md').read_text(encoding='utf-8').splitlines()[100:116]
        rows=[]
        for line in lines:
            nums=re.findall(r'\d+(?:\.\d+)?',line)
            if len(nums)==5:rows.append([float(x) for x in nums])
        self.assertEqual(len(rows),16)
        for row in rows:
            self.a.spec['movement']['power']=int(row[0]);table=CAP.limits(self.a)
            self.assertEqual(table['heavy']+[table['staggering'],table['drag']],row[1:])
    def test_heavy_speed_accuracy_evasion_are_live_and_release_restores_other_stages(self):
        self.a.stages['spe']=2;before=self.a.staged('spe');self.carry(40)
        self.assertEqual(self.a.stages['spe'],2);self.assertEqual(self.a.staged('spe'),20)
        self.assertEqual(self.a.evasion('물리'),2)
        self.assertEqual(self.e.move_profile(self.a),(6,'육상'))
        self.b.stats['spe']=0;self.b.stats['spd']=0
        move=self.rules.move('move/화염방사')
        self.assertFalse(self.e.accuracy_check(self.a,self.b,move,fixed_roll=3)[0])
        self.e.gm.set_carried_objects(self.a,[],'crate released')
        self.assertEqual(self.a.staged('spe'),before)
        self.assertTrue(self.e.accuracy_check(self.a,self.b,move,fixed_roll=3)[0])
    def test_heavy_can_use_real_standard_and_shift_without_global_hand_ban(self):
        self.carry(40);self.turn()
        self.assertTrue(TURN.spend(self.e,self.a,'standard','ordinary action'))
        self.e.approach(self.a,self.b)
        self.assertEqual(self.a.budget['shift'],0);self.assertGreater(self.a.pos[0],1)
    def test_contextual_hand_block_stops_only_named_move_before_cost_rng(self):
        self.carry(40,blocked_actions=['move/화염방사']);self.turn()
        before=deepcopy(self.a.budget);rng=self.e.rng.getstate()
        self.assertEqual(self.e.use_move(self.a,self.b,'move/화염방사'),0)
        self.assertEqual(self.a.budget,before);self.assertEqual(self.e.rng.getstate(),rng)
        self.assertTrue(TURN.spend(self.e,self.a,'swift','unrelated action'))
    def test_staggering_prevents_standard_and_actual_move_before_cost_or_roll(self):
        self.carry(60);self.turn();before=deepcopy(self.a.budget);rng=self.e.rng.getstate()
        self.assertFalse(TURN.spend(self.e,self.a,'standard'))
        self.assertEqual(self.e.use_move(self.a,self.b,'move/화염방사'),0)
        self.assertEqual(self.a.budget,before);self.assertEqual(self.e.rng.getstate(),rng)
        self.assertEqual(self.a.staged('spe'),12);self.assertEqual(self.a.evasion('물리'),0)
    def test_staggering_caps_actual_shift_to_one_metre_even_with_sprint_marker(self):
        self.carry(60);self.turn();self.a.custom_conditions['질주']={}
        self.assertEqual(self.e.move_profile(self.a)[0],1)
        self.e.approach(self.a,self.b)
        self.assertEqual(max(abs(self.a.pos[0]-1),abs(self.a.pos[1]-2)),1);self.assertEqual(self.a.budget['shift'],0)
    def test_high_skill_result_cannot_authorize_overweight_carry(self):
        self.a.spec['skills']['육상']='달인'
        self.assertEqual(self.e.skill_roll(self.a,'육상',fixed=[6]*6).total,36)
        before=deepcopy(self.a.spec);rng=self.e.rng.getstate()
        with self.assertRaises(ValueError):self.carry(105)
        self.assertEqual(self.a.spec,before);self.assertEqual(self.e.rng.getstate(),rng)
    def test_heavy_endpoints_require_gm_and_cannot_override_other_intervals(self):
        # Historical method ID retained; the source defines both endpoints.
        for weight in (34, 52):
            self.e.gm.set_carried_objects(self.a,
                [{'id':'endpoint-'+str(weight), 'weight_kg':weight}], 'actual endpoint load')
            self.assertEqual(CAP.load(self.a)['band'],'heavy')
            self.assertEqual(CAP.accuracy(self.a),-2)
        self.carry(52,boundary_band='heavy')
        self.assertEqual(CAP.load(self.a)['band'],'heavy')
        for weight,band in ((34,'normal'),(52,'staggering'),(60,'normal')):
            before=deepcopy((self.a.spec,self.e._physical_objects));rng=self.e.rng.getstate()
            with self.assertRaises(ValueError):self.carry(weight,boundary_band=band)
            self.assertEqual((self.a.spec,self.e._physical_objects),before)
            self.assertEqual(self.e.rng.getstate(),rng)
    def test_objects_sum_identity_invalid_weight_and_missing_power(self):
        self.e.gm.set_carried_objects(self.a,[{'id':'one','weight_kg':30},{'id':'two','weight_kg':30}],'two actual loads')
        self.assertEqual(CAP.load(self.a)['band'],'staggering')
        before=deepcopy(self.a.spec)
        for weight in [True,-1,float('nan')]:
            with self.assertRaises(ValueError):self.carry(weight)
        with self.assertRaises(ValueError):self.e.gm.set_carried_objects(self.a,[{'id':'same','weight_kg':1}]*2,'duplicate')
        self.assertEqual(self.a.spec,before)
        del self.a.spec['movement']['power']
        with self.assertRaises(ValueError):CAP.load(self.a)
    def test_staggering_check_required_each_round_equality_and_no_duplicate(self):
        self.carry(60);self.turn();rng=self.e.rng.getstate()
        with self.assertRaises(ValueError):self.e.end_of_turn(self.a)
        self.assertEqual(self.e.rng.getstate(),rng)
        result=self.e.carry_check(self.a,fixed=iter([2,2]));self.assertTrue(result.passed)
        self.assertEqual(result.dc,4)
        with self.assertRaises(ValueError):self.e.carry_check(self.a,fixed=[6,6])
        self.e.end_of_turn(self.a)
        self.e.start_round([self.a,self.b]);self.e.start_of_turn(self.a)
        with self.assertRaises(ValueError):self.e.end_of_turn(self.a)
        self.assertTrue(self.e.carry_check(self.a,fixed=[2,2]).passed)
        self.e.end_of_turn(self.a)
    def test_failed_carry_check_waits_for_gm_without_automatic_drop_or_damage(self):
        self.carry(60);self.turn();hp=self.a.hp
        result=self.e.carry_check(self.a,fixed=[1,1])
        self.assertIsInstance(result,C.PendingDecision);self.assertEqual(result.check.total,2)
        self.assertEqual(self.a.hp,hp);self.assertEqual(CAP.load(self.a)['band'],'staggering')
        before=self.a.pos;self.e.approach(self.a,self.b);self.assertEqual(self.a.pos,before)
        with self.assertRaises(ValueError):self.e.end_of_turn(self.a)
        self.e.gm.resolve_carry_failure(self.a,outcome='release',reason='GM decides safely lowering the crate')
        self.assertEqual(CAP.load(self.a)['band'],'normal');self.e.end_of_turn(self.a)
    def test_failed_release_clears_actual_carrier_and_survives_both_restores(self):
        import world_entities as W,state_codec as CODEC
        self.carry(60);self.turn();self.e.carry_check(self.a,fixed=[1,1])
        self.e.gm.resolve_carry_failure(self.a,outcome='release',reason='safely released; landing unknown')
        obj=self.e._physical_objects['crate']
        self.assertNotIn('carrier_id',obj)
        self.assertEqual(W.effective_location(self.e,obj),{'kind':'unknown'})
        self.assertTrue(W.validate_world(self.e)['valid'])
        self.e.gm.snapshot('released')
        loaded=CODEC.load_engine(self.rules,CODEC.dump_engine(self.e))
        self.assertNotIn('carrier_id',loaded._physical_objects['crate'])
        self.e.gm.set_carried_objects(self.b,[{'id':'crate','weight_kg':60}],'another actual carrier')
        self.assertEqual(self.e._physical_objects['crate']['carrier_id'],self.b.entity_id)
        self.e.gm.restore('released');self.assertNotIn('carrier_id',self.e._physical_objects['crate'])
        self.assertFalse(self.a.spec['_carried_load']['failure_pending'])
    def test_failed_carry_continue_keeps_object_and_invalid_choice_is_atomic(self):
        self.carry(60);self.turn();self.e.carry_check(self.a,fixed=[1,1])
        before=deepcopy((self.a.spec,self.e._physical_objects))
        with self.assertRaises(ValueError):self.e.gm.resolve_carry_failure(self.a,outcome='vanish',reason='invalid')
        self.assertEqual((self.a.spec,self.e._physical_objects),before)
        self.e.gm.resolve_carry_failure(self.a,outcome='continue',reason='GM allows continued hold')
        self.assertEqual(self.e._physical_objects['crate']['carrier_id'],self.a.entity_id)
        self.assertEqual(CAP.load(self.a)['band'],'staggering')
        self.assertFalse(self.a.spec['_carried_load']['failure_pending'])
    def test_snapshot_restores_actual_load_and_per_round_check_history(self):
        self.carry(60);self.turn();self.e.carry_check(self.a,fixed=[2,2])
        self.e.gm.snapshot('carrying')
        self.e.gm.set_carried_objects(self.a,[],'drop')
        self.e.gm.restore('carrying')
        self.assertEqual(CAP.load(self.a)['band'],'staggering')
        with self.assertRaises(ValueError):self.e.carry_check(self.a,fixed=[6,6])
    def test_throwing_uses_actual_inventory_range_cost_and_no_automatic_hit(self):
        self.assertEqual(CAP.throwing_range(self.e,self.a),6);self.turn()
        out=self.e.throw_small_object(self.a,item='돌',destination=(7,2),small_object=True,action_cost='standard',reason='GM chosen generic object throw cost')
        self.assertEqual(out['distance'],6);self.assertIsNone(out['hit'])
        self.assertEqual(self.a.spec['items']['돌'],1);self.assertEqual(self.a.budget['standard'],0)
        self.assertEqual(self.a.spec['thrown_objects'][0]['destination'],[7,2])
    def test_out_of_range_big_unowned_and_blocked_throw_do_not_spend(self):
        self.turn();before=deepcopy(self.a.spec);budget=deepcopy(self.a.budget)
        opts=dict(item='돌',destination=(8,2),small_object=True,action_cost='standard',reason='GM')
        with self.assertRaises(ValueError):self.e.throw_small_object(self.a,**opts)
        opts['destination']=(2,2);opts['small_object']=False
        self.assertIsInstance(self.e.throw_small_object(self.a,**opts),C.PendingDecision)
        opts['small_object']=True;opts['item']='unowned'
        with self.assertRaises(ValueError):self.e.throw_small_object(self.a,**opts)
        self.assertEqual(self.a.spec,before);self.assertEqual(self.a.budget,budget)
    def test_virtuoso_throws_twelve_metres_but_skill_roll_keeps_six_dice(self):
        self.a.spec['skills']['육상']='달인';self.a.spec['edges']=['edge/거장'];self.a.spec['edge_choices']={'Virtuoso':['육상']}
        self.assertEqual(CAP.throwing_range(self.e,self.a),12)
        self.assertEqual(self.e.skill_roll(self.a,'육상',fixed=[1]*6).rank,6)
    def test_fainted_no_throw_and_pokemon_does_not_use_trainer_throwing_rule(self):
        self.a.hp=0
        self.assertFalse(self.e.throw_small_object(self.a,item='돌',destination=(2,2),small_object=True,action_cost='standard',reason='GM'))
        self.a.kind='pokemon'
        with self.assertRaises(ValueError):CAP.throwing_range(self.e,self.a)
    def test_drag_moves_actual_object_and_actor_at_most_once_per_round(self):
        self.e.gm.set_physical_object('cart',weight_kg=150,position=(2,2),reason='GM world')
        self.turn()
        out=self.e.drag_object(self.a,object_id='cart',destination=(3,2),actor_destination=(2,2),action_cost='shift',reason='GM push')
        self.assertEqual(out['position'],(3,2));self.assertEqual(self.a.pos,(2,2));self.assertEqual(self.a.budget['shift'],0)
        with self.assertRaises(ValueError):self.e.drag_object(self.a,object_id='cart',destination=(4,2),actor_destination=(3,2),action_cost='standard',reason='GM push again')
        self.assertEqual(self.e._physical_objects['cart']['pos'],(3,2))
    def test_drag_limits_equality_and_favorable_condition_do_not_invent_multiplier(self):
        self.e.gm.set_physical_object('cart',weight_kg=208,position=(2,2),reason='GM world')
        opts=dict(object_id='cart',destination=(3,2),actor_destination=(2,2),action_cost='shift',reason='wheels',round_id='a')
        self.assertIsInstance(self.e.drag_object(self.a,**opts),C.PendingDecision)
        self.e._physical_objects['cart']['weight_kg']=209
        with self.assertRaises(ValueError):self.e.drag_object(self.a,**opts)
        out=self.e.drag_object(self.a,**opts,favorable_limit=300)
        self.assertEqual(out['limit_kg'],300)
    def test_drag_cannot_become_lift_and_invalid_path_has_no_cost(self):
        with self.assertRaises(ValueError):self.carry(150)
        self.e.gm.set_physical_object('cart',weight_kg=150,position=(2,2),reason='GM world')
        self.turn();before=deepcopy(self.a.budget)
        with self.assertRaises(ValueError):self.e.drag_object(self.a,object_id='cart',destination=(5,2),action_cost='shift',reason='GM')
        self.assertEqual(self.a.budget,before);self.assertEqual(self.e._physical_objects['cart']['pos'],(2,2))
    def test_drag_snapshot_preserves_world_object_and_round_use(self):
        self.e.gm.set_physical_object('cart',weight_kg=150,position=(2,2),reason='GM world')
        self.turn();self.e.gm.snapshot('cart')
        self.e.drag_object(self.a,object_id='cart',destination=(3,2),actor_destination=(2,2),action_cost='shift',reason='GM')
        self.e.gm.restore('cart');self.assertEqual(self.e._physical_objects['cart']['pos'],(2,2))
        self.assertEqual(self.a.pos,(1,2));self.assertNotIn('_drag_round',self.a.spec)
    def test_round_cannot_skip_required_carry_check_by_omitting_actor_turn(self):
        self.carry(60);self.e.start_round([self.a,self.b]);before=self.e.elapsed_seconds
        with self.assertRaises(ValueError):self.e.end_round()
        self.assertEqual(self.e.elapsed_seconds,before)
        self.e.carry_check(self.a,fixed=[2,2]);self.e.end_round()
        self.assertEqual(self.e.elapsed_seconds,before+10)
    def test_source_scope_hashes_unchanged(self):
        ledger=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'))
        for e in ledger['entries']:
            if e['id'] in ['C3-CORE-036','C3-CORE-037','C3-CORE-038','C3-CORE-039','C3-CORE-040','C3-CORE-041','C3-CORE-042']:
                src=e['source_snapshot']['source'];lines=(ROOT/src['file']).read_text(encoding='utf-8-sig').splitlines()
                self.assertEqual('\n'.join(lines[src['start']-1:src['end']]),src['excerpt'])
if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
        def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
    r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    files=['engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/combat_social_edges.py','engine/net_capsule.py','engine/trainer_capabilities.py','engine/skill_feature_actions.py','engine/researcher_features.py','engine/precise_actions.py','engine/environmental_effects.py','engine/wild_equipment.py','engine/injury_recovery.py','engine/downtime.py','engine/items.py','engine/common_action_checks.py','engine/heavy_injury_adapter.py','engine/jump_actions.py','engine/context_actions.py','engine/pokemon_requests.py','engine/combat_timing.py','engine/combat_maneuvers.py','data/context-check-policy.json','data/cultivation-policy.json','engine/movement_actions.py','engine/weapon_actions.py','data/weapon-policy.json','engine/bandages.py','engine/crafting_activities.py','engine/contest_features.py','data/planter-policy.json','engine/temporary_hp.py','engine/capability_actions.py','engine/physical_limits.py','engine/engine.py','engine/turn.py','engine/action_lifecycle.py','engine/gm_state.py','engine/effects_ext.py','engine/skill_modifiers.py','engine/common_checks.py','engine/grid.py','engine/ruleset.py','data/capability-policy.json','data/skill-check-policy.json','data/core-rules.json','data/lookup-tables.json','input/ch02-character-creation.md','input/ch06-gameplay.md','input/ch03-skills-edges-feats.md','output/ruleunits.jsonl','tools/test_category3_capabilities.py']
    files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
    files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
    files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

    files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

    files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':r.wasSuccessful(),'results':r.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
    (ROOT/'output/category3-capability-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if r.wasSuccessful() else 1)
