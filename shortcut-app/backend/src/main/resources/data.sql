-- 모든 서비스가 이 값을 전제로 테스트하므로 다시 실행해도 기존 행을 덮지 않는다.
INSERT INTO projects (id, name, block_budget_cap, crew_weekly_hours_used)
VALUES (1, '드라마 숏컷 7화', 1000000, 40)
ON CONFLICT DO NOTHING;

INSERT INTO shoot_days (id, project_id, shoot_date, call_time, data_version, notice, crew_calls)
VALUES (1, 1, CURRENT_DATE, '06:30', 1, '13시 이후 비 예보가 있습니다. 변동 시 알림으로 공지합니다.',
        '[{"team": "연출팀", "time": "06:30"}, {"team": "촬영팀", "time": "06:45"}, {"team": "조명팀", "time": "06:45"},
          {"team": "동시녹음팀", "time": "07:00"}, {"team": "미술팀", "time": "06:30"}]')
ON CONFLICT DO NOTHING;

INSERT INTO actors (id, name, available_from, available_to, weekly_hours_used, contract_doc_id, no_night, max_daily_hours, manager_phone)
VALUES (1, '배우 A', '09:00', '16:00', 44, 'contract-actor-a-v3', true, 10, '010-2481-7731'),
       (2, '배우 B', '07:00', '22:00', 38, 'contract-actor-b-v1', false, NULL, '010-3920-1184'),
       (3, '배우 C', '06:30', '20:00', 30, 'contract-actor-c-v2', false, NULL, '010-5512-0093')
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
        0, false, 1.00, 0, NULL)
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
       (1, 'PM', '13:00', '15:00', 120, 1, '[1, 2, 3]')
ON CONFLICT DO NOTHING;

INSERT INTO scenes (code, shoot_day_id, block_code, title, duration_min, outdoor_intent, location_id, actor_ids, sort)
VALUES ('S01', 1, 'AM', '출근길 로비', 30, false, NULL, '[2, 3]', 1),
       ('S02', 1, 'AM', '회의실 브리핑', 35, false, NULL, '[2, 3]', 2),
       ('S03', 1, 'AM', '탕비실 대화', 30, false, NULL, '[2, 3]', 3),
       ('S04', 1, 'AM', '복도 통화', 30, false, NULL, '[2, 3]', 4),
       ('S05', 1, 'AM', '팀장실 면담', 40, false, NULL, '[2, 3]', 5),
       ('S06', 1, 'AM', '사무실 언쟁', 35, false, NULL, '[2, 3]', 6),
       ('S07', 1, 'AM', '엘리베이터 침묵', 35, false, NULL, '[2, 3]', 7),
       ('S08', 1, 'AM', '퇴근 준비', 35, false, NULL, '[2, 3]', 8),
       ('S12', 1, 'PM', '한강 산책 대화', 90, true, NULL, '[1, 2]', 12),
       ('S13', 1, 'PM', '강변 인서트', 30, true, NULL, '[1]', 13),
       ('S18', NULL, NULL, '작업실 대화', 90, false, 2, '[2, 3]', 18)
ON CONFLICT DO NOTHING;

INSERT INTO plan_options (shoot_day_id, block_code, option_no, location_id, equipment_ids, equipment_fit, start_time, end_time)
VALUES (1, 'PM', 1, 1, '[1, 2, 3]', 1.00, '13:00', '15:00'),
       (1, 'PM', 2, 2, '[1, 4]', 0.75, '14:00', '16:00'),
       (1, 'PM', 3, 3, '[1, 5]', 0.60, '12:30', '14:30')
ON CONFLICT DO NOTHING;

INSERT INTO callsheet_versions (shoot_day_id, version_no, proposal_id, pm_location_id, pm_equipment_ids, pm_start, pm_end, pm_cost)
VALUES (1, 1, NULL, 1, '[1, 2, 3]', '13:00', '15:00', 300000)
ON CONFLICT DO NOTHING;

-- 한강 공원은 13시부터 시간당 8mm 비가 예보되어 있다(촬영 불가 기준 5mm 이상). 나머지 장소는 비가 오지 않는다.
INSERT INTO weather_forecasts (shoot_day_id, location_id, hour, precip_prob, precip_mm)
SELECT 1, l.id, h, CASE WHEN l.id = 1 AND h >= 13 THEN 80 ELSE 20 END,
       CASE WHEN l.id = 1 AND h >= 13 THEN 8.0 WHEN l.id = 1 AND h = 12 THEN 0.5 ELSE 0 END
FROM locations l CROSS JOIN generate_series(6, 18) AS h
ON CONFLICT DO NOTHING;

-- 강수량 열을 추가하기 전에 만든 DB는 확률만 있으므로, 강수량이 하나도 없을 때만 같은 예보로 채운다.
UPDATE weather_forecasts SET precip_mm = CASE WHEN location_id = 1 AND hour >= 13 THEN 8.0
                                               WHEN location_id = 1 AND hour = 12 THEN 0.5 ELSE 0 END
WHERE shoot_day_id = 1 AND location_id < 100
  AND NOT EXISTS (SELECT 1 FROM weather_forecasts WHERE precip_mm > 0);

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
             ('COST', 'PRODUCER')) AS v (change_kind, role)
WHERE NOT EXISTS (SELECT 1 FROM approver_rules);

INSERT INTO reservations (id, shoot_day_id, location_id, start_time, end_time, status, provider)
VALUES ('R-2031', 1, 2, '14:00', '18:00', 'HELD', 'OURPLACE')
ON CONFLICT DO NOTHING;

INSERT INTO external_locations (id, name, indoor, region, distance_km, cost, keywords)
VALUES (1, '일산 실내 스튜디오', true, '경기 고양시', 25, 380000, '["실내", "자연광", "30평"]'),
       (2, '상암 호리존 스튜디오', true, '서울 마포구', 10, 520000, '["실내", "호리존", "방음"]'),
       (3, '김포 창고 스튜디오', true, '경기 김포시', 30, 320000, '["실내", "창고", "넓은 공간"]'),
       (4, '하남 카페 세트', true, '경기 하남시', 35, 350000, '["실내", "자연광", "카페"]'),
       (5, '망원 루프탑', false, '서울 마포구', 9, 280000, '["야외", "루프탑", "도심 야경"]')
ON CONFLICT DO NOTHING;

INSERT INTO ontology_nodes (node_id, type, label, props)
VALUES ('SCENE:S12', 'SCENE', 'S12 한강 산책 대화', '{"code": "S12", "block": "PM", "durationMin": 90, "outdoorIntent": true}'),
       ('SCENE:S13', 'SCENE', 'S13 강변 인서트', '{"code": "S13", "block": "PM", "durationMin": 30, "outdoorIntent": true}'),
       ('SCENE:S18', 'SCENE', 'S18 작업실 대화', '{"code": "S18", "block": "다음 촬영일", "durationMin": 90}'),
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
       ('RESERVATION:R-2031', 'RESERVATION', '성수 스튜디오 가예약 R-2031', '{"status": "HELD", "window": "14:00~18:00", "provider": "아워플레이스"}'),
       ('PLAN:1', 'PLAN', 'PM 1안', '{"optionNo": 1, "time": "13:00~15:00", "equipment": [1, 2, 3]}'),
       ('PLAN:2', 'PLAN', 'PM 2안', '{"optionNo": 2, "time": "14:00~16:00", "equipment": [1, 4]}'),
       ('PLAN:3', 'PLAN', 'PM 3안', '{"optionNo": 3, "time": "12:30~14:30", "equipment": [1, 5]}')
ON CONFLICT DO NOTHING;

INSERT INTO ontology_edges (src, relation, dst, created_by)
VALUES ('SCENE:S12', '출연', 'ACTOR:1', 'seed'),
       ('SCENE:S12', '출연', 'ACTOR:2', 'seed'),
       ('SCENE:S13', '출연', 'ACTOR:1', 'seed'),
       ('SCENE:S12', '촬영지', 'LOCATION:1', 'seed'),
       ('SCENE:S12', '사용', 'EQUIPMENT:2', 'seed'),
       ('SCENE:S12', '사용', 'EQUIPMENT:3', 'seed'),
       ('ACTOR:1', '계약', 'CONTRACT:contract-actor-a-v3', 'seed'),
       ('ACTOR:1', '소속', 'STAFF:manager-a', 'seed'),
       ('ACTOR:1', '제약', 'CONSTRAINT:no-night', 'seed'),
       ('SCENE:S18', '출연', 'ACTOR:2', 'seed'),
       ('SCENE:S18', '촬영지', 'LOCATION:2', 'seed'),
       ('LOCATION:2', '예약', 'RESERVATION:R-2031', 'seed'),
       ('PLAN:1', '포함', 'LOCATION:1', 'seed'),
       ('PLAN:2', '포함', 'LOCATION:2', 'seed'),
       ('PLAN:3', '포함', 'LOCATION:3', 'seed'),
       ('ACTOR:2', '계약', 'CONTRACT:contract-actor-b-v1', 'seed'),
       ('ACTOR:3', '계약', 'CONTRACT:contract-actor-c-v2', 'seed')
ON CONFLICT DO NOTHING;
