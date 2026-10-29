"""Walk It Off connects actual acquisition and Extended use to shared recovery."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import common_checks as C
import skill_modifiers as SKILL_RANKS

FEATURE='feat/기분전환'
CLAUSE='C03-143'
KEY='walk_it_off_uses'
QUOTA={'kind':'daily','uses':1}
SOURCE_SHA256='b94e43349794836391501f9aac10009d20746bf946ea0c4b5ff3adf85e982d23'
DEFINITION={'clause_id':CLAUSE,'span':[869,873],'catalog_span':[869,873],
    'minimum_level':0,'skill':None,
    'source':{'file':'input/ch03-skills-edges-feats.md','sha256':SOURCE_SHA256}}


def source(rules,edition='core'):
    import source_context as S
    if edition not in ('core','local_translation','local_csv'):
        raise ValueError('reviewed Walk It Off source required')
    if rules._selected_rule(FEATURE)!=FEATURE:
        raise ValueError('selected Walk It Off source needs its own adapter')
    data=json.loads((Path(rules.root)/'data/walk-it-off-source-contract.json').read_text(encoding='utf8'))
    row={'edition':edition,**DEFINITION['source'],'span':[869,873]}
    S.verified_source(rules,DEFINITION['source'],label='Walk It Off')
    if edition=='core':
        original=data['core']
        if sha256((Path(rules.root)/original['file']).read_bytes()).hexdigest()!=original['sha256']:
            raise ValueError('reviewed original Walk It Off source changed')
        row['interpretation']=deepcopy(original)
    elif edition=='local_csv':
        selected=data['csv'];S.verified_source(rules,selected,label='Walk It Off CSV')
        row.update(file=selected['file'],sha256=selected['sha256'],record=43,span=None)
    return row


def records(actor,*,active=False):
    import trainer_feature_acquisition as T
    return [record for _, record in T.static_acquisitions(actor, FEATURE, active=active)]


def acquisition_snapshot(engine,actor,selection):
    import skill_modifiers as S
    if selection is not None and (type(selection)is not dict or set(selection)!={'edition'}):
        raise ValueError('one immutable Walk It Off source selection required')
    edition='core' if selection is None else selection['edition']
    return {'athletics':S.rank(engine.r,actor,'육상')[2],'focus':S.rank(engine.r,actor,'집중')[2],
        'selection':deepcopy(selection),'source':source(engine.r,edition)}


def qualification(actor,snapshot,prerequisite_source):
    import acquisition_qualification as Q
    if prerequisite_source is not None or type(snapshot)is not dict or set(snapshot)!={'athletics','focus','selection','source'}:
        raise ValueError('actual Walk It Off acquisition observations required')
    for field in ('athletics','focus'):SKILL_RANKS.validate_rank_value(actor.r,snapshot[field],label='Walk It Off '+field)
    selection=snapshot['selection']
    if selection is not None and (type(selection)is not dict or set(selection)!={'edition'}):
        raise ValueError('one immutable Walk It Off source selection required')
    if snapshot['source']!=source(actor.r,'core' if selection is None else selection['edition']):
        raise ValueError('immutable actual Walk It Off source required')
    return Q.require(FEATURE,'native','acquire',[
        Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),
        Q.check('athletics','prerequisite',snapshot['athletics']>=4,'Adept Athletics required'),
        Q.check('focus','prerequisite',snapshot['focus']>=3,'Novice Focus required')])


def validate_acquisition(actor,record,sid,active):
    import state_grants as G
    if active and actor.spec.get(G.KEY,{}).get('stat_sources',{}).get('hp',{}).get('sources',{}).get(sid,{}).get('acquisition_stat_tag')!={'delta':1,'minimum':None}:
        raise ValueError('actual source-owned Walk It Off HP tag required')


def require(engine,actor):
    import acquired_features as A,trainer_feature_acquisition as T,world_entities as W
    W.require_actors(engine,actor);T.validate_actor(actor);validate(engine)
    rows=records(actor,active=True)
    if actor.kind!='trainer' or A.owned_rule_count(actor,FEATURE)!=1 or len(rows)!=1:
        raise ValueError('one actual acquired Walk It Off Feature required')
    selected=rows[0]['snapshot']['source']
    if selected!=source(engine.r,selected['edition']):raise ValueError('Walk It Off acquisition source changed')
    return rows[0]


def _seal(row):
    import trainer_feature_acquisition as T
    return T._digest('walk-it-off/use/v1',{k:v for k,v in row.items() if k!='integrity'})


def act(engine,actor,*,duration_minutes=None,reason=None):
    """The GM supplies unspecified Extended duration; no fixed default is invented."""
    import activity_jobs as JOBS,frequency as F,injury_recovery as I
    import movement_actions as MOVEMENT,state_grants as G,turn as TURN
    MOVEMENT.boundary(engine,'walk_it_off');acquisition=require(engine,actor)
    if engine.encounter_active:raise ValueError('Walk It Off Extended action cannot run during an encounter')
    if duration_minutes is None or reason is None:
        return C.PendingDecision('GM Walk It Off Extended duration and reason required')
    C.integer(duration_minutes,'Walk It Off duration minutes',1)
    if type(reason)is not str or not reason.strip():raise ValueError('GM Walk It Off duration reason required')
    def apply(e,a):
        if not F.activation_allowed(a,FEATURE,QUOTA,engine=e):raise ValueError('Walk It Off daily use exhausted')
        if not TURN.spend(e,a,'extended',FEATURE):raise ValueError('Walk It Off Extended action unavailable')
        start=e.elapsed_seconds
        job=JOBS.run_fixed(e,a,(),seconds=duration_minutes*60,source=FEATURE,context={'reason':reason})
        injuries_before,hp_before=a.injuries,a.hp
        # PTU p250: fractions use true maximum HP, not the injury recovery ceiling.
        maximum=a.base_max_hp;requested=__import__('arithmetic_policy').ratio(maximum,4)
        # The optional narrative calendar restores an actual Daily activation,
        # not the ordinary Injury pool. Permit one removal per witnessed use.
        day=F.state(a)['day'];session=F.state(a).get('daily_basis')=='session'
        cap=1+sum(r['removed'] for r in a.spec.get(KEY,[]) if r['day']==day) if session else 1
        removed=I.heal_exempt(e,a,1,source=FEATURE,daily_cap=cap)
        gained=e.heal(a,requested,source_kind='feature')
        F.consume_activation(a,FEATURE,QUOTA,engine=e)
        quota=deepcopy(F.state(a)['activations'][FEATURE])
        row={'id':a.entity_id+':walk-it-off:'+str(len(a.spec.get(KEY,[]))+1),
            'source':deepcopy(acquisition['snapshot']['source']),'acquisition':acquisition['request_id'],
            'start':start,'end':e.elapsed_seconds,'duration_minutes':duration_minutes,'reason':reason,
            'job_id':job['job_id'],'day':day,'quota':quota,'exempt_cap':cap,
            'injuries_before':injuries_before,'injuries_after':a.injuries,'removed':removed,
            'hp_before':hp_before,'hp_after':a.hp,'maximum':maximum,'requested':requested,'gained':gained}
        row['integrity']=_seal(row);a.spec.setdefault(KEY,[]).append(row)
        e.log('  '+a.name+': 기분전환, 부상 '+str(removed)+'개 및 HP '+str(gained)+' 회복',FEATURE)
        return deepcopy(row)
    return G.transition(engine,actor,apply)


def validate(engine):
    import frequency as F,injury_recovery as I,world_entities as W
    for actor in W.actor_index(engine).values():
        rows=actor.spec.get(KEY,[])
        if type(rows)is not list:raise ValueError('Walk It Off uses must be a list')
        calendar=actor.spec.get('frequency_state')
        if rows:
            if type(calendar)is not dict:raise ValueError('Walk It Off actual Daily calendar missing')
            F.validate(actor)
        periods=[];exempt=[]
        for number,row in enumerate(rows,1):
            if type(row)is not dict or row.get('integrity')!=_seal(row):raise ValueError('Walk It Off use evidence changed')
            historical=[r for r in records(actor) if r['request_id']==row['acquisition']]
            if actor.kind!='trainer' or len(historical)!=1 or row['source']!=historical[0]['snapshot']['source']:
                raise ValueError('Walk It Off actual acquisition or source missing')
            if row['source']!=source(engine.r,row['source']['edition']) or row['id']!=actor.entity_id+':walk-it-off:'+str(number):
                raise ValueError('Walk It Off source or use identity changed')
            for key in ('start','end','day','injuries_before','injuries_after','maximum','requested','gained'):
                C.integer(row[key],'Walk It Off '+key,0)
            C.integer(row['duration_minutes'],'Walk It Off minutes',1);C.integer(row['removed'],'Walk It Off removed injuries',0,1)
            C.integer(row['hp_before'],'Walk It Off previous HP');C.integer(row['hp_after'],'Walk It Off resulting HP')
            if (row['start']>row['end'] or row['end']>engine.elapsed_seconds or row['end']-row['start']!=row['duration_minutes']*60
                or type(row['reason'])is not str or not row['reason'].strip()
                or row['injuries_before']-row['injuries_after']!=row['removed']
                or row['requested']!=__import__('arithmetic_policy').ratio(row['maximum'],4)
                or row['hp_after']-row['hp_before']!=row['gained'] or row['gained']>row['requested']):
                raise ValueError('Walk It Off actual recovery or elapsed interval changed')
            job=getattr(engine,'_activity_jobs',{}).get('jobs',{}).get(row['job_id'])
            if (job is None or job['owner']is not actor or job['source']!=FEATURE or job['participants'] or job['status']!='complete'
                or job['worked_seconds']!=row['duration_minutes']*60 or job['end_seconds']!=row['end']):
                raise ValueError('Walk It Off actual completed Extended job missing')
            quota=row['quota']
            if type(quota)is not dict or set(quota)!={'kind','period','used'} or quota['kind']!='daily' or quota['used']!=1 or quota['period']in periods:
                raise ValueError('Walk It Off daily use evidence changed')
            period=quota['period'];session=type(period)is list
            if session:
                if (len(period)!=2 or period[0]!='session' or not engine.session_frequency
                    or calendar.get('daily_basis')!='session'):
                    raise ValueError('Walk It Off actual session calendar required')
                C.integer(period[1],'Walk It Off session period',0,calendar['session'])
            elif type(period)is not int or period!=row['day']:
                raise ValueError('Walk It Off actual day period required')
            cap=1+sum(r['removed'] for r in rows[:number-1] if r['day']==row['day']) if session else 1
            if type(row['exempt_cap'])is not int or row['exempt_cap']!=cap:
                raise ValueError('Walk It Off source-owned exempt cap changed')
            periods.append(deepcopy(quota['period']))
            if row['removed']:
                exempt.append({'source':FEATURE,'count':row['removed'],'day':row['day'],'at':row['end'],'daily_cap':cap})
        if [r for r in actor.spec.get(I.EXEMPT,[]) if r.get('source')==FEATURE]!=exempt:
            raise ValueError('Walk It Off exact exempt recovery evidence changed')
        if rows:
            current=calendar['activations'].get(FEATURE)
            previous=rows[-1]['quota']
            adopted=calendar.get('daily_basis')=='session' and type(previous['period'])is int
            if current!=previous and not (adopted and current=={'kind':'daily','period':['session',0],'used':1}):
                raise ValueError('Walk It Off shared Daily quota changed')
    return True
