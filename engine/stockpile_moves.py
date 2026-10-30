"""Stockpile family consumers: 비축하기 r590 / 꿀꺽 r598 / 토해내기 r587; core en 11907-11923.

Both sources: Spit Up adds +8 Damage Base per Stockpiled count and cannot be
used at 0; Swallow heals by count, then sets the count to 0, and at 0 "does
nothing" — a paid no-op, not a refusal. Neither text consumes the count for
Spit Up. The Korean Swallow text names counts 1, 2 and 4; the English names
1, 2 and 3 (S-001: both selectable; no value is invented for the Korean 3).
"""
SPIT='move/토해내기'; SWALLOW='move/꿀꺽'; STOCKPILE='move/비축하기'
EDITIONS=('swallow-en','swallow-kr-literal')
GUARD='stockpile_edition'


def edition(rules):
    version=rules.ruleset.unit_versions.get(SWALLOW)
    if version not in (None,*EDITIONS):raise ValueError('explicit reviewed Swallow edition required')
    return version or 'swallow-en'


def mechanics(rules,mid,mm):
    """Source-bound adjustments on top of the existing declaration layers; other Moves untouched."""
    if mid==SPIT:
        effects=list(mm.get('effects_exec',[]))
        if not any(x.get('type')=='usage_restriction' and 'stockpile' in str(x.get('only_if','')) for x in effects):
            # r587 / en11907: "If the user has no Stockpiled count, Spit Up cannot be used" — refused before cost.
            effects.insert(0,{'type':'usage_restriction','only_if':'stockpile > 0','_source':'r587/en11907'})
        return {**mm,'effects_exec':effects}
    if mid!=SWALLOW:return mm
    literal=edition(rules)=='swallow-kr-literal';effects=[]
    for raw in mm.get('effects_exec',[]):
        x=dict(raw)
        if x.get('type')=='counter' and x.get('name')=='stockpile' and x.get('requires'):
            x['noop_when_unmet']=True   # r598 / en11923: "does nothing" at 0 is paid, not a prerequisite refusal
        if literal and x.get('type')=='alternate_effect' and x.get('if')=='stockpile >= 3':
            x['if']='stockpile == 4';x['note']='r598 literal: full heal at count 4; count 3 is not written'
            effects.append({'type':GUARD,'edition':'swallow-kr-literal','undefined_count':3})
        effects.append(x)
    return {**mm,'effects_exec':effects}


def preflight(e,a,t,effect,source):
    """Literal Korean edition: count 3 has no printed effect; refuse before cost instead of inventing one."""
    if source!=SWALLOW or effect.get('edition')!=edition(e.r) or effect.get('undefined_count')!=3:
        raise ValueError('exact selected Swallow edition guard required')
    if a.counters.get('stockpile',0)==3:
        raise ValueError('Korean Swallow text (r598) defines no effect at Stockpiled count 3; GM ruling required under the literal edition')
