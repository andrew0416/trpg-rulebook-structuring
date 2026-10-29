"""Authority candidate probes: native lethal-hit reaction and post-choice eligibility.

WI07 has a bound failing run; its repair is unexecuted. WI05 remains a probe.
They retain each Rules instance's own configured Rulings and source selection.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]

from engine import Rules
import contest_features as CF
import observed_resolution as OBS
import researcher_fields as RFS
import researcher_features as RF
import skill_modifiers as SKILLS
import test_book_researcher_fields_combat as relic_fixture
import test_category3_contest_skill_features as mistakes_fixture


class WorldInformationCandidateTests(unittest.TestCase):
    def test_wi05_native_lethal_melee_hit_cannot_use_unconscious_razors_reaction(self):
        case = relic_fixture.ResearcherFieldsCombatTests()
        case.rules = Rules(ROOT, ruleset='core')
        self.addCleanup(case.doCleanups)
        case.setUp()
        holder = case.restored('방패톱스', 'candidate-razors')
        relic = RFS.craft_relic(case.e, case.t, holder, relic='def', minutes=10)['id']
        RF.equip_relic(case.e, case.t, holder, relic)
        attacker = case.add('candidate-foe', 'pokemon', (3, 2), side='foe',
            species='피카츄', types=['전기'], moves=['move/몸통박치기'], speed=15)
        RFS.set_razors_reaction(case.e, holder, True)
        case.combat(attacker)

        # Positive control: actual equipped, conscious holder reacts to a real hit.
        before = attacker.hp
        case.use(attacker, holder, 'move/몸통박치기', face=15, set_damage=True)
        self.assertFalse(holder.fainted, 'control hit must leave the holder conscious')
        self.assertEqual(before - attacker.hp, case.e.tick_loss(attacker))
        self.assertEqual(len(holder.spec['researcher_relic_reactions']), 1)

        case.next_turn(attacker)
        case.e.gm.set_hp(holder, 1, reason='actual pre-hit HP for lethal reaction boundary')
        before = attacker.hp
        case.use(attacker, holder, 'move/몸통박치기', face=15, set_damage=True)
        self.assertTrue(holder.fainted, 'native damage must establish the tested boundary')
        self.assertLessEqual(holder.hp, 0)
        self.assertEqual(attacker.hp, before,
            'a standing choice must not authorize a new Reaction after native knockout')
        self.assertEqual(len(holder.spec['researcher_relic_reactions']), 1)

    def test_wi07_mistakes_rechecks_prerequisite_after_actual_gm_skill_change(self):
        case = mistakes_fixture.Tests()
        case.r = Rules(ROOT)
        case.fixture('슬기로움', CF.MISTAKES)
        control = case.mistakes(dc=99, roll_id='unchanged-authority')
        self.assertTrue(control['rerolled'])
        self.assertEqual(case.used(CF.MISTAKES), 1)

        case.fixture('슬기로움', CF.MISTAKES)
        seen = []
        request = 'changed-authority'

        def change_prerequisite(check):
            seen.append(check)
            case.e.gm.set_skill(case.t, '교활', 2,
                reason='independent GM correction after observing the failed check',
                request_id='gm-guile-correction')
            self.assertEqual(SKILLS.rank(case.r, case.t, '교활')[2], 2)
            # Establish the same consumer's current admission contract, without
            # undoing the independently authorized GM correction.
            with self.assertRaises(ValueError):
                CF.style_training(case.e, case.t, '슬기로움')
            return True

        denied = None
        outcome = None
        try:
            outcome = case.mistakes(dc=99, roll_id=request, decision=change_prerequisite)
        except ValueError as error:
            denied = error
        self.assertEqual(len(seen), 1, 'the real failed check must reach its decision callback')
        self.assertFalse(seen[0].passed)
        self.assertEqual(SKILLS.rank(case.r, case.t, '교활')[2], 2,
            'refusing the optional reroll must preserve the separate GM correction')
        self.assertIsNotNone(denied,
            'stale prerequisite reroll returned %r and used quota %s' %
            (outcome, case.used(CF.MISTAKES)))
        record = case.e._ap_rolls[request][OBS.KEY]
        self.assertEqual(record['state'], 'pending')
        self.assertEqual(record['observation']['first'].total, seen[0].total)
        self.assertEqual(case.used(CF.MISTAKES), 0)


    def test_wi07_mistakes_rechecks_selected_source_after_decision(self):
        from copy import deepcopy
        from ruleset import RuleFilter, ExcludedRuleSelection
        case = mistakes_fixture.Tests()
        case.r = Rules(ROOT)
        case.fixture('슬기로움', CF.MISTAKES)
        own_rulings = case.r.rulings
        changed = []
        request = 'source-excluded-after-observation'

        def exclude_source(check):
            self.assertFalse(check.passed)
            profile = deepcopy(case.r.ruleset.profile)
            profile['exclude_units'] = list(dict.fromkeys([
                *profile.get('exclude_units', []), CF.MISTAKES]))
            case.r.ruleset = RuleFilter(profile, name='observed-Mistakes-source-exclusion')
            case.r._apply_ruleset()
            self.assertIs(case.r.rulings, own_rulings)
            self.assertIs(case.e.rulings, own_rulings)
            changed.append(True)
            return True

        with self.assertRaises(ExcludedRuleSelection):
            case.mistakes(dc=99, roll_id=request, decision=exclude_source)
        self.assertEqual(changed, [True], 'source selection must finish before the reroll refusal')
        self.assertEqual(case.used(CF.MISTAKES), 0)
        self.assertEqual(case.e._ap_rolls[request][OBS.KEY]['state'], 'pending')
        self.assertIn(CF.MISTAKES, case.r.ruleset.exclude_units)

if __name__ == '__main__':
    unittest.main()