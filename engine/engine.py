"""
PTK(PTU 1.05 한국어 번역) A층 파일럿 엔진.
SRD 파일럿(../srd-structure-experiment/engine/engine.py)과 같은 설계 원칙으로, 판정 방식만 PTU 식으로 바꾼 것:
  - d20 명중 굴림 vs (기술 AC + 회피)       [SRD: d20 + 보너스 vs AC]
  - 기본 데미지(DB) → 데미지 표 → 공격 스탯 가산 → 방어 스탯 감산 → 타입 배수   [SRD: 주사위 + 능력치 수정, 저항/취약 ×0.5/×2]
  - 전투단계 승수, 부상(대규모 데미지·체력 표시점), 소량의 체력, 포획 굴림
임계값·배수·순서는 전부 data/core-rules.json, data/lookup-tables.json, data/conditions.json 에서 읽고,
모든 로그 줄에 근거 RuleUnit id 를 붙인다.

  python -X utf8 -I engine/engine.py <experiment_root> [seed]
"""
import json
import math
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arithmetic_policy as M
import state_fields as STATE_FIELDS
import arithmetic as EXACT
import combat_precision_features as CPF
import move_activation as MOVE_ACTIVATION
import effect_lifetimes as EFFECT_LIFETIMES
import effect_contracts as EFFECT_CONTRACTS
import heavy_injury_adapter as HEAVY
import temporary_hp as TEMP_HP
import heavy_standard_adapter as HEAVY_STANDARD
import passive_events as PASSIVE_EVENTS
import event_trace as TRACE
import league_runtime as LEAGUE
import action_lifecycle as ACTION
import missed_ball_body as BALL_BODY
import life as LIFE
import common_checks as CHECKS
import roll_pools as POOLS
import capability_actions as CAPABILITIES
import action_points as AP
import ap_roll_bonus as AP_ROLL
import common_action_checks as COMMON_ACTIONS
import optional_weapon_framework as OPTIONAL_WEAPONS
import reactive_ability_events as REACTIVE_ABILITIES
import move_defense_reactions as DEFENSE
import ability_interrupt_choices as ABILITY_INTERRUPTS
import ability_reaction_choices as ABILITY_REACTIONS
import skill_modifiers as SKILL_MODIFIERS
import frequency as FREQ
import damage_reactions as REACTIONS
from grid import Grid, cheb  # noqa: E402
import effects as FX  # noqa: E402
import effects_ext as EXT  # noqa: E402
import items as ITEMS  # noqa: E402
from rulings import Rulings, calc  # noqa: E402
from ruleset import RuleFilter, base_name, UnresolvedRuleSelection, source_unit, build_runtime_selection, require_runtime_weapon, bind_rule_identity  # noqa: E402
from gm_state import GMState  # noqa: E402
import turn as TURN  # noqa: E402

STAT_KO = {"공격": "atk", "방어": "def", "특수공격": "spa", "특수방어": "spd", "스피드": "spe", "특공": "spa", "특방": "spd"}
import status_sets as STATUS_SETS
STATUS_NORM = STATUS_SETS.ALIASES


def _excluded_move_admission(fn):
    """Keep native exclusion refusal ahead of selected-source feature readers."""
    from functools import wraps
    @wraps(fn)
    def run(engine, attacker, target, move_id, *args, **kwargs):
        if move_id in engine.r.excluded_moves:
            if engine._ruleset_move(attacker, move_id) is None:
                return 0
        return fn(engine, attacker, target, move_id, *args, **kwargs)
    return run


class Rules:
    def __init__(self, root, use_hand=True, rulings_path=None, ruleset=None, custom_species=None):
        self.root = root
        self.use_hand = use_hand
        with open(os.path.join(root, "data/skill-check-policy.json"), encoding="utf-8") as policy_file:
            self.skill_policy = json.load(policy_file)
        self.rulings = Rulings()
        self.ruleset = RuleFilter.load(root, ruleset)
        # 종·학습·스킬 데이터 (생성기용). 커스텀 종은 data/custom/species/*.json 또는 인자로 합쳐진다 (출처 'custom').
        self.species, self.learnsets, self.learnset_links, self.species_skills = {}, {}, {}, {}
        for rel, store, key in (("output/entities/pokemon.json", "species", "id"), ("output/entities/learnsets.json", "learnsets", "species"),
                                ("output/entities/learnset_links.json", "learnset_links", "species"), ("output/entities/species_skills.json", "species_skills", "species")):
            q = os.path.join(root, rel)
            if os.path.exists(q):
                for x in json.load(open(q, encoding="utf-8")):
                    getattr(self, store)[x[key]] = x["skills"] if store == "species_skills" else x

        self.units = {}
        for u in json.load(open(os.path.join(root, "data/core-rules.json"), encoding="utf-8"))["units"]:
            self.units[u["id"]] = u
        for rel in ("data/lookup-tables.json", "data/conditions.json"):
            for u in json.load(open(os.path.join(root, rel), encoding="utf-8")):
                self.units[u["id"]] = u
        import condition_editions as CONDITION_EDITIONS
        CONDITION_EDITIONS.install(self)
        p = os.path.join(root, "data/progression-rules.json")         # 경험치 표·레벨업·진화·트레이너 경험치 (engine/downtime.py)
        if os.path.exists(p):
            for u in json.load(open(p, encoding="utf-8"))["units"]:
                self.units[u["id"]] = u
        # C층 아이템·재주·엣지 mech: 규칙 기반(…-mech.json) full > LLM 초안(…-llm.json) > 규칙 기반 partial  (engine/items.py 가 소비)
        self.items_mech, self.items_llm, self.feats_mech, self.feats_llm, self.edges_llm = {}, {}, {}, {}, {}
        for rel, attr, key in (("data/items-mech.json", "items_mech", None), ("data/items-llm.json", "items_llm", "items"), ("data/feats-mech.json", "feats_mech", None),
                               ("data/feats-llm.json", "feats_llm", "feats"), ("data/edges-llm.json", "edges_llm", "edges")):
            p = os.path.join(root, rel)
            if os.path.exists(p):
                d = json.load(open(p, encoding="utf-8"))
                setattr(self, attr, {k: v for k, v in (d[key] if key else d).items() if not k.startswith("$")})
        item_meta_path = os.path.join(root, "output/entities/items_sheet.json")
        if os.path.exists(item_meta_path):
            sys.path.insert(0, os.path.join(root, "tools"))
            from item_records import sheet_items
            for item in sheet_items(root):
                if item.get("_same_source_effect") and item["id"] not in self.items_llm and item["_source_id"] in self.items_llm:
                    self.items_llm[item["id"]] = self.items_llm[item["_source_id"]]
        self.items_reviewed, self.feats_reviewed, self.edges_reviewed = {}, {}, {}
        for rel, attr, key in (("data/items-reviewed.json", "items_llm", "items"), ("data/feats-reviewed.json", "feats_llm", "feats"), ("data/edges-reviewed.json", "edges_llm", "edges")):
            p = os.path.join(root, rel)          # 검수본(reviewed)은 같은 id 의 llm 초안을 덮어쓴다
            if os.path.exists(p):
                for k, v in json.load(open(p, encoding="utf-8"))[key].items():
                    getattr(self, attr)[k] = v["effects"]
                    getattr(self, attr.replace("_llm", "_reviewed"))[k] = v["effects"]
        self.creatures = {c["id"]: c for c in json.load(open(os.path.join(root, "data/creatures.json"), encoding="utf-8"))["creatures"]}
        self.moves = {m["id"]: m for m in json.load(open(os.path.join(root, "output/entities/moves.json"), encoding="utf-8"))}
        self._runtime_weapon_declarations = {}
        self.moves_hand = json.load(open(os.path.join(root, "data/moves-hand.json"), encoding="utf-8"))["moves"]
        p = os.path.join(root, "data/moves-mech.json")
        self.moves_mech = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
        p = os.path.join(root, "data/moves-llm.json")
        self.moves_llm = json.load(open(p, encoding="utf-8"))["moves"] if os.path.exists(p) else {}
        p = os.path.join(root, "data/moves-llm-partial.json")
        self.moves_llm_partial = json.load(open(p, encoding="utf-8"))["moves"] if os.path.exists(p) else {}
        self.ability_effects = {}
        self.ability_freq = {}
        p = os.path.join(root, "output/entities/abilities.json")
        if os.path.exists(p):
            for a in json.load(open(p, encoding="utf-8")):
                self.ability_freq[a["name"]] = a.get("frequency")
        p = os.path.join(root, "data/abilities-mech.json")
        if os.path.exists(p):
            for a in json.load(open(p, encoding="utf-8")).values():
                self.ability_effects[a["name"]] = [{k: v for k, v in e.items() if k != "_src"} for e in a["effects"]]
        p = os.path.join(root, "data/abilities-llm.json")
        if os.path.exists(p):
            for k, v in json.load(open(p, encoding="utf-8"))["abilities"].items():
                self.ability_effects[k] = v
        self.moves_reviewed = {}
        p = os.path.join(root, "data/moves-reviewed.json")
        if os.path.exists(p):
            self.moves_reviewed = json.load(open(p, encoding="utf-8"))["moves"]
        p = os.path.join(root, "data/abilities-reviewed.json")
        if os.path.exists(p):      # id 키 → 특성 이름으로 (ability_effects 는 이름 키)
            id2name = {}
            q = os.path.join(root, "output/entities/abilities.json")
            if os.path.exists(q):
                id2name = {x["id"]: x["name"] for x in json.load(open(q, encoding="utf-8"))}
            for k, v in json.load(open(p, encoding="utf-8"))["abilities"].items():
                self.ability_effects[id2name.get(k, k)] = v["effects"]
        s = self.mech("combat/struggle")
        self.moves["struggle"] = {"id": "struggle", "name": s["name"], "type": s["type"], "class": s["class"], "ac": s["ac"],
                                  "damage_base": s["damage_base"], "frequency": s["frequency"], "range": s["range"], "effect": "", "mech_auto": {}}
        self.custom_species = []
        cdir = os.path.join(root, "data/custom/species")
        paths = sorted(os.path.join(cdir, f) for f in os.listdir(cdir) if f.endswith(".json")) if os.path.isdir(cdir) else []
        for cp in list(paths) + [os.path.join(root, x) if not os.path.isabs(x) else x for x in (custom_species or [])]:
            self.load_custom_species(cp)
        import core_weather_abilities as CORE_WEATHER
        self.core_abilities = CORE_WEATHER.definitions(self)
        import base_stage_abilities as BASE_ABILITIES
        self.base_stage_abilities = BASE_ABILITIES.definitions(self)
        for definition in self.core_abilities.values():
            self.ability_freq[definition["name"]] = definition["frequency"]
            if 'effects' in definition:self.ability_effects[definition['name']]=__import__('copy').deepcopy(definition['effects'])
            else:self.ability_effects.setdefault(definition["name"], [])
        self._apply_ruleset()
        __import__('trickster').install(self)
        __import__('commander').install(self)
        __import__('marksman').install(self)
        __import__('z_moves').install(self)
        import martial_artist_ability_identities as MARTIAL_IDENTITIES
        MARTIAL_IDENTITIES.install(self)
        import example_species as EXAMPLES
        EXAMPLES.install(self)
        import ability_transitions as ABILITY_TRANSITIONS
        ABILITY_TRANSITIONS.install(self)
        __import__('ability_exchange_contracts').install(self)
        import ability_state_projection as ABILITY_STATE_PROJECTION
        ABILITY_STATE_PROJECTION.install(self)
        REACTIVE_ABILITIES.install(self)
        DEFENSE.install(self)
        import capacity_abilities as CAPACITY_ABILITIES
        CAPACITY_ABILITIES.install(self)
        import digital_programs as DIGITAL_PROGRAMS
        DIGITAL_PROGRAMS.install(self)
        __import__('fortress').install_shields(self)
        __import__('glitch_bender').install(self)
        import mega_forms as MEGA
        MEGA.install(self)
        __import__('csv_item_form_contracts').install(self)
        for rf in self.ruleset.rulings_files:        # 룰셋 프로필이 지정한 재정 파일 (core+errata → 에라타 재정)
            self.rulings.load(os.path.join(root, rf), self)
        if rulings_path:
            self.rulings.load(rulings_path, self)
        if getattr(Rules, "_gm_provider", None) is not None:
            self.rulings.provider = Rules._gm_provider

    def select_source_definition(self, requested_id, *, source=None, supports_versions=False):
        """Select one whole definition and optionally verify its current source."""
        import source_selection
        return source_selection.select(self,requested_id,source=source,supports_versions=supports_versions)

    def validate_source_selection(self, record):
        """Recheck selection/provenance instead of trusting an earlier record."""
        import source_selection
        return source_selection.validate(self,record)

    def bind_source_policy(self, requested_id, definitions, *, supports_versions=False):
        """Read complete policy values only from the selected source definition."""
        import source_selection
        return source_selection.bind_policy(self,requested_id,definitions,supports_versions=supports_versions)

    def catalog_definition(self, identity):
        """Return source-selected rows/cells for external rule-authoring scripts."""
        import source_catalog
        return source_catalog.definition(self, identity)

    def load_source_policy_package(self, package):
        """Load validated data declarations without executing their effects."""
        import source_policy
        return source_policy.load_package(self, package)

    def source_policy_document(self, policy_id):
        """Read a detached loaded declaration for the normal execution entry."""
        import source_policy
        return source_policy.loaded_document(self, policy_id)

    def register_source_policy_definitions(self, definitions):
        """Register explicit source-located authored IDs without replacing native rules."""
        import source_policy
        return source_policy.register_sources(self, definitions)

    def resolve_source_policy(self, document, *, context=None, decisions=None):
        """Prepare authored source-bound values; unresolved inputs never execute."""
        import source_policy
        return source_policy.resolve(self, document, context=context, decisions=decisions)

    def mech(self, uid):
        if hasattr(self, "selection"):
            self.selection.require_current_filter(self.ruleset)
            uid = self.selection.require_supported_version(uid, supports_versions=True)
        u = self.units[uid]
        if not hasattr(self, "selection"):
            self.ruleset.require(source_unit(u))
        assert u.get("mech"), f"{uid} 는 mech 층이 없음"
        base = self.ruleset.mech_version(uid, u["mech"]["data"])
        resolved = self.rulings.apply_mech(uid, base)
        import source_context as SOURCE_CONTEXT
        return SOURCE_CONTEXT.mech_read(self,uid,base,resolved) if hasattr(self,"selection") else resolved

    def _apply_ruleset(self):
        """룰셋 필터: 제외된 기술/특성과 코어판→변형판 치환표를 만든다 (데이터는 지우지 않고 조회 때 거부/치환)."""
        rf = self.ruleset
        self.excluded_moves, self.move_alias = {}, {}
        units = [source_unit(m, "db/moves.csv") for m in self.moves.values() if m["id"] != "struggle"]
        kept, excluded, alias = rf.split(units)
        self.excluded_moves = {u["id"]: why for u, why in excluded}
        self.move_alias = alias
        self.unresolved_moves = dict(rf.alias_conflicts)
        self.excluded_abilities, self.ability_alias = {}, {}
        self.unresolved_abilities = {}
        p = os.path.join(self.root, "output/entities/abilities.json")
        if os.path.exists(p):
            abil = json.load(open(p, encoding="utf-8"))
            abil += list(self.core_abilities.values())
            aunits = [source_unit(a, "db/abilities.csv") for a in abil]
            kept_a, excluded_a, alias_a = rf.split(aunits)
            name_of = {a["id"]: a["name"] for a in abil}
            self.excluded_abilities = {name_of[u["id"]]: why for u, why in excluded_a}
            self.ability_alias = {name_of[b]: name_of[v] for b, v in alias_a.items()}
            self.unresolved_abilities = {name_of[b]: options for b, options in rf.alias_conflicts.items()}
            if rf.replaces:        # id 접미사로 못 잡는 이름 표식 변형(예: '옹골참' ↔ '옹골참 [Playtest]')도 이름으로 연결
                kept_names = {a["name"] for a in abil if a["id"] in {u["id"] for u in kept_a}}
                options_by_name = {}
                for n in kept_names:
                    b = base_name(n)
                    if b != n and b in kept_names and b not in self.unresolved_abilities:
                        options_by_name.setdefault(b, set()).add(n)
                for b, options in options_by_name.items():
                    if b in self.ability_alias:
                        continue  # Explicit ID choice already resolved this family.
                    if len(options) == 1:
                        self.ability_alias[b] = next(iter(options))
                    else:
                        self.unresolved_abilities[b] = sorted(options)
            # The current effect registry is name-keyed. An ID choice cannot safely
            # distinguish two retained entities with the same target name.
            ids_by_name = {}
            for u in kept_a:
                ids_by_name.setdefault(name_of[u["id"]], []).append(u["id"])
            for base, target_name in list(self.ability_alias.items()):
                ids = ids_by_name.get(target_name, [])
                if len(ids) > 1:
                    self.unresolved_abilities[base] = sorted(ids)
                    del self.ability_alias[base]

        self.selection = build_runtime_selection(self)
        # Species are read directly by the builder: remove inactive identities
        # from the runtime view, retaining provenance in the selection catalog.
        if hasattr(self, "species"):
            self.species = {uid: sp for uid, sp in self.species.items()
                            if self.ruleset.allows(source_unit(sp))[0]}
        __import__('fortress').install_shields(self)
        __import__('glitch_bender').install(self)

    from source_selection import native_selected_rule as _selected_rule

    def resolve_move(self, mid):
        if mid in self.unresolved_moves:
            raise UnresolvedRuleSelection(mid, self.unresolved_moves[mid])
        mid = self.move_alias.get(mid, mid)
        return self.move_id(mid) or self._selected_rule(mid)

    def load_custom_species(self, path):
        """커스텀 종 파일(custom_species.validate 로 검증됨)을 종·학습·스킬 테이블에 합친다. 같은 id 가 있으면 덮어쓰고 출처를 'custom' 으로 표시한다."""
        from custom_species import load_and_validate
        # Check BEFORE loading: custom definitions can overwrite core IDs.
        provenance = {"file": "data/custom/species/" + os.path.basename(path)}
        marker = {"id": "custom/species-file", "title": "custom species", "source": provenance}
        if not self.ruleset.allows(marker)[0]:
            return None
        sp, ls, links, skills = load_and_validate(self, path)
        with open(path, encoding="utf-8") as handle:
            definition = json.load(handle)
        metadata = getattr(self, "_custom_rule_metadata", {})
        for name in (definition.get("custom_abilities") or {}):
            uid = "ability/custom/" + name
            metadata[uid] = {"id": uid, "title": name, "source": provenance}
        self._custom_rule_metadata = metadata
        self.species[sp["id"]] = sp
        self.learnsets[sp["name"]] = ls
        self.learnset_links[sp["name"]] = links
        if skills:
            self.species_skills[sp["name"]] = skills
        self.custom_species.append(sp["id"])
        if hasattr(self, "selection"):
            self._apply_ruleset()
        return sp

    def formula(self, name):
        import source_context as SOURCE_CONTEXT
        value = self.rulings.formula_expr(name, self)
        return SOURCE_CONTEXT.formula_read(self,name,value) if hasattr(self,"selection") else value

    def move(self, mid):
        import special_entities as SPECIAL
        instance=SPECIAL.prime_instance(self,mid)
        if instance is not None:
            return dict(self.move(instance['move_id']),id=mid,type=instance['type'],
                **{'class':'물리' if instance['damage_class']=='physical' else '특수'},prime_unown_instance=instance)
        import coordinator as COORDINATOR
        created=COORDINATOR.innovation_instance(self,mid)
        if created is not None:return COORDINATOR.definition(self,mid,created)
        import dancer as DANCER
        dance=DANCER.dance_instance(self,mid)
        if dance is not None:return DANCER.definition(self,mid,dance)
        mid = self._selected_rule(mid)
        import homebrew_weather as HOME_WEATHER
        return __import__('glitch_moves').definition(self,__import__('aura_guardian').move_definition(self,HOME_WEATHER.adapt_move(self,self.moves[mid])))

    def move_mech(self, mid):
        mid = self._selected_rule(mid)
        mm, conf = self._move_mech(mid)
        import homebrew_weather as HOME_WEATHER
        mm, conf = HOME_WEATHER.adapt_mechanics(self,mid,mm,conf)
        import area_targets as AREA
        mm = __import__('stockpile_moves').mechanics(self,mid,__import__('glitch_moves').mechanics(self,mid,AREA.mechanics(self,mid,mm)))
        if mid in self.rulings.effects:
            mm, conf = self.rulings.apply_effects(mid, mm), conf + "+gm"
        import gmax_moves as GMAX
        mm = GMAX.prepare_mechanics(self,mid,mm)
        import move_coins as COINS
        mm = COINS.mechanics(self,mid,mm)
        import declarative_move_contracts as DECLARATIVE_MOVES
        import dynamic_chain_moves as CHAIN
        import double_team as DOUBLE
        import roar as ROAR
        mm=ROAR.mechanics(self,mid,DOUBLE.mechanics(self,mid,CHAIN.mechanics(self,mid,DECLARATIVE_MOVES.prepare_mechanics(self,mid,mm))))
        mm=__import__('multi_strike').mechanics(self,mid,mm)
        mm=__import__('jump_kick').mechanics(self,mid,mm)
        mm=__import__('defense_curl').mechanics(self,mid,mm)
        mm=__import__('native_path_area_moves').mechanics(self,mid,mm)
        mm=__import__('focus_punch').mechanics(self,mid,mm)
        mm=__import__('natural_fighter_moves').mechanics(self,mid,mm)
        mm=__import__('substitute').toxic_mechanics(self,mid,mm)
        mm=__import__('fling_move').mechanics(self,mid,mm)
        return __import__('warper').mechanics(self,mid,__import__('telepath').mechanics(self,mid,__import__('telekinetic').mechanics(self,mid,__import__('combat_move_reactions').mechanics(self,mid,mm)))),conf

    def _move_mech(self, mid):
        """우선순위: 사람이 채운 mech(data/moves-hand.json) > 자동 기계화(data/moves-mech.json, tools/mechanize_moves.py) > 식별 플래그(mech_auto)."""
        import special_entities as SPECIAL
        instance=SPECIAL.prime_instance(self,mid)
        import coordinator as COORDINATOR
        created=COORDINATOR.innovation_instance(self,mid)
        if created is not None:return COORDINATOR.mechanics(self,created),'innovation'
        import dancer as DANCER
        dance=DANCER.dance_instance(self,mid)
        if dance is not None:return DANCER.mechanics(self,dance),'dancer'
        mid = self._selected_rule(instance['move_id'] if instance is not None else mid)
        if self.use_hand and mid in self.moves_hand:
            return self.moves_hand[mid]["mech"], "hand"
        if mid in self.moves_reviewed:
            effects=__import__('catalog_move_states').reviewed_effects(self,mid,self.moves_reviewed[mid]["effects"])
            return self.flatten_effects(effects), "reviewed"
        if mid in self.moves_mech:
            auto = self.moves_mech[mid]
            name = auto["name"]
            if auto["coverage"] == "full":
                return self.flatten_effects(auto["effects"]), "auto:full"
            if auto["coverage"] == "none" and name in self.moves_llm:
                return self.flatten_effects(self.moves_llm[name]["effects"]), "llm"
            if auto["coverage"] == "partial" and name in self.moves_llm_partial:
                return self.flatten_effects(auto["effects"] + self.moves_llm_partial[name]), "auto+llm"
            return self.flatten_effects(auto["effects"]), "auto:" + auto["coverage"]
        if mid in self.moves:
            return self.moves[mid].get("mech_auto", {}), "auto"
        return {}, "none"

    @staticmethod
    def flatten_effects(effects):
        """Only lossless legacy projections; preserve every other declaration.

        A duration, target, condition or second contributor must never disappear
        merely because a familiar effect type has a legacy fast path.
        """
        from copy import deepcopy
        mm = {}
        for raw in effects:
            if not isinstance(raw,dict) or 'type' not in raw:
                raise ValueError('typed effect declaration required')
            e=deepcopy(raw);t=e['type']
            # Metadata is preserved on dispatched records, not a condition.
            keys=set(e)-{'_src','_rule_id','_rule_source'}
            if (t=='apply_status' and keys<={'type','status','target'}
                    and e.get('target','target')=='target' and 'apply_status' not in mm):
                mm['apply_status']=e['status']
            elif t=='never_miss' and keys=={'type'}:
                mm['never_miss']=True
            elif (t=='drain' and keys<={'type','fraction','of','target'}
                    and e.get('target','self')=='self' and e.get('of','damage_dealt')=='damage_dealt'
                    and 'drain' not in mm):
                mm['drain']={'fraction':e['fraction'],'of':'damage_dealt'}
            else:
                mm.setdefault('effects_exec',[]).append(e)
        return mm

    def condition_effects(self, cond):
        import boss_transitions as BOSS
        if cond in BOSS.VARIANT_SOURCES:
            # Boss variants replace action/save effects, but Chilled retains
            # Frozen's sourced cure on an actual hit of the listed types.
            return [effect for effect in self.condition_effects(BOSS.condition_source(cond))
                    if effect.get("type") == "cured_by_damage_of_types"]
        if f"condition/{cond}" not in self.units:
            import custom_condition_effects as CUSTOM
            if CUSTOM.by_name(self,cond) is not None:return []
        return self.mech(f"condition/{cond}")["effects"]

    def condition_class(self, cond):
        import boss_transitions as BOSS
        if cond in BOSS.VARIANT_SOURCES:
            return self.condition_class(BOSS.condition_source(cond))
        u = self.units.get(f"condition/{cond}")
        if u:return self.mech(f"condition/{cond}").get("class")
        import custom_condition_effects as CUSTOM
        row=CUSTOM.by_name(self,cond)
        return row['payload']['class'] if row else None

    def move_id(self, name):
        """기술 이름 → id (별칭·룰셋 치환 반영). 없으면 None."""
        import special_entities as SPECIAL
        if SPECIAL.prime_instance(self,name) is not None:return name
        if __import__('coordinator').innovation_instance(self,name) is not None:return name
        if __import__('dancer').dance_instance(self,name) is not None:return name
        if name in self.moves:
            return self._selected_rule(name)
        mid = "move/" + re.sub(r"[^0-9a-z가-힣]+", "-", str(name).lower()).strip("-")
        if mid in self.moves:
            return self._selected_rule(mid)
        candidates = [m["id"] for m in self.moves.values() if m.get("name") == name]
        if not candidates:
            return None
        if hasattr(self, "selection"):
            return self._selected_rule(self.selection.resolve_name(name, ("move/",)))
        return candidates[0]

    def _pick(self, auto, llm, reviewed=None):
        """(effects, header, confidence): reviewed > auto full > llm > auto partial."""
        if reviewed is not None:
            return reviewed, (auto or {}).get("header", {}), "reviewed"
        if auto and auto.get("coverage") == "full":
            return [{k: v for k, v in e.items() if k != "_src"} for e in auto["effects"]], auto.get("header", {}), "auto"
        if llm is not None:
            return llm, (auto or {}).get("header", {}), "llm"
        if auto:
            return [{k: v for k, v in e.items() if k != "_src"} for e in auto["effects"]], auto.get("header", {}), "auto:" + str(auto.get("coverage"))
        return None, {}, None

    def item_effects(self, name):
        """아이템 이름 또는 id → (effects, header+desc). 없으면 (None, {})."""
        prefixes = ("item/", "augment/", "crafted_item/")
        key = name if name.startswith(prefixes) else "item/" + re.sub(r"[^0-9a-z가-힣]+", "-", str(name).lower()).strip("-")
        if not name.startswith(prefixes) and hasattr(self,"selection"):
            candidates=[uid for uid in self.selection.names.get(name,()) if uid.startswith(prefixes)]
            if len(candidates)>1:
                raise UnresolvedRuleSelection(name,candidates)
        auto = self.items_mech.get(key)
        if auto is None:
            key = next((k for k, v in self.items_mech.items() if v.get("name") == name), key)
            auto = self.items_mech.get(key)
        if auto is not None or key in self.items_llm or key in self.items_reviewed:
            key = self._selected_rule(key)
            auto = self.items_mech.get(key)
        effs, header, conf = self._pick(auto, self.items_llm.get(key), self.items_reviewed.get(key))
        if effs is None:
            return None, {}
        header = dict(header, desc=(auto or {}).get("desc", ""), confidence=conf, id=key)
        import equipped_transport_saddle as EQUIPMENT
        effs,header=EQUIPMENT.saddle_definition(self,key,effs,header)
        import equipment_item_contracts as EQUIPMENT_ITEMS
        header = EQUIPMENT_ITEMS.battle_tool_header(self, key, header)
        import fashion_items as FASHION
        header = FASHION.core_header(self, key, header)
        return effs, header

    def feat_effects(self, name):
        """재주/엣지 이름 또는 id → (effects, header). 같은 이름의 여러 종류는 명시적 ID가 필요하다."""
        slug = re.sub(r"[^0-9a-z가-힣]+", "-", str(name).lower()).strip("-")
        keys = [name] if "/" in name else [f"feat/{slug}", f"edge/{slug}", f"poke_edge/{slug}"]
        if "/" not in name and hasattr(self,"selection"):
            candidates=sorted({key for key in keys if key in self.selection.units} |
                              {uid for uid in self.selection.names.get(name,()) if uid.startswith(("feat/","edge/","poke_edge/","gift/"))})
            if len(candidates)>1:
                raise UnresolvedRuleSelection(name,candidates)
        for key in keys:
            if any(key in getattr(self, attr) for attr in ("feats_mech", "feats_llm", "feats_reviewed", "edges_llm", "edges_reviewed")):
                if key=='feat/훈련-상황':__import__('athlete').regime_source(self)
                elif key=='feat/작열':__import__('pokemon_move_edges').incandescence_source(self)
                elif key=='feat/패싱-왈츠':__import__('dancer').waltz_source(self)
                else:key = self._selected_rule(key)
            auto = self.feats_mech.get(key)
            llm = self.feats_llm.get(key) if key.startswith(("feat/", "gift/")) else self.edges_llm.get(key)
            reviewed = self.feats_reviewed if key.startswith(("feat/", "gift/")) else self.edges_reviewed
            effs, header, conf = self._pick(auto, llm, reviewed.get(key))
            if effs is not None:
                return effs, dict(header, confidence=conf, id=key)
        return None, {}


class Combatant:
    @property
    def ap_account(self):
        return AP.ActionPointAccount(self)

    @property
    def acquisitions(self):
        from acquisition_ledger import AcquisitionLedger
        return AcquisitionLedger(self)

    @property
    def active_effects(self):
        from state_grants import ActiveEffects
        return ActiveEffects(self)

    def __init__(self, rules, spec):
        STATE_FIELDS.validate_base(spec)
        import actor_templates as TEMPLATES
        TEMPLATES.validate_soulless_default(rules,spec)
        self.r = rules
        self.spec = spec
        self._entity_id = STATE_FIELDS.identity(spec)
        self._state_revision = 0
        self._state_receipts = {}
        self._state_origin = {"kind": "sheet_import", "structure_validated": True,
                              "creation_legality_certified": False,
                              "profile": getattr(getattr(rules, "ruleset", None), "name", None)}
        self._weight_class = None
        self.name = spec["name"]
        self.level = spec["level"]
        self.stats = dict(spec["stats"])
        self.types = list(spec.get("types", []))
        self.kind = spec["kind"]
        self.stages = {k: 0 for k in ("atk", "def", "spa", "spd", "spe")}
        self.stages.update(spec.get("initial_stages", {}))
        self.accuracy_stage = 0
        self.evasion_mod = 0
        hp = rules.mech("combat/hit-points")
        assert hp["pokemon"] == "level + hp*3 + 10" and hp["trainer"] == "level*2 + hp*3 + 10"
        self.injuries = 0
        self.hp = self.max_hp
        self.conditions = set()
        LIFE.init(self)
        self.moves = list(spec.get("moves", []))
        self.move_uses = dict(spec.get("move_uses", {}))  # serialized frequency usage
        self.last_move = None
        self.captured = False
        self.took_standard = False
        if "location" in spec:
            self.location = STATE_FIELDS.location(spec["location"])
        elif "pos" in spec:
            self.pos = spec["pos"]
        else:
            self.location = {"kind": "unknown"}
        self.temp_hp = 0
        self.damage_reduction = 0
        self.abilities = list(spec.get("abilities", []))
        self.abilities_suppressed = False
        self.modifiers = []
        self.custom_conditions = {}
        self.shield = None
        self.next_attack = None
        self.initiative_override = None
        self.initiative_bonus = 0
        self.counters = {}
        self.stage_loss_immune = set()
        self.ability_triggers = []
        self.setup_move = None
        if spec.get("movement_basis") == "trainer_base":
            self._movement_delta = 0
        else:
            self._movement_value = spec.get("movement", {}).get("land", 4)
        EXT.init_combatant(self)

    @property
    def movement(self):
        if self.spec.get("movement_basis") == "trainer_base":
            if "movement" in self.__dict__:
                raise ValueError("legacy derived movement needs an explicit current/base migration; its raw delta is unknown")
            import trainer_capabilities as TRAINER
            return TRAINER.values(self)["land"] + getattr(self, "_movement_delta", 0)
        if "movement" in self.__dict__ and "_movement_value" in self.__dict__ and self.__dict__["movement"] != self._movement_value:
            raise ValueError("legacy and current movement values disagree")
        return getattr(self, "_movement_value", self.__dict__.get("movement", self.spec.get("movement", {}).get("land", 4)))

    @movement.setter
    def movement(self, value):
        if self.spec.get("movement_basis") == "trainer_base":
            import trainer_capabilities as TRAINER
            delta = value - TRAINER.values(self)["land"]
            self.__dict__.pop("movement", None)
            self._movement_delta = delta
        else:
            self.__dict__.pop("movement", None)
            self._movement_value = value

    @property
    def kind(self):
        return self.spec["kind"]

    @kind.setter
    def kind(self, value):
        if value not in ("trainer", "pokemon"):
            raise ValueError("Combatant kind must be trainer or pokemon")
        self.spec["kind"] = value

    @property
    def weight_class(self):
        import body_state as BODY
        return BODY.weight_class(self)

    @property
    def stages(self):
        import core_weather_abilities as CORE_WEATHER
        CORE_WEATHER.refresh(self)
        import base_stage_abilities as BASE_ABILITIES
        BASE_ABILITIES.refresh(self)
        return self.__dict__["stages"]

    @stages.setter
    def stages(self, value):
        self.__dict__["stages"] = value

    @property
    def item(self):
        import held_equipment as HELD
        return HELD.single(self)

    @item.setter
    def item(self, value):
        import held_equipment as HELD
        HELD.set_single(self,value)

    @property
    def entity_id(self):
        return self._entity_id

    @property
    def name(self):
        return self.spec["name"]

    @name.setter
    def name(self, value):
        self.spec["name"] = value

    @property
    def level(self):
        return self.spec["level"]

    @level.setter
    def level(self, value):
        self.spec["level"] = value

    @property
    def pos(self):
        if self.location["kind"] != "grid":
            raise ValueError("grid position is unknown or abstract; explicit location evidence is required")
        return tuple(self.location["cell"])

    @pos.setter
    def pos(self, value):
        self.location = STATE_FIELDS.location({"kind": "grid", "cell": value})

    @property
    def types(self):
        import blessing_skill_features as BLESSINGS
        import homebrew_state as HOME
        import type_state as TYPES
        return TYPES.validate_types(self.r, HOME.actual_types(self, BLESSINGS.actual_types(self,self._types)))

    @types.setter
    def types(self,value):
        import type_state as TYPES
        self._types=TYPES.validate_types(self.r,value)

    @property
    def base_max_hp(self):
        import actor_templates as TEMPLATES
        if TEMPLATES.soulless(self):
            return 1
        M.validate_source(self.r)
        expr = self.r.formula("max_hp.pokemon" if self.kind == "pokemon" else "max_hp.trainer")
        import ability_state_projection as ABILITY_STATE_PROJECTION
        return M.floor(calc(expr, {"level": self.level, "hp": ABILITY_STATE_PROJECTION.hp_stat(self)}))

    @property
    def max_hp(self):
        base = self.base_max_hp
        # Apply the full injury proportion before rounding the recovery ceiling.
        # True maximum remains the basis of fractions, markers and new injuries.
        pen = calc(self.r.formula("injury_penalty"), {"max_hp": base, "level": self.level})
        import csv_item_capability_contracts as CSV_CAP
        import taskmaster as TASK
        return M.floor(base - (TASK.injury_ceiling(self) + CSV_CAP.essence_base_injuries(self)) * pen)

    def staged(self, stat):
        M.validate_source(self.r)
        import combat_stage_sources as STAGE_SOURCES
        mult = self.r.mech("combat/combat-stage-multipliers")["multiplier_by_stage"]
        stage=STAGE_SOURCES.effective_stage(self,stat)
        import optional_state_effect_contracts as OPTIONAL_STATE
        # The stat minimum also applies after CS and source-specific reductions (ch05:54).
        return max(STATE_FIELDS.stat_minimum(self.spec, stat),
                   OPTIONAL_STATE.staged_value(self, stat, M.stage_stat(self.stats[stat],stage,mult)))

    def evasion(self, move_class, *, conditional_bonus=0, attacker=None, engine=None, ignore_stats=False, ignore_nonstats=False):
        if self.fainted or self.custom_conditions.get("_grapple_relation"):return 0
        import combat_timing as TIMING
        if TIMING.evasion_zero(self):return 0
        ignore_nonstats=ignore_nonstats or attacker is not None and __import__('keen_eye').active(engine,attacker)
        ev = self.r.mech("combat/evasion")
        conditions=__import__('blessing_effects').effective_conditions(self)
        if __import__('keen_eye').active(engine,self):conditions=set(conditions)-{'실명'}
        # Read the selected implication against actual sight; never store a synthetic status.
        import vision_impairment as VISION
        implied_conditions = set(conditions)
        vision = VISION.explicit_level(self) if engine is None else VISION.accuracy_level(engine, self)
        if vision != "none":
            implied_conditions.add(VISION.BLIND)
        if any(e.get("type") == "implied_by" and implied_conditions.intersection(e.get("conditions", ()))
               for e in self.r.condition_effects("취약")):
            return 0
        if any(e["type"] == "evasion_disabled" and not e.get("only") for c in conditions for e in self.r.condition_effects(c)):
            return 0
        src = ev["sources"]
        import evasion_source as EVASION_SOURCE
        def by(stat):
            return min(ev["cap"], EVASION_SOURCE.stat_component(self.r, ev, self.staged(stat)))
        speed_ok = not any(e["type"] == "evasion_disabled" and e.get("only") == "speed" for c in conditions for e in self.r.condition_effects(c))
        speed=by(src["speed"]) if speed_ok else 0
        if speed_ok and engine is not None:
            import control_mount as MOUNT
            speed=MOUNT.speed_evasion(engine,self,speed,ignore_nonstats=ignore_nonstats)
        import type_ace as TA
        if speed_ok and engine is not None and not ignore_nonstats:speed+=TA.speed_evasion(engine,self)
        cands = [speed]
        if move_class == "물리":
            cands.append(by(src["physical"]))
        elif move_class == "특수":
            cands.append(by(src["special"]))
        import training_features as TRAINING
        import combat_modifiers as COMBAT_MODS
        import optional_state_effect_contracts as OPTIONAL_STATE
        import unown_imbuement as UNOWN
        import duelist as DUELIST
        import taskmaster as TASK
        if attacker is not None and engine is not None:conditional_bonus+=DUELIST.evasion(engine,self,attacker)+__import__('channeler').synchronized_bonus(engine,self,attacker)
        extra = COMBAT_MODS.extra_evasion(self.evasion_mod, CAPABILITIES.evasion(self), conditional_bonus,
                                          EFFECT_LIFETIMES.numeric(self,"evasion_modifier"), TRAINING.bonus(self,"evasion"),
                                          OPTIONAL_STATE.evasion_bonus(self), UNOWN.active_count(self), TASK.bonus(self,'evasion'),
                                          TA.evasion_extra(self), __import__('chef_cooking').evasion_bonus(self,move_class),
                                          __import__('martial_artist').bonus(self,attacker,evasion=True),
                                          __import__('fortress').ordinary_shield(engine,self), __import__('fortress').shield_bonus(engine,self)[0])
        extra+=__import__('oracle').instinct_bonus(self,attacker,engine)
        extra+=__import__('telepath').evasion(self)
        extra+=__import__('warper').evasion(self)
        extra+=__import__('ace_trainer').evasion(self)
        extra+=sum(__import__('core_weather_abilities').evasion_contributions(engine,self).values())
        if ignore_nonstats:extra=0
        ignore_stats=ignore_stats or attacker is not None and TA.ignore_stat_evasion(attacker)
        value = min(9, max(0, (0 if ignore_stats else max(cands)) + extra))
        import boss_transitions as BOSS
        return BOSS.evasion(self, value)

    @property
    def fainted(self):
        import taskmaster as TASK
        return not (TASK.conscious(self) or __import__('enduring_soul').conscious(self))

    def __repr__(self):
        c = ",".join(sorted(self.conditions)) or "-"
        st = ",".join(f"{k}{v:+d}" for k, v in self.stages.items() if v) or "-"
        return f"{self.name}[HP {self.hp}/{self.max_hp} 부상 {self.injuries} 상태 {c} 단계 {st}{' 포획됨' if self.captured else ''}]"


class Engine:
    def __init__(self, rules, seed=1, *, death_enabled=True, friendly_battle=False, session_frequency=False, defer_session_refresh=None, session_move_policy=None):
        self.r = rules
        self._root_common_epoch = 0
        self._root_common_receipts = []
        self._extended_checks = {}
        self._ap_rolls = {}
        self._physical_objects = {}
        self._burrow_tunnels = []
        if type(session_frequency) is not bool or (session_frequency and type(defer_session_refresh) is not bool) or (not session_frequency and defer_session_refresh is not None):
            raise ValueError('session frequency requires an explicit selected policy and explicit defer choice')
        self.session_frequency=session_frequency
        self.defer_session_refresh=defer_session_refresh
        self.session_id=None
        self.pending_session_id=None
        self.session_ids_seen=[]
        self.session_epoch=0
        self._session_move_policy=FREQ.prepare_session_policy(self,session_move_policy)
        self.encounter_active=False
        self._party_encounter_epoch=0
        if type(death_enabled) is not bool or type(friendly_battle) is not bool:raise ValueError("life policy must be explicit booleans")
        self.death_enabled=death_enabled
        self.friendly_battle=friendly_battle
        self._campaign_injury_policy=None
        self._hp_loss_policy=None
        self.rng = random.Random(seed)
        self.seed = seed
        self.log_lines = []
        self.zones = {}          # 연막 등: {entity_id: accuracy penalty}  (격자 미사용 시)
        self.grid = None         # Grid 를 붙이면 범위 키워드로 대상을 고른다
        self.zone_cells = {}     # {cell: accuracy penalty}  (격자 사용 시 연막 등)
        self.weather = None
        self.field = None
        self.taunt = None
        self.effect_stats = {"done": 0, "held": 0}
        EXT.init_engine(self)
        self.rulings = rules.rulings
        self.gm = GMState(self)
        self.everyone = []
        self._encounter_actors = None
        self._league_runtime = None
        self._league_dispatch = False
        self._turn_closures = []
        self._active_turn_actor = None
        self._ordinary_turn_rounds = {}
        self._action_grants = []
        HEAVY.initialize(self,native_types=(Engine,Rules,Combatant))
        PASSIVE_EVENTS.initialize(self)
        import precise_actions as PRECISE
        PRECISE.initialize(self)
        self.round_no = 0
        self.elapsed_seconds = 0
        self.round_start_seconds = None
        self.unresolved_time_intervals = []
        self._time_actors = []
        self.weather_rounds = None
        self._gmax_activation_scopes = []
        self._gmax_effect_sequence = 0
        self._gmax_coin_rewards = []
        self._gmax_payload_receipts = []

    def export_state(self):
        import state_codec
        return state_codec.dump_engine(self)

    @classmethod
    def import_state(cls, rules, payload):
        import state_codec
        return state_codec.load_engine(rules, payload)

    def validate_state(self):
        import world_entities
        return world_entities.validate_world(self)

    def entity_identity(self, identity, *, kind=None):
        """Query existing native entities and composition without creating rights."""
        import world_entities
        return world_entities.entity_identity(self, identity, kind=kind)

    def actor_identity(self, identity):
        """Query an actual registered actor; identity alone creates no rights."""
        import world_entities
        return world_entities.actor_identity(self, identity)

    def time_actors(self, combatants=()):
        """Clock membership is independent of the current initiative order."""
        all_actors = [*self._time_actors, *(getattr(self, 'everyone', None) or []),
                      *(getattr(self.gm, 'everyone', None) or []), *combatants]
        import partial_entities as PARTIAL
        for actor in all_actors:PARTIAL.require_complete(actor, "time_actors")
        actors = list({id(c): c for c in all_actors}.values())
        import injury_recovery as INJURY
        # Admission must not alter earlier actors when a later candidate fails.
        for c in actors:
            FREQ.validate_session_binding(self,c);INJURY.validate_clock(c)
        self._time_actors = actors
        for c in self._time_actors:
            FREQ.bind_session(self,c);INJURY.observe_actor(self,c)
        return list(self._time_actors)

    def begin_session(self, session_id, combatants=()):
        """Explicit narrative frequency boundary, independent of elapsed days.

        The first ID labels the current session without restoring preexisting use.
        Daily Moves follow a separate explicit GM composition ruling, if chosen.
        """
        HEAVY.ensure_clear(self)
        FREQ.validate_session_policy(self)
        if not self.session_frequency:raise ValueError('narrative session frequency is not selected')
        if not isinstance(session_id,str) or not session_id.strip():raise ValueError('session ID must be nonempty text')
        if session_id in self.session_ids_seen and session_id!=self.session_id:
            raise ValueError('a past session ID cannot grant another refresh')
        if self.pending_session_id is not None and session_id not in (self.session_id,self.pending_session_id):
            raise ValueError('a deferred session boundary is already pending')
        actors=self.time_actors(combatants)
        # An idempotent boundary request can still explicitly register a newly
        # participating actor; registration itself never refreshes that actor.
        if session_id==self.pending_session_id:return 'deferred'
        if session_id==self.session_id:return 'unchanged'
        if self.session_id is None:
            self.session_id=session_id;self.session_ids_seen.append(session_id)
            return 'initialized'
        if self.encounter_active and self.defer_session_refresh:
            self.pending_session_id=session_id
            return 'deferred'
        self._apply_session_boundary(session_id,actors)
        return 'refreshed'

    def _apply_session_boundary(self, session_id, actors):
        for c in actors:FREQ.refresh_session(self,c)
        self.session_epoch+=1
        self.session_id=session_id
        self.session_ids_seen.append(session_id)
        self.pending_session_id=None
        choice=FREQ.validate_session_policy(self).get('boundary_daily_moves')
        move_result='미해석' if choice is None else ('선택한 GM 판정으로 복원' if choice['value'] else '선택한 GM 판정으로 유지')
        self.log(f'  [세션 빈도 갱신] {session_id}: 일일 재주·특성 사용량 갱신; 일일 기술 {move_result}', 'frequency/session')

    def begin_encounter(self, combatants=()):
        """Explicit encounter scope, also used automatically by start_round."""
        PASSIVE_EVENTS.ensure_clear(self)
        LEAGUE.check_boundary(self, 'begin_encounter')
        HEAVY.ensure_clear(self)
        import combat_state_lifecycle as COMBAT_STATE
        combatants = list(combatants)
        import party_actions as PARTY_ACTIONS
        PARTY_ACTIONS.require_gym_participants(self,combatants,entering=True)
        import equipment_variant_contracts as EQUIPMENT_VARIANTS
        EQUIPMENT_VARIANTS.upgrade_legacy_slipstream(self, commit=False)
        COMBAT_STATE.join(self,combatants)
        EQUIPMENT_VARIANTS.upgrade_legacy_slipstream(self)
        if not self.encounter_active:self._party_encounter_epoch=getattr(self,'_party_encounter_epoch',0)+1
        self.time_actors(combatants)
        self.encounter_active=True

    def start_round(self, combatants):
        """Apply the complete boundary through the shared state transaction."""
        import state_grants as GRANTS
        unspecified = combatants is None
        actors = () if unspecified else tuple(combatants)
        def apply(staged, primary, *participants):
            return staged._start_round(participants)
        return GRANTS.transition(self, None, apply, participants=actors, include_rulings=True)

    def _start_round(self, combatants):
        """Starting a successor declares the previous round complete (10 seconds).
        The first start itself advances no time; a partial final round is explicit.
        """
        import mapless_space as MAPLESS
        MAPLESS.ensure_clear(self)
        import actor_templates as TEMPLATES
        combatants = list(combatants)
        for actor in combatants:
            TEMPLATES.require_ordinary(actor, "start_round")
        PASSIVE_EVENTS.ensure_clear(self)
        LEAGUE.check_boundary(self, 'start_round')
        HEAVY.ensure_clear(self)
        if self._active_turn_actor is not None:
            raise ValueError("cannot advance round while a turn is open")
        combatants = list({id(c): c for c in combatants}.values())
        if self.round_start_seconds is not None:
            # Validate newcomers before advancing, but retain the old membership
            # while completing the previous round's interval.
            import combat_state_lifecycle as COMBAT_STATE
            COMBAT_STATE.members(self, combatants)
            self.end_round()
        self.begin_encounter(combatants)
        self.round_no += 1
        self.round_start_seconds = self.elapsed_seconds
        import initiative_schedule as SCHEDULE
        SCHEDULE.round_started(self,combatants)
        __import__('focused_command').round_started(self,combatants)
        TURN.weather_round_tick(self)
        import field_effects as FIELD
        FIELD.round_started(self)
        for c in combatants:
            c.aoo_used = False
            c._round_marker = self.round_no
            import boss_transitions as BOSS
            BOSS.start_round(self, c)
            FX.fire_event(self, c, {"event": "round_start"})

    def end_round(self):
        """Commit round effects and shared elapsed time together, once."""
        import state_grants as GRANTS
        if __import__('focus_punch').pending(self):return __import__('focus_punch').end_round(self)
        if __import__('marksman').pending(self):return __import__('marksman').end_round(self)
        return GRANTS.transition(self, None, lambda staged, _: staged._end_round())

    def _end_round(self):
        """Explicitly complete a shared ten-second round, once."""
        import mapless_space as MAPLESS
        MAPLESS.ensure_clear(self)
        PASSIVE_EVENTS.ensure_clear(self)
        LEAGUE.check_boundary(self, 'end_round')
        HEAVY.ensure_clear(self)
        if self._active_turn_actor is not None:
            raise ValueError('cannot complete round while a turn is open')
        if self.round_start_seconds is None:
            raise ValueError('no open round to complete')
        import initiative_schedule as SCHEDULE
        SCHEDULE.preflight_end_round(self)
        focus_result=__import__('focus_punch').finish_round(self)
        if isinstance(focus_result,CHECKS.PendingDecision):return focus_result
        marksman_result=__import__('marksman').finish_round(self)
        if isinstance(marksman_result,CHECKS.PendingDecision):return marksman_result
        import conditional_damage_base as CONDITIONAL_DB
        CONDITIONAL_DB.finish_round(self)
        import environmental_effects as ENVIRONMENT
        for actor in self.time_actors():
            ENVIRONMENT.preflight_advance(self,actor,10-(self.elapsed_seconds-self.round_start_seconds))
        CAPABILITIES.finish_round(self)
        import body_modes as BODY_MODES
        BODY_MODES.finish_round(self)
        import movement_actions as MOVEMENT
        MOVEMENT.finish_round(self)
        import combat_timing as TIMING
        TIMING.finish_round(self)
        import duelist as DUELIST
        DUELIST.round_end(self)
        import optional_state_effect_contracts as OPTIONAL_STATE
        OPTIONAL_STATE.finish_round(self)
        import persistent_conditions as PERSISTENT
        PERSISTENT.finish_round(self)
        self.advance_time(10 - (self.elapsed_seconds - self.round_start_seconds))
        SCHEDULE.round_ended(self)
        self.round_start_seconds = None

    def at_round_offset(self, seconds):
        """Record an externally supplied within-round timestamp; not inferred from initiative."""
        CHECKS.integer(seconds, 'round offset', 0)
        if self.round_start_seconds is None or seconds > 10:
            raise ValueError('round offset requires an open round and offset <= 10')
        delta = self.round_start_seconds + seconds - self.elapsed_seconds
        if delta < 0:
            raise ValueError('round offset cannot go backwards')
        self.advance_time(delta)

    # ---------- GM 재정(개변) API ----------
    def rule_formula(self, name, expr, reason="", scope="campaign"):
        e = self.rulings.set_formula(name, expr, reason, scope)
        self.log(f"[GM 개변] 공식 {name}: {e['before'] or '(룰북)'} → {expr} ({reason})", "gm/formula")

    def rule_mech(self, uid, path, value, reason="", scope="campaign"):
        e = self.rulings.set_mech(uid, path, value, reason, scope, self.r)
        self.log(f"[GM 개변] {uid}.{path}: {e['before']} → {value} ({reason})", "gm/mech")

    def rule_effect(self, move_id, op, effect=None, match=None, reason="", scope="campaign"):
        self.rulings.patch_effect(move_id, op, effect, match, reason, scope)
        self.log(f"[GM 개변] {move_id} effect {op} {match or ''} {effect or ''} ({reason})", "gm/effect")

    def rule_situational(self, modifier, value, who=None, uses=1, reason="", scope="scene"):
        self.rulings.add_situational(modifier, value, who, uses, reason, scope)
        self.log(f"[GM 개변] 상황 수정치 {modifier} {value:+} {who or '전원'} ({'장면' if uses == 'scene' else str(uses) + '회'}) ({reason})", "gm/situational")

    def rule_answer(self, key, answer, reason="", scope="scene"):
        self.rulings.add_answer(key, answer, reason, scope)
        self.log(f"[GM 개변] 프롬프트 답 등록 {key} → {answer} ({reason})", "gm/answer")

    def rule_hook(self, when, fn, reason="", scope="scene"):
        self.rulings.add_hook(when, fn, reason, scope)
        self.log(f"[GM 개변] 훅 {when} 등록 ({reason})", "gm/hook")

    def end_encounter(self, combatants=None, *, round_elapsed_seconds=None):
        """Apply the complete boundary through the shared state transaction."""
        __import__('movement_actions').ensure_commands_boundary(self)
        import state_grants as GRANTS
        unspecified = combatants is None
        actors = () if unspecified else tuple(combatants)
        def apply(staged, primary, *participants):
            return staged._end_encounter(None if unspecified else participants, round_elapsed_seconds=round_elapsed_seconds)
        return GRANTS.transition(self, None, apply, participants=actors, include_rulings=True, include_grid=self.grid is not None)

    def _end_encounter(self, combatants=None, *, round_elapsed_seconds=None):
        """End combat without resetting scene AP or frequency.
        Missing final-round duration remains unknown and cannot prove timer expiry.
        """
        import mapless_space as MAPLESS
        MAPLESS.ensure_clear(self)
        PASSIVE_EVENTS.ensure_clear(self)
        EFFECT_CONTRACTS.ensure_clear(self)
        LEAGUE.check_boundary(self, 'end_encounter')
        import maneuver_grants as MG
        MG.ensure_clear(self)
        HEAVY.ensure_clear(self)
        import special_entities as SPECIAL
        sentry_plan = SPECIAL.preflight_sentries(self)
        import initiative_interrupts as INTERRUPTS
        INTERRUPTS.require_clear(self)
        import homebrew_state as HOME
        HOME.preflight(self)
        import combat_state_lifecycle as COMBAT_STATE
        actors = COMBAT_STATE.members(self,() if combatants is None else combatants)
        import blessing_effects as BLESSINGS
        BLESSINGS.checked(self)
        self.time_actors(actors)
        import combat_stage_sources as STAGE_SOURCES
        import food_effects as FOOD
        for c in actors:COMBAT_STATE.preflight(c)
        for c in actors:__import__('native_path_area_moves').end_fairy_source(self,c)
        import declarative_move_contracts as DECLARATIVE_MOVES
        DECLARATIVE_MOVES.end_encounter(self,actors)
        import bide as BIDE
        for actor in actors:BIDE.clear(self,actor)
        if round_elapsed_seconds is not None:
            self.at_round_offset(round_elapsed_seconds)
        elif self.round_start_seconds is not None and self.elapsed_seconds - self.round_start_seconds < 10:
            self.unresolved_time_intervals.append({'round': self.round_no,
                'known_seconds': self.elapsed_seconds - self.round_start_seconds,
                'reason': 'partial_round_elapsed_unresolved'})
            import state_grants as G
            G.sync_capability_losses(self)
            for c in self.time_actors():
                TEMP_HP.unknown_interval(c, 10 - (self.elapsed_seconds - self.round_start_seconds),
                                         outside_combat=not any(member is c for member in actors))
                if c.faint_recovery_seconds is not None and not c.faint_recovery_pending:
                    c.faint_recovery_pending = 'partial_round_elapsed_unresolved'
        __import__('commander_orders').end_encounter(self,actors)
        CPF.end_encounter(self,actors)
        import class_passive_combat as CLASS_PASSIVE
        CLASS_PASSIVE.end_encounter(self,actors)
        import optional_state_effect_contracts as OPTIONAL_STATE
        OPTIONAL_STATE.end_encounter(self,actors)
        import roll_effects as ROLLS
        ROLLS.end_encounter(self)
        import captured_momentum as MOMENTUM
        MOMENTUM.end_encounter(self)
        BLESSINGS.end_encounter(self)
        import gmax_moves as GMAX
        GMAX.end_encounter(self,actors)
        __import__('fashionista').end_encounter(self,actors)
        __import__('telekinetic').end_encounter(self)
        import duelist as DUELIST
        DUELIST.end_encounter(self,actors)
        import setup_move_state as SETUP_MOVE
        SETUP_MOVE.end_encounter(self,actors)
        import hazard_state as HAZARDS
        HAZARDS.end_encounter(self,actors)
        EFFECT_LIFETIMES.end_encounter(self,actors)
        import pickup_item_copy as PICKUP_COPY
        PICKUP_COPY.end_encounter(self,actors)
        import smoke_regions as SMOKE_REGIONS
        SMOKE_REGIONS.clear(self)
        import homebrew_weather as HOME_WEATHER
        HOME_WEATHER.end_encounter(self)
        self.round_start_seconds = None
        for c in actors:
            COMBAT_STATE.cure_volatile(self,c,encounter_end=True)
            changed = any(v for v in c.stages.values()) or c.accuracy_stage != getattr(c, "_passive_acc", 0) or c.evasion_mod != getattr(c, "_passive_eva", 0)
            COMBAT_STATE.reset_actor(self,c)
            c.turns_taken=0
            FOOD.end_encounter(c)
            import restorative_items as RESTORATIVE
            RESTORATIVE.end_encounter(self,c)
            c.pending_action_loss = None
            import action_resources as RESOURCES
            c.spec.pop(RESOURCES.TURN_LOCK,None)
            import exhaust_moves as EXHAUST
            EXHAUST.end_encounter(c)
            if changed:
                self.log(f"  [전투 종료] {c.name} 전투단계·명중·회피 초기화", "combat/combat-stages")

        self._active_turn_actor = None
        self._action_grants.clear()
        import initiative_schedule as SCHEDULE
        SCHEDULE.end_encounter(self)
        was_active=self.encounter_active
        import encounter_settlement as SETTLEMENT
        SETTLEMENT.close_encounter(self,actors)
        self.encounter_active=False
        import party_actions as PARTY_ACTIONS
        PARTY_ACTIONS.end_gym(self)
        self._encounter_actors = None
        import ability_state_projection as ABILITY_STATE_PROJECTION
        for c in actors:ABILITY_STATE_PROJECTION.after_hp_change(self,c)
        import environmental_item_state as ENVIRONMENTAL_ITEMS
        ENVIRONMENTAL_ITEMS.boundary(self,encounter_end=True)
        if was_active:
            import condition_recovery as RECOVERY
            for c in actors:RECOVERY.end_combat(self,c)
        SPECIAL.expire_sentries(self, prepared=sentry_plan, encounter_end=True)
        import precise_actions as PRECISE
        PRECISE.clear(self)
        if self.pending_session_id is not None:
            self._apply_session_boundary(self.pending_session_id,self.time_actors())

    def configure_scene_lighting(self, *, darkness, reason):
        import scene_lighting as LIGHT
        return LIGHT.configure(self,darkness=darkness,reason=reason)

    def observe_scene_light(self, source_id, **observation):
        import scene_lighting as LIGHT
        return LIGHT.observe(self,source_id,**observation)

    def remove_scene_light(self, source_id, *, reason):
        import scene_lighting as LIGHT
        return LIGHT.remove(self,source_id,reason=reason)

    def observe_glow_reactions(self, source_id, **observation):
        import scene_lighting as LIGHT
        return LIGHT.observe_glow_reactions(self,source_id,**observation)

    def glow_response(self, source_id, target, **observation):
        import scene_lighting as LIGHT
        return LIGHT.glow_response(self,source_id,target,**observation)

    def respond_to_glow(self, source_id, target, **declaration):
        import scene_lighting as LIGHT
        return LIGHT.respond_to_glow(self,source_id,target,**declaration)

    def scene_light_projection(self, actor, target):
        import scene_lighting as LIGHT
        return LIGHT.projection(self,actor,target)

    def end_scene(self, combatants=None, *, round_elapsed_seconds=None):
        """Apply the complete boundary through the shared state transaction."""
        __import__('movement_actions').ensure_commands_boundary(self)
        import state_grants as GRANTS
        unspecified = combatants is None
        actors = () if unspecified else tuple(combatants)
        def apply(staged, primary, *participants):
            return staged._end_scene(None if unspecified else participants, round_elapsed_seconds=round_elapsed_seconds)
        return GRANTS.transition(self, None, apply, participants=actors, include_rulings=True, include_grid=self.grid is not None)

    def _end_scene(self, combatants=None, *, round_elapsed_seconds=None):
        """Narrative scene boundary; an open encounter ends too, but adds no guessed time."""
        import mapless_space as MAPLESS
        MAPLESS.ensure_clear(self)
        PASSIVE_EVENTS.ensure_clear(self)
        EFFECT_CONTRACTS.ensure_clear(self)
        HEAVY.ensure_clear(self)
        supplied = () if combatants is None else list({id(c): c for c in combatants}.values())
        scene_actors = AP.validate_scene(self, supplied)
        import field_effects as FIELD
        FIELD.local_scene_end(self)
        import mega_forms as MEGA
        MEGA.prepare_scene(self)
        actors = scene_actors if combatants is None else supplied
        for c in actors:FREQ.validate(c)
        self.time_actors(actors)
        self.end_encounter(actors, round_elapsed_seconds=round_elapsed_seconds)
        import homebrew_state as HOME
        HOME.end_scene(self)
        import class_passive_combat as CLASS_PASSIVE
        CLASS_PASSIVE.end_scene(self,actors)
        __import__('defense_curl').boundary(self,actors,'scene_end')
        import scene_feature_ability_grants as SCENE
        SCENE.end_scene(self,scene_actors)
        for c in scene_actors:__import__('telepath').end_capability(self,c)
        import declarative_move_contracts as DECLARATIVE_MOVES
        DECLARATIVE_MOVES.end_scene(self,actors)
        import linked_move_conditions as LINKED
        LINKED.end_scene(self,actors)
        import ability_state_projection as ABILITY_STATE_PROJECTION
        ABILITY_STATE_PROJECTION.end_scene(self,actors)
        for c in actors:
            c.counters = {k: v for k, v in c.counters.items() if not str(k).startswith(("lim:", "ab:"))}
            import condition_recovery as RECOVERY
            RECOVERY.prepare_scene(c)
            FREQ.end_scene(self, c)
        MEGA.end_scene(self)
        AP.finish_scene(self, actors)
        self.rulings.end_scene(self)
        AP_ROLL.end_scene(self)
        import combat_timing as TIMING
        TIMING.end_scene(self)
        import condition_recovery as RECOVERY
        for c in actors:RECOVERY.end_scene(self,c)
        import scene_lighting as LIGHT
        LIGHT.end_scene(self)
        import mapless_space as MAPLESS
        MAPLESS.end_scene(self)

    def choose_tumbler_acrobatics(self, actor, *, activate, reason):
        return __import__("tumbler").choose_acrobatics(self,actor,activate=activate,reason=reason)

    def declare_jump_move(self, actor, target, move_id, **options):
        return __import__("jump_move_actions").declare(self,actor,target,move_id,**options)

    def resume_tumbler_shift(self, actor):
        return __import__('tumbler').resume_shift(self,actor)

    def resume_jump_move(self, actor, *, event_id):
        return __import__("move_defense_reactions").resume_native_child(self,actor,event_id)

    def stand_up(self, actor):
        import condition_recovery as RECOVERY
        return RECOVERY.stand_up(self,actor)

    def wake_ally(self, actor, target, **options):
        import condition_recovery as RECOVERY
        return RECOVERY.wake_ally(self,actor,target,**options)

    def recover_condition(self, actor, condition, **options):
        import condition_recovery as RECOVERY
        return RECOVERY.recover(self,actor,condition,**options)

    def decide(self, prompt):
        """GM 프롬프트 → 재정 층의 답(스크립트/대화형). 답이 dict 이고 effects 를 담으면 실행한다."""
        ans = self.rulings.decide(prompt)
        if ans is None:
            return None
        self.log(f"    [GM 답] {prompt.get('type')}: {ans if not isinstance(ans, dict) else ans.get('note', '효과 실행')}", "gm/answer")
        if isinstance(ans, dict) and ans.get("effects") and prompt.get("attacker") is not None:
            FX.run_effects(self, prompt["attacker"], prompt.get("target") or prompt["attacker"], ans["effects"], {"attacker": prompt["attacker"], "target": prompt.get("target"), "hit": True, "nat": None, "engine": self}, "gm/answer")
        return ans

    def subscribe_source_policy(self, owner, subscription_id, document, *, event='move_resolved', inputs=None):
        return PASSIVE_EVENTS.subscribe_policy(self,owner,subscription_id,document,event=event,inputs=inputs)

    def deliver_passive_event(self, event_id):
        return PASSIVE_EVENTS.deliver(self, event_id)

    def choose_passive_event(self, event_id, owner, source_rule, choice):
        return PASSIVE_EVENTS.choose(self, event_id, owner, source_rule, choice)

    def formula(self, name, **vars):
        M.validate_source(self.r)
        return calc(self.r.formula(name), vars)

    def register_abilities(self, c):
        """Combatant.spec['abilities'] 의 특성 effect 를 패시브로 등록. 지니는 도구(spec['item'])와 트레이너 재주/엣지(spec['feats'/'edges'])도 여기서 꽂는다."""
        import vitamin_capacity as VITAMIN_CAPACITY
        VITAMIN_CAPACITY.register_current_owner(self,c)
        for name in list(c.abilities):
            self.register_abilities_one(c, name)
        import held_equipment as HELD
        for held in list(HELD.entries(c)):
            ITEMS.register_item(self,c,held['name'],source_instance_id=held.get('instance_id'),as_held=True,held_slot=held['slot_id'])
        import class_passive_combat as CLASS_PASSIVE
        if c.kind == "trainer" and (c.spec.get("classes") or c.spec.get("feats") or c.spec.get("edges")):
            acquired_feats = c.spec.get("feats", [])
            ordinary_feats = [name for name in acquired_feats if CLASS_PASSIVE.identity(name) is None]
            c.spec["feats"] = ordinary_feats
            try:
                ITEMS.register_feats(self, c)
            finally:
                c.spec["feats"] = acquired_feats
        if c.kind == "pokemon" and c.spec.get("trainer_id") is not None:
            import pokemon_party as POKEMON_PARTY
            POKEMON_PARTY.project_current_owner(self,c)
        else:
            CLASS_PASSIVE.register_all(self,c)
        c._passive_acc, c._passive_eva = c.accuracy_stage, c.evasion_mod
        FX.fire_event(self, c, {"event": "enter"})

    def register_abilities_one(self, c, name):
        import state_grants
        return state_grants.ensure_ability(self, c, name)

    def activate_scene_feature_ability(self, trainer, pokemon, source, branch, ability):
        import scene_feature_ability_grants as SCENE
        return SCENE.activate(self, trainer, pokemon, source, branch, ability)

    def issue_orders(self, actor, feature, target, **options):
        return __import__('commander').issue(self,actor,feature,target,**options)

    def fighters_versatility(self,actor,give_move,restore_move,*,edition='core'):
        PASSIVE_EVENTS.ensure_clear(self)
        LEAGUE.check_boundary(self,'fighters_versatility')
        return __import__('versatility').use(self,actor,give_move,restore_move,edition=edition)

    def command_versatility(self,actor,pokemon,give_move,restore_move,*,edition='core'):
        PASSIVE_EVENTS.ensure_clear(self)
        LEAGUE.check_boundary(self,'command_versatility')
        if pokemon is None:raise ValueError('actual Command Versatility Pokemon required')
        return __import__('versatility').use(self,actor,give_move,restore_move,pokemon=pokemon,edition=edition)

    def prepare_focused_command_ap(self,actor,lift,**options):
        PASSIVE_EVENTS.ensure_clear(self)
        LEAGUE.check_boundary(self,'prepare_focused_command_ap')
        return __import__('focused_command').plan_ap(self,actor,lift,**options)

    def focused_command(self,actor,pokemon,**options):
        PASSIVE_EVENTS.ensure_clear(self)
        LEAGUE.check_boundary(self,'focused_command')
        return __import__('focused_command').use(self,actor,pokemon,**options)

    def focused_command_with_voice(self,actor,pokemon,feature,**options):
        PASSIVE_EVENTS.ensure_clear(self)
        LEAGUE.check_boundary(self,'focused_command_with_voice')
        return __import__('commander').focused_voice(self,actor,pokemon,feature,**options)

    def use_general_order(self, actor, target, feature, **options):
        return __import__('commander_orders').use(self,actor,target,feature,**options)

    def brace_for_impact(self, actor):
        import state_grants as G
        return G.transition(self,actor,lambda e,c:__import__('commander_orders').brace(e,c,standard=True))

    def activate_class_passive(self, trainer, pokemon, source, *, communication=None):
        if source in __import__('commander_orders').FEATURES:
            return __import__('commander_orders').use(self,trainer,pokemon,source)
        import class_passive_combat as CLASS_PASSIVE
        import state_grants as GRANTS
        uid = CLASS_PASSIVE.identity(source)
        if uid not in CLASS_PASSIVE.STRATAGEMS:
            raise ValueError("reviewed class passive Stratagem required")
        return GRANTS.transition(
            self,
            trainer,
            lambda staged, staged_trainer, staged_pokemon: CLASS_PASSIVE.activate(
                staged, staged_trainer, staged_pokemon, uid, communication=communication
            ),
            participants=(pokemon,),
        )

    def release_class_passive(self, trainer, pokemon, source):
        import class_passive_combat as CLASS_PASSIVE
        import state_grants as GRANTS
        uid = CLASS_PASSIVE.identity(source)
        if uid not in CLASS_PASSIVE.STRATAGEMS|{CLASS_PASSIVE.STAT_STRATAGEM}:
            raise ValueError("reviewed class passive Stratagem required")
        return GRANTS.transition(
            self,
            trainer,
            lambda staged, staged_trainer, staged_pokemon: CLASS_PASSIVE.release(
                staged, staged_trainer, staged_pokemon, uid
            ),
            participants=(pokemon,),
        )

    def activate_blessed_resilience(self, actor, move_type):
        import class_passive_combat as CLASS_PASSIVE
        import state_grants as GRANTS
        return GRANTS.transition(
            self,
            actor,
            lambda staged, staged_actor: CLASS_PASSIVE.activate_blessed_resilience(
                staged, staged_actor, move_type
            ),
        )

    def validate_optional_state_effect_contracts(self):
        import optional_state_effect_contracts as OPTIONAL_STATE
        OPTIONAL_STATE.validate_global_conditions(self.r)
        return OPTIONAL_STATE.validate_world(self)

    def activate_optional_state_effect(self, actor, clause_id, *, target=None, targets=(), choice=None, communication=None):
        import optional_state_effect_contracts as OPTIONAL_STATE
        import state_grants as GRANTS
        participants = OPTIONAL_STATE.activation_participants(
            self, actor, clause_id, target=target, targets=targets
        )
        return GRANTS.transition(
            self, actor,
            lambda staged, staged_actor, *staged_targets: OPTIONAL_STATE.activate(
                staged, staged_actor, clause_id, staged_targets, choice=choice, communication=communication
            ),
            participants=participants,
        )

    def _register_abilities_one(self, c, name, *, selected_id=None):
        if selected_id is not None:
            import move_state
            registration = move_state.ability_registration(self.r, selected_id)
            if selected_id in __import__('hp_setting_moves').CAPS and registration and name == registration['name']:
                # This exact source was already chosen; do not re-resolve its
                # ambiguous display name against the separately held R492 row.
                requested = registration
            else:
                requested = move_state.ability_registration(self.r, name)
            if not registration or not requested or registration["name"] != requested["name"] or registration["source_id"] != selected_id:
                raise ValueError("explicit ability source requires reviewed exact source identity")
            name = registration["name"]
        if selected_id is None and name in self.r.unresolved_abilities:
            raise UnresolvedRuleSelection(name, self.r.unresolved_abilities[name])
        # An exact reviewed registration can share its display name with an
        # excluded conflicting row; its source identity was validated above.
        if selected_id is None and name in self.r.excluded_abilities:
            self.log(f"  {c.name} 특성 {name}: 룰셋 '{self.r.ruleset.name}' 에서 제외({self.r.excluded_abilities[name]}) → 무시", "ruleset/exclude")
            return
        if name in self.r.ability_alias:
            self.log(f"  [룰셋 {self.r.ruleset.name}] {c.name} 특성 {name} → {self.r.ability_alias[name]} (변형판 대체)", "ruleset/alias")
            name = self.r.ability_alias[name]
        if hasattr(self.r, "selection"):
            if selected_id is None:
                selected_id = self.r.selection.resolve_name(name, ("ability/",))
            selected_id = self.r._selected_rule(selected_id)
        if __import__('ability_control_contracts').register(self,c,selected_id or name):return
        if selected_id in (__import__('skirmisher').FLUTTER,__import__('skirmisher').VANGUARD):return
        import field_effects as FIELD
        if __import__('type_ace').ability_registration(self,c,selected_id):return
        if __import__('stall_ability').registration(self.r,selected_id):return
        if selected_id == FIELD.LOCAL_SOURCE:
            FIELD.local_policy(self.r)
            # Only the explicit local-field activation is implemented.
            # No passive remote-origin permission is granted by registration.
            return
        import base_stage_abilities as BASE_ABILITIES
        if BASE_ABILITIES.registration(self.r,selected_id or name):return
        import ability_transitions as ABILITY_TRANSITIONS
        if ABILITY_TRANSITIONS.native_passive(self.r,selected_id) or ABILITY_TRANSITIONS.registration_only(self.r,selected_id):return
        if __import__('endure').registration(self.r,selected_id or name):return
        if REACTIVE_ABILITIES.handled(self.r,selected_id):return
        import tera_shell as TERA_SHELL
        if TERA_SHELL.registration(self.r,selected_id):return
        import perish_body as PERISH_BODY
        if PERISH_BODY.registration(self.r,selected_id):return
        import capacity_abilities as CAPACITY_ABILITIES
        if CAPACITY_ABILITIES.registration(self.r,selected_id):return
        import ability_state_projection as ABILITY_STATE_PROJECTION
        if ABILITY_STATE_PROJECTION.register(self,c,selected_id):return
        import rage_abilities as RAGE_ABILITIES
        if RAGE_ABILITIES.registration(self.r,selected_id):return
        import stellar_tera_blast as STELLAR_TERA
        if STELLAR_TERA.registration(self.r,selected_id):return
        if PASSIVE_EVENTS.register(self, c, selected_id):
            return
        import typed_defensive_bypass as TYPED
        source_effects=TYPED.effects(self.r,selected_id) if TYPED.handles(selected_id) else self.r.ability_effects.get(name,[])
        source_frequency='항상' if TYPED.handles(selected_id) else self.r.ability_freq.get(name)
        effs = [dict(e, _ability=name, _frequency=source_frequency) if isinstance(e, dict) else e for e in source_effects]
        if selected_id is not None:
            effs = bind_rule_identity(effs, selected_id)
        FX.apply_passives(self, c, effs)
        EXT.register_ability_extras(self, c, effs)
        if effs:
            self.log(f"  {c.name} 특성 {name}: 패시브 {sum(1 for e in effs if e.get('type') in FX.PASSIVE_TYPES)}개 등록", f"ability/{name}")

    def choose_reactive_ability(self, actor, source, *, ability=None, reason):
        """Choose an optional consequence; actual Move producers supply trigger facts."""
        return REACTIVE_ABILITIES.choose(self,actor,source,ability=ability,reason=reason)

    def watch_ability_reaction(self,owner,source,*,reason):
        return ABILITY_REACTIONS.watch(self,owner,source,reason=reason)

    def pending_ability_reactions(self):
        return ABILITY_REACTIONS.pending(self)

    def choose_ability_reaction(self,event_id,owner,*,use,reason):
        return ABILITY_REACTIONS.choose(self,event_id,owner,use=use,reason=reason)

    def watch_ability_interrupt(self, owner, source, *, reason):
        return ABILITY_INTERRUPTS.watch(self,owner,source,reason=reason)

    def choose_ability_interrupt(self,event_id,owner,*,use,options=None,reason):
        return ABILITY_INTERRUPTS.choose(self,event_id,owner,use=use,options=options,reason=reason)

    def watch_move_defense(self, target, requests, *, reason):
        return DEFENSE.watch(self,target,requests,reason=reason)

    def adopt_unown_imbuement(self, actor, clusters, *, gm_id, reason):
        import unown_imbuement as UNOWN
        return UNOWN.adopt(self,actor,clusters,gm_id=gm_id,reason=reason)

    def use_unown_hidden_power(self, actor, target, targets, *, chosen_type, damage_class, request_id, reason):
        import unown_imbuement as UNOWN
        return UNOWN.use_hidden_power(self,actor,target,targets,chosen_type=chosen_type,
            damage_class=damage_class,request_id=request_id,reason=reason)

    def boost_unown_attack(self, actor, target, move_id, targets, *, request_id, reason):
        import unown_imbuement as UNOWN
        return UNOWN.boost_attack(self,actor,target,move_id,targets,request_id=request_id,reason=reason)

    def watch_unown_detect(self, actor, *, reason):
        import unown_imbuement as UNOWN
        return UNOWN.watch_detect(self,actor,reason=reason)

    def configure_ground_flight_option(self, declaration):
        """Record the GM's explicit adoption of the printed optional paragraph."""
        import newground_flight_option as GROUND_FLIGHT
        return GROUND_FLIGHT.configure(self, **declaration)

    def choose_move_defense(self, event_id, reactor, *, use, options=None, reason):
        return DEFENSE.choose(self,event_id,reactor,use=use,options=options,reason=reason)

    def configure_object_durability(self, actor, object_id, **facts):
        """Record explicit GM/source durability for an actual ordinary object."""
        import physical_object_attacks as OBJECTS
        return OBJECTS.configure(self,actor,object_id,**facts)

    def configure_rope(self, actor, object_id, **facts):
        import physical_materials as MATERIALS
        return MATERIALS.configure(self,actor,object_id,**facts)

    def rope_quote(self, rule_id, **facts):
        import physical_materials as MATERIALS
        return MATERIALS.quote(self,rule_id,**facts)

    def rope_capacity(self, object_id, **facts):
        import physical_materials as MATERIALS
        return MATERIALS.capacity(self,object_id,**facts)

    def attack_physical_object(self, actor, object_id, move_id, **adjudication):
        """Pay one actual Move against an object using an explicit GM adjudication."""
        import physical_object_attacks as OBJECTS
        return OBJECTS.attack(self,actor,object_id,move_id,**adjudication)

    def observe_object_combustion(self, actor, object_id, **facts):
        import physical_combustion as FIRE
        return FIRE.observe(self,actor,object_id,**facts)

    def ignite_physical_object(self, actor, object_id, move_id, **adjudication):
        import physical_combustion as FIRE
        return FIRE.attack(self,actor,object_id,move_id,**adjudication)

    def object_fire_state(self, object_id):
        import physical_combustion as FIRE
        return FIRE.current(self,object_id)

    def observe_fire_extinguished(self, actor, object_id, **facts):
        import physical_combustion as FIRE
        return FIRE.extinguish(self,actor,object_id,**facts)

    def observe_weapon_contact_surface(self, actor, instance_id, **facts):
        import physical_tool_attacks as TOOLS
        return TOOLS.observe(self,actor,instance_id,**facts)

    def attack_object_with_weapon(self, actor, object_id, instance_id, **adjudication):
        import physical_tool_attacks as TOOLS
        return TOOLS.attack(self,actor,object_id,instance_id,**adjudication)

    def conquerors_march(self,trainer,pokemon,*,event_id,edition=None):
        import conquerors_march as MARCH
        return MARCH.use(self,trainer,pokemon,event_id=event_id,edition=edition)

    def use_pass_move(self, attacker, move_id, destination, **adjudication):
        import pass_moves as PASS
        return PASS.use(self,attacker,move_id,destination,**adjudication)

    def equip_equipment(self, actor, instance_id, *, replace_selection=None, slot=None):
        import manual_equipment as MANUAL_EQUIPMENT
        PASSIVE_EVENTS.ensure_clear(self)
        LEAGUE.check_boundary(self, 'equip_equipment')
        return MANUAL_EQUIPMENT.equip(self, actor, instance_id, replace_selection=replace_selection, slot=slot)

    def give_equipment(self, giver, receiver, instance_id, *, replace_selection=None, held_slot=None):
        import manual_equipment as MANUAL_EQUIPMENT
        PASSIVE_EVENTS.ensure_clear(self)
        LEAGUE.check_boundary(self, 'give_equipment')
        return MANUAL_EQUIPMENT.give(self, giver, receiver, instance_id, replace_selection=replace_selection, held_slot=held_slot)

    def drop_held_equipment(self, actor, selection):
        import manual_equipment as MANUAL_EQUIPMENT
        PASSIVE_EVENTS.ensure_clear(self)
        LEAGUE.check_boundary(self, 'drop_held_equipment')
        return MANUAL_EQUIPMENT.drop_held(self, actor, selection)

    def use_item(self, user, item, target=None, free=False, accepted=True, *, duration_minutes=None, duration_reason=None, count=1, food_policy=None, selected_move=None, selected_stat=None, owner_consent_by=None, held_selection=None, container_selection=None, shell_batch_id=None, fixed_accuracy=None, resumable=False, request_id=None, aim=None, medicine_source_choice=None):
        """소모 아이템(약·음식·열매·영양제) 사용 → engine/items.py. 반환 (실행, 보류) 또는 None."""
        PASSIVE_EVENTS.ensure_clear(self)
        LEAGUE.check_boundary(self, 'use_item')
        return ITEMS.use_item(self, user, item, target, free, accepted=accepted, duration_minutes=duration_minutes, duration_reason=duration_reason, count=count, food_policy=food_policy, selected_move=selected_move, selected_stat=selected_stat, owner_consent_by=owner_consent_by, held_selection=held_selection, container_selection=container_selection, shell_batch_id=shell_batch_id, fixed_accuracy=fixed_accuracy,resumable=resumable,request_id=request_id,aim=aim,medicine_source_choice=medicine_source_choice)

    def appraise_mushroom(self, actor, *, instance_id, fixed=None, **check_options):
        import herb_mushroom_rules as HERB
        PASSIVE_EVENTS.ensure_clear(self)
        LEAGUE.check_boundary(self, 'appraise_mushroom')
        return HERB.appraise(self,actor,instance_id=instance_id,fixed=fixed,**check_options)

    def choose_ability_state(self, actor, source, choice, *, observation=None, reason):
        import world_entities as WORLD,ability_state_projection as PROJECTION
        WORLD.require_actors(self,actor)
        return PROJECTION.choose(self,actor,source,choice,observation=observation,reason=reason)

    def initialize_ability_state(self, actor, source, *, choice=None, parent_choices=(), reason):
        import world_entities as WORLD,ability_state_projection as PROJECTION
        WORLD.require_actors(self,actor)
        return PROJECTION.initialize(self,actor,source,choice=choice,parent_choices=parent_choices,reason=reason)

    @__import__("cheerleader").ability_action
    def activate_ability_state(self, actor, source, *, choice=None, observation=None, reason, seconds=None):
        import world_entities as WORLD,ability_state_projection as PROJECTION
        WORLD.require_actors(self,actor)
        PASSIVE_EVENTS.ensure_clear(self)
        EFFECT_CONTRACTS.ensure_clear(self)
        LEAGUE.check_boundary(self,'activate_ability_state')
        return PROJECTION.activate(self,actor,source,choice=choice,observation=observation,reason=reason,seconds=seconds)

    def pickup_source_choices(self, actor, target, *, held_selection=None, destination_slot=None):
        import pickup_item_copy as PICKUP_COPY
        return PICKUP_COPY.source_choices(self,actor,target,held_selection=held_selection,destination_slot=destination_slot)

    def pending_pickup_choices(self):
        import pickup_item_copy as PICKUP_COPY
        return PICKUP_COPY.pending(self)

    def resolve_pickup_choice(self, chooser, choice_id, *, selection, expiry_choice=None):
        import pickup_item_copy as PICKUP_COPY
        import csv_item_form_contracts as CSV_FORMS
        CSV_FORMS.require_independent(self,chooser)
        PASSIVE_EVENTS.ensure_clear(self)
        EFFECT_CONTRACTS.ensure_clear(self)
        LEAGUE.check_boundary(self,'activate_ability')
        return PICKUP_COPY.resolve_choice(self,chooser,choice_id,selection=selection,expiry_choice=expiry_choice)

    def cancel_pickup_choice(self, actor, choice_id):
        import pickup_item_copy as PICKUP_COPY
        return PICKUP_COPY.cancel_choice(self,actor,choice_id)

    @__import__("cheerleader").ability_action
    def activate_ability(self, actor, ability, target, *, held_selection=None, destination_slot=None, request_id=None, trigger_event_id=None, pickup_expiry_choice=None):
        """Activate a reviewed manual ability with its actual target and costs."""
        import csv_item_form_contracts as CSV_FORMS
        CSV_FORMS.require_independent(self,actor)
        if hasattr(target,'spec'):CSV_FORMS.require_independent(self,target)
        import manual_effects as MANUAL
        PASSIVE_EVENTS.ensure_clear(self)
        EFFECT_CONTRACTS.ensure_clear(self)
        LEAGUE.check_boundary(self,'activate_ability')
        if pickup_expiry_choice is not None and ability not in ('픽업','ability/픽업'):
            raise ValueError('Pickup expiry choice requires the actual copying Pickup source')
        if not __import__('ability_exchange_contracts').admit_trigger(self,actor,ability):
            raise ValueError('Neutralizing Gas prohibits this triggered ability')
        import hex_maniac as HEX_MANIAC
        if HEX_MANIAC.ability_registration(self.r,ability):return HEX_MANIAC.activate_ability(self,actor,ability,target,event_id=trigger_event_id)
        if trigger_event_id is not None:raise ValueError('hit trigger belongs only to its reviewed Ability')
        if ability in ('파닥파닥','Flutter',__import__('skirmisher').FLUTTER):return __import__('skirmisher').flutter(self,actor,target)
        import field_effects as FIELD
        if ability in (FIELD.LOCAL_SOURCE, '곰팡이군주'):
            return FIELD.activate_local_grass(self,actor,target,request_id=request_id)
        import ability_target_limits as TARGET_LIMITS
        if TARGET_LIMITS.registration(self.r,ability):return TARGET_LIMITS.activate(self,actor,ability,target)
        import ability_transitions as ABILITY_TRANSITIONS
        if ABILITY_TRANSITIONS.registration(self.r,ability):return ABILITY_TRANSITIONS.activate(self,actor,ability,target)
        import pickup_item_copy as PICKUP_COPY
        if PICKUP_COPY.registration(self.r,ability):
            return PICKUP_COPY.activate(self,actor,ability,target,held_selection=held_selection,destination_slot=destination_slot,expiry_choice=pickup_expiry_choice)
        return MANUAL.activate(self,actor,ability,target)

    def mega_evolve(self, trainer, pokemon, form_id, **options):
        import mega_forms as MEGA
        return MEGA.activate(self,trainer,pokemon,form_id,**options)

    def use_hex_maniac_move(self, actor, target, move_id, **options):
        return __import__('hex_maniac').use(self,actor,target,move_id,**options)

    def craft_ninja_tool(self, actor, item, **options):
        return __import__('ninja').craft(self,actor,item,**options)

    def divine(self,actor,mode,**options):return __import__('oracle').divination(self,actor,mode,**options)
    def use_sage(self,actor,target):return __import__('sage').cast(self,actor,target)
    def activate_telepath(self,actor):return __import__('telepath').activate(self,actor)
    def sustain_fortress(self,actor,**options):return __import__('fortress').sustain(self,actor,**options)
    def end_fortress(self,actor,instance_id):return __import__('fortress').end(self,actor,instance_id)
    def ready_fortress_shield(self,actor,instance_id,**options):return __import__('fortress').ready_shield(self,actor,instance_id,**options)
    def follow_fortress_ally(self,actor,ally,target,**options):return __import__('fortress').follow_shift(self,actor,ally,target,**options)
    def guardian_weapon_attack(self,actor,target,move_id,**options):return __import__('fortress').weapon_attack(self,actor,target,move_id,**options)
    def warper_teleport(self,actor,destination,**options):return __import__('warper').transfer(self,actor,destination,**options)
    def warper_ally_switch(self,actor,ally,**options):return __import__('warper').ally_switch(self,actor,ally,**options)
    def arm_warper_move(self,actor,move_id,**options):return __import__('warper').arm_move(self,actor,move_id,**options)
    def arm_probability_control(self,actor,target,**options):return __import__('warper').arm_probability(self,actor,target,**options)
    def resolve_native_pool(self,actor,**options):return __import__('roll_context').native_pool(self,actor,**options)
    def psychic_residue(self,observer,**options):return __import__('warper').discover_residue(self,observer,**options)

    def psionic_sight(self,observer,target):return __import__('psionic_sight').observe(self,observer,target)
    def reality_bender_event(self,actor,**options):return __import__('warper').reality_event(self,actor,**options)
    def reality_bender_item(self,actor,item_id,target=None,**options):return __import__('warper').reality_item(self,actor,item_id,target,**options)
    def thought_detection(self,actor):return __import__('telepath').detection(self,actor)
    def suggestion(self,actor,target,thought):return __import__('telepath').suggest(self,actor,target,thought)
    def release_suggestion(self,actor,instance_id):return __import__('telepath').release(self,actor,instance_id)
    def arm_telepath_reaction(self,actor,source,**options):return __import__('telepath').arm(self,actor,source,**options)
    def use_mind_reader(self,actor,target,**options):return __import__('telepath').cast_reader(self,actor,target,**options)
    def read_mind_reader_thoughts(self,actor,target):return __import__('telepath').read_information(self,actor,target)
    def activate_pk_combat(self,actor,**options):return __import__('telekinetic').activate_combat(self,actor,**options)
    def end_pk_combat(self,actor,**options):return __import__('state_grants').transition(self,actor,lambda e,a:__import__('telekinetic').end_combat(e,a,**options))
    def equip_telekinetic_weapon(self,actor,object_id,**options):return __import__('telekinetic').equip_weapon(self,actor,object_id,**options)
    def use_telekinetic_weapon(self,actor,target,move_id,weapon_id,*,use_spa=False,**options):return __import__('telekinetic').weapon_attack(self,actor,target,move_id,weapon_id,use_spa=use_spa,**options)
    def use_telekinetic_item(self,actor,object_id,target=None,**options):return __import__('telekinetic').use_item(self,actor,object_id,target,**options)
    def telekinetic_burst(self,actor,target,kind,**options):return __import__('telekinetic').burst(self,actor,target,kind,**options)
    def use_telekinetic_move(self,actor,target,move_id,**options):return __import__('telekinetic').cast(self,actor,target,move_id,**options)
    def escape_lifted(self,actor):return __import__('telekinetic').escape(self,actor)
    def telekinesis_evasion_policy(self,decision=None,**options):return __import__('telekinetic').evasion_policy(self,decision,**options)
    def divine_wind(self,actor,move_id):return __import__('sage').wind(self,actor,move_id)
    def record_divination(self,actor,mode,events,**options):return __import__('perception_observe').record_divination_fact(self,actor,mode,events,**options)
    def small_prophecy(self,actor):return __import__('oracle').small(self,actor)
    def choose_prophecy(self,owner,roller,**options):return __import__('oracle').choose_prophecy(self,owner,roller,**options)
    def mark_of_vision(self,owner,target,**options):return __import__('oracle').mark(self,owner,target,**options)
    def mark_access(self,target,owner,**options):return __import__('oracle').mark_access(self,target,owner,**options)
    def focus_mark(self,owner,target=None):return __import__('oracle').focus(self,owner,target)
    def read_mark(self,owner,target,**options):return __import__('oracle').read_mark(self,owner,target,**options)
    def dispel_illusions(self,actor):return __import__('oracle').dispel(self,actor)
    def watch_prescience(self,actor,*,reason):return ABILITY_INTERRUPTS.watch(self,actor,__import__('oracle').PRESCIENCE,reason=reason)
    def choose_prescience(self,event_id,actor,*,use,reason):return ABILITY_INTERRUPTS.choose(self,event_id,actor,use=use,reason=reason)
    def core_pickup(self,actor,**options):return __import__('oracle').pickup(self,actor,**options)
    def mark_illusion_appearance(self,actor,target,**options):return __import__('illusion_state').mark_appearance(self,actor,target,**options)
    def mimic_illusion_appearance(self,actor,target):return __import__('illusion_state').mimic_appearance(self,actor,target)
    def dismiss_illusion_appearance(self,actor):return __import__('illusion_state').dismiss_ability_illusion(self,actor)

    def use_poison_weapon(self, actor, target, move_id, **options):
        return __import__('ninja').weapon_attack(self,actor,target,move_id,**options)

    def use_genjutsu(self, actor, *, appearance=None, darkness=False):
        return __import__('illusion_state').genjutsu(self,actor,appearance=appearance,darkness=darkness)

    def interact_with_genjutsu(self, observer, target, skill, *, interaction, reason, **check_options):
        return __import__('illusion_state').interact_genjutsu(self,observer,target,skill,interaction=interaction,reason=reason,**check_options)

    def utility_drop_shift(self, actor, path, item, **options):
        return __import__('ninja').utility_shift(self,actor,path,item,**options)

    def activate_grand_hex(self, actor, target, event_id, recover_move):
        return __import__('hex_maniac').grand(self,actor,target,event_id,recover_move)

    @__import__("cheerleader").ability_action
    def activate_form_ability(self, actor, ability):
        """Activate a sourced form and its temporary move permissions."""
        import move_permissions
        return move_permissions.activate_form(self, actor, ability)

    def load_container(self, actor, **options):
        import item_containers as CONTAINERS
        PASSIVE_EVENTS.ensure_clear(self)
        LEAGUE.check_boundary(self, 'load_container')
        return CONTAINERS.load(self,actor,**options)

    def consume_food_buff(self, actor, **options):
        import food_effects as FOOD
        return FOOD.consume_buff(self,actor,**options)

    def observe_core_gluttony_quota(self, actor, *, used, reason):
        import food_effects as FOOD
        return FOOD.observe_core_gluttony_quota(self,actor,used=used,reason=reason)

    def adopt_bound_ap_modifier(self, c, instance_id, *, modifier, ending_method, source_ref):
        """Partial lifetime import, not feature activation or an AP refund."""
        PASSIVE_EVENTS.ensure_clear(self)
        import bound_ap
        return bound_ap.adopt(self, c, instance_id, modifier=modifier,
                              ending_method=ending_method, source_ref=source_ref)

    def release_bound_ap(self, c, instance_id, *, event_id):
        """Own-turn Free release of one explicitly adopted effect instance."""
        PASSIVE_EVENTS.ensure_clear(self)
        import bound_ap
        return bound_ap.release(self, c, instance_id, event_id=event_id)

    def confirm_blessing_gift(self, actor, gift, *, reason, configuration=None):
        import blessing_skill_features as BLESSINGS
        return BLESSINGS.confirm(self,actor,gift,reason=reason,configuration=configuration)

    def activate_blessing_skill_rule(self, actor, gift, *, reason):
        import blessing_skill_rules as BLESSING_SKILLS
        return BLESSING_SKILLS.activate(self,actor,gift,reason=reason)

    def tera_exit(self, actor):
        import csv_item_form_contracts as CSV_FORMS
        return CSV_FORMS.tera_exit(actor, engine=self)

    def identify_visible_blessing_crop(self, actor, item_name, *, visible, reason):
        import blessing_skill_rules as BLESSING_SKILLS
        return BLESSING_SKILLS.identify_visible_crop(
            self,actor,item_name,visible=visible,reason=reason)

    def confirm_twisted_form(self, actor, brander, *, appearance, contract, reason):
        import blessing_skill_features as BLESSINGS
        return BLESSINGS.confirm_twisted_form(self,actor,brander,appearance=appearance,contract=contract,reason=reason)

    def trainer_growth_stat_points(self, actor):
        import trainer_milestone_rewards as rewards
        return rewards.growth_points(self, actor)

    def allocate_trainer_growth_stats(self, actor, stats, *, request_id, reason):
        import trainer_milestone_rewards as rewards
        return rewards.allocate_growth(self, actor, stats, request_id=request_id, reason=reason)

    def trainer_milestone_rewards(self, actor):
        import trainer_milestone_rewards as rewards
        return rewards.pending(self, actor)

    def choose_trainer_milestone(self, actor, level, option, *, reason):
        import trainer_milestone_rewards as rewards
        return rewards.choose(self, actor, level, option, reason=reason)

    def allocate_trainer_milestone_stats(self, actor, level, stats, *, request_id, reason):
        import trainer_milestone_rewards as rewards
        return rewards.allocate(self, actor, level, stats, request_id=request_id, reason=reason)

    def pending_trainer_skill_rewards(self, actor):
        """Read restricted free Skill Edge rewards from observed growth."""
        import trainer_entitlements
        return trainer_entitlements.skill_rewards(self, actor)

    def pending_trainer_entitlements(self, actor):
        """Read unspent ordinary level rewards without granting chosen features."""
        import trainer_entitlements
        return trainer_entitlements.pending(self, actor)

    def pay_trainer_retraining(self, actor, kind, *, request_id, reason, refund_policy):
        import trainer_xp_payments as XP
        return XP.retraining(self,actor,kind,request_id=request_id,reason=reason,refund_policy=refund_policy)

    def refund_trainer_xp_payment(self, actor, payment_id, *, reason):
        import trainer_xp_payments as XP
        return XP.refund(self,actor,payment_id,reason=reason)

    def commit_trainer_xp_payment(self, actor, payment_id, *, event_id):
        import trainer_xp_payments as XP
        return XP.mark_used(self,actor,payment_id,event_id=event_id)

    def award_trainer_progression(self, actor, *, kind, request_id, reason, amount=None):
        """Record a trainer experience/milestone event without duplicate leveling."""
        import downtime
        return downtime.award_trainer_progression(self, actor, kind=kind,
            request_id=request_id, reason=reason, amount=amount)

    def complete_training_hour(self, trainer, targets, *, safe, reason, request_id):
        import training_sessions
        return training_sessions.complete(self,trainer,targets,safe=safe,reason=reason,request_id=request_id)

    def plan_training_eligibility(self, trainer, targets, declaration, **observations):
        import training_eligibility
        return training_eligibility.prepare(self,trainer,targets,declaration,**observations)

    def apply_training_rewards(self, trainer, targets, declaration, *, request_id=None, safe=None,
                               from_training=False, from_grooming=False, reason='observed completed training', pushed_skills=None):
        import training_rewards
        return training_rewards.execute(self,trainer,targets,declaration,request_id=request_id,safe=safe,
            from_training=from_training,from_grooming=from_grooming,reason=reason,pushed_skills=pushed_skills)

    def plan_egg_creation(self, owner, parents, declaration, **observations):
        import creation_egg
        return creation_egg.prepare(self,owner,parents,declaration,**observations)

    def observe_target(self, observer, target, declaration, **options):
        import perception_observe
        return perception_observe.observe(self,observer,target,declaration,**options)

    def tremorsense(self, observer, target, **options):
        import tremorsense
        return tremorsense.sense(self,observer,target,**options)

    def communicate(self, sender, recipient, declaration, text, **options):
        import perception_communicate
        return perception_communicate.send(self,sender,recipient,declaration,text,**options)

    def set_communication_consent(self, recipient, sender, source, allowed, *, reason):
        import perception_communicate
        return perception_communicate.permission(self,recipient,sender,source,allowed,reason=reason)

    def disconnect_communication(self, sender, recipient, source, *, reason):
        import perception_communicate
        return perception_communicate.disconnect(self,sender,recipient,source,reason=reason)

    def communication_messages(self, recipient, *, source=None):
        import perception_communicate
        return perception_communicate.received(self,recipient,source=source)

    def board_mount(self, rider, mount, declaration, **options):
        import control_mount
        return control_mount.board(self,rider,mount,declaration,**options)

    def retain_mount(self, rider, **options):
        import control_mount
        return control_mount.retain(self,rider,**options)

    def confusion_self_hit(self, subject, amount):
        import control_mount
        return control_mount.confusion_loss(self,subject,amount)

    def resume_confusion_completion(self, completion_id):
        """Finish only the pending consequence of an already returned attack."""
        import confusion_attacks
        return confusion_attacks.resume(self,completion_id)

    def dismount(self, rider, **options):
        import control_mount
        return control_mount.dismount(self,rider,**options)

    def release_equipment_transport(self, controller, body_id, **options):
        import equipped_transport_saddle as EQUIPMENT
        return EQUIPMENT.release(self,controller,body_id,**options)

    def machine_context(self, operator, machine_id, declaration, **observations):
        import control_vehicle
        return control_vehicle.describe_context(self,operator,machine_id,declaration,**observations)

    def connect_remote_control(self, operator, machine_id, declaration, binding, **observation):
        import control_remote
        return control_remote.connect(self,operator,machine_id,declaration,binding,**observation)

    def disconnect_remote_control(self, operator, route_id, *, reason):
        import control_remote
        return control_remote.disconnect(self,operator,route_id,reason=reason)

    def connect_wired_vehicle(self, pokemon, machine_id, electronics_id, **observation):
        import control_remote
        return control_remote.connect_wired_vehicle(self,pokemon,machine_id,electronics_id,**observation)

    def remote_control_routes(self, operator):
        import control_remote
        return control_remote.routes(self,operator)

    def enter_network(self, actor, network_id, declaration=None, **entry):
        import network_connection
        return network_connection.enter(self,actor,network_id,declaration,**entry)

    def exit_network(self, actor, avatar_id, **exit):
        import network_connection
        return network_connection.exit(self,actor,avatar_id,**exit)

    def digital_operation(self, actor, avatar_id, target_id, declaration, **operation):
        import network_integrity
        return network_integrity.execute(self,actor,avatar_id,target_id,declaration,**operation)

    def restore_object(self, actor, target_id, declaration, **operation):
        import repair_restore
        return repair_restore.execute(self,actor,target_id,declaration,**operation)

    def repair_vehicle(self, actor, target_id, *, cost, seconds, **operation):
        import repair_restore
        return self.restore_object(actor,target_id,repair_restore.vehicle_policy(cost,seconds),**operation)

    def observe_machine_recovery(self, actor, target_id, source, event, **observation):
        import repair_restore
        return repair_restore.observe_module_event(self,actor,target_id,source,event,**observation)

    def regenerate_machine(self, actor, target_id, *, component_id, event, **operation):
        import repair_restore
        return self.restore_object(actor,target_id,repair_restore.regeneration_policy(component_id,event),**operation)

    def damage_vehicle(self, actor, target_id, amount, declaration, **event):
        import repair_breach
        return repair_breach.damage(self,actor,target_id,amount,declaration,**event)

    def vehicle_exposure(self, target_id):
        import repair_breach
        return repair_breach.exposure(self,target_id)

    def repair_breaches(self, actor, target_id, *, count, seconds, subset, **operation):
        import repair_breach
        value=repair_breach.structural_policy(count,seconds,subset)
        if count>repair_breach._vehicle(self,target_id,usable=True)['breaches']:raise ValueError('actual available breaches cannot fund a larger structural repair')
        return self.restore_object(actor,target_id,value,**operation)

    def emergency_repair_vehicle(self, actor, target_id, *, source, **operation):
        import repair_breach
        return self.restore_object(actor,target_id,repair_breach.emergency_policy(source),**operation)

    def operate_machine(self, operator, machine_id, declaration, **command):
        import control_vehicle
        return control_vehicle.operate(self,operator,machine_id,declaration,**command)

    def create_declared_egg(self, owner, parents, declaration, **observations):
        import creation_egg
        return creation_egg.create(self,owner,parents,declaration,**observations)

    def hatch_declared_egg(self, owner, egg_entity_id, **observations):
        import creation_egg
        return creation_egg.hatch(self,owner,egg_entity_id,**observations)

    def plan_fossil_restoration(self, owner, fossil_entity_id, declaration, **observations):
        import creation_fossil
        return creation_fossil.prepare(self,owner,fossil_entity_id,declaration,**observations)

    def restore_declared_fossil(self, owner, fossil_entity_id, declaration, **observations):
        import creation_fossil
        return creation_fossil.restore(self,owner,fossil_entity_id,declaration,**observations)

    def hatch_restored_fossil(self, owner, egg_entity_id, **observations):
        import creation_fossil
        return creation_fossil.hatch(self,owner,egg_entity_id,**observations)

    def start_activity_job(self, owner, participants=(), **declaration):
        import activity_jobs as JOBS
        return JOBS.start(self,owner,participants,**declaration)

    def activity_job_status(self, job_id):
        import activity_jobs as JOBS
        return JOBS.status(self,job_id)

    def advance_activity_job(self, job_id, **interval):
        import activity_jobs as JOBS
        return JOBS.advance(self,job_id,**interval)

    def attempt_activity_job(self, job_id, actor, skill, **interval):
        import activity_jobs as JOBS
        return JOBS.attempt(self,job_id,actor,skill,**interval)

    def interrupt_activity_job(self, job_id, **observation):
        import activity_jobs as JOBS
        return JOBS.interrupt(self,job_id,**observation)

    def resume_activity_job(self, job_id, **observation):
        import activity_jobs as JOBS
        return JOBS.resume(self,job_id,**observation)

    def apply_activity_credit(self, owner, target, **application):
        import activity_jobs as JOBS
        return JOBS.apply_credit(self,owner,target,**application)

    def train_pokemon(self, trainer, choices, *, minutes, reason, request_id, from_grooming=False, from_training=False, safe=None,
                      trained_stats=None, source_clause_id=None):
        import training_features as TRAINING
        return TRAINING.train(self,trainer,choices,minutes=minutes,reason=reason,request_id=request_id,from_grooming=from_grooming,from_training=from_training,safe=safe,
                              trained_stats=trained_stats,source_clause_id=source_clause_id)

    def critical_moment(self,trainer,targets):
        return __import__('ace_trainer').critical_moment(self,trainer,targets)

    def arm_perseverance(self,trainer,pokemon,**choice):
        return __import__('ace_trainer').arm_perseverance(self,trainer,pokemon,**choice)

    def teach_signature_technique(self,trainer,pokemon,**choice):
        return __import__('ace_trainer').teach_technique(self,trainer,pokemon,**choice)

    def observe_z_crystal(self,instance_id,**facts):
        return __import__('z_moves').observe_crystal(self,instance_id,**facts)

    def arm_z_move(self,trainer,pokemon,**choice):
        PASSIVE_EVENTS.ensure_clear(self)
        return __import__('z_moves').arm(self,trainer,pokemon,**choice)

    def combine_z_rings(self,trainer,**choice):
        PASSIVE_EVENTS.ensure_clear(self)
        return __import__('z_moves').combine_rings(self,trainer,**choice)

    def reliable_attack_struggle(self,pokemon,target,completion_id):
        return __import__('ace_trainer').reliable_struggle(self,pokemon,target,completion_id)

    def burst_of_motivation(self,pokemon,completion_id,choices):
        return __import__('ace_trainer').motivation(self,pokemon,completion_id,choices)

    def choose_supreme_concentration(self,pokemon,**choice):
        return __import__('ace_trainer').choose_supreme(self,pokemon,**choice)

    def bloodied_speed(self,pokemon,target,move_id):
        return __import__('ace_trainer').priority_bloodied(self,pokemon,target,move_id)

    def release_pinpoint_strike(self, trainer, pokemon):
        return CPF.release(self,trainer,pokemon)

    def use_decisive_director(self, trainer, target, *, adjustment, communication=None):
        """Exact CSV91: choose an actual Pokemon and increase/decrease."""
        PASSIVE_EVENTS.ensure_clear(self)
        LEAGUE.check_boundary(self, 'use_decisive_director')
        import directive_features as DIRECTIVES
        return DIRECTIVES.activate(self, trainer, target, adjustment=adjustment, communication=communication)

    @__import__("cheerleader").native_action
    def manual_feat(self, c, name, target=None, *, adjustment=None, communication=None):
        PASSIVE_EVENTS.ensure_clear(self)
        LEAGUE.check_boundary(self, 'manual_feat')
        import versatility as VERSATILITY
        if name in (VERSATILITY.FIGHTER,'싸움꾼의 유능함','Fighter’s Versatility',"Fighter's Versatility",
                    VERSATILITY.COMMAND,'융통 명령','Command Versatility'):
            if type(adjustment)is not dict or set(adjustment)-{'give_move','restore_move','edition'} or not {'give_move','restore_move'}<=set(adjustment):
                raise ValueError('Versatility requires its actual two Move exchange selection')
            if name in (VERSATILITY.COMMAND,'융통 명령','Command Versatility'):
                return self.command_versatility(c,target,**adjustment)
            if target is not None and target is not c:raise ValueError('Fighter Versatility exchanges only its actual user Moves')
            return self.fighters_versatility(c,**adjustment)
        import focused_command as FOCUSED
        if name in (FOCUSED.FEATURE,'집중 명령','Focused Command'):
            if type(adjustment)is not dict or 'pokemon_ids' not in adjustment or set(adjustment)-{'pokemon_ids','edition'}:
                raise ValueError('Focused Command requires its actual commanded Pokemon identities')
            actual=dict(adjustment);ids=actual.pop('pokemon_ids');index=__import__('world_entities').actor_index(self)
            if type(ids)is not list or any(uid not in index for uid in ids):raise ValueError('two actual commanded Pokemon identities required')
            return self.focused_command(c,[index[uid] for uid in ids],target=target,**actual)
        if name in (FOCUSED.VOICE,'지휘관의 목소리','Commander’s Voice',"Commander's Voice"):
            raise ValueError('Commander Voice requires its actual native Order combination')
        if name in ('feat/기분전환','기분전환','Walk It Off'):
            if target is not None and target is not c:raise ValueError('Walk It Off affects only its actual user')
            return self.walk_it_off(c,**({} if adjustment is None else adjustment))
        import sage as SAGE
        name=next((uid for uid in SAGE.FEATURES if name in (uid,self.r.selection.units[uid].get('title'),self.r.selection.units[uid].get('eng'))),name)
        if name==SAGE.CLASS and adjustment is None:return self.use_sage(c,target)
        if name==SAGE.WIND:return self.divine_wind(c,adjustment)
        if name in SAGE.FEATURES:raise ValueError('Sage Feature requires its native trigger or acquisition')
        import oracle as ORACLE
        name=next((uid for uid in ORACLE.FEATURES if name in (uid,self.r.selection.units[uid].get('title'),self.r.selection.units[uid].get('eng'))),name)
        if name in ORACLE.FEATURES:
            options={} if adjustment is None else dict(adjustment)
            if name==ORACLE.DIVINATION:return self.divine(c,target=target,**options)
            if name==ORACLE.SMALL and not options:return self.small_prophecy(c)
            if name==ORACLE.MARK:return self.mark_of_vision(c,target,**options)
            if name==ORACLE.SIGHT and not options:return self.dispel_illusions(c)
            raise ValueError('Oracle requires its typed native action or actual hit choice')
        import channeler as CHANNEL
        name=next((uid for uid in CHANNEL.FEATURES if name in (uid,self.r.selection.units[uid].get('title'),self.r.selection.units[uid].get('eng'))),name)
        if name in CHANNEL.FEATURES:
            options={} if adjustment is None else dict(adjustment)
            if name==CHANNEL.CLASS:return self.channel_pokemon(c,target,**options)
            if name==CHANNEL.SENSES:
                if options:raise ValueError('Shared Senses has one actual target')
                return self.imprint_channel(c,target)
            if name==CHANNEL.SYNC:
                if options:raise ValueError('Battle Synchronization affects the actual Channeling group')
                return self.synchronize_channel(c)
            if name==CHANNEL.SPIRIT:
                donor=__import__('world_entities').actor_index(self).get(options.pop('donor_id',None))
                return self.boost_channel_spirit(c,target,donor,**options)
            if name==CHANNEL.CONDUIT:
                recipient=__import__('world_entities').actor_index(self).get(options.pop('recipient_id',None))
                return self.channel_power_conduit(c,target,recipient,**options)
            if name==CHANNEL.SOOTHE:return self.soothe_channel(c,**options)
            raise ValueError('Pain Dampening requires an actual damaging attack that would faint a Channeled Pokemon')
        if name in ('feat/복원력','복원력','Resilience'):
            raise ValueError('Resilience requires an actual native critical-hit or affliction trigger')
        import duelist as DUELIST
        name=next((uid for uid in (DUELIST.CLASS,DUELIST.EXPEND,DUELIST.MANUAL)
                   if name in (uid,self.r.selection.units[uid].get('title'),self.r.selection.units[uid].get('eng'))),name)
        if name==DUELIST.CLASS:
            if communication is not None:raise ValueError('Duelist tagging has no Order communication request')
            return DUELIST.tag(self,c,target)
        if name==DUELIST.EXPEND:return DUELIST.expend(self,c,target,communication=communication,**(adjustment or {}))
        if name==DUELIST.MANUAL:return DUELIST.manual(self,c,target,communication=communication,**(adjustment or {}))
        import taskmaster as TASK
        if name in (TASK.PRESS_ACTION,'압박','Press'):
            if communication is not None:raise ValueError('Press has no Order communication request')
            return TASK.press(self,c,target,**(adjustment or {}))
        if name in TASK.FEATURES:raise ValueError('Taskmaster Feature requires its actual trigger or typed Extended action')
        return ITEMS.manual_feat(self, c, name, target, adjustment=adjustment, communication=communication)

    def taskmaster_extended(self, owner, target, feature, *, seconds, reason, request_id, injuries=None):
        import taskmaster as TASK
        return TASK.extended(self,owner,target,feature,seconds=seconds,reason=reason,request_id=request_id,injuries=injuries)

    def pending_duelist_interrupts(self, trainer):
        import duelist as DUELIST
        return DUELIST.pending(self,trainer)

    def seize_the_moment(self, trainer, pokemon, **options):
        import duelist as DUELIST
        return DUELIST.seize(self,trainer,pokemon,**options)

    def decline_duelist_interrupt(self, trainer, pokemon, event_id):
        import duelist as DUELIST
        return DUELIST.decline(self,trainer,pokemon,event_id)

    def pending_class_actor_state_reactions(self, trainer):
        import class_actor_state_reactions as CLASS_REACTIONS
        return CLASS_REACTIONS.pending(self, trainer)

    def resolve_class_actor_state_reaction(self, trainer, event_id, *, use, stats=()):
        import class_actor_state_reactions as CLASS_REACTIONS
        return CLASS_REACTIONS.resolve(self, trainer, event_id, use=use, stats=stats)

    def pending_class_actor_state_actions(self, trainer):
        import class_actor_state_actions as CLASS_STATE_ACTIONS
        return CLASS_STATE_ACTIONS.pending(self, trainer)

    def resolve_class_actor_state_action(self, trainer, event_id, *, use):
        import class_actor_state_actions as CLASS_STATE_ACTIONS
        return CLASS_STATE_ACTIONS.resolve(self, trainer, event_id, use=use)

    def emergency_care_expertise(self, trainer, target):
        import class_actor_state_actions as CLASS_STATE_ACTIONS
        return CLASS_STATE_ACTIONS.emergency_care(self, trainer, target)

    def offer_top_percentage_at_max_level(self, trainer, pokemon):
        import class_actor_state_actions as CLASS_STATE_ACTIONS
        return CLASS_STATE_ACTIONS.offer_top_percentage_at_max_level(self, trainer, pokemon)

    def log(self, msg, rule=None):
        self.log_lines.append(msg + (f"  => [{rule}]" if rule else ""))

    # ---------- 주사위 ----------
    def roll_expr(self, expr, times=1, *, fixed=None, actor=None, purpose=None):
        """'2d6+8' → (합계, 눈 목록). 기존 times는 주사위와 고정 보너스를 모두 배수 적용한다."""
        result = POOLS.expression(self.rng, expr, dice_multiplier=times,
                                  flat_bonus_multiplier=times, fixed=fixed)
        if actor is not None:result=__import__('roll_context').observe_native(self,actor,purpose,result,lambda faces:POOLS.expression(self.rng,expr,dice_multiplier=times,flat_bonus_multiplier=times,fixed=faces))
        result=__import__('coordinator').capture_pool(self,result)
        return result['total'], result['faces']

    def d20(self):
        return POOLS.die(self.rng, 20)

    @__import__('roll_context').native_choices
    def roll_d20(self,actor,purpose,*,fixed=None):
        if fixed is not None:CHECKS.integer(fixed,'actual single d20 face',1,20)
        first=__import__('oracle').replace_d20(self,actor,self.d20() if fixed is None else fixed,purpose)
        return __import__('roll_context').observe_native(self,actor,purpose,first,lambda faces:POOLS.die(self.rng,20,fixed=None if faces is None else faces[0]))

    # ---------- 전투단계 / 상태 ----------
    def change_stage(self, c, stat, delta):
        import csv_item_food_contracts as CSV_FOOD
        if (type(delta) is int and delta > 0
                and not getattr(self, '_csv_food_stage_transaction', False)
                and CSV_FOOD.mirror_holders(self, exclude=c)):
            return CSV_FOOD.change_stage(self, c, stat, delta)
        return self._change_stage(c, stat, delta)

    def _change_stage(self, c, stat, delta):
        import combat_stage_sources as STAGE_SOURCES
        if stat not in STAGE_SOURCES.STATS:raise ValueError('only five non-HP combat stages may change')
        CHECKS.integer(delta,'combat stage delta')
        if delta<0 and __import__('type_ace').defense_locked(self,c,stat):return
        import ability_target_limits as TARGET_LIMITS
        if delta>0 and TARGET_LIMITS.blocked(self,c,'positive_stages'):
            self.log(f"    {c.name}: 긴장감으로 전투단계 상승 무효",TARGET_LIMITS.SOURCE)
            return
        import ability_transitions as ABILITY_TRANSITIONS
        if ABILITY_TRANSITIONS.active(c,"ability/단순"):delta*=2
        import restorative_items as RESTORATIVE
        if RESTORATIVE.blocks_stage_loss(self,c,delta):return
        if EXT.stage_hook(self, c, delta):
            return
        lo, hi = self.r.mech("combat/combat-stages")["range"]
        before = c.stages[stat]
        import combat_stage_sources as STAGE_SOURCES
        if not STAGE_SOURCES.change_combat(c,stat,delta):
            c.stages[stat] = max(lo, min(hi, before + delta))
        import stage_change_history as STAGE_HISTORY
        STAGE_HISTORY.record(self,c,stat,before,c.stages[stat],requested_delta=delta)
        self.log(f"    {c.name} {stat} 전투단계 {before:+d} → {c.stages[stat]:+d}", "combat/combat-stages")
        import csv_item_food_contracts as CSV_FOOD
        CSV_FOOD._stage_changed(self, c, stat, before, c.stages[stat])
        import csv_item_physical_contracts as CSV_ITEMS
        CSV_ITEMS.after_stage_change(self, c, stat, before, c.stages[stat])

    def immune_to(self, c, cond, *, cause=None):
        import field_effects as FIELD
        run_away=__import__("tumbler").run_away(c,cond)
        if run_away:return run_away
        field_immunity=FIELD.status_immunity(self,c,cond)
        if field_immunity:return field_immunity
        import capability_traits as TRAITS
        trait_immunity=TRAITS.immunity(c,cond,cause=cause)
        if trait_immunity:return trait_immunity
        import ability_transitions as ABILITY_TRANSITIONS
        if cond=="잠듦" and ABILITY_TRANSITIONS.active(c,"ability/불면") and not __import__('trickster').ignores_defensive(self,c,'ability/불면'):return "ability/불면"
        if cond=='실명' and __import__('keen_eye').active(self,c):return 'ability/날카로운눈'
        ability_immunity = FX.passive_status_immunity(self, c, cond)
        if ability_immunity:return ability_immunity
        if __import__('trickster').set_contains(self,c,'status_immune',cond):
            return "item/status_immunity"
        by_type = self.r.mech("combat/type-immunities")["by_type"]
        csv_trainer_paralysis=cond=='마비' and c.kind!='pokemon' and __import__('condition_instances').csv_edition(self.r,cond)
        if not csv_trainer_paralysis and any(cond in by_type.get(t, []) for t in c.types):
            return "combat/type-immunities"
        for e in self.r.condition_effects(cond):
            if e["type"] == "immunity" and e.get('actor_kind',c.kind)==c.kind and any(t in e["types"] for t in c.types):
                return f"condition/{cond}"
        return None

    @__import__('cheerleader').native_action
    def apply_status(self, c, cond, *, source=None, parameters=None, applied_by=None, force=False, _field_deferred=False):
        issuer=applied_by or getattr(self,'_inflictor',None)
        if __import__('glitch_bender').status_interested(self,c):
            import state_grants as GRANTS
            return GRANTS.transition(self,c,lambda e,q,*people:e._apply_status(q,cond,source=source,parameters=parameters,applied_by=people[0] if people else None,force=force,_field_deferred=_field_deferred),participants=() if issuer is None else (issuer,),include_rulings=True)
        if __import__('type_ace').status_interested(self,cond,issuer):
            import state_grants as GRANTS
            return GRANTS.transition(self,c,lambda e,q,a:e._apply_status(q,cond,source=source,parameters=parameters,applied_by=a,force=force,_field_deferred=_field_deferred),participants=(issuer,),include_rulings=True)
        return self._apply_status(c,cond,source=source,parameters=parameters,applied_by=applied_by,force=force,_field_deferred=_field_deferred)

    def _apply_status(self, c, cond, *, source=None, parameters=None, applied_by=None, force=False, _field_deferred=False):
        if type(force) is not bool:raise ValueError("explicit GM force flag required")
        if type(_field_deferred) is not bool:raise ValueError("explicit field deferral flag required")
        import capability_traits as TRAITS
        blindness_cause=TRAITS.blindness_cause(cond,parameters)
        badly_poisoned = cond == "맹독"
        cond = STATUS_NORM.get(cond, cond)
        source_condition = cond
        import optional_physical_equipment as OPTIONAL_EQUIPMENT
        if not force and OPTIONAL_EQUIPMENT.blocks_status(self, c, cond, source):
            self.log(f"    {c.name}은(는) 스발린으로 불꽃 공격의 화상에 면역", "crafted_item/스-발린")
            return False
        import boss_transitions as BOSS
        if not BOSS.preflight_condition(self, c, source_condition, parameters):
            return False
        cond = BOSS.condition_variant(c, source_condition)
        if source_condition=='잠듦':
            import dream_state as DREAM
            DREAM.validate(c)
        import status_sets as STATUS_SETS
        if not STATUS_SETS.can_apply(self,c,source_condition):return False
        import condition_instances as CONDITIONS
        import combat_timing as TIMING
        applied_by=applied_by or getattr(self,'_inflictor',None)
        import type_ace as TA
        if TA.lockdown(self,c,cond,source,applied_by):return True
        if TA.status_immunity(self,c,cond):return False
        survival_immunity=None if force else __import__('survivalist_class').status_immune(self,c,source_condition,source)
        if survival_immunity:
            self.log(f"    {c.name}은(는) {cond}에 면역 (지형 재능)",survival_immunity)
            return False
        import condition_variants as CONDITION_VARIANTS
        poison_variant=CONDITION_VARIANTS.prepare_infliction(self,c,source_condition,source,applied_by)
        if not force and not _field_deferred:
            if cond in CONDITIONS.SUPPORTED:
                CONDITIONS.prepare(self,c,cond,parameters=parameters,applied_by=applied_by)
            import field_effects as FIELD
            deferred=FIELD.defer_status(self,c,source_condition,source=source,parameters=parameters,applied_by=applied_by)
            if deferred is not None:return deferred
        if cond=='조이기':
            import vortex_state as VORTEX
            VORTEX.escape_bonus(parameters)
        if cond=='저주' and applied_by is not None:
            import world_entities as WORLD
            WORLD.require_actors(self,applied_by)
        if cond=='저주' and not force:
            __import__('world_entities').require_actors(self,c)
            if __import__('study_books').cursed_immune(self,c):return False
        legacy_install=any(r.get('installing') and cond in r.get('statuses',[]) for r in TIMING.records(c))
        if cond in CONDITIONS.SUPPORTED and not legacy_install:
            def after_gain():
                BOSS.condition_applied(self,c,source_condition,cond,parameters,source)
                __import__('blessing_effects').status_received(self,c,cond,source=source,applied_by=applied_by)
            return CONDITIONS.grant(self,c,cond,source=source,parameters=parameters,applied_by=applied_by,force=force,after_gain=after_gain)
        EXT.before_apply_status(self,c,cond)
        if cond=="기절":return LIFE.faint(self,c)
        why = self.immune_to(c, source_condition, cause=blindness_cause)
        if why and not force:
            self.log(f"    {c.name}은(는) {cond}에 면역", why)
            return False
        if cond in c.conditions:
            if cond=='조이기':VORTEX.configure(c,parameters)
            self.log(f"    {c.name}은(는) 이미 {cond} 상태")
            return False
        import enduring_resilience as RESILIENCE
        if not force and RESILIENCE.prevent(self,c,condition=source_condition,source=source,attacker=applied_by):return False
        replacement=__import__('glitch_bender').replace_status(self,c,cond,source=source,parameters=parameters,applied_by=applied_by,force=force)
        if replacement is not None:return replacement
        import condition_recovery as RECOVERY
        RECOVERY.invalidate(c,cond)
        c.conditions.add(cond)
        if cond=='저주' and applied_by is not None:
            c.custom_conditions['curse_origin']=applied_by
        if source_condition=='잠듦' and cond=='잠듦':
            import dream_state as DREAM
            DREAM.applied(c,source)
        if poison_variant is not None:
            CONDITION_VARIANTS.grant(self,c,source=source,applied_by=applied_by,prepared=poison_variant)
        elif badly_poisoned:CONDITIONS.grant_bad_poison(self,c,source=source,applied_by=applied_by)
        TA.poison_applied(self,c,cond,source,applied_by)
        EXT.after_apply_status(self,c,cond)
        if cond=='조이기':VORTEX.configure(c,parameters)
        BOSS.condition_applied(self,c,source_condition,cond,parameters,source)
        self.log(f"    {c.name}은(는) {cond} 상태가 됨", f"condition/{cond}")
        if getattr(self, "_inflictor", None) is not None and self._inflictor is not c:
            FX.fire_event(self, self._inflictor, {"event": "on_inflict_status", "status": cond}, c)
        for e in CONDITION_VARIANTS.effects(self,c,cond):
            if e["type"] == "combat_stage" and e.get("while") == "afflicted":
                import combat_state_lifecycle as COMBAT_STATE
                COMBAT_STATE.apply_condition_stage(self,c,cond,e)
            if e["type"] == "apply_condition":
                c.conditions.add(e["condition"])
                self.log(f"    파생: {c.name} {e['condition']} ({e['rounds']}라운드)", f"condition/{cond}")
        import effect_lifetime_policy as EFFECT_TIME
        EFFECT_TIME.reconcile(self)
        __import__('blessing_effects').status_received(self,c,cond,source=source,applied_by=applied_by)
        return True

    def cure_status(self, c, cond):
        cond = STATUS_NORM.get(cond,cond)
        if __import__("provocateur").retain_condition(c,cond):return False
        if __import__('csv_item_form_contracts').retain_condition(c,cond):return False
        import field_effects as FIELD
        deferred_cured=FIELD.cancel_deferred_status(self,c,cond)
        import boss_transitions as BOSS
        cond = BOSS.condition_variant(c,cond)
        if cond in ("기절","사망","임시 체력"):
            self.log(f"    {cond}: 일반 상태치료 대상이 아님", "condition/special")
            return False
        import gmax_moves as GMAX
        if GMAX.retain_condition(self,c,cond):
            self.log(f"    {c.name}: G-Max encounter Suppressed cannot be cured before encounter end",
                     "gmax/depletion")
            return False
        import fashionista as FASHIONISTA
        if FASHIONISTA.retain_condition(self,c,cond):
            self.log(f"    {c.name}: 시크 선택 도구 억압은 전투 종료까지 해소되지 않음",FASHIONISTA.WARDROBE)
            return False
        if cond in c.conditions:
            import combat_timing as TIMING
            if TIMING.retain_manual_status(c,cond):return False
            import condition_variants as CONDITION_VARIANTS
            if CONDITION_VARIANTS.retain_dependent(c,cond):return False
            condition_effects=CONDITION_VARIANTS.effects(self,c,cond)
            import condition_instances as CONDITIONS
            CONDITIONS.cure(self,c,cond)
            __import__("provocateur").cured(self,c,cond)
            EXT.before_cure_status(self,c,cond)
            c.conditions.discard(cond)
            if cond=='저주':c.custom_conditions.pop('curse_origin',None)
            if cond=='잠듦':
                import dream_state as DREAM
                DREAM.cured(c)
            import condition_recovery as RECOVERY
            RECOVERY.invalidate(c,cond)
            for e in condition_effects:
                if e["type"] == "combat_stage" and e.get("while") == "afflicted":
                    import combat_state_lifecycle as COMBAT_STATE
                    COMBAT_STATE.cure_condition_stage(self,c,cond,e)
            self.log(f"    {c.name}의 {cond} 치료됨", f"condition/{cond}")
            import status_sets as STATUS_SETS
            STATUS_SETS.on_cure(self,c,cond)
            BOSS.condition_cured(c,cond)
            import effect_lifetime_policy as EFFECT_TIME
            EFFECT_TIME.reconcile(self)
        return True if deferred_cured else None

    def tick(self, c):
        """소량의 체력 = 실제 최대 체력(부상 패널티 전)의 1/10 — '포켓몬의 최대 체력을 벗어난 모든 효과는 실제 최대값을 사용'(ch07 부상 데미지)."""
        return M.floor(self.formula("tick", max_hp=c.base_max_hp, level=c.level))

    def tick_loss(self,c,ticks=1):
        """Explicit Tick HP loss; healing and numerical percentages use tick()."""
        import common_checks as C,stat_ace as STAT
        C.integer(ticks,'actual Tick loss units',0)
        return STAT.tick_loss(self,c,self.tick(c))*ticks

    def lose_tick_hp(self,c,ticks=1,source='Tick loss'):
        return self.lose_hp(c,self.tick_loss(c,ticks),source=source)

    def start_of_turn(self, c, *, initiative_count=None):
        import ability_state_projection as PROJECTION
        import party_actions as PARTY_ACTIONS
        if __import__('type_ace').ghost_hidden(c):
            import state_grants as GRANTS
            def return_and_start(staged,actor):
                __import__('type_ace').return_from_ghost(staged,actor)
                return staged._start_of_turn(actor,initiative_count=initiative_count)
            return GRANTS.transition(self,c,return_and_start,include_rulings=True,include_grid=self.grid is not None)
        projection_turn=PROJECTION._owned(c,'ability/꼬르륵스위치')
        core_confused=__import__('confusion_attacks').interested(c) and __import__('confusion_attacks').core(self)
        csv_turn=any(condition in c.conditions and __import__('condition_instances').csv_edition(self.r,condition) for condition in ('풀죽음','헤롱헤롱'))
        if getattr(self,'_initiative_schedule',None) is not None or getattr(self,'_initiative_extra_turns',None) or projection_turn or core_confused or csv_turn or PARTY_ACTIONS.gym_profile(self) is not None or __import__('swarm_transitions').state(c) is not None or '마비' in c.conditions:
            import state_grants as GRANTS
            return GRANTS.transition(self,c,lambda staged,actor:staged._start_of_turn(actor,initiative_count=initiative_count),include_rulings=True,include_grid=projection_turn and self.grid is not None)
        return self._start_of_turn(c,initiative_count=initiative_count)

    def _start_of_turn(self, c, *, initiative_count=None):
        """마비 등: 턴 시작 내성 체크."""
        import partial_entities as PARTIAL
        PARTIAL.require_complete(c, "start_of_turn")
        import supplemental_state as SUPPLEMENTAL
        SUPPLEMENTAL.require_actor_access(self, c, "start_of_turn")
        import actor_templates as TEMPLATES
        TEMPLATES.require_ordinary(c, "start_of_turn")
        import swarm_transitions as SWARM
        if SWARM.continuation_pending(self,c):
            import combat_timing as TIMING
            TIMING.preflight_turn(self,initiative_count)
            ACTION.begin_turn(self,c,initiative_count=initiative_count)
            TIMING.at_count(self,initiative_count,_turn_start=True)
            self._initiative_cursor['available_for_turn']=False
            __import__('ability_native_actions').initiative_gained(self,c)
            return c._turn_action_limit
        PASSIVE_EVENTS.ensure_clear(self)
        LEAGUE.check_boundary(self, 'start_of_turn')
        HEAVY.ensure_clear(self)
        import movement_actions as MOVEMENT
        MOVEMENT.reset_preflight(c)
        import combat_social_edges as SOCIAL
        SOCIAL.validate(self,c)
        import enduring_awareness as AWARENESS
        AWARENESS.bonus(self,c)
        import combat_timing as TIMING
        TIMING.preflight_turn(self,initiative_count)
        import paralysis_state as PARALYSIS
        if not __import__('condition_instances').csv_edition(self.r,'마비'):PARALYSIS.preflight_turn(self,c,initiative_count)
        import coat_effects as COATS
        COATS.validate_actor(c)
        import initiative_schedule as SCHEDULE
        SCHEDULE.select_mounted_turn(self,c)
        ACTION.begin_turn(self, c, initiative_count=initiative_count)
        TIMING.begin_turn(self,c,initiative_count)
        import setup_move_state as SETUP_MOVE
        SETUP_MOVE.start_turn(self,c)
        __import__('type_ace').start_turn(self,c)
        __import__('type_ace').fire_boundary(self,c)
        __import__('chronicler').start_turn(self,c)
        import optional_state_effect_contracts as OPTIONAL_STATE
        OPTIONAL_STATE.start_turn(self,c)
        FREQ.start_turn(c)
        TURN.reset_budget(self, c)
        __import__('coordinator').start_turn(self,c)
        import ability_state_projection as ABILITY_STATE_PROJECTION
        ABILITY_STATE_PROJECTION.start_turn(self,c)
        import gmax_moves as GMAX
        GMAX.start_turn(self,c)
        import swarm_transitions as SWARM
        SWARM.start_turn(self, c, initiative_count=initiative_count)
        import boss_transitions as BOSS
        import initiative_interrupts as INTERRUPTS
        INTERRUPTS.after_budget_reset(self,c)
        FX.fire_event(self, c, {"event": "turn_start"})
        EXT.start_of_turn(self, c)
        import field_effects as FIELD
        FIELD.turn_start(self,c)
        import food_effects as FOOD
        FOOD.turn_start(self,c)
        TURN.weather_turn_start(self, c)
        __import__('condition_instances').start_turn(self,c)
        limit = None
        for cond in sorted(c.conditions):
            if not BOSS.condition_applies_this_turn(c,cond):
                continue
            for e in self.r.condition_effects(cond):
                if e["type"] == "save" and e["timing"] == "start_of_turn":
                    import declarative_move_contracts as DECLARATIVE_MOVES
                    if cond == "잠듦" and DECLARATIVE_MOVES.blocks_sleep_save(c):
                        self.log(f"    {c.name}: 잠자기 효과 동안 잠듦 시작 내성 불가", "move/잠자기")
                        continue
                    import combat_maneuvers as MANEUVERS
                    save_disposition=MANEUVERS.save_disposition(c,cond)
                    if save_disposition:
                        outcome_text="내성 불가" if save_disposition=="forbidden" else "내성 자동 실패"
                        self.log(f"    {c.name}: 술수 효과 동안 {cond} {outcome_text}", "maneuver/술수")
                        continue
                    import condition_recovery as RECOVERY
                    check=RECOVERY.saving_check(self,c,cond,e["dc"])
                    ok=check['passed']
                    if ok and e.get("on_success") == "cure":
                        self.cure_status(c, cond)
                    elif not ok:
                        if cond == "마비" and not __import__('condition_instances').csv_edition(self.r,cond):
                            PARALYSIS.failed_save(self,c,check)
                        limit = next((x for x in self.r.condition_effects(cond) if x["type"] == "action_limit"), None)
        c._turn_action_limit = limit
        SWARM.finish_turn_start(self, c)
        c._turn_start_decisions_pending = False
        __import__('confusion_attacks').start_turn(self,c)
        __import__('versatility').begin_turn(self,c)
        __import__('ability_native_actions').initiative_gained(self,c)
        return c._turn_action_limit

    def end_of_turn(self, c, *, swarm_continue=True, fortress_mark=None):
        import state_grants as GRANTS
        return GRANTS.transition(self,c,
            lambda staged,actor:staged._end_of_turn(actor,swarm_continue=swarm_continue,fortress_mark=fortress_mark),include_rulings=True)

    def _end_of_turn(self, c, *, swarm_continue=True, fortress_mark=None):
        PASSIVE_EVENTS.ensure_clear(self)
        LEAGUE.check_boundary(self, 'end_of_turn')
        HEAVY.ensure_clear(self)
        import field_effects as FIELD
        FIELD.preflight_end_turn(self, c)
        if type(swarm_continue) is not bool:
            raise ValueError('explicit swarm continuation choice required')
        import swarm_transitions as SWARM
        if SWARM.defer_action(self,c,continue_action=swarm_continue):
            if fortress_mark is not None:raise ValueError('Fortress Mark requires a real turn end, not a swarm continuation window')
            ACTION.check_end(self,c,continuation=True)
            ACTION.close_swarm_window(self,c)
            return {'status':'swarm_action_pending','initiative':SWARM.state(c)['swarm_turn']['next_initiative']}
        ACTION.check_end(self, c)
        if fortress_mark is not None:c.custom_conditions['fortress_end_turn_mark']=fortress_mark
        import combat_social_edges as SOCIAL
        SOCIAL.validate(self,c)
        import enduring_awareness as AWARENESS
        AWARENESS.bonus(self,c)
        unable_at_turn_end = ACTION.unable_standard(c,engine=self)
        asleep_at_turn_end = "잠듦" in c.conditions
        import rage_abilities as RAGE_ABILITIES
        import boss_transitions as BOSS
        import condition_variants as CONDITION_VARIANTS
        for cond in sorted(c.conditions):
            if cond not in c.conditions:continue
            if not BOSS.condition_applies_this_turn(c,cond):continue
            for e in CONDITION_VARIANTS.effects(self,c,cond):
                if cond not in c.conditions:break
                if e["type"] == "tick_damage" and e.get("when") == "end_of_turn":
                    if BOSS.defer_end_tick(c,cond,e):continue
                    need_std = e.get("if", "").startswith("took_standard_action")
                    unable_branch = e.get("if") == "took_standard_action_or_unable_to" and unable_at_turn_end
                    if need_std and not (c.took_standard or unable_branch):
                        continue
                    import persistent_conditions as PERSISTENT
                    amount = PERSISTENT.loss(self,c,cond,e["ticks"])
                    self.log(f"    {c.name} {cond}: 상태 효과로 {amount} HP 손실", f"condition/{cond}")
                    self.lose_hp(c, amount, source=cond)
                if e["type"] == "save" and e["timing"] == "end_of_turn":
                    import declarative_move_contracts as DECLARATIVE_MOVES
                    if cond == "잠듦" and DECLARATIVE_MOVES.blocks_sleep_save(c):
                        self.log(f"    {c.name}: 잠자기 효과 동안 잠듦 종료 내성 불가", "move/잠자기")
                        continue
                    if asleep_at_turn_end and cond in ("난동", "헤롱헤롱", "혼란"):
                        self.log(f"    {c.name}: 잠듦 중 {cond} 치료 내성은 허용되지 않음; 같은 종료시점의 깨어남 이후 순서는 미확정", "condition/잠듦")
                        continue
                    if RAGE_ABILITIES.end_save_forbidden(c, cond):
                        self.log(f"    {c.name}: 보유 특성으로 난동 종료 내성 불가", "ability/rage")
                        continue
                    import combat_maneuvers as MANEUVERS
                    save_disposition=MANEUVERS.save_disposition(c,cond)
                    if save_disposition:
                        outcome_text="내성 불가" if save_disposition=="forbidden" else "내성 자동 실패"
                        self.log(f"    {c.name}: 술수 효과 동안 {cond} {outcome_text}", "maneuver/술수")
                        continue
                    import condition_recovery as RECOVERY
                    check=RECOVERY.saving_check(self,c,cond,e["dc"])
                    if cond=='혼란':
                        import eldritch_magic as ELDRITCH
                        ELDRITCH.after_confusion_save(self,c,check)
                    ok=check['passed']
                    if ok and e.get("on_success") == "cure":
                        self.cure_status(c, cond)
        CONDITION_VARIANTS.end_turn(self,c)
        BOSS.end_turn(self,c)
        EXT.end_of_turn(self, c)
        before_effects=tuple(getattr(self,'_effect_dispatch_receipts',{}))
        FX.fire_event(self, c, {"event": "turn_end"})
        pending=ACTION.defer_turn_end(self,c,before_effects)
        if pending is not None:return pending
        return self._close_end_of_turn(c)

    def _close_end_of_turn(self, c):
        """Remaining native phase after the original event's effects settle."""
        import field_effects as FIELD
        FIELD.end_turn(self,c)
        import stat_ace as STAT
        STAT.end_turn(self,c)
        __import__('fortress').end_turn(self,c,c.custom_conditions.pop('fortress_end_turn_mark',None))
        c.took_standard = False
        ACTION.close_turn(self, c)
        import combat_timing as TIMING
        __import__('martial_artist').end_turn(self,c)
        TIMING.end_turn(self,c)
        __import__("tumbler").burst_offer(self,c)
        __import__('gmax_moves').end_turn(self,c)
        import setup_move_state as SETUP_MOVE
        SETUP_MOVE.end_turn(self,c)

    # ---------- 명중 ----------
    def pokemon_activity(self, actor, activity, **options):
        import pokemon_activities as POKEMON
        return POKEMON.perform(self, actor, activity, **options)

    def craft_recipe(self, actor, recipe, **options):
        import crafting_recipes as RECIPES
        return RECIPES.craft(self,actor,recipe,**options)

    def threaded(self, actor, target, **options):
        import threaded as THREADED
        return THREADED.use(self,actor,target,**options)

    def threaded_equal_weight_policy(self, actor, target, decision=None):
        import threaded as THREADED
        return THREADED.equal_weight_policy(self,actor,target,decision)

    def manipulate(self, actor, target, kind, **options):
        import combat_maneuvers as MANEUVERS
        return MANEUVERS.manipulate(self,actor,target,kind,**options)

    def trickster_maneuver(self, trainer, pokemon, target, trigger, kind, choice, **options):
        return __import__('trickster').maneuver(self,trainer,pokemon,target,trigger,kind,choice,**options)

    def stacked_deck(self, trainer, pokemon, target, completion, condition):
        return __import__('trickster').stacked_deck(self,trainer,pokemon,target,completion,condition)

    def flourish(self, trainer, pokemon, completion, choice, **options):
        return __import__('trickster').flourish(self,trainer,pokemon,completion,choice,**options)

    def encore_performance(self, trainer, pokemon, completion, choice, **options):
        return __import__('trickster').encore(self,trainer,pokemon,completion,choice,**options)

    def mind_games(self, trainer, pokemon, target, completion, **options):
        return __import__('trickster').mind_games(self,trainer,pokemon,target,completion,**options)

    def escape_artist(self, trainer, pokemon, target, move_id, destination, **options):
        return __import__('trickster').escape_artist(self,trainer,pokemon,target,move_id,destination,**options)

    def shell_game(self, trainer, pokemon, kind, destinations, **options):
        return __import__('trickster').shell_game(self,trainer,pokemon,kind,destinations,**options)

    def sleight(self, trainer, pokemon, **options):
        return __import__('trickster').sleight(self,trainer,pokemon,**options)

    def remove_net(self, actor, **options):
        import net_capsule as NET
        return NET.remove(self,actor,**options)

    def drag_object(self, actor, **options):
        return CAPABILITIES.drag_object(self,actor,**options)

    def carry_check(self, actor, **options):
        return CAPABILITIES.carry_check(self,actor,**options)

    def throw_small_object(self, actor, **options):
        return CAPABILITIES.throw_small_object(self,actor,**options)

    def boost_roll(self, payer, beneficiary, *, roll_id, kind):
        return AP_ROLL.prepare(self,payer,beneficiary,roll_id=roll_id,kind=kind)

    def plan_accuracy_context(self, attacker, target, move, *, situational=0, waive=False, roll_id=None):
        import roll_context as ROLL_CONTEXT
        return ROLL_CONTEXT.accuracy(self,attacker,target,move,situational=situational,waive=waive,roll_id=roll_id)

    def accuracy_check(self, attacker, target, move, situational=0, waive=False, fixed_roll=None, shared_roll=None, *, roll_id=None, reliable_trainer=None):
        import partial_entities as PARTIAL
        PARTIAL.require_complete(attacker, "accuracy_check attacker")
        PARTIAL.require_complete(target, "accuracy_check target")
        import captured_momentum as MOMENTUM
        MOMENTUM.ensure_clear(self)
        import move_accuracy as MOVE_ACCURACY
        import environ_moves as ENVIRON
        MOVE_ACCURACY.preflight(self,attacker,target,move,ENVIRON.read(self,move,attacker)[0],roll_id=roll_id,reliable_trainer=reliable_trainer)
        if reliable_trainer is None:
            return self._accuracy_check_native(attacker,target,move,situational,waive,fixed_roll,shared_roll,roll_id=roll_id)
        import contest_features as CF
        mm,_ = ENVIRON.read(self,move,attacker)
        CF.reliable_accuracy_preflight(self,reliable_trainer,attacker,move,mm,shared_accuracy=shared_roll,fixed_roll=fixed_roll)
        return CF.reliable_accuracy_check(self,reliable_trainer,attacker,
            lambda natural:self._accuracy_check_native(attacker,target,move,situational,waive,fixed_roll=natural,roll_id=roll_id))

    def _prepare_accuracy_context(self, attacker, target, move, situational=0, waive=False, fixed_roll=None, shared_roll=None, *, roll_id=None):
        import environ_moves as ENVIRON
        import body_modes as BODY_MODES
        import marsupial_state as MARSUPIAL
        import partial_entities as PARTIAL
        PARTIAL.require_complete(attacker, "_accuracy_check_native attacker")
        PARTIAL.require_complete(target, "_accuracy_check_native target")
        BODY_MODES.require_targetable(target,attack=MARSUPIAL.attack_blocked(attacker,target,move,engine=self),engine=self,attacker=attacker)
        M.validate_source(self.r)
        import weapon_actions as WEAPONS
        move = WEAPONS.prepare(self,attacker,move)
        import struggle_capabilities as STRUGGLE
        move = STRUGGLE.prepare(self,attacker,move)
        import pokemon_move_edges as POKE_MOVE_EDGES
        move = POKE_MOVE_EDGES.prepare(self,attacker,move)
        ac_rule = self.r.mech("combat/accuracy-roll")
        if fixed_roll is not None:CHECKS.integer(fixed_roll,'d20 face',1,20)
        EXT.validate_combat_edges(self,attacker)
        import event_effects as EVENTS
        EVENTS.validate_for_use(self,attacker,move=move)
        mm, conf = ENVIRON.read(self,move,attacker)
        bide_automatic = None
        if move.get('id') == 'move/참기' and '_retrospective_hp_loss' in move:
            # Accuracy re-reads retain the native phase's policy, not a recalculated damage amount.
            bide_automatic = __import__('bide').project(self,attacker,move,mm)[1]['never_miss']
            mm = dict(mm, never_miss=bide_automatic)
        import class_passive_combat as CLASS_PASSIVE
        CLASS_PASSIVE.preflight(self,attacker,target,move,mm)
        import move_accuracy as MOVE_ACCURACY
        if MOVE_ACCURACY.preflight(self,attacker,target,move,mm,roll_id=roll_id):
            CPF.preflight(self,attacker,target,move,mm)
            no_hit_reason=EXT.blocks_hit(self,attacker,target,move,mm)
            return {'move':move,'no_accuracy':True,'no_hit_reason':no_hit_reason}
        import invisibility_state as INVISIBILITY
        invisibility_penalty=INVISIBILITY.accuracy_penalty(self,target,observer=attacker)
        import vision_impairment as VISION
        VISION.accuracy_penalty(self,attacker,target)  # Validate mapped observations before RNG/cost consumers.
        import blender_state as BLENDER
        blender_evasion=BLENDER.evasion(self,target,move,attacker)
        import environment_derive as ED
        environment_evasion=ED.evasion(self,target,move,mm)
        import grapple_state as GRAPPLE
        grapple_penalty=GRAPPLE.accuracy_penalty(self,attacker,target)
        spatial_penalty=0 if waive else self.spatial_evasion_penalty(target)
        ap_bonus=AP_ROLL.bonus(self,attacker,roll_id,'accuracy')
        if shared_roll is not None and roll_id is not None:
            raise ValueError('identified shared accuracy needs a sourced multi-target AP policy')
        mm, conf = ENVIRON.read(self,move,attacker)
        if bide_automatic is not None:mm = dict(mm, never_miss=bide_automatic)
        no_hit_reason = EXT.blocks_hit(self,attacker,target,move,mm)
        import combat_social_edges as SOCIAL
        SOCIAL.preflight(self,attacker,target,move,mm)
        CPF.preflight(self,attacker,target,move,mm)
        zone_pen = min(self.zones.get(attacker.entity_id, 0), self.zones.get(target.entity_id, 0))
        if self.grid is not None:
            import body_state as BODY
            zone_pen = min((self.zone_cells.get(cell, 0) for actor in (attacker, target)
                            for cell in BODY.cells(actor, require_complete=True)), default=0)
            import map_terrain as TERRAIN
            zone_pen += TERRAIN.accuracy_penalty(self,attacker,target)                                                                            # 험한 지형의 대상 -2
        import roll_effects as ROLLS
        ROLLS.preflight_accuracy(self,attacker,target,move,shared_roll)
        import captured_momentum as MOMENTUM
        MOMENTUM.preflight_accuracy(self,attacker,target,move,shared_roll)
        if fixed_roll is None:
            import fast_combat as FAST_COMBAT
            FAST_COMBAT.require_faces(self,attacker)
        return dict(move=move,no_accuracy=False,ac_rule=ac_rule,mm=mm,conf=conf,no_hit_reason=no_hit_reason,
                    invisibility_penalty=invisibility_penalty,blender_evasion=blender_evasion,environment_evasion=environment_evasion,spatial_penalty=spatial_penalty,ap_bonus=ap_bonus,zone_pen=zone_pen,grapple_penalty=grapple_penalty)

    def _accuracy_check_native(self, attacker, target, move, situational=0, waive=False, fixed_roll=None, shared_roll=None, *, roll_id=None):
        import weapon_actions as WEAPONS,roll_effects as ROLLS,combat_social_edges as SOCIAL
        plan=self._prepare_accuracy_context(attacker,target,move,situational,waive,fixed_roll,shared_roll,roll_id=roll_id)
        move=plan['move'];no_hit_reason=plan['no_hit_reason']
        read=__import__('telepath').read_accuracy(self,attacker,target,move)
        if read is not None:return read and not bool(no_hit_reason),None,False
        if move.get('_tumbler_no_critical'):
            scope=__import__('pass_moves').converted_scope(self,attacker,move['id'])
            if scope is None or scope['conversion']['source']!=__import__('tumbler').FLIP:raise ValueError('actual Flip Out Pass scope required')
            hit=not bool(no_hit_reason)
            if hit and (DEFENSE.consume_shield(self,attacker,target,move) or DEFENSE.consume_shield(self,attacker,target,move,actual_hit=True)):hit=False
            return hit,None,False
        import event_effects as EVENTS
        event_critical=EVENTS.accuracy_attempt(self,attacker,target,move)
        import taskmaster as TASK
        gambit=TASK.gambit_side(self,attacker,target,move)
        import optional_state_effect_contracts as OPTIONAL_STATE
        optional_accuracy, optional_critical = OPTIONAL_STATE.attack_modifiers(attacker, move, engine=self, target=target)
        optional_accuracy,optional_critical,marksman_clear=__import__('marksman').accuracy_modifiers(self,attacker,target,move,(optional_accuracy,optional_critical))
        optional_accuracy+=__import__('skirmisher').accuracy_bonus(self,attacker,move)
        if gambit and not self._taskmaster_gambit['roll_effects']:
            hit=not bool(no_hit_reason)
            if hit and (DEFENSE.consume_shield(self,attacker,target,move) or DEFENSE.consume_shield(self,attacker,target,move,actual_hit=True)):return False,None,False
            critical=hit if gambit=='incoming' else EXT.crit_hook(self,attacker,target,move,hit,hit)
            critical=EVENTS.critical(self,attacker,target,move,hit) or (hit and event_critical) or critical
            return hit,None,critical and not __import__("provocateur").blocked(attacker,"no_critical") and not (__import__("defense_curl").critical_immune(target) or __import__('declarative_move_contracts').defensive_critical_immunity(target))
        if plan['no_accuracy']:
            self.log('    '+move['name']+': 명중 체크 없음'+(' ('+no_hit_reason+')' if no_hit_reason else ''),move['id'])
            hit = not bool(no_hit_reason)
            if hit and DEFENSE.consume_shield(self,attacker,target,move,actual_hit=True):
                hit = False
            import coup_de_grace as COUP
            import duelist as DUELIST
            if __import__('musician').drown_out(self,attacker,target,move,None,shared_roll):return False,None,False
            critical=DUELIST.critical(self,attacker,target,move,hit,hit and COUP.active(self,attacker,target,move))
            critical=EVENTS.critical(self,attacker,target,move,hit) or (hit and event_critical) or critical
            return hit,None,critical and not __import__('provocateur').blocked(attacker,'no_critical') and not (__import__('defense_curl').critical_immune(target) or __import__('declarative_move_contracts').defensive_critical_immunity(target))
        ac_rule,mm,conf=(plan[key] for key in ('ac_rule','mm','conf'))
        environment_evasion=plan['environment_evasion']
        invisibility_penalty,blender_evasion,spatial_penalty,ap_bonus,zone_pen=(plan[key] for key in ('invisibility_penalty','blender_evasion','spatial_penalty','ap_bonus','zone_pen'))
        import fast_combat as FAST_COMBAT
        import duelist as DUELIST
        if shared_roll is not None:nat=fixed_roll
        elif fixed_roll is not None:nat=11 if DUELIST.choose_eleven(self,attacker,'accuracy') else fixed_roll
        else:nat=FAST_COMBAT.roll(self,attacker)
        if shared_roll is None:
            nat=__import__('oracle').replace_d20(self,attacker,nat,'accuracy')
            nat=__import__('roll_context').observe_native(self,attacker,'accuracy',nat,lambda faces:POOLS.die(self.rng,20,fixed=None if faces is None else faces[0]))
        nat=__import__('marksman').deadeye_roll(self,attacker,target,move,nat)
        AP_ROLL.complete(self,attacker,roll_id,'accuracy')
        import combat_modifiers as COMBAT_MODS
        import keen_eye as KEEN_EYE
        keen_eye=KEEN_EYE.active(self,attacker)
        acc=lambda value:max(0,value) if keen_eye else value
        if shared_roll is not None:
            if "actor_mod" not in shared_roll:
                shared_roll["actor_mod"] = COMBAT_MODS.accuracy_stage(attacker,self) + self.rulings.consume("accuracy", attacker.name, self, ignore_penalties=keen_eye)
            actor_mod = shared_roll["actor_mod"]
        else:
            actor_mod = COMBAT_MODS.accuracy_stage(attacker,self) + self.rulings.consume("accuracy", attacker.name, self, ignore_penalties=keen_eye)
        import living_weapon as LIVING
        ordinary_stage=COMBAT_MODS.accuracy_stage(attacker,self)
        actor_mod+=LIVING.accuracy_stage(self,attacker,target,ordinary_stage)-ordinary_stage
        import training_features as TRAINING
        import fashion_items as FASHION
        import field_effects as FIELD
        import class_passive_combat as CLASS_PASSIVE
        import unown_imbuement as UNOWN
        import dynamic_chain_moves as CHAIN
        situational = acc(situational) + acc(CHAIN.bonus(move,'accuracy'))
        mods = sum(acc(value) for value in (
            actor_mod, situational, zone_pen, ap_bonus, plan['grapple_penalty'], -invisibility_penalty,
            optional_accuracy, CAPABILITIES.accuracy(attacker), WEAPONS.accuracy_bonus(move),
            CPF.accuracy_bonus(self,attacker,move), CLASS_PASSIVE.accuracy_bonus(self,attacker,target,move,mm),
            TRAINING.bonus(attacker,"accuracy"), FASHION.all_roll_modifier(attacker), FIELD.accuracy_modifier(self,attacker),
            UNOWN.active_count(attacker), UNOWN.accuracy_bonus(self,attacker,target,move)))
        mods+=DUELIST.accuracy(self,attacker,target)+acc(__import__('channeler').synchronized_bonus(self,attacker,target))
        mods+=acc(__import__('coordinator').attack_boon(attacker,move,'슬기로움'))
        mods+=acc(__import__('chronicler').accuracy_bonus(self,attacker,target,move))
        mods+=acc(__import__('survivalist_class').accuracy_bonus(self,attacker,target,move))
        total = nat + mods
        # ch07:221 uses the defense stat targeted by the move, including
        # special attacks such as Psyshock which explicitly target Defense.
        evasion_class = move["class"]
        for effect in mm.get("effects_exec", []):
            if effect.get("type") == "damage_formula_override":
                evasion_class = effect.get('evasion_class',{"def": "물리", "spd": "특수"}.get(effect.get("defense_stat"), evasion_class))
        evasion_class = FIELD.evasion_class(self, target, evasion_class)
        import double_team as DOUBLE
        double_evasion=DOUBLE.consume(self,target,'evasion',opponent=attacker)
        evasion = 0 if waive or target.fainted else min(9, max(0, target.evasion(evasion_class, attacker=attacker, engine=self, conditional_bonus=SOCIAL.evasion_bonus(self,target,move,mm,attacker)+spatial_penalty+blender_evasion+environment_evasion+CLASS_PASSIVE.evasion_bonus(self,target)+double_evasion+__import__('chronicler').evasion_bonus(self,target,move,attacker)+__import__('researcher_fields').evasion_bonus(self,target,move)+__import__('survivalist_class').evasion_bonus(self,target,attacker,move)-__import__('survivalist_class').ignored_ability_evasion(self,attacker,target)) + self.rulings.consume("evasion", target.name, self)))
        ac = (move.get("ac") or 0)
        if keen_eye or __import__('trickster').flourish_applies(self,attacker,target,move):
            evasion=0 if waive or target.fainted else target.evasion(evasion_class,attacker=attacker,engine=self,ignore_nonstats=True)
        need = ac + evasion
        ac_ov, waive_ev, acc_bonus, never_cond = EXT.accuracy_hook(self, attacker, target, move, mm, {"attacker": attacker, "target": target, "hit": True, "nat": nat, "engine": self, "move": move})
        if waive_ev:
            evasion = 0
        if ac_ov is not None:
            ac = ac_ov
        ac,evasion,automatic = CPF.accuracy_policy(self,attacker,target,move,mm,ac,evasion,bool(mm.get("never_miss") or never_cond))
        if marksman_clear:evasion=0
        automatic = automatic or __import__('commander_orders').perfect_for_move(self,attacker,move)
        if __import__('type_ace').isolated_dragon(self,attacker,target,move):evasion=0
        ac = CLASS_PASSIVE.accuracy_target(self,attacker,move,ac)
        mods += acc(acc_bonus) + acc(ROLLS.use(self,attacker,target,move,'accuracy',{'natural':nat},shared_roll=shared_roll))
        import style_expert as STYLE
        mods += acc(STYLE.accuracy(self,attacker,target,move))
        import double_team as DOUBLE
        mods += acc(DOUBLE.consume(self,attacker,'accuracy',shared_roll,opponent=target))
        import captured_momentum as MOMENTUM
        mods += acc(MOMENTUM.accuracy(self,attacker,target,move,nat,shared_roll))
        import type_ace as TA
        mods+=acc(TA.accuracy(self,attacker,target,move,mm))
        mods+=acc(__import__('fortress').accuracy(self,attacker,target))
        import hunter as HUNTER
        mods+=acc(HUNTER.accuracy(self,attacker,target,move,mm))
        mods+=acc(__import__('martial_artist').bonus(attacker,target))
        nat=TA.accuracy_face(self,attacker,target,move,mm,nat,modifier=mods,ac=ac,evasion=evasion,automatic=automatic,cannot_hit=no_hit_reason,ac_rule=ac_rule)
        nat=HUNTER.accuracy_face(self,attacker,target,move,mm,nat,modifier=mods,ac=ac,evasion=evasion,automatic=automatic,cannot_hit=no_hit_reason,ac_rule=ac_rule,shared_roll=shared_roll)
        total = nat + mods
        need = ac + evasion
        if DEFENSE.consume_shield(self,attacker,target,move):
            move['_shield_miss']=True
            return False,nat,False
        import combat_hit as HIT
        outcome = HIT.resolve(natural=nat, modifier=mods, accuracy=ac, evasion=evasion,
                              automatic=automatic, cannot_hit=no_hit_reason or None,
                              auto_miss_natural=ac_rule["auto_miss_natural"],
                              auto_hit_natural=ac_rule["auto_hit_natural"])
        penalty=acc(__import__('combat_move_reactions').kinesis_accuracy(self,attacker,target,move,outcome['hit']))
        if penalty:
            mods+=penalty;total=nat+mods
            outcome=HIT.resolve(natural=nat,modifier=mods,accuracy=ac,evasion=evasion,automatic=automatic,cannot_hit=no_hit_reason or None,auto_miss_natural=ac_rule['auto_miss_natural'],auto_hit_natural=ac_rule['auto_hit_natural'])
        if (TA.aoo_outcome(self,attacker,move) or __import__('athlete').aoo_outcome(self,attacker,move)) and not no_hit_reason:outcome={'hit':True,'basis':'automatic'}
        hit = not bool(no_hit_reason) if gambit else outcome["hit"]
        if hit and DEFENSE.consume_shield(self,attacker,target,move,actual_hit=True):
            move['_shield_miss']=True
            return False,nat,False
        why = {"automatic": f"{move['id']} (never_miss, {conf})",
               "natural_miss": f"combat/accuracy-roll (자연 {nat})",
               "natural_hit": f"combat/accuracy-roll (자연 {nat})",
               "cannot_hit": str(no_hit_reason) + " (cannot hit)",
               "comparison": "combat/accuracy-roll"}[outcome["basis"]]
        crit_min = M.floor(self.formula("crit_range"))
        for e in mm.get("effects_exec", []):
            if e["type"] == "crit_range" and isinstance(e.get("min"), int):
                crit_min = min(crit_min, e["min"])
        for e in attacker.modifiers:
            if e.get("type") == "crit_range" and isinstance(e.get("min"), int):
                crit_min = min(crit_min, e["min"])
        crit_min -= optional_critical + ITEMS.crit_delta(attacker, move, engine=self) + TRAINING.bonus(attacker,"critical") + CPF.bad_mood_critical_bonus(self,attacker) + CLASS_PASSIVE.critical_bonus(self,attacker,move)
        import taskmaster as TASK
        crit_min -= TASK.bonus(attacker,'critical')
        crit_min -= __import__('berserker').frenzy_bonus(attacker)
        import stat_ace as STAT
        crit_min -= STAT.stratagem_bonus(self,attacker,'critical',move)
        crit_min -= STYLE.critical(self,attacker,move) + __import__('combat_modifiers').incoming_critical_bonus(target)
        crit_min -= __import__('coordinator').attack_boon(attacker,move,'근사함')
        crit_min -= __import__('chef_cooking').critical_bonus(self,attacker,move)
        crit_min -= __import__('arcanist').critical_bonus(self,attacker,move)
        import declarative_move_contracts as DECLARATIVE_MOVES
        crit_min = DECLARATIVE_MOVES.critical_threshold(attacker,crit_min)
        crit = move["class"] in ("물리", "특수") and (nat >= crit_min or any(e["type"] == "crit_range" and e.get("on_natural_roll") == "even" and nat % 2 == 0 for e in mm.get("effects_exec", [])))
        import coup_de_grace as COUP
        if gambit:crit=hit
        crit = bool(hit) if gambit=='incoming' or COUP.active(self,attacker,target,move) else EXT.crit_hook(self, attacker, target, move, hit, crit, natural=nat, crit_min=crit_min)
        if TA.aoo_outcome(self,attacker,move):crit=bool(hit)
        if __import__('marksman').deadeye_critical(self,attacker,target,move,hit):crit=True
        if no_hit_reason:crit=False
        if EVENTS.critical(self,attacker,target,move,hit) or (hit and event_critical):crit=True
        if attacker.next_attack and attacker.next_attack.get("auto_crit") and move["class"] in ("물리", "특수") and hit:
            crit = True
            attacker.next_attack = None
            self.log("    다음 공격 자동 치명타 발동", "effect/next_attack_modifier")
        crit=DUELIST.critical(self,attacker,target,move,hit,crit)
        if __import__("provocateur").blocked(attacker,"no_critical") or __import__("defense_curl").critical_immune(target) or __import__('declarative_move_contracts').defensive_critical_immunity(target):crit=False
        self.log(f"  {attacker.name} {move['name']}: 명중 d20={nat}{mods:+d}={total} vs AC {ac}+회피 {evasion}={need} → {'명중' if hit else '빗나감'}{' 치명타!' if hit and crit else ''}", why)
        TA.after_accuracy(self,attacker,target,move,nat,hit)
        HUNTER.after_accuracy(self,attacker,target,move,nat,hit)
        if __import__('musician').drown_out(self,attacker,target,move,total,shared_roll):return False,nat,False
        return hit, nat, crit

    # ---------- 데미지 ----------
    def type_multiplier(self, move_type, target, *, bypass_type_immunity=False):
        if type(bypass_type_immunity) is not bool:
            raise ValueError("explicit type immunity bypass boolean required")
        import type_state as TYPES
        TYPES.validate_attack(self.r, move_type)
        if move_type=='None':return 1.0,'combat/type-effectiveness (Typeless)'
        te = self.r.mech("combat/type-effectiveness")
        if not target.types:
            return 1.0, "combat/type-effectiveness (타입 없음)"
        source = TYPES.source_defense_steps(self.r, move_type, target.types)
        steps = 0 if source is None else source["net_steps"]
        if steps is None and bypass_type_immunity:
            steps = 0
        for t in target.types if source is None else ():
            v = TYPES.matchup(self.r, move_type, t)
            import newground_flight_option as GROUND_FLIGHT
            v = GROUND_FLIGHT.defense_component(self, move_type, t, target, v)
            if v == 0:
                import field_effects as FIELD
                import catalog_move_states as CATALOG
                flying = t in ("비행", "Flying") and move_type in ("땅", "Ground")
                if not (bypass_type_immunity or flying and (CATALOG.grounded(target)
                        or FIELD.suppresses_ground_immunity(self,target,{"_ability":""}))):
                    steps = None
                    break
                v = 1
            steps += 1 if v > 1 else (-1 if v < 1 else 0)
        value=0.0 if steps is None else te["multiplier_by_net_steps"][str(max(-3, min(3, steps)))]
        import csv_item_capability_contracts as CSV_CAP
        if 'csv_essence_projection' in target.spec:value=CSV_CAP.essence_effectiveness(target,move_type,value)
        return value, source["source"] if source is not None else "combat/type-chart" if steps is None else "combat/type-effectiveness"

    def damage_base(self, attacker, move, *, target=None, _actual_damage_type=None, versatile_stat=None):
        import environ_moves as ENVIRON
        import weapon_actions as WEAPONS
        move = WEAPONS.prepare(self,attacker,move)
        import struggle_capabilities as STRUGGLE
        move = STRUGGLE.prepare(self,attacker,move)
        import pokemon_move_edges as POKE_MOVE_EDGES
        move = POKE_MOVE_EDGES.prepare(self,attacker,move)
        move = EXT.prepare_versatile_move(self,move,versatile_stat)
        db = move["damage_base"]
        import type_ace as TA
        normal_max=TA.new_normal_maximum(self,move) if move.get("_type_ace_new_normal") else None
        import conditional_damage_base as CONDITIONAL_DB
        db = normal_max if normal_max is not None else CONDITIONAL_DB.override_base(self, attacker, target, move, db)
        formulas=[] if normal_max is not None else [x for x in ENVIRON.read(self,move,attacker)[0].get('effects_exec',[]) if x.get('type')=='damage_base_formula']
        for effect in formulas:
            value=FX.evaluate(effect.get('formula'),{'attacker':attacker,'target':target,
                'engine':self,'db':db if isinstance(db,int) and not isinstance(db,bool) else 0})  # printed 'X: See Effect' bases start at 0 (Spit Up r587)
            if value is None:raise ValueError('selected damage-base formula requires an executable expression')
            db=value
        db=__import__('multi_strike').base(attacker,move,db)
        if isinstance(db, str):
            raise ValueError(f"{move['name']}: DB 가변(본문 참조) — 기계화 안 됨")
        for effect in ENVIRON.read(self,move,attacker)[0].get("effects_exec", []):
            if normal_max is not None:
                break
            if effect.get("type") != "conditional_damage_base":
                continue
            override = CONDITIONAL_DB.override(self, attacker, target, move, effect)
            if override is not None:
                db = override
            elif not CONDITIONAL_DB.manages(move) and effect.get("if") not in (CONDITIONAL_DB.ASSURANCE_CONDITION,
                                          CONDITIONAL_DB.RETALIATION_CONDITION) and FX.cond_ok(
                    self, effect, {"attacker": attacker, "target": target, "hit": True, "move": move})[0]:
                db = effect["damage_base"]
        import five_strike as FIVE_STRIKE
        db = FIVE_STRIKE.combined_base(attacker,move,db)
        db += FIVE_STRIKE.technician_bonus(attacker,move)
        import dynamic_chain_moves as CHAIN
        db += CHAIN.bonus(move,'db') + CHAIN.technician(attacker,move)
        db += WEAPONS.damage_bonus(move)
        db += __import__('martial_artist_ability_identities').damage_base_bonus(self,attacker,move)
        stab = self.r.mech("combat/stab")
        import homebrew_state as HOME
        actual_type = _actual_damage_type
        if actual_type is None:
            mechanics, _ = ENVIRON.read(self,move,attacker)
            actual_type = EXT.effective_type(self,attacker,target or attacker,move,mechanics,consume=False)
        import stellar_tera_blast as STELLAR_TERA
        stab_type = STELLAR_TERA.stab_membership_type(self,attacker,target or attacker,move,actual_type)
        if (stab_type in HOME.stab_types(attacker) or EXT.grants_stab(self, attacker, move) or __import__('rune_master').grants_stab(self,attacker,move)) and move["class"] in ("물리", "특수") and move["id"] != "struggle" and move.get("innovation_instance",{}).get("template")!=3 and not WEAPONS.excludes_stab(move):
            bonus = M.floor(self.formula("stab"))
            self.log(f"    자속보정: DB {db} → {db + bonus}", "combat/stab")
            db += bonus
        db_mechanics = ENVIRON.read(self,move,attacker)[0]
        if CONDITIONAL_DB.manages(move):
            db_mechanics = dict(db_mechanics, effects_exec=[effect for effect in db_mechanics.get("effects_exec", [])
                if effect.get("type") != "escalating_damage_base"])
        db += EXT.db_hook(self, attacker, move, db_mechanics)
        import event_effects as EVENTS
        db += EVENTS.damage_base_bonus(self,attacker,move,target)
        return max(1, min(28, db))

    def _damage_roll_plan(self, attacker, target, move, hit_mm, crit, _reaction_event=None, _precision_observation=None):
        df = self.r.mech("combat/damage-formula")
        import type_ace as TA
        mtype = EXT.effective_type(self,attacker,target,move,hit_mm)
        actual_move = dict(move,type=mtype)
        if _reaction_event is not None:_reaction_event["actual_damage_type"] = mtype
        if _precision_observation is not None:_precision_observation.update(actual_damage_type=mtype,type_multiplier=0)
        db = TA.damage_choice(self,attacker,move,self.damage_base(attacker, move, target=target, _actual_damage_type=mtype))
        entry = self.r.mech("combat/damage-chart")["by_damage_base"][str(db)]
        import event_effects as EVENTS
        event_effects=EVENTS.extra_rolls(self,attacker,move,mtype)
        times = (2 if crit and not __import__('multi_strike').separate_critical(move) else 1)+sum(r['effect']['amount'] for r in event_effects)
        times+=__import__('marksman').sniper_times(attacker,crit)
        return df,mtype,actual_move,db,entry,event_effects,times

    def _damage_hit_context(self, attacker, target, move, mm, crit, actual_move, _reaction_event=None):
        import type_ace as TA
        import class_passive_combat as CLASS_PASSIVE
        mtype=actual_move['type']
        mult, why = self.type_multiplier(mtype, target)
        mult=__import__('aura_guardian').scrappy_multiplier(self,attacker,target,mtype,mult)
        import catalog_move_states as CATALOG
        arrows_policy=CATALOG.thousand_arrows_policy(self,move,mm)
        mult=CATALOG.thousand_arrows_base(self,target,actual_move,arrows_policy,mult)
        ace_hit=TA.incoming_multiplier(self,attacker,target,actual_move,mult)
        mult=ace_hit['multiplier']
        ctx = {"attacker": attacker, "target": target, "multiplier": mult, "crit": crit, "hit": True, "move": move, "engine": self, 'actual_damage_type': mtype}
        mult = EXT.effectiveness_hook(self, attacker, target, move, mm, mult, ctx)
        if _reaction_event is not None:
            _reaction_event['cleanse_tag_weapon'] = ctx.get('cleanse_tag_weapon')
        ctx['iterative_evolution_multiplier'] = mult
        mult = CLASS_PASSIVE.effectiveness_modifier(self,attacker,actual_move,mult)
        return mult,why,ace_hit,ctx

    @TRACE.operation('damage_calculation','attacker','target','move','crit','set_damage','fixed_dice')
    def roll_damage(self, attacker, target, move, crit=False, set_damage=False, fixed_dice=None, _reaction_event=None, _precision_observation=None, *, versatile_stat=None):
        import environ_moves as ENVIRON
        import partial_entities as PARTIAL
        PARTIAL.require_complete(attacker, "roll_damage attacker")
        PARTIAL.require_complete(target, "roll_damage target")
        if __import__('defense_curl').critical_immune(target) or __import__('declarative_move_contracts').defensive_critical_immunity(target):crit=False
        import aura_guardian as AURA
        move=AURA.damage_move(self,attacker,move)
        AURA.before_damage(self,attacker,target,move)
        import coup_de_grace as COUP
        coup_bonus = COUP.damage_bonus(self,attacker,target,move,crit)
        import struggle_capabilities as STRUGGLE
        move = STRUGGLE.prepare(self,attacker,move)
        import type_state as TYPES
        TYPES.validate_attack(self.r, move.get("type"))
        TYPES.validate_actor(attacker)
        TYPES.validate_actor(target)
        M.validate_source(self.r)
        move = EXT.prepare_versatile_move(self,move,versatile_stat)
        arcanist_original_move=move
        move,arcanist_normal_boost=__import__('arcanist').link_damage(self,attacker,target,move,actual=False)
        hit_mm,_ = ENVIRON.read(self,move,attacker)
        import class_passive_combat as CLASS_PASSIVE
        CLASS_PASSIVE.preflight(self,attacker,target,move,hit_mm)
        no_hit_reason = EXT.blocks_hit(self,attacker,target,move,hit_mm)
        if no_hit_reason:
            if _precision_observation is not None:_precision_observation.update(hit_prevented=no_hit_reason,nullification="cannot_hit")
            self.log("    공격 명중 불가: "+no_hit_reason,no_hit_reason)
            return 0
        move,arcanist_normal_boost=__import__('arcanist').link_damage(self,attacker,target,arcanist_original_move,actual=_reaction_event is not None)
        arcanist_overdrive=__import__('arcanist').overdrive(self,attacker,move,actual=_reaction_event is not None)
        if __import__('setup_move_state').physical_immunity(target,move.get('class')):
            if _precision_observation is not None:_precision_observation['nullification']='acid_armor'
            return 0
        import food_effects as FOOD
        salty_hit=FOOD.salty_hit_pending(self,target,attacker=attacker)
        chef_plan=None if salty_hit else FOOD.chef_attack_preflight(self,attacker,target,move)
        import blessing_effects as BLESSINGS
        BLESSINGS.checked(self)
        import roll_effects as ROLLS
        ROLLS.require_origin(attacker,'damage')
        import type_ace as TA
        prepared_hit=None
        if salty_hit:
            import state_grants as GRANTS
            def prepare(staged,a,t):
                roll_plan=staged._damage_roll_plan(a,t,move,hit_mm,crit)
                mm,_=ENVIRON.read(staged,move,a)
                hit=staged._damage_hit_context(a,t,move,mm,crit,roll_plan[2])
                plans={id(t):{}}
                FOOD.hit_resistance_preflight(staged,t,roll_plan[1],hit[0],attacker=a,
                    temporary_hp_plan=plans[id(t)])
                chef=FOOD.chef_attack_preflight(staged,a,t,move,temporary_hp_plans=plans)
                return roll_plan,hit,chef
            # Resolve this hit once; rejected grants expose neither payment nor damage RNG.
            roll_plan,prepared_hit,chef_plan=GRANTS.transition(self,attacker,prepare,participants=(target,),include_rulings=True)
        else:
            roll_plan=self._damage_roll_plan(attacker,target,move,hit_mm,crit,_reaction_event,_precision_observation)
        df,mtype,actual_move,db,entry,event_effects,times=roll_plan
        if salty_hit:
            if _reaction_event is not None:_reaction_event["actual_damage_type"] = mtype
            if _precision_observation is not None:_precision_observation.update(actual_damage_type=mtype,type_multiplier=0)
        import event_effects as EVENTS
        actual_type=mtype
        solar_power_bonus=__import__('ability_native_actions').solar_power_damage(self,attacker,target,move,_reaction_event)
        perfect_damage = CLASS_PASSIVE.perfect_damage(self,attacker,dict(move,type=actual_type),entry["dice"],times,fixed=fixed_dice)
        if perfect_damage is not None:
            dice_part, rolls = perfect_damage
            self.log(f"    DB {db} → {entry['dice']} 확실한 완벽 눈 {rolls} = {dice_part}", CLASS_PASSIVE.PERFECT)
        elif set_damage:
            dice_part = entry["set"]["mid"] * times
            self.log(f"    DB {db} 지정 데미지 {entry['set']['mid']}{' ×2(치명타)' if crit else ''} = {dice_part}", "combat/damage-chart")
        elif fixed_dice is not None:
            dice_part, _ = self.roll_expr(entry['dice'], times, fixed=fixed_dice,actor=attacker,purpose='damage')
            self.log(f"    DB {db} → {entry['dice']} 눈 {fixed_dice} = {dice_part}", "combat/damage-chart")
        else:
            dice_part, rolls = self.roll_expr(entry["dice"], times,actor=attacker,purpose='damage')
            self.log(f"    DB {db} → {entry['dice']}{' ×2(치명타)' if crit else ''} 눈 {rolls} = {dice_part}", "combat/critical-hit" if crit else "combat/damage-chart")
        dice_part+=__import__('multi_strike').critical_dice(self,attacker,move,set_damage)
        dice_part+=__import__('ability_control_contracts').damage_dice(self,attacker,move,set_damage)
        dice_part+=__import__('marksman').sniper_dice(self,attacker,move,crit,set_damage)
        long_order_bonus = __import__('commander_orders').long_damage(self,attacker,target,move,dice_part,crit)
        EVENTS.record_damage(self,attacker,target,move,event_effects,db)
        component_roll_mod=ROLLS.use(self,attacker,target,move,'damage',{'damage_base':db,'roll_value':dice_part,'mode':'set' if set_damage else 'fixed_dice' if fixed_dice is not None else 'random'})
        component_roll_mod += solar_power_bonus
        atk_stat = move.get("_versatile_attack_stat",df["attack_stat_by_class"][move["class"]])
        if move.get('_pk_combat_spa'):atk_stat='spa'
        import telekinetic_combat as TK_COMBAT
        if TK_COMBAT.STRUGGLE_MARKER in move:
            atk_stat=move[TK_COMBAT.STRUGGLE_MARKER]['attack_stat']
            TRACE.calculation(self,telekinetic_source=move[TK_COMBAT.STRUGGLE_MARKER],attack_stat=atk_stat,damage_class=move['class'])
        def_stat = df["defense_stat_by_class"][move["class"]]
        mm, conf = ENVIRON.read(self,move,attacker)
        atk_src = attacker          # 속임수: 대상의 공격 스탯으로 계산
        for e in mm.get("effects_exec", []):
            if e.get("type") == "damage_formula_override":
                if e.get("defense_stat") in ("def", "spd"):
                    def_stat = e["defense_stat"]
                if e.get("attack_stat") in ("atk", "spa"):
                    atk_stat = e["attack_stat"]
                elif str(e.get("attack_stat", "")).startswith("target.") and e["attack_stat"][7:] in ("atk", "spa"):
                    atk_src, atk_stat = target, e["attack_stat"][7:]
                elif str(e.get("attack_stat", "")).startswith("max("):
                    atk_stat = max(("atk", "spa"), key=lambda s: attacker.staged(s))
        import field_effects as FIELD
        def_stat = FIELD.defense_stat(self, target, def_stat)
        mult,why,ace_hit,ctx=(self._damage_hit_context(attacker,target,move,mm,crit,actual_move,_reaction_event)
                            if prepared_hit is None else prepared_hit)
        if prepared_hit is not None and _reaction_event is not None:
            _reaction_event['cleanse_tag_weapon'] = ctx.get('cleanse_tag_weapon')
        # A berry is exchanged after the actual hit; it cannot retroactively
        # make Wonder Guard's prior hit predicate false in its preview.
        berry_resistance=FOOD.hit_resistance(self,target,mtype,mult,attacker=attacker)
        ctx["multiplier"] = mult
        if _precision_observation is not None:_precision_observation["nullification"] = "type_immunity" if mult == 0 else None
        db_mod, roll_mod, resist_steps, immune, absorb = FX.passive_damage_mods(self, attacker, target, move, ctx)
        import focused_command as FOCUSED
        focused_penalty=FOCUSED.damage_modifier(self,attacker)
        roll_mod+=focused_penalty
        FOCUSED.record_fact(self,attacker,move['id'],'damage_roll',penalty=focused_penalty)
        import duelist as DUELIST
        roll_mod += coup_bonus + AURA.storm_bonus(self,attacker,move)
        roll_mod += __import__('hunter').damage_bonus(self,attacker,target,move)
        resist_steps += CLASS_PASSIVE.resistance_steps(self,target,mtype)
        if arcanist_normal_boost:resist_steps-=1
        resist_steps += __import__('confusion_attacks').resistance(self,attacker,target,move)
        resist_steps += __import__('marksman').resistance(self,attacker,target,move)
        import taskmaster as TASK
        resist_steps += TASK.bonus(target,'resistance')
        resist_steps += __import__('combat_move_reactions').resistance(self,attacker,target,move)
        import optional_physical_equipment as OPTIONAL_EQUIPMENT
        resist_steps += OPTIONAL_EQUIPMENT.resistance_steps(self,target,mtype)
        for e in mm.get("effects_exec", []):
            if e.get("type") == "bonus_damage" and isinstance(e.get("value"), int):
                ok, _ = FX.cond_ok(self, e, ctx)
                if ok:
                    roll_mod += e["value"]
                    self.log(f"    추가 데미지 +{e['value']} ({e.get('if', '')})", f"{move['id']} ({conf})")
        import catalog_move_states as CATALOG
        defensive_ignored=__import__('chronicler').defensive_ignored(self,attacker,target)
        if (immune is not None and not target.abilities_suppressed and not defensive_ignored
                and not OPTIONAL_EQUIPMENT.bypass_ability_immunity(move,mtype)
                and not (mtype in ("땅", "Ground") and immune.get("_ability") in ("부유", "Levitate")
                         and (CATALOG.grounded(target)
                              or CATALOG.thousand_arrows_ignores_ground_immunity(self,actual_move,mm)))
                and not (mtype in ("땅", "Ground") and FIELD.suppresses_ground_immunity(self,target,immune))):
            if _precision_observation is not None:_precision_observation["nullification"] = "ability_immunity"
            self.log(f"    {target.name} 특성으로 {move['type']} 무효", "effect/immunity")
            return 0
        if absorb is not None and not target.abilities_suppressed and not defensive_ignored:
            if _precision_observation is not None:_precision_observation["nullification"] = "ability_absorption"
            self.log(f"    {target.name} 특성으로 {move['type']} 흡수: {absorb.get('then')}", "effect/absorb")
            then = absorb.get("then", {})
            if then.get("heal") == "tick":
                self.heal(target, self.tick(target))
            if isinstance(then.get("stage_change"), str):
                m2 = re.match(r"([+\-]\d+)\s*(atk|def|spa|spd|spe)", then["stage_change"])
                if m2:
                    self.change_stage(target, m2.group(2), int(m2.group(1)))
            return 0
        import fashion_items as FASHION
        roll_mod += long_order_bonus + component_roll_mod + EVENTS.damage_roll_bonus(self,attacker,target,move,mtype) + FASHION.all_roll_modifier(attacker)
        roll_mod += __import__("provocateur").damage_modifier(self,attacker,target,move,actual_hit=_reaction_event is not None)
        import boss_transitions as BOSS
        roll_mod += BOSS.consume_damage_roll_modifier(attacker)
        roll_mod += __import__('defense_curl').damage_bonus(attacker,move)
        wmod = TURN.weather_damage_mod(self, attacker, move, target=target)
        if wmod:
            roll_mod += wmod
            self.log(f"    날씨({TURN.WEATHER_KO.get(self.weather, self.weather)}): {move['type']} 피해 굴림 {wmod:+d}", "combat/weather")
        import field_effects as FIELD
        roll_mod += FIELD.damage_roll_modifier(self,attacker,target,move,mtype)
        roll_mod += CPF.damage_modifier(self,attacker,move)
        rider_overrun=__import__('conquerors_march').overrun(self,attacker,target,move,_reaction_event)
        roll_mod += CLASS_PASSIVE.damage_roll_modifier(self,attacker,target,actual_move,ctx['iterative_evolution_multiplier'])+rider_overrun['bonus']
        roll_mod += TA.damage_bonus(self,attacker,target,actual_move,mult)
        roll_mod += OPTIONAL_EQUIPMENT.damage_roll_bonus(self,attacker,target,move)
        roll_mod += OPTIONAL_WEAPONS.damage_roll_bonus(self,attacker,move)
        roll_mod += arcanist_overdrive
        import homebrew_state as HOME
        roll_mod += HOME.damage_bonus(attacker, actual_move, engine=self)
        import dynamic_chain_moves as CHAIN
        roll_mod += CHAIN.bonus(move,'damage')
        import rage_abilities as RAGE_ABILITIES
        rage_bonus = RAGE_ABILITIES.outgoing_damage_bonus(attacker)
        if rage_bonus:
            roll_mod += rage_bonus
            self.log(f"    화이트플레임: 난동 중 피해 굴림 +{rage_bonus}", "ability/화이트플레임")
        if roll_mod:
            self.log(f"    패시브/조건 굴림 보정 {roll_mod:+d}", "effect/damage_roll_mod")
        import combat_maneuvers as MANEUVERS
        attack_value,infatuation_mod = MANEUVERS.infatuation_damage(attacker,target,move,atk_src,AURA.attack_stat(self,attacker,move,TA.attack_stat(self,attacker,actual_move,__import__('researcher_fields').attack_stat_value(self,attacker,move,atk_src.staged(atk_stat)))))

        rage_reduction = RAGE_ABILITIES.incoming_damage_reduction(target)
        import stat_ace as STAT
        maneuver_defense=STAT.defense_maneuver(self,target,move,_reaction_event)
        incoming_reduction=DEFENSE.splash_reduction(self,_reaction_event)+rage_reduction+STAT.damage_reduction(self,target)+TA.damage_reduction(self,attacker,target,actual_move,mult)+ace_hit['reduction']+TA.incoming_reduction(self,attacker,target,actual_move,mult)
        incoming_reduction+=__import__('athlete').intercept_reduction(self,target,_reaction_event)
        incoming_reduction+=__import__('arcanist').reduction(self,attacker,target)
        if incoming_reduction:
            # Pass the dynamic contribution through the existing defense hook;
            # effects that ignore damage reduction therefore keep one policy.
            original_reduction = target.damage_reduction
            target.damage_reduction = original_reduction + incoming_reduction
            try:
                def_val, dr_val = EXT.defense_hook(self, attacker, target, move, mm, def_stat,stage_override=6 if maneuver_defense==def_stat else None)
            finally:
                target.damage_reduction = original_reduction
            if rage_reduction:self.log(f"    불굴의격노: 난동 중 피해 감소 +{rage_reduction}", "ability/불굴의격노")
        else:
            def_val, dr_val = EXT.defense_hook(self, attacker, target, move, mm, def_stat,stage_override=6 if maneuver_defense==def_stat else None)
        if AURA.sword(self,attacker,move):dr_val=None
        import cheerleader as CHEER
        excited_dr=CHEER.damage_reduction(self,target,attacker,move,_reaction_event)
        if dr_val is not None:
            dr_val += __import__('commander_orders').reduction(target)
            dr_val += __import__('fortress').damage_reduction(self,target)
            dr_val += __import__('commander_orders').sentinel_reduction(self,target,_reaction_event)
        if excited_dr and dr_val is not None:dr_val+=excited_dr
        if dr_val is not None:dr_val+=rider_overrun['reduction']
        if dr_val is not None:
            dr_val+=TASK.bonus(target,'dr')+TASK.pain_reduction(self,attacker,target,move,_reaction_event)
        class_dr = CLASS_PASSIVE.damage_reduction(self,attacker,target,actual_move,mult,crit)
        if class_dr and dr_val is not None:
            dr_val += class_dr
            self.log(f"    클래스 패시브 피해 감소 {class_dr}", "class-passive/damage-reduction")
        survival_dr = __import__('survivalist_class').damage_reduction(self,attacker,target,actual_move)
        if survival_dr and dr_val is not None:
            dr_val += survival_dr
            self.log(f"    지형 재능 피해 감소 {survival_dr} ({actual_move['type']} 공격 한정)", "feat/지형-재능")
        idr = ITEMS.item_damage_reduction(target, actual_move, engine=self)
        if idr and dr_val is not None:
            dr_val += idr
            self.log(f"    도구 피해 감소 {idr} ({mtype}/{move['class']} 한정)", "item/damage_reduction")
        chef=FOOD.chef_attack_commit(self,attacker,target,move,chef_plan,damage_reduction_allowed=dr_val is not None)
        if chef['bonus_damage']:
            roll_mod += chef['bonus_damage']
            self.log(f"    요리사 간식 추가 피해 +{chef['bonus_damage']}","ch04/chef-snack")
        if chef['damage_reduction'] and dr_val is not None:
            dr_val += chef['damage_reduction']
            self.log(f"    요리사 간식 피해 감소 +{chef['damage_reduction']}","ch04/chef-snack")
        roll_mod+=__import__('coordinator').damage_bonus(self,attacker,move)
        roll_mod+=__import__('berserker').damage_bonus(self,attacker,target,move)
        roll_mod+=__import__('fortress').outgoing_penalty(attacker)
        roll_mod+=__import__('fortress').guardian_damage(self,attacker,target,move,_reaction_event)
        roll_mod+=__import__('skirmisher').vanguard_bonus(self,attacker,target)
        if _reaction_event is not None:_reaction_event['coordinator_formula']={'dice':dice_part,'attack':attack_value,'modifiers':roll_mod+infatuation_mod,'defense':def_val,'reduction':0 if AURA.sword(self,attacker,move) else dr_val}
        rolled_total=dice_part+attack_value+roll_mod+infatuation_mod
        roll_mod+=TA.fountain(self,attacker,actual_move,rolled_total)-rolled_total
        total = dice_part + attack_value + roll_mod + infatuation_mod
        import combat_damage as DAMAGE
        defended = DAMAGE.defend(dice=dice_part, attack=attack_value,
            modifiers=roll_mod+infatuation_mod, defense=def_val, reduction=0 if AURA.sword(self,attacker,move) else dr_val)
        total, after_def = defended['total'], defended['after_defense']
        resist_steps+=berry_resistance
        resist_steps+=__import__('earned_status_choices').outgoing_steps(self,attacker)
        if (_reaction_event is not None and _reaction_event.get('attacker') is attacker
                and _reaction_event.get('target') is target and after_def>0 and mult):
            type_table=self.r.mech('combat/type-effectiveness')['multiplier_by_net_steps']
            step_lookup={float(value):int(key) for key,value in type_table.items()}
            effective=type_table[str(max(-3,min(3,step_lookup[mult]-resist_steps)))]
            resist_steps+=DUELIST.type_steps(self,attacker,target,move,effective)
        if __import__('commander_orders').perfect_for_move(self,attacker,move) and mult:
            actual_step={1.0:0,1.5:1,2.0:2,3.0:3,0.5:-1,0.25:-2,0.125:-3}.get(mult,0)-resist_steps
            if actual_step<0:resist_steps+=1
        if resist_steps:
            te = self.r.mech("combat/type-effectiveness")["multiplier_by_net_steps"]
            steps = {1.0: 0, 1.5: 1, 2.0: 2, 3.0: 3, 0.5: -1, 0.25: -2, 0.125: -3}.get(mult, 0) - resist_steps
            mult = te[str(max(-3, min(3, steps)))] if mult else 0
            self.log(f"    특성 저항 {resist_steps}단계 → 타입 ×{mult}", "effect/resistance_step")
        # The selected Population Bomb option belongs to this actual damage occurrence.
        # Immunity remains distinct from resistance.
        damage_occurrence={'attacker':attacker,'target':target,'move':move}
        mult=REACTIONS.resistance_floor(self,damage_occurrence,mult)
        if _precision_observation is not None:_precision_observation["type_multiplier"] = mult
        other_multiplier = EXT.multiplier_hook(self, attacker, move, mm, ctx)
        adjustment = self.rulings.consume("damage", attacker.name, self)
        final = DAMAGE.scale(after_defense=after_def,type_multiplier=mult,other_multiplier=other_multiplier,adjustment=adjustment)
        TRACE.calculation(self, source=move["id"], damage_class=move["class"], damage_type=mtype,
            attack_source_id=atk_src.entity_id, defense_stat=def_stat,
            damage_base=db, dice_part=dice_part, attack_stat=atk_stat,
            attack_value=attack_value, roll_modifier=roll_mod, infatuation_modifier=infatuation_mod,
            total=total, defense=def_val, damage_reduction=dr_val, after_defense=after_def,
            type_multiplier=mult, other_multiplier=other_multiplier, adjustment=adjustment, result=final)
        floor_effect = any(e.get("type") == "damage_floor" for e in mm.get("effects_exec", []))
        if _reaction_event is not None:
            resisted_mult = REACTIONS.resistance_multiplier(self, mult,event=damage_occurrence)
            resisted = None if resisted_mult is None else DAMAGE.scale(after_defense=after_def,type_multiplier=resisted_mult,other_multiplier=other_multiplier,adjustment=adjustment)
            _reaction_event.update(damage=final, resisted_damage=resisted, attack_stat=atk_stat, context=ctx, damage_floor=floor_effect, actual_damage_type=mtype,
                damage_formula={'after_defense':after_def,'multiplier':mult,'other_multiplier':other_multiplier,'adjustment':adjustment})
        else:
            final = self.rulings.run_hooks("before_damage", final, dict(ctx, final=final), self)
            if floor_effect:
                final = min(final, max(0, target.hp - 1))
        self.log(f"    + {atk_stat} {atk_src.staged(atk_stat)} = {total}, - {target.name} {def_stat} {target.staged(def_stat)}{(' - DR ' + str(target.damage_reduction)) if target.damage_reduction else ''} = {after_def}, 타입 ×{mult} = {final}", why)
        return final

    @TRACE.operation('attack_damage_application','attacker','target','move','crit','set_damage')
    @__import__('cheerleader').native_action
    @__import__('conquerors_march').damage_scope
    def resolve_attack_damage(self, attacker, target, move, crit=False, set_damage=False, intercepted=False, _heavy_context=None, _passive_event=None, _precision_event=None, _damage_observation=None, _defense_token=None, _completion_id=None):
        """Apply one hit and its responses. intercepted means a successful maneuver already resolved by the caller."""
        if __import__('defense_curl').critical_immune(target) or __import__('declarative_move_contracts').defensive_critical_immunity(target):crit=False
        if _damage_observation is not None and not isinstance(_damage_observation, dict):
            raise ValueError("damage observation must be a mapping")
        if _defense_token is not None:
            intercepted=DEFENSE.require_damage_receipt(self,_defense_token,attacker,target,move)
        PASSIVE_EVENTS.ensure_clear(self)
        LEAGUE.check_action(self, attacker, target, move['id'])
        HEAVY.ensure_clear(self)
        HEAVY.validate_native_receipt(self,_heavy_context,attacker,target,move)
        import taskmaster_gambit as GAMBIT,conditional_damage_base as CONDITIONAL_DB
        import combat_damage as DAMAGE,attack_damage_history as DAMAGE_HISTORY
        cached=GAMBIT.restore_damage(self,attacker,target,move,_passive_event)
        if cached is None:
            import conditional_damage_base as CONDITIONAL_DB
            conditional_db_plan = CONDITIONAL_DB.prepare(self, attacker, target, move)
            event = dict(attacker=attacker, target=target, move=move, intercepted=intercepted is True, passive_event=_passive_event)
            event['athlete_defense_token']=_defense_token
            precision_facts = {}
            import enduring_resilience as RESILIENCE
            import taskmaster as TASK
            damage_crit=TASK.critical_damage(self,attacker,target,move,crit)
            resolved_damage_move=__import__('struggle_capabilities').prepare(self,attacker,__import__('aura_guardian').damage_move(self,attacker,move))
            damage = __import__('conquerors_march').damage_selection(self,event,precision_facts)
            lean_deferred=False
            if damage is None:
                damage = __import__('coordinator').calculate_damage(self,attacker,target,move,damage_crit,set_damage,event,precision_facts)
                if "damage" in event:
                    import blessing_effects as BLESSINGS
                    import weather_blessings as WEATHER_BLESSINGS
                    damage = WEATHER_BLESSINGS.select_damage(self,event,_heavy_context)
                    damage = BLESSINGS.select_damage(self,event)
                    damage = REACTIONS.select_mettle(self, event)
                    __import__('conquerors_march').damage_selection(self,event,precision_facts,damage)
            if __import__('setup_move_state').physical_immunity(target,resolved_damage_move.get('class')):
                damage=0
                precision_facts['nullification']='acid_armor'
            lean_deferred,damage=__import__('conquerors_march').prepare_lean(self,event,damage,_heavy_context,_precision_event,precision_facts)
            if "damage" in event and not lean_deferred:damage=REACTIONS.finalize_choice(self,event,damage)
            if __import__('setup_move_state').physical_immunity(target,resolved_damage_move.get('class')):
                damage=0
                precision_facts['nullification']='acid_armor'
            import precise_actions as PRECISE
            if not lean_deferred:PRECISE.damage_hit(self,attacker,target,move,_precision_event,precision_facts,damage)
            if precision_facts.get("hit_prevented"):
                if _damage_observation is not None:_damage_observation['hit_prevented']=True
                return 0
            actual_type = event.get("actual_damage_type",move["type"])
            actual_move = dict(move,type=actual_type)
            actual_multiplier = event.get("damage_formula",{}).get("multiplier",precision_facts.get("type_multiplier",0))
            if event.get("mettle_selected"):
                actual_multiplier = REACTIONS.resistance_multiplier(self,actual_multiplier,event=event)
            substitute=__import__('substitute').receive_damage(self,attacker,target,move,damage)
            if substitute is not None:
                if _damage_observation is not None:
                    _damage_observation['substitute']=substitute
                    if _completion_id is not None:
                        _damage_observation['substitute_damage']=__import__('move_completion').record_substitute_damage(
                            self,attacker,target,_completion_id,_passive_event,substitute,
                            native_context=_heavy_context,move=move)
                return damage
            if not lean_deferred:PASSIVE_EVENTS.note_damage_request(self,_passive_event,damage)
            passive_before = PASSIVE_EVENTS.capture(target) if _passive_event is not None else None
            import combat_damage as DAMAGE
            damage_before = DAMAGE.observe(target)
            import attack_damage_history as DAMAGE_HISTORY
        else:
            event=cached['event'];precision_facts=cached['precision_facts']
            conditional_db_plan=cached['conditional_db_plan'];damage=cached['damage']
            actual_type=cached['actual_type'];actual_multiplier=cached['actual_multiplier']
            actual_move=dict(move,type=actual_type);lean_deferred=False
            passive_before=PASSIVE_EVENTS.capture(target) if _passive_event is not None else None
            damage_before=DAMAGE.observe(target)
            import taskmaster as TASK
        with DAMAGE.native_hit(target) as native_damage, DAMAGE_HISTORY.native_application(self,attacker,target,move,_heavy_context,precision_event=_precision_event) as history_context:
            paired_receipt,damage=__import__('conquerors_march').apply_lean_pair(self,event,damage,_heavy_context,damage_before)
            if paired_receipt is None:
                GAMBIT.retain_damage(self,attacker,target,move,_passive_event,
                    {'event':event,'precision_facts':precision_facts,'conditional_db_plan':conditional_db_plan,
                     'damage':damage,'actual_type':actual_type,'actual_multiplier':actual_multiplier},_precision_event)
                paired_receipt=TASK.apply_gambit_damage(self,attacker,target,move,damage,_heavy_context,damage_before,actual_damage_type=actual_type)
            if paired_receipt is None:
                if GAMBIT.parent_refresh_needed(self,attacker,target,move,_passive_event,_heavy_context):
                    return {'_gambit_parent_receipt_refresh':_passive_event}
                application=HEAVY.apply_attack_damage(self, attacker, target, damage, move,
                    producer=HEAVY.Producer.RESOLVED_HIT,
                    remainder="finish_mettle and remaining use_move effects/reactions have not run",
                    native_context=_heavy_context,actual_damage_type=actual_type)
                if isinstance(application,dict) and application.get('source')==__import__('channeler').PAIN:
                    if _damage_observation is not None:_damage_observation['channeler_pain']=application
                    return 0
            if paired_receipt is not None and paired_receipt.get('channeler_pain'):
                if _damage_observation is not None:_damage_observation['channeler_pain']=paired_receipt['channeler_pain']
                return 0
            damage_receipt = paired_receipt if paired_receipt is not None else DAMAGE.application(requested=damage, before=damage_before,
                after=DAMAGE.observe(target), source=move['id'], damage_class=move['class'])
            if history_context is not None:
                DAMAGE_HISTORY.record(self,attacker,target,move,damage_receipt,
                    event.get('actual_damage_type',move['type']),history_context,
                    completion_id=_completion_id,multiplier=actual_multiplier)
                import cleanse_tags as CLEANSE
                CLEANSE.after_weapon_damage(self,attacker,target,move,damage_receipt,
                    event.get('cleanse_tag_weapon'),history_context)
        if native_damage:
            damage_receipt['native_damage'] = dict(DAMAGE.validate_native_hit(native_damage))
        __import__('catalog_move_states').rage_damage(self,attacker,target,move,damage_receipt)
        CONDITIONAL_DB.commit(attacker, target, move, conditional_db_plan, damage_receipt)
        __import__('food_effects').berry_after_hit(self,attacker,target,move,event,damage_receipt)
        __import__('hex_maniac').record_boost(self,attacker,target,move,conditional_db_plan,_passive_event)
        CONDITIONAL_DB.record_attack_damage(self, attacker, target, damage_receipt)
        import damage_coats as DAMAGE_COATS
        DAMAGE_COATS.after_damage(self,attacker,target,actual_move,damage_receipt,type_multiplier=actual_multiplier)
        import optional_physical_equipment as OPTIONAL_EQUIPMENT
        OPTIONAL_EQUIPMENT.observe_attack_damage(self,attacker,target,move,damage_receipt)
        TRACE.calculation(self, damage_application=damage_receipt)
        import duelist as DUELIST
        DUELIST.observe_damage(self,attacker,target,move,event,damage_receipt)
        if _damage_observation is not None:
            _damage_observation.update(damage_receipt)
            _damage_observation.update(actual_damage_type=actual_type,type_multiplier=actual_multiplier)
        if _passive_event is not None:
            passive_after=PASSIVE_EVENTS.capture(target)
            if paired_receipt is not None and TASK.gambit_side(self,attacker,target,move)=='incoming':
                passive_after=self._taskmaster_gambit['incoming_passive_after']
            PASSIVE_EVENTS.note_attack(self, _passive_event, passive_before, passive_after, damage)
        event["damage_applied"] = True
        import cheerleader as CHEER
        CHEER.finish_damage(self,event,damage_receipt)
        import class_actor_state_reactions as CLASS_REACTIONS
        CLASS_REACTIONS.observe_attack_damage(self, event, damage_receipt, critical=crit)
        if crit:
            import stamina as STAMINA
            STAMINA.observe(self,target,'critical_hit',move_id=move['id'],dealt=damage)
        REACTIONS.finish_mettle(self, event)
        __import__('capture_specialist').after_attack(self,attacker,target,move,damage_receipt,_heavy_context)
        import taskmaster as TASK
        TASK.after_attack(self,attacker,target,move,critical=crit,damage=damage)
        if TASK.gambit_side(self,attacker,target,move)=='incoming':self._taskmaster_gambit=None
        return damage

    @TRACE.operation('non_attack_hp_loss','c','amount','source','unpreventable','loss_kind')
    def lose_hp(self, c, amount, source="damage", *, unpreventable=False, loss_kind="loss"):
        import ability_state_projection as PROJECTION,state_grants as GRANTS
        import keep_fighting as KEEP
        if PROJECTION.hp_change_interested(c) or KEEP.interested(self,c) or __import__('enduring_soul').interested(self,c) or __import__('type_ace').hp_interested(self,c) or c.spec.get('perseverance_choice') or __import__('berserker').acquired(c,__import__('berserker').FIGHT) or __import__('fashion_items').focus_interested(self,c):
            return GRANTS.transition(self,c,lambda e,actor:e._lose_hp(actor,amount,source,unpreventable=unpreventable,loss_kind=loss_kind),include_rulings=True,include_grid=self.grid is not None)
        return self._lose_hp(c,amount,source,unpreventable=unpreventable,loss_kind=loss_kind)

    def _lose_hp(self, c, amount, source="damage", *, unpreventable=False, loss_kind="loss"):
        """Ordinary loss consumes temporary HP; an HP-setting adapter changes actual HP.

        HP setting is HP loss: a selected loss cap can reduce its decrease.
        Explicit unpreventable sources bypass prevention; forced faint is separate.
        Percentage loss keeps ordinary loss layers but cannot overflow a boss bar.
        Marker/life transitions remain shared, without attack-damage reactions.
        Unpreventable loss bypasses damage caps; temporary HP follows the selected
        persistent GM policy (default: temporary HP first).
        """
        import partial_entities as PARTIAL
        PARTIAL.require_complete(c, "lose_hp")
        import supplemental_state as SUPPLEMENTAL
        SUPPLEMENTAL.require_actor_access(self, c, "lose_hp")
        import actor_templates as TEMPLATES
        TEMPLATES.require_ordinary(c, "lose_hp")
        CHECKS.integer(amount, "HP loss", 0)
        if type(unpreventable) is not bool:
            raise ValueError("unpreventable must be an explicit boolean")
        if loss_kind not in ("loss", "percentage", "hp_setting"):
            raise ValueError("loss_kind must be loss, percentage or hp_setting")
        import taskmaster as TASK
        if not unpreventable and loss_kind in ('loss','percentage') and TASK.immune_loss(c):return
        if not unpreventable and loss_kind in ('loss','percentage') and __import__('coordinator').prevent_loss(self,c,source):return
        TEMP_HP.ensure_certain(self, c)
        if not unpreventable:
            amount = EXT.cap_damage(self, c, amount, loss_kind=loss_kind)
        if loss_kind in ("loss", "percentage"):
            amount = TEMP_HP.loss_remainder(self, c, amount, unpreventable=unpreventable)
        before, maxhp = c.hp, c.base_max_hp          # 표시점은 실제 최대 체력 기준
        import keep_fighting as KEEP
        proposed = before - amount
        if not unpreventable:
            proposed=__import__('endure').replace_hp(self,c,before,proposed,source=source,loss_kind=loss_kind)
            proposed=KEEP.replace_hp(self,c,before,proposed,source=source,loss_kind=loss_kind,amount=amount,unpreventable=False)
            proposed=__import__('fashion_items').replace_hp(self,c,before,proposed)
        c.hp = proposed
        import bandages as BANDAGES
        __import__('type_ace').hp_changed(self,c,before,maxhp)
        __import__('athlete').hp_changed(self,c,before,maxhp)
        BANDAGES.on_hp_change(self,c,before,c.hp)
        inj = self.marker_injuries(c, before, c.hp, maxhp)
        __import__('endure').after_damage(self,c)
        import swarm_transitions as SWARM
        SWARM.after_hp_change(self,c,before,source)
        import boss_transitions as BOSS
        BOSS.after_hp_change(self,c,before,source,carry_over=loss_kind == "loss")
        import ability_state_projection as ABILITY_STATE_PROJECTION
        ABILITY_STATE_PROJECTION.after_hp_change(self,c)
        self.log(f"    {c.name} 체력 {before} → {c.hp} ({source})" + (f", 표시점 부상 +{inj}" if inj else ""), "combat/hit-point-loss")
        __import__('trickster').loss(self,c,before,source)
        self.check_fainted(c)


    @TRACE.operation('damage_application','c','amount')
    def take_damage(self, c, amount):
        import partial_entities as PARTIAL
        PARTIAL.require_complete(c, "take_damage")
        import control_mount as MOUNT,state_grants as GRANTS,ability_state_projection as PROJECTION
        projection_hp=PROJECTION.hp_change_interested(c)
        import keep_fighting as KEEP
        keep_hp=KEEP.interested(self,c) or __import__('enduring_soul').interested(self,c) or __import__('type_ace').hp_interested(self,c) or bool(c.spec.get('perseverance_choice')) or __import__('fashion_items').focus_interested(self,c)
        if MOUNT.managed_subject(c) or '잠듦' in c.conditions or projection_hp or keep_hp:
            return GRANTS.transition(self,c,lambda e,target:e._take_damage(target,amount),include_rulings=projection_hp or keep_hp,include_grid=(projection_hp or keep_hp) and self.grid is not None)
        return self._take_damage(c,amount)

    def _take_damage(self, c, amount):
        """한 번의 타격. 부상 판정은 타격 직전의 최대 체력을 기준으로 한다(같은 타격 안에서 부상이 최대 체력을 깎아 표시점을 옮기지 않도록)."""
        import partial_entities as PARTIAL
        PARTIAL.require_complete(c, "take_damage")
        import supplemental_state as SUPPLEMENTAL
        SUPPLEMENTAL.require_actor_access(self, c, "take_damage")
        import actor_templates as TEMPLATES
        TEMPLATES.require_ordinary(c, "take_damage")
        CHECKS.integer(amount, "damage HP", 0)
        TEMP_HP.ensure_certain(self, c)
        import combat_damage as DAMAGE,attack_damage_history as HISTORY
        sleep_before=DAMAGE.observe(c)
        inj = self.r.mech("combat/injuries")
        amount = EXT.cap_damage(self, c, amount)
        __import__('focus_punch').observe_damage(c,amount)
        import bandages as BANDAGES
        BANDAGES.on_damage(self,c,amount)
        amount = TEMP_HP.absorb(self, c, amount)
        before, maxhp = c.hp, c.base_max_hp          # 대규모 데미지·표시점은 실제 최대 체력 기준 (부상 패널티는 회복 상한에만)
        massive = amount >= EXACT.multiply(self.formula("massive_damage"),maxhp)
        DAMAGE.observe_native_hit(c, amount=amount, maximum_hp=maxhp, massive=massive)
        import stamina as STAMINA
        if massive:
            STAMINA.observe(self,c,'massive_damage',amount=amount,maximum_hp=maxhp)
        import keep_fighting as KEEP
        proposed=__import__('endure').replace_hp(self,c,before,before-amount,source='attack_damage',loss_kind='damage')
        proposed = KEEP.replace_hp(self,c,before,proposed,source='attack_damage',loss_kind='damage',amount=amount)
        proposed = __import__('capture_specialist').replace_knockout(self,c,before,proposed)
        c.hp = __import__('fashion_items').replace_hp(self,c,before,proposed,move_damage=True)
        __import__('type_ace').hp_changed(self,c,before,maxhp)
        __import__('athlete').hp_changed(self,c,before,maxhp)
        BANDAGES.on_hp_change(self,c,before,c.hp)
        n_inj = 0
        import actor_templates as TEMPLATES
        if (not TEMPLATES.injuries_immune(c) and not EXT.massive_damage_injury_immune(c)
                and massive and not __import__('endure').prevent_massive(self,c)):
            import precise_actions as PRECISE
            retained=PRECISE.gain_injury(self,c,1,"combat/massive-damage")
            n_inj += retained
            self.log(f"    대규모 데미지({amount} ≥ 최대 체력 {maxhp}의 50%) → 부상 +{retained}", "combat/injuries")
        n_inj += self.marker_injuries(c, before, c.hp, maxhp)
        __import__('endure').after_damage(self,c)
        import swarm_transitions as SWARM
        SWARM.after_hp_change(self,c,before,"attack_damage")
        import boss_transitions as BOSS
        BOSS.after_hp_change(self,c,before,"attack_damage",attack=True)
        import ability_state_projection as ABILITY_STATE_PROJECTION
        ABILITY_STATE_PROJECTION.after_hp_change(self,c)
        self.log(f"    {c.name} 체력 {before} → {c.hp}" + (f", 부상 {c.injuries}개 → 최대 체력 {c.max_hp}" if n_inj else ""), "combat/damage-formula")
        self.check_fainted(c)
        HISTORY.wake_after_loss(self,c,None,sleep_before)
        EXT.after_damage(self, c)
        import control_mount as MOUNT
        MOUNT.notify(self,c,'damage',amount=amount,max_hp=maxhp)
        return n_inj

    def marker_injuries(self, c, before, after, maxhp):
        import actor_templates as TEMPLATES
        if TEMPLATES.marker_injuries_immune(c):
            return 0
        inj = self.r.mech("combat/injuries")
        markers = [0.5, 0.0, -0.5, -1.0]
        f = -1.5
        while f * maxhp > after - 1:
            markers.append(f)
            f -= 0.5
        n = 0
        for fr in markers:
            m = fr * maxhp
            if before > m >= after:
                n += 1
        if n:
            import precise_actions as PRECISE
            n=PRECISE.gain_injury(self,c,n,"combat/hit-point-markers")
            self.log(f"    체력 표시점 통과 {n}개 → 부상 +{n} (총 {c.injuries})", "combat/injuries")
        return n

    def check_fainted(self, c):
        import taskmaster as TASK
        if TASK.defer_faint(self,c) or __import__('conquerors_march').defer_faint(self,c):return
        import keep_fighting as KEEP,state_grants as GRANTS
        if c.hp<=0 and (KEEP.interested(self,c) or __import__('enduring_soul').interested(self,c) or __import__('ability_exchange_contracts').interested(self,c,c) or __import__('berserker').acquired(c,__import__('berserker').FIGHT)):
            return GRANTS.transition(self,c,lambda e,actor:e._check_fainted(actor),include_rulings=True,include_grid=self.grid is not None)
        return self._check_fainted(c)

    def _check_fainted(self, c):
        self.time_actors([c])
        import campaign_injury_policy as CAMPAIGN_INJURY
        CAMPAIGN_INJURY.enforce(self,c)
        LIFE.sync(self,c)
        import homebrew_state as HOME
        HOME.on_faint(c)
        import grapple_state as GRAPPLE
        GRAPPLE.boundary(self)
        __import__('ability_exchange_contracts').refresh(self)
        __import__('ability_control_contracts').refresh(self)

    @TRACE.operation('healing','c','amount','source_kind','round_offset_seconds')
    def heal(self, c, amount, *, source_kind='unspecified', round_offset_seconds=None):
        import partial_entities as PARTIAL
        PARTIAL.require_complete(c, "heal")
        import ability_state_projection as PROJECTION,state_grants as GRANTS
        if PROJECTION.hp_change_interested(c):
            return GRANTS.transition(self,c,lambda e,actor:e._heal(actor,amount,source_kind=source_kind,round_offset_seconds=round_offset_seconds),include_rulings=True,include_grid=self.grid is not None)
        return self._heal(c,amount,source_kind=source_kind,round_offset_seconds=round_offset_seconds)

    def _heal(self, c, amount, *, source_kind='unspecified', round_offset_seconds=None):
        CHECKS.integer(amount,'healing HP',0)
        if source_kind not in ('ordinary_item','move','feature','explicit_revive','rest','unspecified'):
            raise ValueError('unknown healing source kind')
        import partial_entities as PARTIAL
        PARTIAL.require_complete(c, "heal")
        import supplemental_state as SUPPLEMENTAL
        SUPPLEMENTAL.require_actor_access(self, c, "heal")
        self.time_actors([c])
        if round_offset_seconds is not None:
            self.at_round_offset(round_offset_seconds)
        before_hp=c.hp
        gained = LIFE.heal(self,c,amount,source_kind)
        if gained:
            import ability_state_projection as ABILITY_STATE_PROJECTION
            ABILITY_STATE_PROJECTION.after_hp_change(self,c)
        if (self.round_start_seconds is not None and round_offset_seconds is None
                and source_kind == 'ordinary_item' and before_hp <= 0 and gained > 0
                and c.faint_recovery_seconds is not None and not c.faint_recovery_pending):
            c.faint_recovery_pending = 'within_round_healing_timestamp_unresolved'
            c.faint_recovery_birth_round = self.round_no
        return gained

    def revive(self, c, hp):
        import ability_state_projection as PROJECTION,state_grants as GRANTS
        if PROJECTION.hp_change_interested(c):
            return GRANTS.transition(self,c,lambda e,actor:e._revive(actor,hp),include_rulings=True,include_grid=self.grid is not None)
        return self._revive(c,hp)

    def _revive(self, c, hp):
        import partial_entities as PARTIAL
        PARTIAL.require_complete(c,'revive')
        import supplemental_state as SUPPLEMENTAL
        SUPPLEMENTAL.require_actor_access(self,c,'heal')
        before_hp=c.hp
        result=LIFE.revive(self,c,hp)
        if c.hp!=before_hp:
            import ability_state_projection as ABILITY_STATE_PROJECTION
            ABILITY_STATE_PROJECTION.after_hp_change(self,c)
        return result

    @TRACE.operation('integrity_recovery')
    def repair_integrity(self, entity_id, amount, *, source, eligible, reason):
        import recovery_resolution as RECOVERY
        return RECOVERY.repair_integrity(self,entity_id,amount,source=source,
                                         eligible=eligible,reason=reason)

    def resolve_fall_ruling(self, actor, **options):
        import environmental_effects as ENVIRONMENT
        return ENVIRONMENT.resolve_fall_ruling(self,actor,**options)

    def walk_it_off(self, actor, *, duration_minutes=None, reason=None):
        PASSIVE_EVENTS.ensure_clear(self)
        LEAGUE.check_boundary(self, 'walk_it_off')
        return __import__('walk_it_off').act(self,actor,duration_minutes=duration_minutes,reason=reason)

    def recover_injury(self, actor, *, source='natural', **options):
        import injury_recovery as INJURY
        if source=='natural':
            if options:raise ValueError('natural injury recovery uses actual observed time')
            return INJURY.recover_naturally(self,actor)
        if source=='trainer_ap':return INJURY.recover_with_ap(self,actor,**options)
        raise ValueError('unknown injury recovery source')

    def observe_breathing(self, actor, **options):
        import environmental_effects as ENVIRONMENT
        return ENVIRONMENT.observe_breathing(self,actor,**options)

    def observe_vacuum_exposure(self, actor, **options):
        import environmental_capabilities as CAPABILITIES
        return CAPABILITIES.observe_vacuum(self,actor,**options)

    def resolve_vacuum_injury_check(self, actor, **options):
        import environmental_capabilities as CAPABILITIES
        return CAPABILITIES.resolve_vacuum_check(self,actor,**options)

    def observe_environment(self, region_id, facts, **options):
        import environment_derive as ED
        return ED.observe_region(self,region_id,facts,**options)

    def bind_environment(self, actor, declaration, **options):
        import environment_derive as ED
        return ED.bind(self,actor,declaration,**options)

    def environment_context(self, actor):
        import environment_derive as ED
        return ED.context(self,actor)

    def change_environment(self, region_id, changes, **options):
        import environment_change as EC
        return EC.change(self,region_id,changes,**options)

    def transfer_environment(self, actor, region_id, **options):
        import environment_change as EC
        return EC.transfer(self,actor,region_id,**options)

    def falling_damage(self, actor, **options):
        import environmental_effects as ENVIRONMENT
        return ENVIRONMENT.fall(self,actor,**options)

    def preflight_advance_time(self, seconds, combatants=()):
        """Validate a proposed shared interval without registering or changing actors."""
        __import__('movement_actions').ensure_commands_boundary(self)
        ACTION.ensure_resolutions_clear(self)
        PASSIVE_EVENTS.ensure_clear(self)
        EFFECT_CONTRACTS.ensure_clear(self)
        LEAGUE.check_boundary(self, 'advance_time')
        import maneuver_grants as MG
        MG.ensure_clear(self)
        HEAVY.ensure_clear(self)
        CHECKS.integer(seconds,'elapsed seconds',0)
        if self.round_start_seconds is not None and self.elapsed_seconds + seconds > self.round_start_seconds + 10:
            raise ValueError('elapsed interval exceeds the open round')
        known = [*self._time_actors, *(getattr(self, 'everyone', None) or []),
                 *(getattr(self.gm, 'everyone', None) or []), *combatants]
        actors = list({id(c): c for c in known}.values())
        import bandages as BANDAGES
        for c in actors:BANDAGES.preflight_advance(self,c)
        import environmental_effects as ENVIRONMENT
        for c in actors:ENVIRONMENT.preflight_advance(self,c,seconds)
        import item_maturation as MATURATION
        for c in actors:MATURATION.preflight(self,c,seconds)
        import effect_lifetime_policy as EFFECT_TIME
        import world_entities as WORLD
        EFFECT_TIME.validate_world(self,WORLD.actor_index(self))
        return actors

    def advance_time(self, seconds, combatants=(), *, request_id=None, source=None, resumable=False):
        """Commit all shared clocks and timed consequences as one transition."""
        combatants=tuple(combatants)
        import clock_invocations as CLOCK
        if type(resumable) is not bool:raise ValueError('explicit resumable clock option required')
        if resumable:
            return CLOCK.advance(self,seconds,combatants,request_id=request_id,source=source or 'world/clock')
        declared=None
        if source is not None or request_id is not None:
            declared=CLOCK.intent(seconds,combatants,source or 'world/clock')
            prior=CLOCK.replay(self,request_id,declared)
            if prior is not None:return prior
        actors = self.preflight_advance_time(seconds, combatants)
        import state_grants as GRANTS
        def apply(staged, primary, *participants):
            if declared is None:return staged._advance_time(seconds, participants)
            row=CLOCK.begin(staged,declared,request_id,participants)
            previous=getattr(staged,CLOCK.ACTIVE,None)
            setattr(staged,CLOCK.ACTIVE,row['id'])
            try:staged._advance_time(seconds, participants)
            finally:setattr(staged,CLOCK.ACTIVE,previous)
            row.update(end=staged.elapsed_seconds,status='complete')
            CLOCK.validate(staged)
            return row
        return GRANTS.transition(self, actors[0] if actors else None,
                                 apply, participants=actors)

    def resolve_effect_condition(self, actor, receipt, **observation):
        return FX.resolve_condition(self,actor,receipt,**observation)

    def _advance_time(self, seconds, combatants=()):
        """Internal staged interval; external callers use advance_time."""
        actors = self.preflight_advance_time(seconds, combatants)
        import effect_lifetime_policy as EFFECT_TIME
        EFFECT_TIME.reconcile(self)
        import crafting_products as PRODUCTS
        PRODUCTS.reconcile(self)
        end_at = self.elapsed_seconds + seconds
        if not seconds:
            self._advance_time_slice(0,actors)
            EFFECT_TIME.boundary(self,'time_advanced')
        while self.elapsed_seconds < end_at:
            interval = min(EFFECT_TIME.next_interval(self,end_at),PRODUCTS.next_interval(self,end_at))
            self._advance_time_slice(interval,actors)
            EFFECT_TIME.boundary(self,'time_advanced')

    def _advance_time_slice(self, seconds, actors):
        """One continuous interval ending at an actual declared due instant."""
        import special_entities as SPECIAL
        sentry_plan = SPECIAL.preflight_sentries(self)
        import item_maturation as MATURATION
        maturation_plans=[(c,MATURATION.preflight(self,c,seconds)) for c in actors]
        self.time_actors(actors)
        import bandages as BANDAGES
        import environmental_effects as ENVIRONMENT
        import injury_recovery as INJURY
        for c in actors:
            LIFE.advance(self,c,seconds)
            TEMP_HP.advance(self,c,seconds)
        self.elapsed_seconds += seconds
        __import__('csv_item_form_contracts').elapsed(self)
        import state_grants as G
        G.sync_capability_losses(self)
        import environmental_item_state as ENVIRONMENTAL_ITEMS
        ENVIRONMENTAL_ITEMS.boundary(self,time_advanced=True)
        import crafting_products as PRODUCTS
        PRODUCTS.reconcile(self)
        for c in actors:INJURY.advance(self,c,seconds)
        for c in actors:ENVIRONMENT.advance(self,c)
        for c in actors:BANDAGES.advance(self,c)
        SPECIAL.expire_sentries(self, prepared=sentry_plan)
        for c,plan in maturation_plans:MATURATION.advance(self,c,plan)

    # ---------- 기술 사용 ----------
    def enter_gigantamax(self, actor, *, source_id, reason):
        import state_grants as GRANTS
        import gmax_moves as GMAX
        return GRANTS.transition(self,actor,
            lambda staged,subject:GMAX.enter(staged,subject,source_id=source_id,reason=reason))

    def exit_gigantamax(self, actor, *, reason):
        import state_grants as GRANTS
        import gmax_moves as GMAX
        return GRANTS.transition(self,actor,
            lambda staged,subject:GMAX.exit(staged,subject,reason=reason))

    def use_gmax_move_on(self, actor, primary, base_move_id, gmax_move_id, everyone, **options):
        import gmax_moves as GMAX
        return GMAX.activate(self,actor,primary,base_move_id,gmax_move_id,everyone,**options)

    def observe_setup_move_exit(self, actor, **observation):
        import setup_move_state as SETUP_MOVE
        return SETUP_MOVE.observe_exit(self,actor,**observation)

    def use_setup_move_on(self, actor, primary, move_id, everyone, *, setup_options=None,
                          weapon_id=None, struggle_choice=None, aim=None, appendage_id=None, set_damage=False):
        """Prepare or resume one source-owned Set-Up Move atomically."""
        if type(set_damage) is not bool:raise ValueError('boolean Set Damage declaration required')
        import field_effects as FIELD
        field_block = FIELD.native_move_block_reason(self, move_id, actor)
        if field_block:
            self.log(f"    {actor.name}: 전장 효과가 이 기술을 무효화", field_block)
            return 0
        import setup_move_state as SETUP_MOVE
        native = {"weapon_id": weapon_id, "struggle_choice": struggle_choice, "aim": aim, "appendage_id": appendage_id, "set_damage": set_damage}
        return SETUP_MOVE.activate(self, actor, primary, move_id, everyone,
                                   setup_options=setup_options, native_options=native)

    def burn_cleanse_tag(self, actor, instance_id, **options):
        import cleanse_tag_burn as CLEANSE_BURN
        return CLEANSE_BURN.burn(self, actor, instance_id, **options)

    def coup_de_grace(self, actor, target, move_id, **options):
        return self.use_move(actor,target,move_id,coup_de_grace=True,**options)

    @__import__('hp_setting_moves').preparation_scope
    @__import__('partial_entities').complete_move
    @_excluded_move_admission
    @__import__('recycle_move').native_move
    @__import__('wish_move').native_move
    @__import__('glitch_bender').native_move
    @__import__('warper').native_move
    @__import__('telepath').native_move
    @__import__('telekinetic').native_move
    @__import__('channeler').native_move
    @__import__('aura_guardian').native_move
    @__import__('taskmaster').native_move
    @__import__('duelist').attack_scope
    @__import__('defense_curl').native_move
    @OPTIONAL_WEAPONS.atomic_move
    @__import__('arcanist').atomic_move
    @__import__('marksman').atomic_move
    @__import__('skirmisher').atomic_move
    @__import__('fling_move').atomic_move
    @ACTION.resolved_move
    @__import__("cheerleader").native_action
    @__import__('electro_shot').native_move
    def use_move_on(self, attacker, primary, move_id, everyone, *, weapon_id=None, equipment_options=None, struggle_choice=None, aim=None, appendage_id=None, origin_part=None, set_damage=False, chain_steps=None, versatile_stat=None, weather_ball_type=None, use_radiated_type=None):
        pending=__import__('musician').no_accuracy_pending(self,attacker,move_id)
        if pending is not None:return pending
        if type(set_damage) is not bool:raise ValueError('boolean Set Damage declaration required')
        if set_damage and __import__('coordinator').damage_offer(self,attacker) is not None:raise ValueError('Coordinator rerolls a Damage Roll, not Set Damage')
        import body_state as BODY
        if origin_part is not None:BODY.part_cell(self,attacker,origin_part)
        import ability_state_projection as PROJECTION
        """격자 사용 시: 범위 키워드로 대상 집합을 구해 각각 처리. 근접/사거리 밖이면 먼저 접근."""
        if (not getattr(self,'_reactive_move_transaction',False)
                and (REACTIVE_ABILITIES.interested(self,attacker,primary)
                     or (not getattr(self, '_setup_move_scopes', ())
                         and __import__('herb_mushroom_rules').power_herb_interested(attacker))
                     or PROJECTION.native_move_interested(self,attacker,primary)
                     or __import__('enduring_soul').move_interested(self)
                     or __import__('berserker').move_interested(self,attacker,primary)
                     or DEFENSE.interested(self,attacker,primary)
                     or ABILITY_INTERRUPTS.interested(self)
                     or __import__('musician').drown_interested(self)
                     or ABILITY_REACTIONS.interested(self)
                     or __import__('ice_lake').interested(self,attacker,primary)
                     or __import__('type_ace').move_interested(self,attacker,primary)
                     or __import__('commander_orders').move_interested(self,attacker,primary)
                     or __import__('z_moves').interested(attacker)
                     or __import__('conquerors_march').interested(self)
                     or __import__('dynamic_chain_moves').declared(self.r.move_mech(move_id)[0])
                     or self.r.move_id(move_id) in ('move/배턴터치','move/웅크리기','move/페어리록'))):
            def staged(e,a,t):
                import state_grants as G
                group,options=G._stage_transition_payload(self,e,(everyone,dict(weapon_id=weapon_id,
                    equipment_options=equipment_options,struggle_choice=struggle_choice,aim=aim,appendage_id=appendage_id,origin_part=origin_part,set_damage=set_damage,versatile_stat=versatile_stat,weather_ball_type=weather_ball_type,chain_steps=chain_steps,use_radiated_type=use_radiated_type)))
                from inspect import unwrap
                return unwrap(Engine.use_move_on)(e,a,t,move_id,group,**options)
            return REACTIVE_ABILITIES.atomic_move(self,attacker,primary,staged)
        import partial_entities as PARTIAL
        PARTIAL.require_complete(attacker, "use_move_on")
        import invisibility_state as INVISIBILITY
        INVISIBILITY.require_move(self,attacker)
        import supplemental_state as SUPPLEMENTAL
        SUPPLEMENTAL.require_actor_access(self, attacker, "use_move_on")
        import actor_templates as TEMPLATES
        TEMPLATES.require_ordinary(attacker, "use_move_on")
        move_id = self._ruleset_move(attacker, move_id)
        __import__('natural_fighter').group_entry(self,attacker,move_id)
        import vision_impairment as VISION
        if move_id is not None:VISION.require_move(self,attacker,self.r.move(move_id))
        import setup_move_state as SETUP_MOVE
        SETUP_MOVE.require_native_scope(self,attacker,move_id)
        SETUP_MOVE.require_targetable(self,attacker,primary,move_id)
        import forced_move_lock as FORCED_MOVE
        if move_id is not None and not FORCED_MOVE.preflight_choice(
                self, attacker, move_id, everyone, ordinary=True):
            return 0
        if move_id=="move/트릭":
            if weapon_id is not None:raise ValueError("Trick has no weapon adaptation")
            import equipment_actions as EQUIPMENT
            return EQUIPMENT.use_trick(self,attacker,primary,everyone,equipment_options)
        if equipment_options is not None:raise ValueError("equipment target options belong only to Trick")
        if move_id is None:
            return 0
        import stellar_tera_blast as STELLAR_TERA
        stellar_choice = STELLAR_TERA.prepare(self,attacker,self.r.move(move_id),use_radiated_type).get(STELLAR_TERA.CHOICE)
        EXT.prepare_versatile_move(self,self.r.move(move_id),versatile_stat)
        __import__('weather_state').prepare_weather_ball(self,attacker,self.r.move(move_id),weather_ball_type)
        import body_state as BODY
        import ability_transitions as ABILITY_TRANSITIONS
        if move_id=="move/잠자기" and ABILITY_TRANSITIONS.active(attacker,"ability/불면"):
            raise ValueError("Insomnia prevents using Rest")
        import pokemon_party as POKEMON_PARTY
        POKEMON_PARTY.require_participation(self,attacker)
        import party_actions as PARTY_ACTIONS
        PARTY_ACTIONS.require_command(self,attacker,move_id)
        import pokemon_understanding as UNDERSTANDING
        UNDERSTANDING.require_activity(self,attacker,'move')
        import pokemon_activities as POKEMON
        loyalty_pending = POKEMON.loyalty_pending(self,attacker)
        if loyalty_pending is not None:return loyalty_pending
        PASSIVE_EVENTS.ensure_clear(self)
        EFFECT_CONTRACTS.ensure_clear(self)
        LEAGUE.check_boundary(self, 'use_move_on')
        HEAVY.ensure_clear(self)
        import pass_moves as PASS
        if PASS.is_pass(self.r.move(move_id)):
            raise ValueError('Pass Move requires use_pass_move and an actual complete path')
        import conditional_damage_base as CONDITIONAL_DB,bide as BIDE
        paid_resolution = (CONDITIONAL_DB.round_end_authorized(attacker,primary,move_id)
                           or BIDE.authorized(self,attacker,primary,move_id))
        allowed, reason = (True, '') if paid_resolution else FREQ.move_allowed(self, attacker, move_id, outside_combat=not self.encounter_active)
        if not allowed:
            self.log(f"  {attacker.name}: {reason}", "frequency/move")
            return 0
        import weapon_actions as WEAPONS
        import environ_moves as ENVIRON
        move = __import__('skirmisher').prepare_move(self,attacker,WEAPONS.prepare(self,attacker,ENVIRON.prepare(self,attacker,self.r.move(move_id)),weapon_id))
        move = __import__('arcanist').prepare(self,attacker,move)
        move = __import__('confusion_attacks').prepare(self,attacker,move)
        if stellar_choice is not None:move = dict(move,**{STELLAR_TERA.CHOICE:stellar_choice})
        import area_targets as AREA
        import stat_ace as STAT
        move = STAT.bind(self,attacker,move)
        move = __import__('telekinetic').project_move(self,attacker,move)
        if move_id=='move/일렉트로빔' and aim is None:aim=primary.pos
        move = AREA.bind(self,attacker,move,aim)
        move=__import__('native_area_hit_effects').bind(self,attacker,primary,move)
        aim=move.get('_area_aim',aim)
        import struggle_capabilities as STRUGGLE
        move = STRUGGLE.prepare(self,attacker,move,struggle_choice)
        import cleanse_tags as CLEANSE
        move = CLEANSE.prepare_appendage(self,attacker,move,appendage_id)
        import pokemon_move_edges as POKE_MOVE_EDGES
        move = POKE_MOVE_EDGES.prepare(self,attacker,move)
        move = __import__('weather_state').prepare_weather_ball(self,attacker,move,weather_ball_type)
        import gmax_moves as GMAX
        move = GMAX.prepare_native_move(self,attacker,move)
        move = __import__('musician').project_move(self,attacker,move)
        move = __import__('coordinator').prepare(self,attacker,move)
        move = __import__('researcher_fields').prepare_move(self,attacker,move)
        move = BODY.bind_origin(self,attacker,move,origin_part)
        move = __import__('martial_artist').prepare(self,attacker,move)
        move = EXT.prepare_versatile_move(self,move,versatile_stat)
        VISION.require_move(self,attacker,move)
        move = __import__('fling_move').prepare_move(self,attacker,primary,move)
        activation_range = WEAPONS.range_spec(self,move,attacker)
        if WEAPONS.is_field(activation_range) or WEAPONS.is_blessing(activation_range):
            # Field and Blessing Moves have no creature primary. Keep one actual user anchor
            # so action/frequency/effect lifecycles execute exactly once.
            primary=attacker
        import native_area_hit_effects as AREA_HIT
        AREA_HIT.require_candidates(self,attacker,move,everyone,primary)
        WEAPONS.selected_targets(self,attacker,move,everyone,primary)
        self.everyone = everyone
        native_mm = ENVIRON.mechanics(self,move,self.r.move_mech(move_id)[0])
        native_mm = __import__("jump_move_actions").mechanics(self.r,move_id,native_mm)
        native_mm = __import__('ace_trainer').mechanics(self,attacker,move,native_mm)
        import unown_imbuement as UNOWN
        native_mm = UNOWN.mechanics(self,attacker,move,native_mm)
        native_mm = __import__('rune_master').mechanics(self,attacker,move,native_mm)
        import optional_move_modes as OPTIONAL_MODES
        move, native_mm = OPTIONAL_MODES.project(self,attacker,primary,move,native_mm)
        import retrospective_moves as RETROSPECTIVE
        move, native_mm = RETROSPECTIVE.project(self,attacker,move,native_mm)
        move, native_mm = __import__("endure").project(self,attacker,primary,move,native_mm)
        import linked_move_conditions as LINKED
        LINKED.check_move(self,attacker,move_id)
        native_mm = LINKED.project(self,move,native_mm)
        native_mm = __import__('misty_explosion').mechanics(self.r,move,native_mm)
        if move_id == 'move/미스트버스트' and aim is None:
            aim = attacker.pos
            move = AREA.bind(self,attacker,move,aim)
        import five_strike as FIVE_STRIKE
        FIVE_STRIKE.preflight(self,attacker,move)
        # An explicit area aim, rather than the legacy primary placeholder, owns
        # target-free geometry. The inner activation uses the actor only as its
        # lifecycle anchor, so target-only preflights cannot vary by placeholder.
        if AREA.requires_empty_field_activation(native_mm):
            return MOVE_ACTIVATION.activate_empty_area(self,attacker,move,native_mm,
                weapon_id=weapon_id,struggle_choice=struggle_choice,aim=aim,appendage_id=appendage_id,set_damage=set_damage,versatile_stat=versatile_stat)
        if AREA.empty_field_effects(native_mm) or __import__('ice_lake').empty_area_adopted(self,attacker,move):
            empty_targets = self.targets_in_range(attacker,move,everyone,attacker)
            if not empty_targets:
                return MOVE_ACTIVATION.activate_empty_area(self,attacker,move,native_mm,
                    weapon_id=weapon_id,struggle_choice=struggle_choice,aim=aim,appendage_id=appendage_id,set_damage=set_damage,versatile_stat=versatile_stat)
        PARTIAL.require_complete(primary, "use_move_on target")
        SUPPLEMENTAL.require_actor_access(self, primary, "use_move_on")
        TEMPLATES.require_ordinary(primary, "use_move_on")
        import body_modes as BODY_MODES
        if not BODY_MODES.target_visible(self,attacker,primary):raise ValueError("Phasing or inflated body blocks targeting")
        POKEMON_PARTY.require_participation(self,primary,acting=False)
        import class_move_grants as CLASS_MOVES
        move, mm = CLASS_MOVES.prepare_curse(self,attacker,primary,move,native_mm,allow_approach=True)
        WEAPONS.validate_target(self,attacker,primary,move,allow_approach=True)
        EXT.validate_combat_edges(self,attacker)
        EXT.validate_combat_move(self,attacker,move)
        import event_effects as EVENTS
        EVENTS.validate_for_use(self,attacker,move=move)
        TEMP_HP.ensure_certain(self,attacker)
        import confusion_attacks as CONFUSION
        CONFUSION.preflight(self,attacker,move)
        TEMP_HP.ensure_certain(self,primary)
        import combat_social_edges as SOCIAL
        SOCIAL.preflight(self,attacker,primary,move,mm,applying=True)
        CPF.preflight(self,attacker,primary,move,mm,applying=True)
        import roll_effects as ROLLS
        ROLLS.preflight_move(self,attacker,primary,move,mm)
        FX.preflight_effects(self,attacker,primary,mm.get('effects_exec', []),move_id)
        __import__('earned_status_choices').preflight_move(self,attacker,primary,move,mm)
        if not EXT.entry_move_allowed(self,attacker,move,mm,target=primary):return 0
        __import__("jump_move_actions").preflight(self,attacker,primary,move)
        import move_accuracy as MOVE_ACCURACY
        if not MOVE_ACCURACY.preflight(self,attacker,primary,move,mm):
            INVISIBILITY.accuracy_penalty(self,primary,observer=attacker)
            import blender_state as BLENDER
            BLENDER.evasion(self,primary,move,attacker)
            import environment_derive as ED
            ED.evasion(self,primary,move,mm)
        import dynamic_chain_moves as CHAIN
        if CHAIN.declared(mm):
            # Source choices are admitted before ordinary approach or payment.
            CHAIN.policy(self.r,move_id)
            selected=CHAIN.steps(self,attacker,chain_steps,first=True)
            if selected[0]['target'] is not primary:raise ValueError('first chain recipient must be the actual primary')
        elif chain_steps is not None:raise ValueError('chain steps belong only to a dynamic chain Move')
        rng = WEAPONS.range_spec(self,move,attacker)
        reach = BODY.melee_reach(attacker) if rng.get("origin") == "melee" else (rng.get("origin") if isinstance(rng.get("origin"), int) else 1)
        if self.grid is not None and origin_part is None and not rng.get("shape") and not BODY.in_range(self,__import__('rune_master').range_actor(self,__import__('type_ace').range_actor(self,attacker,move),move),primary,reach):
            if __import__('trickster').impromptu_scope(self,attacker,move):raise ValueError('Impromptu Move must be in its actual range without approach movement')
            self.approach(attacker, primary, reach)
        if CHAIN.declared(mm):
            return CHAIN.use(self,attacker,primary,move_id,selected,
                dict(weapon_id=weapon_id,struggle_choice=struggle_choice,aim=aim,
                     appendage_id=appendage_id,origin_part=origin_part,set_damage=set_damage,versatile_stat=versatile_stat),move=move)
        __import__('telepath').capture_area(self,attacker,primary,move)
        # 연막은 피격자가 없는 공간에도 생성된다. 대상별로 중심을 옮기지 않는다.
        if "zone" in mm and self.grid is not None:
            aim = primary.pos if aim is None else aim
            move = AREA.bind(self,attacker,move,aim)
            targets = [primary]
        else:
            targets = self.targets_in_range(attacker, move, everyone, primary)
        import optional_physical_equipment as OPTIONAL_EQUIPMENT
        targets = OPTIONAL_EQUIPMENT.filter_targets(attacker, move, targets)
        targets = OPTIONAL_MODES.filter_targets(self,attacker,move,targets)
        targets = __import__('coordinator').selected_targets(self,attacker,move,__import__('musician').friendly_targets(attacker,move,targets),primary)
        if move_id == LINKED.PERISH and attacker not in targets: targets.append(attacker)
        import move_completion as COMPLETE
        field_effects = AREA.empty_field_effects(mm)
        if not targets and self.grid is not None and rng.get("shape") and not field_effects:
            self.approach(attacker, primary, rng.get("size", 1))
            targets = self.targets_in_range(attacker, move, everyone, primary)
            targets = OPTIONAL_EQUIPMENT.filter_targets(attacker, move, targets)
            targets = OPTIONAL_MODES.filter_targets(self,attacker,move,targets)
            targets = __import__('coordinator').selected_targets(self,attacker,move,__import__('musician').friendly_targets(attacker,move,targets),primary)
        if not targets:
            if field_effects:
                return MOVE_ACTIVATION.activate_empty_area(self,attacker,move,mm,
                    weapon_id=weapon_id,struggle_choice=struggle_choice,aim=aim,appendage_id=appendage_id,set_damage=set_damage,versatile_stat=versatile_stat)
            self.log(f"  {attacker.name} {move['name']}: 사거리 밖/가로막힘 → 행동 없음", "ch10/범위-키워드")
            return 0
        move, mm = OPTIONAL_MODES.project(self,attacker,primary,
            dict(move,_actual_targets=tuple(targets)),mm)
        for target in targets:
            __import__('condition_instances').require_target(attacker,target)
            import move_accuracy as MOVE_ACCURACY
            if not MOVE_ACCURACY.preflight(self,attacker,target,move,mm):
                self.spatial_evasion_penalty(target)
                INVISIBILITY.accuracy_penalty(self,target,observer=attacker)
                import blender_state as BLENDER
                BLENDER.evasion(self,target,move,attacker)
                import environment_derive as ED
                ED.evasion(self,target,move,mm)
            POKEMON_PARTY.require_participation(self,target,acting=False)
            SOCIAL.preflight(self,attacker,target,move,mm,applying=True)
            CPF.preflight(self,attacker,target,move,mm,applying=True)
            FX.preflight_effects(self,attacker,target,mm.get('effects_exec', []),move_id)
            __import__('earned_status_choices').preflight_move(self,attacker,target,move,mm)
            import weather_blessings as WEATHER_BLESSINGS
            WEATHER_BLESSINGS.preflight_attack(self,attacker,target,move,mm)
        total = 0
        import native_area_hit_effects as AREA_HIT
        AREA_HIT.require_targets(self,attacker,move,targets,primary)
        with MOVE_ACTIVATION.open_scope(self,attacker,move_id,targets,
                shared=bool(rng.get("shape")),primary=primary,
                options=dict(weapon_id=weapon_id,struggle_choice=struggle_choice,aim=aim,appendage_id=appendage_id,origin_part=origin_part,set_damage=set_damage,versatile_stat=versatile_stat,weather_ball_type=weather_ball_type,use_radiated_type=use_radiated_type)) as (activation,shared_accuracy):
            STELLAR_TERA.bind_activation(self,attacker,activation,move)
            for i, t in enumerate(targets):
                paired=__import__('conquerors_march').paired_return(self,activation,t)
                ace=__import__('type_ace').scope(self,attacker,{'id':move_id})
                if paired is not None:
                    dealt=paired
                elif i==0 and ace and ace.get('extra_move'):
                    with ACTION.move_grant(self,attacker,t,move_id,source=ace['feature'],kind='free') as grant:
                        dealt=self.use_move(attacker,t,move_id,count_use=not ace.get('ignore_frequency',False),free_action=True,_action_grant=grant,_activation=activation,_shared_accuracy=shared_accuracy,aim=aim,set_damage=set_damage,versatile_stat=versatile_stat,weather_ball_type=weather_ball_type,use_radiated_type=use_radiated_type)
                elif i==0 and __import__('rune_master').move_authority(self,attacker,t,move_id,'feat/폭발-룬'):
                    with ACTION.move_grant(self,attacker,t,move_id,source='feat/폭발-룬',kind='free') as grant:
                        dealt=self.use_move(attacker,t,move_id,count_use=True,free_action=True,_action_grant=grant,_activation=activation,_shared_accuracy=shared_accuracy,weapon_id=weapon_id,struggle_choice=struggle_choice,aim=aim,appendage_id=appendage_id,origin_part=origin_part,set_damage=set_damage,versatile_stat=versatile_stat,weather_ball_type=weather_ball_type,use_radiated_type=use_radiated_type)
                elif i == 0:
                    import conditional_damage_base as CONDITIONAL_DB
                    import bide as BIDE
                    dealt = self.use_move(attacker, t, move_id, count_use=not (CONDITIONAL_DB.resolving(attacker,move_id) or BIDE.resolving(self,attacker,move_id)), _activation=activation, _shared_accuracy=shared_accuracy,weapon_id=weapon_id,struggle_choice=struggle_choice,aim=aim,appendage_id=appendage_id,origin_part=origin_part,set_damage=set_damage,versatile_stat=versatile_stat,weather_ball_type=weather_ball_type,use_radiated_type=use_radiated_type)
                else:
                    with ACTION.move_grant(self, attacker, t, move_id, source="same_move_activation") as grant:
                        dealt = self.use_move(attacker, t, move_id, count_use=False, _activation=activation, _shared_accuracy=shared_accuracy, _action_grant=grant,weapon_id=weapon_id,struggle_choice=struggle_choice,aim=aim,appendage_id=appendage_id,origin_part=origin_part,set_damage=set_damage,versatile_stat=versatile_stat,weather_ball_type=weather_ball_type,use_radiated_type=use_radiated_type)
                total += dealt
                if paired is None and MOVE_ACTIVATION.note_result(self,activation,dealt):return total
                # A miss is an activated move; refusal or a preparation turn is not.
                if i == 0 and not activation.get("started"):
                    return total
        return total

    def continue_chain_move(self, completion_id, *, chain_steps=None, stop=False):
        import dynamic_chain_moves as CHAIN
        return CHAIN.continue_move(self,completion_id,chain_steps=chain_steps,stop=stop)

    def _ruleset_move(self, attacker, move_id):
        """룰셋 필터: 제외된 기술은 거부(None), 코어판→변형판 치환은 로그."""
        if move_id in self.r.unresolved_moves:
            raise UnresolvedRuleSelection(move_id, self.r.unresolved_moves[move_id])
        if move_id in self.r.excluded_moves:
            self.r.selection.require_current_filter(self.r.ruleset)
            self.log(f"  {attacker.name} {self.r.moves[move_id]['name']}: 룰셋 '{self.r.ruleset.name}' 에서 제외된 기술({self.r.excluded_moves[move_id]}) → 사용 불가", "ruleset/exclude")
            return None
        import living_weapon as LIVING
        LIVING.refresh(self,attacker)
        new = self.r.resolve_move(move_id)
        if self.r.move(new).get('class') == '항상':
            raise ValueError('static learned Move cannot be activated')
        if new != move_id:
            self.log(f"  [룰셋 {self.r.ruleset.name}] {self.r.moves[move_id]['name']} → {self.r.moves[new]['name']} (변형판 대체)", "ruleset/alias")
        return new

    @__import__('hp_setting_moves').preparation_scope
    @__import__('partial_entities').complete_move
    @_excluded_move_admission
    @__import__('recycle_move').native_move
    @__import__('wish_move').native_move
    @__import__('glitch_bender').native_move
    @__import__('warper').native_move
    @__import__('telepath').native_move
    @__import__('telekinetic').native_move
    @__import__('channeler').native_move
    @__import__('aura_guardian').native_move
    @__import__('taskmaster').native_move
    @__import__('duelist').attack_scope
    @__import__('defense_curl').native_move
    @OPTIONAL_WEAPONS.atomic_move
    @__import__('arcanist').atomic_move
    @__import__('marksman').atomic_move
    @__import__('skirmisher').atomic_move
    @__import__('fling_move').atomic_move
    @ACTION.resolved_move
    @MOVE_ACTIVATION.effect_contributions
    @TRACE.operation('move_attempt','attacker','target','move_id','set_damage','count_use','free_action')
    @__import__("cheerleader").native_action
    @__import__('electro_shot').native_move
    def use_move(self, attacker, target, move_id, situational=0, set_damage=False, count_use=True, free_action=False, _activation=None, _shared_accuracy=None, _action_grant=None, _field_activation=None, *, roll_id=None, weapon_id=None, reliable_trainer=None, struggle_choice=None, aim=None, appendage_id=None, origin_part=None, coup_de_grace=False, versatile_stat=None, weather_ball_type=None, use_radiated_type=None):
        if type(set_damage) is not bool:raise ValueError('boolean Set Damage declaration required')
        if set_damage and __import__('coordinator').damage_offer(self,attacker) is not None:raise ValueError('Coordinator rerolls a Damage Roll, not Set Damage')
        import taskmaster as TASK
        TASK.move_permission(attacker,move_id)
        __import__('focus_punch').require_release(self,attacker,move_id)
        pending=__import__('musician').no_accuracy_pending(self,attacker,move_id)
        if pending is not None:return pending
        import coup_de_grace as COUP
        if type(coup_de_grace) is not bool:raise ValueError('boolean Coup de Grace declaration required')
        if coup_de_grace:
            if (not count_use or free_action or any(value is not None for value in
                    (_activation,_shared_accuracy,_action_grant,_field_activation))):
                raise ValueError('Coup de Grace requires one ordinary attack activation')
            COUP.require_target(self,attacker,target)
        import body_state as BODY
        if origin_part is not None:BODY.part_cell(self,attacker,origin_part)
        import ability_state_projection as PROJECTION
        if (not getattr(self,'_reactive_move_transaction',False)
                and (coup_de_grace or TASK.move_interested(self,attacker,target) or REACTIVE_ABILITIES.interested(self,attacker,target)
                     or (not getattr(self, '_setup_move_scopes', ())
                         and __import__('herb_mushroom_rules').power_herb_interested(attacker))
                     or PROJECTION.native_move_interested(self,attacker,target)
                     or __import__('enduring_soul').move_interested(self)
                     or __import__('berserker').move_interested(self,attacker,target)
                     or DEFENSE.interested(self,attacker,target)
                     or ABILITY_INTERRUPTS.interested(self)
                     or __import__('musician').drown_interested(self)
                     or ABILITY_REACTIONS.interested(self)
                     or __import__('ice_lake').interested(self,attacker,target)
                     or __import__('type_ace').move_interested(self,attacker,target)
                     or __import__('commander_orders').move_interested(self,attacker,target)
                     or __import__('z_moves').interested(attacker)
                     or __import__('conquerors_march').interested(self)
                     or self.r.move_id(move_id) in ('move/배턴터치','move/웅크리기','move/페어리록'))):
            def staged(e,a,t):
                import state_grants as G
                options=G._stage_transition_payload(self,e,dict(situational=situational,set_damage=set_damage,
                    count_use=count_use,free_action=free_action,_activation=_activation,
                    _shared_accuracy=_shared_accuracy,_action_grant=_action_grant,
                    _field_activation=_field_activation,roll_id=roll_id,weapon_id=weapon_id,
                    reliable_trainer=reliable_trainer,struggle_choice=struggle_choice,aim=aim,appendage_id=appendage_id,origin_part=origin_part,
                    coup_de_grace=coup_de_grace,versatile_stat=versatile_stat,weather_ball_type=weather_ball_type,use_radiated_type=use_radiated_type))
                # The outer native decorators already opened the action,
                # contribution and trace scopes copied into this transaction.
                # Re-enter only their body so accuracy suspension owns one scope.
                from inspect import unwrap
                return unwrap(Engine.use_move)(e,a,t,move_id,**options)
            return REACTIVE_ABILITIES.atomic_move(self,attacker,target,staged)
        import type_ace as TA
        # Select the rule before any action gate can observe or change game state.
        field_requested = _field_activation is not None
        import pass_moves as PASS
        actual_id=self.r.move_id(move_id)
        if actual_id is not None:PASS.require_native_target(self,attacker,target,actual_id)
        import partial_entities as PARTIAL
        PARTIAL.require_complete(attacker, "use_move")
        import invisibility_state as INVISIBILITY
        INVISIBILITY.require_move(self,attacker)
        import supplemental_state as SUPPLEMENTAL
        SUPPLEMENTAL.require_actor_access(self, attacker, "use_move")
        import actor_templates as TEMPLATES
        TEMPLATES.require_ordinary(attacker, "use_move")
        if not field_requested:
            PARTIAL.require_complete(target, "use_move target")
            SUPPLEMENTAL.require_actor_access(self, target, "use_move")
            TEMPLATES.require_ordinary(target, "use_move")
            import body_modes as BODY_MODES
            if not BODY_MODES.target_visible(self,attacker,target):raise ValueError("Phasing or inflated body blocks targeting")
        move_id = self._ruleset_move(attacker, move_id)
        __import__('natural_fighter').target_entry(self,attacker,move_id,_activation)
        import vision_impairment as VISION
        if move_id is not None:VISION.require_move(self,attacker,self.r.move(move_id))
        if move_id is None:
            return 0
        import stellar_tera_blast as STELLAR_TERA
        stellar_choice = STELLAR_TERA.prepare(self,attacker,self.r.move(move_id),use_radiated_type,activation=_activation).get(STELLAR_TERA.CHOICE)
        EXT.prepare_versatile_move(self,self.r.move(move_id),versatile_stat)
        __import__('weather_state').prepare_weather_ball(self,attacker,self.r.move(move_id),weather_ball_type)
        import move_permissions as MOVE_PERMISSIONS
        MOVE_PERMISSIONS.require_native_move(self,attacker,move_id)
        import field_effects as FIELD
        field_block = FIELD.native_move_block_reason(self, move_id, attacker)
        if field_block:
            self.log(f"    {attacker.name}: 전장 효과가 이 기술을 무효화", field_block)
            return 0
        import setup_move_state as SETUP_MOVE
        SETUP_MOVE.require_native_scope(self,attacker,move_id)
        if not field_requested:
            SETUP_MOVE.require_targetable(self,attacker,target,move_id)
        if not SETUP_MOVE.generic_ready(self,attacker,move_id):return 0
        ordinary_choice = (count_use and not free_action and _activation is None
                           and _shared_accuracy is None and _action_grant is None)
        import forced_move_lock as FORCED_MOVE
        choice_candidates = list(getattr(self, "everyone", ()) or ())
        if target is not attacker and target not in choice_candidates:
            choice_candidates.append(target)
        if not FORCED_MOVE.preflight_choice(
                self, attacker, move_id, choice_candidates, ordinary=ordinary_choice):
            return 0
        import conditional_damage_base as CONDITIONAL_DB
        if CONDITIONAL_DB.action_locked(attacker) and not CONDITIONAL_DB.resolving(attacker, move_id):
            self.log(f"  {attacker.name}: 라운드말 예약 공격 때문에 다른 행동을 할 수 없음",
                     "conditional_damage_base/round_end_setup")
            return 0
        round_end_authorized = CONDITIONAL_DB.round_end_authorized(attacker, target, move_id)
        import bide as BIDE
        round_end_authorized = round_end_authorized or BIDE.authorized(self,attacker,target,move_id)
        if field_requested:
            MOVE_ACTIVATION.require_empty_field_scope(self,attacker,move_id,_field_activation)
            if target is not attacker:raise ValueError('target-free Move lifecycle anchor must be its actual user')
            if (not count_use or free_action or _activation is not None or _shared_accuracy is not None
                    or _action_grant is not None):
                raise ValueError('empty area activation owns one ordinary action and frequency use')
            if situational != 0 or set_damage or roll_id is not None or reliable_trainer is not None:
                raise ValueError('empty area activation has no accuracy or damage declaration')
        PASSIVE_EVENTS.preflight_continuation(self,attacker,
            ordinary_single=(count_use and not free_action and _activation is None
                             and _shared_accuracy is None and _action_grant is None))
        import homebrew_weather as HOME_WEATHER
        HOME_WEATHER.require_actor(self,attacker,move_id)
        import pokemon_party as POKEMON_PARTY
        POKEMON_PARTY.require_participation(self,attacker)
        import party_actions as PARTY_ACTIONS
        PARTY_ACTIONS.require_command(self,attacker,move_id)
        import pokemon_understanding as UNDERSTANDING
        UNDERSTANDING.require_activity(self,attacker,'move')
        if not field_requested:
            POKEMON_PARTY.require_participation(self,target,acting=False)
            MOVE_ACTIVATION.verify(self,attacker,target,move_id,_activation,_shared_accuracy,
                count_use=count_use,free_action=free_action)
            if _action_grant is not None and not any(g[0] is _action_grant and g[1] is attacker and g[2] is target and g[3]==move_id for g in self._action_grants):
                raise ValueError('actual live move grant required')
        PASSIVE_EVENTS.ensure_clear(self)
        EFFECT_CONTRACTS.ensure_clear(self)
        if field_requested:LEAGUE.check_boundary(self,'target-free use_move')
        else:LEAGUE.check_action(self, attacker, target, move_id)
        HEAVY.ensure_clear(self)
        import pokemon_activities as POKEMON
        obedience = POKEMON.obedience_gate(self,attacker,target,move_id,action_grant=_action_grant)
        if isinstance(obedience, CHECKS.PendingDecision):return obedience
        if not obedience:return 0
        if not TURN.can_act(self, attacker):
            return 0
        import weapon_actions as WEAPONS
        import environ_moves as ENVIRON
        move = __import__('skirmisher').prepare_move(self,attacker,WEAPONS.prepare(self,attacker,ENVIRON.prepare(self,attacker,self.r.move(move_id)),weapon_id))
        move = __import__('arcanist').prepare(self,attacker,move)
        move = __import__('confusion_attacks').prepare(self,attacker,move)
        if stellar_choice is not None:move = dict(move,**{STELLAR_TERA.CHOICE:stellar_choice})
        import area_targets as AREA
        move = PASS.bind(self,attacker,move)
        import stat_ace as STAT
        move = STAT.bind(self,attacker,move)
        move = __import__('telekinetic').project_move(self,attacker,move)
        move = AREA.bind(self,attacker,move,aim)
        import struggle_capabilities as STRUGGLE
        move = STRUGGLE.prepare(self,attacker,move,struggle_choice)
        import cleanse_tags as CLEANSE
        move = CLEANSE.prepare_appendage(self,attacker,move,appendage_id)
        import pokemon_move_edges as POKE_MOVE_EDGES
        move = POKE_MOVE_EDGES.prepare(self,attacker,move)
        import weather_state as WEATHER
        move = WEATHER.prepare_weather_ball(self,attacker,move,weather_ball_type)
        import gmax_moves as GMAX
        move = GMAX.prepare_native_move(self,attacker,move)
        move = __import__('musician').project_move(self,attacker,move)
        move = __import__('coordinator').prepare(self,attacker,move)
        if not __import__('coordinator').selected_targets(self,attacker,move,[target],target):return 0
        move = __import__('researcher_fields').prepare_move(self,attacker,move,target=target)
        move = __import__('fling_move').prepare_move(self,attacker,target,move)
        if target is not attacker and not __import__('musician').friendly_targets(attacker,move,[target]):return 0
        move = BODY.bind_origin(self,attacker,move,origin_part)
        move = __import__('martial_artist').prepare(self,attacker,move)
        move = EXT.prepare_versatile_move(self,move,versatile_stat)
        VISION.require_move(self,attacker,move)
        move = dict(move,_actual_targets=() if _field_activation is not None else
                    (_shared_accuracy or {}).get("targets",(target,)))
        import combat_maneuvers as MANEUVERS
        allowed,reason=MANEUVERS.move_allowed(self,attacker,move)
        if not allowed:
            self.log(f"    {attacker.name}: {reason}", "maneuver/술수")
            return 0
        allowed,reason=GMAX.move_allowed(self,attacker,move)
        if not allowed:
            self.log(f"    {attacker.name}: {reason}", "gmax/depletion")
            return 0
        EXT.validate_combat_edges(self,attacker)
        EXT.validate_combat_move(self,attacker,move)
        import event_effects as EVENTS
        EVENTS.validate_for_use(self,attacker,move=move)
        TEMP_HP.ensure_certain(self,attacker)
        if not field_requested:TEMP_HP.ensure_certain(self,target)
        import confusion_attacks as CONFUSION
        CONFUSION.preflight(self,attacker,move)
        mm, conf = self.r.move_mech(move_id)
        mm = ENVIRON.mechanics(self,move,mm)
        move=__import__('ninja').project_weapon(self,attacker,move)
        mm=__import__('substitute').project(self,attacker,move,mm)
        move,mm=__import__('combat_move_reactions').bind(self,attacker,move,mm)
        mm = CONDITIONAL_DB.execution_mechanics(move, mm)
        mm = __import__("jump_move_actions").mechanics(self.r,move_id,mm)
        mm = __import__('ace_trainer').mechanics(self,attacker,move,mm)
        import unown_imbuement as UNOWN
        mm = UNOWN.mechanics(self,attacker,move,mm)
        mm = __import__('rune_master').mechanics(self,attacker,move,mm)
        import optional_move_modes as OPTIONAL_MODES
        move, mm = OPTIONAL_MODES.project(self,attacker,target,move,mm,native=True)
        import move_type_choices as TYPE_CHOICES
        move, mm = TYPE_CHOICES.project(self,attacker,target,move,mm)
        import retrospective_moves as RETROSPECTIVE
        move, mm = RETROSPECTIVE.project(self,attacker,move,mm)
        import spite as SPITE
        move, mm = SPITE.project(self,attacker,target,move,mm)
        if move_id in (__import__('glitch_bender').DISABLE,__import__('glitch_bender').METRONOME):move,mm=__import__('glitch_bender').project_move(self,attacker,target,move,mm)
        move=__import__('tumbler').project_acrobatics(self,attacker,move)
        move, mm = __import__("endure").project(self,attacker,target,move,mm)
        mm=REACTIVE_ABILITIES.preflight_move(self,attacker,target,move,mm,
            ordinary_action='full' if coup_de_grace else 'free' if free_action else TURN.action_kind_of_move(self,attacker,move,mm))
        import linked_move_conditions as LINKED
        LINKED.check_move(self,attacker,move_id)
        mm = LINKED.project(self,move,mm)
        import five_strike as FIVE_STRIKE
        FIVE_STRIKE.preflight(self,attacker,move)
        if move_id == LINKED.PERISH and _activation is None:
            raise ValueError('Perish Song requires its native area activation including the user')
        if not field_requested:
            import class_move_grants as CLASS_MOVES
            move, mm = CLASS_MOVES.prepare_curse(self,attacker,target,move,mm)
            WEAPONS.validate_target(self,attacker,target,move)
        if coup_de_grace:move=COUP.prepare(self,attacker,target,move,mm)
        if self.grid is not None and ("zone" in mm or move_id in ("move/날려버리기","move/일렉트로빔")) and not PASS.converted_scope(self,attacker,move_id):
            move = AREA.bind(self,attacker,move,target.pos if aim is None else aim)
            move = dict(move,_effect_area_cells=AREA.cells(self,attacker,move))
            if move_id=="move/일렉트로빔":move=__import__("electro_shot").capture_geometry(self,attacker,move)
        __import__('telepath').capture_area(self,attacker,target,move)
        mm = __import__('misty_explosion').mechanics(self.r,move,mm)
        field_scope = (MOVE_ACTIVATION.verify_empty_field(self,attacker,move,mm,_field_activation)
                       if _field_activation is not None else None)
        if move_id == 'move/미스트버스트':
            mm = {k:v for k,v in mm.items() if k not in ('_native_empty_field_activation','_native_empty_field_kind')}
        import field_effects as FIELD
        field_block=FIELD.move_block_reason(self,attacker,target,move,mm,targetless=field_scope is not None)
        if field_block:
            self.log(f"    {attacker.name}: 전장 효과가 이 기술을 무효화",field_block)
            return 0
        if not EXT.entry_move_allowed(self,attacker,move,mm,target=target,targetless=field_scope is not None):return 0
        __import__("jump_move_actions").preflight(self,attacker,target,move)
        __import__('telekinetic').preflight_move(self,attacker,target,move)
        import food_effects as FOOD
        if not FOOD.move_allowed(self,attacker,move,mm):
            return 0
        import herb_mushroom_rules as HERB
        power_herb = HERB.power_herb_plan(self,attacker,move_id)
        import sound_state as SOUND
        sound_activity=SOUND.prepare_move(self,attacker,move)
        if self.grid is not None and field_scope is None:
            import body_state as BODY
            native_range=WEAPONS.range_spec(self,move,attacker)
            if move.get('_struggle_range') and not BODY.in_range(self,attacker,target,native_range['origin'],move=move):
                return 0
            reach = native_range.get('origin')
            if reach == 'melee':
                reach = BODY.melee_reach(attacker)
            if type(reach) is int and not native_range.get('shape') and not BODY.in_range(self,__import__('jump_move_actions').range_actor(self,__import__('rune_master').range_actor(self,__import__('type_ace').range_actor(self,attacker,move),move),move),target,reach,move=move):
                self.log('    target outside current attack reach', 'combat/range')
                return 0
        import mapless_space as MAPLESS
        if self.grid is None and MAPLESS.active(self) and field_scope is None:
            MAPLESS.require_target(self,attacker,target,move)
        import condition_instances as CONDITIONS
        if field_scope is not None:
            field_mm = dict(mm,effects_exec=list(field_scope['effects']))
            CONDITIONS.preflight_move(self,attacker,attacker,field_mm)
            FX.preflight_effects(self,attacker,attacker,field_scope['effects'],move_id)
        else:
            import equipment_actions as EQUIPMENT
            EQUIPMENT.trick_context(self,attacker,target,move_id)
            import dynamic_chain_moves as CHAIN
            if CHAIN.declared(mm):move=CHAIN.prepare(self,attacker,target,move)
            move=__import__('natural_fighter_moves').prepare_move(self,attacker,target,move)
            CONDITIONS.preflight_move(self,attacker,target,mm)
            FX.preflight_effects(self,attacker,target,mm.get('effects_exec', []),move_id)
            __import__('earned_status_choices').preflight_move(self,attacker,target,move,mm)
            import weather_blessings as WEATHER_BLESSINGS
            WEATHER_BLESSINGS.preflight_attack(self,attacker,target,move,mm)
            EXT.blocks_hit(self,attacker,target,move,mm)  # source/conditional preflight before Standard, frequency or RNG
            import combat_social_edges as SOCIAL
            SOCIAL.preflight(self,attacker,target,move,mm,applying=True)
            CPF.preflight(self,attacker,target,move,mm,applying=True)
            import move_accuracy as MOVE_ACCURACY
            if not MOVE_ACCURACY.preflight(self,attacker,target,move,mm,roll_id=roll_id,reliable_trainer=reliable_trainer):
                self.spatial_evasion_penalty(target)
                INVISIBILITY.accuracy_penalty(self,target,observer=attacker)
                import blender_state as BLENDER
                BLENDER.evasion(self,target,move,attacker)
                import environment_derive as ED
                ED.evasion(self,target,move,mm)
            import roll_effects as ROLLS
            ROLLS.preflight_move(self,attacker,target,move,mm)
            import fast_combat as FAST_COMBAT
            FAST_COMBAT.preflight_move(self,attacker,target,move,mm,
                shared_accuracy=_shared_accuracy,reliable_trainer=reliable_trainer)
            if reliable_trainer is not None:
                import contest_features as CF
                if _action_grant is not None or not count_use or free_action:
                    raise ValueError('Reliable Performance granted/free composite activation needs an explicit policy')
                CF.reliable_accuracy_preflight(self,reliable_trainer,attacker,move,mm,
                    shared_accuracy=_shared_accuracy,activation=_activation)
            if roll_id is not None:
                AP_ROLL.bonus(self,attacker,roll_id,'accuracy')
                if _shared_accuracy is not None or EXT.multi_roll_spec(mm) is not None:
                    raise ValueError('identified composite accuracy needs a sourced per-roll policy')
        kind = "full" if coup_de_grace else "free" if free_action else TURN.action_kind_of_move(self, attacker, move, mm)
        if not CAPABILITIES.action_permission(self,attacker,kind,move_id):return 0
        standard_pre_context = None
        if self.encounter_active and attacker.injuries >= 5 and kind == "standard" and not TASK.ignores_acting_loss(attacker):
            standard_inputs = dict(situational=situational,set_damage=set_damage,
                                   count_use=count_use,free_action=free_action)
            standard_diagnostic = (HEAVY_STANDARD.diagnose_empty_field(
                self,attacker,move,mm,field_scope['effects'],
                count_use and not free_action and _activation is None
                and _shared_accuracy is None and _action_grant is None,
                public_inputs=standard_inputs) if field_scope is not None else
                HEAVY_STANDARD.diagnose(self,attacker,target,move,mm,
                    count_use and not free_action and _activation is None
                    and _shared_accuracy is None and _action_grant is None,
                    public_inputs=standard_inputs))
            standard_pre_context = dict(before=HEAVY.observe(attacker),public_inputs=standard_inputs,
                diagnostic=standard_diagnostic)
        grant_ok, grant_kind = ACTION.consume_move_grant(self, _action_grant, attacker, target, move_id, count_use=count_use, free_action=free_action)
        if self.encounter_active:
            if (free_action or not count_use) and not grant_ok and not round_end_authorized:
                self.log("    [보류] 비용/빈도 생략에는 출처가 확인된 실행 권한 필요", "common/action-lifecycle")
                return 0
            if not grant_ok and not round_end_authorized and not ACTION.ordinary_permission(self, attacker):
                return 0
        sleep_cure = ACTION.self_cures_sleep(attacker, target, mm.get("effects_exec", []))
        if not ACTION.status_permission(self, attacker, kind, sleep_cure=sleep_cure, new_action=not (grant_ok and grant_kind is None),_native_move=move):
            return 0
        if count_use:
            allowed, reason = FREQ.move_allowed(self, attacker, move_id, outside_combat=not self.encounter_active)
            if not allowed:
                self.log(f"  {attacker.name} {move['name']}: {reason}", "frequency/move")
                return 0
        import exhaust_moves as EXHAUST
        if not EXHAUST.preflight(self,attacker,move,count_use=count_use):
            return 0
        if not free_action and count_use:
            if not TURN.spend(self, attacker, kind, move["name"], sleep_cure=sleep_cure, _native_move=move):
                return 0
            __import__("provocateur").quick_committed(self,attacker,move)
            if kind != "standard":
                self.log(f"    {move['name']}은(는) {'완전' if kind == 'full' else '신속' if kind == 'swift' else '자유' if kind == 'free' else '이동'} 행동", "combat/action-economy")
            rng = WEAPONS.range_spec(self,move,attacker)
            if field_scope is None and self.grid is not None and isinstance(rng.get("origin"), int) and rng.get("origin", 0) > 1 and target.pos != attacker.pos and not self.adjacent(attacker,target):
                if not __import__("tumbler").defer_attack_aoo(self,attacker,"인접하지 않은 대상에게 원거리 공격"):TURN.trigger_aoo(self, attacker, "인접하지 않은 대상에게 원거리 공격")
                if attacker.fainted:
                    return 0
        if free_action and (not self.encounter_active or grant_ok):
            ACTION.record_action(self, attacker, grant_kind or "free")
        return self._continue_move_after_payment(attacker=attacker, target=target, move_id=move_id, move=move, mm=mm, conf=conf, _action_grant=_action_grant, _activation=_activation, _shared_accuracy=_shared_accuracy, count_use=count_use, field_scope=field_scope, free_action=free_action, grant_ok=grant_ok, kind=kind, power_herb=power_herb, reliable_trainer=reliable_trainer, roll_id=roll_id, set_damage=set_damage, situational=situational, sound_activity=sound_activity, standard_pre_context=standard_pre_context)

    def _continue_move_after_payment(self, *, attacker, target, move_id, move, mm, conf, _action_grant, _activation, _shared_accuracy, count_use, field_scope, free_action, grant_ok, kind, power_herb, reliable_trainer, roll_id, set_damage, situational, sound_activity, standard_pre_context):
        """Native paid suffix; a resumed reaction never repeats payment or entry checks."""
        import event_effects as EVENTS
        import conditional_damage_base as CONDITIONAL_DB
        import equipment_actions as EQUIPMENT
        import exhaust_moves as EXHAUST
        import herb_mushroom_rules as HERB
        import setup_move_state as SETUP_MOVE
        import type_ace as TA
        import taskmaster as TASK
        import unown_imbuement as UNOWN
        import weather_blessings as WEATHER_BLESSINGS
        import move_accuracy as MOVE_ACCURACY
        import sound_state as SOUND
        continuation={'attacker':attacker, 'target':target, 'move_id':move_id, 'move':move, 'mm':mm, 'conf':conf, '_action_grant':_action_grant, '_activation':_activation, '_shared_accuracy':_shared_accuracy, 'count_use':count_use, 'field_scope':field_scope, 'free_action':free_action, 'grant_ok':grant_ok, 'kind':kind, 'power_herb':power_herb, 'reliable_trainer':reliable_trainer, 'roll_id':roll_id, 'set_damage':set_damage, 'situational':situational, 'sound_activity':sound_activity, 'standard_pre_context':standard_pre_context}
        if __import__('combat_move_reactions').initiation(self,attacker,target,move,continuation=continuation):return 0
        if not EXT.pre_use(self, attacker, target, move, mm,targetless=field_scope is not None):
            return 0
        delayed_attack = EXT.delayed_attack_spec(mm)
        setup = next((e for e in mm.get("effects_exec", []) if e.get("type") == "set_up_move"), None)
        skip_setup = TA.setup_skip(self,attacker,move) or setup is not None and setup.get("skip_setup_if_weather") and FX.weather_matches(self, setup["skip_setup_if_weather"],attacker)
        if _activation is not None and _activation.get('power_herb_skip') is True:
            skip_setup = True
        if power_herb is not None:
            HERB.consume_power_herb(self,attacker,move_id)
            skip_setup = True
            if _activation is not None:
                _activation['power_herb_skip'] = True
        if CONDITIONAL_DB.round_end_setup(setup) and not CONDITIONAL_DB.resolving(attacker, move_id):
            CONDITIONAL_DB.declare(self, attacker, target, move)
            return 0
        native_setup_phase = SETUP_MOVE.native_phase(self,attacker,target,move_id) if setup is not None and SETUP_MOVE.owns(self.r,move_id) else None
        if native_setup_phase == "prepared":
            if move["type"]=="고스트":TA._curse_token(self,attacker)
            return 0
        generic_continuing = _activation is not None and _activation.get("started")
        if native_setup_phase is None and setup is not None and not CONDITIONAL_DB.round_end_setup(setup) and not generic_continuing and attacker.setup_move != move_id and not skip_setup:
            if move["type"]=="고스트":TA._curse_token(self,attacker)
            SETUP_MOVE.prepare_turn(self,attacker,move_id)
            self.log(f"  {attacker.name} {move['name']}: 준비 턴 ({str(setup.get('setup', ''))[:50]})", f"{move_id} ({conf}) set_up_move")
            st = setup.get("setup")
            if isinstance(st, list):
                FX.run_effects(self, attacker, target, st, {"attacker": attacker, "target": target, "hit": True, "nat": None, "engine": self}, f"{move_id} 준비")
            if move_id == "move/솔라빔" and st == "end turn unless sunny" and self.r._selected_rule(move_id) == move_id:
                self.end_of_turn(attacker)
            return 0
        if native_setup_phase is None and setup is not None and not CONDITIONAL_DB.round_end_setup(setup) and not generic_continuing:
            SETUP_MOVE.consume_turn(attacker)
            self.log(f"  {attacker.name} {move['name']}: 발동 턴", f"{move_id} ({conf}) set_up_move")
        if _activation is not None:
            _activation["started"] = True
        import ability_state_projection as ABILITY_STATE_PROJECTION
        ABILITY_STATE_PROJECTION.after_move(self,attacker,move_id,move,mm)
        import move_completion as COMPLETE
        if field_scope is not None:
            EVENTS.begin_move_use(self,attacker,target,move,mm,targetless=True)
            FX.fire_event(self,attacker,{"event":"on_move_use","move":move},None)
            attacker.last_move = move_id
            attacker.last_target = None
            FREQ.consume_move(self,attacker,move_id)
            EXHAUST.commit(self,attacker,move,count_use=count_use)
            field_standard_context = None
            if (self.encounter_active and attacker.injuries >= 5 and kind == "standard" and not TASK.ignores_acting_loss(attacker)
                    and not grant_ok):
                from copy import deepcopy
                field_standard_context = object()
                self._heavy_standard_sequence += 1
                self._heavy_standard_receipts[field_standard_context] = dict(actor=attacker,
                    action_target=None,move=move,mm=mm,round=self.round_no,
                    epoch=self._heavy_standard_sequence,move_uses=attacker.move_uses.get(move_id,0),
                    history_length=len(attacker._action_history),pre_context=standard_pre_context,
                    ordinary_single=True,targetless=True,
                    field_effects=deepcopy(field_scope['effects']))
                HEAVY_STANDARD.observe_activation(self,field_standard_context)
            if sound_activity is not None:SOUND.observe(self,attacker,sound_activity,move['id'])
            COMPLETE.apply_empty_field(self,attacker,move,field_scope['effects'],field_scope['cells'])
            HEAVY_STANDARD.finish(self,field_standard_context,hit=False,dealt=0)
            return 0
        CONDITIONAL_DB.begin_activation(attacker, move_id)
        completion_id=COMPLETE.start_target(self,attacker,target,move,mm,
            MOVE_ACTIVATION.current_scope(self,attacker,target,move_id))
        __import__('aura_guardian').begin_move(self,attacker,target,move,completion_id)
        __import__('commander_orders').begin_move(self,attacker,target,move,completion_id)
        if DEFENSE.skip_received(self,attacker,target,move,completion_id):return 0
        __import__('endure').begin(self,attacker,move,completion_id)
        __import__('enduring_soul').begin_move(self,attacker,move,completion_id)
        __import__('roughneck').begin_display(self,attacker,target,move,completion_id)
        UNOWN.begin_move_use(self,attacker,target,move,completion_id)
        REACTIVE_ABILITIES.begin_move(self,attacker,target,move,completion_id)
        import event_effects as EVENTS
        EVENTS.begin_move_use(self,attacker,target,move,mm)
        __import__('telekinetic').begin_move(self,attacker,target,move,completion_id)
        import optional_state_effect_contracts as OPTIONAL_STATE
        OPTIONAL_STATE.begin_move(self,attacker,target,move,completion_id)
        FX.fire_event(self, attacker, {"event": "on_move_use", "move": move}, target)
        self._inflictor = attacker
        if count_use:
            attacker.last_move = move_id
            attacker.last_target = target
            FREQ.consume_move(self, attacker, move_id)
            EXHAUST.commit(self,attacker,move,count_use=count_use)
            __import__('dancer').after_move_use(self,attacker,move_id,move,mm)
            __import__('musician').after_move_use(self,attacker,target,move,mm,completion_id)
        __import__('fling_move').launch(self,attacker,target,move,completion_id)
        standard_context = None
        if (self.encounter_active and attacker.injuries >= 5 and kind == "standard" and not TASK.ignores_acting_loss(attacker)
            and count_use and not free_action and not grant_ok):
            # Occurrence authority is issued here, after this producer's real
            # activation. Unknown contexts remain activation evidence, not proof
            # of a universal semantic commit phase.
            standard_context = object()
            self._heavy_standard_sequence += 1
            self._heavy_standard_receipts[standard_context] = dict(actor=attacker,
                action_target=target,move=move,mm=mm,round=self.round_no,
                epoch=self._heavy_standard_sequence,move_uses=attacker.move_uses.get(move_id,0),
                history_length=len(attacker._action_history),pre_context=standard_pre_context,
                ordinary_single=(_activation is None and _shared_accuracy is None and _action_grant is None))
            HEAVY_STANDARD.observe_activation(self,standard_context)
        import sound_state as SOUND
        if sound_activity is not None:SOUND.observe(self,attacker,sound_activity,move['id'])
        if delayed_attack is not None:
            EXT.schedule_delayed_attack(self,attacker,target,move,mm,completion_id)
            HEAVY_STANDARD.finish(self,standard_context,hit=False,dealt=0)
            return 0
        suffix={key:value for key,value in locals().items() if key in ['attacker', 'target', 'move_id', 'move', 'mm', 'conf', 'situational', 'set_damage', 'count_use', 'free_action', '_activation', '_shared_accuracy', '_action_grant', 'roll_id', 'reliable_trainer', 'standard_context', 'completion_id']}
        pending=__import__("jump_move_actions").begin(self,attacker,target,move,completion_id,suffix)
        if pending is not None:return pending
        return self._after_move_movement(**suffix)

    def _after_move_movement(self, attacker, target, move_id, move, mm, conf, situational, set_damage, count_use, free_action, _activation, _shared_accuracy, _action_grant, roll_id, reliable_trainer, standard_context, completion_id):
        import equipment_actions as EQUIPMENT
        import move_accuracy as MOVE_ACCURACY
        import move_activation as MOVE_ACTIVATION
        import type_ace as TA
        import taskmaster as TASK
        import weather_blessings as WEATHER_BLESSINGS
        if __import__('jump_move_actions').decline_attack(self,attacker,target,move,completion_id):return 0
        passive_event = PASSIVE_EVENTS.begin(self, attacker, target, move, move_mechanics=mm, completion_id=completion_id, ordinary_single=(count_use and not free_action and _activation is None and _shared_accuracy is None and _action_grant is None))
        import precise_actions as PRECISE
        precision_event = PRECISE.attacked(self,attacker,target,move)
        weather_attack = WEATHER_BLESSINGS.begin_attack(self,attacker,target,move)

        move=TASK.prepare_gambit(self,attacker,target,move,event_id=passive_event,completion_id=completion_id)
        self._move_completions[completion_id]['target_moves'][target.entity_id]=move

        def check_accuracy(index=0):
            accuracy_required=self._move_completions[completion_id].setdefault('juggler_accuracy_required',{})
            accuracy_required[target.entity_id]=False
            if __import__('confusion_attacks').automatic_hit(self,attacker,target,move):
                return True,None,False
            if EQUIPMENT.automatic_accuracy(self,attacker,target,move):
                self.log("    트릭: 자신 또는 실제 동의한 아군, 명중굴림 없음",move_id)
                return True,None,False
            no_status_check=MOVE_ACCURACY.no_status_check(self,attacker,target,move,mm)
            accuracy_required[target.entity_id]=not no_status_check
            if no_status_check:
                return self.accuracy_check(attacker,target,move,situational,roll_id=roll_id)
            if _shared_accuracy is None:
                extra = {'reliable_trainer':reliable_trainer} if reliable_trainer is not None else {}
                return self.accuracy_check(attacker, target, move, situational, roll_id=roll_id, **extra)
            scope=MOVE_ACTIVATION.current_scope(self,attacker,target,move_id)
            if scope is None:raise ValueError("actual shared accuracy scope required")
            scope["actual_accuracy_index"]=index
            rolls = _shared_accuracy.setdefault("rolls", [])
            while len(rolls) <= index:
                import fast_combat as FAST_COMBAT
                first=__import__('oracle').replace_d20(self,attacker,FAST_COMBAT.roll(self,attacker),'shared_accuracy')
                rolls.append(__import__('roll_context').observe_native(self,attacker,'accuracy',first,lambda faces:POOLS.die(self.rng,20,fixed=None if faces is None else faces[0])))
            return self.accuracy_check(attacker, target, move, situational,
                                       fixed_roll=rolls[index], shared_roll=_shared_accuracy)

        remained=__import__('telepath').reaction(self,attacker,target,move,True,completion_id)
        if (mr := EXT.multi_roll_spec(mm)) is not None:
            res = [check_accuracy(i) for i in range(int(mr.get("rolls", 3)))]
            hit = any(h for h, _, _ in res)
            nat = max((n for _, n, _ in res if n is not None),default=None)
            crit = any(c_ for _, _, c_ in res) if mr.get("crit_if_any_crit") else all(c_ for _, _, c_ in res)
            move=__import__('multi_strike').record(self,attacker,target,move,res)
            self._move_completions[completion_id].setdefault('target_moves',{})[target.entity_id]=move
            attacker.counters["multi_hits"] = sum(1 for h, _, _ in res if h)
            self.log(f"    다중 굴림 {len(res)}회: 명중 {attacker.counters['multi_hits']}회 → {'명중' if hit else '빗나감'}{' (치명타)' if hit and crit else ''}", "effect/multi_roll")
        else:
            hit, nat, crit = check_accuracy()
        hit=hit and remained
        move = __import__('researcher_fields').after_accuracy(self,attacker,move,nat)
        PASSIVE_EVENTS.note_accuracy(self,passive_event,hit,nat,crit)
        if __import__('earned_status_choices').native(move,mm):
            move=__import__('earned_status_choices').observe(self,attacker,target,move,res,passive_event,
                completion_id,hit=hit,critical=crit,natural=nat)
            self._move_completions[completion_id]['target_moves'][target.entity_id]=move
        PRECISE.accuracy(precision_event,hit)
        EQUIPMENT.record_accuracy(self,attacker,target,move,hit,nat)
        return PASSIVE_EVENTS.after_accuracy(self,
            attacker=attacker,target=target,move_id=move_id,move=move,mm=mm,conf=conf,
            hit=hit,nat=nat,crit=crit,set_damage=set_damage,standard_context=standard_context,
            passive_event=passive_event,precision_event=precision_event,weather_attack=weather_attack,
            completion_id=completion_id,
            ordinary_single=(count_use and not free_action and _activation is None
                             and _shared_accuracy is None and _action_grant is None))

    @ACTION.resolved_move
    def _finish_move_resolution(self, attacker, target, move_id, move, mm, conf, hit, nat, crit, set_damage, standard_context, passive_event, precision_event, weather_attack, *, ordinary_single, completion_id=None, _accuracy_hit=None):
        """Native post-accuracy continuation; never repays or rerolls activation.

        Only the admitted producer supplies this state. Reaction suspension must
        preserve that producer state rather than call use_move again.
        """
        import type_ace as TA
        # A reflection changes this recipient's result, not its accuracy witness.
        if _accuracy_hit is None:_accuracy_hit=hit
        reaction_args=dict(attacker=attacker,target=target,move_id=move_id,move=move,mm=mm,conf=conf,hit=hit,nat=nat,crit=crit,set_damage=set_damage,standard_context=standard_context,passive_event=passive_event,precision_event=precision_event,weather_attack=weather_attack,ordinary_single=ordinary_single,completion_id=completion_id)
        __import__('warper').reaction(self,reaction_args)
        hit=reaction_args['hit']
        completion=getattr(self,'_move_completions',{}).get(completion_id,{})
        if (not getattr(self,'_reactive_move_transaction',False)
                and (REACTIVE_ABILITIES.interested(self,attacker,target)
                     or DEFENSE.interested(self,attacker,target)
                     or ABILITY_INTERRUPTS.interested(self)
                     or ABILITY_INTERRUPTS.bound(self,passive_event)
                     or ABILITY_REACTIONS.interested(self)
                     or ABILITY_REACTIONS.bound(self,passive_event)
                     or DEFENSE.routed(self,passive_event)
                     or completion.get(REACTIVE_ABILITIES.TAG))):
            def staged(e,a,t):
                import state_grants as G
                options=G._stage_transition_payload(self,e,dict(move=move,mm=mm,conf=conf,hit=hit,nat=nat,crit=crit,
                    set_damage=set_damage,standard_context=standard_context,passive_event=passive_event,
                    precision_event=precision_event,weather_attack=weather_attack,
                    ordinary_single=ordinary_single,completion_id=completion_id,_accuracy_hit=_accuracy_hit))
                from inspect import unwrap
                return unwrap(Engine._finish_move_resolution)(e,a,t,move_id,**options)
            return REACTIVE_ABILITIES.atomic_move(self,attacker,target,staged)
        if DEFENSE.routed(self,passive_event):
            return DEFENSE.finish(self,dict(attacker=attacker,target=target,move_id=move_id,
                move=move,mm=mm,conf=conf,hit=hit,nat=nat,crit=crit,set_damage=set_damage,
                standard_context=standard_context,passive_event=passive_event,
                precision_event=precision_event,weather_attack=weather_attack,
                ordinary_single=ordinary_single,completion_id=completion_id))
        import move_completion as COMPLETE
        result=self._apply_move_recipient(attacker,target,move_id,move,mm,conf,hit,nat,crit,
            set_damage,precision_event,weather_attack,ordinary_single=ordinary_single,
            completion_id=completion_id,passive_event=passive_event)
        standard_event=self._heavy_standard_receipts.get(standard_context,{}).get('event_id')
        HEAVY_STANDARD.finish(self,standard_context,hit=result['hit'],dealt=result['dealt'])
        return PASSIVE_EVENTS.after_recipient(self,dict(attacker=attacker,target=target,
            move_id=move_id,move=move,mm=mm,conf=conf,hit=_accuracy_hit,nat=nat,crit=crit,
            set_damage=set_damage,standard_context=None,completed_standard_event=standard_event,passive_event=passive_event,
            precision_event=precision_event,weather_attack=weather_attack,
            ordinary_single=ordinary_single,completion_id=completion_id),result)

    def _resolve_move_recipient(self, attacker, recipient, move_id, move, mm, conf, hit,
            nat, crit, set_damage, precision_event, weather_attack, *, ordinary_single,
            completion_id, passive_event, defense_token):
        """Resolve only a recipient admitted by the actual native defense producer."""
        DEFENSE.require_recipient(self,defense_token,attacker,recipient,move,completion_id)
        return self._apply_move_recipient(attacker,recipient,move_id,move,mm,conf,hit,nat,
            crit,set_damage,precision_event,weather_attack,ordinary_single=ordinary_single,
            completion_id=completion_id,passive_event=passive_event,
            _defense_token=defense_token)

    @__import__("endure").recipient_scope
    def _apply_move_recipient(self, attacker, target, move_id, move, mm, conf, hit, nat,
            crit, set_damage, precision_event, weather_attack, *, ordinary_single,
            completion_id, passive_event, _defense_token=None):
        """Shared effects leaf; completion and reaction ownership stays with its producer."""
        cached_prefix=__import__('coordinator').recipient_prefix(self,passive_event,attacker,target,move_id)
        if cached_prefix is not None:
            return self._apply_hit_recipient(attacker,target,move_id,move,mm,conf,hit,nat,crit,set_damage,precision_event,weather_attack,ordinary_single=ordinary_single,completion_id=completion_id,passive_event=passive_event,_defense_token=_defense_token,substitute=cached_prefix['substitute'],completion_receipts=set(cached_prefix['completion_receipts']))
        if hit and move_id in __import__('warper').MOVES:__import__('warper').resolve_self_move(self,attacker,move_id)
        if getattr(self,'_move_completions',{}).get(completion_id,{}).get('drown_out',{}).get('cancelled'):
            return dict(hit=False,dealt=0,held=0,hit_prevented=True,effects=[])
        import condition_instances as CONDITIONS
        completion_receipts=set(getattr(self,'_effect_dispatch_receipts',{}))
        # Intercept keeps the original accuracy witness, but its actual recipient
        # can forbid the hit. Reuse the direct native gate before on-hit payment
        # or any secondary/legacy effect; zero damage alone is never a miss.
        no_hit_reason=EXT.blocks_hit(self,attacker,target,move,mm)
        if _defense_token is not None and DEFENSE.recipient_prevented(self,_defense_token,attacker,target,move,completion_id):
            no_hit_reason='native defense avoidance'
        if hit and no_hit_reason:
            self.log("    공격 명중 불가: "+no_hit_reason,no_hit_reason)
            import precise_actions as PRECISE
            PRECISE.damage_hit(self,attacker,target,move,precision_event,
                dict(hit_prevented=no_hit_reason,nullification='cannot_hit'),0)
            hit=False
        hit=__import__('combat_move_reactions').before_recipient(self,attacker,target,move,hit,completion_id)
        if target.entity_id in __import__('oracle').prescience_misses(self,passive_event):hit=False
        hit=__import__('type_ace').incoming_hit(self,attacker,target,move,hit)
        __import__('type_ace').miss(self,attacker,move,hit)
        if not __import__('tumbler').hit(self,attacker,target,move,completion_id,hit,passive_event):
            return dict(hit=False,dealt=0,held=0,hit_prevented=True,effects=[])
        if not hit:
            import conditional_damage_base as CONDITIONAL_DB
            CONDITIONAL_DB.miss(attacker, move)
            import forced_move_lock as FORCED_MOVE
            FORCED_MOVE.miss(self, attacker, move)
            ctx = {"attacker": attacker, "target": target, "nat": nat, "hit": False, "dealt": 0, "crit": False, "move": move, "engine": self}
            miss_effects=[] if no_hit_reason else [e for e in mm.get("effects_exec", []) if e.get("on_miss")]
            miss_effects=__import__('jump_kick').miss_effects(move,miss_effects)
            miss_effects=__import__('martial_artist').miss_effects(self,attacker,move,miss_effects)
            ctx['move_completion']=completion_id
            import attack_damage_history as DAMAGE_HISTORY
            with DAMAGE_HISTORY.native_effects(self,attacker,target,move,completion_id):
                miss_done, miss_held = FX.run_effects(self, attacker, target, miss_effects, ctx, f"{move_id} ({conf})")
                import duelist as DUELIST
                import type_ace as TYPE_ACE
                smite = 0
                if not no_hit_reason and move.get('class') in ('물리','특수'):
                    ace_scope = TYPE_ACE.scope(self,attacker,move)
                    if DUELIST.interrupt_attack(self,attacker,target,move) is not None:
                        smite = DUELIST.smite(self,attacker,target,move,set_damage)
                    elif move.get('_type_ace_boo') or ace_scope and ace_scope['feature'] == TYPE_ACE.uid('Gneiss Aim'):
                        smite = TYPE_ACE.smite(self,attacker,target,move,set_damage)
                    elif {'강타','Smite'} & EXT.keywords_for(attacker,move):
                        # Selected ch10 Smite: half damage, without target secondary effects.
                        facts = {}
                        smite = M.ratio(self.roll_damage(attacker,target,move,False,set_damage,_precision_observation=facts),2)
                        DAMAGE_HISTORY.apply_smite(self,attacker,target,move,smite,facts.get('actual_damage_type',move['type']))
            return dict(hit=False,dealt=smite,held=miss_held,hit_prevented=bool(no_hit_reason),
                effects=[key for key in getattr(self,'_effect_dispatch_receipts',{}) if key not in completion_receipts])
        substitute=__import__('substitute').intercept(self,attacker,target,move)
        water_absorbed=__import__('weather_passive_benefits').absorbs_water(self,attacker,target,move,mm,substitute=substitute)
        if substitute is None and not water_absorbed and move['class'] in ('물리','특수'):__import__('illusion_state').end_ability_illusion(self,target,'damaging Move hit: '+move_id)
        if substitute is None and not water_absorbed:
            __import__('type_ace').observe_close_quarters_hit(self,attacker,target,move,passive_event)
            __import__("endure").offer(self,attacker,target,move,completion_id,passive_event)
            __import__('ninja').poison_hit(self,attacker,target,move,nat)
        __import__('coordinator').recipient_prefix(self,passive_event,attacker,target,move_id,{'substitute':substitute,'completion_receipts':list(completion_receipts)})
        return self._apply_hit_recipient(attacker,target,move_id,move,mm,conf,hit,nat,crit,set_damage,precision_event,weather_attack,ordinary_single=ordinary_single,completion_id=completion_id,passive_event=passive_event,_defense_token=_defense_token,substitute=substitute,completion_receipts=completion_receipts)

    @__import__('berserker').native_hit
    def _apply_hit_recipient(self,attacker,target,move_id,move,mm,conf,hit,nat,crit,set_damage,precision_event,weather_attack,*,ordinary_single,completion_id,passive_event,_defense_token,substitute,completion_receipts):
        import attack_damage_history as WEATHER_HISTORY
        with WEATHER_HISTORY.native_effects(self,attacker,target,move,completion_id):
            water_immunity=__import__('weather_passive_benefits').water_hit(self,attacker,target,move,mm,completion_id,substitute=substitute,natural=nat,critical=crit,defense_token=_defense_token)
        if water_immunity is not None:return water_immunity
        __import__('conquerors_march').observe_hit(self,attacker,target,move,completion_id,passive_event)
        __import__('trickster').accuracy_hit(self,attacker,target,move,completion_id,nat,crit)
        import condition_instances as CONDITIONS
        reactive_contact=__import__('reactive_ability_events').native_contact(self,attacker,move)
        dealt = 0
        reactive_damage_observation={}
        import gleeful_interference as GLEEFUL
        observed=self._passive_events.get(passive_event,{})
        if substitute is None and not (observed.get('coordinator_damage') or observed.get('rider_damage_selection') or observed.get('taskmaster_gambit_damage')):GLEEFUL.observe_hit(self,attacker,target,move,passive_event)
        import optional_move_modes as OPTIONAL_MODES
        if not (observed.get('coordinator_damage') or observed.get('rider_damage_selection') or observed.get('taskmaster_gambit_damage')):OPTIONAL_MODES.on_hit(self,attacker,target,move,completion_id)
        __import__('fortress').guardian_hit(self,attacker,target,move,completion_id,passive_event=passive_event,defense_token=_defense_token)
        import attack_damage_history as DAMAGE_HISTORY
        if (move["class"] in ("물리", "특수") and '_retrospective_hp_loss' not in move
                and not DAMAGE_HISTORY.direct_hp_loss(move,mm)):
            import taskmaster_gambit as GAMBIT
            for receipt_attempt in range(2):
                diagnostic = HEAVY.certify_native_context(self,attacker,target,move,mm,
                    ordinary_single=ordinary_single)
                # Issuance remains inside the already-authorized/use-counted
                # producer, including after its actual counter has returned.
                heavy_context = object()
                self._heavy_activation_sequence += 1
                self._heavy_native_receipts[heavy_context] = dict(diagnostic=diagnostic,
                    attacker=attacker,target=target,move_id=move_id,round=self.round_no,
                    active_actor=self._active_turn_actor,move_uses=attacker.move_uses.get(move_id,0),
                    history_length=len(getattr(attacker,"_action_history",[])),
                    activation_epoch=self._heavy_activation_sequence,weather_attack=weather_attack,completion_id=completion_id)
                try:
                    dealt = self.resolve_attack_damage(attacker, target, move, crit, set_damage,
                        _heavy_context=heavy_context, _passive_event=passive_event, _precision_event=precision_event,
                        _damage_observation=reactive_damage_observation,
                        _defense_token=_defense_token,_completion_id=completion_id)
                    if type(dealt) is dict and '_gambit_parent_receipt_refresh' in dealt:
                        if receipt_attempt:raise ValueError('parent receipt already reissued after actual counter')
                        GAMBIT.validate_parent_refresh(self,dealt,attacker,target,move,passive_event,heavy_context)
                        continue
                    break
                finally:
                    self._heavy_native_receipts.pop(heavy_context,None)
        if reactive_damage_observation.get('channeler_pain'):
            return dict(hit=True,dealt=0,held=0,hit_prevented=False,melee_contact=reactive_contact,channeler_pain=reactive_damage_observation['channeler_pain'],effects=[key for key in getattr(self,'_effect_dispatch_receipts',{}) if key not in completion_receipts])
        if substitute is not None:
            if move_id == 'move/목숨걸기':
                # The coat intercepts the target damage, never the user's cost.
                mm = dict(mm, effects_exec=[dict(effect,target='self') if effect.get('type')=='self_hp_set' else effect
                                           for effect in mm.get('effects_exec',[])])
            mm=__import__('substitute').mechanics(move,mm)
        actual_type = reactive_damage_observation.get("actual_damage_type",move["type"])
        # 효과 (hand mech 우선, 없으면 auto)
        import eldritch_magic as ELDRITCH
        if substitute is None:
            ELDRITCH.after_hit(self,attacker,target,move,nat,completion_id=completion_id,
                defense_token=_defense_token)
            __import__("combat_modifiers").incoming_status_hit(self,attacker,target,move,mm,nat)
        if "apply_status" in mm:
            self.apply_status(target, mm["apply_status"],source=move_id,applied_by=attacker,parameters=CONDITIONS.native_parameters(self,attacker,target,mm["apply_status"]))
        if "on_natural_roll" in mm and nat is not None and CPF.effect_natural(self,attacker,move,nat,actual_damage_type=actual_type) >= __import__("combat_modifiers").incoming_status_threshold(target,mm["on_natural_roll"].get("apply_status"),mm["on_natural_roll"]["min"]):
            o = mm["on_natural_roll"]
            self.log(f"    자연 {nat} ≥ {o['min']}: 추가 효과 발동", f"{move_id} ({conf})")
            if "apply_status" in o:
                self.apply_status(target, o["apply_status"],source=move_id,applied_by=attacker)
            if "stage_change" in o:
                tgt = attacker if o["stage_change"].get("target") == "self" else target
                if tgt is attacker:tgt = __import__('combat_move_reactions').snatch_recipient(self,attacker,target,move_id,{'move_completion':completion_id}) or tgt
                FX.apply_stage_changes(self, attacker, tgt,
                    {o["stage_change"]["stat"]: o["stage_change"]["delta"]}, source_id=move_id)
        for sc in mm.get("stage_changes_exec", []):
            tgt = attacker if sc.get("target") == "self" else target
            if tgt is attacker:tgt = __import__('combat_move_reactions').snatch_recipient(self,attacker,target,move_id,{'move_completion':completion_id}) or tgt
            stats = ["atk", "def", "spa", "spd", "spe"] if sc["stat"] == "all" else [sc["stat"]]
            changes = {st: sc["delta"] for st in stats if st in tgt.stages}
            if changes:
                FX.apply_stage_changes(self, attacker, tgt, changes, source_id=move_id)
        if "drain" in mm and dealt:
            self.log(f"    흡수: 입힌 피해 {dealt}의 {mm['drain']['fraction']} 회복", f"{move_id} ({conf})")
            self.heal(attacker, M.product(dealt,mm["drain"]["fraction"]))
        if "zone" in mm:
            import smoke_regions as SMOKE_REGIONS
            SMOKE_REGIONS.apply(self, target, move, mm["zone"], move_id, conf)
        if "evasion_mod" in mm:
            import state_grants as GRANTS
            if not GRANTS.adjust_numeric(target, "evasion_mod", mm["evasion_mod"]["value"]):
                target.evasion_mod = max(-6,min(6,target.evasion_mod + mm["evasion_mod"]["value"]))
            self.log(f"    {target.name} 회피 {mm['evasion_mod']['value']:+d}", f"{move_id} ({conf})")
        if conf == "auto":
            for sc in mm.get("stage_changes", []):
                FX.apply_stage_changes(self, attacker, target,
                    {STAT_KO[sc["stat"]]: sc["delta"]}, source_id=move_id)
            for st in mm.get("status", []):
                self.apply_status(target, st,source=move_id,applied_by=attacker)
        ctx = {"attacker": attacker, "target": target, "nat": nat, "hit": True, "dealt": dealt, "crit": crit, "move": move, "engine": self, "db": mm.get("header", {}).get("db") if isinstance(mm.get("header"), dict) else None,
               "multiplier": reactive_damage_observation["type_multiplier"] if "type_multiplier" in reactive_damage_observation else self.type_multiplier(move["type"], target)[0], "actual_damage_type": actual_type, "ko": target.fainted}
        ctx['move_completion']=completion_id
        import ability_state_projection as ABILITY_STATE_PROJECTION
        if substitute is None:
            ABILITY_STATE_PROJECTION.after_hit(self,target,multiplier=ctx['multiplier'],dealt=dealt)
            __import__('researcher_fields').relic_after_hit(self,attacker,target,move,dealt)
        with DAMAGE_HISTORY.native_effects(self,attacker,target,move,completion_id):
            done, held = FX.run_effects(self, attacker, target, mm.get("effects_exec", []), ctx, f"{move_id} ({conf})")
        if move_id == "move/목숨걸기":
            dealt = DAMAGE_HISTORY.effect_damage_total(self, attacker, target, move_id, completion_receipts)
            ctx["dealt"] = dealt
        self.effect_stats["done"] += done
        self.effect_stats["held"] += held
        EXT.after_move(self, attacker, target, move, mm, ctx)
        __import__('telekinetic').after_hit(self,attacker,target,move,completion_id)
        __import__('telepath').after_hit(self,attacker,target,move,completion_id)
        import class_passive_combat as CLASS_PASSIVE
        if substitute is None:CLASS_PASSIVE.after_move(self,attacker,target,move,mm,nat,dealt,actual_damage_type=actual_type)
        FX.fire_event(self, attacker, {"event": "on_hit_dealt", "move": move, "dealt": dealt}, target)
        if substitute is None:
            with DAMAGE_HISTORY.native_effects(self,attacker,target,move,completion_id):
                __import__('weather_passive_benefits').fire_hit(self,attacker,target,move,completion_id,actual_type,defense_token=_defense_token)
            FX.fire_event(self, target, {"event": "on_hit_received", "move": move, "dealt": dealt}, attacker)
            __import__('type_ace').after_damage(self,attacker,target,move,dealt,crit)
            __import__('hunter').after_damage(self,attacker,target,move,dealt)
        if target.fainted:
            FX.fire_event(self, attacker, {"event": "enemy_faint_by_user", "move": move}, target)
            FX.fire_event(self, target, {"event": "self_faint", "move": move}, attacker)
        result=dict(hit=True,dealt=0 if substitute is not None else dealt,held=held,
            hit_prevented=substitute is not None or bool(reactive_damage_observation.get('hit_prevented')),
            melee_contact=reactive_contact,
            effects=[key for key in getattr(self,'_effect_dispatch_receipts',{}) if key not in completion_receipts])
        receipt=reactive_damage_observation.get('substitute_damage')
        if receipt is not None:result['substitute_damage']=receipt
        return result

    def choose_move_status(self, actor, event_id, choices):
        return __import__('earned_status_choices').choose(self,actor,event_id,choices)

    def resolve_maneuver_grant(self, actor, grant_id, **choices):
        import maneuver_grants as MG
        return MG.resolve(self,actor,grant_id,**choices)

    def quick_wit(self, actor, target, **options):
        return __import__('provocateur').quick_wit(self,actor,target,**options)

    def play_them_like_a_fiddle(self, actor, target, completion_id, **options):
        return __import__('provocateur').fiddle(self,actor,target,completion_id,**options)

    def enchanting_gaze(self, actor, kind, *, aim):
        return __import__('provocateur').gaze(self,actor,kind,aim=aim)

    def choose_defense_curl_source(self, actor, variant, *, reason):
        return __import__('defense_curl').choose_source(self,actor,variant,reason=reason)

    def stop_defense_curl(self, actor):
        return __import__('defense_curl').stop(self,actor)

    def take_breather(self, actor, **options):
        import breather as BREATHER
        return BREATHER.take(self,actor,**options)

    def resolve_stamina(self, actor, action_id, *, skill=None):
        import stamina as STAMINA
        return STAMINA.resolve(self,actor,action_id,skill=skill)

    def enable_execution_trace(self, enabled=True):
        TRACE.enable(self,enabled)

    def execution_traces(self, trace_id=None):
        return TRACE.records(self,trace_id)

    def event_trace(self, event_id):
        import event_trace
        return event_trace.event(self,event_id)

    def evaluate_source_policy_composition_bundle(self, actor, target, plan, contributors):
        import composition_derive as COMPOSITION
        return COMPOSITION.bundle(self,actor,target,plan,contributors)

    def evaluate_source_policy_composition(self, actor, target, document, **options):
        import composition_derive as COMPOSITION
        return COMPOSITION.policy(self,actor,target,document,**options)

    def evaluate_source_policy_qualification(self, actor, target, document, **options):
        import acquisition_qualification as Q
        return Q.policy(self,actor,target,document,**options)

    def source_policy_execution(self, execution_id):
        """Read actual source/input/decision evidence for a completed execution."""
        import source_policy
        return source_policy.execution_record(self, execution_id)

    def acquisition_account(self, actor):
        import acquisition_receipts as RECEIPTS
        return RECEIPTS.account(self,actor)

    def configure_form_allocations(self, actor, forms, *, active, source):
        import form_allocations as FORMS
        return FORMS.configure(self,actor,forms,active=active,source=source)

    def commit_growth_nature(self, actor, target, nature, **declaration):
        import growth_stats as GROWTH
        return GROWTH.commit_nature(self,actor,target,nature,**declaration)

    def plan_growth_nature(self, actor, nature, *, investment=None):
        import growth_stats as GROWTH
        return GROWTH.nature_plan(self,actor,nature,investment=investment)

    def configure_growth_forms(self, actor, declarations, *, active, source):
        import growth_stats as GROWTH
        return GROWTH.configure_forms(self,actor,declarations,active=active,source=source)

    def import_growth_investment(self, actor, investment, *, source, reason, request_id):
        import growth_stats as GROWTH
        return GROWTH.import_investment(self,actor,investment,source=source,reason=reason,request_id=request_id)

    def growth_stat_projection(self, actor):
        import growth_stats as GROWTH
        return GROWTH.project_actor(self,actor)

    def form_allocation_projection(self, actor):
        import form_allocations as FORMS
        return FORMS.project(actor)

    def bind_grant_reconciliation(self, actor, source_id, document, *, cause):
        import composition_reconcile as COMPOSITION
        return COMPOSITION.bind(self,actor,source_id,document,cause=cause)

    def bind_grant_withdrawal_policy(self, actor, source_id, policies):
        import acquisition_withdrawal as WITHDRAWAL
        return WITHDRAWAL.bind_policy(self,actor,source_id,policies)

    def bind_grant_dependencies(self, actor, source_id, depends_on):
        import acquisition_withdrawal as W
        return W.dependencies(self,actor,source_id,depends_on)

    def record_irreversible_grant_use(self, actor, source_id, *, event_id, reason):
        import acquisition_withdrawal as W
        return W.irreversible(self,actor,source_id,event_id=event_id,reason=reason)

    def retrain_trainer_source(self, actor, rule_id, **decision):
        import acquisition_withdrawal as W
        return W.retrain(self, actor, rule_id, **decision)

    def acquisition_receipts(self, actor):
        import acquisition_receipts as RECEIPTS
        return RECEIPTS.read(self,actor)

    def acquire_grant_group(self, actor, group_id, grants, points, **options):
        """Host-adjudicated source grants with one actual Tutor Point debit."""
        import grant_payments
        return grant_payments.acquire(self,actor,group_id,grants,points,**options)

    def refund_grant_sources(self, actor, sources, **options):
        """Withdraw payment-backed sources using explicit refund allocation."""
        import grant_payments
        return grant_payments.refund(self,actor,sources,**options)

    def execute_source_policy_operations(self, actor, target, document, *, context=None, decisions=None, request_id=None,
                                         tool_instance_id=None):
        """Execute an external ordered program with native atomicity and evidence."""
        import source_policy
        return source_policy.execute_operations(self,actor,target,document,
            context=context,decisions=decisions,request_id=request_id,tool_instance_id=tool_instance_id)

    def execute_source_policy_training(self, actor, document, *, context=None, decisions=None, request_id=None):
        """Execute source-bound multi-Pokemon training through native consumers."""
        import source_policy
        return source_policy.execute_training(self, actor, document,
            context=context, decisions=decisions, request_id=request_id)

    def execute_source_policy_teaching(self, actor, target, document, *, context=None, decisions=None, request_id=None):
        """Run source-bound JSON teaching through the native acquisition paths."""
        import source_policy
        return source_policy.execute_teaching(self, actor, target, document,
            context=context, decisions=decisions, request_id=request_id)

    def execute_source_policy_progression(self, actor, target, document, *, context=None, decisions=None, request_id=None):
        """Run external trainer growth declarations through native progression."""
        import source_policy
        return source_policy.execute_progression(self, actor, target, document,
            context=context, decisions=decisions, request_id=request_id)

    def execute_source_policy_grants(self, actor, target, document, *, context=None, decisions=None, request_id=None):
        """Execute a source-bound JSON grant payment or withdrawal declaration."""
        import source_policy
        return source_policy.execute_grants(self, actor, target, document,
                                            context=context, decisions=decisions, request_id=request_id)

    def execute_source_policy_action(self, actor, target, document, *, context=None, decisions=None, request_id=None):
        """Ordinary combat action, AP and effects commit together; acquisition is separate."""
        import source_policy
        return source_policy.execute_effects(self, actor, target, document,
                                             context=context, decisions=decisions, request_id=request_id, _action=True)

    def execute_source_policy_effects(self, actor, target, document, *, context=None, decisions=None, request_id=None):
        """Application-authorized source-bound effects; action legality is separate."""
        import source_policy
        return source_policy.execute_effects(self, actor, target, document,
                                             context=context, decisions=decisions, request_id=request_id)

    def apply_effect(self, attacker, target, e, nat, hit, dealt, src):
        """Compatibility entry uses the same preflight/dispatcher as native moves."""
        HEAVY.ensure_clear(self)
        ctx={'attacker':attacker,'target':target,'nat':nat,'hit':hit,
             'dealt':dealt,'engine':self}
        FX.preflight_effects(self,attacker,target,[e],src)
        return FX.run_effects(self,attacker,target,[e],ctx,src)

    def end_effects(self, actor, *, source=None, occurrence=None):
        """End source-owned common effects selected by their actual provenance."""
        import effect_lifetime_policy as EFFECT_TIME
        return EFFECT_TIME.end_selected(self,actor,source=source,occurrence=occurrence)

    def activate_fashion_item(self, actor, item_id, *, target=None, instance_id=None):
        """Activate one of the reviewed crafted Fashion battle contracts."""
        import fashion_items as FASHION
        return FASHION.activate(self,actor,item_id,target=target,instance_id=instance_id)

    def arm_fashion_reaction(self, actor, item_id, *, instance_id=None):
        """Accept the next actual trigger for an optional Fashion reaction."""
        import fashion_items as FASHION
        return FASHION.arm_reaction(self,actor,item_id,instance_id=instance_id)

    def spatial_state(self, actor):
        import body_state as BODY
        return {'body': BODY.projection(actor), 'flanking': BODY.flanking(self,actor)}

    def adjacent(self, left, right, *, cardinal=False):
        import mapless_space as MAPLESS
        if self.grid is None and MAPLESS.active(self):
            if cardinal:raise ValueError('mapless contact has no inferred cardinal direction')
            return MAPLESS.adjacent(self,left,right)
        import body_state as BODY
        return BODY.adjacent(left,right,cardinal=cardinal)

    def spatial_evasion_penalty(self, target):
        if self.grid is None:return 0
        import body_state as BODY
        state=BODY.flanking(self,target)
        if state['flanked'] is None:raise ValueError('Flanking needs observed geometry: '+', '.join(state['pending']))
        return state['evasion_penalty']

    # ---------- 격자: 범위 키워드로 대상 선택 ----------
    def shape_ground(self, actor, changes, *, reason):
        import terrain_actions as TERRAIN
        return TERRAIN.shape(self,actor,changes,reason=reason)

    def change_body_mode(self, actor, mode, **options):
        import body_modes as MODES
        return MODES.change(self,actor,mode,**options)

    def move_shadow(self, actor, path, **observation):
        import body_modes as MODES
        return MODES.shadow_move(self,actor,path,**observation)

    def targets_in_range(self, attacker, move, candidates, primary):
        """실효 범위에서 자신 대상을 고르고, 다른 범위는 Grid 또는 primary로 선택한다."""
        import body_state as BODY
        import weapon_actions as WEAPONS
        origin_part=move.get('_body_origin_part')
        move = WEAPONS.prepare(self,attacker,move)
        import pokemon_move_edges as POKE_MOVE_EDGES
        move = POKE_MOVE_EDGES.prepare(self,attacker,move)
        move = BODY.bind_origin(self,attacker,move,origin_part)
        rng = WEAPONS.range_spec(self,move,attacker)
        if WEAPONS.is_field(rng):
            WEAPONS.field_members(self)
            return [attacker]
        if WEAPONS.is_self_only(rng) or WEAPONS.is_blessing(rng):
            return [attacker]
        selected=__import__('glitch_moves').selected_targets(self,attacker,move,candidates,primary)
        if selected is not None:return selected
        selected=WEAPONS.selected_targets(self,attacker,move,candidates,primary)
        if selected is not None:return selected
        if self.grid is None:
            import mapless_space as MAPLESS
            if MAPLESS.active(self):return MAPLESS.targets(self,attacker,move,candidates,primary)
            return [primary]
        if '_area_aim' in move:
            import area_targets as AREA
            return AREA.targets(self,attacker,move,candidates)
        shape, size, origin = rng.get("shape"), rng.get("size"), rng.get("origin")
        import body_modes as MODES
        import setup_move_state as SETUP_MOVE
        import marsupial_state as MARSUPIAL
        others = [c for c in candidates if c is not attacker and not c.fainted and not c.captured
                  and MARSUPIAL.target_present(c,engine=self) and MODES.target_visible(self,attacker,c)
                  and SETUP_MOVE.targetable(c,engine=self,attacker=attacker,move=move)]
        import stat_ace as STAT
        selected=__import__('rune_master').selected_targets(self,attacker,move,others,primary)
        if selected is not None:return selected
        selected=__import__('ace_trainer').selected_targets(self,attacker,move,others,primary)
        if selected is not None:return selected
        selected=STAT.selected_targets(self,attacker,move,others,primary)
        if selected is not None:return selected
        if shape == "burst":
            cells = self.grid.burst(attacker.pos, size) | {attacker.pos}
            return [c for c in others if BODY.cells(c,require_complete=True).intersection(cells)]
        if shape in ("cone", "line", "close_blast"):
            dx = (primary.pos[0] > attacker.pos[0]) - (primary.pos[0] < attacker.pos[0])
            dy = (primary.pos[1] > attacker.pos[1]) - (primary.pos[1] < attacker.pos[1])
            d = (dx if (dx or dy) else 1, dy)
            if shape == "cone":
                cells = self.grid.cone(attacker.pos, d, size)
            elif shape == "line":
                cells = self.grid.line(attacker.pos, d, size)
            else:
                cells = self.grid.close_blast(attacker.pos, size, d)
            hit = [c for c in others if BODY.cells(c,require_complete=True).intersection(cells)]
            self.log(f"    범위 {rng.get('raw')}: 방향 {d}, 칸 {len(cells)}개 → {', '.join(c.name for c in hit) or '아무도 없음'}", "ch10/범위-키워드")
            return hit
        if shape == "blast":
            cells = self.grid.ranged_blast(primary.pos, size)
            return [c for c in others if BODY.cells(c,require_complete=True).intersection(cells)]
        if primary not in others:
            return []
        reach = BODY.melee_reach(attacker) if origin == "melee" else (origin if isinstance(origin, int) else 99)
        if not BODY.in_range(self,__import__('rune_master').range_actor(self,__import__('type_ace').range_actor(self,attacker,move),move),primary,reach,move=move):
            return []
        return [primary]

    def configure_party_combat(self,trainer,**options):
        import party_actions as PARTY_ACTIONS
        return PARTY_ACTIONS.configure(self,trainer,**options)

    def configure_gym_challenge(self,leader,**options):
        import party_actions as PARTY_ACTIONS
        return PARTY_ACTIONS.configure_gym(self,leader,**options)

    def act_on_party(self,trainer,**options):
        import party_actions as PARTY_ACTIONS
        return PARTY_ACTIONS.act(self,trainer,**options)

    def observe_map_terrain(self,cells,**options):
        import map_terrain as TERRAIN
        return TERRAIN.observe(self,cells,**options)

    def move_abstract(self, actor, **declaration):
        import mapless_space as MAPLESS
        return MAPLESS.move(self,actor,**declaration)

    def move_relative(self, actor, **declaration):
        import relative_movement as RELATIVE
        return RELATIVE.move(self,actor,**declaration)

    def observe_relative_directions(self, actor, **observation):
        import relative_movement as RELATIVE
        return RELATIVE.observe_directions(self,actor,**observation)

    def equip_living_weapon(self, wielder, pokemon, *, consent, slots=None, source_choice=None, no_guard_choice=None):
        import living_weapon as LIVING
        return LIVING.equip(self,wielder,pokemon,consent=consent,slots=slots,source_choice=source_choice,no_guard_choice=no_guard_choice)

    def separate_living_weapon(self, actor, *, destination=None):
        import living_weapon as LIVING
        return LIVING.detach(self,actor,destination=destination)

    def move_profile(self, c, movement_mode=None, *, as_slowed=False):
        """(이동 거리, 방식): 공중/부유 이동이 육상보다 빠르면 그걸 쓴다 — 공중·부유는 둔화/험한 지형 비용을 무시한다(차단 지형은 통과 못 함)."""
        import movement_actions as MOVEMENT
        import living_weapon as LIVING
        donor=LIVING.movement_donor(self,c)
        if donor is not c:return self.move_profile(donor,movement_mode=movement_mode,as_slowed=as_slowed)
        mv = MOVEMENT.capabilities(self,c)
        import pokemon_understanding as UNDERSTANDING
        UNDERSTANDING.require_activity(self,c,'movement')
        land = mv.get("land", c.movement)
        sky = max(mv.get("sky", 0), mv.get("levitate", 0))
        value,mode=EXT.movement_profile(self,c,land,sky,movement_mode=movement_mode,capabilities=mv,as_slowed=as_slowed)
        return CAPABILITIES.movement_limit(c,value),mode

    def approve_skill_stunt(self, actor, **options):
        import skill_stunts as STUNTS
        return STUNTS.approve(self,actor,**options)

    def offer_let_me_help(self, helper, target, **options):
        return __import__('skill_feature_actions').offer_help(self,helper,target,**options)

    def apply_mulch(self, actor, plant_id, *, soil_quality=0, reason):
        import cultivation_state as CULTIVATION
        return CULTIVATION.apply_mulch(self,actor,plant_id,soil_quality=soil_quality,reason=reason)

    def observe_cultivation_site(self, actor, site_id, **observation):
        import cultivation_growth as GROWTH
        return GROWTH.observe_site(self,actor,site_id,**observation)

    def plant_growth(self, actor, declaration, **options):
        import cultivation_growth as GROWTH
        return GROWTH.plant(self,actor,declaration,**options)

    def growth_status(self, actor, plant_id, **observation):
        import cultivation_growth as GROWTH
        return GROWTH.status(self,actor,plant_id,**observation)

    def fertilize_growth(self, actor, plant_id, **options):
        import cultivation_growth as GROWTH
        return GROWTH.fertilize(self,actor,plant_id,**options)

    def harvest_growth(self, actor, declaration, **options):
        import cultivation_harvest as HARVEST
        return HARVEST.harvest(self,actor,declaration,**options)

    def activate_blender(self, actor, *, reason):
        import blender_state as BLENDER
        return BLENDER.activate(self,actor,reason=reason)

    def blender_state(self, actor):
        import blender_state as BLENDER
        return BLENDER.projection(actor)

    def change_invisibility(self, actor, enabled, *, reason):
        import invisibility_state as INVISIBILITY
        return INVISIBILITY.change(self,actor,enabled,reason=reason)

    def invisibility_state(self, actor):
        import invisibility_state as INVISIBILITY
        return INVISIBILITY.projection(self,actor)

    def observe_invisibility_elapsed(self, actor, seconds, *, reason):
        import invisibility_state as INVISIBILITY
        return INVISIBILITY.observe_elapsed(self,actor,seconds,reason=reason)

    def choose_silence(self, actor, enabled, *, reason):
        import sound_state as SOUND
        return SOUND.choose(self,actor,enabled,reason=reason)

    def sound_state(self, actor):
        import sound_state as SOUND
        return SOUND.projection(actor)

    def set_aura_openness(self, target, reader, allowed, *, reason):
        import aura_pulse as PULSE
        return PULSE.willingness(self,target,reader,allowed,reason=reason)

    def project_aura_thought(self, sender, recipient, thought):
        import aura_pulse as PULSE
        return PULSE.project(self,sender,recipient,thought)

    def read_aura_thought(self, reader, target):
        import aura_pulse as PULSE
        return PULSE.read(self,reader,target)

    def read_telepathic_thought(self, reader, target, **options):
        policy=options.pop('source_policy','korean_ch10')
        if policy not in ('core_1.05','korean_ch10'):raise ValueError('explicit printed Telepathy source policy required')
        return __import__('telepathy_core' if policy=='core_1.05' else 'telepathy').read(self,reader,target,**options)

    def project_telepathic_thought(self, sender, recipients, thought, **options):
        policy=options.pop('source_policy','korean_ch10')
        if policy not in ('core_1.05','korean_ch10'):raise ValueError('explicit printed Telepathy source policy required')
        return __import__('telepathy_core' if policy=='core_1.05' else 'telepathy').project(self,sender,recipients,thought,**options)

    def offer_telepathic_thought(self, trainer, telepath, thought, **options):
        import telepathy
        return telepathy.offer(self,trainer,telepath,thought,**options)

    def telepathy_attempts(self, actor=None, **options):
        import telepathy
        return telepathy.events(self,actor,**options)

    def telekinetic_struggle_policy(self, decision=None):
        import telekinetic_combat as TK
        return TK.struggle_policy(self,decision)

    def underdog_bonus_policy(self, actor, source='poke_edge/잠재력-발견', decision=None, *, species=None):
        import world_entities as W,underdog_edges as U
        W.require_actors(self,actor)
        return U.bonus_policy(self.r,actor.spec,U.ALIASES.get(source,source),decision,species=species)

    def teach_personal_tutor(self, actor, **options):
        import personal_tutoring as PERSONAL_TUTOR
        return PERSONAL_TUTOR.teach(self, actor, **options)

    def apply_type_sync(self, actor, **options):
        return __import__('type_sync').apply_feature(self,actor,**options)

    def remove_type_sync(self, actor, **options):
        return __import__('type_sync').remove_feature(self,actor,**options)

    def acquire_mentor_feature(self, actor, feature='class/멘토', **options):
        return __import__('mentor').acquire(self,actor,feature,**options)

    def acquire_hobbyist_feature(self, actor, feature='class/하비스트', **options):
        return __import__('hobbyist').acquire(self,actor,feature,**options)

    def look_and_learn(self, actor, feature, **options):
        return __import__('hobbyist').look_and_learn(self,actor,feature,**options)

    def claim_dabbler_reward(self, actor, level, **options):
        return __import__('hobbyist').dabbler_reward(self,actor,level,**options)

    def acquire_milestone_general_feature(self, actor, level, feature, **options):
        return __import__('trainer_milestone_rewards').acquire_general_feature(self,actor,level,feature,**options)

    def mentor_lesson(self, actor, target, name, **options):
        return __import__('mentor').lesson(self,actor,target,name,**options)

    def expand_horizons(self, actor, target, **options):
        return __import__('mentor').expand(self,actor,target,**options)

    def choose_inheritance_move(self, actor, level, move, **options):
        return __import__('growth_milestones').choose_inheritance(self,actor,level,move,**options)

    def mentor_egg_list_policy(self, actor, target, document, **options):
        return __import__('mentor').egg_list_policy(self,actor,target,document,**options)

    def edit_mentor_egg_list(self, actor, target, move, **options):
        return __import__('mentor').edit_egg_list(self,actor,target,move,**options)

    def hm_teaching_policy(self, actor, *, target, instance_id, decision=None):
        import pokemon_teaching as TEACHING
        return TEACHING.hm_teaching_policy(self,actor,target=target,instance_id=instance_id,decision=decision)

    def telekinetic_maneuver(self, actor, target, kind, **options):
        PASSIVE_EVENTS.ensure_clear(self)
        LEAGUE.check_boundary(self, "telekinetic_maneuver")
        HEAVY.ensure_clear(self)
        import telekinetic_combat as TK
        return TK.maneuver(self,actor,target,kind,**options)

    def telekinetic_lift(self, actor, object_ids, **options):
        import telekinetic_load as TK
        return TK.lift(self,actor,object_ids,**options)

    def move_telekinetic_objects(self, actor, paths, **options):
        import telekinetic_load as TK
        return TK.move_objects(self,actor,paths,**options)

    def release_telekinetic_load(self, actor, **options):
        import telekinetic_load as TK
        return TK.release(self,actor,**options)

    def link_keystone(self, actor, stone_id, **options):
        import keystone_state as K
        return K.link(self,actor,stone_id,**options)

    def keystone_warp(self, actor, stone_id, **options):
        import keystone_state as K
        return K.warp(self,actor,stone_id,**options)

    def linked_keystones(self, actor):
        import keystone_state as K
        return K.links(self,actor)

    def capability_product_catalog(self):
        import capability_products as PRODUCTS
        return PRODUCTS.catalog(self.r)

    def collect_capability_product(self, producer, source, **options):
        import capability_products as PRODUCTS
        return PRODUCTS.collect(self,producer,source,**options)

    def read_dream(self, reader, target, *, share=False):
        import dream_state as DREAM
        return DREAM.read(self,reader,target,share=share)

    def declare_focus_punch(self, actor, target=None, *, request_id, path=(), mode='land', reason):
        return __import__('focus_punch').declaration(self,actor,target,request_id=request_id,path=path,mode=mode,reason=reason)

    def choose_focus_punch(self, actor, *, use, target=None, path=(), mode='land', request_id, reason):
        return __import__('focus_punch').choose(self,actor,use=use,target=target,path=path,mode=mode,request_id=request_id,reason=reason)

    def channel_pokemon(self,actor,target,**options):
        return __import__('channeler').channel(self,actor,target,**options)

    def stop_channeling(self,actor,target):
        return __import__('channeler').stop(self,actor,target)

    def observe_channel_information(self,subject,**facts):
        return __import__('perception_observe').observe_channel_information(self,subject,**facts)

    def communicate_channel(self,sender,recipient,fields,**options):
        return __import__('channeler').communicate(self,sender,recipient,fields,**options)

    def imprint_channel(self,actor,target):
        return __import__('channeler').imprint(self,actor,target)

    def release_channel_imprint(self,actor,target):
        return __import__('channeler').release_imprint(self,actor,target)

    def focus_channel_senses(self,actor,target):
        return __import__('channeler').focus(self,actor,target)

    def read_channel_senses(self,actor):
        return __import__('channeler').read_senses(self,actor)

    def synchronize_channel(self,actor):
        return __import__('channeler').synchronize(self,actor)

    def boost_channel_spirit(self,actor,target,donor,**options):
        return __import__('channeler').spirit(self,actor,target,donor,**options)

    def channel_power_conduit(self,actor,donor,recipient,**options):
        return __import__('channeler').conduit(self,actor,donor,recipient,**options)

    def soothe_channel(self,actor,allocation):
        return __import__('channeler').soothing(self,actor,allocation)

    def channel_knowledge(self,actor,target):
        import channeler as CHANNEL
        CHANNEL.require(self,actor,CHANNEL.CLASS);CHANNEL.target(self,actor,target)
        return __import__('perception_observe').channel_information(self,target)

    def activate_aura_reader(self, actor):
        return __import__('aura_guardian').activate_reader(self,actor)

    def spend_aura_blessing(self, actor, choice, *, target=None, status=None):
        return __import__('aura_guardian').spend_blessing(self,actor,choice,target=target,status=status)

    def read_aura(self, reader, target):
        import aura_state as AURA
        return AURA.read(self,reader,target)

    def capability_traits(self, actor):
        import capability_traits as TRAITS
        return TRAITS.projection(actor,engine=self)

    def survivalist_activity(self, actor, activity, **options):
        import survivalist_features as SURVIVALIST
        return SURVIVALIST.activity(self,actor,activity,**options)

    def jump(self, actor, destination, **options):
        import jump_actions as JUMP
        import pokemon_understanding as UNDERSTANDING
        UNDERSTANDING.require_activity(self,actor,'movement')
        return JUMP.jump(self, actor, destination, **options)

    def teleport(self, actor, destination, **options):
        import movement_actions as MOVEMENT
        return MOVEMENT.teleport(self, actor, destination, **options)

    def aerial_move(self, actor, destination, **options):
        import movement_actions as MOVEMENT
        return MOVEMENT.aerial_move(self, actor, destination, **options)

    def sprint(self, actor, **options):
        import movement_actions as MOVEMENT
        import pokemon_understanding as UNDERSTANDING
        UNDERSTANDING.require_activity(self,actor,'movement')
        return MOVEMENT.sprint(self, actor, **options)

    def burrow_move(self, actor, path, **options):
        import movement_actions as MOVEMENT
        return MOVEMENT.burrow_move(self, actor, path, **options)

    def at_initiative_count(self, count):
        PASSIVE_EVENTS.ensure_clear(self)
        LEAGUE.check_boundary(self, "initiative_count")
        HEAVY.ensure_clear(self)
        import combat_timing as TIMING
        import state_grants as GRANTS
        return GRANTS.transition(self,None,lambda staged,_: TIMING.at_count(staged,count))

    def push(self, actor, target, **options):
        import physics_maneuvers as PHYSICS
        return PHYSICS.push(self,actor,target,**options)

    def opposed_maneuver(self, actor, target, declaration, **options):
        import maneuver_opposed as OPPOSED
        return OPPOSED.execute(self,actor,target,declaration,**options)

    def grapple(self, actor, target, **options):
        import grapple_state as GRAPPLE
        return GRAPPLE.initiate(self,actor,target,**options)

    def grapple_action(self, actor, kind, **options):
        import grapple_state as GRAPPLE
        return GRAPPLE.action(self,actor,kind,**options)

    def trip(self, actor, target, **options):
        import physics_maneuvers as PHYSICS
        return PHYSICS.trip(self,actor,target,**options)

    def dirty_fighting(self, actor, target, completion_id, trick, **options):
        return __import__('rogue').dirty_fighting(self,actor,target,completion_id,trick,**options)

    def scoundrel_strike(self, actor, target, completion_id, **options):
        return __import__('rogue').scoundrel_strike(self,actor,target,completion_id,**options)

    def dirty_trick(self, actor, target, trick, **options):
        PASSIVE_EVENTS.ensure_clear(self)
        LEAGUE.check_boundary(self, "dirty_trick")
        HEAVY.ensure_clear(self)
        import combat_maneuvers as MANEUVERS
        return MANEUVERS.dirty_trick(self,actor,target,trick,**options)

    def disarm(self, actor, target, **options):
        PASSIVE_EVENTS.ensure_clear(self)
        LEAGUE.check_boundary(self, 'disarm')
        HEAVY.ensure_clear(self)
        return TURN.disarm(self,actor,target,**options)

    def disengage(self, c, destination, *, movement_mode=None):
        return TURN.disengage(self, c, destination, movement_mode=movement_mode)

    def occupied(self, except_c=None):
        import body_state as BODY
        import control_mount as MOUNT
        ignored=MOUNT.travel_group(self,except_c)
        import living_weapon as LIVING
        ignored=(*ignored,*LIVING.group(self,except_c))
        import body_modes as MODES
        import control_vehicle as CONTROL
        result = CONTROL.occupied_cells(self,except_c)
        for actor in (self.everyone or []):
            if actor not in ignored and not actor.fainted and not actor.captured and getattr(actor, "on_field", True) and not MODES.flat(actor):
                result.update(BODY.cells(actor,require_complete=True))
        return result

    def admit_wild_encounter(self, wearer, candidates, *, nearby, reason):
        import encounter_candidates as CANDIDATES
        return CANDIDATES.admit_wild(self,wearer,candidates,nearby=nearby,reason=reason)

    def observe_repel_approach(self, wearer, target, *, nearby, reason):
        import repels as REPELS
        return REPELS.approach(self,wearer,target,nearby=nearby,reason=reason)

    def observe_repel_flee(self, target, **observation):
        import repels as REPELS
        return REPELS.observe_flee(self,target,**observation)

    def resolve_repel_flee(self, target):
        import repels as REPELS
        return REPELS.flee(self,target)

    def approach(self, c, target, reach=1, *, movement_mode=None, blindness_options=None):
        import living_weapon as LIVING
        if LIVING.relation(self,c):
            import state_grants as G
            def together(e,a,t):
                LIVING.relation(e,a,usable=True)
                remaining=LIVING.movement_remaining(e,a,movement_mode=movement_mode)
                if remaining is not None:remaining=int(remaining)
                blind_cursor=a.spec.get('_survivalist_shift')
                if remaining==0 and not (isinstance(blind_cursor,dict) and blind_cursor.get('finished') is False):
                    return {'distance':0,'position':a.pos,'mode':e.move_profile(a,movement_mode=movement_mode)[1]}
                result=e._approach(a,t,reach,movement_mode=movement_mode,blindness_options=blindness_options,maximum_distance=remaining)
                LIVING.sync(e,a)
                return result
            return G.transition(self,c,together,participants=(target,))
        import environment_change as EC
        if EC.managed(self,c):
            return EC.run(self,c,lambda e,a,t:e.approach(a,t,reach,movement_mode=movement_mode,blindness_options=blindness_options),participants=(target,))
        import control_mount as MOUNT
        if MOUNT.manages(self,c):return MOUNT.approach(self,c,target,reach,movement_mode=movement_mode,blindness_options=blindness_options)
        if __import__('commander_orders').passers(self,c):
            import state_grants as G
            return G.transition(self,c,lambda e,a,t:e._approach(a,t,reach,movement_mode=movement_mode,blindness_options=blindness_options),participants=(target,),include_rulings=True)
        return self._approach(c,target,reach,movement_mode=movement_mode,blindness_options=blindness_options)

    def _approach(self, c, target, reach=1, *, movement_mode=None, blindness_options=None, action_owner=None, maximum_distance=None):
        """이동 행동: 차단 지형과 다른 전투원을 피해(너비 우선 경로) 대상의 사거리 안 가장 가까운 칸으로. 둔화 지형은 2칸 비용(공중/부유는 1칸)."""
        action_owner=c if action_owner is None else action_owner
        import conditional_damage_base as CONDITIONAL_DB
        if CONDITIONAL_DB.action_locked(action_owner):
            self.log(f"  {action_owner.name}: 라운드말 예약 공격 때문에 이동할 수 없음",
                     "conditional_damage_base/round_end_setup")
            return 0
        PASSIVE_EVENTS.ensure_clear(self)
        LEAGUE.check_boundary(self, 'approach')
        HEAVY.ensure_clear(self)
        import survivalist_features as SURVIVALIST
        import movement_actions as MOVEMENT
        import body_state as BODY
        if SURVIVALIST.approach_preflight(self,c,target,reach,movement_mode,blindness_options):return
        if self.grid is None:
            return
        if BODY.in_range(self,c,target,reach):
            return
        budget, mode = self.move_profile(c, movement_mode=movement_mode)
        if movement_mode == "teleport":
            raise ValueError("Teleport movement needs its LOS, surface and once-per-round adapter; walking is not teleportation")
        import burrow_tunnels as TUNNELS
        tunnel_walk = mode in ('land','육상') and TUNNELS.can_pass(self,c,c.pos)
        if movement_mode == "burrow" or (c.spec.get("_burrow",{}).get("underground") and not tunnel_walk):
            raise ValueError("Burrow needs an explicit diggable path and surface/underground destination")
        sprint_rate = False
        if "질주" in c.custom_conditions:
            sprint_rate = __import__('athlete').sprint_rate(self,c)
            budget = M.increase(budget,sprint_rate,quantity='movement',base_id='current_capability',stage='sprint')
        budget=CAPABILITIES.movement_limit(c,budget)
        if maximum_distance is not None:budget=min(budget,maximum_distance)
        occ = self.occupied(c)
        commander_passers=__import__('commander_orders').passers(self,c)
        goal_ok = lambda p: BODY.can_place(self,c,p) and BODY.in_range(self,c,target,reach,left_position=p)
        # 너비 우선 탐색 (비용 가중: 둔화 지형 2)
        import heapq
        start = (*c.pos, getattr(c, "_diagonal_steps", 0) % 2)
        dist = {start: 0}
        prev = {}
        heap = [(0, start)]
        best = None
        while heap:
            d, state = heapq.heappop(heap)
            p, parity = state[:2], state[2]
            if d > dist.get(state, 1e9):
                continue
            if goal_ok(p):
                best = state
                break
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if not dx and not dy:
                        continue
                    q = (p[0] + dx, p[1] + dy)
                    import map_terrain as TERRAIN
                    probe=TUNNELS.at_origin(self,c,p)
                    if not TERRAIN.can_travel(self,probe,q,mode,capability_actor=c,movement_mode=movement_mode) or not BODY.can_place(self,probe,q,origin=p,ignore_actors=commander_passers):
                        continue
                    step,next_diagonals=MOVEMENT.step_cost(p,q,parity)
                    cost = step + MOVEMENT.slow_terrain_penalty(self, c, q, mode,step=step)
                    nxt = (*q, next_diagonals % 2)
                    nd = d + cost
                    if nd < dist.get(nxt, 1e9):
                        dist[nxt] = nd
                        prev[nxt] = state
                        heapq.heappush(heap, (nd, nxt))
        if best is None:
            if not TURN.spend(self,action_owner,"shift","이동",movement=True):return
            if "질주" in c.custom_conditions:MOVEMENT.consume_sprint(c)
            self.log(f"  {c.name} 이동 행동: {target.name}에게 가는 길이 막힘", "ch07/이동과-위치선정")
            return
        path = []
        state = best
        while state != start:
            path.append(state)
            state = prev[state]
        path.reverse()
        blind_plan=SURVIVALIST.prepare_approach(self,c,target,reach,movement_mode,mode,budget,path,blindness_options)
        if not TURN.spend(self,action_owner,'shift','이동',movement=True):return
        if '질주' in c.custom_conditions:MOVEMENT.consume_sprint(c)
        if blind_plan:
            SURVIVALIST.begin_approach(self,c,target,blind_plan,blindness_options)
            return
        movement_progress=None
        if sprint_rate is not False and (movement_mode or mode) in ('sky','공중/부유') and MOVEMENT.capabilities(self,c,environment=False).get('free_float',0)>0:
            movement_progress={}
            MOVEMENT._paid_progress(c,[tuple(node[:2]) for node in path],movement_progress)
            movement_progress['free_float_sprint_rate']=sprint_rate
        movement=MOVEMENT.follow_paid_path(self,c,path,mode=mode,maximum_distance=budget,action_owner=action_owner,movement_mode=movement_mode,progress=movement_progress)
        moved,spent=movement['steps'],movement['distance']
        if moved:
            c.airborne = (mode == "공중/부유")
            self.log(f"  {c.name} 이동 행동: {moved}칸 → {c.pos} ({mode} {budget}{', 경로 ' + str(len(path)) + '칸' if len(path) > moved else ''})", "ch07/이동과-위치선정")
        result={'distance':spent,'position':c.pos,'mode':mode}
        if 'charged_distance' in movement:result['charged_distance']=movement['charged_distance']
        return result

    # ---------- 포획 ----------
    def capture_rate(self, target, rarity=0, *, source_variant=None, hp=None):
        import capture_resolution as CAPTURE
        return CAPTURE.rate(self,target,rarity,source_variant=source_variant,hp=hp)

    def capture_rate_superseded(self, target, hp_fraction, demo_hp_penalty=25):
        """구판(1d100): 데모 재현용. 100 - 2×레벨 - (체력 75%↑: 30, 데모 25) + (진화 2단계 남음: 10) + 5×부상."""
        rate = 100 - 2 * target.level
        if hp_fraction >= 0.75:
            rate -= demo_hp_penalty
        if target.spec.get("evolutions_remaining") == 2:
            rate += 10
        rate += 5 * target.injuries
        return rate

    @BALL_BODY.atomic_throw
    def throw_ball(self, trainer, target, ball_name="몬스터볼", rarity=0, *, fixed_accuracy=None, fixed_capture=None, accuracy_roll_id=None, collector_choice=None, fixed_reroll=None, cannon_instance_id=None, type_manual_instance_id=None, physical_instance_id=None, snare_conversion=None, capture_source=None, curve_ball=False, suppression_case=None, gotta_swap=None,bounce=None):
        """Native capture attempt; retain the actual thrown ball for GM recovery/repair.
        ch05:684-710, ch09:7-17. Damage is a separate observed fact, not an
        automatic consequence assigned to every unsuccessful capture.
        """
        import world_entities as WORLD
        WORLD.require_actors(self, trainer, target)
        import special_entities as SPECIAL
        SPECIAL.require_prime_independent(self,target)
        import body_modes as BODY_MODES
        BODY_MODES.require_targetable(target,engine=self,attacker=trainer)
        import actor_templates as TEMPLATES
        template = TEMPLATES.projection(target)
        if template and template["capture_immune"]:
            self.log(f"    {target.name}: 마지막 체력 바 전에는 포획 면역", "C11-135")
            return False
        TEMPLATES.require_ordinary(target, "boss capture and normal-form restoration")
        import pokemon_activities as POKEMON_ACTIVITIES
        from capability_actions import throwing_range
        PASSIVE_EVENTS.ensure_clear(self)
        LEAGUE.check_boundary(self, 'throw_ball')
        HEAVY.ensure_clear(self)
        import capture_resolution as CAPTURE
        procedure, cr = CAPTURE.bind_native(self.r,capture_source)
        import capture_specialist as SPECIALIST
        combo = SPECIALIST.combo_allowed(self,trainer,target)
        if not TURN.can_act(self, trainer):
            return False
        if trainer.kind != 'trainer' or target.kind != 'pokemon':
            raise ValueError('capture needs a trainer and a Pokemon target')
        if ((target.fainted or target.hp <= 0) and not combo) or target.dead or target.captured or getattr(target,'side',None) == "party" or target.spec.get('trainer_id') or target.spec.get('trainer'):
            self.log(f"    {target.name}: 기절했거나 이미 주인이 있어 포획 불가", "pokemon/capture-rate")
            return False
        import captured_momentum as MOMENTUM
        momentum_plan = MOMENTUM.capture_plan(self,trainer,capture_source)
        if fixed_accuracy is not None: CHECKS.integer(fixed_accuracy,'capture accuracy d20',1,20)
        if fixed_capture is not None: CHECKS.integer(fixed_capture,'capture die',1,procedure.sides)
        if fixed_reroll is not None: CHECKS.integer(fixed_reroll,'collector reroll d20',1,20)
        collector=POKEMON_ACTIVITIES.collector_eligible(self,trainer,collector_choice is not None or fixed_reroll is not None)
        choice_callback=collector_choice if callable(collector_choice) else None
        choice=None if choice_callback else POKEMON_ACTIVITIES.collector_choice(collector_choice,trainer.spec.get('collector_stacks',0))
        if fixed_reroll is not None and not choice_callback and choice['kind']!='reroll':
            raise ValueError('fixed reroll requires the collector reroll choice')
        CHECKS.integer(rarity,'GM capture rarity')
        AP_ROLL.bonus(self,trainer,accuracy_roll_id,'accuracy')
        name=ITEMS.ball_name(self.r.items_mech.get(ball_name,{}).get('name',ball_name))
        import csv_item_physical_contracts as CSV_ITEMS
        cannon = CSV_ITEMS.cannon_profile(self,trainer,cannon_instance_id,projectile='ball') if cannon_instance_id is not None else None
        manual_bonus = 0 if type_manual_instance_id is None else M.ratio(-CSV_ITEMS.manual_capture_modifier(self,trainer,target,type_manual_instance_id),5)
        book_manual=__import__('study_books').type_capture(trainer,target)
        if book_manual:
            manual_bonus=min(manual_bonus,book_manual) if procedure.sides==100 else max(manual_bonus,M.ratio(-book_manual,5))
        inv=trainer.spec.get('items',{})
        inventory_key=ITEMS.ball_inventory_key(trainer,ball_name)
        if cannon is not None:
            ammo=self._physical_objects[cannon['ball_instance_id']]
            if ITEMS.ball_name(self.r.items_mech.get(self.r._selected_rule(ammo['item_rule_id']),{}).get('name',ammo['item_rule_id'])) != name:raise ValueError('Cannon must fire its actual loaded ball kind')
            inventory_key=ammo['item_rule_id']
        if physical_instance_id is not None:
            inventory_key=BALL_BODY.physical(self,trainer,physical_instance_id)['item_rule_id']
        if inventory_key is None:
            product=BALL_BODY.ball_rule(self,name)
            if CHECKS.integer(inv.get(product,0),'actual owned ball count',0):inventory_key=product
        if inventory_key is None:
            self.log(f'    {trainer.name}: 소유한 {name} 없음 → 포획 불가','pokemon/capture-rate')
            return False
        if name not in ITEMS.BALL_RULES:
            effects,header=self.r.item_effects(ball_name)
            if not effects or not any(e.get('type')=='capture_mod' for e in effects):
                raise ValueError('unsupported capture ball')
        else:
            # Consult source selection even when the numerical policy is known.
            self.r._selected_rule('item/'+name)
        bounce_plan=None if bounce is None else __import__('juggler').bounce_plan(self,trainer,target,bounce)
        if bounce_plan is not None and cannon is not None:raise ValueError('Bounce Shot requires the actual hand-thrown ball')
        maximum=cannon['range_m'] if cannon is not None else throwing_range(self,trainer,category='poke_ball')
        range_position=target.pos if bounce_plan is None else tuple(bounce_plan['landing'])
        if cheb(trainer.pos,range_position)>maximum:
            self.log(f'    {target.name}: 볼 투척 사거리 {maximum}m 밖 → 포획 불가','pokemon/capture-rate')
            return False
        rate,boxes=self.capture_rate(target,rarity,source_variant=capture_source,hp=1 if combo else None)
        physical_plan=BALL_BODY.prepare(self,trainer,name,inventory_key,physical_instance_id,cannon)
        book_ball_accuracy=__import__('study_books').ball_accuracy(self,physical_instance_id if cannon is None else cannon['ball_instance_id'])
        bonus=-trainer.level if procedure.sides==100 else max([b for lv,b in cr['trainer_bonus_by_level'].items() if trainer.level>=int(lv)],default=0)
        bmod,bwhy=CAPTURE.ball_modifier(self,name,trainer,target,procedure)
        import wild_equipment as WILD
        snare_bonus=WILD.snare_bonus(self,trainer,target,conversion=snare_conversion,source_variant=capture_source)
        import net_capsule as NET
        net_bonus=NET.capture_bonus(self,target)*(-5 if procedure.sides==100 else 1)+SPECIALIST.net_modifier(self,target,procedure)
        tools_accuracy=SPECIALIST.tools_accuracy(self,trainer,'cap_cannon' if cannon is not None else 'ball') if __import__('capture_techniques')._rows(trainer) else WILD.tools_bonus(self,trainer,'accuracy')
        curve_plan=SPECIALIST.ball_plan(self,trainer,curve_ball=curve_ball,suppression_case=suppression_case,standard=not combo,physical_plan=physical_plan)
        SPECIALIST.gotta_preflight(self,trainer,procedure,gotta_swap)
        new_family=POKEMON_ACTIVITIES.collector_new_family(self,trainer,target) if collector else False
        import pokemon_party as POKEMON_PARTY
        placement_plan=POKEMON_PARTY.preflight_capture(self,trainer,target)
        import event_effects as EVENTS,roll_effects as ROLLS
        EVENTS.validate_for_use(self,trainer)
        ROLLS.require_origin(trainer,'accuracy')
        ball={'id':'ball','name':ball_name,'class':'변화','ac':cr['throw']['ac'],'type':'노말'}
        import confusion_attacks as CONFUSION
        CONFUSION.preflight(self,trainer,ball)
        if not combo and not TURN.spend(self,trainer,'standard',ball_name):return False
        if cannon is not None:CSV_ITEMS.fire_cannon(self,trainer,cannon_instance_id,ball_instance_id=cannon['ball_instance_id'])
        attempts=trainer.spec.setdefault('capture_attempts',{})
        serial=trainer.spec.get('capture_attempt_serial',0)+1
        trainer.spec['capture_attempt_serial']=serial
        attempt_id='capture-'+str(serial)
        record={'id':attempt_id,'item':inventory_key,'ball_kind':'poke_ball','target':target.spec.get('id',target.name),'hit':False,'captured':False,'status':'thrown','source':'pokemon/capture-rate'}
        attempts[attempt_id]=record
        record.update(capture_source=capture_source,action='free' if combo else 'standard')
        if snare_conversion is not None:
            record['snare_conversion']={'authority':'gm_ruling','source':'input/ch04-trainer-classes.md:405-407','book_modifier':-10,'procedure':{'source':procedure.source,'sides':procedure.sides,'comparison':procedure.comparison},'attempt_id':attempt_id,'request':dict(snare_conversion),'applied_modifier':snare_bonus}
        actual_ball=BALL_BODY.launch(self,trainer,target,record,physical_plan)
        WORLD._set_object_location(actual_ball,{'kind':'grid','cell':list(target.pos)})
        if cannon is not None:
            record['cannon']=dict(cannon,instance_id=cannon_instance_id)
            import world_entities as WORLD
            WORLD._set_object_location(self._physical_objects[cannon['ball_instance_id']],{'kind':'grid','cell':list(target.pos)})
        if type_manual_instance_id is not None:record['type_manual']={'instance_id':type_manual_instance_id,'bonus':manual_bonus,'source':'C2CSV/inventory:70:1'}
        __import__('juggler').capture_launch(self,trainer,target,record,actual_ball,bounce_plan)
        CONFUSION.observe_action(self,trainer,ball)
        accuracy_options={'situational':tools_accuracy+book_ball_accuracy+(cannon['accuracy_bonus'] if cannon is not None else 0)}
        if fixed_accuracy is not None:accuracy_options['fixed_roll']=fixed_accuracy
        if accuracy_roll_id is not None:accuracy_options['roll_id']=accuracy_roll_id
        hit,nat,_=self.accuracy_check(trainer,target,ball,**accuracy_options)
        record.update(hit=hit,accuracy_natural=nat,tools_accuracy=tools_accuracy)
        if not hit:
            record['status']=procedure.miss_state
            __import__('juggler').capture_function(self,trainer,record,actual_ball,hit=False)
            BALL_BODY.miss(self,trainer,record)
            return False
        SPECIALIST.ball_hit(self,trainer,target,record,curve_plan)
        return CAPTURE._post_hit(self,trainer,target,record=record,actual_ball=actual_ball,
            combo=combo,rarity=rarity,capture_source=capture_source,cannon=cannon,
            momentum_plan=momentum_plan,fixed_capture=fixed_capture,procedure=procedure,
            gotta_swap=gotta_swap,nat=nat,choice_callback=choice_callback,bonus=bonus,
            bmod=bmod,bwhy=bwhy,snare_bonus=snare_bonus,net_bonus=net_bonus,
            manual_bonus=manual_bonus,fixed_reroll=fixed_reroll,choice=choice,
            collector=collector,new_family=new_family,placement_plan=placement_plan,
            name=name,ball_name=ball_name)

    def choose_captured_momentum(self, actor, *, attempt_id, choice, target=None, conversion=None, composition=None, ap_policy=None,capture_source=None):
        import captured_momentum as MOMENTUM
        return MOMENTUM.choose(self,actor,attempt_id=attempt_id,choice=choice,target=target,conversion=conversion,composition=composition,ap_policy=ap_policy,capture_source=capture_source)

    def devitalizing_throw(self,actor,**options):
        return __import__('capture_specialist').devitalize(self,actor,**options)

    def fast_pitch(self,actor,target,ball_name='몬스터볼',**options):
        return __import__('capture_specialist').fast_pitch(self,actor,target,ball_name,**options)

    def use_capture_tool(self,actor,target,object_id,**options):
        return __import__('capture_specialist').use_tool(self,actor,target,object_id,**options)

    def use_motivated(self, actor, instance_id, stat):
        import cheerleader as CHEER
        return CHEER.motivate(self,actor,instance_id,stat)

    def moment_of_action(self, actor, targets, *, funding, allies, communication=None):
        import moment_of_action as MOMENT
        return MOMENT.use(self,actor,targets,funding=funding,allies=allies,communication=communication)

    def go_fight_win(self, actor, *, cheer, stat=None, communication=None):
        import go_fight_win as GO
        return GO.use(self,actor,cheer=cheer,stat=stat,communication=communication)

    def open_common_checks(self, registry, registration, actors, configuration, principals=()):
        """Bind admitted ordinary-check sessions to these native actors.

        Registry and GM/roller capabilities are installed by the host. Existing
        numeric helpers remain separate; this path preserves pending receipts.
        """
        import root_common_engine
        return root_common_engine.EngineCheckBinding(self, registry, registration, actors, configuration, principals)

    # ---------- 스킬 체크 (d6 풀) ----------
    def evaluate_source_policy_roll_plan(self, actor, target, document, *, purpose, **options):
        import roll_context as ROLL_CONTEXT
        return ROLL_CONTEXT.policy(self,actor,target,document,purpose=purpose,**options)

    def execute_source_policy_rolls(self, submissions, procedure, *, request_id):
        import roll_context as ROLL_CONTEXT
        return ROLL_CONTEXT.execute_policies(self,submissions,procedure,request_id=request_id)

    def choose_growth_ability(self, actor, level, ability, *, reason):
        import growth_milestones as MILESTONES
        return MILESTONES.choose_ability(self,actor,level,ability,reason=reason)

    def choose_growth_inheritance(self, actor, level, move, *, reason):
        import growth_milestones as MILESTONES
        return MILESTONES.choose_inheritance(self,actor,level,move,reason=reason)

    def plan_rank_context(self, actor, skill, *, purpose, targets, source, provider=None):
        import roll_context as ROLL_CONTEXT
        return ROLL_CONTEXT.rank_plan(self,actor,skill,purpose=purpose,targets=targets,source=source,provider=provider)

    def plan_skill_check(self, actor, skill, *, purpose, target=None, provider=None, replacement=None, **options):
        import roll_context as ROLL_CONTEXT
        return ROLL_CONTEXT.plan(self,actor,skill,purpose=purpose,target=target,provider=provider,replacement=replacement,**options)

    def resolve_roll_context(self, requests, procedure, *, request_id=None, observed_choices=None):
        import roll_context as ROLL_CONTEXT
        return ROLL_CONTEXT.resolve(self,requests,procedure,request_id=request_id,observed_choices=observed_choices)

    def _prepare_skill_roll(self, c, skill, mods=0, helper_rank=0, fixed=None, *, penalty_count=0, fixed_penalties=None, roll_id=None, helper_bonus=None, feature=None, feature_options=None, skill_context=None, skill_stunt=None, skill_target=None, helper_source=None):
        M.validate_source(self.r)
        import pokemon_intelligence as INTELLIGENCE
        INTELLIGENCE.require_skill(self,c,skill)
        import pokemon_understanding as UNDERSTANDING
        UNDERSTANDING.require_activity(self,c,'skill')
        """Ordinary rank procedure; validate the entire request before consuming RNG."""
        import environmental_effects as ENVIRONMENT
        ENVIRONMENT.ensure_clear(self)
        import skill_feature_actions as SF
        if feature is not None:
            return SF.prepare(self,c,skill,feature,feature_options,dict(mods=mods,helper_rank=helper_rank,fixed=fixed,penalty_count=penalty_count,fixed_penalties=fixed_penalties,roll_id=roll_id,helper_bonus=helper_bonus,skill_context=skill_context,skill_stunt=skill_stunt,skill_target=skill_target,helper_source=helper_source))
        if feature_options is not None:raise ValueError('feature options require a selected feature')
        if getattr(c,'dead',False) or getattr(c,'fainted',False):
            raise ValueError('unconscious actor requires a sourced action exception')
        import blessing_skill_features as BLESSINGS
        BLESSINGS.validate_sleep_check(self,c,skill,skill_context)
        import living_weapon as LIVING
        living_sources=LIVING.check_sources(self,c,skill_context)
        blessing_context=skill_context
        if isinstance(blessing_context,dict) and 'living_weapon' in blessing_context:
            blessing_context={k:v for k,v in blessing_context.items() if k!='living_weapon'} or None
        shared_skill_context=BLESSINGS.ADVANCED.shared_context(blessing_context)
        self.r.mech("gameplay/skill-check")
        AP_ROLL.bonus(self,c,roll_id,'skill')
        import researcher_features as RF
        pokemon_plan=RF.native_plan(self,c,skill)
        rank_name,expr,n = (pokemon_plan['rank_name'],pokemon_plan['expression'],pokemon_plan['rank']) if pokemon_plan is not None else SKILL_MODIFIERS.rank(self.r,c,skill)
        resolved = SKILL_MODIFIERS.modifiers(self.r,c,skill,mods,skill_context=shared_skill_context)
        import taskmaster as TASK
        press_bonus=TASK.obedience_bonus(self,c,shared_skill_context,skill_target)
        resolved['modifier']+=press_bonus
        if press_bonus:resolved['sources']+=((TASK.PRESS_ACTION,press_bonus,'Press obedience this round'),)
        profile_sources=__import__('chronicler').profile_bonus(self,c,skill,skill_target)
        resolved['modifier']+=sum(x[1] for x in profile_sources)
        resolved['sources']+=profile_sources
        resolved['modifier']+=sum(x[1] for x in living_sources)
        resolved['sources']+=living_sources
        import environment_derive as ED
        environment_sources=ED.skill(self,c,skill)
        resolved['modifier']+=sum(x[1] for x in environment_sources)
        resolved['sources']+=environment_sources
        import scene_lighting as LIGHT
        light_sources=LIGHT.skill_modifier(self,c,skill,skill_target)
        resolved['modifier']+=sum(x[1] for x in light_sources)
        resolved['sources']+=light_sources
        import survivalist_features as SURVIVALIST
        # Press owns this purpose; terrain ownership and unconditional bonuses still apply.
        terrain_context=None if TASK.is_obedience_context(shared_skill_context) else shared_skill_context
        terrain_sources=SURVIVALIST.modifier(self,c,skill,terrain_context)
        resolved['modifier']+=sum(x[1] for x in terrain_sources)
        resolved['sources']+=terrain_sources
        import elemental_connection as ELEMENTAL
        elemental_sources=ELEMENTAL.modifier(self,c,skill,skill_target)
        if elemental_sources:
            contributions=[{'id':'elemental:'+str(i),'source':source,'value':value}
                           for i,(source,value,detail) in enumerate(elemental_sources)]
            resolved['modifier']=SKILL_MODIFIERS.COMPOSITION.derive(resolved['modifier'],contributions,
                [{'law':'add','contributors':[row['id'] for row in contributions]}])['value']
        resolved['sources']+=elemental_sources
        blessing_sources=BLESSINGS.modifiers(self,c,skill,blessing_context)
        resolved['modifier']+=sum(x[1] for x in blessing_sources)
        resolved['sources']+=blessing_sources
        if pokemon_plan is not None:
            resolved['modifier']+=pokemon_plan['modifier']
            resolved['pokemon_plan']=pokemon_plan
        resolved['dice_count']=int(expr[:-2]) if pokemon_plan is None else pokemon_plan['dice_count']
        blessing_plan=BLESSINGS.ADVANCED.prepare(
            self,c,skill,resolved,blessing_context,skill_target)
        resolved['modifier']+=blessing_plan['modifier']
        resolved['sources']+=tuple(blessing_plan['modifier_sources'])
        resolved['dice_count']+=blessing_plan['bonus_dice']
        resolved['blessing_skill_plan']=blessing_plan
        import tk_mastery as TK_MASTERY
        tk_bonus=TK_MASTERY.carry_bonus(self,c,skill,skill_context)
        resolved['dice_count']+=tk_bonus
        if tk_bonus:resolved['sources']+=((TK_MASTERY.SOURCE,tk_bonus,'Telekinetic Focus dice'),)
        import athlete as ATHLETE
        coaching_bonus=ATHLETE.coaching_dice(self,c,skill)
        resolved['dice_count']+=coaching_bonus
        if coaching_bonus:resolved['sources']+=((ATHLETE.COACHING,coaching_bonus,'Coaching bonus die'),)
        import skill_stunts as STUNTS
        STUNTS.apply(self,c,skill,resolved,skill_stunt)
        import combat_timing as TIMING
        import training_features as TRAINING
        training_bonus = TRAINING.bonus(c,"skill")
        import fashion_items as FASHION
        resolved["modifier"] += TIMING.skill_modifier(c) + training_bonus + FASHION.all_roll_modifier(c)
        if training_bonus:resolved["sources"] += (("training/features",training_bonus,"Focused"),)
        # rank() or the Pokemon adapter already validated the selected rank/pool.
        SKILL_MODIFIERS.validate_helper(self,c,helper_rank,helper_bonus,helper_source)
        CHECKS.validate_resolved_request(mods,helper_rank,penalty_count,helper_bonus)
        faces = CHECKS.dice(fixed,resolved['dice_count']) if fixed is not None else None
        penalties = CHECKS.dice(fixed_penalties,penalty_count) if fixed_penalties is not None else None
        return rank_name,expr,n,faces,penalties,resolved

    @__import__('roll_context').native_choices
    def skill_roll(self, c, skill, mods=0, helper_rank=0, fixed=None, *, penalty_count=0, fixed_penalties=None, roll_id=None, helper_bonus=None, feature=None, feature_options=None, skill_context=None, skill_stunt=None, skill_target=None, helper_source=None):
        import skill_feature_actions as SF
        import blessing_skill_features as BLESSINGS
        offer=getattr(self,'_let_me_help_offers',{}).get(c.entity_id)
        if roll_id is None and offer is not None:
            stem=offer['request_id']+'/target-check';roll_id=stem
            ordinal=1
            while roll_id in self._ap_rolls:
                ordinal+=1;roll_id=stem+'/'+str(ordinal)
        options=dict(mods=mods,helper_rank=helper_rank,fixed=fixed,penalty_count=penalty_count,fixed_penalties=fixed_penalties,roll_id=roll_id,helper_bonus=helper_bonus,skill_context=skill_context,skill_stunt=skill_stunt,skill_target=skill_target,helper_source=helper_source)
        if feature is not None:return SF.roll(self,c,skill,feature,feature_options,options)
        if feature_options is not None:raise ValueError('feature options require a selected feature')
        rank_name,expr,n,faces,penalties,resolved=self._prepare_skill_roll(c,skill,mods,helper_rank,fixed,penalty_count=penalty_count,fixed_penalties=fixed_penalties,roll_id=roll_id,helper_bonus=helper_bonus,skill_context=skill_context,skill_stunt=skill_stunt,skill_target=skill_target,helper_source=helper_source)
        prepared=(rank_name,expr,n,faces,penalties,resolved)
        faces=tuple(POOLS.pool(self.rng,resolved['dice_count'],fixed=faces)['faces'])
        faces = BLESSINGS.ADVANCED.apply_faces(
            self,c,faces,resolved['blessing_skill_plan'])
        penalties = tuple(POOLS.pool(self.rng, penalty_count, fixed=penalties)['faces'])
        mods=resolved["modifier"]+AP_ROLL.bonus(self,c,roll_id,'skill')
        if resolved.get('skill_stunt') is not None or (resolved.get('pokemon_plan') is None and (int(expr[:-2])!=n or n>6 or helper_rank>6 and helper_rank!=8)):
            result=CHECKS.AdjustedSkillRoll(n,faces,mods,helper_rank,penalties,helper_bonus,resolved['dice_count'])
        elif resolved['dice_count']!=n or n>6 or helper_rank>6 and helper_rank!=8:
            import researcher_features as RF
            result=RF.PokemonSkillRoll(n,faces,mods,helper_rank,penalties,helper_bonus,resolved['dice_count'])
        else:result=CHECKS.SkillRoll(n,faces,mods,helper_rank,penalties,helper_bonus)
        def reroll_native_skill(replacement):
            from dataclasses import replace
            count=resolved['dice_count']
            all_faces=POOLS.pool(self.rng,count+penalty_count,fixed=replacement)['faces']
            new_faces=tuple(BLESSINGS.ADVANCED.apply_faces(self,c,tuple(all_faces[:count]),resolved['blessing_skill_plan']))
            return replace(result,faces=new_faces,penalties=tuple(all_faces[count:]))
        result=__import__('roll_context').observe_native(self,c,'skill',result,reroll_native_skill)
        faces,penalties=result.faces,result.penalties
        BLESSINGS.ADVANCED.finish(self,c,resolved['blessing_skill_plan'])
        AP_ROLL.complete(self,c,roll_id,'skill')
        SF.observe(self,c,skill,result,prepared,options)
        for uid,value,choice in resolved["sources"]:
            self.log(f"  스킬 보너스 {uid}: {choice} +{value}",uid)
        self.log(f"  {c.name} {skill}({rank_name}) {expr}{mods:+d} 지원 +{M.ratio(helper_rank,2) if helper_bonus is None else helper_bonus}, 패널티 {penalties}: {faces} → {result.total}", "gameplay/skill-check")
        return result

    def skill_check(self, c, skill, dc, mods=0, helper_rank=0, fixed=None, *, penalty_count=0, fixed_penalties=None, roll_id=None, helper_bonus=None, feature=None, feature_options=None, skill_context=None, skill_stunt=None, skill_target=None, helper_source=None):
        CHECKS.integer(dc,'DC')
        import skill_feature_actions as SF
        result=SF.check_with_help(self,c,skill,dc,{'roll_id':roll_id},lambda:self.skill_roll(c,skill,mods,helper_rank,fixed,penalty_count=penalty_count,fixed_penalties=fixed_penalties,roll_id=roll_id,helper_bonus=helper_bonus,feature=feature,feature_options=feature_options,skill_context=skill_context,skill_stunt=skill_stunt,skill_target=skill_target,helper_source=helper_source))
        SF.finish(self,c,roll_id)
        self.log(f"  판정 {result.total} vs DC {dc}, 차이 {result.margin} → {'성공' if result.passed else '실패'}", "gameplay/skill-check")
        return result.passed,result.total

    def opposed_check(self, a, skill_a, b, skill_b, *, challenger_options=None, defender_options=None):
        """b must be the defender maintaining the status quo; ties favor b."""
        if a is b:raise ValueError('opposed check requires two distinct participants')
        challenger_options={} if challenger_options is None else dict(challenger_options)
        defender_options={} if defender_options is None else dict(defender_options)
        import skill_targets as TARGETS
        challenger_options=TARGETS.bind(self,challenger_options,b)
        defender_options=TARGETS.bind(self,defender_options,a)
        import skill_feature_actions as SF
        if any(o.get('feature') is not None for o in (challenger_options,defender_options)):
            return SF.opposed(self,a,skill_a,b,skill_b,challenger_options,defender_options)
        if challenger_options.get('roll_id') is not None and challenger_options.get('roll_id') == defender_options.get('roll_id'):
            raise ValueError('each opposed roll needs its own identity')
        for actor,skill,options in ((a,skill_a,challenger_options),(b,skill_b,defender_options)):
            prepared=self._prepare_skill_roll(actor,skill,**options)
            if prepared[3] is not None:options['fixed']=prepared[3]
            if prepared[4] is not None:options['fixed_penalties']=prepared[4]
        ra=self.skill_roll(a,skill_a,**challenger_options)
        rb=self.skill_roll(b,skill_b,**defender_options)
        SF.finish(self,a,challenger_options.get('roll_id'))
        SF.finish(self,b,defender_options.get('roll_id'))
        winner,(ra,rb)=SF.resolve_opposed(self,[(a,skill_a,challenger_options),(b,skill_b,defender_options)],[ra,rb])
        self.log(f"  대항 체크: {a.name} {ra.total} vs {b.name} {rb.total} → {'공격 측 승' if winner=='challenger' else '수비 측 승(동률 포함)'}", "gameplay/skill-check")
        return winner=='challenger'

    def craft_relic_crown(self, trainer, pokemon, **options):
        import researcher_features as RF
        return RF.craft_relic_crown(self,trainer,pokemon,**options)

    def equip_relic_crown(self, trainer, pokemon, identity):
        import researcher_features as RF
        return RF.equip_relic_crown(self,trainer,pokemon,identity)

    def contest_skill_feature(self, trainer, pokemon, feature, skill, dc, **options):
        import contest_features
        return contest_features.skill_feature(self, trainer, pokemon, feature, skill, dc, **options)

    def style_move(self,trainer,pokemon,target,move,**options):
        import style_expert as STYLE
        return STYLE.use_move(self,trainer,pokemon,target,move,**options)

    def enticing_beauty(self,trainer,pokemon):
        import style_expert as STYLE
        return STYLE.entice(self,trainer,pokemon)

    def style_endurance(self,trainer,pokemon,kind,**options):
        import style_expert as STYLE
        return STYLE.use_endurance(self,trainer,pokemon,kind,**options)

    def difficulty_guidance(self):
        import adjudication_guidance as GUIDANCE
        return GUIDANCE.policy(self)

    def configure_pokedex(self, actor, selection, **facts):
        import pokedex_device as POKEDEX
        return POKEDEX.configure(self, actor, selection, **facts)

    def scan_pokedex(self, actor, target, selection, **observation):
        import pokedex_device as POKEDEX
        return POKEDEX.scan(self, actor, target, selection, **observation)

    def download_pokedex_app(self, actor, selection, app_id, **observation):
        import pokedex_device as POKEDEX
        return POKEDEX.download(self, actor, selection, app_id, **observation)

    def use_pokedex(self, actor, selection, function, **observation):
        import pokedex_device as POKEDEX
        return POKEDEX.use(self, actor, selection, function, **observation)

    def pokemon_knowledge(self, actor, target, topic, **options):
        import adjudication_guidance as GUIDANCE
        return GUIDANCE.knowledge(self, actor, target, topic, **options)

    def scavenge(self, actor, **options):
        """Resolve a real timed Scavenger activity and its daily reward together."""
        import csv_item_capability_contracts as CAP
        return CAP.scavenge(self, actor, **options)

    @COMMON_ACTIONS.with_declaration
    def common_action(self, c=None, skill=None, dc=None, *, mode=None, outcome=None, description=None, cost=None, failure_margin_accepted=False, **roll_options):
        """Explicit ordinary-action branch. Does not apply world-state effects.
        The GM selects mode, skill, DC and consequences. Team mode takes
        participants, required_people, equal_contribution and no_main_actor.
        Extended mode advances selected actual intervals by task_id/interval_id.
        Owned skill edges are resolved from explicit choices; mods supplies other
        already resolved modifiers. Narrative effects remain GM-owned.
        """
        CHECKS.validate_adjudication(outcome,description,cost,failure_margin_accepted)
        if c is not None and mode is not None:
            import pokemon_understanding as UNDERSTANDING
            UNDERSTANDING.require_activity(self,c,'request')
        if c is not None and (getattr(c,'dead',False) or getattr(c,'fainted',False) or getattr(c,'hp',1)<=0):
            return CHECKS.PendingDecision('unconscious actor requires a sourced action exception')
        if mode is None:return CHECKS.PendingDecision('GM action branch / skill / DC')
        adjudication=dict(outcome=outcome,description=description,cost=cost,failure_margin_accepted=failure_margin_accepted)
        if mode=='no_roll':return CHECKS.adjudicate(**adjudication)
        if mode=='rank':return COMMON_ACTIONS.rank_judgment(self,c,skill,dc,roll_options,adjudication)
        if mode=='focus_task':
            import focus_tasks as FOCUS
            return FOCUS.perform(self,c,skill,dc,roll_options,adjudication)
        if mode=='precise':
            import precise_actions as PRECISE
            return PRECISE.perform(self,c,skill,dc,roll_options,adjudication)
        if mode=='context':
            if c is None:return CHECKS.PendingDecision('GM actual actor')
            import context_actions as CONTEXT
            return CONTEXT.perform(self,c,skill,dc,roll_options,adjudication)
        if mode=='team':
            if c is not None:raise ValueError('ordinary team check has no main actor; use participants')
            return COMMON_ACTIONS.team_action(self,skill,dc,roll_options,adjudication)
        if mode=='extended':
            return COMMON_ACTIONS.extended_action(self,c,skill,dc,roll_options,adjudication)
        if mode!='skill':return CHECKS.PendingDecision('specialized action interface: '+str(mode))
        if c is None or skill is None or dc is None:return CHECKS.PendingDecision('GM actor / skill / DC')
        return COMMON_ACTIONS.ordinary_action(self,c,skill,dc,roll_options,adjudication)

    # ---------- 이니셔티브 ----------
    def campaign_reward(self, actor, activity, **options):
        import campaign_rewards
        return campaign_rewards.perform(self, actor, activity, **options)

    def start_league(self, pairs, *, mode):
        return LEAGUE.start(self, pairs, mode=mode)

    def league_declare(self, actor_id, intent):
        return LEAGUE.declare(self, actor_id, intent)

    def league_step(self, *, pokemon_intent=None):
        return LEAGUE.execute_next(self, pokemon_intent=pokemon_intent)

    def league_complete_round(self):
        return LEAGUE.complete_round(self)

    def next_league_round(self):
        return LEAGUE.next_round(self)

    def end_league(self):
        return LEAGUE.finish(self)

    def league_status(self):
        return LEAGUE.status(self)

    def initiative_value(self, participant, *, procedure=None):
        """Nonconsuming common calculation with actual source/participant detail."""
        import initiative as INITIATIVE
        return INITIATIVE.value(self.r, participant, engine=self, procedure=procedure)

    def prepare_battle_initiative(self, participants, **declaration):
        import party_actions as PARTY_ACTIONS
        return PARTY_ACTIONS.prepare_initiative(self,participants,**declaration)

    def prepare_initiative_schedule(self, participants, **declaration):
        import initiative_schedule as SCHEDULE
        return SCHEDULE.prepare(self,participants,**declaration)

    def initiative_schedule_status(self):
        import initiative_schedule as SCHEDULE
        return SCHEDULE.status(self)

    def queue_initiative_reactions(self, candidates, **declaration):
        import initiative_interrupts as INTERRUPTS
        return INTERRUPTS.queue(self,candidates,**declaration)

    def use_ambush(self, actor, target, move_id, *, ability, weapon_id=None):
        return __import__('priority_actions').use(self,actor,target,move_id,ambush=ability,weapon_id=weapon_id)

    def use_priority_move(self, actor, target, move_id, *, shocking_speed=None):
        import priority_actions as PRIORITY_ACTIONS
        return PRIORITY_ACTIONS.use(self, actor, target, move_id, shocking_speed=shocking_speed)

    def begin_initiative_reaction(self, window_id, request_id):
        import initiative_interrupts as INTERRUPTS
        return INTERRUPTS.begin(self,window_id,request_id)

    def finish_initiative_reaction(self):
        import initiative_interrupts as INTERRUPTS
        return INTERRUPTS.finish(self)

    def decline_initiative_reaction(self, window_id, request_id, **declaration):
        import initiative_interrupts as INTERRUPTS
        return INTERRUPTS.decline(self,window_id,request_id,**declaration)

    def initiative_reaction_status(self):
        import initiative_interrupts as INTERRUPTS
        return INTERRUPTS.status(self)

    def settle_borrowed_turn(self):
        import initiative_interrupts as INTERRUPTS
        return INTERRUPTS.settle(self)

    def skip_switch_locked_turn(self, actor):
        import initiative_schedule as SCHEDULE
        return SCHEDULE.skip_switch_locked(self,actor)

    def declare_scheduled_action(self, actor, intent):
        import initiative_schedule as SCHEDULE
        return SCHEDULE.declare(self,actor,intent)

    def replace_scheduled_participant(self, slot, actor, *, source, reason):
        import initiative_schedule as SCHEDULE
        return SCHEDULE.replace(self,slot,actor,source=source,reason=reason)

    def initiative(self, combatants, *, procedures=None):
        """Ordinary order, or None while a required initiative decision is pending."""
        import initiative as INITIATIVE
        return INITIATIVE.order(self, combatants, procedures=procedures)


def scenario(root, seed, use_hand=True, rulings_path=None, ruleset=None, hook=None):
    """hook(engine, combatant, round) 가 있으면 각 전투원의 턴 직전에 부른다 (GM 콘솔·스크립트)."""
    r = Rules(root, use_hand=use_hand, rulings_path=rulings_path, ruleset=ruleset)
    e = Engine(r, seed)
    silvana = Combatant(r, r.creatures["trainer/silvana"])
    maya = Combatant(r, r.creatures["trainer/maya"])
    archie = Combatant(r, r.creatures["pokemon/archie"])
    oddish = [Combatant(r, r.creatures[f"pokemon/oddish-{i}"]) for i in (1, 2, 3)]
    for o in oddish:
        o.side = "wild"
    for c in [silvana, maya, archie] + oddish:
        e.register_abilities(c)
    e.gm.everyone = [silvana, maya, archie] + oddish
    party = [silvana, archie]
    # 격자: 데모의 호숫가. 덤불(둔화·험한 지형) 속 뚜벅초, 물가·호수 뚜벅초, 중간에 바위(차단 지형) 하나
    e.grid = Grid(14, 10, blocking={(7, 4)}, slow={(9, 7), (10, 7), (9, 8)}, rough={(9, 7), (10, 7), (9, 8)})
    silvana.pos, archie.pos = (2, 5), (3, 5)
    oddish[0].pos, oddish[1].pos, oddish[2].pos = (9, 7), (10, 3), (12, 5)
    maya.pos = (1, 4)
    e.log("# PTK 파일럿 전투 로그: 실바나 + 아치(브케인) vs 야생 뚜벅초 3마리 (챕터 7 전투 데모 재구성, seed %d)" % seed)
    e.log("격자 14×10: 바위(차단) (7,4), 덤불(둔화·험한 지형) (9,7)(10,7)(9,8). 위치: 실바나 (2,5), 아치 (3,5), 뚜벅초 A 덤불 (9,7), B 물가 (10,3), C 호수 (12,5)")
    e.log("")
    e.log("참가자: " + "; ".join(map(repr, party + oddish)))
    e.log("")
    try:
        for rnd in range(1, 9):
            alive_odd = [o for o in oddish if not o.fainted and not o.captured]
            if not alive_odd or all(c.fainted for c in party):
                break
            if rnd == 3:
                party.append(maya)
                e.log("마야가 전투에 합류한다.")
            e.log(f"## 라운드 {rnd}")
            order = e.initiative([c for c in party if not c.fainted] + alive_odd)
            if order is None:
                e.log("전투 보류: 이니셔티브 결정 필요 — 라운드/시간 진행 없음", "combat/initiative")
                break
            e.start_round(order)
            for c in order:
                if hook is not None:
                    hook(e, c, rnd)
                if c.fainted or c.captured or not c.on_field:
                    continue
                limit = e.start_of_turn(c)
                alive_odd = [o for o in oddish if not o.fainted and not o.captured]
                if not alive_odd:
                    break
                if c in oddish:
                    # 야생 포켓몬 AI: 상대 포켓몬을 먼저, 없으면 트레이너를 노린다
                    targets = [t for t in party if not t.fainted and t.kind == "pokemon"] or [t for t in party if not t.fainted]
                    if not targets:
                        break
                    tgt = e.rng.choice(targets)
                    usable = [m for m in c.moves if not (r.move(m)["frequency"].startswith("턴1회") and c.last_move == m)
                              and not (r.move(m)["frequency"].startswith("장면") and c.move_uses.get(m))]
                    mv = e.rng.choice(usable)
                    e.use_move_on(c, tgt, mv, party + oddish)
                elif c is archie:
                    tgt = min(alive_odd, key=lambda o: o.hp)
                    mv = "move/연막" if rnd == 1 else "move/불꽃세례"
                    e.use_move_on(c, tgt, mv, party + oddish)
                elif c is silvana:
                    weak = [o for o in alive_odd if o.hp <= 0.5 * o.base_max_hp]
                    if weak and ITEMS.ball_inventory_key(silvana) is not None:
                        tgt = min(weak, key=lambda o: o.hp)
                        e.approach(silvana, tgt, 4 + 3)       # 사거리 4 + 육상 랭크(초보 3)
                        e.log(f"  실바나가 {tgt.name}에게 몬스터볼을 던진다 (거리 {cheb(silvana.pos, tgt.pos)})")
                        e.throw_ball(silvana, tgt)
                    else:
                        e.use_move_on(c, min(alive_odd, key=lambda o: o.hp), "struggle", party + oddish)
                elif c is maya:
                    mv = "move/제비반환" if c.last_move != "move/제비반환" else "struggle"
                    e.use_move_on(c, min(alive_odd, key=lambda o: o.hp), mv, party + oddish)
                e.end_of_turn(c)
            combat_ended = all(o.fainted or o.captured or not o.on_field for o in oddish) or all(c.fainted or not c.on_field for c in party)
            if combat_ended:
                e.end_encounter(party + oddish)
            else:
                e.end_round()
            e.log("상태: " + "; ".join(map(repr, party + oddish)))
            e.log("위치: " + ", ".join(f"{c.name} {c.pos}" for c in party + oddish if not c.fainted and not c.captured))
            e.log("")
            if combat_ended:
                break
    except PASSIVE_EVENTS.PassiveEventPending as pending:
        PASSIVE_EVENTS.report_driver_pending(e,pending)
        return e
    except HEAVY.HeavyPending as pending:
        HEAVY.report_driver_pending(e,pending)
        return e
    e.log("## 결과")
    e.log("; ".join(map(repr, party + oddish)))
    return e


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    auto_only = "--auto" in sys.argv     # 사람이 채운 moves-hand.json 을 무시하고 자동 기계화만 사용
    ruleset = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--ruleset=")), None)
    eng = scenario(root, seed, use_hand=not auto_only, ruleset=ruleset)
    out = "\n".join(eng.log_lines) + "\n"
    os.makedirs(os.path.join(root, "output"), exist_ok=True)
    open(os.path.join(root, "output/pilot-combat-log" + ("-auto" if auto_only else "") + ".md"), "w", encoding="utf-8").write(out)
    print(out)


