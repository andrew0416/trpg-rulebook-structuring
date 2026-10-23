"""Declared dice procedures; callers own costs and transaction phases."""
from collections import deque
import re
import common_checks as C


def pool(rng, count, *, sides=6, offset=0, fixed=None):
    """Observe an ordinary pool, retaining faces and stable die-path evidence.

    Fixed observations must describe the entire pool and consume no RNG. All
    declared inputs are checked before the first random observation.
    """
    C.integer(count, 'pool count', 0)
    C.integer(sides, 'die sides', 1)
    C.integer(offset, 'pool offset')
    if fixed is not None:
        if type(fixed) not in (list, tuple) or len(fixed) != count:
            raise ValueError('fixed dice count mismatch: one observation per declared die required')
        fixed = {str(i): face for i, face in enumerate(fixed)}
    observations = recursive(rng, count, sides=sides, repeat_faces=(), fixed=fixed)
    faces = [row['face'] for row in observations]
    return {'count': count, 'sides': sides, 'offset': offset, 'faces': faces,
            'observations': observations, 'total': sum(faces) + offset}


def expression(rng, expr, *, dice_multiplier=1, flat_bonus_multiplier=1, fixed=None):
    """Roll NdS[+/-B], scaling dice count and flat bonus independently.

    This is arithmetic only: the native rule caller chooses both multipliers.
    It does not infer critical-hit, payment, or effect-consumption policies.
    """
    if type(expr) is not str:
        raise ValueError('dice expression must be text')
    match = re.fullmatch(r'([0-9]+)d([0-9]+)([+-][0-9]+)?', expr)
    if match is None:
        raise ValueError('unsupported dice expression')
    C.integer(dice_multiplier, 'dice multiplier', 0)
    C.integer(flat_bonus_multiplier, 'flat bonus multiplier', 0)
    count, sides = int(match[1]), int(match[2])
    offset = int(match[3] or 0) * flat_bonus_multiplier
    return pool(rng, count * dice_multiplier, sides=sides, offset=offset, fixed=fixed)


def die(rng, sides=6, *, fixed=None):
    """One declared die, with the same fixed-observation and RNG contract."""
    return pool(rng, 1, sides=sides, fixed=None if fixed is None else [fixed])['faces'][0]


def recursive(rng, count, *, sides=6, repeat_faces=(6,), repeat=False, fixed=None, on_face=None):
    """Breadth-first pool with stable die paths and per-face observation hooks.

    A hook runs before a repeated child is queued, preserving interleaved reward
    RNG. This primitive does not roll back observations or grant gameplay use;
    its native caller chooses the appropriate transaction boundary.
    """
    C.integer(count,'pool count',0);C.integer(sides,'die sides',1)
    if type(repeat_faces) not in (list,tuple) or len(set(repeat_faces))!=len(repeat_faces):
        raise ValueError('distinct repeat faces required')
    for face in repeat_faces:C.integer(face,'repeat face',1,sides)
    if type(repeat) is not bool and not isinstance(repeat,(set,frozenset)):
        raise ValueError('repeat choice must be bool or explicit die paths')
    paths=set() if type(repeat) is bool else set(repeat)
    if any(type(path) is not str or not path for path in paths):raise ValueError('invalid repeat path')
    if fixed is not None:
        if type(fixed) is not dict:raise ValueError('fixed dice must map die paths to faces')
        for path,face in fixed.items():
            if type(path) is not str or not path:raise ValueError('invalid fixed path')
            C.integer(face,'fixed pool face',1,sides)
    if on_face is not None and not callable(on_face):raise ValueError('face observer must be callable')
    queue=deque(str(i) for i in range(count));results=[];used=set();selected=set()
    while queue:
        path=queue.popleft()
        if fixed is not None:
            if path not in fixed:raise ValueError('missing fixed pool face')
            face=fixed[path];used.add(path)
        else:face=C.integer(rng.randint(1,sides),'pool face',1,sides)
        extra={} if on_face is None else on_face(path,face)
        if type(extra) is not dict or set(extra)&{'path','face','rerolled'}:
            raise ValueError('face observer metadata conflicts with pool evidence')
        again=face in repeat_faces and (repeat is True or path in paths)
        if again:selected.add(path);queue.append(path+'.1')
        results.append(dict(extra,path=path,face=face,rerolled=again))
    if paths-selected:raise ValueError('selected repeat path did not produce a repeat face')
    if fixed is not None and set(fixed)!=used:raise ValueError('unused fixed pool faces')
    return results


def select(faces, *, operation, indices, replacements=None, rng=None, sides=6):
    """One declared keep/drop/replace/reroll step on original die indices."""
    C.integer(sides,'die sides',1)
    if type(faces) not in (list,tuple):raise ValueError('ordered observed faces required')
    original=tuple(C.integer(x,'observed face',1,sides) for x in faces)
    if type(indices) not in (list,tuple):raise ValueError('ordered distinct die indices required')
    for index in indices:C.integer(index,'die index',0,len(original)-1)
    if len(set(indices))!=len(indices):raise ValueError('duplicate die index')
    if operation not in ('keep','drop','replace','reroll'):raise ValueError('explicit die operation required')
    if operation=='replace':
        if type(replacements) not in (list,tuple) or len(replacements)!=len(indices):raise ValueError('one replacement per selected die required')
        for face in replacements:C.integer(face,'replacement face',1,sides)
    elif replacements is not None:raise ValueError('replacement faces require replace operation')
    if operation=='reroll' and rng is None:raise ValueError('reroll RNG required')
    selected=set(indices);result=list(original);changes=[]
    if operation in ('keep','drop'):
        retained=[i for i in range(len(original)) if (i in selected)==(operation=='keep')]
        result=[original[i] for i in retained]
    else:
        retained=list(range(len(original)))
        for offset,index in enumerate(indices):
            face=replacements[offset] if operation=='replace' else die(rng,sides)
            changes.append({'index':index,'before':original[index],'after':face});result[index]=face
    return {'operation':operation,'original':original,'indices':tuple(indices),'retained_indices':tuple(retained),'faces':tuple(result),'changes':changes}


def score_faces(faces, table, *, dimensions, override=None, sides=6):
    """Score every observed face through a declared table, retaining evidence."""
    C.integer(sides,'die sides',1)
    if type(faces) not in (list,tuple):raise ValueError('ordered observed faces required')
    if type(dimensions) not in (list,tuple) or not dimensions or any(type(x) is not str or not x for x in dimensions) or len(set(dimensions))!=len(dimensions):
        raise ValueError('distinct score dimensions required')
    if type(table) is not dict or set(table)!={str(i) for i in range(1,sides+1)}:raise ValueError('complete face score table required')
    if override is None:override={}
    if type(override) is not dict or set(override)-set(table):raise ValueError('invalid face score override')
    resolved={}
    for key,base in table.items():
        extra=override.get(key,{})
        if type(base) is not dict or type(extra) is not dict or (set(base)|set(extra))-set(dimensions):raise ValueError('unknown face score dimension')
        cell=dict(base);cell.update(extra)
        resolved[key]={dimension:C.integer(cell.get(dimension,0),'face score') for dimension in dimensions}
    totals=dict.fromkeys(dimensions,0);trace=[]
    for index,face in enumerate(faces):
        C.integer(face,'scored face',1,sides);cell=resolved[str(face)]
        for dimension,value in cell.items():totals[dimension]+=value
        trace.append({'index':index,'face':face,'scores':dict(cell)})
    return {'totals':totals,'trace':trace}
