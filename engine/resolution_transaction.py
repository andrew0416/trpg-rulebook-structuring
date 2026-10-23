"""Shared in-memory state graph commit for native rule resolution.

Only staged subjects and RNG commit; external I/O is outside this contract.
Surviving mutable containers, subject aliases and returned subject references
retain their original identity. Invalid resolution raises before commit.
"""
from copy import deepcopy


def commit_graph(payload, anchors, replacements=()):
    """Allocate the complete result before applying anchored container changes.

    Anchors map staged identities to the original native objects/containers.
    Callers finish validation and callbacks before entering this commit phase.
    """
    anchors=dict(anchors)
    pending={}
    def visit(value):
        if not isinstance(value,(dict,list,set,tuple)) or id(value) in pending:return
        pending[id(value)]=value
        if isinstance(value,dict):
            for key,child in value.items():visit(key);visit(child)
        else:
            for child in value:visit(child)
    visit(payload)
    # A surviving staged container owns its original identity. A replacement
    # cannot also claim it: splitting a shared field must create a new container.
    occupied={id(anchors[key]) for key in pending if key in anchors}
    for value,previous in replacements:
        key=id(value)
        if key in pending and key not in anchors and id(previous) not in occupied:
            anchors[key]=previous
            occupied.add(id(previous))
    prepared=[]
    for key,value in pending.items():
        target=anchors.get(key)
        if target is None or not isinstance(value,(dict,list,set)):continue
        if isinstance(value,dict):content=[(deepcopy(k,anchors),deepcopy(v,anchors)) for k,v in value.items()]
        else:content=[deepcopy(v,anchors) for v in value]
        prepared.append((target,content))
    committed=deepcopy(payload,anchors)
    # All validation, user-rule callbacks and graph allocation have finished.
    for target,content in prepared:
        if isinstance(target,dict):target.clear();target.update(content)
        elif isinstance(target,list):target[:]=content
        else:target.clear();target.update(content)
    return committed


def resolve_transaction(subjects, rng, resolve):
    """Resolve a staged graph; valid failed checks still commit specified costs."""
    subjects=list(subjects)
    if any(not hasattr(subject,'__dict__') for subject in subjects):
        raise TypeError('Transaction subjects require mutable object state')
    stateful_rng=callable(getattr(rng,'getstate',None)) and callable(getattr(rng,'setstate',None))
    if not stateful_rng and not hasattr(rng,'__dict__'):
        raise TypeError('RNG must expose getstate/setstate or mutable object state')
    originals={}
    def collect(value):
        if id(value) in originals:return
        if isinstance(value,(dict,list,set,tuple)):
            originals[id(value)]=value
            if isinstance(value,dict):
                for key,child in value.items():collect(key);collect(child)
            else:
                for child in value:collect(child)
    for subject in subjects:collect(vars(subject))
    if not stateful_rng:collect(vars(rng))
    memo={}
    staged_subjects,staged_rng=deepcopy((subjects,rng),memo)
    result=resolve(staged_subjects,staged_rng)
    if not subjects and stateful_rng:
        # RNG-only consumers return borrowed live actor references in event
        # records. No subject graph was staged, so there is nothing to remap.
        rng.setstate(staged_rng.getstate())
        return result
    anchors={id(staged):original for original,staged in zip(subjects,staged_subjects)}
    anchors[id(staged_rng)]=rng
    for identity,original in originals.items():
        staged=memo.get(identity)
        if staged is not None and isinstance(original,(dict,list,set)):
            anchors[id(staged)]=original
    pairs=list(zip(subjects,staged_subjects))
    if not stateful_rng:pairs.append((rng,staged_rng))
    replacements=[]
    for original,staged in pairs:
        anchors[id(vars(staged))]=vars(original)
        for field,value in vars(staged).items():
            previous=getattr(original,field,None)
            if type(value) is type(previous) and isinstance(value,(dict,list,set)):
                replacements.append((value,previous))
    payload={'states':[vars(staged) for original,staged in pairs],'result':result if subjects else None}
    committed=commit_graph(payload,anchors,replacements)
    if stateful_rng:rng.setstate(staged_rng.getstate())
    return committed['result'] if subjects else result


def json_fingerprint(value, *, compact=False, allow_nan=True, sort_keys=True):
    """Hash the owner's JSON encoding without changing existing saved digests."""
    import json
    from hashlib import sha256
    if any(type(value) is not bool for value in (compact, allow_nan, sort_keys)):
        raise ValueError('explicit JSON fingerprint policy required')
    options = {'sort_keys': sort_keys, 'ensure_ascii': False, 'allow_nan': allow_nan}
    if compact:options['separators'] = (',', ':')
    return sha256(json.dumps(value, **options).encode()).hexdigest()


def request_fingerprint(intent):
    """Canonical data-only request identity, compatible with native receipts."""
    import root_resolution as R
    intent=R.plain(R.freeze(intent))
    return json_fingerprint(intent)


def replay_result(records, request_id, intent, *, fingerprint_field=None):
    """Return a detached completed receipt or None; never authorize fresh work.

    The owner retains its existing persisted receipt collection. Callers check
    identity and request shape first, then lookup before current-use eligibility.
    Pending/resumable events retain their own lifecycle and are not handled here.
    """
    if type(request_id) is not str or not request_id.strip():
        raise ValueError('request identity required')
    if not isinstance(records,dict):raise ValueError('request receipt mapping required')
    signature=request_fingerprint(intent)
    if request_id not in records:return None
    prior=records[request_id]
    if not isinstance(prior,dict):raise ValueError('completed request receipt required')
    if fingerprint_field is not None:
        stored=prior.get(fingerprint_field)
    else:
        if 'intent' not in prior:raise ValueError('request receipt intent missing')
        stored=request_fingerprint(prior['intent'])
    if stored!=signature:raise ValueError('request identity reused with changed input')
    return deepcopy(prior)


def bind_request_intent(record, intent, *, field='intent_fingerprint'):
    """Bind a pending or completed record to one canonical intent.

    Lifecycle status and completed-step receipts stay with the native owner.
    Call on staged records, or when the producer finalizes a new occurrence.
    """
    if type(record) is not dict or type(field) is not str or not field:
        raise ValueError('request record and fingerprint field required')
    signature = request_fingerprint(intent)
    if field in record and record[field] != signature:
        raise ValueError('request identity reused with changed input')
    record[field] = signature
    return signature

