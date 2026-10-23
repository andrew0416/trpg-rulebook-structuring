"""TR03/TR04/I11 input boundary; no source registrations or RNG provider shipped.

Trusted installation pins exact requests and authentic transport principals. Pins
are freshness/identity, not proof of source interpretation or chooser authority.
The caller must not control installation. This is an in-process architecture
boundary, not a hostile-Python security sandbox. Acceptance changes only this
broker's input ledger, never gameplay state. No automatic effect follows choice.
"""
from dataclasses import dataclass, fields
from types import MappingProxyType
import json

if __package__:
    from . import resolution_transaction as _FINGERPRINTS
else:
    import resolution_transaction as _FINGERPRINTS


def _text(v):
    if type(v) is not str or not v:
        raise ValueError('nonempty text required')
    return v


def _hash(v):
    if type(v) is not str or len(v) != 64 or any(c not in '0123456789abcdef' for c in v):
        raise ValueError('canonical SHA256 required')
    return v


def freeze(v):
    if v is None or type(v) in (bool, int, str):
        return v
    if type(v) in (list, tuple):
        return tuple(freeze(x) for x in v)
    if type(v) in (dict, MappingProxyType):
        if any(type(k) is not str or not k for k in v):
            raise TypeError('JSON object keys must be nonempty strings')
        return MappingProxyType({k: freeze(x) for k, x in v.items()})
    raise TypeError('exact integer JSON data required; nonintegers need explicit refinement encoding')


def plain(v):
    if type(v) is MappingProxyType:
        return {k: plain(x) for k, x in v.items()}
    if type(v) is tuple:
        return [plain(x) for x in v]
    return v


def canonical(v):
    return json.dumps(plain(freeze(v)), sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False)


def digest(v):
    return _FINGERPRINTS.json_fingerprint(plain(freeze(v)), sort_keys=True, compact=True, allow_nan=False)


def _names(v):
    if type(v) not in (tuple, list):
        raise TypeError('explicit identity sequence required')
    out = tuple(_text(x) for x in v)
    if not out or len(set(out)) != len(out):
        raise ValueError('nonempty distinct identities required')
    return out


@dataclass(frozen=True)
class Binding:
    event_id: str
    event_hash: str
    profile_hash: str
    revision: int
    context_hash: str

    def __post_init__(self):
        _text(self.event_id)
        for v in (self.event_hash, self.profile_hash, self.context_hash):
            _hash(v)
        if type(self.revision) is not int or self.revision < 0:
            raise ValueError('exact nonnegative revision required')

    def payload(self):
        return {f.name: getattr(self, f.name) for f in fields(self)}


def _request_base(req, responders):
    if type(req.binding) is not Binding:
        raise TypeError('typed binding required')
    _text(req.id); _text(req.purpose)
    if type(req.mode) is not str or req.mode not in ('source', 'synthetic'):
        raise ValueError('explicit source/synthetic mode required')
    object.__setattr__(req, 'source_refs', _names(req.source_refs))
    object.__setattr__(req, responders, _names(getattr(req, responders)))


def request_payload(req):
    if type(req) not in (ChoiceRequest, RollRequest):
        raise TypeError('typed input request required')
    return {'kind': type(req).__name__, **{
        f.name: (req.binding.payload() if f.name == 'binding' else getattr(req, f.name))
        for f in fields(req)}}


def request_fingerprint(req):
    return digest(request_payload(req))


@dataclass(frozen=True)
class ChoiceRequest:
    id: str
    binding: Binding
    purpose: str
    source_refs: tuple
    mode: str
    chooser_ids: tuple
    domain: tuple  # explicit finite JSON alternatives, not arbitrary predicates

    def __post_init__(self):
        _request_base(self, 'chooser_ids')
        if type(self.domain) not in (tuple, list) or not self.domain:
            raise ValueError('nonempty explicit finite JSON domain required')
        values = tuple(freeze(x) for x in self.domain)
        if len({canonical(x) for x in values}) != len(values):
            raise ValueError('duplicate canonical domain alternative')
        object.__setattr__(self, 'domain', values)


@dataclass(frozen=True)
class RollRequest:
    id: str
    binding: Binding
    purpose: str
    source_refs: tuple
    mode: str
    supplier_ids: tuple
    count: int
    sides: int
    distribution: str

    def __post_init__(self):
        _request_base(self, 'supplier_ids')
        if type(self.count) is not int or self.count < 1:
            raise ValueError('positive exact dice count required')
        if type(self.sides) is not int or self.sides < 2:
            raise ValueError('exact sides >=2 required')
        if type(self.distribution) is not str or self.distribution != 'independent_uniform_faces':
            raise ValueError('unsupported/unresolved distribution; refinement remains missing')


@dataclass(frozen=True)
class TrustedPolicy:
    id: str
    mode: str
    request_fingerprints: object

    def __post_init__(self):
        _text(self.id)
        if type(self.mode) is not str or self.mode not in ('source', 'synthetic'):
            raise ValueError('explicit policy mode required')
        if type(self.request_fingerprints) not in (dict, MappingProxyType):
            raise TypeError('explicit request pins required')
        pins = {_text(k): _hash(v) for k, v in self.request_fingerprints.items()}
        object.__setattr__(self, 'request_fingerprints', MappingProxyType(pins))


@dataclass(frozen=True, eq=False)
class Principal:
    id: str
    def __post_init__(self):
        _text(self.id)


@dataclass(frozen=True, eq=False)
class Handle:
    request_id: str


@dataclass(frozen=True, eq=False)
class AcceptedReceipt:
    request_id: str
    request_hash: str
    binding: Binding
    principal_id: str
    value: object
    mode: str
    evidence_kind: str
    # No source-certified boolean: a source-mode label is not source proof.


@dataclass(frozen=True)
class Finding:
    code: str
    detail: str


class Broker:
    """Trusted policy/transport installation; ordinary submitters only get handles.

    No native RNG, implicit reroll, gameplay update, dynamic authority inference,
    persistence or restore API. Parent bridge must bind all five context fields
    and keep lifecycle/snapshot invalidation consistent with kernel occurrences.
    """
    def __init__(self, policy, principals=()):
        if type(policy) is not TrustedPolicy:
            raise TypeError('installed typed policy required')
        principals = tuple(principals)
        if any(type(x) is not Principal for x in principals):
            raise TypeError('installed principal capabilities required')
        if len({x.id for x in principals}) != len(principals):
            raise ValueError('duplicate principal identity')
        self.policy = policy
        self._principals = {x.id: x for x in principals}
        self._requests = {}
        self._handles = {}
        self._receipts = {}

    def register(self, request):
        if type(request) not in (ChoiceRequest, RollRequest):
            return Finding('RejectedRequest', 'typed input request required')
        fingerprint = request_fingerprint(request)
        if request.mode != self.policy.mode or self.policy.request_fingerprints.get(request.id) != fingerprint:
            return Finding('PendingAuthority', 'no installed exact request pin in this mode')
        ids = request.chooser_ids if type(request) is ChoiceRequest else request.supplier_ids
        if not set(ids) <= set(self._principals):
            return Finding('PendingAuthority', 'request names an uninstalled transport principal')
        if request.id in self._handles:
            if request_fingerprint(self._requests[request.id]) != fingerprint:
                return Finding('ConflictingRequest', 'request ID already bound')
            return self._handles[request.id]
        handle = Handle(request.id)
        self._requests[request.id] = request
        self._handles[request.id] = handle
        return handle

    def _checked(self, handle, binding):
        if type(handle) is not Handle or self._handles.get(handle.request_id) is not handle:
            return Finding('RejectedHandle', 'handle not issued by this broker')
        req = self._requests[handle.request_id]
        if type(binding) is not Binding or binding != req.binding:
            return Finding('StaleOrMismatchedContext', 'request/event/profile/revision/context differs')
        if self.policy.mode != req.mode or self.policy.request_fingerprints.get(req.id) != request_fingerprint(req):
            return Finding('PendingAuthority', 'installed request pin changed')
        return req

    def accept(self, handle, principal, value, current_binding):
        req = self._checked(handle, current_binding)
        if type(req) is Finding:
            return req
        if type(principal) is not Principal or self._principals.get(principal.id) is not principal:
            return Finding('RejectedAuthority', 'principal capability not installed')
        ids = req.chooser_ids if type(req) is ChoiceRequest else req.supplier_ids
        if principal.id not in ids:
            return Finding('RejectedAuthority', 'principal not scoped to this request')
        try:
            if type(req) is ChoiceRequest:
                answer = freeze(value)
                if canonical(answer) not in {canonical(x) for x in req.domain}:
                    return Finding('OutsideDomain', 'choice outside exact JSON domain')
            else:
                if type(value) not in (tuple, list) or len(value) != req.count:
                    return Finding('InvalidFaces', 'ordered face count must match request')
                if any(type(x) is not int or not 1 <= x <= req.sides for x in value):
                    return Finding('InvalidFaces', 'exact integer faces in requested range required')
                answer = tuple(value)
        except (TypeError, ValueError):
            return Finding('OutsideDomain', 'input is not supported finite JSON')
        previous = self._receipts.get(req.id)
        if previous is not None:
            if previous.principal_id == principal.id and canonical(previous.value) == canonical(answer):
                return previous
            return Finding('ConflictingReplay', 'accepted input cannot be replaced or rerolled')
        receipt = AcceptedReceipt(req.id, request_fingerprint(req), req.binding,
                                  principal.id, answer, req.mode,
                                  'source_choice' if type(req) is ChoiceRequest else 'randomness')
        self._receipts[req.id] = receipt
        return receipt

    def validate_receipt(self, handle, receipt, current_binding):
        req = self._checked(handle, current_binding)
        if type(req) is Finding:
            return req
        if type(receipt) is not AcceptedReceipt or self._receipts.get(req.id) is not receipt:
            return Finding('RejectedReceipt', 'not the accepted receipt for this issued request')
        return receipt.value
