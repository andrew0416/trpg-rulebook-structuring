"""C3-EX-024: owned social edges through native moves, saves and initiative."""
import hashlib,json,sys,unittest
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
import combat_social_edges as SOCIAL
import combat_timing as TIMING
import items as ITEMS

class FixedRng:
    def __init__(self,values):self.values=list(values)
    def randint(self,a,b):
        value=self.values.pop(0)
        assert type(value) is int and a<=value<=b,(a,b,value)
        return value

class SocialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(str(ROOT))
    def setUp(self):
        self.e=Engine(self.r,seed=541)
        self.a=self.actor('social trainer');self.t=self.actor('target','pokemon')
        self.a.spec['edges']=[SOCIAL.FLUSTER];self.a.side='party';self.t.side='wild'
        self.e.everyone=[self.a,self.t];self.e.gm.everyone=[self.a,self.t]
    def actor(self,name,kind='trainer'):
        return Combatant(self.r,{'name':name,'kind':kind,'size':'medium','level':30,
            'stats':{'hp':60,'atk':20,'def':10,'spa':20,'spd':15,'spe':5},
            'skills':{'매력':'숙련','교활':'미숙','집중':'전문'},
            'moves':['move/애교부리기','move/부추기기','move/째려보기','move/칼춤'],
            'movement':{'land':6}})
    def begin(self,count=20):
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=count)
    def hit(self,face=15,move='move/애교부리기'):
        self.e.rng=FixedRng([face]);self.e.use_move(self.a,self.t,move)
        self.assertFalse(self.e.rng.values)
    def smooth(self):
        self.t=self.actor('smooth defender');self.t.spec['edges']=[SOCIAL.SMOOTH]
        self.e.everyone=[self.a,self.t];self.e.gm.everyone=[self.a,self.t]
    def test_source_exact_scope_and_acquisition_duration_context(self):
        ledger=json.loads((ROOT/'data/verification/category3-register.json').read_text('utf-8'))
        entry=next(x for x in ledger['entries'] if x['id']=='C3-EX-024')
        for anchor in entry['source_snapshot']['source_anchors']:
            lines=(ROOT/anchor['file']).read_text('utf-8-sig').splitlines()
            self.assertEqual('\n'.join(lines[anchor['start_line']-1:anchor['end_line']]),anchor['excerpt'])
        lines=(ROOT/'input/ch03-skills-edges-feats.md').read_text('utf-8').splitlines()
        self.assertIn('숙련 매력 또는 숙련 교활',lines[446])
        self.assertIn('전문 매력 또는 전문 집중',lines[470])
        self.assertIn('다음 라운드에서 동일한 이니셔티브', (ROOT/'input/ch07-combat.md').read_text('utf-8').splitlines()[33])
    def test_native_owned_social_hit_applies_volatile_penalty_after_real_standard(self):
        ITEMS.register_feats(self.e,self.a);self.begin();self.hit()
        self.assertEqual(self.a.budget['standard'],0)
        self.assertEqual(self.t.stages['atk'],-2)
        self.assertEqual(SOCIAL.save_bonus(self.e,self.t,'혼란'),-2)
        self.assertEqual(TIMING.records(self.t)[0]['count_deadline'],(2,20))
        self.assertIs(TIMING.records(self.t)[0]['attacker'],self.a)
    def test_social_miss_and_unowned_or_nonsocial_move_do_not_apply(self):
        self.begin();self.hit(1);self.assertFalse(TIMING.records(self.t))
        self.setUp();self.a.spec['edges']=[];self.begin();self.hit();self.assertFalse(TIMING.records(self.t))
        self.setUp();self.begin();self.e.use_move(self.a,self.a,'move/칼춤');self.assertFalse(TIMING.records(self.a))
    def test_unlearned_social_move_preserves_standard_and_never_installs(self):
        self.a.moves.remove('move/애교부리기');self.begin();state=self.e.rng.getstate()
        with self.assertRaisesRegex(ValueError,'learned move'):self.e.use_move(self.a,self.t,'move/애교부리기')
        self.assertEqual(self.a.budget['standard'],1);self.assertEqual(self.e.rng.getstate(),state)
        self.assertFalse(TIMING.records(self.t))
    def test_fluster_native_save_fail_at_seventeen_and_success_at_eighteen(self):
        for roll,cured in [(17,False),(18,True)]:
            self.setUp();self.begin();self.hit(move='move/부추기기');self.assertIn('혼란',self.t.conditions)
            self.e.end_of_turn(self.a);self.e.start_of_turn(self.t,initiative_count=10)
            self.e.rng=FixedRng([roll]);self.e.end_of_turn(self.t)
            self.assertEqual('혼란' not in self.t.conditions,cured);self.assertFalse(self.e.rng.values)
    def test_fluster_does_not_penalize_native_persistent_paralysis_save(self):
        self.begin();self.hit();self.e.apply_status(self.t,'마비')
        self.e.end_of_turn(self.a);self.e.rng=FixedRng([11]);result=self.e.start_of_turn(self.t,initiative_count=10)
        self.assertIsNone(result);self.assertFalse(self.e.rng.values)
    def test_fluster_expires_at_next_same_initiative_not_turn_or_first_round_end(self):
        self.begin();self.hit();self.e.end_of_turn(self.a)
        self.e.start_of_turn(self.t,initiative_count=10);self.e.end_of_turn(self.t)
        self.assertEqual(SOCIAL.save_bonus(self.e,self.t,'난동'),-2)
        self.e.end_round();self.assertEqual(SOCIAL.save_bonus(self.e,self.t,'난동'),-2)
        self.e.start_round(self.e.everyone);self.e.at_initiative_count(21)
        self.assertEqual(SOCIAL.save_bonus(self.e,self.t,'난동'),-2)
        self.e.at_initiative_count(20);self.assertEqual(SOCIAL.save_bonus(self.e,self.t,'난동'),0)
    def test_fluster_snapshot_preserves_actual_owner_and_expiry_state(self):
        self.begin();self.hit();self.e.rng=__import__('random').Random(541);self.e.gm.snapshot('social')
        self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round(self.e.everyone);self.e.at_initiative_count(20)
        self.assertFalse(TIMING.records(self.t));self.e.gm.restore('social')
        self.assertEqual(self.e.round_no,1);self.assertIs(TIMING.records(self.t)[0]['attacker'],self.a)
        self.assertEqual(SOCIAL.save_bonus(self.e,self.t,'혼란'),-2)
    def test_missing_initiative_and_overlap_hold_before_cost_frequency_or_rng(self):
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a)
        before=(dict(self.a.budget),dict(self.a.move_uses),self.e.rng.getstate())
        with self.assertRaisesRegex(ValueError,'initiative'):self.e.use_move(self.a,self.t,'move/애교부리기')
        self.assertEqual(before,(dict(self.a.budget),dict(self.a.move_uses),self.e.rng.getstate()))
        self.setUp();other=self.actor('second social owner');other.spec['edges']=[SOCIAL.FLUSTER];other.side='party'
        self.e.everyone.append(other);self.begin();self.hit();self.e.end_of_turn(self.a)
        self.e.start_of_turn(other,initiative_count=19);self.e.rng=__import__('random').Random(41)
        before=(dict(other.budget),dict(other.move_uses),self.e.rng.getstate())
        with self.assertRaisesRegex(ValueError,'overlapping'):self.e.use_move(other,self.t,'move/애교부리기')
        self.assertEqual(before,(dict(other.budget),dict(other.move_uses),self.e.rng.getstate()))
        self.assertEqual(len(TIMING.records(self.t)),1)
    def test_owned_prerequisite_aliases_and_unique_trainer_acquisition(self):
        for uid,skill,rank in [(SOCIAL.FLUSTER,'매력','숙련'),(SOCIAL.FLUSTER,'교활','숙련'),(SOCIAL.SMOOTH,'매력','전문'),(SOCIAL.SMOOTH,'집중','전문')]:
            actor=self.actor('owned');actor.spec['skills']={skill:rank};actor.spec['edges']=[uid]
            self.assertTrue(SOCIAL.owns(self.e,actor,uid))
        self.a.spec['edges']=['Flustering Charisma'];self.assertTrue(SOCIAL.owns(self.e,self.a,SOCIAL.FLUSTER))
        self.a.spec['feats']=['번뜩이는 카리스마']
        with self.assertRaisesRegex(ValueError,'exactly one'):ITEMS.register_feats(self.e,self.a)
        self.a.spec.pop('feats');self.a.kind='pokemon'
        with self.assertRaisesRegex(ValueError,'trainer'):ITEMS.register_feats(self.e,self.a)
    def test_invalid_owned_prerequisite_and_selected_variant_hold_before_native_cost(self):
        self.a.spec['skills']={'매력':'초보','교활':'초보'}
        with self.assertRaisesRegex(ValueError,'prerequisite'):self.e.use_move(self.a,self.t,'move/애교부리기')
        self.assertFalse(self.a.move_uses);self.assertFalse(TIMING.records(self.t))
        self.setUp();self.begin();before=(dict(self.a.budget),self.e.rng.getstate())
        original=self.r._selected_rule
        self.r._selected_rule=lambda uid,*a,**kw: uid+'-variant' if uid==SOCIAL.FLUSTER else original(uid,*a,**kw)
        try:
            with self.assertRaisesRegex(ValueError,'variant'):self.e.use_move(self.a,self.t,'move/애교부리기')
        finally:self.r._selected_rule=original
        self.assertEqual(before,(dict(self.a.budget),self.e.rng.getstate()))
    def test_smooth_native_social_accuracy_bonus_and_ordinary_move_exclusion(self):
        self.smooth();move=self.r.move('move/애교부리기')
        self.assertFalse(self.e.accuracy_check(self.a,self.t,move,fixed_roll=6)[0])
        self.assertTrue(self.e.accuracy_check(self.a,self.t,move,fixed_roll=7)[0])
        ordinary=self.r.move('move/화염방사')
        self.assertTrue(self.e.accuracy_check(self.a,self.t,ordinary,fixed_roll=ordinary['ac']+self.t.evasion('특수'))[0])
        self.assertTrue(self.e.accuracy_check(self.a,self.t,move,fixed_roll=2,waive=True)[0])
        self.assertFalse(self.e.accuracy_check(self.a,self.t,move,fixed_roll=1,situational=100)[0])
        self.assertTrue(self.e.accuracy_check(self.a,self.t,move,fixed_roll=20,situational=-100)[0])
    def test_smooth_evasion_combines_negative_evasion_before_floor_and_total_nine_cap(self):
        self.smooth();move=self.r.move('move/애교부리기');self.t.evasion_mod=-6;self.t.stats['spe']=0
        self.assertTrue(self.e.accuracy_check(self.a,self.t,move,fixed_roll=2)[0])
        self.t.stats['spe']=50;self.t.evasion_mod=6
        self.assertFalse(self.e.accuracy_check(self.a,self.t,move,fixed_roll=10)[0])
        self.assertTrue(self.e.accuracy_check(self.a,self.t,move,fixed_roll=11)[0])
    def test_smooth_evasion_never_overrides_vulnerability_or_unconsciousness(self):
        self.smooth();move=self.r.move('move/애교부리기')
        for condition in ('취약','잠듦','넘어짐','얼음','기절','실명'):
            self.t.conditions={condition}
            self.assertTrue(self.e.accuracy_check(self.a,self.t,move,fixed_roll=2)[0],condition)
        self.t.conditions=set();self.t.hp=0
        self.assertTrue(self.e.accuracy_check(self.a,self.t,move,fixed_roll=2)[0])
    def test_smooth_native_rage_and_infatuation_save_exact_bonus_boundaries(self):
        for condition,roll,cured in [('난동',12,False),('난동',13,True),('헤롱헤롱',13,False),('헤롱헤롱',14,True)]:
            self.setUp();self.smooth();ITEMS.register_feats(self.e,self.t)
            self.e.apply_status(self.t,condition,applied_by=self.a if condition=='헤롱헤롱' else None);self.e.start_round(self.e.everyone);self.e.start_of_turn(self.t,initiative_count=10)
            self.e.rng=FixedRng([roll]);self.e.end_of_turn(self.t)
            self.assertEqual(condition not in self.t.conditions,cured);self.assertFalse(self.e.rng.values)
            self.assertEqual(self.t.save_mod,0)
    def test_smooth_does_not_grant_confusion_bonus_and_repeated_registration_no_double_bonus(self):
        self.smooth();ITEMS.register_feats(self.e,self.t);ITEMS.register_feats(self.e,self.t)
        self.e.apply_status(self.t,'혼란');self.e.start_round(self.e.everyone);self.e.start_of_turn(self.t,initiative_count=10)
        self.e.rng=FixedRng([14]);self.e.end_of_turn(self.t);self.assertIn('혼란',self.t.conditions)
        self.assertEqual(SOCIAL.save_bonus(self.e,self.t,'난동'),2);self.assertEqual(self.t.save_mod,0)
    def test_smooth_and_fluster_stack_with_existing_save_mod_once(self):
        self.smooth();self.t.save_mod=1;self.begin();self.hit();self.e.apply_status(self.t,'난동')
        self.e.end_of_turn(self.a);self.e.start_of_turn(self.t,initiative_count=10)
        self.e.rng=FixedRng([14]);self.e.end_of_turn(self.t);self.assertNotIn('난동',self.t.conditions)
        self.assertEqual(SOCIAL.save_bonus(self.e,self.t,'난동'),0)
    def test_removing_owned_smooth_removes_live_bonus_without_stale_registration(self):
        self.smooth();ITEMS.register_feats(self.e,self.t);self.t.spec['edges']=[]
        self.assertEqual(SOCIAL.save_bonus(self.e,self.t,'난동'),0)
        self.assertTrue(self.e.accuracy_check(self.a,self.t,self.r.move('move/애교부리기'),fixed_roll=3)[0])
    def test_social_area_move_installs_only_on_actual_targets_with_single_standard(self):
        from grid import Grid
        other=self.actor('area target','pokemon');other.side='wild'
        self.a.pos=(3,3);self.t.pos=(4,3);other.pos=(5,3)
        self.e.grid=Grid(9,9);self.e.everyone=[self.a,self.t,other];self.begin()
        self.e.rng=FixedRng([15]);self.e.use_move_on(self.a,self.t,'move/째려보기',self.e.everyone)
        self.assertEqual(self.a.budget['standard'],0);self.assertFalse(self.e.rng.values)
        self.assertTrue(TIMING.records(self.t));self.assertTrue(TIMING.records(other))
        self.assertFalse(TIMING.records(self.a));self.assertEqual(self.t.stages['def'],-1)
    def test_scene_end_expires_only_fluster_and_cannot_leave_stale_penalty(self):
        self.begin();self.hit();self.e.end_of_turn(self.a);self.e.end_round();self.e.end_scene()
        self.assertEqual(SOCIAL.save_bonus(self.e,self.t,'혼란'),0)

if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
        def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(SocialTests))
    files=['engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/net_capsule.py','engine/trainer_capabilities.py','engine/skill_feature_actions.py','engine/researcher_features.py','engine/precise_actions.py','engine/environmental_effects.py','engine/wild_equipment.py','engine/injury_recovery.py','engine/downtime.py','engine/common_action_checks.py','engine/heavy_injury_adapter.py','engine/jump_actions.py','engine/context_actions.py','engine/pokemon_requests.py','engine/combat_maneuvers.py','data/context-check-policy.json','data/cultivation-policy.json','engine/combat_social_edges.py','engine/engine.py','engine/effects_ext.py','engine/effects.py','engine/items.py','engine/skill_modifiers.py','engine/combat_timing.py','engine/turn.py','engine/action_lifecycle.py','engine/frequency.py','engine/gm_state.py','engine/weapon_actions.py','engine/capability_actions.py','engine/passive_events.py','data/skill-check-policy.json','data/core-rules.json','data/conditions.json','data/moves-mech.json','data/moves-hand.json','data/moves-llm.json','data/feats-mech.json','data/edges-llm.json','input/ch03-skills-edges-feats.md','input/ch07-combat.md','tools/test_category3_social_edges.py']
    files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
    files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
    files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

    files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

    files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['C3-EX-024'],'results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
    (ROOT/'output/category3-social-edge-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
