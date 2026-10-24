"""Learned Static Bind qualifies actual native grapple consumers, without casting."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import unittest

from engine import Rules, Engine, Combatant
from builder import build_pokemon, build_trainer
from grid import Grid
import grapple_state as GRAPPLE
import state_grants as GRANTS

ROOT = Path(__file__).resolve().parents[1]
BIND = 'move/조이기'


class StaticBindPassiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset='core')

    def world(self, kind='trainer'):
        e = Engine(self.r, seed=200)
        e.grid = Grid(8, 8)
        skills = {'전투': 4, '육상': 4, '곡예': 4}
        extra = {'skills': skills, 'weight_kg': 30, 'movement': {'land': 6, 'power': 4},
                 'movement_basis': 'base', 'power_basis': 'base'}
        if kind == 'pokemon':
            spec = build_pokemon(self.r, '이상해씨', 20, name='actual Static learner',
                moves=[], abilities=[], pos=(2, 2), side='party', extra=deepcopy(extra))
        else:
            spec = build_trainer(self.r, 'actual Static learner', 20,
                dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 10),
                moves=[], skills=skills, pos=(2, 2), side='party', extra=deepcopy(extra))
        a = Combatant(self.r, spec)
        b = Combatant(self.r, build_trainer(self.r, 'actual grapple partner', 20,
            dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 10),
            moves=[], skills=skills, pos=(3, 2), side='opponent', extra=deepcopy(extra)))
        e.gm.add_combatant(a)
        e.gm.add_combatant(b)
        e.start_round(e.everyone)
        e.start_of_turn(a, initiative_count=20)
        return e, a, b

    def learn(self, actor, source='actual-owned-bind', *, mode='learned'):
        GRANTS.grant_moves(actor, [BIND], source, 'feature', owner_id=actor.entity_id,
            lifetime='while_owned', rule_id=BIND, mode=mode)

    def enter(self, e, a, b, *, accuracy=20, faces_a=None, faces_b=None, mods_a=0, mods_b=0):
        return e.grapple(a, b, challenger_skill='전투', defender_skill='육상',
            fixed_accuracy=accuracy,
            challenger_options={'fixed': faces_a or [4] * 4, 'mods': mods_a},
            defender_options={'fixed': faces_b or [2] * 4, 'mods': mods_b})

    def contest(self, e, challenger, defender, faces_a, faces_b, *, mods_a=0, mods_b=0):
        return e.grapple_action(challenger, 'contest', challenger_skill='육상',
            defender_skill='전투', challenger_options={'fixed': faces_a, 'mods': mods_a},
            defender_options={'fixed': faces_b, 'mods': mods_b},
            winner_choices={challenger.entity_id: 'keep', defender.entity_id: 'keep'})

    def next_round_a(self, e, a):
        active = getattr(e, '_active_turn_actor', None)
        if active is not None:
            e.end_of_turn(active)
        e.end_round()
        e.start_round(e.everyone)
        e.start_of_turn(a, initiative_count=20)

    def test_actual_learning_changes_native_entry_accuracy_for_both_holder_kinds(self):
        for kind in ('trainer', 'pokemon'):
            for learned in (False, True):
                with self.subTest(kind=kind, learned=learned):
                    e, a, b = self.world(kind)
                    if learned:
                        self.learn(a)
                    frequency = deepcopy(a.spec.get('frequency_state', {}))
                    uses, rng, hp = dict(a.move_uses), e.rng.getstate(), (a.hp, b.hp)
                    row = self.enter(e, a, b, accuracy=4 + b.evasion('변화') - 1)
                    self.assertEqual(bool(row), learned)
                    self.assertEqual(GRAPPLE.relation(e, a) is not None, learned)
                    if learned:
                        self.assertEqual(row['dominant'], a.entity_id)
                        self.assertEqual(GRAPPLE.relation(e, b)['id'], row['id'])
                    self.assertEqual(a.budget['standard'], 0)
                    self.assertEqual(a.spec.get('frequency_state', {}), frequency)
                    self.assertEqual(a.move_uses, uses)
                    self.assertEqual(e.rng.getstate(), rng)
                    self.assertEqual((a.hp, b.hp), hp)

    def test_entry_gain_dominance_bonus_is_exact_and_keeps_manual_modifiers(self):
        cases = (
            (False, [3, 3, 3, 2], 0, False),
            (True, [3, 3, 3, 2], 0, True),
            (True, [3, 3, 2, 2], 0, False),
            (True, [3, 3, 2, 2], 1, True),
        )
        for learned, faces, manual, expected in cases:
            with self.subTest(learned=learned, faces=faces, manual=manual):
                e, a, b = self.world()
                if learned:
                    self.learn(a)
                row = self.enter(e, a, b, faces_a=faces, faces_b=[3] * 4, mods_a=manual)
                self.assertEqual(bool(row), expected)
                self.assertEqual(GRAPPLE.relation(e, a) is not None, expected)
        e, a, b = self.world()
        self.learn(b)
        row = self.enter(e, a, b, faces_a=[4, 3, 3, 3], faces_b=[3] * 4)
        self.assertEqual(row['dominant'], a.entity_id, 'initial resistance does not gain dominance')

    def test_contest_uses_each_current_learner_and_composes_with_one_check_secure(self):
        for holder in ('challenger', 'defender'):
            with self.subTest(holder=holder):
                e, a, b = self.world('pokemon')
                self.enter(e, a, b)
                self.learn(b if holder == 'challenger' else a)
                e.end_of_turn(a)
                e.start_of_turn(b, initiative_count=10)
                faces = ([3, 3, 3, 2], [3] * 4) if holder == 'challenger' else ([4, 3, 3, 3], [3] * 4)
                result = self.contest(e, b, a, *faces)
                winner = b if holder == 'challenger' else a
                self.assertEqual(result['winner_id'], winner.entity_id)
                self.assertEqual(GRAPPLE.relation(e, a)['dominant'], winner.entity_id)
        e, a, b = self.world()
        self.enter(e, a, b)
        self.learn(a)
        self.next_round_a(e, a)
        e.grapple_action(a, 'secure')
        e.end_of_turn(a)
        e.start_of_turn(b, initiative_count=10)
        result = self.contest(e, b, a, [4] * 4, [3] * 4)
        self.assertEqual(result['winner_id'], a.entity_id, '12 + 3 Secure + 2 Bind beats 16')
        self.assertEqual(GRAPPLE.relation(e, a)['secure'], {})
        self.next_round_a(e, a)
        e.end_of_turn(a)
        e.start_of_turn(b, initiative_count=10)
        result = self.contest(e, b, a, [4] * 4, [3] * 4)
        self.assertEqual(result['winner_id'], b.entity_id, 'Bind remains; spent Secure does not')

    def test_permissions_overlays_and_vortex_do_not_replace_actual_learning(self):
        for state, expected in (('permission', False), ('overlay_only', False),
                                ('hidden_learning', True), ('vortex', False)):
            with self.subTest(state=state):
                e, a, b = self.world()
                if state == 'permission':
                    self.learn(a, mode='permission')
                    self.assertIn(BIND, a.moves)
                elif state == 'overlay_only':
                    GRANTS.overlay(a, 'display-only', moves=[BIND])
                    self.assertEqual(a.moves, [BIND])
                elif state == 'hidden_learning':
                    self.learn(a)
                    GRANTS.overlay(a, 'display-only', moves=[])
                    self.assertNotIn(BIND, a.moves)
                else:
                    e.apply_status(a, '조이기', source='move/회오리불꽃', applied_by=b)
                    self.assertIn('조이기', a.conditions)
                row = self.enter(e, a, b, accuracy=4 + b.evasion('변화') - 1)
                self.assertEqual(bool(row), expected)
        e, a, b = self.world()
        self.learn(a)
        self.assertEqual(e.skill_roll(a, '전투', fixed=[3] * 4).total, 12)
        self.assertFalse(e.trip(a, b, challenger_skill='전투', defender_skill='전투',
            fixed_accuracy=6 + b.evasion('변화') - 1,
            challenger_options={'fixed': [4] * 4}, defender_options={'fixed': [2] * 4}))
        self.assertNotIn('넘어짐', b.conditions)

    def test_current_source_loss_forgetting_and_independent_learning_drive_native_results(self):
        for state, expected in (('last_source', False), ('other_source', True),
                                ('baseline', True), ('all_sources', False), ('forgotten', False)):
            with self.subTest(state=state):
                e, a, b = self.world()
                self.learn(a, 'first')
                if state in ('other_source', 'all_sources'):
                    self.learn(a, 'independent')
                if state in ('baseline', 'forgotten'):
                    e.gm.set_move(a, BIND, reason='actual observed independent learning')
                GRANTS.revoke(a, 'first', engine=e)
                if state == 'all_sources':
                    GRANTS.revoke(a, 'independent', engine=e)
                if state == 'forgotten':
                    e.gm.set_move(a, BIND, add=False, reason='actual observed forgetting')
                self.assertEqual(bool(self.enter(e, a, b, accuracy=4 + b.evasion('변화') - 1)), expected)
        for boundary in ('accuracy', 'skill'):
            with self.subTest(duplicate_boundary=boundary):
                e, a, b = self.world()
                self.learn(a, 'first')
                self.learn(a, 'independent')
                row = (self.enter(e, a, b, accuracy=4 + b.evasion('변화') - 2)
                    if boundary == 'accuracy' else
                    self.enter(e, a, b, faces_a=[3, 3, 2, 2], faces_b=[3] * 4))
                self.assertFalse(row, 'one learned Move contribution even with two owners')

    def test_fresh_rules_restore_recomputes_passive_consumption_then_obeys_source_loss(self):
        e, a, b = self.world('pokemon')
        self.learn(a, 'restored-owned-bind')
        identities = a.entity_id, b.entity_id
        saved = json.loads(json.dumps(e.export_state(), ensure_ascii=False))
        restored = Engine.import_state(Rules(ROOT, ruleset='core'), saved)
        index = {actor.entity_id: actor for actor in restored.everyone}
        a, b = (index[uid] for uid in identities)
        row = self.enter(restored, a, b, accuracy=4 + b.evasion('변화') - 1)
        self.assertEqual(row['dominant'], a.entity_id)
        GRANTS.revoke(a, 'restored-owned-bind', engine=restored)
        restored.end_of_turn(a)
        restored.start_of_turn(b, initiative_count=10)
        result = self.contest(restored, b, a, [4, 3, 3, 3], [3] * 4)
        self.assertEqual(result['winner_id'], b.entity_id)
        self.assertNotIn(BIND, a.moves)

    def test_invalid_selected_source_and_invented_public_bonus_refuse_before_costs(self):
        for defect in ('catalog', 'source_hash', 'source_file', 'definition', 'replacement'):
            with self.subTest(defect=defect):
                e, a, b = self.world()
                self.learn(a)
                before = e.export_state()
                if defect == 'catalog':
                    context = patch.dict(self.r.moves)
                elif defect == 'definition':
                    context = patch.dict(self.r.moves[BIND], {'frequency': '임의'})
                elif defect == 'replacement':
                    original = self.r._selected_rule
                    context = patch.object(self.r, '_selected_rule',
                        side_effect=lambda uid, *args, **kwargs: 'move/몸통박치기'
                            if uid == BIND else original(uid, *args, **kwargs))
                else:
                    origin = self.r.selection.units[BIND]['source']
                    changes = {'sha256': '0' * 64} if defect == 'source_hash' else {'file': 'db/no-such-bind-source.csv'}
                    context = patch.dict(origin, changes)
                with context:
                    if defect == 'catalog':
                        self.r.moves.pop(BIND)
                    with self.assertRaises((ValueError, KeyError)):
                        self.enter(e, a, b)
                self.assertEqual(e.export_state(), before)
                self.assertTrue(self.enter(e, a, b, accuracy=4 + b.evasion('변화') - 1))
        e, a, b = self.world()
        before = e.export_state()
        with self.assertRaises(TypeError):
            e.grapple(a, b, _accuracy_bonus=99)
        self.assertEqual(e.export_state(), before)


if __name__ == '__main__':
    unittest.main()
