"""CORE051/071: actual League result, inventory/credit and distinct luck receipts."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
import unittest,json,hashlib,sys,time
from unittest import mock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
import campaign_rewards as R
import league_consequences as L
import common_checks as C
import life
from ruleset import UnresolvedRuleSelection
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,31)
  def make(name,kind,speed):
   return Combatant(self.r,{'id':kind+'/'+name,'name':name,'kind':kind,'level':10,'stats':dict(hp=30,atk=30,**{'def':30},spa=30,spd=30,spe=speed),'types':[],'abilities':[],'moves':['struggle'],'money':6000,'items':{}})
  self.a=make('a','trainer',10);self.b=make('b','trainer',20);self.p=make('p','pokemon',40);self.q=make('q','pokemon',30)
  self.e.everyone=self.e.gm.everyone=[self.a,self.b,self.p,self.q]
 def act(self,activity,actor=None,**kw):return self.e.campaign_reward(actor or self.a,activity,**kw)
 def test_ambiguous_reward_name_rejects_and_explicit_id_survives_policy_revalidation(self):
  before=self.state()
  pools={'battle':['플러스파워'],'berry':['버치열매'],'ball':['몬스터볼'],'healing':['상처약'],'stone':['불꽃의돌'],'vitamin':['타우린'],'held':['구애머리띠'],'tm':['TM26']}
  with self.assertRaises(UnresolvedRuleSelection):self.config(pools=pools)
  self.assertEqual(before,self.state())
  configured=self.config()
  self.assertEqual(configured['pools']['ball'],['item/몬스터볼-2'])
  row=self.act('luck',event_id='selected-ball',reason='actual selected pool',fixed=11)
  self.assertEqual(row['item'],'item/몬스터볼-2')
  self.assertEqual(self.a.spec['items']['item/몬스터볼-2'],1)
 def state(self):return deepcopy((self.a.spec,self.b.spec,self.p.spec,self.q.spec,self.e.rng.getstate(),self.e.elapsed_seconds,self.a.hp,self.b.hp,self.p.hp,self.q.hp,self.p.dead,self.q.dead))
 def config(self,**kw):
  args=dict(pools={'battle':['플러스파워'],'berry':['버치열매'],'ball':['item/몬스터볼-2'],'healing':['상처약'],'stone':['불꽃의돌'],'vitamin':['타우린'],'held':['구애머리띠'],'tm':['TM26']},merchant='Mart',spend_basis='cash',reason='GM adopts this concrete revised reward pool and program',lottery_success=[20],lottery_choices=['item/몬스터볼-2','상처약']);args.update(kw)
  return self.act('configure',**args)
 def buy(self,event_id='purchase',**kw):
  args=dict(event_id=event_id,merchant='Mart',items={'상처약':10},reason='actual shop sale');args.update(kw)
  return self.act('purchase',**args)
 def league(self):
  self.e.start_league([('a',self.a,self.p),('b',self.b,self.q)],mode='league')
  self.e.league_declare('a:trainer',{'kind':'no_action'});self.e.league_declare('b:trainer',{'kind':'no_action'})
  self.e.league_step();self.e.league_step();self.e.league_step(pokemon_intent={'kind':'no_action'});self.e.league_step(pokemon_intent={'kind':'no_action'})
  self.e.league_complete_round();return self.e.end_league()['encounter_id']
 def settle(self,key,**kw):
  args=dict(encounter_id=key,winner='b',reason='GM adjudicates actual League contest result');args.update(kw)
  return self.act('league_result',**args)
 def test_fixed_source_scopes(self):
  rows=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8-sig'))['entries']
  for row in rows:
   if row['id'] in ('C3-CORE-051','C3-CORE-071'):
    s=row['source_snapshot']['source'];self.assertEqual(s['excerpt'],'\n'.join((ROOT/s['file']).read_text(encoding='utf-8-sig').splitlines()[s['start']-1:s['end']]))
 def test_actual_league_loss_never_halves_money_kills_rebuilds_or_ends_campaign(self):
  self.p.hp=0;self.p.conditions.add('기절');before_roster=tuple(self.e.everyone)
  key=self.league();before=self.state();self.assertIsNone(self.settle(key)['automatic_loss'])
  self.assertEqual(before,self.state());self.assertEqual(set(before_roster),set(self.e.everyone));self.assertEqual(self.a.spec['money'],6000);self.assertFalse(self.p.dead);self.assertEqual(self.p.hp,0)
  self.assertFalse(hasattr(self.e,'campaign_ended'));self.assertNotIn('replacement_character',self.a.spec)
 def test_league_result_requires_native_finish_and_actual_participants_once(self):
  before=self.state()
  with self.assertRaises(ValueError):self.settle('fabricated')
  self.assertEqual(before,self.state());key=self.league()
  with self.assertRaises(ValueError):self.settle(key,winner='outsider')
  self.settle(key)
  with self.assertRaises(ValueError):self.settle(key)
 def test_league_rounds_share_one_encounter_receipt(self):
  self.e.start_league([('a',self.a,self.p),('b',self.b,self.q)],mode='league');key=self.e._league_runtime['encounter_id']
  for n in range(2):
   self.e.league_declare('a:trainer',{'kind':'no_action'});self.e.league_declare('b:trainer',{'kind':'no_action'});self.e.league_step();self.e.league_step();self.e.league_step(pokemon_intent={'kind':'no_action'});self.e.league_step(pokemon_intent={'kind':'no_action'});self.e.league_complete_round()
   if n==0:self.e.next_league_round();self.assertEqual(self.e._league_runtime['encounter_id'],key)
  self.assertEqual(self.e.end_league()['encounter_id'],key);self.assertEqual(len(self.e._league_outcomes),1)
 def test_explicit_lethal_event_is_not_erased_by_league_label(self):
  self.e.start_league([('a',self.a,self.p),('b',self.b,self.q)],mode='league');self.p.injuries=10;life.sync(self.e,self.p);self.assertTrue(self.p.dead)
 def test_league_result_source_change_refuses_before_state(self):
  key=self.league();old=dict(self.r.selection.aliases);self.r.selection.aliases[L.SOURCE]=R.SOURCE
  try:
   before=self.state()
   with self.assertRaises(ValueError):self.settle(key)
   self.assertEqual(before,self.state());self.assertEqual(self.e._league_outcomes[key]['status'],'awaiting_ruling')
  finally:self.r.selection.aliases=old
 def test_league_result_does_not_require_unrelated_money_source(self):
  key=self.league();old=dict(self.r.selection.aliases);self.r.selection.aliases[R.SOURCE]=L.SOURCE
  try:
   before=self.state();self.assertEqual(self.settle(key)['status'],'settled');self.assertEqual(before,self.state())
   with self.assertRaises(ValueError):self.act('grant',event_id='money',kind='gym',reason='unselected reward source',money=100)
  finally:self.r.selection.aliases=old
 def test_loss_and_wager_are_separate_real_escrow_and_payout(self):
  self.act('wager',event_id='bet',opponent=self.b,stakes={self.a.spec['id']:1500,self.b.spec['id']:2000},consents={self.a.spec['id']:True,self.b.spec['id']:True},reason='both trainers agree to exact stakes')
  self.assertEqual((self.a.spec['money'],self.b.spec['money']),(4500,4000));key=self.league();self.settle(key);self.assertEqual(self.a.spec['money'],4500)
  out=self.act('settle_wager',event_id='bet',encounter_id=key);self.assertEqual(out['payout'],3500);self.assertEqual((self.a.spec['money'],self.b.spec['money']),(4500,7500))
  with self.assertRaises(ValueError):self.act('settle_wager',event_id='bet',encounter_id=key)
 def test_wager_missing_consent_funds_and_observed_result_cannot_spend(self):
  before=self.state()
  for stakes,consents in (({self.a.spec['id']:10,self.b.spec['id']:10},{self.a.spec['id']:True,self.b.spec['id']:False}),({self.a.spec['id']:99999,self.b.spec['id']:10},{self.a.spec['id']:True,self.b.spec['id']:True})):
   with self.assertRaises(ValueError):self.act('wager',event_id='bet',opponent=self.b,stakes=stakes,consents=consents,reason='declared agreement')
   self.assertEqual(before,self.state())
  key=self.league();self.settle(key);self.act('wager',event_id='late',opponent=self.b,stakes={self.a.spec['id']:10,self.b.spec['id']:10},consents={self.a.spec['id']:True,self.b.spec['id']:True},reason='new future contest')
  before=self.state()
  with self.assertRaises(ValueError):self.act('settle_wager',event_id='late',encounter_id=key)
  self.assertEqual(before,self.state())
 def test_gm_rewards_pay_real_money_inventory_credit_without_guidance_caps(self):
  for i,kind in enumerate(('gym','contest','family','side_job','service_sale')):self.act('grant',event_id=str(i),kind=kind,reason='actual GM reward or completed work',money=9000,items={'상처약':1,'TM26':1},credits={'Mart':500})
  self.assertEqual(self.a.spec['money'],51000);self.assertEqual(self.a.spec['items']['상처약'],5);self.assertEqual(self.a.spec['items']['TM26'],5);self.assertEqual(self.a.spec['store_credit']['Mart'],2500)
  with self.assertRaises(ValueError):self.act('grant',event_id='0',kind='gym',reason='duplicate',money=9000)
 def test_awarded_item_and_tm_are_consumed_by_native_inventory_users(self):
  self.act('grant',event_id='reward',kind='gym',reason='actual gym award',items={'상처약':1,'TM26':1});self.p.hp-=30
  hp=self.p.hp;self.e.use_item(self.a,'상처약',self.p);self.assertGreater(self.p.hp,hp);self.assertEqual(self.a.spec['items']['상처약'],0)
  row=self.e.pokemon_activity(self.a,'register_machine',instance_id='reward-tm',code='TM26');self.assertEqual(row['status'],'owned')
 def test_invalid_reward_item_rejects_before_money_or_inventory(self):
  before=self.state()
  with self.assertRaises(ValueError):self.act('grant',event_id='bad',kind='family',reason='gift',money=100,items={'not-an-item':1})
  self.assertEqual(before,self.state());self.assertNotIn('bad',R.events(self.e))
 def test_actual_purchase_spends_owned_resources_and_records_receipt(self):
  row=self.buy();self.assertEqual(row['cash_spent'],2000);self.assertEqual(self.a.spec['money'],4000);self.assertEqual(self.a.spec['items']['상처약'],10)
  before=self.state()
  with self.assertRaises(ValueError):self.buy()
  with self.assertRaises(ValueError):self.buy('too-much',items={'상처약':100})
  self.assertEqual(before,self.state())
 def test_promotion_requires_actual_owned_qualifying_merchant_receipt_once(self):
  self.config();self.buy();out=self.act('promotion',purchase_id='purchase');self.assertEqual(out,{'punches':0,'credit':1000});self.assertEqual(self.a.spec['store_credit']['Mart'],1000)
  for actor,pid in ((self.a,'purchase'),(self.b,'purchase'),(self.a,'fabricated')):
   with self.assertRaises(ValueError):self.act('promotion',actor=actor,purchase_id=pid)
 def test_promotion_accumulates_partial_spend_and_credit_is_actually_redeemed(self):
  self.config()
  for i in range(20):self.buy(str(i),items={'상처약':1},unit_prices={'상처약':50});self.act('promotion',purchase_id=str(i))
  self.assertEqual(self.a.spec['store_credit']['Mart'],500);self.assertEqual(self.a.spec['promotion_spend_remainders']['Mart'],0)
  self.buy('redeem',items={'상처약':2},credit=400);self.assertEqual(self.a.spec['store_credit']['Mart'],100);self.assertEqual(self.a.spec['money'],5000)
  self.assertEqual(self.act('promotion',purchase_id='redeem')['credit'],0)
 def test_promotion_and_lottery_share_native_purchase_receipts_after_both_restores(self):
  # C11-031/032: a purchase has separate, single-use promotion and lottery
  # receipts. Restoring either path must preserve their real inventory owner.
  def reload_json():
   self.e=Engine.import_state(self.r,json.loads(json.dumps(self.e.export_state())))
   actors={c.entity_id:c for c in self.e.everyone}
   self.a,self.b,self.p,self.q=[actors[c.entity_id] for c in (self.a,self.b,self.p,self.q)]
  self.config();purchase=self.buy()
  self.assertEqual(purchase['cash_spent'],2000)
  self.e.gm.snapshot('before-benefits')
  self.act('promotion',purchase_id='purchase')
  self.act('lottery',event_id='lottery',purchase_id='purchase',fixed=20)
  self.e.gm.restore('before-benefits')
  self.assertNotIn('Mart',self.a.spec.get('store_credit',{}))
  self.assertFalse(R.events(self.e)['purchase']['promotion_consumed'])
  self.assertIsNone(R.events(self.e)['purchase']['lottery_event'])
  reload_json()
  self.assertEqual(self.act('promotion',purchase_id='purchase'),{'punches':0,'credit':1000})
  self.assertEqual(self.act('lottery',event_id='lottery',purchase_id='purchase',fixed=20)['status'],'awaiting_choice')
  self.e.gm.snapshot('awaiting-prize')
  self.act('claim_lottery',event_id='lottery',item_name='item/몬스터볼-2')
  self.e.gm.restore('awaiting-prize')
  self.assertNotIn('item/몬스터볼-2',self.a.spec['items'])
  reload_json()
  self.act('claim_lottery',event_id='lottery',item_name='상처약')
  self.assertEqual(self.a.spec['items']['상처약'],11)
  self.buy('redeem',items={'상처약':2},credit=400)
  self.assertEqual((self.a.spec['money'],self.a.spec['store_credit']['Mart']),(4000,600))
  self.p.hp-=30;hp=self.p.hp
  self.e.use_item(self.a,'상처약',self.p)
  self.assertGreater(self.p.hp,hp)
  self.assertEqual(self.a.spec['items']['상처약'],12)
  reload_json();before=self.state();receipts=deepcopy(R.events(self.e))
  for activity,options in (
   ('promotion',{'purchase_id':'purchase'}),
   ('lottery',{'event_id':'duplicate','purchase_id':'purchase','fixed':20}),
   ('claim_lottery',{'event_id':'lottery','item_name':'상처약'})):
   with self.subTest(activity=activity),self.assertRaises(ValueError):self.act(activity,**options)
   self.assertEqual(self.state(),before)
   self.assertEqual(R.events(self.e),receipts)
 def test_lottery_missing_success_threshold_preserves_money_rng_and_receipt(self):
  self.config(lottery_success=None);self.buy();before=self.state();out=self.act('lottery',event_id='lottery',purchase_id='purchase');self.assertIsInstance(out,C.PendingDecision);self.assertEqual(before,self.state());self.assertNotIn('lottery',R.events(self.e));self.assertIsNone(R.events(self.e)['purchase']['lottery_event'])
 def test_lottery_uses_separate_d20_then_player_choice_once(self):
  self.config();self.buy()
  with mock.patch.object(self.e,'d20',side_effect=AssertionError('accuracy d20 must not run')):out=self.act('lottery',event_id='lottery',purchase_id='purchase',fixed=20)
  self.assertEqual(out['status'],'awaiting_choice');before=self.a.spec['items'].get('item/몬스터볼-2',0)
  with self.assertRaises(ValueError):self.act('lottery',event_id='other',purchase_id='purchase',fixed=20)
  with self.assertRaises(ValueError):self.act('claim_lottery',event_id='lottery',item_name='구애머리띠')
  self.act('claim_lottery',event_id='lottery',item_name='item/몬스터볼-2');self.assertEqual(self.a.spec['items']['item/몬스터볼-2'],before+1)
  with self.assertRaises(ValueError):self.act('claim_lottery',event_id='lottery',item_name='item/몬스터볼-2')
 def test_lottery_loss_and_small_purchase_do_not_grant_prize_or_second_roll(self):
  self.config();self.buy('small',items={'상처약':1});before=self.state()
  with self.assertRaises(ValueError):self.act('lottery',event_id='small-roll',purchase_id='small')
  self.assertEqual(before,self.state());self.buy();out=self.act('lottery',event_id='lost',purchase_id='purchase',fixed=1);self.assertEqual(out['status'],'lost')
  with self.assertRaises(ValueError):self.act('claim_lottery',event_id='lost',item_name='상처약')
 def test_every_default_luck_face_pays_exact_source_category(self):
  self.config();expected=['none']*4+['battle']*2+['money']*2+['berry']*2+['ball']*2+['healing']*4+['stone','vitamin','held','tm']
  before=self.a.spec['money']
  for face in range(1,21):
   out=self.act('luck',event_id='luck'+str(face),reason='GM declares actual inventory need',fixed=face,fixed_cash=4);self.assertEqual(out['category'],expected[face-1]);self.assertEqual(out['status'],'paid')
  self.assertEqual(self.a.spec['money'],before+800)
  for name,count in {'플러스파워':2,'버치열매':2,'item/몬스터볼-2':2,'상처약':4,'불꽃의돌':1,'타우린':1,'구애머리띠':1,'TM26':1}.items():self.assertEqual(self.a.spec['items'][name],count)
 def test_native_luck_rng_has_no_skill_accuracy_or_ap_modifiers(self):
  self.config();self.a.spec['skills']={'행운':99};before=self.e.rng.getstate()
  with mock.patch.object(self.e,'d20',side_effect=AssertionError('accuracy unavailable')),mock.patch.object(self.e,'skill_roll',side_effect=AssertionError('skill unavailable')):row=self.act('luck',event_id='native',reason='GM occasion')
  self.assertNotEqual(before,self.e.rng.getstate());self.assertEqual(row['rolls'][0]['die'],20)
  before=self.state()
  with self.assertRaises(ValueError):self.act('luck',event_id='native',reason='try again')
  self.assertEqual(before,self.state())
 def test_custom_luck_table_is_explicit_and_invalid_pool_fails_before_rng(self):
  self.config(luck_table=['money']*20);out=self.act('luck',event_id='custom',reason='adopted GM table',fixed=1,fixed_cash=2);self.assertEqual(out['money'],200)
  before=self.state()
  with self.assertRaises(ValueError):self.config(luck_table=['money'])
  with self.assertRaises(ValueError):self.config(pools={})
  self.assertEqual(before,self.state())
 def test_changed_policy_after_observation_cannot_rewrite_prize(self):
  self.config();self.buy();self.act('lottery',event_id='lot',purchase_id='purchase',fixed=20);self.config(lottery_choices=['구애머리띠']);before=self.state()
  with self.assertRaises(ValueError):self.act('claim_lottery',event_id='lot',item_name='구애머리띠')
  self.assertEqual(before,self.state())
 def test_reward_source_change_rejects_before_rng_and_payment(self):
  self.config();old=dict(self.r.selection.aliases);self.r.selection.aliases[R.SOURCE]=L.SOURCE
  try:
   before=self.state()
   with self.assertRaises(ValueError):self.act('luck',event_id='bad',reason='try')
   with self.assertRaises(ValueError):self.buy()
   self.assertEqual(before,self.state())
  finally:self.r.selection.aliases=old
 def test_snapshot_restores_observed_choice_and_inventory_exactly_once(self):
  self.config();self.buy();self.act('lottery',event_id='lot',purchase_id='purchase',fixed=20);self.e.gm.snapshot('choice');self.act('claim_lottery',event_id='lot',item_name='item/몬스터볼-2');self.e.gm.restore('choice')
  self.assertNotIn('item/몬스터볼-2',self.a.spec['items']);self.act('claim_lottery',event_id='lot',item_name='상처약');self.assertEqual(self.a.spec['items']['상처약'],11)
  with self.assertRaises(ValueError):self.act('claim_lottery',event_id='lot',item_name='상처약')
 def test_snapshot_before_configuration_removes_later_policy_events_and_league(self):
  self.e.gm.snapshot('before');self.config();self.buy();key=self.league();self.settle(key);self.e.gm.restore('before')
  for name in ('_campaign_reward_policy','_campaign_reward_events','_league_outcomes'):self.assertFalse(hasattr(self.e,name))
  self.assertEqual(self.a.spec['money'],6000)
 def test_snapshot_wager_preserves_actual_actors_and_single_payout(self):
  self.act('wager',event_id='bet',opponent=self.b,stakes={self.a.spec['id']:10,self.b.spec['id']:10},consents={self.a.spec['id']:True,self.b.spec['id']:True},reason='agreed');key=self.league();self.settle(key);self.e.gm.snapshot('settled');self.act('settle_wager',event_id='bet',encounter_id=key);self.e.gm.restore('settled')
  self.assertIs(R.events(self.e)['bet']['parties'][0],self.a);self.act('settle_wager',event_id='bet',encounter_id=key);self.assertEqual((self.a.spec['money'],self.b.spec['money']),(5990,6010))
if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':getattr(t,'_testMethodName',t.id()),'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':getattr(t,'_testMethodName',t.id()),'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':getattr(t,'_testMethodName',t.id()),'status':'error'})
 test_started=datetime.now(timezone.utc).isoformat();test_clock=time.perf_counter()
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 files={p.relative_to(ROOT).as_posix() for p in (ROOT/'engine').glob('*.py')}|{'data/campaign-reward-policy.json','data/pokemon-machines.json','input/ch06-gameplay.md','input/ch11-running-the-game.md','output/ruleunits.jsonl','data/rulesets.json','tools/test_category3_batch15_pokemon.py'}
 files |= {p.relative_to(ROOT).as_posix() for p in (ROOT/'data').glob('*.json')}
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'test_started_at':test_started,'test_duration_seconds':time.perf_counter()-test_clock,'successful':result.wasSuccessful(),'results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in sorted(files)}}
 (ROOT/'output/category3-batch15-pokemon-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
