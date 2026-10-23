"""C09-079: the real item catalog and its native consumption exceptions."""
from copy import deepcopy
from unittest.mock import patch
import unittest
import test_category2_dream_mist as MIST
import common_checks as C
import equipment_item_contracts as CONTRACTS
import items as ITEMS


class Tests(unittest.TestCase):
    setUpClass=classmethod(MIST.Tests.setUpClass.__func__)
    setUp=MIST.Tests.setUp
    add=MIST.Tests.add
    pokemon=MIST.Tests.pokemon
    restored=MIST.Tests.restored
    begin=MIST.Tests.begin
    held=MIST.Tests.held
    prepare=MIST.Tests.prepare
    use=MIST.Tests.use

    def snapshot(self):
        return deepcopy((self.e.elapsed_seconds,self.e.rng.getstate(),
            [vars(x) for x in self.e.gm.everyone],
            getattr(self.e,'_physical_objects',{}),self.e.log_lines),{id(self.r):self.r})

    def test_actual_catalog_preserves_group_and_individual_lifetimes(self):
        singles=('item/마름쇠','item/독-마름쇠','item/꿈안개-1',
                 'item/오물탄-1','item/오물탄-격노','item/오물탄-혼란',
                 'item/오물탄-화상','item/오물탄-독','item/오물탄-마비',
                 'item/오물탄-잠듦','item/연막탄-1')
        for uid,policy in [(x,'single_use') for x in singles]+[
                ('item/마법피리-1','daily_reusable'),('item/순결의부적-1','use_mode')]:
            with self.subTest(item=uid):
                effects,header=self.r.item_effects(uid)
                self.assertIsNotNone(effects)
                self.assertEqual(header['id'],uid)
                self.assertEqual(header['battle_tool'],{
                    'kind':'battle_tool','clause_id':'C09-079',
                    'source_id':CONTRACTS.BATTLE_TOOL_SOURCE,
                    'normally_consumable':True,'stock_policy':policy})
                self.assertEqual(header['use']=='consumable',policy=='single_use')
        self.assertNotIn('battle_tool',self.r.item_effects('item/상처약')[1])
        # A caller's edited view cannot rewrite the source or later reads.
        header['battle_tool']['stock_policy']='single_use'
        self.assertEqual(self.r.item_effects('item/순결의부적-1')[1]['battle_tool']['stock_policy'],'use_mode')

    def test_native_supported_tool_still_pays_standard_and_one_quantity_on_miss(self):
        self.prepare()
        header=self.r.item_effects('item/꿈안개-1')[1]
        self.assertEqual(header['battle_tool']['stock_policy'],'single_use')
        result=self.use(1,accepted=False)
        self.assertFalse(result['hit'])
        self.assertEqual(self.a.spec['items']['item/꿈안개-1'],3)
        self.assertEqual(self.a.budget['standard'],0)
        self.assertNotIn('잠듦',self.t.conditions)

    def test_native_supported_tool_consumes_exact_physical_body_and_restores(self):
        self.prepare(self.p)
        self.held(self.p,'item/꿈안개-1','mist-catalog')
        result=self.use(actor=self.p,held_selection='mist-catalog')
        self.assertTrue(result['status_applied'])
        self.assertEqual(result['payment']['instance_id'],'mist-catalog')
        self.assertIn('consumed',self.e._physical_objects['mist-catalog'])
        self.assertEqual(self.p.spec['items']['item/꿈안개-1'],4)
        e=self.restored()
        self.assertIn('consumed',e._physical_objects['mist-catalog'])
        self.e.gm.snapshot('consumed-battle-tool')
        self.e.gm.restore('consumed-battle-tool')
        self.assertIn('consumed',self.e._physical_objects['mist-catalog'])

    def test_category_never_spends_inert_or_exception_tools_as_immediate_items(self):
        self.prepare()
        for uid in ('item/오물탄-화상',
                    'item/연막탄-1','item/순결의부적-1'):
            with self.subTest(item=uid):
                self.a.spec['items'][uid]=1
                before=self.snapshot()
                result=self.e.use_item(self.a,uid,self.t)
                self.assertIsInstance(result,C.PendingDecision)
                self.assertEqual(result.basis['catalog']['stock_policy'],
                    self.r.item_effects(uid)[1]['battle_tool']['stock_policy'])
                self.assertEqual(self.snapshot(),before)
        # A source adapter cannot invent the reusable tool's manufacture facts.
        self.a.spec['items']['item/마법피리-1']=1
        before=self.snapshot()
        result=self.e.use_item(self.a,'item/마법피리-1')
        self.assertIsInstance(result,C.PendingDecision)
        self.assertEqual(self.snapshot(),before)
        # The same observation boundary preserves an actual held reusable body.
        self.held(self.p,'item/마법피리-1','flute-catalog')
        before=self.snapshot()
        result=self.e.use_item(self.p,'item/마법피리-1',held_selection='flute-catalog')
        self.assertIsInstance(result,C.PendingDecision)
        self.assertEqual(self.snapshot(),before)
        self.assertNotIn('consumed',self.e._physical_objects['flute-catalog'])

    def test_category_source_selection_is_checked_before_catalog_or_payment(self):
        self.prepare()
        original=self.r._selected_rule
        def select(uid,*args,**kwargs):
            return 'custom/other-category' if uid==CONTRACTS.BATTLE_TOOL_SOURCE else original(uid,*args,**kwargs)
        before=self.snapshot()
        with patch.object(self.r,'_selected_rule',side_effect=select):
            with self.assertRaisesRegex(ValueError,'category source changed'):
                self.e.use_item(self.a,'item/꿈안개-1',self.t,fixed_accuracy=20)
        self.assertEqual(self.snapshot(),before)


if __name__=='__main__':unittest.main()
