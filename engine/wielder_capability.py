"""C10-151/152: live Wielder admission and actual attached weapon identities.

Attached anatomy is observed through body_state, never registered as an item.
External weapons retain the ordinary equipment and physical-object owners.
"""
from copy import deepcopy
import perception_communicate as COMM
import world_entities as WORLD
from source_context import verified_source

SOURCE = 'capability/장착자'
REFERENCE = {'file':'input/ch10-index-reference.md',
    'sha256':'c3a1d783b4f649f0f6e25a9443a90ca8079a6e036c42c6f8797e100127157abe'}
NATURAL = 'wielder_natural_weapons'


def active(engine, actor):
    if actor.kind != 'pokemon' or not COMM._owns(actor,'capabilities',(SOURCE,'장착자','Wielder')):
        return False
    if engine.r._selected_rule(SOURCE) != SOURCE:
        raise ValueError('selected Wielder variant needs its own capability contract')
    verified_source(engine.r,REFERENCE,label='Wielder')
    return True


def require_weapon(engine, actor, weapon):
    if actor.kind != 'pokemon':return
    if not active(engine,actor):raise ValueError('current Wielder capability required for Pokemon weapons')
    import body_state as BODY
    size=BODY.projection(actor)['size']
    if size in ('소형','small','Small'):kind='소형 근접무기'
    elif size in ('중형','대형','거대','거대형','초거대','초거대형',
                  'medium','large','huge','gigantic','Medium','Large','Huge','Gigantic'):
        kind='대형 근접무기'
    else:raise ValueError('current observed Wielder size required')
    if weapon['kind'] != kind:raise ValueError('weapon kind does not match current Wielder size')
    uid=weapon.get('instance_id')
    if not uid or weapon.get('framework_instance') != uid:
        raise ValueError('Wielder requires one actual external weapon instance')
    import optional_weapon_framework as FRAMEWORK
    FRAMEWORK.object_profile(engine,uid)


def observe_natural_weapon(engine, actor, appendage_id, *, name, reason):
    """GM anatomy observation; it grants no move, item, slot or attack bonus."""
    WORLD.require_actors(engine,actor)
    if not active(engine,actor):raise ValueError('current Wielder required for natural weapon observation')
    WORLD._text(name,'natural weapon name');WORLD._text(reason,'natural weapon observation reason')
    import state_grants as GRANTS, body_state as BODY
    def apply(e,c):
        BODY.observe_appendage(e,c,appendage_id,reason=reason)
        row={'actor_id':c.entity_id,'appendage_id':appendage_id,'name':name,
             'source':SOURCE,'reason':reason}
        old=c.custom_conditions.get(NATURAL,{}).get(appendage_id)
        if old is not None and old!=row:raise ValueError('actual natural weapon observation changed')
        c.custom_conditions.setdefault(NATURAL,{})[appendage_id]=row
        return deepcopy(row)
    return GRANTS.transition(engine,actor,apply)


def natural_rows(actor):
    """Only observed attached body identities, with no fabricated physical item."""
    rows=[]
    for uid,row in actor.custom_conditions.get(NATURAL,{}).items():
        observed=actor.spec.get('observed_appendages',{}).get(uid,{})
        if (row.get('source')!=SOURCE or row.get('actor_id')!=actor.entity_id
                or row.get('appendage_id')!=uid or observed.get('actor_id')!=actor.entity_id
                or observed.get('appendage_id')!=uid or observed.get('source')!='gm/observation'):
            raise ValueError('natural weapon requires its actual observed attached body identity')
        rows.append({'key':'natural:'+uid,'name':row['name'],'natural_weapon':uid,
                     'instance_id':None,'held':False,'slots':[],'source':SOURCE})
    return rows


def natural_identity(actor,row):
    return next((r for r in natural_rows(actor) if r['key']==row.get('key')
                 and r['natural_weapon']==row.get('natural_weapon')),None)


def disarm_options(engine, actor, options):
    import common_checks as C, composition_derive as COMPOSITION
    result=dict(options or {});C.integer(result.get('mods',0),'Disarm modifier')
    if active(engine,actor):
        result['mods']=COMPOSITION.derive(result.get('mods',0),
            [{'id':SOURCE,'source':SOURCE,'value':2}],
            [{'law':'add','contributors':[SOURCE]}])['value']
    return result
