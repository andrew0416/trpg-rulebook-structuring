"""C09-030/103: sourced drink state and real GM/durable continuation."""
from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_item_stock as _fixture_test_category2_item_stock
import items as I

class DrinkStateTests(unittest.TestCase):
    setUpClass=classmethod(_fixture_test_category2_item_stock.ItemStockTests.setUpClass.__func__)
    setUp=_fixture_test_category2_item_stock.ItemStockTests.setUp
    add=_fixture_test_category2_item_stock.ItemStockTests.add
    restored=_fixture_test_category2_item_stock.ItemStockTests.restored
    held=_fixture_test_category2_item_stock.ItemStockTests.held
    snap=_fixture_test_category2_item_stock.ItemStockTests.snap

    def drink(self,e,user,target,name='맛있는물',**options):
        return e.use_item(user,name,target,duration_minutes=1,duration_reason='GM observed whole drink intake',**options)

    def test_five_source_rows_keep_effect_price_and_receipt_in_both_storage_forms(self):
        # Independent expected table: input/ch09-equipment.md:224-231.
        for name,amount,price in [('맛있는물',20,75),('나무열매쥬스',30,None),('미네랄사이다',30,125),('후르츠밀크',50,250),('튼튼밀크',80,500)]:
            for kind in ('a','p'):
                for physical in (False,True):
                    with self.subTest(name=name,kind=kind,physical=physical):
                        self.setUp();target=getattr(self,kind);target.hp=1
                        effects,header=self.r.item_effects(name)
                        self.assertEqual(header.get('price'),price)
                        target.spec['items']={name:2}
                        if physical:self.held(target,name,'drink')
                        result=self.drink(self.e,target,target,name,held_selection='drink' if physical else None)
                        self.assertEqual(result['healed'],min(amount,target.max_hp-1))
                        self.assertEqual(target.spec['items'][name],2 if physical else 1)
                        record=target.spec['drink_history'][-1]
                        self.assertEqual((record['item'],record['source'],record['at']),('item/'+name,'ch09-equipment/모험-도구/음료수',60))
                        self.assertEqual(record['item_stock']['item_id'],'item/'+name)
                        loaded=self.restored();c=next(c for c in loaded.gm.everyone if c.entity_id==target.entity_id)
                        self.assertEqual((c.hp,c.spec['drink_history']),(target.hp,target.spec['drink_history']))

    def test_recipient_hour_limit_continues_after_both_restore_paths(self):
        for target_name in ('a','p'):
            self.setUp();target=getattr(self,target_name);target.hp=1
            self.a.spec['items']={'맛있는물':3}
            self.drink(self.e,self.a,target)
            snapshot=self.e.gm.snapshot();loaded=self.restored()
            for e in (self.e,loaded):
                user=next(c for c in e.gm.everyone if c.entity_id==self.a.entity_id)
                recipient=next(c for c in e.gm.everyone if c.entity_id==target.entity_id)
                e.advance_time(3480,[user,recipient])
                before=deepcopy((e.elapsed_seconds,user.spec['items'],recipient.spec['drink_history'],recipient.hp))
                with self.assertRaisesRegex(ValueError,'limit'):self.drink(e,user,recipient)
                self.assertEqual(before,(e.elapsed_seconds,user.spec['items'],recipient.spec['drink_history'],recipient.hp))
                e.advance_time(60,[user,recipient]);self.drink(e,user,recipient)
                self.assertEqual((e.elapsed_seconds,len(recipient.spec['drink_history']),user.spec['items']['맛있는물']),(3660,2,1))
            self.e.gm.restore(snapshot)
            self.assertEqual((self.e.elapsed_seconds,self.a.spec['items']['맛있는물'],len(target.spec['drink_history'])),(60,2,1))
            with self.assertRaisesRegex(ValueError,'limit'):self.drink(self.e,self.a,target)
