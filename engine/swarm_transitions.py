"""Native transitions for the selected Chapter 11 swarm template.

The durable owner remains ``actor.spec['encounter_template']``.  This adapter
only mutates that selected state from actual HP, turn, action and frequency
consumers; it does not create a second runtime ledger.
"""
from copy import deepcopy


SUPPORTED_ORDINARY_OPERATIONS = {
    "start_round", "start_of_turn", "use_move", "use_move target",
    "use_move_on", "use_move_on target", "take_damage", "lose_hp",
}


def state(actor):
    row = actor.spec.get("encounter_template")
    if isinstance(row, dict) and row.get("active") is True and row.get("kind") == "swarm":
        return row
    return None


def supports(actor, operation):
    return state(actor) is not None and operation in SUPPORTED_ORDINARY_OPERATIONS


def validate(actor, row=None):
    row = state(actor) if row is None else row
    if not isinstance(row, dict) or row.get("kind") != "swarm":
        return True
    multiplier = row.get("multiplier")
    points = row.get("swarm_points")
    if type(multiplier) is not int or multiplier < 0:
        raise ValueError("swarm multiplier must be a nonnegative integer")
    if type(points) is not int or not 0 <= points <= multiplier:
        raise ValueError("swarm points cannot exceed the current multiplier")
    if type(row.get("first_standard_used")) is not bool:
        raise ValueError("swarm first-standard state must be explicit")
    turn = row.get("swarm_turn")
    if turn is not None:
        if not isinstance(turn, dict) or set(turn) != {
                "round", "key", "start_initiative", "current_initiative",
                "action_index", "minimum_action", "minimum_action_used",
                "window_used", "lifecycle", "next_initiative"}:
            raise ValueError("swarm turn receipt shape changed")
        for key in ("round", "start_initiative", "current_initiative", "action_index"):
            if type(turn[key]) is not int or turn[key] < 0:
                raise ValueError("swarm turn values must be nonnegative integers")
        if not isinstance(turn["key"], str) or not turn["key"]:
            raise ValueError("swarm turn identity required")
        if type(turn["minimum_action"]) is not bool or type(turn["minimum_action_used"]) is not bool:
            raise ValueError("swarm minimum-action flags must be explicit")
        if type(turn['window_used']) is not bool or turn['lifecycle'] not in ('open','pending','closed'):
            raise ValueError('swarm action window must have an actual lifecycle')
        if turn['next_initiative'] is not None and (type(turn['next_initiative']) is not int or turn['next_initiative'] < 0):
            raise ValueError('swarm continuation initiative must be nonnegative')
    for key, receipt in row.get("round_trigger_receipts", {}).items():
        if not isinstance(key, str) or not isinstance(receipt, dict):
            raise ValueError("swarm round receipts require identities and state maps")
        actions = receipt.get("actions", [])
        if not isinstance(actions, list):
            raise ValueError("swarm action receipts must be ordered")
        previous = None
        for action in actions:
            if (not isinstance(action, dict) or type(action.get("index")) is not int
                    or type(action.get("initiative")) is not int
                    or type(action.get("point_cost")) is not int):
                raise ValueError("swarm action receipt is incomplete")
            if previous is not None and action["initiative"] > previous:
                raise ValueError("swarm additional initiative cannot increase")
            previous = action["initiative"]
    return True


def _turn(row):
    turn = row.get("swarm_turn")
    if not isinstance(turn, dict):
        raise ValueError("swarm needs an actual opened turn")
    return turn


def start_turn(engine, actor, initiative_count=None):
    row = state(actor)
    if row is None:
        return None
    if continuation_pending(engine, actor):
        turn = _turn(row)
        if initiative_count != turn['next_initiative']:
            raise ValueError('swarm additional action requires its next initiative count')
        turn.update(current_initiative=initiative_count, next_initiative=None,
                    action_index=turn['action_index']+1, window_used=False, lifecycle='open')
        validate(actor, row)
        return deepcopy(turn)
    previous = row.get('swarm_turn')
    if isinstance(previous, dict) and previous['round'] == engine.round_no:
        raise ValueError('swarm turn already granted this round')
    if initiative_count is None:
        observed = engine.initiative_value(actor)
        initiative_count = observed.value
    if type(initiative_count) is not int or initiative_count < 0:
        raise ValueError("swarm turn needs a nonnegative actual initiative count")
    row["swarm_points"] = row["multiplier"]
    row["first_standard_used"] = False
    key = f"round:{engine.round_no}:turn:{actor.spec.get('frequency_state', {}).get('turn', 0)}"
    row["own_turn_key"] = key
    row["swarm_turn"] = {
        "round": engine.round_no, "key": key,
        "start_initiative": initiative_count, "current_initiative": initiative_count,
        "action_index": 0, "minimum_action": False, "minimum_action_used": False,
        "window_used": False, "lifecycle": "open", "next_initiative": None,
    }
    row["round_trigger_receipts"][key] = {
        "round": engine.round_no, "start_initiative": initiative_count,
        "points_granted": row["multiplier"], "condition_point_cost": 0, "actions": [],
    }
    validate(actor, row)
    return deepcopy(row["swarm_turn"])


def finish_turn_start(engine, actor):
    row = state(actor)
    if row is None:
        return None
    turn = _turn(row)
    unable = bool(actor.conditions & {"잠듦", "얼음"})
    if unable:
        cost = min(1, row["swarm_points"])
        row["swarm_points"] -= cost
        turn["minimum_action"] = True
        row["round_trigger_receipts"][turn["key"]]["condition_point_cost"] = cost
        engine.log(f"    {actor.name}: 행동불능 대신 스웜 포인트 {cost} 소비; 남은 행동 보존",
                   "C11-091/swarm-condition-action")
    validate(actor, row)
    return unable


def incapacitation_replaced(actor, *, engine=None):
    row = state(actor)
    if row is None or engine is None:return False
    turn=row.get('swarm_turn',{})
    receipt=row.get('round_trigger_receipts',{}).get(turn.get('key'))
    return bool(turn.get('minimum_action') and turn.get('lifecycle')=='open'
        and turn.get('round')==engine.round_no and engine._active_turn_actor is actor
        and row.get('own_turn_key')==turn.get('key') and isinstance(receipt,dict)
        and receipt.get('round')==engine.round_no and receipt.get('points_granted',0)>0
        and receipt.get('condition_point_cost')==1)


def continuation_pending(engine, actor):
    row = state(actor)
    turn = row.get('swarm_turn', {}) if row else {}
    return turn.get('round') == engine.round_no and turn.get('lifecycle') == 'pending'


def defer_action(engine, actor, *, continue_action=True):
    row = state(actor)
    if row is None:
        return False
    turn = _turn(row)
    if turn['lifecycle'] != 'open':
        raise ValueError('swarm action window is not open')
    if continue_action and turn['window_used'] and row['swarm_points'] > 0:
        turn.update(lifecycle='pending', next_initiative=max(0, turn['current_initiative']-5))
        return True
    return False


def finish_turn(actor):
    row=state(actor)
    if row is not None:_turn(row).update(lifecycle='closed',next_initiative=None)


def _move_kind(engine, actor, move):
    import turn as TURN
    mm = engine.r.move_mech(move["id"])[0]
    return TURN.action_kind_of_move(engine, actor, move, mm)


def standard_cost(engine, actor, move):
    if move is None:
        return 1, "at_will"
    import frequency as FREQ
    kind, _ = FREQ.move_frequency(engine, move["id"], actor)
    policy = actor_templates_policy(actor)["swarm_standard_costs"]
    cost_kind = "eot" if kind == "every_other_turn" else kind
    if cost_kind not in policy:
        raise ValueError("swarm standard action has no reviewed frequency cost")
    return policy[cost_kind], kind


def actor_templates_policy(actor):
    import actor_templates as TEMPLATES
    return TEMPLATES.policy(actor)


def _record_standard(engine, actor, move, cost, frequency_kind):
    row = state(actor); turn = _turn(row)
    if turn['lifecycle'] != 'open' or turn['window_used']:
        return False
    first = not row["first_standard_used"]
    if first:
        initiative = turn["current_initiative"]
        row["first_standard_used"] = True
        if isinstance(getattr(actor, "budget", None), dict):
            actor.budget["standard"] = 0
    else:
        if row["swarm_points"] < cost:
            engine.log(f"    {actor.name}: 스웜 포인트 {cost} 필요, {row['swarm_points']} 남음",
                       "C11-089/swarm-action-cost")
            return False
        row["swarm_points"] -= cost
        initiative = turn["current_initiative"]
    turn['window_used'] = True
    if turn["minimum_action"] and turn["action_index"] == 0:
        turn["minimum_action_used"] = True
    receipt = {
        "index": turn["action_index"]+1, "initiative": initiative,
        "point_cost": 0 if first else cost, "frequency": frequency_kind,
        "move_id": None if move is None else move["id"], "free_first": first,
    }
    row["round_trigger_receipts"][turn["key"]]["actions"].append(receipt)
    engine.log(f"    {actor.name}: 스웜 행동 #{turn['action_index']+1} @ {initiative}, 포인트 {receipt['point_cost']} 소비",
               "C11-087/C11-088/C11-089")
    validate(actor, row)
    return True


def schedule_continuation(engine, actor, schedule, slot, phase):
    if not continuation_pending(engine,actor):
        return
    turn=_turn(state(actor)); count=turn['next_initiative']
    import initiative as INIT
    at=schedule['cursor']
    while at < len(schedule['steps']):
        next_step=schedule['steps'][at]
        if next_step['phase'] != phase or next_step['kind'] != 'turn':break
        other=schedule['slots'][next_step['slot']]['actor']
        pending=state(other)
        other_count=(pending['swarm_turn']['next_initiative'] if continuation_pending(engine,other)
                     else INIT.value(engine.r,other,engine=engine).value)
        if type(other_count) is not int:
            raise ValueError('swarm continuation needs a resolved actual opposing initiative count')
        if other_count < count:break
        if other_count == count:
            from initiative import InitiativeValue
            group=[('existing',other,InitiativeValue(count,'native schedule')),
                   ('swarm',actor,InitiativeValue(count,'C11-088'))]
            plan=INIT._tie_plan(engine,group,count)
            if plan is None:raise ValueError('swarm initiative tie requires the native tie decision')
            order=plan[1] if plan[0]=='order' else INIT._roll_group(engine,group,count,plan[1])
            if order is None:raise ValueError('swarm initiative tie remains unresolved')
            if (order[0] == 'swarm' if plan[0]=='order' else order[0][1] is actor):break
        at+=1
    record={'after_cursor':schedule['cursor'],'insert_at':at,'slot':slot,'phase':phase,
            'initiative':count,'origin_initiative':turn['current_initiative'],
            'action_index':turn['action_index'],'action_key':turn['key']}
    __import__('initiative_schedule').record_step_change(schedule,'swarm_continuations',record)
    schedule['steps'].insert(at,{'phase':phase,'slot':slot,'kind':'turn'})
    schedule['slots'][slot]['turn']='ready'


def expanded_schedule(engine, schedule, steps, *, after=0, before=None):
    """Rebuild queued continuations, also at intervening mounted exchanges."""
    previous=0
    for row in schedule.get('swarm_continuations',[]):
        if before is not None and row['after_cursor']>before:break
        if row['after_cursor']<=after:
            previous=row['after_cursor']
            continue
        after=row['after_cursor']; at=row['insert_at']; slot=row['slot']
        if (type(after) is not int or not previous < after <= schedule['cursor']
                or type(at) is not int or not after <= at <= len(steps)
                or slot not in schedule['slots']):
            raise ValueError('swarm continuation must follow its actual closed action')
        previous=after
        if steps[after-1] != {'phase':row['phase'],'slot':slot,'kind':'turn'}:
            raise ValueError('swarm continuation belongs to another schedule step')
        actor=schedule['slots'][slot]['actor']; swarm=state(actor)
        receipt=swarm.get('round_trigger_receipts',{}).get(row['action_key']) if swarm else None
        actions=receipt.get('actions',[]) if receipt else []
        index=row['action_index']
        if (type(index) is not int or not 0 <= index < len(actions)
                or actions[index]['initiative'] != row['origin_initiative']
                or row['initiative'] != max(0,row['origin_initiative']-5)):
            raise ValueError('swarm continuation requires its actual Standard Action')
        steps.insert(at,{'phase':row['phase'],'slot':slot,'kind':'turn'})
    return steps


def spend(engine, actor, kind, move=None):
    """Return None for ordinary handling, otherwise a completed swarm decision."""
    row = state(actor)
    if row is None:
        return None
    if kind == "standard":
        cost, frequency_kind = standard_cost(engine, actor, move)
        return _record_standard(engine, actor, move, cost, frequency_kind)
    if kind in ("swift", "free") and move is not None:
        # Frequency admission is owned by frequency.move_allowed.  The ordinary
        # one-Swift token is replaced by the per-swarm-action ledger.
        return True
    return None


def move_allowed(engine, actor, move_id, frequency_kind, cap):
    row = state(actor)
    if row is None:
        return None
    move = engine.r.move(move_id)
    action_kind = _move_kind(engine, actor, move)
    turn = row.get("swarm_turn")
    if not isinstance(turn, dict) or turn.get("round") != engine.round_no:
        return False, "스웜 기술은 열린 실제 스웜 턴이 필요"
    if turn['lifecycle'] != 'open':
        return False, '스웜 추가 행동은 다음 이니셔티브 창을 기다려야 함'
    if action_kind == "standard":
        if turn['window_used']:
            return False, '현재 스웜 행동의 기본 행동을 이미 사용'
        cost_key = "eot" if frequency_kind == "every_other_turn" else frequency_kind
        cost = actor_templates_policy(actor)["swarm_standard_costs"].get(cost_key)
        if cost is None:
            return False, "스웜 기본 행동 빈도 비용 미해석"
        if not row["first_standard_used"] or row["swarm_points"] >= cost:
            return True, ""
        return False, "스웜 포인트 부족"
    if action_kind in ("swift", "free"):
        ledger = row["frequency_ledger"].get(move_id, {})
        if frequency_kind in ("scene", "daily"):
            scene = actor.spec.get("frequency_state", {}).get("scene", 0)
            used = ledger.get("used", 0) if ledger.get("scene") == scene else 0
            return (used < row["multiplier"], "" if used < row["multiplier"] else "스웜 장면 신속/자유 사용 횟수 소진")
        if frequency_kind in ("at_will", "every_other_turn"):
            allowed = ledger.get("turn_key") != turn["key"] or ledger.get("action_index") != turn["action_index"]
            return allowed, "" if allowed else "현재 스웜 행동의 신속/자유 사용 횟수 소진"
    return None


def record_move_use(engine, actor, move_id, frequency_kind):
    row = state(actor)
    if row is None:
        return
    move = engine.r.move(move_id)
    action_kind = _move_kind(engine, actor, move)
    if action_kind not in ("standard", "swift", "free"):
        return
    turn = _turn(row)
    old = row["frequency_ledger"].get(move_id, {})
    scene = actor.spec.get("frequency_state", {}).get("scene", 0)
    used = old.get("used", 0) if old.get("scene") == scene else 0
    row["frequency_ledger"][move_id] = {
        "kind": frequency_kind, "action_kind": action_kind, "scene": scene,
        "used": used + 1, "turn_key": turn["key"], "action_index": turn["action_index"],
    }
    validate(actor, row)


def after_hp_change(engine, actor, before, source):
    row = state(actor)
    if row is None or actor.hp > 0:
        return None
    bars = row["hp_bars"]
    remaining = bars["total"] - bars["spent"]
    if remaining <= 0:
        return None
    bars["spent"] += 1
    row["multiplier"] = bars["total"] - bars["spent"]
    row["swarm_points"] = min(row["swarm_points"], row["multiplier"])
    receipt = {
        "source_id": "C11-086", "bar": bars["spent"], "before_hp": before,
        "depleted_hp": actor.hp, "discarded_overflow": max(0, -actor.hp),
        "remaining_bars": row["multiplier"], "source": source,
    }
    row["bar_transition_receipts"].append(receipt)
    if row["multiplier"] > 0:
        actor.hp = actor.max_hp
        engine.log(f"    {actor.name}: 체력 바 소진 → 스웜 군집체 {row['multiplier']}, 다음 바 {actor.hp}",
                   "C11-086/swarm-hp-bars")
    else:
        engine.log(f"    {actor.name}: 마지막 체력 바 소진 → 스웜 군집체 0",
                   "C11-086/swarm-hp-bars")
    validate(actor, row)
    return receipt
