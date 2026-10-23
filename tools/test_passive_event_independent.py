"""Independent boundary tests. Synthetic metadata is explicitly test-only."""
from pathlib import Path
import sys,json,hashlib,unittest,copy
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from synthetic_rule_fixture import register_synthetic
import passive_events as PE
import effects as FX
import temporary_hp as TEMP_HP
RULE='ability/자기과신'
class Cases(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
 def fixture(self,seed=0):
  e=Engine(self.rules,seed=seed)
  def make(n,side,ab):
   x=Combatant(self.rules,dict(name=n,kind='pokemon',level=20,stats={s:30 for s in ('hp','atk','def','spa','spd','spe')},moves=['struggle'],abilities=ab,types=[]));x.side=side;return x
  a,b=make('owner','party',['자기과신']),make('target','enemy',[]);e.everyone=e.gm.everyone=[a,b];e.register_abilities(a);e.start_round([a,b]);e.start_of_turn(a);b.hp=8;return e,a,b
 def ev(self,e):return list(e._passive_events.values())[-1]
 def runmove(self,e,a,b,mid='struggle'):return e.use_move(a,b,mid,set_damage=True)
 def synthetic(self,e,a,effects):
  uid='test/passive-independent-'+self._testMethodName;register_synthetic(e.r,uid)
  m=copy.deepcopy(e.r.move('struggle'));m.update(id=uid,name=uid);e.r.moves[uid]=m;e.r.moves_mech[uid]={'name':uid,'coverage':'full','effects':effects};a.moves.append(uid);return uid
 def test_001_actual_KO_cost_and_once(self):
  e,a,b=self.fixture();self.runmove(e,a,b);v=self.ev(e)
  self.assertEqual((a.stages['atk'],a._action_history,a.move_uses['struggle']),(1,['standard'],1));self.assertFalse(v['outcomes'][RULE]['source_action_created']);self.assertEqual(a.spec.get('ap_spent',0),0)
 def test_002_natural_and_critical(self):
  e,a,b=self.fixture(5);self.runmove(e,a,b);v=self.ev(e);self.assertEqual((v['hit'],v['natural_roll'],v['critical']),(True,20,True))
 def test_003_miss_loss_unknown(self):
  e,a,b=self.fixture(31);self.runmove(e,a,b);v=self.ev(e);self.assertEqual((v['hit'],v['natural_roll'],v['dealt']),(False,1,0));self.assertIsNone(v['real_hp_loss']);self.assertEqual(a.stages['atk'],0)
 def test_004_temp_HP_distinct(self):
  e,a,b=self.fixture();TEMP_HP.grant(e,b,20);self.runmove(e,a,b);v=self.ev(e);self.assertEqual((v['hit'],v['dealt'],v['real_hp_loss'],v['temp_hp_loss']),(True,11,0,11));self.assertIsNone(v['raw_damage']);self.assertIsNone(v['resolved_damage'])
 def test_005_capped_damage_distinct(self):
  e,a,b=self.fixture();b.damage_cap={'value':0};self.runmove(e,a,b);v=self.ev(e);self.assertEqual((v['dealt'],v['real_hp_loss'],b.hp),(11,0,8));self.assertEqual(a.stages['atk'],0)
 def test_006_external_loss_not_move(self):
  e,a,b=self.fixture();e.lose_hp(b,11);self.assertFalse(e._passive_events);self.assertEqual(a.stages['atk'],0)
 def test_007_effect_KO_cause_unproved(self):
  e,a,b=self.fixture();b.hp=20;mid=self.synthetic(e,a,[{'type':'hp_loss','value':20,'target':'target'}])
  with self.assertRaises(PE.PassiveEventPending):self.runmove(e,a,b,mid)
  self.assertEqual(a.stages['atk'],0);self.assertFalse(self.ev(e)['attack_observation']['after']['fainted'])
 def test_008_unknown_effect_rejected_before_passive_event(self):
  import effect_contracts as CONTRACTS
  e,a,b=self.fixture();mid=self.synthetic(e,a,[{'type':'independent_unimplemented_effect'}])
  before=copy.deepcopy((a.spec,a.budget,a._action_history,a.move_uses)),b.hp,e.rng.getstate()
  with self.assertRaises(CONTRACTS.EffectContractError):self.runmove(e,a,b,mid)
  self.assertFalse(e._passive_events);self.assertEqual(a.stages['atk'],0)
  self.assertEqual(before,((a.spec,a.budget,a._action_history,a.move_uses),b.hp,e.rng.getstate()))
 def test_009_multi_roll_not_single(self):
  e,a,b=self.fixture();mid=self.synthetic(e,a,[{'type':'multi_roll','rolls':3}])
  with self.assertRaises(PE.PassiveEventPending):self.runmove(e,a,b,mid)
  self.assertFalse(self.ev(e)['ordinary_single'] and self.ev(e).get('mechanics_scope_supported',True));self.assertEqual(a.stages['atk'],0)
 def test_010_owner_faint_after_KO_pending(self):
  e,a,b=self.fixture();a.hp=5;mid=self.synthetic(e,a,[{'type':'hp_loss','value':5,'target':'self'}])
  with self.assertRaises(PE.PassiveEventPending):self.runmove(e,a,b,mid)
  self.assertFalse(self.ev(e)['owner_before']['fainted']);self.assertTrue(a.fainted);self.assertTrue(b.fainted);self.assertEqual(a.stages['atk'],0)
 def test_011_initial_suppression(self):
  e,a,b=self.fixture();a.abilities_suppressed=True;self.runmove(e,a,b);self.assertEqual(self.ev(e)['status'],'inapplicable');self.assertEqual(a.stages['atk'],0)
 def test_012_initial_faint(self):
  e,a,b=self.fixture();e.lose_hp(a,200);self.runmove(e,a,b);self.assertFalse(e._passive_events)
 def test_013_enemy_unknown_holds_clock(self):
  e,a,b=self.fixture();del b.side
  with self.assertRaises(PE.PassiveEventPending):self.runmove(e,a,b)
  self.assertEqual((a.stages['atk'],b.hp),(0,-3))
  with self.assertRaises(PE.PassiveEventPending):e.end_round()
  self.assertEqual(e.elapsed_seconds,0)
 def test_014_ally_and_old_KO(self):
  e,a,b=self.fixture();b.side=a.side;self.runmove(e,a,b);self.assertEqual(a.stages['atk'],0)
  e,a,b=self.fixture();e.lose_hp(b,10);self.runmove(e,a,b);self.assertEqual(a.stages['atk'],0)
 def test_015_redelivery_and_legacy_not_double(self):
  e,a,b=self.fixture();e.register_abilities(a);self.assertFalse(a.ability_triggers);self.runmove(e,a,b);self.assertEqual(e.deliver_passive_event(self.ev(e)['id']),'already_delivered');FX.fire_event(e,a,{'event':'enemy_faint_by_user','move':e.r.move('struggle')},b);self.assertEqual((a.stages['atk'],len(e._passive_receipts)),(1,1))
 def test_016_distinct_activation_receipts(self):
  e,a,b=self.fixture();self.runmove(e,a,b);first=self.ev(e)['id'];e.end_of_turn(a);e.end_round();e.start_round([a,b]);e.start_of_turn(a);e.gm.set_hp(b,8);e.gm.remove_condition(b,'기절');self.runmove(e,a,b);self.assertNotEqual(first,self.ev(e)['id']);self.assertEqual((a.stages['atk'],len(e._passive_receipts)),(2,2))
 def test_017_snapshot_before_after_identity(self):
  e,a,b=self.fixture();e.gm.snapshot('pre');self.runmove(e,a,b);e.gm.restore('pre');self.assertFalse(e._passive_events);self.assertIn(a,e._passive_listeners);self.runmove(e,a,b);eid=self.ev(e)['id'];e.gm.snapshot('post');e.gm.restore('post');self.assertIs(self.ev(e)['actor'],a);self.assertEqual(e.deliver_passive_event(eid),'already_delivered');self.assertEqual(a.stages['atk'],1)
 def test_018_pending_snapshot(self):
  e,a,b=self.fixture();del b.side
  with self.assertRaises(PE.PassiveEventPending):self.runmove(e,a,b)
  e.gm.snapshot('pending');e.gm.restore('pending')
  with self.assertRaises(PE.PassiveEventPending):e.advance_time(10)
  self.assertEqual(e.elapsed_seconds,0)
 def test_019_shared_activation_pending(self):
  e,a,b=self.fixture()
  with self.assertRaises(PE.PassiveEventPending):e.use_move_on(a,b,'struggle',[a,b])
  self.assertFalse(self.ev(e)['ordinary_single']);self.assertEqual(a.stages['atk'],0)
 def test_020_public_fake_event_and_unimplemented_choice(self):
  e,a,b=self.fixture()
  with self.assertRaises(ValueError):e.deliver_passive_event('fake')
  self.runmove(e,a,b);before=copy.deepcopy((a.hp,a.spec,a.budget,a.stages));res=e.choose_passive_event(self.ev(e)['id'],a,RULE,{'effect':'heal'});self.assertFalse(res['choice_applied']);self.assertEqual(before,(a.hp,a.spec,a.budget,a.stages))
 def test_021_no_budget_no_event(self):
  e,a,b=self.fixture();a.budget['standard']=0;self.runmove(e,a,b);self.assertFalse(e._passive_events);self.assertEqual(b.hp,8)
 def test_022_internal_unknown_hit_not_false(self):
  # Internal component API only: native producer currently supplies bool literals.
  e,a,b=self.fixture();eid=PE.begin(e,a,b,e.r.move('struggle'),ordinary_single=True)
  try:PE.complete(e,eid,hit=None,natural=None,critical=None,dealt=None)
  except (PE.PassiveEventPending,ValueError,TypeError):pass
  self.assertNotEqual(self.ev(e)['status'],'inapplicable');self.assertEqual(a.stages['atk'],0)
 def test_023_exact_source_anchor(self):
  p=json.loads((ROOT/'data/verification/passive-event-runtime-profile.json').read_text(encoding='utf8'));s=p['source_anchor'];f=ROOT/s['file'];self.assertEqual(hashlib.sha256(f.read_bytes()).hexdigest(),s['file_sha256']);ex='\n'.join(f.read_text(encoding='utf-8-sig').splitlines()[s['start']-1:s['end']]);self.assertEqual(ex,s['excerpt']);self.assertEqual(hashlib.sha256(ex.encode()).hexdigest(),s['excerpt_sha256'])
class Result(unittest.TextTestResult):
 def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
 def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':'PASSIVE-INDEPENDENT-'+t._testMethodName,'status':'pass'})
 def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':'PASSIVE-INDEPENDENT-'+t._testMethodName,'status':'fail','detail':self._exc_info_to_string(e,t)})
 def addError(self,t,e):super().addError(t,e);self.rows.append({'id':'PASSIVE-INDEPENDENT-'+t._testMethodName,'status':'error','detail':self._exc_info_to_string(e,t)})
if __name__=='__main__':
 r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Cases))
 paths=list((ROOT/'engine').glob('*.py'))+list((ROOT/'data').rglob('*.json'))+list((ROOT/'output/entities').glob('*.json'))
 paths += [Path(__file__),ROOT/'tools/synthetic_rule_fixture.py',ROOT/'input/db/abilities.csv',ROOT/'input/ch03-skills-edges-feats.md',ROOT/'input/ch07-combat.md',ROOT/'input/ch10-index-reference.md',ROOT/'data/verification/passive-event-runtime-profile.json',ROOT/'output/ruleunits.jsonl']
 report={'results':r.rows,'tests_run':r.testsRun,'whole_source_closure':False,'scope':'Bounded transport and one source witness. Synthetic boundaries are not production source admission. Test022 is internal API only.','input_hashes':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.exists()}}
 (ROOT/'output/passive-event-independent-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8');sys.exit(not r.wasSuccessful())
