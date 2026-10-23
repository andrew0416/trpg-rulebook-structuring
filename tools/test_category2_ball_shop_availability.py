"""C09-004: real shared merchant stock is consumed by native purchases."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
import ball_shop_availability as BALL
import campaign_rewards as REWARDS
import common_checks as CHECKS
import item_stock
import test_category3_batch15_pokemon as fixtures


class BallShopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')

    def setUp(self):
        self.e=Engine(self.r,904)
        def actor(uid):return Combatant(self.r,{'id':uid,'name':uid,'kind':'trainer',
            'level':10,'stats':dict(hp=30,atk=30,**{'def':30},spa=30,spd=30,spe=10),
            'types':[],'abilities':[],'moves':['struggle'],'money':100000,'items':{}})
        self.a=actor('trainer/buyer');self.b=actor('trainer/other-buyer')
        self.e.everyone=self.e.gm.everyone=[self.a,self.b]

    def act(self,activity,**options):return self.e.campaign_reward(self.a,activity,**options)
    def observe(self,event_id='shop',**options):
        args=dict(event_id=event_id,merchant='Mart',stock={'item/몬스터볼-2':4},
            reason='GM observes this named shop stock and confirms source prices')
        args.update(options);return self.act('observe_ball_shop',**args)
    def buy(self,event_id='sale',**options):
        args=dict(event_id=event_id,merchant='Mart',items={'item/몬스터볼-2':1},
            reason='actual purchase at the observed merchant')
        args.update(options);return self.act('purchase',**args)
    def snapshot(self):
        return deepcopy((self.a.spec,self.b.spec,REWARDS.events(self.e),self.e.rng.getstate(),
            self.e.elapsed_seconds,self.e.log_lines,self.e.gm_prompts))
    def stock(self,observation='shop'):return REWARDS.events(self.e)[observation]['stock']

    def test_all_twenty_four_source_prices_feed_default_mixed_purchase_and_native_owned_stock(self):
        specials=('사파리볼','레벨볼','루어볼','문볼','프렌드볼','러브러브볼','헤비볼',
            '스피드볼','컴퍼티션볼','프리미어볼','리피트볼','타이머볼','네스트볼','네트볼',
            '다이브볼','럭셔리볼','힐볼','퀵볼','다크볼','프레셔스볼','파크볼')
        expected={'item/몬스터볼-2':250,'item/슈퍼볼':400,'item/하이퍼볼':800,
                  **{'item/'+name:800 for name in specials}}
        self.assertEqual(len(expected),24)
        row=self.observe(stock=dict.fromkeys(expected,1))
        names={uid:REWARDS.item(self.e,uid)[0] for uid in expected}
        self.assertEqual(row['unit_prices'],{names[uid]:price for uid,price in expected.items()})
        self.assertEqual(self.a.spec['items'],{});self.assertNotIn('sale',REWARDS.events(self.e))
        purchased=self.buy(items={**dict.fromkeys(expected,1),'item/초코바':1})
        self.assertEqual(purchased['price'],18325)
        self.assertEqual(self.a.spec['money'],81675)
        self.assertEqual(purchased['ball_shop']['observation_id'],'shop')
        self.assertEqual(set(self.stock().values()),{0})
        for uid,price in expected.items():
            with self.subTest(ball=uid):
                self.assertEqual(purchased['unit_prices'][names[uid]],price)
                stock=item_stock.prepare(self.e,self.a,uid)
                self.assertEqual(stock['count'],1)
        actual=item_stock.prepare(self.e,self.a,'item/네트볼')
        item_stock.debit(self.e,self.a,actual)
        self.assertEqual(self.a.spec['items'][names['item/네트볼']],0)
        # Another source's ball devices keep their existing general purchase contract.
        device=self.buy('case',merchant='Unobserved device shop',items={'item/탄력케이스':1})
        self.assertEqual(device['price'],800);self.assertNotIn('ball_shop',device)

    def test_omitted_observation_id_cannot_bypass_unknown_supply_and_explicit_zero_or_short_stock(self):
        before=self.snapshot()
        self.assertIsInstance(self.buy(),CHECKS.PendingDecision)
        self.assertEqual(self.snapshot(),before)
        self.observe(stock={'item/몬스터볼-2':0,'item/슈퍼볼':1})
        before=self.snapshot()
        for options in ({},{'items':{'item/슈퍼볼':2}},
                {'ball_shop_id':'shop','merchant':'Other Mart'}):
            with self.subTest(options=options),self.assertRaises(ValueError):self.buy(**options)
            self.assertEqual(self.snapshot(),before)
        for options in ({'items':{'item/네트볼':1}},
                {'merchant':'Other Mart'},{'ball_shop_id':'not-yet-observed'}):
            with self.subTest(options=options):self.assertIsInstance(self.buy(**options),CHECKS.PendingDecision)
            self.assertEqual(self.snapshot(),before)
        self.assertNotIn('sale',REWARDS.events(self.e))

    def test_latest_observation_and_all_buyers_share_one_merchant_remainder(self):
        old=self.observe();old['stock']['item/몬스터볼-2']=999
        self.observe('new-stock',stock={'item/몬스터볼-2':2})
        self.observe('other-store',merchant='Other Mart',stock={'item/몬스터볼-2':7})
        before=self.snapshot()
        with self.assertRaises(ValueError):self.buy(ball_shop_id='shop')
        self.assertEqual(self.snapshot(),before)
        first=self.buy();self.assertEqual(first['ball_shop']['stock_after'],{'item/몬스터볼-2':1})
        self.e.campaign_reward(self.b,'purchase',event_id='second',merchant='Mart',
            items={'item/몬스터볼-2':1},reason='another actual buyer shares this observed shop')
        self.assertEqual(self.stock('new-stock'),{'item/몬스터볼-2':0})
        self.assertEqual(self.stock('other-store'),{'item/몬스터볼-2':7})
        before=self.snapshot()
        for event in ('sale','third'):
            with self.assertRaises(ValueError):self.buy(event)
            self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.b.spec['items'],{'item/몬스터볼-2':1})

    def test_observed_price_and_explicit_point_or_dollar_agreements_keep_credit_and_promotion_owner(self):
        fixtures.Tests.config(self)
        self.a.spec['store_credit']={'Mart':500}
        self.observe(stock={'item/몬스터볼-2':4},unit_prices={'item/몬스터볼-2':300})
        first=self.buy(credit=100)
        self.assertEqual((first['price'],first['cash_spent'],first['credit_spent']),(300,200,100))
        self.assertEqual(first['ball_shop']['price_basis'],'observed')
        second=self.buy('point-agreement',unit_prices={'item/몬스터볼-2':270})
        third=self.buy('dollar-agreement',price_currency='dollar',unit_prices={'item/몬스터볼-2':'5.5'})
        self.assertEqual((second['price'],third['price']),(270,275))
        self.assertEqual(third['quotation']['unit_prices'],{'item/몬스터볼-2':'11/2'})
        self.assertEqual(third['ball_shop']['observed_unit_prices'],{'item/몬스터볼-2':300})
        self.assertEqual(self.act('promotion',purchase_id='sale'),{'punches':2,'credit':0})
        before=self.snapshot()
        with self.assertRaises(ValueError):self.act('promotion',purchase_id='sale')
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.stock(),{'item/몬스터볼-2':1})
        mixed=self.buy('mixed-machine',items={'item/몬스터볼-2':1,'TM26':1},
            unit_prices={'item/몬스터볼-2':250,'TM26':0})
        self.assertEqual(mixed['items'],{'item/몬스터볼-2':1,'TM26':1})
        self.assertEqual(self.a.spec['items']['TM26'],1)
        self.assertEqual(self.stock(),{'item/몬스터볼-2':0})

    def test_delivery_receipt_and_post_stock_faults_rollback_and_retry_the_same_sale_once(self):
        for boundary in ('delivery','receipt','stock'):
            with self.subTest(boundary=boundary):
                self.setUp();self.observe(stock={'item/몬스터볼-2':2})
                self.a.spec['store_credit']={'Mart':50}
                before=self.snapshot();spec_alias=self.a.spec;stock_alias=self.stock()
                if boundary=='delivery':
                    native=REWARDS.pay
                    def fail(*args,**kwargs):native(*args,**kwargs);raise RuntimeError('after actual delivery')
                    target=patch.object(REWARDS,'pay',side_effect=fail)
                elif boundary=='receipt':
                    native=REWARDS.put
                    def fail(*args,**kwargs):native(*args,**kwargs);raise RuntimeError('after actual receipt')
                    target=patch.object(REWARDS,'put',side_effect=fail)
                else:
                    native=BALL.deepcopy
                    def fail(value):
                        if isinstance(value,dict) and 'ball_shop' in value:
                            self.assertEqual(self.stock(),{'item/몬스터볼-2':2})
                            self.assertEqual(value['ball_shop']['stock_after'],{'item/몬스터볼-2':1})
                            raise RuntimeError('after staged stock and receipt metadata')
                        return native(value)
                    target=patch.object(BALL,'deepcopy',side_effect=fail)
                with target,self.assertRaises(RuntimeError):self.buy(credit=50)
                self.assertEqual(self.snapshot(),before)
                self.assertIs(self.a.spec,spec_alias);self.assertIs(self.stock(),stock_alias)
                row=self.buy(credit=50)
                self.assertEqual((row['price'],row['credit_spent']),(250,50))
                self.assertEqual(self.stock(),{'item/몬스터볼-2':1})
                self.assertEqual(self.a.spec['items'],{'item/몬스터볼-2':1})

    def test_gm_and_cold_json_restore_preserve_stock_receipt_and_reject_duplicate_purchase(self):
        self.observe(stock={'item/몬스터볼-2':3});self.buy()
        self.e.gm.snapshot('remaining-two')
        self.buy('discarded-future');self.e.gm.restore('remaining-two')
        self.assertEqual(self.stock(),{'item/몬스터볼-2':2})
        self.assertNotIn('discarded-future',REWARDS.events(self.e))
        self.e=Engine.import_state(Rules(ROOT,ruleset='core'),json.loads(json.dumps(self.e.export_state())))
        self.a,self.b=self.e.everyone
        before=self.snapshot()
        with self.assertRaises(ValueError):self.buy()
        self.assertEqual(self.snapshot(),before)
        self.buy('after-cold',items={'item/몬스터볼-2':2})
        self.assertEqual(self.stock(),{'item/몬스터볼-2':0})
        self.assertEqual(self.a.spec['items'],{'item/몬스터볼-2':3})

    def test_selected_source_version_and_warm_source_freshness_fail_before_inventory_or_payment(self):
        self.observe();before=self.snapshot()
        native=Path.read_bytes
        def changed(path):return native(path)+(b'changed' if path.name=='ch09-equipment.md' else b'')
        with patch.object(Path,'read_bytes',changed),self.assertRaises(ValueError):self.buy()
        self.assertEqual(self.snapshot(),before)
        original=self.r._selected_rule
        def replace(uid,*args,**kwargs):return REWARDS.SOURCE if uid==BALL.SOURCE else original(uid,*args,**kwargs)
        with patch.object(self.r,'_selected_rule',side_effect=replace),self.assertRaises(ValueError):self.buy()
        self.assertEqual(self.snapshot(),before)
        with patch.dict(self.r.ruleset.unit_versions,{BALL.SOURCE:'unreviewed-version'}),self.assertRaises(ValueError):self.buy()
        self.assertEqual(self.snapshot(),before)

    def test_invalid_observation_and_unsold_master_ball_do_not_create_supply_or_money(self):
        before=self.snapshot()
        invalid=({'stock':{}},{'stock':{'item/초코바':1}},
            {'stock':{'item/몬스터볼-2':True}},{'stock':{'item/몬스터볼-2':-1}},
            {'stock':{'item/몬스터볼-2':1.5}},{'stock':{'몬스터볼':1}},
            {'stock':{'item/마스터볼':1},'unit_prices':{'item/마스터볼':300000}},
            {'unit_prices':{}},{'unit_prices':{'item/몬스터볼-2':True}},
            {'unit_prices':{'item/몬스터볼-2':-1}},{'reason':''})
        for options in invalid:
            with self.subTest(options=options),self.assertRaises(ValueError):self.observe(**options)
            self.assertEqual(self.snapshot(),before)
        self.observe();before=self.snapshot()
        with self.assertRaises(ValueError):self.buy(items={'item/마스터볼':1},unit_prices={'item/마스터볼':300000})
        self.assertEqual(self.snapshot(),before)
        with self.assertRaises(ValueError):self.observe()
        self.assertEqual(self.snapshot(),before)

    def test_failed_money_credit_or_agreement_never_debits_observed_stock_and_nonball_sale_needs_no_supply(self):
        self.observe();before=self.snapshot()
        for options in ({'credit':1},{'unit_prices':{}},{'unit_prices':{'item/몬스터볼-2':-1}},
                {'price_currency':'dollar'},{'items':{'item/몬스터볼-2':401}},
                {'items':{'item/몬스터볼-2':0}}):
            with self.subTest(options=options),self.assertRaises(ValueError):self.buy(**options)
            self.assertEqual(self.snapshot(),before)
        self.a.spec['money']=0;before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'insufficient actual money'):self.buy()
        self.assertEqual(self.snapshot(),before)
        self.a.spec['money']=75
        row=self.buy('candy',merchant='Unobserved candy shop',items={'item/초코바':1})
        self.assertEqual(row['price'],75);self.assertNotIn('ball_shop',row)
        self.assertEqual(self.stock(),{'item/몬스터볼-2':4})


if __name__=='__main__':unittest.main()
