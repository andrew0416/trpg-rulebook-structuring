"""Independent cross-owner restore and actual evolution checks for CSV104."""
from copy import deepcopy
import json
import unittest
import test_category2_mentor_csv as _fixture_test_category2_mentor_csv
from engine import Rules, Engine
import mentor_csv as CSV
import pokemon_teaching as T
import move_state as MOVES
import state_codec as CODEC
import downtime as D


class MentorIndependentTests(unittest.TestCase):
    setUpClass=classmethod(_fixture_test_category2_mentor_csv.MentorCSVTests.setUpClass.__func__)

    def fixture(self):
        f=_fixture_test_category2_mentor_csv.MentorCSVTests();f.rules=self.rules;f.setUp();f.acquire();return f

    def test_mixed_free_paid_daily_pool_survives_both_restores_and_both_entries(self):
        f=self.fixture();p=f.pupil('이상해씨',30,tp=3)
        for mid,cost in [('move/덩굴채찍',0),('move/광합성',1),('move/씨폭탄',1)]:
            self.assertEqual(f.teach(p,mid)['point_cost'],cost)
        self.assertEqual((p.spec['tutor_points'],f.e.elapsed_seconds),(1,180))
        f.e.gm.snapshot('three-paid-and-free')
        loaded=Engine.import_state(Rules(str(self.rules.root),ruleset='core'),json.loads(json.dumps(f.e.export_state())))
        f.e.gm.restore('three-paid-and-free')
        for e in (f.e,loaded):
            index={c.entity_id:c for c in e.everyone};a=index[f.a.entity_id];target=index[p.entity_id]
            before=CODEC.dump_engine(e)
            for entry in ('csv','catalog'):
                with self.assertRaisesRegex(ValueError,'daily frequency'):
                    if entry=='csv':CSV.teach(e,a,target=target,move_id='move/돌진',seconds=60,reason='actual fourth instruction')
                    else:T.teach_feature(e,a,target=target,move_id='move/돌진',feature=T.MENTOR,seconds=60,reason='actual fourth old entry')
                self.assertEqual(CODEC.dump_engine(e),before)
            self.assertEqual((target.spec['tutor_points'],e.elapsed_seconds),(1,180))

    def test_actual_evolution_retains_original_learning_and_rejects_mirrored_proof_in_both_restores(self):
        f=self.fixture();p=f.pupil('실쿤',10,tp=1);mid='move/단단해지기'
        f.teach(p,mid)
        original=deepcopy(p.spec['move_learning'][mid])
        self.assertTrue(D.evolve_combatant(f.e,p,'뷰티플라이')['evolved'])
        self.assertTrue(any(row.get('kind')=='evolution' for row in p.spec['allocation_migrations']))
        self.assertEqual(p.spec['move_learning'][mid],original)
        self.assertEqual(MOVES.describe(self.rules,p.spec)['classifications'][mid],'natural')
        self.assertEqual((original['learned_at_level'],original['mentor_skill_ranks'],original['paid_tp']),(10,[5,3],0))
        f.e.gm.snapshot('evolved-proof')
        valid_payload=f.e.export_state()
        for mutation in ('source','ancestor','payment'):
            def corrupt(spec):
                row=spec['move_learning'][mid]
                if mutation=='source':row['mentor_source_clause']='C2CSV/input/db/feats.csv:R106:main'
                elif mutation=='ancestor':row['mentor_csv_proof']['ancestor']='카스쿤'
                else:row['paid_tp']=1
                for i,logged in enumerate(spec['move_learning_log']):
                    if logged.get('move_id')==mid:spec['move_learning_log'][i]=dict(deepcopy(row),move_id=mid,replaced=logged.get('replaced'))
            saved=deepcopy(p.spec);corrupt(p.spec)
            with self.assertRaises(ValueError):MOVES.validate_actor(p)
            encoder=CODEC._Encoder(f.e);bad=deepcopy(valid_payload)
            bad['root']=encoder.value(f.e);bad['nodes']=encoder.nodes
            p.spec.clear();p.spec.update(saved)
            with self.assertRaises(ValueError):Engine.import_state(Rules(str(self.rules.root),ruleset='core'),bad)
            snapshot=f.e.gm.snapshots['evolved-proof']
            attrs=snapshot['combatants'][id(p)]
            prior=deepcopy(attrs['spec']);corrupt(attrs['spec'])
            with self.assertRaises(ValueError):f.e.gm.restore('evolved-proof')
            attrs['spec']=prior
            self.assertEqual(p.spec['move_learning'][mid],original)
        f.e.gm.restore('evolved-proof')
        loaded=Engine.import_state(Rules(str(self.rules.root),ruleset='core'),valid_payload)
        restored=next(c for c in loaded.everyone if c.entity_id==p.entity_id)
        self.assertEqual(restored.spec['move_learning'][mid],original)
        self.assertEqual(MOVES.describe(loaded.r,restored.spec)['classifications'][mid],'natural')


if __name__=='__main__':unittest.main()
