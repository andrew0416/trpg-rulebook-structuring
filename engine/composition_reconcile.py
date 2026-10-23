"""Source-owned retention predicates checked inside native graph transactions."""
from copy import deepcopy

class ReconciliationPending(ValueError): pass

def evaluate(engine,actor,row,contract,*,cache=None,source_id=None):
    import source_policy as P,source_policy_state as S
    import acquisition_qualification as Q
    prepared=P.resolve(engine.r,contract['document'],
        _state_reader=lambda specs:S.read(engine,actor,actor,specs))
    if prepared['selected_id']!=row.get('rule_id'):raise ValueError('retention policy must select actual grant rule')
    if prepared['status']=='PolicyNotApplicable':return False
    if prepared['status']!='PolicyValuesReady':raise ReconciliationPending('retention inputs unresolved')
    values=prepared['values']
    if set(values)!={'retained'}:raise ValueError('exact retained predicate required')
    # Resolve above always revalidates source freshness and reads actual inputs.
    import root_resolution as R
    cache_key=(actor.entity_id,source_id)
    signature=R.fingerprint(prepared)
    if cache is not None and cache.get(cache_key,(None,))[0]==signature:return cache[cache_key][1]
    retained=Q.predicate(values['retained'])
    if retained is None:raise ReconciliationPending('retention predicate unresolved')
    if cache is not None:cache[cache_key]=(signature,retained)
    return retained

def bind(engine,actor,source_id,document,*,cause):
    import acquisition_withdrawal as W
    _,row=W._source(engine,actor,source_id)
    if cause not in W.CAUSES:raise ValueError('known loss cause required')
    contract={'document':deepcopy(document),'cause':cause}
    if row.get('reconciliation') is not None and row['reconciliation']!=contract:raise ValueError('recorded retention policy cannot be replaced')
    W.policy({'cause':cause,'policies':row.get('withdrawal_policies',{})})
    if not evaluate(engine,actor,row,contract):raise ValueError('new retention contract must currently hold')
    row['reconciliation']=contract
    return deepcopy(contract)

def reconcile(engine,actor,*,cache=None):
    """Called only on staged actors: all removals and parent mutation commit together."""
    import state_grants as G,grant_payments as PAY,acquisition_withdrawal as W
    removed=[]
    while True:
        sources=actor.spec.get(G.KEY,{}).get('sources',{})
        doomed=[];partitions={'actual':[],'none':[]}
        for key,row in list(sources.items()):
            contract=row.get('reconciliation')
            if contract is None or evaluate(engine,actor,row,contract,cache=cache,source_id=key):continue
            decision=W.policy({'cause':contract['cause'],'policies':row.get('withdrawal_policies',{})})
            if decision['status']!='allowed':raise ReconciliationPending('loss policy '+decision['status']+': '+key)
            if decision['refund_mode']=='actual' and not row.get('payment_id'):
                raise ReconciliationPending('actual refund requires recorded payment: '+key)
            doomed.append(key);partitions[decision['refund_mode']].append(key)
        if not doomed:return {'removed':removed}
        plans=[]
        try:
            for mode,keys in partitions.items():
                if keys:plans.extend(PAY.quote(actor,keys,refund_mode=mode))
            G.preflight_revoke(actor,doomed)
        except ValueError as exc:raise ReconciliationPending(str(exc)) from exc
        PAY.settle_sources(engine,actor,doomed,plans,'source retention condition lost')
        removed.extend(doomed)
