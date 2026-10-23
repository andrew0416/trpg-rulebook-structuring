"""Observed scene lights and one live, target-bound darkness projection.

Source policy owns radii and native Glow/Illuminate qualification. This module
owns observations, ordinary mapped geometry and scene lifetime, not fuel or
special extinction rules. Cells are derived, never saved as a second truth.
"""
from copy import deepcopy
import world_entities as WORLD
import state_grants as GRANTS
import root_resolution as ROOT
import terrain_actions as TERRAIN
import scene_light_policy as POLICY

FIELD='_scene_lighting'


def _text(value):
    if type(value) is not str or not value.strip():
        raise ValueError('explicit light observation identity/reason required')
    return value


def _point(e,value):
    if e.grid is None:raise ValueError('scene light requires an actual mapped location')
    point=TERRAIN.point(value)
    if not e.grid.inside(point):raise ValueError('light location must be inside the actual map')
    return point


def _sign(row):
    row=dict(row)
    row['fingerprint']=ROOT.fingerprint(row)
    return row


def _verify(row):
    if row.get('fingerprint')!=ROOT.fingerprint({k:v for k,v in row.items() if k!='fingerprint'}):
        raise ValueError('scene light observation changed')


def active(e):
    state=getattr(e,FIELD,None)
    return state is not None and state['observation']['darkness']


def configure(e,*,darkness,reason):
    if type(darkness) is not bool:raise ValueError('explicit scene darkness observation required')
    _text(reason);POLICY.definition(e.r)
    if e.grid is None:raise ValueError('ordinary scene lighting requires an actual map')
    def apply(staged,_):
        state=deepcopy(getattr(staged,FIELD,None)) or {'version':1,'sources':{}}
        state['observation']=_sign({'darkness':darkness,'reason':reason,'seconds':staged.elapsed_seconds})
        setattr(staged,FIELD,state)
        return deepcopy(state['observation'])
    return GRANTS.transition(e,None,apply)


def observe(e,source_id,*,kind,origin=None,owner=None,size=None,radiant=False,reason):
    _text(source_id);_text(reason)
    if type(radiant) is not bool:raise ValueError('explicit Illuminate assertion required')
    if (owner is None)==(origin is None):raise ValueError('one actual light owner or fixed origin required')
    if owner is not None:WORLD.require_actors(e,owner)
    if getattr(e,FIELD,None) is None:raise ValueError('observe the actual scene lighting first')
    def apply(staged,subject):
        state=getattr(staged,FIELD)
        if source_id in state['sources']:raise ValueError('light identity already observed; remove before replacing')
        if subject is not None and (not subject.on_field or subject.captured):
            raise ValueError('light owner must be present at observation')
        point=_point(staged,subject.pos if subject is not None else origin)
        radius=POLICY.radius(staged,kind=kind,owner=subject,size=size,radiant=radiant)
        if not radius['eligible']:raise ValueError('actual eligible light source required')
        if radiant and radius['ability_source'] is None:raise ValueError('Illuminate assertion lacks its actual active ability')
        row=_sign({'id':source_id,'kind':kind,'owner_id':None if subject is None else subject.entity_id,
                   'origin':list(point) if subject is None else None,'size':size,
                   'radiant':radiant,'reason':reason,'seconds':staged.elapsed_seconds})
        state['sources'][source_id]=row
        return dict(deepcopy(row),projection=radius)
    return GRANTS.transition(e,owner,apply,include_grid=True)


def remove(e,source_id,*,reason):
    _text(source_id);_text(reason)
    def apply(staged,_):
        state=getattr(staged,FIELD,None)
        if state is None or source_id not in state['sources']:raise ValueError('actual observed light required')
        return deepcopy(state['sources'].pop(source_id))
    return GRANTS.transition(e,None,apply)


def _reactions(e,value):
    if (type(value) is not dict or not value or
            any(species not in e.r.species or response not in ('attract','repel','none')
                for species,response in value.items())):
        raise ValueError('explicit actual species and observed Glow responses required')
    return deepcopy(value)


def _glow_source(e,source_id):
    _text(source_id)
    state=getattr(e,FIELD,None)
    if state is None or source_id not in state['sources']:
        raise ValueError('actual observed Glow light required')
    validate_world(e,WORLD.actor_index(e))
    row=state['sources'][source_id]
    if row['kind']!='glow':raise ValueError('species reactions require actual Glow body light')
    owner=WORLD.actor_index(e)[row['owner_id']]
    current=POLICY.radius(e,kind='glow',owner=owner)
    if not current['eligible'] or not owner.on_field or owner.captured:
        raise ValueError('current present emitting Glow Pokemon required')
    return row,owner


def observe_glow_reactions(e,source_id,*,reactions,reason):
    """GM observes species responses; the source prints no response table."""
    _text(reason);reactions=_reactions(e,reactions);_glow_source(e,source_id)
    def apply(staged,_):
        row,_owner=_glow_source(staged,source_id)
        row['glow_reactions']={'source':'gm/glow-species-reactions','reactions':reactions,
                               'reason':reason,'seconds':staged.elapsed_seconds}
        row['fingerprint']=ROOT.fingerprint({k:v for k,v in row.items() if k!='fingerprint'})
        return deepcopy(row['glow_reactions'])
    return GRANTS.transition(e,None,apply)


def glow_response(e,source_id,target,*,nearby,reason):
    """Read live body light, species and visual exposure, without compelling action.

    ``nearby`` is an independent GM observation, never the darkness light radius.
    The existing sensory environment owns actual target-to-source visual contact.
    Missing observations remain unknown; no species response or DC is inferred.
    """
    _text(reason)
    if nearby is not None and type(nearby) is not bool:
        raise ValueError('explicit nearby observation or unknown required')
    row,owner=_glow_source(e,source_id);WORLD.require_actors(e,target)
    if target is owner or target.kind!='pokemon' or not target.on_field or target.captured:
        raise ValueError('another actual present Pokemon target required')
    species=target.spec.get('species')
    result={'source':POLICY.GLOW,'light_id':source_id,'owner_id':owner.entity_id,
            'target_id':target.entity_id,'species':species,'response':None,
            'nearby':nearby,'reason':reason,'at':e.elapsed_seconds}
    def finish(status,why):return dict(result,status=status,observation_reason=why)
    if nearby is None:return finish('unknown','nearby_unknown')
    if not nearby:return finish('not_observable','not_nearby')
    import perception_observe as PERCEPTION
    import vision_impairment as VISION
    if VISION.explicit_level(target)=='total':return finish('not_observable','vision_blocked')
    declaration=PERCEPTION.native(POLICY.GLOW,[],mode='visual')
    declaration['path']='visual'
    exposure=PERCEPTION.observe(e,target,owner,declaration)
    if exposure['status']!='observed':return finish(exposure['status'],exposure['reason'])
    reactions=row.get('glow_reactions',{}).get('reactions',{})
    if species not in reactions:return finish('unknown','species_reaction_unknown')
    result['response']=reactions[species]
    return finish('unaffected' if result['response']=='none' else 'ready','gm_species_reaction')


def respond_to_glow(e,source_id,target,*,nearby,reason,accept,movement=None):
    """A target chooses its own ordinary Shift in response to observed Glow.

    Attracted targets may choose native approach. Repelled targets may choose a
    known relative direction away from the actual light. Normal movement costs,
    geometry, reactions and interruptions remain owned by those native actions.
    Glow grants no command, forced movement, extra action, disposition or capture.
    """
    if type(accept) is not bool:raise ValueError('explicit target response choice required')
    response=glow_response(e,source_id,target,nearby=nearby,reason=reason)
    if not accept:
        if movement is not None:raise ValueError('declined Glow response has no movement declaration')
        return dict(response,accepted=False,movement=None)
    if response['status']!='ready':return dict(response,accepted=True,movement=None)
    if type(movement) is not dict:raise ValueError('target-chosen native movement declaration required')
    options=deepcopy(movement);kind=options.pop('kind',None)
    _,owner=_glow_source(e,source_id)
    if response['response']=='attract':
        if kind!='approach' or set(options)-{'reach','movement_mode','blindness_options'}:
            raise ValueError('attracted target chooses native approach options')
        result=e.approach(target,owner,**options)
    else:
        if kind!='relative' or set(options)-{'direction','distance','pace','movement_id','movement_mode','blindness_options'}:
            raise ValueError('repelled target chooses native relative movement options')
        import relative_movement as RELATIVE
        frame=target.spec.get(RELATIVE.FRAME,{})
        vector=frame.get('directions',{}).get(options.get('direction'))
        if vector is None:raise ValueError('repelled target needs its actual known direction frame')
        # Outward heading only; this is not an influence distance or duration.
        if sum(vector[i]*(target.pos[i]-owner.pos[i]) for i in (0,1))<=0:
            raise ValueError('repelled target movement must head away from the light')
        result=e.move_relative(target,**options)
    return dict(response,accepted=True,movement=result)


def end_scene(e):
    if hasattr(e,FIELD):delattr(e,FIELD)


def illuminated(e):
    state=getattr(e,FIELD,None)
    if state is None:return set(),[]
    validate_world(e,WORLD.actor_index(e))
    index=WORLD.actor_index(e);cells=set();sources=[]
    for row in state['sources'].values():
        owner=None if row['owner_id'] is None else index[row['owner_id']]
        if owner is not None and (not owner.on_field or owner.captured):continue
        # Size and acquired capabilities are live; the original observation
        # authorizes neither a stale size nor a suppressed Illuminate bonus.
        radius=POLICY.radius(e,kind=row['kind'],owner=owner,
                             size=row['size'] if owner is None else None,radiant=False)
        if not radius['eligible']:continue
        point=_point(e,row['origin'] if owner is None else owner.pos)
        lit=e.grid.burst(point,radius['radius'])|{point}
        cells.update(lit)
        sources.append(dict(radius,id=row['id'],origin=point,cells=tuple(sorted(lit))))
    import type_ace as TA
    for actor in index.values():
        lights=TA.light_projection(e,actor)
        if lights is not None:cells.update(lights['cells']);sources.append(lights)
    return cells,sources


def projection(e,actor,target):
    """One meter per traversed grid cell, excluding origin and including target."""
    if not active(e):return None
    WORLD.require_actors(e,actor,target)
    start=_point(e,actor.pos);end=_point(e,target.pos)
    cells,sources=illuminated(e)
    line=[] if start==end else e.grid.line_cells(start,end)+[end]
    unlit=[cell for cell in line if cell not in cells]
    import capability_traits as TRAITS
    senses=TRAITS.projection(actor,engine=e)
    exempt=senses['blindsense'] or senses['darkvision']
    return {'actor_id':actor.entity_id,'target_id':target.entity_id,'line':tuple(line),
            'unlit_cells':tuple(unlit),'unlit_meters':len(unlit),
            'penalty':0 if exempt else -2*len(unlit),'sensory_exempt':bool(exempt),
            'illuminated_cells':tuple(sorted(cells)),'sources':sources}


def skill_modifier(e,actor,skill,target):
    import skill_modifiers as SKILLS
    if (not active(e) or target is None or
            SKILLS.skill_id(e.r.skill_policy,skill)!='perception'):return ()
    result=projection(e,actor,target)
    return (('scene/ordinary-light',result['penalty'],'unlit meters: '+str(result['unlit_meters'])),)


def validate_world(e,index):
    state=getattr(e,FIELD,None)
    if state is None:return True
    if type(state) is not dict or set(state)!={'version','observation','sources'} or state['version']!=1:
        raise ValueError('known observed scene light state required')
    POLICY.definition(e.r)
    if e.grid is None:raise ValueError('observed scene lighting lost its actual map')
    observed=state['observation']
    if set(observed)!={'darkness','reason','seconds','fingerprint'} or type(observed['darkness']) is not bool:
        raise ValueError('actual scene darkness observation required')
    _text(observed['reason']);_verify(observed)
    if type(state['sources']) is not dict:raise ValueError('identified scene lights required')
    for uid,row in state['sources'].items():
        fields={'id','kind','owner_id','origin','size','radiant','reason','seconds','fingerprint'}
        if 'glow_reactions' in row:fields.add('glow_reactions')
        if set(row)!=fields or row['id']!=uid:
            raise ValueError('actual source light identity required')
        _text(uid);_text(row['reason']);_verify(row)
        if type(row['radiant']) is not bool:raise ValueError('observed Illuminate assertion required')
        owner=None if row['owner_id'] is None else index.get(row['owner_id'])
        if row['owner_id'] is not None and owner is None:raise ValueError('light owner no longer resolves')
        if (owner is None)==(row['origin'] is None):raise ValueError('one fixed or actor-owned light origin required')
        if owner is None:_point(e,row['origin'])
        POLICY.radius(e,kind=row['kind'],owner=owner,size=row['size'] if owner is None else None,radiant=False)
        if 'glow_reactions' in row:
            observed=row['glow_reactions']
            if (row['kind']!='glow' or type(observed) is not dict or
                    set(observed)!={'source','reactions','reason','seconds'} or
                    observed['source']!='gm/glow-species-reactions'):
                raise ValueError('actual Glow species reaction observation required')
            _reactions(e,observed['reactions']);_text(observed['reason'])
            if type(observed['seconds']) is not int or not 0<=observed['seconds']<=e.elapsed_seconds:
                raise ValueError('actual Glow species observation time required')
    return True
