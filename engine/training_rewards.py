"""One completed work batch pays declared training rewards atomically."""
from copy import deepcopy
import common_checks as C,crafting_recipes as Q,training_eligibility as E
import world_entities as W,resolution_transaction as TX,arithmetic_policy as M

KEY='training_reward_records'
BONUSES={'movement','initiative','critical','effect','accuracy','skill','evasion','save'}
DAILY={'actor_record':'experience_training','target_stamp':'experience_training_day','target_history':'experience_training_history'}


def xp_formula(value):
    Q._fields(value,('level_divisor','rounding','rank_bonus','flat'))
    C.integer(value['level_divisor'],'training XP level divisor',1);C.integer(value['flat'],'training XP flat adjustment')
    if value['rounding'] not in ('floor','ceil'):raise ValueError('explicit training XP rounding required')
    rows=value['rank_bonus']
    if type(rows) is not list or not rows:raise ValueError('declared XP rank steps required')
    last=-1
    for n,row in enumerate(rows):
        Q._fields(row,('maximum','value'));C.integer(row['value'],'XP rank step value')
        if row['maximum'] is None:
            if n!=len(rows)-1:raise ValueError('XP catch-all must be the final step')
        else:
            C.integer(row['maximum'],'XP rank step maximum',last+1);last=row['maximum']
    if rows[-1]['maximum'] is not None:raise ValueError('XP rank formula needs an explicit final step')
    return deepcopy(value)


def native_xp_formula():
    return {'level_divisor':2,'rounding':'floor','rank_bonus':[
        {'maximum':2,'value':0},{'maximum':4,'value':5},{'maximum':6,'value':10},{'maximum':None,'value':15}],'flat':0}


def amount(level,rank,formula):
    formula=xp_formula(formula);C.integer(level,'actual recipient level',1);C.integer(rank,'actual XP rank',0)
    bonus=next(row['value'] for row in formula['rank_bonus'] if row['maximum'] is None or rank<=row['maximum'])
    base=(M.ratio if formula['rounding']=='floor' else M.ceil_ratio)(level,formula['level_divisor'])
    return C.integer(base+bonus+formula['flat'],'actual training XP award',0)


def bonus_definition(row):
    Q._fields(row,('id','source','kind','bonuses'))
    Q._text(row['id']);Q._text(row['source'])
    if row['kind']!='bonus' or type(row['bonuses']) is not dict or not row['bonuses'] or not set(row['bonuses'])<=BONUSES:
        raise ValueError('declared supported training bonus fields required')
    for value in row['bonuses'].values():C.integer(value,'declared training bonus')
    return deepcopy(row)


def declaration(value):
    Q._fields(value,('id','source','eligibility','seconds','rewards'))
    Q._text(value['id']);Q._text(value['source']);E.declaration(value['eligibility']);C.integer(value['seconds'],'training work seconds',1)
    if value['source']!=value['eligibility']['source']:raise ValueError('training provider source must agree with admission')
    if type(value['rewards']) is not list or not value['rewards']:raise ValueError('declared training rewards required')
    identities=set();families=set()
    for row in value['rewards']:
        if type(row) is not dict:raise ValueError('training reward declaration required')
        for key in ('id','source','kind'):Q._text(row.get(key))
        if row['id'] in identities:raise ValueError('distinct training reward identities required')
        identities.add(row['id']);kind=row['kind'];family='bonus' if kind=='regime' else kind
        if kind!='teach' and family in families:raise ValueError('one reward per participant and reward family required')
        families.add(family)
        if kind=='xp':
            Q._fields(row,('id','source','kind','formula'));xp_formula(row['formula'])
            if value['eligibility']['xp_rank'] is None or value['eligibility']['daily']!=DAILY:
                raise ValueError('XP rewards require independent XP rank and actual target daily evidence')
        elif kind=='bonus':bonus_definition(row)
        elif kind in ('regime','teach'):
            Q._fields(row,('id','source','kind','choices',*(['edge'] if kind=='teach' else [])))
            if type(row['choices']) is not dict:raise ValueError('explicit per-participant reward choices required')
            if kind=='teach':
                Q._text(row['edge'])
                if row['edge']!=row['source']:raise ValueError('teaching reward retains its canonical edge source')
            for identity,choices in row['choices'].items():
                Q._text(identity)
                if kind=='regime':
                    if type(choices) is not list or not choices:raise ValueError('selected training regimes required')
                    for uid in choices:Q._text(uid)
                elif type(choices) is not dict or not set(choices)<= {'skill','stat','capability','move_id'}:
                    raise ValueError('explicit native teaching choices required')
        elif kind=='credit':
            Q._fields(row,('id','source','kind','publication','policy'))
            if row['publication'] not in (None,'ordinary','grooming'):raise ValueError('explicit completed-credit publication required')
            import activity_jobs as J
            J.definition({'required_seconds':value['seconds'],'credit':row['policy']})
            if row['source']!=value['source']:raise ValueError('completed job credit keeps its actual provider source')
            if row['publication'] is not None and (value['seconds']!=3600 or row['policy']!=J.training_policy()):
                raise ValueError('native teaching credit requires an actual safe one-hour training job')
            if row['publication']=='ordinary' and row['source']!='ch05-pokemon/포켓몬-훈련':raise ValueError('ordinary training credit keeps its reviewed source')
            if row['publication']=='grooming' and row['source']!='edge/미용사':raise ValueError('grooming credit keeps its reviewed source')
        elif kind=='groom':
            Q._fields(row,('id','source','kind','intro_dice'));C.integer(row['intro_dice'],'grooming introduction dice',0)
        else:raise ValueError('training reward needs a supported effect consumer')
    return deepcopy(value)


def policy(eligibility,seconds,rewards,identity='native:training-rewards'):
    return {'id':identity,'source':eligibility['source'],'eligibility':deepcopy(eligibility['declaration']),
            'seconds':seconds,'rewards':deepcopy(rewards)}


def _replace_training(engine,trainer,target,rows,*,request_id,started_at):
    """Replace one target's training contributions under their actual sources."""
    import training_features as F,state_grants as G
    for old in list(F.active(target)):
        if old['mode']=='training':G.revoke(target,old[G.TAG],engine=engine)
    applied=[]
    for source,uid,authority,definition in rows:
        G._source(target,source,'training',owner_id=trainer.entity_id,lifetime='your_pokemon',rule_id=uid,tutor_points=0)
        row={'type':F.TYPE,'rule_id':uid,'mode':'training','owner':trainer,'session':request_id,
             'elite_authority':authority,'started_at':started_at,'completed_at':engine.elapsed_seconds}
        if definition is not None:row['training_reward_definition']=definition
        G.apply_owned(engine,target,source,lambda row=row:target.registry.append(row))
        applied.append({'pokemon_id':target.entity_id,'rule_id':uid,'source':source})
    return applied


def grant_regimes(engine,trainer,targets,plan,*,request_id,started_at):
    import training_features as F
    serial=C.integer(trainer.custom_conditions.get('_training_session_serial',0),'training session serial',0)+1
    trainer.custom_conditions['_training_session_serial']=serial;authority=F.elite(trainer);applied=[]
    for target,(_,uids) in zip(targets,plan):
        if not uids:continue
        rows=[]
        for uid in uids:
            source='training:'+trainer.entity_id+':'+str(serial)+':'+target.entity_id+':'+uid
            rows.append((source,uid,authority,None))
        actual=_replace_training(engine,trainer,target,rows,request_id=request_id,started_at=started_at)
        import taskmaster as TASK
        for result in actual:
            if result['rule_id']==F.BRUTAL:
                hardened=TASK.training(engine,trainer,target,session=request_id,training_source=result['source'])
                if hardened is not None:result['taskmaster']=hardened
        applied.extend(actual)
    return applied


def grant_bonus(engine,trainer,targets,row,*,record_id,started_at):
    definition=bonus_definition(row);applied=[]
    for target in targets:
        source='training-reward:'+record_id+':'+row['id']+':'+target.entity_id
        rows=[(source,row['source'],False,definition)]
        applied.extend(_replace_training(engine,trainer,target,rows,request_id=record_id,started_at=started_at))
    return applied


def _credit_facts(engine,trainer,targets,application,*,from_training):
    import pokemon_teaching as T
    result=[]
    for target in targets:
        row=T.training_credit(engine,trainer,target,application,from_training=from_training)
        result.append({'target_id':target.entity_id,'credit_id':row['credit_id'],'application':application})
    return result


def execute(engine,trainer,targets,value,*,request_id=None,safe=None,from_training=False,from_grooming=False,
            reason='observed completed training',pushed_skills=None,type_manual=None,_eligibility=None,_session_id=None,_pushed_source=None):
    import state_grants as G,activity_jobs as J,pokemon_teaching as T,training_features as F
    import downtime as D,food_effects as FOOD,researcher_features as RF
    W.require_actors(engine,trainer,*targets);value=declaration(value);Q._text(reason)
    if request_id is not None:Q._text(request_id)
    request={'declaration':value,'trainer_id':trainer.entity_id,'target_ids':[t.entity_id for t in targets],
             'safe':safe,'from_training':from_training,'from_grooming':from_grooming,'reason':reason,'pushed_skills':deepcopy(pushed_skills)}
    if type_manual is not None:request['type_manual']=deepcopy(type_manual)
    def apply(e,owner,*participants):
        store=owner.spec.get(KEY,{})
        if type(store) is not dict:raise ValueError('actual training reward records required')
        if request_id is not None:
            prior=TX.replay_result(store,request_id,request,fingerprint_field='intent')
            if prior is not None:
                validate_world(e,W.actor_index(e));return deepcopy(prior['result'])
        eligibility=deepcopy(_eligibility) if _eligibility is not None else E.prepare(e,owner,participants,value['eligibility'],safe=safe,from_training=from_training,from_grooming=from_grooming)
        if eligibility['trainer_id']!=owner.entity_id or eligibility['target_ids']!=[t.entity_id for t in participants] or eligibility['declaration']!=value['eligibility']:
            raise ValueError('training reward admission/provider changed')
        credit_node=next((row for row in value['rewards'] if row['kind']=='credit'),None)
        shared=from_training or from_grooming
        if shared and credit_node is not None:raise ValueError('completed shared time cannot mint a new work credit')
        if shared and value['seconds']>3600:raise ValueError('completed one-hour credit cannot cover longer training work')
        if any(row['kind']=='groom' or row['kind']=='credit' and row['publication']=='grooming' for row in value['rewards']):
            import pokemon_activities as A
            A._feature(e,owner,'groomer');A._tool(owner,'미용사 킷',"Groomer's Kit")
        claims=[];prepared={}
        for node in value['rewards']:
            Q._selected(e,node['source']);kind=node['kind']
            if kind in ('regime','teach') and set(node['choices'])!={t.entity_id for t in participants}:raise ValueError('reward choices must match actual participants')
            if kind=='xp':
                awards=[amount(t.level,eligibility['xp_rank'],node['formula']) for t in participants]
                for target,award in zip(participants,awards):
                    if not target.spec.get('species'):raise ValueError('actual species required for native XP progression')
                    D.gain_exp(e.r,__import__('world_entities').spec_copy(target),award)
                prepared[node['id']]={'awards':awards,'levels':[t.level for t in participants],
                    'baby':[FOOD.baby_training_plan(e,t,a) for t,a in zip(participants,awards)]}
                if type_manual is not None:
                    if type(type_manual) is not dict or set(type_manual)!={'instance_id','target_id'}:
                        raise ValueError('Type Study Manual requires one actual manual and one training participant')
                    matched=[t for t in participants if t.entity_id==type_manual['target_id']]
                    if len(matched)!=1:raise ValueError('Type Study Manual must select one actual training participant')
                    target=matched[0];position=list(participants).index(target)
                    import csv_item_physical_contracts as CSV_ITEMS,contest_features as FEATURES
                    extra=CSV_ITEMS.manual_training_level(e,owner,target,type_manual['instance_id'],
                        baby_food=prepared[node['id']]['baby'][position],champion_trainer=FEATURES.owned(owner,'feat/챔피언-트레이너'))
                    prepared[node['id']]['manual_target']=target.entity_id if extra else None
                    if extra:
                        probe=__import__('world_entities').spec_copy(target);D.gain_exp(e.r,probe,awards[position])
                        D.gain_exp(e.r,probe,max(0,D.exp_for_level(e.r,probe['level']+1)-probe['exp']),source_kind='level_grant')
            elif kind=='regime':prepared[node['id']]=F._targets(e,owner,[(t,node['choices'][t.entity_id]) for t in participants])
            if shared and kind in ('xp','regime','bonus'):
                claims+=_credit_facts(e,owner,participants,'experience_training' if kind=='xp' else 'training_regime',from_training=from_training)
            if kind=='teach' and not shared and (credit_node is None or credit_node['publication'] is None):
                raise ValueError('teaching reward requires an actual completed native training credit')
        pushed=RF.prepare_training(e,owner,participants,pushed_skills)
        identity=request_id if request_id is not None else 'auto:'+str(len(store)+1)
        record_id=owner.entity_id+':training-reward:'+identity
        if identity in store:raise ValueError('training reward identity already used')
        started=e.elapsed_seconds
        job=None
        if not shared:
            job=J.run_fixed(e,owner,participants,seconds=value['seconds'],source=value['source'],context={'safe':True,'reason':reason},
                           job_id='training-rewards:'+record_id,credit=None if credit_node is None else credit_node['policy'])
        credit_result=None
        if credit_node is not None:
            if credit_node['publication']=='ordinary':
                import training_sessions as S
                credit_result=S.publish(e,owner,participants,job,request_id=_session_id or record_id,reason=reason,
                                       eligibility=eligibility,started_at=started,reward_record_id=record_id)
            elif credit_node['publication']=='grooming':
                for target in participants:
                    target.spec['training_credit']={'trainer_id':owner.entity_id,'day':eligibility['day'],'hours':1,'safe':True,
                        'source':credit_node['source'],'completed_at':e.elapsed_seconds,'job_id':job['job_id'],
                        'credit_id':job['credit_ids'][target.entity_id],'reward_record_id':record_id}
            credit_result=credit_result or {'job_id':job['job_id'],'credit_ids':deepcopy(job['credit_ids'])}
        artifacts=[]
        for node in value['rewards']:
            kind=node['kind'];outputs=[]
            if kind=='xp':
                prepared_xp=prepared[node['id']];day=eligibility['day'];prior=owner.spec.get('experience_training',{})
                old_ids=list(prior.get('target_ids',[])) if prior.get('day')==day else []
                for target,award,level,baby in zip(participants,prepared_xp['awards'],prepared_xp['levels'],prepared_xp['baby']):
                    before=target.spec['exp'];D.gain_exp_combatant(e,target,award);FOOD.finish_baby_training(e,target,baby)
                    manual_reward=prepared_xp.get('manual_target')==target.entity_id
                    if manual_reward:D.gain_exp_combatant(e,target,'to next level')
                    target.spec['experience_training_day']=day
                    row={'source':node['source'],'trainer_id':owner.entity_id,'day':day,'base_award':award,'skill':eligibility.get('skill',value['eligibility']['capacity']['skill']),
                         'rank':eligibility.get('rank',eligibility['capacity_rank']),'xp_rank':eligibility['xp_rank'],'grooming_policy':eligibility.get('grooming_policy'),
                         'beast_policy':eligibility.get('beast_policy'),'daily_target_limit':eligibility['target_limit'],'rank_plans':deepcopy(eligibility['rank_plans']),
                         'completed_at':e.elapsed_seconds,'eligibility':deepcopy(eligibility),'reward_record_id':record_id,'reward_id':node['id']}
                    if manual_reward:row['extra_level_source']={'source':'C2CSV/inventory:70:1','instance_id':type_manual['instance_id']}
                    target.spec.setdefault('experience_training_history',[]).append(row)
                    outputs.append({'target_id':target.entity_id,'level':level,'base_award':award,'exp_before':before,'exp_after':target.spec['exp'],'history':deepcopy(row)})
                owner.spec['experience_training']={'day':day,'count':eligibility['daily_used']+len(participants),
                    'target_ids':old_ids+[t.entity_id for t in participants],'source':node['source']}
            elif kind=='regime':outputs=grant_regimes(e,owner,participants,prepared[node['id']],request_id=record_id,started_at=started)
            elif kind=='bonus':outputs=grant_bonus(e,owner,participants,node,record_id=record_id,started_at=started)
            elif kind=='groom':
                for target in participants:
                    row={'day':eligibility['day'],'trainer_id':owner.entity_id,'source':node['source'],'intro_dice':node['intro_dice'],'completed_at':e.elapsed_seconds,'reward_record_id':record_id}
                    target.spec['grooming']=row;outputs.append(dict(target_id=target.entity_id,**deepcopy(row)))
            elif kind=='credit':outputs=[{'target_id':t.entity_id,'credit_id':job['credit_ids'][t.entity_id]} for t in participants]
            elif kind=='teach':
                for target in participants:
                    ordinary=from_training or credit_node is not None and credit_node['publication']=='ordinary'
                    import training_sessions as S
                    credit_id=target.spec[S.KEY if ordinary else 'training_credit']['credit_id']
                    actual_credit=target.custom_conditions[J.CREDITS][credit_id];before_claims=list(actual_credit['claims'])
                    result=T.teach_edge(e,owner,target=target,edge=node['edge'],from_training=ordinary,from_grooming=not ordinary,**node['choices'][target.entity_id])
                    if isinstance(result,C.PendingDecision):raise ValueError('unresolved teaching cannot commit a partial reward batch')
                    paid=[app for app in actual_credit['claims'] if app not in before_claims]
                    if len(paid)!=1:raise ValueError('native teaching must consume its actual work application once')
                    claims.append({'target_id':target.entity_id,'credit_id':credit_id,'application':paid[0]})
                    outputs.append({'target_id':target.entity_id,'result':deepcopy(result)})
            if kind in ('xp','regime','bonus') and (shared or credit_node is not None and credit_node['publication'] in ('ordinary','grooming')):
                ordinary=from_training or not shared and credit_node['publication']=='ordinary'
                application='experience_training' if kind=='xp' else 'training_regime'
                if not shared:claims+=_credit_facts(e,owner,participants,application,from_training=ordinary)
                for target in participants:T.consume_credit(target,application,**({'from_training':True} if ordinary else {}))
            artifacts.append({'id':node['id'],'source':node['source'],'kind':kind,'outputs':outputs,'result':deepcopy(credit_result) if kind=='credit' else None})
        RF.finish_training(e,owner,pushed,_pushed_source or value['source'])
        result={'activity':'training_rewards','reward_record_id':record_id,'trainer_id':owner.entity_id,'target_ids':[t.entity_id for t in participants],
                'started_at':started,'completed_at':e.elapsed_seconds,'eligibility':deepcopy(eligibility),'awards':artifacts}
        record={'id':record_id,'request':deepcopy(request),'intent':TX.request_fingerprint(request),'result':deepcopy(result),'result_sha256':TX.request_fingerprint(result),
                'job_id':None if job is None else job['job_id'],'claims':claims}
        owner.spec.setdefault(KEY,{})[identity]=record
        validate_world(e,W.actor_index(e))
        return result
    return G.transition(engine,trainer,apply,participants=targets)


def validate_world(engine,actors=None):
    import activity_jobs as J
    import training_features as F
    actors=W.actor_index(engine) if actors is None else actors
    for owner in actors.values():
        F.validate_trained(owner,actors)
        store=owner.spec.get(KEY,{})
        if type(store) is not dict:raise ValueError('actual training reward records required')
        for identity,record in store.items():
            Q._text(identity)
            if type(record) is not dict or record.get('intent')!=TX.request_fingerprint(record.get('request')):raise ValueError('training reward intent changed')
            request=record['request'];value=declaration(request['declaration']);result=record.get('result',{})
            if record.get('result_sha256')!=TX.request_fingerprint(result):raise ValueError('completed training reward receipt changed')
            Q._selected(engine,value['source'])
            for node in value['rewards']:Q._selected(engine,node['source'])
            expected_id=owner.entity_id+':training-reward:'+identity
            if record.get('id')!=expected_id or result.get('reward_record_id')!=expected_id or request.get('trainer_id')!=owner.entity_id or result.get('trainer_id')!=owner.entity_id:
                raise ValueError('training reward provider identity changed')
            ids=request.get('target_ids')
            if type(ids) is not list or not ids or len(set(ids))!=len(ids) or any(uid not in actors for uid in ids) or result.get('target_ids')!=ids:
                raise ValueError('training reward actual participant evidence changed')
            start=C.integer(result.get('started_at'),'training reward start',0);end=C.integer(result.get('completed_at'),'training reward completion',start,engine.elapsed_seconds)
            eligibility=result.get('eligibility',{})
            if eligibility.get('declaration')!=value['eligibility'] or eligibility.get('trainer_id')!=owner.entity_id or eligibility.get('target_ids')!=ids:raise ValueError('training reward admission evidence changed')
            if record.get('job_id') is not None:
                job=J._row(engine,record['job_id'])
                credit_node=next((row for row in value['rewards'] if row['kind']=='credit'),None)
                if job['status']!='complete' or job['source']!=value['source'] or job['owner'] is not owner or [p.entity_id for p in job['participants']]!=ids or job['progress_seconds']!=value['seconds'] or end-start!=value['seconds'] or job['definition']['credit']!=(None if credit_node is None else credit_node['policy']):
                    raise ValueError('training reward lost its completed actual work')
            elif end!=start:raise ValueError('shared completed work cannot invent more elapsed time')
            rows=result.get('awards')
            if type(rows) is not list or len(rows)!=len(value['rewards']):raise ValueError('complete training reward distribution required')
            for node,award in zip(value['rewards'],rows):
                if any(award.get(key)!=node[key] for key in ('id','source','kind')):raise ValueError('training reward source or definition changed')
                outputs=award.get('outputs')
                expected_ids=[uid for uid in ids for choice in node['choices'][uid]] if node['kind']=='regime' else ids
                if type(outputs) is not list or any(type(row) is not dict for row in outputs) or [row.get('target_id',row.get('pokemon_id')) for row in outputs]!=expected_ids:raise ValueError('training rewards must pay every actual participant once')
                if node['kind']=='regime' and [row.get('rule_id') for row in outputs]!=[choice for uid in ids for choice in node['choices'][uid]]:
                    raise ValueError('actual awarded regimes changed')
                if node['kind']=='credit':
                    for uid,row in zip(ids,outputs):
                        if record.get('job_id') is None or row.get('credit_id')!=job['credits'][uid]['id']:raise ValueError('training credit lost its actual completed job')
                if node['kind']=='xp':
                    for uid,row in zip(ids,outputs):
                        C.integer(row.get('exp_before'),'reward XP before',0);C.integer(row.get('exp_after'),'reward XP after',row['exp_before'])
                        expected=amount(row.get('level'),eligibility.get('xp_rank'),node['formula'])
                        history=row.get('history')
                        if row.get('base_award')!=expected or type(history) is not dict or history.get('base_award')!=expected or history.get('reward_record_id')!=expected_id or history.get('reward_id')!=node['id'] or history not in actors[uid].spec.get('experience_training_history',[]):
                            raise ValueError('training XP formula or actual target receipt changed')
            for claim in record.get('claims',[]):
                target=actors.get(claim.get('target_id'));receipt=None if target is None else target.custom_conditions.get(J.CREDITS,{}).get(claim.get('credit_id'))
                if type(receipt) is not dict or receipt['owner_id']!=owner.entity_id or J._row(engine,receipt['job_id'])['credits'].get(target.entity_id) is not receipt or claim.get('application') not in receipt['claims']:
                    raise ValueError('training reward lost its actual consumed work credit')
            for uid in ids:
                import training_features as F,state_grants as G
                for projection in F.records(actors[uid]):
                    if projection.get('session')!=expected_id or 'training_reward_definition' not in projection:continue
                    definition=projection['training_reward_definition']
                    if definition not in value['rewards'] or not any(row.get('source')==projection.get(G.TAG) for award in rows for row in award['outputs']):
                        raise ValueError('training bonus projection changed its awarded declaration')
    return True
