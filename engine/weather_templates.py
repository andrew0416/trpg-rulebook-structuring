"""Bonus-weather ideas and durable GM designs; this API never creates Moves."""
from copy import deepcopy
from dataclasses import dataclass
import hashlib,json
from pathlib import Path
import type_state as TYPES

SOURCE='hb-weather-1'
KEY='_weather_templates'
SOURCE_SHA256='fd593708dd202b960aa6487c108b21a406e2c07c3eff623b33edb97fff7fea83'
_SOURCE={'document':'PTK 코어 룰북 (PTU 1.05 한국어 번역, 포켓몬스터 TRPG 한국 지부)',
         'license':'팬 제작 무료 배포물 / 번역 저작물 — 비공개 실험용',
         'path':['hb-weather'],'file':'hb-weather.md','lines':[69,84]}

import resolution_transaction as _FINGERPRINTS

@dataclass(frozen=True)
class WeatherTemplate:
    """Immutable source row, with no inferred base/Move type."""
    name:str
    english_name:str
    boost_types:tuple[str,str]
    reduce_type:str
    source_id:str=SOURCE
    @property
    def id(self):return 'weather-template/'+self.name
    def to_dict(self):
        return {'id':self.id,'name':self.name,'english_name':self.english_name,
                'boost_types':list(self.boost_types),'reduce_type':self.reduce_type,
                'source_id':self.source_id,'source':deepcopy(_SOURCE),'source_sha256':SOURCE_SHA256,
                'origin':'catalog','kind':'template','creates_native_move':False}

_SAMPLES=(
    WeatherTemplate('산성비','Acid Rain',('독','강철'),'땅'),
    WeatherTemplate('유성우','Starshower',('노말','강철'),'격투'),
    WeatherTemplate('열번개','Heat Lightning',('전기','불꽃'),'땅'),
    WeatherTemplate('백야','Midnight Sun',('악','고스트'),'페어리'),
    WeatherTemplate('태풍','Typhoon',('비행','물'),'전기'),
    WeatherTemplate('군집지령','Hive Order',('벌레','풀'),'불꽃'),
    WeatherTemplate('고공','Thin Air',('에스퍼','격투'),'고스트'),
    WeatherTemplate('마법안개','Mystic Mist',('페어리','드래곤'),'강철'),
    WeatherTemplate('마녀의시간','Witching Hour',('고스트','페어리'),'악'),
)

def require(rules,source_id=SOURCE):
    if source_id!=SOURCE or rules._selected_rule(SOURCE)!=SOURCE:
        raise ValueError('bonus weather requires its exact selected source')
    if rules.selection.units[SOURCE].get('source')!={**_SOURCE,'sha256':SOURCE_SHA256}:
        raise ValueError('bonus weather source provenance changed')
    root=Path(rules.root)
    if hashlib.sha256((root/'input/hb-weather.md').read_bytes()).hexdigest()!=SOURCE_SHA256:
        raise ValueError('bonus weather source text changed')
    policy=json.loads((root/'data/homebrew-weather-policy.json').read_text(encoding='utf-8'))
    expected={r.name:{'english_name':r.english_name,'boost_types':list(r.boost_types),
              'reduce_type':r.reduce_type,'source':SOURCE,'kind':'template','creates_native_move':False} for r in _SAMPLES}
    if policy.get('samples')!=expected or policy.get('source_files',{}).get('input/hb-weather.md')!=SOURCE_SHA256:
        raise ValueError('bonus weather sample policy differs from its canonical source')

def catalog(rules):
    """Nine frozen typed source samples, admitted by the selected source."""
    require(rules)
    for sample in _SAMPLES:
        TYPES.validate_types(rules,[*sample.boost_types,sample.reduce_type],label='sample weather types')
    return tuple(deepcopy(sample) for sample in _SAMPLES)

def signature(row):
    return _FINGERPRINTS.json_fingerprint(row, sort_keys=True, compact=False, allow_nan=True)

def state(engine):
    if not hasattr(engine,KEY):return {'version':1,'definitions':{}}
    current=getattr(engine,KEY)
    if type(current)is not dict or set(current)!={'version','definitions'} or type(current['version'])is not int or current['version']!=1 or type(current['definitions'])is not dict:
        raise ValueError('invalid weather-template state envelope')
    return current

def weaknesses(rules,defending_type):
    return {attack for attack in TYPES.allowed_types(rules) if TYPES.matchup(rules,attack,defending_type)>1}

def validate_definition(rules,row):
    keys={'id','name','base_type','boost_types','reduce_type','source_id','source','source_sha256','reason','origin','kind','creates_native_move'}
    if type(row)is not dict or set(row)!=keys:raise ValueError('weather design must be an explicit closed template definition')
    require(rules,row['source_id'])
    if not isinstance(row['id'],str) or not row['id'].startswith('weather-template/') or not row['id'].removeprefix('weather-template/').strip() or row['id'] in {sample.id for sample in _SAMPLES}:
        raise ValueError('custom weather design needs a distinct stable template identity')
    if not isinstance(row['name'],str) or not row['name'].strip():raise ValueError('custom weather design needs its actual name')
    if row['origin']!='custom' or row['kind']!='template' or row['creates_native_move']is not False or row['source']!=_SOURCE or row['source_sha256']!=SOURCE_SHA256:
        raise ValueError('weather template origin or source provenance changed')
    if not isinstance(row['reason'],str) or not row['reason'].strip():raise ValueError('custom weather design requires the actual GM rationale')
    TYPES.validate_types(rules,[row['base_type']],label='explicit base/Move type')
    boosts=row['boost_types']
    if type(boosts)is not list or len(boosts)!=2:raise ValueError('custom weather requires exactly two distinct boosted types')
    TYPES.validate_types(rules,boosts,label='weather boosted types')
    TYPES.validate_types(rules,[row['reduce_type']],label='weather reduced type')
    shared=weaknesses(rules,boosts[0])&weaknesses(rules,boosts[1])
    # Only the no-shared case is constrained in the source. No additional
    # shared-weakness obligation is inferred for an explicit GM reduction.
    if not shared and row['reduce_type'] not in weaknesses(rules,row['base_type']):
        raise ValueError('without shared weakness reduction must be a weakness of the explicit base')
    return row

def validate(engine):
    current=state(engine)
    if hasattr(engine,KEY):require(engine.r)
    for identity,record in current['definitions'].items():
        if type(record)is not dict or set(record)!={'definition','definition_sha256'}:raise ValueError('invalid weather-template definition record')
        row=validate_definition(engine.r,record['definition'])
        if identity!=row['id'] or record['definition_sha256']!=signature(row):raise ValueError('weather template definition identity or content changed')
    return True

def define(engine,identity,*,name,base_type,boost_types,reduce_type,reason,source_id=SOURCE):
    """Record a GM idea; base_type is its explicitly chosen proposed Move type.

    This grants no executable Move or weather effect. Revisions need a new
    identity. No frequency, AC, range, duration or activation is inferred.
    """
    validate(engine)
    row={'id':identity,'name':name,'base_type':base_type,'boost_types':deepcopy(boost_types),
         'reduce_type':reduce_type,'source_id':source_id,'source':deepcopy(_SOURCE),
         'source_sha256':SOURCE_SHA256,'reason':reason,'origin':'custom','kind':'template','creates_native_move':False}
    validate_definition(engine.r,row)
    current=state(engine)
    if identity in current['definitions']:raise ValueError('weather-template identities are immutable; choose a new identity')
    current['definitions'][identity]={'definition':row,'definition_sha256':signature(row)}
    setattr(engine,KEY,current)
    return deepcopy(row)

def definition(engine,identity):
    """Inspect a catalog sample or GM design as a detached JSON object."""
    require(engine.r);validate(engine)
    if identity in state(engine)['definitions']:return deepcopy(state(engine)['definitions'][identity]['definition'])
    for sample in catalog(engine.r):
        if identity==sample.id:return sample.to_dict()
    raise ValueError('unknown weather-template identity')

