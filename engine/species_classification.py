"""Species identity produces capture classification; GM exceptions stay explicit.

The catalogue is taxonomy only. Ball effects remain with their selected CSV rule.
"""
from pathlib import Path
import json
from copy import deepcopy

KEY = 'species_classification'


def _canonical(rules, spec):
    species = rules.species.get(spec.get('species'))
    if species is None:raise ValueError('actual selected species identity required')
    if species.get('source', 'db') != 'db':return None
    policy = json.loads((Path(rules.root)/'data/species-classification.json').read_text(encoding='utf-8'))
    if policy.get('schema_version') != 1:raise ValueError('reviewed species classification policy required')
    selected = policy['ultra_beasts'].get(spec['species'])
    if selected is not None and str(species.get('dex')) != selected['dex']:
        raise ValueError('Ultra Beast catalogue species identity changed')
    return {'authority':'catalogue', 'species_id':species['id'], 'ultra_beast':selected is not None}


def classification(rules, spec):
    expected = _canonical(rules, spec)
    declared = spec.get(KEY)
    if declared is not None and type(declared) is not dict:
        raise ValueError('explicit species classification record required')
    if declared is not None and declared.get('authority') == 'gm':
        if (type(declared) is not dict or set(declared) != {'authority','species_id','ultra_beast','source','reason'}
                or declared['species_id'] != spec.get('species') or type(declared['ultra_beast']) is not bool
                or any(type(declared[k]) is not str or not declared[k].strip() for k in ('source','reason'))):
            raise ValueError('explicit species-bound GM Ultra Beast classification required')
        return deepcopy(declared)
    # Catalogue values are derived from the current species, including evolution.
    # A sheet flag cannot replace that producer; GM exceptions use the branch above.
    if declared is not None and declared.get('authority') != 'catalogue':
        raise ValueError('known species classification authority required')
    return expected


def produce(rules, spec):
    value = classification(rules, spec)
    if value is not None:spec[KEY] = value


def declare(engine, actor, ultra_beast, *, source, reason):
    """Explicit GM/homebrew classification, bound to this observed species."""
    import state_grants as G, world_entities as W
    W.require_actors(engine, actor)
    if actor.kind != 'pokemon':raise ValueError('actual Pokemon classification required')
    value = {'authority':'gm','species_id':actor.spec['species'],'ultra_beast':ultra_beast,
             'source':source,'reason':reason}
    classification(engine.r, {**actor.spec,KEY:value})
    def apply(e, a):
        a.spec[KEY] = deepcopy(value)
        return deepcopy(value)
    return G.transition(engine, actor, apply)


def ultra_beast(engine, actor):
    value = classification(engine.r, actor.spec)
    return value is not None and value['ultra_beast'] is True
