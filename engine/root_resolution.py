"""Pure R04 model resolver. No source certification, live Engine or callback execution.

Frozen source refinement/admission belongs to the caller's independently checked
registry. Nonempty witness labels and hashes are trace references, never proof.
"""
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from fractions import Fraction
from types import MappingProxyType
from collections.abc import Mapping
import json

if __package__:
    from . import resolution_transaction as _FINGERPRINTS
else:
    import resolution_transaction as _FINGERPRINTS


class Truth(Enum):
    TRUE = 'true'
    FALSE = 'false'
    UNKNOWN = 'unknown'


def _id(value):
    if type(value) is not str or not value:
        raise ValueError('nonempty string identity required')
    return value


def freeze(value):
    if value is None or type(value) in (str, int, bool):
        return value
    if isinstance(value, Mapping):
        if any(type(k) is not str or not k for k in value):
            raise ValueError('nonempty JSON object keys required')
        return MappingProxyType({k: freeze(v) for k, v in value.items()})
    if type(value) in (tuple, list):
        return tuple(freeze(v) for v in value)
    raise TypeError('exact immutable JSON value required; floats/callbacks unsupported')


def plain(value):
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {f.name: plain(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {k: plain(v) for k, v in value.items()}
    if type(value) in (tuple, list):
        return [plain(v) for v in value]
    return value


def canonical(value):
    return json.dumps(plain(value), sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def fingerprint(value):
    return _FINGERPRINTS.json_fingerprint(plain(value), sort_keys=True, compact=True, allow_nan=False)


def _paths(value):
    result = []
    for p in value:
        if type(p) not in (tuple, list) or not p:
            raise ValueError('footprint must contain nonempty typed path tuples')
        result.append(tuple(_id(x) for x in p))
    return tuple(sorted(set(result)))


def _overlap(a, b):
    return a[:len(b)] == b or b[:len(a)] == a


@dataclass(frozen=True)
class Predicate:
    truth: Truth
    obligation: str = ''
    reads: tuple = ()

    def __post_init__(self):
        object.__setattr__(self, 'reads', _paths(self.reads))
        if not isinstance(self.truth, Truth):
            raise TypeError('explicit Truth required')
        if self.truth is Truth.UNKNOWN:
            _id(self.obligation)
        elif self.obligation:
            raise ValueError('known predicate must not carry unknown obligation')


TRUE = Predicate(Truth.TRUE)
FALSE = Predicate(Truth.FALSE)


def conjunction(*predicates):
    if any(not isinstance(p, Predicate) for p in predicates):
        raise TypeError('typed predicates required')
    reads = tuple(pth for p in predicates for pth in p.reads)
    if any(p.truth is Truth.FALSE for p in predicates):
        return Predicate(Truth.FALSE, reads=reads)
    unknown = sorted({p.obligation for p in predicates if p.truth is Truth.UNKNOWN})
    return Predicate(Truth.UNKNOWN, ';'.join(unknown), reads) if unknown else Predicate(Truth.TRUE, reads=reads)


@dataclass(frozen=True)
class Footprint:
    reads: tuple = ()
    writes: tuple = ()
    observations: tuple = ()  # Includes emitted events, RNG stream use, decision consumption.

    def __post_init__(self):
        for key in ('reads', 'writes', 'observations'):
            object.__setattr__(self, key, _paths(getattr(self, key)))


def _union_footprints(items):
    return Footprint(*(tuple(p for f in items for p in getattr(f, k))
                       for k in ('reads', 'writes', 'observations')))


@dataclass(frozen=True)
class Clause:
    id: str
    aspect: str
    value: object
    selected: Predicate = TRUE
    scope: Predicate = TRUE
    premises: Predicate = TRUE
    footprint: Footprint = Footprint()
    source_refs: tuple = ()

    def __post_init__(self):
        _id(self.id); _id(self.aspect)
        if not all(isinstance(p, Predicate) for p in (self.selected, self.scope, self.premises)):
            raise TypeError('clause predicates required')
        if not isinstance(self.footprint, Footprint):
            raise TypeError('typed footprint required')
        object.__setattr__(self, 'value', freeze(self.value))
        object.__setattr__(self, 'source_refs', tuple(_id(x) for x in self.source_refs))


@dataclass(frozen=True)
class Override:
    general: str
    specific: str
    aspect: str
    guard: Predicate
    witness_ref: str

    def __post_init__(self):
        for x in (self.general, self.specific, self.aspect, self.witness_ref): _id(x)
        if not isinstance(self.guard, Predicate): raise TypeError('edge guard required')


@dataclass(frozen=True)
class CompositionLaw:
    aspect: str
    kind: str
    witness_ref: str
    idempotent: bool = False
    contributor_order: tuple = ()
    observation_policy: str = 'none'  # none, commutative, ordered
    guard: Predicate = TRUE

    def __post_init__(self):
        for x in (self.aspect, self.kind, self.witness_ref): _id(x)
        if type(self.idempotent) is not bool: raise TypeError('explicit idempotence required')
        if not isinstance(self.guard, Predicate): raise TypeError('law guard required')
        if self.observation_policy not in ('none', 'commutative', 'ordered'):
            raise ValueError('unknown observation composition policy')
        order = tuple(_id(x) for x in self.contributor_order)
        if len(set(order)) != len(order): raise ValueError('duplicate contributor order')
        object.__setattr__(self, 'contributor_order', order)


@dataclass(frozen=True)
class AspectOrder:
    before: str
    after: str
    guard: Predicate
    witness_ref: str

    def __post_init__(self):
        for x in (self.before, self.after, self.witness_ref): _id(x)
        if not isinstance(self.guard, Predicate): raise TypeError('order guard required')


@dataclass(frozen=True)
class Independence:
    left: str
    right: str
    guard: Predicate
    witness_ref: str
    gameplay_commutes: bool = False
    observations_commute: bool = False

    def __post_init__(self):
        for x in (self.left, self.right, self.witness_ref): _id(x)
        if not isinstance(self.guard, Predicate): raise TypeError('independence guard required')
        if type(self.gameplay_commutes) is not bool or type(self.observations_commute) is not bool:
            raise TypeError('explicit typed commutation predicates required')


@dataclass(frozen=True)
class ResolutionRequest:
    event_id: str
    event_kind: str
    profile_hash: str
    catalog_hash: str
    context_hash: str  # Caller pins relevant G, event payload, decisions and version.
    clauses: tuple
    overrides: tuple = ()
    laws: tuple = ()
    candidate_closure: Predicate = Predicate(Truth.UNKNOWN, 'candidate_closure_unreviewed')
    aspects: tuple = ()  # Empty means all declared clause aspects, not all source rules.
    aspect_orders: tuple = ()
    independences: tuple = ()

    def __post_init__(self):
        for key in ('event_id', 'event_kind', 'profile_hash', 'catalog_hash', 'context_hash'):
            _id(getattr(self, key))
        if not isinstance(self.candidate_closure, Predicate): raise TypeError('typed closure predicate required')
        for key, typ in (('clauses', Clause), ('overrides', Override), ('laws', CompositionLaw),
                         ('aspect_orders', AspectOrder), ('independences', Independence)):
            val = tuple(getattr(self, key))
            if any(not isinstance(x, typ) for x in val): raise TypeError('invalid '+key)
            object.__setattr__(self, key, val)
        ids = [c.id for c in self.clauses]
        if len(set(ids)) != len(ids): raise ValueError('duplicate clause identity')
        aspects = tuple(sorted(set(_id(x) for x in self.aspects)))
        object.__setattr__(self, 'aspects', aspects)
        law_aspects = [l.aspect for l in self.laws]
        if len(set(law_aspects)) != len(law_aspects): raise ValueError('ambiguous composition laws for aspect')
        by_id = {c.id: c for c in self.clauses}
        for e in self.overrides:
            if e.general not in by_id or e.specific not in by_id:
                raise ValueError('unknown override endpoint')
            if by_id[e.general].aspect != e.aspect or by_id[e.specific].aspect != e.aspect:
                raise ValueError('cross-aspect override')
        declared = {c.aspect for c in self.clauses} | set(aspects)
        for o in self.aspect_orders:
            if o.before not in declared or o.after not in declared: raise ValueError('unknown aspect order endpoint')
        for i in self.independences:
            if i.left not in declared or i.right not in declared or i.left == i.right:
                raise ValueError('invalid independence endpoints')


@dataclass(frozen=True)
class Obligation:
    code: str
    subjects: tuple
    detail: str


@dataclass(frozen=True)
class AspectPlan:
    aspect: str
    value: object
    contributors: tuple
    contributions: tuple
    dominated: tuple
    footprint: Footprint
    law_ref: str
    used_override_refs: tuple
    contributor_order: tuple = ()


@dataclass(frozen=True)
class Resolution:
    tag: str
    request_fingerprint: str
    aspects: tuple
    dependencies: tuple
    footprint: Footprint
    obligations: tuple
    receipt: object
    gameplay_certified: bool = False

    def __post_init__(self):
        if self.tag not in ('ModelReady', 'Pending', 'Excluded'): raise ValueError('resolver cannot issue SourceReady')
        if self.gameplay_certified is not False: raise ValueError('model resolution is not source certification')
        object.__setattr__(self, 'receipt', freeze(self.receipt))


def _closure(nodes, edges):
    reach = set(edges)
    for mid in sorted(nodes):
        reach |= {(a,b) for a,k in tuple(reach) for k2,b in tuple(reach) if k == mid == k2}
    return reach


def _maxima(active, reach):
    return tuple(sorted(a for a in active if not any(a != b and (a,b) in reach for b in active)))


def _number(value):
    if type(value) is int: return Fraction(value)
    if isinstance(value, Mapping) and set(value) == {'numerator', 'denominator'}:
        n, d = value['numerator'], value['denominator']
        if type(n) is int and type(d) is int and d > 0: return Fraction(n, d)
    raise ValueError('exact integer or {numerator:int,denominator:positiveInt} required')


def _numeric_value(value):
    return value.numerator if value.denominator == 1 else freeze({'numerator':value.numerator, 'denominator':value.denominator})


def _compose(law, members):
    """Declared finite algebras. Algebra registration itself is a model assumption."""
    values = [c.value for c in members]
    if law.kind == 'exclusive':
        if len(values) > 1 and not law.idempotent: raise ValueError('exclusive_merge_requires_idempotence')
        if len({canonical(v) for v in values}) != 1: raise ValueError('incompatible_exclusive_values')
        return values[0]
    if law.kind in ('additive', 'product', 'minimum', 'maximum'):
        # Reuse the same exact arithmetic as source-owned effect previews.
        # Min/max have no neutral finite base; seed them from an actual member.
        if __package__:
            from . import composition_derive as COMPOSITION
        else:
            import composition_derive as COMPOSITION
        operator = {'additive':'add', 'product':'multiply',
                    'minimum':'minimum', 'maximum':'maximum'}[law.kind]
        base = 0 if law.kind == 'additive' else 1 if law.kind == 'product' else values[0]
        rows = [{'id':c.id, 'source':c.source_refs[0] if c.source_refs else c.id,
                 'value':plain(c.value)} for c in members]
        steps = [{'law':operator, 'contributors':[c.id for c in members]}] if rows else []
        result = COMPOSITION.derive(plain(base), rows, steps, rounding='exact')
        return freeze(result['value'])
    if law.kind == 'sequence':
        by_id = {c.id:c for c in members}
        if not set(by_id) <= set(law.contributor_order): raise ValueError('missing_contributor_order')
        return tuple(by_id[c].value for c in law.contributor_order if c in by_id)
    if law.kind == 'set_union':
        if not law.idempotent: raise ValueError('set_union_requires_idempotence')
        if any(type(v) is not tuple for v in values): raise ValueError('set_union_requires_explicit_sequences')
        unique = {canonical(x): x for seq in values for x in seq}
        return tuple(unique[k] for k in sorted(unique))
    raise ValueError('unsupported_composition_operator:'+law.kind)


def resolve(request):
    if not isinstance(request, ResolutionRequest): raise TypeError('typed resolution request required')
    req_hash = fingerprint(request)
    obligations = []
    excluded, unknowns, ignored_edges = [], [], []
    plans = []
    wanted = set(request.aspects) or {c.aspect for c in request.clauses}
    by_id = {c.id:c for c in request.clauses}
    laws = {l.aspect:l for l in request.laws}
    evaluations = {c.id:conjunction(c.selected,c.scope,c.premises) for c in request.clauses if c.aspect in wanted}
    def need(code, subjects, detail):
        obligations.append(Obligation(code, tuple(sorted(subjects)), detail))
    if request.candidate_closure.truth is not Truth.TRUE:
        need('candidate_closure_incomplete', (), request.candidate_closure.obligation or 'candidate set declared incomplete')
    for aspect in sorted(wanted):
        relevant = [c for c in request.clauses if c.aspect == aspect]
        aspect_reads = tuple(p for c in relevant for p in evaluations[c.id].reads)
        aspect_reads += tuple(p for e in request.overrides if e.aspect == aspect for p in e.guard.reads)
        if aspect in laws: aspect_reads += laws[aspect].guard.reads
        active = {c.id for c in relevant if evaluations[c.id].truth is Truth.TRUE}
        unknown = [c.id for c in relevant if evaluations[c.id].truth is Truth.UNKNOWN]
        excluded.extend(c.id for c in relevant if evaluations[c.id].truth is Truth.FALSE)
        if unknown:
            unknowns.extend(unknown)
            for uid in sorted(unknown): need('unknown_applicability', (uid,), evaluations[uid].obligation)
        if not active: continue
        # Frozen R04 contract uses applicable induced graph. Excluded/premise-false
        # intermediate clauses cannot supply a path. Guard false is never an edge.
        edges = [e for e in request.overrides if e.aspect == aspect and e.general in active and e.specific in active]
        lower = {(e.general,e.specific) for e in edges if e.guard.truth is Truth.TRUE}
        upper = lower | {(e.general,e.specific) for e in edges if e.guard.truth is Truth.UNKNOWN}
        lower_reach, upper_reach = _closure(active, lower), _closure(active, upper)
        if any((c,c) in lower_reach for c in active):
            need('cyclic_override_relation', active, 'guard-true applicable relation is not a strict partial order');continue
        maxima = _maxima(active, lower_reach)
        unknown_edges = [e for e in edges if e.guard.truth is Truth.UNKNOWN]
        if unknown_edges and (maxima != _maxima(active, upper_reach) or any((c,c) in upper_reach for c in active)):
            need('unknown_override_influence', {e.general for e in unknown_edges}|{e.specific for e in unknown_edges},
                 ';'.join(sorted({e.guard.obligation for e in unknown_edges})))
        else:
            ignored_edges.extend(e.witness_ref for e in unknown_edges)
        law = laws.get(aspect)
        if law is None:
            need('missing_composition_law', (aspect,), 'no implicit composition, including singleton plan');continue
        if law.guard.truth is not Truth.TRUE:
            need('composition_law_unavailable', (aspect,), law.guard.obligation or 'law guard false');continue
        if any(uid not in by_id or by_id[uid].aspect != aspect for uid in law.contributor_order):
            need('invalid_contributor_order', (aspect,), 'order must refer to clauses of the governed aspect');continue
        members = [by_id[c] for c in maxima]
        observed = {c.id for c in members if c.footprint.observations}
        observation_participants = set(observed) if len(observed) > 1 else set()
        for left in members:
            for right in members:
                if left.id != right.id and any(_overlap(w,o) for w in left.footprint.writes for o in right.footprint.observations):
                    observation_participants.update((left.id,right.id))
        if observation_participants:
            if law.observation_policy == 'none':
                need('within_aspect_observation_order_missing', observation_participants, 'value law alone does not compose observations or write/observation interference')
            elif law.observation_policy == 'ordered' and not observation_participants <= set(law.contributor_order):
                need('within_aspect_observation_order_missing', observation_participants, 'explicit contributor order must include all interfering contributors')
        try: value = _compose(law, members)
        except ValueError as exc:
            need('composition_unresolved', maxima, str(exc));continue
        used_refs = tuple(sorted({e.witness_ref for e in edges if e.guard.truth is Truth.TRUE}))
        plans.append(AspectPlan(aspect, freeze(value), maxima, tuple((c.id,c.value) for c in members),
                                tuple(sorted(active-set(maxima))), _union_footprints([c.footprint for c in members]+[Footprint(reads=aspect_reads)]),
                                law.witness_ref, used_refs, tuple(c for c in law.contributor_order if c in maxima)))
    names = {p.aspect for p in plans}
    orders = [o for o in request.aspect_orders if o.before in names and o.after in names and o.guard.truth is Truth.TRUE]
    dependencies = _closure(names, {(o.before,o.after) for o in orders})
    if any((a,a) in dependencies for a in names): need('cyclic_aspect_order', names, 'no execution plan for cyclic order')
    for index, a in enumerate(plans):
        for b in plans[index+1:]:
            if (a.aspect,b.aspect) in dependencies or (b.aspect,a.aspect) in dependencies: continue
            fa,fb = a.footprint,b.footprint
            gameplay = (any(_overlap(x,y) for x in fa.writes for y in fb.reads+fb.writes)
                        or any(_overlap(x,y) for x in fb.writes for y in fa.reads))
            # Distinct observation labels do not prove joint observation commutation.
            observation = (bool(fa.observations and fb.observations)
                           or any(_overlap(x,y) for x in fa.writes for y in fb.observations)
                           or any(_overlap(x,y) for x in fb.writes for y in fa.observations))
            proofs = [i for i in request.independences if {i.left,i.right}=={a.aspect,b.aspect} and i.guard.truth is Truth.TRUE]
            if gameplay and not any(i.gameplay_commutes for i in proofs):
                need('unordered_gameplay_dependency', (a.aspect,b.aspect), 'overlapping declared read/write paths require order or explicit commutation law')
            if observation and not any(i.observations_commute for i in proofs):
                need('unordered_observation_dependency', (a.aspect,b.aspect), 'observations, randomness and decision use require order or explicit commutation law')
    # Pending diagnostics may contain partial aspect analyses; they are not executable.
    tag = 'Pending' if obligations else 'ModelReady' if plans else 'Excluded'
    obligations = tuple(sorted(set(obligations),key=lambda o:(o.code,o.subjects,o.detail)))
    plans = tuple(plans)
    # Predicates are caller-evaluated facts. Preserve declared conservative reads,
    # including excluded candidates, without claiming their completeness is proved.
    evaluation_reads = request.candidate_closure.reads
    evaluation_reads += tuple(p for ev in evaluations.values() for p in ev.reads)
    evaluation_reads += tuple(p for e in request.overrides if e.aspect in wanted for p in e.guard.reads)
    evaluation_reads += tuple(p for law in request.laws if law.aspect in wanted for p in law.guard.reads)
    evaluation_reads += tuple(p for edge in request.aspect_orders for p in edge.guard.reads)
    evaluation_reads += tuple(p for edge in request.independences for p in edge.guard.reads)
    footprint = _union_footprints([p.footprint for p in plans]+[Footprint(reads=evaluation_reads)])
    plan_payload = {'aspects':plain(plans),'dependencies':sorted(dependencies),'footprint':plain(footprint)}
    receipt = {'request_fingerprint':req_hash,'event_id':request.event_id,'event_kind':request.event_kind,
               'profile_hash':request.profile_hash,'catalog_hash':request.catalog_hash,'context_hash':request.context_hash,
               'plan_fingerprint':fingerprint(plan_payload),'candidate_closure':plain(request.candidate_closure),
               'excluded_clause_ids':sorted(excluded),'unknown_clause_ids':sorted(unknowns),
               'ignored_unknown_edges_by_maxima_noninfluence':sorted(ignored_edges),
               'claim':'model_experiment_only; source admission/refinement/closure not certified',
               'executable_model_plan':tag=='ModelReady','source_ready':False}
    return Resolution(tag,req_hash,plans,tuple(sorted(dependencies)),footprint,obligations,receipt)


def plan_payload(resolution):
    """Input for parent's trusted factory, not an Engine/root_machine Plan itself."""
    if not isinstance(resolution, Resolution) or resolution.tag != 'ModelReady':
        raise ValueError('only ModelReady has an executable model plan payload')
    return freeze({'request_fingerprint':resolution.request_fingerprint,
                   'plan_fingerprint':resolution.receipt['plan_fingerprint'],
                   'aspects':plain(resolution.aspects),'dependencies':plain(resolution.dependencies),
                   'footprint':plain(resolution.footprint),'source_ready':False})
