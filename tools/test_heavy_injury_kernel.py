"""Independent pure-kernel arithmetic/boundary oracles; no whole-runtime proof."""
import argparse, hashlib, json, pathlib, sys, unittest
from dataclasses import replace
from datetime import datetime, timezone
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "engine"))
from heavy_injury_kernel import State, Event, Snapshot, Proposal, Kind, Action, Context, evaluate
FINITE_CASES = 0

def standard(state=None, **changes):
    state = state or State(50, 0, 5, 110)
    values = dict(event_id="event-1", kind=Kind.ACTION_TAKEN,
                  before=state, after=state, action=Action.STANDARD, in_combat=True,
                  context=Context.NO_OTHER_INTERACTIONS, prevention_or_cap=False)
    values.update(changes)
    return Event(**values)

def attack(before=None, **changes):
    before = before or State(50, 0, 5, 110)
    values = dict(event_id="attack-1", kind=Kind.ATTACK_DAMAGE, before=before,
                  after=replace(before, hp=39), damage=11, in_combat=True,
                  context=Context.NO_OTHER_INTERACTIONS, prevention_or_cap=False)
    values.update(changes)
    return Event(**values)

def run(event, seen=frozenset()):
    return evaluate(Snapshot(event.after, seen), event)

def unit_subtract(hp, temp, count):
    # Independent unit-step oracle; intentionally does not call kernel helpers.
    for _ in range(count):
        if temp:
            temp -= 1
        else:
            hp -= 1
    return hp, temp

class KernelTests(unittest.TestCase):
    def test_001_stable_standard_trainers_and_pokemon(self):
        for actor in ("trainer", "pokemon"):
            for injuries in (5, 7):
                event = standard(State(50, 0, injuries, 110, actor))
                got = run(event)
                self.assertEqual(got.status, "ready")
                self.assertEqual(got.snapshot.state.hp, 50-injuries)
                self.assertEqual(got.loss, injuries)
    def test_002_reservation_is_not_action(self):
        got = run(standard(kind=Kind.COST_RESERVED))
        self.assertEqual((got.status, got.snapshot.state.hp), ("not_applicable", 50))
    def test_003_pure_hp_loss_does_not_trigger(self):
        event = standard(kind=Kind.HP_LOSS, after=State(47, 0, 5, 110))
        self.assertEqual(run(event).status, "not_applicable")
    def test_004_stable_positive_attack(self):
        got = run(attack())
        self.assertEqual((got.status, got.snapshot.state.hp), ("ready", 34))
    def test_005_standard_requires_combat(self):
        self.assertEqual(run(standard(in_combat=False)).status, "not_applicable")
        self.assertEqual(run(standard(in_combat=None)).status, "pending")
    def test_006_attack_noncombat_scope_remains_pending(self):
        self.assertEqual(run(attack(in_combat=True)).snapshot.state.hp, 34)
        for combat in (False, None):
            got = run(attack(in_combat=combat))
            self.assertEqual(got.reason, "attack_outside_combat_scope_unresolved")
            self.assertEqual(got.snapshot.state.hp, 39)
    def test_007_below_threshold(self):
        self.assertEqual(run(standard(State(50, 0, 4, 110))).status, "not_applicable")
    def test_008_temp_hp_absorbs_other_effect(self):
        got = run(standard(State(50, 12, 5, 110)))
        self.assertEqual((got.status, got.snapshot.state.hp, got.snapshot.state.temporary_hp),
                         ("ready", 50, 7))
    def test_009_temp_overflow(self):
        got = run(standard(State(50, 3, 5, 110)))
        self.assertEqual((got.snapshot.state.hp, got.snapshot.state.temporary_hp), (48, 0))
    def test_010_partial_absorbed_attack_both_orders(self):
        event = attack(State(50, 3, 5, 110), after=State(42, 0, 5, 110))
        got = run(event)
        self.assertEqual((got.status, got.snapshot.state.hp), ("ready", 37))
    def test_011_fully_absorbed_attack_remains_pending(self):
        event = attack(State(50, 12, 5, 110), after=State(50, 1, 5, 110))
        self.assertEqual(run(event).reason, "fully_absorbed_attack_trigger_unresolved")
    def test_012_zero_damage_not_forced_into_trigger(self):
        before = State(50, 0, 5, 110)
        self.assertEqual(run(attack(before, after=before, damage=0)).status, "pending")
    def test_013_count_changed_four_to_five_or_five_to_six(self):
        for old, new in ((4,5), (5,6), (6,5)):
            event = attack(State(50, 0, old, 110), after=State(39, 0, new, 110))
            got = run(event)
            self.assertEqual(got.reason, "injury_count_sampling_unresolved")
            self.assertEqual(got.snapshot.state, event.after)
    def test_014_standard_actor_effects_are_pending(self):
        event = standard(after=State(49, 0, 5, 110))
        self.assertEqual(run(event).reason, "action_effect_changes_actor_state")
    def test_015_standard_loss_faint_is_pending_without_choice(self):
        event = standard(State(3, 0, 5, 110))
        got = run(event)
        self.assertEqual(got.reason, "loss_would_incapacitate_actor")
        self.assertEqual(got.snapshot.state.hp, 3)
    def test_016_attack_loss_faint_is_pending_without_choice(self):
        event = attack(State(15, 0, 5, 110), after=State(4, 0, 5, 110))
        self.assertEqual(run(event).reason, "ordering_involves_incapacitation")
    def test_017_loss_marker_boundary_pending(self):
        got = run(standard(State(57, 0, 5, 110)))
        self.assertEqual(got.reason, "loss_crosses_injury_marker")
        self.assertEqual(got.snapshot.state.injuries, 5)
    def test_018_odd_max_marker_no_invented_rounding(self):
        got = run(standard(State(56, 0, 5, 111)))
        self.assertEqual(got.reason, "loss_crosses_injury_marker")
    def test_019_cap_or_prevention_not_bypassed(self):
        for cap in (True, None):
            event = standard(prevention_or_cap=cap)
            got = run(event)
            self.assertEqual(got.reason, "prevention_or_cap_composition_unresolved")
            self.assertEqual(got.snapshot.state.hp, 50)
    def test_020_unknown_interactions_default_pending(self):
        event = Event("minimal", Kind.ACTION_TAKEN, State(50,0,5,110),
                      State(50,0,5,110), action=Action.STANDARD, in_combat=True)
        self.assertEqual(run(event).reason, "other_effect_interactions_unknown")
    def test_021_duplicate_event_not_applied_twice(self):
        event = standard()
        first = run(event)
        second = evaluate(first.snapshot, event)
        self.assertEqual(second.reason, "event_already_applied")
        self.assertEqual(second.snapshot.state.hp, 45)
    def test_022_followup_hp_loss_nonrecursive(self):
        first = run(standard())
        consequence = Event("loss-child", Kind.HP_LOSS, State(50,0,5,110),
                            first.snapshot.state)
        second = evaluate(first.snapshot, consequence)
        self.assertEqual(second.status, "not_applicable")
        self.assertEqual(second.snapshot.state.hp, 45)
    def test_023_immutable_snapshot_replay(self):
        event = standard()
        saved = Snapshot(event.after)
        first = evaluate(saved, event)
        replay = evaluate(saved, event)
        self.assertEqual(first, replay)
        self.assertEqual(saved.state.hp, 50)
        self.assertFalse(saved.applied_event_ids)
    def test_024_pending_does_not_consume_event(self):
        event = standard(context=Context.UNKNOWN)
        got = run(event)
        self.assertFalse(got.snapshot.applied_event_ids)
        fixed_evidence = replace(event, context=Context.NO_OTHER_INTERACTIONS)
        self.assertEqual(evaluate(got.snapshot, fixed_evidence).status, "ready")
    def test_025_state_drift_not_silently_applied(self):
        got = evaluate(Snapshot(State(40,0,5,110)), standard())
        self.assertEqual(got.reason, "observed_state_does_not_match_event")
    def test_026_full_action_not_relabelled_standard(self):
        self.assertEqual(run(standard(action=Action.FULL)).status, "pending")
        self.assertEqual(run(standard(action=Action.FREE)).status, "not_applicable")
        for kind in (Action.SHIFT, Action.SWIFT):
            self.assertEqual(run(standard(action=kind)).status, "pending")
            self.assertEqual(run(standard(action=kind, paid_resource=kind)).status, "not_applicable")
    def test_027_typed_input_rejects_bool_or_fabricated_kind(self):
        for make in (lambda: State(True,0,5,110), lambda: State(50,-1,5,110),
                     lambda: standard(kind="attack"), lambda: attack(damage=True),
                     lambda: standard(in_combat=1), lambda: standard(event_id="")):
            with self.assertRaises(ValueError):
                make()
    def test_028_attack_marker_change_cannot_be_hidden(self):
        event = attack(State(60,0,5,110), after=State(49,0,5,110))
        self.assertEqual(run(event).reason, "attack_crosses_injury_marker")
    def test_029_finite_unit_step_oracle(self):
        global FINITE_CASES
        for injuries in range(5,10):
            for hp in range(11,51):
                for temp in range(10):
                    for damage in range(1,9):
                        after_hp, after_temp = unit_subtract(hp,temp,damage)
                        before = State(hp,temp,injuries,110)
                        event = attack(before, after=State(after_hp,after_temp,injuries,110),
                                       damage=damage)
                        got = run(event)
                        expected_hp, expected_temp = unit_subtract(after_hp,after_temp,injuries)
                        if damage <= temp or expected_hp <= 0:
                            self.assertEqual(got.status, "pending")
                        else:
                            self.assertEqual(got.status, "ready")
                            self.assertEqual((got.snapshot.state.hp,got.snapshot.state.temporary_hp),
                                             (expected_hp,expected_temp))
                            self.assertEqual(got.snapshot.state.injuries, injuries)
                        FINITE_CASES += 1
    def test_031_massive_damage_not_hidden_by_stable_count_claim(self):
        event = attack(State(150,0,5,110), after=State(90,0,5,110), damage=60)
        self.assertEqual(run(event).reason, "massive_damage_injury_evidence_unresolved")
    def test_032_kind_or_maximum_change_is_not_identity_check(self):
        for changed in (State(50,0,5,120), State(50,0,5,110,"pokemon")):
            got = run(standard(after=changed))
            self.assertEqual(got.reason, "actor_kind_or_maximum_changed")
            self.assertNotIn("identity",got.reason)
    def test_033_standard_paid_shift_or_swift_remains_pending(self):
        for kind in (Action.SHIFT,Action.SWIFT):
            for context in (Context.UNKNOWN,Context.NO_OTHER_INTERACTIONS):
                event = standard(action=kind,paid_resource=Action.STANDARD,context=context)
                got = run(event)
                self.assertEqual(got.reason,"standard_paid_substitution_consequence_unresolved")
                self.assertEqual(got.snapshot.state.hp,50)
    def test_034_massive_candidate_before_temp_absorption_pending(self):
        event = attack(State(90,60,5,110),after=State(85,0,5,110),damage=65)
        got = run(event)
        self.assertEqual(got.reason,"massive_damage_injury_evidence_unresolved")
        self.assertEqual(got.snapshot.state,State(85,0,5,110))
    def test_030_source_hashes_and_exact_anchors(self):
        review = json.loads((ROOT/"data/verification/common-hp-resource-semantics.json").read_text(encoding="utf8"))
        for anchor in review["anchors"]:
            source = ROOT/anchor["file"]
            lines = source.read_text(encoding="utf8").splitlines()
            excerpt = "\n".join(lines[anchor["start"]-1:anchor["end"]])
            self.assertEqual(excerpt,anchor["text"])
            self.assertEqual(hashlib.sha256(excerpt.encode()).hexdigest(),anchor["excerpt_sha256"])
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),anchor["file_sha256"])

class Results(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs); self.rows=[]
    def addSuccess(self,test):
        super().addSuccess(test)
        self.rows.append(dict(id="HEAVY-KERNEL-"+test._testMethodName,status="pass"))
    def addFailure(self,test,error):
        super().addFailure(test,error)
        self.rows.append(dict(id="HEAVY-KERNEL-"+test._testMethodName,status="fail",
                              detail=self._exc_info_to_string(error,test)))
    def addError(self,test,error):
        super().addError(test,error)
        self.rows.append(dict(id="HEAVY-KERNEL-"+test._testMethodName,status="error",
                              detail=self._exc_info_to_string(error,test)))

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=pathlib.Path,
                        default=ROOT/"output/heavy-injury-kernel-tests.json")
    args=parser.parse_args()
    paths=["engine/heavy_injury_kernel.py","tools/test_heavy_injury_kernel.py",
           "input/ch07-combat.md","data/verification/common-hp-resource-semantics.json"]
    hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
    result=unittest.TextTestRunner(verbosity=2,resultclass=Results).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(KernelTests))
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),tests_run=result.testsRun,
                finite_cases=FINITE_CASES,results=result.rows,input_hashes=hashes,
                production_runtime_verified=False,semantic_closure=False,
                scope="Pure kernel and exact source-anchor integrity; production event wiring tested separately.")
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    sys.exit(0 if result.wasSuccessful() else 1)
