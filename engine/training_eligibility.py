"""Data-declared training admission over actual trainers, targets and credits."""
from copy import deepcopy
import common_checks as C,crafting_recipes as Q,world_entities as W


def require_safety(safe):
    if type(safe) is not bool:raise ValueError('explicit training safety observation required')
    if not safe:raise ValueError('training requires an observed safe environment')


def _formula(row):
    if row is None:return
    Q._fields(row,('skill','purpose','multiplier'))
    Q._text(row['skill']);Q._text(row['purpose']);C.integer(row['multiplier'],'training rank multiplier',1)


def declaration(value):
    Q._fields(value,('id','source','session_limit','capacity','xp_rank','requirements','daily','shared_time'))
    Q._text(value['id']);Q._text(value['source']);C.integer(value['session_limit'],'training session participant limit',1)
    _formula(value['capacity']);_formula(value['xp_rank'])
    if value['capacity'] and value['xp_rank'] and value['capacity']['purpose']==value['xp_rank']['purpose']:
        raise ValueError('target capacity and XP rank require distinct purposes')
    if type(value['requirements']) is not list:raise ValueError('declared training requirements required')
    seen=set()
    for row in value['requirements']:
        Q._fields(row,('id','source','condition','reason'))
        for field in ('id','source','reason'):Q._text(row[field])
        Q._condition(row['condition'])
        if row['id'] in seen:raise ValueError('distinct training requirements required')
        seen.add(row['id'])
    if value['daily'] is not None:
        Q._fields(value['daily'],('actor_record','target_stamp','target_history'))
        for field in value['daily'].values():Q._text(field)
        if value['capacity'] is None:raise ValueError('daily training quota needs its own capacity formula')
    if value['shared_time'] is not None:
        Q._fields(value['shared_time'],('application','minimum_seconds'))
        Q._text(value['shared_time']['application']);C.integer(value['shared_time']['minimum_seconds'],'shared training duration',1)
    return deepcopy(value)


def participants(engine,trainer,targets,limit=6):
    import pokemon_activities as A
    C.integer(limit,'training session participant limit',1)
    if type(targets) not in (list,tuple) or not 1<=len(targets)<=limit:
        raise ValueError('one to '+('six' if limit==6 else str(limit))+' distinct training participants required')
    if len({id(t) for t in targets})!=len(targets):raise ValueError('distinct actual training targets required')
    W.require_actors(engine,trainer,*targets);A._trainer(trainer)
    day=C.integer(trainer.spec.get('frequency_state',{}).get('day',0),'training calendar day',0)
    for target in targets:
        A._pokemon(target);A._owner(trainer,target)
        if target.dead or target.fainted:raise ValueError('conscious training participant required')
        if C.integer(target.spec.get('frequency_state',{}).get('day',0),'participant training day',0)!=day:
            raise ValueError('training calendars must agree')
    return day


def _daily(trainer,targets,policy,day,limit):
    record=trainer.spec.get(policy['actor_record'],{})
    if type(record) is not dict:raise ValueError('actual daily training record required')
    if record:
        C.integer(record.get('day'),'recorded training day',0)
        C.integer(record.get('count'),'recorded training target count',0)
    used=record.get('count',0) if record.get('day')==day else 0
    if used+len(targets)>limit:raise ValueError('daily training target limit exceeded')
    for target in targets:
        stamp=target.spec.get(policy['target_stamp'])
        if stamp is not None:C.integer(stamp,'actual target training day',0)
        history=target.spec.get(policy['target_history'],[])
        if type(history) is not list:raise ValueError('actual target training history required')
        received=stamp==day
        for row in history:
            if type(row) is not dict:raise ValueError('actual target training history record required')
            received=received or C.integer(row.get('day'),'historical target training day',0)==day
        if received:raise ValueError('Pokemon already received experience training today')
    return used


def prepare(engine,trainer,targets,value,*,safe=None,from_grooming=False,from_training=False):
    import pokemon_teaching as TEACHING
    value=declaration(value);TEACHING.credit_mode(from_grooming,from_training)
    Q._selected(engine,value['source'])
    if engine.encounter_active:raise ValueError('training requires its outside-combat procedure')
    day=participants(engine,trainer,targets,value['session_limit'])
    for row in value['requirements']:
        Q._selected(engine,row['source'])
        if not Q._observe(engine,trainer,row['condition'],set()):raise ValueError(row['reason'])
    plans={}
    def rank(row):
        if row is None:return None
        plan=engine.plan_rank_context(trainer,row['skill'],purpose=row['purpose'],targets=targets,source=value['source'])
        plans[row['purpose']]=plan
        return C.integer(plan['effective_rank'],'actual training rank',0)*row['multiplier']
    capacity=rank(value['capacity']);xp_rank=rank(value['xp_rank'])
    limit=value['session_limit'] if capacity is None else capacity
    used=_daily(trainer,targets,value['daily'],day,limit) if value['daily'] is not None else 0
    if value['daily'] is None and len(targets)>limit:raise ValueError('training target capacity exceeded')
    credits=[]
    if from_grooming or from_training:
        shared=value['shared_time']
        if shared is None:raise ValueError('this training purpose does not admit a completed-hour credit')
        for target in targets:
            credit=TEACHING.training_credit(engine,trainer,target,shared['application'],from_training=from_training)
            if credit['hours']*3600<shared['minimum_seconds']:raise ValueError('completed training does not cover training duration')
            credits.append({'pokemon_id':target.entity_id,'completed_at':credit['completed_at'],'source':credit['source']})
    else:require_safety(safe)
    return {'id':value['id'],'source':value['source'],'declaration':value,'trainer_id':trainer.entity_id,
            'target_ids':[t.entity_id for t in targets],'day':day,'session_limit':value['session_limit'],
            'target_limit':limit,'capacity_rank':None if value['capacity'] is None else capacity//value['capacity']['multiplier'],
            'xp_rank':xp_rank,'daily_used':used,'rank_plans':plans,'completed_training_credits':credits}


def native(purpose,*,seconds=3600):
    import pokemon_progression as P
    return {'id':'native:'+purpose,'source':'edge/미용사' if purpose=='groom' else P.TRAINING,
            'session_limit':6,'capacity':None,'xp_rank':None,'requirements':[],'daily':None,
            'shared_time':None if purpose in ('groom','training_hour') else {'application':purpose,'minimum_seconds':seconds}}


def experience_plan(engine,trainer,targets,*,use_intimidate=False,use_reserves=False,from_grooming=False,from_training=False,
                    safe=None,bonus_skill=None,grooming_policy=None,beast_policy=None):
    """Existing reviewed adapters select each independent rank formula."""
    import pokemon_activities as A,skill_modifiers as S
    for flag in (use_intimidate,use_reserves):
        if type(flag) is not bool:raise ValueError('explicit training substitution choice required')
    if use_intimidate:A._feature(engine,trainer,'beast')
    if use_reserves:
        A._feature(engine,trainer,'reserves')
        if use_intimidate or from_grooming:raise ValueError('Train the Reserves cannot replace Command using Beast Master or Groomer')
    value=native('experience_training');skill='협박' if use_intimidate else '명령'
    value['capacity']={'skill':skill,'purpose':'experience_training.target_limit','multiplier':2 if use_reserves else 1}
    value['xp_rank']={'skill':skill,'purpose':'experience_training.xp_bonus','multiplier':1}
    value['daily']={'actor_record':'experience_training','target_stamp':'experience_training_day','target_history':'experience_training_history'}
    selected_beast=None;selected_policy=None
    if use_intimidate:
        selected_beast='body_limit_and_xp' if beast_policy is None else beast_policy
        if selected_beast not in ('body_limit_and_xp','csv_target_limit'):raise ValueError('explicit reviewed Beast Master source policy required')
        if selected_beast=='csv_target_limit':
            A._beast_csv_source(engine.r);value['xp_rank']['skill']='명령'
    elif beast_policy is not None:raise ValueError('Beast Master source selection requires Intimidate substitution')
    if from_grooming:
        A._feature(engine,trainer,'groomer')
        if use_intimidate:raise ValueError('combined Beast Master/Groomer rank policy requires a sourced ruling')
        if bonus_skill is None:raise ValueError('choose General or Pokemon Education for grooming XP')
        if S.skill_id(engine.r.skill_policy,bonus_skill,required=True) not in {S.skill_id(engine.r.skill_policy,s) for s in ('일반 지식','포켓몬학')}:
            raise ValueError('invalid Groomer bonus skill')
        selected_policy='body_bonus_xp' if grooming_policy is None else grooming_policy
        if selected_policy not in ('body_bonus_xp','csv_target_limit'):raise ValueError('explicit reviewed Groomer source policy required')
        if selected_policy=='csv_target_limit':A._groomer_csv_source(engine.r)
        value['capacity' if selected_policy=='csv_target_limit' else 'xp_rank']['skill']=bonus_skill
    elif bonus_skill is not None or grooming_policy is not None:raise ValueError('education/source selection is exclusive to Groomer')
    plan=prepare(engine,trainer,targets,value,safe=safe,from_grooming=from_grooming,from_training=from_training)
    base=plan['capacity_rank']
    if value['capacity']['skill']!=skill:
        base=engine.plan_rank_context(trainer,skill,purpose='experience_training.target_limit',targets=targets,source=value['source'])['effective_rank']
    plan.update(skill=skill,rank=base,grooming_policy=selected_policy,beast_policy=selected_beast)
    return plan
