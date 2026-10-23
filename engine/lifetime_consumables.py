"""Data-defined lifetime quotas and native permanent-effect consumption.

Definitions select shared operations; the ledger follows the recipient's identity,
not its owner, day or item spelling. Import without evidence stays unknown.
"""
from copy import deepcopy
from pathlib import Path
import json
import common_checks as C

KEY='consumable_lifetime'
ITEMS=frozenset(('item/이상한사탕','item/이상한사탕-1'))


def definitions(rules):
    cached=getattr(rules,'_lifetime_consumable_policies',None)
    if cached is None:
        data=json.loads((Path(rules.root)/'data/lifetime-consumable-policy.json').read_text(encoding='utf-8'))
        if data.get('schema_version')!=1:raise ValueError('unsupported lifetime consumable definition')
        cached=data['rules'];rules._lifetime_consumable_policies=cached
    return cached


def definition(rules, uid):
    if uid not in ITEMS or rules._selected_rule(uid)!=uid:raise ValueError('selected lifetime consumable source required')
    matches=[(key,row) for key,row in definitions(rules).items() if uid in row['item_ids']]
    if len(matches)!=1:raise ValueError('one lifetime quota definition per selected item required')
    key,row=matches[0]
    C.integer(row['maximum'],'lifetime maximum',1)
    if row['scope']!='actor_lifetime' or row['target_kind']!='pokemon' or row['effect']!={'operation':'reach_next_level'} or row['action']!='standard':
        raise ValueError('lifetime consumable needs a supported native operation')
    return key,row


def fresh(rules,spec):
    spec.setdefault(KEY,{'version':1,'actor_id':spec['id'],'quotas':{
        key:{'origin':'fresh_creation','initial_count':0,'receipts':[]}
        for key,row in definitions(rules).items() if row['target_kind']==spec['kind']}})


def validate(actor):
    ledger=actor.spec.get(KEY)
    if KEY not in actor.spec:return True
    if not isinstance(ledger,dict) or type(ledger.get('version'))is not int or ledger['version']!=1 or ledger.get('actor_id')!=actor.entity_id:
        raise ValueError('lifetime consumption requires the actual recipient identity')
    quotas=ledger.get('quotas')
    if not isinstance(quotas,dict):raise ValueError('lifetime quota mapping required')
    policies=definitions(actor.r)
    for key,row in quotas.items():
        if key not in policies or not isinstance(row,dict):raise ValueError('unknown lifetime quota or invalid history')
        policy=policies[key]
        if actor.kind!=policy['target_kind']:raise ValueError('lifetime quota target kind mismatch')
        C.integer(row.get('initial_count'),'observed past consumption',0,policy['maximum'])
        if row.get('origin')=='fresh_creation':
            if row['initial_count']!=0:raise ValueError('fresh creation cannot invent past consumption')
        elif row.get('origin')=='observed_history':
            if not isinstance(row.get('reason'),str) or not row['reason'].strip():raise ValueError('historical consumption needs an observation reason')
            C.integer(row.get('observed_at'),'observation time',0)
        else:raise ValueError('lifetime consumption origin required')
        receipts=row.get('receipts')
        if not isinstance(receipts,list) or row['initial_count']+len(receipts)>policy['maximum']:raise ValueError('lifetime consumption exceeds source limit')
        last_at=row.get('observed_at',0)
        for n,receipt in enumerate(receipts,row['initial_count']+1):
            if not isinstance(receipt,dict):raise ValueError('lifetime consumption receipt required')
            uid=receipt.get('source')
            if definition(actor.r,uid)[0]!=key:raise ValueError('consumption source belongs to another quota')
            if receipt.get('actor_id')!=actor.entity_id or type(receipt.get('ordinal'))is not int or receipt['ordinal']!=n:raise ValueError('consumption identity or sequence mismatch')
            if not isinstance(receipt.get('user_id'),str) or not receipt['user_id'].strip():raise ValueError('actual consuming user identity required')
            C.integer(receipt.get('at'),'consumption time',last_at);last_at=receipt['at']
            before,after=receipt.get('before'),receipt.get('after')
            if not isinstance(before,dict) or not isinstance(after,dict):raise ValueError('growth input and result required')
            C.integer(before.get('level'),'previous level',1,99);C.integer(after.get('level'),'resulting level',2,100)
            C.integer(before.get('exp'),'previous XP',0);C.integer(after.get('exp'),'resulting XP',0)
            import downtime as D
            if D.level_for_exp(actor.r,before['exp'])!=before['level'] or after['level']!=before['level']+1 or after['exp']!=D.exp_for_level(actor.r,after['level']) or after['exp']<=before['exp']:
                raise ValueError('growth receipt disagrees with the next-level threshold')
            stock=receipt.get('item_stock')
            if not isinstance(stock,dict) or stock.get('item_id')!=uid or type(stock.get('count'))is not int or stock['count']!=1 or stock.get('kind') not in ('quantity','held_instance'):
                raise ValueError('actual one-unit consumption receipt required')
            if stock['kind']=='held_instance' and (not isinstance(stock.get('instance_id'),str) or not stock['instance_id']):raise ValueError('consumed physical identity required')
    return True


def observe(engine, actor, *, item, count, reason):
    key,policy=definition(engine.r,engine.r.item_effects(item)[1].get('id'))
    validate(actor)
    if actor.kind!=policy['target_kind']:raise ValueError('actual recipient kind required')
    C.integer(count,'observed lifetime consumption',0,policy['maximum'])
    if not isinstance(reason,str) or not reason.strip():raise ValueError('historical consumption observation reason required')
    if key in actor.spec.get(KEY,{}).get('quotas',{}):raise ValueError('known lifetime consumption cannot be reset by an observation')
    import state_grants as G
    def apply(e,c):
        ledger=c.spec.setdefault(KEY,{'version':1,'actor_id':c.entity_id,'quotas':{}})
        ledger['quotas'][key]={'origin':'observed_history','initial_count':count,'reason':reason,'observed_at':e.elapsed_seconds,'receipts':[]}
        validate(c);e.gm._rec('lifetime consumption',None,count,reason,c)
        return deepcopy(ledger['quotas'][key])
    return G.transition(engine,actor,apply)


def consume(engine,user,target,uid,*,free=False,held_selection=None):
    key,policy=definition(engine.r,uid)
    if target.kind!=policy['target_kind']:raise ValueError('lifetime consumable requires a Pokemon target')
    validate(target)
    row=target.spec.get(KEY,{}).get('quotas',{}).get(key)
    if row is None:return C.PendingDecision('Actual lifetime consumption history must be observed before this item can grant growth',basis={'actor_id':target.entity_id,'source':uid})
    if row['initial_count']+len(row['receipts'])>=policy['maximum']:
        return (0,0)
    effects,_=engine.r.item_effects(uid)
    if len(effects or [])!=1 or {k:v for k,v in effects[0].items() if k!='note'}!={'type':'exp_gain','value':'to next level','target':'target'}:
        raise ValueError('selected growth item requires its reviewed next-level effect')
    import downtime as D,item_stock as STOCK,state_grants as G
    C.integer(target.spec.get('exp'),'actual cumulative XP before consumption',0)
    if D.level_for_exp(engine.r,target.spec['exp'])!=target.level:raise ValueError('actual XP and level disagree; reconcile before growth')
    if target.level>=engine.r.mech('pokemon/experience-table')['max_level']:
        return C.PendingDecision('No next level exists in the selected source; this application grants no reviewed growth')
    if free and engine.encounter_active:raise ValueError('a waived growth-item cost requires actual action permission')
    if engine.encounter_active and (user.injuries>=5 and not __import__('taskmaster').ignores_acting_loss(user)) and not free:raise ValueError('growth item Standard needs reviewed heavy-injury composition')
    stock=STOCK.prepare(engine,user,uid,held_selection=held_selection,allow_empty=True)
    if stock is None:return (0,0)
    def apply(e,t,u):
        import turn as TURN
        if not TURN.spend(e,u,'free' if free else policy['action'],uid):return (0,0)
        before={'level':t.level,'exp':t.spec['exp']}
        paid=STOCK.debit(e,u,stock)
        # Deterministic growth is already inside this one admitted transaction.
        D._gain_exp_combatant(e,t,'to next level')
        current=t.spec[KEY]['quotas'][key]
        current['receipts'].append({'source':uid,'actor_id':t.entity_id,'user_id':u.entity_id,
            'ordinal':current['initial_count']+len(current['receipts'])+1,'at':e.elapsed_seconds,
            'before':before,'after':{'level':t.level,'exp':t.spec['exp']},'item_stock':paid})
        import consumption_execution as EXECUTION
        EXECUTION.finish(u,paid,target_id=t.entity_id,outcome='applied',
                         results=[{'kind':'lifetime_consumable','id':t.entity_id+':'+key+':'+str(current['receipts'][-1]['ordinal'])}])
        validate(t)
        e.log(f'    {t.name}: lifetime growth use {current["initial_count"]+len(current["receipts"])}/{policy["maximum"]}',uid)
        return (1,0)
    return G.transition(engine,target,apply,participants=(user,))
