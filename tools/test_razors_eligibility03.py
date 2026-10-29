"""WI05: actual paid melee hit, living/KO eligibility, and codec recovery."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]

from engine import Rules
import attack_damage_history as HISTORY
import researcher_fields as RFS
import researcher_features as RF
import test_book_researcher_fields_combat as fixture


class RazorsEligibilityTests(unittest.TestCase):
    def paid_hit(self, case, *, reacts):
        attacker, holder = case.attacker, case.holder
        before = attacker.hp
        holder_before = holder.hp
        reactions = len(holder.spec.get('researcher_relic_reactions', []))
        history = list(getattr(attacker, '_action_history', []))
        hits = len(HISTORY.records(holder))
        heavy = set(case.e._heavy_events)
        self.assertEqual(attacker.budget['standard'], 1)
        case.use(attacker, holder, 'move/몸통박치기', face=15, set_damage=True)
        self.assertLess(holder.hp, holder_before, 'actual native hit must deal damage')
        self.assertEqual(attacker.budget['standard'], 0)
        self.assertEqual(attacker._action_history, history + ['standard'])
        self.assertEqual(len(HISTORY.records(holder)), hits + 1)
        added = set(case.e._heavy_events) - heavy
        self.assertEqual(len(added), 1, 'one real paid attack crosses the Heavy adapter')
        packet = case.e._heavy_events[added.pop()]
        self.assertIs(packet['attacker'], attacker)
        self.assertIs(packet['target'], holder)
        self.assertEqual(packet['move']['id'], 'move/몸통박치기')
        self.assertGreater(packet['amount'], 0)
        self.assertEqual(packet['before']['hp'], holder_before)
        self.assertEqual(packet['observed_after']['hp'], holder.hp)
        self.assertIsNone(case.e._heavy_pending)
        self.assertFalse(case.e._heavy_native_receipts)
        self.assertEqual(before - attacker.hp, case.e.tick_loss(attacker) if reacts else 0)
        self.assertEqual(len(holder.spec.get('researcher_relic_reactions', [])), reactions + int(reacts))
        self.assertTrue(holder.spec['researcher_razors_reaction'], 'eligibility must not erase the standing choice')

    def exercise(self, *, roundtrip):
        case = fixture.ResearcherFieldsCombatTests()
        case.rules = Rules(ROOT, ruleset='core')
        self.addCleanup(case.doCleanups)
        case.setUp()
        case.holder = case.restored('방패톱스', 'razors-eligibility')
        relic = RFS.craft_relic(case.e, case.t, case.holder, relic='def', minutes=10)['id']
        RF.equip_relic(case.e, case.t, case.holder, relic)
        case.attacker = case.add('razors-foe', 'pokemon', (3, 2), side='foe',
            species='피카츄', types=['전기'], moves=['move/몸통박치기'], speed=15)
        RFS.set_razors_reaction(case.e, case.holder, True)
        case.combat(case.attacker)
        self.paid_hit(case, reacts=True)
        self.assertFalse(case.holder.fainted)
        case.next_turn(case.attacker)
        case.e.gm.set_hp(case.holder, 1, reason='observed pre-hit HP at the knockout boundary')
        self.paid_hit(case, reacts=False)
        self.assertTrue(case.holder.fainted)
        self.assertLessEqual(case.holder.hp, 0)
        if roundtrip:
            hp = case.holder.hp
            reactions = list(case.holder.spec['researcher_relic_reactions'])
            case.restore('t', 'holder', 'attacker')
            self.assertEqual(case.holder.hp, hp)
            self.assertTrue(case.holder.fainted)
            self.assertEqual(case.holder.spec['researcher_relic_reactions'], reactions)
            self.assertTrue(case.holder.spec['researcher_razors_reaction'])
        # A separate, authorized recovery must not permanently disable the offer.
        case.e.gm.set_hp(case.holder, case.holder.base_max_hp,
            reason='GM-observed recovery after the completed knockout hit')
        self.assertFalse(case.holder.fainted)
        case.next_turn(case.attacker)
        self.paid_hit(case, reacts=True)
        self.assertFalse(case.holder.fainted)
        self.assertEqual(len(case.holder.spec['researcher_relic_reactions']), 2)
        case.valid()

    def test_native_living_ko_recovery_rechecks_reaction_without_replaying_paid_hit(self):
        self.exercise(roundtrip=False)

    def test_codec_restored_knockout_keeps_choice_and_recovered_holder_reacts_to_new_hit(self):
        self.exercise(roundtrip=True)


if __name__ == '__main__':
    unittest.main()