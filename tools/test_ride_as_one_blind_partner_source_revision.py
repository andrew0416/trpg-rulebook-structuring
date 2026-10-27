"""Actual mounted Speed Evasion sharing reads the partner's current sight."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules
from grid import Grid
import test_book_ride_as_one as _ride_fixture
import control_mount as MOUNT
import state_grants as GRANTS
import state_codec as CODEC
import survivalist_features as SURVIVAL
import vision_impairment as VISION
import world_entities as WORLD


class RideAsOneBlindPartnerSourceRevisionTests(unittest.TestCase):
    setUpClass = classmethod(_ride_fixture.RideAsOneTests.setUpClass.__func__)
    setup = _ride_fixture.RideAsOneTests.setup
    acquire = _ride_fixture.RideAsOneTests.acquire
    board = _ride_fixture.RideAsOneTests.board
    snap = _ride_fixture.RideAsOneTests.snap

    def scene(self, *, fast='mount'):
        self.setup(mounted=True)
        self.e.grid = Grid(8, 8)
        from native_scenario_fixture import prepare_body
        for actor in (self.a,self.p,self.enemy):
            prepare_body(self.e,actor,size=actor.spec.get('size','중형'),offsets=[(0,0)],
                reason='observed complete one-cell mounted scenario bodies')
        if fast == 'rider':
            self.e.gm.set_stat(self.a, 'spe', 25, reason='actual faster mounted trainer')
            self.e.gm.set_stat(self.p, 'spe', 10, reason='actual slower Pokemon mount')
        self.assertIs(WORLD.mount_relation(WORLD.actor_index(self.e), self.a), self.p)
        self.assertEqual(self.pair(), (5, 5))
        return (self.p, self.a) if fast == 'mount' else (self.a, self.p)

    def pair(self):
        return tuple(actor.evasion('변화', engine=self.e) for actor in (self.a, self.p))

    def observe(self, actor, light):
        return SURVIVAL.observe_environment(self.e, actor, terrains=['urban'], light=light,
            reason='GM observes the actual illumination around this mounted participant')

    def test_actual_fast_partner_blindness_and_cure_change_shared_evasion_and_native_accuracy(self):
        for fast in ('mount', 'rider'):
            for condition in ('실명', '완전 실명'):
                with self.subTest(fast=fast, condition=condition):
                    partner, recipient = self.scene(fast=fast)
                    sources = deepcopy((self.a.stats, self.p.stats, self.a.spec[MOUNT.CONTRACT]))
                    move = self.rules.move('move/몸통박치기')
                    self.assertFalse(self.e.accuracy_check(self.enemy, recipient, move, fixed_roll=4)[0])
                    self.assertTrue(self.e.apply_status(partner, condition, parameters={'cause': 'external'}))
                    self.assertEqual(recipient.evasion('변화', engine=self.e), 2)
                    self.assertEqual(partner.evasion('변화', engine=self.e), 0)
                    self.assertNotIn('취약', partner.conditions)
                    self.assertTrue(self.e.accuracy_check(self.enemy, recipient, move, fixed_roll=4)[0])
                    self.e.cure_status(partner, condition)
                    self.assertEqual(self.pair(), (5, 5))
                    self.assertFalse(self.e.accuracy_check(self.enemy, recipient, move, fixed_roll=4)[0])
                    self.assertEqual((self.a.stats, self.p.stats, self.a.spec[MOUNT.CONTRACT]), sources)

    def test_coarse_darkness_native_senses_and_mapped_light_keep_distinct_partner_contributions(self):
        partner, recipient = self.scene()
        conditions = set(partner.conditions)
        for light, expected in (('low_light', 'ordinary'), ('complete_darkness', 'total')):
            self.observe(partner, light)
            self.assertEqual(VISION.accuracy_level(self.e, partner), expected)
            self.assertEqual(recipient.evasion('변화', engine=self.e), 2)
            self.assertEqual(partner.conditions, conditions)
        for capability in ('Darkvision', 'Blindsense'):
            source = 'observed/native-sense/' + capability
            GRANTS.grant(partner, 'capabilities', capability, source, 'actual independent sensory capability')
            self.assertEqual(VISION.accuracy_level(self.e, partner), 'none')
            self.assertEqual(self.pair(), (5, 5))
            applied = self.e.apply_status(partner, '완전 실명', parameters={'cause': 'external'})
            self.assertEqual(applied, capability == 'Darkvision')
            self.assertEqual(recipient.evasion('변화', engine=self.e), 2 if applied else 5)
            if applied:
                self.e.cure_status(partner, '완전 실명')
            GRANTS.revoke(partner, source, engine=self.e)
            self.assertEqual(recipient.evasion('변화', engine=self.e), 2)
        self.observe(partner, 'normal')
        self.assertEqual(self.pair(), (5, 5))
        self.e.configure_scene_lighting(darkness=True, reason='actual mapped unlit distance only')
        self.assertLess(self.e.scene_light_projection(partner, self.enemy)['penalty'], 0)
        self.assertEqual(VISION.accuracy_level(self.e, partner), 'none')
        self.assertEqual(self.pair(), (5, 5))
        self.assertEqual(partner.conditions, conditions)

    def test_selected_vulnerable_implication_and_own_zero_still_govern_before_sharing(self):
        partner, recipient = self.scene()
        self.e.apply_status(partner, '완전 실명', parameters={'cause': 'external'})
        self.assertEqual(recipient.evasion('변화', engine=self.e), 2)
        selected_effects = self.rules.condition_effects
        def selected_without_blind_implication(name):
            effects = deepcopy(selected_effects(name))
            if name == '취약':
                for effect in effects:
                    if effect.get('type') == 'implied_by':
                        effect['conditions'] = [c for c in effect.get('conditions', ()) if c != VISION.BLIND]
            return effects
        # Consumer sensitivity only: this controlled selected-effect seam is not a claimed printed edition.
        with patch.object(self.rules, 'condition_effects', side_effect=selected_without_blind_implication):
            self.assertEqual(VISION.accuracy_level(self.e, partner), 'total')
            self.assertEqual(recipient.evasion('변화', engine=self.e), 5)
        self.assertEqual(recipient.evasion('변화', engine=self.e), 2)
        self.e.apply_status(recipient, '완전 실명', parameters={'cause': 'external'})
        self.assertEqual(recipient.evasion('변화', engine=self.e, conditional_bonus=4), 0)
        self.e.apply_status(recipient, '취약')
        self.e.cure_status(recipient, '완전 실명')
        self.assertEqual(recipient.evasion('변화', engine=self.e), 0)
        self.e.cure_status(recipient, '취약')
        self.assertEqual(recipient.evasion('변화', engine=self.e), 2)
        self.e.cure_status(partner, '완전 실명')
        self.assertEqual(self.pair(), (5, 5))

    def test_actual_gm_and_fresh_rules_json_restore_preserve_pair_sight_and_independent_sources(self):
        for restoration in ('gm', 'json'):
            with self.subTest(restoration=restoration):
                partner, _ = self.scene()
                source = 'observed/independent-Darkvision'
                GRANTS.grant(partner, 'capabilities', 'Darkvision', source, 'actual separate sense source')
                self.observe(partner, 'complete_darkness')
                self.e.apply_status(partner, '완전 실명', parameters={'cause': 'external'})
                self.assertEqual(self.pair(), (2, 0))
                ids = [actor.entity_id for actor in (self.a, self.p, self.enemy)]
                saved = deepcopy((self.a.stats, self.p.stats, self.a.spec[MOUNT.CONTRACT],
                                  GRANTS.effective_capabilities(self.p)))
                if restoration == 'gm':
                    self.e.gm.snapshot('actual mounted partner blindness')
                    self.e.cure_status(self.p, '완전 실명')
                    self.assertEqual(self.pair(), (5, 5))
                    self.e.gm.restore('actual mounted partner blindness')
                else:
                    fresh = Rules(ROOT, ruleset='all')
                    fresh.load_source_policy_package((ROOT / 'data/examples/scripting-repulse.json').read_text(encoding='utf-8'))
                    self.e = CODEC.load_engine(fresh, json.loads(json.dumps(self.snap(), ensure_ascii=False)))
                index = WORLD.actor_index(self.e)
                self.a, self.p, self.enemy = [index[identity] for identity in ids]
                self.assertIs(WORLD.mount_relation(index, self.a), self.p)
                self.assertEqual(self.pair(), (2, 0))
                self.assertNotIn('취약', self.p.conditions)
                self.assertEqual((self.a.stats, self.p.stats, self.a.spec[MOUNT.CONTRACT],
                                  GRANTS.effective_capabilities(self.p)), saved)
                self.e.cure_status(self.p, '완전 실명')
                self.assertEqual(self.pair(), (5, 5))
                GRANTS.revoke(self.p, source, engine=self.e)
                self.assertEqual(self.pair(), (2, 0))
                self.observe(self.p, 'normal')
                self.assertEqual(self.pair(), (5, 5))


if __name__ == '__main__':
    unittest.main()
