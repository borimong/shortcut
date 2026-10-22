"""대본 마크다운에서 대본 시드 SQL(data-script.sql)을 만든다.

대본 파일 하나가 원본이다. rag-mcp는 같은 파일을 RAG 문서로 색인하고, backend는 이 도구가 만든 SQL로
씬 분해(script_scenes), 배역(characters), 등장(scene_characters), 대본 줄(script_lines)을 채운다.
둘을 같은 파일에서 만들어야 엔진이 보는 표와 Agent가 인용하는 원문이 어긋나지 않는다.

세트 고정, 예상 분, 요구 장비, 캐스팅처럼 제작부가 정하는 값은 여기서 만들지 않고 data-schedule.sql에 손으로 적는다.

    python3 tools/script_to_sql.py          # data-script.sql을 다시 만든다
    python3 tools/script_to_sql.py --check  # 커밋된 파일과 다르면 실패한다(테스트용)
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
SCRIPT_PATH = APP_DIR / "mcp" / "rag-mcp" / "corpus" / "script-ep07-v1.md"
OUTPUT_PATH = APP_DIR / "backend" / "src" / "main" / "resources" / "data-script.sql"
PROJECT_ID = 1

HEADER = re.compile(r"^S#(\d+)\.\s+(.+?)\s+\((낮|밤),\s*(실내|실외)\)$")
CHARACTER = re.compile(r"^- (.+?): (.+?), (주연|조연)\. (.+)$")
KINDS = {"주연": "LEAD", "조연": "SUPPORT"}
TIME_OF_DAY = {"낮": "DAY", "밤": "NIGHT"}
INT_EXT = {"실내": "INT", "실외": "EXT"}


@dataclass
class Character:
    id: int
    label: str
    name: str
    kind: str


@dataclass
class Line:
    kind: str
    character_id: int | None
    text: str


@dataclass
class Scene:
    code: str
    heading: str
    setting: str
    time_of_day: str
    int_ext: str
    synopsis: str = ""
    character_ids: list[int] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)


@dataclass
class Script:
    doc_id: str
    characters: list[Character]
    scenes: list[Scene]


def parse(raw: str) -> Script:
    """머리말, 등장인물 목록, 씬(머리말, 요약, 등장, 지문과 대사)을 읽는다. 형식이 틀리면 줄 위치와 함께 실패한다."""
    lines = raw.strip().splitlines()
    end = lines.index("---", 1)
    meta = dict(line.split(":", 1) for line in lines[1:end])
    doc_id = meta["doc_id"].strip()

    characters: list[Character] = []
    scenes: list[Scene] = []
    section = None
    for number, line in enumerate(lines[end + 1 :], start=end + 2):
        if line.startswith("## "):
            title = line[3:].strip()
            if title == "등장인물":
                section = "characters"
                continue
            match = HEADER.match(title)
            if not match:
                raise ValueError(f"{number}행: 씬 머리말 형식이 아니다: {title}")
            code = f"S{int(match.group(1)):02d}"
            if any(s.code == code for s in scenes):
                raise ValueError(f"{number}행: 씬 {code}가 두 번 나온다")
            scenes.append(Scene(code, title, match.group(2), TIME_OF_DAY[match.group(3)], INT_EXT[match.group(4)]))
            section = "scene"
        elif section == "characters" and line.startswith("- "):
            match = CHARACTER.match(line)
            if not match:
                raise ValueError(f"{number}행: 등장인물 형식이 아니다: {line}")
            characters.append(Character(len(characters) + 1, match.group(1), match.group(2), KINDS[match.group(3)]))
        elif section == "scene" and line.strip():
            _scene_line(scenes[-1], line.strip(), characters, number)
    for scene in scenes:
        if not scene.character_ids:
            raise ValueError(f"{scene.code}: 등장 줄이 없다")
    return Script(doc_id, characters, scenes)


def _scene_line(scene: Scene, line: str, characters: list[Character], number: int) -> None:
    by_label = {c.label: c for c in characters}
    if line.startswith("> 요약:"):
        scene.synopsis = line.removeprefix("> 요약:").strip()
        return
    if line.startswith("등장:"):
        for label in (part.strip() for part in line.removeprefix("등장:").split(",")):
            if label not in by_label:
                raise ValueError(f"{number}행: 등장인물 목록에 없는 배역이다: {label}")
            scene.character_ids.append(by_label[label].id)
        return
    label, sep, text = line.partition(": ")
    if sep and label in by_label:
        speaker = by_label[label]
        # 대사 화자는 등장 줄에 있어야 한다. 빠뜨리면 촬영 배정에서 그 배우를 부르지 않게 된다.
        if speaker.id not in scene.character_ids:
            raise ValueError(f"{number}행: {scene.code}의 등장 줄에 없는 화자다: {label}")
        scene.lines.append(Line("DIALOGUE", speaker.id, text))
    else:
        scene.lines.append(Line("ACTION", None, line))


def to_sql(script: Script) -> str:
    """시드 SQL을 만든다. 다시 돌려도 같은 결과가 나오게 하고, 대본을 고치면 다음 기동에서 표에도 반영되게 한다."""
    p = PROJECT_ID
    out = [
        f"-- 이 파일은 tools/script_to_sql.py가 {SCRIPT_PATH.relative_to(APP_DIR)}에서 만든다.",
        "-- 손으로 고치지 말고 대본을 고친 뒤 다시 만든다. 세트 고정, 예상 분, 요구 장비, 캐스팅은 data-schedule.sql에 있다.",
        "",
        "-- 대본에서 오는 열만 덮어쓴다. 촬영 배정(scenes)이 이 행을 외래키로 가리키므로 지우지 않는다.",
        "INSERT INTO script_scenes (project_id, code, heading, int_ext, time_of_day, setting, synopsis, script_doc_id)",
        "VALUES " + ",\n       ".join(
            f"({p}, {q(s.code)}, {q(s.heading)}, {q(s.int_ext)}, {q(s.time_of_day)}, {q(s.setting)}, {q(s.synopsis)}, "
            f"{q(script.doc_id)})"
            for s in script.scenes
        ),
        "ON CONFLICT (project_id, code) DO UPDATE SET heading = EXCLUDED.heading, int_ext = EXCLUDED.int_ext,",
        "    time_of_day = EXCLUDED.time_of_day, setting = EXCLUDED.setting, synopsis = EXCLUDED.synopsis,",
        "    script_doc_id = EXCLUDED.script_doc_id;",
        "",
        "-- 배역 이름과 종류만 덮어쓴다. 캐스팅(actor_id)은 제작부 값이다.",
        "INSERT INTO characters (id, project_id, name, kind)",
        "VALUES " + ",\n       ".join(f"({c.id}, {p}, {q(c.name)}, {q(c.kind)})" for c in script.characters),
        "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, kind = EXCLUDED.kind;",
        "",
        "-- 등장과 대본 줄은 다른 표가 가리키지 않으므로 지우고 다시 넣는다. 대본에서 빠진 등장이나 줄이 남지 않는다.",
        f"DELETE FROM scene_characters WHERE project_id = {p};",
        "INSERT INTO scene_characters (project_id, scene_code, character_id)",
        "VALUES " + ",\n       ".join(
            f"({p}, {q(s.code)}, {cid})" for s in script.scenes for cid in s.character_ids
        ) + ";",
        "",
        f"DELETE FROM script_lines WHERE project_id = {p};",
        "INSERT INTO script_lines (project_id, scene_code, line_no, kind, character_id, text)",
        "VALUES " + ",\n       ".join(
            f"({p}, {q(s.code)}, {no}, {q(line.kind)}, {line.character_id or 'NULL'}, {q(line.text)})"
            for s in script.scenes
            for no, line in enumerate(s.lines, start=1)
        ) + ";",
        "",
    ]
    return "\n".join(out)


def q(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="커밋된 data-script.sql과 다르면 실패한다")
    args = parser.parse_args(argv)
    sql = to_sql(parse(SCRIPT_PATH.read_text(encoding="utf-8")))
    if args.check:
        if not OUTPUT_PATH.exists() or OUTPUT_PATH.read_text(encoding="utf-8") != sql:
            print(f"{OUTPUT_PATH.name}가 대본과 다릅니다. python3 tools/script_to_sql.py로 다시 만드세요.", file=sys.stderr)
            return 1
        return 0
    OUTPUT_PATH.write_text(sql, encoding="utf-8")
    print(f"{OUTPUT_PATH.relative_to(APP_DIR)}를 만들었습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
