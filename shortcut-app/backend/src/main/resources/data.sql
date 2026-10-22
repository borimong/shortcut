-- 모든 서비스가 이 값을 전제로 테스트하므로 다시 실행해도 기존 행을 덮지 않는다.
INSERT INTO projects (id, name, block_budget_cap, crew_weekly_hours_used)
VALUES (1, '드라마 숏컷 7화', 1000000, 40)
ON CONFLICT DO NOTHING;

INSERT INTO shoot_days (id, project_id, shoot_date, call_time, data_version, notice, crew_calls)
VALUES (1, 1, CURRENT_DATE, '06:30', 1, '날씨가 바뀌면 알림으로 공지합니다.',
        '[{"team": "연출팀", "time": "06:30"}, {"team": "촬영팀", "time": "06:45"}, {"team": "조명팀", "time": "06:45"},
          {"team": "동시녹음팀", "time": "07:00"}, {"team": "미술팀", "time": "06:30"}]')
ON CONFLICT DO NOTHING;

-- 예보가 실시간으로 바뀌어 "13시 이후 비"가 맞지 않을 수 있으므로, 이미 만든 DB의 시드 공지도 같은 문구로 바꾼다.
UPDATE shoot_days SET notice = '날씨가 바뀌면 알림으로 공지합니다.'
WHERE id = 1 AND notice = '13시 이후 비 예보가 있습니다. 변동 시 알림으로 공지합니다.';

-- 2회차 촬영일은 1회차 다음 날이다. 자원 상태의 적용 기간(until_date)처럼 날짜를 넘나드는 기능을 확인하려고 둔다.
-- 촬영판은 오늘 이후 가장 가까운 촬영일을 고르므로 1회차가 오늘이면 그대로 1회차를 보여 준다.
INSERT INTO shoot_days (id, project_id, shoot_date, call_time, data_version, notice, crew_calls)
SELECT 2, 1, shoot_date + 1, '07:30', 1, '성수 스튜디오 실내 촬영입니다. 주차는 건물 뒤편을 이용합니다.',
       '[{"team": "연출팀", "time": "07:30"}, {"team": "촬영팀", "time": "07:45"}, {"team": "조명팀", "time": "07:45"},
         {"team": "동시녹음팀", "time": "08:00"}, {"team": "미술팀", "time": "07:30"}]'
FROM shoot_days WHERE id = 1
ON CONFLICT DO NOTHING;

-- 3회차는 1회차 이틀 뒤 오후·밤 촬영이다. 밤 야외 장면(S21, S22)을 합정 루프탑에서 찍어 낮/밤 대본 규칙과
-- 새 배우(배우 D, E)의 날짜별 일정이 실제 판정에 쓰이게 한다. 초기화는 n회차를 오늘 + (n - 1)일에 둔다.
INSERT INTO shoot_days (id, project_id, shoot_date, call_time, data_version, notice, crew_calls)
SELECT 3, 1, shoot_date + 2, '12:30', 1, '합정 루프탑 야간 촬영이 있습니다. 방한복을 챙기세요.',
       '[{"team": "연출팀", "time": "12:30"}, {"team": "촬영팀", "time": "12:45"}, {"team": "조명팀", "time": "12:45"},
         {"team": "동시녹음팀", "time": "13:00"}, {"team": "미술팀", "time": "12:30"}]'
FROM shoot_days WHERE id = 1
ON CONFLICT DO NOTHING;

-- 낮/밤 장면 판정에 쓰는 일출과 일몰이다. 서울 10월 하순 근사값이다.
UPDATE shoot_days SET sunrise = '06:50', sunset = '17:40' WHERE sunrise IS NULL;

INSERT INTO actors (id, name, available_from, available_to, weekly_hours_used, contract_doc_id, no_night, max_daily_hours, manager_phone)
VALUES (1, '배우 A', '09:00', '16:00', 44, 'contract-actor-a-v3', true, 10, '010-2481-7731'),
       (2, '배우 B', '07:00', '22:00', 38, 'contract-actor-b-v1', false, NULL, '010-3920-1184'),
       (3, '배우 C', '06:30', '20:00', 30, 'contract-actor-c-v2', false, NULL, '010-5512-0093'),
       (4, '배우 D', '10:00', '23:00', 12, 'contract-actor-d-v1', false, NULL, '010-4417-2208'),
       (5, '배우 E', '08:00', '19:00', 36, 'contract-actor-e-v1', true, 9, '010-6630-5521')
ON CONFLICT DO NOTHING;

INSERT INTO locations (id, name, address, indoor, region, open_from, open_to, permit_from, permit_to,
                       cost, no_fly_zone, fit, distance_km, note)
VALUES (1, '한강 공원', '서울 영등포구 여의도 한강공원', false, '서울 영등포구', '06:00', '22:00', '09:00', '17:00',
        300000, false, 0.95, 6, NULL),
       (2, '성수 스튜디오', '서울 성동구 성수동 스튜디오', true, '서울 성동구', '14:00', '18:00', NULL, NULL,
        450000, false, 0.80, 14, '평일 오후 인근 공사 소음 가능'),
       (3, '파주 세트장', '경기 파주시 세트장', true, '경기 파주시', '08:00', '20:00', NULL, NULL,
        600000, true, 0.70, 41, NULL),
       (4, '목동 오피스 세트', '서울 양천구 목동 오피스 세트', true, '서울 양천구', '06:00', '13:00', NULL, NULL,
        0, false, 1.00, 0, NULL),
       (5, '합정 루프탑', '서울 마포구 합정동 루프탑', false, '서울 마포구', '16:00', '23:00', '18:00', '23:00',
        280000, false, 0.90, 10, '주말 저녁 소음 민원 주의')
ON CONFLICT DO NOTHING;

INSERT INTO equipment (id, name, available, drone, cost)
VALUES (1, '카메라 패키지 A', true, false, 0),
       (2, '드론', true, true, 0),
       (3, '반사판', true, false, 0),
       (4, '추가 조명 패키지', true, false, 250000),
       (5, '짐벌 세트', true, false, 0)
ON CONFLICT DO NOTHING;

INSERT INTO blocks (shoot_day_id, code, start_time, end_time, duration_min, location_id, equipment_ids)
VALUES (1, 'AM', '07:00', '11:30', 270, 4, '[1]'),
       (1, 'PM', '13:00', '15:00', 120, 1, '[1, 2, 3]'),
       (2, 'AM', '08:00', '10:00', 120, 4, '[1]'),
       (2, 'PM', '14:00', '16:00', 120, 2, '[1, 5]'),
       (3, 'AM', '14:00', '16:00', 120, 3, '[1]'),
       (3, 'PM', '19:00', '21:00', 120, 5, '[1, 3]')
ON CONFLICT DO NOTHING;

-- 씬 배정(scenes)은 대본 씬을 외래키로 가리키므로 대본 시드 뒤에 도는 data-schedule.sql에 있다.

INSERT INTO plan_options (shoot_day_id, block_code, option_no, location_id, equipment_ids, equipment_fit, start_time, end_time)
VALUES (1, 'PM', 1, 1, '[1, 2, 3]', 1.00, '13:00', '15:00'),
       (1, 'PM', 2, 2, '[1, 4]', 0.75, '14:00', '16:00'),
       (1, 'PM', 3, 3, '[1, 5]', 0.60, '12:30', '14:30'),
       (2, 'PM', 1, 2, '[1, 5]', 1.00, '14:00', '16:00'),
       (2, 'PM', 2, 3, '[1, 5]', 0.80, '13:00', '15:00'),
       (2, 'PM', 3, 1, '[1, 3]', 0.60, '13:00', '15:00'),
       -- 3회차 밤 블록. 한강 공원은 야간 허가가 없어 2안이 늘 막히고, 파주 세트장은 밤 야외 장면을 실내 세트로 찍는 안이다.
       (3, 'PM', 1, 5, '[1, 3]', 1.00, '19:00', '21:00'),
       (3, 'PM', 2, 1, '[1, 4]', 0.70, '18:00', '20:00'),
       (3, 'PM', 3, 3, '[1, 4]', 0.60, '18:00', '20:00')
ON CONFLICT DO NOTHING;

INSERT INTO callsheet_versions (shoot_day_id, version_no, proposal_id, pm_location_id, pm_equipment_ids, pm_start, pm_end, pm_cost)
VALUES (1, 1, NULL, 1, '[1, 2, 3]', '13:00', '15:00', 300000),
       (2, 1, NULL, 2, '[1, 5]', '14:00', '16:00', 450000),
       (3, 1, NULL, 5, '[1, 3]', '19:00', '21:00', 280000)
ON CONFLICT DO NOTHING;

-- 한강 공원은 13시부터 시간당 8mm 비가 예보되어 있다(촬영 불가 기준 5mm 이상). 나머지 장소는 비가 오지 않는다.
INSERT INTO weather_forecasts (shoot_day_id, location_id, hour, precip_mm)
SELECT 1, l.id, h, CASE WHEN l.id = 1 AND h >= 13 THEN 8.0 WHEN l.id = 1 AND h = 12 THEN 0.5 ELSE 0 END
FROM locations l CROSS JOIN generate_series(6, 18) AS h
ON CONFLICT DO NOTHING;

-- 2회차에는 비가 오지 않는다.
INSERT INTO weather_forecasts (shoot_day_id, location_id, hour, precip_mm)
SELECT 2, l.id, h, 0
FROM locations l CROSS JOIN generate_series(6, 18) AS h
WHERE l.id < 100
ON CONFLICT DO NOTHING;

-- 3회차에도 비가 오지 않는다. 밤 블록(19~21시)이 있어 23시까지 둔다.
INSERT INTO weather_forecasts (shoot_day_id, location_id, hour, precip_mm)
SELECT 3, l.id, h, 0
FROM locations l CROSS JOIN generate_series(6, 23) AS h
WHERE l.id < 100
ON CONFLICT DO NOTHING;

-- 강수량 열을 추가하기 전에 만든 DB는 확률만 있으므로, 강수량이 하나도 없을 때만 같은 예보로 채운다.
UPDATE weather_forecasts SET precip_mm = CASE WHEN location_id = 1 AND hour >= 13 THEN 8.0
                                               WHEN location_id = 1 AND hour = 12 THEN 0.5 ELSE 0 END
WHERE shoot_day_id = 1 AND location_id < 100 AND source = 'SEED'
  AND NOT EXISTS (SELECT 1 FROM weather_forecasts WHERE precip_mm > 0 AND source = 'SEED');

INSERT INTO app_settings (id, max_loops, rain_block_mm, rain_warn_mm, rain_alert_lead_hours)
VALUES (1, 5, 5.0, 1.0, 3)
ON CONFLICT DO NOTHING;

-- 필수 승인자 기본값이다. 관리자가 지운 규칙이 재시작 때 되살아나지 않게 표가 비어 있을 때만 넣는다.
INSERT INTO approver_rules (change_kind, role)
SELECT v.change_kind, v.role
FROM (VALUES ('ALWAYS', 'DIRECTOR'),
             ('LOCATION', 'AD1'), ('LOCATION', 'SOUND'),
             ('EQUIPMENT', 'DOP'),
             ('TIME', 'AD1'), ('TIME', 'AD2'),
             ('SCENE', 'AD1'), ('SCENE', 'AD2'),
             ('COST', 'PRODUCER')) AS v (change_kind, role)
WHERE NOT EXISTS (SELECT 1 FROM approver_rules);

-- 씬 순서 변경(SCENE) 승인자는 나중에 생긴 종류라, 이미 규칙이 있는 DB에는 SCENE 규칙이 하나도 없을 때만 넣는다.
INSERT INTO approver_rules (change_kind, role)
SELECT 'SCENE', v.role
FROM (VALUES ('AD1'), ('AD2')) AS v (role)
WHERE NOT EXISTS (SELECT 1 FROM approver_rules WHERE change_kind = 'SCENE');

INSERT INTO reservations (id, shoot_day_id, location_id, start_time, end_time, status, provider)
VALUES ('R-2031', 1, 2, '14:00', '18:00', 'HELD', 'OURPLACE'),
       ('R-2032', 2, 2, '14:00', '18:00', 'HELD', 'OURPLACE'),
       ('R-2033', 3, 5, '18:00', '23:00', 'HELD', 'OURPLACE')
ON CONFLICT DO NOTHING;

INSERT INTO external_locations (id, name, indoor, region, distance_km, cost, keywords)
VALUES (1, '일산 실내 스튜디오', true, '경기 고양시', 25, 380000, '["실내", "자연광", "30평"]'),
       (2, '상암 호리존 스튜디오', true, '서울 마포구', 10, 520000, '["실내", "호리존", "방음"]'),
       (3, '김포 창고 스튜디오', true, '경기 김포시', 30, 320000, '["실내", "창고", "넓은 공간"]'),
       (4, '하남 카페 세트', true, '경기 하남시', 35, 350000, '["실내", "자연광", "카페"]'),
       (5, '망원 루프탑', false, '서울 마포구', 9, 280000, '["야외", "루프탑", "도심 야경"]')
ON CONFLICT DO NOTHING;

-- 날씨 API에 넘길 위경도다. 시드 주소가 동네 수준이라 동네 중심 좌표를 쓴다.
-- 위경도 열을 나중에 추가했으므로 INSERT가 아니라 UPDATE로 넣고, 이미 고친 좌표는 덮지 않는다.
UPDATE locations l SET latitude = v.lat, longitude = v.lng
FROM (VALUES (1, 37.52830, 126.93260), (2, 37.54460, 127.05570), (3, 37.75990, 126.78020), (4, 37.52640, 126.87520),
             (5, 37.54960, 126.91380))
         AS v (id, lat, lng)
WHERE l.id = v.id AND l.latitude IS NULL;

UPDATE external_locations e SET latitude = v.lat, longitude = v.lng
FROM (VALUES (1, 37.65840, 126.77000), (2, 37.57900, 126.88950), (3, 37.61530, 126.71560), (4, 37.53930, 127.21490),
             (5, 37.55600, 126.90500))
         AS v (id, lat, lng)
WHERE e.id = v.id AND e.latitude IS NULL;

-- 좌표 열을 넣기 전에 등록된 4안 장소(id = 100 + 카탈로그 id)도 카탈로그 좌표를 받는다.
UPDATE locations l SET latitude = e.latitude, longitude = e.longitude
FROM external_locations e
WHERE l.id = 100 + e.id AND l.latitude IS NULL;

-- 온톨로지 노드는 업무 테이블 행을 TYPE:키 글자로 가리킨다. 촬영일은 SHOOT_DAY:<id>, 블록은 BLOCK:<촬영일>-<코드>,
-- 안은 PLAN:<촬영일>-<번호>(Agent가 만드는 4안은 PLAN:<촬영일>-4)다. 기동할 때 업무 행이 없는 노드를 찾아 경고한다.
-- 씬 노드는 Agent가 다시 짜는 오후 블록의 씬만 둔다. 오전 블록은 블록 노드 하나로 장소와 장비만 잇는다.
INSERT INTO ontology_nodes (node_id, type, label, props)
VALUES ('SCENE:S12', 'SCENE', 'S12 한강 산책 대화', '{"code": "S12", "shootDayId": 1, "block": "PM", "durationMin": 90, "intExt": "EXT", "timeOfDay": "DAY"}'),
       ('SCENE:S13', 'SCENE', 'S13 강변 인서트', '{"code": "S13", "shootDayId": 1, "block": "PM", "durationMin": 30, "intExt": "EXT", "timeOfDay": "DAY"}'),
       ('SCENE:S18', 'SCENE', 'S18 작업실 대화', '{"code": "S18", "shootDayId": 2, "block": "PM", "durationMin": 90, "intExt": "INT", "timeOfDay": "DAY"}'),
       ('SCENE:S19', 'SCENE', 'S19 작업실 인서트', '{"code": "S19", "shootDayId": 2, "block": "PM", "durationMin": 30, "intExt": "INT", "timeOfDay": "DAY"}'),
       ('ACTOR:1', 'ACTOR', '배우 A', '{"availableFrom": "09:00", "availableTo": "16:00", "weeklyHoursUsed": 44, "noNight": true, "maxDailyHours": 10}'),
       ('ACTOR:2', 'ACTOR', '배우 B', '{"availableFrom": "07:00", "availableTo": "22:00", "weeklyHoursUsed": 38}'),
       ('ACTOR:3', 'ACTOR', '배우 C', '{"availableFrom": "06:30", "availableTo": "20:00", "weeklyHoursUsed": 30}'),
       ('LOCATION:1', 'LOCATION', '한강 공원', '{"indoor": false, "region": "서울 영등포구", "permit": "09:00~17:00", "cost": 300000}'),
       ('LOCATION:2', 'LOCATION', '성수 스튜디오', '{"indoor": true, "region": "서울 성동구", "open": "14:00~18:00", "cost": 450000, "note": "평일 오후 인근 공사 소음 가능"}'),
       ('LOCATION:3', 'LOCATION', '파주 세트장', '{"indoor": true, "region": "경기 파주시", "noFlyZone": true, "cost": 600000}'),
       ('LOCATION:4', 'LOCATION', '목동 오피스 세트', '{"indoor": true, "region": "서울 양천구", "cost": 0}'),
       ('EQUIPMENT:1', 'EQUIPMENT', '카메라 패키지 A', '{"cost": 0}'),
       ('EQUIPMENT:2', 'EQUIPMENT', '드론', '{"cost": 0, "drone": true}'),
       ('EQUIPMENT:3', 'EQUIPMENT', '반사판', '{"cost": 0}'),
       ('EQUIPMENT:4', 'EQUIPMENT', '추가 조명 패키지', '{"cost": 250000}'),
       ('EQUIPMENT:5', 'EQUIPMENT', '짐벌 세트', '{"cost": 0}'),
       ('CONTRACT:contract-actor-a-v3', 'CONTRACT', '배우 A 출연 계약서 v3', '{"docId": "contract-actor-a-v3"}'),
       ('CONTRACT:contract-actor-b-v1', 'CONTRACT', '배우 B 출연 계약서 v1', '{"docId": "contract-actor-b-v1"}'),
       ('CONTRACT:contract-actor-c-v2', 'CONTRACT', '배우 C 출연 계약서 v2', '{"docId": "contract-actor-c-v2"}'),
       ('STAFF:manager-a', 'STAFF', '배우 A 매니저', '{"role": "매니저", "phone": "010-2481-7731"}'),
       ('CONSTRAINT:no-night', 'CONSTRAINT', '야간 촬영 불가', '{"rule": "22시 이후 촬영 불가", "ruleRef": "CONTRACT_NIGHT"}'),
       ('RESERVATION:R-2031', 'RESERVATION', '성수 스튜디오 가예약 R-2031', '{"shootDayId": 1, "status": "HELD", "window": "14:00~18:00", "provider": "아워플레이스"}'),
       ('RESERVATION:R-2032', 'RESERVATION', '성수 스튜디오 가예약 R-2032', '{"shootDayId": 2, "status": "HELD", "window": "14:00~18:00", "provider": "아워플레이스"}'),
       ('PLAN:1-1', 'PLAN', '1회차 PM 1안', '{"shootDayId": 1, "optionNo": 1, "time": "13:00~15:00", "equipment": [1, 2, 3]}'),
       ('PLAN:1-2', 'PLAN', '1회차 PM 2안', '{"shootDayId": 1, "optionNo": 2, "time": "14:00~16:00", "equipment": [1, 4]}'),
       ('PLAN:1-3', 'PLAN', '1회차 PM 3안', '{"shootDayId": 1, "optionNo": 3, "time": "12:30~14:30", "equipment": [1, 5]}'),
       ('PLAN:2-1', 'PLAN', '2회차 PM 1안', '{"shootDayId": 2, "optionNo": 1, "time": "14:00~16:00", "equipment": [1, 5]}'),
       ('PLAN:2-2', 'PLAN', '2회차 PM 2안', '{"shootDayId": 2, "optionNo": 2, "time": "13:00~15:00", "equipment": [1, 5]}'),
       ('PLAN:2-3', 'PLAN', '2회차 PM 3안', '{"shootDayId": 2, "optionNo": 3, "time": "13:00~15:00", "equipment": [1, 3]}'),
       ('SHOOT_DAY:1', 'SHOOT_DAY', '1회차 촬영일', '{"shootDayId": 1}'),
       ('SHOOT_DAY:2', 'SHOOT_DAY', '2회차 촬영일', '{"shootDayId": 2}'),
       ('BLOCK:1-AM', 'BLOCK', '1회차 오전 블록', '{"shootDayId": 1, "code": "AM"}'),
       ('BLOCK:1-PM', 'BLOCK', '1회차 오후 블록', '{"shootDayId": 1, "code": "PM"}'),
       ('BLOCK:2-AM', 'BLOCK', '2회차 오전 블록', '{"shootDayId": 2, "code": "AM"}'),
       ('BLOCK:2-PM', 'BLOCK', '2회차 오후 블록', '{"shootDayId": 2, "code": "PM"}'),
       -- 3회차(밤 촬영), 새 배우와 장소
       ('SHOOT_DAY:3', 'SHOOT_DAY', '3회차 촬영일', '{"shootDayId": 3}'),
       ('BLOCK:3-AM', 'BLOCK', '3회차 첫 블록', '{"shootDayId": 3, "code": "AM"}'),
       ('BLOCK:3-PM', 'BLOCK', '3회차 밤 블록', '{"shootDayId": 3, "code": "PM"}'),
       ('SCENE:S21', 'SCENE', 'S21 루프탑 소문', '{"code": "S21", "shootDayId": 3, "block": "PM", "durationMin": 90, "intExt": "EXT", "timeOfDay": "NIGHT"}'),
       ('SCENE:S22', 'SCENE', 'S22 루프탑 야경 인서트', '{"code": "S22", "shootDayId": 3, "block": "PM", "durationMin": 30, "intExt": "EXT", "timeOfDay": "NIGHT"}'),
       ('PLAN:3-1', 'PLAN', '3회차 PM 1안', '{"shootDayId": 3, "optionNo": 1, "time": "19:00~21:00", "equipment": [1, 3]}'),
       ('PLAN:3-2', 'PLAN', '3회차 PM 2안', '{"shootDayId": 3, "optionNo": 2, "time": "18:00~20:00", "equipment": [1, 4]}'),
       ('PLAN:3-3', 'PLAN', '3회차 PM 3안', '{"shootDayId": 3, "optionNo": 3, "time": "18:00~20:00", "equipment": [1, 4]}'),
       ('RESERVATION:R-2033', 'RESERVATION', '합정 루프탑 가예약 R-2033', '{"shootDayId": 3, "status": "HELD", "window": "18:00~23:00", "provider": "아워플레이스"}'),
       ('ACTOR:4', 'ACTOR', '배우 D', '{"availableFrom": "10:00", "availableTo": "23:00", "weeklyHoursUsed": 12}'),
       ('ACTOR:5', 'ACTOR', '배우 E', '{"availableFrom": "08:00", "availableTo": "19:00", "weeklyHoursUsed": 36, "noNight": true, "maxDailyHours": 9}'),
       ('CONTRACT:contract-actor-d-v1', 'CONTRACT', '배우 D 출연 계약서 v1', '{"docId": "contract-actor-d-v1"}'),
       ('CONTRACT:contract-actor-e-v1', 'CONTRACT', '배우 E 출연 계약서 v1', '{"docId": "contract-actor-e-v1"}'),
       ('LOCATION:5', 'LOCATION', '합정 루프탑', '{"indoor": false, "region": "서울 마포구", "permit": "18:00~23:00", "cost": 280000, "note": "주말 저녁 소음 민원 주의"}'),
       -- 대본의 배역. 배역 id는 characters.id이고 누가 연기하는지는 캐스팅 엣지로 잇는다.
       ('CHARACTER:1', 'CHARACTER', '봉지우 (배역)', '{"kind": "LEAD"}'),
       ('CHARACTER:2', 'CHARACTER', '강도현 (배역)', '{"kind": "LEAD"}'),
       ('CHARACTER:3', 'CHARACTER', '봉재필 대표 (배역)', '{"kind": "SUPPORT"}'),
       ('CHARACTER:4', 'CHARACTER', '문태 (배역)', '{"kind": "SUPPORT"}'),
       ('CHARACTER:5', 'CHARACTER', '구 노무사 (배역)', '{"kind": "SUPPORT"}')
ON CONFLICT DO NOTHING;

-- 대본 씬 정보를 더하기 전에 만든 씬 노드에도 실내/실외와 낮/밤을 붙인다. 야외 의도(outdoorIntent)는 intExt로 바뀌었다.
UPDATE ontology_nodes SET props = (props - 'outdoorIntent') || v.extra
FROM (VALUES ('SCENE:S12', CAST('{"intExt": "EXT", "timeOfDay": "DAY"}' AS jsonb)),
             ('SCENE:S13', CAST('{"intExt": "EXT", "timeOfDay": "DAY"}' AS jsonb)),
             ('SCENE:S18', CAST('{"intExt": "INT", "timeOfDay": "DAY"}' AS jsonb)),
             ('SCENE:S19', CAST('{"intExt": "INT", "timeOfDay": "DAY"}' AS jsonb))) AS v (node_id, extra)
WHERE ontology_nodes.node_id = v.node_id AND ontology_nodes.props ->> 'intExt' IS NULL;

-- 위 INSERT는 이미 있는 노드를 덮지 않으므로, 2회차가 생기기 전에 만든 DB에도 촬영일 표시를 더한다.
-- S18은 "다음 촬영일"에서 2회차 오후 블록으로 옮겨졌다.
UPDATE ontology_nodes SET props = props || '{"shootDayId": 1}'
WHERE node_id IN ('SCENE:S12', 'SCENE:S13', 'RESERVATION:R-2031', 'PLAN:1', 'PLAN:2', 'PLAN:3')
  AND props ->> 'shootDayId' IS NULL;
UPDATE ontology_nodes SET props = props || '{"shootDayId": 2, "block": "PM"}'
WHERE node_id = 'SCENE:S18' AND props ->> 'shootDayId' IS NULL;

-- 안 노드 ID에 촬영일을 붙이기 전(PLAN:1~4)에 만든 DB를 PLAN:<촬영일>-<번호>로 옮긴다.
-- 엣지가 노드를 외래키로 가리키므로 새 노드를 넣고, 엣지를 옮기고, 옛 노드를 지운다.
-- 옛 1/2/3안은 위에서 붙인 촬영일을 쓰고, 촬영일 표시가 없던 4안은 대체 장소를 등록한 촬영일을 쓴다.
UPDATE ontology_nodes
SET props = props || jsonb_build_object('shootDayId', COALESCE((SELECT min(shoot_day_id) FROM shoot_day_alternatives), 1))
WHERE node_id ~ '^PLAN:[0-9]+$' AND props ->> 'shootDayId' IS NULL;
INSERT INTO ontology_nodes (node_id, type, label, props)
SELECT 'PLAN:' || (props ->> 'shootDayId') || '-' || substr(node_id, 6), type, label,
       props || jsonb_build_object('optionNo', CAST(substr(node_id, 6) AS integer))
FROM ontology_nodes WHERE node_id ~ '^PLAN:[0-9]+$'
ON CONFLICT DO NOTHING;
UPDATE ontology_edges e SET src = 'PLAN:' || (n.props ->> 'shootDayId') || '-' || substr(n.node_id, 6)
FROM ontology_nodes n
WHERE n.node_id = e.src AND n.node_id ~ '^PLAN:[0-9]+$'
  AND NOT EXISTS (SELECT 1 FROM ontology_edges d
                  WHERE d.src = 'PLAN:' || (n.props ->> 'shootDayId') || '-' || substr(n.node_id, 6)
                    AND d.relation = e.relation AND d.dst = e.dst);
UPDATE ontology_edges e SET dst = 'PLAN:' || (n.props ->> 'shootDayId') || '-' || substr(n.node_id, 6)
FROM ontology_nodes n
WHERE n.node_id = e.dst AND n.node_id ~ '^PLAN:[0-9]+$'
  AND NOT EXISTS (SELECT 1 FROM ontology_edges d
                  WHERE d.dst = 'PLAN:' || (n.props ->> 'shootDayId') || '-' || substr(n.node_id, 6)
                    AND d.relation = e.relation AND d.src = e.src);
DELETE FROM ontology_edges WHERE src ~ '^PLAN:[0-9]+$' OR dst ~ '^PLAN:[0-9]+$';
DELETE FROM ontology_nodes WHERE node_id ~ '^PLAN:[0-9]+$';
-- 4안을 오후 블록의 후보로 잇기 전에 만든 4안도 PlanRepository.registerAlternative처럼 블록에 잇는다.
INSERT INTO ontology_edges (src, relation, dst, created_by)
SELECT b.node_id, '후보', p.node_id, 'agent'
FROM ontology_nodes p JOIN ontology_nodes b ON b.node_id = 'BLOCK:' || (p.props ->> 'shootDayId') || '-PM'
WHERE p.node_id ~ '^PLAN:[0-9]+-4$'
ON CONFLICT DO NOTHING;

INSERT INTO ontology_edges (src, relation, dst, created_by)
VALUES ('SCENE:S12', '출연', 'ACTOR:1', 'seed'),
       ('SCENE:S12', '출연', 'ACTOR:2', 'seed'),
       ('SCENE:S13', '출연', 'ACTOR:1', 'seed'),
       ('SCENE:S12', '촬영지', 'LOCATION:1', 'seed'),
       ('ACTOR:1', '계약', 'CONTRACT:contract-actor-a-v3', 'seed'),
       ('ACTOR:1', '소속', 'STAFF:manager-a', 'seed'),
       ('ACTOR:1', '제약', 'CONSTRAINT:no-night', 'seed'),
       ('SCENE:S18', '출연', 'ACTOR:2', 'seed'),
       ('SCENE:S18', '촬영지', 'LOCATION:2', 'seed'),
       ('LOCATION:2', '예약', 'RESERVATION:R-2031', 'seed'),
       ('PLAN:1-1', '포함', 'LOCATION:1', 'seed'),
       ('PLAN:1-2', '포함', 'LOCATION:2', 'seed'),
       ('PLAN:1-3', '포함', 'LOCATION:3', 'seed'),
       ('ACTOR:2', '계약', 'CONTRACT:contract-actor-b-v1', 'seed'),
       ('ACTOR:3', '계약', 'CONTRACT:contract-actor-c-v2', 'seed')
ON CONFLICT DO NOTHING;

-- 1/2/3안이 쓰는 장비 (plan_options.equipment_ids)
INSERT INTO ontology_edges (src, relation, dst, created_by)
VALUES ('PLAN:1-1', '사용', 'EQUIPMENT:1', 'seed'),
       ('PLAN:1-1', '사용', 'EQUIPMENT:2', 'seed'),
       ('PLAN:1-1', '사용', 'EQUIPMENT:3', 'seed'),
       ('PLAN:1-2', '사용', 'EQUIPMENT:1', 'seed'),
       ('PLAN:1-2', '사용', 'EQUIPMENT:4', 'seed'),
       ('PLAN:1-3', '사용', 'EQUIPMENT:1', 'seed'),
       ('PLAN:1-3', '사용', 'EQUIPMENT:5', 'seed')
ON CONFLICT DO NOTHING;

-- 2회차 1/2/3안의 장소와 장비 (plan_options shoot_day_id = 2)
INSERT INTO ontology_edges (src, relation, dst, created_by)
VALUES ('PLAN:2-1', '포함', 'LOCATION:2', 'seed'),
       ('PLAN:2-2', '포함', 'LOCATION:3', 'seed'),
       ('PLAN:2-3', '포함', 'LOCATION:1', 'seed'),
       ('PLAN:2-1', '사용', 'EQUIPMENT:1', 'seed'),
       ('PLAN:2-1', '사용', 'EQUIPMENT:5', 'seed'),
       ('PLAN:2-2', '사용', 'EQUIPMENT:1', 'seed'),
       ('PLAN:2-2', '사용', 'EQUIPMENT:5', 'seed'),
       ('PLAN:2-3', '사용', 'EQUIPMENT:1', 'seed'),
       ('PLAN:2-3', '사용', 'EQUIPMENT:3', 'seed')
ON CONFLICT DO NOTHING;

-- 씬의 장소와 배우 (scenes.location_id, 등장 배역의 캐스팅). 장소가 비어 있는 씬은 블록 장소에서 찍는다.
INSERT INTO ontology_edges (src, relation, dst, created_by)
VALUES ('SCENE:S13', '촬영지', 'LOCATION:1', 'seed'),
       ('SCENE:S18', '출연', 'ACTOR:3', 'seed'),
       ('SCENE:S19', '출연', 'ACTOR:2', 'seed'),
       ('SCENE:S19', '촬영지', 'LOCATION:2', 'seed'),
       ('LOCATION:2', '예약', 'RESERVATION:R-2032', 'seed')
ON CONFLICT DO NOTHING;

-- 촬영일이 블록을, 블록이 씬을 포함한다. 영향 분석이 씬, 블록, 촬영일 순으로 이어진다.
INSERT INTO ontology_edges (src, relation, dst, created_by)
VALUES ('SHOOT_DAY:1', '포함', 'BLOCK:1-AM', 'seed'),
       ('SHOOT_DAY:1', '포함', 'BLOCK:1-PM', 'seed'),
       ('SHOOT_DAY:2', '포함', 'BLOCK:2-AM', 'seed'),
       ('SHOOT_DAY:2', '포함', 'BLOCK:2-PM', 'seed'),
       ('BLOCK:1-PM', '포함', 'SCENE:S12', 'seed'),
       ('BLOCK:1-PM', '포함', 'SCENE:S13', 'seed'),
       ('BLOCK:2-PM', '포함', 'SCENE:S18', 'seed'),
       ('BLOCK:2-PM', '포함', 'SCENE:S19', 'seed')
ON CONFLICT DO NOTHING;

-- 블록의 장소와 장비 (blocks.location_id, equipment_ids의 시드 값)
INSERT INTO ontology_edges (src, relation, dst, created_by)
VALUES ('BLOCK:1-AM', '촬영지', 'LOCATION:4', 'seed'),
       ('BLOCK:1-AM', '사용', 'EQUIPMENT:1', 'seed'),
       ('BLOCK:1-PM', '촬영지', 'LOCATION:1', 'seed'),
       ('BLOCK:1-PM', '사용', 'EQUIPMENT:1', 'seed'),
       ('BLOCK:1-PM', '사용', 'EQUIPMENT:2', 'seed'),
       ('BLOCK:1-PM', '사용', 'EQUIPMENT:3', 'seed'),
       ('BLOCK:2-AM', '촬영지', 'LOCATION:4', 'seed'),
       ('BLOCK:2-AM', '사용', 'EQUIPMENT:1', 'seed'),
       ('BLOCK:2-PM', '촬영지', 'LOCATION:2', 'seed'),
       ('BLOCK:2-PM', '사용', 'EQUIPMENT:1', 'seed'),
       ('BLOCK:2-PM', '사용', 'EQUIPMENT:5', 'seed')
ON CONFLICT DO NOTHING;

-- 블록의 후보안 (plan_options.shoot_day_id, block_code)
INSERT INTO ontology_edges (src, relation, dst, created_by)
VALUES ('BLOCK:1-PM', '후보', 'PLAN:1-1', 'seed'),
       ('BLOCK:1-PM', '후보', 'PLAN:1-2', 'seed'),
       ('BLOCK:1-PM', '후보', 'PLAN:1-3', 'seed'),
       ('BLOCK:2-PM', '후보', 'PLAN:2-1', 'seed'),
       ('BLOCK:2-PM', '후보', 'PLAN:2-2', 'seed'),
       ('BLOCK:2-PM', '후보', 'PLAN:2-3', 'seed')
ON CONFLICT DO NOTHING;

-- 씬의 요구 장비(scene_requirements의 EQUIPMENT 가운데 카메라 패키지를 뺀 것)다. 필수는 MUST, 선호는 WANT다.
-- 예전 시드의 SCENE:S12 사용 EQUIPMENT:2, 3은 선호로 옮긴다.
DELETE FROM ontology_edges WHERE src = 'SCENE:S12' AND relation = '사용' AND dst IN ('EQUIPMENT:2', 'EQUIPMENT:3')
                             AND created_by = 'seed';
INSERT INTO ontology_edges (src, relation, dst, created_by)
VALUES ('SCENE:S12', '선호', 'EQUIPMENT:2', 'seed'),
       ('SCENE:S12', '선호', 'EQUIPMENT:3', 'seed'),
       ('SCENE:S18', '선호', 'EQUIPMENT:5', 'seed'),
       ('SCENE:S21', '선호', 'EQUIPMENT:3', 'seed')
ON CONFLICT DO NOTHING;

-- 3회차: 촬영일 → 블록 → 씬, 블록의 장소·장비·후보안, 1/2/3안의 장소·장비, 씬의 배우와 장소
INSERT INTO ontology_edges (src, relation, dst, created_by)
VALUES ('SHOOT_DAY:3', '포함', 'BLOCK:3-AM', 'seed'),
       ('SHOOT_DAY:3', '포함', 'BLOCK:3-PM', 'seed'),
       ('BLOCK:3-PM', '포함', 'SCENE:S21', 'seed'),
       ('BLOCK:3-PM', '포함', 'SCENE:S22', 'seed'),
       ('BLOCK:3-AM', '촬영지', 'LOCATION:3', 'seed'),
       ('BLOCK:3-AM', '사용', 'EQUIPMENT:1', 'seed'),
       ('BLOCK:3-PM', '촬영지', 'LOCATION:5', 'seed'),
       ('BLOCK:3-PM', '사용', 'EQUIPMENT:1', 'seed'),
       ('BLOCK:3-PM', '사용', 'EQUIPMENT:3', 'seed'),
       ('BLOCK:3-PM', '후보', 'PLAN:3-1', 'seed'),
       ('BLOCK:3-PM', '후보', 'PLAN:3-2', 'seed'),
       ('BLOCK:3-PM', '후보', 'PLAN:3-3', 'seed'),
       ('PLAN:3-1', '포함', 'LOCATION:5', 'seed'),
       ('PLAN:3-2', '포함', 'LOCATION:1', 'seed'),
       ('PLAN:3-3', '포함', 'LOCATION:3', 'seed'),
       ('PLAN:3-1', '사용', 'EQUIPMENT:1', 'seed'),
       ('PLAN:3-1', '사용', 'EQUIPMENT:3', 'seed'),
       ('PLAN:3-2', '사용', 'EQUIPMENT:1', 'seed'),
       ('PLAN:3-2', '사용', 'EQUIPMENT:4', 'seed'),
       ('PLAN:3-3', '사용', 'EQUIPMENT:1', 'seed'),
       ('PLAN:3-3', '사용', 'EQUIPMENT:4', 'seed'),
       ('SCENE:S21', '출연', 'ACTOR:2', 'seed'),
       ('SCENE:S21', '출연', 'ACTOR:4', 'seed'),
       ('SCENE:S22', '출연', 'ACTOR:4', 'seed'),
       ('SCENE:S21', '촬영지', 'LOCATION:5', 'seed'),
       ('SCENE:S22', '촬영지', 'LOCATION:5', 'seed'),
       ('LOCATION:5', '예약', 'RESERVATION:R-2033', 'seed'),
       ('ACTOR:4', '계약', 'CONTRACT:contract-actor-d-v1', 'seed'),
       ('ACTOR:5', '계약', 'CONTRACT:contract-actor-e-v1', 'seed')
ON CONFLICT DO NOTHING;

-- 배역: 씬에 등장하는 배역과 배역을 연기하는 배우(characters.actor_id). 오전 블록 씬은 아래 묶음에 있다.
INSERT INTO ontology_edges (src, relation, dst, created_by)
VALUES ('SCENE:S12', '등장', 'CHARACTER:1', 'seed'),
       ('SCENE:S12', '등장', 'CHARACTER:2', 'seed'),
       ('SCENE:S13', '등장', 'CHARACTER:1', 'seed'),
       ('SCENE:S18', '등장', 'CHARACTER:2', 'seed'),
       ('SCENE:S18', '등장', 'CHARACTER:3', 'seed'),
       ('SCENE:S19', '등장', 'CHARACTER:2', 'seed'),
       ('SCENE:S21', '등장', 'CHARACTER:2', 'seed'),
       ('SCENE:S21', '등장', 'CHARACTER:4', 'seed'),
       ('SCENE:S22', '등장', 'CHARACTER:4', 'seed'),
       ('CHARACTER:1', '캐스팅', 'ACTOR:1', 'seed'),
       ('CHARACTER:2', '캐스팅', 'ACTOR:2', 'seed'),
       ('CHARACTER:3', '캐스팅', 'ACTOR:3', 'seed'),
       ('CHARACTER:4', '캐스팅', 'ACTOR:4', 'seed'),
       ('CHARACTER:5', '캐스팅', 'ACTOR:5', 'seed')
ON CONFLICT DO NOTHING;

-- 오전 블록 씬(scenes 배정 시드의 AM 씬). 씬 노드가 오후 씬에만 있어 배우 일정이 오전 씬에 닿는지 그래프로 찾을 수 없었다.
-- 세트 고정 씬이 아니므로 씬 → 장소(촬영지) 엣지는 두지 않고, 장소는 블록의 촬영지로 따라간다.
INSERT INTO ontology_nodes (node_id, type, label, props)
VALUES ('SCENE:S01', 'SCENE', 'S01 출근길 로비', '{"code": "S01", "shootDayId": 1, "block": "AM", "durationMin": 30, "intExt": "INT", "timeOfDay": "DAY"}'),
       ('SCENE:S02', 'SCENE', 'S02 회의실 브리핑', '{"code": "S02", "shootDayId": 1, "block": "AM", "durationMin": 35, "intExt": "INT", "timeOfDay": "DAY"}'),
       ('SCENE:S03', 'SCENE', 'S03 탕비실 대화', '{"code": "S03", "shootDayId": 1, "block": "AM", "durationMin": 30, "intExt": "INT", "timeOfDay": "DAY"}'),
       ('SCENE:S04', 'SCENE', 'S04 복도 통화', '{"code": "S04", "shootDayId": 1, "block": "AM", "durationMin": 30, "intExt": "INT", "timeOfDay": "DAY"}'),
       ('SCENE:S05', 'SCENE', 'S05 팀장실 면담', '{"code": "S05", "shootDayId": 1, "block": "AM", "durationMin": 40, "intExt": "INT", "timeOfDay": "DAY"}'),
       ('SCENE:S06', 'SCENE', 'S06 사무실 언쟁', '{"code": "S06", "shootDayId": 1, "block": "AM", "durationMin": 35, "intExt": "INT", "timeOfDay": "DAY"}'),
       ('SCENE:S07', 'SCENE', 'S07 엘리베이터 침묵', '{"code": "S07", "shootDayId": 1, "block": "AM", "durationMin": 35, "intExt": "INT", "timeOfDay": "DAY"}'),
       ('SCENE:S08', 'SCENE', 'S08 퇴근 준비', '{"code": "S08", "shootDayId": 1, "block": "AM", "durationMin": 35, "intExt": "INT", "timeOfDay": "DAY"}'),
       ('SCENE:S14', 'SCENE', 'S14 편집실 회의', '{"code": "S14", "shootDayId": 2, "block": "AM", "durationMin": 60, "intExt": "INT", "timeOfDay": "DAY"}'),
       ('SCENE:S15', 'SCENE', 'S15 복도 재회', '{"code": "S15", "shootDayId": 2, "block": "AM", "durationMin": 60, "intExt": "INT", "timeOfDay": "DAY"}'),
       ('SCENE:S16', 'SCENE', 'S16 노무사 상담', '{"code": "S16", "shootDayId": 3, "block": "AM", "durationMin": 90, "intExt": "INT", "timeOfDay": "DAY"}'),
       ('SCENE:S17', 'SCENE', 'S17 노무사 복도 통화', '{"code": "S17", "shootDayId": 3, "block": "AM", "durationMin": 30, "intExt": "INT", "timeOfDay": "DAY"}')
ON CONFLICT DO NOTHING;

-- 오전 블록이 씬을 포함하고, 씬에 배역이 등장하며, 그 배역을 연기하는 배우가 출연한다(scene_characters, 캐스팅 시드).
INSERT INTO ontology_edges (src, relation, dst, created_by)
VALUES ('BLOCK:1-AM', '포함', 'SCENE:S01', 'seed'),
       ('BLOCK:1-AM', '포함', 'SCENE:S02', 'seed'),
       ('BLOCK:1-AM', '포함', 'SCENE:S03', 'seed'),
       ('BLOCK:1-AM', '포함', 'SCENE:S04', 'seed'),
       ('BLOCK:1-AM', '포함', 'SCENE:S05', 'seed'),
       ('BLOCK:1-AM', '포함', 'SCENE:S06', 'seed'),
       ('BLOCK:1-AM', '포함', 'SCENE:S07', 'seed'),
       ('BLOCK:1-AM', '포함', 'SCENE:S08', 'seed'),
       ('BLOCK:2-AM', '포함', 'SCENE:S14', 'seed'),
       ('BLOCK:2-AM', '포함', 'SCENE:S15', 'seed'),
       ('BLOCK:3-AM', '포함', 'SCENE:S16', 'seed'),
       ('BLOCK:3-AM', '포함', 'SCENE:S17', 'seed'),
       ('SCENE:S01', '등장', 'CHARACTER:2', 'seed'), ('SCENE:S01', '등장', 'CHARACTER:3', 'seed'),
       ('SCENE:S02', '등장', 'CHARACTER:2', 'seed'), ('SCENE:S02', '등장', 'CHARACTER:3', 'seed'),
       ('SCENE:S03', '등장', 'CHARACTER:2', 'seed'), ('SCENE:S03', '등장', 'CHARACTER:3', 'seed'),
       ('SCENE:S04', '등장', 'CHARACTER:2', 'seed'), ('SCENE:S04', '등장', 'CHARACTER:3', 'seed'),
       ('SCENE:S05', '등장', 'CHARACTER:2', 'seed'), ('SCENE:S05', '등장', 'CHARACTER:3', 'seed'),
       ('SCENE:S06', '등장', 'CHARACTER:2', 'seed'), ('SCENE:S06', '등장', 'CHARACTER:3', 'seed'),
       ('SCENE:S07', '등장', 'CHARACTER:2', 'seed'), ('SCENE:S07', '등장', 'CHARACTER:3', 'seed'),
       ('SCENE:S08', '등장', 'CHARACTER:2', 'seed'), ('SCENE:S08', '등장', 'CHARACTER:3', 'seed'),
       ('SCENE:S14', '등장', 'CHARACTER:2', 'seed'), ('SCENE:S14', '등장', 'CHARACTER:3', 'seed'),
       ('SCENE:S15', '등장', 'CHARACTER:3', 'seed'),
       ('SCENE:S16', '등장', 'CHARACTER:2', 'seed'), ('SCENE:S16', '등장', 'CHARACTER:5', 'seed'),
       ('SCENE:S17', '등장', 'CHARACTER:5', 'seed'),
       ('SCENE:S01', '출연', 'ACTOR:2', 'seed'), ('SCENE:S01', '출연', 'ACTOR:3', 'seed'),
       ('SCENE:S02', '출연', 'ACTOR:2', 'seed'), ('SCENE:S02', '출연', 'ACTOR:3', 'seed'),
       ('SCENE:S03', '출연', 'ACTOR:2', 'seed'), ('SCENE:S03', '출연', 'ACTOR:3', 'seed'),
       ('SCENE:S04', '출연', 'ACTOR:2', 'seed'), ('SCENE:S04', '출연', 'ACTOR:3', 'seed'),
       ('SCENE:S05', '출연', 'ACTOR:2', 'seed'), ('SCENE:S05', '출연', 'ACTOR:3', 'seed'),
       ('SCENE:S06', '출연', 'ACTOR:2', 'seed'), ('SCENE:S06', '출연', 'ACTOR:3', 'seed'),
       ('SCENE:S07', '출연', 'ACTOR:2', 'seed'), ('SCENE:S07', '출연', 'ACTOR:3', 'seed'),
       ('SCENE:S08', '출연', 'ACTOR:2', 'seed'), ('SCENE:S08', '출연', 'ACTOR:3', 'seed'),
       ('SCENE:S14', '출연', 'ACTOR:2', 'seed'), ('SCENE:S14', '출연', 'ACTOR:3', 'seed'),
       ('SCENE:S15', '출연', 'ACTOR:3', 'seed'),
       ('SCENE:S16', '출연', 'ACTOR:2', 'seed'), ('SCENE:S16', '출연', 'ACTOR:5', 'seed'),
       ('SCENE:S17', '출연', 'ACTOR:5', 'seed')
ON CONFLICT DO NOTHING;
