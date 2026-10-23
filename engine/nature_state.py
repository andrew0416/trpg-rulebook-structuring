"""Source-backed mechanical Natures; narrative personality is a separate field."""
import roll_pools as POOLS
STATS = ("hp", "atk", "def", "spa", "spd", "spe")
STAT_NAMES = {"HP": "hp", "공격": "atk", "방어": "def", "특공": "spa", "특수공격": "spa", "특방": "spd", "특수방어": "spd", "스피드": "spe"}
# ch05:89-97 and nature-type.csv describe the same up/down pairs using these
# three different Korean labels. Preserve the chosen label and catalog spelling.
ALIASES = {"절박": ("무모", "atk", "hp"), "낭만적": ("낭만", "spd", "hp"), "활발": ("소심", "spe", "hp")}


def describe(rules, nature):
    if nature is None:
        return None
    if not isinstance(nature, str) or not nature.strip():
        raise ValueError("known selected mechanical Nature required")
    table = rules.mech("pokemon/natures")["by_name"]
    canonical = nature
    alias = ALIASES.get(nature) if nature not in table else None
    if alias:
        canonical = alias[0]
    row = table.get(canonical)
    if row is None:
        raise ValueError("unknown mechanical Nature: " + nature)
    up = STAT_NAMES.get(row["up"], row["up"])
    down = STAT_NAMES.get(row["down"], row["down"])
    if up not in STATS or down not in STATS:
        raise ValueError("selected Nature has unknown stat identities")
    if alias and (up, down) != alias[1:]:
        raise ValueError("selected Nature variant differs from its source-backed alias")
    neutral = up == down
    return {"name": nature, "catalog_name": canonical, "up_stat": up, "down_stat": down,
            "neutral": neutral, "likes": None if neutral else row["likes"],
            "dislikes": None if neutral else row["dislikes"],
            "source": "pokemon/natures", "label_source": "input/ch05-pokemon.md:89-97" if alias else "input/db/nature-type.csv"}


def from_dice(rules, rng, *, raise_die=None, lower_die=None):
    """Optional 2d6 lookup; fixed supplied dice remain fixed and consume no roll."""
    for value in (raise_die, lower_die):
        if value is not None and (type(value) is not int or not 1 <= value <= 6):
            raise ValueError("Nature dice must be integers from 1 through 6")
    up = STATS[POOLS.die(rng, fixed=raise_die) - 1]
    down = STATS[POOLS.die(rng, fixed=lower_die) - 1]
    matches = [name for name in rules.mech("pokemon/natures")["by_name"]
               if (describe(rules, name)["up_stat"], describe(rules, name)["down_stat"]) == (up, down)]
    if len(matches) != 1:
        raise ValueError("selected Nature table must have one entry per dice pair")
    return matches[0]
