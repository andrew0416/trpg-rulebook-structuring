"""Immutable child obligations; source refinements, not names, justify ownership/order.

No executable child Plan or registration is carried: every child still requires
separate admission. 'IndependentLifetime' includes separately owned deferred
occurrences, not only enduring effects. Persistence is in-process only.
"""
from dataclasses import dataclass,field,replace
from types import MappingProxyType
import json,hashlib

if __package__:
    from . import resolution_transaction as _FINGERPRINTS
else:
    import resolution_transaction as _FINGERPRINTS

def _text(x):
    if type(x) is not str or not x:raise ValueError('nonempty child identity/scope required')
    return x

def _names(xs):
    if type(xs) not in (tuple,list):raise TypeError('explicit tuple/list required')
    out=tuple(_text(x) for x in xs)
    if len(set(out))!=len(out):raise ValueError('duplicate child scope identity')
    return out

def freeze(x):
    if x is None or type(x) in (str,int,bool):return x
    if type(x) in (tuple,list):return tuple(freeze(v) for v in x)
    if type(x) in (dict,MappingProxyType):
        if any(type(k) is not str or not k for k in x):raise ValueError('nonempty JSON keys required')
        return MappingProxyType({k:freeze(v) for k,v in x.items()})
    raise TypeError('immutable integer JSON required')

def plain(x):
    if type(x) is MappingProxyType:return {k:plain(v) for k,v in x.items()}
    if type(x) is tuple:return [plain(v) for v in x]
    return x

def child_id(parent,node,key):
    values=tuple(_text(x) for x in (parent,node,key))
    return 'child:'+_FINGERPRINTS.json_fingerprint(values, sort_keys=False, compact=True, allow_nan=True)

@dataclass(frozen=True)
class ChildSpec:
    key: str
    event_kind: str
    payload: object
    barrier: str
    completion_owner: str
    scope: str
    source_refs: tuple
    timing: str  # after_emission | after_parent_complete | unknown
    before_nodes: tuple=()
    independent_nodes: tuple=()
    after_siblings: tuple=()
    independent_siblings: tuple=()
    def __post_init__(self):
        for v in (self.key,self.event_kind,self.completion_owner,self.scope):_text(v)
        if self.barrier not in ('before_parent_complete','independent_lifetime','unknown'):raise ValueError('explicit barrier required')
        if self.timing not in ('after_emission','after_parent_complete','unknown'):raise ValueError('explicit dispatch timing required')
        if self.barrier=='before_parent_complete' and self.timing=='after_parent_complete':raise ValueError('cyclic parent/child completion dependency')
        for name in ('source_refs','before_nodes','independent_nodes','after_siblings','independent_siblings'):object.__setattr__(self,name,_names(getattr(self,name)))
        if not self.source_refs:raise ValueError('emission refinement references required')
        if set(self.before_nodes)&set(self.independent_nodes):raise ValueError('conflicting child/node order declarations')
        if self.before_nodes and self.timing=='after_parent_complete':raise ValueError('parent node waits for post-completion child cycle')
        if self.key in self.after_siblings or self.key in self.independent_siblings or set(self.after_siblings)&set(self.independent_siblings):raise ValueError('invalid sibling relation')
        object.__setattr__(self,'payload',freeze(self.payload))

@dataclass(frozen=True)
class ChildRecord:
    id: str
    parent_event: str
    parent_node: str
    spec: ChildSpec
    status: str='outstanding'
    def __post_init__(self):
        for v in (self.id,self.parent_event,self.parent_node):_text(v)
        if type(self.spec) is not ChildSpec:raise TypeError('typed child spec required')
        if self.id!=child_id(self.parent_event,self.parent_node,self.spec.key):raise ValueError('incorrect causal child identity')
        if self.status not in ('outstanding','running','awaiting_input','awaiting_children','blocked','rejected','completed'):raise ValueError('unknown child status')

@dataclass(frozen=True)
class NeedChildren:
    child_ids: tuple
    reason: str
    def __post_init__(self):
        object.__setattr__(self,'child_ids',_names(self.child_ids));_text(self.reason)


def sync(records,occurrences):
    out={}
    for key,row in records.items():
        occurrence=occurrences.get(key)
        status='outstanding' if occurrence is None else 'running' if occurrence.outcome is None else {'AwaitingInput':'awaiting_input','AwaitingChildren':'awaiting_children','Completed':'completed','Blocked':'blocked','Rejected':'rejected'}[occurrence.outcome.tag]
        out[key]=replace(row,status=status)
    return out

