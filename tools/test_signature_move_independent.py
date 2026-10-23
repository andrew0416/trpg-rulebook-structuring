"""Independent historical qualification and native-consumer integrity checks."""
from copy import deepcopy
import json
import unittest
import test_category2_signature_moves as _fixture_test_category2_signature_moves
import signature_moves as S
import trainer_feature_acquisition as A
import state_grants as G
import items as I
import class_move_grants as CLASSES
import frequency as F
from engine import Rules, Engine


class IndependentSignatureTests(unittest.TestCase):
    setUpClass = classmethod(_fixture_test_category2_signature_moves.SignatureMoveTests.setUpClass.__func__)

    def fixture(self):
        fixture = _fixture_test_category2_signature_moves.SignatureMoveTests()
        fixture.rules = self.rules
        fixture.setUp()
        return fixture

    def test_actual_class_source_withdrawal_preserves_historical_selection_after_restore(self):
        fixture = self.fixture()
        e, actor = fixture.engine, fixture.actor
        G.set_baseline(actor, 'moves', ['move/방어지령', 'move/단단해지기'])
        actor.spec['classes'] = ['class/로그']
        I.register_feats(e, actor)
        receipt = fixture.acquire(move='move/도둑질', stat='spe')
        actor.spec['classes'] = []
        CLASSES.register_all(e, actor)
        self.assertFalse(any(row.get('class_move_projection') for row in actor.spec[G.KEY]['sources'].values()))
        self.assertEqual(S.receipt(actor), receipt)
        self.assertEqual(fixture.acquire(move='move/도둑질', stat='spe'), receipt)
        e.gm.snapshot('historical-class')
        payload = json.loads(json.dumps(e.export_state(), ensure_ascii=False))
        restored = Engine.import_state(Rules(str(self.rules.root), ruleset='core'), payload)
        e.gm.restore('historical-class')
        for current in (e, restored):
            holder = next(c for c in current.everyone if c.entity_id == actor.entity_id)
            self.assertEqual(S.receipt(holder), receipt)
            self.assertEqual(holder.stats['spe'], 11)
            self.assertNotIn('move/도둑질', holder.moves)
            self.assertEqual(A.selected_values(holder, S.FEATURE, S.FEATURE + ':1'), ('move/도둑질',))

    def test_native_used_pool_and_original_qualification_cannot_be_rewritten_on_read(self):
        fixture = self.fixture()
        e, actor = fixture.engine, fixture.actor
        receipt = fixture.acquire(move='move/코튼가드', stat='hp')
        fixture.turn()
        fixture.cast('move/코튼가드')
        self.assertEqual(actor.move_uses['move/코튼가드'], 1)
        self.assertEqual(F.move_frequency(e, 'move/코튼가드', actor), ('scene', 2))
        stored = actor.spec[A.LEDGER_KEY]['signature/1']
        original = deepcopy(stored['qualification'])
        stored['qualification']['checks'][1]['observed']['count'] = 3
        before = deepcopy((actor.budget, actor.move_uses, e.rng.getstate()))
        for read in (lambda: S.receipt(actor), lambda: F.move_frequency(e, 'move/코튼가드', actor), e.export_state):
            with self.assertRaises(ValueError):
                read()
        self.assertEqual((actor.budget, actor.move_uses, e.rng.getstate()), before)
        stored['qualification'] = original
        self.assertEqual(S.receipt(actor), receipt)
        loaded = Engine.import_state(Rules(str(self.rules.root), ruleset='core'), e.export_state())
        holder = next(c for c in loaded.everyone if c.entity_id == actor.entity_id)
        self.assertEqual(holder.move_uses['move/코튼가드'], 1)
        self.assertEqual(holder.stats['hp'], 11)
        self.assertEqual(F.move_frequency(loaded, 'move/코튼가드', holder), ('scene', 2))


if __name__ == '__main__':
    unittest.main()
