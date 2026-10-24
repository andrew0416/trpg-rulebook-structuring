"""Defender acquisition and its actual native Shift Intercept consumer.

The reviewed CSV/native source is other-category execution dependency only;
this suite does not add Category2 completion credit.
"""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules
import test_category2_move_defense_reactions as FIXTURE
ROOT=FIXTURE.ROOT
import intercept_profiles as PROFILES
import items as ITEMS
import passive_events as PASSIVE
import action_resources as RESOURCES
import movement_actions as MOVE
import world_entities as WORLD


class DefenderInterceptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')

    def fixture(self):
        class DefenderFixture(FIXTURE.MoveDefenseReactionsTests):
            def setUp(self):
                super().setUp()
                # Pound is a selected native melee Move without a Pass path requirement.
                self.a.moves[0]='move/막치기';self.a.spec['moves'][0]='move/막치기'

            def waiting(self,move='move/막치기',*,area=False):
                return super().waiting(move,area=area)
        f=DefenderFixture('runTest');f.rules=self.rules;f.setUp()
        return f

    def acquire(self,f,*,actor=None,source=PROFILES.DEFENDER,mode='apply'):
        actor=actor or f.r
        actor.spec['skills']['Athletics']=4
        actor.spec['feats']=[source]
        base=actor.stats['hp']
        if mode=='included':actor.stats['hp']=actor.spec['stats']['hp']=base+1
        actor.spec['feature_stat_imports']={PROFILES.DEFENDER:{'mode':mode,'base_stat':base}}
        ITEMS.register_feats(f.e,actor)
        return actor

    def faces(self,f,values=(6,6,6,6)):
        return f.melee(faces=values)

    def state(self,f):
        return deepcopy((f.r.spec,f.r.stats,f.r.custom_conditions,getattr(f.r,'budget',None),
            getattr(f.r,'_action_history',None),f.e.rng.getstate(),f.e.log_lines,f.e.gm_prompts))

    def attempt(self,f):
        row=next(row for row in f.e._move_completions.values() if row['actor'] is f.a)
        return row['defense'][f.t.entity_id]['attempts'][0]

    def test_exact_source_policy_and_actual_acquisition_effect_skip_legacy_fallback(self):
        for source in (PROFILES.DEFENDER,'디펜더'):
            for mode in ('apply','included'):
                with self.subTest(source=source,mode=mode):
                    f=self.fixture();before_hp=f.r.hp;base=f.r.stats['hp'];prompt_count=len(f.e.gm_prompts)
                    self.acquire(f,source=source,mode=mode)
                    ITEMS.register_feats(f.e,f.r)
                    self.assertEqual((f.r.stats['hp'],f.r.spec['stats']['hp']),(base+1,base+1))
                    self.assertEqual(f.r.hp,before_hp)
                    self.assertEqual(len(f.e.gm_prompts),prompt_count)
                    receipt=f.r.custom_conditions[PROFILES.RECEIPTS][PROFILES.DEFENDER]
                    self.assertEqual(receipt['qualification'],{'skill':'athletics','minimum':4,'rank_at_acquisition':4})
                    self.assertEqual(len([k for k in f.r.custom_conditions[PROFILES.RECEIPTS] if PROFILES.identity(k)]),1)
                    self.assertFalse(any(row.get('name') in PROFILES.ALIASES for row in f.r.registry))
        policy=PROFILES._policy(self.rules)
        self.assertEqual(policy['source_cells'][1:4],['[+HP]','숙련 육상','항상'])
        self.assertEqual(policy['category2_completion_credit'],0)

    def test_acquisition_missing_import_underqualified_or_duplicate_refuses_before_mutation(self):
        for invalid in ('missing_import','underqualified','duplicate'):
            with self.subTest(invalid=invalid):
                f=self.fixture();f.r.spec['skills']['Athletics']=4;f.r.spec['feats']=[PROFILES.DEFENDER]
                f.r.spec['feature_stat_imports']={PROFILES.DEFENDER:{'mode':'apply','base_stat':f.r.stats['hp']}}
                if invalid=='missing_import':f.r.spec.pop('feature_stat_imports')
                elif invalid=='underqualified':f.r.spec['skills']['Athletics']=3
                else:f.r.spec['feats'].append('디펜더')
                before=self.state(f)
                with self.assertRaises(ValueError):ITEMS.register_feats(f.e,f.r)
                self.assertEqual(self.state(f),before)

    def test_native_melee_success_and_failure_pay_shift_only_with_same_base_geometry(self):
        for values,success in (((6,6,6,6),True),((1,1,1,1),False)):
            with self.subTest(success=success):
                f=self.fixture();self.acquire(f);f.watch();event=f.waiting();hp=(f.t.hp,f.r.hp)
                f.choose(event,options=self.faces(f,values))
                self.assertEqual(f.r._action_history,['shift'])
                self.assertEqual(RESOURCES.pending(f.r),{'shift':1})
                self.assertEqual(self.attempt(f)['cost_profile']['action'],'shift')
                self.assertEqual(self.attempt(f)['check_total'],sum(values))
                if success:
                    self.assertEqual((f.t.pos,f.r.pos),((4,2),(3,2)))
                    self.assertEqual(f.t.hp,hp[0]);self.assertLess(f.r.hp,hp[1])
                else:
                    self.assertEqual(f.r.pos,(3,4));self.assertLess(f.t.hp,hp[0]);self.assertEqual(f.r.hp,hp[1])
                self.assertIs(f.e._active_turn_actor,f.a)
                self.assertTrue(f.e.validate_state()['valid'])

    def test_native_ranged_success_and_failure_preserve_target_and_partial_distance(self):
        for success in (True,False):
            with self.subTest(success=success):
                f=self.fixture();self.acquire(f);f.t.pos=(6,2);f.r.pos=(4,5)
                f.watch('maneuver/원거리-가로채기');event=f.waiting('move/물대포');hp=f.t.hp
                values=(6,6,6,6) if success else (1,1,1,1)
                options={'path':[(4,5),(4,4),(4,3),(4,2)],'skill':'육상','mode':'land','roll_options':{'fixed':list(values)}}
                f.choose(event,options=options)
                self.assertEqual(f.r.pos,(4,2) if success else (4,3))
                self.assertEqual(f.t.pos,(6,2));self.assertEqual(RESOURCES.pending(f.r),{'shift':1})
                self.assertEqual(f.r._action_history,['shift'])
                if success:self.assertEqual(f.t.hp,hp)
                else:self.assertLess(f.t.hp,hp)

    def test_another_ally_defender_never_changes_unowned_reactors_full_cost(self):
        f=self.fixture();self.acquire(f,actor=f.t);f.watch();event=f.waiting()
        f.choose(event,options=f.melee())
        self.assertEqual(f.r._action_history,['full'])
        self.assertEqual(RESOURCES.pending(f.r),{'standard':1,'shift':1})
        self.assertEqual(self.attempt(f)['cost_profile']['modifier_sources'],[])

    def test_decline_and_invalid_path_leave_defender_shift_debt_and_rng_unchanged(self):
        f=self.fixture();self.acquire(f);f.watch();event=f.waiting();before=f.e.export_state()
        invalid=self.faces(f);invalid['path']=[(3,5),(3,2)]
        with self.assertRaises(ValueError):f.choose(event,options=invalid)
        self.assertEqual(f.e.export_state(),before)
        rng=f.e.rng.getstate();f.choose(event,use=False)
        self.assertEqual(RESOURCES.pending(f.r),{})
        self.assertEqual(f.e.rng.getstate(),rng)
        self.assertEqual(f.r.pos,(3,5))

    def test_real_pending_cold_restore_uses_one_shift_and_no_second_accuracy_or_skill_check(self):
        f=self.fixture();self.acquire(f);f.watch();event=f.waiting();rng=f.e.rng.getstate()
        f.fresh();f.choose(event,options=self.faces(f))
        self.assertEqual(f.r._action_history,['shift']);self.assertEqual(RESOURCES.pending(f.r),{'shift':1})
        self.assertEqual(f.e.rng.getstate(),rng)
        self.assertEqual(f.a.move_uses['move/막치기'],1)
        before=f.e.export_state()
        with self.assertRaises(ValueError):f.choose(event,options=self.faces(f))
        self.assertEqual(f.e.export_state(),before)
        f.fresh()

    def test_actual_pass_producer_holds_unsupported_reactive_scope_atomically(self):
        # Retain the historical ID: direct use still cannot invent Pass authority,
        # while the actual Pass producer now owns the paid reactive continuation.
        import pass_moves as PASS, move_completion as COMPLETE
        f=self.fixture();self.acquire(f);f.watch()
        f.a.moves[0]=f.a.spec['moves'][0]='move/풀베기'
        before=f.e.export_state()
        with self.assertRaisesRegex(ValueError,'Pass Move requires use_pass_move'):
            f.e.use_move(f.a,f.t,'move/풀베기')
        self.assertEqual(f.e.export_state(),before)
        hp=(f.t.hp,f.r.hp)
        with patch.object(type(f.e),'d20',return_value=20):
            with self.assertRaises(PASSIVE.PassiveEventPending):
                f.e.use_pass_move(f.a,'move/풀베기',(4,2),event_id='defender-pass/pending',
                    object_adjudications={},source='gm/observed-object-hits',
                    reason='actual complete Pass path crosses the watched ally')
            self.assertEqual((f.t.hp,f.r.hp),hp)
            self.assertEqual(f.a.move_uses['move/풀베기'],1)
            self.assertEqual((f.a.budget['standard'],f.a.budget['shift']),(0,0))
            f.choose(f.e._passive_pending,options=self.faces(f))
        row=getattr(f.e,PASS.KEY)['defender-pass/pending']
        self.assertEqual(row['phase'],'complete')
        self.assertEqual(COMPLETE.actual_recipients(f.e._move_completions[row['completion_id']]),[f.r])
        self.assertEqual(f.t.hp,hp[0]);self.assertLess(f.r.hp,hp[1])
        self.assertEqual(f.a.move_uses['move/풀베기'],1)
        self.assertEqual(f.a._action_history,['standard','shift'])
        self.assertEqual(RESOURCES.pending(f.r),{'shift':1})
        self.assertIsNone(getattr(f.e,'_passive_pending',None))
        self.assertFalse(getattr(f.e,'_pass_move_scope',None))
        self.assertTrue(f.e.validate_state()['valid'])

    def test_later_athletics_rank_reduction_preserves_qualified_acquisition_cost(self):
        f=self.fixture();self.acquire(f);f.r.spec['skills']['Athletics']=3
        f.watch();event=f.waiting();f.choose(event,options=f.melee())
        self.assertEqual(f.r._action_history,['shift'])
        proof=self.attempt(f)['cost_profile']['modifier_sources'][0]
        self.assertEqual(proof['acquisition']['qualification']['rank_at_acquisition'],4)
        self.assertEqual(self.attempt(f)['check_total'],18)

    def test_later_native_hp_growth_keeps_receipt_and_shift_cost_without_second_import(self):
        f=self.fixture();self.acquire(f)
        receipt=deepcopy(f.r.custom_conditions[PROFILES.RECEIPTS][PROFILES.DEFENDER])
        before=f.r.stats['hp'];current_hp=f.r.hp
        f.e.gm.set_stat(f.r,'hp',delta=3,reason='permanent HP growth after Defender acquisition')
        ITEMS.register_feats(f.e,f.r)
        self.assertEqual((f.r.stats['hp'],f.r.spec['stats']['hp']),(before+3,before+3))
        self.assertEqual(f.r.hp,current_hp)
        self.assertEqual(f.r.custom_conditions[PROFILES.RECEIPTS][PROFILES.DEFENDER],receipt)
        f.watch();event=f.waiting();f.choose(event,options=self.faces(f))
        self.assertEqual(f.r._action_history,['shift'])
        self.assertEqual(RESOURCES.pending(f.r),{'shift':1})
        self.assertEqual(self.attempt(f)['cost_profile']['modifier_sources'][0]['acquisition'],receipt)
        self.assertTrue(f.e.validate_state()['valid'])
        f.fresh()

    def test_source_selection_change_refuses_before_reaction_payment(self):
        f=self.fixture();self.acquire(f);f.watch();event=f.waiting();before=f.e.export_state()
        selected=self.rules._selected_rule
        with patch.object(self.rules,'_selected_rule',side_effect=lambda uid,*a,**kw:uid+'/unreviewed' if uid==PROFILES.DEFENDER else selected(uid,*a,**kw)):
            with self.assertRaises(ValueError):f.choose(event,options=self.faces(f))
        self.assertEqual(f.e.export_state(),before)

    def test_historical_profile_requires_actual_persisted_receipt_and_owner(self):
        f=self.fixture();self.acquire(f);value=PROFILES.profile(f.e,f.r,{},'maneuver/근접-가로채기')
        for wrong in ('owner','receipt','absent_issued_receipt'):
            with self.subTest(wrong=wrong):
                altered=deepcopy(value);saved=deepcopy(f.r.custom_conditions)
                if wrong=='owner':altered['modifier_sources'][0]['actor_id']=f.t.entity_id
                elif wrong=='receipt':
                    receipt=altered['modifier_sources'][0]['acquisition'];receipt['before']+=1;receipt['after']+=1
                else:f.r.custom_conditions[PROFILES.RECEIPTS].pop(PROFILES.DEFENDER)
                with self.assertRaises(ValueError):PROFILES.validate_profile(f.e,f.r,altered,historical=True)
                f.r.custom_conditions=saved

    def test_exact_static_cache_matches_cold_fingerprint_but_live_override_remains_bound(self):
        import state_codec as CODEC
        import static_trainer_modifiers as STATIC
        rules=Rules(ROOT,ruleset='core')
        cold=CODEC.rules_fingerprint(rules)
        STATIC._policy(rules)
        self.assertEqual(CODEC.rules_fingerprint(rules),cold)
        rules._static_trainer_modifier_policy=deepcopy(rules._static_trainer_modifier_policy)
        rules._static_trainer_modifier_policy['schema_version']=99
        self.assertNotEqual(CODEC.rules_fingerprint(rules),cold)

    def test_withdrawal_during_paid_native_movement_wait_retains_past_shift_then_defaults_full(self):
        f=self.fixture();self.acquire(f);f.watch();event=f.waiting();original=MOVE.departure
        def block(engine,actor,cell,height,**scopes):
            result=original(engine,actor,cell,height,**scopes)
            if actor.entity_id==f.r.entity_id and cell==(3,3):engine.grid.blocking.add(cell)
            return result
        with patch.object(MOVE,'departure',side_effect=block):
            with self.assertRaises(PASSIVE.PassiveEventPending):f.choose(event,options=self.faces(f))
        self.assertEqual(f.r.pos,(3,4));self.assertEqual(f.r._action_history,['shift'])
        self.assertEqual(RESOURCES.pending(f.r),{'shift':1})
        f.r.spec['feats']=[]
        self.assertEqual(PROFILES.profile(f.e,f.r,{},'maneuver/근접-가로채기'),
            {'action':'full','payment':'next','budget':{'standard':1,'shift':1},'modifier_sources':[]})
        rng=f.e.rng.getstate();f.fresh();f.e.grid.blocking.remove((3,3))
        with patch.object(f.e,'skill_check',side_effect=AssertionError('paid check must not repeat')):
            f.e.deliver_passive_event(event)
        self.assertEqual(f.r.pos,(3,2));self.assertEqual(f.r._action_history,['shift'])
        self.assertEqual(RESOURCES.pending(f.r),{'shift':1});self.assertEqual(f.e.rng.getstate(),rng)
        self.assertTrue(f.e.validate_state()['valid'])
        f.fresh()


if __name__=='__main__':unittest.main()

