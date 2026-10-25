"""Chef class cooking: taste assignment, chef-made food batches, Dumplings
composition, Hearty Meal max-AP state and Accentuated Taste bonuses.

Digestion Buffs remain owned by food_effects, the two 1-AP triggered reactions
(Hits the Spot, Complex Aftertaste) by class_actor_state_actions, the Tutor
Point Ability lesson (Culinary Appreciation) by feature_ability_lessons and
Vitamin capacity (Dietician) by vitamin_capacity.  Acquisition uses the shared
static trainer-feature receipts; cooking uses the shared recipe admission,
time, payment and transformation ledger.  Chef-made food lives in per-cook
batches with explicit provenance; ordinary inventory snacks are unchanged.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json

import common_checks as C

POLICY = 'data/chef-definitions.json'
CLASS = 'class/요리사'
HITS = 'feat/이-맛이야'
APPRECIATION = 'feat/요리-음미'
ACCENTUATED = 'feat/특색있는-맛'
AFTERTASTE = 'feat/복잡한-뒷맛'
DIETICIAN = 'feat/영양사'
DUMPLINGS = 'feat/경단'
CHEF_SOURCE = 'ch04-trainer-classes/프로페셔널-클래스'
TASTY = 'recipe/맛있는-간식'
HEARTY = 'recipe/푸짐한-식사'
PRESERVES = 'recipe/프리저브스'
LEFTOVERS = 'recipe/먹다남은음식'
HEARTY_ITEM = 'item/푸짐한-식사'
LEFTOVERS_ITEM = 'item/먹다남은음식'
KEY = 'chef_batches'
SERIAL = 'chef_batch_serial'
MEAL = 'hearty_meal'
BONUS = 'chef_taste_bonus'
RULING = 'chef_taste_bonus_lifetime'
BATCH_KINDS = ('tasty_snack', 'hearty_meal', 'preserves', 'leftovers', 'dumplings')
SNACK_BATCH_KINDS = ('tasty_snack', 'preserves', 'leftovers', 'dumplings')
IMMEDIATE_KINDS = ('heal', 'cure', 'turn_heal')
TRIGGER_KINDS = ('chef_snack', 'type_resistance')
BONUS_FIELDS = {'critical_range': 'chef_critical_range', 'evasion_damaging': 'chef_evasion_damaging',
                'effect_range': 'chef_effect_range', 'save_check': 'save_modifier', 'initiative': 'chef_initiative'}

_CACHE = {}
_VERIFIED = set()
_RAW = json.loads((Path(__file__).resolve().parents[1] / POLICY).read_text(encoding='utf-8'))
FEATURES = {CLASS: tuple(_RAW['class_definition']['span']), **{uid: tuple(row['span']) for uid, row in _RAW['features'].items()}}
STATIC_DEFINITIONS = {CLASS: dict(_RAW['class_definition'], clause_id=_RAW['class_definition']['clause_id']),
                      **{uid: dict(row) for uid, row in _RAW['features'].items()}}
CHEF_FEATURES = tuple(FEATURES)


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + ' required')
    return value


def _policy_path(rules):
    canonical = Path(rules.root) / POLICY
    return canonical if canonical.is_file() else Path(__file__).resolve().parents[1] / POLICY


def definitions(rules):
    """Read the reviewed Chef definitions and verify every bound source each call."""
    path = _policy_path(rules)
    body = path.read_bytes()
    digest = hashlib.sha256(body).hexdigest()
    cached = _CACHE.get(digest)
    if cached is None:
        data = json.loads(body.decode('utf-8'))
        if data.get('schema_version') != 1 or data.get('class') != CLASS:
            raise ValueError('unsupported Chef definition policy')
        _CACHE[digest] = data
        cached = data
    data = cached
    root = Path(rules.root)
    key = (digest, str(root), id(rules))
    if key in _VERIFIED:
        return data
    if hashlib.sha256((root / data['source_file']).read_bytes()).hexdigest() != data['source_sha256']:
        raise ValueError('Chef source file changed: ' + data['source_file'])
    lines = (root / data['source_file']).read_text(encoding='utf-8').splitlines()
    for uid, row in data['features'].items():
        span = row['span']
        excerpt = '\n'.join(lines[span[0] - 1:span[1]])
        if hashlib.sha256(excerpt.encode('utf-8')).hexdigest() != row['excerpt_sha256']:
            raise ValueError('Chef feature excerpt changed: ' + uid)
        unit = rules.selection.units.get(uid, {}).get('source', {})
        if unit.get('lines') != row['catalog_span'] or unit.get('sha256') != data['source_sha256']:
            raise ValueError('Chef feature catalog binding changed: ' + uid)
    source = data['recipe_source']
    recipe_path = root / source['file']
    if hashlib.sha256(recipe_path.read_bytes()).hexdigest() != source['file_sha256']:
        raise ValueError('Chef recipe source file changed')
    import csv
    import resolution_transaction as FINGERPRINTS
    with recipe_path.open(encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.reader(handle))
    for uid, row in data['recipes'].items():
        cells = [rows[row['record'] - 1][column - 1] for column in source['columns']]
        if FINGERPRINTS.json_fingerprint(cells, sort_keys=False, compact=True, allow_nan=True) != row['cell_sha256']:
            raise ValueError('Chef recipe cells changed: ' + uid)
        if rules._selected_rule(uid) != uid:
            raise ValueError('selected Chef recipe needs its own policy: ' + uid)
    for uid in (CLASS, *data['features']):
        if rules._selected_rule(uid) != uid:
            raise ValueError('selected Chef feature needs its own policy: ' + uid)
    prohibition = data['dumplings']['nested_dumplings_prohibition']
    if rules.ruleset.allows(prohibition)[0]:
        source = prohibition['source']
        if hashlib.sha256((root / source['file']).read_bytes()).hexdigest() != source['sha256']:
            raise ValueError('Dumplings errata source changed')
    _VERIFIED.add(key)
    return data


def _nested_dumplings_allowed(rules):
    rule = definitions(rules)['dumplings']
    return rule['nested_dumplings'] and not rules.ruleset.allows(rule['nested_dumplings_prohibition'])[0]


def _composite_parts(parts):
    """Keep the two actual ingredients in the batch; consumers receive their leaf effects once."""
    return [deepcopy(leaf) for part in parts for leaf in
            (part['effect']['components'] if part['effect']['kind'] == 'chef_composite'
             else [{'item': part['item'], 'effect': part['effect']}])]


# ---------- acquisition (shared static receipts) ----------

def _acquisitions(actor, feature, active=False):
    import trainer_feature_acquisition as T
    return [record for _, record in T.static_acquisitions(actor, feature, active=active)]


def _owned(actor, uid):
    import acquired_features as A
    return A.owned_rule_count(actor, uid) > 0


def _parent_reference(actor, uid):
    rows = _acquisitions(actor, uid, True)
    if rows:
        return rows[0]['request_id']
    if _owned(actor, uid):
        return uid
    raise ValueError('actual acquired Chef prerequisite required: ' + uid)


def _intuition(actor):
    import skill_modifiers as S
    return S.rank(actor.r, actor, '직감')[2]


def chef_feature_count(actor, exclude=()):
    """Count acquired Chef Features; the [Class] entry counts as one Feature."""
    data = definitions(actor.r)
    uids = [uid for uid in CHEF_FEATURES if uid not in exclude and (uid != CLASS or data['class_counts_as_feature'])]
    return sum(1 for uid in uids if _owned(actor, uid))


def acquisition_snapshot(engine, actor, feature):
    data = definitions(engine.r)
    if feature == CLASS:
        import pokemon_activities as P
        P._feature(engine, actor, 'basic_cooking')
        return {'parent': data['class_definition']['prerequisites']['edge'], 'intuition': _intuition(actor)}
    row = data['features'][feature]
    result = {'parents': {uid: _parent_reference(actor, uid) for uid in row['parents']}, 'intuition': _intuition(actor)}
    if feature == DUMPLINGS:
        result['chef_features'] = [uid for uid in CHEF_FEATURES if uid != DUMPLINGS and _owned(actor, uid)]
    return result


def qualification(actor, feature, snapshot, prerequisite_source):
    import acquisition_qualification as Q
    data = definitions(actor.r)
    if prerequisite_source is not None or type(snapshot) is not dict:
        raise ValueError('exact Chef acquisition observations required')
    C.integer(snapshot.get('intuition'), 'Chef Intuition rank', 0)
    checks = [Q.check('trainer', 'prerequisite', actor.kind == 'trainer', 'actual Trainer required')]
    if feature == CLASS:
        if set(snapshot) != {'parent', 'intuition'} or snapshot['parent'] != data['class_definition']['prerequisites']['edge']:
            raise ValueError('Basic Cooking prerequisite identity changed')
        minimum = data['class_definition']['prerequisites']['intuition_rank']
        checks.append(Q.check('edge', 'prerequisite', _owned(actor, snapshot['parent']), 'Chef requires the acquired Basic Cooking Edge'))
    else:
        row = data['features'][feature]
        fields = {'parents', 'intuition'} | ({'chef_features'} if feature == DUMPLINGS else set())
        if set(snapshot) != fields or set(snapshot['parents']) != set(row['parents']):
            raise ValueError('printed Chef prerequisites required')
        for uid, reference in snapshot['parents'].items():
            if reference != uid and not any(r['request_id'] == reference for r in _acquisitions(actor, uid)):
                raise ValueError('actual historical Chef prerequisite acquisition required')
            if reference == uid and not _owned(actor, uid):
                raise ValueError('actual acquired Chef prerequisite required: ' + uid)
        minimum = row['intuition_rank']
        if feature == DUMPLINGS:
            listed = snapshot['chef_features']
            if type(listed) is not list or len(set(listed)) != len(listed) or any(uid not in CHEF_FEATURES or uid == DUMPLINGS for uid in listed):
                raise ValueError('actual acquired Chef Feature list required')
            checks.append(Q.check('chef_features', 'prerequisite', len(listed) >= row['chef_features'] and all(_owned(actor, uid) for uid in listed),
                                  'Dumplings requires four acquired Chef Features'))
    checks.append(Q.check('intuition', 'prerequisite', snapshot['intuition'] >= minimum, 'printed Intuition rank required'))
    return Q.require(feature, 'native', 'acquire', checks)


# ---------- taste helpers ----------

def taste_of(buff):
    row = buff.get('taste_assignment') if isinstance(buff, dict) else None
    return row.get('taste') if isinstance(row, dict) else None


def _tasty_item(rules, taste):
    for uid, flavor in definitions(rules)['tasty_snacks'].items():
        if flavor == taste:
            return uid
    raise ValueError('no basic Tasty Snack recipe matches taste ' + str(taste))


def _validate_taste(rules, row, *, kind, item_id=None):
    data = definitions(rules)
    if row is None:
        return None
    if type(row) is not dict or set(row) != {'taste', 'source', 'assigned_by', 'basis'}:
        raise ValueError('typed Chef taste assignment required')
    if row['source'] != ACCENTUATED or row['basis'] not in ('cooking', 'complex_aftertaste'):
        raise ValueError('taste assignment source changed')
    _text(row['assigned_by'], 'taste assigning trainer')
    if kind == 'tasty_snack' or row['basis'] == 'complex_aftertaste':
        if row['taste'] != data['tasty_snacks'].get(item_id):
            raise ValueError('Tasty Snacks must carry their corresponding Taste')
    elif row['taste'] not in data['tastes']['assignable']:
        raise ValueError('assigned Taste outside the printed choice')
    return row


# ---------- batches ----------

def batches(actor):
    rows = actor.spec.get(KEY, {})
    if type(rows) is not dict:
        raise ValueError('Chef batches must be a mapping')
    return rows


def _batch(actor, batch_id):
    row = batches(actor).get(batch_id)
    if row is None:
        raise ValueError('actual owned Chef batch required')
    return row


def _expected_payload(rules, row):
    import food_effects as FOOD
    kind = row['kind']
    if kind == 'tasty_snack':
        return FOOD.chef_effect(rules, row['item_id'])
    if kind == 'leftovers':
        return FOOD.snack_effect(rules, LEFTOVERS_ITEM)
    if kind == 'preserves':
        return FOOD.snack_effect(rules, row['origin_item'])
    if kind == 'dumplings':
        return {'kind': 'chef_composite', 'components': _composite_parts(row['components'])}
    return None


def _validate_batch(actor, batch_id, row):
    data = definitions(actor.r)
    required = {'id', 'kind', 'recipe', 'item_id', 'count', 'units', 'created_at', 'gap_count', 'created_by', 'taste', 'payload', 'served'}
    if type(row) is not dict or set(row) - (required | {'origin_item', 'components', 'ingredients', 'production_id'}) or set(row) & required != required:
        raise ValueError('exact Chef batch fields required')
    if row['id'] != batch_id or row['kind'] not in BATCH_KINDS or row['created_by'] != actor.entity_id:
        raise ValueError('Chef batch identity or cook changed')
    recipe = data['recipes'].get(row['recipe'])
    if row['kind'] == 'dumplings':
        if row['recipe'] != DUMPLINGS:
            raise ValueError('Dumplings batch recipe changed')
    elif recipe is None or recipe['kind'] != row['kind']:
        raise ValueError('Chef batch recipe changed')
    C.integer(row['units'], 'Chef batch units', 1)
    C.integer(row['count'], 'Chef batch remaining units', 0, row['units'])
    C.integer(row['created_at'], 'Chef batch creation time', 0)
    C.integer(row['gap_count'], 'Chef batch unknown-interval count', 0)
    if type(row['served']) is not list or len(row['served']) != row['units'] - row['count']:
        raise ValueError('Chef batch service history disagrees with its remaining units')
    item_id = row['item_id']
    if row['kind'] == 'hearty_meal':
        if item_id != HEARTY_ITEM or row['payload'] is not None:
            raise ValueError('Hearty Meal batch payload changed')
    else:
        if actor.r.item_effects(item_id)[1].get('id') != item_id:
            raise ValueError('Chef batch item identity changed')
        if row['kind'] == 'tasty_snack' and item_id not in data['tasty_snacks']:
            raise ValueError('Tasty Snack batch item changed')
        if row['kind'] == 'leftovers' and item_id != LEFTOVERS_ITEM:
            raise ValueError('Leftovers batch item changed')
        if row['kind'] == 'preserves' and (row.get('origin_item') != item_id or not isinstance(item_id, str)):
            raise ValueError('Preserves batch origin changed')
        if row['kind'] == 'dumplings':
            parts = row.get('components')
            if type(parts) is not list or len(parts) != 2 or parts[0]['item'] != item_id:
                raise ValueError('Dumplings batch needs its two components')
            _validate_components(actor.r, parts)
            for index, part in enumerate(parts):
                if part['batch_kind'] != 'dumplings':
                    continue
                origin = part['ingredient']
                if type(origin) is not dict or set(origin) != {'kind', 'batch_id', 'taste'} or origin['kind'] != 'batch':
                    raise ValueError('nested Dumplings needs its actual ingredient batch')
                parent = batches(actor).get(origin['batch_id'])
                debits = row.get('ingredients')
                if (parent is None or parent is row or parent['kind'] != 'dumplings'
                        or parent['created_at'] >= row['created_at'] or parent['item_id'] != part['item']
                        or parent['payload'] != part['effect'] or parent['taste'] != origin['taste']
                        or type(debits) is not list or len(debits) != 2
                        or debits[index] != {'kind': 'batch', 'batch_id': parent['id']}):
                    raise ValueError('nested Dumplings ingredient provenance changed')
        if row['payload'] != _expected_payload(actor.r, row):
            raise ValueError('Chef batch payload differs from its source effect')
    _validate_taste(actor.r, row['taste'], kind=row['kind'], item_id=item_id)
    return row


def _validate_components(rules, parts):
    import food_effects as FOOD
    data = definitions(rules)
    seen = []
    for part in parts:
        if type(part) is not dict or set(part) != {'item', 'effect', 'ingredient', 'batch_kind'}:
            raise ValueError('typed Dumplings component required')
        if part['batch_kind'] not in ('leftovers', 'preserves', 'tasty_snack', 'inventory_leftovers', 'dumplings'):
            raise ValueError('Dumplings component kind changed')
        if part['batch_kind'] == 'dumplings':
            if not _nested_dumplings_allowed(rules):
                raise ValueError('Dumplings cannot be mixed from another Dumplings under the selected errata')
            validate_composite(rules, {'item': part['item'], 'effect': part['effect'], 'effect_source': DUMPLINGS})
        else:
            effect = FOOD.snack_effect(rules, part['item'])
            if effect is None or part['effect'] != effect or effect['kind'] not in data['dumplings']['composite_component_kinds']:
                raise ValueError('Dumplings component effect differs from its source')
        identity = (part['batch_kind'] if part['batch_kind'] != 'inventory_leftovers' else 'leftovers', part['item'])
        if identity in seen:
            raise ValueError('the two Dumplings ingredients must be different items')
        seen.append(identity)


def validate_actor(actor):
    rows = batches(actor)
    if rows and actor.kind != 'trainer':
        raise ValueError('Chef batches belong to a trainer cook')
    for batch_id, row in rows.items():
        _validate_batch(actor, batch_id, row)
    C.integer(actor.spec.get(SERIAL, 0), 'Chef batch serial', len(rows))
    meal = actor.spec.get(MEAL)
    if meal is not None:
        data = definitions(actor.r)
        recipe = data['recipes'][HEARTY]
        if actor.kind != 'trainer' or type(meal) is not dict or set(meal) != {'source', 'recipe', 'ap_bonus', 'ends', 'eaten_at', 'batch_id', 'cook_id', 'taste'}:
            raise ValueError('typed Hearty Meal effect required')
        if meal['source'] != HEARTY_ITEM or meal['recipe'] != HEARTY or meal['ap_bonus'] != recipe['ap_bonus'] or meal['ends'] != recipe['ends']:
            raise ValueError('Hearty Meal effect payload changed')
        C.integer(meal['eaten_at'], 'Hearty Meal intake time', 0)
        _text(meal['batch_id'], 'Hearty Meal batch')
        _text(meal['cook_id'], 'Hearty Meal cook')
        _validate_taste(actor.r, meal['taste'], kind='hearty_meal')
    import combat_timing as TIMING
    for record in TIMING.records(actor):
        bonus = record.get(BONUS)
        if bonus is None:
            continue
        _validate_bonus_record(actor, record, bonus)
    return True


def validate_world(engine, index):
    for actor in index.values():
        validate_actor(actor)
    return True


# ---------- cooking ----------

def _duration(e, minutes, reason):
    import pokemon_activities as P
    P._outside(e)
    C.integer(minutes, 'GM cooking duration minutes', 1)
    P._text(reason, 'GM cooking duration reason')


def _names(rules, uid):
    unit = rules.selection.units[uid]
    return list(dict.fromkeys(x for x in (uid, unit.get('title'), unit.get('eng')) if x))


def _requirements(e, actor, prerequisites):
    import pokemon_activities as P
    data = definitions(e.r)
    conditions = [{'kind': 'owned', 'fields': ['classes', 'feats'], 'names': _names(e.r, CLASS)},
                  {'kind': 'owned', 'fields': ['edges'], 'names': [P.FEATURES['basic_cooking'][0], *P.FEATURES['basic_cooking'][1]]},
                  {'kind': 'skill', 'skill': '직감', 'rank': data['class_definition']['prerequisites']['intuition_rank'], 'effective': False}]
    for uid in prerequisites:
        if uid == CLASS:
            continue
        conditions.append({'kind': 'owned', 'fields': ['feats'], 'names': _names(e.r, uid)})
    tool = data['tool']
    return [{'id': 'permission', 'condition': {'kind': 'all', 'conditions': conditions}, 'reason': 'acquired Chef recipe provider and actual skill prerequisite required'},
            {'id': 'tool', 'condition': {'kind': 'tool', 'item_id': tool['item'], 'names': list(tool['names']), 'instance_id': None}, 'reason': 'required equipment is not accessible: ' + tool['names'][0]}]


def _assign_taste(e, actor, *, kind, item_id, taste):
    """Accentuated Taste: optional for Chef Snacks, mandatory and fixed for Tasty Snacks."""
    data = definitions(e.r)
    accentuated = _owned(actor, ACCENTUATED)
    if kind == 'tasty_snack':
        corresponding = data['tasty_snacks'][item_id]
        if not accentuated:
            if taste is not None:
                raise ValueError('taste assignment requires acquired Accentuated Taste')
            return None
        if taste is not None and taste != corresponding:
            raise ValueError('Tasty Snacks must be assigned their corresponding Taste')
        taste = corresponding
    elif taste is None:
        return None
    elif not accentuated:
        raise ValueError('taste assignment requires acquired Accentuated Taste')
    elif taste not in data['tastes']['assignable']:
        raise ValueError('assigned Taste must be one of ' + ', '.join(data['tastes']['assignable']))
    return {'taste': taste, 'source': ACCENTUATED, 'assigned_by': actor.entity_id, 'basis': 'cooking'}


def _inventory_key(actor, item_id):
    inventory = actor.spec.get('items', {})
    for key in (item_id, item_id.split('/', 1)[1], item_id.split('/', 1)[1].replace('-', ' ')):
        if type(inventory.get(key)) is int and inventory[key] > 0:
            return key
    raise ValueError('insufficient owned ingredient: ' + item_id)


def _declaration(e, actor, *, recipe_id, source, output_item, prerequisites, materials, seconds):
    return {'id': 'native:chef:' + recipe_id.split('/', 1)[1], 'source': source,
            'output': {'item_id': output_item, 'key': output_item},
            'requirements': _requirements(e, actor, prerequisites), 'materials': materials, 'seconds': seconds}


def _run(e, actor, declaration, *, inputs, reason, context):
    """Admit, spend the action, run the fixed job, pay; the caller stores the batch."""
    import crafting_recipes as RECIPES
    import turn as TURN
    import frequency as FREQ
    import activity_jobs as JOBS
    plan = RECIPES.prepare(e, actor, declaration, count=1, inputs=inputs)
    recipe = plan['recipe']
    policy = plan['policy']
    source = recipe['source']
    if not TURN.spend(e, actor, policy['action'], source):
        raise ValueError('recipe action not admitted')
    job = JOBS.run_fixed(e, actor, (), seconds=recipe['seconds'], source=source, context=dict(context, recipe=recipe['id'], reason=reason))['job_id']
    FREQ.consume_activation(actor, source, policy['frequency'], engine=e)
    payments = RECIPES.pay_materials(e, actor, plan['payments'])
    return plan, payments, job


def _store_batch(e, actor, *, kind, recipe, item_id, units, taste, payload, **extra):
    serial = C.integer(actor.spec.get(SERIAL, 0), 'Chef batch serial', 0) + 1
    batch_id = 'chef-batch:' + actor.entity_id + ':' + str(serial)
    row = {'id': batch_id, 'kind': kind, 'recipe': recipe, 'item_id': item_id, 'count': units, 'units': units,
           'created_at': e.elapsed_seconds, 'gap_count': len(e.unresolved_time_intervals), 'created_by': actor.entity_id,
           'taste': taste, 'payload': deepcopy(payload), 'served': [], **extra}
    _validate_batch(actor, batch_id, row)
    actor.spec.setdefault(KEY, {})[batch_id] = row
    actor.spec[SERIAL] = serial
    return row


def _money_material(category, amount):
    return [{'id': 'cost', 'options': [{'kind': 'value', 'category': category, 'amount': amount, 'scrap': True, 'money': True}]}]


def _result(e, actor, *, recipe, plan, payments, job, batch):
    values = [x for x in payments if x['kind'] == 'value']
    return {'activity': 'cook_chef_food', 'recipe_id': plan['recipe']['id'], 'chef_recipe': recipe, 'recipe_source': plan['recipe']['source'], 'item_id': batch['item_id'],
            'item': batch['item_id'], 'count': batch['units'], 'batch': deepcopy(batch), 'batch_id': batch['id'],
            'category': values[0]['category'] if len(values) == 1 else None, 'scrap_spent': sum(x['scrap'] for x in values),
            'money_spent': sum(x['money'] for x in values), 'recipe_definition': plan['recipe'], 'qualification': plan['qualification'],
            'materials': payments, 'recipe_sources': plan['sources'], 'job_id': job}


def _cook_tasty_snack(e, actor, *, snack, minutes, reason, taste=None, scrap_value=0):
    data = definitions(e.r)
    _duration(e, minutes, reason)
    def forms(uid):
        slug = uid.split('/', 1)[1]
        return {uid, slug, slug.replace('-', ' '), *_names(e.r, uid)}
    item_id = snack if snack in data['tasty_snacks'] else next((uid for uid in data['tasty_snacks'] if snack in forms(uid)), None)
    if item_id is None:
        raise ValueError('Tasty Snacks produce one of the six printed basic snacks')
    row = data['recipes'][TASTY]
    assignment = _assign_taste(e, actor, kind='tasty_snack', item_id=item_id, taste=taste)
    declaration = _declaration(e, actor, recipe_id=TASTY, source=CHEF_SOURCE, output_item=item_id, prerequisites=row['prerequisites'],
                               materials=_money_material('음식', row['money']), seconds=minutes * 60)
    plan, payments, job = _run(e, actor, declaration, inputs={'cost': {'option': 0, 'scrap_value': scrap_value}}, reason=reason, context={'snack': item_id})
    import food_effects as FOOD
    batch = _store_batch(e, actor, kind='tasty_snack', recipe=TASTY, item_id=item_id, units=row['units'], taste=assignment, payload=FOOD.chef_effect(e.r, item_id))
    return _result(e, actor, recipe=TASTY, plan=plan, payments=payments, job=job, batch=batch)


def _cook_leftovers(e, actor, *, minutes, reason, taste=None, scrap_value=0):
    data = definitions(e.r)
    _duration(e, minutes, reason)
    row = data['recipes'][LEFTOVERS]
    assignment = _assign_taste(e, actor, kind='leftovers', item_id=LEFTOVERS_ITEM, taste=taste)
    declaration = _declaration(e, actor, recipe_id=LEFTOVERS, source=CHEF_SOURCE, output_item=LEFTOVERS_ITEM, prerequisites=row['prerequisites'],
                               materials=_money_material('음식', row['money']), seconds=minutes * 60)
    plan, payments, job = _run(e, actor, declaration, inputs={'cost': {'option': 0, 'scrap_value': scrap_value}}, reason=reason, context={})
    import food_effects as FOOD
    batch = _store_batch(e, actor, kind='leftovers', recipe=LEFTOVERS, item_id=LEFTOVERS_ITEM, units=row['units'], taste=assignment, payload=FOOD.snack_effect(e.r, LEFTOVERS_ITEM))
    return _result(e, actor, recipe=LEFTOVERS, plan=plan, payments=payments, job=job, batch=batch)


def _cook_preserves(e, actor, *, origin, minutes, reason, taste=None, scrap_value=0):
    import food_effects as FOOD
    import herb_mushroom_rules as HERB
    data = definitions(e.r)
    _duration(e, minutes, reason)
    header = e.r.item_effects(origin)[1]
    origin_id = header.get('id')
    if not isinstance(origin_id, str) or header.get('category') != '음식':
        raise ValueError('Preserves require an actual Berry, Herb or Mushroom')
    berry = '열매' in origin_id
    herb = origin_id in HERB.SNACK_HERBS or origin_id in FOOD.HERBS
    mushroom = origin_id in HERB.MUSHROOMS
    if not (berry or herb or mushroom):
        raise ValueError('Preserves require an actual Berry, Herb or Mushroom')
    payload = FOOD.snack_effect(e.r, origin_id)
    if payload is None:
        raise ValueError('Preserves of this consumable need its source-specific consumer before cooking: ' + origin_id)
    row = data['recipes'][PRESERVES]
    assignment = _assign_taste(e, actor, kind='preserves', item_id=origin_id, taste=taste)
    key = _inventory_key(actor, origin_id)
    materials = _money_material('음식', row['money']) + [{'id': 'origin', 'options': [{'kind': 'item', 'item_id': origin_id, 'key': key, 'amount': 1}]}]
    declaration = _declaration(e, actor, recipe_id=PRESERVES, source=CHEF_SOURCE, output_item=origin_id, prerequisites=row['prerequisites'],
                               materials=materials, seconds=minutes * 60)
    plan, payments, job = _run(e, actor, declaration, inputs={'cost': {'option': 0, 'scrap_value': scrap_value}, 'origin': {'option': 0, 'scrap_value': 0}}, reason=reason, context={'origin': origin_id})
    batch = _store_batch(e, actor, kind='preserves', recipe=PRESERVES, item_id=origin_id, units=row['units'], taste=assignment, payload=payload, origin_item=origin_id)
    return _result(e, actor, recipe=PRESERVES, plan=plan, payments=payments, job=job, batch=batch)


def _cook_hearty_meal(e, actor, *, ingredients, units, minutes, reason, taste=None):
    data = definitions(e.r)
    _duration(e, minutes, reason)
    row = data['recipes'][HEARTY]
    C.integer(units, 'Hearty Meal count', 1, row['maximum_units'])
    options = row['ingredients']
    index = next((i for i, option in enumerate(options) if option['id'] == ingredients), None)
    if index is None:
        raise ValueError('Hearty Meal ingredients must be one printed option: ' + ', '.join(option['id'] for option in options))
    option = options[index]
    key = _inventory_key(actor, option['item'])
    materials = [{'id': 'ingredients', 'options': [{'kind': 'item', 'item_id': option['item'], 'key': key, 'amount': option['amount']}]}]
    assignment = _assign_taste(e, actor, kind='hearty_meal', item_id=HEARTY_ITEM, taste=taste)
    declaration = _declaration(e, actor, recipe_id=HEARTY, source=CHEF_SOURCE, output_item=HEARTY_ITEM, prerequisites=row['prerequisites'],
                               materials=materials, seconds=minutes * 60)
    plan, payments, job = _run(e, actor, declaration, inputs={'ingredients': {'option': 0, 'scrap_value': 0}}, reason=reason, context={'ingredients': option['id'], 'units': units})
    batch = _store_batch(e, actor, kind='hearty_meal', recipe=HEARTY, item_id=HEARTY_ITEM, units=units, taste=assignment, payload=None, ingredients=[dict(option)])
    return _result(e, actor, recipe=HEARTY, plan=plan, payments=payments, job=job, batch=batch)


def _ingredient(e, actor, selection, allowed, label):
    """Resolve one Dumplings ingredient to (component, debit plan)."""
    import food_effects as FOOD
    data = definitions(e.r)
    if type(selection) is not dict or set(selection) not in ({'batch_id'}, {'item'}):
        raise ValueError(label + ': select one owned Chef batch or one inventory item')
    if 'item' in selection:
        if 'leftovers' not in allowed:
            raise ValueError(label + ': only Leftovers may come from ordinary inventory')
        header = e.r.item_effects(selection['item'])[1]
        if header.get('id') != LEFTOVERS_ITEM:
            raise ValueError(label + ': Leftovers, Preserves or a Snack made with Chef required')
        key = _inventory_key(actor, LEFTOVERS_ITEM)
        effect = FOOD.snack_effect(e.r, LEFTOVERS_ITEM)
        return ({'item': LEFTOVERS_ITEM, 'effect': effect, 'ingredient': {'kind': 'inventory', 'key': key}, 'batch_kind': 'inventory_leftovers'},
                {'kind': 'inventory', 'item_id': LEFTOVERS_ITEM, 'key': key})
    batch = _batch(actor, selection['batch_id'])
    _validate_batch(actor, batch['id'], batch)
    kind = batch['kind']
    if kind == 'dumplings' and not _nested_dumplings_allowed(e.r):
        raise ValueError(label + ': Dumplings cannot be mixed from another Dumplings under the selected errata')
    if kind == 'hearty_meal':
        raise ValueError(label + ': Hearty Meals are not a Snack ingredient')
    bucket = 'chef_snack' if kind in ('tasty_snack', 'dumplings') else kind
    if bucket not in allowed:
        raise ValueError(label + ': ' + ', '.join(allowed) + ' required')
    if batch['count'] < 1:
        raise ValueError(label + ': the selected Chef batch is exhausted')
    effect = batch['payload']
    if kind != 'dumplings' and effect['kind'] not in data['dumplings']['composite_component_kinds']:
        raise ValueError(label + ': this ingredient effect needs its source-specific composite consumer: ' + effect['kind'])
    return ({'item': batch['item_id'], 'effect': deepcopy(effect), 'ingredient': {'kind': 'batch', 'batch_id': batch['id'], 'taste': deepcopy(batch['taste'])}, 'batch_kind': kind},
            {'kind': 'batch', 'batch_id': batch['id']})


def _take_batch_unit(e, actor, batch_id, *, reason):
    row = _batch(actor, batch_id)
    if row['count'] < 1:
        raise ValueError('the selected Chef batch is exhausted')
    row['count'] -= 1
    row['served'].append({'kind': 'ingredient', 'at': e.elapsed_seconds, 'by': actor.entity_id, 'reason': reason})
    return {'kind': 'chef_batch', 'item_id': row['item_id'], 'batch_id': batch_id, 'count': 1, 'unit': len(row['served'])}


def _mix_dumplings(e, actor, *, ingredient_1, ingredient_2, minutes, reason, taste=None):
    data = definitions(e.r)
    _duration(e, minutes, reason)
    rule = data['dumplings']
    first, debit_1 = _ingredient(e, actor, ingredient_1, rule['ingredient_1'], 'ingredient 1')
    second, debit_2 = _ingredient(e, actor, ingredient_2, rule['ingredient_2'], 'ingredient 2')
    _validate_components(e.r, [first, second])
    if debit_1 == debit_2:
        raise ValueError('the two Dumplings ingredients must be different items')
    effects = _composite_parts((first, second))
    triggers = [part['effect']['kind'] for part in effects if part['effect']['kind'] in TRIGGER_KINDS]
    if len(triggers) > 1:
        signature = {(part['effect']['kind'], part['effect'].get('trigger'), part['effect'].get('move_type')) for part in effects if part['effect']['kind'] in TRIGGER_KINDS}
        if len(signature) > 1:
            raise ValueError('Dumplings with two different trigger-bound ingredient effects need a GM trade-in policy before mixing')
    materials = []
    inputs = {}
    for name, debit in (('ingredient_1', debit_1), ('ingredient_2', debit_2)):
        if debit['kind'] == 'inventory':
            materials.append({'id': name, 'options': [{'kind': 'item', 'item_id': debit['item_id'], 'key': debit['key'], 'amount': 1}]})
            inputs[name] = {'option': 0, 'scrap_value': 0}
    assignment = _assign_taste(e, actor, kind='dumplings', item_id=first['item'], taste=taste)
    declaration = _declaration(e, actor, recipe_id=DUMPLINGS, source=DUMPLINGS, output_item=first['item'],
                               prerequisites=[DUMPLINGS], materials=materials, seconds=minutes * 60)
    plan, payments, job = _run(e, actor, declaration, inputs=inputs, reason=reason, context={'ingredients': [first['item'], second['item']]})
    for debit in (debit_1, debit_2):
        if debit['kind'] == 'batch':
            payments.append(dict(_take_batch_unit(e, actor, debit['batch_id'], reason='Dumplings ingredient'), group='ingredient'))
    payload = {'kind': 'chef_composite', 'components': effects}
    batch = _store_batch(e, actor, kind='dumplings', recipe=DUMPLINGS, item_id=first['item'], units=1, taste=assignment, payload=payload,
                         components=[first, second], ingredients=[debit_1, debit_2])
    result = _result(e, actor, recipe=DUMPLINGS, plan=plan, payments=payments, job=job, batch=batch)
    result['trigger_components'] = triggers
    return result


COOKS = {'tasty_snack': _cook_tasty_snack, 'leftovers': _cook_leftovers, 'preserves': _cook_preserves,
         'hearty_meal': _cook_hearty_meal, 'dumplings': _mix_dumplings}


def _perform(e, actor, options):
    import pokemon_activities as P
    P._trainer(actor)
    options = dict(options)
    recipe = options.pop('recipe', None)
    if recipe not in COOKS:
        raise ValueError('Chef recipe must be one of ' + ', '.join(COOKS))
    return COOKS[recipe](e, actor, **options)


class ChefCookingUse(__import__('transformation_use').TransformationUse):
    operation = 'cook_chef_food'

    def perform(self, engine, actor, options):
        return _perform(engine, actor, options)

    def sources(self, engine, actor, options, result):
        import crafting_resources as R
        rows = [R.SOURCE, result['recipe_source'], result['chef_recipe'], result['item_id'], *result.get('recipe_sources', [])]
        return list(dict.fromkeys(rows))


__import__('transformation_use').ADAPTERS['cook_chef_food'] = ChefCookingUse()


def cook(e, actor, **options):
    import transformation_use as T
    return T.dispatch(e, actor, 'cook_chef_food', **options)


# ---------- serving (batch stock) ----------

def prepare_batch_stock(engine, actor, rule_id, batch_id):
    _text(batch_id, 'Chef batch identity')
    row = _batch(actor, batch_id)
    _validate_batch(actor, batch_id, row)
    if row['item_id'] != rule_id:
        raise ValueError('Chef batch belongs to another item rule')
    if row['count'] < 1:
        raise ValueError('the selected Chef batch is exhausted')
    return {'kind': 'chef_batch', 'item_id': rule_id, 'batch_id': batch_id, 'count': 1, 'unit': len(row['served']) + 1}


def consume_batch_unit(engine, actor, stock):
    checked = prepare_batch_stock(engine, actor, stock['item_id'], stock['batch_id'])
    if checked != stock:
        raise ValueError('prepared Chef batch unit changed')
    row = batches(actor)[stock['batch_id']]
    row['count'] -= 1
    row['served'].append({'kind': 'served', 'at': engine.elapsed_seconds, 'by': actor.entity_id})
    _validate_batch(actor, row['id'], row)
    return checked


def batch_for_intake(engine, user, uid, batch_id):
    row = _batch(user, batch_id)
    _validate_batch(user, batch_id, row)
    if row['item_id'] != uid:
        raise ValueError('Chef batch belongs to another item rule')
    if row['count'] < 1:
        raise ValueError('the selected Chef batch is exhausted')
    return row


def intake_provenance(batch, user):
    """Provenance copied onto the Digestion Buff of one served chef-made Snack."""
    row = {'chef_batch': {'batch_id': batch['id'], 'kind': batch['kind'], 'recipe': batch['recipe'], 'cook_id': batch['created_by'], 'created_at': batch['created_at']}}
    if batch['taste'] is not None:
        row['taste_assignment'] = deepcopy(batch['taste'])
    if batch['kind'] == 'dumplings':
        row['effect_source'] = DUMPLINGS
    return row


def hearty_freshness(engine, batch, *, when):
    data = definitions(engine.r)
    limit = batch['created_at'] + data['recipes'][HEARTY]['freshness_seconds']
    if batch['gap_count'] != len(engine.unresolved_time_intervals):
        return C.PendingDecision('unknown elapsed time prevents an exact Hearty Meal freshness decision')
    if when > limit:
        raise ValueError('Hearty Meals not consumed within 20 minutes of creation lose all flavor and effect')
    return None


def eat_hearty_meal(engine, user, target, plan, stock_receipt):
    data = definitions(engine.r)
    recipe = data['recipes'][HEARTY]
    if target.kind != 'trainer':
        raise ValueError('Hearty Meals are consumed by Trainers')
    if target.spec.get(MEAL) is not None:
        raise ValueError('a Trainer may only be under the effect of one Hearty Meal at a time')
    batch = plan['chef_batch']
    if type(batch) is not dict or set(batch) != {'batch_id', 'cook_id', 'created_at', 'gap_count', 'taste'}:
        raise ValueError('typed Hearty Meal intake plan required')
    pending = hearty_freshness(engine, {'created_at': batch['created_at'], 'gap_count': batch['gap_count']}, when=engine.elapsed_seconds)
    if pending is not None:
        raise ValueError(str(pending))
    record = {'source': HEARTY_ITEM, 'recipe': HEARTY, 'ap_bonus': recipe['ap_bonus'], 'ends': recipe['ends'], 'eaten_at': engine.elapsed_seconds,
              'batch_id': batch['batch_id'], 'cook_id': batch['cook_id'], 'taste': deepcopy(batch.get('taste'))}
    target.spec[MEAL] = record
    validate_actor(target)
    import action_points as AP
    engine.log(f"    {target.name}: 푸짐한 식사 → 다음 연장 휴식까지 최대 AP +{recipe['ap_bonus']} (현재 최대 {AP.maximum(target)})", HEARTY)
    return {'status': 'hearty_meal', 'item': HEARTY_ITEM, 'ap_bonus': recipe['ap_bonus'], 'until': recipe['ends'], 'at': engine.elapsed_seconds, 'item_stock': stock_receipt, 'maximum_ap': AP.maximum(target)}


def max_ap_bonus(actor):
    meal = actor.spec.get(MEAL)
    if meal is None:
        return 0
    validate_actor(actor)
    if actor.r._selected_rule(HEARTY) != HEARTY:
        raise ValueError('selected Hearty Meal recipe needs its own AP policy')
    return meal['ap_bonus']


def extended_rest(engine, actor):
    meal = actor.spec.get(MEAL)
    if meal is None:
        return
    validate_actor(actor)
    actor.spec.pop(MEAL)
    engine.log(f"    {actor.name}: 푸짐한 식사 효과 종료 (연장 휴식)", HEARTY)


def serve(e, actor, *, batch_id, target=None, minutes=None, reason=None, accepted=True):
    """Serve one unit of an owned chef-made batch through the shared food intake."""
    import state_grants as G
    import world_entities as W
    import food_effects as FOOD
    target = actor if target is None else target
    W.require_actors(e, actor, target)
    row = _batch(actor, batch_id)
    _validate_batch(actor, batch_id, row)
    uid = row['item_id']

    def apply(staged, user, *rest):
        recipient = rest[0] if rest else user
        return FOOD.consume(staged, user, recipient, uid, minutes=minutes, reason=reason, accepted=accepted, chef_batch_id=batch_id)
    return G.transition(e, actor, apply, participants=() if target is actor else (target,))


# ---------- composite Digestion Buffs ----------

def composite_expected(rules, buff):
    import food_effects as FOOD
    effect = buff.get('effect')
    if type(effect) is not dict or effect.get('kind') != 'chef_composite' or type(effect.get('components')) is not list or len(effect['components']) < 2:
        raise ValueError('Dumplings Digestion Buff needs its ingredient effects')
    if len(effect['components']) > 2 and not _nested_dumplings_allowed(rules):
        raise ValueError('Dumplings cannot be mixed from another Dumplings under the selected errata')
    return {'kind': 'chef_composite', 'components': [{'item': part['item'], 'effect': FOOD.snack_effect(rules, part['item'])} for part in effect['components']]}


def validate_composite(rules, buff):
    data = definitions(rules)
    expected = composite_expected(rules, buff)
    if buff['effect'] != expected or buff.get('item') != expected['components'][0]['item']:
        raise ValueError('Dumplings Digestion Buff differs from its component sources')
    kinds = [part['effect']['kind'] for part in expected['components']]
    if any(kind not in data['dumplings']['composite_component_kinds'] for kind in kinds):
        raise ValueError('Dumplings component needs its source-specific composite consumer')
    if buff.get('effect_source') != DUMPLINGS:
        raise ValueError('Dumplings Digestion Buff needs its Dumplings effect source')
    return True


def trigger_component(buff):
    """One trigger-bound component or None; two different trigger payloads are undefined by the text."""
    effect = buff['effect']
    if effect.get('kind') != 'chef_composite':
        return None
    rows = [part['effect'] for part in effect['components'] if part['effect']['kind'] in TRIGGER_KINDS]
    if not rows:
        return None
    if len(rows) > 1:
        signature = {(row['kind'], row.get('trigger'), row.get('move_type')) for row in rows}
        if len(signature) > 1:
            raise ValueError('Dumplings with two different trigger-bound ingredient effects need a GM trade-in policy before use')
    return rows[0]


def immediate_components(buff):
    """Immediate Dumplings components as {'item','effect'} rows."""
    effect = buff['effect']
    if effect.get('kind') != 'chef_composite':
        return []
    return [{'item': part['item'], 'effect': deepcopy(part['effect'])} for part in effect['components'] if part['effect']['kind'] in IMMEDIATE_KINDS]


def validate_buff_provenance(actor, buff):
    """Shape checks for chef provenance carried by any Digestion Buff or spent receipt."""
    kind = buff.get('chef_batch', {}).get('kind') if isinstance(buff.get('chef_batch'), dict) else None
    taste = buff.get('taste_assignment')
    if taste is not None:
        if kind is None and (type(buff.get('chef_provenance')) is not dict):
            raise ValueError('taste assignment requires a chef-made batch or Complex Aftertaste provenance')
        _validate_taste(actor.r, taste, kind=kind or 'tasty_snack', item_id=buff.get('item'))
    batch = buff.get('chef_batch')
    if batch is not None:
        if type(batch) is not dict or set(batch) != {'batch_id', 'kind', 'recipe', 'cook_id', 'created_at'} or batch['kind'] not in SNACK_BATCH_KINDS:
            raise ValueError('typed chef batch provenance required')
        _text(batch['batch_id'], 'chef batch identity')
        _text(batch['cook_id'], 'chef cook identity')
        C.integer(batch['created_at'], 'chef batch creation time', 0)
    provenance = buff.get('chef_provenance')
    if provenance is not None:
        if type(provenance) is not dict or set(provenance) != {'source', 'event_id', 'owner_id', 'origin_receipt_sequence', 'origin_item'} or provenance['source'] != AFTERTASTE:
            raise ValueError('typed Complex Aftertaste provenance required')
        _text(provenance['event_id'], 'Complex Aftertaste event')
        _text(provenance['owner_id'], 'Complex Aftertaste owner')
        C.integer(provenance['origin_receipt_sequence'], 'Complex Aftertaste origin receipt', 1)
    if buff.get('effect', {}).get('kind') == 'chef_composite' and kind != 'dumplings':
        raise ValueError('composite Digestion Buff needs its Dumplings batch provenance')
    return True


# ---------- Accentuated Taste bonuses ----------

def bonus_plan(engine, actor, buff):
    """The printed bonus for one tasted Snack traded in by a Pokemon that does not dislike it."""
    taste = taste_of(buff)
    if taste is None:
        return None
    data = definitions(engine.r)
    if actor.kind != data['taste_bonus_recipient'] or not actor.r._selected_rule(ACCENTUATED) == ACCENTUATED:
        return None
    import food_effects as FOOD
    disposition = FOOD._flavor_disposition(actor, taste)
    if disposition == 'disliked':
        return None
    bonus = data['taste_bonuses'][taste]
    return {'taste': taste, 'disposition': disposition, **bonus}


def _ruling(engine):
    data = definitions(engine.r)
    rule = data['taste_bonus_lifetime_ruling']
    answer = engine.rulings.decide({'type': rule['prompt_type'], 'unit': ACCENTUATED, 'text': rule['question']})
    if answer is None:
        return None
    if answer not in rule['boundaries']:
        raise ValueError('Accentuated Taste bonus lifetime ruling must be one of ' + ', '.join(rule['boundaries']))
    return answer


def taste_bonus_preflight(engine, actor, buff, *, temporary_hp_grants=None, temporary_hp_plan=None):
    plan = bonus_plan(engine, actor, buff)
    if temporary_hp_grants is not None:
        import temporary_hp as TEMP_HP
        grants = list(temporary_hp_grants)
        if plan is not None and plan['kind'] == 'temporary_hp':
            grants.append((plan['value'], 'chef_taste'))
        if grants:
            TEMP_HP.preflight_food_grants(engine, actor, grants, plan=temporary_hp_plan)
    if plan is None or plan['kind'] == 'temporary_hp':
        return None
    if _ruling(engine) is None:
        return C.PendingDecision('GM ruling ' + RULING + ' (encounter_end|scene_end) required: the printed Accentuated Taste bonus has no duration')
    return None


def apply_taste_bonus(engine, actor, buff, receipt):
    plan = bonus_plan(engine, actor, buff)
    if plan is None:
        return None
    if receipt.get('taste_bonus') is not None:
        raise ValueError('Accentuated Taste bonus already applied for this receipt')
    provenance = {'source': ACCENTUATED, 'taste': plan['taste'], 'buff_id': buff['id'], 'receipt_sequence': receipt['sequence'], 'item': buff.get('item')}
    if plan['kind'] == 'temporary_hp':
        import temporary_hp as TEMP_HP
        gained = TEMP_HP.grant(engine, actor, plan['value'], stack=True, provenance=provenance,
                               contribution_source=TEMP_HP.food_source(actor, 'chef_taste', receipt))
        result = {'kind': 'temporary_hp', 'taste': plan['taste'], 'disposition': plan['disposition'], 'value': plan['value'], 'gained': gained, 'stack': True}
        blocked = TEMP_HP.blocked_reason(actor)
        if blocked is not None:
            result['blocked_reason'] = blocked
    else:
        boundary = _ruling(engine)
        if boundary is None:
            raise ValueError('GM ruling ' + RULING + ' required before applying the Accentuated Taste bonus')
        import combat_timing as TIMING
        record = {'source': ACCENTUATED, 'effect_contract': True, BONUS: dict(provenance, kind=plan['kind'], value=plan['value'], lifetime_boundary=boundary),
                  BONUS_FIELDS[plan['kind']]: plan['value']}
        if boundary == 'encounter_end':
            record['encounter_end'] = True
        TIMING.install(engine, actor, record)
        result = {'kind': plan['kind'], 'taste': plan['taste'], 'disposition': plan['disposition'], 'value': plan['value'], 'lifetime_boundary': boundary}
    receipt['taste_bonus'] = result
    engine.log(f"    {actor.name}: 특색있는 맛 {plan['taste']} 보너스 {result['kind']} +{plan['value']}", ACCENTUATED)
    return result


def _validate_bonus_record(actor, record, bonus):
    data = definitions(actor.r)
    allowed = {'source', 'effect_contract', BONUS, 'encounter_end', 'owned_statuses', 'installing', *BONUS_FIELDS.values()}
    if set(record) - allowed or record.get('source') != ACCENTUATED or record.get('effect_contract') is not True:
        raise ValueError('typed Accentuated Taste bonus record required')
    if type(bonus) is not dict or set(bonus) != {'source', 'taste', 'buff_id', 'receipt_sequence', 'item', 'kind', 'value', 'lifetime_boundary'}:
        raise ValueError('typed Accentuated Taste bonus provenance required')
    expected = data['taste_bonuses'].get(bonus['taste'])
    if expected is None or expected['kind'] != bonus['kind'] or expected['value'] != bonus['value'] or bonus['kind'] == 'temporary_hp':
        raise ValueError('Accentuated Taste bonus differs from its printed value')
    if bonus['lifetime_boundary'] not in data['taste_bonus_lifetime_ruling']['boundaries'] or (bonus['lifetime_boundary'] == 'encounter_end') != bool(record.get('encounter_end')):
        raise ValueError('Accentuated Taste bonus lifetime changed')
    field = BONUS_FIELDS[bonus['kind']]
    if record.get(field) != bonus['value'] or any(record.get(other) is not None for other in BONUS_FIELDS.values() if other != field):
        raise ValueError('Accentuated Taste bonus contribution changed')
    receipts = [row for row in actor.spec.get('food_consumption_receipts', []) if row.get('sequence') == bonus['receipt_sequence']]
    if len(receipts) != 1 or receipts[0].get('buff_id') != bonus['buff_id'] or receipts[0].get('taste_bonus', {}).get('kind') != bonus['kind']:
        raise ValueError('Accentuated Taste bonus lacks its actual trade-in receipt')
    return True


def _bonus_total(actor, field):
    import combat_timing as TIMING
    total = 0
    for record in TIMING.records(actor):
        if record.get(BONUS) is None or field not in record:
            continue
        _validate_bonus_record(actor, record, record[BONUS])
        total += record[field]
    return total


def critical_bonus(engine, attacker, move):
    if move.get('class') not in ('물리', '특수'):
        return 0
    return _bonus_total(attacker, BONUS_FIELDS['critical_range'])


def effect_range_bonus(engine, attacker, move):
    if not move or move.get('class') not in ('물리', '특수'):
        return 0
    return _bonus_total(attacker, BONUS_FIELDS['effect_range'])


def evasion_bonus(actor, move_class):
    if move_class not in ('물리', '특수'):
        return 0
    return _bonus_total(actor, BONUS_FIELDS['evasion_damaging'])


def initiative_bonus(actor):
    return _bonus_total(actor, BONUS_FIELDS['initiative'])


# ---------- Complex Aftertaste helpers (owner: class_actor_state_actions) ----------

def aftertaste_owners(engine, actor):
    """Trainers for whom the consumer is 'you or an ally': self, own Pokemon's trainer, same-side actors."""
    import world_entities as W
    index = W.actor_index(engine)
    result = []
    side = getattr(actor, 'side', None)
    for trainer in index.values():
        if trainer.kind != 'trainer':
            continue
        own = actor.kind == 'pokemon' and actor.spec.get('trainer_id') == trainer.entity_id
        allied = side is not None and getattr(trainer, 'side', None) == side and getattr(trainer, 'on_field', True) and not trainer.captured
        if trainer is actor or own or allied:
            result.append(trainer)
    return result


def aftertaste_grant(engine, owner, target, event):
    import food_effects as FOOD
    payload = event['payload']
    taste = payload.get('taste')
    uid = _tasty_item(engine.r, taste)
    effect = FOOD.chef_effect(engine.r, uid)
    provenance = {'taste_assignment': {'taste': taste, 'source': ACCENTUATED, 'assigned_by': payload.get('assigned_by', owner.entity_id), 'basis': 'complex_aftertaste'},
                  'chef_provenance': {'source': AFTERTASTE, 'event_id': event['id'], 'owner_id': owner.entity_id,
                                      'origin_receipt_sequence': payload['receipt_sequence'], 'origin_item': payload['item']}}
    buff = FOOD.grant_buff(engine, target, uid, effect, source=FOOD.FOOD, provenance=provenance)
    if buff is None:
        raise ValueError('Complex Aftertaste target cannot gain another Digestion Buff')
    engine.log(f"    {target.name}: 복잡한 뒷맛 → {uid} 만복 버프 ({taste})", AFTERTASTE)
    return {'buff_id': buff['id'], 'item': uid, 'taste': taste, 'ap_spent': 1}
