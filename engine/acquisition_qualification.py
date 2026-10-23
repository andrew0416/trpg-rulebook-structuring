"""Shared, read-only acquisition constraints; qualification never grants ownership.
Native callers supply observed facts. Authored callers retain source/input evidence.
"""
from copy import deepcopy
KINDS={'prerequisite','repeat','rank','selection','capacity','stage'}

def text(value):
    if type(value) is not str or not value.strip():raise ValueError('qualification identity required')
    return value

def evaluate(*,source_id,provider,stage,checks,waivers=()):
    for value in (source_id,provider,stage):text(value)
    if type(checks) is not list or not checks:raise ValueError('nonempty qualification checks required')
    indexed={}
    for check in checks:
        if type(check) is not dict or set(check) not in ({'id','kind','passed','reason'},{'id','kind','test','reason'}):raise ValueError('exact qualification check fields required')
        if 'test' in check:check=dict(check,passed=predicate(check['test']))
        key=text(check['id']);text(check['reason'])
        if key in indexed:raise ValueError('duplicate qualification check identity')
        if type(check['kind']) is not str or check['kind'] not in KINDS:raise ValueError('unknown qualification constraint kind')
        if check['passed'] is not None and type(check['passed']) is not bool:raise ValueError('qualification fact must be boolean or unresolved')
        indexed[key]=check
    if not isinstance(waivers,(list,tuple)):raise ValueError('waivers must be records')
    allowed={}
    for waiver in waivers:
        if type(waiver) is not dict or set(waiver)!={'source_id','provider','stage','checks','reason'}:raise ValueError('exact scoped waiver fields required')
        for key in ('source_id','provider','stage','reason'):text(waiver[key])
        names=waiver['checks']
        if type(names) is not list or not names or any(type(k) is not str for k in names) or len(set(names))!=len(names):raise ValueError('distinct waived check identities required')
        if any(k not in indexed or indexed[k]['kind']!='prerequisite' for k in names):raise ValueError('waiver may only name existing prerequisites')
        if (waiver['source_id'],waiver['provider'],waiver['stage'])==(source_id,provider,stage):
            for key in names:
                if key in allowed:raise ValueError('duplicate waiver for prerequisite')
                allowed[key]=waiver['reason']
    rows=[]
    for key,check in indexed.items():
        state='passed' if check['passed'] is True else 'waived' if key in allowed else 'pending' if check['passed'] is None else 'denied'
        row=dict(deepcopy(check),state=state)
        if state=='waived':row['waiver_reason']=allowed[key]
        rows.append(row)
    status='denied' if any(x['state']=='denied' for x in rows) else 'pending' if any(x['state']=='pending' for x in rows) else 'qualified'
    return {'schema':1,'source_id':source_id,'provider':provider,'stage':stage,'status':status,'checks':rows,'acquired':False}

def require(source_id,provider,stage,checks):
    result=evaluate(source_id=source_id,provider=provider,stage=stage,checks=checks)
    if result['status']!='qualified':
        raise ValueError(next(row['reason'] for row in result['checks'] if row['state'] in ('denied','pending')))
    return result

def check(identity,kind,passed,reason):
    return {'id':identity,'kind':kind,'passed':passed,'reason':reason}

def owned_skill_edge(actor,source_id,document,*,prerequisite_reason):
    """Qualify one native acquired skill Edge; never infer or grant ownership."""
    import acquired_features as A,skill_modifiers as S
    require(source_id,'native','owned',[
        check('trainer','prerequisite',actor.kind==document['owner_kind'],
              source_id+' requires an actual '+document['owner_kind']),
        rank_limit('copies',A.owned_rule_count(actor,source_id),1,document['maximum_copies'],
                   source_id+' requires one actual acquired Edge'),
        check('skill','prerequisite',S.rank(actor.r,actor,document['skill'])[2]>=document['minimum_rank'],
              prerequisite_reason)])
    return True

def policy(engine,actor,target,document,*,context=None,decisions=None):
    import source_policy as P,source_policy_state as S,world_entities as W
    W.require_actors(engine,actor,target)
    prepared=P.resolve(engine.r,document,context=context,decisions=decisions,
        _state_reader=lambda specs:S.read(engine,actor,target,specs))
    if prepared['status']!='PolicyValuesReady':return prepared
    values=prepared['values']
    if set(values)!={'qualification'} or type(values['qualification']) is not dict:raise ValueError('exact qualification declaration required')
    result=declaration_result(prepared['selected_id'],values['qualification'])
    return dict(prepared,status='PolicyQualificationEvaluated',qualification=result,effects_executed=False)


def declaration_result(source_id,declaration):
    if type(declaration) is not dict:raise ValueError('qualification declaration required')
    if set(declaration) not in ({'provider','stage','checks','waivers'},{'provider','stage','checks','waivers','rank_request'}):raise ValueError('exact qualification fields required')
    declaration=deepcopy(declaration)
    if 'rank_request' in declaration:
        request=declaration.pop('rank_request')
        if type(request) is not dict or set(request)!={'selection','requested_rank','policies'}:raise ValueError('exact rank request required')
        declaration['checks']=declaration['checks']+stage_checks(stage=declaration['stage'],**request)
    return evaluate(source_id=source_id,**declaration)


def predicate(node):
    """Strict JSON comparisons with unknown propagation; never execute code."""
    if node is None or type(node) is bool:return node
    if type(node) is not dict or type(node.get('op')) is not str:raise ValueError('typed qualification predicate required')
    op=node['op']
    if op in ('all','any'):
        if set(node)!={'op','terms'} or type(node['terms']) is not list or not node['terms']:raise ValueError('nonempty predicate terms required')
        values=[predicate(term) for term in node['terms']]
        if op=='all':return False if False in values else None if None in values else True
        return True if True in values else None if None in values else False
    if op=='not':
        if set(node)!={'op','term'}:raise ValueError('exact negation fields required')
        value=predicate(node['term']);return None if value is None else not value
    if set(node)!={'op','left','right'} or op not in ('eq','ne','lt','le','gt','ge','in','not_in'):raise ValueError('known comparison and exact operands required')
    left,right=node['left'],node['right']
    if left is None or right is None:return None
    if op in ('lt','le','gt','ge'):
        if type(left) is not int or type(right) is not int:raise ValueError('ordered qualification operands must be whole numbers')
        return {'lt':left<right,'le':left<=right,'gt':left>right,'ge':left>=right}[op]
    if op in ('in','not_in'):
        if type(right) is not list:raise ValueError('selection domain must be a list')
        found=any(type(left) is type(value) and left==value for value in right)
        return found if op=='in' else not found
    equal=type(left) is type(right) and left==right
    return equal if op=='eq' else not equal


def rank_limit(identity,current,minimum,maximum,reason):
    return {'id':identity,'kind':'rank','reason':reason,'test':{'op':'all','terms':[
        {'op':'ge','left':current,'right':minimum}, {'op':'le','left':current,'right':maximum}]}}


def stage_checks(*,stage,selection,requested_rank,policies):
    """Selected source supplies each stage's cap and locked selections explicitly."""
    text(stage)
    if type(requested_rank) is not int or requested_rank<1:raise ValueError('positive requested rank required')
    text(selection)
    if type(policies) is not dict or stage not in policies:raise ValueError('explicit policy for acquisition stage required')
    for name,row in policies.items():
        text(name)
        if type(row) is not dict or set(row)!={'max_rank','blocked_selections'}:raise ValueError('exact stage policy required')
        if type(row['max_rank']) is not int or row['max_rank']<1:raise ValueError('positive stage rank cap required')
        if type(row['blocked_selections']) is not list or any(type(x) is not str or not x for x in row['blocked_selections']):raise ValueError('explicit blocked selections required')
    row=policies[stage]
    return [rank_limit('stage_rank',requested_rank,1,row['max_rank'],'requested rank exceeds stage cap'),
        {'id':'stage_selection','kind':'stage','reason':'selection is locked in acquisition stage',
         'test':{'op':'not_in','left':selection,'right':deepcopy(row['blocked_selections'])}}]


def replacement(engine,actor,target,source_id,operation):
    """Resolve one provider-declared duplicate replacement before payment.
    Ownership comes from the live grant projection; caller-supplied booleans
    cannot assert duplication. The original selected source defines candidates.
    """
    import state_grants as G
    request=operation['replacement']
    if type(request) is not dict or set(request)!={'provider','stage','child_id','original','choice','candidates'}:
        raise ValueError('exact replacement declaration required')
    for key in ('provider','stage','child_id','original','choice'):text(request[key])
    if request['provider']!=actor.entity_id:raise ValueError('replacement provider must be actual granting actor')
    grants=deepcopy(operation['grants'])
    matches=[row for row in grants if row['source_id']==request['child_id']]
    if len(matches)!=1 or matches[0]['field'] not in G.LIST_FIELDS:raise ValueError('replacement requires one source-owned list grant')
    grant=matches[0]
    if grant['value']!=request['original']:raise ValueError('replacement original disagrees with grant')
    candidates=request['candidates']
    if type(candidates) is not dict or not candidates:raise ValueError('explicit replacement candidate domain required')
    for value,checks in candidates.items():
        text(value)
        evaluate(source_id=source_id,provider=request['provider'],stage=request['stage'],checks=checks)
    owned=G.effective(target,grant['field'])
    duplicate=request['original'] in owned
    choice=request['choice']
    if not duplicate and choice!=request['original']:raise ValueError('replacement requires actual duplicate ownership')
    if duplicate and choice==request['original']:raise ValueError('duplicate grant requires a different candidate')
    if choice not in candidates:raise ValueError('replacement choice outside provider domain')
    if duplicate and choice in owned:raise ValueError('replacement candidate already owned')
    result=evaluate(source_id=source_id,provider=request['provider'],stage=request['stage'],checks=candidates[choice])
    result.update(original=request['original'],choice=choice,duplicate=duplicate,child_id=request['child_id'])
    if result['status']=='qualified':grant['value']=choice
    return grants,result
