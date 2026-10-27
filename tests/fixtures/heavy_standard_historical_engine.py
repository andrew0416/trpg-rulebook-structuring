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
import heavy_injury_adapter as HEAVY
import action_lifecycle as ACTION
import life as LIFE
import common_checks as CHECKS
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
STATUS_NORM = {"중독": "독", "맹독": "독"}


class Rules:
    def __init__(self, root, use_hand=True, rulings_path=None, ruleset=None, custom_species=None):
        self.root = root
        self.use_hand = use_hand
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
        self._apply_ruleset()
        for rf in self.ruleset.rulings_files:        # 룰셋 프로필이 지정한 재정 파일 (core+errata → 에라타 재정)
            self.rulings.load(os.path.join(root, rf), self)
        if rulings_path:
            self.rulings.load(rulings_path, self)
        if getattr(Rules, "_gm_provider", None) is not None:
            self.rulings.provider = Rules._gm_provider

    def mech(self, uid):
        if hasattr(self, "selection"):
            uid = self.selection.require_supported_version(uid, supports_versions=True)
        u = self.units[uid]
        if not hasattr(self, "selection"):
            self.ruleset.require(source_unit(u))
        assert u.get("mech"), f"{uid} 는 mech 층이 없음"
        return self.rulings.apply_mech(uid, self.ruleset.mech_version(uid, u["mech"]["data"]))

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

    def _selected_rule(self, uid, supports_versions=False):
        if not hasattr(self, "selection"):
            return uid  # Only construction/legacy bare test fixtures lack index.
        if getattr(self, "moves", {}).get(uid, {}).get("source") == "weapon":
            return require_runtime_weapon(self, uid)
        return self.selection.require_supported_version(uid, supports_versions)

    def resolve_move(self, mid):
        if mid in self.unresolved_moves:
            raise UnresolvedRuleSelection(mid, self.unresolved_moves[mid])
        return self._selected_rule(self.move_alias.get(mid, mid))

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
        return self.rulings.formula_expr(name, self)

    def move(self, mid):
        mid = self._selected_rule(mid)
        return self.moves[mid]

    def move_mech(self, mid):
        mid = self._selected_rule(mid)
        mm, conf = self._move_mech(mid)
        if mid in self.rulings.effects:
            return self.rulings.apply_effects(mid, mm), conf + "+gm"
        return mm, conf

    def _move_mech(self, mid):
        """우선순위: 사람이 채운 mech(data/moves-hand.json) > 자동 기계화(data/moves-mech.json, tools/mechanize_moves.py) > 식별 플래그(mech_auto)."""
        mid = self._selected_rule(mid)
        if self.use_hand and mid in self.moves_hand:
            return self.moves_hand[mid]["mech"], "hand"
        if mid in self.moves_reviewed:
            return self.flatten_effects(self.moves_reviewed[mid]["effects"]), "reviewed"
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
        """mechanize_moves.py 의 effects 목록 → 엔진이 쓰는 평면 dict (moves-hand.json 과 같은 모양)."""
        mm = {}
        for e in effects:
            t = e["type"]
            if "on_natural_roll_min" in e:
                o = mm.setdefault("on_natural_roll", {"min": e["on_natural_roll_min"]})
                if t == "apply_status":
                    o["apply_status"] = e["status"]
                if t == "stage_change":
                    o["stage_change"] = {"stat": e["stat"], "delta": e["delta"], "target": e.get("target", "target")}
            elif t == "apply_status" and not e.get("if") and e.get("target", "target") == "target" and not any(k in e for k in ("duration", "while", "limit", "repeat", "trigger", "applies_on_miss", "until")):
                mm["apply_status"] = e["status"]
            elif t == "never_miss" and not any(e.get(k) for k in ("if", "if_weather", "except")):
                mm["never_miss"] = True
            elif t == "push":
                mm["push"] = {"meters": e["meters"]}
            elif t == "drain":
                mm["drain"] = {"fraction": e["fraction"], "of": "damage_dealt"}
            elif t == "evasion_mod":
                mm["evasion_mod"] = {"value": e["value"], "floor": 0}
            elif t == "accuracy_mod":
                mm["zone"] = {"accuracy_penalty": e["value"]}
            elif t == "zone":      # llm 초안의 {"type":"zone","shape":"blast"} → 연막 구역 (명중 -3 이 auto 쪽에 이미 있으면 유지)
                mm.setdefault("zone", {"accuracy_penalty": e.get("accuracy_penalty", e.get("value", -3))})
            elif t in ("heal", "hp_loss", "cure_status", "cure_all_status", "temp_hp", "set_weather", "apply_status_random", "crit_range", "stage_change"):
                mm.setdefault("effects_exec", []).append(e)
            else:
                mm.setdefault("effects_exec", []).append(e)      # 그 밖의 유형은 effects.py 실행기에 맡긴다
        return mm

    def condition_effects(self, cond):
        return self.mech(f"condition/{cond}")["effects"]

    def condition_class(self, cond):
        u = self.units.get(f"condition/{cond}")
        return self.mech(f"condition/{cond}").get("class") if u else None

    def move_id(self, name):
        """기술 이름 → id (별칭·룰셋 치환 반영). 없으면 None."""
        if name in self.moves:
            return self._selected_rule(name)
        mid = "move/" + re.sub(r"[^0-9a-z가-힣]+", "-", str(name).lower()).strip("-")
        if mid in self.moves:
            return self._selected_rule(mid)
        candidates = [m["id"] for m in self.moves.values() if m.get("name") == name]
        if not candidates:
            return None
        if hasattr(self, "selection"):
            return self.selection.resolve_name(name, ("move/",))
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
        key = name if name.startswith(("item/", "augment/")) else "item/" + re.sub(r"[^0-9a-z가-힣]+", "-", str(name).lower()).strip("-")
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
        return effs, header

    def feat_effects(self, name):
        """재주/엣지 이름 또는 id → (effects, header). feat/ → edge/ → poke_edge/ 순으로 찾는다."""
        slug = re.sub(r"[^0-9a-z가-힣]+", "-", str(name).lower()).strip("-")
        keys = [name] if "/" in name else [f"feat/{slug}", f"edge/{slug}", f"poke_edge/{slug}"]
        for key in keys:
            if any(key in getattr(self, attr) for attr in ("feats_mech", "feats_llm", "feats_reviewed", "edges_llm", "edges_reviewed")):
                key = self._selected_rule(key)
            auto = self.feats_mech.get(key)
            llm = self.feats_llm.get(key) if key.startswith(("feat/", "gift/")) else self.edges_llm.get(key)
            reviewed = self.feats_reviewed if key.startswith(("feat/", "gift/")) else self.edges_reviewed
            effs, header, conf = self._pick(auto, llm, reviewed.get(key))
            if effs is not None:
                return effs, dict(header, confidence=conf, id=key)
        return None, {}


class Combatant:
    def __init__(self, rules, spec):
        self.r = rules
        self.spec = spec
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
        self.pos = tuple(spec.get("pos", (0, 0)))
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
        self.movement = spec.get("movement", {}).get("land", 4)
        EXT.init_combatant(self)

    @property
    def base_max_hp(self):
        expr = self.r.formula("max_hp.pokemon" if self.kind == "pokemon" else "max_hp.trainer")
        return int(calc(expr, {"level": self.level, "hp": self.stats["hp"]}))

    @property
    def max_hp(self):
        base = self.base_max_hp
        pen = int(calc(self.r.formula("injury_penalty"), {"max_hp": base, "level": self.level}))
        return base - self.injuries * pen

    def staged(self, stat):
        mult = self.r.mech("combat/combat-stage-multipliers")["multiplier_by_stage"]
        return math.floor(self.stats[stat] * mult[str(self.stages[stat])] + 1e-9)

    def evasion(self, move_class):
        if self.fainted:return 0
        ev = self.r.mech("combat/evasion")
        if any(e["type"] == "evasion_disabled" and not e.get("only") for c in self.conditions for e in self.r.condition_effects(c)):
            return 0
        src = ev["sources"]
        def by(stat):
            return min(ev["cap"], self.staged(stat) // ev["per_points"])
        speed_ok = not any(e["type"] == "evasion_disabled" and e.get("only") == "speed" for c in self.conditions for e in self.r.condition_effects(c))
        cands = [by(src["speed"]) if speed_ok else 0]
        if move_class == "물리":
            cands.append(by(src["physical"]))
        elif move_class == "특수":
            cands.append(by(src["special"]))
        return max(0, max(cands) + self.evasion_mod)

    @property
    def fainted(self):
        return self.dead or "기절" in self.conditions

    def __repr__(self):
        c = ",".join(sorted(self.conditions)) or "-"
        st = ",".join(f"{k}{v:+d}" for k, v in self.stages.items() if v) or "-"
        return f"{self.name}[HP {self.hp}/{self.max_hp} 부상 {self.injuries} 상태 {c} 단계 {st}{' 포획됨' if self.captured else ''}]"


class Engine:
    def __init__(self, rules, seed=1, *, death_enabled=True, friendly_battle=False, session_frequency=False, defer_session_refresh=None):
        self.r = rules
        if type(session_frequency) is not bool or (session_frequency and type(defer_session_refresh) is not bool) or (not session_frequency and defer_session_refresh is not None):
            raise ValueError('session frequency requires an explicit selected policy and explicit defer choice')
        self.session_frequency=session_frequency
        self.defer_session_refresh=defer_session_refresh
        self.session_id=None
        self.pending_session_id=None
        self.session_ids_seen=[]
        self.session_epoch=0
        self.encounter_active=False
        if type(death_enabled) is not bool or type(friendly_battle) is not bool:raise ValueError("life policy must be explicit booleans")
        self.death_enabled=death_enabled
        self.friendly_battle=friendly_battle
        self.rng = random.Random(seed)
        self.seed = seed
        self.log_lines = []
        self.zones = {}          # 연막 등: {combatant_name: accuracy penalty}  (격자 미사용 시)
        self.grid = None         # Grid 를 붙이면 범위 키워드로 대상을 고른다
        self.zone_cells = {}     # {cell: accuracy penalty}  (격자 사용 시 연막 등)
        self.weather = None
        self.field = None
        self.taunt = None
        self.effect_stats = {"done": 0, "held": 0}
        EXT.init_engine(self)
        self.rulings = rules.rulings
        self.gm = GMState(self)
        self._active_turn_actor = None
        self._ordinary_turn_rounds = {}
        self._action_grants = []
        HEAVY.initialize(self)
        self.round_no = 0
        self.elapsed_seconds = 0
        self.round_start_seconds = None
        self.unresolved_time_intervals = []
        self._time_actors = []
        self.weather_rounds = None

    def time_actors(self, combatants=()):
        """Clock membership is independent of the current initiative order."""
        all_actors = [*self._time_actors, *(getattr(self, 'everyone', None) or []),
                      *(getattr(self.gm, 'everyone', None) or []), *combatants]
        self._time_actors = list({id(c): c for c in all_actors}.values())
        for c in self._time_actors:FREQ.bind_session(self,c)
        return list(self._time_actors)

    def begin_session(self, session_id, combatants=()):
        """Explicit narrative frequency boundary, independent of elapsed days.

        The first ID labels the current session without restoring preexisting use.
        Daily Move restoration at this optional boundary is still unresolved.
        """
        HEAVY.ensure_clear(self)
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
        self.log(f'  [세션 빈도 갱신] {session_id}: 일일 재주·특성 사용량 갱신; 일일 기술의 세션 복원은 미해석', 'frequency/session')

    def begin_encounter(self, combatants=()):
        """Explicit encounter scope, also used automatically by start_round."""
        HEAVY.ensure_clear(self)
        self.time_actors(combatants)
        self.encounter_active=True

    def start_round(self, combatants):
        """Starting a successor declares the previous round complete (10 seconds).
        The first start itself advances no time; a partial final round is explicit.
        """
        HEAVY.ensure_clear(self)
        if self._active_turn_actor is not None:
            raise ValueError("cannot advance round while a turn is open")
        combatants = list({id(c): c for c in combatants}.values())
        self.begin_encounter(combatants)
        if self.round_start_seconds is not None:
            self.end_round()
        self.round_no += 1
        self.round_start_seconds = self.elapsed_seconds
        TURN.weather_round_tick(self)
        for c in combatants:
            c.aoo_used = False
            c._round_marker = self.round_no
            FX.fire_event(self, c, {"event": "round_start"})

    def end_round(self):
        """Explicitly complete a shared ten-second round, once."""
        HEAVY.ensure_clear(self)
        if self._active_turn_actor is not None:
            raise ValueError('cannot complete round while a turn is open')
        if self.round_start_seconds is None:
            raise ValueError('no open round to complete')
        self.advance_time(10 - (self.elapsed_seconds - self.round_start_seconds))
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
        """End combat without resetting scene AP or frequency.
        Missing final-round duration remains unknown and cannot prove timer expiry.
        """
        HEAVY.ensure_clear(self)
        actors = self.time_actors() if combatants is None else list({id(c): c for c in combatants}.values())
        self.time_actors(actors)
        if round_elapsed_seconds is not None:
            self.at_round_offset(round_elapsed_seconds)
        elif self.round_start_seconds is not None and self.elapsed_seconds - self.round_start_seconds < 10:
            self.unresolved_time_intervals.append({'round': self.round_no,
                'known_seconds': self.elapsed_seconds - self.round_start_seconds,
                'reason': 'partial_round_elapsed_unresolved'})
            for c in self.time_actors():
                if c.faint_recovery_seconds is not None and not c.faint_recovery_pending:
                    c.faint_recovery_pending = 'partial_round_elapsed_unresolved'
        self.round_start_seconds = None
        for c in actors:
            for condition in sorted(c.conditions):
                if self.r.condition_class(condition) == 'volatile' and condition != '기절':
                    self.cure_status(c, condition)
            changed = any(v for v in c.stages.values()) or c.accuracy_stage != getattr(c, "_passive_acc", 0) or c.evasion_mod != getattr(c, "_passive_eva", 0)
            for k in c.stages:
                c.stages[k] = 0
            for r in getattr(c, "_item_reg", {}).values():          # 지니는 도구가 올린 상시 전투단계(분홍진주 등)는 유지
                for k, d in r.get("stages", {}).items():
                    c.stages[k] += d
            c.accuracy_stage = getattr(c, "_passive_acc", 0)
            c.evasion_mod = getattr(c, "_passive_eva", 0)
            c.pending_action_loss = None
            if changed:
                self.log(f"  [전투 종료] {c.name} 전투단계·명중·회피 초기화", "combat/combat-stages")

        self._active_turn_actor = None
        self._action_grants.clear()
        self.encounter_active=False
        if self.pending_session_id is not None:
            self._apply_session_boundary(self.pending_session_id,self.time_actors())

    def end_scene(self, combatants=None, *, round_elapsed_seconds=None):
        """Narrative scene boundary; an open encounter ends too, but adds no guessed time."""
        HEAVY.ensure_clear(self)
        actors = self.time_actors() if combatants is None else list({id(c): c for c in combatants}.values())
        self.time_actors(actors)
        self.end_encounter(actors, round_elapsed_seconds=round_elapsed_seconds)
        for c in actors:
            c.counters = {k: v for k, v in c.counters.items() if not str(k).startswith(("lim:", "ab:"))}
            FREQ.end_scene(self, c)
        self.rulings.end_scene(self)

    def decide(self, prompt):
        """GM 프롬프트 → 재정 층의 답(스크립트/대화형). 답이 dict 이고 effects 를 담으면 실행한다."""
        ans = self.rulings.decide(prompt)
        if ans is None:
            return None
        self.log(f"    [GM 답] {prompt.get('type')}: {ans if not isinstance(ans, dict) else ans.get('note', '효과 실행')}", "gm/answer")
        if isinstance(ans, dict) and ans.get("effects") and prompt.get("attacker") is not None:
            FX.run_effects(self, prompt["attacker"], prompt.get("target") or prompt["attacker"], ans["effects"], {"attacker": prompt["attacker"], "target": prompt.get("target"), "hit": True, "nat": None, "engine": self}, "gm/answer")
        return ans

    def formula(self, name, **vars):
        return calc(self.r.formula(name), vars)

    def register_abilities(self, c):
        """Combatant.spec['abilities'] 의 특성 effect 를 패시브로 등록. 지니는 도구(spec['item'])와 트레이너 재주/엣지(spec['feats'/'edges'])도 여기서 꽂는다."""
        for name in list(c.abilities):
            self.register_abilities_one(c, name)
        if c.item:
            ITEMS.register_item(self, c)
        if c.kind == "trainer" and (c.spec.get("feats") or c.spec.get("edges")):
            ITEMS.register_feats(self, c)
        c._passive_acc, c._passive_eva = c.accuracy_stage, c.evasion_mod
        FX.fire_event(self, c, {"event": "enter"})

    def register_abilities_one(self, c, name):
        if name in self.r.unresolved_abilities:
            raise UnresolvedRuleSelection(name, self.r.unresolved_abilities[name])
        if name in self.r.excluded_abilities:
            self.log(f"  {c.name} 특성 {name}: 룰셋 '{self.r.ruleset.name}' 에서 제외({self.r.excluded_abilities[name]}) → 무시", "ruleset/exclude")
            return
        if name in self.r.ability_alias:
            self.log(f"  [룰셋 {self.r.ruleset.name}] {c.name} 특성 {name} → {self.r.ability_alias[name]} (변형판 대체)", "ruleset/alias")
            name = self.r.ability_alias[name]
        selected_id = None
        if hasattr(self.r, "selection"):
            selected_id = self.r.selection.resolve_name(name, ("ability/",))
            self.r.selection.require_supported_version(selected_id)
        effs = [dict(e, _ability=name, _frequency=self.r.ability_freq.get(name)) if isinstance(e, dict) else e for e in self.r.ability_effects.get(name, [])]
        if selected_id is not None:
            effs = bind_rule_identity(effs, selected_id)
        FX.apply_passives(self, c, effs)
        EXT.register_ability_extras(self, c, effs)
        if effs:
            self.log(f"  {c.name} 특성 {name}: 패시브 {sum(1 for e in effs if e.get('type') in FX.PASSIVE_TYPES)}개 등록", f"ability/{name}")

    def use_item(self, user, item, target=None, free=False, accepted=True):
        """소모 아이템(약·음식·열매·영양제) 사용 → engine/items.py. 반환 (실행, 보류) 또는 None."""
        return ITEMS.use_item(self, user, item, target, free, accepted=accepted)

    def manual_feat(self, c, name, target=None):
        return ITEMS.manual_feat(self, c, name, target)

    def log(self, msg, rule=None):
        self.log_lines.append(msg + (f"  => [{rule}]" if rule else ""))

    # ---------- 주사위 ----------
    def roll_expr(self, expr, times=1):
        """'2d6+8' → (합계, 눈 목록). times=2 면 주사위만 두 번(치명타), 고정 보너스는 한 번만."""
        m = re.match(r"(\d+)d(\d+)(?:\+(\d+))?", expr)
        n, d, bonus = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
        rolls = [self.rng.randint(1, d) for _ in range(n * times)]
        return sum(rolls) + bonus * times, rolls

    def d20(self):
        return self.rng.randint(1, 20)

    # ---------- 전투단계 / 상태 ----------
    def change_stage(self, c, stat, delta):
        if EXT.stage_hook(self, c, delta):
            return
        lo, hi = self.r.mech("combat/combat-stages")["range"]
        before = c.stages[stat]
        c.stages[stat] = max(lo, min(hi, before + delta))
        self.log(f"    {c.name} {stat} 전투단계 {before:+d} → {c.stages[stat]:+d}", "combat/combat-stages")

    def immune_to(self, c, cond):
        if cond in getattr(c, "status_immune", ()):
            return "item/status_immunity"
        by_type = self.r.mech("combat/type-immunities")["by_type"]
        if any(cond in by_type.get(t, []) for t in c.types):
            return "combat/type-immunities"
        for e in self.r.condition_effects(cond):
            if e["type"] == "immunity" and any(t in e["types"] for t in c.types):
                return f"condition/{cond}"
        return None

    def apply_status(self, c, cond):
        cond = STATUS_NORM.get(cond, cond)
        if cond=="기절":return LIFE.faint(self,c)
        why = self.immune_to(c, cond)
        if why:
            self.log(f"    {c.name}은(는) {cond}에 면역", why)
            return False
        if cond in c.conditions:
            self.log(f"    {c.name}은(는) 이미 {cond} 상태")
            return False
        c.conditions.add(cond)
        self.log(f"    {c.name}은(는) {cond} 상태가 됨", f"condition/{cond}")
        if getattr(self, "_inflictor", None) is not None and self._inflictor is not c:
            FX.fire_event(self, self._inflictor, {"event": "on_inflict_status", "status": cond}, c)
        for e in self.r.condition_effects(cond):
            if e["type"] == "combat_stage" and e.get("while") == "afflicted":
                self.change_stage(c, e["stat"], e["delta"])
            if e["type"] == "apply_condition":
                c.conditions.add(e["condition"])
                self.log(f"    파생: {c.name} {e['condition']} ({e['rounds']}라운드)", f"condition/{cond}")
        return True

    def cure_status(self, c, cond):
        if cond in ("기절","사망","임시 체력"):
            self.log(f"    {cond}: 일반 상태치료 대상이 아님", "condition/special")
            return False
        if cond in c.conditions:
            c.conditions.discard(cond)
            for e in self.r.condition_effects(cond):
                if e["type"] == "combat_stage" and e.get("while") == "afflicted":
                    self.change_stage(c, e["stat"], -e["delta"])
            self.log(f"    {c.name}의 {cond} 치료됨", f"condition/{cond}")

    def tick(self, c):
        """소량의 체력 = 실제 최대 체력(부상 패널티 전)의 1/10 — '포켓몬의 최대 체력을 벗어난 모든 효과는 실제 최대값을 사용'(ch07 부상 데미지)."""
        return int(self.formula("tick", max_hp=c.base_max_hp, level=c.level))

    def start_of_turn(self, c):
        """마비 등: 턴 시작 내성 체크."""
        HEAVY.ensure_clear(self)
        ACTION.begin_turn(self, c)
        FREQ.start_turn(c)
        TURN.reset_budget(self, c)
        FX.fire_event(self, c, {"event": "turn_start"})
        EXT.start_of_turn(self, c)
        TURN.weather_turn_start(self, c)
        limit = None
        for cond in sorted(c.conditions):
            for e in self.r.condition_effects(cond):
                if e["type"] == "save" and e["timing"] == "start_of_turn":
                    roll = self.d20()
                    dc = EXT.save_dc(self, c, cond, e["dc"]) + self.rulings.consume("dc", c.name, self) - TURN.weather_save_mod(self, cond); ok = roll >= dc
                    self.log(f"    {c.name} {cond} 내성 체크 d20={roll} vs DC {dc} → {'성공' if ok else '실패'}", f"condition/{cond}")
                    if ok and e.get("on_success") == "cure":
                        self.cure_status(c, cond)
                    elif not ok:
                        limit = next((x for x in self.r.condition_effects(cond) if x["type"] == "action_limit"), None)
        c._turn_action_limit = limit
        c._turn_start_decisions_pending = False
        return limit

    def end_of_turn(self, c):
        HEAVY.ensure_clear(self)
        ACTION.check_end(self, c)
        unable_at_turn_end = ACTION.unable_standard(c)
        asleep_at_turn_end = "잠듦" in c.conditions
        for cond in sorted(c.conditions):
            if cond not in c.conditions:continue
            for e in self.r.condition_effects(cond):
                if cond not in c.conditions:break
                if e["type"] == "tick_damage" and e.get("when") == "end_of_turn":
                    need_std = e.get("if", "").startswith("took_standard_action")
                    unable_branch = e.get("if") == "took_standard_action_or_unable_to" and unable_at_turn_end
                    if need_std and not (c.took_standard or unable_branch):
                        continue
                    amount = self.tick(c) * e["ticks"]
                    self.log(f"    {c.name} {cond}: 소량의 체력 ×{e['ticks']} = {amount} 손실", f"condition/{cond}")
                    self.lose_hp(c, amount, source=cond)
                if e["type"] == "save" and e["timing"] == "end_of_turn":
                    if asleep_at_turn_end and cond in ("난동", "헤롱헤롱", "혼란"):
                        self.log(f"    {c.name}: 잠듦 중 {cond} 치료 내성은 허용되지 않음; 같은 종료시점의 깨어남 이후 순서는 미확정", "condition/잠듦")
                        continue
                    roll = self.d20()
                    dc = EXT.save_dc(self, c, cond, e["dc"]) + self.rulings.consume("dc", c.name, self) - TURN.weather_save_mod(self, cond); ok = roll >= dc
                    self.log(f"    {c.name} {cond} 내성 체크 d20={roll} vs DC {dc} → {'성공' if ok else '실패'}", f"condition/{cond}")
                    if ok and e.get("on_success") == "cure":
                        self.cure_status(c, cond)
        EXT.end_of_turn(self, c)
        FX.fire_event(self, c, {"event": "turn_end"})
        c.took_standard = False
        ACTION.close_turn(self, c)

    # ---------- 명중 ----------
    def accuracy_check(self, attacker, target, move, situational=0, waive=False, fixed_roll=None, shared_roll=None):
        ac_rule = self.r.mech("combat/accuracy-roll")
        nat = fixed_roll if fixed_roll is not None else self.d20()
        zone_pen = self.zones.get(attacker.name, 0)
        if self.grid is not None:
            zone_pen = min(self.zone_cells.get(attacker.pos, 0), self.zone_cells.get(target.pos, 0))   # 연막 안에서/향해 공격 -3
            if target.pos in self.grid.rough:
                zone_pen -= 2                                                                            # 험한 지형의 대상 -2
        if shared_roll is not None:
            if "actor_mod" not in shared_roll:
                shared_roll["actor_mod"] = attacker.accuracy_stage + self.rulings.consume("accuracy", attacker.name, self)
            actor_mod = shared_roll["actor_mod"]
        else:
            actor_mod = attacker.accuracy_stage + self.rulings.consume("accuracy", attacker.name, self)
        mods = actor_mod + situational + zone_pen
        total = nat + mods
        evasion = 0 if waive else max(0, target.evasion(move["class"]) + self.rulings.consume("evasion", target.name, self))
        ac = (move.get("ac") or 0)
        need = ac + evasion
        mm, conf = self.r.move_mech(move["id"])
        ac_ov, waive_ev, acc_bonus, never_cond = EXT.accuracy_hook(self, attacker, target, move, mm, {"attacker": attacker, "target": target, "hit": True, "nat": nat, "engine": self, "move": move})
        if waive_ev:
            evasion = 0
        if ac_ov is not None:
            ac = ac_ov
        mods += acc_bonus
        total = nat + mods
        need = ac + evasion
        if target.shield is not None and move["class"] in ("물리", "특수") and not target.abilities_suppressed:
            self.log(f"  {attacker.name} {move['name']}: {target.name}의 방패({target.shield.get('trigger', '')[:20]}) → 명중 무효", f"effect/reaction_shield")
            target.shield = None
            return False, nat, False
        if mm.get("never_miss") or never_cond:
            hit = True
            why = f"{move['id']} (never_miss, {conf})"
        elif nat == ac_rule["auto_miss_natural"]:
            hit, why = False, "combat/accuracy-roll (자연 1)"
        elif nat == ac_rule["auto_hit_natural"]:
            hit, why = True, "combat/accuracy-roll (자연 20)"
        else:
            hit, why = total >= need, "combat/accuracy-roll"
        crit_min = int(self.formula("crit_range"))
        for e in mm.get("effects_exec", []):
            if e["type"] == "crit_range" and isinstance(e.get("min"), int):
                crit_min = min(crit_min, e["min"])
        for e in attacker.modifiers:
            if e.get("type") == "crit_range" and isinstance(e.get("min"), int):
                crit_min = min(crit_min, e["min"])
        crit_min -= ITEMS.crit_delta(attacker, move)
        crit = move["class"] in ("물리", "특수") and (nat >= crit_min or any(e["type"] == "crit_range" and e.get("on_natural_roll") == "even" and nat % 2 == 0 for e in mm.get("effects_exec", [])))
        crit = EXT.crit_hook(self, attacker, target, move, hit, crit)
        if attacker.next_attack and attacker.next_attack.get("auto_crit") and move["class"] in ("물리", "특수") and hit:
            crit = True
            attacker.next_attack = None
            self.log("    다음 공격 자동 치명타 발동", "effect/next_attack_modifier")
        self.log(f"  {attacker.name} {move['name']}: 명중 d20={nat}{mods:+d}={total} vs AC {ac}+회피 {evasion}={need} → {'명중' if hit else '빗나감'}{' 치명타!' if hit and crit else ''}", why)
        return hit, nat, crit

    # ---------- 데미지 ----------
    def type_multiplier(self, move_type, target):
        te = self.r.mech("combat/type-effectiveness")
        if not target.types:
            return 1.0, "combat/type-effectiveness (타입 없음)"
        chart = self.r.mech("combat/type-chart")["attack_vs_defense"]
        steps = 0
        for t in target.types:
            v = chart[move_type][t]
            if v == 0:
                return 0.0, "combat/type-chart"
            steps += 1 if v > 1 else (-1 if v < 1 else 0)
        return te["multiplier_by_net_steps"][str(max(-3, min(3, steps)))], "combat/type-effectiveness"

    def damage_base(self, attacker, move):
        db = move["damage_base"]
        if isinstance(db, str):
            raise ValueError(f"{move['name']}: DB 가변(본문 참조) — 기계화 안 됨")
        for effect in self.r.move_mech(move["id"])[0].get("effects_exec", []):
            if effect.get("type") == "conditional_damage_base" and FX.cond_ok(self, effect, {"attacker": attacker, "hit": True})[0]:
                db = effect["damage_base"]
        stab = self.r.mech("combat/stab")
        if (move["type"] in attacker.types or EXT.grants_stab(self, attacker, move)) and move["class"] in ("물리", "특수") and move["id"] != "struggle":
            bonus = int(self.formula("stab"))
            self.log(f"    자속보정: DB {db} → {db + bonus}", "combat/stab")
            db += bonus
        db += EXT.db_hook(self, attacker, move, self.r.move_mech(move["id"])[0])
        return max(1, min(28, db))

    def roll_damage(self, attacker, target, move, crit=False, set_damage=False, fixed_dice=None, _reaction_event=None):
        df = self.r.mech("combat/damage-formula")
        db = self.damage_base(attacker, move)
        entry = self.r.mech("combat/damage-chart")["by_damage_base"][str(db)]
        times = 2 if crit else 1
        if set_damage:
            dice_part = entry["set"]["mid"] * times
            self.log(f"    DB {db} 지정 데미지 {entry['set']['mid']}{' ×2(치명타)' if crit else ''} = {dice_part}", "combat/damage-chart")
        elif fixed_dice is not None:
            m = re.match(r"(\d+)d(\d+)(?:\+(\d+))?", entry["dice"])
            dice_part = sum(fixed_dice) + int(m.group(3) or 0) * times
            self.log(f"    DB {db} → {entry['dice']} 눈 {fixed_dice} = {dice_part}", "combat/damage-chart")
        else:
            dice_part, rolls = self.roll_expr(entry["dice"], times)
            self.log(f"    DB {db} → {entry['dice']}{' ×2(치명타)' if crit else ''} 눈 {rolls} = {dice_part}", "combat/critical-hit" if crit else "combat/damage-chart")
        atk_stat = df["attack_stat_by_class"][move["class"]]
        def_stat = df["defense_stat_by_class"][move["class"]]
        mm, conf = self.r.move_mech(move["id"])
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
        mtype = EXT.effective_type(self, attacker, target, move, mm)
        mult, why = self.type_multiplier(mtype, target)
        ctx = {"attacker": attacker, "target": target, "multiplier": mult, "crit": crit, "hit": True, "move": move, "engine": self}
        mult = EXT.effectiveness_hook(self, attacker, target, move, mm, mult, ctx)
        ctx["multiplier"] = mult
        db_mod, roll_mod, resist_steps, immune, absorb = FX.passive_damage_mods(self, attacker, target, move, ctx)
        for e in mm.get("effects_exec", []):
            if e.get("type") == "bonus_damage" and isinstance(e.get("value"), int):
                ok, _ = FX.cond_ok(self, e, ctx)
                if ok:
                    roll_mod += e["value"]
                    self.log(f"    추가 데미지 +{e['value']} ({e.get('if', '')})", f"{move['id']} ({conf})")
        if immune is not None and not target.abilities_suppressed:
            self.log(f"    {target.name} 특성으로 {move['type']} 무효", "effect/immunity")
            return 0
        if absorb is not None and not target.abilities_suppressed:
            self.log(f"    {target.name} 특성으로 {move['type']} 흡수: {absorb.get('then')}", "effect/absorb")
            then = absorb.get("then", {})
            if then.get("heal") == "tick":
                self.heal(target, self.tick(target))
            if isinstance(then.get("stage_change"), str):
                m2 = re.match(r"([+\-]\d+)\s*(atk|def|spa|spd|spe)", then["stage_change"])
                if m2:
                    self.change_stage(target, m2.group(2), int(m2.group(1)))
            return 0
        wmod = TURN.weather_damage_mod(self, attacker, move)
        if wmod:
            roll_mod += wmod
            self.log(f"    날씨({TURN.WEATHER_KO.get(self.weather, self.weather)}): {move['type']} 피해 굴림 {wmod:+d}", "combat/weather")
        if attacker.next_attack and isinstance(attacker.next_attack.get("damage"), int) and attacker.next_attack.get("damage"):
            roll_mod += attacker.next_attack["damage"]
            self.log(f"    다음 굴림 보너스 피해 +{attacker.next_attack['damage']}", "effect/next_roll_bonus")
            attacker.next_attack = None
        if roll_mod:
            self.log(f"    패시브/조건 굴림 보정 {roll_mod:+d}", "effect/damage_roll_mod")
        total = dice_part + atk_src.staged(atk_stat) + roll_mod
        def_val, dr_val = EXT.defense_hook(self, attacker, target, move, mm, def_stat)
        idr = ITEMS.item_damage_reduction(target, move)
        if idr and dr_val is not None:
            dr_val += idr
            self.log(f"    도구 피해 감소 {idr} ({move['type']}/{move['class']} 한정)", "item/damage_reduction")
        after_def = max(0, total - def_val - dr_val)
        if resist_steps and not target.abilities_suppressed:
            te = self.r.mech("combat/type-effectiveness")["multiplier_by_net_steps"]
            steps = {1.0: 0, 1.5: 1, 2.0: 2, 3.0: 3, 0.5: -1, 0.25: -2, 0.125: -3}.get(mult, 0) - resist_steps
            mult = te[str(max(-3, min(3, steps)))] if mult else 0
            self.log(f"    특성 저항 {resist_steps}단계 → 타입 ×{mult}", "effect/resistance_step")
        other_multiplier = EXT.multiplier_hook(self, attacker, move, mm, ctx)
        adjustment = self.rulings.consume("damage", attacker.name, self)
        final = max(0, math.floor(after_def * mult * other_multiplier + 1e-9) + adjustment)
        floor_effect = any(e.get("type") == "damage_floor" for e in mm.get("effects_exec", []))
        if _reaction_event is not None:
            resisted_mult = REACTIONS.resistance_multiplier(self, mult)
            resisted = None if resisted_mult is None else max(0, math.floor(after_def * resisted_mult * other_multiplier + 1e-9) + adjustment)
            _reaction_event.update(damage=final, resisted_damage=resisted, attack_stat=atk_stat, context=ctx, damage_floor=floor_effect)
        else:
            final = self.rulings.run_hooks("before_damage", final, dict(ctx, final=final), self)
            if floor_effect:
                final = min(final, max(0, target.hp - 1))
        self.log(f"    + {atk_stat} {attacker.staged(atk_stat)} = {total}, - {target.name} {def_stat} {target.staged(def_stat)}{(' - DR ' + str(target.damage_reduction)) if target.damage_reduction else ''} = {after_def}, 타입 ×{mult} = {final}", why)
        return final

    def resolve_attack_damage(self, attacker, target, move, crit=False, set_damage=False, intercepted=False, _heavy_context=None):
        """Apply one hit and its responses. intercepted means a successful maneuver already resolved by the caller."""
        HEAVY.ensure_clear(self)
        HEAVY.validate_native_receipt(self,_heavy_context,attacker,target,move)
        event = dict(attacker=attacker, target=target, move=move, intercepted=intercepted is True)
        damage = self.roll_damage(attacker, target, move, crit, set_damage, _reaction_event=event)
        if "damage" in event:
            damage = REACTIONS.select_mettle(self, event)
            damage = self.rulings.run_hooks("before_damage", damage, dict(event["context"], final=damage), self)
            if event.get("damage_floor"):
                damage = min(damage, max(0, target.hp - 1))
        HEAVY.apply_attack_damage(self, attacker, target, damage, move,
            producer=HEAVY.Producer.RESOLVED_HIT,
            remainder="finish_mettle and remaining use_move effects/reactions have not run",
            native_context=_heavy_context)
        event["damage_applied"] = True
        REACTIONS.finish_mettle(self, event)
        return damage

    def lose_hp(self, c, amount, source="damage", *, unpreventable=False):
        """HP loss keeps marker injuries; explicit unpreventable loss bypasses caps."""
        if type(unpreventable) is not bool:
            raise ValueError("unpreventable must be an explicit boolean")
        if not unpreventable:
            amount = EXT.cap_damage(self, c, amount)
        before, maxhp = c.hp, c.base_max_hp          # 표시점은 실제 최대 체력 기준
        c.hp -= amount
        inj = self.marker_injuries(c, before, c.hp, maxhp)
        self.log(f"    {c.name} 체력 {before} → {c.hp} ({source})" + (f", 표시점 부상 +{inj}" if inj else ""), "combat/hit-point-loss")
        self.check_fainted(c)

    def take_damage(self, c, amount):
        """한 번의 타격. 부상 판정은 타격 직전의 최대 체력을 기준으로 한다(같은 타격 안에서 부상이 최대 체력을 깎아 표시점을 옮기지 않도록)."""
        inj = self.r.mech("combat/injuries")
        amount = EXT.cap_damage(self, c, amount)
        if c.temp_hp:
            used = min(c.temp_hp, amount)
            c.temp_hp -= used
            amount -= used
            self.log(f"    임시 체력이 {used} 흡수 (남은 임시 {c.temp_hp})", "condition/임시-체력")
        before, maxhp = c.hp, c.base_max_hp          # 대규모 데미지·표시점은 실제 최대 체력 기준 (부상 패널티는 회복 상한에만)
        c.hp -= amount
        n_inj = 0
        if amount >= float(self.formula("massive_damage")) * maxhp:
            n_inj += 1
            c.injuries += 1
            self.log(f"    대규모 데미지({amount} ≥ 최대 체력 {maxhp}의 50%) → 부상 +1", "combat/injuries")
        n_inj += self.marker_injuries(c, before, c.hp, maxhp)
        self.log(f"    {c.name} 체력 {before} → {c.hp}" + (f", 부상 {c.injuries}개 → 최대 체력 {c.max_hp}" if n_inj else ""), "combat/damage-formula")
        self.check_fainted(c)
        EXT.after_damage(self, c)
        return n_inj

    def marker_injuries(self, c, before, after, maxhp):
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
            c.injuries += n
            self.log(f"    체력 표시점 통과 {n}개 → 부상 +{n} (총 {c.injuries})", "combat/injuries")
        return n

    def check_fainted(self, c):
        self.time_actors([c])
        LIFE.sync(self,c)

    def heal(self, c, amount, *, source_kind='unspecified', round_offset_seconds=None):
        self.time_actors([c])
        if round_offset_seconds is not None:
            CHECKS.integer(amount, 'healing HP', 0)
            if source_kind not in ('ordinary_item','move','feature','explicit_revive','rest','unspecified'):
                raise ValueError('unknown healing source kind')
            self.at_round_offset(round_offset_seconds)
        gained = LIFE.heal(self,c,amount,source_kind)
        if (self.round_start_seconds is not None and round_offset_seconds is None
                and source_kind == 'ordinary_item' and gained > 0
                and c.faint_recovery_seconds is not None and not c.faint_recovery_pending):
            c.faint_recovery_pending = 'within_round_healing_timestamp_unresolved'
            c.faint_recovery_birth_round = self.round_no
        return gained

    def revive(self, c, hp):
        return LIFE.revive(self,c,hp)

    def advance_time(self, seconds, combatants=()):
        """One shared interval for all registered actors, including off-field/fainted actors.
        Separate calls are sequential. Unknown earlier intervals remain recorded separately.
        """
        HEAVY.ensure_clear(self)
        CHECKS.integer(seconds,'elapsed seconds',0)
        if self.round_start_seconds is not None and self.elapsed_seconds + seconds > self.round_start_seconds + 10:
            raise ValueError('elapsed interval exceeds the open round')
        actors = self.time_actors(combatants)
        for c in actors:
            LIFE.advance(self,c,seconds)
        self.elapsed_seconds += seconds

    # ---------- 기술 사용 ----------
    def use_move_on(self, attacker, primary, move_id, everyone):
        """격자 사용 시: 범위 키워드로 대상 집합을 구해 각각 처리. 근접/사거리 밖이면 먼저 접근."""
        HEAVY.ensure_clear(self)
        move_id = self._ruleset_move(attacker, move_id)
        if move_id is None:
            return 0
        allowed, reason = FREQ.move_allowed(self, attacker, move_id)
        if not allowed:
            self.log(f"  {attacker.name}: {reason}", "frequency/move")
            return 0
        move = self.r.move(move_id)
        self.everyone = everyone
        rng = self.r.moves_mech.get(move_id, {}).get("header", {}).get("range") or {}
        reach = 1 if rng.get("origin") == "melee" else (rng.get("origin") if isinstance(rng.get("origin"), int) else 1)
        if self.grid is not None and not rng.get("shape") and cheb(attacker.pos, primary.pos) > reach:
            self.approach(attacker, primary, reach)
        targets = self.targets_in_range(attacker, move, everyone, primary)
        if not targets and self.grid is not None and rng.get("shape"):
            self.approach(attacker, primary, rng.get("size", 1))
            targets = self.targets_in_range(attacker, move, everyone, primary)
        if not targets:
            self.log(f"  {attacker.name} {move['name']}: 사거리 밖/가로막힘 → 행동 없음", "ch10/범위-키워드")
            return 0
        total = 0
        activation = {}
        shared_accuracy = {} if rng.get("shape") else None
        for i, t in enumerate(targets):
            if i == 0:
                total += self.use_move(attacker, t, move_id, _activation=activation, _shared_accuracy=shared_accuracy)
            else:
                with ACTION.move_grant(self, attacker, t, move_id, source="same_move_activation") as grant:
                    total += self.use_move(attacker, t, move_id, count_use=False, _shared_accuracy=shared_accuracy, _action_grant=grant)
            # A miss is an activated move; refusal or a preparation turn is not.
            if i == 0 and not activation.get("started"):
                return total
        chain = next((e for e in self.r.move_mech(move_id)[0].get("effects_exec", []) if e.get("type") == "multi_target_chain"), None)
        if chain and self.grid is not None:
            used = set(id(t) for t in targets)
            for _ in range(int(chain.get("max", 3)) - 1):
                others = [c for c in everyone if c is not attacker and not c.fainted and not c.captured and id(c) not in used and cheb(attacker.pos, c.pos) <= 1 + int(chain.get("shift_between", 2))]
                if not others:
                    break
                nxt = others[0]
                self.approach(attacker, nxt, 1)
                self.log(f"    연쇄 공격 → {nxt.name}", f"{move_id} multi_target_chain")
                used.add(id(nxt))
                with ACTION.move_grant(self, attacker, nxt, move_id, source="same_move_activation") as grant:
                    total += self.use_move(attacker, nxt, move_id, count_use=False, _action_grant=grant)
        return total

    def _ruleset_move(self, attacker, move_id):
        """룰셋 필터: 제외된 기술은 거부(None), 코어판→변형판 치환은 로그."""
        if move_id in self.r.unresolved_moves:
            raise UnresolvedRuleSelection(move_id, self.r.unresolved_moves[move_id])
        if move_id in self.r.excluded_moves:
            self.log(f"  {attacker.name} {self.r.moves[move_id]['name']}: 룰셋 '{self.r.ruleset.name}' 에서 제외된 기술({self.r.excluded_moves[move_id]}) → 사용 불가", "ruleset/exclude")
            return None
        new = self.r.resolve_move(move_id)
        if new != move_id:
            self.log(f"  [룰셋 {self.r.ruleset.name}] {self.r.moves[move_id]['name']} → {self.r.moves[new]['name']} (변형판 대체)", "ruleset/alias")
        return new

    def use_move(self, attacker, target, move_id, situational=0, set_damage=False, count_use=True, free_action=False, _activation=None, _shared_accuracy=None, _action_grant=None):
        HEAVY.ensure_clear(self)
        move_id = self._ruleset_move(attacker, move_id)
        if move_id is None:
            return 0
        if not TURN.can_act(self, attacker):
            return 0
        move = self.r.move(move_id)
        mm, conf = self.r.move_mech(move_id)
        kind = "free" if free_action else TURN.action_kind_of_move(self, attacker, move, mm)
        grant_ok, grant_kind = ACTION.consume_move_grant(self, _action_grant, attacker, target, move_id)
        if self.encounter_active:
            if (free_action or not count_use) and not grant_ok:
                self.log("    [보류] 비용/빈도 생략에는 출처가 확인된 실행 권한 필요", "common/action-lifecycle")
                return 0
            if not grant_ok and not ACTION.ordinary_permission(self, attacker):
                return 0
        sleep_cure = ACTION.self_cures_sleep(attacker, target, mm.get("effects_exec", []))
        if not ACTION.status_permission(self, attacker, kind, sleep_cure=sleep_cure, new_action=not (grant_ok and grant_kind is None)):
            return 0
        if count_use:
            allowed, reason = FREQ.move_allowed(self, attacker, move_id)
            if not allowed:
                self.log(f"  {attacker.name} {move['name']}: {reason}", "frequency/move")
                return 0
        if not free_action and count_use:
            if not TURN.spend(self, attacker, kind, move["name"], sleep_cure=sleep_cure):
                return 0
            if kind != "standard":
                self.log(f"    {move['name']}은(는) {'완전' if kind == 'full' else '신속' if kind == 'swift' else '자유' if kind == 'free' else '이동'} 행동", "combat/action-economy")
            rng = (self.r.moves_mech.get(move_id, {}).get("header", {}) or {}).get("range") or {}
            if self.grid is not None and isinstance(rng.get("origin"), int) and rng.get("origin", 0) > 1 and target.pos != attacker.pos and cheb(attacker.pos, target.pos) > 1:
                TURN.trigger_aoo(self, attacker, "인접하지 않은 대상에게 원거리 공격")
                if attacker.fainted:
                    return 0
        if free_action and (not self.encounter_active or grant_ok):
            ACTION.record_action(self, attacker, grant_kind or "free")
        if not EXT.pre_use(self, attacker, target, move, mm):
            return 0
        setup = next((e for e in mm.get("effects_exec", []) if e.get("type") == "set_up_move"), None)
        skip_setup = setup is not None and setup.get("skip_setup_if_weather") and FX.weather_matches(self, setup["skip_setup_if_weather"])
        if setup is not None and attacker.setup_move != move_id and not skip_setup:
            attacker.setup_move = move_id
            self.log(f"  {attacker.name} {move['name']}: 준비 턴 ({str(setup.get('setup', ''))[:50]})", f"{move_id} ({conf}) set_up_move")
            st = setup.get("setup")
            if isinstance(st, list):
                FX.run_effects(self, attacker, target, st, {"attacker": attacker, "target": target, "hit": True, "nat": None, "engine": self}, f"{move_id} 준비")
            return 0
        if setup is not None:
            attacker.setup_move = None
            self.log(f"  {attacker.name} {move['name']}: 발동 턴", f"{move_id} ({conf}) set_up_move")
        if _activation is not None:
            _activation["started"] = True
        FX.fire_event(self, attacker, {"event": "on_move_use", "move": move}, target)
        self._inflictor = attacker
        if count_use:
            attacker.last_move = move_id
            attacker.last_target = target
            FREQ.consume_move(self, attacker, move_id)
        def check_accuracy(index=0):
            if _shared_accuracy is None:
                return self.accuracy_check(attacker, target, move, situational)
            rolls = _shared_accuracy.setdefault("rolls", [])
            while len(rolls) <= index:
                rolls.append(self.d20())
            return self.accuracy_check(attacker, target, move, situational,
                                       fixed_roll=rolls[index], shared_roll=_shared_accuracy)

        if move["class"] == "변화" and not move.get("ac") and "자신" in move.get("range", ""):
            hit, nat, crit = True, None, False
            self.log(f"  {attacker.name} {move['name']} (자신 대상, 명중 굴림 없음)")
        elif (mr := EXT.multi_roll_spec(mm)) is not None:
            res = [check_accuracy(i) for i in range(int(mr.get("rolls", 3)))]
            hit = any(h for h, _, _ in res)
            nat = max(n for _, n, _ in res)
            crit = any(c_ for _, _, c_ in res) if mr.get("crit_if_any_crit") else all(c_ for _, _, c_ in res)
            attacker.counters["multi_hits"] = sum(1 for h, _, _ in res if h)
            self.log(f"    다중 굴림 {len(res)}회: 명중 {attacker.counters['multi_hits']}회 → {'명중' if hit else '빗나감'}{' (치명타)' if hit and crit else ''}", "effect/multi_roll")
        else:
            hit, nat, crit = check_accuracy()
        if not hit:
            ctx = {"attacker": attacker, "target": target, "nat": nat, "hit": False, "dealt": 0, "crit": False, "move": move, "engine": self}
            FX.run_effects(self, attacker, target, [e for e in mm.get("effects_exec", []) if e.get("on_miss")], ctx, f"{move_id} ({conf})")
            return 0
        dealt = 0
        if move["class"] in ("물리", "특수"):
            diagnostic = HEAVY.certify_native_context(self,attacker,target,move,mm,
                ordinary_single=(count_use and not free_action and _activation is None
                                 and _shared_accuracy is None and _action_grant is None))
            # Issuance is inside the already-authorized/use-counted producer.
            # Public diagnostic results are not tokens and cannot be replayed.
            heavy_context = object()
            self._heavy_activation_sequence += 1
            self._heavy_native_receipts[heavy_context] = dict(diagnostic=diagnostic,
                attacker=attacker,target=target,move_id=move_id,round=self.round_no,
                active_actor=self._active_turn_actor,move_uses=attacker.move_uses.get(move_id,0),
                history_length=len(getattr(attacker,"_action_history",[])),
                activation_epoch=self._heavy_activation_sequence)
            try:
                dealt = self.resolve_attack_damage(attacker, target, move, crit, set_damage,
                                                   _heavy_context=heavy_context)
            finally:
                self._heavy_native_receipts.pop(heavy_context,None)
        # 효과 (hand mech 우선, 없으면 auto)
        if "apply_status" in mm:
            self.apply_status(target, mm["apply_status"])
        if "on_natural_roll" in mm and nat is not None and nat >= mm["on_natural_roll"]["min"]:
            o = mm["on_natural_roll"]
            self.log(f"    자연 {nat} ≥ {o['min']}: 추가 효과 발동", f"{move_id} ({conf})")
            if "apply_status" in o:
                self.apply_status(target, o["apply_status"])
            if "stage_change" in o:
                tgt = attacker if o["stage_change"].get("target") == "self" else target
                self.change_stage(tgt, o["stage_change"]["stat"], o["stage_change"]["delta"])
        for sc in mm.get("stage_changes_exec", []):
            tgt = attacker if sc.get("target") == "self" else target
            stats = ["atk", "def", "spa", "spd", "spe"] if sc["stat"] == "all" else [sc["stat"]]
            for st in stats:
                if st in tgt.stages:
                    self.change_stage(tgt, st, sc["delta"])
        if "drain" in mm and dealt:
            self.log(f"    흡수: 입힌 피해 {dealt}의 {mm['drain']['fraction']} 회복", f"{move_id} ({conf})")
            self.heal(attacker, math.floor(dealt * mm["drain"]["fraction"]))
        if "zone" in mm:
            if self.grid is not None:
                size = (self.r.moves_mech.get(move_id, {}).get("header", {}).get("range") or {}).get("size", 3)
                for cell in self.grid.ranged_blast(target.pos, size) | {target.pos}:
                    self.zone_cells[cell] = mm["zone"]["accuracy_penalty"]
                self.log(f"    {target.pos} 중심 폭발 {size} 영역에 연막: 명중 {mm['zone']['accuracy_penalty']}", f"{move_id} ({conf})")
            else:
                self.zones[target.name] = mm["zone"]["accuracy_penalty"]
                self.log(f"    {target.name} 주변에 연막: 명중 {mm['zone']['accuracy_penalty']}", f"{move_id} ({conf})")
        if "evasion_mod" in mm:
            target.evasion_mod += mm["evasion_mod"]["value"]
            self.log(f"    {target.name} 회피 {mm['evasion_mod']['value']:+d}", f"{move_id} ({conf})")
        if conf == "auto":
            for sc in mm.get("stage_changes", []):
                self.change_stage(target, STAT_KO[sc["stat"]], sc["delta"])
            for st in mm.get("status", []):
                self.apply_status(target, st)
        ctx = {"attacker": attacker, "target": target, "nat": nat, "hit": True, "dealt": dealt, "crit": crit, "move": move, "engine": self, "db": mm.get("header", {}).get("db") if isinstance(mm.get("header"), dict) else None,
               "multiplier": self.type_multiplier(move["type"], target)[0], "ko": target.fainted}
        done, held = FX.run_effects(self, attacker, target, mm.get("effects_exec", []), ctx, f"{move_id} ({conf})")
        self.effect_stats["done"] += done
        self.effect_stats["held"] += held
        EXT.after_move(self, attacker, target, move, mm, ctx)
        FX.fire_event(self, attacker, {"event": "on_hit_dealt", "move": move, "dealt": dealt}, target)
        FX.fire_event(self, target, {"event": "on_hit_received", "move": move, "dealt": dealt}, attacker)
        if target.fainted:
            FX.fire_event(self, attacker, {"event": "enemy_faint_by_user", "move": move}, target)
            FX.fire_event(self, target, {"event": "self_faint", "move": move}, attacker)
        return dealt

    def apply_effect(self, attacker, target, e, nat, hit, dealt, src):
        """effect-vocabulary 의 '기존' 유형을 실행한다 (조건 키가 있으면 검사)."""
        HEAVY.ensure_clear(self)
        if e.get("on_miss") or (e.get("if_weather") and not FX.weather_matches(self, e["if_weather"])):
            return
        if "on_natural_roll_min" in e and (nat is None or nat < e["on_natural_roll_min"]):
            return
        if e.get("on_natural_roll") == "even" and (nat is None or nat % 2):
            return
        tgt = attacker if e.get("target") == "self" else target
        t = e["type"]
        if t == "heal":
            num, den = e["fraction_of_max"]
            self.heal(tgt, tgt.base_max_hp * num // den)
        elif t == "hp_loss":
            v = e["value"]
            if isinstance(v, str):
                v = {"user.level": attacker.level, "current_hp/2": max(0, tgt.hp) // 2, "max_hp/2": tgt.base_max_hp // 2, "max_hp/4": tgt.base_max_hp // 4}.get(v)
                if v is None:
                    m = re.match(r"tick\*(\d+)", e["value"])
                    v = self.tick(tgt) * int(m.group(1)) if m else None
            if v is not None:
                self.log(f"    체력 손실 {v} ({e['value']})", src)
                self.lose_hp(tgt, v, source=src)
        elif t == "cure_status":
            for st in (e["status"] if isinstance(e["status"], list) else [e["status"]]):
                self.cure_status(tgt, STATUS_NORM.get(st, st))
        elif t == "cure_all_status":
            for st in list(tgt.conditions - {"기절"}):
                self.cure_status(tgt, st)
        elif t == "temp_hp" and isinstance(e.get("value"), int):
            tgt.temp_hp = max(getattr(tgt, "temp_hp", 0), e["value"])
            self.log(f"    {tgt.name} 임시 체력 {tgt.temp_hp}", src)
        elif t == "set_weather":
            self.weather = e["weather"]
            self.log(f"    날씨: {e['weather']}", src)
        elif t == "apply_status_random":
            st = self.rng.choice(e["options"])
            self.log(f"    무작위 상태 {e['options']} → {st}", src)
            self.apply_status(tgt, st)
        elif t == "stage_change" and isinstance(e.get("delta"), int):
            stats = ["atk", "def", "spa", "spd", "spe"] if e["stat"] == "all" else [e["stat"]]
            for st in stats:
                if st in tgt.stages:
                    self.change_stage(tgt, st, e["delta"])

    # ---------- 격자: 범위 키워드로 대상 선택 ----------
    def targets_in_range(self, attacker, move, candidates, primary):
        """moves-mech 의 range 구조(origin/shape/size)와 Grid 로 실제 맞는 대상을 고른다. 격자가 없으면 primary 하나."""
        if self.grid is None:
            return [primary]
        rng = self.r.moves_mech.get(move["id"], {}).get("header", {}).get("range") or {"raw": move.get("range", "")}
        shape, size, origin = rng.get("shape"), rng.get("size"), rng.get("origin")
        others = [c for c in candidates if c is not attacker and not c.fainted and not c.captured and getattr(c, "on_field", True)]
        if shape == "burst":
            cells = self.grid.burst(attacker.pos, size)
            return [c for c in others if c.pos in cells]
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
            hit = [c for c in others if c.pos in cells]
            self.log(f"    범위 {rng.get('raw')}: 방향 {d}, 칸 {len(cells)}개 → {', '.join(c.name for c in hit) or '아무도 없음'}", "ch10/범위-키워드")
            return hit
        if shape == "blast":
            cells = self.grid.ranged_blast(primary.pos, size)
            return [c for c in others if c.pos in cells]
        reach = 1 if origin == "melee" else (origin if isinstance(origin, int) else 99)
        if cheb(attacker.pos, primary.pos) > reach or self.grid.blocked(attacker.pos, primary.pos):
            return []
        return [primary] if primary in others else []       # 퇴장(볼 복귀)·기절·포획된 대상은 고를 수 없다

    def move_profile(self, c):
        """(이동 거리, 방식): 공중/부유 이동이 육상보다 빠르면 그걸 쓴다 — 공중·부유는 둔화/험한 지형 비용을 무시한다(차단 지형은 통과 못 함)."""
        mv = c.spec.get("movement") or {}
        land = mv.get("land", c.movement)
        sky = max(mv.get("sky", 0), mv.get("levitate", 0))
        if sky > land:
            return sky, "공중/부유"
        return land, "육상"

    def occupied(self, except_c=None):
        return {x.pos for x in (self.everyone or []) if x is not except_c and not x.fainted and not x.captured and getattr(x, "on_field", True)}

    def approach(self, c, target, reach=1):
        """이동 행동: 차단 지형과 다른 전투원을 피해(너비 우선 경로) 대상의 사거리 안 가장 가까운 칸으로. 둔화 지형은 2칸 비용(공중/부유는 1칸)."""
        HEAVY.ensure_clear(self)
        if self.grid is None:
            return
        if cheb(c.pos, target.pos) <= reach and not self.grid.blocked(c.pos, target.pos):
            return
        if not TURN.spend(self, c, "shift", "이동", movement=True):
            return
        budget, mode = self.move_profile(c)
        if "질주" in c.custom_conditions:
            budget = int(budget * 1.5)
        adjacent_before = TURN.adjacent_enemies(self, c)
        occ = self.occupied(c)
        goal_ok = lambda p: cheb(p, target.pos) <= reach and p not in occ and not self.grid.blocked(p, target.pos)
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
                    if not self.grid.inside(q) or self.grid.blocked(p, q) or q in occ:
                        continue
                    diagonal = bool(dx and dy)
                    cost = (2 if diagonal and parity else 1) + int(q in self.grid.slow and mode == "육상")
                    nxt = (*q, parity ^ int(diagonal))
                    nd = d + cost
                    if nd < dist.get(nxt, 1e9):
                        dist[nxt] = nd
                        prev[nxt] = state
                        heapq.heappush(heap, (nd, nxt))
        if best is None:
            self.log(f"  {c.name} 이동 행동: {target.name}에게 가는 길이 막힘", "ch07/이동과-위치선정")
            return
        path = []
        state = best
        while state != start:
            path.append(state)
            state = prev[state]
        path.reverse()
        moved, spent = 0, 0
        for state in path:
            q = state[:2]
            diagonal = c.pos[0] != q[0] and c.pos[1] != q[1]
            parity = getattr(c, "_diagonal_steps", 0) % 2
            cost = (2 if diagonal and parity else 1) + int(q in self.grid.slow and mode == "육상")
            if spent + cost > budget:
                break
            if diagonal:
                c._diagonal_steps = getattr(c, "_diagonal_steps", 0) + 1
            c.pos = q
            spent += cost
            moved += 1
            EXT.on_enter_cell(self, c, c.pos)
        if moved:
            c.airborne = (mode == "공중/부유")
            self.log(f"  {c.name} 이동 행동: {moved}칸 → {c.pos} ({mode} {budget}{', 경로 ' + str(len(path)) + '칸' if len(path) > moved else ''})", "ch07/이동과-위치선정")
            now = {id(x) for x in TURN.adjacent_enemies(self, c)}
            left = [x for x in adjacent_before if id(x) not in now]
            if left and moved > 1:          # 1칸만 움직인 것은 '이탈' 동작으로 본다 (기회 공격 미유발)
                TURN.trigger_aoo(self, c, "인접 칸 밖으로 이동", left)

    # ---------- 포획 ----------
    def capture_rate(self, target, rarity=0):
        cr = self.r.mech("pokemon/capture-rate")["capture_rate"]
        rate = cr["base"] + target.level // 10 * cr["per_10_levels"] + rarity
        boxes = 0
        ctx = {"hp": target.hp, "max_hp": target.base_max_hp, "injuries": target.injuries,
               "status": bool(target.conditions - {"기절", "취약"}), "evo": target.spec.get("evolutions_remaining", 0)}
        for cb in cr["checkboxes"]:
            hit = {"hp_le_50": ctx["hp"] <= 0.5 * ctx["max_hp"], "hp_le_25": ctx["hp"] <= 0.25 * ctx["max_hp"],
                   "injuries_ge_5": ctx["injuries"] >= 5, "any_status": ctx["status"],
                   "two_evolutions_left": ctx["evo"] == 2, "one_evolution_left": ctx["evo"] == 1}[cb["id"]]
            if hit:
                boxes += cb["boxes"]
        return rate - boxes * cr["checkbox_penalty"], boxes

    def capture_rate_superseded(self, target, hp_fraction, demo_hp_penalty=25):
        """구판(1d100): 데모 재현용. 100 - 2×레벨 - (체력 75%↑: 30, 데모 25) + (진화 2단계 남음: 10) + 5×부상."""
        rate = 100 - 2 * target.level
        if hp_fraction >= 0.75:
            rate -= demo_hp_penalty
        if target.spec.get("evolutions_remaining") == 2:
            rate += 10
        rate += 5 * target.injuries
        return rate

    def throw_ball(self, trainer, target, ball_name="몬스터볼", rarity=0):
        """몬스터볼 투척: AC 6 변화기 → 포획 굴림 1d20 + 트레이너 보너스 + 볼 보정(engine/items.py BALL_RULES) ≥ 포획률. 기절·주인 있는 포켓몬은 불가."""
        HEAVY.ensure_clear(self)
        cr = self.r.mech("pokemon/capture-rate")
        if not TURN.can_act(self, trainer):
            return False
        if target.fainted or target.captured or target.side == "party":
            self.log(f"    {target.name}: 기절했거나 이미 주인이 있어 포획 불가", "pokemon/capture-rate")
            return False
        if not TURN.spend(self, trainer, "standard", ball_name):
            return False
        trainer.took_standard = True
        ball = {"id": "ball", "name": ball_name, "class": "변화", "ac": cr["throw"]["ac"], "type": "노말"}
        hit, nat, _ = self.accuracy_check(trainer, target, ball)
        if not hit:
            return False
        rate, boxes = self.capture_rate(target, rarity)
        bonus = max([b for lv, b in cr["trainer_bonus_by_level"].items() if trainer.level >= int(lv)], default=0)
        bmod, bwhy = ITEMS.ball_modifier(self, ball_name, trainer, target)
        roll = self.d20() + bonus + bmod
        ok = roll >= rate
        self.log(f"    포획 굴림 1d20{bonus:+d}{bmod:+d}[{bwhy}] = {roll} vs 포획률 {rate} (체크박스 {boxes}개) → {'포획!' if ok else '실패'}", "pokemon/capture-rate")
        if ok:
            target.captured = True
            after = ITEMS.BALL_AFTER.get(ball_name.replace("item/", ""))
            if after == "full_heal":
                target.hp = target.max_hp
                for x in list(target.conditions):
                    self.cure_status(target, x)
                self.log(f"    {ball_name}: 포획한 {target.name} 체력·상태 완전 회복", f"item/{ball_name}")
            elif after:
                self.log(f"    {ball_name}: 포획 후 효과 {after} (GM 적용)", f"item/{ball_name}")
            caught = trainer.spec.setdefault("caught_species", [])
            if target.spec.get("species") and target.spec["species"] not in caught:
                caught.append(target.spec["species"])
        return ok

    # ---------- 스킬 체크 (d6 풀) ----------
    def _prepare_skill_roll(self, c, skill, mods=0, helper_rank=0, fixed=None, *, penalty_count=0, fixed_penalties=None):
        """Ordinary rank procedure; validate the entire request before consuming RNG."""
        if getattr(c,'dead',False) or getattr(c,'fainted',False) or getattr(c,'hp',1)<=0:
            raise ValueError('unconscious actor requires a sourced action exception')
        self.r.mech("gameplay/skill-check")
        ranks = self.r.mech("gameplay/skill-rank-dice")["by_rank_name"]
        rank_name = c.spec.get("skills", {}).get(skill, "미숙")
        if rank_name not in ranks:raise ValueError("unresolved skill rank: " + str(rank_name))
        expr = ranks[rank_name]["dice"]
        if not re.fullmatch(r"[1-6]d6", expr):raise ValueError("specialized skill dice require a sourced extension")
        n = int(expr.split("d")[0])
        CHECKS.validate_request(n,mods,helper_rank,penalty_count)
        faces = CHECKS.dice(fixed,n) if fixed is not None else None
        penalties = CHECKS.dice(fixed_penalties,penalty_count) if fixed_penalties is not None else None
        return rank_name,expr,n,faces,penalties

    def skill_roll(self, c, skill, mods=0, helper_rank=0, fixed=None, *, penalty_count=0, fixed_penalties=None):
        rank_name,expr,n,faces,penalties=self._prepare_skill_roll(c,skill,mods,helper_rank,fixed,penalty_count=penalty_count,fixed_penalties=fixed_penalties)
        if faces is None:faces=tuple(self.rng.randint(1,6) for _ in range(n))
        if penalties is None:penalties=tuple(self.rng.randint(1,6) for _ in range(penalty_count))
        result=CHECKS.SkillRoll(n,faces,mods,helper_rank,penalties)
        self.log(f"  {c.name} {skill}({rank_name}) {expr}{mods:+d} 지원 +{helper_rank//2}, 패널티 {penalties}: {faces} → {result.total}", "gameplay/skill-check")
        return result

    def skill_check(self, c, skill, dc, mods=0, helper_rank=0, fixed=None, *, penalty_count=0, fixed_penalties=None):
        CHECKS.integer(dc,'DC')
        result=CHECKS.against_dc(self.skill_roll(c,skill,mods,helper_rank,fixed,penalty_count=penalty_count,fixed_penalties=fixed_penalties),dc)
        self.log(f"  판정 {result.total} vs DC {dc}, 차이 {result.margin} → {'성공' if result.passed else '실패'}", "gameplay/skill-check")
        return result.passed,result.total

    def opposed_check(self, a, skill_a, b, skill_b, *, challenger_options=None, defender_options=None):
        """b must be the defender maintaining the status quo; ties favor b."""
        challenger_options={} if challenger_options is None else challenger_options
        defender_options={} if defender_options is None else defender_options
        self._prepare_skill_roll(a,skill_a,**challenger_options)
        self._prepare_skill_roll(b,skill_b,**defender_options)
        ra=self.skill_roll(a,skill_a,**challenger_options)
        rb=self.skill_roll(b,skill_b,**defender_options)
        winner=CHECKS.opposed(ra,rb)
        self.log(f"  대항 체크: {a.name} {ra.total} vs {b.name} {rb.total} → {'공격 측 승' if winner=='challenger' else '수비 측 승(동률 포함)'}", "gameplay/skill-check")
        return winner=='challenger'

    def common_action(self, c=None, skill=None, dc=None, *, mode=None, outcome=None, description=None, cost=None, failure_margin_accepted=False, **roll_options):
        """Explicit ordinary-action branch. Does not apply world-state effects.
        The GM selects mode, skill, DC and consequences; specialized action
        interfaces and automatic modifier collection are outside this procedure.
        """
        CHECKS.validate_adjudication(outcome,description,cost,failure_margin_accepted)
        if c is not None and (getattr(c,'dead',False) or getattr(c,'fainted',False) or getattr(c,'hp',1)<=0):
            return CHECKS.PendingDecision('unconscious actor requires a sourced action exception')
        if mode is None:return CHECKS.PendingDecision('GM action branch / skill / DC')
        if mode=='no_roll':return CHECKS.adjudicate(outcome=outcome,description=description,cost=cost,failure_margin_accepted=failure_margin_accepted)
        if mode!='skill':return CHECKS.PendingDecision('specialized action interface: '+str(mode))
        if c is None or skill is None or dc is None:return CHECKS.PendingDecision('GM actor / skill / DC')
        CHECKS.integer(dc,'DC')
        check=CHECKS.against_dc(self.skill_roll(c,skill,**roll_options),dc)
        return CHECKS.adjudicate(check,outcome=outcome,description=description,cost=cost,failure_margin_accepted=failure_margin_accepted)

    # ---------- 이니셔티브 ----------
    def initiative(self, combatants):
        """Ordinary order, or None while a required initiative decision is pending."""
        import initiative as INITIATIVE
        return INITIATIVE.order(self, combatants)


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
                    weak = [o for o in alive_odd if o.hp <= 0.5 * o.max_hp]
                    if weak and silvana.spec["items"]["poke_ball"] > 0:
                        silvana.spec["items"]["poke_ball"] -= 1
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
