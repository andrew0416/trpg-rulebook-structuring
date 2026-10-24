"""Defense Curl's complete Core and September definitions on native condition instances."""
from copy import deepcopy
from pathlib import Path
import json
import effect_instances as E
import condition_instances as CONDITIONS
import root_resolution as ROOT

MOVE='move/웅크리기'
NAME='웅크리기'
CHOICE='defense_curl_source'
ROLLING={'move/구르기','move/아이스볼'}
_POLICY=json.loads((Path(__file__).resolve().parents[1]/'data/defense-curl-policy.json').read_text(encoding='utf-8'))


def policy(rules):
    from source_context import verified_source
    verified_source(rules,_POLICY['source'],label='Defense Curl Core and September Playtest')
    if rules._selected_rule(MOVE)!=MOVE:raise ValueError('selected Defense Curl source requires its own adapter')
    return _POLICY


def document(rules):
    data=policy(rules)
    return {'schema':1,'id':'native/defense-curl-source','variants':[{
        'rule_id':MOVE,'source':data['source'],
        'values':{'variant':{'$input':'source_text'},'definitions':data['variants']},
        'inputs':{'source_text':{'type':'string','authority':'gm','decision_kind':'source_conflict',
            'choices':list(data['variants']),'question':'Choose the complete Core or September Playtest Defense Curl definition.'}}}]}


def source_choices(rules):
    return __import__('source_policy').resolve(rules,document(rules))


def selected(rules,binding=None):
    data=policy(rules)
    if binding is None:return 'core',data['variants']['core']
    if type(binding)is not dict or set(binding)!={'choice','resolution'}:raise ValueError('actual Defense Curl source binding required')
    choice=binding['choice'];resolved=binding['resolution'];doc=document(rules)
    if type(choice)is not dict or set(choice)!={'value','reason','scope'}:raise ValueError('scoped Defense Curl source choice required')
    E.text(choice['reason'],'Defense Curl source reason')
    import source_selection as SOURCE
    values=SOURCE.policy_values(resolved['source_policy_binding'],doc['variants'])
    variant=choice['value']
    if (variant not in data['variants'] or resolved['status']!='PolicyValuesReady'
            or resolved['selected_id']!=MOVE or resolved['definition_hash']!=ROOT.fingerprint(doc)
            or resolved['values']!={'variant':variant,'definitions':values['definitions']}
            or resolved['decision_scope']!=choice['scope']
            or resolved['inputs_hash']!=ROOT.fingerprint({'context':{},'decisions':{'source_text':choice},'state':{}})
            or resolved['decision_evidence']!=[{'input':'source_text','reason':choice['reason'],'decision_kind':'source_conflict','scope':choice['scope']}]):
        raise ValueError('Defense Curl producing source choice changed')
    return variant,data['variants'][variant]


def choose_source(engine,actor,variant,*,reason):
    import world_entities as W,state_grants as G,source_policy as SOURCE
    W.require_actors(engine,actor)
    decision={'value':variant,'reason':reason,'scope':source_choices(engine.r)['decision_scope']}
    binding={'choice':decision,'resolution':SOURCE.resolve(engine.r,document(engine.r),decisions={'source_text':decision})}
    selected(engine.r,binding)
    def apply(e,a):
        before=deepcopy(a.spec.get(CHOICE));a.spec[CHOICE]=deepcopy(binding)
        e.gm._rec('Defense Curl source',before,binding,reason,who=a)
        return deepcopy(binding)
    return G.transition(engine,actor,apply,include_rulings=True)


def mechanics(rules,mid,mm):
    if mid!=MOVE:return mm
    if mm!=policy(rules)['raw_mechanics']:raise ValueError('Defense Curl complete selected effect declaration changed')
    return {'effects_exec':[deepcopy(_POLICY['raw_mechanics']['effects_exec'][0])]}


def definition(rules):
    policy(rules)
    return {'payload':{'kind':'custom_condition','condition':NAME,'class':'other','operation':'defense_curl'},
            'raw':deepcopy(_POLICY['raw_mechanics']['effects_exec'][0])}


def live(actor):
    rows=CONDITIONS.records(actor,NAME)
    if len(rows)>1:raise ValueError('one actual Defense Curl state required')
    for row in rows:validate_record(actor,row)
    if NAME in actor.conditions and not rows:raise ValueError('legacy Defense Curl requires actual source adoption or cure')
    return rows[0] if rows else None


def prepare(engine,actor,target,effect,source):
    __import__('world_entities').require_actors(engine,actor,target)
    row=definition(engine.r)
    if source!=MOVE or actor is not target or {k:v for k,v in effect.items() if not k.startswith('_')}!=row['raw']:
        raise ValueError('Defense Curl requires its actual Self Move and selected payload')
    selected(engine.r,actor.spec.get(CHOICE));live(actor)
    return row


def grant(engine,actor,target,effect,source):
    prepare(engine,actor,target,effect,source)
    binding=deepcopy(actor.spec.get(CHOICE));variant,values=selected(engine.r,binding)
    old=live(actor)
    if old is not None:CONDITIONS.end(engine,actor,old,{'kind':'defense_curl_end','boundary':'replaced'})
    payload=dict(definition(engine.r)['payload'],variant=variant)
    row=E.create(engine,actor,kind='condition',source=MOVE,payload=payload,
        capacity={'bucket':'condition:'+NAME,'source':MOVE},
        lifetime={'boundary':'defense_curl_source_end','ends_on':list(values['ends_on'])},applied_by=actor)
    row[CHOICE]=binding
    actor.custom_conditions.setdefault(CONDITIONS.KEY,[]).append(row);actor.conditions.add(NAME)
    engine.time_actors([actor])
    if values['defense_stages']:engine.change_stage(actor,'def',values['defense_stages'])
    engine.log('    '+actor.name+': Defense Curl '+variant,MOVE)
    return True


def validate_record(actor,row,*,terminal=False):
    E.validate(row,actor=actor,terminal=terminal)
    variant,values=selected(actor.r,row.get(CHOICE))
    if (CHOICE not in row or row['source']!=MOVE or row[E.KEY]['kind']!='condition'
            or row['effect']!=dict(definition(actor.r)['payload'],variant=variant)
            or row[E.KEY]['capacity']!={'bucket':'condition:'+NAME,'source':MOVE}
            or row[E.KEY]['lifetime']!={'boundary':'defense_curl_source_end','ends_on':list(values['ends_on'])}):
        raise ValueError('Defense Curl source, payload or lifetime changed')
    if not terminal and NAME not in actor.conditions:raise ValueError('Defense Curl presence projection missing')
    if terminal:
        event=row[E.KEY]['end_event']
        if event.get('kind')!='condition_cure' and (event.get('kind')!='defense_curl_end'
                or event.get('boundary') not in [*values['ends_on'],'replaced']):
            raise ValueError('Defense Curl actual source ending required')
    return True


def values(actor):
    row=live(actor)
    return None if row is None else selected(actor.r,row[CHOICE])[1]


def slowed(actor):
    value=values(actor)
    return bool(value and value['slowed_without_rolling_move']
                and not any(actor.r.move_id(mid) in ROLLING for mid in actor.moves))


def accuracy(actor,move):
    value=values(actor)
    return value['accuracy_penalty'] if value and move['id'] not in ROLLING else 0


def damage_bonus(actor,move):
    value=values(actor)
    return value['rolling_damage_bonus'] if value and move['id'] in ROLLING else 0


def reduction(actor):
    value=values(actor)
    return value['damage_reduction'] if value else 0


def critical_immune(actor):
    value=values(actor)
    return bool(value and value['critical_immune'])


def boundary(engine,actors,name):
    for actor in actors:
        row=live(actor)
        if row is not None and name in row[E.KEY]['lifetime']['ends_on']:
            CONDITIONS.end(engine,actor,row,{'kind':'defense_curl_end','boundary':name})


def stop(engine,actor):
    import state_grants as G,turn as TURN
    __import__('world_entities').require_actors(engine,actor)
    row=live(actor)
    if row is None or 'swift' not in row[E.KEY]['lifetime']['ends_on']:
        raise ValueError('active Core Defense Curl required for its Swift ending')
    def apply(e,a):
        if not TURN.spend(e,a,'swift','end Defense Curl'):return False
        boundary(e,(a,),'swift')
        return True
    return G.transition(engine,actor,apply)


def validate_world(engine,index):
    for actor in index.values():
        if CHOICE in actor.spec:selected(engine.r,actor.spec[CHOICE])
        live(actor)
    return True
