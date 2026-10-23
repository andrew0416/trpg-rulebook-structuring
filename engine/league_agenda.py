"""Partial League agenda: ch07:21,25,27-28,74.
Records are engineering markers, never Engine action/turn authority.
No cost, frequency, HP, RNG, effects or clock is owned here.
"""
from dataclasses import dataclass, replace
from enum import Enum

class Role(str,Enum):
 TRAINER='trainer'
 POKEMON='pokemon'
class Phase(str,Enum):
 DECLARE='declare_trainers'
 TRAINERS='resolve_trainers'
 POKEMON='pokemon'
 EXHAUSTED='agenda_exhausted'
@dataclass(frozen=True)
class Participant:
 actor_id:str
 player_id:str
 role:Role
 initiative:int
 able:bool=True
@dataclass(frozen=True)
class Record:
 event_id:str
 actor_id:str
 phase:Phase
 evidence_ref:str
 disposition:str
@dataclass(frozen=True)
class Agenda:
 round_id:str
 participants:tuple
 declaration_order:tuple
 trainer_order:tuple
 pokemon_order:tuple
 phase:Phase=Phase.DECLARE
 cursor:int=0
 records:tuple=()
 pending:tuple=()
 @property
 def turn_rights(self):
  # Permanent slot identities, not consumable executable permission tokens.
  return tuple((self.round_id,p.player_id,p.role.value) for p in self.participants)
 @property
 def actor_bindings(self):
  return tuple((self.round_id,p.player_id,p.role.value,p.actor_id) for p in self.participants)
 @property
 def remaining_records(self):
  return 2*len(self.trainer_order)+len(self.pokemon_order)-len(self.records)

def _text(v,label):
 if type(v) is not str or not v.strip():raise ValueError(label+' must be nonempty text')
def _normalize(s):
 orders={Phase.DECLARE:s.declaration_order,Phase.TRAINERS:s.trainer_order,Phase.POKEMON:s.pokemon_order}
 successors={Phase.DECLARE:Phase.TRAINERS,Phase.TRAINERS:Phase.POKEMON,Phase.POKEMON:Phase.EXHAUSTED}
 while s.phase!=Phase.EXHAUSTED and s.cursor==len(orders[s.phase]):
  s=replace(s,phase=successors[s.phase],cursor=0)
 return s
def create(round_id,participants,*,resolved_order=None):
 """Caller supplies League-mode roster/bindings, availability and fixed initiatives.
 Mode selection and source derivation of initiative are caller preconditions.
 This API does not verify them. Availability changes must be explicitly held.
 One trainer/Pokemon pair per player is a supported input profile, not a
 prohibition of double/triple battles. Ties are explicitly unsupported.
 """
 _text(round_id,'round_id');ps=tuple(participants)
 if not ps or any(type(p) is not Participant for p in ps):raise ValueError('nonempty Participant inputs required')
 for p in ps:
  _text(p.actor_id,'actor_id');_text(p.player_id,'player_id')
  if type(p.role) is not Role or type(p.initiative) is not int or type(p.able) is not bool:raise ValueError('exact Role/int/bool fields required')
 if len({p.actor_id for p in ps})!=len(ps):raise ValueError('duplicate actor identity')
 ts=tuple(p for p in ps if p.role==Role.TRAINER);pslots=tuple(p for p in ps if p.role==Role.POKEMON)
 reasons=[]
 for player in {p.player_id for p in ps}:
  roles=[p.role for p in ps if p.player_id==player]
  if roles.count(Role.TRAINER)!=1 or roles.count(Role.POKEMON)!=1:reasons.append('participant profile outside one supplied pair per player')
 if resolved_order is None:
  for group in (ts,pslots):
   if len({p.initiative for p in group})!=len(group):reasons.append('initiative tie requires separate interpretation')
  trainers=tuple(p.actor_id for p in sorted(ts,key=lambda p:p.initiative,reverse=True))
  pokes=tuple(p.actor_id for p in sorted(pslots,key=lambda p:p.initiative,reverse=True))
 else:
  order=tuple(resolved_order)
  if len(order)!=len(set(order)) or set(order)!={p.actor_id for p in ps}:raise ValueError('exact actual resolved order required')
  by_id={p.actor_id:p for p in ps}
  trainers=tuple(key for key in order if by_id[key].role==Role.TRAINER)
  pokes=tuple(key for key in order if by_id[key].role==Role.POKEMON)
  for group in (trainers,pokes):
   if any(by_id[a].initiative<by_id[b].initiative for a,b in zip(group,group[1:])):raise ValueError('resolved order contradicts actual initiative')
 return _normalize(Agenda(round_id,ps,tuple(reversed(trainers)),trainers,pokes,pending=tuple(dict.fromkeys(reasons))))
def expected(s):
 """Next agenda operation, never permission to invoke Engine actions."""
 if s.pending or s.phase==Phase.EXHAUSTED:return None
 order={Phase.DECLARE:s.declaration_order,Phase.TRAINERS:s.trainer_order,Phase.POKEMON:s.pokemon_order}[s.phase]
 return s.phase,order[s.cursor]
def _append(s,actor_id,event_id,evidence_ref,disposition,declaring):
 if s.pending:raise ValueError('agenda pending; no continuation supplied')
 if s.phase==Phase.EXHAUSTED:raise ValueError('agenda exhausted; no new round inferred')
 if declaring!=(s.phase==Phase.DECLARE):raise ValueError('declaration and resolution phases are distinct')
 if expected(s)[1]!=actor_id:raise ValueError('actor not next in this phase')
 _text(event_id,'event_id');_text(evidence_ref,'evidence_ref')
 if event_id in {r.event_id for r in s.records}:raise ValueError('duplicate event identity')
 p=next(p for p in s.participants if p.actor_id==actor_id)
 permitted=('declaration_recorded' if declaring else 'resolution_acknowledged') if p.able else 'unavailable_recorded'
 if disposition!=permitted:raise ValueError('disposition does not match supplied availability/profile')
 record=Record(event_id,actor_id,s.phase,evidence_ref,disposition)
 return _normalize(replace(s,cursor=s.cursor+1,records=s.records+(record,)))
def declare(s,actor_id,event_id,evidence_ref,*,disposition='declaration_recorded'):
 """Trainer declaration record only; no Pokemon decision required."""
 return _append(s,actor_id,event_id,evidence_ref,disposition,True)
def acknowledge(s,actor_id,event_id,evidence_ref,*,disposition='resolution_acknowledged'):
 """External agenda acknowledgement, NOT proof of any actual action/turn.
 Unavailable placeholders preserve the other role's slot. Their phase placement
 is an interface convention, not a source timing rule.
 """
 return _append(s,actor_id,event_id,evidence_ref,disposition,False)
def hold(s,reason,evidence_ref):
 """Preserve unresolved context and block later records. No resume/refund."""
 _text(reason,'reason');_text(evidence_ref,'evidence_ref')
 return replace(s,pending=s.pending+((reason,evidence_ref),))
