"""Optional cosmetic Shiny observations and their actual native consumers.

This is an individual appearance fact, never a new species definition. The
source gives no price formula: a funded money sale needs explicit GM agreement.
"""
from copy import deepcopy
import common_checks as C
import world_entities as W
import state_grants as G
import resolution_transaction as TX
import campaign_rewards as MONEY
import pokemon_party as PARTY
from source_context import verified_source

SOURCE = 'ch11-running-the-game/이로치-포켓몬'
REFERENCE = {'file': 'input/ch11-running-the-game.md',
             'sha256': '5311a50a2c70748465fe6fd73b52a8abbf337a11791509d88a15e19295232dad'}
KEY = 'cosmetic_shiny'


def source(rules):
    if rules._selected_rule(SOURCE) != SOURCE:
        raise ValueError('selected cosmetic Shiny source requires its own adapter')
    verified_source(rules, REFERENCE, label='cosmetic Shiny')


def read(engine, pokemon):
    """Detached observed appearance; no species, type, ability or stat grant."""
    W.require_actors(engine, pokemon)
    if pokemon.kind != 'pokemon':
        raise ValueError('actual Pokemon specimen required')
    row = pokemon.spec.get(KEY)
    if row is None:
        return None
    source(engine.r)
    if (type(row) is not dict or set(row) != {'actor_id', 'source', 'reference',
            'description', 'reason', 'introduction_bonus'} or row['source'] != SOURCE
            or row['actor_id'] != pokemon.entity_id or row['reference'] != REFERENCE
            or type(row['introduction_bonus']) is not bool):
        raise ValueError('actual cosmetic Shiny observation required')
    W._text(row['description'], 'observed cosmetic coloration')
    W._text(row['reason'], 'GM cosmetic Shiny adoption reason')
    return deepcopy(row)


def observe(engine, pokemon, *, description, introduction_bonus, reason):
    """GM explicitly adopts this specimen and independently chooses +2d6."""
    source(engine.r)
    W.require_actors(engine, pokemon)
    if pokemon.kind != 'pokemon' or type(introduction_bonus) is not bool:
        raise ValueError('actual Pokemon and explicit optional introduction choice required')
    W._text(description, 'observed cosmetic coloration')
    W._text(reason, 'GM cosmetic Shiny adoption reason')
    row = dict(actor_id=pokemon.entity_id, source=SOURCE, reference=deepcopy(REFERENCE),
               description=description, introduction_bonus=introduction_bonus, reason=reason)
    def apply(e, p):
        before = deepcopy(p.spec.get(KEY))
        p.spec[KEY] = deepcopy(row)
        read(e, p)
        e.gm._rec('cosmetic Shiny observation', before, row, reason, p)
        return deepcopy(row)
    return G.transition(engine, pokemon, apply)


def introduction_dice(engine, pokemon):
    row = read(engine, pokemon)
    if row is None or not row['introduction_bonus']:
        raise ValueError('this actual specimen has no adopted Shiny introduction bonus')
    return 2


def _placement(owner, pokemon):
    row = owner.spec.get('pokemon_registry', {}).get(pokemon.entity_id)
    if (pokemon.spec.get('trainer_id') != owner.entity_id or row is None
            or row.get('owner_id') != owner.entity_id
            or pokemon.spec.get('party_location') != {**row, 'pokemon_id': pokemon.entity_id}):
        raise ValueError('actual current owner registry and specimen placement must agree')


def settle_money_sale(engine, seller, pokemon, buyer, *, ordinary_value, agreed_value,
                      agreement, reason, request_id):
    """Explicit funded money-for-Pokemon agreement using native transfer/payment.

    Values are canonical integer points. No default price, premium multiplier,
    barter equivalence or universal permission to sell is inferred from ch11.
    The existing transfer receipt also owns this settlement's intent/result.
    """
    source(engine.r)
    W.require_actors(engine, seller, pokemon, buyer)
    MONEY.base(engine, seller, reward_source=False)
    MONEY.base(engine, buyer, reward_source=False)
    if seller is buyer:
        raise ValueError('different actual buyer and seller required')
    observation = read(engine, pokemon)
    if observation is None:
        raise ValueError('actual adopted cosmetic Shiny specimen required')
    C.integer(ordinary_value, 'GM agreed ordinary specimen value', 0)
    C.integer(agreed_value, 'GM agreed higher Shiny value', 1)
    if agreed_value <= ordinary_value:
        raise ValueError('Shiny agreement must exceed the explicit ordinary value')
    W._text(agreement, 'GM money sale agreement including its ordinary comparison')
    W._text(reason, 'actual money sale reason')
    W._text(request_id, 'actual money sale request identity')
    intent = dict(source=SOURCE, seller_id=seller.entity_id, buyer_id=buyer.entity_id,
                  pokemon_id=pokemon.entity_id, observation=observation,
                  ordinary_value=ordinary_value, agreed_value=agreed_value,
                  agreement=agreement, reason=reason, settlement='money_sale')
    records = getattr(engine, '_world_relation_receipts', {})
    previous = TX.replay_result(records, request_id, intent, fingerprint_field='settlement_sha256')
    if previous is not None:
        _placement(buyer, pokemon)
        return previous
    _placement(seller, pokemon)
    MONEY.balances(seller)
    MONEY.balances(buyer)
    if buyer.spec.get('money', 0) < agreed_value:
        raise ValueError('actual buyer lacks agreed point payment')
    def apply(e, s, p, b):
        receipt = PARTY.transfer(e, s, target=p, new_owner=b, reason=reason, request_id=request_id)
        MONEY.pay(b, money=-agreed_value)
        MONEY.pay(s, money=agreed_value)
        receipt.update(settlement_sha256=TX.request_fingerprint(intent), settlement=deepcopy(intent))
        e._world_relation_receipts[request_id] = deepcopy(receipt)
        return deepcopy(receipt)
    return G.transition(engine, seller, apply, participants=(pokemon, buyer))
