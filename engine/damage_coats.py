"""Read-only effectiveness contribution, consumed after actual typed damage."""
import common_checks as C
import effect_instances as E


def validate_record(actor,record,*,terminal=False):
    import coat_effects as COATS
    E.validate(record,actor=actor,terminal=terminal)
    row=COATS.definition(actor.r,record['source']);meta=record[E.KEY]
    if row is None or record['effect']!=row['payload'] or record['effect']['kind']!='damage_coat':raise ValueError('selected typed coat payload required')
    if meta['capacity']!={'bucket':'source_coat','source':record['source']} or meta['lifetime']!={'boundary':row['lifetime']}:raise ValueError('typed coat source authority mismatch')
    if not meta.get('applied_by_actor_id'):raise ValueError('actual typed coat creator required')
    for event in meta['ownership'][1:]:
        if event.get('source') not in ('move/배턴터치','feat/태그-인'):raise ValueError('typed Coat ownership requires Baton Pass or actual Tag In')
    if record.get('applications')!=[]:raise ValueError('single-use coat has no periodic applications')
    C.integer(record.get('issued_turn'),'typed coat issue turn',0,COATS.serial(actor))
    if terminal:
        event=meta['end_event']
        if meta['state']=='expired':
            if event.get('kind')!='coat_removed' or event.get('source') not in COATS.REMOVERS:raise ValueError('actual coat remover required')
        elif meta['state']=='consumed':
            if event.get('kind')!='typed_attack_damage' or event.get('move_type')!=record['effect']['match_type']:raise ValueError('matching typed damage required')
            minimum=0 if row.get('consumption')=='matching_attack_hit' else 1
            C.integer(event.get('requested'),'actual typed damage',minimum)
            C.integer(event.get('absorbed'),'actual absorbed damage',minimum)
            if (event['requested']==0 or event['absorbed']==0) and event.get('observation_boundary')!='native_attack_application_including_its_hooks':
                raise ValueError('zero-damage consumption requires the actual resolved-hit boundary')
            E.text(event.get('source'),'actual damage source')
        else:raise ValueError('actual coat ending required')
        E.text(event.get('actor_id'),'actual damage/removal actor')
    return True


def steps(engine,actor,move):
    import coat_effects as COATS
    COATS.validate_actor(actor)
    if move.get('class') not in ('물리','특수'):return 0
    return sum(r['effect']['steps'] for r in COATS.live(actor)
               if r['effect'].get('kind')=='damage_coat' and r['effect']['match_type']==move['type'])


def after_damage(engine,attacker,target,move,receipt, *, type_multiplier=None):
    import coat_effects as COATS
    absorbed=receipt['net_hp_loss']+receipt['net_temporary_hp_loss']
    actual_hit=(receipt.get('observation_boundary')=='native_attack_application_including_its_hooks'
                and receipt.get('source')==move['id']
                and receipt.get('damage_class')==move['class'])
    for row in list(COATS.live(target)):
        payload=row['effect']
        if payload.get('kind')!='damage_coat' or payload['match_type']!=move['type']:continue
        policy=COATS.definition(engine.r,row['source'])
        if policy.get('consumption')=='matching_attack_hit':
            if not actual_hit:continue
        elif receipt['requested']<=0 or absorbed<=0:continue
        E.archive(engine,target,row,state='consumed',event={'kind':'typed_attack_damage',
            'actor_id':attacker.entity_id,'source':move['id'],'move_type':move['type'],
            'requested':receipt['requested'],'absorbed':absorbed,
            'observation_boundary':receipt.get('observation_boundary')})
        target.coats.remove(row)
        engine.log('    '+target.name+': typed damage consumed Coat '+row['id'],row['source'])
    import equipment_variant_contracts as EQUIPMENT_VARIANTS
    EQUIPMENT_VARIANTS.after_attack_damage(engine,attacker,target,move,receipt,type_multiplier=type_multiplier)
    import held_item_reactions as HELD_REACTIONS
    HELD_REACTIONS.after_hit(engine,attacker,target,move,absorbed)
