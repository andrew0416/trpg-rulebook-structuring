"""Actual underground sensing via the common route and bounded-information owner."""
from pathlib import Path
import json
import state_grants as G,skill_modifiers as S,perception_observe as O
import capability_parameter_edges as P
from source_context import verified_source

SOURCE='capability/진동감지'
EDGE='poke_edge/지진계'
ALIASES={EDGE:EDGE,'지진계':EDGE,'Seismometer':EDGE}


def policy(rules):
    value=json.loads((Path(rules.root)/'data/tremorsense-policy.json').read_text(encoding='utf-8'))
    verified_source(rules,value['source'],label='Tremorsense')
    if value.get('rule_id')!=SOURCE or rules._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected native Tremorsense source required')
    O.declaration(value['declaration'])
    if value['declaration']['source']!=SOURCE:raise ValueError('native Tremorsense declaration identity required')
    return value


def declaration(actor):
    value=policy(actor.r)['declaration']
    parameter=P.parameters(actor,EDGE)
    if parameter:
        # This is a range-only projection. The actual skill pool is unchanged.
        value['range']['maximum']+=S.effective_rank(actor.r,actor,parameter['range_skill'])
    return O.declaration(value)


def sense(engine,observer,target,*,information=None):
    return O.observe(engine,observer,target,declaration(observer),information=information)
