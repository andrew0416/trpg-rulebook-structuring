"""
최종 산출물: PTK 룰북 전체를 RuleUnit 하나의 DB(JSONL)로 내보낸다.

  python -X utf8 -I tools/export_ruleunits.py <experiment_root>

합치는 것
  - 헤딩 노드 전부 (output/structure-map.json + input/*.md 본문 슬라이스)          → kind = 분류기 unit_type, mech = null
  - A층 수작업 단위 (data/core-rules.json, data/contest-rules.json), D층 표 (data/lookup-tables.json), B층 상태 (data/conditions.json)
  - 블록 엔티티 (output/entities/*.json: feat, edge, maneuver, capability, keyword, item, poke_edge, weapon_move, contest_effect, action_type, class, …)
    feat 는 output/feat-graph.json 의 refs 를 붙인다
  - 시트 엔티티: 기술(헤더 + mech: hand > auto full > llm > auto partial), 특성(auto), 포켓몬 종(헤더만으로 full)
검증: 모든 레코드가 id/kind/title/source/text.body 를 갖는지, id 유일성, refs 대상 존재 여부. 결과 요약은 output/ruleunits-coverage.md.
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict

DOC = "PTK 코어 룰북 (PTU 1.05 한국어 번역, 포켓몬스터 TRPG 한국 지부)"
LIC = "팬 제작 무료 배포물 / 번역 저작물 — 비공개 실험용"


def load(root, rel):
    return json.load(open(os.path.join(root, rel), encoding="utf-8"))


def unit(id_, kind, title, source, body, summary=None, mech=None, refs=None, tags=None, extra=None):
    u = {"id": id_, "kind": kind, "title": title, "source": {"document": DOC, "license": LIC, **source},
         "text": {"body": body or ""}, "mech": mech}
    if summary:
        u["text"]["summary"] = summary
    if refs:
        u["refs"] = refs
    if tags:
        u["tags"] = tags
    if extra:
        u.update(extra)
    return u


def slug(s):
    s = re.sub(r"\[.*?\]|\(.*?\)", "", str(s))
    return re.sub(r"[^0-9a-z가-힣]+", "-", s.lower()).strip("-") or "x"


def main(root):
    out, seen = [], set()
    location_overrides = load(root, "data/source-location-overrides.json")["units"] if os.path.exists(os.path.join(root, "data/source-location-overrides.json")) else {}

    def add(u):
        if u["id"] in location_overrides:
            u["source"].update(location_overrides[u["id"]])
        if u["id"] in seen:
            u["id"] += "-" + str(sum(1 for x in out if x["id"].startswith(u["id"])))
        seen.add(u["id"])
        out.append(u)

    # 1. 헤딩 노드 (참조 층)
    smap = load(root, "output/structure-map.json")
    files = {}
    for n in smap["nodes"]:
        ch = n["chapter"]
        if ch not in files:
            files[ch] = open(os.path.join(root, "input", ch + ".md"), encoding="utf-8").read().splitlines()
        body = "\n".join(files[ch][n["line"]:n["end"]]).strip()
        kind = n["unit_type"]
        add(unit(slug(n["id"]).replace("--", "-") if "/" not in n["id"] else "/".join(slug(p) for p in n["id"].split("/")),
                 kind, n["title"], {"path": n["id"].split("/"), "file": ch + ".md", "lines": [n["line"], n["end"]]},
                 body, tags=[ch, kind.split(":")[0]], extra={"_layer": "E" if kind.startswith("rule") or kind in ("example", "container", "chapter") else "A" if kind == "procedure" else "D" if kind == "table" else "B/C"}))

    # 2. 수작업/자동 mech 단위
    for rel in ("data/core-rules.json", "data/contest-rules.json", "data/progression-rules.json"):
        if not os.path.exists(os.path.join(root, rel)):
            continue
        for u in load(root, rel)["units"]:
            src = u["source"]
            add(unit(u["id"], u["kind"], u["text"].get("summary", u["id"])[:60], {"path": [src.get("chapter", ""), src.get("section", "")], "file": src.get("chapter", "") + ".md", "lines": [src.get("line", 0), src.get("line", 0)]},
                     u["text"].get("body", ""), u["text"].get("summary"), u.get("mech"), [{"to": r, "relation": "uses_term"} for r in u.get("refs", [])], ["A", "hand"], {"_layer": "A"}))
    for u in load(root, "data/lookup-tables.json"):
        src = u["source"]
        add(unit(u["id"], "table", u["text"]["summary"], {"path": [src.get("chapter", src.get("sheet", ""))], "file": src.get("chapter", "") + ".md" if src.get("chapter") else src.get("sheet", ""), "lines": [src.get("line", 0), src.get("line", 0)]},
                 u["text"].get("note", ""), u["text"]["summary"], u["mech"], tags=["D", "auto"], extra={"_layer": "D"}))
    for u in load(root, "data/conditions.json"):
        src = u["source"]
        add(unit(u["id"], u["kind"], u["mech"]["data"]["name"], {"path": src["section"].split(" / "), "file": src["chapter"] + ".md", "lines": [src["line"], src["line"]]},
                 u["text"]["body"], u["text"]["summary"], u["mech"], tags=["B", "auto"], extra={"_layer": "B"}))

    # 3. 블록 엔티티
    ent = os.path.join(root, "output/entities")
    graph = {n["id"]: n for n in load(root, "output/feat-graph.json")["nodes"]}
    # 재주·엣지·아이템 mech: 규칙 기반(…-mech.json, tools/mechanize_feats.py / mechanize_items.py) full > LLM 초안(…-llm.json, tools/apply_drafts.py) > 규칙 기반 partial > 필드만
    feats_mech = load(root, "data/feats-mech.json") if os.path.exists(os.path.join(root, "data/feats-mech.json")) else {}
    feats_llm = load(root, "data/feats-llm.json")["feats"] if os.path.exists(os.path.join(root, "data/feats-llm.json")) else {}
    items_mech = load(root, "data/items-mech.json") if os.path.exists(os.path.join(root, "data/items-mech.json")) else {}
    items_llm = load(root, "data/items-llm.json")["items"] if os.path.exists(os.path.join(root, "data/items-llm.json")) else {}
    edges_llm = load(root, "data/edges-llm.json")["edges"] if os.path.exists(os.path.join(root, "data/edges-llm.json")) else {}
    reviewed_cx = {}
    for rel, key in (("data/feats-reviewed.json", "feats"), ("data/items-reviewed.json", "items"), ("data/edges-reviewed.json", "edges")):
        if os.path.exists(os.path.join(root, rel)):
            reviewed_cx.update(load(root, rel)[key])
    src_cx = Counter()

    feat_by_slug = {}
    for k in list(feats_llm) + [k for k, v in feats_mech.items() if v.get("coverage") == "full"]:
        feat_by_slug.setdefault(k.split("/", 1)[1], k)

    def gift_alias(uid):
        """기프트 시트 id → 같은 이름(접미사 일치)의 재주 초안 id. 시트와 본문이 같은 전설 기프트를 두 번 담고 있어서."""
        g = re.sub(r"-\d+$", "", uid.split("/", 1)[1])
        if g in feat_by_slug:
            return feat_by_slug[g]
        return next((k for s, k in feat_by_slug.items() if s.endswith("-" + g) or g.endswith("-" + s)), None)

    def pick_mech(uid, schema, data):
        """(mech) — reviewed > auto full > llm > auto partial > 필드만(partial, 자유문). 기프트 시트는 같은 이름의 재주 초안을 빌린다."""
        dup = uid if uid not in seen else uid + "-" + str(sum(1 for x in out if x["id"].startswith(uid)))
        auto = (feats_mech if schema in ("feat", "gift") else items_mech if schema in ("item", "crafted_item") else {}).get(dup if schema in ("feat", "gift") else uid)
        llm = (feats_llm if schema in ("feat", "gift") else items_llm if schema in ("item", "crafted_item") else edges_llm).get(uid)
        if schema == "item" and llm is None and data.get("_same_source_effect"):
            llm = items_llm.get(data.get("_source_id"))
        if schema == "gift" and auto is None and llm is None:
            alias = gift_alias(uid)
            if alias:
                auto, llm = feats_mech.get(alias), feats_llm.get(alias)
                data = {**data, "_alias_of": alias}
        header = {k: v for k, v in (auto or {}).get("header", {}).items()} if auto else {}
        dup = uid if uid not in seen else uid + "-" + str(sum(1 for x in out if x["id"].startswith(uid)))     # add() 가 붙일 중복 접미사 id (검수 큐는 이 id 를 쓴다)
        rv = reviewed_cx.get(dup) or reviewed_cx.get(uid) or (reviewed_cx.get(data.get("_alias_of")) if data.get("_alias_of") else None)
        if rv is not None:
            src_cx[schema + ":reviewed"] += 1
            gm = any(isinstance(e, dict) and e.get("type") in ("gm", "rule") for e in rv["effects"])
            return {"schema": schema, "confidence": "reviewed", "coverage": rv.get("coverage", "partial" if gm else "full"), "data": {**data, "header": header, "effects": rv["effects"], "_review_note": rv.get("note", "")}}
        if auto and auto.get("coverage") == "full":
            src_cx[schema + ":auto"] += 1
            return {"schema": schema, "confidence": "auto", "coverage": "full", "data": {**data, "header": header, "effects": [{k: v for k, v in e.items() if k != "_src"} for e in auto["effects"]]}}
        if llm is not None:
            src_cx[schema + ":llm"] += 1
            gm = any(isinstance(e, dict) and e.get("type") in ("gm", "rule") for e in llm)
            return {"schema": schema, "confidence": "llm", "coverage": "partial" if gm else "full", "data": {**data, "header": header, "effects": llm}}
        if auto and auto.get("effects"):
            src_cx[schema + ":auto-partial"] += 1
            return {"schema": schema, "confidence": "auto", "coverage": "partial", "data": {**data, "header": header, "effects": [{k: v for k, v in e.items() if k != "_src"} for e in auto["effects"]], "narrative": auto.get("narrative", [])}}
        src_cx[schema + ":none"] += 1
        return {"schema": schema, "confidence": "auto", "coverage": "partial", "data": data, "_note": "필드는 구조화됐지만 효과 본문은 자유문"}
    kinds = {"feat": "entity:feat", "edge": "entity:edge", "poke_edge": "entity:poke_edge", "maneuver": "definition:maneuver", "capability": "definition:capability",
             "keyword": "definition:keyword", "item": "entity:item", "weapon_move": "entity:weapon_move", "contest_effect": "definition:contest_effect",
             "action_type": "definition:action_type", "stat": "definition:stat", "definition": "definition:term", "crafted_item": "entity:item", "gift": "entity:feat", "block": "entity:block"}
    for fname, kind in kinds.items():
        path = os.path.join(ent, fname + ".json")
        if not os.path.exists(path):
            continue
        for r in load(root, f"output/entities/{fname}.json"):
            body = r.get("text") or "\n".join(f"{k}: {v}" for k, v in r.items() if k in ("prereq", "frequency", "trigger", "target", "effect", "cost", "reagent", "ac", "range", "class", "type", "restriction") and v)
            refs = None
            if fname == "feat" and r["id"] in graph:
                refs = [{"to": x["ref"], "relation": "prerequisite", "resolved": True} for x in graph[r["id"]]["refs"] if x.get("ref")]
                refs += [{"to": f"skill/{slug(x['skill'])}", "relation": "prerequisite", "resolved": True, "rank": x["rank"]} for x in graph[r["id"]]["refs"] if x["kind"] == "skill_rank"]
            mech = None
            if fname in ("feat", "edge", "poke_edge", "gift", "crafted_item", "item"):
                data = {k: v for k, v in r.items() if k not in ("id", "name", "eng", "chapter", "section", "line", "extra", "_source")}
                mech = pick_mech(r["id"], fname, data)
            elif fname in ("maneuver", "weapon_move"):
                data = {k: v for k, v in r.items() if k not in ("id", "name", "eng", "chapter", "section", "line", "extra", "_source")}
                mech = {"schema": fname, "confidence": "auto", "coverage": "partial", "data": data, "_note": "필드는 구조화됐지만 효과 본문은 자유문"}
            add(unit(r["id"], kind, r["name"], {"path": r.get("section", "").split(" / "), "file": r.get("chapter", "") + ".md", "lines": [r.get("line", 0), r.get("end_line", r.get("line", 0))], **r.get("_source", {})},
                     body, None, mech, refs, [fname, "B" if kind.startswith("definition") else "C"], {"eng": r.get("eng"), "_layer": "B" if kind.startswith("definition") else "C"}))
    for c in load(root, "output/entities/classes.json"):
        add(unit(c["id"], "entity:class", c["name"], {"path": ["Chapter 4 : 트레이너 클래스", c["category"], c["name"]], "file": "ch04-trainer-classes.md", "lines": [c["line"], c["line"]]},
                 "", None, {"schema": "class", "confidence": "auto", "coverage": "partial", "data": {k: v for k, v in c.items() if k not in ("id", "name", "eng", "line")}},
                 [{"to": f"feat/{slug(f)}", "relation": "grants", "resolved": True} for f in c["features"]], ["class", "C"], {"eng": c["eng"], "_layer": "C"}))

    # 4. 시트 엔티티
    mech_auto = load(root, "data/moves-mech.json")
    reviewed_mv = load(root, "data/moves-reviewed.json")["moves"] if os.path.exists(os.path.join(root, "data/moves-reviewed.json")) else {}
    reviewed_ab = load(root, "data/abilities-reviewed.json")["abilities"] if os.path.exists(os.path.join(root, "data/abilities-reviewed.json")) else {}
    verdicts = load(root, "data/review-verdicts.json") if os.path.exists(os.path.join(root, "data/review-verdicts.json")) else {}
    hand = load(root, "data/moves-hand.json")["moves"]
    llm = load(root, "data/moves-llm.json")["moves"]
    llm_partial = load(root, "data/moves-llm-partial.json")["moves"]
    src_mv = Counter()
    core_mv = Counter()
    for m in load(root, "output/entities/moves.json"):
        mid = m["id"]
        auto = mech_auto.get(mid)
        header = auto["header"] if auto else {"type": m["type"], "class": m["class"], "damage_base": m["damage_base"], "ac": m["ac"], "frequency": m["frequency"], "range": m["range"]}
        if mid in hand:
            hm = hand[mid]["mech"]
            eff = []
            for k, v in hm.items():          # moves-hand 의 평면 dict → effects 목록
                if k == "on_natural_roll":
                    if "apply_status" in v:
                        eff.append({"type": "apply_status", "status": v["apply_status"], "target": "target", "on_natural_roll_min": v["min"]})
                    if "stage_change" in v:
                        eff.append({"type": "stage_change", **v["stage_change"], "target": v["stage_change"].get("target", "target"), "on_natural_roll_min": v["min"]})
                elif k == "apply_status":
                    eff.append({"type": "apply_status", "status": v, "target": "target"})
                elif k == "never_miss":
                    eff.append({"type": "never_miss"})
                elif k == "drain":
                    eff.append({"type": "drain", **v})
                elif k == "zone":
                    eff.append({"type": "accuracy_mod", "value": v["accuracy_penalty"], "target": "target", "zone": True})
                elif k == "evasion_mod":
                    eff.append({"type": "evasion_mod", **v, "target": "target"})
                elif k == "push":
                    eff.append({"type": "push", **v, "target": "target"})
            mech = {"schema": "move", "confidence": "hand", "coverage": "full", "data": {"header": header, "effects": eff}}
        elif mid in reviewed_mv:
            eff = reviewed_mv[mid]["effects"]
            mech = {"schema": "move", "confidence": "reviewed", "coverage": "full" if not any(e["type"] == "gm" for e in eff) else "partial", "data": {"header": header, "effects": eff}}
        elif auto and auto["coverage"] == "full":
            mech = {"schema": "move", "confidence": "auto", "coverage": "full", "data": {"header": header, "effects": [{k: v for k, v in e.items() if k != "_src"} for e in auto["effects"]]}}
        elif m["name"] in llm:
            mech = {"schema": "move", "confidence": "llm", "coverage": "full" if not any(e["type"] == "gm" for e in llm[m["name"]]["effects"]) else "partial", "data": {"header": header, "effects": llm[m["name"]]["effects"]}}
        elif auto and auto["coverage"] == "partial" and m["name"] in llm_partial:
            eff = [{k: v for k, v in e.items() if k != "_src"} for e in auto["effects"]] + llm_partial[m["name"]]
            mech = {"schema": "move", "confidence": "auto+llm", "coverage": "full" if not any(e["type"] == "gm" for e in eff) else "partial", "data": {"header": header, "effects": eff}}
        elif auto:
            mech = {"schema": "move", "confidence": "auto", "coverage": auto["coverage"], "data": {"header": header, "effects": [{k: v for k, v in e.items() if k != "_src"} for e in auto["effects"]], "narrative": auto["narrative"]}}
        else:
            mech = {"schema": "move", "confidence": "auto", "coverage": "partial", "data": {"header": header, "effects": [], "narrative": [m["effect"]]}, "_note": "홈브류 구역"}
        src_mv[mech["confidence"] + ":" + mech["coverage"]] += 1
        if not m.get("homebrew"):
            core_mv[mech["coverage"]] += 1
        add(unit(mid, "entity:move", m["name"], {"path": ["데이터베이스 시트", "기술 목록"] + (["홈브류"] if m.get("homebrew") else []), "file": "db/moves.csv", "lines": [0, 0], **m.get("_source", {})},
                 m["effect"], f"{m['type']} {m['class']} DB {m['damage_base']} AC {m['ac']} {m['frequency']} {m['range']}", mech, None, ["move", "C"] + (["homebrew"] if m.get("homebrew") else []), {"eng": m.get("eng"), "_layer": "C", **({"review": verdicts[mid]} if mid in verdicts else {})}))
    ab_mech = load(root, "data/abilities-mech.json")
    ab_llm = load(root, "data/abilities-llm.json")["abilities"] if os.path.exists(os.path.join(root, "data/abilities-llm.json")) else {}
    src_ab = Counter()
    for a in load(root, "output/entities/abilities.json"):
        am = ab_mech.get(a["id"])
        if a["id"] in reviewed_ab:
            eff = reviewed_ab[a["id"]]["effects"]
            mech = {"schema": "ability", "confidence": "reviewed", "coverage": "partial" if any(e.get("type") == "gm" for e in eff) else "full", "data": {"header": am["header"] if am else {}, "effects": eff}}
        elif am and am["coverage"] == "full":
            mech = {"schema": "ability", "confidence": "auto", "coverage": "full", "data": {"header": am["header"], "effects": [{k: v for k, v in e.items() if k != "_src"} for e in am["effects"]]}}
        elif a["name"] in ab_llm:
            eff = ab_llm[a["name"]]
            mech = {"schema": "ability", "confidence": "llm", "coverage": "partial" if any(e.get("type") == "gm" or "truncated" in json.dumps(e, ensure_ascii=False) for e in eff) else "full",
                    "data": {"header": am["header"] if am else {}, "effects": eff}}
        elif am and am["coverage"] == "partial":
            mech = {"schema": "ability", "confidence": "auto", "coverage": "partial", "data": {"header": am["header"], "effects": [{k: v for k, v in e.items() if k != "_src"} for e in am["effects"]], "narrative": am["narrative"]}}
        else:
            mech = {"schema": "ability", "confidence": "auto", "coverage": "none", "data": {"header": am["header"] if am else {}, "effects": [], "narrative": [a["effect"]]}}
        src_ab[mech["confidence"] + ":" + mech["coverage"]] += 1
        add(unit(a["id"], "entity:ability", a["name"], {"path": ["데이터베이스 시트", "특성 데이터"], "file": "db/abilities.csv", "lines": [0, 0], **a.get("_source", {})}, a["effect"], a["frequency"], mech, None, ["ability", "C"], {"eng": a.get("eng"), "_layer": "C", **({"review": verdicts[a["id"]]} if a["id"] in verdicts else {})}))
    ls = {x["species"]: x for x in load(root, "output/entities/learnsets.json")} if os.path.exists(os.path.join(root, "output/entities/learnsets.json")) else {}
    sks = {x["species"]: x["skills"] for x in load(root, "output/entities/species_skills.json")} if os.path.exists(os.path.join(root, "output/entities/species_skills.json")) else {}
    links = {x["species"]: x for x in load(root, "output/entities/learnset_links.json")} if os.path.exists(os.path.join(root, "output/entities/learnset_links.json")) else {}
    for p in load(root, "output/entities/pokemon.json"):
        data = {k: v for k, v in p.items() if k not in ("id", "name", "eng", "dex", "group", "_source")}
        L = ls.get(p["name"])
        if L:
            data["learnset"] = {k: L[k] for k in ("level_up", "tm", "tutor", "evolution", "abilities") if k in L}
            data["learnset_confidence"] = L.get("confidence", "auto")
        if p["name"] in sks:
            data["skills"] = sks[p["name"]]
        lk = links.get(p["name"])
        sp_refs = None
        if lk:
            sp_refs = [{"to": m["to"], "relation": "uses_term", "source": m["source"]} for m in lk["moves"] if m.get("to")]
            sp_refs += [{"to": a["to"], "relation": "grants", "slot": a["slot"]} for a in lk["abilities"]]
            data["unresolved_links"] = lk["unresolved"]
        add(unit(p["id"], "entity:species", p["name"], {"path": ["데이터베이스 시트", "포켓몬 데이터"] + ([p["group"]] if p.get("group") else []), "file": "db/pokemon.csv", "lines": [0, 0], **p.get("_source", {})},
                 f"{p['name']} ({p['eng']}) #{p['dex']} 타입 {'/'.join(p['types'])} 기본 스탯 {p['base_stats']}", None,
                 {"schema": "species", "confidence": "auto", "coverage": "full", "data": data}, sp_refs, ["species", "C"], {"eng": p.get("eng"), "_layer": "C"}))

    # 4b. 나머지 시트: 아이템·레시피·테크닉·전설 기프트·필드·포켓봇
    extra = [("items_sheet.json", "entity:item", "item", ["데이터베이스 시트", "인벤/아이템 데이터"]),
             ("recipes.json", "entity:recipe", "recipe", ["데이터베이스 시트", "클래스 데이터", "레시피/케이스"]),
             ("techniques.json", "entity:technique", "technique", ["데이터베이스 시트", "클래스 데이터", "테크닉"]),
             ("legendary_gifts.json", "entity:feat", "gift", ["데이터베이스 시트", "클래스 데이터", "전설 기프트"]),
             ("fields_sheet.json", "definition:field", "field", ["데이터베이스 시트", "아이템 데이터", "날씨와 필드"]),
             ("pokebot.json", "table", "pokebot", ["데이터베이스 시트", "포켓봇 데이터"])]
    for fname, kind, tag, path in extra:
        fp = os.path.join(root, "output/entities", fname)
        if not os.path.exists(fp):
            continue
        if fname == "items_sheet.json":
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from item_records import sheet_items
            records = sheet_items(root)
        else:
            records = load(root, f"output/entities/{fname}")
        for i, r in enumerate(records):
            name = r.get("name") or r.get("포케봇 Size") or f"{tag}-{i}"
            rid = r.get("id") or f"{tag}/{slug(name)}-{i}"
            body = r.get("text") or r.get("desc") or r.get("effect") or json.dumps({k:v for k,v in r.items() if k != "_source"}, ensure_ascii=False)[:800]
            data = {k: v for k, v in r.items() if k not in ("id", "name", "text", "_source")}
            mech = pick_mech(rid, tag, data) if tag in ("item", "gift") else {"schema": tag, "confidence": "auto", "coverage": "partial", "data": data} if tag != "field" else None
            add(unit(rid, kind, name, {"path": path, "file": "db/", "lines": [0, 0], **r.get("_source", {})}, body, None,
                     mech, None, [tag, "C" if kind.startswith("entity") else "B/D"], {"_layer": "C" if kind.startswith("entity") else "D"}))

    # 4b. GM 재정(F층): data/gm-rulings.json — 룰북 단위를 덮어쓰는 단위. refs 는 relation=modifies 로 대상 단위를 가리킨다.
    for rfile in ("data/gm-rulings.json", "data/gm-rulings-errata.json"):
        rp = os.path.join(root, rfile)
        if not os.path.exists(rp):
            continue
        for r in load(root, rfile).get("rulings", []):
            k = r.get("kind")
            target = {"formula": {"tick": "combat/tick-of-hit-points", "max_hp.pokemon": "combat/hit-points", "max_hp.trainer": "combat/hit-points", "injury_penalty": "combat/injuries",
                                  "crit_range": "combat/critical-hit", "massive_damage": "combat/injuries", "stab": "combat/stab"}.get(r.get("name")),
                      "mech": r.get("unit"), "effect": r.get("move"), "situational": "combat/accuracy-roll" if r.get("modifier") in ("accuracy", "evasion") else "combat/damage-formula",
                      "answer": None}.get(k)
            if k == "formula":
                what = f"공식 {r.get('name')} = {r.get('expr')}"
            elif k == "mech":
                what = f"{r.get('unit')}.{r.get('path')} = {r.get('value')}"
            elif k == "effect":
                what = f"{r.get('move')} effect {r.get('op')} {r.get('match') or (r.get('effect') or {}).get('type', '')}"
            elif k == "situational":
                what = f"{r.get('modifier')} {r.get('value', 0):+} ({r.get('who') or '전원'})"
            elif k == "answer":
                what = f"프롬프트 '{r.get('key')}' → {r.get('answer')}"
            else:
                what = str(k)
            add(unit(f"ruling/{slug(r.get('id', what))}", "ruling:" + str(k), what[:60], {"path": ["GM 재정" if "errata" not in rfile else "에라타 재정", rfile], "file": rfile, "lines": [0, 0]},
                     r.get("reason", ""), f"범위 {r.get('scope', 'campaign')}", {"schema": "ruling", "confidence": "hand", "coverage": "full", "data": {x: y for x, y in r.items() if x != "reason"}},
                     [{"to": target, "relation": "modifies", "resolved": True}] if target else [], ["ruling", "F", "errata" if "errata" in rfile else "gm"], {"_layer": "F"}))
    # 5. 검증 (먼저 refs 대상 보정: resolve_refs 가 만든 'class/<제목>' 을 실제 헤딩 노드 id 로)
    ids = {u["id"] for u in out}
    by_title = {}
    for u in out:
        by_title.setdefault(slug(u["title"].split(":")[-1]), u["id"])
        by_title.setdefault(slug(u["title"]), u["id"])
    for u in out:
        for r in u.get("refs", []):
            if r["to"] not in ids and r["to"].startswith("class/"):
                key = slug(r["to"][6:].replace("-", " ").split(":")[-1])
                if key in by_title:
                    r["to"] = by_title[key]
    errors = []
    for u in out:
        for k in ("id", "kind", "title", "source", "text"):
            if k not in u or u[k] in (None, ""):
                errors.append(f"{u.get('id')}: {k} 없음")
        if not re.match(r"^[a-z0-9가-힣_\-]+(/[a-z0-9가-힣_\-]+)*$", u["id"]):
            errors.append(f"{u['id']}: id 형식")
        if "body" not in u["text"]:
            errors.append(f"{u['id']}: text.body 없음")
        if u.get("mech") and not all(k in u["mech"] for k in ("schema", "confidence", "coverage", "data")):
            errors.append(f"{u['id']}: mech 봉투 불완전")
    unresolved = sum(1 for u in out for r in u.get("refs", []) if r["to"] not in ids and not r["to"].startswith("skill/"))
    total_refs = sum(len(u.get("refs", [])) for u in out)

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from validate_ruleunits import validate_rows
    errors.extend(validate_rows(out, load(root, "schema/rule-unit.schema.json")))
    if errors:
        for error in errors:
            print(error)
        return False

    # 6. 출력
    with open(os.path.join(root, "output/ruleunits.jsonl"), "w", encoding="utf-8") as f:
        for u in out:
            f.write(json.dumps(u, ensure_ascii=False) + "\n")
    by_kind = Counter(u["kind"] for u in out)
    cov = defaultdict(Counter)
    for u in out:
        cov[u["kind"]][("없음" if not u.get("mech") else u["mech"]["coverage"] + "/" + u["mech"]["confidence"])] += 1
    lines = ["# PTK RuleUnit DB 커버리지 대시보드 (자동 생성)", "", f"총 {len(out)}개 단위 → [ruleunits.jsonl](ruleunits.jsonl). 검증 오류 {len(errors)}건, refs {total_refs}개 중 미해소 {unresolved}개.", "",
             "| kind | 수 | mech 상태 (coverage/confidence) |", "|---|---|---|"]
    for k, n in by_kind.most_common():
        lines.append(f"| {k} | {n} | " + ", ".join(f"{s} {c}" for s, c in cov[k].most_common()) + " |")
    with_mech = sum(1 for u in out if u.get("mech"))
    full = sum(1 for u in out if u.get("mech") and u["mech"]["coverage"] == "full")
    mv = sum(src_mv.values())
    lines += ["", f"- mech 보유 단위 {with_mech}/{len(out)} ({with_mech/len(out):.0%}), 그중 full {full}.",
              f"- 기술 {mv}개 mech 출처: " + ", ".join(f"{k} {v}" for k, v in src_mv.most_common()) + ".",
              f"- 특성 {sum(src_ab.values())}개 mech 출처: " + ", ".join(f"{k} {v}" for k, v in src_ab.most_common()) + ".",
              f"- 재주·엣지·아이템 mech 출처(auto=규칙 기반 full, llm=LLM 초안, auto-partial, none=필드만): " + ", ".join(f"{k} {v}" for k, v in sorted(src_cx.items())) + ".",
              f"- **코어 기술 {sum(core_mv.values())}개: " + ", ".join(f"{k} {v}" for k, v in core_mv.most_common()) + "** (자동 분류 표기이며 전체 효과 구현·원문 검수 완료를 뜻하지 않음).",
              f"- 전 단위에 로컬 text 필드가 있음. 원본 이미지·표·전체 의미의 완전한 보존 여부는 별도 감사 대상.",
              "- 층별: " + ", ".join(f"{k} {v}" for k, v in Counter(u["_layer"] for u in out).most_common()) + "."]
    if errors:
        lines += ["", "## 검증 오류", ""] + [f"- {e}" for e in errors[:30]]
    open(os.path.join(root, "output/ruleunits-coverage.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return len(errors) == 0


if __name__ == "__main__":
    sys.exit(0 if main(sys.argv[1] if len(sys.argv) > 1 else ".") else 1)
