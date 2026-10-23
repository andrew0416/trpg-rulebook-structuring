"""Persistent XP, Tutor Point awards and daily training state.

Fresh construction may allocate a fresh budget. An imported sheet with no TP
balance stays unknown: newly earned points are retained pending reconciliation,
never mistaken for its entire unspent lifetime budget.
"""
from copy import deepcopy
import state_fields as F
import arithmetic_policy as M

POINTS='ch05-pokemon/레벨-업/가르침-포인트'
TRAINING='ch05-pokemon/포켓몬-훈련'
LEVEL_STATE='tutor_point_level_state'


def source(rules, uid):
    if rules._selected_rule(uid)!=uid:
        raise ValueError('selected progression source needs its own policy: '+uid)


def fresh(rules, spec, *, explicit_balance=False):
    source(rules,POINTS)
    F.integer(spec['level'],'initial Pokemon level',1,100)
    spec.setdefault('exp',rules.mech('pokemon/experience-table')['exp_to_reach'][str(spec['level'])])
    if not explicit_balance:
        spec['tutor_points']=1+M.ratio(spec['level'],5)
    spec.setdefault(LEVEL_STATE,{'through_level':spec['level'],'pending_points':0,
        'origin':'observed_balance' if explicit_balance else 'fresh_creation',
        'initial_level':spec['level'],'initial_balance':spec.get('tutor_points'),'source':POINTS,'awards':[]})
    validate(spec)


def prepare_level(rules, spec):
    source(rules,POINTS)
    validate(spec)
    # The imported current level does not establish past spending or awards.
    spec.setdefault(LEVEL_STATE,{'through_level':spec['level'],'pending_points':0,
        'origin':'observed_balance' if 'tutor_points' in spec else 'unknown_import',
        'initial_level':spec['level'],'source':POINTS,'awards':[]})


def award_level(rules, spec):
    source(rules,POINTS)
    row=spec[LEVEL_STATE]
    level=spec['level']
    if level<=row['through_level']:
        return
    if level%5==0:
        known='tutor_points' in spec
        if known:spec['tutor_points']+=1
        else:row['pending_points']+=1
        row['awards'].append({'source':POINTS,'level':level,'points':1,
                              'destination':'balance' if known else 'pending'})
    row['through_level']=level


def observe_balance(e, actor, *, balance, reason):
    """GM establishes the actual current total, including pending awards."""
    if actor.kind!='pokemon':raise ValueError('Pokemon required')
    F.integer(balance,'actual current Tutor Points',0)
    if not isinstance(reason,str) or not reason.strip():raise ValueError('balance observation reason required')
    source(e.r,POINTS)
    prepare_level(e.r,actor.spec)
    before=actor.spec.get('tutor_points')
    pending=actor.spec[LEVEL_STATE]['pending_points']
    actor.spec['tutor_points']=balance
    actor.spec[LEVEL_STATE]['pending_points']=0
    actor.spec.setdefault('tutor_point_observations',[]).append({
        'source':POINTS,'before':before,'after':balance,
        'pending_included':pending,'reason':reason,'at':e.elapsed_seconds})
    return {'activity':'observe_tutor_points','balance':balance,'pending_included':pending}


def validate(spec):
    import growth_milestones as MILESTONES
    MILESTONES.validate(spec)
    if spec.get('kind')=='pokemon':
        if 'exp' in spec:F.integer(spec['exp'],'cumulative Pokemon XP',0)
        if 'tutor_points' in spec:F.integer(spec['tutor_points'],'remaining Tutor Points',0)
        row=spec.get(LEVEL_STATE)
        if row is not None:
            if not isinstance(row,dict) or row.get('source')!=POINTS:raise ValueError('invalid Tutor Point level source')
            F.integer(row.get('through_level'),'highest observed level',1,100)
            F.integer(row.get('initial_level'),'initial observed level',1,row['through_level'])
            F.integer(row.get('pending_points'),'unreconciled earned Tutor Points',0)
            if row.get('initial_balance') is not None:F.integer(row['initial_balance'],'recorded initial Tutor Points',0)
            if row.get('origin') not in ('fresh_creation','observed_balance','unknown_import','hatch'):raise ValueError('explicit Tutor Point origin required')
            if 'tutor_points' in spec and row['pending_points']:raise ValueError('known balance cannot omit pending Tutor Points')
            seen=set();pending=0
            if not isinstance(row.get('awards'),list):raise ValueError('Tutor Point awards must be a list')
            for award in row['awards']:
                if not isinstance(award,dict) or award.get('source')!=POINTS:raise ValueError('invalid Tutor Point award source')
                level=award.get('level');F.integer(level,'Tutor Point award level',row['initial_level']+1,row['through_level'])
                if level%5 or level in seen or type(award.get('points'))is not int or award['points']!=1:raise ValueError('one Tutor Point per distinct fifth level')
                if award.get('destination') not in ('balance','pending'):raise ValueError('Tutor Point award destination required')
                seen.add(level);pending+=int(award['destination']=='pending')
            reconciled=0
            for observation in spec.get('tutor_point_observations',[]):
                if not isinstance(observation,dict) or observation.get('source')!=POINTS:raise ValueError('invalid Tutor Point observation source')
                F.integer(observation.get('pending_included'),'reconciled earned Tutor Points',0)
                F.integer(observation.get('after'),'observed current Tutor Points',0)
                reconciled+=observation['pending_included']
            if row['pending_points']!=pending-reconciled:raise ValueError('pending Tutor Points lack actual award/reconciliation history')
    if 'experience_training_day' in spec:F.integer(spec['experience_training_day'],'last experience training day',0)
    record=spec.get('experience_training')
    if record is not None:
        if not isinstance(record,dict):raise ValueError('daily training record required')
        F.integer(record.get('day'),'trainer training day',0)
        F.integer(record.get('count'),'daily trained Pokemon count',0)
        if 'target_ids' in record:
            ids=record['target_ids']
            if not isinstance(ids,list) or any(not isinstance(x,str) or not x for x in ids) or len(set(ids))!=len(ids) or len(ids)>record['count']:raise ValueError('distinct actual daily training identities required')


def projection(spec):
    validate(spec)
    return {'xp':{'known':'exp' in spec,'value':spec.get('exp')},
            'tutor_points':{'known':'tutor_points' in spec,'value':spec.get('tutor_points'),
                            'level_awards':deepcopy(spec.get(LEVEL_STATE))},
            'training':deepcopy(spec.get('experience_training')),
            'last_training_day':spec.get('experience_training_day')}


def observe_xp(e, actor, *, total, reason):
    if actor.kind!='pokemon':raise ValueError('Pokemon required')
    F.integer(total,'observed cumulative Pokemon XP',0)
    if not isinstance(reason,str) or not reason.strip():raise ValueError('XP observation reason required')
    before=actor.spec.get('exp')
    actor.spec['exp']=total
    actor.spec.setdefault('xp_observations',[]).append({'source':'pokemon/experience-table',
        'before':before,'after':total,'reason':reason,'at':e.elapsed_seconds})
    return {'activity':'observe_pokemon_xp','total':total}
