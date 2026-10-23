"""Bound capture comparison, separate from throw admission and acquisition."""
from dataclasses import dataclass
from copy import deepcopy
import common_checks as C

@dataclass(frozen=True)
class Procedure:
    source: str
    sides: int
    comparison: str
    automatic_faces: tuple = ()
    miss_state: str = 'recoverable_on_ground'
    failure_state: str = 'failed_capture'
    success_state: str = 'captured'

    def __post_init__(self):
        if not isinstance(self.source,str) or not self.source.strip():raise ValueError('capture procedure source required')
        C.integer(self.sides,'capture die sides',2)
        if self.comparison not in ('>=','<='):raise ValueError('capture comparison must be explicit')
        if not isinstance(self.automatic_faces,tuple):raise ValueError('immutable automatic faces required')
        for face in self.automatic_faces:C.integer(face,'automatic capture face',1,self.sides)
        if len(set(self.automatic_faces))!=len(self.automatic_faces):raise ValueError('duplicate automatic face')
        if any(not isinstance(x,str) or not x.strip() for x in (self.miss_state,self.failure_state,self.success_state)):
            raise ValueError('complete capture result states required')

    def resolve(self, natural, *, threshold, modifiers):
        C.integer(natural,'capture natural',1,self.sides)
        C.integer(threshold,'capture threshold')
        if not isinstance(modifiers,dict) or any(not isinstance(k,str) or not k.strip() for k in modifiers):
            raise ValueError('named capture modifiers required')
        for value in modifiers.values():C.integer(value,'capture modifier')
        total=natural+sum(modifiers.values())
        automatic=natural in self.automatic_faces
        captured=automatic or (total>=threshold if self.comparison=='>=' else total<=threshold)
        return dict(source=self.source,sides=self.sides,comparison=self.comparison,
                    natural=natural,modifiers=dict(modifiers),total=total,threshold=threshold,
                    automatic=automatic,captured=captured,
                    status=self.success_state if captured else self.failure_state)


def bind_native(rules):
    selected=rules.mech('pokemon/capture-rate')
    if selected.get('_version') is not None:
        raise ValueError('selected capture version needs a complete procedure and matching ball modifiers')
    if selected.get('roll')!='1d20 + trainer_bonus' or selected.get('success')!='roll >= capture_rate':
        raise ValueError('capture roll and comparison require a matching complete procedure')
    throw=selected.get('throw',{})
    if throw.get('action')!='standard' or throw.get('class')!='변화' or throw.get('range')!='4 + athletics_rank':
        raise ValueError('capture throw policy requires a matching procedure')
    C.integer(throw.get('ac'),'capture throw AC',0)
    rates=selected.get('capture_rate',{})
    for key in ('base','per_10_levels','checkbox_penalty'):C.integer(rates.get(key),'capture '+key)
    known={'hp_le_50':'hp <= 0.5*max_hp','hp_le_25':'hp <= 0.25*max_hp',
           'injuries_ge_5':'injuries >= 5','any_status':'has persistent or volatile affliction',
           'two_evolutions_left':'evolutions_remaining == 2','one_evolution_left':'evolutions_remaining == 1'}
    rows=rates.get('checkboxes')
    if not isinstance(rows,list) or any(not isinstance(r,dict) or r.get('id') not in known for r in rows):
        raise ValueError('capture checkbox declaration requires known predicates')
    if len({r['id'] for r in rows})!=len(rows):raise ValueError('duplicate capture checkbox')
    for row in rows:
        C.integer(row.get('boxes'),'capture checkbox count',0)
        if row.get('when')!=known[row['id']]:raise ValueError('capture checkbox predicate requires a matching procedure')
    bonuses=selected.get('trainer_bonus_by_level')
    if not isinstance(bonuses,dict) or not bonuses:raise ValueError('trainer capture bonus table required')
    for level,bonus in bonuses.items():
        if not isinstance(level,str) or not level.isdigit():raise ValueError('trainer bonus level must be numeric')
        C.integer(bonus,'trainer capture bonus')
    return Procedure('pokemon/capture-rate',20,'>='),deepcopy(selected)
