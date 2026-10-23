"""An explicitly supplied enemy accuracy sheet, consumed by native producers.

The application/GM supplies already generated faces. No random generator,
combat policy, damage default, spatial shortcut or automatic reset lives here.
"""
from copy import deepcopy
import common_checks as C
import resolution_transaction as TX
import source_context as SOURCE_CONTEXT
import state_grants as G
import world_entities as W

FIELD = '_enemy_accuracy_sheet'
SOURCE = 'ch11-running-the-game/빠른-포켓몬-스탯분배/더-빠른-전투-진행'
REFERENCE = {'file': 'input/ch11-running-the-game.md',
             'sha256': '5311a50a2c70748465fe6fd73b52a8abbf337a11791509d88a15e19295232dad'}


def _source(e):
    if e.r._selected_rule(SOURCE) != SOURCE or SOURCE in e.r.ruleset.unit_versions:
        raise ValueError('selected fast-combat source required')
    selected = e.r.selection.units[SOURCE]['source']
    if (selected.get('file') != REFERENCE['file'].removeprefix('input/')
            or selected.get('sha256') != REFERENCE['sha256']
            or e.r.rulings.mech.get(SOURCE) or e.r.rulings.effects.get(SOURCE)):
        raise ValueError('fast-combat source replacement needs its own policy')
    SOURCE_CONTEXT.verified_source(e.r, REFERENCE, label='enemy accuracy sheet')


def _declaration(e, sheet_id, enemy_ids, faces, reason, *, admitting=True):
    G._text(sheet_id, 'enemy accuracy sheet ID')
    G._text(reason, 'enemy accuracy sheet adoption reason')
    if (type(enemy_ids) is not list or not enemy_ids
            or any(type(uid) is not str or not uid.strip() for uid in enemy_ids)
            or len(set(enemy_ids)) != len(enemy_ids)):
        raise ValueError('distinct actual enemy IDs required')
    index = W.actor_index(e)
    if not set(enemy_ids) <= set(index):
        raise ValueError('accuracy sheet enemies must be actual registered actors')
    if admitting and any(getattr(index[uid], 'side', 'party') == 'party' for uid in enemy_ids):
        raise ValueError('accuracy sheet cannot enroll party actors as enemies')
    if type(faces) is not list or not faces:
        raise ValueError('explicit nonempty pregenerated d20 sheet required')
    for face in faces:
        C.integer(face, 'pregenerated accuracy face', 1, 20)
    return dict(sheet_id=sheet_id, enemy_ids=deepcopy(enemy_ids), faces=deepcopy(faces),
                reason=reason, source=deepcopy(REFERENCE))


def validate(e):
    state = getattr(e, FIELD, None)
    if state is None:
        return None
    _source(e)
    if type(state) is not dict or set(state) != {'declaration', 'sha256', 'cursor', 'adoptions'}:
        raise ValueError('enemy accuracy sheet state changed')
    row = state['declaration']
    if (type(row) is not dict
            or set(row) != {'sheet_id', 'enemy_ids', 'faces', 'reason', 'source'}
            or row['source'] != REFERENCE
            or state['sha256'] != TX.request_fingerprint(row)):
        raise ValueError('enemy accuracy sheet declaration changed')
    _declaration(e, row['sheet_id'], row['enemy_ids'], row['faces'], row['reason'], admitting=False)
    C.integer(state['cursor'], 'enemy accuracy sheet cursor', 0, len(row['faces']))
    receipts = state['adoptions']
    if type(receipts) is not dict or row['sheet_id'] not in receipts:
        raise ValueError('enemy accuracy sheet adoption receipt missing')
    for key, receipt in receipts.items():
        if (type(key) is not str or not key.strip() or type(receipt) is not dict
                or set(receipt) != {'sheet_id', 'sha256'} or receipt['sheet_id'] != key
                or type(receipt['sha256']) is not str or len(receipt['sha256']) != 64
                or any(ch not in '0123456789abcdef' for ch in receipt['sha256'])):
            raise ValueError('enemy accuracy sheet adoption receipt changed')
    if receipts[row['sheet_id']]['sha256'] != state['sha256']:
        raise ValueError('active enemy accuracy sheet adoption disagrees')
    return state


def adopt(e, *, sheet_id, enemy_ids, faces, reason):
    """Bind an external sheet, or the next explicit sheet after full exhaustion."""
    _source(e)
    row = _declaration(e, sheet_id, enemy_ids, faces, reason, admitting=False)
    old = validate(e)
    if old is not None:
        replay = TX.replay_result(old['adoptions'], sheet_id, row, fingerprint_field='sha256')
        if replay is not None:
            return replay
        if old['cursor'] != len(old['declaration']['faces']):
            raise ValueError('consume the adopted enemy accuracy sheet before supplying the next sheet')
    _declaration(e, sheet_id, enemy_ids, faces, reason)
    receipt = {'sheet_id': sheet_id}
    TX.bind_request_intent(receipt, row, field='sha256')

    def apply(staged, _):
        receipts = deepcopy(old['adoptions']) if old is not None else {}
        receipts[sheet_id] = deepcopy(receipt)
        state = dict(declaration=deepcopy(row), sha256=receipt['sha256'], cursor=0,
                     adoptions=receipts)
        setattr(staged, FIELD, state)
        staged.gm._rec('적 사전 명중 수열', None, sheet_id, reason)
        return deepcopy(receipt)
    return G.transition(e, None, apply, include_rulings=True)


def require_faces(e, actor, count=1):
    """Check available sheet observations without drawing or charging anything."""
    C.integer(count, 'required accuracy observations', 0)
    state = validate(e)
    if state is None or actor.entity_id not in state['declaration']['enemy_ids']:
        return False
    if W.actor_index(e).get(actor.entity_id) is not actor:
        raise ValueError('accuracy sheet requires its actual enemy actor')
    if getattr(actor, 'side', 'party') == 'party':
        return False
    if state['cursor'] + count > len(state['declaration']['faces']):
        raise ValueError('pregenerated enemy accuracy sheet exhausted')
    return True


def preflight_move(e, actor, target, move, mechanics, *, shared_accuracy=None, reliable_trainer=None):
    """Reserve no faces; native activation still owns all action/roll authority."""
    import equipment_actions as EQUIPMENT
    import move_accuracy as ACCURACY
    import effects_ext as EXT
    if (reliable_trainer is not None or EQUIPMENT.automatic_accuracy(e, actor, target, move)
            or ACCURACY.no_status_check(e, actor, target, move, mechanics)):
        return
    multi = EXT.multi_roll_spec(mechanics)
    count = int(multi.get('rolls', 3)) if multi is not None else 1
    observed = len(shared_accuracy.get('rolls', [])) if shared_accuracy is not None else 0
    require_faces(e, actor, max(0, count - observed))


def roll(e, actor):
    """Supply exactly one natural to an actual native accuracy producer."""
    import duelist as DUELIST
    if DUELIST.choose_eleven(e,actor,'accuracy'):return 11
    if not require_faces(e, actor):
        return e.d20()
    state = getattr(e, FIELD)
    cursor = state['cursor']
    face = state['declaration']['faces'][cursor]
    state['cursor'] += 1
    e.log(f"    적 사전 명중 {state['declaration']['sheet_id']}[{cursor + 1}] = {face}", SOURCE)
    return face
