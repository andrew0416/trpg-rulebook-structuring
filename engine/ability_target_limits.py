"""Finite target restrictions stored in the existing combat-timing records."""
import common_checks as C
import combat_timing as TIME

SOURCE='ability/긴장감'
NAME='긴장감'
KEY='ability_target_limits'
LIMITS=('positive_stages','food_buff')


def registration(rules,name):
    if name not in (NAME,SOURCE) and rules.ability_alias.get(name)!=NAME:return None
    if rules._selected_rule(SOURCE)!=SOURCE:raise ValueError('Unnerve selected source changed')
    return SOURCE


def blocked(engine,actor,limit):
    if limit not in LIMITS:raise ValueError('unknown target restriction consumer')
    records=[record for record in TIME.records(actor) if record.get('source')==SOURCE and KEY in record]
    if not records:return False
    import world_entities as WORLD
    index=WORLD.actor_index(engine)
    if index.get(actor.entity_id) is not actor:raise ValueError('target restriction needs the actual registered holder')
    for record in records:
        if record[KEY]!=list(LIMITS):raise ValueError('Unnerve restriction payload changed')
        origin=record.get('applied_by')
        if origin is None or index.get(getattr(origin,'entity_id',None)) is not origin:raise ValueError('Unnerve needs its actual source actor')
        deadline=record.get('count_deadline')
        if not isinstance(deadline,(list,tuple)) or len(deadline)!=2:raise ValueError('Unnerve full-round deadline required')
        C.integer(deadline[0],'Unnerve expiry round',1);C.integer(deadline[1],'Unnerve expiry count')
    if engine.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('Unnerve selected source changed')
    return True


def activate(engine,actor,ability,target):
    import body_state as BODY,partial_entities as PARTIAL,world_entities as WORLD
    import state_grants as GRANTS,frequency as F,turn as TURN
    if registration(engine.r,ability) is None:raise ValueError('reviewed target restriction source required')
    PARTIAL.require_complete(actor,'target restriction source');PARTIAL.require_complete(target,'target restriction target')
    index=WORLD.actor_index(engine)
    if index.get(actor.entity_id) is not actor or index.get(target.entity_id) is not target:raise ValueError('actual registered source and target required')
    if actor.abilities_suppressed or not any(registration(engine.r,name) for name in actor.abilities):raise ValueError('actual unsuppressed Unnerve required')
    if actor is target or not getattr(actor,'side',None) or not getattr(target,'side',None) or actor.side==target.side:raise ValueError('Unnerve requires one actual enemy')
    if not actor.on_field or not target.on_field or actor.fainted or target.fainted:raise ValueError('Unnerve requires on-field conscious participants')
    if not BODY.in_range(engine,actor,target,6):raise ValueError('Unnerve target must be within6 meters')
    count=TIME.current(engine)
    def apply(e,giver,holder):
        key='ability:'+NAME
        if not F.activation_allowed(giver,key,'임의',engine=e):raise ValueError('Unnerve frequency unavailable')
        if not TURN.spend(e,giver,'swift',NAME):raise ValueError('Unnerve Swift action unavailable')
        F.consume_activation(giver,key,'임의',engine=e)
        record={'source':SOURCE,KEY:list(LIMITS),'applied_by':giver,'count_deadline':(e.round_no+1,count)}
        TIME.install(e,holder,record)
        e.log(f'    {holder.name}: 긴장감, 한 라운드 동안 전투단계 상승과 음식 버프 소비 금지',SOURCE)
        return {'source':SOURCE,'source_actor_id':giver.entity_id,'target_id':holder.entity_id,'count_deadline':record['count_deadline']}
    return GRANTS.transition(engine,actor,apply,participants=(target,))
