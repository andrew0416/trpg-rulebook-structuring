"""Shared permanent move learning; native routes supply verified candidates.

This prepares and commits learning state only. The enclosing native transaction
owns qualification, payment, timing and source-owned independent grants.
"""
from copy import deepcopy


def learn_moves(rules,spec,*,candidates,selected,method,source,reason,provider=None,paid_tp=0,position='before_struggle',details=None,replaced=None):
    import move_state as M
    if rules._selected_rule(source)!=source:raise ValueError('selected learning source required')
    if not isinstance(method,str) or not method.strip() or not isinstance(reason,str) or not reason.strip():
        raise ValueError('explicit learning method and reason required')
    if provider is not None and (not isinstance(provider,str) or not provider.strip()):raise ValueError('actual provider identity required')
    if type(paid_tp)is not int or paid_tp<0:raise ValueError('actual nonnegative learning cost required')
    if position not in ('before_struggle','front'):raise ValueError('explicit learning insertion policy required')
    def canonical(values):
        if type(values)is not list:raise ValueError('explicit learning list required')
        ids=[rules.move_id(v) for v in values]
        if any(mid is None or mid in rules.excluded_moves for mid in ids) or len(set(ids))!=len(ids):
            raise ValueError('distinct available learning identities required')
        return ids
    if details is None:details={}
    if type(details)is not dict or set(details)&{'method','source','paid_tp','teacher_id','learned_at_level','species_id','reason','lifetime','candidates','learning_contract','move_id','replaced'}:
        raise ValueError('route details cannot overwrite shared learning provenance')
    pool=canonical(candidates)
    if selected is None:return {'status':'pending','candidates':pool,'source':source,'method':method}
    choices=canonical(selected)
    if any(mid not in pool for mid in choices):raise ValueError('selected move outside actual learning candidates')
    known=M.known(rules,spec)
    if any(mid in known for mid in choices):raise ValueError('move already permanently learned')
    candidate=deepcopy(spec);records=[]
    for mid in choices:
        record={'method':method,'source':source,'paid_tp':paid_tp,'teacher_id':provider,
                'learned_at_level':spec['level'],'species_id':spec.get('species'),
                'reason':reason,'lifetime':'permanent','candidates':list(pool),'learning_contract':1,**deepcopy(details)}
        moves=candidate['moves']
        at=0 if position=='front' else moves.index('struggle') if 'struggle' in moves else len(moves)
        moves.insert(at,mid)
        candidate.setdefault('move_learning',{})[mid]=deepcopy(record)
        receipt={'move_id':mid,'replaced':replaced,**record}
        candidate.setdefault('move_learning_log',[]).append(deepcopy(receipt));records.append(receipt)
    M.validate_spec(rules,candidate)
    for field in ('moves','move_learning','move_learning_log'):
        if field in candidate:spec[field]=candidate[field]
    return {'status':'applied','records':deepcopy(records)}


def validate(rules,spec):
    """Validate new common receipts without inventing old acquisition evidence."""
    def record(mid,row):
        if type(row.get('learning_contract'))is not int or row['learning_contract']!=1:raise ValueError('unsupported learning contract')
        if rules.move_id(mid)!=mid:raise ValueError('canonical learned identity required')
        pool=row.get('candidates')
        if type(pool)is not list or any(type(x)is not str or rules.move_id(x)!=x for x in pool) or len(set(pool))!=len(pool) or mid not in pool:
            raise ValueError('learning candidate evidence mismatch')
        if rules._selected_rule(row.get('source'))!=row.get('source'):raise ValueError('selected learning source required')
        for key in ('method','reason'):
            if type(row.get(key))is not str or not row[key].strip():raise ValueError('learning route provenance required')
        if type(row.get('paid_tp'))is not int or row['paid_tp']<0 or row.get('lifetime')!='permanent':raise ValueError('learning cost or lifetime mismatch')
        level=row.get('learned_at_level')
        if type(level)is not int or not 1<=level<=100:raise ValueError('actual historical learning level required')
        provider=row.get('teacher_id')
        if provider is not None and (type(provider)is not str or not provider.strip()):raise ValueError('learning provider identity required')
        if row['method'] in ('level_up','evolution'):
            if row['paid_tp']!=0 or row['source']!='pokemon/level-up':raise ValueError('natural learning provenance mismatch')
        if row['method']=='hm':
            import pokemon_teaching as T
            if row['source']==T.MACHINES:T.validate_hm_record(rules,spec,row)
    log=spec.get('move_learning_log',[])
    for row in log:
        if isinstance(row,dict) and 'learning_contract' in row:record(row.get('move_id'),row)
    for mid,row in spec.get('move_learning',{}).items():
        if isinstance(row,dict) and 'learning_contract' in row:
            record(mid,row)
            if not any(isinstance(x,dict) and x.get('move_id')==mid and {k:v for k,v in x.items() if k not in ('move_id','replaced','natural')}=={k:v for k,v in row.items() if k!='natural'} for x in log):
                raise ValueError('learning receipt missing from history')
