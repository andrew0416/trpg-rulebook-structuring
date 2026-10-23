"""Cross-event model scheduler over the local root Machine.

Assumes trusted, complete footprints for guards, input decisions, effects,
observations and global invariants. This assumption is a source-refinement proof
obligation, not established by this scheduler. Dynamic emitted-child obligations
and explicit parent continuations are supported; source interpretation, unknown
future child footprints and persistent restore remain unresolved. External writes
through the underlying Machine are
rejected; all scheduled mutations must use this owner.
"""
from dataclasses import dataclass,replace
from collections.abc import Mapping
from . import root_machine as m
from . import root_resolution as r
from . import root_children as rc


@dataclass(frozen=True)
class Schedule:
    plan: m.Plan
    footprint: r.Footprint
    dependencies: tuple=()
    def __post_init__(self):
        if not isinstance(self.plan,m.Plan) or not isinstance(self.footprint,r.Footprint):
            raise TypeError('typed plan and complete footprint required')
        deps=tuple(self.dependencies)
        if any(type(d) is not str or not d for d in deps) or len(set(deps))!=len(deps):raise ValueError('distinct event dependency identities required')
        object.__setattr__(self,'dependencies',deps)
        for node in self.plan.nodes:
            for name in ('reads','writes'):
                if any(not any(m.covers(declared,actual) for declared in getattr(self.footprint,name)) for actual in getattr(node,name)):
                    raise ValueError('schedule underdeclares node '+name)
        for p in self.footprint.reads+self.footprint.writes:m.path(p)


@dataclass(frozen=True)
class Finding:
    tag: str
    detail: str


@dataclass(frozen=True)
class Record:
    schedule: Schedule
    event: m.Event
    projection: str


def projected(game,paths):
    rows=[]
    for p in sorted(set(paths)):
        value=game;found=True
        for key in p:
            if not isinstance(value,Mapping) or key not in value:
                found=False;break
            value=value[key]
        rows.append((p,'present',value) if found else (p,'absent'))
    return m.identity(tuple(rows))


def interferes(a,b):
    # Observational order (RNG/decision/event streams) is globally observable;
    # distinct labels alone do not establish commutation.
    return bool(a.observations and b.observations) or any(
        m.overlaps(x,y) for x in a.writes for y in b.reads+b.writes+b.observations
    ) or any(m.overlaps(x,y) for x in b.writes for y in a.reads+a.observations)


class Scheduler:
    def __init__(self,machine,invariant_reads=None):
        if not isinstance(machine,m.Machine):raise TypeError('typed local machine required')
        self.machine=machine;self._expected=machine.state;self._records={}
        # None is an unknown invariant dependency, not an empty set.
        if invariant_reads is None:
            self.invariant_reads=();self._invariants_known=not bool(machine.invariants)
        else:
            footprints=tuple(tuple(m.path(p) for p in row) for row in invariant_reads)
            if len(footprints)!=len(machine.invariants):raise ValueError('one declared read set per installed invariant required')
            self.invariant_reads=tuple(p for row in footprints for p in row);self._invariants_known=True

    def _fresh(self):
        if self.machine.state is not self._expected:
            return Finding('RejectedStaleOrMismatch','underlying state was changed or restored outside scheduler')
        return None

    def _footprint(self,schedule):
        return r.Footprint(schedule.footprint.reads+self.invariant_reads,schedule.footprint.writes,schedule.footprint.observations)

    def _projection(self,schedule):
        footprint=self._footprint(schedule)
        # Including writes preserves targets/parent container presence as well.
        return projected(self.machine.state.game,footprint.reads+footprint.writes)

    def _pending(self):
        return {key:rec for key,rec in self.machine.state.occurrences.items()
                if rec.outcome is None or rec.outcome.tag in ('AwaitingInput','AwaitingChildren','Blocked')}

    def check_new(self,schedule,event):
        if not isinstance(schedule,Schedule) or not isinstance(event,m.Event):raise TypeError('typed schedule/event required')
        fresh=self._fresh()
        if fresh:return fresh
        if event.profile!=self.machine.state.profile or schedule.plan.profile!=event.profile or event.kind!=schedule.plan.event_kind or event.expected_revision!=self.machine.state.revision:
            return Finding('RejectedStaleOrMismatch','profile, kind or revision mismatch')
        if event.id in self.machine.state.occurrences:return Finding('RejectedStaleOrMismatch','occurrence is not owned by this scheduler')
        deps=set(schedule.dependencies)
        emitted=self.machine.state.children.get(event.id)
        ancestors=self._ancestors(event.id) if emitted is not None else set()
        if emitted is not None:
            expected=self.machine.child_event(event.id)
            if isinstance(expected,m.Block):return Finding('BlockedDependency',expected.detail)
            if m.event_fingerprint(expected)!=m.event_fingerprint(event):return Finding('RejectedStaleOrMismatch','event differs from emitted obligation')
            sibling_issue=self._sibling_order(emitted)
            if sibling_issue:return sibling_issue
            deps.update(rc.child_id(emitted.parent_event,emitted.parent_node,k) for k in emitted.spec.after_siblings)
        elif event.parent is not None:deps.add(event.parent)
        frontier=self._unplanned_frontier(event.id)
        if frontier:return frontier
        if event.id in deps:return Finding('BlockedDependency','self dependency')
        for key in sorted(deps):
            rec=self.machine.state.occurrences.get(key)
            if rec is None:return Finding('BlockedDependency','unknown dependency: '+key)
            if rec.outcome is None or rec.outcome.tag!='Completed':
                return Finding('BlockedDependency','dependency not successfully settled: '+key)
        pending=self._pending()
        for key in sorted(pending):
            owner=self._records.get(key)
            if owner is None:return Finding('BlockedDependency','unowned pending occurrence: '+key)
            if key in ancestors and pending[key].outcome is not None and pending[key].outcome.tag=='AwaitingChildren':continue
            if not self._invariants_known:return Finding('BlockedDependency','global invariant read scope unknown')
            if interferes(self._footprint(owner.schedule),self._footprint(schedule)):
                return Finding('BlockedDependency','interference with unresolved event: '+key)
        return None

    def submit(self,schedule,event):
        if not isinstance(schedule,Schedule) or not isinstance(event,m.Event):raise TypeError('typed schedule/event required')
        fresh=self._fresh()
        if fresh:return fresh
        old=self._records.get(event.id)
        if old:
            if old.schedule is not schedule or m.event_fingerprint(old.event)!=m.event_fingerprint(event):
                return Finding('RejectedStaleOrMismatch','event identity reused with changed schedule/request')
            # Machine checks current profile before returning its exact receipt.
            return self.machine.submit(schedule.plan,event)
        issue=self.check_new(schedule,event)
        if issue:return issue
        pending=self._pending()
        ancestors=self._ancestors(event.id)
        outcome=self.machine.submit(schedule.plan,event)
        self._expected=self.machine.state
        if event.id in self.machine.state.occurrences:
            self._records[event.id]=Record(schedule,event,self._projection(schedule))
        # Independent continuation must actually preserve every pending projection.
        for key in pending:
            owner=self._records[key]
            if key in ancestors and pending[key].outcome is not None and pending[key].outcome.tag=='AwaitingChildren':
                self._records[key]=Record(owner.schedule,owner.event,self._projection(owner.schedule))
                continue
            if self._projection(owner.schedule)!=owner.projection:
                # A trusted footprint/invariant assumption was violated. Do not
                # manufacture rollback over a semantic prefix; quarantine owner.
                self._expected=None
                return Finding('RejectedIntegrity','declared independence violated; scheduler quarantined')
        return outcome

    def resumable(self,event_id):
        fresh=self._fresh()
        if fresh:return fresh
        owner=self._records.get(event_id)
        rec=self.machine.state.occurrences.get(event_id)
        if owner is None or rec is None:return Finding('RejectedStaleOrMismatch','unknown scheduler-owned event')
        if rec.event.profile!=self.machine.state.profile or rec.plan is not owner.schedule.plan or m.event_fingerprint(rec.event)!=m.event_fingerprint(owner.event):
            return Finding('RejectedStaleOrMismatch','event, plan or profile changed')
        if rec.outcome is None or rec.outcome.tag!='AwaitingInput':return Finding('BlockedDependency','only outstanding input can resume')
        if self._projection(owner.schedule)!=owner.projection:
            return Finding('RejectedStaleOrMismatch','pending read/write projection changed')
        frontier=self._continuation_frontier(event_id)
        if frontier:return frontier
        return None

    def resume(self,event_id,answers):
        issue=self.resumable(event_id)
        if issue:return issue
        owner=self._records[event_id];snapshot=self.machine.state
        rec=snapshot.occurrences[event_id]
        request=rec.outcome.obligation
        if not isinstance(answers,Mapping) or set(answers)!={request.key}:
            return Finding('RejectedInput','answer only the outstanding request')
        try:m.freeze(answers)
        except (TypeError,ValueError):return Finding('RejectedInput','input does not use immutable root values')
        # Rebind execution bookkeeping only after the declared projection proof.
        # Original Event, expected_revision, payload and node receipts are intact.
        ledger=dict(snapshot.occurrences)
        ledger[event_id]=replace(rec,revision=snapshot.revision,state_fingerprint=m.state_fingerprint(snapshot))
        self.machine.state=m.Snapshot(snapshot.profile,snapshot.revision,snapshot.game,ledger,snapshot.children)
        self._expected=self.machine.state
        outcome=self.machine.resume(event_id,answers)
        self._expected=self.machine.state
        self._records[event_id]=Record(owner.schedule,owner.event,self._projection(owner.schedule))
        self._refresh_ancestors(event_id)
        return outcome

    def _ancestors(self,event_id):
        found=set();row=self.machine.state.children.get(event_id)
        while row is not None:
            if row.parent_event in found:raise ValueError('causal cycle')
            found.add(row.parent_event);row=self.machine.state.children.get(row.parent_event)
        return found

    def _sibling_order(self,row):
        siblings=[x for x in self.machine.state.children.values() if x.parent_event==row.parent_event and x.id!=row.id and x.status!='completed']
        batch={x.spec.key:x.spec for x in self.machine.state.children.values() if x.parent_event==row.parent_event and x.parent_node==row.parent_node}
        deps={k:set(s.after_siblings) for k,s in batch.items()}
        for _ in batch:
            for k in deps:deps[k]|=set().union(*(deps[x] for x in tuple(deps[k])))
        for peer in siblings:
            if peer.parent_node!=row.parent_node:return Finding('BlockedDependency','cross-batch sibling relation unrefined')
            if row.spec.key in deps[peer.spec.key] or peer.spec.key in deps[row.spec.key]:continue
            if peer.spec.key in row.spec.independent_siblings and row.spec.key in peer.spec.independent_siblings:continue
            return Finding('BlockedDependency','sibling ordering/independence unrefined')
        return None

    def _refresh_ancestors(self,event_id):
        for key in self._ancestors(event_id):
            rec=self.machine.state.occurrences.get(key);owner=self._records.get(key)
            if rec is not None and owner is not None and rec.outcome is not None and rec.outcome.tag=='AwaitingChildren':
                self._records[key]=Record(owner.schedule,owner.event,self._projection(owner.schedule))

    def resume_children(self,event_id):
        fresh=self._fresh()
        if fresh:return fresh
        owner=self._records.get(event_id);rec=self.machine.state.occurrences.get(event_id)
        if owner is None or rec is None:return Finding('RejectedStaleOrMismatch','unknown scheduler-owned parent')
        if rec.outcome is None or rec.outcome.tag!='AwaitingChildren':return Finding('BlockedDependency','parent not waiting for children')
        if rec.plan is not owner.schedule.plan or rec.event.profile!=self.machine.state.profile or m.event_fingerprint(rec.event)!=m.event_fingerprint(owner.event):return Finding('RejectedStaleOrMismatch','parent identity changed')
        if self._projection(owner.schedule)!=owner.projection:return Finding('RejectedStaleOrMismatch','parent projection changed outside authorized child execution')
        frontier=self._continuation_frontier(event_id)
        if frontier:return frontier
        snapshot=self.machine.state;ledger=dict(snapshot.occurrences)
        ledger[event_id]=replace(rec,revision=snapshot.revision,state_fingerprint=m.state_fingerprint(snapshot))
        self.machine.state=m.Snapshot(snapshot.profile,snapshot.revision,snapshot.game,ledger,snapshot.children)
        self._expected=self.machine.state
        outcome=self.machine.resume_children(event_id)
        self._expected=self.machine.state
        self._records[event_id]=Record(owner.schedule,owner.event,self._projection(owner.schedule))
        self._refresh_ancestors(event_id)
        return outcome

    def _unplanned_frontier(self,event_id):
        # The same conservative frontier applies to first delivery AND both
        # continuation APIs. Existing ownership is not proof of independence.
        lineage=[];branch=self.machine.state.children.get(event_id)
        while branch is not None:
            lineage.append(branch);branch=self.machine.state.children.get(branch.parent_event)
        for row in self.machine.state.children.values():
            if row.status=='completed' or row.id in self.machine.state.occurrences:continue
            if row.id==event_id or row.parent_event==event_id or event_id in self._ancestors(row.id):continue
            allowed=False
            for branch in lineage:
                if branch.id==row.id:allowed=True;break
                if branch.parent_event!=row.parent_event or branch.parent_node!=row.parent_node:continue
                batch={x.spec.key:x.spec for x in self.machine.state.children.values() if x.parent_event==row.parent_event and x.parent_node==row.parent_node}
                deps={k:set(v.after_siblings) for k,v in batch.items()}
                for _ in batch:
                    for k in deps:deps[k]|=set().union(*(deps[x] for x in tuple(deps[k])))
                # A source-ordered future sibling cannot interfere yet. A
                # predecessor must actually finish, not just carry an edge.
                allowed=branch.spec.key in deps[row.spec.key] or (row.spec.key in branch.spec.independent_siblings and branch.spec.key in row.spec.independent_siblings)
                if allowed:break
            if not allowed:return Finding('BlockedDependency','outstanding unplanned child responsibility: '+row.id)
        return None

    def _remaining_footprint(self,event_id):
        owner=self._records[event_id];rec=self.machine.state.occurrences[event_id]
        remaining=[n for n in owner.schedule.plan.nodes if n.id not in rec.settled]
        # Schedule-level reads also cover selection/guard/context dependencies
        # that need not appear in any Node.reads. Retain them until execution is
        # finished. Additional writes likewise cannot be erased by projection.
        node_writes={p for n in owner.schedule.plan.nodes for p in n.writes}
        extras=tuple(p for p in owner.schedule.footprint.writes if p not in node_writes)
        return r.Footprint((owner.schedule.footprint.reads if remaining else ())+self.invariant_reads,
                           tuple(p for n in remaining for p in n.writes)+(extras if remaining else ()),
                           owner.schedule.footprint.observations if remaining else ())

    def _continuation_frontier(self,event_id):
        unknown=self._unplanned_frontier(event_id)
        if unknown:return unknown
        ancestors=self._ancestors(event_id)
        own=self._remaining_footprint(event_id)
        for key,rec in self._pending().items():
            if key==event_id:continue
            owner=self._records.get(key)
            if owner is None:return Finding('BlockedDependency','unowned pending occurrence: '+key)
            if key in ancestors and rec.outcome is not None and rec.outcome.tag=='AwaitingChildren':continue
            if not self._invariants_known:return Finding('BlockedDependency','global invariant read scope unknown')
            if interferes(own,self._remaining_footprint(key)):
                return Finding('BlockedDependency','continuation interferes with pending event: '+key)
        return None
