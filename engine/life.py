"""Common life transitions. Open timing branches are explicit pending state.
No resurrection rule is inferred from ordinary healing. The shared engine clock
advances actor timers; unknown elapsed time never invents an exact deadline.
"""
FIELDS=('dead','faint_recovery_seconds','faint_recovery_pending','faint_recovery_interrupted','life_elapsed_seconds','faint_recovery_birth_round')
import recovery_resolution as RECOVERY


def at_full_hp(c):
    """Full-HP effects use true maximum; injury ceiling only limits recovery."""
    return c.hp >= c.base_max_hp


def init(c):
    c.dead=False
    c.faint_recovery_seconds=None
    c.faint_recovery_pending=None
    c.faint_recovery_interrupted=False
    c.faint_recovery_birth_round=None
    c.life_elapsed_seconds=0


def clear_recovery(c):
    c.faint_recovery_seconds=None
    c.faint_recovery_pending=None
    c.faint_recovery_interrupted=False
    c.faint_recovery_birth_round=None


def faint(engine,c):
    if '기절' in c.conditions:return False
    import setup_move_state as SETUP_MOVE
    SETUP_MOVE.cancel(engine,c,'faint')
    import stat_exchange_state as STAT_EXCHANGE
    STAT_EXCHANGE.validate_actor(c)
    snapshot=__import__('ability_exchange_contracts').before_faint(engine,c)
    c.conditions.add('기절')
    __import__('ability_exchange_contracts').fainted(engine,c,snapshot)
    __import__('native_path_area_moves').end_fairy_source(engine,c)
    __import__('juggler').event(engine,'faint',c,source_id='condition/기절')
    __import__('perception_communicate').boundary(engine,'faint',c)
    import bide as BIDE
    BIDE.clear(engine,c)
    import duelist as DUELIST
    DUELIST.clear(engine,c,'faint')
    import csv_item_physical_contracts as CSV_ITEMS
    CSV_ITEMS.switched_or_fainted(c)
    import csv_item_form_contracts as CSV_FORMS
    CSV_FORMS.fainted(engine,c)
    STAT_EXCHANGE.end_event(engine,c,'faint')
    import ability_transitions as ABILITY_TRANSITIONS
    ABILITY_TRANSITIONS.end(engine,c,'faint')
    import status_sets as STATUS_SETS
    STATUS_SETS.cure_group(engine,c,'persistent')
    import combat_state_lifecycle as COMBAT_STATE
    COMBAT_STATE.cure_volatile(engine,c)
    import linked_move_conditions as LINKED
    LINKED.boundary(engine,c,'faint')
    __import__('type_ace').faint_boundary(engine,c)
    engine.log(f'    {c.name} 기절; 지속성/휘발성 상태 치료', 'condition/기절')
    return True


def sync(engine,c):
    """Evaluate death on every boundary, including already-fainted/positive HP."""
    if c.dead:return
    import actor_templates as TEMPLATES
    dying=False
    if engine.death_enabled and not TEMPLATES.soulless(c):
        d=engine.r.mech('combat/injuries')['death']
        from rulings import calc
        threshold=calc(d['hp_non_friendly'],{'max_hp':c.base_max_hp})
        import csv_item_capability_contracts as CSV_CAP
        dying=(c.injuries+CSV_CAP.essence_base_injuries(c)>=d['injuries'] or (not engine.friendly_battle and c.hp<=threshold))
    import taskmaster as TASK
    press=False if dying else TASK.faint_boundary(engine,c)
    if c.hp>0:__import__('berserker').faint_boundary(engine,c)
    if c.hp<=0 and not dying and not press:
        press=__import__('berserker').faint_boundary(engine,c)
    if c.hp<=0 and not dying and not press:
        press=__import__('enduring_soul').faint_boundary(engine,c)
    if c.hp<=0 and not press:
        faint(engine,c)
        if c.faint_recovery_seconds is not None:
            c.faint_recovery_seconds=None
            c.faint_recovery_interrupted=True
            c.faint_recovery_pending='recovery_interrupted_by_nonpositive_hp'
    if dying:
        c.dead=True
        clear_recovery(c)
        engine.log(f'    {c.name} 사망: HP {c.hp}, 부상 {c.injuries}', 'combat/injuries')


def heal(engine,c,amount,source_kind='unspecified'):
    if type(amount) is not int or amount<0:raise ValueError('healing must be nonnegative integer HP')
    if source_kind not in ('ordinary_item','move','feature','explicit_revive','rest','unspecified'):
        raise ValueError('unknown healing source kind')
    sync(engine,c)
    if c.dead:
        engine.log(f'    {c.name}: 사망 상태는 일반 회복/소생으로 해제되지 않음','combat/injuries')
        return 0
    import healing_blocks as HEALING_BLOCKS
    if HEALING_BLOCKS.blocked(c):return 0
    before=c.hp
    # A recovery ceiling limits an increase; it must never turn healing into loss.
    plan=RECOVERY.resolve(before,amount,resource='hp',ceiling=c.max_hp)
    c.hp=plan['after']
    gained=plan['applied']
    if c.hp>0:
        import taskmaster as TASK
        for row in TASK.records(c):row['press_on']=False
        __import__('berserker').faint_boundary(engine,c)
    if '기절' in c.conditions and c.hp>0 and gained>0:
        import optional_physical_equipment as OPTIONAL_EQUIPMENT
        if OPTIONAL_EQUIPMENT.awakening_blocked(engine,c):
            pass
        elif source_kind in ('move','feature','explicit_revive'):
            c.conditions.discard('기절');clear_recovery(c)
        elif source_kind=='ordinary_item' and before<=0:
            # A new crossing starts a new ten-minute interval. Earlier positive
            # intervals cannot count across another actual knockout.
            clear_recovery(c)
            c.faint_recovery_seconds=600
        elif c.faint_recovery_seconds is None:
            # Further healing does not undo a known ordinary-item recovery.
            # Unknown positive-HP history still cannot supply a start timestamp.
            c.faint_recovery_pending='faint_recovery_source_or_rest_timing_unresolved'
    engine.log(f'    {c.name} 체력 {before} → {c.hp} (회복 {amount}, {source_kind})')
    return gained


def revive(engine,c,hp):
    """Explicit faint-recovery effect setting HP, not resurrection from death."""
    if type(hp) is not int or hp<=0:raise ValueError('revive HP must be positive integer')
    sync(engine,c)
    if c.dead:return False
    import optional_physical_equipment as OPTIONAL_EQUIPMENT
    if OPTIONAL_EQUIPMENT.awakening_blocked(engine,c):return False
    import healing_blocks as HEALING_BLOCKS
    if HEALING_BLOCKS.blocked(c):return False
    recovered=RECOVERY.resolve(c.hp,hp,resource='hp',mode='at_least',ceiling=c.max_hp)['after']
    if recovered<=0:return False
    c.hp=recovered;c.conditions.discard('기절');clear_recovery(c)
    return True


def advance(engine,c,seconds):
    if type(seconds) is not int or seconds<0:raise ValueError('elapsed seconds must be nonnegative integer')
    sync(engine,c)
    c.life_elapsed_seconds+=seconds
    import optional_physical_equipment as OPTIONAL_EQUIPMENT
    had_kaladanda = OPTIONAL_EQUIPMENT.NO_AWAKENING in c.custom_conditions
    if OPTIONAL_EQUIPMENT.awakening_blocked(engine,c,at_time=engine.elapsed_seconds+seconds):return
    if had_kaladanda and c.hp>0 and '기절' in c.conditions:
        c.conditions.discard('기절');clear_recovery(c)
        engine.log(f'    {c.name}: 카라단다의 24시간 봉인 종료, 기절 해제','crafted_item/카라단다')
        return
    if c.dead or c.faint_recovery_seconds is None:return
    temporal_unknowns = {'within_round_healing_timestamp_unresolved','partial_round_elapsed_unresolved'}
    if c.faint_recovery_pending and c.faint_recovery_pending not in temporal_unknowns:return
    # An unknown birth position cannot receive its entire birth-round interval.
    # Later known intervals are a lower bound on elapsed time: once that bound
    # reaches600seconds recovery is certain even though the exact expiry was unknown.
    if (c.faint_recovery_pending == 'within_round_healing_timestamp_unresolved'
            and engine.round_start_seconds is not None
            and c.faint_recovery_birth_round == engine.round_no):return
    if c.hp<=0:return
    c.faint_recovery_seconds=max(0,c.faint_recovery_seconds-seconds)
    if c.faint_recovery_seconds==0:
        c.conditions.discard('기절');clear_recovery(c)
        engine.log(f'    {c.name}: 일반 회복 후 10분 경과, 기절 해제','condition/기절')
