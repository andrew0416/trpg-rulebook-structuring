"""Shared persistent-affliction consumers; variant counters reuse effect instances."""
import common_checks as C
import condition_instances as CI


def loss(engine,actor,condition,ticks):
    import condition_variants as VARIANTS
    if condition=='독' and __import__('survivalist_class').poison_hp_immune(engine,actor):return 0
    if condition=='독' and VARIANTS.active(actor) is not None:return 0
    rows=CI.records(actor,'독') if condition=='독' else []
    if rows:
        row=rows[0];CI.validate_record(actor,row)
        definition=next(e for e in engine.r.condition_effects('독') if e.get('type')=='hp_loss_escalating' and e.get('variant')=='맹독')
        if definition.get('growth')!='x2_per_round':raise ValueError('poison growth requires a reviewed source adapter')
        return C.integer(definition['start'],'poison initial loss',1)*(2**row['completed_rounds'])+__import__('type_ace').poison_loss(actor)
    return engine.tick_loss(actor,ticks)+(__import__('type_ace').poison_loss(actor) if condition=='독' else 0)


def finish_round(engine):
    import combat_state_lifecycle as COMBAT
    for actor in COMBAT.members(engine):
        for row in CI.records(actor,'독'):
            import condition_variants as VARIANTS
            if VARIANTS.owns(row):continue
            CI.validate_record(actor,row)
            if row['last_completed_round']==engine.round_no:continue
            row['completed_rounds']+=1;row['last_completed_round']=engine.round_no;row['round_history'].append(engine.round_no)
            engine.log('    '+actor.name+': 맹독 누적 라운드 '+str(row['completed_rounds']),row['source'])


def base_save_dc(engine,actor,condition,dc):
    # The Frozen source explicitly gives the Fire-type Pokemon exception.
    for effect in engine.r.condition_effects(condition):
        if effect.get('type')=='save_modifier' and effect.get('if_type') in actor.types and actor.kind=='pokemon' and 'dc' in effect:
            dc=C.integer(effect['dc'],'condition type-specific save DC',1)
    return dc


def attack_hit(engine,target,move):
    # Called only by the actual attack-damage producer, never by previews,
    # misses or generic HP loss. Damaging is the Move class, not a new HP-loss DC.
    if move.get('class') not in ('물리','특수'):return
    for condition in tuple(sorted(target.conditions)):
        if engine.r.condition_class(condition) is None:continue
        for effect in engine.r.condition_effects(condition):
            if effect.get('type')=='cured_by_damage_of_types' and move.get('type') in effect.get('types',[]):
                engine.cure_status(target,condition)
                break
