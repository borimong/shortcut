"""mock backend 고정 데이터. 가상 드라마 1편의 일부.

C가 실제 시드 데이터(data/seed)를 만들면 그 값으로 바꾼다. ID 형식은 문서 7장과 같다.
"""

PRODUCTION_ID = 1

LOCATIONS = {
    "L01": {"locationId": "L01", "name": "일산 스튜디오 A", "region": "고양", "outdoor": False},
    "L02": {"locationId": "L02", "name": "남산 공원 산책로", "region": "서울 중구", "outdoor": True},
    "L03": {"locationId": "L03", "name": "연남동 카페", "region": "서울 마포구", "outdoor": False},
    "L04": {"locationId": "L04", "name": "한강 둔치", "region": "서울 영등포구", "outdoor": True},
}

ACTORS = {
    "A01": {"actorId": "A01", "name": "윤재하", "dailyMaxHours": 12, "contractDocId": "contract-A01"},
    "A03": {"actorId": "A03", "name": "서하린", "dailyMaxHours": 12, "contractDocId": "contract-A03"},
    "A05": {"actorId": "A05", "name": "도민결", "dailyMaxHours": 10, "contractDocId": "contract-A05"},
}

EQUIPMENT = {"E01": "ARRI 카메라 세트", "E02": "크레인", "E03": "조명 세트 B", "E04": "드론"}

SCENES = {
    "S21": {"sceneId": "S21", "title": "남산 산책로 재회", "locationId": "L02", "indoor": False,
            "actorIds": ["A01", "A03"], "equipmentIds": ["E01", "E02"], "durationMin": 240},
    "S22": {"sceneId": "S22", "title": "카페 첫 대화", "locationId": "L03", "indoor": True,
            "actorIds": ["A01", "A03"], "equipmentIds": ["E01", "E03"], "durationMin": 180},
    "S23": {"sceneId": "S23", "title": "스튜디오 사무실 회의", "locationId": "L01", "indoor": True,
            "actorIds": ["A03", "A05"], "equipmentIds": ["E01", "E03"], "durationMin": 180},
    "S24": {"sceneId": "S24", "title": "남산 야경 독백", "locationId": "L02", "indoor": False,
            "actorIds": ["A03"], "equipmentIds": ["E01", "E04"], "durationMin": 120},
    "S25": {"sceneId": "S25", "title": "스튜디오 복도 추격", "locationId": "L01", "indoor": True,
            "actorIds": ["A01", "A05"], "equipmentIds": ["E01", "E02"], "durationMin": 180},
    "S26": {"sceneId": "S26", "title": "한강 자전거", "locationId": "L04", "indoor": False,
            "actorIds": ["A01"], "equipmentIds": ["E01", "E04"], "durationMin": 150},
}

# 기준(확정) 스케줄 12: 2026-11-12 ~ 2026-11-14
BASE_SCHEDULE_ID = 12
BASE_SLOTS = [
    {"date": "2026-11-12", "sceneId": "S21", "locationId": "L02", "start": "09:00", "end": "13:00", "equipmentIds": ["E01", "E02"]},
    {"date": "2026-11-12", "sceneId": "S24", "locationId": "L02", "start": "18:00", "end": "20:00", "equipmentIds": ["E01", "E04"]},
    {"date": "2026-11-13", "sceneId": "S22", "locationId": "L03", "start": "10:00", "end": "13:00", "equipmentIds": ["E01", "E03"]},
    {"date": "2026-11-13", "sceneId": "S23", "locationId": "L01", "start": "15:00", "end": "18:00", "equipmentIds": ["E01", "E03"]},
    {"date": "2026-11-14", "sceneId": "S25", "locationId": "L01", "start": "09:00", "end": "12:00", "equipmentIds": ["E01", "E02"]},
    {"date": "2026-11-14", "sceneId": "S26", "locationId": "L04", "start": "14:00", "end": "16:30", "equipmentIds": ["E01", "E04"]},
]

# 강수 확률(%). 남산은 11/12 비 예보 → 시연 시나리오 1
WEATHER = {
    ("L02", "2026-11-12"): {"rainProb": 80, "condition": "비"},
    ("L02", "2026-11-13"): {"rainProb": 10, "condition": "맑음"},
    ("L02", "2026-11-14"): {"rainProb": 20, "condition": "구름 많음"},
    ("L04", "2026-11-14"): {"rainProb": 30, "condition": "구름 많음"},
}
DEFAULT_WEATHER = {"rainProb": 10, "condition": "맑음"}
RAIN_THRESHOLD = 60  # OUTDOOR_RAIN 기준 (미결정 3, C가 확정)

# 배우 불가 시간 → 시연 시나리오 2
ACTOR_UNAVAILABLE = {
    ("A03", "2026-11-13"): [{"start": "14:00", "end": "18:00", "reason": "타 작품 촬영"}],
}
WORK_DAY = {"start": "07:00", "end": "23:00"}

PERMITS = {
    ("L02", "2026-11-12"): {"permitId": 301, "status": "APPROVED", "allowedStart": "08:00", "allowedEnd": "21:00"},
    ("L02", "2026-11-13"): {"permitId": 302, "status": "APPROVED", "allowedStart": "08:00", "allowedEnd": "21:00"},
    ("L02", "2026-11-14"): {"permitId": 303, "status": "REQUESTED", "allowedStart": "08:00", "allowedEnd": "18:00"},
    ("L04", "2026-11-14"): {"permitId": 304, "status": "APPROVED", "allowedStart": "10:00", "allowedEnd": "17:00"},
}

# 콜시트 수신자 (users.id)
USERS = {
    1: {"id": 1, "name": "PD 최가온", "role": "PD"},
    3: {"id": 3, "name": "조감독 남궁연", "role": "AD"},
    11: {"id": 11, "name": "윤재하", "role": "STAFF", "actorId": "A01"},
    13: {"id": 13, "name": "서하린", "role": "STAFF", "actorId": "A03"},
    15: {"id": 15, "name": "도민결", "role": "STAFF", "actorId": "A05"},
    21: {"id": 21, "name": "촬영감독 배시온", "role": "STAFF"},
}
