"""Menace consumers preserve the separate Roughneck and Flinch timer owners."""
from copy import deepcopy
from pathlib import Path
import sys, unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_nonmove_hit_consumers as BASE
import test_book_roughneck_full as RF
import roughneck as R, combat_timing as CLOCK, combat_modifiers as MOD
import condition_instances as CI, action_points as AP, common_checks as C
import state_codec as CODEC


class NonMoveActionsRepairTests(unittest.TestCase):
    setUpClass=classmethod(BASE.NonMoveHitConsumerTests.setUpClass.__func__)
    menace=BASE.NonMoveHitConsumerTests.menace
    dirty=BASE.NonMoveHitConsumerTests.dirty

    def roughneck_fixture(self,*features):
        f=RF.RoughneckTests();f.rules=self.rules;f.setUp();self.addCleanup(f.doCleanups)
        f.roughneck(*features);f.p=f.foe()
        return f

    def child(self,f):
        rows=[r for r in CLOCK.records(f.p) if 'flinch_parent_id' in r]
        self.assertEqual(len(rows),1)
        return rows[0]

    def test_menace_flinch_child_cure_gm_json_and_independent_full_round(self):
        f=self.menace();self.assertFalse(self.dirty(f,won=False))
        parents=CI.records(f.p,'풀죽음');self.assertEqual(len(parents),1)
        parent=parents[0];child=self.child(f)
        self.assertEqual((parent['source'],child['source'],child['flinch_parent_id']),
                         (R.MENACE,R.MENACE,parent['id']))
        self.assertEqual(tuple(child['count_deadline']),(f.e.round_no+1,25))
        self.assertNotIn('effect_receipt',child)
        f.valid();f.restore('t','p','b')
        f.e.cure_status(f.p,'풀죽음')
        self.assertFalse(CI.records(f.p,'풀죽음'));self.assertIn('취약',f.p.conditions)
        archived=deepcopy(f.p.spec['effect_instance_history'])
        f.e.gm.snapshot('menace-cured-parent')
        f.e.cure_status(f.p,'취약');f.e.gm.restore('menace-cured-parent')
        self.assertEqual(f.p.spec['effect_instance_history'],archived)
        f.restore('t','p','b');self.assertEqual(self.child(f)['flinch_parent_id'],parent['id'])
        f.e.end_of_turn(f.b);f.e.end_round();f.e.start_round(f.e.everyone)
        f.e.start_of_turn(f.t,initiative_count=30)
        self.assertFalse(any('incoming_status_range' in r for r in CLOCK.records(f.p)))
        self.assertIn('취약',f.p.conditions);self.child(f);f.valid()
        f.e.end_of_turn(f.t);f.e.start_of_turn(f.b,initiative_count=25)
        self.assertNotIn('취약',f.p.conditions)
        self.assertFalse(any('flinch_parent_id' in r for r in CLOCK.records(f.p)));f.valid()

    def test_menace_move_new_range_and_existing_plus_four_are_restorable(self):
        for move,face,flinched in (('move/몸통박치기',16,False),('move/몸통박치기',17,True),
                                  ('move/박치기',10,False),('move/박치기',11,True)):
            with self.subTest(move=move,face=face):
                f=self.menace();f.use(f.b,f.p,move,face=face)
                self.assertEqual('풀죽음' in f.p.conditions,flinched)
                self.assertEqual(len(CI.records(f.p,'풀죽음')),int(flinched))
                f.valid();f.restore('t','p','b')
                self.assertEqual('풀죽음' in f.p.conditions,flinched)
                if flinched:self.child(f)

    def test_pending_menace_overlap_restores_and_pays_once_without_replaying_flinch(self):
        f=self.roughneck_fixture(R.MENACE);f.second_roughneck(R.MENACE)
        f.combat(f.t);f.answer('roughneck_menace',True);f.terrorize(f.p,won=False)
        self.assertFalse(CI.records(f.p,'풀죽음'))
        f.e.end_of_turn(f.t);f.e.start_of_turn(f.b,initiative_count=25)
        ap=AP.available(f.b)
        pending=f.e.manipulate(f.b,f.p,'terrorize',defender_skill='집중',fixed_accuracy=20,
            challenger_options={'fixed':[1]*6},defender_options={'fixed':[6]*6})
        self.assertIsInstance(pending,C.PendingDecision)
        binding=deepcopy(pending.basis['binding']);event_id=binding['new_origin']['event_id']
        parent_id=CI.records(f.p,'풀죽음')[0]['id'];self.child(f)
        self.assertEqual((f.b.budget['standard'],f.b.budget['swift'],AP.available(f.b)),(0,1,ap))
        f.valid();f.e.gm.snapshot('pending-menace-overlap')
        f.e.cure_status(f.p,'풀죽음');f.e.gm.restore('pending-menace-overlap')
        f.restore('t','p','b')
        f.answer('roughneck_overlap',{'binding':binding,'operator':'add','reason':'GM resolves this exact pair additively'})
        rng=f.e.rng.getstate()
        for _ in range(2):R.resolve_maneuver(f.e,f.b,event_id)
        self.assertEqual(f.e.rng.getstate(),rng)
        self.assertEqual((f.b.budget['standard'],f.b.budget['swift'],AP.available(f.b)),(0,0,ap))
        self.assertEqual([r['id'] for r in CI.records(f.p,'풀죽음')],[parent_id])
        self.assertEqual(self.child(f)['flinch_parent_id'],parent_id)
        self.assertEqual(len([r for r in CLOCK.records(f.p) if 'incoming_status_range' in r]),2)
        self.assertEqual(MOD.incoming_status_threshold(f.p,'풀죽음',15),7)
        f.valid();f.restore('t','p','b')

    def test_roughneck_metadata_and_flinch_parent_cannot_substitute_for_each_other(self):
        for source in (R.MENACE,R.DISPLAY):
            for damage in ('missing_metadata','forged_child_marker','borrowed_child_marker',
                           'forged_parent','extra_receipt','extra_origin'):
                with self.subTest(source=source,damage=damage):
                    if source==R.MENACE:
                        f=self.menace();self.dirty(f)
                    else:
                        f=self.roughneck_fixture(R.DISPLAY);f.combat(f.t);f.display()
                        f.use(f.t,f.p,'move/박치기',face=20)
                    f.valid();child=self.child(f)
                    contribution=next(r for r in CLOCK.records(f.p)
                                      if r['source']==source and 'effect_receipt' in r)
                    producer=f.e._effect_dispatch_receipts[contribution['effect_receipt']]
                    if damage in ('missing_metadata','forged_child_marker','borrowed_child_marker'):
                        producer.pop('roughneck_timed')
                        if damage=='forged_child_marker':contribution['flinch_parent_id']='forged-parent'
                        elif damage=='borrowed_child_marker':contribution['flinch_parent_id']=child['flinch_parent_id']
                    elif damage=='forged_parent':child['flinch_parent_id']='forged-parent'
                    elif damage=='extra_receipt':child['effect_receipt']=contribution['effect_receipt']
                    else:child['roughneck_origin']=deepcopy(contribution['roughneck_origin'])
                    report=f.e.validate_state();self.assertFalse(report['valid'],report)
                    expected='grapple_state' if damage=='missing_metadata' else 'effect_instance'
                    self.assertTrue(any(row['code']==expected for row in report['issues']),report['issues'])
                    with self.assertRaises(CODEC.StateCodecError):f.e.export_state()


if __name__=='__main__':unittest.main()
