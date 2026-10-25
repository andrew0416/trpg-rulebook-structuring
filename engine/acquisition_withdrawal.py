"""Native grant dependency and irreversible-use guards shared by withdrawals."""
from copy import deepcopy

def _source(engine,actor,source_id):
    import world_entities as W
    W.require_actors(engine,actor,actor)
    rows=actor.spec.get('state_grants',{}).get('sources',{})
    if type(source_id) is not str or source_id not in rows:raise ValueError('actual active grant source required')
    return rows,rows[source_id]

def dependencies(engine,actor,source_id,depends_on):
    """Host-adjudicated dependencies attach to a real source, never a display name."""
    rows,row=_source(engine,actor,source_id)
    if type(depends_on) is not list or any(type(key) is not str or key not in rows or key==source_id for key in depends_on) or len(set(depends_on))!=len(depends_on):
        raise ValueError('distinct actual dependency sources required')
    declared=sorted(depends_on)
    if 'withdrawal_dependencies' in row and row['withdrawal_dependencies']!=declared:
        raise ValueError('recorded withdrawal dependencies cannot be replaced')
    pending=list(declared);seen=set()
    while pending:
        key=pending.pop()
        if key==source_id:raise ValueError('cyclic grant dependency')
        if key in seen:continue
        seen.add(key);pending.extend(rows[key].get('withdrawal_dependencies',[]))
    row['withdrawal_dependencies']=declared
    return deepcopy(declared)

def irreversible(engine,actor,source_id,*,event_id,reason):
    """Native consumer reports completed irreversible use; no inference from ownership."""
    _,row=_source(engine,actor,source_id)
    if any(type(v) is not str or not v.strip() for v in (event_id,reason)):raise ValueError('actual use event identity and reason required')
    uses=row.setdefault('irreversible_uses',{})
    if event_id in uses and uses[event_id]!=reason:raise ValueError('irreversible use event changed')
    uses[event_id]=reason
    return {'source_id':source_id,'event_id':event_id,'reason':reason}

def preflight(actor,removed):
    rows=actor.spec.get('state_grants',{}).get('sources',{})
    removed=set(removed)
    __import__('hobbyist').preflight_revoke(actor,removed)
    for identity,row in rows.items():
        dependencies=row.get('withdrawal_dependencies',[])
        uses=row.get('irreversible_uses',{})
        if type(dependencies) is not list or any(type(x) is not str for x in dependencies) or type(uses) is not dict:
            raise ValueError('invalid withdrawal evidence')
        if identity not in removed and removed.intersection(dependencies):
            raise ValueError('retained grant depends on withdrawn source: '+identity)
        if identity in removed and uses:
            raise ValueError('grant has prior irreversible use: '+identity)


def refund_native_investments(spec, records, *, source, reason, lost_prerequisite):
    """Settle qualified native removals inside the caller's staged transition."""
    import state_fields as F
    records = list(records)
    if not records:
        return 0
    if any(not isinstance(value, str) or not value.strip() for value in (source, reason)):
        raise ValueError('actual native refund source and reason required')
    if not isinstance(lost_prerequisite, dict) or not lost_prerequisite:
        raise ValueError('actual lost prerequisite required')
    owned = spec.get('learned_poke_edges', [])
    if len({id(row) for row in records}) != len(records):
        raise ValueError('distinct actual native investments required')
    for row in records:
        if not any(row is actual for actual in owned) or row.get('status') != 'active':
            raise ValueError('actual active native investment required')
        F.integer(row.get('point_cost'), 'actual native investment payment', 0)
    F.integer(spec.get('tutor_points'), 'actual remaining Tutor Points for prerequisite refund', 0)
    if any('pusher' in row for row in records):import researcher_fields as RFS
    costs = [RFS.pusher_receipt(None,row) if 'pusher' in row else row['point_cost'] for row in records]
    refunded = sum(costs)
    for row in records:
        row.update(status='refunded', refund={
            'source': source, 'points': row['point_cost'], 'reason': reason,
            'lost_prerequisite': deepcopy(lost_prerequisite)})
        if 'pusher' in row:row['refund']['net_points']=0
    spec['tutor_points'] += refunded
    return refunded


CAUSES={'retraining','prerequisite_loss','provider_loss','expiry'}

def policy(declaration):
    if type(declaration) is not dict or set(declaration)!={'cause','policies'}:raise ValueError('exact withdrawal policy declaration required')
    cause=declaration['cause'];policies=declaration['policies']
    if type(cause) is not str or cause not in CAUSES or type(policies) is not dict or cause not in policies:
        raise ValueError('explicit policy for actual withdrawal cause required')
    for name,row in policies.items():
        if name not in CAUSES or type(row) is not dict or set(row)!={'allowed','refund_mode'}:raise ValueError('known cause and exact policy fields required')
        if row['allowed'] is not None and type(row['allowed']) is not bool:raise ValueError('withdrawal permission must be boolean or pending')
        if row['refund_mode'] not in ('actual','none'):raise ValueError('known actual or no-refund policy required')
    selected=policies[cause]
    return {'cause':cause,'status':'pending' if selected['allowed'] is None else 'allowed' if selected['allowed'] else 'denied',
            'refund_mode':selected['refund_mode']}


class WithdrawalPolicyPending(ValueError): pass

def retrain(engine, actor, rule_id, **decision):
    """C02-163 actual trainer selection removal uses the existing source guard."""
    import trainer_retraining as TRAINER
    return TRAINER.retrain(engine, actor, rule_id, **decision)

def bind_policy(engine,actor,source_id,policies):
    """Persist host-adjudicated cause policy on an actual grant source."""
    _,row=_source(engine,actor,source_id)
    if type(policies) is not dict or not policies:raise ValueError('nonempty withdrawal policies required')
    for cause in policies:policy({'cause':cause,'policies':policies})
    if 'withdrawal_policies' in row and row['withdrawal_policies']!=policies:
        previous=row['withdrawal_policies']
        if set(previous)!=set(policies) or any(
            previous[cause]['refund_mode']!=policies[cause]['refund_mode'] or
            (previous[cause]['allowed'] is not None and previous[cause]['allowed']!=policies[cause]['allowed'])
            for cause in previous):
            raise ValueError('recorded withdrawal policy cannot be replaced')
    row['withdrawal_policies']=deepcopy(policies)
    return deepcopy(policies)

def owner_loss_plan(actor,sources):
    """The owner-bound lifetime consumer supplies the actual loss cause."""
    import grant_payments as PAY
    selections={};partitions={'actual':[],'none':[]};legacy_refund=0
    for key,row in sources:
        mode='actual'
        if 'withdrawal_policies' in row:
            selected=policy({'cause':'provider_loss','policies':row['withdrawal_policies']})
            if selected['status']=='pending':raise WithdrawalPolicyPending('owner-bound withdrawal policy unresolved')
            if selected['status']!='allowed':raise ValueError('owner-bound withdrawal cause denied')
            mode=selected['refund_mode'];selections[key]=selected
        partitions[mode].append(key)
        if mode=='actual':legacy_refund+=row.get('tutor_points',0)
    plans=[]
    for mode,keys in partitions.items():
        if keys:plans.extend(PAY.quote(actor,keys,refund_mode=mode))
    return plans,legacy_refund+sum(row['amount'] for row in plans),selections


def policy_bindings(bindings,grants):
    """Validate declarations before package publication or payment mutation."""
    if type(bindings) is not dict or not bindings:raise ValueError('nonempty withdrawal policy bindings required')
    if type(grants) is not list or any(type(row) is not dict for row in grants):raise ValueError('declared grant rows required')
    children=[row.get('source_id') for row in grants]
    for key,policies in bindings.items():
        if type(key) is not str or key not in children:raise ValueError('withdrawal policy must name a declared grant source')
        if type(policies) is not dict or not policies:raise ValueError('nonempty withdrawal policies required')
        for cause in policies:policy({'cause':cause,'policies':policies})
