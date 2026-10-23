"""The existing Smokescreen field producer, shared by moves and actual tools.

Only engine.zone_cells/engine.zones are gameplay state. Callers retain their
own source admission, geometry, payment and receipt boundaries.
"""


def apply(engine, target, move, zone, source, confidence):
    if engine.grid is not None:
        cells = move['_effect_area_cells']
        for cell in cells:
            engine.zone_cells[cell] = zone['accuracy_penalty']
        engine.log(f"    {move['_area_aim']} 중심 {len(cells)}칸에 연막: 명중 {zone['accuracy_penalty']}",
                   f'{source} ({confidence})')
        return {'cells': sorted(cells), 'accuracy_penalty': zone['accuracy_penalty']}
    engine.zones[target.entity_id] = zone['accuracy_penalty']
    engine.log(f"    {target.name} 주변에 연막: 명중 {zone['accuracy_penalty']}",
               f'{source} ({confidence})')
    return {'target_id': target.entity_id, 'accuracy_penalty': zone['accuracy_penalty']}
