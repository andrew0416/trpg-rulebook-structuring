"""Pure planning for explicitly continuous thirty-minute rest intervals.

Source scope: input/ch07-combat.md resting paragraph (uninterrupted 30 minutes,
first eight resting hours per day). This module neither advances time nor heals
HP, declares days, classifies activities, or grants four-hour extended-rest effects.
The caller owns daily accounting and injury-based healing eligibility.
"""


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _rest_id(value):
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ValueError("rest_id must be None or a nonempty string")
    return value


def _context(*, gap_count, round_no, day, injuries, base_max_hp,
             cap_minutes, block_minutes):
    return dict(
        gap_count=_integer(gap_count, "gap_count"),
        round_no=_integer(round_no, "round_no"),
        day=_integer(day, "day"),
        injuries=_integer(injuries, "injuries"),
        base_max_hp=_integer(base_max_hp, "base_max_hp", 1),
        cap_minutes=_integer(cap_minutes, "cap_minutes"),
        block_minutes=_integer(block_minutes, "block_minutes", 1),
    )


def _validate_record(record):
    if not isinstance(record, dict):
        raise ValueError("record must be a dictionary or None")
    required = {"id", "end_seconds", "carry_minutes", "total_minutes", "context"}
    if not required <= record.keys():
        raise ValueError("incomplete rest interval record")
    _rest_id(record["id"])
    _integer(record["end_seconds"], "record.end_seconds")
    carry = _integer(record["carry_minutes"], "record.carry_minutes")
    total = _integer(record["total_minutes"], "record.total_minutes")
    context = record["context"]
    keys = {"gap_count", "round_no", "day", "injuries", "base_max_hp", "cap_minutes", "block_minutes"}
    if not isinstance(context, dict) or context.keys() != keys:
        raise ValueError("invalid rest interval context")
    _context(**context)
    if carry >= context["block_minutes"] or carry > total:
        raise ValueError("invalid rest interval remainder")


def plan_rest(record, *, rest_id, now_seconds, gap_count, round_no, day,
              injuries, base_max_hp, minutes, rested_minutes_today,
              cap_minutes=480, block_minutes=30):
    """Return a fresh interval record and newly earned time blocks.

    A nonempty string ID explicitly declares the same uninterrupted rest bout.
    Reusing it requires exact temporal adjacency and unchanged checked context.
    None or a new ID begins an independent bout and discards the prior remainder.
    Rejected continuity never silently resets or joins intervals. Input is not
    mutated. The caller must commit this plan with the shared clock and its daily
    resting-minute ledger, and apply healing eligibility separately.
    """
    _rest_id(rest_id)
    _integer(now_seconds, "now_seconds")
    _integer(minutes, "minutes")
    _integer(rested_minutes_today, "rested_minutes_today")
    context = _context(gap_count=gap_count, round_no=round_no, day=day,
                       injuries=injuries, base_max_hp=base_max_hp,
                       cap_minutes=cap_minutes, block_minutes=block_minutes)
    if record is not None:
        _validate_record(record)
    usable = min(minutes, max(0, cap_minutes - rested_minutes_today))
    import activity_jobs as JOBS
    previous=None if record is None else dict(id=record['id'],end_seconds=record['end_seconds'],
        carry=record['carry_minutes'],total=record['total_minutes'],context=record['context'])
    interval,blocks=JOBS.plan_interval(previous,interval_id=rest_id,now_seconds=now_seconds,
        duration=minutes,usable=usable,block=block_minutes,context=context,unit_seconds=60)
    return dict(id=interval['id'],end_seconds=interval['end_seconds'],carry_minutes=interval['carry'],
                total_minutes=interval['total'],context=interval['context']),blocks


ACTIVITIES='rest_activity_history'


def validate_actor(c):
    """Durable history is source evidence, not permission to invent elapsed time."""
    _integer(c.spec.get('rested_minutes_today',0),'rested_minutes_today')
    record=c.spec.get('rest_interval')
    if record is not None:_validate_record(record)
    history=c.spec.get(ACTIVITIES,[])
    if not isinstance(history,list):raise ValueError('rest activity history must be a list')
    for row in history:
        if not isinstance(row,dict) or row.get('source')!='combat/resting':raise ValueError('rest activity source required')
        if type(row.get('qualifies_as_rest')) is not bool:raise ValueError('explicit GM activity classification required')
        if not isinstance(row.get('reason'),str) or not row['reason'].strip():raise ValueError('GM activity reason required')
        for key in ('start','end','day'):_integer(row.get(key),'activity '+key)
        _integer(row.get('minutes'),'activity minutes',1)
        if row['end']-row['start']!=row['minutes']*60:raise ValueError('activity duration mismatch')
        _rest_id(row.get('rest_id'))
        if not row['qualifies_as_rest'] and row.get('rest_id') is not None:raise ValueError('non-rest cannot claim a rest bout')


def validate_world(engine,actors):
    for c in actors.values():
        validate_actor(c)
        record=c.spec.get('rest_interval')
        day=c.spec.get('frequency_state',{}).get('day',0)
        if record is not None:
            context=record['context']
            if (record['end_seconds']>engine.elapsed_seconds or context['day']>day
                    or context['round_no']>engine.round_no or context['gap_count']>len(engine.unresolved_time_intervals)):
                raise ValueError('rest interval claims future or absent world time')
        for row in c.spec.get(ACTIVITIES,[]):
            if row['end']>engine.elapsed_seconds or row['day']>day:raise ValueError('rest activity claims future world time')
