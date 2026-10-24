"""Independent production-path tests for the containing project."""
import hashlib,json,pathlib,sys,unittest,copy,subprocess,builtins,io
from unittest import mock
READ_INPUTS=set()
from datetime import datetime,timezone
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/"engine"))
from engine import Rules,Engine,Combatant
import heavy_injury_adapter as H
import effects_ext as EXT
import effects as FX
import turn as TURN

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset="core")
 def pair(self,injuries=5,certified=False):
  e=Engine(self.rules);e.rulings=copy.deepcopy(e.rulings)
  if not certified:e.rulings.hooks["before_damage"].append(dict(fn=lambda value,ctx:value,reason="test-only unknown interaction"))
  def actor(name):return Combatant(self.rules,dict(name=name,kind="trainer",level=10,stats={x:30 for x in ("hp","atk","def","spa","spd","spe")},types=[],abilities=[],moves=["struggle"]))
  a,b=actor("attacker"),actor("target");a.hp=b.hp=50;b.injuries=injuries
  e.everyone=e.gm.everyone=[a,b];e.d20=lambda:10;e.start_round([a,b]);e.start_of_turn(a)
  return e,a,b
 def pending(self,e,a,b):
  with self.assertRaises(H.HeavyPending) as caught:e.use_move(a,b,"struggle",set_damage=True)
  return e._heavy_events[caught.exception.event_id]
 def ack(self,e,b,packet,**changes):
  values=dict(expected_current_state=H.observe(b),ruling="TEST-ONLY explicit GM ruling: accept adjudicated state",
              disposition=H.ContinuationDisposition.CANCELLED_BY_RULING,
              continuation_reason="TEST-ONLY ruling cancels the unexecuted caller remainder")
  values.update(changes)
  return H.acknowledge_ruling(e,packet["event_id"],b,**values)
 def test_001_actual_primary_producer_preserves_hit_and_holds(self):
  e,a,b=self.pair();p=self.pending(e,a,b)
  self.assertEqual((p["producer"],p["before"]["hp"],p["observed_after"]["hp"]),
                   ("Engine.resolve_attack_damage",50,39))
  self.assertEqual((b.hp,b.injuries),(39,5));self.assertEqual(a.move_uses["struggle"],1)
  self.assertEqual(p["context"],"unknown");self.assertEqual(p["kernel_status"],"pending")
  self.assertFalse(p["continuation_reified"])
 def test_002_double_strike_holds_before_public_activation(self):
  e,a,b=self.pair();a.registry.append(dict(type="gain_keyword",keyword="이단타격"))
  b.reflect={"trigger":"physical","attacker_hp_loss":"hp user lost"}
  before=(dict(a.budget),dict(a.move_uses),e.rng.getstate(),a.hp,b.hp,list(a._action_history))
  with self.assertRaisesRegex(ValueError,"Double Strike combined damage"):
   e.use_move(a,b,"struggle",set_damage=True)
  self.assertEqual(before,(dict(a.budget),dict(a.move_uses),e.rng.getstate(),a.hp,b.hp,list(a._action_history)))
  self.assertIsNotNone(b.reflect);self.assertFalse(e._heavy_events)
  # Future source implementation must resolve both accuracy/critical results,
  # combine the damage roll as the keyword requires, and settle heavy/reflection
  # ordering. An independently applied second hit is not a valid substitute.
 def test_003_actual_delayed_hit_stops_remaining_queue(self):
  e,a,b=self.pair();e.roll_damage=lambda *args,**kwargs:11
  first=dict(kind="attack",who=b,attacker=a,turns=1,move_id="struggle")
  second=dict(kind="attack",who=b,attacker=a,turns=1,move_id="struggle")
  e.delayed=[first,second]
  with self.assertRaises(H.HeavyPending):EXT.end_of_turn(e,b)
  p=e._heavy_events[e._heavy_pending]
  self.assertEqual(p["producer"],"EXT.end_of_turn.delayed_attack")
  self.assertEqual(b.hp,39);self.assertEqual(len(e.delayed),1);self.assertIs(e.delayed[0],second)
  self.assertEqual(second["turns"],1)
 def test_004_nonheavy_attack_keeps_existing_path(self):
  e,a,b=self.pair(3);dealt=e.use_move(a,b,"struggle",set_damage=True)
  self.assertEqual(dealt,11);self.assertEqual(b.hp,39);self.assertIsNone(e._heavy_pending)
  self.assertEqual(next(iter(e._heavy_events.values()))["status"],"not_applicable")
 def test_005_bare_damage_not_fabricated_attack_provenance(self):
  e,a,b=self.pair();e.take_damage(b,3)
  self.assertEqual(b.hp,47);self.assertFalse(e._heavy_events)
 def test_006_plain_hp_loss_not_attack_event(self):
  e,a,b=self.pair();e.lose_hp(b,3,source="test-only nonattack")
  self.assertEqual(b.hp,47);self.assertFalse(e._heavy_events)
 def test_007_original_cap_preserved_and_composition_held(self):
  e,a,b=self.pair();b.damage_cap={"value":2};p=self.pending(e,a,b)
  self.assertEqual(b.hp,48);self.assertEqual(p["amount"],11)
  self.assertIn("cap_composition_unresolved",p["issues"])
 def test_008_four_to_five_injury_sampling_held(self):
  e,a,b=self.pair(4);b.hp=b.base_max_hp//2+5;expected=b.hp-11;p=self.pending(e,a,b)
  self.assertEqual((p["before"]["injuries"],p["observed_after"]["injuries"]),(4,5))
  self.assertEqual(b.hp,expected);self.assertIn("injury_count_sampling_unresolved",p["issues"])
 def test_009_original_faint_preserved_without_extra_loss(self):
  e,a,b=self.pair();b.hp=3;p=self.pending(e,a,b)
  self.assertEqual(b.hp,-8);self.assertTrue(b.fainted)
  self.assertIn("incapacitation_order_unresolved",p["issues"])
 def test_010_original_temp_absorption_preserved(self):
  e,a,b=self.pair();b.temp_hp=12;p=self.pending(e,a,b)
  self.assertEqual((b.hp,b.temp_hp),(50,1))
  self.assertEqual(p["before"]["temporary_hp"],12)
 def test_011_pending_blocks_action_turn_round_and_time(self):
  e,a,b=self.pair();self.pending(e,a,b)
  for operation in (lambda:e.use_move(a,b,"struggle"),lambda:e.start_of_turn(b),
                    lambda:e.end_of_turn(a),lambda:e.start_round([a,b]),e.end_round,
                    lambda:e.begin_encounter([a,b]),lambda:e.end_encounter([a,b]),
                    lambda:e.end_scene([a,b]),lambda:e.advance_time(1)):
   before=(a.hp,b.hp,e.round_no,e.elapsed_seconds,copy.deepcopy(a.budget))
   with self.assertRaises(H.HeavyPending):operation()
   self.assertEqual((a.hp,b.hp,e.round_no,e.elapsed_seconds,a.budget),before)
 def test_012_pending_blocks_cost_reservation(self):
  e,a,b=self.pair();self.pending(e,a,b);before=copy.deepcopy(a.budget)
  with self.assertRaises(H.HeavyPending):TURN.spend(e,a,"shift")
  self.assertEqual(a.budget,before)
 def test_013_fx_handler_exception_propagates_no_later_effect(self):
  e,a,b=self.pair()
  def hit(engine,attacker,target,effect,ctx):
   engine.resolve_attack_damage(attacker,target,engine.r.move("struggle"),set_damage=True)
  def later(engine,attacker,target,effect,ctx):target.counters["should_not_run"]=1
  prior={k:FX.HANDLERS.get(k) for k in ("test_only_heavy_hit","test_only_later")}
  FX.HANDLERS["test_only_heavy_hit"]=hit;FX.HANDLERS["test_only_later"]=later
  try:
   with self.assertRaises(H.HeavyPending):
    FX.run_effects(e,a,b,[{"type":"test_only_heavy_hit"},{"type":"test_only_later"}],
                   {"attacker":a,"target":b,"engine":e},"test-only/propagation")
  finally:
   for k,v in prior.items():
    if v is None:FX.HANDLERS.pop(k,None)
    else:FX.HANDLERS[k]=v
  self.assertEqual(b.hp,39);self.assertNotIn("should_not_run",b.counters)
 def test_014_pending_reentry_does_not_run_first_handler(self):
  e,a,b=self.pair();self.pending(e,a,b)
  with self.assertRaises(H.HeavyPending):
   FX.run_effects(e,a,b,[{"type":"stage_change","stat":"atk","delta":1,"target":"target"}],{},"test-only")
  self.assertEqual(b.stages["atk"],0)
 def test_015_resolution_rejects_same_values_wrong_actor(self):
  e,a,b=self.pair();p=self.pending(e,a,b)
  wrong=Combatant(self.rules,dict(b.spec));wrong.hp=b.hp;wrong.injuries=b.injuries
  with self.assertRaises(ValueError):self.ack(e,wrong,p)
  self.assertEqual(e._heavy_pending,p["event_id"])
 def test_016_resolution_requires_reason_disposition_and_state(self):
  e,a,b=self.pair();p=self.pending(e,a,b)
  for change in (dict(ruling=""),dict(disposition="resume"),dict(continuation_reason=""),
                 dict(expected_current_state=dict(H.observe(b),hp=40))):
   with self.assertRaises(ValueError):self.ack(e,b,p,**change)
  self.assertEqual(b.hp,39);self.assertFalse(e._heavy_resolution_history)
 def test_017_explicit_external_ruling_is_not_automatic_hp_application(self):
  e,a,b=self.pair();p=self.pending(e,a,b)
  e.gm.set_hp(b,value=34,reason="TEST-ONLY externally adjudicated HP")
  receipt=self.ack(e,b,p)
  self.assertEqual(b.hp,34);self.assertIsNone(e._heavy_pending)
  self.assertFalse(receipt["source_conformance_proven"])
  self.assertEqual(receipt["original_after"]["hp"],39)
  self.assertEqual(receipt["adjudicated_state"]["hp"],34)
  with self.assertRaises(ValueError):self.ack(e,b,p)
  self.assertEqual(b.hp,34);self.assertEqual(len(e._heavy_resolution_history),1)
 def test_018_pending_snapshot_keeps_exact_target_identity(self):
  e,a,b=self.pair();p=self.pending(e,a,b);event_id=p["event_id"]
  e.everyone=e.gm.everyone=[a] # Event ledger is now the only target reference.
  e.gm.snapshot("pending");b.hp=1;e.gm.restore("pending")
  self.assertIs(e._heavy_events[event_id]["target"],b)
  self.assertEqual(b.hp,39);self.assertEqual(e._heavy_pending,event_id)
 def test_019_resolved_snapshot_does_not_allow_duplicate_resolution(self):
  e,a,b=self.pair();p=self.pending(e,a,b);self.ack(e,b,p);e.gm.snapshot("resolved")
  e._heavy_events[p["event_id"]]["status"]="pending";e._heavy_pending=p["event_id"]
  e.gm.restore("resolved")
  self.assertIsNone(e._heavy_pending)
  with self.assertRaises(ValueError):self.ack(e,b,e._heavy_events[p["event_id"]])
  self.assertEqual(len(e._heavy_resolution_history),1)
 def test_020_rewind_before_attack_replays_once_in_restored_branch(self):
  e,a,b=self.pair();e.gm.snapshot("before")
  first=self.pending(e,a,b);self.ack(e,b,first)
  e.gm.restore("before");self.assertEqual(b.hp,50)
  self.assertFalse(e._heavy_events);self.assertFalse(e._heavy_resolution_history)
  second=self.pending(e,a,b)
  self.assertEqual(second["event_id"],first["event_id"]);self.assertEqual(b.hp,39)
  self.assertEqual(len(e._heavy_events),1)
 def test_021_repeated_restore_pending_ledger_isolated(self):
  e,a,b=self.pair();p=self.pending(e,a,b);e.gm.snapshot("pending")
  self.ack(e,b,p);e.gm.restore("pending")
  self.assertEqual(e._heavy_events[p["event_id"]]["status"],"pending")
  self.assertFalse(e._heavy_resolution_history)
  self.ack(e,b,e._heavy_events[p["event_id"]]);e.gm.restore("pending")
  self.assertEqual(e._heavy_events[p["event_id"]]["status"],"pending")
 def test_022_raw_massive_candidate_near_threshold_held(self):
  e,a,b=self.pair(4);b.hp=90;b.temp_hp=60;e.roll_damage=lambda *args,**kwargs:65
  p=self.pending(e,a,b)
  self.assertEqual((b.hp,b.temp_hp,b.injuries),(85,0,4))
  self.assertIn("raw_massive_damage_threshold_requires_review",p["issues"])
 def test_023_delayed_actor_identity_restored(self):
  e,a,b=self.pair();e.everyone=e.gm.everyone=[b]
  e.delayed=[dict(kind="attack",who=b,attacker=a,turns=1,move_id="struggle")]
  e.roll_damage=lambda *args,**kwargs:11
  with self.assertRaises(H.HeavyPending):EXT.end_of_turn(e,b)
  event_id=e._heavy_pending;e.gm.snapshot("delayed");e.gm.restore("delayed")
  self.assertIs(e._heavy_events[event_id]["attacker"],a)
  self.assertIs(e._heavy_events[event_id]["target"],b)
 def test_024_stale_state_resolution_rejected(self):
  e,a,b=self.pair();p=self.pending(e,a,b);stale=H.observe(b);b.hp=38
  with self.assertRaises(ValueError):self.ack(e,b,p,expected_current_state=stale)
  self.assertEqual(e._heavy_pending,p["event_id"]);self.assertEqual(b.hp,38)
 def test_025_packet_clock_and_provenance_not_game_authority(self):
  e,a,b=self.pair();p=self.pending(e,a,b)
  self.assertIs(p["attacker"],a);self.assertIs(p["target"],b)
  self.assertEqual((p["round"],p["elapsed_seconds"]),(1,0))
  self.assertEqual(p["context"],"unknown")
  self.assertIn("production_effect_interactions_not_proven",p["issues"])
 def test_027_native_struggle_applies_source_local_loss(self):
  for injuries in (5,7):
   e,a,b=self.pair(injuries,certified=True)
   dealt=e.use_move(a,b,"struggle",set_damage=True)
   p=next(iter(e._heavy_events.values()))
   self.assertEqual(dealt,11);self.assertEqual(b.hp,50-11-injuries)
   self.assertEqual(b.injuries,injuries);self.assertIsNone(e._heavy_pending)
   self.assertEqual(p["status"],"applied");self.assertEqual(p["context_evidence"]["failures"],[])
   self.assertEqual(p["heavy_consequence"]["kind"],"hp_loss")
   self.assertFalse(p["heavy_consequence"]["recursive_attack"])
   self.assertEqual(p["heavy_consequence"]["order_claim"],"both_restricted_orders_agree")
 def test_028_native_partial_temp_absorption_then_local_loss(self):
  e,a,b=self.pair(certified=True);b.temp_hp=3
  e.use_move(a,b,"struggle",set_damage=True)
  self.assertEqual((b.hp,b.temp_hp,b.injuries),(37,0,5))
  self.assertEqual(len(e._heavy_events),1)
 def test_029_context_proof_rejects_each_uninspected_effect_channel(self):
  changes=[lambda e,a,b:b.registry.append({"type":"test_only_opaque"}),
           lambda e,a,b:b.ability_triggers.append({"name":"test-only"}),
           lambda e,a,b:b.modifiers.append({"test_only":True}),
           lambda e,a,b:b.conditions.add("test-only"),
           lambda e,a,b:setattr(b,"item","test-only"),
           lambda e,a,b:setattr(b,"reflect",{"test_only":True}),
           lambda e,a,b:setattr(e,"weather","test-only"),
           lambda e,a,b:e.rulings.hooks["before_damage"].append(dict(fn=lambda v,c:v,reason="test-only")),
           lambda e,a,b:a.spec.update(feats=["test-only"]),
           lambda e,a,b:setattr(a,"injuries",5)]
  for change in changes:
   e,a,b=self.pair(certified=True);change(e,a,b)
   receipt=H.certify_native_context(e,a,b,e.r.move("struggle"),{},ordinary_single=True)
   self.assertTrue(receipt.failures)
 def test_030_heavy_attacker_and_target_require_unresolved_activation_ruling(self):
  e,a,b=self.pair(certified=True);a.injuries=5;rng=e.rng.getstate();p=self.pending(e,a,b)
  # The Standard extension observes activation but does not certify commit or
  # continue accuracy/damage in this interacting two-heavy-actor context.
  self.assertEqual((a.hp,b.hp),(50,50));self.assertEqual(e.rng.getstate(),rng)
  self.assertEqual(p["kind"],"activation_observed");self.assertFalse(p["semantic_commit_proven"])
  self.assertIsNone(p["actual_action_count"]);self.assertEqual(a.move_uses['struggle'],1)
  self.assertEqual(a.budget['standard'],0);self.assertEqual(len(e._heavy_events),1)
 def test_031_direct_primary_call_lacks_outer_activation_receipt(self):
  e,a,b=self.pair(certified=True)
  with self.assertRaises(H.HeavyPending):e.resolve_attack_damage(a,b,e.r.move("struggle"),set_damage=True)
  self.assertEqual(b.hp,39)
 def test_032_certified_context_still_respects_kernel_marker_pending(self):
  e,a,b=self.pair(7,certified=True);b.hp=b.base_max_hp//2+16;p=self.pending(e,a,b)
  self.assertEqual(b.hp,b.base_max_hp//2+5);self.assertEqual(b.injuries,7)
  self.assertEqual(p["context"],"certified_native_single");self.assertEqual(p["kernel_status"],"pending")
 def test_033_native_context_is_target_bound(self):
  e,a,b=self.pair(certified=True)
  receipt=H.certify_native_context(e,a,a,e.r.move("struggle"),{},ordinary_single=True)
  with self.assertRaises(ValueError):e.resolve_attack_damage(a,b,e.r.move("struggle"),set_damage=True,_heavy_context=receipt)
  self.assertEqual(b.hp,50)
 def test_034_actual_receipt_single_use_inside_activation(self):
  e,a,b=self.pair(certified=True);original=Engine.resolve_attack_damage;captured=[]
  def probe(engine,attacker,target,move,*args,**kwargs):
   token=kwargs.get("_heavy_context");captured.append(token)
   result=original(engine,attacker,target,move,*args,**kwargs)
   with self.assertRaises(ValueError):original(engine,attacker,target,move,*args,**kwargs)
   return result
  with mock.patch.object(Engine,"resolve_attack_damage",probe):
   e.use_move(a,b,"struggle",set_damage=True)
  self.assertEqual(b.hp,34);self.assertFalse(e._heavy_native_receipts)
  with self.assertRaises(ValueError):original(e,a,b,e.r.move("struggle"),set_damage=True,_heavy_context=captured[0])
  self.assertEqual(b.hp,34)
 def test_035_pending_fire_event_does_not_consume_frequency(self):
  e,a,b=self.pair();self.pending(e,a,b)
  a.ability_triggers=[dict(name="test-only-pending-frequency",spec={"event":"test-only"},
      frequency={"kind":"daily","uses":1},effects=[{"type":"stage_change","stat":"atk","delta":1}])]
  before=copy.deepcopy(a.counters)
  with self.assertRaises(H.HeavyPending):FX.fire_event(e,a,{"event":"test-only"},b)
  self.assertEqual(a.counters,before)
 def test_036_pending_use_move_on_does_not_replace_roster(self):
  e,a,b=self.pair();self.pending(e,a,b);roster=e.everyone
  with self.assertRaises(H.HeavyPending):e.use_move_on(a,b,"struggle",[a])
  self.assertIs(e.everyone,roster);self.assertEqual(e.everyone,[a,b])
 def test_037_diagnostic_cannot_issue_activation_authority(self):
  e,a,b=self.pair(certified=True);receipt=H.certify_native_context(e,a,b,e.r.move("struggle"),{},ordinary_single=True)
  self.assertFalse(receipt.failures);before=copy.deepcopy(a.budget)
  for _ in range(2):
   with self.assertRaises(ValueError):e.resolve_attack_damage(a,b,e.r.move("struggle"),set_damage=True,_heavy_context=receipt)
  self.assertEqual(b.hp,50);self.assertEqual(a.budget,before);self.assertEqual(a.move_uses,{})
  self.assertFalse(e._heavy_events)
 def test_038_encounter_returns_incomplete_without_turn_or_time_finish(self):
  import encounter as ENC
  e,a,b=self.pair();e._active_turn_actor=None;e._ordinary_turn_rounds={};e.round_no=0;e.round_start_seconds=None;e.encounter_active=False
  e.initiative=lambda actors:[a,b]
  with mock.patch.object(ENC,"load_encounter",return_value=(e,{"name":"test-only-heavy","rounds":2},[a],[b])), mock.patch.object(ENC,"choose_action",return_value=("move","struggle",b)):
   got,party,wild=ENC.run_encounter(str(ROOT),"test-only",write=False)
  self.assertIs(got,e);self.assertEqual(e._heavy_driver_result["status"],"incomplete")
  self.assertEqual(e.elapsed_seconds,0);self.assertEqual(e.round_no,1)
  self.assertIs(e._active_turn_actor,a);self.assertTrue(e.encounter_active)
  self.assertFalse(any("파티 승리" in line for line in e.log_lines))
 def test_039_scenario_returns_incomplete_from_hook(self):
  import engine as E
  def hook(e,c,rnd):
   target=next(x for x in e.gm.everyone if x is not c);target.hp=50;target.injuries=5
   e.roll_damage=lambda *args,**kwargs:11
   e.resolve_attack_damage(c,target,e.r.move("struggle"),set_damage=True)
  with mock.patch.object(Engine,"initiative",lambda e,actors:list(actors)):
   e=E.scenario(str(ROOT),1,ruleset="core",hook=hook)
  self.assertEqual(e._heavy_driver_result["status"],"incomplete")
  self.assertEqual(e.elapsed_seconds,0);self.assertEqual(e.round_no,1)
  self.assertTrue(e.encounter_active);self.assertFalse(any(line=="## 결과" for line in e.log_lines))
 def test_040_isolated_cli_import_path(self):
  command="import runpy;runpy.run_path("+repr(str(ROOT/"engine/engine.py"))+",run_name='isolated_import_check')"
  p=subprocess.run([sys.executable,"-B","-I","-X","utf8","-c",command],capture_output=True,text=True,encoding="utf8")
  self.assertEqual(p.returncode,0,p.stderr)
 def test_041_receipt_epoch_bound_before_damage(self):
  e,a,b=self.pair(certified=True);original=Engine.resolve_attack_damage
  def probe(engine,attacker,target,move,*args,**kwargs):
   engine.round_no+=1
   try:
    with self.assertRaises(ValueError):original(engine,attacker,target,move,*args,**kwargs)
   finally:engine.round_no-=1
   return 0
  with mock.patch.object(Engine,"resolve_attack_damage",probe):e.use_move(a,b,"struggle",set_damage=True)
  self.assertEqual(b.hp,50);self.assertFalse(e._heavy_events);self.assertFalse(e._heavy_native_receipts)
 def test_042_counted_massive_below_five_does_not_create_pending(self):
  for producer in (H.Producer.RESOLVED_HIT,H.Producer.SECOND_HIT):
   e,a,b=self.pair(injuries=2);b.hp=b.base_max_hp//2-1
   amount=b.base_max_hp//2+1
   H.apply_attack_damage(e,a,b,amount,e.r.move("struggle"),producer=producer,remainder="test-only continuation")
   self.assertEqual(b.injuries,4);self.assertTrue(b.fainted)
   self.assertIsNone(e._heavy_pending)
   self.assertEqual(next(iter(e._heavy_events.values()))["status"],"not_applicable")
 def test_043_absorbed_massive_below_five_still_requires_review(self):
  e,a,b=self.pair(injuries=4);b.hp=b.base_max_hp-10;b.temp_hp=60
  with self.assertRaises(H.HeavyPending):
   H.apply_attack_damage(e,a,b,65,e.r.move("struggle"),producer=H.Producer.RESOLVED_HIT,remainder="test-only continuation")
  self.assertEqual(b.injuries,4);self.assertEqual(b.temp_hp,0)
  self.assertIn("raw_massive_damage_threshold_requires_review",e._heavy_events[e._heavy_pending]["issues"])
 def test_026_runtime_source_identity_index_present(self):
  self.assertTrue((ROOT/"output/ruleunits.jsonl").is_file())
  self.assertEqual(self.rules._selected_rule("item/상처약"),"item/상처약")

 def test_044_attack_log_sink_observer_does_not_certify_local_loss(self):
  e,a,b=self.pair(certified=True);seen=[]
  class HPLog(list):
   def append(self,line):
    if 'DB 4 지정 데미지' in line:
     seen.append(b.hp)
     if b.hp>47:b.stats['def']=0
    super().append(line)
  e.log_lines=HPLog(e.log_lines)
  with self.assertRaises(H.HeavyPending):e.use_move(a,b,'struggle',set_damage=True)
  self.assertEqual(seen,[50]);self.assertEqual(b.hp,9)
  p=e._heavy_events[e._heavy_pending]
  self.assertEqual(p['status'],'pending');self.assertNotIn('heavy_consequence',p)
  self.assertIn('noncanonical_log_sink',p['context_evidence']['failures'])
 def test_045_shared_passive_contract_rejects_attack_name_and_registry_observers(self):
  for field,value in [('name',type('ObservedName',(str,),{})('target')),
                      ('registry',type('ObservedRegistry',(list,),{})())]:
   e,a,b=self.pair(certified=True);setattr(b,field,value)
   p=self.pending(e,a,b)
   self.assertEqual(b.hp,39)
   self.assertIn('target:nonpassive_state:'+field,p['context_evidence']['failures'])
   self.assertEqual(p['status'],'pending')
 def test_046_below_threshold_skips_expensive_proof_without_granting_certificate(self):
  e,a,b=self.pair(injuries=0,certified=True)
  with mock.patch.object(H,'passive_prefix_failures',side_effect=AssertionError('unneeded full data scan')):
   certificate=H.certify_native_context(e,a,b,e.r.move('struggle'),{},ordinary_single=True)
   self.assertEqual(certificate.failures,('below_threshold_pair_not_certified',))
   e.use_move(a,b,'struggle',set_damage=True)
  self.assertEqual(b.hp,39);self.assertIsNone(e._heavy_pending)
  b.injuries=type('ObservedInt',(int,),{})(0)
  with mock.patch.object(H,'passive_prefix_failures',return_value=['test observer boundary']) as scan:
   certificate=H.certify_native_context(e,a,b,e.r.move('struggle'),{},ordinary_single=True)
  self.assertEqual(scan.call_count,1)
  self.assertIn('test observer boundary',certificate.failures)
class Results(unittest.TextTestResult):
 def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
 def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id="HEAVY-PRODUCTION-"+t._testMethodName,status="pass"))
 def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id="HEAVY-PRODUCTION-"+t._testMethodName,status="fail",detail=self._exc_info_to_string(e,t)))
 def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id="HEAVY-PRODUCTION-"+t._testMethodName,status="error",detail=self._exc_info_to_string(e,t)))
if __name__=="__main__":
 def tracing(original):
  def read(file,mode="r",*args,**kwargs):
   if "r" in mode or "+" in mode:
    try:
     path=pathlib.Path(file).resolve()
     if path.is_relative_to(ROOT) and path.is_file():READ_INPUTS.add(path)
    except (TypeError,ValueError,OSError):pass
   return original(file,mode,*args,**kwargs)
  return read
 original_open,original_io=builtins.open,io.open
 builtins.open,io.open=tracing(original_open),tracing(original_io)
 try:result=unittest.TextTestRunner(verbosity=2,resultclass=Results).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 finally:builtins.open,io.open=original_open,original_io
 files=set(READ_INPUTS)
 for module in list(sys.modules.values()):
  file=getattr(module,"__file__",None)
  if file:
   path=pathlib.Path(file).resolve()
   if path.is_relative_to(ROOT/"engine") and path.suffix==".py":files.add(path)
 files.update([pathlib.Path(__file__),ROOT/"input/ch07-combat.md"])
 files=sorted(files)
 report=dict(generated_at=datetime.now(timezone.utc).isoformat(),tests_run=result.testsRun,results=result.rows,
             input_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
             scope="Production attack paths and fail-closed pending; certified native single attack applies local loss; unknown contexts pending; restricted native Standard integration; general action commitment unresolved",semantic_closure=False)
 (ROOT/"output/heavy-production-tests.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
 sys.exit(0 if result.wasSuccessful() else 1)
