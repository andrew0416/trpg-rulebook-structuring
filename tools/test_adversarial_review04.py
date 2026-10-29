"""Unexecuted adversarial compositions for integrated payload/Mistakes staging."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules
import blessing_skill_rules as B
import contest_features as CF
import skill_feature_actions as SF
import skill_modifiers as SK
import warper as WARPER
import test_authority_candidate01_probes as team_fixture
import test_category3_contest_skill_features as mistakes_fixture


class AdversarialReview04(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        team_fixture.Candidate01Probes.setUpClass()

    def team(self):
        fixture = team_fixture.Candidate01Probes()
        engine, first, second = fixture.wisdom_fixture(probability=True)
        return fixture, engine, first, second

    def team_state(self, engine, actors):
        memo = {id(actor): actor for actor in actors}
        return deepcopy(([(actor.spec, 'budget' in vars(actor), getattr(actor, 'budget', None),
                          '_action_history' in vars(actor), getattr(actor, '_action_history', [])) for actor in actors],
                         engine.rng.getstate(), engine.log_lines, engine._ap_rolls), memo)

    def test_unreached_help_offer_does_not_disable_private_team_rollback(self):
        fixture, engine, first, second = self.team()
        helper = fixture.trainer(engine, 'armed-only-helper', (4, 2), feats=(SF.HELP,))
        helper_seen = []
        engine.offer_let_me_help(helper, second, request_id='armed-only-help', payment='next',
            decision=lambda check: helper_seen.append(check) or False)
        probability_seen = []
        def invalid_probability(roll):
            probability_seen.append(roll)
            return 'invalid native choice'
        engine.arm_probability_control(first, second, purpose='skill', decision=invalid_probability)
        actors = (first, second, helper)
        before = self.team_state(engine, actors)
        with self.assertRaisesRegex(ValueError, 'observed native reroll choice'):
            engine.common_action(skill='오컬트학', dc=10, mode='team',
                participants=[first, second], required_people=2,
                equal_contribution=True, no_main_actor=True)
        self.assertEqual(len(probability_seen), 1, 'must reach the actual second native roll choice')
        self.assertEqual(helper_seen, [], 'mere help offer is not an exposed Help decision')
        self.assertEqual(self.team_state(engine, actors), before,
            'an unreached Help offer must not turn private first-participant consumption into a live commit')
        self.assertEqual(first.spec[B.STATE]['activations'][B.ANCIENT_WISDOM]['status'], 'pending')

    def test_mistakes_private_probability_choice_preserves_independent_gm_correction(self):
        # The public Mistakes decision is a positive control for the earlier
        # private first-roll Probability callback. Both decline their rerolls.
        for boundary in ('mistakes', 'private_probability'):
            with self.subTest(boundary=boundary):
                case = mistakes_fixture.Tests()
                case.r = Rules(ROOT)
                case.fixture('슬기로움', CF.MISTAKES)
                self.assertEqual((case.t.side, case.p.side), ('party', 'party'))
                seen = []
                def correction(preview):
                    seen.append(preview)
                    case.e.gm.set_skill(case.t, '교활', 2,
                        reason='independent GM correction in actual observed callback',
                        request_id='adversarial04-guile-' + boundary)
                    self.assertEqual(SK.rank(case.r, case.t, '교활')[2], 2)
                    return False
                if boundary == 'private_probability':
                    case.e.gm.set_ability(case.t, WARPER.PROBABILITY,
                                         reason='GM observes actual Probability Control ability')
                    case.e.arm_probability_control(case.t, case.p, purpose='skill', decision=correction)
                    own_decision = lambda check: False
                else:
                    own_decision = correction
                result = None
                try:
                    result = case.mistakes(dc=99, roll_id='adversarial04-' + boundary,
                                           decision=own_decision)
                except ValueError:
                    if boundary == 'mistakes':raise
                    # Refusing a stale private first calculation is permitted;
                    # overwriting its independently completed GM correction is not.
                self.assertEqual(len(seen), 1, 'native callback must actually run')
                self.assertEqual(SK.rank(case.r, case.t, '교활')[2], 2,
                    'private first-roll transaction overwrote an independent live trainer correction')
                self.assertEqual(case.used(CF.MISTAKES), 0)
                if result is not None:self.assertFalse(result['rerolled'])

    def test_payload_team_original_gm_change_rejects_staged_consumption_but_keeps_correction(self):
        _, engine, first, second = self.team()
        original_first = first.spec
        original_second = second.spec
        paid_activation = deepcopy(first.spec[B.STATE])
        rng = engine.rng.getstate()
        seen = []
        def correction(roll):
            seen.append(roll)
            engine.gm.set_skill(second, '집중', 4,
                reason='independent original graph correction during staged native choice',
                request_id='adversarial04-focus')
            return False
        engine.arm_probability_control(first, second, purpose='skill', decision=correction)
        with self.assertRaisesRegex(ValueError, 'original world changed before commit'):
            engine.common_action(skill='오컬트학', dc=10, mode='team',
                participants=[first, second], required_people=2,
                equal_contribution=True, no_main_actor=True)
        self.assertEqual(len(seen), 1)
        self.assertIs(first.spec, original_first)
        self.assertIs(second.spec, original_second)
        self.assertEqual(SK.rank(engine.r, second, '집중')[2], 4)
        self.assertEqual(first.spec[B.STATE], paid_activation)
        self.assertEqual(engine.rng.getstate(), rng)

    def test_mistakes_private_probability_gm_correction_without_request_id(self):
        case = mistakes_fixture.Tests()
        case.r = Rules(ROOT)
        case.fixture('슬기로움', CF.MISTAKES)
        self.assertEqual((case.t.side, case.p.side), ('party', 'party'))
        case.e.gm.set_ability(case.t, WARPER.PROBABILITY,
                             reason='actual Probability Control provider for no-receipt diagnostic')
        seen = []
        def correction(preview):
            before_receipts = deepcopy(case.t._state_receipts)
            before_revision = case.t._state_revision
            seen.append(preview)
            # The only expansion axis: use this public GM API's default None
            # request ID, instead of writing the shared optional receipt dict.
            case.e.gm.set_skill(case.t, '교활', 2,
                reason='independent actual GM correction without request identity')
            self.assertEqual(case.t._state_receipts, before_receipts)
            self.assertEqual(case.t._state_revision, before_revision + 1)
            self.assertEqual(SK.rank(case.r, case.t, '교활')[2], 2)
            return False
        case.e.arm_probability_control(case.t, case.p, purpose='skill', decision=correction)
        result = None
        refusal = None
        try:
            result = case.mistakes(dc=99, roll_id='adversarial04-no-request-id',
                                   decision=lambda check: False)
        except ValueError as error:
            refusal = error
        actual = SK.rank(case.r, case.t, '교활')[2]
        print('AR04-H02-no-request-id', {'callback_count':len(seen), 'guile':actual,
            'mistakes_used':case.used(CF.MISTAKES),
            'refusal':None if refusal is None else type(refusal).__name__ + ': ' + str(refusal),
            'returned':result is not None})
        self.assertEqual(len(seen), 1, 'actual native Probability callback must be reached')
        self.assertEqual(actual, 2, 'independent no-request-ID GM correction was overwritten')
        self.assertEqual(case.used(CF.MISTAKES), 0)
        if result is not None:self.assertFalse(result['rerolled'])

if __name__ == '__main__':
    unittest.main()