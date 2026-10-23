"""Source-bound digital programs composed with the existing digital state owners."""
from hashlib import sha256
from pathlib import Path
import json
import crafting_recipes as Q, world_entities as W, state_grants as G
import network_connection as N, network_integrity as I, special_entities as S
from ruleset import source_unit


def policy(rules):
    value=json.loads((Path(rules.root)/'data/digital-program-policy.json').read_text(encoding='utf-8'))
    if value.get('schema_version')!=1 or set(value.get('programs',{}))!={'data_snare','net_shield'}:
        raise ValueError('reviewed digital program policy required')
    path=Path(rules.root)/value['source_file'];raw=path.read_bytes()
    if sha256(raw).hexdigest()!=value['source_file_sha256']:
        raise ValueError('digital program source changed; review required')
    lines=raw.decode('utf-8').splitlines()
    for row in value['programs'].values():
        excerpt='\n'.join(lines[row['lines'][0]-1:row['lines'][1]])
        if sha256(excerpt.encode('utf-8')).hexdigest()!=row['excerpt_sha256']:
            raise ValueError('digital program source excerpt changed')
    snare=value['programs']['data_snare'];shield=value['programs']['net_shield']
    if (snare['id']!='digital-program/data-snare' or snare['integrity']!=50 or
            snare['defense']!=0 or snare['evasion']!=0 or snare['cost']!=2000 or
            shield['id']!='digital-program/net-shield' or shield['temporary_integrity']!=20 or
            shield['consume'] is not True or shield['seconds'] is not None or shield['cost']!=800):
        raise ValueError('source-bound digital program definition changed')
    return value


def install(rules):
    """Register these distinct source identities without a physical Shield alias."""
    value=policy(rules)
    try:
        if rules._selected_rule(value['parent_source'])!=value['parent_source']:return ()
    except ValueError:return ()
    for key,row in value['programs'].items():
        unit={'id':row['id'],'title':row['name'],'kind':'entity:item',
              'source':{'file':value['source_file'].removeprefix('input/'),
                        'lines':row['lines'],'sha256':value['source_file_sha256']},
              'tags':['digital-program'],'keyword':None,'source_group':None}
        if row['id'] not in rules.selection.units:
            rules.selection.register_derived(unit,(value['parent_source'],))
        elif rules.selection.units[row['id']]!=source_unit(unit):
            raise ValueError('digital program source identity changed')
        try:selected=rules._selected_rule(row['id'])==row['id']
        except ValueError:selected=False
        if selected:
            definition={'id':row['id'],'name':row['name'],'effects':[],
                        'digital_program':key,'source_clause_id':row['clause_id']}
            old=rules.items_mech.get(row['id'])
            if old is not None and old!=definition:raise ValueError('digital program cannot replace a catalog identity')
            rules.items_mech[row['id']]=definition
    return tuple(row['id'] for row in value['programs'].values())


def definition(e,key):
    value=policy(e.r);row=value['programs'][key]
    Q._selected(e,value['parent_source']);Q._selected(e,row['id'])
    return row


def validate_operation(e,value,avatar_id=None,target_id=None):
    """The native source cannot be relabeled as an arbitrary authored effect."""
    if value['source']!='digital-program/net-shield':return
    row=definition(e,'net_shield');effect=value['effect'];program=value['program']
    if (effect.get('kind')!='temporary' or effect.get('amount')!=row['temporary_integrity']
            or effect.get('seconds') is not None or effect.get('maximum',0)<row['temporary_integrity']
            or program is None or program['item_rule_id']!=row['id'] or program['consume'] is not True
            or value.get('id','native/net-shield/'+program['instance_id'])!='native/net-shield/'+program['instance_id']
            or value['requirements'] or value['range'] is not None or value['check'] is not None
            or avatar_id is not None and avatar_id!=target_id):
        raise ValueError('native Net Shield requires its own one-use program and 20 temporary Integrity')


def validate_receipt(e,intent,result,request_id):
    value=intent['policy']
    if value['source']!='digital-program/net-shield':return
    program=value['program'];obj=e._physical_objects.get(program['instance_id'],{})
    consumed=obj.get('consumed');before=result.get('before')
    if (obj.get('kind')!='item_instance' or obj.get('item_rule_id')!=program['item_rule_id']
            or type(consumed) is not dict or consumed.get('request_id')!=request_id
            or consumed.get('source')!=program['item_rule_id'] or consumed.get('by_actor_id')!=intent['actor_id']
            or consumed.get('at')!=result['at'] or consumed.get('consumer')!='digital_program'
            or result.get('program_id')!=program['instance_id'] or result.get('kind')!='temporary'
            or type(before) is not int or before<0 or result.get('after')!=max(before,20)
            or result.get('applied')!=max(0,20-before)):
        raise ValueError('native Net Shield grant needs its actual one-use consumption receipt')


def net_shield(e,actor,avatar_id,program_id,*,action,request_id,reason):
    """Use an actual installed one-use Shield; the caller supplies action policy."""
    row=definition(e,'net_shield');W.require_actors(e,actor)
    avatar=I._target(e,avatar_id);old=I._state(e)['requests'].get(request_id)
    maximum=max(avatar.get('temp_integrity',0),row['temporary_integrity'])
    # A receipt keeps its original ceiling after later damage or legacy pools.
    if old is not None:maximum=old['intent']['policy']['effect'].get('maximum',maximum)
    value={'id':'native/net-shield/'+program_id,'source':row['id'],'requirements':[],
           'action':action,'range':None,'check':None,
           'effect':{'kind':'temporary','amount':row['temporary_integrity'],
                     'maximum':maximum,'seconds':row['seconds']},
           'program':{'instance_id':program_id,'item_rule_id':row['id'],'consume':True}}
    return I.execute(e,actor,avatar_id,avatar_id,value,request_id=request_id,reason=reason)


def observe_data_snare(e,actor,avatar_id,node_id,*,reason):
    """Observe a distinct installed false core, without certifying acquisition."""
    row=definition(e,'data_snare');W.require_actors(e,actor);Q._text(node_id);Q._text(reason)
    N._connected(e,actor,avatar_id)
    def apply(staged,c):
        avatar=N._connected(staged,c,avatar_id)
        if node_id in staged._physical_objects:raise ValueError('new Data Snare identity required; observation cannot reset a damaged object')
        node={'id':node_id,'kind':'digital_node',
              'location':{'kind':'abstract','place_id':avatar['network_id']+'/false-core'},
              'node_type':'data_snare','network_id':avatar['network_id'],
              'integrity':row['integrity'],'max_integrity':row['integrity'],'temp_integrity':0,
              'status':'connected','anchor_id':None,'controller_id':c.entity_id,
              'defense':row['defense'],'evasion':row['evasion'],
              'data_state':'not_applicable','bot_id':None}
        S.observe(staged,node,reason=reason)
        return {'node_id':node_id,'network_id':avatar['network_id'],
                'source':row['id'],'clause_id':row['clause_id'],'integrity':row['integrity']}
    return G.transition(e,actor,apply)


def known_data_snares(e,actor,avatar_id):
    """Recognition is derived from this actual user's completed intrusion receipt."""
    W.require_actors(e,actor);I.validate_world(e,W.actor_index(e));avatar=N._connected(e,actor,avatar_id)
    return {uid:request for uid,request in I._recognized_snares(e,actor.entity_id).items()
            if e._physical_objects[uid]['network_id']==avatar['network_id']}
