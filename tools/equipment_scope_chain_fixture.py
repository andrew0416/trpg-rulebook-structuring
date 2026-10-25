"""Actual legacy armor worlds passed from successful binding to corrupt-import checks."""
import unittest
from chained_case_lifecycle import bind_case_lifecycle, defer_case_commit

METHODS = (
    "test_legacy_active_json_binds_once_preserves_receipts_and_later_battle_unlocks",
    "test_corrupt_scope_and_receipt_shapes_are_rejected_by_json_and_gm_without_commit",
)


def prepare_cases(cls, cases):
    selected = [case for case in cases if case._testMethodName in METHODS]
    if {case._testMethodName for case in selected} != set(METHODS):
        return None
    if len(selected) != len(METHODS) or any(type(case) is not cls for case in selected):
        raise ValueError("each equipment stage must be selected exactly once")
    if any(hasattr(case, "_equipment_chain") for case in selected):
        raise ValueError("equipment cases already connected")
    by_name = {case._testMethodName: case for case in selected}
    stages = tuple(by_name[name] for name in METHODS)
    context = {"next_stage": 0, "case_ids": tuple(case.id() for case in stages)}
    for case in stages:
        case._equipment_chain = context
        bind_case_lifecycle(case, lambda reason: context.setdefault("blocked", reason))
    ordered = []
    for case in cases:
        if case._testMethodName in METHODS:
            if case is selected[0]:
                ordered.extend(stages)
        else:
            ordered.append(case)
    return ordered


def enter(test):
    context = getattr(test, "_equipment_chain", None)
    if context is None:
        return False
    stage = METHODS.index(test._testMethodName)
    test.assertEqual(context["case_ids"][stage], test.id())
    if context.get("blocked") or context["next_stage"] != stage:
        raise unittest.SkipTest("equipment predecessor unverified: " + str(context.get("blocked", context["next_stage"])))
    if stage:
        test.r = context["rules"]
        test.f = context["helper"]
        return True
    return False


def complete(test, stage, worlds):
    context = getattr(test, "_equipment_chain", None)
    if context is None:
        return
    test.assertEqual(context["next_stage"], stage)
    completed = {"next_stage": stage + 1, "worlds": worlds,
                 "rules": test.r, "helper": test.f}
    if stage == 0:
        completed["producer_objects"] = tuple((id(e), id(a), id(t), id(e._physical_objects[uid]))
                                               for e, a, t, uid in worlds.values())
    defer_case_commit(test, lambda: context.update(completed))


def matrix_inputs(test, items):
    context = getattr(test, "_equipment_chain", None)
    if context is not None:
        worlds = context["worlds"]
        identities = tuple((id(e), id(a), id(t), id(e._physical_objects[uid]))
                           for e, a, t, uid in worlds.values())
        test.assertEqual(identities, context["producer_objects"])
        context["consumer_objects"] = identities
        return worlds
    # Isolated B constructs only O_A's native state, without replaying A's checks
    # or its later redundant round trips. The legacy import remains a cold load.
    worlds = {}
    for item in items:
        engine, actor, target, uid = test.legacy_used(item, sessions=True)
        engine = test.restore(engine)
        actor, target = test.actual(engine, actor), test.actual(engine, target)
        engine.apply_status(actor, "구속", source="gm/repair", applied_by=target)
        test.assertEqual(engine.begin_session("session-two", [actor, target]), "refreshed")
        actor.spec["frequency_state"]["scene"] += 1
        test.next_battle(engine, actor, target)
        test.assertTrue(__import__("equipment_variant_contracts").activate_slipstream(engine, actor)["activated"])
        engine.apply_status(actor, "구속", source="gm/repair", applied_by=target)
        worlds[item] = (engine, actor, target, uid)
    return worlds
