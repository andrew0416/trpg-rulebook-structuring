"""Table-driven, source-bound observation rights for acquired Blessing Gifts.

The table grants information rights only.  A caller must own the exact Gift,
retain its GM approval receipt, and use an actual registered observer/target.
World facts are signed separately so an observation never invents campaign
truth from a name, a handler, or a caller-provided result.
"""
from copy import deepcopy
from math import hypot,isfinite
from pathlib import Path
import json

import action_points as AP
import blessing_skill_features as BLESSINGS
import crafting_recipes as Q
import frequency as FREQUENCY
import resolution_transaction as TX
import state_grants as GRANTS
import turn as TURN
import world_entities as WORLD

FACTS = '_blessing_observation_facts'
ACTIVE = '_blessing_observation_active'
CHOICES = 'gift_choices'

_POLICY = json.loads((Path(__file__).resolve().parents[1] / 'data/blessing-observation-policy.json').read_text(encoding='utf-8'))
if _POLICY.get('schema_version') != 1 or _POLICY.get('source') != 'input/db/class-data.csv':
    raise ValueError('unsupported source-bound Blessing observation policy')
RULES = {row['gift']: row for row in _POLICY.get('rules', [])}
if len(RULES) != 11 or len(RULES) != len(_POLICY.get('rules', [])):
    raise ValueError('exactly eleven distinct Blessing observation clauses required')

_ACTIONS = {None, 'standard', 'swift', 'extended'}
_PROVIDERS = {'target_fact', 'typed_presence', 'world_fact', 'clock', 'spatial', 'gift_presence'}
for _gift, _row in RULES.items():
    required = {'clause_id','record','name','gift','provider','action','ap','frequency','target','fields','cell_sha256','source_text'}
    if set(_row) - (required | {'range_m','maximum_age_seconds','duration_seconds'}):
        raise ValueError('unknown Blessing observation policy field')
    if not required <= set(_row) or _row['gift'] != _gift:
        raise ValueError('complete exact Blessing observation policy required')
    if not _row['clause_id'].startswith('C2CSV/input/db/class-data.csv:R') or _row['provider'] not in _PROVIDERS:
        raise ValueError('source-bound supported Blessing observation provider required')
    if type(_row['record']) is not int or _row['record'] < 1 or _row['action'] not in _ACTIONS:
        raise ValueError('valid Blessing record and action policy required')
    if type(_row['ap']) is not int or _row['ap'] < 0:
        raise ValueError('nonnegative Blessing AP policy required')
    if type(_row['fields']) is not list or not _row['fields'] or len(set(_row['fields'])) != len(_row['fields']):
        raise ValueError('distinct finite Blessing information fields required')
    for _field in ('gift','name','cell_sha256','source_text'):
        Q._text(_row[_field])
    BLESSINGS.SOURCES[_gift] = _gift


def catalog():
    """Return the finite source-bound table; this is not an acquisition grant."""
    return deepcopy(_POLICY['rules'])


def _rule(engine, gift):
    if gift not in RULES:
        raise ValueError('supported exact Blessing observation Gift required')
    if engine.r._selected_rule(gift) != gift:
        raise ValueError('selected Blessing observation source requires its own policy')
    return RULES[gift]


def _owner(engine, observer, gift):
    WORLD.require_actors(engine, observer)
    if observer.kind != 'trainer':
        raise ValueError('Blessing observation owner must be an actual trainer')
    if not BLESSINGS.require(engine, observer, gift):
        raise ValueError('actual acquired Blessing Gift required')
    return observer.entity_id


def confirm(engine, observer, gift, *, reason):
    """Confirm one already acquired Gift using the shared acquisition receipt."""
    _rule(engine, gift)
    WORLD.require_actors(engine, observer)
    return BLESSINGS.confirm(engine, observer, gift, reason=reason)


def _choice(observer, gift, field, allowed):
    mapping = observer.spec.get(CHOICES, {})
    if type(mapping) is not dict:
        raise ValueError('Gift choices must be a mapping')
    row = mapping.get(gift)
    if type(row) is not dict or set(row) != {field} or row[field] not in allowed:
        raise ValueError('exact acquired Gift choice required: ' + field)
    return row[field]


def _target_id(target):
    return target.get('id') if isinstance(target,dict) else target.entity_id


def _fact_key(gift, target):
    return gift if target is None else gift + ':' + _target_id(target)


def _gift_snapshot(target):
    gifts=target.spec.get('gifts',[]);patrons=target.spec.get('gift_patrons',{})
    if not isinstance(gifts,(list,tuple)) or not isinstance(patrons,dict):
        raise ValueError('actual acquired Gift and patron state required')
    if len(gifts)!=len(set(gifts)):raise ValueError('distinct actual Gifts required')
    for gift in gifts:
        Q._text(gift);Q._text(patrons.get(gift))
    return {'gifts':sorted(gifts),'patrons':{gift:patrons[gift] for gift in sorted(gifts)}}


def _geometry_binding(target):
    import perception_observe as OBSERVE
    import body_state as BODY
    effective=None if isinstance(target,dict) else BODY.projection(target)
    return json.dumps({'geometry':OBSERVE._geometry_context(target),
        'height_m':None if effective is None else effective['height_m']},
        sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'))


def _fact_context(rule,target):
    if rule['provider']=='gift_presence':return _gift_snapshot(target)
    if rule['provider']=='spatial':return {'geometry':_geometry_binding(target)}
    return None


def _typed(field, value):
    booleans = {'desire_altruistic','harms_patron_followers','presence','legendary_presence'}
    texts = {'allegiance','goals','motives','disaster_kind','tone','hint','size'}
    integers = {'when_seconds','died_at'}
    text_lists = {'weaknesses','approximate_locations'}
    if field in booleans and type(value) is bool:
        return value
    if field in texts and isinstance(value, str) and (value.strip() or field in {'allegiance','goals','motives'} and value==''):
        return value
    if field in integers and type(value) is int and value >= 0:
        return value
    if field in text_lists and type(value) is list and len(set(value)) == len(value) and all(isinstance(x,str) and x.strip() for x in value):
        return list(value)
    if field == 'communication_links' and type(value) is list:
        links=[]
        for link in value:
            if type(link) is not dict or set(link) != {'from_id','to_id'}:
                raise ValueError('communication links require exact endpoints')
            Q._text(link['from_id']); Q._text(link['to_id'])
            links.append({'from_id':link['from_id'],'to_id':link['to_id']})
        if len({(x['from_id'],x['to_id']) for x in links}) != len(links):
            raise ValueError('communication links must be distinct')
        return links
    raise ValueError('invalid observed Blessing fact field: ' + field)


def _fact_value(rule, value):
    if rule['provider']=='gift_presence':
        if (type(value) is not dict or not {'range_cm','basis'}<=set(value)
                or set(value)-{'range_cm','basis','exception_reason'}
                or type(value['range_cm']) is not int or value['range_cm']<0):
            raise ValueError('GM adjudicated gift-count sensing radius required')
        Q._text(value['basis'])
        if 'exception_reason' in value:Q._text(value['exception_reason'])
        if value['range_cm']>rule['range_m']*100 and 'exception_reason' not in value:
            raise ValueError('beyond the usual 1500 cm requires an explicit GM exception reason')
        return dict(value)
    if rule['provider']=='spatial':
        if type(value) is not dict or set(value)!={'dimensions_cm'}:
            raise ValueError('GM measured actual object dimensions required')
        dimensions=value['dimensions_cm']
        if (type(dimensions) is not dict or not dimensions or not set(dimensions)<={'length','width','height'}
                or any(type(v) is not int or not 1<=v<=rule['range_m']*100 for v in dimensions.values())):
            raise ValueError('actual dimensions must be positive whole centimetres within ten metres')
        return {'dimensions_cm':dict(dimensions)}
    if type(value) is not dict or set(value) != set(rule['fields']):
        raise ValueError('observed fact must contain exactly the policy information fields')
    prepared={field:_typed(field,value[field]) for field in rule['fields']}
    if 'legendary_presence' in prepared and bool(prepared['approximate_locations'])!=prepared['legendary_presence']:
        raise ValueError('legendary absence must have no approximate locations')
    return prepared


def record_fact(engine, observer, gift, value, *, reason, target=None):
    """Record GM-established campaign truth before the Gift may reveal it."""
    rule=_rule(engine,gift); _owner(engine,observer,gift); Q._text(reason)
    contextual=rule['provider'] in ('gift_presence','spatial')
    if rule['provider'] not in ('target_fact','world_fact','gift_presence','spatial'):
        raise ValueError('this Blessing derives from native state, not a GM fact')
    if contextual:
        if target is None or WORLD.entity_index(engine).get(_target_id(target)) is not target:
            raise ValueError('actual registered observation fact target required')
        if rule['provider']=='gift_presence':WORLD.require_actors(engine,target)
    elif rule['target'] in ('actor','corpse'):
        if target is None:raise ValueError('actual observed target required')
        WORLD.require_actors(engine,target)
    elif target is not None:
        raise ValueError('world fact must not be rebound to a target')
    prepared=_fact_value(rule,value); key=_fact_key(gift,target)
    def apply(staged, owner, staged_target=None):
        _owner(staged,owner,gift)
        if isinstance(target,dict):staged_target=WORLD.entity_index(staged).get(_target_id(target))
        old=owner.spec.get(FACTS,{})
        if type(old) is not dict:raise ValueError('Blessing observation fact ledger must be a mapping')
        previous=old.get(key); revision=1 if previous is None else previous['revision']+1
        row={'source':'gm/blessing-observation','clause_id':rule['clause_id'],'owner_id':owner.entity_id,
             'gift':gift,'target_id':None if staged_target is None else _target_id(staged_target),
             'value':deepcopy(prepared),'reason':reason,'at':staged.elapsed_seconds,'revision':revision}
        if contextual:row['context']=_fact_context(rule,staged_target)
        if rule['provider']=='gift_presence' and previous is not None:
            if previous.get('sha256')!=TX.request_fingerprint({k:v for k,v in previous.items() if k!='sha256'}):
                raise ValueError('prior GM sensing judgment signature changed')
            # Only one observer/target's same explicit GM criterion is compared.
            # A new environment or adjudication basis does not inherit a radius.
            if previous['value']['basis']==prepared['basis']:
                count=lambda snapshot:sum('미싱노' not in snapshot['patrons'][g] for g in snapshot['gifts'])
                delta=count(row['context'])-count(previous['context'])
                change=prepared['range_cm']-previous['value']['range_cm']
                if delta*change<0:raise ValueError('same-basis gift-count sensing radius must remain monotonic')
        row['sha256']=TX.request_fingerprint(row)
        owner.spec.setdefault(FACTS,{})[key]=row
        staged.gm._rec('축복 관측 사실',previous,row,reason,owner)
        return deepcopy(row)
    participants=() if target is None or isinstance(target,dict) else (target,)
    return GRANTS.transition(engine,observer,apply,participants=participants,include_rulings=True)


def _read_fact(engine, observer, gift, rule, target):
    key=_fact_key(gift,target); row=observer.spec.get(FACTS,{}).get(key)
    contextual=rule['provider'] in ('gift_presence','spatial')
    fields={'source','clause_id','owner_id','gift','target_id','value','reason','at','revision','sha256'}
    if contextual:fields.add('context')
    if type(row) is not dict or set(row) != fields:
        if rule['provider']=='gift_presence':raise ValueError('GM gift-count sensing radius required for this actual target')
        raise ValueError('signed GM Blessing observation fact required')
    if row['source']!='gm/blessing-observation' or row['clause_id']!=rule['clause_id'] or row['owner_id']!=observer.entity_id or row['gift']!=gift:
        raise ValueError('Blessing observation fact provenance changed')
    expected=None if target is None else _target_id(target)
    if row['target_id']!=expected or row['sha256']!=TX.request_fingerprint({k:v for k,v in row.items() if k!='sha256'}):
        raise ValueError('Blessing observation fact identity or signature changed')
    Q._text(row['reason']); _fact_value(rule,row['value'])
    if contextual and row['context']!=_fact_context(rule,target):
        raise ValueError('observed Gift/patron count or object geometry changed; fresh GM fact required')
    if type(row['at']) is not int or row['at']<0 or row['at']>engine.elapsed_seconds or type(row['revision']) is not int or row['revision']<1:
        raise ValueError('Blessing observation fact time or revision invalid')
    return deepcopy(row['value'])


def _distance(engine, left, right, *, euclidean=False):
    a=WORLD.effective_location(engine,left); b=WORLD.effective_location(engine,right)
    if a.get('kind')!='grid' or b.get('kind')!='grid' or a.get('map_id')!=b.get('map_id'):
        return None
    dx=a['cell'][0]-b['cell'][0];dy=a['cell'][1]-b['cell'][1]
    return hypot(dx,dy) if euclidean else max(abs(dx),abs(dy))


def _derived(engine, observer, gift, rule, target, selection):
    provider=rule['provider']
    if provider=='clock':
        if selection is None:return {'world_seconds':engine.elapsed_seconds,'stopwatch_seconds':0}
        if type(selection) is not dict or set(selection)!={'started_at'} or type(selection['started_at']) is not int or not 0<=selection['started_at']<=engine.elapsed_seconds:
            raise ValueError('stopwatch requires one actual world-clock start')
        return {'world_seconds':engine.elapsed_seconds,'stopwatch_seconds':engine.elapsed_seconds-selection['started_at']}
    if provider=='spatial':
        if target is None:raise ValueError('actual spatial target required')
        index=WORLD.entity_index(engine)
        uid=target.get('id') if isinstance(target,dict) else target.entity_id
        if index.get(uid) is not target:raise ValueError('actual registered spatial target required')
        left=observer
        if selection is not None:
            if type(selection) is not dict or set(selection)!={'from_id'} or selection['from_id'] not in index:
                raise ValueError('one actual spatial starting entity required')
            left=index[selection['from_id']]
        for endpoint in (left,target):
            reach=_distance(engine,observer,endpoint,euclidean=True)
            if reach is None or reach>rule['range_m']:raise ValueError('spatial target outside the known ten-metre area')
        distance=_distance(engine,left,target,euclidean=True)
        if distance is None or distance>rule['range_m']:raise ValueError('spatial length exceeds ten metres')
        size=target.get('size') if isinstance(target,dict) else target.spec.get('size')
        Q._text(size)
        import body_state as BODY
        data=target if isinstance(target,dict) else target.spec
        dimensions=deepcopy(data.get('dimensions_cm',{}))
        height=data.get('height_m') if isinstance(target,dict) else BODY.projection(target)['height_m']
        if height is not None:
            if type(height) not in (int,float) or not isfinite(height) or not 0<height<=rule['range_m']:
                raise ValueError('native object height outside the ten-metre measurement range')
            dimensions['height']=int(height*100+0.5)
        if _fact_key(gift,target) in observer.spec.get(FACTS,{}):
            measured=_read_fact(engine,observer,gift,rule,target)['dimensions_cm']
            if any(k in dimensions and dimensions[k]!=v for k,v in measured.items()):
                raise ValueError('GM dimensions disagree with actual native object geometry')
            dimensions.update(measured)
        if not dimensions:raise ValueError('GM measured object dimensions required; size category is not a length')
        _fact_value(rule,{'dimensions_cm':dimensions})
        return {'distance_cm':int(distance*100+0.5),'size':size,'dimensions_cm':dimensions}
    if provider=='typed_presence':
        patron=_choice(observer,gift,'patron',{'프리져','파이어','썬더','앤테이','라이코','스이쿤'})
        granted={'프리져':'얼음','파이어':'불꽃','썬더':'전기','앤테이':'불꽃','라이코':'전기','스이쿤':'물'}[patron]
        found=any(actor.kind=='pokemon' and granted in actor.types and (_distance(engine,observer,actor) is not None and _distance(engine,observer,actor)<=rule['range_m']) for actor in WORLD.actor_index(engine).values())
        return {'presence':found}
    if provider=='gift_presence':
        found=False
        for actor in WORLD.actor_index(engine).values():
            if actor is observer:continue
            distance=_distance(engine,observer,actor)
            if distance is None:continue
            snapshot=_gift_snapshot(actor)
            if not any('미싱노' not in snapshot['patrons'][x] for x in snapshot['gifts']):continue
            if distance>rule['range_m'] and _fact_key(gift,actor) not in observer.spec.get(FACTS,{}):continue
            radius=_read_fact(engine,observer,gift,rule,actor)['range_cm']
            if distance*100<=radius:found=True
        return {'presence':found}
    return _read_fact(engine,observer,gift,rule,target)


def _project(engine, observer, gift, rule, value, target, selection):
    if gift=='gift/위대한-존재의-통찰력':
        role=_choice(observer,gift,'role',{'메시아','계약자'})
        if role=='메시아':return deepcopy(value)
        weakness=None
        if value['weaknesses']:
            if type(selection) is not dict or set(selection)!={'weakness'} or selection['weakness'] not in value['weaknesses']:
                raise ValueError('contractor must select one actual weakness')
            weakness=selection['weakness']
        elif selection is not None:raise ValueError('target has no weakness to select')
        return {'weakness':weakness,'aligned':bool(value['allegiance']),
                'harms_patron_followers':value['harms_patron_followers']}
    if gift=='gift/메이저-기프트-진실의-눈':return {'desire_altruistic':value['desire_altruistic']}
    if gift=='gift/마이너-기프트-데스-센스':
        if target is None or target.spec.get('dead') is not True:raise ValueError('Death Sense requires an actual corpse')
        died=value['died_at'];age=engine.elapsed_seconds-died
        if age<0 or age>rule['maximum_age_seconds']:raise ValueError('corpse death lies outside the one-week information window')
        return {'hours_since_death':age//3600}
    if gift=='gift/메이저-기프트-꿈의-전조':
        patron=_choice(observer,gift,'patron',{'크레세리아','다크라이'})
        expected='유리함' if patron=='크레세리아' else '위험/슬픔'
        if value['tone']!=expected:raise ValueError('omen tone disagrees with the acquired patron')
        return {'tone':value['tone'],'hint':value['hint']}
    if gift=='gift/마이너-기프트-세계뱀의-포옹':
        return {'legendary_presence':value['legendary_presence'],'approximate_locations':deepcopy(value['approximate_locations'])}
    if gift=='gift/메이저-기프트-접속-시각화':return {'communication_links':deepcopy(value['communication_links'])}
    return deepcopy(value)


def _frequency(observer, gift, rule):
    if rule['frequency']!='variant':return rule['frequency']
    return '장면' if _choice(observer,gift,'role',{'메시아','계약자'})=='메시아' else None


def observe(engine, observer, gift, *, target=None, selection=None):
    """Consume the declared costs atomically and reveal only table-authorized data."""
    rule=_rule(engine,gift);owner_id=_owner(engine,observer,gift)
    if rule['target'] in ('actor','corpse'):
        if target is None:raise ValueError('actual Blessing target required')
        WORLD.require_actors(engine,target)
    elif rule['target']=='entity':
        if target is None:raise ValueError('actual entity target required')
    elif target is not None:
        raise ValueError('this Blessing does not accept a bound target')
    value=_derived(engine,observer,gift,rule,target,selection)
    projected=_project(engine,observer,gift,rule,value,target,selection)
    frequency=_frequency(observer,gift,rule); key='blessing-observation:'+gift
    active=observer.spec.get(ACTIVE,{}).get(gift)
    reuse=(gift=='gift/메이저-기프트-접속-시각화' and isinstance(active,dict) and active.get('owner_id')==owner_id and
           type(active.get('expires_at')) is int and engine.elapsed_seconds<active['expires_at'])
    if reuse:
        return {'status':'active','source':gift,'clause_id':rule['clause_id'],'owner_id':owner_id,
                'provider':rule['provider'],'values':projected,'lifetime':deepcopy(active)}
    participants=() if target is None or isinstance(target,dict) else (target,)
    def apply(staged, owner, staged_target=None):
        actual_target=WORLD.entity_index(staged).get(target.get('id')) if isinstance(target,dict) else staged_target
        if isinstance(target,dict) and actual_target is None:raise ValueError('staged spatial target is missing')
        _owner(staged,owner,gift)
        staged_value=_derived(staged,owner,gift,rule,actual_target,selection)
        staged_projected=_project(staged,owner,gift,rule,staged_value,actual_target,selection)
        if staged_projected!=projected:raise ValueError('Blessing information changed during staged execution')
        if frequency and not FREQUENCY.activation_allowed(owner,key,frequency,engine=staged):
            raise ValueError('Blessing observation frequency exhausted')
        if rule['ap']:
            if AP.available(owner)<rule['ap']:raise ValueError('Blessing observation AP unavailable')
            AP.charge(owner,rule['ap'],mode='spend')
        if rule['action'] and not TURN.spend(staged,owner,rule['action'],gift):
            raise ValueError('Blessing observation action unavailable')
        if gift=='gift/메이저-기프트-꿈의-전조' and not staged.apply_status(owner,'잠듦',source=gift,applied_by=owner):
            raise ValueError('Dream Omen requires entering deep sleep')
        if frequency:FREQUENCY.consume_activation(owner,key,frequency,engine=staged)
        lifetime={'kind':'while_owned'}
        if rule.get('duration_seconds'):
            lifetime={'kind':'world_clock','started_at':staged.elapsed_seconds,'expires_at':staged.elapsed_seconds+rule['duration_seconds']}
            owner.spec.setdefault(ACTIVE,{})[gift]={'owner_id':owner.entity_id,'source':gift,**lifetime}
        out={'status':'activated' if rule['action'] else 'observed','source':gift,'clause_id':rule['clause_id'],
             'owner_id':owner.entity_id,'provider':rule['provider'],'values':deepcopy(staged_projected),'lifetime':lifetime}
        staged.gm._rec('축복 관측 실행',None,out,rule['clause_id'],owner)
        return out
    return GRANTS.transition(engine,observer,apply,participants=participants,include_rulings=True)
