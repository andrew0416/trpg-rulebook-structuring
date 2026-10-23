"""Resource-owner recovery originals; a repeated parent never restores later costs."""
from copy import deepcopy
import resolution_transaction as REQUESTS

KEY='resource_recovery_receipts'


def validate(actor):
    rows=actor.spec.get(KEY,{})
    if type(rows) is not dict:raise ValueError('resource recovery originals required')
    for identity,row in rows.items():
        if type(row) is not dict or row.get('owner_id')!=actor.entity_id or row.get('id')!=identity:
            raise ValueError('actual recovery owner required')
        intent=row.get('intent')
        if type(intent) is not dict or intent.get('owner_id')!=actor.entity_id:
            raise ValueError('recovery intent owner mismatch')
        if row.get('intent_fingerprint')!=REQUESTS.request_fingerprint(intent):
            raise ValueError('recovery intent changed')
        if type(row.get('eligibility')) is not dict or type(row['eligibility'].get('eligible')) is not bool:
            raise ValueError('observed recovery eligibility required')
        if type(row.get('applied')) is not bool or row['applied']!=(row.get('before')!=row.get('after')):
            raise ValueError('recovery result differs from actual before/after')
        if not row['eligibility']['eligible'] and row['applied']:
            raise ValueError('ineligible recovery cannot alter its resource')
    return rows


def execute(actor, *, resource, source, request_id, policy, read, qualify, commit):
    """Called inside the native owner's admitted transition, with native callbacks.

    The identity excludes mutable balances and eligibility; completed replay is
    resolved before reading them. Initial balances are observations, not a claim
    that pre-import usage never occurred.
    """
    rows=validate(actor)
    for value in (resource,source):
        if type(value) is not str or not value:raise ValueError('recovery resource/source required')
    if request_id is None:request_id=actor.entity_id+':recovery:'+str(len(rows)+1)
    if type(request_id) is not str or not request_id:raise ValueError('recovery parent request required')
    intent={'owner_id':actor.entity_id,'resource':resource,'source':source,
            'parent_request':request_id,'policy':deepcopy(policy)}
    identity=REQUESTS.request_fingerprint([request_id,resource,source])
    prior=REQUESTS.replay_result(rows,identity,intent)
    if prior is not None:return prior
    before=deepcopy(read())
    eligibility=deepcopy(qualify())
    if type(eligibility) is not dict or type(eligibility.get('eligible')) is not bool or not eligibility.get('reason'):
        raise ValueError('native recovery qualification and reason required')
    if eligibility['eligible']:commit()
    after=deepcopy(read())
    row={'id':identity,'owner_id':actor.entity_id,'intent':intent,
         'intent_fingerprint':REQUESTS.request_fingerprint(intent),
         'eligibility':eligibility,'before':before,'after':after,
         'initial_basis':'observed_native_balance','applied':before!=after}
    actor.spec.setdefault(KEY,{})[identity]=row
    return deepcopy(row)
