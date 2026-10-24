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


def bind_native(rules, source_variant=None):
    if source_variant == 'core_105':
        import source_context as SOURCES
        SOURCES.verified_source(rules, {'file':'source-audit/ptu-core-1.05.pdf',
            'sha256':'e5e0371031601c3ad0a04056771c17599a2d8826e5a5102ccd37f9b368108907'},
            label='Core capture p214',source_root='source-audit')
        return Procedure('core_105/capture-p214',100,'<=',(100,)), {
            'source_variant':source_variant,'throw':{'action':'standard','ac':6,'class':'변화','range':'4 + athletics_rank'},
            'trainer_bonus_by_level':{},'capture_rate':{'source':'Core 1.05 p214'}}
    if source_variant not in (None,'official_sep2015'):
        raise ValueError('select an actual complete capture procedure')
    if source_variant=='official_sep2015':
        __import__('capture_specialist').official_source(rules,source_variant)
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


def rate(engine,target,rarity=0,*,source_variant=None,hp=None):
    procedure,selected=bind_native(engine.r,source_variant)
    current=target.hp if hp is None else C.integer(hp,'capture-only HP observation',1)
    if procedure.sides==20:
        cr=selected['capture_rate'];boxes=0
        ctx={'hp_le_50':current<=0.5*target.base_max_hp,'hp_le_25':current<=0.25*target.base_max_hp,
             'injuries_ge_5':target.injuries>=5,
             'any_status':any(engine.r.condition_class(s) in ('persistent','volatile') for s in target.conditions),
             'two_evolutions_left':target.spec.get('evolutions_remaining',0)==2,
             'one_evolution_left':target.spec.get('evolutions_remaining',0)==1}
        boxes=sum(row['boxes'] for row in cr['checkboxes'] if ctx[row['id']])
        import arithmetic_policy as M
        return cr['base']+M.ratio(target.level,10)*cr['per_10_levels']+rarity-boxes*cr['checkbox_penalty'],boxes
    C.integer(rarity,'Core GM capture rarity adjustment')
    if current<=0:raise ValueError('Core capture requires positive HP or actual Catch Combo')
    health=30 if current==1 else 15 if current<=target.base_max_hp/4 else 0 if current<=target.base_max_hp/2 else -15 if current<=target.base_max_hp*3/4 else -30
    evolutions=C.integer(target.spec.get('evolutions_remaining',0),'remaining evolution stages',0,2)
    conditions=sum(10 if engine.r.condition_class(s)=='persistent' else 5 if engine.r.condition_class(s)=='volatile' else 0 for s in target.conditions)
    total=100-2*target.level+health+{2:10,1:0,0:-10}[evolutions]+5*target.injuries+conditions
    total-=10 if target.spec.get('shiny',False) else 0
    total-=30 if target.spec.get('legendary',False) else 0
    total+=10 if '구속' in target.conditions else 0
    total+=5 if '둔화' in target.conditions else 0
    return total+rarity,0


def ball_modifier(engine,name,trainer,target,procedure):
    import items
    value,why=items.ball_modifier(engine,name,trainer,target)
    # The official September conversion explicitly gives the inverse of each
    # original modifier. Use that complete paired table, including Timer bounds.
    if procedure.sides==100:
        __import__('capture_specialist').official_source(engine.r,'official_sep2015')
        return -5*value,why+' (Core paired modifier)'
    return value,why
