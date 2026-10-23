"""Independent common life-state boundaries, real engine adapters and persistence."""
import hashlib,json,sys,unittest
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
import effects as FX
import effects_ext as EXT
import downtime as DT
import turn as TURN

class LifeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
    def fixture(self,**policy):
        e=Engine(self.rules,**policy)
        c=Combatant(self.rules,dict(name='Life',level=3,kind='pokemon',stats={'hp':9,'atk':5,'def':5,'spa':5,'spd':5,'spe':5},types=['노말'],moves=[]))
        e.everyone=e.gm.everyone=[c]
        self.assertEqual(c.base_max_hp,40)
        return e,c
    def knocked_out(self):
        e,c=self.fixture();c.hp=-1;e.check_fainted(c);return e,c
    def test_death_threshold_equality_and_both_maximum_branches(self):
        for maxhp,points in [(40,[(-79,False),(-80,True),(-81,True)]),(20,[(-49,False),(-50,True),(-51,True)])]:
            for hp,dead in points:
                e,c=self.fixture()
                if maxhp==20:c.level=1;c.stats['hp']=3
                c.hp=hp;e.check_fainted(c)
                self.assertEqual(c.dead,dead,(maxhp,hp))
    def test_injury_death_includes_positive_hp_and_already_fainted(self):
        for hp in [1,-1]:
            for prior in [False,True]:
                e,c=self.fixture(friendly_battle=True);c.hp=hp;c.injuries=10
                if prior:c.conditions.add('기절')
                e.check_fainted(c);self.assertTrue(c.dead,(hp,prior))
    def test_friendly_suppresses_hp_death_only(self):
        e,c=self.fixture(friendly_battle=True);c.hp=-1000;c.injuries=9;e.check_fainted(c)
        self.assertFalse(c.dead);c.injuries=10;e.check_fainted(c);self.assertTrue(c.dead)
    def test_campaign_death_disable_does_not_disable_fainting(self):
        e,c=self.fixture(death_enabled=False);c.hp=-1000;c.injuries=10;e.check_fainted(c)
        self.assertFalse(c.dead);self.assertTrue(c.fainted)
    def test_additional_injury_effect_checks_death(self):
        e,c=self.fixture();c.injuries=9;c.hp=1
        EXT.h_injury(e,c,c,{'value':1},{})
        self.assertTrue(c.dead);self.assertFalse(TURN.can_act(e,c))
    def test_already_fainted_further_hp_loss_can_kill(self):
        e,c=self.fixture();c.hp=-79;e.check_fainted(c);self.assertFalse(c.dead)
        e.lose_hp(c,1);self.assertTrue(c.dead)
    def test_death_persists_through_ordinary_heal_revive_and_rest(self):
        e,c=self.fixture();c.hp=-80;e.check_fainted(c)
        e.heal(c,200,source_kind='ordinary_item');self.assertFalse(e.revive(c,40))
        DT.rest(e,c,600);DT.extended_rest(e,c,24);DT.pokemon_center(e,c)
        self.assertTrue(c.dead);self.assertEqual(c.hp,-80);self.assertTrue(c.fainted)
    def test_death_persists_through_full_restore_effect(self):
        e,c=self.fixture();c.hp=-80;e.check_fainted(c)
        EXT.h_full_restore(e,c,c,{'heal_injuries':10},{})
        self.assertTrue(c.dead);self.assertEqual(c.hp,-80)
    def test_faint_cures_persistent_and_volatile_with_stage_restoration(self):
        e,c=self.fixture();e.apply_status(c,'독');e.apply_status(c,'혼란')
        self.assertEqual(c.stages['spd'],-2)
        c.hp=0;e.check_fainted(c)
        self.assertNotIn('독',c.conditions);self.assertNotIn('혼란',c.conditions)
        self.assertEqual(c.stages['spd'],0);self.assertTrue(c.fainted)
    def test_faint_preserves_temporary_hp_other_conditions_and_injuries(self):
        e,c=self.fixture();c.conditions.update(['임시 체력','실명','취약']);c.temp_hp=12;c.injuries=2;c.hp=0
        e.check_fainted(c)
        self.assertTrue({'임시 체력','실명','취약'}<=c.conditions);self.assertEqual((c.temp_hp,c.injuries),(12,2))
    def test_rechecking_faint_does_not_double_restore_stages(self):
        e,c=self.fixture();e.apply_status(c,'독');c.hp=0;e.check_fainted(c);e.check_fainted(c)
        self.assertEqual(c.stages['spd'],0)
    def test_timer_does_not_start_at_knockout(self):
        e,c=self.knocked_out();e.advance_time(3600,[c])
        self.assertTrue(c.fainted);self.assertIsNone(c.faint_recovery_seconds)
    def test_ordinary_item_timer_starts_at_positive_hp_and_expires_at_600(self):
        e,c=self.knocked_out();e.advance_time(3600,[c]);e.heal(c,10,source_kind='ordinary_item')
        self.assertEqual((c.hp,c.faint_recovery_seconds),(9,600));self.assertTrue(c.fainted)
        e.advance_time(599,[c]);self.assertTrue(c.fainted)
        e.advance_time(1,[c]);self.assertFalse(c.fainted);self.assertEqual(c.hp,9)
    def test_ordinary_heal_to_zero_does_not_start_timer(self):
        e,c=self.knocked_out();e.heal(c,1,source_kind='ordinary_item');e.advance_time(600,[c])
        self.assertTrue(c.fainted);self.assertIsNone(c.faint_recovery_seconds)
    def test_move_and_feature_healing_to_positive_hp_revive_immediately(self):
        for source in ['move','feature']:
            e,c=self.knocked_out();e.heal(c,10,source_kind=source)
            self.assertFalse(c.fainted);self.assertIsNone(c.faint_recovery_seconds)
    def test_move_healing_not_positive_cannot_revive(self):
        e,c=self.knocked_out();e.heal(c,1,source_kind='move');self.assertTrue(c.fainted)
    def test_unspecified_or_rest_healing_does_not_invent_revival_timing(self):
        for source in ['unspecified','rest']:
            e,c=self.knocked_out();e.heal(c,10,source_kind=source);e.advance_time(6000,[c])
            self.assertTrue(c.fainted);self.assertTrue(c.faint_recovery_pending)
    def test_repeated_positive_item_healing_preserves_original_deadline(self):
        e,c=self.knocked_out();e.heal(c,10,source_kind='ordinary_item');e.heal(c,1,source_kind='ordinary_item');e.advance_time(600,[c])
        self.assertFalse(c.fainted);self.assertIsNone(c.faint_recovery_pending)
    def test_reinjury_requires_a_new_positive_crossing_and_full_interval(self):
        e,c=self.knocked_out();e.heal(c,10,source_kind='ordinary_item');e.lose_hp(c,10)
        self.assertIsNone(c.faint_recovery_seconds);self.assertTrue(c.faint_recovery_pending)
        e.heal(c,10,source_kind='ordinary_item');e.advance_time(599,[c]);self.assertTrue(c.fainted)
        e.advance_time(1,[c]);self.assertFalse(c.fainted)
    def test_explicit_revive_can_resolve_pending_faint_recovery(self):
        e,c=self.knocked_out();e.heal(c,10);self.assertTrue(c.faint_recovery_pending)
        self.assertTrue(e.revive(c,10));self.assertFalse(c.fainted);self.assertIsNone(c.faint_recovery_pending)
    def test_healing_cannot_reduce_hp_above_injury_recovery_ceiling(self):
        e,c=self.fixture();c.injuries=5;c.hp=30
        self.assertEqual(c.max_hp,20);self.assertEqual(e.heal(c,5),0);self.assertEqual(c.hp,30)
    def test_general_status_cure_cannot_remove_faint_or_temporary_hp(self):
        e,c=self.knocked_out();c.conditions.add('임시 체력');c.temp_hp=10
        e.cure_status(c,'기절');e.cure_status(c,'임시 체력')
        self.assertTrue(c.fainted);self.assertIn('임시 체력',c.conditions);self.assertEqual(c.temp_hp,10)
    def test_effect_dispatch_preserves_item_move_and_feat_healing_origin(self):
        for src,still_fainted in [('item/test',True),('move/test',False),('feat/test',False)]:
            e,c=self.knocked_out();FX.run_effects(e,c,c,[{'type':'heal','amount':10}],{'hit':True},src)
            self.assertEqual(c.fainted,still_fainted,src)
    def test_delayed_move_heal_preserves_origin(self):
        e,c=self.knocked_out()
        FX.run_effects(e,c,c,[{'type':'delayed_heal','fraction_of_max':[1,2]}],{'hit':True},'move/test')
        EXT.end_of_turn(e,c);self.assertFalse(c.fainted)
    def test_rest_advances_existing_item_recovery_timer(self):
        e,c=self.knocked_out();e.heal(c,10,source_kind='ordinary_item');DT.rest(e,c,9)
        self.assertTrue(c.fainted);DT.rest(e,c,1);self.assertFalse(c.fainted)
    def test_heavily_injured_rest_still_advances_recovery_clock(self):
        e,c=self.knocked_out();c.injuries=5;e.heal(c,10,source_kind='ordinary_item');hp=c.hp
        DT.rest(e,c,10);self.assertFalse(c.fainted);self.assertEqual(c.hp,hp)
    def test_elapsed_interval_deduplicates_actors_and_rejects_bad_values(self):
        e,c=self.knocked_out();e.heal(c,10,source_kind='ordinary_item');e.advance_time(300,[c,c])
        self.assertEqual(c.faint_recovery_seconds,300)
        for value in [-1,True,0.5]:
            with self.assertRaises(ValueError):e.advance_time(value,[c])
        self.assertEqual(c.faint_recovery_seconds,300)
    def test_snapshot_rewinds_timer_death_and_policy_together(self):
        e,c=self.knocked_out();e.heal(c,10,source_kind='ordinary_item');e.gm.snapshot('alive')
        c.injuries=10;e.check_fainted(c);e.friendly_battle=True;e.death_enabled=False
        e.gm.restore('alive');self.assertFalse(c.dead);self.assertEqual(c.faint_recovery_seconds,600)
        self.assertFalse(e.friendly_battle);self.assertTrue(e.death_enabled)
        e.advance_time(600,[c]);self.assertFalse(c.fainted)
    def test_gm_revive_is_explicit_external_override(self):
        e,c=self.fixture();c.hp=-80;e.check_fainted(c);e.gm.revive(c,10,reason='explicit test ruling')
        self.assertFalse(c.dead);self.assertFalse(c.fainted)
        self.assertTrue(any('explicit test ruling' in line for line in e.log_lines))
    def test_ordinary_ability_trigger_cannot_fire_while_fainted(self):
        e,c=self.knocked_out();c.ability_triggers=[dict(name='test',spec={'event':'turn_start'},effects=[{'type':'heal','amount':10}],frequency='장면 1회')]
        FX.fire_event(e,c,{'event':'turn_start'})
        self.assertEqual(c.hp,-1);self.assertNotIn('ab:test',c.counters)
    def test_dead_actor_cannot_fire_even_a_self_faint_trigger(self):
        e,c=self.fixture();c.hp=-80;e.check_fainted(c)
        c.ability_triggers=[dict(name='test',spec={'event':'self_faint'},effects=[{'type':'counter','name':'test','value':1}])]
        FX.fire_event(e,c,{'event':'self_faint'});self.assertNotIn('ab:test',c.counters)
    def test_unconscious_common_check_rejected_before_rng(self):
        e,c=self.knocked_out();state=e.rng.getstate()
        with self.assertRaises(ValueError):e.skill_check(c,'test',10)
        self.assertEqual(e.rng.getstate(),state)
    def test_fainting_retains_zero_evasion_after_sleep_cure(self):
        e,c=self.fixture();e.apply_status(c,'잠듦');c.stats['def']=20;c.hp=0;e.check_fainted(c)
        self.assertNotIn('잠듦',c.conditions);self.assertEqual(c.evasion('물리'),0)
        e.revive(c,10);self.assertEqual(c.evasion('물리'),4)
    def test_full_restore_and_center_do_not_lower_above_ceiling_hp(self):
        e,c=self.fixture();c.injuries=1;c.hp=40
        EXT.h_full_restore(e,c,c,{},{});self.assertEqual(c.hp,40)
        c.spec['center_injuries_today']=3;DT.pokemon_center(e,c);self.assertEqual(c.hp,40)
    def test_drain_and_injury_heal_preserve_move_origin(self):
        e,c=self.knocked_out();FX.h_drain(e,c,c,{'fraction':0.5},{'dealt':20,'healing_source_kind':'move'})
        self.assertFalse(c.fainted)
        e,c=self.knocked_out();c.injuries=1
        EXT.h_heal_injury(e,c,c,{'value':1,'heal_per_injury':'tick'},{'healing_source_kind':'move'})
        self.assertFalse(c.fainted)
    def test_life_spec_source_integrity_and_false_completion_rejected(self):
        import copy
        from audit_life_state import validate
        spec=json.loads((ROOT/'data/verification/life-state-semantics.json').read_text(encoding='utf-8'))
        self.assertEqual(validate(spec,ROOT),[])
        bad=copy.deepcopy(spec);bad['certification']['whole_rule_certified']=True
        self.assertIn('unsupported_life_certification',validate(bad,ROOT))
        bad=copy.deepcopy(spec);bad['clauses'][0]['sources'][0]['excerpt']='invented'
        self.assertIn('stale_review_excerpt:LIFE-01',validate(bad,ROOT))
    def test_hp_transfer_does_not_assume_revival_authority(self):
        e,c=self.knocked_out();donor=Combatant(self.rules,dict(c.spec,name='donor'))
        EXT.h_hp_share(e,donor,c,{}, {'healing_source_kind':'move'})
        self.assertGreater(c.hp,0);self.assertTrue(c.fainted);self.assertTrue(c.faint_recovery_pending)
    def test_life_policy_requires_real_boolean(self):
        for options in [dict(death_enabled='false'),dict(friendly_battle=1)]:
            with self.assertRaises(ValueError):Engine(self.rules,**options)

if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='LIFE-'+t._testMethodName,status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='LIFE-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='LIFE-'+t._testMethodName,status='error'))
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(LifeTests))
    paths=[ROOT/'tools/audit_life_state.py',ROOT/'tools/audit_world_state_semantics.py',Path(__file__)]+[ROOT/p for p in ['engine/life.py','engine/engine.py','engine/effects.py','engine/effects_ext.py','engine/items.py','engine/downtime.py','engine/gm_state.py','data/core-rules.json','data/conditions.json','data/verification/life-state-semantics.json','input/ch07-combat.md']]
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),scope='Common death/faint/healing boundary components; unresolved repeated-healing timing is held. Not whole life-rule certification.',results=result.rows,input_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (ROOT/'output/life-state-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
