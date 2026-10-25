"""대본 파일과 생성된 대본 시드가 맞는지, 대본 형식 검사가 틀린 대본을 막는지 본다.

    python3 -m pytest tools
"""
import pytest

from script_to_sql import SCRIPT_PATH, main, parse

SCRIPT = SCRIPT_PATH.read_text(encoding="utf-8")


def test_커밋된_대본_시드가_대본_파일과_같다():
    assert main(["--check"]) == 0


def test_씬_분해와_배역을_읽는다():
    script = parse(SCRIPT)
    scenes = {s.code: s for s in script.scenes}
    assert len(scenes) == 23
    assert [c.name for c in script.characters] == ["봉지우", "강도현", "봉재필", "문태", "구 노무사"]
    assert (scenes["S12"].int_ext, scenes["S12"].time_of_day, scenes["S12"].character_ids) == ("EXT", "DAY", [1, 2])
    assert (scenes["S21"].int_ext, scenes["S21"].time_of_day, scenes["S21"].character_ids) == ("EXT", "NIGHT", [2, 4])
    # 대사가 없는 씬도 등장 줄로 배역을 안다.
    assert scenes["S19"].character_ids == [2]
    assert all(line.kind == "ACTION" for line in scenes["S19"].lines)


def test_지금_촬영_배정의_출연_배우와_등장_배역이_같다():
    # 배역 id와 배우 id는 시드에서 같게 캐스팅한다(지우=배우 A 1, 도현=배우 B 2, 봉 대표=배우 C 3).
    scenes = {s.code: s for s in parse(SCRIPT).scenes}
    seeded = {"S01": [2, 3], "S08": [2, 3], "S12": [1, 2], "S13": [1], "S14": [2, 3], "S15": [3], "S18": [2, 3], "S19": [2]}
    for code, actors in seeded.items():
        assert scenes[code].character_ids == actors, code


def test_등장_줄에_없는_화자는_막는다():
    broken = SCRIPT.replace("등장: 지우\n강가 난간", "등장: 도현\n강가 난간").replace(
        "지우, 결국 웃으며", "지우: 바보.\n지우, 결국 웃으며"
    )
    with pytest.raises(ValueError, match="등장 줄에 없는 화자"):
        parse(broken)


def test_머리말_형식이_틀리면_막는다():
    with pytest.raises(ValueError, match="씬 머리말 형식"):
        parse(SCRIPT.replace("## S#13. 한강 강변 (낮, 실외)", "## S#13. 한강 강변 (오후)"))
