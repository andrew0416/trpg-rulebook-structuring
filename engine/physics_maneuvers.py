import body_state as BODY
"""Source-specific Push and Trip; only their proven roll plumbing is shared.

Repeated Push remains an explicit unresolved source procedure. It does not get
invented checks, unlimited follow movement, or an extra automatic Shift.
"""
import common_checks as C
import turn as TURN
import skill_modifiers as SKILLS
import skill_maneuver_actions as SM
from grid import cheb
from physical_limits import number

PUSH='maneuver/밀기'
TRIP='maneuver/걸기'

from maneuver_opposed import _options, _prepare, _run


def trip(e,a,t,*,challenger_skill,defender_skill,fixed_accuracy=None,challenger_options=None,defender_options=None,_grant=None):
    plans,prepared=_prepare(e,a,t,TRIP,('전투','곡예'),challenger_skill,defender_skill,fixed_accuracy,challenger_options,defender_options,{},_grant)
    def outcome(won):
        if not won:return False
        e.apply_status(t,'넘어짐')
        e.log('  '+t.name+': 걸기 대항 패배로 넘어짐',TRIP)
        return True
    return _run(e,a,t,TRIP,6,plans,prepared,outcome,fixed_accuracy,_grant)

def push(e,a,t,*,challenger_skill,defender_skill,fixed_accuracy=None,challenger_options=None,defender_options=None,follow_steps=0,_grant=None):
    C.integer(follow_steps,'Push follow movement count',0)
    if follow_steps:
        return C.PendingDecision('Repeated Push requires a selected repeat-check procedure and actual remaining-round movement accounting',basis={'source':PUSH,'follow_steps':follow_steps})
    import capability_actions as CAP
    weight=number(BODY.weight_kg(t),'actual target body weight in kilograms',minimum=0)
    limit=CAP.limits(a)['heavy'][1]
    if weight>limit and __import__('type_ace').threaded_scope(e,a) is None:raise ValueError('Push target is heavier than actual Heavy Lifting rating')
    origin_a=tuple(a.pos);origin_t=tuple(t.pos)
    dx=(origin_t[0]>origin_a[0])-(origin_t[0]<origin_a[0]);dy=(origin_t[1]>origin_a[1])-(origin_t[1]<origin_a[1])
    if dx and dy:return C.PendingDecision('diagonal one-metre forced Push geometry',basis={'source':PUSH})
    destination=(origin_t[0]+dx,origin_t[1]+dy)
    import forced_movement as FORCED
    if not FORCED.can_step(e,t,destination):
        return C.PendingDecision('Push collision or unavailable destination; source grants no collision damage',basis={'source':PUSH,'destination':destination})
    plans,prepared=_prepare(e,a,t,PUSH,('전투','육상'),challenger_skill,defender_skill,fixed_accuracy,challenger_options,defender_options,{'weight_kg':weight,'heavy_lifting_kg':limit,'destination':destination,'follow_steps':0},_grant)
    def outcome(won):
        if not won:return False
        if __import__('type_ace').push_immunity(e,t):return {'pushed_metres':0,'target_position':tuple(t.pos),'follow_metres':0,'prevented_by':'Insectoid Utility'}
        if tuple(a.pos)!=origin_a or tuple(t.pos)!=origin_t or not FORCED.can_step(e,t,destination):
            return C.PendingDecision('actual Push geometry changed during its native resolution',basis={'source':PUSH,'destination':destination})
        result=FORCED.displace(e,a,t,direction=(dx,dy),distance=1,source=PUSH)
        if result['stopped_by']=='immune':return {'pushed_metres':0,'target_position':tuple(t.pos),'follow_metres':0,'prevented_by':'coat'}
        e.log('  '+a.name+': '+t.name+'을 바로 뒤로 1m 밀기',PUSH)
        import stat_ace as STAT
        STAT.maneuver_success(e,a,t,PUSH)
        return {'pushed_metres':1,'target_position':destination,'follow_metres':0}
    return _run(e,a,t,PUSH,4,plans,prepared,outcome,fixed_accuracy,_grant)
