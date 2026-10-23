"""
Drive 뷰어에서 긁은 docx 페이지 텍스트(헤딩 정보 없음, 45자 줄바꿈, 줄마다 빈 줄) → 마크다운.
휴리스틱:
  - 'N/M페이지' 표식 제거, 줄바꿈으로 끊긴 문장은 다시 잇는다(끝에 문장부호가 없으면 다음 줄과 결합).
  - 'Chapter N' → #, '이름(English)' 다음 줄이 타입라인/태그/전제조건/빈도면 재주·클래스 블록의 **이름** 줄.
  - '전제조건:' '효과:' '발동조건:' '대상:' 등 라벨 줄 → **라벨:** 값 (PTK 룰북 서식과 맞춤).
  - 짧고(≤24자) 문장부호 없는 줄이 그 뒤에 긴 문단을 거느리면 ### 소제목.
  - 블록(이름/태그/라벨/빈도/타입라인) 줄 사이의 빈 줄은 지워 ptk_structure 의 블록 파서가 한 덩어리로 읽게 한다.
  python -X utf8 -I tools/docx_to_md.py <pages.txt> <out.md> "<제목>"
"""
import re
import sys

LABELS = ["전제조건", "전제 조건", "발동조건", "발동 조건", "효과", "대상", "특수", "비용", "빈도", "행동", "AC", "분류", "범위", "참고", "조건", "시약"]
LABEL_RE = re.compile(r"^(" + "|".join(LABELS) + r"|랭크\s*\d+\s*전제\s*조건)\s*[:：]\s*(.*)$")
FREQ_RE = re.compile(r"^(임의|항상|장면(?:\s*x\s*\d+)?|일일|하루(?:\s*x\s*\d+)?|\d+\s*AP(?:\s*제거)?|연장 행동(?:\([^)]{1,12}\))?|턴\s*1회|매 턴)\s*(?:[-–]\s*([^.。]{1,24}))?$")
NAME_RE = re.compile(r"^[가-힣A-Za-z0-9 ·!?'’/]{1,30}\s*[\(（][A-Za-z0-9 '’!?.,:-]{2,60}[\)）]$")
TAG_RE = re.compile(r"^(\[[^\]]+\]\s*)+$")
TYPELINE_RE = re.compile(r"^(여행 및 조사|트레이너 전투|패시브 포켓몬 서포트|액티브 포켓몬 서포트|연관 스킬)\s*[:：]")
END_PUNCT = ("다.", "요.", ".", "!", "?", ":", "：", "]", ")", "）", "…", "~")


def clean(text):
    out = []
    for l in text.split("\n"):
        l = l.strip()
        if re.match(r"^\d+/\d+페이지$", l):
            continue
        if l or (out and out[-1]):
            out.append(l)
    return out


def join_wrapped(lines):
    """뷰어가 45자 정도에서 강제 줄바꿈한 줄을 다시 잇는다 (라벨 줄도 이어지며, 다음 줄이 새 블록 요소면 멈춘다)."""
    res, i = [], 0
    while i < len(lines):
        l = lines[i]
        if not l:
            res.append(l)
            i += 1
            continue
        while i + 1 < len(lines) and not l.endswith(END_PUNCT) and len(l) >= 22 and not NAME_RE.match(l) and not TAG_RE.match(l):
            nxt_i = i + 1 if lines[i + 1] else (i + 2 if i + 2 < len(lines) else None)
            nxt = lines[nxt_i] if nxt_i is not None else ""
            if not nxt or NAME_RE.match(nxt) or TAG_RE.match(nxt) or LABEL_RE.match(nxt) or FREQ_RE.match(nxt) or TYPELINE_RE.match(nxt) or re.match(r"^Chapter\s*\d", nxt):
                break
            l = l + " " + nxt
            i = nxt_i
        res.append(l)
        i += 1
    return res


def is_name_line(x):
    return x.startswith("**") and x.endswith("**") and bool(NAME_RE.match(x.strip("*").strip()))


def blockish(x):
    return bool(x) and (x.startswith("**") or bool(TAG_RE.match(x)) or bool(FREQ_RE.match(x)) or x.startswith("_"))


def to_markdown(lines, title):
    md = [f"# {title}", ""]
    for i, l in enumerate(lines):
        if not l:
            md.append("")
            continue
        nxt = next((x for x in lines[i + 1:i + 4] if x), "")
        if re.match(r"^Chapter\s*\d+\s*[:：]", l):
            md.append(f"# {l}")
        elif NAME_RE.match(l) and (TYPELINE_RE.match(nxt) or re.match(r"^\S+\s*[:：]\s*\d", nxt)):
            md.append(f"### {l}")
        elif TYPELINE_RE.match(l):
            md.append(f"_{l}_")
        elif NAME_RE.match(l) and (TAG_RE.match(nxt) or LABEL_RE.match(nxt) or FREQ_RE.match(nxt)):
            md.append(f"**{l}**")
        elif LABEL_RE.match(l):
            m = LABEL_RE.match(l)
            md.append(f"**{m.group(1)}:** {m.group(2)}")
        elif (len(l) <= 24 and not l.endswith(END_PUNCT) and not FREQ_RE.match(l) and not TAG_RE.match(l)
              and nxt and len(nxt) > 40 and not LABEL_RE.match(nxt)):
            md.append(f"### {l}")
        else:
            md.append(l)
    compact = []
    for i, l in enumerate(md):
        if l == "" and compact and blockish(compact[-1]):
            nxt = next((x for x in md[i + 1:i + 3] if x != ""), "")
            if blockish(nxt) and not is_name_line(nxt):
                continue
        compact.append(l)
    return "\n".join(compact) + "\n"


if __name__ == "__main__":
    src, dst, title = sys.argv[1], sys.argv[2], sys.argv[3]
    md = to_markdown(join_wrapped(clean(open(src, encoding="utf-8").read())), title)
    open(dst, "w", encoding="utf-8").write(md)
    print(dst, len(md), "chars,", md.count("\n# "), "h1,", md.count("\n### "), "h3,", md.count("\n**"), "bold lines")
