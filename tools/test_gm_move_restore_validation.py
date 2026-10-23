"""Candidate-only move validation preserves valid saves and rejects atomically."""
from copy import deepcopy
import unittest
import test_category2_mentor_move_state as _fixture_test_category2_mentor_move_state
from engine import Rules, Engine
import move_state as MOVES
import state_codec as CODEC


class RestoreValidationTests(unittest.TestCase):
    setUpClass=classmethod(_fixture_test_category2_mentor_move_state.MentorMoveStateTests.setUpClass.__func__)

    def test_actual_acquisition_receipt_with_coherent_projection_rejects_atomically(self):
        from test_category2_signature_moves import SignatureMoveTests
        import trainer_feature_acquisition as A
        f=SignatureMoveTests();f.rules=self.r;f.setUp();f.acquire()
        f.engine.gm.snapshot('acquisition')
        attrs=f.engine.gm.snapshots['acquisition']['combatants'][id(f.actor)]
        spec=attrs['spec'];rows=spec[A.LEDGER_KEY]
        row=next(iter(rows.values()))
        row['selection']['values']=['move/코튼가드']
        spec[A.PROJECTION_KEY]=A._projection_from_rows(list(rows.values()))
        f.engine.advance_time(1,f.engine.everyone)
        before=CODEC.dump_engine(f.engine)
        with self.assertRaises(ValueError):f.engine.gm.restore('acquisition')
        self.assertEqual(CODEC.dump_engine(f.engine),before)

    def fixture(self):
        f=_fixture_test_category2_mentor_move_state.MentorMoveStateTests();f.r=self.r;f.setUp();p=f.pokemon();f.teach(p,'move/화염방사');return f,p

    def test_valid_old_mentor_and_legacy_actor_restore_without_new_route_requirement(self):
        f,p=self.fixture();legacy=f.pokemon()
        f.e.gm.set_move(legacy,'move/파도타기',True,reason='legacy observed known move without invented tutor receipt')
        self.assertIn('move/파도타기',MOVES.describe(self.r,legacy.spec)['unknown_routes'])
        proof=deepcopy(p.spec['move_learning']);f.e.gm.snapshot('valid-old')
        f.e.gm.set_move(p,'move/화염방사',False,reason='later actual forgetting')
        f.e.gm.restore('valid-old')
        self.assertEqual(p.spec['move_learning'],proof)
        self.assertEqual(MOVES.describe(self.r,p.spec)['classifications']['move/화염방사'],'natural')
        self.assertIn('move/파도타기',MOVES.describe(self.r,legacy.spec)['unknown_routes'])
        self.assertTrue(f.e.validate_state()['valid'])

    def test_invalid_move_and_mirrored_natural_receipt_reject_before_any_world_commit(self):
        f,p=self.fixture();other=f.pokemon()
        f.e.gm.snapshot('bad')
        snapshot=f.e.gm.snapshots['bad'];original=deepcopy(snapshot['combatants'][id(p)])
        f.e.advance_time(1,f.e.everyone);other.hp-=1
        before=CODEC.dump_engine(f.e)
        for mode in ('unknown_move','natural_proof'):
            attrs=snapshot['combatants'][id(p)]
            attrs.clear();attrs.update(deepcopy(original))
            def corrupt(spec):
                if mode=='unknown_move':spec['moves'].append('move/not-actual')
                else:
                    row=spec['move_learning']['move/화염방사'];row['mentor_skill_ranks']=[3,3]
                    for i,old in enumerate(spec['move_learning_log']):
                        if old.get('move_id')=='move/화염방사':spec['move_learning_log'][i]=dict(deepcopy(row),move_id='move/화염방사',replaced=old.get('replaced'))
            corrupt(attrs['spec'])
            with self.assertRaises(ValueError):f.e.gm.restore('bad')
            self.assertEqual(CODEC.dump_engine(f.e),before)
            saved=deepcopy(p.spec);corrupt(p.spec)
            encoder=CODEC._Encoder(f.e);bad=deepcopy(before)
            bad['root']=encoder.value(f.e);bad['nodes']=encoder.nodes
            p.spec.clear();p.spec.update(saved)
            with self.assertRaises(ValueError):Engine.import_state(Rules(str(self.r.root),ruleset='core'),bad)
            self.assertEqual(CODEC.dump_engine(f.e),before)


if __name__=='__main__':unittest.main()
