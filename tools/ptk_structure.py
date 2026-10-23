"""
PTK(Pokemon Tabletop Korea = PTU 1.05 한국어 번역) 마크다운 -> 구조 맵 / 엔티티 추출 실험 도구.
srd-structure-experiment/tools/srd_structure.py 를 PTK 서식에 맞게 고친 것.

사용법:
  python -X utf8 -I ptk_structure.py outline  <input_dir> <out_dir>
  python -X utf8 -I ptk_structure.py entities <input_dir> <out_dir>

SRD와 가장 다른 점: PTK의 엔티티(재주·엣지·상태이상·전투동작·아이템·재능·키워드)는
헤딩이 아니라 **굵은 이름 줄 + 라벨 필드 줄** 블록(문단 단위)이다. 그래서 헤딩 노드 하나가
엔티티 수십 개를 담는 '목록 노드'가 되고, 추출기는 헤딩이 아니라 블록을 읽는다.
"""
import csv
import json
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from source_locations import record as source_record
from collections import Counter, defaultdict

CHAPTER_ORDER = [
    "ch00-front", "ch00-credits", "ch01-intro", "ch02-character-creation", "ch03-skills-edges-feats",
    "ch04-trainer-classes", "ch05-pokemon", "ch06-gameplay", "ch07-combat", "ch08-contests",
    "ch09-equipment", "ch10-index-reference", "ch11-running-the-game",
    "supp-fantasy", "supp-blessings",
    "hb-finance", "hb-terastal", "hb-zmoves", "hb-weather",
    "supp-polygon", "supp-errata",
]
CORE_CHAPTERS = set(CHAPTER_ORDER[:13])

H_RE = re.compile(r"^(#{1,6}) (.+?)\s*$")
EMPTY_H_RE = re.compile(r"^#{1,6} ?\s*$")                       # 구글문서 페이지 나눔이 빈 헤딩으로 남음
NAME_RE = re.compile(r"^\*\*([^*]{1,80}?)\*\*\s*$")              # **이름(Eng)**  단독 줄
MANEUVER_RE = re.compile(r"^\*\*동작\s*[:：]\s*([^*]+?)\*\*\s*$")   # **동작: 기회 공격(Attack of Opportunity)**
# **라벨:** 값  /  **라벨**: 값  /  **라벨: **값   (번역본은 콜론 위치가 제각각)
FIELD_RE = re.compile(r"^\*\*\s*([^*:：]{1,24}?)\s*[:：]?\s*\*\*\s*[:：]?\s*(.*)$")
# 한 줄 정의: **이름(Eng):** 본문  — 상태이상·재능·키워드·아이템·행동타입이 이 꼴
DEF_RE = re.compile(r"^\*\*([^*]{1,60}?)\s*[:：]?\s*\*\*\s*[:：]\s*(\S.*)$|^\*\*([^*]{1,60}?)\s*[:：]\s*\*\*\s*(\S.*)$")
FREQ_RE = re.compile(r"^(임의|항상|장면\s*(?:x\s*\d+)?|일일|하루(?:\s*x\s*\d+)?|\d+\s*AP(?:\s*(?:제거|지속))?|연장 행동(?:\([^)]{1,12}\))?|턴\s*1회|매 턴)\s*(?:[-–]\s*([^.。]{1,24}))?$")
TAG_RE = re.compile(r"^\[([^\]]+)\]")
STEP_RE = re.compile(r"^\d+\. |^### 스텝 \d|^\*\*\d+\.")
BULLET_RE = re.compile(r"^»")
ENG_RE = re.compile(r"^(.*?)\s*[\(（]([A-Za-z][^()（）]*)[\)）]\s*$")
XREF_RE = re.compile(r"(\d+)\s*(?:페이지|쪽)|\(?챕터\s*(\d+)|[‘'“\"]([^’'”\"]{2,20})[’'”\"]\s*(?:섹션|문단|챕터)?\s*을?\s*참조")
TYPELINE_RE = re.compile(r"^_(.+)_$")
SIDEBAR_LABELS = ("독시", "참고", "캐스트", "개발노트", "옵션 룰", "번역", "역주", "주석", "팁", "참고하세요")

FIELD_LABELS = {
    "전제조건": "prereq", "전제 조건": "prereq", "선제조건": "prereq", "전제": "prereq",
    "발동조건": "trigger", "발동 조건": "trigger", "효과": "effect", "대상": "target",
    "행동": "action", "AC": "ac", "분류": "class", "범위": "range", "빈도": "frequency",
    "참고": "note", "특수": "special", "계산": "calc", "예시": "example", "비용": "cost",
    "시약": "reagent", "조건": "condition",
    # 무기 기술(ch09) 전용 필드
    "기술이름": "name", "타입": "type", "기본 데미지": "damage_base", "사정거리": "range",
    "부가효과": "effect", "제한": "restriction", "무기 추천": "weapon_hint",
}
WEAPON_FIELDS = {"type", "damage_base", "restriction", "weapon_hint"}
# 엔티티가 아니라 서식/예시 필드인 굵은 라벨 (아키타입 소제목, 샘플 NPC 필드, 데모 대화 화자)
NOISE_LABELS = {"스킬", "주요 스킬", "제작 방법", "주목할만한 예", "이름", "나이", "성별", "전문성", "배틀 테마곡",
                "트레이너 클래스", "배경", "특성", "기술", "포켓몬 엣지", "전략", "보상", "테마", "GM", "실바나", "마야",
                "중요한 재주", "고유한 메커니즘", "커스텀 기술", "부가 데미지", "대체 기술 효과"}
VALUE_JUNK_RE = re.compile(r"^(?:\*\*\s*[:：]?\s*\*\*\s*[:：]?\s*|[:：]\s*)+")   # '**전제조건****:** 없음' 같은 이중 굵게 잔재


def match_name(line):
    """Recognize split bold runs and trailing translation glosses without changing source text."""
    normalized = line.rstrip().replace("****", "")
    # Only a fully bold bilingual name may have a trailing translator gloss.
    gloss = re.fullmatch(r"\*\*([^*]{1,80}?[（(][A-Za-z][^*()（）]*[)）])\s+[-–]\s+[^*]+\*\*", normalized)
    if gloss:
        normalized = "**" + gloss.group(1) + "**"
    return NAME_RE.match(normalized)


def norm_label(s):
    s = re.sub(r"\(.*?\)", "", s).strip()
    return s


def slug(s):
    s = re.sub(r"\[.*?\]|\(.*?\)", "", s)
    s = re.sub(r"[^0-9A-Za-z가-힣]+", "-", s).strip("-").lower()
    return s or "x"


def uid(s):
    """엔티티 id 용 슬러그: 괄호 안 변형 표식([홈브류], [Playtest], [물리], (G), +)을 버리지 않고 접미사로 남겨 코어/변형판이 같은 id 를 갖지 않게 한다."""
    tags = re.findall(r"\[(.*?)\]|\((.*?)\)", s)
    base = re.sub(r"\[.*?\]|\(.*?\)", "", s)
    plus = base.count("+")
    out = slug(base)
    for a_, b_ in tags:
        out += "-" + slug(a_ or b_)
    if plus:
        out += "-plus"
    return out


def dedupe_ids(recs):
    """같은 id 가 남으면(시트에 같은 이름이 두 번) 두 번째부터 -2, -3 을 붙인다."""
    seen = {}
    for r in recs:
        n = seen.get(r["id"], 0) + 1
        seen[r["id"]] = n
        if n > 1:
            r["id"] = f"{r['id']}-{n}"
    return recs


def split_name(s):
    m = ENG_RE.match(s.strip())
    return (m.group(1).strip(), m.group(2).strip()) if m else (s.strip(), None)


# ---------- 블록 파서 (PTK의 핵심) ----------
def block_source(lines, start):
    """Preserve the complete block, including field-only labels, bullets and tables."""
    end = start + 1
    while end < len(lines):
        line = lines[end].rstrip()
        named = match_name(line)
        field = FIELD_RE.match(line)
        label = norm_label(field.group(1)) if field else ""
        field_only = bool(field and (label in FIELD_LABELS or "효과" in label or re.fullmatch(r"(?:모든 랭크|랭크\s*\d+) 전제조건", label)))
        if H_RE.match(line) or MANEUVER_RE.match(line):
            break
        if named and not field_only:
            break
        # A new inline definition starts another entity, not a continuation.
        if DEF_RE.match(line) and not field_only:
            break
        if label == "기술이름":
            break
        end += 1
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    return "\n".join(lines[start:end]), end


def parse_blocks(lines):
    """본문 줄 목록 -> 엔티티 블록 목록. 헤딩 하나 아래 재주 20개 같은 구조를 읽는다."""
    blocks, i, n = [], 0, len(lines)
    while i < n:
        ln = lines[i].rstrip()
        m_man = MANEUVER_RE.match(ln)
        m_name = match_name(ln) if not m_man else None
        m_def = DEF_RE.match(ln)
        mf0 = FIELD_RE.match(ln)
        # 무기 기술: '**기술이름**: 백스윙' 으로 시작하는 필드 묶음 (굵은 이름 줄이 없음)
        if mf0 and norm_label(mf0.group(1)) == "기술이름":
            k, e = split_name(VALUE_JUNK_RE.sub("", mf0.group(2)).strip())
            blk = {"kind": "weapon_move", "name": k, "eng": e, "line": i, "tags": [], "fields": {}, "freq": None, "extra": []}
            j = i + 1
            while j < n and lines[j].strip() and not H_RE.match(lines[j]):
                mf = FIELD_RE.match(lines[j].rstrip())
                if not mf or norm_label(mf.group(1)) == "기술이름":
                    break
                lab = norm_label(mf.group(1))
                if lab in FIELD_LABELS:
                    blk["fields"][FIELD_LABELS[lab]] = VALUE_JUNK_RE.sub("", mf.group(2)).strip()
                    if lab == "기본 데미지":
                        mdb = re.search(r"\((\d+)\)", mf.group(1))
                        blk["fields"]["db"] = int(mdb.group(1)) if mdb else None
                else:
                    blk["extra"].append(lines[j].rstrip())
                j += 1
            blocks.append(blk)
            i = j
            continue
        if m_def and not m_man:
            name = m_def.group(1) or m_def.group(3)
            body = m_def.group(2) or m_def.group(4)
            label = name.strip()
            if norm_label(label) in FIELD_LABELS or label.startswith(SIDEBAR_LABELS) or label.startswith("»"):
                i += 1
                continue
            k, e = split_name(label)
            text = [body.strip()]
            j = i + 1          # 같은 문단의 이어지는 줄(번역본은 문장 중간에 줄바꿈이 있음)과 » 소항목을 흡수
            while j < n and lines[j].strip() and not (match_name(lines[j]) or DEF_RE.match(lines[j]) or FIELD_RE.match(lines[j]) or H_RE.match(lines[j]) or lines[j].startswith("<table>")):
                text.append(lines[j].strip())
                j += 1
            blocks.append({"kind": "noise" if k in NOISE_LABELS else "definition", "name": k, "eng": e, "line": i, "text": "\n".join(text), "fields": {}})
            i = j
            continue
        if m_man or (m_name and not m_name.group(1).strip().endswith((":", "：")) and not m_name.group(1).strip().startswith(SIDEBAR_LABELS)):
            raw = (m_man or m_name).group(1).strip()
            k, e = split_name(raw)
            blk = {"kind": "maneuver" if m_man else "block", "name": k, "eng": e, "line": i, "tags": [], "fields": {}, "freq": None, "extra": []}
            j = i + 1
            while j < n and not match_name(lines[j]) and not MANEUVER_RE.match(lines[j]) and not H_RE.match(lines[j]):
                if not lines[j].strip():
                    # A blank line before an explicit field/frequency is formatting, not a new entity.
                    k = j + 1
                    while k < n and not lines[k].strip():
                        k += 1
                    following = FIELD_RE.match(lines[k]) if k < n else None
                    if k < n and (FREQ_RE.match(lines[k]) or (following and norm_label(following.group(1)) in FIELD_LABELS)):
                        j = k
                    else:
                        break
                l2 = lines[j].rstrip()
                mt = TAG_RE.match(l2)
                mf = FIELD_RE.match(l2)
                mq = FREQ_RE.match(l2)
                if mt and not mf:
                    blk["tags"] += re.findall(r"\[([^\]]+)\]", l2)
                elif mf and norm_label(mf.group(1)) in FIELD_LABELS:
                    blk["fields"][FIELD_LABELS[norm_label(mf.group(1))]] = VALUE_JUNK_RE.sub("", mf.group(2)).strip()
                elif mq and blk["freq"] is None:
                    blk["freq"] = l2
                elif l2.startswith("<table>"):
                    while j < n and not lines[j].startswith("</table>"):
                        j += 1
                else:
                    blk["extra"].append(l2)
                j += 1
            if blk["fields"] or blk["freq"]:
                blocks.append(blk)
                i = j
                continue
        i += 1
    return blocks


def classify_block(b, chapter, heading_path):
    hp = " / ".join(heading_path)
    if b["kind"] in ("maneuver", "noise", "weapon_move"):
        return b["kind"]
    if b["kind"] == "block":
        f = b["fields"]
        if "cost" in f or "포켓엣지" in hp:
            return "poke_edge"
        if "reagent" in f:
            return "crafted_item"
        if chapter == "ch03-skills-edges-feats" and "엣지" in " / ".join(heading_path[1:]) and "prereq" in f and "effect" in f and not b["freq"]:
            return "edge"
        if "prereq" in f or b["freq"] or b["tags"]:
            return "feat"
        if "ac" in f or "range" in f:
            return "maneuver"
        if chapter == "supp-blessings":
            return "gift"
        return "block"
    # definition
    if "데모" in hp or "시범" in hp:
        return "noise"                      # 전투/콘테스트 데모의 대화 화자 라벨
    if "상태이상" in hp or "상태 이상" in hp:
        return "condition"
    if "특수 재능" in hp or ("재능" in hp and chapter == "ch10-index-reference"):
        return "capability"
    if "콘테스트 효과" in hp:
        return "contest_effect"
    if "키워드" in hp:
        return "keyword"
    if "행동 타입" in hp:
        return "action_type"
    if chapter == "ch09-equipment":
        return "item"
    if "스탯" in hp and chapter == "ch07-combat":
        return "stat"
    if "날씨" in hp:
        return "weather"
    if chapter == "ch11-running-the-game" and ("샘플" in hp or "보스" in hp or "NPC" in hp or "체육관" in hp):
        return "noise"                      # 샘플 NPC/보스 스탯 필드
    return "definition"


# ---------- outline ----------
def parse_headings(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    nodes = []
    for i, ln in enumerate(lines, 1):
        if EMPTY_H_RE.match(ln):
            lines[i - 1] = ""          # 페이지 나눔 헤딩은 본문에서 지움
            continue
        m = H_RE.match(ln)
        if m:
            title = re.sub(r"\[img\]", "", m.group(2)).strip()
            if len(title) > 90:        # '## 텔레파시(Telepath): 본문...' 처럼 본문이 헤딩으로 잘못 들어간 경우
                head, _, rest = title.partition(":")
                lines[i - 1] = "**" + head.strip() + ":** " + rest.strip()
                continue
            nodes.append({"level": len(m.group(1)), "title": title, "line": i})
    for k, n in enumerate(nodes):
        n["end"] = nodes[k + 1]["line"] - 1 if k + 1 < len(nodes) else len(lines)
    return lines, nodes


def body_stats(lines, start, end, chapter, path):
    seg = lines[start:end]
    text = "\n".join(seg)
    tables, sidebars = [], 0
    k = 0
    while k < len(seg):
        if seg[k].startswith("<table>"):
            rows = []
            k += 1
            while k < len(seg) and not seg[k].startswith("</table>"):
                rows.append(seg[k])
                k += 1
            cells = max((r.count("|") - 1 for r in rows), default=0)
            if len(rows) == 1 and cells <= 1:
                sidebars += 1                      # 한 칸짜리 표 = 사이드바/콜아웃
            else:
                tables.append({"rows": len(rows), "cols": cells})
        k += 1
    blocks = parse_blocks(seg)
    kinds = Counter(classify_block(b, chapter, path) for b in blocks)
    kinds.pop("noise", None)
    return {
        "words": len(re.findall(r"[0-9A-Za-z가-힣]+", text)),
        "tables": len(tables), "sidebars": sidebars,
        "steps": sum(1 for l in seg if STEP_RE.match(l)),
        "bullets": sum(1 for l in seg if BULLET_RE.match(l)),
        "field_lines": sum(1 for l in seg if FIELD_RE.match(l) and norm_label(FIELD_RE.match(l).group(1)) in FIELD_LABELS),
        "blocks": dict(kinds),
        "xrefs": [next(g for g in m if g) for m in XREF_RE.findall(text)],
        "xref_mentions": text.count("참조"),
        "typeline": [TYPELINE_RE.match(l).group(1) for l in seg[:6] if TYPELINE_RE.match(l)],
        "imgs": text.count("[img]"),
    }


def classify(node, chapter, children):
    st, title, lvl = node["stats"], node["title"], node["level"]
    path = " / ".join(node["path"])
    bl = st["blocks"]
    n_ent = sum(bl.values())
    if lvl == 1:
        return "chapter"
    if chapter == "ch04-trainer-classes" and lvl == 3 and any(t.startswith(("연관 스킬", "패시브", "액티브", "여행", "트레이너 전투")) for t in st["typeline"]):
        return "entity:class"
    if chapter == "ch03-skills-edges-feats" and lvl == 3 and node["parent_title"] == "스킬":
        return "entity:skill"
    if chapter == "ch02-character-creation" and lvl == 3 and node["parent_title"] == "트레이너 아키타입 제작":
        return "entity:archetype"
    if chapter == "ch11-running-the-game" and node["parent_title"] == "포켓몬 서식지 리스트":
        return "entity:habitat"
    if n_ent >= 2:
        top = max(bl, key=bl.get)
        return f"list:{top}"
    if n_ent == 1:
        return "entity:" + next(iter(bl))
    if st["steps"] >= 2 or re.match(r"^스텝 \d", title):
        return "procedure"
    if st["tables"] and st["words"] < 400:
        return "table"
    if children and st["words"] < 60:
        return "container"
    if st["field_lines"] or st["bullets"] >= 3:
        return "rule:with_fields"
    if "데모" in path or "시범" in path or "예제" in title or "샘플" in title:
        return "example"
    return "rule:prose"


def build_outline(md_dir, out_dir):
    chapters, flat, cls_counter = [], [], Counter()
    for ch in CHAPTER_ORDER:
        path = os.path.join(md_dir, ch + ".md")
        if not os.path.exists(path):
            continue
        lines, nodes = parse_headings(path)
        stack = []
        for n in nodes:
            while stack and stack[-1]["level"] >= n["level"]:
                stack.pop()
            n["parent_title"] = stack[-1]["title"] if stack else None
            n["path"] = [s["title"] for s in stack] + [n["title"]]
            n["id"] = f"{ch}/" + "/".join(slug(p) for p in n["path"][1:]) if len(n["path"]) > 1 else ch
            stack.append(n)
        kids = defaultdict(list)
        for n in nodes:
            if n["parent_title"] is not None:
                kids[tuple(n["path"][:-1])].append(n)
        for n in nodes:
            n["stats"] = body_stats(lines, n["line"], n["end"], ch, n["path"])
            n["children_count"] = len(kids.get(tuple(n["path"]), []))
            n["unit_type"] = classify(n, ch, n["children_count"])
            cls_counter[n["unit_type"]] += 1
            flat.append({"chapter": ch, **{k: n[k] for k in ("id", "level", "title", "line", "end", "unit_type", "children_count")}, **n["stats"]})
        ent_total = Counter()
        for n in nodes:
            ent_total.update(n["stats"]["blocks"])
        chapters.append({
            "chapter": ch, "file": ch + ".md", "lines": len(lines), "headings": len(nodes),
            "words": sum(n["stats"]["words"] for n in nodes),
            "by_level": dict(Counter(n["level"] for n in nodes)),
            "unit_types": dict(Counter(n["unit_type"] for n in nodes)),
            "entity_blocks": dict(ent_total),
            "tables": sum(n["stats"]["tables"] for n in nodes), "sidebars": sum(n["stats"]["sidebars"] for n in nodes),
            "xrefs": sum(len(n["stats"]["xrefs"]) for n in nodes),
            "xref_mentions": sum(n["stats"]["xref_mentions"] for n in nodes),
        })
    os.makedirs(out_dir, exist_ok=True)
    json.dump({"source": "PTK 코어 룰북 (PTU 1.05 한국어 번역, 포켓몬스터 TRPG 한국 지부) + 서플리먼트 2종", "chapters": chapters, "nodes": flat},
              open(os.path.join(out_dir, "structure-map.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    md = ["# PTK 코어 룰북 구조 통계 (자동 생성)", "", "## 챕터별 헤딩 수", "",
          "| 챕터 | 줄 | 어절 | 헤딩 | h2 | h3 | h4 | 표 | 사이드바 | 엔티티 블록 | 교차참조(페이지/챕터) | '참조' 언급 |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in chapters:
        bl = c["by_level"]
        md.append(f"| {c['chapter']} | {c['lines']} | {c['words']} | {c['headings']} | {bl.get(2, 0)} | {bl.get(3, 0)} | {bl.get(4, 0)} | {c['tables']} | {c['sidebars']} | {sum(c['entity_blocks'].values())} | {c['xrefs']} | {c['xref_mentions']} |")
    md += ["", "## 자동 분류된 룰 단위 유형 (헤딩 노드 기준, 전체)", "", "| 유형 | 개수 |", "|---|---|"]
    for k, v in cls_counter.most_common():
        md.append(f"| {k} | {v} |")
    md += ["", "## 엔티티 블록 (헤딩 아래 굵은 이름+필드 블록) 챕터별 수", ""]
    for c in chapters:
        if c["entity_blocks"]:
            md.append(f"- **{c['chapter']}**: " + ", ".join(f"{k} {v}" for k, v in sorted(c["entity_blocks"].items(), key=lambda x: -x[1])))
    md += ["", "## 챕터별 헤딩 유형 분포", ""]
    for c in chapters:
        md.append(f"- **{c['chapter']}**: " + ", ".join(f"{k} {v}" for k, v in sorted(c["unit_types"].items(), key=lambda x: -x[1])))
    open(os.path.join(out_dir, "stats.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    print("\n".join(md))


# ---------- entities ----------
def iter_sections(md_dir):
    """(chapter, heading_path, start_line, body_lines) 전부."""
    for ch in CHAPTER_ORDER:
        path = os.path.join(md_dir, ch + ".md")
        if not os.path.exists(path):
            continue
        lines, nodes = parse_headings(path)
        stack = []
        for n in nodes:
            while stack and stack[-1]["level"] >= n["level"]:
                stack.pop()
            n["path"] = [s["title"] for s in stack] + [n["title"]]
            stack.append(n)
            yield ch, n["path"], n["line"], lines[n["line"]:n["end"]]


def fainted_definition_source(lines, block):
    """Preserve the separated recovery paragraph up to the next definition.

    Reviewed source boundary: ch07 Fainted includes the following plain-text
    recovery paragraph. Other definitions retain their existing boundaries.
    """
    text = block["text"]
    j = block["line"] + len(text.splitlines())
    extra = []
    end = j
    while j < len(lines):
        line = lines[j]
        if match_name(line) or DEF_RE.match(line) or FIELD_RE.match(line) or H_RE.match(line) or line.startswith("<table>"):
            break
        extra.append(line.rstrip())
        if line.strip():
            end = j + 1
        j += 1
    return (text + "\n" + "\n".join(extra)).rstrip(), end


def extract_blocks(md_dir):
    out = defaultdict(list)
    for ch, path, start, body in iter_sections(md_dir):
        for b in parse_blocks(body):
            kind = classify_block(b, ch, path)
            rec = {"id": f"{kind}/{slug(b['name'])}", "name": b["name"], "eng": b.get("eng"), "chapter": ch,
                   "section": " / ".join(path), "line": start + b["line"] + 1}
            if b["kind"] in ("definition", "noise"):
                rec["text"] = b["text"]
                if kind == "condition" and ch == "ch07-combat" and b["name"] == "기절":
                    rec["text"], end = fainted_definition_source(body, b)
                    rec["end_line"] = start + end
            else:
                rec.update({"tags": b.get("tags", []), "frequency": b.get("freq"), **b["fields"]})
                if b["extra"]:
                    rec["extra"] = b["extra"]
            if b["kind"] not in ("definition", "noise"):
                rec["text"], end = block_source(body, b["line"])
                rec["end_line"] = start + end
            out[kind].append(rec)
    return out


def extract_classes(md_dir):
    classes = []
    for ch, path, start, body in iter_sections(md_dir):
        if ch != "ch04-trainer-classes" or len(path) != 3:
            continue
        tl = [TYPELINE_RE.match(l).group(1) for l in body[:8] if TYPELINE_RE.match(l)]
        if not any(t.startswith("연관 스킬") for t in tl):
            continue
        k, e = split_name(path[-1])
        rec = {"id": "class/" + slug(k), "name": k, "eng": e, "category": path[1], "line": start}
        for t in tl:
            if ":" in t:
                a, b = t.split(":", 1)
                rec[a.strip()] = b.strip()
        cf = next((l for l in body if l.startswith("| **") and "[클래스]" in l), None)
        rec["class_feat_table"] = bool(cf)
        if cf:
            m = re.search(r"\*\*전제조건:\*\*\s*(.+?)\s*(?:항상|\d+ AP[^*]*|임의[^*]*|장면[^*]*)\s*\*\*", cf)
            rec["class_prereq"] = m.group(1) if m else None
        rec["features"] = [b["name"] for b in parse_blocks(body) if b["kind"] == "block"]
        classes.append(rec)
    return classes


# ---------- 데이터베이스 시트 (C층) ----------
STAT_RE = re.compile(r"(공격|방어|특수공격|특수방어|특공|특방|스피드|명중|회피)\s*(?:의\s*)?전투단계(?:를|가|은|는)?\s*([+\-−]\s*\d+)")
STATUS_WORDS = ["화상", "얼음", "마비", "맹독", "중독", "독", "잠듦", "혼란", "풀죽음", "헤롱헤롱", "저주", "난동", "억압", "사슬묶기", "취약", "넘어짐", "둔화", "구속", "수렁", "실명", "악몽"]
STATUS_RE = re.compile("(" + "|".join(STATUS_WORDS) + r")\s*(?:상태|이|에|를|을|으로|가|됩니다|시킵니다)")
CRIT_RE = re.compile(r"(\d+)\s*(?:이상|\+)\s*(?:이\s*나왔을\s*때|에서)?\s*(?:치명타|추가 효과)")
ONROLL_RE = re.compile(r"명중\s*굴림(?:의 값)?이\s*(\d+)\s*(?:이상|\+)")
HEAL_RE = re.compile(r"(?:체력|HP)(?:을|를)?\s*(?:최대 체력의\s*)?([0-9/]+)\s*(?:만큼\s*)?회복")
WEATHER_RE = re.compile(r"(쾌청|비바라기|싸라기눈|모래바람)")
KEYWORD_RE = re.compile(r"(파동|나무열매|축복|코트|대시|이단타격|환경|일격|탈진|친화|오단타격|지면통과|함정|환영|방해|통과|맹세|가루|우선|밀기|반응|반동|준비|방패|강타|사회적|소리|정신급증|발동조건|조이기|날씨|무게 등급|베기|가변|바람)")


EXTRA_MECH = [
    ("never_miss", re.compile(r"빗나가지\s*않")),
    ("evasion", re.compile(r"[+\-]\s*\d+\s*(?:의\s*)?(?:물리|특수|속도)?\s*회피")),
    ("bonus_damage", re.compile(r"\+\s*\d+\s*(?:의\s*)?(?:데미지|피해)")),
    ("conditional_db", re.compile(r"기본\s*(?:데미지|피해량?)(?:는|은|가|이|을|를)?\s*(?:대신\s*)?\d+")),
    ("heal", re.compile(r"체력(?:을|를)?\s*(?:다시\s*)?(?:얻|회복)|회복합니다|회복시킵니다")),
    ("tick_hp", re.compile(r"소량의\s*체력|최대\s*체력의\s*1/\d+")),
    ("swap", re.compile(r"서로\s*바꾸|서로\s*바뀝|교체합니다|교환")),
    ("ability_change", re.compile(r"특성(?:을|이)\s*(?:얻|무효|잃|바꾸|복사)")),
    ("push_move", re.compile(r"밀어|밀려|밀쳐|순간이동|이동시킵니다|끌어")),
    ("initiative", re.compile(r"이니셔티브")),
    ("temp_hp", re.compile(r"임시\s*체력")),
    ("hazard_terrain", re.compile(r"함정|지형|칸")),
]


def move_mech(eff, rng=""):
    mech = {}
    for s, v in STAT_RE.findall(eff):
        mech.setdefault("stage_changes", []).append({"stat": s, "delta": int(v.replace("−", "-").replace(" ", ""))})
    st = STATUS_RE.findall(eff)
    if st:
        mech["status"] = sorted(set(st))
    m = ONROLL_RE.search(eff) or CRIT_RE.search(eff)
    if m:
        mech["on_roll"] = int(m.group(1))
    if "치명타" in eff:
        mech["crit_related"] = True
    w = WEATHER_RE.search(eff)
    if w:
        mech["weather"] = w.group(1)
    for key, rx in EXTRA_MECH:
        if rx.search(eff):
            mech[key] = True
    return mech


def parse_moves(csv_path):
    rows = list(csv.reader(open(csv_path, encoding="utf-8", newline="")))
    hdr_i = next(i for i, r in enumerate(rows) if r and r[0].strip() == "이름")
    recs, fails = [], []
    section = None            # 시트 뒤쪽의 '[홈브류]', 'Z기술', '다이맥스' 구역 표식
    for row_number,r in enumerate(rows[hdr_i + 1:],hdr_i+2):
        if not r or not r[0].strip():
            continue
        name = r[0].strip()
        db, freq, ac, rng, eff, contest, cls, typ = (r[i].strip() if i < len(r) else "" for i in (3, 4, 5, 6, 7, 8, 9, 10))
        eng = r[22].strip() if len(r) > 22 else None
        if eff == "--":
            eff = ""
        if not typ and not cls and not rng:          # 구역 표식 행
            section = name
            fails.append({"name": name, "reason": "section_marker"})
            continue
        rec = {"id": "move/" + uid(name), "name": name, "eng": eng, "type": typ, "class": cls,
               "damage_base": int(db) if db.isdigit() else None, "ac": int(ac) if ac.isdigit() else None,
               "frequency": freq, "range": rng, "effect": eff, "contest": contest,
               "homebrew": bool(section) or "홈브류" in name or "Z기술" in rng}
        rec["_source"] = source_record(csv_path,row_number,{'name': 1, 'damage_base': 4, 'frequency': 5, 'ac': 6, 'range': 7, 'effect': 8, 'contest': 9, 'class': 10, 'type': 11, 'eng': 23})
        if section:
            rec["sheet_section"] = section
        # The printed Athlete table explicitly learns Bind. Its exact saved
        # CSV definition is a Static Move, not an inserted combat maneuver.
        static_move = (name, eng, cls, freq, typ, db, ac, rng) == (
            "조이기", "Bind", "항상", "항상", "노말", "--", "--", "--")
        if typ in ("", "--") and cls not in ("물리", "특수", "변화") or (cls == "항상" and not static_move) or typ == "--":
            # 기술이 아니라 전투 동작·무기 숙련·키워드 규칙이 시트에 끼어 있는 행
            rec["reason"] = "inserted_other_kind"
            fails.append(rec)
            continue
        if not typ and cls in ("물리", "특수", "변화"):
            rec["reason"] = "inserted_other_kind"   # 타입 없는 변화기 = 전투 동작(술수, 밀기 등)
            fails.append(rec)
            continue
        mech = move_mech(eff, rng)
        if cls in ("물리", "특수") and rec["damage_base"] is None:
            # Fling's saved sheet row delegates its DB to the printed Fling
            # keyword table.  Preserve it as a variable-DB move so learned
            # move projections can point at a real catalog identity; this
            # does not claim that the separate held-item DB table is mechanized.
            if name == "내던지기" and eng == "Fling" and db == "효과 확인":
                rec["damage_base"] = "variable"
                mech["db_variable"] = True
                mech["held_item_damage"] = True
            elif re.search(r"기본\s*(?:데미지|피해)|데미지|피해|체력", eff):
                rec["damage_base"] = "variable"
                mech["db_variable"] = True
            else:
                rec["reason"] = "data_error"
                fails.append(rec)
                continue
        if not cls:
            rec["reason"] = "data_error"
            fails.append(rec)
            continue
        kw = KEYWORD_RE.findall(rng + " " + eff)
        if kw:
            rec["keywords"] = sorted(set(kw))
        rec["mech_auto"] = mech
        recs.append(rec)
    return recs, fails


def parse_abilities(csv_path):
    rows = list(csv.reader(open(csv_path, encoding="utf-8", newline="")))
    recs, fails = [], []
    unresolved_copies = {}
    for row_number,r in enumerate(rows[1:],2):
        if not r or not r[0].strip():
            continue
        name, freq, eff, trig, tgt, kw, eff2, eng = (r[i].strip() if i < len(r) else "" for i in range(8))
        # Preserve the original secondary column, including non-redundant clauses.
        original_eff = eff
        redundant = re.sub(r"\s+", "", " ".join([eff, trig, tgt, kw]))
        additions = [line.strip() for line in eff2.splitlines()
                     if line.strip() and re.sub(r"\s+", "", line) not in redundant
                     and not re.match(r"^(발동조건|발동 조건|대상|키워드)\s*[-:：]", line.strip())]
        if additions:
            eff += "\n" + "\n".join(additions)
        rec = {"id": "ability/" + uid(name), "name": name, "eng": eng or None, "frequency": freq, "effect": eff,
               "trigger": trig or None, "target": tgt or None, "keyword": kw or None,
               "effect_primary": original_eff, "effect2": eff2, "effect_additions": additions}
        rec["_source"] = source_record(csv_path,row_number,{'name': 1, 'frequency': 2, 'effect_primary': 3, 'trigger': 4, 'target': 5, 'keyword': 6, 'effect2': 7, 'eng': 8})
        fm = re.match(r"^(항상|장면(?:\s*x\s*\d+)?|일일(?:\s*x\s*\d+)?|하루(?:\s*x\s*\d+)?|임의|턴\s*1회|매 턴)\s*(?:[-–]\s*(.+))?$", freq)
        if fm:
            rec["freq_kind"], rec["action"] = fm.group(1), fm.group(2)
        mech = move_mech(eff)
        if re.search(r"면역", eff):
            mech["immunity"] = True
        rec["mech_auto"] = mech
        if not eff:
            rec["reason"] = "missing_effect_body"
            fails.append(rec)
            continue
        if not fm:
            # A source definition still exists when its activation needs the
            # ability's own text. Never infer At-Will/Always from this marker.
            rec["frequency_parse"] = {"status": "requires_rule_specific_interpretation", "raw": freq}
            action = re.match(r"^(?:특수|발동조건)\s*[-–]\s*(.+)$", freq)
            if action:
                rec["action"] = action.group(1)
            # Recovering identical failed rows must not introduce an ambiguous
            # second name identity. Existing regular-frequency IDs are unchanged.
            signature = tuple(r)
            if signature in unresolved_copies:
                unresolved_copies[signature].setdefault("_source_duplicates", []).append(rec["_source"])
                continue
            unresolved_copies[signature] = rec
        recs.append(rec)
    return recs, fails


def pokemon_type_values(name, raw):
    """Exact source typo repair; retain original cells and its interpretation."""
    values = list(raw)
    receipt = None
    if name == "블레이범 히스이" and values == ["불", "고스트"]:
        values = ["불꽃", "고스트"]
        receipt = {"kind": "source_typo_normalization", "raw": list(raw), "normalized": list(values),
                   "reason": "불 is the shortened Fire label, not an additional type; ch05:21 names 불꽃.",
                   "basis": ["input/ch05-pokemon.md:21", "input/db/nature-type.csv:48"],
                   "source_columns": [32, 33]}
    return values, receipt


def parse_pokemon(csv_path):
    rows = list(csv.reader(open(csv_path, encoding="utf-8", newline="")))
    recs, fails, groups, cur = [], [], [], None
    header = next(i for i, r in enumerate(rows) if r and "포켓몬 이름" in r[0])
    for row_number,r in enumerate(rows[header + 1:],header+2):
        if not r or not r[0].strip():
            continue
        g = lambda i: r[i].strip() if i < len(r) else ""
        stats = [g(i) for i in range(1, 7)]
        if not any(stats) or (not any(stats[1:]) and stats[0] in (g(0), "MEGAS")):  # 원본 구역 라벨
            cur = g(0)
            groups.append(cur)
            continue
        rec = {"id": "pokemon/" + slug(g(0)), "name": g(0), "eng": g(33) or None, "dex": g(36) or None,
               "base_stats": dict(zip(["hp", "atk", "def", "spa", "spd", "spe"], [int(x) if x.lstrip("-").isdigit() else None for x in stats])),
               "types": [t for t in (g(31), g(32)) if t and t not in ("None", "-")],
               "movement": {k: (int(g(i)) if g(i).lstrip("-").isdigit() else None) for k, i in zip(["land", "sky", "swim", "levitate", "burrow", "high_jump", "long_jump", "power"], range(9, 17))},
               "naturewalk": g(17) if g(17) not in ("", "-") else None,
               "capabilities": [g(i) for i in range(18, 27) if g(i) and g(i) != "-"],
               "size": g(27), "weight_class": int(g(28)) if g(28).isdigit() else None,
               "egg_groups": [x for x in (g(29), g(30)) if x and x != "-"], "group": cur}
        rec["_source"] = source_record(csv_path,row_number,{'name': 1, 'eng': 34, 'dex': 37})
        rec["types"], type_note = pokemon_type_values(rec["name"], rec["types"])
        if type_note is not None:
            rec["types_raw"] = type_note["raw"]
            rec["_type_normalization"] = dict(type_note, source=source_record(csv_path,row_number,{"type_1":32,"type_2":33}))
        ok = all(v is not None for v in rec["base_stats"].values()) and rec["types"] and rec["size"]
        (recs if ok else fails).append(rec)
    return recs, fails, groups


def parse_simple_sheet(csv_path, kind, cols, name_col=0):
    rows = list(csv.reader(open(csv_path, encoding="utf-8", newline="")))
    recs, groups, cur = [], 0, None
    for row_number,r in enumerate(rows[1:],2):
        if not r or not any(c.strip() for c in r):
            continue
        if not r[name_col].strip():      # 이름 없는 행 = 그룹 헤더
            cur = next((c.strip() for c in r if c.strip()), cur)
            groups += 1
            continue
        rec = {"id": f"{kind}/{slug(r[name_col])}", "name": r[name_col].strip(), "group": cur}
        for i, c in cols.items():
            if i < len(r) and r[i].strip():
                rec[c] = r[i].strip()
        rec["_source"] = source_record(csv_path,row_number,{"name": name_col+1, **{field:col+1 for col,field in cols.items()}})
        recs.append(rec)
    return recs, groups


def build_entities(md_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    blocks = extract_blocks(md_dir)
    classes = extract_classes(md_dir)
    report = ["# PTK 엔티티 자동 추출 커버리지", "", "## 룰북 본문(블록 단위)", "",
              "블록 = 헤딩 아래의 `**이름(Eng)**` 줄 + `**라벨:**` 필드 줄 묶음, 또는 `**이름(Eng):** 본문` 한 줄 정의.", "",
              "| 종류 | 추출 수 | 필드 보유 수 | 비고 |", "|---|---|---|---|"]
    noise = blocks.pop("noise", [])
    for kind, recs in sorted(blocks.items(), key=lambda x: -len(x[1])):
        json.dump(recs, open(os.path.join(out_dir, f"{kind}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        core = sum(1 for r in recs if r.get("chapter") in CORE_CHAPTERS)
        eng = sum(1 for r in recs if r.get("eng"))
        if kind in ("feat", "edge", "maneuver", "poke_edge", "gift", "crafted_item", "block"):
            have = {f: sum(1 for r in recs if r.get(f)) for f in ("prereq", "trigger", "effect", "target", "frequency", "cost", "reagent", "ac", "range")}
            report.append(f"| {kind} | {len(recs)} (코어 {core}) | " + ", ".join(f"{k} {v}" for k, v in have.items() if v) + f" | 영문명 {eng} |")
        elif kind == "weapon_move":
            have = {f: sum(1 for r in recs if r.get(f)) for f in ("type", "frequency", "ac", "db", "class", "range", "effect", "restriction")}
            report.append(f"| {kind} | {len(recs)} (코어 {core}) | " + ", ".join(f"{k} {v}" for k, v in have.items() if v) + f" | 영문명 {eng}. 굵은 이름 줄 없이 '기술이름:' 필드로 시작하는 별도 서식 |")
        else:
            report.append(f"| {kind} | {len(recs)} (코어 {core}) | 한 줄 정의 | 영문명 {eng} |")
    json.dump(noise, open(os.path.join(out_dir, "_noise.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    report.append(f"| (noise: 아키타입 소제목·샘플 NPC 필드·데모 대화) | {len(noise)} | 제외 | _noise.json |")
    json.dump(classes, open(os.path.join(out_dir, "classes.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    report.append(f"| class (헤딩+타입라인) | {len(classes)} | 클래스 재주 표 {sum(1 for c in classes if c['class_feat_table'])}, 평균 재주 {sum(len(c['features']) for c in classes)/max(1,len(classes)):.1f}개 | 영문명 보유 {sum(1 for c in classes if c['eng'])} |")

    db = os.path.join(md_dir, "db")
    report += ["", "## 데이터베이스 시트 (C층: 대량 엔티티)", "", "| 시트 | 파싱 성공 | 실패 | 비고 |", "|---|---|---|---|"]
    moves, mf = parse_moves(os.path.join(db, "moves.csv"))
    dedupe_ids(moves)
    json.dump(moves, open(os.path.join(out_dir, "moves.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(mf, open(os.path.join(out_dir, "moves-failed.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    core_moves = [m for m in moves if not m["homebrew"]]
    dmg = [m for m in core_moves if m["class"] in ("물리", "특수")]
    reasons = Counter(f.get("reason") for f in mf)
    report.append(f"| 기술(moves) | {len(moves)} (코어 {len(core_moves)}, 홈브류 {len(moves)-len(core_moves)}) | {len(mf)} = " + ", ".join(f"{k} {v}" for k, v in reasons.items()) +
                  f" | 헤더 열 라벨이 밀려 있음(DB·AC 열에 라벨 없음). 코어 물리/특수 {len(dmg)}, 변화 {len(core_moves)-len(dmg)}, DB 가변 {sum(1 for m in dmg if m['damage_base']=='variable')} |")
    abil, af = parse_abilities(os.path.join(db, "abilities.csv"))
    dedupe_ids(abil)
    json.dump(abil, open(os.path.join(out_dir, "abilities.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(af, open(os.path.join(out_dir, "abilities-failed.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    report.append(f"| 특성(abilities) | {len(abil)} | {len(af)} | 이름·효과 정의 보존. 특수/발동조건 빈도는 원문별 해석 미확정으로 표시하며 동일 복구 사본은 출처 좌표를 함께 보존 |")
    poke, pf, pgroups = parse_pokemon(os.path.join(db, "pokemon.csv"))
    json.dump(poke, open(os.path.join(out_dir, "pokemon.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(pf, open(os.path.join(out_dir, "pokemon-failed.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    report.append(f"| 포켓몬 종(pokemon) | {len(poke)} | {len(pf)} | 6 스탯+타입+크기 기준. 구역 헤더 행 {len(pgroups)}개({', '.join(pgroups)}) |")
    for fname, kind, cols in [("feats.csv", "feat_sheet", {1: "tags", 2: "prereq", 3: "frequency", 4: "effect"}),
                              ("edges.csv", "edge_sheet", {1: "prereq", 2: "effect"}),
                              ("poke-edges.csv", "poke_edge", {1: "effect", 2: "prereq", 3: "cost"}),
                              ("tm.csv", "tm", {1: "price", 2: "category"})]:
        recs, groups = parse_simple_sheet(os.path.join(db, fname), kind, cols)
        json.dump(recs, open(os.path.join(out_dir, f"{kind}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        report.append(f"| {fname} | {len(recs)} | 0 | 그룹 헤더 행 {groups}개 |")

    report += ["", "## 본문 메커닉 자동 식별 (코어 기술 효과 텍스트 기준)", "", "| 항목 | 식별 수 | 모수 |", "|---|---|---|"]

    def cnt(key, pool):
        return sum(1 for m in pool if m["mech_auto"].get(key))
    M = core_moves
    with_eff = [m for m in M if m["effect"]]
    labels = [("stage_changes", "전투단계 변화(스탯·수치까지)"), ("status", "상태이상 부여/언급"), ("on_roll", "굴림값 조건(N+ 추가효과/치명타)"),
              ("crit_related", "치명타 관련"), ("weather", "날씨"), ("never_miss", "빗나가지 않음"), ("evasion", "회피 수정"),
              ("bonus_damage", "추가 데미지 +N"), ("conditional_db", "조건부 기본 데미지"), ("heal", "회복"), ("tick_hp", "소량 체력/최대 체력 비율"),
              ("swap", "교환/교체"), ("ability_change", "특성 변경"), ("push_move", "밀기/이동/순간이동"), ("initiative", "이니셔티브"),
              ("temp_hp", "임시 체력"), ("hazard_terrain", "함정/지형/칸"), ("db_variable", "DB 가변(본문 참조)")]
    report += [f"| 기본 데미지(DB) 숫자 보유 | {sum(1 for m in dmg if isinstance(m['damage_base'], int))} | 물리/특수 {len(dmg)} |",
               f"| AC 보유 | {sum(1 for m in M if m['ac'] is not None)} | 전체 {len(M)} |",
               f"| 효과 텍스트 없음(순수 데미지, 헤더만으로 완결) | {len(M) - len(with_eff)} | {len(M)} |",
               f"| 키워드 보유(범위/효과 텍스트에 키워드 단어) | {sum(1 for m in M if m.get('keywords'))} | {len(M)} |"]
    for key, lab in labels:
        report.append(f"| {lab} | {cnt(key, with_eff)} | 효과 있음 {len(with_eff)} |")
    none = [m for m in with_eff if not m["mech_auto"] and not m.get("keywords")]
    report.append(f"| 위 중 아무것도 식별 안 됨 | {len(none)} | 효과 있음 {len(with_eff)} |")
    json.dump(none, open(os.path.join(out_dir, "moves-unidentified.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    report += ["", f"특성 {len(abil)}개: 전투단계 {cnt('stage_changes', abil)}, 상태이상 {cnt('status', abil)}, 면역 {cnt('immunity', abil)}, 아무것도 식별 안 됨 {sum(1 for a in abil if not a['mech_auto'])}; 빈도 종류 " + ", ".join(f"{k} {v}" for k, v in Counter(a.get("freq_kind") for a in abil).most_common())]
    open(os.path.join(out_dir, "entity-coverage.md"), "w", encoding="utf-8").write("\n".join(report) + "\n")
    print("\n".join(report))


if __name__ == "__main__":
    mode, md_dir, out_dir = sys.argv[1:4]
    (build_outline if mode == "outline" else build_entities)(md_dir, out_dir)
