"""C11-035: explicitly adopted dollar prices settle native point purchases."""
from copy import deepcopy
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
import campaign_rewards as REWARDS
import state_codec as CODEC
import test_category3_batch15_pokemon as fixtures


class CurrencyDenominationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')

    def setUp(self):
        self.e=Engine(self.r,35)
        self.a=Combatant(self.r,{'id':'trainer/currency-owner','name':'Currency owner','kind':'trainer',
            'level':10,'stats':dict(hp=30,atk=30,**{'def':30},spa=30,spd=30,spe=10),
            'types':[],'abilities':[],'moves':['struggle'],'money':6000,'items':{}})
        self.e.everyone=self.e.gm.everyone=[self.a]
        self.e.campaign_reward(self.a,'observe_ball_shop',event_id='currency-shop',merchant='Mart',
            stock={'item/몬스터볼-2':100},reason='GM observes actual basic-ball stock at source point price')

    def act(self,activity,**options):return self.e.campaign_reward(self.a,activity,**options)
    def buy(self,event_id='sale',**options):
        args=dict(event_id=event_id,merchant='Mart',items={'item/몬스터볼-2':1,'item/초코바':1},
            reason='GM explicitly agrees to the source dollar quotation',
            price_currency='dollar',unit_prices={'item/몬스터볼-2':5,'item/초코바':'1.5'})
        args.update(options);return self.act('purchase',**args)
    def snapshot(self):return deepcopy(CODEC.dump_engine(self.e))
    def configure(self,**options):return fixtures.Tests.config(self,**options)

    def test_actual_ball_and_candy_dollar_sale_pays_points_and_delivers_owned_stock(self):
        row=self.buy()
        self.assertEqual(row['unit_prices'],{'item/몬스터볼-2':250,'초코바':75})
        self.assertEqual((row['price'],row['cash_spent'],row['credit_spent']),(325,325,0))
        self.assertEqual(self.a.spec['money'],5675)
        self.assertEqual(self.a.spec['items'],{'item/몬스터볼-2':1,'초코바':1})
        self.assertEqual(row['quotation'],{'source':REWARDS.CURRENCY_SOURCE,'unit':'dollar',
            'points_per_unit':50,'unit_prices':{'item/몬스터볼-2':'5','초코바':'3/2'},
            'total':'13/2','settlement_unit':'point','credit_unit':'point'})
        self.assertEqual(REWARDS.events(self.e)['sale'],row)
        # The native selected inventory owner sees the actual purchased item.
        import item_stock
        self.assertEqual(item_stock.prepare(self.e,self.a,'item/몬스터볼-2')['key'],'item/몬스터볼-2')
        row['quotation']['unit_prices']['초코바']='999'
        self.assertEqual(REWARDS.events(self.e)['sale']['quotation']['unit_prices']['초코바'],'3/2')

    def test_unselected_catalogue_and_agreed_point_prices_keep_default_contract(self):
        self.buy('dollars')
        row=self.buy('catalogue',price_currency='point',unit_prices=None)
        self.assertEqual((row['price'],row['cash_spent']),(325,325));self.assertNotIn('quotation',row)
        row=self.act('purchase',event_id='agreed-points',merchant='Mart',items={'item/초코바':2},
            reason='GM agreed point price independent of dollar example',unit_prices={'item/초코바':11})
        self.assertEqual(row['price'],22);self.assertNotIn('quotation',row)
        self.assertEqual(self.a.spec['money'],5328)
        self.assertFalse(hasattr(self.e,'_campaign_reward_policy'))

    def test_exact_native_values_and_counts_do_not_use_decimal_context_or_rounding(self):
        for i,value in enumerate((Decimal('1.5'),Fraction(3,2),1.5,'1.5','3/2')):
            with self.subTest(value=value),localcontext() as context:
                context.prec=1
                row=self.buy(str(i),items={'item/초코바':3},unit_prices={'item/초코바':value})
                self.assertEqual(row['price'],225);self.assertEqual(row['quotation']['total'],'9/2')
        for i,value in enumerate(('0.1',0.1,Decimal('0.1'),Fraction(1,10),0)):
            row=self.buy('small'+str(i),items={'item/초코바':2},unit_prices={'item/초코바':value})
            self.assertEqual(row['price'],0 if value==0 else 10)
        self.assertEqual(self.a.spec['money'],6000-1125-40)

    def test_invalid_or_unadopted_denominations_refuse_before_point_payment(self):
        invalid=(True,-1,'-0.02','0.01',Fraction(1,3),float('nan'),float('inf'),
            Decimal('NaN'),Decimal('Infinity'),0.1+0.2,'not-a-price',None)
        before=self.snapshot()
        for value in invalid:
            with self.subTest(value=repr(value)),self.assertRaises(ValueError):
                self.buy(items={'item/초코바':1},unit_prices={'item/초코바':value})
            self.assertEqual(before,self.snapshot())
        for options in ({'price_currency':'yen'},{'price_currency':None},{'unit_prices':None},
                {'unit_prices':{'item/몬스터볼-2':5}},{'credit':Fraction(1,2)},
                {'price_currency':'point','unit_prices':{'item/몬스터볼-2':5,'item/초코바':1.5}}):
            with self.subTest(options=options),self.assertRaises(ValueError):self.buy(**options)
            self.assertEqual(before,self.snapshot())
        self.assertNotIn('sale',REWARDS.events(self.e))

    def test_credit_and_promotion_consume_canonical_point_receipt_after_restore(self):
        self.configure();self.a.spec['store_credit']={'Mart':500}
        row=self.buy(items={'item/몬스터볼-2':4},unit_prices={'item/몬스터볼-2':5},credit=250)
        self.assertEqual((row['price'],row['cash_spent'],row['credit_spent']),(1000,750,250))
        self.assertEqual((self.a.spec['money'],self.a.spec['store_credit']['Mart']),(5250,250))
        self.assertEqual(self.a.spec['items'],{'item/몬스터볼-2':4})
        self.e=Engine.import_state(self.r,json.loads(json.dumps(self.e.export_state())))
        self.a=self.e.everyone[0]
        self.assertEqual(REWARDS.events(self.e)['sale']['quotation'],row['quotation'])
        self.assertEqual(self.act('promotion',purchase_id='sale'),{'punches':7,'credit':0})
        self.assertEqual(self.a.spec['promotion_spend_remainders']['Mart'],50)
        row=self.buy('next',items={'item/몬스터볼-2':1},unit_prices={'item/몬스터볼-2':5})
        self.assertEqual(self.act('promotion',purchase_id='next'),{'punches':0,'credit':500})
        self.assertEqual((self.a.spec['money'],self.a.spec['store_credit']['Mart']),(5000,750))
        before=self.snapshot()
        for activity,options in (('purchase',dict(event_id='sale',merchant='Mart',
                items={'item/초코바':1},reason='duplicate actual sale',unit_prices={'item/초코바':1.5},price_currency='dollar')),
                ('promotion',{'purchase_id':'sale'})):
            with self.assertRaises(ValueError):self.act(activity,**options)
            self.assertEqual(before,self.snapshot())

    def test_source_authority_and_insufficient_money_or_credit_preserve_purchase(self):
        before=self.snapshot()
        for options in ({'credit':1},{'credit':326},{'items':{'item/몬스터볼-2':25},
                'unit_prices':{'item/몬스터볼-2':5}}):
            with self.subTest(options=options),self.assertRaises(ValueError):self.buy(**options)
            self.assertEqual(before,self.snapshot())
        original=self.r._selected_rule
        with patch.object(self.r,'_selected_rule',side_effect=lambda uid: 'unselected/other' if uid==REWARDS.SOURCE else original(uid)):
            with self.assertRaises(ValueError):self.buy()
        self.assertEqual(before,self.snapshot())


if __name__=='__main__':unittest.main()
