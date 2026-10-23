"""제약 수집(collect_constraints) 근거 평가에 쓰는 변경 시나리오를 만듭니다.

시나리오마다 변경 이벤트, 블록 배우의 현재 계약서, 1/2/3안 후보 장소, 재난 문자, 영향 분석 위험 문장과
상황 키(topics)를 둡니다. 정답 조항은 여기서 정하지 않고, 평가기가 조항 라벨과 이 정보로 계산합니다.
같은 seed면 항상 같은 목록이 나옵니다.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field

# 장소 id -> (이름, 야외 여부, 지역)
LOCATIONS = {
    "hangang": ("한강공원 여의도 구간", True, "서울 영등포구"),
    "seoul-forest": ("서울숲", True, "서울 성동구"),
    "bukchon": ("북촌 한옥마을", True, "서울 종로구"),
    "gwanghwamun": ("광화문광장", True, "서울 종로구"),
    "namsan": ("남산공원", True, "서울 중구"),
    "olympic-park": ("올림픽공원", True, "서울 송파구"),
    "subway-euljiro": ("을지로입구역 역사", False, "서울 중구"),
    "haeundae": ("해운대 해수욕장", True, "부산 해운대구"),
    "bukhansan": ("북한산국립공원", True, "서울 은평구"),
    "paju-set": ("파주 세트장", False, "경기 파주시"),
    "ilsan-studio": ("일산 실내 스튜디오", False, "경기 고양시"),
    "incheon-wharf": ("인천 내항 부두", True, "인천 중구"),
}

# 배우 id -> (현재 계약서 문서 ID, 표시 이름, 상황 키)
ACTORS = {
    "actor-a": ("contract-actor-a-v3", "배우 A", []),
    "actor-b": ("contract-actor-b-v1", "배우 B", []),
    "actor-c": ("contract-actor-c-v2", "배우 C", []),
    "actor-d": ("contract-actor-d-v1", "배우 D", []),
    "actor-e": ("contract-actor-e-v2", "배우 E", []),
    "actor-f": ("contract-actor-f-v1", "아역 배우 F", ["minor"]),
    "actor-g": ("contract-actor-g-v1", "청소년 배우 G", ["minor"]),
    "actor-h": ("contract-actor-h-v2", "스턴트 대역 H", ["stunt"]),
    "actor-i": ("contract-actor-i-v1", "외국인 배우 I", ["foreign"]),
    "actor-j": ("contract-actor-j-v3", "배우 J", ["elderly"]),
    "actor-k": ("contract-actor-k-v1", "배우 K", []),
    "actor-l": ("contract-actor-l-v1", "촬영견 L", ["animal"]),
    "actor-m": ("contract-actor-m-v1", "보조출연 M팀", ["extras"]),
}

BASE_ACTORS = ["actor-a", "actor-b", "actor-c"]
BASE_LOCATIONS = ["hangang", "paju-set"]
OUTDOOR = [k for k, v in LOCATIONS.items() if v[1]]
WATERSIDE = ["hangang", "haeundae", "incheon-wharf"]


@dataclass
class Scenario:
    id: str
    kind: str
    event: dict
    actors: list[str]
    locations: list[str]
    topics: list[str]
    alerts: list[dict] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)

    @property
    def contract_doc_ids(self) -> list[str]:
        return sorted(ACTORS[a][0] for a in self.actors)

    def to_dict(self) -> dict:
        return asdict(self) | {"contract_doc_ids": self.contract_doc_ids}


def _name(location: str) -> str:
    return LOCATIONS[location][0]


def _region(location: str) -> str:
    return LOCATIONS[location][2]


def _alert(kind: str, level: str, region: str, start: str, end: str, message: str) -> dict:
    return {"region": region, "kind": kind, "level": level, "start": start, "end": end, "message": message}


# 이벤트 종류마다 (상황 키, 장소 후보, 필요한 배우 상황, 문장 생성 함수)
def _rain(r, loc):
    mm = r.choice([3, 6, 8, 12, 20])
    hour = r.choice([11, 13, 15])
    return {"type": "RAIN", "detail": f"{hour}시 이후 {_name(loc)} 시간당 {mm}mm 비 예보"}, [], [f"야외 촬영 구간 강수 {mm}mm"]


def _heavy_rain_alert(r, loc):
    region = _region(loc)
    alert = _alert("집중호우", "긴급재난문자", region, "13:00", "18:00", f"{region} 호우경보, 하천변 접근 금지")
    return (
        {"type": "DISASTER", "detail": f"{region} 호우경보 긴급재난문자 13~18시"},
        [alert],
        ["재난 문자 발령 지역과 촬영 시간대 겹침"],
    )


def _heat(r, loc):
    t = r.choice([33, 35, 37])
    alert = _alert("폭염", "안전안내문자", _region(loc), "11:00", "17:00", f"폭염경보, 체감온도 {t}도 이상 야외활동 자제")
    return {"type": "HEAT", "detail": f"{_name(loc)} 낮 최고 체감온도 {t}도 폭염경보"}, [alert], ["한낮 야외 촬영 열사병 위험"]


def _cold(r, loc):
    t = r.choice([8, 12, 15])
    return {"type": "COLD", "detail": f"{_name(loc)} 새벽 최저 영하 {t}도 한파주의보"}, [], ["새벽 야외 촬영 저체온 위험"]


def _wind(r, loc):
    v = r.choice([12, 15, 18])
    return (
        {"type": "WIND", "detail": f"{_name(loc)} 순간 풍속 초속 {v}m 강풍주의보, 조명 타워와 크레인 설치 예정"},
        [],
        ["고소 장비 전도 위험"],
    )


def _typhoon(r, loc):
    region = _region(loc)
    alert = _alert("태풍", "긴급재난문자", region, "12:00", "23:59", f"태풍경보 발효, {region} 해안가와 하천 접근 금지")
    return {"type": "TYPHOON", "detail": f"태풍 북상으로 {region} 오후 태풍경보"}, [alert], ["강풍과 호우 동반, 촬영 중단 가능성"]


def _earthquake(r, loc):
    region = _region(loc)
    alert = _alert("지진", "안전안내문자", region, "09:40", "12:00", "규모 4.0 지진 발생, 여진에 대비하세요")
    return (
        {"type": "EARTHQUAKE", "detail": f"{region} 인근 규모 4.0 지진, 여진 우려"},
        [alert],
        ["세트 구조물과 고소 장비 점검 필요"],
    )


def _dust(r, loc):
    return {"type": "DUST", "detail": f"{_region(loc)} 초미세먼지 매우 나쁨 예보"}, [], ["야외 장시간 촬영 호흡기 위험"]


def _lightning(r, loc):
    return {"type": "LIGHTNING", "detail": f"{_name(loc)} 오후 3~6시 낙뢰 예보"}, [], ["야외 금속 장비 낙뢰 위험"]


def _actor_unavailable(r, loc, actors):
    actor = r.choice(actors)
    hour = r.choice([14, 15, 17])
    detail = f"{ACTORS[actor][1]} 소속사 요청으로 {hour}시 이후 촬영 불가, 장면 순서 조정 필요"
    return {"type": "ACTOR_UNAVAILABLE", "detail": detail}, [], ["배우 가용 시간 축소"]


def _night_extension(r, loc):
    end = r.choice([22, 23])
    return (
        {
            "type": "SCHEDULE_CHANGE",
            "detail": f"야간 장면 추가로 {_name(loc)} 촬영 종료를 {end}시로 연장",
            "instruction": "밤 장면 꼭 넣자",
        },
        [],
        ["야간 촬영과 연장 근로 발생"],
    )


def _equipment(r, loc):
    item = r.choice(["드론 기체 고장", "메인 카메라 바디 고장", "조명 발전차 고장"])
    return {"type": "EQUIPMENT_FAILURE", "detail": f"{item}, 대체 장비 당일 렌탈 필요"}, [], ["장비 렌탈 추가 비용"]


def _drone_add(r, loc):
    return (
        {"type": "SCHEDULE_CHANGE", "detail": f"{_name(loc)} 부감 드론 숏 추가", "instruction": "드론으로 위에서 한 번 잡아 줘"},
        [],
        ["드론 비행 가능 여부 확인 필요"],
    )


def _location_cancel(r, loc):
    return (
        {"type": "LOCATION_CANCEL", "detail": f"{_name(loc)} 촬영 허가 취소 통보, 대체 장소 필요"},
        [],
        ["장소 취소 위약금과 대체 장소 비용"],
    )


def _budget_cut(r, loc):
    pct = r.choice([10, 20, 30])
    return {"type": "BUDGET_CHANGE", "detail": f"제작비 조정으로 이번 블록 예산 {pct}% 감액"}, [], ["장소와 장비 비용 축소 필요"]


def _overtime(r, loc):
    h = r.choice([44, 47, 50])
    return (
        {"type": "SCHEDULE_CHANGE", "detail": f"이번 주 스태프 누적 근로 {h}시간, 남은 촬영 8시간 추가 필요"},
        [],
        ["주 52시간 초과 위험"],
    )


def _crowd(r, loc):
    return {"type": "CROWD", "detail": f"{_name(loc)} 주말 축제로 인파 밀집 예상"}, [], ["인파 통제와 안전 요원 필요"]


def _water(r, loc):
    return (
        {"type": "SCHEDULE_CHANGE", "detail": f"{_name(loc)} 보트 추격 수상 장면 추가", "instruction": "물 위 액션 넣자"},
        [],
        ["수상 촬영 안전 인력 필요"],
    )


def _stunt(r, loc):
    return (
        {"type": "SCHEDULE_CHANGE", "detail": "와이어 액션 장면을 오전으로 앞당김"},
        [],
        ["고소 와이어 장비와 대역 배우 조건 확인"],
    )


def _minor_late(r, loc, actors):
    minor = next(a for a in actors if "minor" in ACTORS[a][2])
    return (
        {"type": "SCHEDULE_CHANGE", "detail": f"{ACTORS[minor][1]} 출연 장면 지연으로 21시 30분까지 촬영 필요"},
        [],
        ["청소년 출연자 야간 촬영 제한"],
    )


# (종류, 상황 키, 장소 조건, 필요한 배우 상황, 생성 함수, 배우 목록을 받는지)
KINDS = [
    ("rain", ["rain"], OUTDOOR, None, _rain, False),
    ("heavy_rain_alert", ["rain"], OUTDOOR, None, _heavy_rain_alert, False),
    ("heat", ["heat"], OUTDOOR, None, _heat, False),
    ("cold", ["cold"], OUTDOOR, None, _cold, False),
    ("wind", ["wind", "height"], OUTDOOR, None, _wind, False),
    ("typhoon", ["typhoon", "wind", "rain"], OUTDOOR, None, _typhoon, False),
    ("earthquake", ["earthquake"], list(LOCATIONS), None, _earthquake, False),
    ("dust", ["dust"], OUTDOOR, None, _dust, False),
    ("lightning", ["lightning"], OUTDOOR, None, _lightning, False),
    ("actor_unavailable", ["night"], list(LOCATIONS), None, _actor_unavailable, True),
    ("night_extension", ["night", "overtime", "noise"], list(LOCATIONS), None, _night_extension, False),
    ("equipment", ["equipment"], list(LOCATIONS), None, _equipment, False),
    ("drone_add", ["drone"], OUTDOOR, None, _drone_add, False),
    ("location_cancel", ["cancel", "location_fee"], list(LOCATIONS), None, _location_cancel, False),
    ("budget_cut", ["equipment", "location_fee"], list(LOCATIONS), None, _budget_cut, False),
    ("overtime", ["overtime"], list(LOCATIONS), None, _overtime, False),
    ("crowd", ["crowd"], ["hangang", "gwanghwamun", "haeundae", "olympic-park", "seoul-forest"], None, _crowd, False),
    ("water", ["water", "stunt"], WATERSIDE, "stunt", _water, False),
    ("stunt", ["stunt", "height"], list(LOCATIONS), "stunt", _stunt, False),
    ("minor_late", ["minor", "night"], list(LOCATIONS), "minor", _minor_late, True),
]


def _pick_actors(r: random.Random, pool: list[str], need: str | None) -> list[str]:
    count = r.choice([1, 2, 2, 3])
    actors = r.sample(pool, min(count, len(pool)))
    if need and not any(need in ACTORS[a][2] for a in actors):
        actors[0] = r.choice([a for a in pool if need in ACTORS[a][2]])
    return sorted(set(actors))


def _make(r: random.Random, index: int, kind: tuple, actor_pool: list[str], location_pool: list[str]) -> Scenario:
    name, topics, allowed_locations, need, build, takes_actors = kind
    candidates = [loc for loc in allowed_locations if loc in location_pool] or location_pool
    primary = r.choice(candidates)
    actors = _pick_actors(r, actor_pool, need)
    event, alerts, risks = build(r, primary, actors) if takes_actors else build(r, primary)
    # 1/2/3안에는 다른 장소가 섞일 수 있어 후보 장소를 하나 더 둔다.
    others = [loc for loc in location_pool if loc != primary]
    locations = [primary] + ([r.choice(others)] if others and r.random() < 0.6 else [])
    names = ", ".join(f"{_name(loc)}({i + 1}안)" for i, loc in enumerate(locations))
    risks = risks + [f"후보 장소: {names}"]
    all_topics = set(topics)
    for actor in actors:
        all_topics.update(ACTORS[actor][2])
    return Scenario(
        id=f"s{index:03d}-{name}",
        kind=name,
        event={"id": index, "requested_by": "제작실장", **event},
        actors=actors,
        locations=locations,
        topics=sorted(all_topics),
        alerts=alerts,
        risks=risks,
    )


def build_scenarios(count: int = 150, base_count: int = 30, seed: int = 7) -> list[Scenario]:
    """앞의 base_count개는 운영 코퍼스에 있는 배우(A, B, C)와 장소(한강, 파주)만 씁니다."""
    r = random.Random(seed)
    scenarios = []
    base_kinds = [k for k in KINDS if k[3] is None]
    for i in range(base_count):
        kind = base_kinds[i % len(base_kinds)]
        scenarios.append(_make(r, i + 1, kind, BASE_ACTORS, BASE_LOCATIONS))
    for i in range(base_count, count):
        kind = KINDS[i % len(KINDS)]
        scenarios.append(_make(r, i + 1, kind, list(ACTORS), list(LOCATIONS)))
    return scenarios


if __name__ == "__main__":
    import json

    for s in build_scenarios():
        print(json.dumps(s.to_dict(), ensure_ascii=False))
