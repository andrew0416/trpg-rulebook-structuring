"""Shared native gameplay validation for GM snapshots and durable state.

Domain validators retain ownership of their contracts. This boundary raises
native errors; persistence adapters translate them into their own error type.
"""


class WorldIntegrityError(ValueError):
    """Findings returned by the world's reference-integrity inspection."""


def validate(engine, actors):
    import body_modes as BODY_MODES
    from state_fields import validate_actor
    from world_entities import validate_mount_relations, validate_world
    import temporary_hp as TEMP_HP
    TEMP_HP.loss_policy(engine)
    for actor in actors:
        if actor.kind != actor.spec.get('kind'):
            raise ValueError('actor kind disagrees with base state')
        if type(actor.conditions) is not set or any(type(v) is not str for v in actor.conditions):
            raise ValueError('conditions must be explicit named states')
        validate_actor(actor)
        import trainer_feature_acquisition as TRAINER_FEATURES
        TRAINER_FEATURES.validate_actor(actor)
        import body_modes as BODY_MODES
        BODY_MODES.validate(actor)
        import consumption_execution as CONSUMPTION
        import recovery_receipts as RECOVERY
        import state_episodes as EPISODES
        CONSUMPTION.validate(actor)
        RECOVERY.validate(actor)
        EPISODES.validate_bindings(actor)
        import invisibility_state as INVISIBILITY
        INVISIBILITY.elapsed_bounds(engine, actor)
        import baby_templates as BABY
        BABY.validate_actor(engine, actor)
    BODY_MODES.validate_world(engine,{actor.entity_id:actor for actor in actors})
    import marsupial_state as MARSUPIAL
    MARSUPIAL.validate_world(engine)
    import newground_flight_option as GROUND_FLIGHT
    GROUND_FLIGHT.validate(engine)
    import weather_state as WEATHER
    WEATHER.validate(engine)
    import fast_combat as FAST_COMBAT
    FAST_COMBAT.validate(engine)
    import weather_templates as WEATHER_TEMPLATES
    WEATHER_TEMPLATES.validate(engine)
    issues = validate_world(engine)['issues']
    if issues:
        raise WorldIntegrityError('world reference integrity: ' + '; '.join(row['code'] for row in issues))
    # This native relation boundary also owns Telekinetic object/holder checks,
    # which are not included in WORLD's findings collector.
    validate_mount_relations(engine)
    # WORLD reports relations; these receipt owners additionally validate the
    # current clock, physical materialization and native Hazard provenance.
    import clock_invocations as CLOCK
    import materialization_origins as ORIGINS
    import hazard_state as HAZARDS
    CLOCK.validate(engine)
    ORIGINS.validate_world(engine)
    HAZARDS.validate_world(engine)
    import action_lifecycle as ACTION
    ACTION.validate_turn_end_closures(engine)

