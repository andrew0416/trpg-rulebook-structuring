"""Source-audit candidate probes. Run only in Root's complete validation tree.

C01 Disruption is a diagnostic of retained authority, not an asserted universal
trigger-expiry rule. Devious has an explicit immediate source requirement.
C02/C03 are acceptance regressions; failure at the final consumer is evidence.
"""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Engine
import ability_transitions as ABILITIES
import combat_timing as TIME
import move_completion as COMPLETE
import passive_events as PASSIVE
import stellar_tera_blast as STELLAR
import test_book_type_ace_reactions as ACE_FIX
import test_book_type_ace_acquisition as ACQUIRE_FIX
import test_category2_csv_stellar_tera_blast as STELLAR_FIX
import type_ace as TA
import world_entities as WORLD


class TypeAceCandidateTests(unittest.TestCase):
    setUpClass = classmethod(ACQUIRE_FIX.TypeAceAcquisitionTests.setUpClass.__func__)
    setUp = ACQUIRE_FIX.TypeAceAcquisitionTests.setUp
    setup = ACQUIRE_FIX.TypeAceAcquisitionTests.setup
    add = ACQUIRE_FIX.TypeAceAcquisitionTests.add
    acquire = ACQUIRE_FIX.TypeAceAcquisitionTests.acquire
    combat = ACQUIRE_FIX.TypeAceAcquisitionTests.combat
    restore = ACQUIRE_FIX.TypeAceAcquisitionTests.restore
    valid = ACQUIRE_FIX.TypeAceAcquisitionTests.valid
    family = ACE_FIX.TypeAceReactionTests.family
    known = ACE_FIX.TypeAceReactionTests.known
    native = ACE_FIX.TypeAceReactionTests.native
    completed = ACE_FIX.TypeAceReactionTests.completed
    react = ACE_FIX.TypeAceReactionTests.react

    def later_actor_attack(self):
        self.e.end_of_turn(self.p)
        self.e.start_of_turn(self.b, initiative_count=20)
        self.native(self.b, self.q, 'move/물대포')
        self.assertIs(self.e._active_turn_actor, self.b)
        self.assertIs(self.e.rulings, self.e.r.rulings)

    def test_c01_diagnostic_disruption_accepts_old_completion_after_another_actor_attacks(self):
        self.family('벌레', 'Insectoid Utility', 'Disruption Order')
        self.known(self.b, 'move/물대포')
        self.combat(self.p)
        self.native(self.p, self.b, 'move/시그널빔')
        original = self.completed()['id']
        self.later_actor_attack()
        self.assertTrue(TA.react(self.e, self.t, self.p, TA.uid('Disruption Order'), original))
        rows = [r for r in TIME.records(self.b) if r.get('ace_disruption')]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['accuracy_modifier'], -3)  # adopted S-003 half-rank
        self.assertEqual(rows[0]['turn_deadline'], self.p.custom_conditions['combat_turn_serial'] + 1)
        self.valid()

    def devious_hit(self):
        self.family('악', 'Clever Ruse', 'Devious')
        self.known(self.p, 'move/울음소리', 'move/거짓울음')
        self.known(self.b, 'move/물대포')
        self.combat(self.p)
        self.native(self.p, self.b, 'move/울음소리')
        return self.completed()['id']

    def test_c01_devious_immediate_control_commits_one_additional_native_move(self):
        original = self.devious_hit()
        before = self.p.move_uses.get('move/거짓울음', 0)
        with patch.object(Engine, 'd20', return_value=10):
            TA.react(self.e, self.t, self.p, TA.uid('Devious'), original,
                     target=self.b, move='move/거짓울음')
        self.assertEqual(self.p.move_uses['move/거짓울음'], before + 1)
        self.assertEqual(self.completed()['move_id'], 'move/거짓울음')
        self.valid()

    def test_c01_devious_cannot_reuse_immediate_trigger_after_another_actor_attacks(self):
        original = self.devious_hit()
        self.later_actor_attack()
        before = self.e.export_state()
        try:
            with patch.object(Engine, 'd20', return_value=10):
                TA.react(self.e, self.t, self.p, TA.uid('Devious'), original,
                         target=self.b, move='move/거짓울음')
        except ValueError:
            self.assertEqual(self.e.export_state(), before)
            return
        self.assertEqual(self.e.export_state(), before,
                         'Devious consumed a closed immediate trigger after a later native attack')

    def test_c01_devious_immediate_credit_ends_after_own_swift_action(self):
        import turn as TURN
        original = self.devious_hit()
        self.assertTrue(TURN.spend(self.e, self.p, 'swift', 'actual intervening Swift action'))
        before = self.e.export_state()
        with self.assertRaisesRegex(ValueError, 'immediate native Move completion'):
            TA.react(self.e, self.t, self.p, TA.uid('Devious'), original,
                     target=self.b, move='move/거짓울음')
        self.assertEqual(self.e.export_state(), before)

    def test_c01_devious_immediate_completion_survives_cold_restore_once(self):
        original = self.devious_hit()
        self.restore()
        self.assertIs(self.e.rulings, self.e.r.rulings)
        with patch.object(Engine, 'd20', return_value=10):
            TA.react(self.e, self.t, self.p, TA.uid('Devious'), original,
                     target=self.b, move='move/거짓울음')
        self.assertEqual(self.p.move_uses['move/거짓울음'], 1)
        before = self.e.export_state()
        with self.assertRaises(ValueError):
            TA.react(self.e, self.t, self.p, TA.uid('Devious'), original,
                     target=self.b, move='move/거짓울음')
        self.assertEqual(self.e.export_state(), before)
        self.valid()

    def test_c02_aqua_vortex_direct_target_control(self):
        self.family('물', 'Flood!', 'Aqua Vortex')
        self.combat(self.p)
        self.native(self.p, self.b, 'move/물대포')
        self.react('Aqua Vortex')
        self.assertIn('조이기', self.b.conditions)
        self.assertEqual([r['ace_damage'] for r in TIME.records(self.b) if r.get('ace_vortex')], [-6])
        self.valid()

    def test_c02_aqua_vortex_follows_actual_ranged_interceptor_after_pending_restore(self):
        self.family('물', 'Flood!', 'Aqua Vortex')
        self.e.gm.set_position(self.b, (6, 2), reason='actual ranged Water target')
        self.u = self.add('actual ranged interceptor', 'trainer', (4, 4),
                          side='foe', classes=[], feats=[])
        self.known(self.p, 'move/물대포')
        self.combat(self.p)
        self.e.watch_move_defense(self.b, [{'actor_id':self.u.entity_id,
            'source':'maneuver/원거리-가로채기'}], reason='actual native interception choice')
        hp = self.b.hp, self.u.hp
        with patch.object(Engine, 'd20', return_value=10):
            with self.assertRaises(PASSIVE.PassiveEventPending):
                self.e.use_move(self.p, self.b, 'move/물대포', set_damage=True)
        event = self.e._passive_pending
        self.assertEqual((self.b.hp, self.u.hp), hp)
        self.restore()
        self.assertIs(self.e.rulings, self.e.r.rulings)
        self.e.choose_move_defense(event, self.u, use=True, options={
            'path':[(4, 4), (4, 3), (4, 2)], 'skill':'육상', 'mode':'land',
            'roll_options':{'fixed':[6] * 6}}, reason='actual successful ranged interception')
        row = self.completed()
        self.assertEqual(row['targets'], [self.b])
        self.assertIsNone(COMPLETE.recipient_result(row, self.b))
        self.assertEqual(COMPLETE.actual_recipients(row), [self.u])
        self.assertTrue(COMPLETE.recipient_result(row, self.u)['hit'])
        self.assertEqual(self.p.move_uses['move/물대포'], 1)
        self.assertEqual(self.b.hp, hp[0])
        self.assertLess(self.u.hp, hp[1])
        self.react('Aqua Vortex', row)
        self.assertNotIn('조이기', self.b.conditions,
                         'The original target was replaced by the actual interceptor')
        self.assertIn('조이기', self.u.conditions)
        self.assertFalse(any(r.get('ace_vortex') for r in TIME.records(self.b)))
        self.assertEqual([r['ace_damage'] for r in TIME.records(self.u) if r.get('ace_vortex')], [-6])
        self.valid()


class StellarLifetimeCandidateTests(unittest.TestCase):
    setUpClass = classmethod(STELLAR_FIX.StellarTeraBlastTests.setUpClass.__func__)
    setUp = STELLAR_FIX.StellarTeraBlastTests.setUp

    def radiate_native(self):
        # Keep the real random.Random for graph persistence; only fix the native
        # d20 boundary. Do not reuse the legacy fixture's custom FixedRng.
        self.assertIs(self.engine.rulings, self.engine.r.rulings)
        with patch.object(Engine, 'd20', return_value=10):
            self.engine.use_move(self.owner, self.foe, 'move/몸통박치기', set_damage=True)
        opportunity = self.owner.spec[STELLAR.STATE]['opportunities'][-1]
        self.engine.gm.activate_stellar_blast(self.owner, opportunity['id'], '불꽃',
            reason='actual completed enemy-hit radiation')
        self.assertEqual(STELLAR.damage_roll_bonus(self.engine, self.ally, '불꽃')[0], 10)

    def test_c03_selected_native_suppression_or_replacement_preserves_usable_saved_world(self):
        for move in ('move/위액', 'move/고민씨'):
            with self.subTest(move=move):
                self.setUp()
                self.engine.gm.set_move(self.foe, move, reason='actual learned source-changing Move')
                self.radiate_native()
                self.engine.end_of_turn(self.owner)
                self.engine.start_of_turn(self.foe, initiative_count=19)
                self.engine.gm.choose_ability_transition(self.foe, self.owner, move,
                    ability='ability/스텔라버스트', reason='actual selected Stellar source')
                with patch.object(Engine, 'd20', return_value=20):
                    self.engine.use_move(self.foe, self.owner, move)
                self.assertFalse(self.owner.abilities_suppressed)
                self.assertFalse(ABILITIES.active(self.owner, 'ability/스텔라버스트'))
                self.assertTrue(self.owner.spec[STELLAR.STATE]['history'])
                ids = {name:getattr(self, name).entity_id for name in ('owner', 'ally', 'far', 'foe')}
                saved = json.loads(json.dumps(self.engine.export_state(), ensure_ascii=False))
                self.engine = Engine.import_state(self.rules, saved)
                index = WORLD.actor_index(self.engine)
                for name, identity in ids.items():setattr(self, name, index[identity])
                self.assertIs(self.engine.rulings, self.engine.r.rulings)
                self.engine.end_of_turn(self.foe)
                self.engine.start_of_turn(self.ally, initiative_count=18)
                # C03 suspects an unrelated real attack errors while traversing
                # the former source owner's retained radiation history.
                with patch.object(Engine, 'd20', return_value=10):
                    self.engine.use_move(self.ally, self.foe, 'move/불꽃세례', set_damage=True)
                self.assertEqual(STELLAR.damage_roll_bonus(self.engine, self.ally, '불꽃')[0], 0)
                self.assertIsNone(STELLAR.active_radiation(self.engine, self.owner))
                self.engine.end_of_turn(self.ally)
                self.engine.end_encounter(self.engine.everyone)
                self.assertTrue(ABILITIES.active(self.owner, 'ability/스텔라버스트'))
                self.assertTrue(self.engine.validate_state()['valid'])

    def test_c03_suppressed_owner_cannot_spend_an_unconsumed_native_opportunity(self):
        with patch.object(Engine, 'd20', return_value=10):
            self.engine.use_move(self.owner, self.foe, 'move/몸통박치기', set_damage=True)
        opportunity = self.owner.spec[STELLAR.STATE]['opportunities'][-1]
        self.owner.abilities_suppressed = True
        before = self.engine.export_state()
        with self.assertRaisesRegex(ValueError, 'actual active ability'):
            self.engine.gm.activate_stellar_blast(self.owner, opportunity['id'], '불꽃',
                                                reason='suppressed source cannot authorize a new activation')
        self.assertEqual(self.engine.export_state(), before)
        self.owner.abilities_suppressed = False
        self.engine.gm.activate_stellar_blast(self.owner, opportunity['id'], '불꽃',
                                            reason='restored active source uses original current hit')
        self.assertEqual(self.owner.budget['swift'], 0)
        self.assertEqual(len(self.owner.spec[STELLAR.STATE]['history']), 1)

    def test_c03_new_encounter_requires_new_hit_and_preserves_past_radiation_history(self):
        self.radiate_native()
        past = deepcopy(self.owner.spec[STELLAR.STATE]['history'])
        old_epoch = self.owner.spec[STELLAR.STATE]['encounter_epoch']
        self.engine.end_of_turn(self.owner)
        self.engine.end_encounter(self.engine.everyone)
        self.engine.start_round(self.engine.everyone)
        self.engine.start_of_turn(self.owner, initiative_count=20)
        self.assertIsNone(STELLAR.active_radiation(self.engine, self.owner))
        self.assertEqual(STELLAR.damage_roll_bonus(self.engine, self.ally, '불꽃')[0], 0)
        self.radiate_native()
        state = self.owner.spec[STELLAR.STATE]
        self.assertGreater(state['encounter_epoch'], old_epoch)
        self.assertEqual(state['history'][:len(past)], past)
        self.assertEqual(len(state['history']), len(past) + 1)
        saved = json.loads(json.dumps(self.engine.export_state(), ensure_ascii=False))
        loaded = Engine.import_state(self.rules, saved)
        owner = WORLD.actor_index(loaded)[self.owner.entity_id]
        self.assertEqual(STELLAR.active_radiation(loaded, owner)['radiated_type'], '불꽃')

    def test_c03_retained_history_still_requires_its_actual_native_hit(self):
        self.radiate_native()
        state = self.owner.spec[STELLAR.STATE]
        original = state['opportunities'][0]['completion_id']
        state['opportunities'][0]['completion_id'] = 'move-complete:never-issued'
        with self.assertRaisesRegex(ValueError, 'actual native hit completion'):
            STELLAR.validate_actor(self.engine, self.owner)
        state['opportunities'][0]['completion_id'] = original
        self.assertTrue(STELLAR.validate_actor(self.engine, self.owner))

    def test_c03_global_suppression_control_keeps_history_without_damage_query_error(self):
        self.radiate_native()
        history = deepcopy(self.owner.spec[STELLAR.STATE]['history'])
        self.owner.abilities_suppressed = True  # existing global-suppression control
        self.assertIsNone(STELLAR.active_radiation(self.engine, self.owner))
        self.assertEqual(STELLAR.damage_roll_bonus(self.engine, self.ally, '불꽃')[0], 0)
        self.assertEqual(self.owner.spec[STELLAR.STATE]['history'], history)
        self.owner.abilities_suppressed = False
        self.assertEqual(STELLAR.damage_roll_bonus(self.engine, self.ally, '불꽃')[0], 10)


if __name__ == '__main__':
    unittest.main()