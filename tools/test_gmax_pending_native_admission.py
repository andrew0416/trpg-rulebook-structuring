"""Derived Move wrappers preserve unresolved native source rulings before payment."""
from copy import deepcopy
import unittest
import test_category2_gmax_moves as FIXTURE
import common_checks as C
import musician as MUSICIAN


class GMaxPendingNativeAdmissionTests(unittest.TestCase):
    setUpClass=classmethod(FIXTURE.GMaxMoveTests.setUpClass.__func__)
    mapped_world=FIXTURE.GMaxMoveTests.mapped_world
    mapped_use=FIXTURE.GMaxMoveTests.mapped_use

    def test_no_accuracy_core_drown_out_ruling_remains_pending_without_completion_or_payload(self):
        e, actor, (inside, outside), base, mid=self.mapped_world('C2CSV-MOVE-R1021')
        e.gm.set_ability(inside,'소리묻히기',reason='actual counter ability')
        actor.registry.append({'type':'gain_keyword','keyword':'소리','moves':'all'})
        MUSICIAN.request_drown_out(e,inside,reason='actual unresolved Core cancellation')
        before=deepcopy((actor.budget,actor.move_uses,e.rng.getstate(),
                         e._gmax_payload_receipts,e._gmax_coin_rewards))
        result=self.mapped_use(e,actor,inside,base,mid,1)
        self.assertIsInstance(result,C.PendingDecision)
        self.assertEqual(result.basis['move_id'],mid)
        self.assertEqual((actor.budget,actor.move_uses,e.rng.getstate(),
                          e._gmax_payload_receipts,e._gmax_coin_rewards),before)
        self.assertFalse(getattr(e,'_move_completions',{}))
        self.assertFalse(getattr(e,'_gmax_activation_scopes',[]))


if __name__=='__main__':unittest.main()
