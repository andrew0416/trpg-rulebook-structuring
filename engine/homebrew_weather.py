"""Reviewed hb-weather foundation; charges are handled by a separate adapter.

Reads selected source authority without storing a second weather registry or
mutating Rules caches. Raw core Move records remain unchanged.
"""
from copy import deepcopy
from pathlib import Path
import hashlib,json
from ruleset import ExcludedRuleSelection

SOURCE='hb-weather'
SOURCE_SHA256='fd593708dd202b960aa6487c108b21a406e2c07c3eff623b33edb97fff7fea83'
POLICY_SHA256='1b2d246c8416c813559d1db1c3c0deb7d06634a91bd0493dc8bd19b7d0138ba9'
LIFETIME='encounter_end_or_weather_replacement'
MOVE_ALIASES={'move/설경':'move/싸라기눈'}
# The implementation predates completion reconciliation for these optional
# clauses.  Keep their exact identities on every native occurrence so a saved
# ruling can be traced back to the paragraphs that produced, parameterised and
# ended its shared charge pool.
CLAUSE_IDS={
    'move/싸라기눈':('CHB-WEATHER-001','CHB-WEATHER-003','CHB-WEATHER-007','CHB-WEATHER-008'),
    'move/비바라기':('CHB-WEATHER-001','CHB-WEATHER-010','CHB-WEATHER-011'),
    'move/모래바람':('CHB-WEATHER-001','CHB-WEATHER-013','CHB-WEATHER-014'),
    'move/쾌청':('CHB-WEATHER-001','CHB-WEATHER-016','CHB-WEATHER-017'),
}
OVERRIDDEN_AMBIENT_NOTES=frozenset(('싸라기눈 동안 얼음타입이 아닌 모든 포켓몬은 턴 시작 시 소량의 체력(tick) 손실',
                                  '모래바람 동안 땅·바위·강철이 아닌 포켓몬은 턴 시작 시 소량의 체력(tick) 손실'))

def policy(rules):
    try:selected=rules.selection.require_supported_version(SOURCE)
    except ExcludedRuleSelection:return None
    if selected!=SOURCE or rules.selection.units[selected]['source'].get('file')!='hb-weather.md':
        raise ValueError('reviewed hb-weather source identity required')
    root=Path(rules.root)
    data=(root/'data/homebrew-weather-policy.json').read_bytes()
    if hashlib.sha256(data).hexdigest()!=POLICY_SHA256:
        raise ValueError('reviewed homebrew weather policy changed')
    payload=json.loads(data)
    if payload['schema_version']!=1 or payload['source']!=SOURCE or payload['source_files']!={'input/hb-weather.md':SOURCE_SHA256}:
        raise ValueError('homebrew weather policy provenance changed')
    if hashlib.sha256((root/'input/hb-weather.md').read_bytes()).hexdigest()!=SOURCE_SHA256:
        raise ValueError('reviewed hb-weather source text changed')
    return payload

def enabled(rules):return policy(rules) is not None

def canonical_weather(rules,name):
    selected=policy(rules)
    return name if selected is None else selected['aliases'].get(name,name)

def definition(rules,move_id):
    selected=policy(rules)
    return None if selected is None else selected['moves'].get(MOVE_ALIASES.get(move_id,move_id))

def provenance(move_id):
    clauses=CLAUSE_IDS.get(MOVE_ALIASES.get(move_id,move_id))
    if clauses is None:raise ValueError('homebrew weather clause provenance requires a native Move')
    return {'source_id':SOURCE,'source_sha256':SOURCE_SHA256,'policy_sha256':POLICY_SHA256,
            'native_move_id':move_id,'lifetime':LIFETIME,'clause_ids':list(clauses)}

def adapt_move(rules,move):
    row=definition(rules,move['id'])
    if row is None:return move
    result=deepcopy(move)
    for key in ('type','frequency','ac','class','range','keywords'):result[key]=deepcopy(row[key])
    result['_weather_policy']=provenance(move['id'])
    result['effect']='Weather lasts until encounter end or replacement; selected source hb-weather.'
    return result

def adapt_mechanics(rules,move_id,mechanics,confidence):
    row=definition(rules,move_id)
    if row is None:return mechanics,confidence
    result=deepcopy(mechanics)
    if move_id in MOVE_ALIASES:result['effects_exec']=[]
    result['effects_exec']=[effect for effect in result.get('effects_exec',[]) if effect.get('type')!='set_weather' and
                           not (set(effect)=={'type','note'} and effect['type']=='rule' and effect['note'] in OVERRIDDEN_AMBIENT_NOTES)]
    result['effects_exec'].append({'type':'set_weather','weather':row['weather'],'rounds':None,
                                   '_weather_policy':provenance(move_id)})
    return result,confidence+'+hb-weather'

def require_actor(engine,actor,move_id):
    if definition(engine.r,move_id) is None:return
    roster=[*getattr(engine.gm,'everyone',()),*(getattr(engine,'everyone',None) or ()),
            *(getattr(engine,'_encounter_actors',None) or ())]
    import world_entities as WORLD
    if actor is None or not any(person is actor for person in roster) or WORLD.actor_index(engine).get(actor.entity_id) is not actor:
        raise ValueError('homebrew weather requires an actual registered actor')

def require_request(engine,weather,rounds,move_id,origin,metadata):
    if origin!='move' or definition(engine.r,move_id) is None:return
    selected=[effect for effect in engine.r.move_mech(move_id)[0].get('effects_exec',[]) if effect.get('type')=='set_weather']
    if not any(effect.get('weather')==weather and effect.get('rounds',5)==rounds and
               effect.get('_weather_policy')==metadata for effect in selected):
        raise ValueError('weather request differs from selected native policy or explicit GM override')
    if metadata is None:
        receipt={'source_policy':provenance(move_id),
                 'rulings':deepcopy(engine.r.rulings.effects.get(move_id,[]))}
        validate_override(engine.r,move_id,weather,rounds,receipt)
        return receipt

def validate_override(rules,move_id,weather,rounds,receipt):
    if type(receipt) is not dict or set(receipt)!={'source_policy','rulings'} or receipt['source_policy']!=provenance(move_id):
        raise ValueError('weather GM override source receipt changed')
    rows=receipt['rulings']
    if type(rows) is not list or not rows:raise ValueError('actual recorded weather GM override required')
    for row in rows:
        if (type(row) is not dict or set(row)!={'op','match','effect','scope','reason'} or
            row['op'] not in ('set','replace','remove','add') or not isinstance(row['reason'],str) or
            not row['reason'].strip() or not isinstance(row['scope'],str) or not row['scope'].strip()):
            raise ValueError('explicit weather GM ruling operation and reason required')
    from rulings import Rulings
    recorded=Rulings();recorded.effects[move_id]=rows
    base,confidence=rules._move_mech(move_id)
    base,_=adapt_mechanics(rules,move_id,base,confidence)
    resolved=recorded.apply_effects(move_id,base)
    if (type(rounds) is not int or rounds<=0 or not any(effect.get('type')=='set_weather' and
        effect.get('weather')==weather and effect.get('rounds',5)==rounds and
        effect.get('_weather_policy') is None for effect in resolved.get('effects_exec',[]))):
        raise ValueError('weather occurrence differs from its recorded finite GM override')

def preflight(engine,weather,rounds,move_id,actor,metadata):
    row=definition(engine.r,move_id)
    if row is None or metadata!=provenance(move_id) or weather!=row['weather'] or rounds is not None:
        raise ValueError('native homebrew weather producer or lifetime changed')
    engine.r._selected_rule(move_id)
    require_actor(engine,actor,move_id)
    if not engine.encounter_active:raise ValueError('homebrew weather requires an open encounter')
    import weather_blessings as BLESSINGS
    BLESSINGS.preflight(engine,actor,move_id)
    if engine.weather!=weather:return None
    ruling=deepcopy(engine.rulings.mech.get(SOURCE,{}).get('same_weather_reapplication'))
    validate_reapplication_ruling(ruling)
    import weather_state as WEATHER
    previous=getattr(engine,WEATHER.KEY)['active']
    return {'previous_occurrence_id':previous['id'],'ruling':ruling}


def validate_reapplication_ruling(ruling):
    if (type(ruling) is not dict or set(ruling)!={'value','scope','reason'} or
        ruling['value']!='replace' or ruling['scope'] not in ('scene','campaign') or
        not isinstance(ruling['reason'],str) or not ruling['reason'].strip()):
        raise ValueError('same-weather recast requires a recorded replace ruling with reason and scene/campaign scope')


def validate_reapplication(engine,record):
    """Validate the creation receipt, even after its scene ruling has expired."""
    import weather_state as WEATHER
    previous=next((r for r in getattr(engine,WEATHER.KEY)['history'] if r['id']==record['id']-1),None)
    replaced_same=bool(previous and previous['weather']==record['weather'] and
                       previous.get('end_reason')=='replaced' and
                       previous.get('end_source')==record['source_id'] and
                       previous.get('ended_round')==record['started_round'])
    receipt=record.get('reapplication')
    if receipt is None:
        if replaced_same:raise ValueError('same-weather replacement lost its recorded ruling')
        return
    if (not replaced_same or type(receipt) is not dict or
        set(receipt)!={'previous_occurrence_id','ruling'} or
        type(receipt['previous_occurrence_id']) is not int or
        receipt['previous_occurrence_id']!=previous['id']):
        raise ValueError('same-weather replacement receipt does not match its actual predecessor')
    validate_reapplication_ruling(receipt['ruling'])

def validate_record(engine,record,*,active,index=None):
    selected=policy(engine.r)
    metadata=record.get('policy')
    override=record.get('policy_override')
    native=record.get('source_id')
    row=definition(engine.r,native)
    if metadata is None and override is None:
        if row is not None:raise ValueError('native homebrew weather lost its selected policy provenance')
        return False
    if row is None or (metadata is not None and metadata!=provenance(native)):
        raise ValueError('weather selected policy or native source changed')
    if metadata is not None and override is not None:raise ValueError('weather requires one source authority receipt')
    expected={'weather','source_id','origin','reason','started_round','duration','deadline_round',
              'deadline_count','id','actor_id','started_seconds'}
    if 'item_extension' in record:expected.add('item_extension')
    expected.add('policy' if metadata is not None else 'policy_override')
    if metadata is not None and 'reapplication' in record:expected.add('reapplication')
    if not active:expected|={'ended_round','end_source','end_reason'}
    if set(record)!=expected:raise ValueError('unexpected homebrew weather record field')
    if record['origin']!='move':raise ValueError('weather source authority requires its actual native Move')
    if metadata is not None:
        if (record['weather']!=row['weather'] or
            any(record[key] is not None for key in ('duration','deadline_round','deadline_count'))):
            raise ValueError('homebrew weather has only its exact encounter lifetime')
        validate_reapplication(engine,record)
    else:
        duration=record.get('item_extension',{}).get('base_rounds',record['duration'])
        validate_override(engine.r,native,record['weather'],duration,override)
    import world_entities as WORLD
    actual=WORLD.actor_index(engine) if index is None else index
    if not isinstance(record['actor_id'],str) or record['actor_id'] not in actual:
        raise ValueError('homebrew weather source actor is missing')
    stamp=record['started_seconds']
    if type(stamp) is not int or not 0<=stamp<=engine.elapsed_seconds:
        raise ValueError('homebrew weather start time is invalid')
    if metadata is not None and active and not engine.encounter_active:raise ValueError('encounter weather remains active after encounter end')
    if not active and (type(record['ended_round']) is not int or not record['started_round']<=record['ended_round']<=engine.round_no):
        raise ValueError('homebrew weather ending round is invalid')
    return True

def end_encounter(engine):
    import weather_state as WEATHER
    if not hasattr(engine,WEATHER.KEY):return
    WEATHER.validate(engine)
    record=getattr(engine,WEATHER.KEY)['active']
    if record and record.get('policy',{}).get('lifetime')==LIFETIME:
        WEATHER.clear(engine,source_id=SOURCE,reason='encounter ended')
