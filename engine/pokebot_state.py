"""Source-bounded Pokebot material/component state projections, no crafting/actions."""
from copy import deepcopy
import state_fields as F
import arithmetic_policy as M

MATERIALS={
 'standard':{'weak':['불꽃','전기','땅'],'resist':[],'cost_ratio':[1,1]},
 'ferrofluid':{'weak':['강철','얼음','독'],'resist':['불꽃','전기','격투'],'cost_ratio':[3,2]},
 'conductive_crystal':{'weak':['강철','격투','바위'],'resist':[],'cost_ratio':[6,5]},
 'psionic_alloy':{'weak':['악'],'resist':['에스퍼','격투'],'cost_ratio':[2,1]},
 'reinforced_steel':{'type_matchup':'강철','cost_ratio':[2,1]},
}
MOVES={'basic_combat':['할퀴기','몸통박치기','돌진','웅크리기'],'advanced_combat':['누르기','베어가르기','록온','싫은소리']}
DRIVES={
 'magmarizer':(['불꽃펀치','화염방사','회오리불꽃'],['내열'],['얼음']),
 'electirizer':(['번개펀치','방전','전자부유'],['전기엔진'],['마비']),
 'metal_coat':(['아이언헤드','러스터캐논','철벽'],[],[]),
 'upgrade':(['트라이어택','텍스처','전기자석파'],['다운로드','애널라이즈'],[]),
 'dubious_disc':(['손가락흔들기','경혈찌르기','사슬묶기'],['변덕쟁이'],[]),
}
COSTS={'basic_combat':1,'basic_utility':1,'advanced_combat':2,'advanced_utility':2,'sympathetic_drive':2,'repair_nanites':2,'wired_core':3}


def project(e,row,p,registry,index):
    material=row.get('material','standard')
    if material not in MATERIALS:raise ValueError('Pokebot material requires a selected sourced definition')
    if material!='standard':e.r._selected_rule('supp-polygon/포켓봇-재료-대안들')
    result={'material':material,'defense_matchup':deepcopy(MATERIALS[material]),'effective_types':[],
        'movement':{'land':row['base_body']['land']},'power':row['base_body']['power'],
        'skills':dict(row['skills']),'capabilities':list(p['pokebot_base_capabilities']),
        'moves':[],'abilities':[],'extra_condition_immunities':[],
        'organic_healing_allowed':False,'source_grants':[],'unresolved_component_ids':[],'unresolved':[]}
    if material=='psionic_alloy':result['capabilities'].remove('mindlock');result['capabilities'].append('telepathic_control')
    seen=set();skill_picks=0;wired=[];swim=False;speed_bonus=0
    for c in row['components']:
        module=c.get('module_id')
        if module is None:result['unresolved_component_ids'].append(c['instance_id']);continue
        if module not in COSTS or c['complexity']!=COSTS[module]:raise ValueError('component complexity disagrees with its sourced module')
        e.r._selected_rule('feat/엔지니어')
        choice=c.get('choice');grant={'source_instance_id':c['instance_id'],'module_id':module,'choice':deepcopy(choice)}
        if module in MOVES:
            if not isinstance(choice,list) or len(choice)!=2 or len(set(choice))!=2 or not set(choice)<=set(MOVES[module]):raise ValueError('combat module requires two distinct allowed move choices')
            keys=[(module,m) for m in choice]
            if any(k in seen for k in keys):raise ValueError('repeat combat parts must choose different moves')
            seen.update(keys);result['moves'].extend(choice)
        elif module=='basic_utility':
            if choice not in ('movement_plus4','swim_half_land','levitate_sky2','stealth_and_silent'):raise ValueError('unknown basic utility choice')
            key=(module,choice)
            if key in seen:raise ValueError('repeat basic utility parts must choose different effects')
            seen.add(key)
            if choice=='movement_plus4':speed_bonus+=4
            elif choice=='swim_half_land':swim=True
            elif choice=='levitate_sky2':result['abilities'].append('부유');result['movement']['sky']=2
            else:result['capabilities'].extend(['stealth','dead_silent'])
        elif module=='advanced_utility':
            if not isinstance(choice,dict) or choice.get('kind') not in ('skills','power_plus4','magnetic'):raise ValueError('explicit advanced utility choice required')
            name=choice['kind'];key=(module,name)
            if name=='skills':
                values=choice.get('ranks')
                if not isinstance(values,dict) or not values:raise ValueError('assigned skill ranks required')
                for k,v in values.items():
                    if not isinstance(k,str) or not k:raise ValueError('skill identity required')
                    F.integer(v,'component skill ranks',0)
                if sum(values.values())!=3:raise ValueError('advanced utility grants exactly three skill ranks')
                skill_picks+=1
                if skill_picks>2:raise ValueError('advanced utility skill option may be chosen only twice')
                for k,v in values.items():result['skills'][k]=result['skills'].get(k,0)+v
            else:
                if key in seen:raise ValueError('repeat advanced utility parts must choose different effects')
                seen.add(key)
                if name=='power_plus4':result['power']+=4
                else:result['capabilities'].append('magnetic');result['special_immunities']=['scramble','emp']
        elif module=='sympathetic_drive':
            if not isinstance(choice,dict) or set(choice)!={'item','mode'} or choice['item'] not in DRIVES or choice['mode'] not in ('moves','trait'):raise ValueError('sourced sympathetic drive item/mode required')
            key=(module,choice['item'],choice['mode'])
            if key in seen:raise ValueError('two sympathetic drives cannot grant the same effect')
            seen.add(key);moves,abilities,immunities=DRIVES[choice['item']]
            if choice['mode']=='moves':result['moves'].extend(moves)
            else:
                result['abilities'].extend(abilities);result['extra_condition_immunities'].extend(immunities)
                if choice['item']=='metal_coat':result['effective_types']=['강철'];result['defense_matchup']={'type_matchup':'강철','replaces_material':True}
                if choice['item']=='dubious_disc':result['organic_healing_allowed']=True
        elif module=='repair_nanites':
            if module in seen:raise ValueError('duplicate identical Repair Nanites source is unsupported')
            seen.add(module);result['abilities'].append('재생력');result['food_buff_access']={'rule':'먹다남은음식','uses_per_day':1,'action':'extended'}
        elif module=='wired_core':wired.append(c)
        result['source_grants'].append(grant)
    for mode in result['movement']:result['movement'][mode]+=speed_bonus
    if swim:
        result['movement']['swim']=None if speed_bonus else M.ratio(result['movement']['land'],2)
        if speed_bonus:
            result['relative_movement']={'swim':{'source_fraction':[1,2],'of':'land','all_movement_bonus':speed_bonus}}
            result['unresolved'].append('C2SPECIAL-CONFLICT-bot-relative-movement-order')
    for c in wired:
        choice=c.get('choice')
        if not isinstance(choice,dict) or set(choice)!={'moves','ability','controller_id'}:raise ValueError('wired core permanent choices and actual interface controller required')
        if not isinstance(choice['moves'],list) or len(choice['moves'])>2 or len(set(choice['moves']))!=len(choice['moves']) or not set(choice['moves'])<=set(result['moves']):raise ValueError('wired core selects at most two actual bot moves')
        if choice['ability'] not in result['abilities']:raise ValueError('wired core selects an actual bot ability')
        if choice['controller_id'] is not None:
            controller=index.get(choice['controller_id'])
            if controller is None or controller.kind!='pokemon':raise ValueError('wired core controller must be an actual Pokemon')
            result['wired_projection']={'controller_id':controller.entity_id,'moves':list(choice['moves']),'ability':choice['ability'],'bot_other_moves_available':False,'interface_capability_permission_checked':False}
            import control_remote as REMOTE
            routes=REMOTE.wired_routes(e,row,controller.entity_id)
            result['wired_projection'].update(actual_remote_route_ids=routes,interface_capability_permission_checked=bool(routes))
    return result
