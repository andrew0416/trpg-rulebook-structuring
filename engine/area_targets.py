"""Explicit aim geometry shared by native area attacks and weapon adapters."""
from copy import copy
import common_checks as C
from grid import cheb


class _EmptyFieldAuthority:
    """Runtime-only proof that the native adapter recognized the exact rule."""
    def __deepcopy__(self, memo):
        return self


_EMPTY_FIELD_AUTHORITY = _EmptyFieldAuthority()
_WHIRLWIND_PUSH = {'type': 'push', 'meters': '8 - target.weight_class',
                   'target': 'all_targets'}
_WHIRLWIND_FIELDS = ({'type': 'destroy_hazards', 'area': 'line'},
                     {'type': 'clear_field', 'remove': ['연막 in line']})


def mechanics(rules, move_id, declaration):
    """날려버리기의 전체 대상 밀기를 기존 영역별 대상 실행에 결합한다."""
    if move_id == 'move/날려버리기':
        effects = declaration.get('effects_exec', [])
        push = _WHIRLWIND_PUSH
        expected = [push, *_WHIRLWIND_FIELDS]
        if effects == expected:
            # 대상별 밀기와 한 활성화에 한 번인 필드 부가 효과를 분리한다. 밑줄
            # 표식은 원문 authoring 필드가 아니라 native 실행 어댑터의 내부 계약이다.
            field = [dict(effect, _activation_scope='field') for effect in effects[1:]]
            declaration = dict(declaration, effects_exec=[dict(push, target='target'), *field],
                               _native_empty_field_activation=_EMPTY_FIELD_AUTHORITY)
    if move_id=='move/소란피기' and declaration=={'effects_exec':[{'type':'cure_status','status':'잠듦','target':'all_targets'}]}:
        declaration=dict(declaration,effects_exec=[dict(declaration['effects_exec'][0],_activation_scope='field')],_native_empty_field_activation=_EMPTY_FIELD_AUTHORITY,_native_empty_field_kind='uproar')
    if move_id=='move/일렉트로빔':
        import electro_shot as ELECTRO
        declaration=ELECTRO.mechanics(rules,move_id,declaration)
        declaration=dict(declaration,_native_empty_field_activation=_EMPTY_FIELD_AUTHORITY,_native_empty_field_kind='electro_shot')
    import hazard_state as HAZARDS
    return HAZARDS.mechanics(rules, move_id, declaration)


def empty_field_effects(declaration):
    """Return effects only from the exact runtime adapter, never authoring data."""
    import misty_explosion as MISTY
    mist = MISTY.field_effects(declaration)
    if mist:
        return mist
    import hazard_state as HAZARDS
    hazard = HAZARDS.field_effects(declaration)
    if hazard:
        return hazard
    if declaration.get('_native_empty_field_activation') is not _EMPTY_FIELD_AUTHORITY:
        return []
    if declaration.get('_native_empty_field_kind')=='electro_shot':
        return __import__('electro_shot').field_effects(declaration)
    if declaration.get('_native_empty_field_kind')=='uproar' and declaration.get('effects_exec')==[{'type':'cure_status','status':'잠듦','target':'all_targets','_activation_scope':'field'}]:return declaration['effects_exec']
    expected = [dict(_WHIRLWIND_PUSH, target='target'),
                *(dict(effect, _activation_scope='field')
                  for effect in _WHIRLWIND_FIELDS)]
    if declaration.get('effects_exec') != expected:
        return []
    import move_completion as COMPLETE
    return COMPLETE.field_effects(declaration.get('effects_exec', ()))


def requires_empty_field_activation(declaration):
    import hazard_state as HAZARDS
    return HAZARDS.target_free(declaration)


def point(value):
    if not isinstance(value,(list,tuple)) or len(value)!=2:raise ValueError('explicit aim cell required')
    return tuple(C.integer(x,'aim coordinate') for x in value)


def bind(engine,actor,move,aim):
    import weapon_actions as W
    import hazard_state as HAZARDS
    hazard = HAZARDS.bind(engine,actor,move,aim)
    if hazard is not None:return hazard
    if move.get('id') == 'move/날려버리기' and engine.grid is None:
        raise ValueError('Whirlwind requires an actual mapped line before action cost')
    rng=W.range_spec(engine,move,actor)
    if aim is None:
        if move.get('_weapon_attack') and rng.get('shape'):raise ValueError('weapon area attack requires an explicit aim cell')
        return move
    if not rng.get('shape'):raise ValueError('aim cell belongs to an actual area attack')
    if engine.grid is None:raise ValueError('explicit area aim requires an actual grid')
    aim=point(aim)
    if not engine.grid.inside(aim):raise ValueError('aim cell lies outside map')
    out=copy(move);out['_area_aim']=aim
    cells(engine,actor,out)
    return out


def cells(engine,actor,move):
    import weapon_actions as W
    import body_state as BODY
    import hazard_state as HAZARDS
    hazard=HAZARDS.cells(move)
    if hazard is not None:return hazard
    if engine.grid is None:raise ValueError('area geometry requires actual map')
    rng=W.range_spec(engine,move,actor);shape=rng.get('shape');size=C.integer(rng.get('size'),'area size',1)
    aim=point(move.get('_area_aim'))
    origin=actor.pos;g=engine.grid
    distance=min(cheb(c,aim) for c in BODY.cells(actor,require_complete=True))
    if distance<move.get('_weapon_attack',{}).get('minimum_distance',0):raise ValueError('aim is within the selected weapon minimum range')
    if shape=='blast':
        reach=rng.get('origin')
        if type(reach) not in (int,float) or distance>reach:raise ValueError('aim cell outside selected ranged area origin')
        if g.blocked(origin,aim):raise ValueError('line of sight to aim cell is blocked')
        return g.ranged_blast(aim,size)
    if shape=='burst':
        if aim!=origin:raise ValueError('Burst is centered on the actual user')
        # Burst excludes its user as a recipient, not other bodies at its origin.
        return g.burst(origin,size)|{origin}
    dx=(aim[0]>origin[0])-(aim[0]<origin[0]);dy=(aim[1]>origin[1])-(aim[1]<origin[1])
    if not dx and not dy:raise ValueError('directional area requires a distinct aim cell')
    methods={'cone':g.cone,'line':g.line}
    if shape=='close_blast':return g.close_blast(origin,size,(dx,dy))
    if shape not in methods:raise ValueError('selected area shape requires an execution policy')
    area=methods[shape](origin,(dx,dy),size)
    if move.get('id')=='move/날려버리기':
        import smoke_regions as SMOKE
        SMOKE.require_bound_line(engine,area)
    return area


def targets(engine,actor,move,candidates):
    import body_state as BODY
    import body_modes as MODES
    import marsupial_state as MARSUPIAL
    import setup_move_state as SETUP
    area=cells(engine,actor,move)
    return [c for c in candidates if c is not actor and not c.fainted and not c.captured
            and MARSUPIAL.target_present(c,engine=engine)
            and SETUP.targetable(c,engine=engine,attacker=actor,move=move)
            and MODES.target_visible(engine,actor,c)
            and BODY.cells(c,require_complete=True).intersection(area)]
