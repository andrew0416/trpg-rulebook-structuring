"""Reviewed selectable TM conditions, derived from the authenticated originals.

This production adapter supplies missing edition metadata, not replacement
default definitions or verification registry rows. S-001 preserves real source
differences; the English Core only fills the CSV's omitted Frozen timing.
"""
from copy import deepcopy
import csv
import io
import json

TM={'file':'input/db/tm.csv','sha256':'dd06395776044c0c13e698420aead38907d6969f475caf8485ec2cd1a2259f44'}
CORE={'file':'source-audit/ptu-core-1.05.pdf','sha256':'e5e0371031601c3ad0a04056771c17599a2d8826e5a5102ccd37f9b368108907'}
CSV_VERSION='csv-core-1.05'
ROWS={'마비':73,'풀죽음':83,'헤롱헤롱':85,'억압':88,'얼음':113}
PROFILES={
    'core-csv-status-1.05':{
        'description':'Explicit original Core 1.05/CSV status editions; default Korean/February 2016 statuses remain unchanged.',
        'sources':['core'],'variants':[],
        'unit_versions':{'condition/마비':CSV_VERSION,'condition/혼란':'core-1.05',
                         'condition/풀죽음':CSV_VERSION,'condition/헤롱헤롱':CSV_VERSION,'condition/억압':CSV_VERSION}},
    'core-csv-frozen-homebrew':{
        'description':'Core with the explicitly selected TM CSV row113 Frozen homebrew; printed Frozen remains the core default.',
        'sources':['core'],'variants':[],
        'unit_versions':{'condition/얼음':'csv-homebrew','condition/혼란':'core-1.05'}}}


def _same(left,right):
    def encoded(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
    return encoded(left)==encoded(right)


def profile(name,declared):
    if name not in PROFILES:return declared
    expected=PROFILES[name]
    if declared is not None:
        if not _same({key:value for key,value in declared.items() if key!='description'},{key:value for key,value in expected.items() if key!='description'}):
            raise ValueError('reviewed CSV condition profile changed; explicit source review required')
        return declared
    return deepcopy(expected)


def edition(condition):
    effects={
        '마비':[{'type':'combat_stage','stat':'spe','delta':-4,'while':'afflicted'},
               {'type':'save','dc':5,'timing':'start_of_turn','on_success':'act_normally'},
               {'type':'action_limit','forbidden':['standard','shift','swift','full'],'if':'save_failed','source':'condition/마비'},
               {'type':'immunity','types':['전기'],'actor_kind':'pokemon'}],
        '풀죽음':[{'type':'next_turn_in_application_round','no_actions':True,'expires':'round_end'}],
        '헤롱헤롱':[{'type':'infatuation_start_turn','blocked_max':10,'normal_max':18,'cure_min':19,
                  'target':'actual_beloved','prohibits':['move','attack']}],
        '억압':[{'type':'suppressed_frequency','pp_up':False,'at_will':'every_other_turn',
               'every_other_turn':'scene','scene_2':'scene'}],
        '얼음':[{'type':'no_actions'},{'type':'evasion_disabled'},
              {'type':'save','dc':12,'timing':'end_of_turn','on_success':'cure'},
              {'type':'immunity','types':['얼음'],'actor_kind':'pokemon'},
              {'type':'save_modifier','if_type':'불꽃','dc':8},
              {'type':'cured_by_damage_of_types','types':['불꽃','격투','바위','강철']},
              {'type':'save_modifier','weather':{'쾌청':2,'싸라기눈':-4}}]}[condition]
    authority=dict(TM,row=ROWS[condition],columns=[4,5])
    if condition=='얼음':authority['timing_authority']='PTU 1.05 Core p246: end of each turn; S-001 fills omitted Korean timing only'
    else:authority.update(original_document='PTU 1.05 Core',page=246 if condition=='마비' else 247)
    return {'effects':effects,'authority':authority}


def source(rules,condition):
    from source_context import verified_source
    content=verified_source(rules,TM,label='selectable CSV condition')
    rows=list(csv.reader(io.StringIO(content.decode('utf-8-sig'),newline='')))
    number=ROWS[condition]
    expected='얼음 [홈브류]' if condition=='얼음' else condition
    if len(rows)<number or len(rows[number-1])<5 or rows[number-1][3]!=expected or not rows[number-1][4].strip():
        raise ValueError('reviewed logical CSV condition record required')
    verified_source(rules,CORE,source_root='source-audit',label='Core 1.05 condition timing and edition')


def install(rules):
    """Attach only an explicitly selected missing edition, preserving its base."""
    for condition in ROWS:
        key='csv-homebrew' if condition=='얼음' else CSV_VERSION
        uid='condition/'+condition
        if rules.ruleset.unit_versions.get(uid)!=key:continue
        source(rules,condition)
        data=rules.units[uid]['mech']['data']
        expected=edition(condition)
        if key in data and not _same(data[key],expected):
            raise ValueError('reviewed CSV condition edition changed')
        if key not in data:data[key]=expected


def modern_paralysis_definition(rules,definition):
    """Exclude only exact reviewed auxiliary metadata from the unchanged base pin."""
    if CSV_VERSION not in definition:return definition
    if not _same(definition[CSV_VERSION],edition('마비')):
        raise ValueError('unreviewed CSV Paralysis metadata cannot be excluded from modern fingerprint')
    source(rules,'마비')
    return {key:value for key,value in definition.items() if key!=CSV_VERSION}
