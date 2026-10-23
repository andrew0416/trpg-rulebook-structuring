"""Independent CSV91 cross-boundary consumer and original receipt checks."""
from copy import deepcopy
import json
import unittest
import test_category2_directive_features as _fixture_test_category2_directive_features
from engine import Rules
import state_codec as CODEC
import directive_features as D
import effects as FX
import root_resolution as ROOT_RESOLUTION

class DirectiveIndependentTests(unittest.TestCase):
    setUpClass=classmethod(_fixture_test_category2_directive_features.DirectiveFeatureTests.setUpClass.__func__)

    def fixture(self):
        f=_fixture_test_category2_directive_features.DirectiveFeatureTests();f.r=self.r;f.setUp();return f

    def test_low_current_charm_class_receipt_and_cross_scene_two_restores(self):
        f=self.fixture()
        # The acquired class is the printed prerequisite; no extra Grace or
        # Novice Charm reacquisition is printed for this already-owned feature.
        f.a.spec['skills']['매력']=1
        out=f.use('decrease')
        self.assertEqual(out['delta'],-2)
        self.assertEqual(f.e.initiative_value(f.b).value,f.base-2)
        f.e.end_of_turn(f.a)
        f.e.end_encounter(f.e.everyone,round_elapsed_seconds=0)
        f.e.end_scene(f.e.everyone)
        f.a.spec['skills']['매력']=6
        f.e.gm.snapshot('after-scene')
        f.e.gm.restore('after-scene')
        payload=json.loads(json.dumps(CODEC.dump_engine(f.e)))
        loaded=CODEC.load_engine(Rules(str(self.r.root),ruleset='core'),payload)
        for e in (f.e,loaded):
            a=next(c for c in e.everyone if c.entity_id==f.a.entity_id)
            b=next(c for c in e.everyone if c.entity_id==f.b.entity_id)
            observer=next(c for c in e.everyone if c.entity_id==f.c.entity_id)
            self.assertEqual(e.initiative_value(b).value,f.base-2)
            e.start_round(e.everyone)
            e.start_of_turn(observer);e.end_of_turn(observer)
            self.assertEqual(e.initiative_value(b).value,f.base-2)
            e.start_of_turn(b);e.end_of_turn(b)
            self.assertEqual(e.initiative_value(b).value,f.base)
            CODEC.dump_engine(e)

    def test_original_effect_and_plan_independent_tamper_and_completed_replay(self):
        f=self.fixture();f.use();row=f.row()
        before=CODEC.dump_engine(f.e)
        with self.assertRaises(ValueError):
            FX.run_effects(f.e,f.a,f.b,[row['effect']],{'hit':True},D.SOURCE,_resume_receipt=row['receipt'])
        self.assertEqual(CODEC.dump_engine(f.e),before)
        f.e.gm.snapshot('original')
        before=CODEC.dump_engine(f.e)
        snapshot_row=next(iter(f.e.gm.snapshots['original']['engine']['_effect_dispatch_receipts'].values()))
        def corrupt(row,mode):
            if mode=='delta':
                row['effect']['delta']+=2
                row['fingerprint']=ROOT_RESOLUTION.fingerprint(row['effect'])
            elif mode=='source':row['source_id']='C2CSV/input/db/feats.csv:R90:main'
            else:
                plan=row[D.KEY]['plan']
                if mode=='sign':plan['adjustment']='decrease'
                elif mode=='target':plan['target_id']=f.c.entity_id
                elif mode=='clock':plan['target_turn']+=1
                row[D.KEY]['integrity']=D._digest(plan)
        def saved(row):
            # Preserve native graph aliases while undoing test-only mutations.
            return (deepcopy(row[D.KEY]['plan']),row[D.KEY]['integrity'],
                    row['effect']['delta'],row['fingerprint'],row['source_id'])
        def undo(row,old):
            plan,integrity,delta,fingerprint,source=old
            row[D.KEY]['plan'].clear();row[D.KEY]['plan'].update(plan)
            row[D.KEY]['integrity']=integrity
            row['effect']['delta']=delta;row['fingerprint']=fingerprint;row['source_id']=source
        for mode in ('target','sign','delta','clock','source'):
            old=saved(snapshot_row);corrupt(snapshot_row,mode)
            with self.assertRaises(ValueError):f.e.gm.restore('original')
            self.assertEqual(CODEC.dump_engine(f.e),before)
            undo(snapshot_row,old)
            old=saved(row);corrupt(row,mode)
            encoder=CODEC._Encoder(f.e);bad=deepcopy(before)
            bad['root']=encoder.value(f.e);bad['nodes']=encoder.nodes
            undo(row,old)
            with self.assertRaises(ValueError):
                CODEC.load_engine(Rules(str(self.r.root),ruleset='core'),bad)
            self.assertEqual(CODEC.dump_engine(f.e),before)

if __name__=='__main__':unittest.main()
