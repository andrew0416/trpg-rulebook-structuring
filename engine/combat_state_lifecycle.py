"""Actual encounter membership and the shared combat-state reset boundary."""
import common_checks as C
import combat_stage_sources as CS


def _members(engine, current, extra):
    import world_entities as W
    actors = list(current) + list(extra)
    index = W.actor_index(engine, extra=actors)
    actual = {id(actor) for actor in index.values()}
    if any(id(actor) not in actual for actor in actors):
        raise ValueError('encounter membership requires actual actors')
    return list({id(actor): actor for actor in actors}.values())


def members(engine, extra=()):
    validate(engine)
    current = getattr(engine, '_encounter_actors', None)
    # Only the declared combat roster is a legacy fallback, never clock users.
    if current is None: current = getattr(engine, 'everyone', ())
    return _members(engine, current, extra)


def join(engine, actors):
    validate(engine)
    import marsupial_state as MARSUPIAL
    for actor in actors:MARSUPIAL.require_independent(engine,actor)
    current = getattr(engine, '_encounter_actors', None)
    planned = _members(engine, () if current is None else current, actors)
    import condition_recovery as RECOVERY
    for actor in planned:RECOVERY.invalidate(actor)
    engine._encounter_actors = planned;__import__('world_entities').roster_changed(engine)
    import csv_item_form_contracts as CSV_FORMS
    for actor in actors:CSV_FORMS.encounter_join(engine,actor)
    return planned


def validate(engine):
    actors = getattr(engine, '_encounter_actors', None)
    if actors is None: return
    if not isinstance(actors, list) or len({id(c) for c in actors}) != len(actors):
        raise ValueError('encounter membership must be unique actual actors')
    _members(engine, actors, ())


def preflight(actor):
    CS.validate(actor)
    C.integer(actor.accuracy_stage,'accuracy stage',-6,6)
    C.integer(actor.evasion_mod,'extra evasion',-6,6)
    for field in ('accuracy_stage','evasion_mod'):
        row=actor.spec.get('state_grants',{}).get('numbers',{}).get(field)
        if row is not None and row.get('visible')!=getattr(actor,field):raise ValueError('untracked bounded combat modifier needs reconciliation')


def condition_key(condition,stat):return 'condition-stage:'+condition+':'+stat


def apply_condition_stage(engine,actor,condition,effect):
    import restorative_items as R,effects_ext as EXT
    stat,delta=effect['stat'],effect['delta'];C.integer(delta,'condition stage delta')
    delta=__import__('survivalist_class').poison_stage_delta(engine,actor,condition,delta)
    if stat not in CS.STATS:raise ValueError('condition requires an actual non-HP stage')
    if R.blocked_condition_stage(engine,actor,condition,stat,delta):return
    if EXT.stage_hook(engine,actor,delta):
        actor.custom_conditions.setdefault('blocked_condition_stages',{}).setdefault(condition,[]).append([stat,delta]);return
    key=condition_key(condition,stat)
    CS.add_base(actor,key,stat,delta,source='condition/'+condition,ends=key)


def cure_condition_stage(engine,actor,condition,effect):
    import restorative_items as R
    stat,delta=effect['stat'],effect['delta']
    delta=__import__('survivalist_class').poison_stage_delta(engine,actor,condition,delta)
    if R.consume_blocked_condition_stage(actor,condition,stat,delta):return
    key=condition_key(condition,stat)
    state=CS.validate(actor)
    if state is not None and key in state['base']:CS.end_source(actor,ends=key)
    else:engine.change_stage(actor,stat,-delta)  # legacy applied state, before its first reconciled reset


def _condition_defaults(engine,actor):
    # At a reset, ordinary stage history is gone. Remaining explicit afflicted
    # sources define defaults without guessing old hidden clamping offsets.
    import condition_variants as VARIANTS
    for condition in sorted(actor.conditions):
        for effect in VARIANTS.effects(engine,actor,condition):
            if effect.get('type')!='combat_stage' or effect.get('while')!='afflicted':continue
            stat,delta=effect['stat'],effect['delta'];key=condition_key(condition,stat)
            delta=__import__('survivalist_class').poison_stage_delta(engine,actor,condition,delta)
            if [stat,delta] in actor.custom_conditions.get('blocked_condition_stages',{}).get(condition,[]):continue
            state=CS.validate(actor)
            if state is not None and key in state['base']:continue
            CS.add_base(actor,key,stat,delta,source='condition/'+condition,ends=key)


def reset_actor(engine,actor,*,recall=False):
    preflight(actor)
    if not CS.end_encounter(actor):
        actor.stages.update(dict.fromkeys(CS.STATS,0))
        for registration in getattr(actor,'_item_reg',{}).values():
            for stat,delta in registration.get('stages',{}).items():
                if stat not in CS.STATS:raise ValueError('legacy item stage names must be non-HP')
                actor.stages[stat]=max(-6,min(6,actor.stages[stat]+delta))
    import boss_transitions as BOSS
    boss=BOSS.state(actor)
    if boss is not None:
        # Defaults replace combat history, preserving independent base sources.
        state=CS.validate(actor)
        if state is None:actor.stages.update(boss['baseline_stages'])
        else:
            state['combat']=dict(boss['baseline_stages'])
            CS.write(actor,state)
    _condition_defaults(engine,actor)
    import state_grants as G
    for field in ('accuracy_stage','evasion_mod'):
        if not G.reset_numeric(actor,field):setattr(actor,field,0)
    __import__('martial_artist').reset_evasion(engine,actor)
    __import__('optional_state_effect_contracts').reset_stages(actor)
    # Timed ordinary stages are also removed at a stage-reset boundary.
    # Independent physical-source/condition roll penalties are not stages.
    import combat_timing as TIMING
    for record in list(TIMING.records(actor)):
        # Debilitate's independent Accuracy roll penalty keeps its printed lifetime.
        record.pop('ace_evasion',None)
        if record.get('effect_contract') and not record.get('manual_end') and 'lifetime_policy' not in record and any(k in record for k in ('accuracy_modifier','evasion_modifier')):
            if recall and __import__('native_switch_transfer').preserve_order_on_recall(engine,actor,record):continue
            TIMING.expire(engine,actor,record)
    if not recall:__import__('native_switch_transfer').clear_pending_stages(engine,actor)


def cure_volatile(engine,actor,*,encounter_end=False):
    """Clear volatile conditions while respecting encounter-owned locks."""
    import csv_item_physical_contracts as CSV_ITEMS
    import status_sets as STATUS_SETS
    if encounter_end:
        CSV_ITEMS.end_encounter(actor,engine=engine)
    for condition in STATUS_SETS.afflictions(actor,'volatile'):
        if CSV_ITEMS.retain_encounter_condition(actor,condition):
            continue
        engine.cure_status(actor,condition)


def recall(engine,actor,*,ignore_trapped=False):
    import csv_item_form_contracts as CSV_FORMS
    CSV_FORMS.require_independent(engine,actor)
    preflight(actor)
    before_stages=dict(actor.stages)
    was_on_field=actor.on_field
    import condition_recovery as RECOVERY
    if type(ignore_trapped) is not bool:raise ValueError('explicit recall bypass flag required')
    if not ignore_trapped and not RECOVERY.permits_recall(actor):
        raise ValueError('Trapped prevents ordinary recall')
    import setup_move_state as SETUP_MOVE
    SETUP_MOVE.cancel(engine,actor,'recall')
    if was_on_field:__import__('native_path_area_moves').end_fairy_source(engine,actor)
    if was_on_field:
        import native_switch_transfer as SWITCH
        SWITCH.observe_recall(engine,actor,before_stages)
        SWITCH.begin_recall(engine,actor)
    import duelist as DUELIST
    DUELIST.clear(engine,actor,'recall')
    import csv_item_physical_contracts as CSV_ITEMS
    CSV_ITEMS.switched_or_fainted(actor)
    import declarative_move_contracts as DECLARATIVE_MOVES
    DECLARATIVE_MOVES.recall(engine,actor)
    import bide as BIDE
    BIDE.clear(engine,actor)
    import stat_exchange_state as STAT_EXCHANGE
    STAT_EXCHANGE.end_event(engine,actor,'switch')
    cure_volatile(engine,actor)
    import linked_move_conditions as LINKED
    LINKED.boundary(engine,actor,'recall')
    import healing_blocks as HEALING_BLOCKS
    HEALING_BLOCKS.boundary(engine,(actor,),'replacement')
    __import__('defense_curl').boundary(engine,(actor,),'replacement')
    import condition_recovery as RECOVERY
    RECOVERY.switch_out(engine,actor)
    import ability_transitions as ABILITY_TRANSITIONS
    ABILITY_TRANSITIONS.end(engine,actor,"recall")
    reset_actor(engine,actor,recall=True)
    import temporary_hp as TEMP
    TEMP.clear(engine,actor,'몬스터볼 복귀')
    import hazard_state as HAZARDS
    HAZARDS.on_recall(actor)
    actor.on_field=False
    if was_on_field and actor.spec.get('native_recall_history'):
        import root_resolution as ROOT
        record=actor.spec['native_recall_history'][-1]
        record['fact']['action_boundary']=SWITCH.action_boundary(engine)
        record['integrity']=ROOT.fingerprint(record['fact'])
    import marsupial_state as MARSUPIAL
    MARSUPIAL.sync(engine)


def send_out(engine,actor,*,pos=None,request_id=None,source_id=None):
    """One actual send boundary shared by paid party actions and GM placement."""
    import csv_item_form_contracts as CSV_FORMS
    CSV_FORMS.require_independent(engine,actor)
    before=actor.on_field
    if not before:
        import native_switch_transfer as SWITCH
        SWITCH.before_send(engine,actor)
    if engine.encounter_active:join(engine,[actor])
    actor.on_field=True
    if not before:actor.turns_taken=0
    if pos is not None:actor.pos=tuple(pos)
    if not before:
        __import__('illusion_state').on_release(engine,actor)
        owner=__import__('party_actions').owner(engine,actor)
        if owner is not None:
            request_id=request_id or 'native/send-out:'+str(owner.spec.get('native_send_serial',0))
            __import__('juggler').released(engine,owner,actor,request_id=request_id,source_id=source_id)
    # Placement loads shallow lake ice without passing through unrelated Hazards.
    import ice_lake as ICE_LAKE
    ICE_LAKE.enter(engine,actor)
