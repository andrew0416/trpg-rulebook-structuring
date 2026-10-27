"""Printed Blessing range creates one source-owned shared team pool natively."""
from copy import copy
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_team_blessings as FIX
import blessing_effects as B
import weapon_actions as WEAPONS
import body_state as BODY
from grid import Grid

class NativeBlessingRangeTests(unittest.TestCase):
    setUpClass=classmethod(FIX.TeamBlessingTests.setUpClass.__func__)
    known=FIX.TeamBlessingTests.known
    begin=FIX.TeamBlessingTests.begin
    add=FIX.TeamBlessingTests.add
    snap=FIX.TeamBlessingTests.snap
    valid=FIX.TeamBlessingTests.valid
    restored=FIX.TeamBlessingTests.restored

    def setUp(self):
        FIX.TeamBlessingTests.setUp(self)
        self.e.grid=Grid(16,16)
        for actor,pos in ((self.a,(12,12)),(self.p,(1,1)),(self.other,(14,14))):
            self.e.gm.set_position(actor,pos,reason='observed Blessing field positions')
            BODY.observe(self.e,actor,[(0,0)],reason='actual one-cell Blessing participant')
        for y in range(16):
            self.e.gm.set_terrain((7,y),'blocking',reason='wall does not divide an allied Blessing pool')

    def test_all_eight_printed_blessings_create_one_pool_and_pay_once_on_map(self):
        names=('드래곤옐','순풍','오로라베일','흰안개','주술','신비의부적','빛의장막','리플렉터')
        for index,name in enumerate(names):
            with self.subTest(move=name):
                if index:self.setUp()
                mid='move/'+name
                self.known(self.p,name)
                if name=='오로라베일':self.e.gm.set_weather('hail',rounds=None,reason='printed Aurora Veil creation weather')
                self.begin(self.p)
                self.assertEqual(self.e.targets_in_range(self.p,self.r.move(mid),self.e.everyone,self.p),[self.p])
                self.e.use_move_on(self.p,self.p,mid,self.e.everyone)
                rows=[(owner,row) for owner in self.e.gm.everyone for row in B.live(owner)]
                self.assertEqual(len(rows),1)
                owner,row=rows[0]
                self.assertIs(owner,self.p)
                self.assertEqual((row['source'],self.p.budget['standard'],self.p.move_uses[mid]),(mid,0,1))
                self.assertEqual([r['id'] for _,r in B.beneficiaries(self.e,self.a)],[row['id']])
                self.assertEqual([r['id'] for _,r in B.beneficiaries(self.e,self.p)],[row['id']])
                self.assertEqual(B.beneficiaries(self.e,self.other),[])
                self.assertFalse(self.a.blessings);self.assertFalse(self.other.blessings)
                completed=[r for r in self.e._move_completions.values() if r['actor'] is self.p and r['move_id']==mid]
                self.assertEqual(len(completed),1);self.assertEqual(completed[0]['targets'],[self.p])
                self.assertEqual(completed[0]['phase'],'complete')
                self.valid()

    def test_lucky_chant_rejects_foreign_caster_and_keeps_team_pool_after_recall(self):
        self.known(self.p,'주술');B.definition(self.r,'move/주술');self.begin(self.p)
        before=self.snap();rng=self.e.rng.getstate()
        with self.assertRaises(ValueError):
            self.e.use_move_on(copy(self.p),self.other,'move/주술',self.e.everyone)
        self.assertEqual(self.snap(),before);self.assertEqual(self.e.rng.getstate(),rng)
        self.e.use_move_on(self.p,self.other,'move/주술',self.e.everyone)
        row=B.live(self.p)[0];identity=row['id']
        self.assertEqual((self.p.budget['standard'],self.p.move_uses['move/주술'],B.remaining(row)),(0,1,3))
        complete=next(r for r in self.e._move_completions.values() if r['move_id']=='move/주술')
        self.assertEqual(complete['targets'],[self.p])
        self.e.end_of_turn(self.p);self.e.gm.recall(self.p,reason='actual Blessing creator recall')
        self.assertFalse(self.p.on_field)
        self.assertEqual([r['id'] for _,r in B.beneficiaries(self.e,self.a)],[identity])
        self.assertEqual(B.remaining(B.live(self.p)[0]),3)
        self.assertEqual(B.beneficiaries(self.e,self.other),[])
        self.valid()

    def test_numeric_range_with_blessing_keyword_stays_numeric_and_self_field_stay_distinct(self):
        self.begin(self.p)
        self.assertTrue(WEAPONS.is_blessing({'raw':'Blessing'}))
        self.assertFalse(WEAPONS.is_blessing({'raw':'6, 대상 1, 축복','origin':6,'targets':1}))
        self.assertFalse(WEAPONS.is_field({'raw':'축복'}))
        self.assertFalse(WEAPONS.is_self_only({'raw':'축복'}))
        self.assertEqual(self.e.targets_in_range(self.p,self.r.move('move/칼춤'),self.e.everyone,self.other),[self.p])
        self.assertEqual(self.e.targets_in_range(self.p,self.r.move('move/흑안개'),self.e.everyone,self.other),[self.p])
        numeric=dict(self.r.move('move/전기자석파'),keywords=['축복'])
        self.assertEqual(self.e.targets_in_range(self.p,numeric,self.e.everyone,self.p),[])
        self.assertEqual(self.e.targets_in_range(self.p,numeric,self.e.everyone,self.other),[])
        self.e.gm.set_position(self.other,(2,1),reason='actual nearby numeric-range opponent')
        self.assertEqual(self.e.targets_in_range(self.p,numeric,self.e.everyone,self.other),[self.other])
        self.assertEqual(self.p.budget['standard'],1)
