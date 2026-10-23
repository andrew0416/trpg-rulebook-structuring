"""Owned Throwing Masteries contributes to actual native throwing ranges."""
from pathlib import Path
import json
import acquisition_qualification as Q,physical_limits as LIMITS
from source_context import verified_source

SOURCE='edge/투척-마스터리'
NAMES=(SOURCE,'투척 마스터리','Throwing Masteries')

def policy(rules):
    value=json.loads((Path(rules.root)/'data/throwing-masteries-policy.json').read_text(encoding='utf-8'))
    if value['rule_id']!=SOURCE or rules._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected native Throwing Masteries source required')
    verified_source(rules,value['source'],label='Throwing Masteries')
    verified_source(rules,value['csv_source'],label='Throwing Masteries duplicate CSV')
    source=rules.selection.units[SOURCE]['source']
    if source.get('file')!=value['source']['file'].removeprefix('input/') or source.get('lines')!=value['lines']:raise ValueError('Throwing Masteries literal source identity changed')
    return value

def owned_policy(actor):
    entries=actor.spec.get('edges',[])
    if type(entries) not in (list,tuple):raise ValueError('actual acquired Edge list required')
    if not any(value in NAMES for value in entries):return None
    value=policy(actor.r)
    Q.owned_skill_edge(actor,SOURCE,value,prerequisite_reason='Throwing Masteries requires Adept Acrobatics')
    return value

def validate(actor):
    return owned_policy(actor) is not None

def extend(actor,base,category):
    LIMITS.number(base,'native throwing range',minimum=0)
    value=owned_policy(actor)
    if value is None:return base
    if category not in value['categories']:raise ValueError('Throwing Masteries has no sourced range bonus for this category')
    return LIMITS.add_sources(base,[{'id':'throwing-masteries:'+category,'source':SOURCE,'value':value['range_bonus']}])['value']
