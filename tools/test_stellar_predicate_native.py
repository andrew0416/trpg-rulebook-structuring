"""Tera Blast's native predicates complete once; unrelated conditions stay unknown."""
import unittest
import effect_contracts as CONTRACTS
import stellar_tera_blast as STELLAR
from tools import test_stellar_r663_optional_source_revision as FIXTURE


class StellarNativePredicateTests(unittest.TestCase):
    setUpClass=classmethod(FIXTURE.StellarR663OptionalSourceRevisionTests.setUpClass.__func__)
    world=FIXTURE.StellarR663OptionalSourceRevisionTests.world
    next_turn=FIXTURE.StellarR663OptionalSourceRevisionTests.next_turn
    hit=FIXTURE.StellarR663OptionalSourceRevisionTests.hit
    last=FIXTURE.StellarR663OptionalSourceRevisionTests.last

    def test_dormant_source_conditions_finish_native_hit_and_publish_actual_opportunity(self):
        e,actor,target=self.world(radiate=False)
        move=e.r.move('move/테라버스트-물리');ctx={'move':move,'attacker':actor,'target':target,'hit':True}
        self.assertIs(CONTRACTS.condition_text(e,actor,target,'terastallized',ctx),False)
        self.assertIs(CONTRACTS.condition_text(e,actor,target,'stellar',ctx),False)
        self.assertIsNone(CONTRACTS.condition_text(e,actor,target,'stellar',dict(ctx,move=e.r.move('move/몸통박치기'))))
        self.assertGreater(self.hit(e,actor,target,move['id']),0)
        self.assertEqual(self.last(e)['phase'],'complete')
        self.assertEqual(len(actor.spec[STELLAR.STATE]['opportunities']),1)
        CONTRACTS.ensure_clear(e)
        self.next_turn(e,actor)
        self.assertEqual(actor.move_uses[move['id']],1)
        self.assertTrue(e.validate_state()['valid'])


if __name__=='__main__':unittest.main()
