"""mock backend 고정 데이터: 가상 드라마 「여름의 끝에서」 7화, 촬영일 2026-11-12 하루치.

아키텍처 v2(Notion ShortCut) 7장 MVP 규모: 씬 20개, 배우 5명, 장소 3곳, 장비 5종, 1/2/3안 세트.
C가 실제 시드 데이터를 만들면 이 값으로 바꾼다. 이름·수치는 모두 시연용 가정이다.
"""

PROJECT_ID = "drama-ep07"
PRODUCTION_ID = 1
SHOOT_DATE = "2026-11-12"
BASE_SCHEDULE_VERSION = 7          # 현재 확정 계획 v7
EPISODE_BUDGET_REMAINING = 400_000  # 회차 남은 예산(원), HARD 예산 한도
RAIN_THRESHOLD = 60                 # 강수 확률(%) 이상인 시간대의 야외 촬영 = HARD (SCHEDULE.OUTDOOR_RAIN)
WEEKLY_LIMIT_HOURS = 52             # 근로기준법 주 52시간
DEFAULT_WEIGHTS = {"location": 0.25, "equipment": 0.15, "weather": 0.15, "budget": 0.20, "time": 0.10, "distance": 0.15}

# ---------------------------------------------------------------- 사람과 역할 (Notion 메모: 제작부·연출부·기술부서)

ROLES = {
    "PRODUCER": "책임 프로듀서", "PRODUCTION_PD": "제작 PD", "PRODUCTION_MANAGER": "제작실장", "PRODUCTION_STAFF": "제작부원",
    "DIRECTOR": "연출감독", "AD1": "1조감독", "AD2": "2조감독", "DIRECTING_STAFF": "연출부원",
    "DOP": "촬영감독", "GAFFER": "조명감독", "ART_DIRECTOR": "미술감독", "SOUND_LEAD": "동시녹음팀장",
    "GRIP_CHIEF": "그립실장", "COSTUME_MAKEUP": "의상·분장실장", "CAST": "출연자", "AGENCY_MANAGER": "소속사 매니저",
}
CHANGE_REQUEST_ROLES = {"PRODUCTION_MANAGER", "AD1", "AD2"}   # 변경 입력·계획안 저장 가능

USERS = {
    1: {"id": 1, "name": "남궁하람", "role": "PRODUCER"},
    2: {"id": 2, "name": "최가온", "role": "PRODUCTION_PD"},
    3: {"id": 3, "name": "윤솔", "role": "PRODUCTION_MANAGER"},
    4: {"id": 4, "name": "백도윤", "role": "DIRECTOR"},
    5: {"id": 5, "name": "서이준", "role": "AD1"},
    6: {"id": 6, "name": "한다온", "role": "AD2"},
    7: {"id": 7, "name": "배시온", "role": "DOP"},
    8: {"id": 8, "name": "문해솔", "role": "GAFFER"},
    9: {"id": 9, "name": "조은결", "role": "ART_DIRECTOR"},
    10: {"id": 10, "name": "강라온", "role": "SOUND_LEAD"},
    11: {"id": 11, "name": "임새벽", "role": "GRIP_CHIEF"},
    12: {"id": 12, "name": "오누리", "role": "COSTUME_MAKEUP"},
    21: {"id": 21, "name": "윤재하", "role": "CAST", "actorId": "A01"},
    22: {"id": 22, "name": "서하린", "role": "CAST", "actorId": "A02"},
    23: {"id": 23, "name": "도민결", "role": "CAST", "actorId": "A03"},
    24: {"id": 24, "name": "차여름", "role": "CAST", "actorId": "A04"},
    25: {"id": 25, "name": "유나래", "role": "CAST", "actorId": "A05"},
    31: {"id": 31, "name": "정바름", "role": "AGENCY_MANAGER", "managedActorIds": ["A04"]},
}
ROLE_USER = {u["role"]: u["id"] for u in USERS.values() if u["role"] not in {"CAST", "AGENCY_MANAGER"}}

# ---------------------------------------------------------------- 배우·계약

ACTORS = {
    "A01": {"actorId": "A01", "name": "윤재하", "available": [("08:00", "22:00")], "weeklyHoursSoFar": 40.0, "contractDocId": "contract-A01-v3"},
    "A02": {"actorId": "A02", "name": "서하린", "available": [("08:00", "22:00")], "weeklyHoursSoFar": 36.0, "contractDocId": "contract-A02-v1"},
    "A03": {"actorId": "A03", "name": "도민결", "available": [("08:00", "23:00")], "weeklyHoursSoFar": 30.0, "contractDocId": "contract-A03-v1"},
    "A04": {"actorId": "A04", "name": "차여름", "available": [("09:00", "16:00")], "weeklyHoursSoFar": 30.0, "contractDocId": "contract-A04-v3"},
    "A05": {"actorId": "A05", "name": "유나래", "available": [("12:00", "23:00")], "weeklyHoursSoFar": 28.0, "contractDocId": "contract-A05-v1"},
}
# 계약 문서 메타 (RAG 문서 data/docs/contract-*.md와 docId가 같다). status=SUPERSEDED는 옛 버전
CONTRACTS = {
    "contract-A01-v3": {"docId": "contract-A01-v3", "actorId": "A01", "version": 3, "status": "CURRENT", "nightBanAfter": None, "dailyMaxHours": 12},
    "contract-A02-v1": {"docId": "contract-A02-v1", "actorId": "A02", "version": 1, "status": "CURRENT", "nightBanAfter": None, "dailyMaxHours": 12},
    "contract-A03-v1": {"docId": "contract-A03-v1", "actorId": "A03", "version": 1, "status": "CURRENT", "nightBanAfter": None, "dailyMaxHours": 12},
    "contract-A04-v2": {"docId": "contract-A04-v2", "actorId": "A04", "version": 2, "status": "SUPERSEDED", "nightBanAfter": None, "dailyMaxHours": 12},
    "contract-A04-v3": {"docId": "contract-A04-v3", "actorId": "A04", "version": 3, "status": "CURRENT", "nightBanAfter": "22:00", "dailyMaxHours": 10},
    "contract-A05-v1": {"docId": "contract-A05-v1", "actorId": "A05", "version": 1, "status": "CURRENT", "nightBanAfter": None, "dailyMaxHours": 12},
}
STAFF_WEEKLY_HOURS_SO_FAR = {"DOP": 38.0, "GAFFER": 36.0, "SOUND_LEAD": 34.0}

# ---------------------------------------------------------------- 장소·장비

LOCATIONS = {
    "L01": {"locationId": "L01", "name": "한강공원 망원지구", "outdoor": True, "available": [("09:00", "17:00")],
            "permit": {"permitId": 301, "status": "APPROVED", "start": "09:00", "end": "17:00", "docId": "permit-hangang", "section": "2.3"},
            "droneProhibited": False, "zoneDocId": None},
    "L02": {"locationId": "L02", "name": "성수 스튜디오 S", "outdoor": False, "available": [("14:00", "18:30")],
            "permit": None, "droneProhibited": False, "zoneDocId": None, "bookingId": "R-2031"},
    "L03": {"locationId": "L03", "name": "파주 세트장", "outdoor": False, "available": [("08:00", "22:00")],
            "permit": None, "droneProhibited": True, "zoneDocId": "zone-paju"},
}
# km, 분
ROUTES = {
    frozenset({"L01", "L02"}): (8, 20),
    frozenset({"L01", "L03"}): (30, 50),
    frozenset({"L02", "L03"}): (41, 60),
}

EQUIPMENT = {
    "E01": {"equipmentId": "E01", "name": "카메라 세트", "available": [("07:00", "23:00")]},
    "E02": {"equipmentId": "E02", "name": "드론", "available": [("07:00", "23:00")], "isDrone": True},
    "E03": {"equipmentId": "E03", "name": "반사판", "available": [("07:00", "23:00")]},
    "E04": {"equipmentId": "E04", "name": "추가 조명 세트", "available": [("13:00", "19:00")]},
    "E05": {"equipmentId": "E05", "name": "크레인", "available": [("07:00", "23:00")]},
}
# 장비 묶음. extraCost = 새로 빌려야 하는 비용(원)
PACKAGES = {
    "PKG-BASE": {"packageId": "PKG-BASE", "name": "기존 렌탈 (카메라·드론·반사판)", "equipmentIds": ["E01", "E02", "E03"], "extraCost": 0},
    "PKG-LIGHT": {"packageId": "PKG-LIGHT", "name": "추가 조명 대여 (카메라·반사판·추가 조명)", "equipmentIds": ["E01", "E03", "E04"], "extraCost": 320_000},
    "PKG-MIN": {"packageId": "PKG-MIN", "name": "최소 장비 (카메라)", "equipmentIds": ["E01"], "extraCost": 0},
}
# SOFT 장비 점수: 묶음 × 실내/야외
EQUIPMENT_SCORE = {
    ("PKG-BASE", "outdoor"): 1.0, ("PKG-BASE", "indoor"): 0.8,
    ("PKG-LIGHT", "outdoor"): 0.8, ("PKG-LIGHT", "indoor"): 1.0,
    ("PKG-MIN", "outdoor"): 0.6, ("PKG-MIN", "indoor"): 0.6,
}

# 시간대별 강수 확률(%). 야외 장소만 의미가 있다. 13시 이후 비 → 시연 시나리오
WEATHER_HOURLY = {
    ("L01", SHOOT_DATE): {9: 20, 10: 20, 11: 20, 12: 30, 13: 80, 14: 80, 15: 80, 16: 80, 17: 80, 18: 70, 19: 60, 20: 60, 21: 50},
}

# ---------------------------------------------------------------- 씬·촬영 블록·1/2/3안

def _scenes(ids, title, intent, actors, minutes):
    return {sid: {"sceneId": sid, "title": f"{title} {i + 1}", "intent": intent, "actorIds": actors, "durationMin": minutes}
            for i, sid in enumerate(ids)}

SCENES = {
    **_scenes([f"S{n:02d}" for n in range(1, 9)], "세트장 거실", "실내 대화", ["A01", "A02", "A03"], 20),
    **_scenes(["S12", "S13", "S14"], "한강 산책", "맑은 날 야외 산책", ["A01", "A04"], 40),
    **_scenes(["S18", "S19"], "스튜디오 사무실", "실내 갈등", ["A01", "A02"], 60),
    **_scenes([f"S{n:02d}" for n in range(20, 27)], "세트장 밤 부엌", "실내 야간", ["A03", "A05"], 17),
}

BLOCKS = [
    {"blockId": "B1", "locationId": "L03", "start": "09:00", "end": "11:40", "sceneIds": [f"S{n:02d}" for n in range(1, 9)], "equipmentIds": ["E01", "E03"], "packageId": None},
    {"blockId": "B2", "locationId": "L01", "start": "13:00", "end": "15:00", "sceneIds": ["S12", "S13", "S14"], "equipmentIds": ["E01", "E02", "E03"], "packageId": "PKG-BASE"},
    {"blockId": "B3", "locationId": "L02", "start": "16:30", "end": "18:30", "sceneIds": ["S18", "S19"], "equipmentIds": ["E01", "E03", "E05"], "packageId": None},
    {"blockId": "B4", "locationId": "L03", "start": "19:30", "end": "21:30", "sceneIds": [f"S{n:02d}" for n in range(20, 27)], "equipmentIds": ["E01", "E03"], "packageId": None},
]

# 장면 의도와 장소의 적합도 (SOFT 장소 점수)
LOCATION_FIT = {"맑은 날 야외 산책": {"L01": 0.95, "L02": 0.75, "L03": 0.60}}

# 제작사가 미리 만든 1/2/3안. 요소: 장소, 장비, 시간대 (이동 거리는 장소에서 계산)
PLAN_SETS = {
    "B2": {
        "blockId": "B2",
        "plans": {
            "P1": {"label": "1안", "locationId": "L01", "packageId": "PKG-BASE", "start": "13:00", "end": "15:00"},
            "P2": {"label": "2안", "locationId": "L02", "packageId": "PKG-LIGHT", "start": "14:00", "end": "16:00"},
            "P3": {"label": "3안", "locationId": "L03", "packageId": "PKG-MIN", "start": "10:00", "end": "12:00"},
        },
    }
}

# 아워플레이스 검색 mock (공개 예약 API 미확인 → 예약은 담당자 완료 단계)
OURPLACE = [
    {"placeId": "OP-101", "name": "성수 루프탑 스튜디오", "area": "성수", "indoor": True, "areaPyeong": 35, "pricePerHour": 120_000, "naturalLight": True},
    {"placeId": "OP-102", "name": "망원 한옥 카페", "area": "망원", "indoor": True, "areaPyeong": 28, "pricePerHour": 90_000, "naturalLight": True},
    {"placeId": "OP-103", "name": "일산 화이트 호리존", "area": "일산", "indoor": True, "areaPyeong": 50, "pricePerHour": 150_000, "naturalLight": False},
]
