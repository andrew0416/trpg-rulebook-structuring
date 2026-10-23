"""Ordinary paid equipment actions over existing item and physical owners.

Component registration, forced transfers and GM restoration keep their existing
costs. Possession, equipment effects and next-turn permission have separate owners.
"""
import items as ITEMS
import world_entities as WORLD
import state_grants as GRANTS
import capability_actions as CAP
import turn as TURN

SLOTS = ('held', '머리', '주요손', '반대손', '몸통', '발', '장신구')


def _require_turn(engine, actor):
    WORLD.require_actors(engine, actor)
    if (not engine.encounter_active or engine._active_turn_actor is not actor
            or not actor.on_field or actor.captured):
        raise ValueError('manual equipment requires the actual open own turn')


def _carried(engine, actor, instance_id):
    obj = getattr(engine, '_physical_objects', {}).get(instance_id)
    import optional_weapon_framework as WEAPONS
    if not isinstance(obj, dict) or (obj.get('kind') != 'item_instance' and WEAPONS.PROFILE not in obj):
        raise ValueError('manual equipment requires an actual item or observed weapon instance')
    WORLD.require_physical_access(obj)
    if obj.get('carrier_id') != actor.entity_id:
        raise ValueError('manual equipment requires actual physical possession')
    if obj.get('equipped_by') not in (None, actor.entity_id):
        raise ValueError('item is equipped by another actor')
    load = actor.spec.get('_carried_load', {})
    if load.get('mode', 'physical') != 'physical' or load.get('blocked_actions') or load.get('failure_pending'):
        raise ValueError('manual equipment requires a resolved physical carrying policy')
    rows = load.get('objects', [])
    found = next((r for r in rows if r['id'] == instance_id), None)
    if found is None or found['weight_kg'] != obj.get('weight_kg'):
        raise ValueError('actual item weight and carrier evidence disagree')
    return obj, [dict(row) for row in rows]


def _spend(engine, actor, kind):
    if not TURN.spend(engine, actor, kind, '장비 ' + kind):
        raise ValueError('manual equipment action unavailable')


def _release(engine, actor, row, operation):
    import equipment_protection as PROTECTION
    PROTECTION.require(engine,actor,row,operation,(actor,))
    if row.get('weapon_key'):
        TURN.unequip_weapon(engine,actor,row['weapon_key'])
        WORLD._set_object_location(engine._physical_objects[row['instance_id']],{'kind':'unknown'})
    else:ITEMS._unregister_selected(engine,actor,row)
    ITEMS._refresh_unresolved(engine,actor)


def _selected(actor,selection,slots=SLOTS):
    rows=[r for r in ITEMS.equipment_options(actor,slots) if r.get('instance_id')==selection]
    return rows[0] if len(rows)==1 else ITEMS.selected_equipment(actor,selection,slots)


def _run(engine,actor,apply,*,kind,participants=()):
    import heavy_injury_adapter as HEAVY, heavy_standard_adapter as STANDARD
    HEAVY.ensure_clear(engine)
    before=HEAVY.observe(actor)
    if kind=='standard' and actor.injuries>=5:
        __import__('temporary_hp').ensure_certain(engine,actor)
    context=STANDARD.equipment_context(engine,actor) if kind=='standard' and actor.injuries>=5 else []
    def perform(e,c,*others):
        result=apply(e,c,*others)
        if kind=='standard' and before['injuries']>=5:
            event=STANDARD.finish_equipment(e,c,before,result,context)
            result['heavy_event']=event
        return result
    result=GRANTS.transition(engine,actor,perform,participants=participants)
    if getattr(engine,'_heavy_pending',None):raise HEAVY.HeavyPending(engine._heavy_pending)
    return result


def equip(engine, actor, instance_id, *, replace_selection=None, slot=None):
    """Equip one actual carried item/weapon; replacement retains old possession."""
    _require_turn(engine, actor)

    def apply(e, c):
        _spend(e, c, 'standard')
        obj, _ = _carried(e, c, instance_id)
        if obj.get('equipped_by'):
            raise ValueError('item is already equipped')
        if replace_selection is not None:
            row = _selected(c, replace_selection)
            _release(e,c,row,'drop')
        import optional_weapon_framework as WEAPONS
        if WEAPONS.PROFILE in obj:
            key=WEAPONS.equip(e,c,instance_id,slot=slot or '주요손')
            registration=c.custom_conditions['equipped_weapons'][key]
            return {'equipped':instance_id,'replaced':replace_selection,'slots':list(registration['slots'])}
        if slot is not None:raise ValueError('explicit slot requires an observed weapon')
        ITEMS.register_item(e, c, obj['item_rule_id'], source_instance_id=instance_id)
        registration = next((r for r in getattr(c, '_item_reg', {}).values()
                             if r.get('instance_id') == instance_id), None)
        if registration is None:
            raise ValueError('item registration did not acquire an equipment slot')
        return {'equipped': instance_id, 'replaced': replace_selection,
                'slots': list(registration['slots'])}

    return _run(engine,actor,apply,kind='standard')


def give(engine, giver, receiver, instance_id, *, replace_selection=None, held_slot=None):
    """Trainer receives possession; Pokemon receives held equipment and turn lock.

    The receiver gains physical possession, never an equipment registration.
    Legal ownership is preserved; this operation records no sale or gift title.
    """
    _require_turn(engine, giver)
    WORLD.require_actors(engine, receiver)
    if giver.kind != 'trainer' or receiver.kind not in ('trainer','pokemon'):
        raise ValueError('manual handoff requires an actual Trainer and recipient')
    if receiver.kind=='trainer' and (replace_selection is not None or held_slot is not None):
        raise ValueError('Trainer receipt does not equip or replace anything')
    if (giver is receiver or not receiver.on_field or receiver.captured
            or not engine.adjacent(giver, receiver)):
        raise ValueError('manual handoff requires one adjacent on-field recipient')

    def apply(e, a, b):
        _spend(e, a, 'standard')
        obj, giving = _carried(e, a, instance_id)
        receiving = b.spec.get('_carried_load', {})
        if (receiving.get('mode', 'physical') != 'physical'
                or receiving.get('blocked_actions') or receiving.get('failure_pending')):
            raise ValueError('recipient carrying policy unresolved')
        if obj.get('equipped_by'):
            row = _selected(a, instance_id)
            _release(e,a,row,'transfer')
        CAP.set_carried(e, a, [r for r in giving if r['id'] != instance_id], 'manual equipment handoff')
        CAP.set_carried(e, b, [*receiving.get('objects', []),
                              {'id': instance_id, 'weight_kg': obj['weight_kg']}],
                        'manual equipment receipt; not equipped')
        equipped=False
        if b.kind=='pokemon':
            if replace_selection is not None:
                _release(e,b,_selected(b,replace_selection,('held',)),'drop')
            ITEMS.register_item(e,b,obj['item_rule_id'],source_instance_id=instance_id,as_held=True,held_slot=held_slot)
            if not any(x.get('instance_id')==instance_id for x in __import__('held_equipment').entries(b)):
                raise ValueError('handoff did not acquire the actual held slot')
            import action_resources as RESOURCES
            RESOURCES.schedule_turn_lock(e,b,instance_id)
            equipped=True
        return {'given': instance_id, 'recipient': b.entity_id, 'equipped': equipped}

    return _run(engine,giver,apply,kind='standard',participants=(receiver,))


def drop_held(engine, actor, selection):
    """Own-turn drop with printed individual-item action overrides."""
    _require_turn(engine, actor)
    slots=('held',) if actor.kind=='pokemon' else SLOTS
    selected=ITEMS.selected_equipment(actor,selection,slots)
    if selected.get('weapon_key'):raise ValueError('held-item drop does not declare a weapon removal cost')
    kind='standard' if selected.get('item_id') in STANDARD_DROP else 'free'

    def apply(e, c):
        row = ITEMS.selected_equipment(c, selection, slots)
        _spend(e, c, kind)
        return ITEMS.drop_equipment(e, c, (row['key'],), slots=slots,
                                    consent_by=(c,), source='ch09/manual-held-drop')

    return _run(engine,actor,apply,kind=kind)


# ch09:799/804/806/817; rule IDs identify exceptions, not actor-name guesses.
STANDARD_DROP={'item/화염구슬','item/검은철구','item/맹독구슬',
               'item/느림보꼬리','item/느림보-도구','item/느림보-도구-1','item/느림보-도구-2',
               'item/느림보-도구-3','item/느림보-도구-4'}
