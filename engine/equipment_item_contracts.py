"""Shared source contracts for Chapter 9 food and crafting item state.

This module classifies an already-selected real item.  The native food and
crafting modules continue to own payment, actions, effects and receipts.
"""

FOOD_SOURCE = 'ch09-equipment/모험-도구/음식'
SNACK_CLAUSE = 'C09-028'
OTHER_FOOD_CLAUSE = 'C09-031'
SCRAP_CLAUSE = 'C09-052'
SCRAP_EXAMPLE_KINDS = ('음식', '약', '스프레이', '몬스터볼', '패션 도구')
BATTLE_TOOL_SOURCE = 'ch09-equipment/전투용-도구'
BATTLE_TOOL_CLAUSE = 'C09-079'
# The chapter's broad category does not override an individual item's lifetime.
BATTLE_TOOL_POLICIES = {
    **dict.fromkeys(('item/마름쇠-독-마름쇠', 'item/마름쇠', 'item/독-마름쇠',
                     'item/꿈안개', 'item/꿈안개-1', 'item/오물탄', 'item/오물탄-1',
                     'item/오물탄-격노', 'item/오물탄-혼란', 'item/오물탄-화상',
                     'item/오물탄-독', 'item/오물탄-마비', 'item/오물탄-잠듦',
                     'item/연막탄', 'item/연막탄-1'), 'single_use'),
    **dict.fromkeys(('item/마법피리', 'item/마법피리-1'), 'daily_reusable'),
    **dict.fromkeys(('item/순결의부적', 'item/순결의부적-1'), 'use_mode'),
}


def battle_tool_header(rules, item_id, header):
    """Project the selected battle-tool category without granting an effect.

    Called by the actual catalog reader after its item selection.  Action,
    frequency and physical debit still belong to each native use adapter.
    """
    policy = BATTLE_TOOL_POLICIES.get(item_id)
    if policy is None:
        return header
    if header.get('id') != item_id:
        raise ValueError('battle-tool catalog and selected identity disagree')
    if rules._selected_rule(BATTLE_TOOL_SOURCE) != BATTLE_TOOL_SOURCE:
        raise ValueError('selected battle-tool category source changed')
    result = dict(header, battle_tool={
        'kind': 'battle_tool', 'clause_id': BATTLE_TOOL_CLAUSE,
        'source_id': BATTLE_TOOL_SOURCE, 'normally_consumable': True,
        'stock_policy': policy,
    })
    if policy == 'single_use':
        result['use'] = 'consumable'
    return result


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + ' must be nonempty text')
    return value


def selected_item(rules, item_id):
    """Return the selected catalog header for one exact item identity."""
    _text(item_id, 'actual item identity')
    if not item_id.startswith('item/'):
        raise ValueError('actual item identity must use its item/ rule id')
    header = rules.item_effects(item_id)[1]
    if not isinstance(header, dict) or header.get('id') != item_id:
        raise ValueError('catalog item and selected identity disagree')
    return header


def food_intake(rules, item_id, *, snack_items, drink_items,
                other_food_items, forced_snack=False, source_selection=None):
    """Classify one native intake without merging its distinct limit bucket."""
    if type(forced_snack) is not bool:
        raise ValueError('explicit forced-snack state required')
    if source_selection is None:
        selected_item(rules, item_id)
    else:
        import csv_item_food_contracts as CSV
        CSV.validate_choice(rules, source_selection, item_id)
        CSV.selected_header(rules, source_selection, item_id)
    berry = item_id.startswith('item/') and '열매' in item_id and item_id not in drink_items
    if forced_snack or item_id in snack_items or berry:
        if rules._selected_rule(FOOD_SOURCE) != FOOD_SOURCE:
            raise ValueError('selected snack source changed')
        return {
            'kind': 'snack',
            'clause_id': SNACK_CLAUSE,
            'action': 'extended',
            'limit_bucket': 'digestion_buff',
            'berries_are_snacks': berry,
        }
    if item_id in drink_items:
        return {
            'kind': 'drink',
            'clause_id': None,
            'action': 'extended',
            'limit_bucket': 'drink_window',
            'berries_are_snacks': False,
        }
    if item_id in other_food_items:
        return {
            'kind': 'other_food',
            'clause_id': OTHER_FOOD_CLAUSE,
            'action': 'extended',
            'limit_bucket': 'independent',
            'berries_are_snacks': False,
        }
    raise ValueError('native food item has no reviewed intake contract')


def scrap_kind(header, *, known=None, declared=None, reason=None):
    """Keep the five source examples while allowing a reasoned related kind."""
    if not isinstance(header, dict):
        raise ValueError('actual item catalog header required')
    _text(header.get('id'), 'actual item identity')
    if known is not None:
        _text(known, 'source scrap kind')
        if known not in SCRAP_EXAMPLE_KINDS:
            raise ValueError('known source scrap kind is not a Chapter 9 example')
        if declared is not None and declared != known:
            raise ValueError('declared scrap kind contradicts the item source')
        return known
    _text(declared, 'explicit scrap kind for an unclassified intact item')
    _text(reason, 'GM source-related scrap classification reason')
    return declared


def validate_scrap_balance_kind(kind):
    """Scrap kinds are open names; consumers still require an exact match."""
    return _text(kind, 'crafting scrap resource kind')
