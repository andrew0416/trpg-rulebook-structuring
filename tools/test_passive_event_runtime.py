"""Actual-producer Static event tests. One source-specific witness, no full passive closure."""
from pathlib import Path
import sys,json,hashlib,unittest,copy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"engine"))
from unittest import mock
from engine import Rules,Engine,Combatant
import passive_events as PE
import effects as FX
import temporary_hp as TEMP_HP
RULE="ability/자기과신"
class Cases(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset="core")
 def fixture(self,seed=0,register=True):
  e=Engine(self.rules,seed=seed)
  def c(name,side,abilities):
   x=Combatant(self.rules,dict(name=name,kind="pokemon",level=20,stats={s:30 for s in ("hp","atk","def","spa","spd","spe")},moves=["struggle"],abilities=abilities,types=[]));x.side=side;return x
  a,b=c("a","party",["자기과신"]),c("b","enemy",[])
  e.everyone=e.gm.everyone=[a,b]
  if register:e.register_abilities(a)
  e.start_round([a,b]);e.start_of_turn(a);b.hp=8
  return e,a,b
 def run_move(self,e,a,b):return e.use_move(a,b,"struggle",set_damage=True)
 def ev(self,e):return list(e._passive_events.values())[-1]
 def ledger(self,a):return copy.deepcopy((a.spec,a.budget,a._action_history,a.move_uses,a.frequency_state if hasattr(a,"frequency_state") else None))
 def assert_moxie_stage_change(self,before,after):
  import stage_change_history as HISTORY
  before,after=copy.deepcopy((before,after))
  old=before[0][0].pop(HISTORY.KEY);new=after[0][0].pop(HISTORY.KEY)
  self.assertEqual(before,after)
  event=new['rise_window']['events'][-1]
  self.assertEqual({k:event[k] for k in ('direction','stat','before','after','requested_delta','actual_delta')},
                   dict(direction='rise',stat='atk',before=0,after=1,requested_delta=1,actual_delta=1))
  expected=copy.deepcopy(old);expected['sequence']+=1;expected['rise_window']['events'].append(event)
  self.assertEqual(new,expected)
 def test_001_real_source_native_KO_no_fake_action(self):
  e,a,b=self.fixture();owner_ap=copy.deepcopy(a.spec);self.run_move(e,a,b)
  self.assertEqual(a.stages["atk"],1);self.assertEqual(a._action_history,["standard"]);self.assertEqual(a.move_uses["struggle"],1)
  self.assertEqual(a.spec.get("ap_spent",0),0);self.assertEqual(a.spec.get("ap_removed",0),0)
  self.assertEqual(self.ev(e)["status"],"applied");self.assertFalse(self.ev(e)["outcomes"][RULE]["source_action_created"])
 def test_002_actual_natural_critical_evidence(self):
  e,a,b=self.fixture(seed=5);self.run_move(e,a,b);v=self.ev(e)
  self.assertEqual(v["natural_roll"],20);self.assertTrue(v["critical"]);self.assertTrue(v["hit"]);self.assertEqual(a.stages["atk"],1)
 def test_003_miss_is_not_hit(self):
  e,a,b=self.fixture(seed=31);self.run_move(e,a,b);v=self.ev(e)
  self.assertEqual(v["natural_roll"],1);self.assertFalse(v["hit"]);self.assertEqual(a.stages["atk"],0);self.assertIsNone(v["real_hp_loss"])
 def test_004_absorbed_hit_distinct_from_HP_loss(self):
  e,a,b=self.fixture();TEMP_HP.grant(e,b,20);self.run_move(e,a,b);v=self.ev(e)
  self.assertTrue(v["hit"]);self.assertEqual(v["dealt"],11);self.assertEqual(v["real_hp_loss"],0);self.assertEqual(v["temp_hp_loss"],11);self.assertEqual(a.stages["atk"],0)
 def test_005_zero_damage_cap_preserves_distinct_fields(self):
  e,a,b=self.fixture();b.damage_cap={"value":0};self.run_move(e,a,b);v=self.ev(e)
  self.assertTrue(v["hit"]);self.assertEqual(v["dealt"],11);self.assertEqual(v["real_hp_loss"],0)
  self.assertIsNone(v["raw_damage"]);self.assertIsNone(v["resolved_damage"]);self.assertEqual(a.stages["atk"],0)
 def test_006_HP_loss_without_move_creates_no_event(self):
  e,a,b=self.fixture();e.lose_hp(b,11,source="test explicit HP loss")
  self.assertTrue(b.fainted);self.assertFalse(e._passive_events);self.assertEqual(a.stages["atk"],0)
 def test_007_already_fainted_is_not_new_KO(self):
  e,a,b=self.fixture();e.lose_hp(b,9);self.run_move(e,a,b)
  self.assertEqual(a.stages["atk"],0);self.assertEqual(self.ev(e)["outcomes"][RULE]["reason"],"target_already_fainted")
 def test_008_ally_is_not_enemy(self):
  e,a,b=self.fixture();b.side=a.side;self.run_move(e,a,b);self.assertEqual(a.stages["atk"],0)
 def test_009_unknown_side_pending_preserves_attack_prefix(self):
  e,a,b=self.fixture();b.side=None
  with self.assertRaises(PE.PassiveEventPending):self.run_move(e,a,b)
  self.assertEqual(b.hp,-3);self.assertEqual(a.stages["atk"],0);v=self.ev(e);self.assertEqual(v["reason"],"enemy_relation_unknown")
  before=self.ledger(a)
  for call in [lambda:e.end_of_turn(a),lambda:e.end_round(),lambda:e.use_move_on(a,b,"struggle",[a]),lambda:e.advance_time(10)]:
   with self.assertRaises(PE.PassiveEventPending):call()
  self.assertEqual(before,self.ledger(a));self.assertEqual(e.everyone,[a,b]);self.assertEqual(e.elapsed_seconds,0)
 def test_010_suppressed_is_not_new_ability_use(self):
  e,a,b=self.fixture();a.abilities_suppressed=True;self.run_move(e,a,b);self.assertEqual(a.stages["atk"],0)
 def test_011_fainted_actor_refused_without_occurrence(self):
  e,a,b=self.fixture();e.lose_hp(a,200);self.run_move(e,a,b);self.assertFalse(e._passive_events);self.assertEqual(b.hp,8)
 def test_012_register_and_delivery_are_idempotent(self):
  e,a,b=self.fixture();e.register_abilities(a);e.register_abilities_one(a,"자기과신")
  self.assertEqual(len(e._passive_listeners[a]),1);self.assertFalse(a.ability_triggers)
  self.run_move(e,a,b);before=self.ledger(a);eid=self.ev(e)["id"]
  self.assertEqual(e.deliver_passive_event(eid),"already_delivered");self.assertEqual(a.stages["atk"],1);self.assertEqual(before,self.ledger(a))
  FX.fire_event(e,a,{"event":"enemy_faint_by_user","move":e.r.move("struggle")},b);self.assertEqual(a.stages["atk"],1)
 def test_013_new_actual_activation_not_deduplicated_by_shape(self):
  e,a,b=self.fixture();self.run_move(e,a,b);first=self.ev(e)["id"]
  e.end_of_turn(a);e.end_round();e.start_round([a,b]);e.start_of_turn(a)
  # Explicit GM intervention restores a target; it does not invent a move event.
  e.gm.set_hp(b,8);e.gm.remove_condition(b,"기절")
  self.run_move(e,a,b);self.assertNotEqual(first,self.ev(e)["id"]);self.assertEqual(a.stages["atk"],2)
 def test_014_snapshot_before_event_restores_ledger_actor_refs(self):
  e,a,b=self.fixture();e.gm.snapshot("pre");self.run_move(e,a,b);e.gm.restore("pre")
  self.assertEqual(a.stages["atk"],0);self.assertEqual(b.hp,8);self.assertFalse(e._passive_events)
  self.assertIn(a,e._passive_listeners);self.run_move(e,a,b);self.assertEqual(a.stages["atk"],1)
 def test_015_snapshot_after_event_preserves_receipt(self):
  e,a,b=self.fixture();self.run_move(e,a,b);eid=self.ev(e)["id"];e.gm.snapshot("post");e.gm.restore("post")
  self.assertIs(self.ev(e)["actor"],a);self.assertIs(self.ev(e)["target"],b)
  self.assertEqual(e.deliver_passive_event(eid),"already_delivered");self.assertEqual(a.stages["atk"],1)
 def test_016_pre_registration_snapshot_removes_listener(self):
  e,a,b=self.fixture(register=False);e.gm.snapshot("unregistered");e.register_abilities(a);e.gm.restore("unregistered")
  self.assertFalse(e._passive_listeners);self.run_move(e,a,b);self.assertFalse(e._passive_events)
 def test_017_choice_requires_real_event_and_is_not_implemented(self):
  e,a,b=self.fixture()
  with self.assertRaises(ValueError):e.choose_passive_event("fake",a,RULE,{"effects":[{"type":"heal","value":100}]})
  self.run_move(e,a,b);eid=self.ev(e)["id"];before=self.ledger(a)
  self.assertEqual(e.choose_passive_event(eid,a,RULE,"arbitrary")["reason"],"source_choice_adapter_not_implemented")
  with self.assertRaises(ValueError):e.choose_passive_event(eid,b,RULE,"arbitrary")
  self.assertEqual(before,self.ledger(a))
 def test_018_unknown_event_delivery_cannot_fabricate_occurrence(self):
  e,a,b=self.fixture()
  with self.assertRaises(ValueError):e.deliver_passive_event("fake")
  self.assertEqual(a.stages["atk"],0)
 def test_019_shared_activation_scope_remains_pending(self):
  e,a,b=self.fixture()
  with self.assertRaises(PE.PassiveEventPending):e.use_move_on(a,b,"struggle",[a,b])
  self.assertEqual(a.stages["atk"],0);self.assertEqual(self.ev(e)["reason"],"multi_target_or_nonordinary_activation_scope_unproved")
 def test_020_source_anchor_exact(self):
  p=json.loads((ROOT/"data/verification/passive-event-runtime-profile.json").read_text(encoding="utf8"));x=p["source_anchor"];q=ROOT/x["file"]
  self.assertEqual(hashlib.sha256(q.read_bytes()).hexdigest(),x["file_sha256"]);ex="\n".join(q.read_text(encoding="utf-8-sig").splitlines()[x["start"]-1:x["end"]])
  self.assertEqual(ex,x["excerpt"]);self.assertEqual(hashlib.sha256(ex.encode()).hexdigest(),x["excerpt_sha256"])
 def test_021_no_budget_no_occurrence(self):
  e,a,b=self.fixture();a.budget["standard"]=0;self.run_move(e,a,b);self.assertFalse(e._passive_events);self.assertEqual(b.hp,8)
 def test_022_pending_snapshot_preserves_boundary(self):
  e,a,b=self.fixture();b.side=None
  with self.assertRaises(PE.PassiveEventPending):self.run_move(e,a,b)
  e.gm.snapshot("pending");e.gm.restore("pending")
  with self.assertRaises(PE.PassiveEventPending):e.end_of_turn(a)
  self.assertEqual(b.hp,-3);self.assertEqual(a.stages["atk"],0)
 def test_025_pending_event_retries_after_snapshot_without_repeating_attack(self):
  e,a,b=self.fixture();b.side=None
  with self.assertRaises(PE.PassiveEventPending):self.run_move(e,a,b)
  eid=self.ev(e)['id'];e.gm.snapshot('pending-retry');e.gm.restore('pending-retry')
  before=self.ledger(a),b.hp,e.rng.getstate()
  with self.assertRaises(PE.PassiveEventPending):e.deliver_passive_event(eid)
  self.assertEqual(before,(self.ledger(a),b.hp,e.rng.getstate()))
  b.side='enemy'
  self.assertEqual(e.deliver_passive_event(eid),'applied')
  self.assert_moxie_stage_change(before,(self.ledger(a),b.hp,e.rng.getstate()))
  self.assertEqual(a.stages['atk'],1);self.assertIsNone(e._passive_pending)
  completed=self.ledger(a),b.hp,e.rng.getstate()
  self.assertEqual(e.deliver_passive_event(eid),'already_delivered')
  self.assertEqual((self.ledger(a),b.hp,e.rng.getstate()),completed)
  self.assertEqual(a.stages['atk'],1)

 def test_026_late_listener_failure_cannot_duplicate_effect_on_retry(self):
  e,a,b=self.fixture();original=PE.PROFILES.apply
  def fail(engine,event,rule):
   original(engine,event,rule)
   engine.rng.random()
   raise ValueError('listener failed after state change')
  with mock.patch.object(PE.PROFILES,'apply',side_effect=fail):
   with self.assertRaisesRegex(ValueError,'listener failed'):self.run_move(e,a,b)
  eid=self.ev(e)['id'];before=self.ledger(a),b.hp,e.rng.getstate()
  self.assertEqual(a.stages['atk'],0);self.assertFalse(e._passive_receipts)
  self.assertEqual(e.deliver_passive_event(eid),'applied')
  self.assert_moxie_stage_change(before,(self.ledger(a),b.hp,e.rng.getstate()))
  self.assertEqual(a.stages['atk'],1)
  completed=self.ledger(a),b.hp,e.rng.getstate()
  self.assertEqual(e.deliver_passive_event(eid),'already_delivered')
  self.assertEqual((self.ledger(a),b.hp,e.rng.getstate()),completed)
  self.assertEqual(a.stages['atk'],1)

 def test_027_pending_event_survives_durable_restore_and_resumes_once(self):
  import state_codec as CODEC
  e,a,b=self.fixture();b.side=None
  with self.assertRaises(PE.PassiveEventPending):self.run_move(e,a,b)
  eid=self.ev(e)['id'];loaded=CODEC.load_engine(self.rules,CODEC.dump_engine(e))
  ev=loaded._passive_events[eid];actor,target=ev['actor'],ev['target']
  self.assertIn(actor,loaded.everyone);self.assertIn(target,loaded.everyone)
  target.side='enemy';before=target.hp,copy.deepcopy(actor.move_uses),loaded.rng.getstate()
  self.assertEqual(loaded.deliver_passive_event(eid),'applied')
  self.assertEqual(before,(target.hp,actor.move_uses,loaded.rng.getstate()))
  self.assertEqual(actor.stages['atk'],1)
  self.assertEqual(loaded.deliver_passive_event(eid),'already_delivered')

 def test_028_pending_later_listener_does_not_repeat_completed_prefix(self):
  e,a,b=self.fixture()
  # Test-only unsupported subscription witnesses transport ordering, not a
  # claimed implementation of a second passive rule.
  e._passive_listeners[a]['test/unsupported']={'test_only':True}
  with self.assertRaises(PE.PassiveEventPending):self.run_move(e,a,b)
  eid=self.ev(e)['id'];self.assertEqual(a.stages['atk'],1)
  before=self.ledger(a),b.hp,e.rng.getstate()
  with self.assertRaises(PE.PassiveEventPending):e.deliver_passive_event(eid)
  self.assertEqual(before,(self.ledger(a),b.hp,e.rng.getstate()))
  self.assertEqual(a.stages['atk'],1);self.assertEqual(len(e._passive_receipts),1)

 def test_029_completed_event_rejects_changed_intent_without_repeating_effects(self):
  e,a,b=self.fixture();self.run_move(e,a,b)
  ev=self.ev(e);eid=ev['id'];original=copy.deepcopy(ev['source_ids'])
  before=self.ledger(a),b.hp,a.stages['atk'],e.rng.getstate(),copy.deepcopy(e._passive_receipts,{id(a):a,id(b):b})
  ev['source_ids'].append('test/another-source')
  with self.assertRaisesRegex(ValueError,'changed input'):e.deliver_passive_event(eid)
  self.assertEqual(before,(self.ledger(a),b.hp,a.stages['atk'],e.rng.getstate(),e._passive_receipts))
  ev['source_ids']=original
  self.assertEqual(e.deliver_passive_event(eid),'already_delivered')

 def test_030_pending_event_rejects_changed_observation_after_restore(self):
  from state_codec import dump_engine,load_engine
  e,a,b=self.fixture();b.side=None
  with self.assertRaises(PE.PassiveEventPending):self.run_move(e,a,b)
  eid=self.ev(e)['id'];loaded=load_engine(self.rules,dump_engine(e));ev=loaded._passive_events[eid]
  actor,target=ev['actor'],ev['target'];target.side='enemy'
  before=actor.stages['atk'],target.hp,loaded.rng.getstate()
  ev['natural_roll']=999
  with self.assertRaisesRegex(ValueError,'changed input'):loaded.deliver_passive_event(eid)
  self.assertEqual(before,(actor.stages['atk'],target.hp,loaded.rng.getstate()))
  self.assertEqual(loaded._passive_pending,eid)

 def driver_hook(self,e,c,rnd):
  target=next(x for x in e.gm.everyone if x is not c)
  e.grid=None;c.abilities.append("자기과신");e.register_abilities_one(c,"자기과신")
  c.stats["atk"]=30;target.stats["def"]=30;target.hp=1;target.side=None
  e.start_of_turn(c);e.use_move(c,target,"struggle",set_damage=True)
 def assert_driver_pending(self,e):
  self.assertEqual(e._passive_driver_result["status"],"incomplete")
  self.assertFalse(e._passive_driver_result["automatic_resume"]);self.assertEqual(e.elapsed_seconds,0)
  self.assertTrue(e.encounter_active);self.assertIsNotNone(e._active_turn_actor)
  self.assertTrue(self.ev(e)["target_after"]["fainted"]);self.assertEqual(self.ev(e)["reason"],"enemy_relation_unknown")
  with self.assertRaises(PE.PassiveEventPending):e.end_round()
 def test_023_actual_scenario_driver_returns_incomplete(self):
  from engine import scenario
  # Driver component fixture supplies an explicit order; initiative semantics are not under test.
  with mock.patch.object(Engine,"initiative",lambda e,actors:list(actors)):
   e=scenario(str(ROOT),seed=5,ruleset="core",hook=self.driver_hook)
  self.assert_driver_pending(e)
 def test_024_actual_encounter_driver_returns_incomplete(self):
  from encounter import run_encounter
  with mock.patch.object(Engine,"initiative",lambda e,actors:list(actors)):
   e,party,wild=run_encounter(str(ROOT),"data/encounters/lakeside.json",seed=5,ruleset="core",hook=self.driver_hook,write=False)
  self.assert_driver_pending(e)
class Result(unittest.TextTestResult):
 def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
 def addSuccess(self,t):super().addSuccess(t);self.rows.append({"id":"PASSIVE-RUNTIME-"+t._testMethodName,"status":"pass"})
 def addFailure(self,t,err):super().addFailure(t,err);self.rows.append({"id":"PASSIVE-RUNTIME-"+t._testMethodName,"status":"fail","detail":self._exc_info_to_string(err,t)})
 def addError(self,t,err):super().addError(t,err);self.rows.append({"id":"PASSIVE-RUNTIME-"+t._testMethodName,"status":"error","detail":self._exc_info_to_string(err,t)})
if __name__=="__main__":
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Cases))
 paths=list((ROOT/"engine").glob("*.py"))+[Path(__file__),ROOT/"input/db/abilities.csv",ROOT/"data/verification/passive-event-runtime-profile.json"]
 paths+=list((ROOT/"data").glob("*.json"))+list((ROOT/"output/entities").glob("*.json"))
 report=dict(results=result.rows,tests_run=result.testsRun,source_scope="One Static consequence witness; choice implementation=0; Flourish/whole passive closure=false",input_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
 (ROOT/"output/passive-event-runtime-tests.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
 sys.exit(not result.wasSuccessful())
