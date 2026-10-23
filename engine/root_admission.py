"""Scoped source-refinement admission and bridge to the structural root machine.

Trust starts in operator-installed policy pins and reviewed Python adapters. Hashes
check freshness, not natural-language fidelity. No production certificates ship
with this module. Synthetic policies issue ModelAdmitted, never SourceReady.
This is an in-process engineering boundary, not a Python security sandbox.
"""
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping
from types import MappingProxyType
import hashlib
import inspect
from . import root_machine as rm
from . import root_resolution as rr
from . import root_scheduler as rs
from . import root_inputs as ri
from . import root_children as rc
from . import resolution_transaction as _FINGERPRINTS

CHAIN = frozenset(('authority','source','semantics','candidate_closure',
                   'resolution_laws','adapter_refinement','independent_evidence','review'))


def digest(value): return _FINGERPRINTS.json_fingerprint(rm.thaw(value), sort_keys=True, compact=True, allow_nan=True)


def _text(x):
    if type(x) is not str or not x: raise ValueError('nonempty identity required')
    return x


def _sha(x):
    if type(x) is not str or len(x)!=64 or any(c not in '0123456789abcdef' for c in x):
        raise ValueError('canonical SHA256 required')
    return x


def context_fingerprint(snapshot,event):
    # Include occurrence ledger: pending parents/decisions affect applicability.
    ledger={k:dict(event=rm.event_fingerprint(v.event),plan=v.plan.id,revision=v.revision,
        settled=v.settled,committed=v.committed,excluded=v.excluded,results=v.results,
        evidence=v.evidence,outcome=None if v.outcome is None else dict(tag=v.outcome.tag,
        obligation=repr(v.outcome.obligation)),state_fingerprint=v.state_fingerprint)
        for k,v in snapshot.occurrences.items()}
    return digest((rm.state_fingerprint(snapshot),rm.event_fingerprint(event),ledger,child_ledger(snapshot)))


def child_ledger(snapshot):
    return {key:dict(id=row.id,parent_event=row.parent_event,parent_node=row.parent_node,
        status=row.status,spec={name:getattr(row.spec,name) for name in row.spec.__dataclass_fields__})
        for key,row in snapshot.children.items()}


@dataclass(frozen=True)
class ChildRoute:
    parent_node: str
    emission_key: str
    certificate_id: str
    event_kind: str
    barrier: str
    timing: str
    def __post_init__(self):
        for value in (self.parent_node,self.emission_key,self.certificate_id,self.event_kind,self.barrier,self.timing):_text(value)
    def payload(self):return {name:getattr(self,name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class Certificate:
    id: str
    mode: str  # source or synthetic
    profile_hash: str
    catalog_hash: str
    interface: str
    event_kind: str
    aspects: tuple
    source_refs: tuple
    propositions: tuple
    support_domain: str
    adapter_id: str
    artifacts: object  # relative file -> SHA256, includes all reviewed dependencies
    chain: object  # CHAIN role -> nonempty artifact paths
    positive_cases: tuple
    negative_cases: tuple
    child_routes: tuple=()  # exact emission site/kind/barrier/timing -> separately reviewed child certificate

    def __post_init__(self):
        for name in ('id','interface','event_kind','support_domain','adapter_id'): _text(getattr(self,name))
        for name in ('profile_hash','catalog_hash'): _sha(getattr(self,name))
        if self.mode not in ('source','synthetic'): raise ValueError('explicit evidence mode required')
        for name in ('aspects','source_refs','propositions','positive_cases','negative_cases'):
            values=tuple(_text(x) for x in getattr(self,name))
            if not values or len(set(values))!=len(values): raise ValueError('nonempty distinct '+name+' required')
            object.__setattr__(self,name,values)
        routes=tuple(self.child_routes)
        if any(type(x) is not ChildRoute for x in routes):raise TypeError('typed child authority routes required')
        keys=[(x.parent_node,x.emission_key,x.certificate_id,x.event_kind,x.barrier,x.timing) for x in routes]
        if len(set(keys))!=len(keys):raise ValueError('duplicate child authority route')
        object.__setattr__(self,'child_routes',routes)
        artifacts=dict(self.artifacts)
        for name,sha in artifacts.items():
            q=Path(name)
            if not name or q.is_absolute() or '..' in q.parts or ':' in name: raise ValueError('relative artifact path required')
            _sha(sha)
        chain={k:tuple(v) for k,v in self.chain.items()}
        if set(chain)!=CHAIN or any(not v or not set(v)<=artifacts.keys() for v in chain.values()):
            raise ValueError('all eight evidence-chain roles must reference pinned artifacts')
        object.__setattr__(self,'artifacts',rm.freeze(artifacts))
        object.__setattr__(self,'chain',rm.freeze(chain))

    def fingerprint(self): return digest(self.payload())
    def payload(self): return {name:tuple(x.payload() for x in self.child_routes) if name=='child_routes' else getattr(self,name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class TrustedPolicy:
    id: str
    mode: str
    certificates: object  # operator-configured exact certificate id -> digest
    def __post_init__(self):
        _text(self.id)
        if self.mode not in ('source','synthetic'): raise ValueError('policy mode required')
        pins=dict(self.certificates)
        for key,value in pins.items(): _text(key);_sha(value)
        object.__setattr__(self,'certificates',MappingProxyType(pins))


@dataclass(frozen=True)
class Adapter:
    id: str
    support: object  # (snapshot,event)->rr.Predicate
    derive: object  # (snapshot,event)->rr.ResolutionRequest
    build: object  # (AspectPlan,snapshot,event)->rm.Node, one atomic aspect node
    input_request: object=None  # optional reviewed (binding,pending,snapshot,event)->Choice/RollRequest
    child_registration: object=None  # reviewed (ChildRecord,snapshot,parent_event)->certificate id
    def __post_init__(self):
        _text(self.id)
        if any(not inspect.isfunction(f) for f in (self.support,self.derive,self.build)+tuple(x for x in (self.input_request,self.child_registration) if x is not None)):
            raise TypeError('reviewed module functions required, not caller callbacks')


@dataclass(frozen=True)
class Finding:
    tag: str
    detail: str


@dataclass(frozen=True,eq=False)
class Registration:
    certificate_id: str


@dataclass(frozen=True,eq=False)
class Ticket:
    tag: str
    event_id: str
    context_hash: str
    request_hash: str
    resolution_hash: str
    certificate_hash: str


class Registry:
    def __init__(self,root,policy,adapters=()):
        if not isinstance(policy,TrustedPolicy): raise TypeError('trusted policy required')
        self.root=Path(root).resolve();self.policy=policy
        adapters=tuple(adapters)
        if any(not isinstance(a,Adapter) for a in adapters): raise TypeError('typed adapter required')
        if len({a.id for a in adapters})!=len(adapters): raise ValueError('duplicate adapter identity')
        self._adapters={a.id:a for a in adapters};self._registrations={}

    def _check(self,certificate):
        if not isinstance(certificate,Certificate): return Finding('PendingEvidence','typed certificate missing')
        if certificate.mode!=self.policy.mode: return Finding('RejectedIntegrity','source/synthetic policy mismatch')
        if self.policy.certificates.get(certificate.id)!=certificate.fingerprint():
            return Finding('PendingEvidence','certificate not accepted by installed trusted policy')
        adapter=self._adapters.get(certificate.adapter_id)
        if adapter is None:return Finding('PendingEvidence','reviewed adapter not installed')
        try:
            pinned={}
            for rel,sha in certificate.artifacts.items():
                p=(self.root/rel).resolve()
                if not p.is_relative_to(self.root): return Finding('RejectedIntegrity','artifact escapes root')
                if hashlib.sha256(p.read_bytes()).hexdigest()!=sha:
                    return Finding('RejectedIntegrity','stale artifact: '+rel)
                pinned[p]=sha
            # All actual factory entrypoints must be among adapter-refinement pins.
            allowed={(self.root/p).resolve() for p in certificate.chain['adapter_refinement']}
            for callback in (adapter.support,adapter.derive,adapter.build)+tuple(x for x in (adapter.input_request,adapter.child_registration) if x is not None):
                code=Path(inspect.getsourcefile(callback) or '').resolve()
                if code not in allowed or code not in pinned or callback.__closure__:
                    return Finding('RejectedIntegrity','unreviewed adapter entrypoint or closure')
                module=inspect.getmodule(callback)
                if module is None or getattr(module,callback.__name__,None) is not callback:
                    return Finding('RejectedIntegrity','adapter must be the reviewed module-level function')
        except (OSError,TypeError,ValueError) as exc:
            return Finding('RejectedIntegrity',type(exc).__name__+': '+str(exc))
        return adapter

    def verify_registration(self,certificate):
        checked=self._check(certificate)
        if isinstance(checked,Finding):return checked
        handle=Registration(certificate.id)
        self._registrations[handle]=(certificate,checked)
        return handle

    def checked(self,handle):
        if handle not in self._registrations:return Finding('PendingEvidence','unknown registration handle')
        certificate,adapter=self._registrations[handle]
        check=self._check(certificate)
        return check if isinstance(check,Finding) else (certificate,adapter)


@dataclass(frozen=True,eq=False)
class PendingInput:
    event_id: str
    request: object


class Runtime:
    """Registry-authorized preparation; execution tickets bind the exact request.

    The application supplies its own Machine. Existing Engine does not call this
    bridge yet. Authenticated inputs and conservative independent scheduling are
    supported. Child emissions require separate scoped admission. Whole-source semantics remain open.
    """
    def __init__(self,registry,machine,principals=(),invariant_reads=None):
        if not isinstance(registry,Registry) or not isinstance(machine,rm.Machine): raise TypeError('typed registry and machine required')
        self.registry=registry;self.machine=machine;self._tickets={};self._delivered={};self._prepared={}
        self.scheduler=rs.Scheduler(machine,invariant_reads)
        self._schedules={};self._input_pending={};self._input_by_binding={}
        self._child_tickets={}
        self._principals=tuple(principals)
        if any(type(p) is not ri.Principal for p in self._principals) or len({p.id for p in self._principals})!=len(self._principals):
            raise ValueError('distinct authenticated transport principals required')

    def prepare(self,handle,event):
        if not isinstance(event,rm.Event):raise TypeError('typed event required')
        row=self.machine.state.children.get(event.id)
        if row is not None:
            parent_ticket=self._prepared.get(row.parent_event)
            if parent_ticket is None:return Finding('RejectedIntegrity','child parent has no admitted ticket')
            result=self.prepare_child(parent_ticket,row.id)
            if isinstance(result,Ticket):
                issued_handle,issued_event,_=self._tickets[result]
                if issued_handle is not handle or rm.event_fingerprint(issued_event)!=rm.event_fingerprint(event):
                    return Finding('RejectedIntegrity','direct child request differs from reviewed child route')
            return result
        return self._prepare(handle,event)

    def _prepare(self,handle,event):
        checked=self.registry.checked(handle)
        if isinstance(checked,Finding):return checked
        cert,adapter=checked;snapshot=self.machine.state
        if not isinstance(event,rm.Event):raise TypeError('typed event required')
        if event.profile!=cert.profile_hash or snapshot.profile!=cert.profile_hash or event.kind!=cert.event_kind:
            return Finding('RejectedStaleOrMismatch','profile or event kind mismatch')
        previous=self._prepared.get(event.id)
        if previous is not None:
            old_handle,old_event,old_plan=self._tickets[previous]
            if old_handle is not handle or rm.event_fingerprint(old_event)!=rm.event_fingerprint(event):
                return Finding('RejectedStaleOrMismatch','event identity reused with different registration or request')
            occurrence=snapshot.occurrences.get(event.id)
            if previous in self._delivered:
                if occurrence is None or occurrence.plan is not old_plan or rm.event_fingerprint(occurrence.event)!=rm.event_fingerprint(event):
                    return Finding('RejectedStaleOrMismatch','delivered occurrence ledger was replaced or restored')
            elif context_fingerprint(snapshot,event)!=previous.context_hash:
                return Finding('RejectedStaleOrMismatch','prepared request context changed')
            return previous
        if event.expected_revision!=snapshot.revision or event.id in snapshot.occurrences:
            return Finding('RejectedStaleOrMismatch','revision mismatch or occurrence owned by another executor')
        context=context_fingerprint(snapshot,event)
        try:
            supported=adapter.support(snapshot,event)
            if not isinstance(supported,rr.Predicate):return Finding('RejectedIntegrity','typed support predicate required')
            if supported.truth is rr.Truth.FALSE:return Finding('OutsideSupportedDomain',cert.support_domain)
            if supported.truth is rr.Truth.UNKNOWN:return Finding('PendingContext',supported.obligation)
            request=adapter.derive(snapshot,event)
            if not isinstance(request,rr.ResolutionRequest):return Finding('RejectedIntegrity','typed derived request required')
            if (request.event_id,request.event_kind,request.profile_hash,request.catalog_hash,request.context_hash)!=(event.id,event.kind,cert.profile_hash,cert.catalog_hash,context):
                return Finding('RejectedStaleOrMismatch','derived request is not bound to exact event and context')
            if set(request.aspects)!=set(cert.aspects) or any(c.aspect not in cert.aspects for c in request.clauses):
                return Finding('RejectedIntegrity','request exceeds reviewed aspects')
            if any(not c.source_refs or not set(c.source_refs)<=set(cert.source_refs) for c in request.clauses):
                return Finding('RejectedIntegrity','candidate source outside certificate')
            witnesses=tuple(x.witness_ref for group in (request.overrides,request.laws,request.aspect_orders,request.independences) for x in group)
            if not set(witnesses)<=set(cert.source_refs):
                return Finding('RejectedIntegrity','precedence, composition or independence witness outside certificate')
            resolution=rr.resolve(request)
            if resolution.tag=='Pending':return Finding('PendingResolution',rr.canonical(resolution.obligations))
            if resolution.tag=='Excluded':return Finding('ExcludedBySelectedSource','all reviewed candidates excluded')
            nodes=[]
            for aspect in resolution.aspects:
                node=adapter.build(aspect,snapshot,event)
                if not isinstance(node,rm.Node) or node.id!=aspect.aspect:
                    return Finding('RejectedIntegrity','one typed atomic node per resolved aspect required')
                if set(node.reads)!=set(aspect.footprint.reads) or set(node.writes)!=set(aspect.footprint.writes):
                    return Finding('RejectedIntegrity','runtime footprint differs from resolved aspect')
                predecessors={a for a,b in resolution.dependencies if b==aspect.aspect}
                if set(node.after)!=predecessors:return Finding('RejectedIntegrity','runtime order differs from resolution')
                nodes.append(node)
            plan=rm.Plan('admitted:'+rr.fingerprint((request,resolution)),cert.profile_hash,event.kind,tuple(nodes),
                'source_refinement_candidate' if cert.mode=='source' else 'model_experiment',cert.source_refs)
            issue=rm.validate_plan(plan)
            if issue:return Finding('PendingRefinement',issue.detail)
            schedule=rs.Schedule(plan,resolution.footprint)
            sched_issue=self.scheduler.check_new(schedule,event)
            if sched_issue:return Finding('PendingContext' if sched_issue.tag=='BlockedDependency' else sched_issue.tag,sched_issue.detail)
        except Exception as exc:return Finding('PendingRefinement',type(exc).__name__+': '+str(exc))
        # Trusted factories are required pure; detectable mutation invalidates admission.
        if self.machine.state is not snapshot or context_fingerprint(self.machine.state,event)!=context:
            return Finding('RejectedIntegrity','adapter changed preparation context')
        ticket=Ticket('ScopedSourceReady' if cert.mode=='source' else 'ModelAdmitted',event.id,context,
            rr.fingerprint(request),rr.fingerprint(resolution),cert.fingerprint())
        self._tickets[ticket]=(handle,event,plan)
        self._schedules[ticket]=schedule
        self._prepared[event.id]=ticket
        return ticket

    def submit(self,ticket):
        if ticket not in self._tickets:return Finding('RejectedIntegrity','unknown ticket')
        handle,event,plan=self._tickets[ticket]
        checked=self.registry.checked(handle)
        if isinstance(checked,Finding):return checked
        if checked[0].fingerprint()!=ticket.certificate_hash:return Finding('RejectedIntegrity','certificate changed')
        lineage=self._parent_evidence(event.id)
        if isinstance(lineage,Finding):return lineage
        if event.profile!=self.machine.state.profile or plan.profile!=self.machine.state.profile:
            return rm.Outcome('Rejected',event.id,obligation=rm.Block('stale_evidence','profile mismatch'))
        if ticket in self._delivered:
            occurrence=self.machine.state.occurrences.get(event.id)
            if occurrence is None or occurrence.plan is not plan or rm.event_fingerprint(occurrence.event)!=rm.event_fingerprint(event):
                return Finding('RejectedStaleOrMismatch','delivered occurrence ledger was replaced or restored')
            # Reuse Machine identity checks, so profile changes cannot return stale success.
            return self.scheduler.submit(self._schedules[ticket],event)
        if context_fingerprint(self.machine.state,event)!=ticket.context_hash:
            return Finding('RejectedStaleOrMismatch','state, ledger or event changed since admission')
        outcome=self.scheduler.submit(self._schedules[ticket],event)
        self._delivered[ticket]=outcome
        return outcome

    def _parent_evidence(self,event_id):
        row=self.machine.state.children.get(event_id)
        if row is None:return None
        parent_ticket=self._prepared.get(row.parent_event)
        if parent_ticket is None:return Finding('RejectedIntegrity','child parent has no admitted ticket')
        checked=self._executed(parent_ticket)
        return checked if isinstance(checked,Finding) else None

    def _executed(self,ticket):
        if ticket not in self._tickets or ticket not in self._delivered:
            return Finding('RejectedIntegrity','operation requires executed admitted ticket')
        handle,event,plan=self._tickets[ticket]
        checked=self.registry.checked(handle)
        if isinstance(checked,Finding):return checked
        if checked[0].fingerprint()!=ticket.certificate_hash:
            return Finding('RejectedIntegrity','certificate changed')
        fresh=self.scheduler._fresh()
        if fresh:return Finding(fresh.tag,fresh.detail)
        rec=self.machine.state.occurrences.get(event.id)
        if rec is None or rec.plan is not plan or rm.event_fingerprint(rec.event)!=rm.event_fingerprint(event) or event.profile!=self.machine.state.profile:
            return Finding('RejectedStaleOrMismatch','executed occurrence identity changed')
        lineage=self._parent_evidence(event.id)
        return lineage if isinstance(lineage,Finding) else checked

    def get_children(self,ticket):
        checked=self._executed(ticket)
        if isinstance(checked,Finding):return checked
        event=self._tickets[ticket][1]
        return tuple(row for row in self.machine.state.children.values() if row.parent_event==event.id)

    def prepare_child(self,parent_ticket,child_id):
        checked=self._executed(parent_ticket)
        if isinstance(checked,Finding):return checked
        cert,adapter=checked
        handle,parent_event,parent_plan=self._tickets[parent_ticket]
        before=self.machine.state
        row=before.children.get(child_id)
        if row is None or row.parent_event!=parent_event.id or row.parent_node not in before.occurrences[parent_event.id].committed:
            return Finding('RejectedIntegrity','child is not a committed emission of this parent')
        if not set(row.spec.source_refs)<=set(cert.source_refs):
            return Finding('RejectedIntegrity','emission source outside parent certificate')
        if adapter.child_registration is None:
            return Finding('PendingRefinement','no reviewed child registration factory')
        context=context_fingerprint(before,parent_event)
        try:selected=adapter.child_registration(row,before,parent_event)
        except Exception as exc:return Finding('PendingRefinement',type(exc).__name__+': '+str(exc))
        if self.machine.state is not before or context_fingerprint(before,parent_event)!=context:
            return Finding('RejectedIntegrity','child factory changed execution context')
        if type(selected) is not str or not selected:
            return Finding('RejectedIntegrity','child factory must select a certificate identity')
        route=ChildRoute(row.parent_node,row.spec.key,selected,row.spec.event_kind,row.spec.barrier,row.spec.timing)
        if route not in cert.child_routes:
            return Finding('RejectedIntegrity','child route outside reviewed parent authority')
        registrations=[key for key,(c,a) in self.registry._registrations.items() if c.id==selected]
        if not registrations:return Finding('PendingEvidence','child requires its own verified registration')
        child_handle=registrations[0]
        child_checked=self.registry.checked(child_handle)
        if isinstance(child_checked,Finding):return child_checked
        child_cert,_=child_checked
        if child_cert.mode!=cert.mode or child_cert.profile_hash!=cert.profile_hash or child_cert.catalog_hash!=cert.catalog_hash or child_cert.event_kind!=row.spec.event_kind:
            return Finding('RejectedIntegrity','child certificate mode, profile, catalog or kind mismatch')
        if not set(row.spec.source_refs)<=set(child_cert.source_refs):
            return Finding('RejectedIntegrity','child certificate does not review emission semantics')
        cached=self._child_tickets.get((parent_ticket,child_id))
        if cached is not None:
            old_handle,old_event,_=self._tickets[cached]
            return self._prepare(old_handle,old_event)
        event=self.machine.child_event(child_id)
        if isinstance(event,rm.Block):return Finding('PendingContext',event.detail)
        ticket=self._prepare(child_handle,event)
        if isinstance(ticket,Ticket):self._child_tickets[(parent_ticket,child_id)]=ticket
        return ticket

    def resume_children(self,parent_ticket):
        checked=self._executed(parent_ticket)
        if isinstance(checked,Finding):return checked
        event=self._tickets[parent_ticket][1]
        outcome=self.scheduler.resume_children(event.id)
        if isinstance(outcome,rs.Finding):return Finding(outcome.tag,outcome.detail)
        self._delivered[parent_ticket]=outcome
        return outcome

    def _binding(self,ticket):
        handle,event,plan=self._tickets[ticket]
        issue=self.scheduler.resumable(event.id)
        if issue:return Finding(issue.tag,issue.detail)
        rec=self.machine.state.occurrences[event.id]
        schedule=self._schedules[ticket]
        context=digest((event_fingerprint_for_input(event),plan.id,
            self.scheduler._projection(schedule),rec.settled,rec.committed,rec.excluded,
            rec.evidence,rec.outcome.obligation.key,rec.outcome.obligation.kind,child_ledger(self.machine.state)))
        return ri.Binding(event.id,digest(event_fingerprint_for_input(event)),event.profile,rec.revision,context)

    def get_input(self,ticket):
        if ticket not in self._tickets or ticket not in self._delivered:return Finding('RejectedIntegrity','input requires an executed admitted ticket')
        handle,event,plan=self._tickets[ticket]
        checked=self._executed(ticket)
        if isinstance(checked,Finding):return checked
        cert,adapter=checked
        if adapter.input_request is None:return Finding('PendingRefinement','no source-scoped input request factory')
        binding=self._binding(ticket)
        if isinstance(binding,Finding):return binding
        key=(ticket,ri.digest(binding.payload()))
        if key in self._input_by_binding:return self._input_by_binding[key]
        rec=self.machine.state.occurrences[event.id];pending=rec.outcome.obligation
        before=self.machine.state
        try:request=adapter.input_request(binding,pending,before,event)
        except Exception as exc:return Finding('PendingRefinement',type(exc).__name__+': '+str(exc))
        expected=ri.ChoiceRequest if pending.kind=='source_choice' else ri.RollRequest
        if type(request) is not expected or request.binding!=binding or request.mode!=cert.mode or not set(request.source_refs)<=set(cert.source_refs):
            return Finding('RejectedIntegrity','input request kind, binding, mode or source exceeds admitted scope')
        if self.machine.state is not before:return Finding('RejectedIntegrity','input factory changed execution state')
        policy=ri.TrustedPolicy('admitted:'+cert.id,cert.mode,{request.id:ri.request_fingerprint(request)})
        broker=ri.Broker(policy,self._principals);input_handle=broker.register(request)
        if isinstance(input_handle,ri.Finding):return Finding(input_handle.code,input_handle.detail)
        public=PendingInput(event.id,request)
        self._input_pending[public]=dict(ticket=ticket,broker=broker,handle=input_handle,binding=binding,outcome=None)
        self._input_by_binding[key]=public
        return public

    def answer(self,pending,principal,value):
        record=self._input_pending.get(pending)
        if record is None:return Finding('RejectedIntegrity','input handle not issued by runtime')
        ticket=record['ticket'];handle,event,plan=self._tickets[ticket]
        checked=self._executed(ticket)
        if isinstance(checked,Finding):return checked
        fresh=self.scheduler._fresh()
        if fresh:return Finding(fresh.tag,fresh.detail)
        if event.profile!=self.machine.state.profile:return Finding('RejectedStaleOrMismatch','input profile changed')
        if record['outcome'] is None:
            current=self._binding(ticket)
            if isinstance(current,Finding):return current
        else:current=record['binding']  # idempotent historical answer; never executes again
        broker=record['broker'];input_handle=record['handle']
        receipt=broker.accept(input_handle,principal,value,current)
        if isinstance(receipt,ri.Finding):return Finding(receipt.code,receipt.detail)
        accepted=broker.validate_receipt(input_handle,receipt,current)
        if isinstance(accepted,ri.Finding):return Finding(accepted.code,accepted.detail)
        if record['outcome'] is not None:return record['outcome']
        request=self.machine.state.occurrences[event.id].outcome.obligation
        outcome=self.scheduler.resume(event.id,{request.key:accepted})
        if isinstance(outcome,rs.Finding):return Finding(outcome.tag,outcome.detail)
        record['outcome']=outcome
        self._delivered[ticket]=outcome
        return outcome


def event_fingerprint_for_input(event):
    return rm.event_fingerprint(event)
