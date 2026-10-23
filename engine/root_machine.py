"""Executable top-level transition kernel, not a completed rulebook engine.

G is immutable gameplay state; K contains occurrence receipts and pending inputs.
Trusted refinements supply guards, local updates and source-specific order. This
kernel checks structural invariants/frames; it cannot prove arbitrary Python
refinements pure, correctly sourced, or complete. No universal cost/effect order.
"""
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from collections.abc import Mapping
from typing import Callable
import json
from . import root_children as rc
from . import resolution_transaction as _FINGERPRINTS

DOMAINS = frozenset(('actors','world','clock','resources','effects','growth','domains'))


def freeze(value):
    if value is None or type(value) in (str,int,bool): return value
    if isinstance(value, Mapping):
        if any(type(k) is not str or not k for k in value): raise ValueError('nonempty string keys required')
        return MappingProxyType({k:freeze(v) for k,v in value.items()})
    if type(value) in (tuple,list): return tuple(freeze(v) for v in value)
    raise TypeError('state/evidence must contain immutable JSON values')


def thaw(value):
    if isinstance(value, Mapping): return {k:thaw(v) for k,v in value.items()}
    if type(value) is tuple: return [thaw(v) for v in value]
    return value


def identity(value): return json.dumps(thaw(value),sort_keys=True,separators=(',',':'),ensure_ascii=False)


def state_fingerprint(snapshot):
    return _FINGERPRINTS.json_fingerprint(thaw((snapshot.profile,snapshot.revision,snapshot.game)), sort_keys=True, compact=True, allow_nan=True)


def event_fingerprint(event):
    return identity((event.id,event.kind,event.profile,event.expected_revision,event.payload,event.parent))


def path(value):
    value=tuple(value)
    if not value or value[0] not in DOMAINS or any(type(k) is not str or not k for k in value):
        raise ValueError('invalid typed gameplay path')
    return value


def covers(prefix, child): return child[:len(prefix)]==prefix

def overlaps(a,b): return covers(a,b) or covers(b,a)


class Truth(Enum):
    TRUE='true'
    FALSE='false'
    UNKNOWN='unknown'


@dataclass(frozen=True)
class NeedInput:
    key: str
    kind: str  # source_choice or randomness, never missing implementation
    reason: str
    def __post_init__(self):
        if any(type(v) is not str or not v for v in (self.key,self.reason)) or self.kind not in ('source_choice','randomness'):
            raise ValueError('invalid input request')


@dataclass(frozen=True)
class Block:
    reason: str
    detail: str
    def __post_init__(self):
        if self.reason not in ('source_ambiguity','missing_refinement','missing_runtime','conflict','stale_evidence','invalid_state','frame_violation','precondition_false'):
            raise ValueError('unknown blocker category')
        if type(self.detail) is not str: raise ValueError('block detail must be text')


@dataclass(frozen=True)
class Guard:
    truth: Truth
    missing: object=None
    def __post_init__(self):
        if not isinstance(self.truth,Truth): raise ValueError('Truth is not a Python truthiness value')
        if self.truth is Truth.UNKNOWN and not isinstance(self.missing,(NeedInput,Block)):
            raise ValueError('unknown guard needs typed obligation')
        if self.truth is not Truth.UNKNOWN and self.missing is not None: raise ValueError('known guard with missing obligation')


@dataclass(frozen=True)
class Write:
    path: tuple
    value: object=None
    delete: bool=False
    def __post_init__(self):
        object.__setattr__(self,'path',path(self.path));object.__setattr__(self,'value',freeze(self.value))
        if type(self.delete) is not bool: raise ValueError('delete must be boolean')


@dataclass(frozen=True)
class Commit:
    writes: tuple=()
    result: object=None
    children: tuple=()
    def __post_init__(self):
        ws=tuple(self.writes)
        if any(not isinstance(w,Write) for w in ws): raise ValueError('typed writes required')
        if any(overlaps(a.path,b.path) for i,a in enumerate(ws) for b in ws[i+1:]):
            raise ValueError('overlapping writes within atomic node')
        object.__setattr__(self,'writes',ws);object.__setattr__(self,'result',freeze(self.result))
        cs=tuple(self.children)
        if any(type(c) is not rc.ChildSpec for c in cs) or len({c.key for c in cs})!=len(cs):raise ValueError('distinct typed emitted child keys required')
        object.__setattr__(self,'children',cs)


@dataclass(frozen=True)
class Event:
    id: str
    kind: str
    profile: str
    expected_revision: int
    payload: object=field(default_factory=dict)
    parent: str|None=None
    def __post_init__(self):
        if any(type(x) is not str or not x for x in (self.id,self.kind,self.profile)):
            raise ValueError('event identity/kind/profile required')
        if type(self.expected_revision) is not int or self.expected_revision<0: raise ValueError('invalid revision')
        if self.parent is not None and (type(self.parent) is not str or not self.parent): raise ValueError('invalid causal parent')
        object.__setattr__(self,'payload',freeze(self.payload))


@dataclass(frozen=True)
class Node:
    id: str
    reads: tuple
    writes: tuple
    guard: Callable
    update: Callable
    after: tuple=()
    false_policy: str='reject'
    post: Callable|None=None
    after_children: tuple=()  # (emitting node id, child key); absent dynamic emission is unresolved
    def __post_init__(self):
        if type(self.id) is not str or not self.id or not callable(self.guard) or not callable(self.update): raise ValueError('invalid node')
        if self.false_policy not in ('reject','exclude'): raise ValueError('source false branch required')
        object.__setattr__(self,'reads',tuple(path(x) for x in self.reads))
        object.__setattr__(self,'writes',tuple(path(x) for x in self.writes))
        object.__setattr__(self,'after',tuple(self.after))
        cs=tuple(tuple(x) for x in self.after_children)
        if any(len(x)!=2 or any(type(y) is not str or not y for y in x) for x in cs) or len(set(cs))!=len(cs):raise ValueError('typed child dependency pairs required')
        object.__setattr__(self,'after_children',cs)


@dataclass(frozen=True)
class Plan:
    id: str
    profile: str
    event_kind: str
    nodes: tuple
    origin: str  # model_experiment or source_refinement_candidate; neither is certification
    source_refs: tuple=()
    def __post_init__(self):
        if any(type(x) is not str or not x for x in (self.id,self.profile,self.event_kind)): raise ValueError('plan identity required')
        if self.origin not in ('model_experiment','source_refinement_candidate'): raise ValueError('invalid origin')
        if self.origin=='source_refinement_candidate' and not self.source_refs: raise ValueError('source references required, not sufficient for certification')
        object.__setattr__(self,'nodes',tuple(self.nodes));object.__setattr__(self,'source_refs',tuple(self.source_refs))
        if any(type(ref) is not str or not ref for ref in self.source_refs): raise ValueError('source reference identities must be strings')
        if not self.nodes or any(not isinstance(n,Node) for n in self.nodes): raise ValueError('nonempty typed plan required')


class ReadView:
    def __init__(self,game,allowed): self._game=game;self._allowed=allowed
    def get(self,key):
        key=path(key)
        if not any(covers(a,key) for a in self._allowed): raise PermissionError('undeclared read: '+repr(key))
        value=self._game
        for k in key: value=value[k]
        return value


@dataclass(frozen=True)
class Outcome:
    tag: str
    event_id: str
    committed: tuple=()
    excluded: tuple=()
    results: tuple=()
    obligation: object=None
    gameplay_certified: bool=False
    def __post_init__(self):
        if self.tag not in ('Rejected','Blocked','AwaitingInput','AwaitingChildren','Completed'): raise ValueError('unknown top-level outcome')
        if type(self.event_id) is not str or not self.event_id: raise ValueError('outcome event required')
        if self.gameplay_certified is not False: raise ValueError('kernel cannot certify source gameplay')
        for name in ('committed','excluded'):
            items=tuple(getattr(self,name))
            if any(type(x) is not str for x in items): raise ValueError('node identity required')
            object.__setattr__(self,name,items)
        object.__setattr__(self,'results',freeze(self.results))
        if self.obligation is not None and not isinstance(self.obligation,(Block,NeedInput,rc.NeedChildren)): raise TypeError('typed obligation required')


@dataclass(frozen=True)
class Occurrence:
    event: Event
    plan: Plan
    revision: int
    settled: tuple=()
    committed: tuple=()
    excluded: tuple=()
    results: tuple=()
    evidence: object=field(default_factory=dict)
    outcome: Outcome|None=None
    state_fingerprint: str=""
    def __post_init__(self):
        if not isinstance(self.event,Event) or not isinstance(self.plan,Plan): raise TypeError('typed occurrence identity required')
        if type(self.revision) is not int or self.revision<0: raise ValueError('invalid occurrence revision')
        for name in ('settled','committed','excluded'): object.__setattr__(self,name,tuple(getattr(self,name)))
        object.__setattr__(self,'results',freeze(self.results))
        if self.outcome is not None and (not isinstance(self.outcome,Outcome) or self.outcome.event_id!=self.event.id): raise ValueError('typed matching occurrence outcome required')
        object.__setattr__(self,'evidence',freeze(self.evidence))


@dataclass(frozen=True)
class Snapshot:
    profile: str
    revision: int
    game: object
    occurrences: object=field(default_factory=dict)
    children: object=field(default_factory=dict)
    def __post_init__(self):
        g=freeze(self.game)
        if set(g)!=DOMAINS or any(not isinstance(g[k],Mapping) for k in DOMAINS): raise ValueError('seven typed game domains required')
        if type(self.revision) is not int or self.revision<0: raise ValueError('invalid revision')
        if type(self.profile) is not str or not self.profile: raise ValueError('profile required')
        object.__setattr__(self,'game',g)
        ledger=dict(self.occurrences)
        if any(type(k) is not str or not isinstance(v,Occurrence) or v.event.id!=k or v.revision>self.revision for k,v in ledger.items()):
            raise ValueError('typed occurrence ledger with matching event keys/revisions required')
        object.__setattr__(self,'occurrences',MappingProxyType(ledger))
        children=dict(self.children)
        for k,row in children.items():
            if type(row) is not rc.ChildRecord or k!=row.id or row.parent_event not in ledger or row.parent_node not in ledger[row.parent_event].committed:raise ValueError('child obligation lacks committed causal parent')
        object.__setattr__(self,'children',MappingProxyType(children))


def validate_plan(plan):
    ns={n.id:n for n in plan.nodes}
    if len(ns)!=len(plan.nodes): return Block('conflict','duplicate node identity')
    parents={n.id:set(n.after) for n in plan.nodes}
    if any(not p<=ns.keys() for p in parents.values()): return Block('conflict','unknown predecessor')
    changed=True
    while changed:
        changed=False
        for k in parents:
            closure=parents[k]|set().union(*(parents[p] for p in tuple(parents[k])))
            if closure!=parents[k]:parents[k]=closure;changed=True
    if any(k in p for k,p in parents.items()): return Block('conflict','cyclic source order')
    if any(emitter not in parents[n.id] for n in plan.nodes for emitter,key in n.after_children):return Block('conflict','child dependency emitter must precede its consumer')
    for i,a in enumerate(plan.nodes):
        for b in plan.nodes[i+1:]:
            if a.id in parents[b.id] or b.id in parents[a.id]: continue
            if any(overlaps(x,y) for x in a.writes for y in b.reads+b.writes) or any(overlaps(x,y) for x in b.writes for y in a.reads):
                return Block('conflict','unordered read/write hazard: '+a.id+'/'+b.id)
    return None


def apply_writes(game,writes,allowed):
    for w in writes:
        if not any(covers(a,w.path) for a in allowed): raise PermissionError('undeclared write: '+repr(w.path))
        if len(w.path)==1: raise PermissionError('cannot replace whole game domain')
    g=thaw(game)
    for w in writes:
        parent=g
        for k in w.path[:-1]: parent=parent[k]
        if not isinstance(parent,dict): raise ValueError('write parent must be a mapping')
        if w.delete: del parent[w.path[-1]]
        else: parent[w.path[-1]]=thaw(w.value)
    return freeze(g)


class Machine:
    """Trusted pure-refinement executor. In-process snapshots; no durable save claim.
    No live Engine mutation is authorized merely by constructing this model.
    """
    def __init__(self,snapshot,invariants=()):
        self.state=snapshot;self.invariants=tuple(invariants)
        if not all(v(snapshot.game) is True for v in self.invariants): raise ValueError('initial invariant violation')

    def submit(self,plan,event):
        if not isinstance(plan,Plan) or not isinstance(event,Event): raise TypeError('typed plan/event required')
        if event.profile!=self.state.profile or plan.profile!=self.state.profile:
            return Outcome("Rejected",event.id,obligation=Block("stale_evidence","profile mismatch"))
        old=self.state.occurrences.get(event.id)
        if old:
            if old.plan is not plan or event_fingerprint(old.event)!=event_fingerprint(event):
                return Outcome('Rejected',event.id,obligation=Block('conflict','occurrence identity reused with changed request/plan'))
            return old.outcome
        if event.profile!=self.state.profile or plan.profile!=self.state.profile or event.kind!=plan.event_kind or event.expected_revision!=self.state.revision:
            return Outcome('Rejected',event.id,obligation=Block('stale_evidence','profile/kind/state mismatch'))
        if event.parent is not None and event.parent not in self.state.occurrences:
            return Outcome('Rejected',event.id,obligation=Block('conflict','unknown causal parent'))
        emitted=self.state.children.get(event.id)
        if emitted is not None:
            issue=self.child_event(event.id)
            if isinstance(issue,Block):return Outcome('Blocked',event.id,obligation=issue)
            if event_fingerprint(issue)!=event_fingerprint(event):return Outcome('Rejected',event.id,obligation=Block('conflict','event differs from emitted child obligation'))
        issue=validate_plan(plan)
        if issue:return Outcome('Blocked',event.id,obligation=issue)
        rec=Occurrence(event,plan,self.state.revision)
        return self._run(rec)

    def resume(self,event_id,answers):
        rec=self.state.occurrences[event_id]
        if rec.outcome.tag!='AwaitingInput': raise ValueError('only a source input request may be resumed')
        request=rec.outcome.obligation
        if not isinstance(answers,Mapping) or set(answers)!={request.key}:raise ValueError('answer only the pending source request')
        if rec.revision!=self.state.revision or rec.event.profile!=self.state.profile or rec.plan.profile!=self.state.profile or rec.state_fingerprint!=state_fingerprint(self.state):
            return Outcome('Blocked',event_id,rec.committed,rec.excluded,rec.results,Block('stale_evidence','game state changed while waiting'))
        evidence=dict(rec.evidence);evidence.update(answers)
        return self._run(Occurrence(rec.event,rec.plan,rec.revision,rec.settled,rec.committed,rec.excluded,rec.results,evidence))

    def _store(self,rec,outcome):
        ledger=dict(self.state.occurrences)
        ledger[rec.event.id]=Occurrence(rec.event,rec.plan,self.state.revision,rec.settled,rec.committed,rec.excluded,rec.results,rec.evidence,outcome,state_fingerprint(self.state))
        self.state=Snapshot(self.state.profile,self.state.revision,self.state.game,ledger,rc.sync(self.state.children,ledger))
        return outcome

    def _run(self,rec):
        settled=list(rec.settled);committed=list(rec.committed);excluded=list(rec.excluded);results=list(rec.results)
        def finish(tag,obligation=None):
            updated=Occurrence(rec.event,rec.plan,self.state.revision,tuple(settled),tuple(committed),tuple(excluded),tuple(results),rec.evidence)
            return self._store(updated,Outcome(tag,rec.event.id,tuple(committed),tuple(excluded),tuple(results),obligation))
        while len(settled)<len(rec.plan.nodes):
            ready=[n for n in rec.plan.nodes if n.id not in settled and set(n.after)<=set(settled)]
            node=min(ready,key=lambda n:n.id) # hazards checked; no source priority inferred
            wait=self._child_wait(rec,node)
            if wait is not None:return finish('AwaitingChildren',wait)
            before=self.state.game;view=ReadView(before,node.reads)
            try:
                guard=node.guard(view,rec.event,rec.evidence)
                if not isinstance(guard,Guard):raise TypeError('guard must return Truth3')
                if guard.truth is Truth.UNKNOWN:
                    return finish('AwaitingInput' if isinstance(guard.missing,NeedInput) else 'Blocked',guard.missing)
                if guard.truth is Truth.FALSE:
                    if node.false_policy=='exclude':excluded.append(node.id);settled.append(node.id);continue
                    return finish('Blocked' if committed else 'Rejected',Block('precondition_false',node.id))
                update=node.update(view,rec.event,rec.evidence)
                if isinstance(update,(Block,NeedInput)):
                    return finish('AwaitingInput' if isinstance(update,NeedInput) else 'Blocked',update)
                if not isinstance(update,Commit):raise TypeError('typed local result required')
                new_children=self._validate_emissions(rec,node,update.children,settled)
                after=apply_writes(before,update.writes,node.writes)
                # Postconditions may inspect only declared reads and writes.
                observed=tuple(set(node.reads+node.writes))
                if node.post and node.post(ReadView(before,observed),ReadView(after,observed),update.result) is not True:
                    return finish('Blocked',Block('invalid_state','local postcondition: '+node.id))
                if not all(v(after) is True for v in self.invariants):
                    return finish('Blocked',Block('invalid_state','game invariant: '+node.id))
            except PermissionError as exc:return finish('Blocked',Block('frame_violation',str(exc)))
            except Exception as exc:return finish('Blocked',Block('missing_runtime',type(exc).__name__+': '+str(exc)))
            committed.append(node.id);settled.append(node.id);results.append((node.id,update.result))
            ledger=dict(self.state.occurrences)
            ledger[rec.event.id]=Occurrence(rec.event,rec.plan,self.state.revision+1,tuple(settled),tuple(committed),tuple(excluded),tuple(results),rec.evidence)
            children=dict(self.state.children);children.update(new_children)
            self.state=Snapshot(self.state.profile,self.state.revision+1,after,ledger,rc.sync(children,ledger))
            if any(x.spec.barrier=='unknown' or x.spec.timing=='unknown' for x in new_children.values()):return finish('AwaitingChildren',rc.NeedChildren(tuple(new_children),'unknown child barrier or timing'))
        return finish('AwaitingChildren',wait) if (wait:=self._child_wait(rec,None)) is not None else finish('Completed')

    def _validate_emissions(self,rec,node,specs,settled):
        out={};nodes={n.id for n in rec.plan.nodes}
        batch={c.key:c for c in specs}
        dependencies={k:set(c.after_siblings) for k,c in batch.items()}
        if any(not (set(c.after_siblings)|set(c.independent_siblings))<=set(batch) for c in specs):raise ValueError('sibling relation outside emission batch')
        for _ in batch:
            for k in dependencies:dependencies[k]|=set().union(*(dependencies[x] for x in tuple(dependencies[k])))
        if any(k in deps for k,deps in dependencies.items()):raise ValueError('cyclic sibling dependencies')
        for spec in specs:
            key=rc.child_id(rec.event.id,node.id,spec.key)
            if key in self.state.children or key in self.state.occurrences:raise ValueError('child identity already in ledger')
            if not set(spec.source_refs)<=set(rec.plan.source_refs):raise ValueError('child emission source outside parent refinement')
            referenced=set(spec.before_nodes)|set(spec.independent_nodes)
            if not referenced<=nodes or referenced & (set(settled)|{node.id}):raise ValueError('child ordering names absent/already-settled parent node')
            out[key]=rc.ChildRecord(key,rec.event.id,node.id,spec)
        return out

    def _child_wait(self,rec,node):
        rows=[x for x in self.state.children.values() if x.parent_event==rec.event.id]
        for row in rows:
            if row.spec.barrier=='unknown' or row.spec.timing=='unknown':return rc.NeedChildren((row.id,),'unknown child barrier or timing')
        if node is None:
            waiting=tuple(x.id for x in rows if x.spec.barrier=='before_parent_complete' and x.status!='completed')
            return rc.NeedChildren(waiting,'required child not successfully completed') if waiting else None
        by_key={(x.parent_node,x.spec.key):x for x in rows}
        explicit=[]
        for key in node.after_children:
            row=by_key.get(key)
            if row is None:return rc.NeedChildren((),'declared dynamic child was not emitted; branch refinement missing')
            explicit.append(row.id)
        for row in rows:
            needs=row.id in explicit or node.id in row.spec.before_nodes
            if needs:
                if row.status!='completed':return rc.NeedChildren((row.id,),'parent node awaits its explicit child dependency')
            elif node.id not in row.spec.independent_nodes:
                return rc.NeedChildren((row.id,),'parent node/child order or independence unrefined')
        return None

    def child_event(self,child_id):
        row=self.state.children.get(child_id)
        if row is None:return Block('conflict','unknown emitted child')
        if row.spec.barrier=='unknown' or row.spec.timing=='unknown':return Block('source_ambiguity','unknown child classification or timing')
        parent=self.state.occurrences[row.parent_event]
        if row.spec.timing=='after_parent_complete' and (parent.outcome is None or parent.outcome.tag!='Completed'):
            return Block('conflict','child execution requires parent completion')
        return Event(row.id,row.spec.event_kind,self.state.profile,self.state.revision,row.spec.payload,row.parent_event)

    def resume_children(self,event_id):
        rec=self.state.occurrences[event_id]
        if rec.outcome is None or rec.outcome.tag!='AwaitingChildren':raise ValueError('parent is not waiting for child obligations')
        if rec.event.profile!=self.state.profile or rec.revision!=self.state.revision or rec.state_fingerprint!=state_fingerprint(self.state):
            return Outcome('Blocked',event_id,rec.committed,rec.excluded,rec.results,Block('stale_evidence','parent continuation context changed'))
        return self._run(Occurrence(rec.event,rec.plan,rec.revision,rec.settled,rec.committed,rec.excluded,rec.results,rec.evidence))
