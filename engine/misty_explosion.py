"""The selected Misty Explosion's fixed local Mist, not a global Terrain."""
from copy import deepcopy
import csv
import io

SOURCE = 'move/미스트버스트'
TERRAIN = 'move/미스트필드'
CONDITION = 'user affected by 미스트필드'
EFFECT = {'type':'field_effect','field':'미스트','rounds':5,'shape':'blast 7 centered on user'}
COST = {'type':'self_hp_set','self_hp':'-50% max','unpreventable':True}
DAMAGE = {'type':'conditional_damage_base','damage_base':15,'if':CONDITION}


def handles(source, effect):
    return source == SOURCE and isinstance(effect,dict) and effect.get('type') == 'field_effect'


def definition(rules):
    import hp_setting_moves as HP
    import field_effects as FIELD
    import resolution_transaction as TX
    from source_context import verified_source
    content = verified_source(rules,HP.MOVE_REF,label='Misty Explosion local field')
    cells = list(csv.reader(io.StringIO(content.decode('utf-8-sig'))))[167]
    if (rules._selected_rule(SOURCE) != SOURCE or cells[0] != '미스트버스트'
            or rules.move(SOURCE).get('effect') != cells[7]):
        raise ValueError('selected Misty Explosion source changed')
    for uid,record in ((SOURCE,168),(TERRAIN,169)):
        origin = rules.selection.units[uid]['source']
        if (rules._selected_rule(uid) != uid or origin.get('file') != 'db/moves.csv'
                or origin.get('record_span') != [record,record]):
            raise ValueError('Misty field exact selected source locator changed')
    terrain = FIELD.policy(rules)['moves'][TERRAIN]
    payload = {'grounded_ignore_first_turn_of_status':True,'grounded_immune_persistent':True,
               'dragon_vs_grounded_damage_roll':-10}
    if terrain['field'] != '미스트' or terrain['rounds'] != 5 or terrain['effect'] != payload:
        raise ValueError('selected Misty Terrain payload changed')
    return {'source_row_sha256':TX.json_fingerprint(cells,sort_keys=False,compact=True,allow_nan=True),
            'effect':payload}


def declaration(rules, effect):
    row = definition(rules)
    if {k:v for k,v in effect.items() if k != '_src' and not (k == '_activation_scope' and v == 'field')} != EFFECT:
        raise ValueError('Misty Explosion needs its exact local field declaration')
    return row


def after_all(rules, move, effect):
    if not handles((move or {}).get('id'),effect):
        return False
    declaration(rules,effect)
    return True


def prepare(engine, actor, effect):
    import world_entities as WORLD
    import body_state as BODY
    row = declaration(engine.r,effect)
    WORLD.require_actors(engine,actor)
    if not engine.encounter_active or engine.round_start_seconds is None or engine.grid is None:
        raise ValueError('Misty Explosion needs an actual mapped open combat round')
    BODY.cells(actor,require_complete=True)
    for other in WORLD.actor_index(engine).values():
        if other.on_field:
            BODY.cells(other,require_complete=True)
    if not engine.grid.inside(tuple(actor.pos)):
        raise ValueError('Misty Explosion origin outside map')
    return row


def authorized(engine, ctx, effect):
    import move_completion as COMPLETE
    row = getattr(engine,COMPLETE.KEY,{}).get(ctx.get('move_completion'))
    if not (ctx.get('after_all_targets') and COMPLETE.authorized(engine,ctx)
        and row['move_id'] == SOURCE and ctx.get('source_id',SOURCE) == SOURCE
        and ctx.get('move',{}).get('id') == SOURCE and effect in row['post_effects']):
        return False
    if row['targets']:
        return (any(ctx.get('target') is t for t in row['targets'])
                and not all(result['cancelled'] for result in row['results'].values()))
    return bool(empty_applying(engine,row)
                and ctx.get('target') is row['actor'] and row.get('field_cells')
                and row['post_effects'] == empty_effects())


def install(engine, actor, target, effect, ctx):
    import field_effects as FIELD
    import effect_contracts as CONTRACTS
    definition_row = prepare(engine,actor,effect)
    if not authorized(engine,ctx,effect):
        raise ValueError('Misty Explosion requires its actual all-target completion')
    occurrence = ctx.get('effect_occurrence')
    CONTRACTS.validate_receipt(engine,ctx.get('effect_receipt'),SOURCE,occurrence,actor,target,effect)
    FIELD.validate_local(engine)
    state = getattr(engine,FIELD.LOCAL_KEY,{'version':1,'receipts':{}})
    if occurrence in state['receipts']:
        return deepcopy(state['receipts'][occurrence])
    grid = engine.grid
    origin = tuple(actor.pos)
    row = {'request_id':occurrence,'source_id':SOURCE,'clause_id':'C2CSV-MOVE-R0168',
        'source_row_sha256':definition_row['source_row_sha256'],'creator_id':actor.entity_id,
        'completion_id':ctx['move_completion'],'round':engine.round_no,'expires_round':engine.round_no+5,
        'origin':list(origin),'geometry':{'width':grid.w,'height':grid.h,
            'blocking':[list(p) for p in sorted(grid.blocking)],
            'walls':[[list(p) for p in wall] for wall in sorted(grid.walls)],'shape':'blast','size':7},
        'cells':[list(p) for p in sorted(grid.ranged_blast(origin,7))],
        'name':'미스트','effect':deepcopy(definition_row['effect']),'ended':False}
    row['seal'] = FIELD._local_seal(row)
    # The actual dispatcher occurrence retains the original observation;
    # resealing a relocated or extended local row cannot rewrite that witness.
    engine._effect_dispatch_receipts[ctx['effect_receipt']]['misty_field'] = {
        k:deepcopy(v) for k,v in row.items() if k not in ('ended','seal')}
    state['receipts'][occurrence] = row
    setattr(engine,FIELD.LOCAL_KEY,state)
    FIELD.validate_local(engine)
    engine.log('Misty Explosion local Mist installed for five rounds',SOURCE)
    return deepcopy(row)


def validate(engine, row, index, request):
    import field_effects as FIELD
    import move_completion as COMPLETE
    from grid import Grid
    required = {'request_id','source_id','clause_id','source_row_sha256','creator_id','completion_id',
                'round','expires_round','origin','geometry','cells','name','effect','ended','seal'}
    source = definition(engine.r)
    if (set(row) != required or type(request) is not str or not request
            or row['request_id'] != request or row['source_id'] != SOURCE
            or row['clause_id'] != 'C2CSV-MOVE-R0168' or row['name'] != '미스트'
            or row['source_row_sha256'] != source['source_row_sha256'] or row['effect'] != source['effect']
            or row['seal'] != FIELD._local_seal(row) or type(row['ended']) is not bool
            or type(row['round']) is not int or not 0 <= row['round'] <= engine.round_no
            or type(row['expires_round']) is not int or row['expires_round'] != row['round']+5
            or not row['ended'] and engine.round_no > row['expires_round']):
        raise ValueError('Misty Explosion local field provenance or lifetime changed')
    owner = index.get(row['creator_id'])
    completion = getattr(engine,COMPLETE.KEY,{}).get(row['completion_id'])
    if (owner is None or completion is None or completion['actor'] is not owner
            or completion['move_id'] != SOURCE or not completion['sealed']
            or completion['phase'] not in ('applying','completion_effects','complete','interrupted')
            or any(t.entity_id not in completion['results'] for t in completion['targets'])
            or (all(result['cancelled'] for result in completion['results'].values()) if completion['targets'] else
                not (completion.get('activation') == 'empty_area_field' and not completion['results']
                     and completion.get('field_cells') and completion['post_effects'] == empty_effects()))
            or not any(handles(SOURCE,e) and declaration(engine.r,e) for e in completion['post_effects'])):
        raise ValueError('Misty Explosion lacks its actual completed producer')
    receipts = [r for r in getattr(engine,'_effect_dispatch_receipts',{}).values()
                if r.get('occurrence') == request and r.get('source_id') == SOURCE]
    if (len(receipts) != 1 or receipts[0].get('actor') is not owner
            or not (any(receipts[0].get('target') is t for t in completion['targets']) if completion['targets']
                    else receipts[0].get('target') is owner)
            or receipts[0].get('status') not in ('dispatching','completed')):
        raise ValueError('Misty Explosion lacks its actual native field receipt')
    declaration(engine.r,receipts[0]['effect'])
    if receipts[0].get('misty_field') != {k:v for k,v in row.items() if k not in ('ended','seal')}:
        raise ValueError('Misty Explosion original native field observation changed')
    geo = row['geometry']
    if (not isinstance(geo,dict) or set(geo) != {'width','height','blocking','walls','shape','size'}
            or geo['shape'] != 'blast' or geo['size'] != 7
            or any(type(geo[k]) is not int or geo[k] < 1 for k in ('width','height'))):
        raise ValueError('Misty Explosion original blast geometry changed')
    def point(p):
        return isinstance(p,(list,tuple)) and len(p)==2 and all(type(x) is int for x in p) and 0<=p[0]<geo['width'] and 0<=p[1]<geo['height']
    if (not point(row['origin']) or not all(point(p) for p in geo['blocking'])
            or not all(len(w)==2 and all(point(p) for p in w) for w in geo['walls'])):
        raise ValueError('Misty Explosion original coordinates changed')
    grid = Grid(geo['width'],geo['height'],blocking=[tuple(p) for p in geo['blocking']],
                walls=[tuple(tuple(p) for p in w) for w in geo['walls']])
    if row['cells'] != [list(p) for p in sorted(grid.ranged_blast(tuple(row['origin']),7))]:
        raise ValueError('Misty Explosion cells disagree with the original centered blast')
    return row


def affected(engine, actor):
    import field_effects as FIELD
    state = FIELD.terrain_for(engine,actor,'미스트')
    return state is not None and (state['source_id'] in (SOURCE,'item/부스트에너지')
                                  or FIELD.touches_ground(actor))


def conditional(rules, move, effect):
    if (move or {}).get('id') != SOURCE or effect.get('type') != 'conditional_damage_base':
        return False
    definition(rules)
    if {k:v for k,v in effect.items() if k != '_src'} != DAMAGE:
        raise ValueError('Misty Explosion conditional damage declaration changed')
    return True


def empty_effects():
    return [dict(effect,_activation_scope='field') for effect in (COST,EFFECT)]


def empty_applying(engine, row):
    return bool(row.get('move_id') == SOURCE and row.get('activation') == 'empty_area_field'
        and row.get('phase') == 'applying' and not row.get('targets') and not row.get('results')
        and row.get('post_effects') == empty_effects()
        and any(scope['actor'] is row['actor'] and scope['move_id'] == SOURCE
                and scope['cells'] == row.get('field_cells') and scope['effects'] == row['post_effects']
                for scope in getattr(engine,'_empty_field_activation_scopes',())))


def mechanics(rules, move, declaration):
    if move.get('id') != SOURCE:
        return declaration
    definition(rules)
    effects = [{k:v for k,v in effect.items() if k != '_src'}
               for effect in declaration.get('effects_exec',[])]
    if effects != [COST,EFFECT,DAMAGE]:
        raise ValueError('Misty Explosion needs its exact selected native declarations')
    import area_targets as AREA
    return dict(declaration,_native_empty_field_activation=AREA._EMPTY_FIELD_AUTHORITY,
                _native_empty_field_kind='misty_explosion')


def field_effects(declaration):
    import area_targets as AREA
    if (declaration.get('_native_empty_field_activation') is not AREA._EMPTY_FIELD_AUTHORITY
            or declaration.get('_native_empty_field_kind') != 'misty_explosion'):
        return []
    effects = [{k:v for k,v in effect.items() if k != '_src'}
               for effect in declaration.get('effects_exec',[])]
    if effects != [COST,EFFECT,DAMAGE]:
        raise ValueError('Misty Explosion native empty-area declarations changed')
    return empty_effects()
