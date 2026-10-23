"""Ordinary common-check refinement through the existing root Runtime.

This adapter records check arithmetic and separately authorized GM adjudication.
It does not apply fictional consequences, costs, elapsed time, or scene changes.
An operator-installed certificate must establish source/config/actor provenance;
configuration booleans and this module alone do not certify source fidelity.
"""
from collections.abc import Mapping
from dataclasses import asdict
from . import common_checks as cc
from . import root_machine as m
from . import root_resolution as r
from . import root_admission as a
from . import root_inputs as i

ADAPTER_ID = 'common-checks-v1'
EVENT_KIND = 'common_check'
ASPECTS = ('check_result', 'world_response')
BASE = ('domains', 'common_checks')
MODES = ('no_roll', 'dc', 'opposed', 'team', 'extended')


def _text(value, label):
    if type(value) is not str or not value: raise ValueError('nonempty '+label+' required')
    return value


def _bool(value, label):
    if type(value) is not bool: raise ValueError('exact boolean '+label+' required')
    return value


def initial_snapshot(profile, actors, config):
    """Build the exact adapter G layout from an operator-supplied actor projection.

    ordinary_default means a complete ordinary initial skill sheet, not unknown
    data. Missing skills receive rank 2 only within the fixed skill_catalog.
    The live Engine bridge must verify projection freshness throughout a session.
    """
    config=m.thaw(m.freeze(config)); actors=m.thaw(m.freeze(actors))
    if config.get('mode') not in ('synthetic','source'):raise ValueError('explicit evidence mode')
    a._sha(config.get('catalog_hash'))
    for key in ('source_refs','gm_ids','skill_catalog'):
        values=config.get(key)
        if not isinstance(values,list) or not values or len(set(values))!=len(values):raise ValueError('distinct nonempty '+key)
        for value in values:_text(value,key)
    _bool(config.get('combat_active'),'combat_active')
    if not isinstance(config.get('roller_ids'),dict) or not isinstance(config.get('requests'),dict):raise ValueError('request and supplier maps required')
    for actor_id,actor in actors.items():
        _text(actor_id,'actor identity')
        if not isinstance(actor.get('skills'),dict):raise ValueError('skill map required')
        for skill,rank in actor['skills'].items():
            _text(skill,'skill')
            if rank is not None:cc.integer(rank,'ordinary rank',1,6)
        for key in ('ordinary_default','dead','fainted'):_bool(actor.get(key),key)
        cc.integer(actor.get('hp'),'HP');cc.integer(actor.get('injuries'),'injuries',0)
        for key in ('conditions','modifier_sources'):
            if not isinstance(actor.get(key),list):raise ValueError('explicit '+key+' inventory required')
        suppliers=config['roller_ids'].get(actor_id)
        if not isinstance(suppliers,list) or not suppliers:raise ValueError('actor suppliers required')
        for supplier in suppliers:_text(supplier,'supplier')
    tasks={}
    for key,req in config['requests'].items():
        _text(key,'request key');_validate_request(req,actors,config)
        for decision in req['decisions']:
            if decision['mode']=='extended':tasks[decision['task_id']]=None
    game={name:{} for name in m.DOMAINS}
    game['actors']=actors
    game['domains']['common_checks']={'config':config,'results':{},'tasks':tasks}
    return m.Snapshot(profile,0,game)


def _validate_request(req,actors,config):
    intent=req.get('intent')
    if type(intent) is not str or not intent.strip():raise ValueError('declared action intent required')
    ids=req.get('actors')
    if not isinstance(ids,(tuple,list)) or not ids or len(set(ids))!=len(ids) or any(x not in actors for x in ids):raise ValueError('distinct known participating actors required')
    if not isinstance(req.get('context_obligations'),(tuple,list)):raise ValueError('explicit context obligations required')
    if req.get('modifier_policy')!='none':raise ValueError('automatic/source modifier composition is not supported')
    decisions=req.get('decisions');outcomes=req.get('outcomes')
    if not isinstance(decisions,(tuple,list)) or not decisions:raise ValueError('finite GM decision domain required')
    if not isinstance(outcomes,(tuple,list)) or not outcomes:raise ValueError('finite GM response domain required')
    for d in decisions:
        mode=d.get('mode')
        if mode not in MODES:raise ValueError('unsupported check family')
        fields={'mode','reason'} if mode=='no_roll' else {'mode','skill','penalty_count','modifier'}
        if mode=='opposed':fields.add('skills')
        if mode in ('dc','team','extended'):fields.add('dc')
        if mode in ('dc','extended'):fields.add('helper_id')
        if mode=='team':fields.update(('required_people','equal_contribution','no_main_actor'))
        if mode=='extended':fields.update(('complexity','limited','task_id','interval_id','interval'))
        if set(d)-fields:raise ValueError('uninterpreted decision fields: '+repr(sorted(set(d)-fields)))
        if mode=='no_roll':
            if d.get('reason') not in ('trivial','uninteresting_failure'):raise ValueError('no-roll contextual reason required')
            continue
        if mode=='opposed' and 'skills' in d:
            if 'skill' in d:raise ValueError('choose per-actor skills or shared shorthand, not both')
            if not isinstance(d['skills'],Mapping) or set(d['skills'])!=set(ids):raise ValueError('each opposed participant needs exactly one skill')
            if any(x not in config['skill_catalog'] for x in d['skills'].values()):raise ValueError('skill outside fixed catalog')
        elif d.get('skill') not in config['skill_catalog']:raise ValueError('skill outside fixed catalog')
        cc.integer(d.get('penalty_count',0),'penalty count',0)
        if d.get('modifier',0)!=0 or type(d.get('modifier',0)) is not int:raise ValueError('unsourced additive modifier not supported')
        if mode in ('dc','team','extended'):cc.integer(d.get('dc'),'DC',1 if mode=='extended' else None)
        if mode in ('dc','extended') and len(ids)!=1:raise ValueError('one main actor required')
        if mode=='opposed' and len(ids)!=2:raise ValueError('challenger and status-quo defender required')
        if mode=='team':
            cc.integer(d.get('required_people'),'required people',1)
            if d.get('equal_contribution') is not True or d.get('no_main_actor') is not True:raise ValueError('ordinary equal contribution/no-main-actor scope required')
        helper=d.get('helper_id')
        if helper is not None and (mode not in ('dc','extended') or helper not in actors or helper in ids):raise ValueError('single distinct helper scope required')
        if mode=='extended':
            cc.integer(d.get('complexity'),'complexity',2,5);_bool(d.get('limited'),'limited')
            for key in ('task_id','interval_id'):_text(d.get(key),key)
            interval=d.get('interval')
            if not isinstance(interval,Mapping):raise ValueError('GM interval required')
            cc.integer(interval.get('amount'),'interval amount',1);_text(interval.get('unit'),'interval unit')
    if len({m.identity(d) for d in decisions})!=len(decisions):raise ValueError('duplicate GM decisions')
    for result in outcomes:
        if set(result)-{'outcome','description','cost','failure_margin_accepted'}:raise ValueError('unsupported narrative authority fields')
        cc.validate_adjudication(**result)
    if len({m.identity(d) for d in outcomes})!=len(outcomes):raise ValueError('duplicate GM responses')


def _data(snapshot,event):
    if set(event.payload)!={'request_key'}:raise ValueError('event carries only registered request key')
    config=snapshot.game['domains']['common_checks']['config']
    return config,config['requests'][event.payload['request_key']]


def _rank(actor,skill):
    if skill in actor['skills']:
        value=actor['skills'][skill]
        if value is None:return m.Block('missing_refinement','explicit unknown skill rank')
        return cc.integer(value,'ordinary rank',1,6)
    if actor['ordinary_default'] is True:return 2
    return m.Block('missing_refinement','missing rank without complete ordinary initial sheet')


def _actor_problem(actor):
    if actor['dead'] or actor['fainted'] or actor['hp']<=0:return m.Block('precondition_false','actor cannot perform ordinary active check')
    if actor['conditions'] or actor['injuries'] or actor['modifier_sources']:return m.Block('missing_refinement','status/injury/source modifier composition outside ordinary profile')
    return None


def support(snapshot,event):
    try:
        config,req=_data(snapshot,event)
        _validate_request(req,snapshot.game['actors'],config)
        if req['context_obligations']:return r.Predicate(r.Truth.UNKNOWN,'; '.join(req['context_obligations']), (BASE+('config',),))
        for actor_id in req['actors']:
            issue=_actor_problem(snapshot.game['actors'][actor_id])
            if issue:return r.Predicate(r.Truth.UNKNOWN,issue.detail,(('actors',actor_id),))
        return r.TRUE
    except (KeyError,TypeError,ValueError) as exc:return r.Predicate(r.Truth.UNKNOWN,'unsupported common-check request: '+str(exc))


def _footprints(snapshot,event):
    config,req=_data(snapshot,event)
    ids=set(req['actors'])|{d['helper_id'] for d in req['decisions'] if d.get('helper_id')}
    tasks=sorted({d['task_id'] for d in req['decisions'] if d['mode']=='extended'})
    reads=(BASE+('config',),)+tuple(('actors',x) for x in sorted(ids))+tuple(BASE+('tasks',x) for x in tasks)
    raw_path=BASE+('results',event.id)
    writes=(raw_path,)+tuple(BASE+('tasks',x) for x in tasks)
    return r.Footprint(reads,writes),r.Footprint((BASE+('config',),raw_path),(raw_path,))


def derive(snapshot,event):
    config,req=_data(snapshot,event); fps=_footprints(snapshot,event);refs=tuple(config['source_refs'])
    clauses=tuple(r.Clause('common:'+aspect,aspect,{'request_key':event.payload['request_key']},footprint=fp,source_refs=refs) for aspect,fp in zip(ASPECTS,fps))
    return r.ResolutionRequest(event.id,event.kind,snapshot.profile,config['catalog_hash'],a.context_fingerprint(snapshot,event),clauses,
        laws=tuple(r.CompositionLaw(x,'exclusive',refs[0]) for x in ASPECTS),candidate_closure=r.TRUE,aspects=ASPECTS,
        aspect_orders=(r.AspectOrder('check_result','world_response',r.TRUE,refs[0]),))


def _key(event,suffix):return 'common:'+event.id+':'+suffix


def _need(event,suffix,kind,reason):return m.NeedInput(_key(event,suffix),kind,reason)


def _config_req(view,event):
    config=view.get(BASE+('config',));return config,config['requests'][event.payload['request_key']]


def _selected(view,event,evidence):
    config,req=_config_req(view,event)
    key=_key(event,'decision')
    if key not in evidence:return _need(event,'decision','source_choice','GM selects check mode, skill and task parameters')
    decision=evidence[key]
    if m.identity(decision) not in {m.identity(x) for x in req['decisions']}:return m.Block('invalid_state','decision outside installed finite domain')
    return decision


def _roll_specs(view,event,decision):
    config,req=_config_req(view,event)
    if decision['mode']=='no_roll':return ()
    if decision['mode']=='extended' and config['combat_active']:return m.Block('precondition_false','extended action not executable during combat')
    skill=decision.get('skill');helper_rank=0
    if decision.get('helper_id'):
        helper=view.get(('actors',decision['helper_id']));issue=_actor_problem(helper)
        if issue:return issue
        helper_rank=_rank(helper,skill)
        if isinstance(helper_rank,m.Block):return helper_rank
        if helper_rank<3:return m.Block('precondition_false','single helper requires ordinary rank >= 3')
    specs=[]
    for index,actor_id in enumerate(req['actors']):
        actor=view.get(('actors',actor_id));issue=_actor_problem(actor)
        if issue:return issue
        actor_skill=decision['skills'][actor_id] if decision['mode']=='opposed' and 'skills' in decision else skill
        rank=_rank(actor,actor_skill)
        if isinstance(rank,m.Block):return rank
        specs.append({'actor':actor_id,'skill':actor_skill,'rank':rank,'modifier':0,'helper_rank':helper_rank,'penalty_count':decision.get('penalty_count',0),'index':index})
    return tuple(specs)


def _signature(decision,spec):
    return a.digest(({k:v for k,v in decision.items() if k!='interval_id'},spec))


def _history(view,event,d,spec):
    task=view.get(BASE+('tasks',d['task_id']))
    if task is None:return (),(),None
    if task['signature']!=_signature(d,spec):return m.Block('missing_refinement','extended task parameters/rank changed')
    if task['status']!='in_progress':return m.Block('precondition_false','extended task already terminal')
    if d['interval_id'] in task['interval_ids']:return m.Block('precondition_false','interval already recorded under another occurrence')
    return tuple(task['rolls']),tuple(task['interval_ids']),task


def _raw_guard(view,event,evidence):
    d=_selected(view,event,evidence)
    if isinstance(d,(m.NeedInput,m.Block)):return m.Guard(m.Truth.UNKNOWN,d)
    specs=_roll_specs(view,event,d)
    if isinstance(specs,m.Block):return m.Guard(m.Truth.UNKNOWN,specs)
    if d['mode']=='extended':
        history=_history(view,event,d,specs[0])
        if isinstance(history,m.Block):return m.Guard(m.Truth.UNKNOWN,history)
        previous=cc.extended(tuple(cc.SkillRoll(**m.thaw(x)) for x in history[0]),d['dc'],d['complexity'],specs[0]['rank'],d['limited'])
        # Rank 1, limited: zero attempts; record exhausted without asking for dice.
        if previous.status=='exhausted' and not history[0]:return m.Guard(m.Truth.TRUE)
    for spec in specs:
        for kind,count in (('dice',spec['rank']),('penalty',spec['penalty_count'])):
            if count and _key(event,kind+':'+str(spec['index'])) not in evidence:
                return m.Guard(m.Truth.UNKNOWN,_need(event,kind+':'+str(spec['index']),'randomness','ordered '+kind+' d6 for '+spec['actor']))
    return m.Guard(m.Truth.TRUE)


def _roll(view,event,d,spec,evidence):
    return cc.SkillRoll(spec['rank'],evidence[_key(event,'dice:'+str(spec['index']))],0,spec['helper_rank'],evidence.get(_key(event,'penalty:'+str(spec['index'])),()))


def _raw_update(view,event,evidence):
    d=_selected(view,event,evidence);config,req=_config_req(view,event);specs=_roll_specs(view,event,d)
    rolls=();writes=[];owed=[]
    if d['mode']=='no_roll':raw={'kind':'no_roll','reason':d['reason']}
    elif d['mode']=='extended':
        old,intervals,_=_history(view,event,d,specs[0]); previous=[cc.SkillRoll(**m.thaw(x)) for x in old]
        before=cc.extended(previous,d['dc'],d['complexity'],specs[0]['rank'],d['limited'])
        if before.status=='exhausted':result=before
        else:
            current=_roll(view,event,d,specs[0],evidence);rolls=(current,);previous.append(current)
            result=cc.extended(previous,d['dc'],d['complexity'],specs[0]['rank'],d['limited'])
            intervals=intervals+(d['interval_id'],)
            owed=[{'task_id':d['task_id'],'interval_id':d['interval_id'],'interval':d['interval'],'applied_to_clock':False}]
        raw={'kind':'extended',**asdict(result)}
        task={'signature':_signature(d,specs[0]),'rolls':[asdict(x) for x in previous],'interval_ids':intervals,'status':result.status,'total':result.total,'dc':result.dc,
              'elapsed_time_applied':False,'interval_obligations':(() if _ is None else _['interval_obligations'])+tuple(owed)}
        writes.append(m.Write(BASE+('tasks',d['task_id']),task))
    else:
        rolls=tuple(_roll(view,event,d,s,evidence) for s in specs)
        if d['mode']=='opposed':raw={'kind':'opposed','winner':cc.opposed(*rolls),'challenger_total':rolls[0].total,'defender_total':rolls[1].total}
        else:
            result=cc.team(rolls,d['dc'],d['required_people']) if d['mode']=='team' else cc.against_dc(rolls[0],d['dc'])
            raw={'kind':d['mode'],**asdict(result)}
    record={'request_key':event.payload['request_key'],'intent':req['intent'],'actors':req['actors'],'decision':d,'raw':raw,'rolls':[dict(asdict(x),total=x.total) for x in rolls],
            'narrative':None,'world_effects_applied':False,'costs_applied':False,'owed_intervals':owed,
            'completion_scope':'check_and_adjudication_record_only'}
    writes.insert(0,m.Write(BASE+('results',event.id),record))
    return m.Commit(tuple(writes),raw)


def _check_from_raw(raw):
    if raw['kind'] in ('dc','team'):return cc.CheckResult(raw['total'],raw['dc'],raw['margin'],raw['passed'])
    if raw['kind']=='opposed':
        return cc.CheckResult(raw['challenger_total'],raw['defender_total'],raw['challenger_total']-raw['defender_total'],raw['winner']=='challenger')
    if raw['kind']=='extended' and raw['status']!='in_progress':
        return cc.CheckResult(raw['total'],raw['dc'],raw['total']-raw['dc'],raw['status']=='complete')
    return None


def _response_guard(view,event,evidence):
    key=_key(event,'response')
    if key not in evidence:return m.Guard(m.Truth.UNKNOWN,_need(event,'response','source_choice','GM world response distinct from numeric check'))
    config,req=_config_req(view,event);choice=evidence[key]
    if m.identity(choice) not in {m.identity(x) for x in req['outcomes']}:return m.Guard(m.Truth.UNKNOWN,m.Block('invalid_state','response outside installed domain'))
    record=view.get(BASE+('results',event.id))
    if record['raw']['kind']=='extended' and record['raw']['status']=='in_progress' and choice.get('outcome')!='other':
        return m.Guard(m.Truth.UNKNOWN,m.Block('missing_refinement','in-progress interval is not whole-task success or failure'))
    decision=cc.adjudicate(_check_from_raw(record['raw']),**choice)
    if isinstance(decision,cc.PendingDecision):return m.Guard(m.Truth.UNKNOWN,m.Block('missing_refinement',decision.required))
    return m.Guard(m.Truth.TRUE)


def _response_update(view,event,evidence):
    record=m.thaw(view.get(BASE+('results',event.id)))
    record['narrative']=evidence[_key(event,'response')]
    return m.Commit((m.Write(BASE+('results',event.id),record),),{'narrative':record['narrative'],'world_effects_applied':False})


def build(aspect,snapshot,event):
    raw=aspect.aspect=='check_result'
    return m.Node(aspect.aspect,aspect.footprint.reads,aspect.footprint.writes,_raw_guard if raw else _response_guard,_raw_update if raw else _response_update,
                  after=() if raw else ('check_result',))


def input_request(binding,pending,snapshot,event):
    config,req=_data(snapshot,event); refs=tuple(config['source_refs'])
    request_id='common-input:'+a.digest((binding.event_id,binding.event_hash,binding.profile_hash,binding.revision,binding.context_hash,pending.key))
    common=(request_id,binding,pending.reason,refs,config['mode'])
    if pending.key==_key(event,'decision'):return i.ChoiceRequest(*common,tuple(config['gm_ids']),tuple(req['decisions']))
    if pending.key==_key(event,'response'):return i.ChoiceRequest(*common,tuple(config['gm_ids']),tuple(req['outcomes']))
    rec=snapshot.occurrences[event.id];d=rec.evidence[_key(event,'decision')]
    view=m.ReadView(snapshot.game,_footprints(snapshot,event)[0].reads)
    specs=_roll_specs(view,event,d)
    for spec in specs:
        for kind,count in (('dice',spec['rank']),('penalty',spec['penalty_count'])):
            if pending.key==_key(event,kind+':'+str(spec['index'])):
                return i.RollRequest(*common,tuple(config['roller_ids'][spec['actor']]),count,6,'independent_uniform_faces')
    raise ValueError('input outside recognized check occurrence')


def adapter():return a.Adapter(ADAPTER_ID,support,derive,build,input_request)


class CheckSession:
    """Small public facade; Registry and Broker own all actual authority."""
    def __init__(self,runtime,registration):
        if not isinstance(runtime,a.Runtime):raise TypeError('existing root Runtime required')
        self.runtime=runtime;self.registration=registration;self._events={}
    def begin(self,event_id,request_key):
        if event_id in self._events:
            event=self._events[event_id]
            if event.payload['request_key']!=request_key:return a.Finding('ConflictingReplay','occurrence request key changed')
        else:
            state=self.runtime.machine.state
            event=m.Event(event_id,EVENT_KIND,state.profile,state.revision,{'request_key':request_key})
            self._events[event_id]=event
        return self.runtime.prepare(self.registration,event)
    def submit(self,ticket):return self.runtime.submit(ticket)
    def pending(self,ticket):return self.runtime.get_input(ticket)
    def answer(self,pending,principal,value):return self.runtime.answer(pending,principal,value)
    def result(self,event_id):return self.runtime.machine.state.game['domains']['common_checks']['results'].get(event_id)
