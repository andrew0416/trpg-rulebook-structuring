"""Private native Probability choices inside the real Mistakes first-roll owner."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules
import contest_features as CF
import frequency as FREQ
import observed_resolution as OBS
import skill_modifiers as SK
import warper as WARPER
import test_category3_contest_skill_features as FIXTURE


class ContestPrivateCommitTests(unittest.TestCase):
    def fixture(self):
        case = FIXTURE.Tests()
        case.r = Rules(ROOT)
        case.fixture('슬기로움', CF.MISTAKES)
        self.assertEqual((case.t.side, case.p.side), ('party', 'party'))
        case.e.gm.set_ability(case.t, WARPER.PROBABILITY,
                             reason='actual Probability Control provider for the native skill roll')
        return case

    def test_private_probability_no_receipt_gm_correction_survives_rejected_stale_first_roll(self):
        for accepted in (False, True):
            with self.subTest(probability_accepted=accepted):
                case = self.fixture()
                seen, own_choices, corrected, revisions = [], [], [], []
                trainer_spec, pokemon_spec = case.t.spec, case.p.spec

                def correction(first):
                    seen.append(first)
                    before_receipts = deepcopy(case.t._state_receipts)
                    before_revision = case.t._state_revision
                    case.e.gm.set_skill(case.t, '교활', 2,
                        reason='independent actual GM correction without optional request identity')
                    self.assertEqual(case.t._state_receipts, before_receipts)
                    self.assertEqual(case.t._state_revision, before_revision + 1)
                    revisions.append(case.t._state_revision)
                    corrected.append(deepcopy(case.t.spec))
                    return accepted

                case.e.arm_probability_control(case.t, case.p, purpose='skill',
                    decision=correction, reroll_fixed=[2, 2, 2])
                rng = case.e.rng.getstate()
                before_pokemon = deepcopy(case.p.spec)
                request = 'private-first-correction'
                with self.assertRaisesRegex(ValueError, 'original world changed before commit'):
                    case.mistakes(dc=99, fixed=None, reroll_faces=None, roll_id=request,
                        decision=lambda check: own_choices.append(check) or False)
                self.assertEqual(len(seen), 1, 'actual Probability callback must run')
                self.assertEqual(own_choices, [], 'stale private calculation must not expose a Mistakes choice')
                self.assertIs(case.t.spec, trainer_spec)
                self.assertIs(case.p.spec, pokemon_spec)
                self.assertEqual(SK.rank(case.r, case.t, '교활')[2], 2)
                self.assertEqual(case.t.spec, corrected[0], 'retain the independent GM operation exactly')
                self.assertEqual(case.t._state_revision, revisions[0])
                self.assertEqual(case.p.spec, before_pokemon)
                self.assertEqual(case.e.rng.getstate(), rng)
                self.assertEqual(case.used(CF.MISTAKES), 0)
                self.assertNotIn(OBS.KEY, case.e._ap_rolls.get(request, {}))

    def test_normal_private_probability_choice_commits_before_mistakes_decline(self):
        for accepted in (False, True):
            with self.subTest(probability_accepted=accepted):
                case = self.fixture()
                seen, own_choices = [], []
                trainer_spec, pokemon_spec = case.t.spec, case.p.spec
                case.e.arm_probability_control(case.t, case.p, purpose='skill',
                    decision=lambda first: seen.append(first) or accepted, reroll_fixed=[2, 2, 2])
                result = case.mistakes(dc=99, fixed=[1, 1, 1], roll_id='normal-private-choice',
                    decision=lambda check: own_choices.append(check) or False)
                self.assertEqual((len(seen), len(own_choices)), (1, 1))
                self.assertEqual(result['first_roll'].faces, (2, 2, 2) if accepted else (1, 1, 1))
                self.assertEqual(result['roll'], result['first_roll'])
                self.assertFalse(result['rerolled'])
                self.assertEqual(case.used(CF.MISTAKES), 0)
                self.assertEqual(FREQ.state(case.t)['activations'].get(WARPER.PROBABILITY, {}).get('used', 0),
                                 1 if accepted else 0)
                self.assertNotIn('native_roll_offer', case.t.spec)
                self.assertEqual(case.e._ap_rolls['normal-private-choice'][OBS.KEY]['state'], 'complete')
                self.assertIs(case.t.spec, trainer_spec)
                self.assertIs(case.p.spec, pokemon_spec)


if __name__ == '__main__':
    unittest.main()