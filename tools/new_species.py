"""커스텀 종 파일 초안 생성 / 검증.
  python -X utf8 -I tools/new_species.py <root> --from 뚜벅쵸 --name 실험체 [--author 이름]   → data/custom/species/<slug>.json 초안
  python -X utf8 -I tools/new_species.py <root> --validate data/custom/species/foo.json      → 오류/경고 출력 (오류 있으면 종료 코드 1)"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
from engine import Rules  # noqa: E402
from custom_species import slug, template_from, validate  # noqa: E402


def main(argv):
    root = argv[1] if len(argv) > 1 and not argv[1].startswith("--") else "."
    r = Rules(root)
    if "--validate" in argv:
        path = argv[argv.index("--validate") + 1]
        data = json.load(open(path, encoding="utf-8"))
        errors, warns = validate(r, data)
        for e in errors:
            print("오류:", e)
        for w in warns:
            print("경고:", w)
        print("검증 통과" if not errors else f"검증 실패 ({len(errors)}건)")
        return 0 if not errors else 1
    src = argv[argv.index("--from") + 1]
    name = argv[argv.index("--name") + 1]
    author = argv[argv.index("--author") + 1] if "--author" in argv else None
    data = template_from(r, src, name, author)
    out_dir = os.path.join(root, "data/custom/species")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{slug(name)}.json")
    json.dump(data, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"초안 → {out} (기본 스탯 합 {sum(data['base_stats'].values())}, 학습 기술 {len(data['learnset']['level_up'])}개)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
