"""PTK ordinary team/assisted/extended actions on the existing native Engine.

Arithmetic stays in common_checks. GM-selected skills, DCs, contribution policy
and elapsed intervals are inputs; this adapter does not infer them from prose
or apply narrative consequences/costs. No new root/certificate API is required.
"""
from copy import copy, deepcopy
from dataclasses import dataclass, replace
from functools import wraps
import common_checks as checks
import skill_modifiers as skills
from resolution_transaction import resolve_transaction

@dataclass(frozen=True)
class ExtendedAction:
    task_id: str
    interval_id: str
    result: checks.ExtendedResult
    outcome: object

def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('nonempty ' + name + ' required')
    return value

def assisted_options(engine, actor, skill, options):
    """GM supplies a relevant helper skill; derive its rank from the live actor."""
    options = dict(options)
    if 'helper' not in options:
        if 'helper_skill' in options:
            raise ValueError('helper_skill requires a helper')
        return options
    helper = options.pop('helper')
    helper_skill = options.pop('helper_skill', skill)
    if helper is None or helper is actor:
        raise ValueError('a distinct helper is required')
    if helper.dead or helper.fainted:
        raise ValueError('a conscious helper is required')
    if 'helper_rank' in options or 'helper_bonus' in options:
        raise ValueError('provide a helper actor or a pre-resolved rank, not both')
    _text(helper_skill, 'GM-selected helper skill')
    plan=engine.plan_skill_check(helper,helper_skill,purpose='assistance',target=actor,provider=helper)
    rank=plan['effective_rank']
    minimum = engine.r.mech('gameplay/skill-check')['assist_min_rank']
    if rank < minimum:
        raise ValueError('helper skill must be at least Novice')
    options['helper_rank'] = rank
    options['helper_bonus'] = skills.assistance_bonus(engine.r,helper,helper_skill,rank)
    return options

def _staged_rolls(engine, resolve):
    """Only valid resolution commits RNG/logs; skill rolls read actor state."""
    def run(_subjects, rng):
        staged = copy(engine)
        staged.rng, staged.log_lines = rng, []
        # Records retain live actor references; mutations are replacements.
        staged._ap_rolls = {k: dict(v) for k, v in engine._ap_rolls.items()}
        result = resolve(staged)
        return result, staged.log_lines, staged._ap_rolls
    result, logs, ap_rolls = resolve_transaction([], engine.rng, run)
    engine.log_lines.extend(logs)
    engine._ap_rolls.clear()
    engine._ap_rolls.update(ap_rolls)
    return result

def team_action(engine, skill, dc, options, adjudication):
    options = dict(options)
    participants = options.pop('participants', None)
    required = options.pop('required_people', None)
    equal = options.pop('equal_contribution', None)
    no_main = options.pop('no_main_actor', None)
    per_actor = options.pop('participant_options', None)
    weights = options.pop('contribution_weights', None)
    reason = options.pop('weighting_reason', None)
    action_id = options.pop('action_id', None)
    if options:
        raise ValueError('unsupported team options: ' + repr(sorted(options)))
    if participants is None or skill is None or dc is None or required is None:
        return checks.PendingDecision('GM team participants / skill / DC / required people')
    if no_main is not True or (weights is None and equal is not True):
        return checks.PendingDecision('ordinary team requires equal contributions and no main actor; weighting needs a sourced ruling')
    if weights is not None and (equal is not False or reason is None):
        return checks.PendingDecision('GM explicit unequal contributions and weighting reason')
    if weights is None and reason is not None:raise ValueError('weighting reason needs explicit participant weights')
    participants = list(participants)
    if not participants or len({id(c) for c in participants}) != len(participants):
        raise ValueError('distinct nonempty team participants required')
    if weights is not None:
        _text(reason,'GM weighting reason')
        if not isinstance(weights,(list,tuple)) or len(weights)!=len(participants):raise ValueError('one explicit weight per team participant')
        weights=tuple(checks.integer(x,'contribution multiplier',1) for x in weights)
    _text(skill, 'GM-selected team skill')
    checks.integer(dc, 'DC')
    checks.integer(required, 'required people', 1)
    if per_actor is None:
        per_actor = [{} for _ in participants]
    if not isinstance(per_actor, (list, tuple)) or len(per_actor) != len(participants):
        raise ValueError('one roll-options record per participant required')
    roll_ids = [o.get("roll_id") for o in per_actor if isinstance(o, dict) and o.get("roll_id") is not None]
    if len(set(roll_ids)) != len(roll_ids):
        raise ValueError("each team roll needs its own identity")
    import skill_feature_actions as SF
    featured=any(isinstance(o,dict) and o.get('feature') is not None for o in per_actor)
    if featured:_text(action_id,'team action identity with observed feature choices')
    elif action_id is not None:raise ValueError('team action_id currently identifies explicit feature resolution')
    prepared = []
    for actor, opts in zip(participants, per_actor):
        if not isinstance(opts, dict):
            raise ValueError('participant roll options must be a mapping')
        opts = dict(opts)
        if opts.get('helper_rank', 0) != 0 or 'helper' in opts or 'helper_skill' in opts:
            raise ValueError('team-plus-assistance needs an explicit sourced extension')
        roll = SF.prepared_for_sequence(engine,actor,skill,opts) if featured else engine._prepare_skill_roll(actor,skill,**opts)
        if roll[3] is not None: opts['fixed'] = roll[3]
        if roll[4] is not None: opts['fixed_penalties'] = roll[4]
        prepared.append(opts)
    def resolve(staged, rolls=None):
        if rolls is None:rolls = [staged.skill_roll(c, skill, **opts) for c, opts in zip(participants, prepared)]
        result = checks.team(rolls, dc, required) if weights is None else checks.weighted_team(rolls,dc,required,weights)
        staged.log(f'  팀 판정: 합계 {result.total} vs DC {dc} × 필요 인원 {required} = {result.dc}', 'gameplay/skill-check')
        outcome=checks.adjudicate(result, **adjudication)
        if weights is not None:
            staged.log('  GM 팀 기여도: '+str(weights)+'; '+reason,'gameplay/skill-check')
            outcome=replace(outcome,basis={'kind':'weighted_team','weights':weights,'reason':reason,'participants':tuple(c.spec.get('id',c.name) for c in participants),'ordinary_dc':dc,'required_people':required})
        return outcome
    if featured:
        basis={'kind':'team','dc':dc,'required':required,'weights':weights,'reason':reason}
        plans=[(actor,skill,opts) for actor,opts in zip(participants,prepared)]
        return SF.sequence(engine,'team:'+action_id,basis,plans,lambda rolls:resolve(engine,rolls))
    return _staged_rolls(engine, resolve)

def extended_action(engine, actor, skill, dc, options, adjudication):
    options = dict(options)
    helper=options.get('helper')
    task_id = options.pop('task_id', None)
    interval_id = options.pop('interval_id', None)
    interval = options.pop('interval', None)
    elapsed = options.pop('interval_completed', None)
    complexity = options.pop('complexity', None)
    limited = options.pop('limited', None)
    if actor is None or skill is None or dc is None:
        return checks.PendingDecision('GM extended-check actor / skill / DC')
    if engine.encounter_active:
        return checks.PendingDecision('extended checks require noncombat intervals')
    if any(x is None for x in (task_id, interval_id, interval, complexity, limited)) or elapsed is not True:
        return checks.PendingDecision('GM task, completed interval, complexity and limited/unlimited decision')
    _text(task_id, 'task identity')
    _text(interval_id, 'interval identity')
    _text(skill, 'GM-selected extended skill')
    if not isinstance(interval, dict) or set(interval) != {'amount', 'unit'}:
        raise ValueError('interval needs amount and unit')
    checks.integer(interval['amount'], 'interval amount', 1)
    _text(interval['unit'], 'interval unit')
    scales={'second':1,'seconds':1,'초':1,'minute':60,'minutes':60,'분':60,'hour':3600,'hours':3600,'시간':3600,
            'day':86400,'days':86400,'일':86400,'week':604800,'weeks':604800,'주':604800}
    if interval['unit'] not in scales:return checks.PendingDecision('GM interval duration in a known actual time unit')
    seconds=interval['amount']*scales[interval['unit']]
    options = assisted_options(engine, actor, skill, options)
    import skill_feature_actions as SF
    featured=options.get('feature') is not None
    prepared = SF.prepared_for_sequence(engine,actor,skill,options) if featured else engine._prepare_skill_roll(actor,skill,**options)
    rank = prepared[2]
    effect_rank = skills.effective_rank(engine.r,actor,skill)
    if prepared[3] is not None: options['fixed'] = prepared[3]
    if prepared[4] is not None: options['fixed_penalties'] = prepared[4]
    initial = checks.extended([], dc, complexity, rank, limited, effective_rank=effect_rank)
    basis = {
        'skill': skill, 'rank': rank, 'effective_rank': effect_rank, 'dc': dc, 'complexity': complexity,
        'limited': limited, 'interval': deepcopy(interval),
        'modifier': prepared[5], 'helper_rank': options.get('helper_rank', 0), 'helper_bonus':options.get('helper_bonus'),
        'penalty_count': options.get('penalty_count', 0),
        'rank_rule': engine.r.mech('gameplay/skill-rank-dice'),
        'ordinary_rule': engine.r.mech('gameplay/skill-check'),
    }
    previous = engine._extended_checks.get(task_id)
    if previous is not None:
        if previous['actor'] is not actor or previous['basis'] != basis:
            raise ValueError('changed extended task actor/rank/policy requires an explicit new ruling')
        if previous['result'].status != 'in_progress':
            raise ValueError('extended task already terminal; no automatic retry')
        if interval_id in previous['interval_ids']:
            raise ValueError('extended interval already recorded')
        rolls, ids = tuple(previous['rolls']), tuple(previous['interval_ids'])
    else:
        rolls, ids = (), ()
    def resolve(staged, observed=None, actual=None, native_options=None):
        actual=actor if actual is None else actual
        native_options=options if native_options is None else native_options
        if initial.status in ('complete', 'exhausted') and not rolls:
            # Zero attempts or an already reached target: do not draw phantom dice.
            recorded, intervals, result = (), (), initial
        else:
            roll = observed[0] if observed is not None else staged.skill_roll(actual, skill, **native_options)
            recorded, intervals = (*rolls, roll), (*ids, interval_id)
            result = checks.extended(recorded, dc, complexity, rank, limited, effective_rank=effect_rank)
        staged.log(f'  연장 판정 {task_id}: {result.total}/{result.dc}, {result.attempts_used}회, {result.status}', 'gameplay/skill-check')
        if result.status == 'in_progress':
            outcome = checks.PendingDecision('next GM-confirmed interval')
        else:
            raw = checks.CheckResult(result.total, result.dc, result.total-result.dc, result.status == 'complete')
            outcome = checks.adjudicate(raw, **adjudication)
        record = {'actor': actual, 'basis': basis, 'rolls': recorded,
                  'interval_ids': intervals, 'result': result}
        return ExtendedAction(task_id, interval_id, result, outcome), record
    import activity_jobs as JOBS,state_grants as G,world_entities as W
    job_id='extended-check:'+task_id
    policy={'target':initial.dc,'attempt_limit':initial.attempt_limit,'interval_seconds':seconds,
            'continuity':'resumable','resume':'retain'}
    participants=() if helper is None else (helper,)
    existing=getattr(engine,'_activity_jobs',{}).get('jobs',{}).get(job_id)
    if previous is not None and existing is None:raise ValueError('historical extended arithmetic has no elapsed job proof; select a new task')
    if existing is not None:
        JOBS._checked_row(engine,job_id)
        if existing['owner'] is not actor or existing['participants']!=list(participants) or existing['definition']!=JOBS.definition(policy):
            raise ValueError('changed extended job participants or duration policy')
    contributor={'actor_id':actor.entity_id,'skill':skill}
    terminal=initial.status in ('complete','exhausted') and not rolls
    if featured and not terminal:
        # Observed feature choices remain durable on their existing native path.
        # Time-boundary errors must be found before drawing or paying for them.
        if existing is not None:JOBS._preflight_work(engine,existing,interval_id=interval_id,seconds=seconds,attempt=True,contribution=contributor)
        else:engine.preflight_advance_time(seconds,[actor,*participants])
    def commit_interval(observed=None):
        def apply(staged,actual,*helpers):
            index=W.actor_index(staged)
            memo={id(c):index[c.entity_id] for c in W.actors(engine) if c.entity_id in index}
            memo[id(actor)]=actual
            native_options=deepcopy(options,memo)
            # The existing adapter binds an explicitly supplied actor to its
            # durable task. Preserve that native admission for detached new IDs.
            if task_id not in staged._extended_checks:staged._extended_checks[task_id]={'actor':actual}
            if existing is None:JOBS._start(staged,actual,helpers,job_id=job_id,source='gameplay/skill-check',policy=policy,context={'task_id':task_id})
            if terminal:
                action,record=resolve(staged,observed,actual,native_options)
            else:
                payload=[]
                def native_roll(e):
                    action,record=resolve(e,observed,actual,native_options);payload.append((action,record))
                    return record['rolls'][-1]
                JOBS._work(staged,JOBS._row(staged,job_id),interval_id=interval_id,seconds=seconds,
                           roller=native_roll,contribution=contributor)
                action,record=payload[0]
            record['job_id']=job_id;staged._extended_checks[task_id]=record
            JOBS.validate_world(staged,W.actor_index(staged))
            return action
        return G.transition(engine,actor,apply,participants=participants)
    if featured and not terminal:
        return SF.sequence(engine,'extended:'+task_id+':'+interval_id,basis,[(actor,skill,options)],commit_interval)
    return commit_interval()



def with_declaration(action):
    """Preserve a player's intent and the GM selection on the native action path.

    No prose classifier: the host/GM explicitly identifies ordinary vs specialized
    activity. A suggested skill never supplies the GM's selected skill.
    """
    @wraps(action)
    def declared(engine, c=None, skill=None, dc=None, *, declaration=None, difficulty_context=None, disagreement=None, **options):
        import adjudication_guidance as GUIDANCE
        selection={'mode':options.get('mode'),'skill':skill,'dc':dc}
        difficulty=GUIDANCE.difficulty(engine,dc,difficulty_context)
        dispute=GUIDANCE.disagreement(engine,disagreement,selection)
        def annotate(result):
            if difficulty is None and dispute is None:return result
            base=result.outcome if isinstance(result,ExtendedAction) else result
            basis=deepcopy(base.basis or {})
            if difficulty is not None:basis['difficulty_guidance']=difficulty
            if dispute is not None:basis['disagreement']=dispute
            revised=replace(base,basis=basis)
            return replace(result,outcome=revised) if isinstance(result,ExtendedAction) else revised
        if declaration is None:return annotate(action(engine,c,skill,dc,**options))
        if not isinstance(declaration,dict):
            raise ValueError('action declaration must be a mapping')
        allowed={'action','intent','method','proposed_skill','activity','context'}
        if set(declaration)-allowed:raise ValueError('unknown declaration fields')
        for field,value in declaration.items():_text(value,'declaration '+field)
        if 'action' not in declaration:raise ValueError('declared action required')
        record=deepcopy(declaration)
        record['gm_selection']={'mode':options.get('mode'),'skill':skill,'dc':dc}
        activity=record.get('activity','ordinary')
        if activity!='ordinary':
            chapters={'breeding':'ch05','capture':'ch05','befriending':'ch05',
                      'fossils':'ch05','fishing':'ch05','mounting':'ch05','combat':'ch07'}
            result=checks.PendingDecision('specialized activity '+activity+' requires its own procedure ('+chapters.get(activity,'source needed')+')')
        else:
            result=action(engine,c,skill,dc,**options)
        if isinstance(result,ExtendedAction):
            return annotate(replace(result,outcome=replace(result.outcome,declaration=record)))
        return annotate(replace(result,declaration=record))
    return declared

def rank_judgment(engine,actor,skill,dc,options,adjudication):
    """ch03 Athletics: GM may inspect the live rank without drawing dice."""
    if actor is None or skill is None:return checks.PendingDecision('GM actor and rank-selected skill')
    if dc is not None or options:raise ValueError('rank judgment is not a DC or dice check')
    sid=skills.skill_id(engine.r.skill_policy,skill,required=True)
    if sid!=skills.skill_id(engine.r.skill_policy,'육상',required=True):
        return checks.PendingDecision('source for this other skill rank-only procedure')
    name,expr,ordinary=skills.rank(engine.r,actor,skill)
    effective=skills.effective_rank(engine.r,actor,skill)
    basis={'kind':'rank_judgment','skill':sid,'rank_name':name,'ordinary_rank':ordinary,'effective_rank':effective,'source':'input/ch03-skills-edges-feats.md:68-76'}
    result=checks.adjudicate(**adjudication)
    engine.log(f'  {actor.name}: GM이 육상 랭크 {effective}를 근거로 판단 (굴림 없음)','skill/육상')
    return replace(result,basis=basis)


def ordinary_action(engine,actor,skill,dc,options,adjudication):
    import skill_feature_actions as SF
    checks.integer(dc,'DC')
    options=dict(options)
    purpose=options.pop('roll_purpose','ordinary skill check')
    options=assisted_options(engine,actor,skill,options)
    def finish(rolls,executor=None):
        executor=engine if executor is None else executor
        result=checks.against_dc(rolls[0],dc)
        SF.finish(executor,actor,options.get('roll_id'))
        return checks.adjudicate(result,**adjudication)
    if options.get('feature') is not None:
        roll_id=options.get('roll_id')
        if not isinstance(roll_id,str) or not roll_id.strip():raise ValueError('feature action requires actual roll ID')
        return SF.sequence(engine,'ordinary:'+roll_id,{'dc':dc},[(actor,skill,options)],finish)
    plan_options=dict(options);target=plan_options.pop('skill_target',actor)
    plan=engine.plan_skill_check(actor,skill,purpose=purpose,target=target,**plan_options)
    options['fixed']=plan['fixed_faces'];options['fixed_penalties']=plan['fixed_penalties']
    def resolve(staged):
        return replace(finish([staged.skill_roll(actor,skill,**options)],staged),basis={'roll_plan':plan})
    return _staged_rolls(engine,resolve)
