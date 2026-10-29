"""Native Eject Pack windows distinguish eligibility probes from real Free actions."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules
from contest import ContestRules
import action_points as AP
import contest_features as CF
import csv_item_physical_contracts as PHYSICAL
import skill_feature_actions as SKILL
import warper as WARPER
import test_category2_csv_remaining_item_contracts as ITEMS_FIX
import test_category3_contest_skill_features as MISTAKES_FIX
import test_category3_skill_feature_actions as MONKEY_FIX
import test_category3_reliable_performance as RELIABLE_FIX


class PreflightEjectWindowTests(unittest.TestCase):
    def pack(self, engine, rules):
        fixture = ITEMS_FIX.RemainingCsvItemContractTests()
        fixture.r = rules
        holder = fixture.pokemon('actual-preflight-eject-holder')
        engine.gm.add_combatant(holder, reason='actual independent held-reaction participant')
        obj = fixture.equip(engine, holder, 'native-preflight-eject-pack', 'item/탈출팩')
        engine.change_stage(holder, 'atk', -1)
        pending = holder.spec[PHYSICAL.PENDING]['eject_pack']
        self.assertEqual(pending['instance_id'], obj['id'])
        self.assertEqual(pending['event']['stage'], {'stat': 'atk', 'before': 0, 'after': -1})
        return holder, obj, deepcopy(pending), deepcopy(obj)

    def retained(self, holder, obj, pending, before_object):
        self.assertEqual(holder.spec[PHYSICAL.PENDING]['eject_pack'], pending)
        self.assertEqual(obj, before_object)
        self.assertNotIn('consumed', obj)

    def test_mistakes_preflight_success_decline_and_private_refusal_keep_window_until_real_reroll(self):
        for mode in ('success', 'decline', 'private_refusal', 'accept'):
            with self.subTest(mode=mode):
                case = MISTAKES_FIX.Tests()
                case.r = Rules(ROOT)
                case.fixture('슬기로움', CF.MISTAKES)
                seen = []
                if mode == 'private_refusal':
                    case.e.gm.set_ability(case.t, WARPER.PROBABILITY,
                                         reason='actual native Probability provider')
                    case.e.arm_probability_control(case.t, case.p, purpose='skill',
                        decision=lambda first: seen.append(first) or 'invalid choice')
                holder, obj, pending, before_object = self.pack(case.e, case.r)
                history = list(getattr(case.t, '_action_history', []))
                if mode == 'private_refusal':
                    with self.assertRaisesRegex(ValueError, 'observed native reroll choice'):
                        case.mistakes(dc=99, roll_id='mistakes-window', decision=lambda check: False)
                    self.assertEqual(len(seen), 1)
                else:
                    result = case.mistakes(dc=1 if mode == 'success' else 99,
                        roll_id='mistakes-window', decision=lambda check: seen.append(check) or mode == 'accept')
                    self.assertEqual(result['rerolled'], mode == 'accept')
                    self.assertEqual(len(seen), 0 if mode == 'success' else 1)
                if mode == 'accept':
                    self.assertNotIn('eject_pack', holder.spec.get(PHYSICAL.PENDING, {}))
                    self.assertEqual(case.t._action_history, history + ['free'])
                    self.assertEqual(case.used(CF.MISTAKES), 1)
                    self.assertNotIn('consumed', obj)
                else:
                    self.retained(holder, obj, pending, before_object)
                    self.assertEqual(getattr(case.t, '_action_history', []), history)
                    self.assertEqual(case.used(CF.MISTAKES), 0)

    def test_skill_monkey_preflight_decline_and_bad_choice_keep_window_until_accepted_action(self):
        for mode in ('decline', 'bad_choice', 'accept'):
            with self.subTest(mode=mode):
                case = MONKEY_FIX.Tests()
                case.r = Rules(ROOT)
                case.fixture()
                holder, obj, pending, before_object = self.pack(case.e, case.r)
                history = list(getattr(case.t, '_action_history', []))
                seen = []
                def choose(first):
                    seen.append(first)
                    return 'invalid' if mode == 'bad_choice' else mode == 'accept'
                if mode == 'bad_choice':
                    with self.assertRaisesRegex(ValueError, 'observed reroll choice'):
                        case.roll(feature_options={'decision': choose, 'reroll_faces': [2] * 4})
                    self.assertEqual(SKILL.event(case.e, case.t, 'r').state, 'pending')
                else:
                    case.roll(feature_options={'decision': choose, 'reroll_faces': [2] * 4})
                self.assertEqual(len(seen), 1)
                if mode == 'accept':
                    self.assertNotIn('eject_pack', holder.spec.get(PHYSICAL.PENDING, {}))
                    self.assertEqual(case.t._action_history, history + ['free'])
                    self.assertEqual(case.used(), 1)
                    self.assertNotIn('consumed', obj)
                else:
                    self.retained(holder, obj, pending, before_object)
                    self.assertEqual(getattr(case.t, '_action_history', []), history)
                    self.assertEqual(case.used(), 0)

    def test_reliable_accuracy_quote_keeps_window_and_actual_accuracy_expires_it_once(self):
        case = RELIABLE_FIX.Tests()
        case.r = Rules(ROOT)
        case.cr = ContestRules(ROOT)
        case.setUp()
        holder, obj, pending, before_object = self.pack(case.e, case.r)
        history = list(getattr(case.t, '_action_history', []))
        available = AP.available(case.t)
        CF.prepare_reliable_accuracy(case.e, case.t, case.p)
        self.retained(holder, obj, pending, before_object)
        self.assertEqual((AP.available(case.t), getattr(case.t, '_action_history', [])), (available, history))
        case.accuracy()
        self.assertNotIn('eject_pack', holder.spec.get(PHYSICAL.PENDING, {}))
        self.assertEqual(AP.available(case.t), available - 2)
        self.assertEqual(case.t._action_history, history + ['free'])
        self.assertNotIn('consumed', obj)


if __name__ == '__main__':
    unittest.main()