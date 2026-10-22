-- 제작부가 정하는 값이다. 대본 시드(data-script.sql) 뒤에 돈다.
-- 캐스팅, 씬 분해의 제작부 값(세트 고정, 예상 분, 요구 장비·소품·보조출연), 씬 배정, 배우 날짜별 일정을 둔다.
-- 서버가 켜질 때마다, 그리고 초기화가 배우 일정을 다시 만들 때 다시 돌므로 모든 문장은 여러 번 돌려도 같은 결과여야 한다.

-- 캐스팅. 대본은 배역만 알고 누가 연기하는지는 제작부가 정한다. 바꾼 캐스팅은 덮지 않는다.
UPDATE characters c SET actor_id = v.actor_id
FROM (VALUES (1, 1), (2, 2), (3, 3), (4, 4), (5, 5)) AS v (character_id, actor_id)
WHERE c.id = v.character_id AND c.actor_id IS NULL;

-- 작업실 미술 세트가 성수 스튜디오에만 있어 S18, S19는 다른 장소에서 찍을 수 없다.
UPDATE script_scenes SET setting_locked = true
WHERE project_id = 1 AND code IN ('S18', 'S19') AND NOT setting_locked;

-- 아직 배정하지 않은 씬의 예상 촬영 분이다. 배정 가능성 검사가 이만큼 배우가 함께 비는 날을 찾는다.
UPDATE script_scenes s SET est_minutes = v.minutes
FROM (VALUES ('S09', 30), ('S10', 30), ('S11', 15), ('S20', 30), ('S23', 45)) AS v (code, minutes)
WHERE s.project_id = 1 AND s.code = v.code AND s.est_minutes IS NULL;

-- 씬 요구. 모든 1/2/3안에 카메라 패키지(1)가 있으므로 필수로 둬도 시연이 막히지 않는다.
-- 드론과 반사판은 선호라 성수 2안(장비 1, 4)은 경고만 받는다.
INSERT INTO scene_requirements (project_id, scene_code, kind, equipment_id, label, qty, level)
VALUES (1, 'S12', 'EQUIPMENT', 1, '카메라 패키지 A', 1, 'MUST'),
       (1, 'S12', 'EQUIPMENT', 2, '드론(강변 부감)', 1, 'WANT'),
       (1, 'S12', 'EQUIPMENT', 3, '반사판', 1, 'WANT'),
       (1, 'S12', 'PROP', NULL, '텀블러', 2, 'MUST'),
       (1, 'S13', 'EQUIPMENT', 1, '카메라 패키지 A', 1, 'MUST'),
       (1, 'S13', 'EXTRAS', NULL, '산책 시민', 6, 'MUST'),
       (1, 'S18', 'EQUIPMENT', 1, '카메라 패키지 A', 1, 'MUST'),
       (1, 'S18', 'EQUIPMENT', 5, '짐벌 세트(몸싸움 핸드헬드)', 1, 'WANT'),
       (1, 'S18', 'PROP', NULL, '구겨진 계약서', 1, 'MUST'),
       (1, 'S18', 'COSTUME', NULL, '봉 대표 넥타이(같은 것 2개)', 2, 'MUST'),
       (1, 'S19', 'EQUIPMENT', 1, '카메라 패키지 A', 1, 'MUST'),
       (1, 'S19', 'PROP', NULL, '구겨진 계약서', 1, 'MUST'),
       (1, 'S21', 'EQUIPMENT', 1, '카메라 패키지 A', 1, 'MUST'),
       (1, 'S21', 'EQUIPMENT', 3, '반사판(야경 보조광)', 1, 'WANT'),
       (1, 'S21', 'PROP', NULL, '캔커피', 2, 'MUST'),
       (1, 'S22', 'EQUIPMENT', 1, '카메라 패키지 A', 1, 'MUST'),
       (1, 'S23', 'SPECIAL', NULL, '봉 대표 이마 반창고 분장', 1, 'MUST')
ON CONFLICT DO NOTHING;

-- 씬 배정. 같은 씬을 여러 촬영일에 나눠 찍을 수 있어 씬 코드는 촬영일 안에서만 유일하다.
-- 출연 배우(actor_ids)와 야외 의도(outdoor_intent)는 이제 대본의 등장 배역과 실내/실외에서 읽는다. 두 열은 시드 대조 테스트가 같은지 본다.
INSERT INTO scenes (project_id, code, shoot_day_id, block_code, title, duration_min, outdoor_intent, location_id, actor_ids, sort)
VALUES (1, 'S01', 1, 'AM', '출근길 로비', 30, false, NULL, '[2, 3]', 1),
       (1, 'S02', 1, 'AM', '회의실 브리핑', 35, false, NULL, '[2, 3]', 2),
       (1, 'S03', 1, 'AM', '탕비실 대화', 30, false, NULL, '[2, 3]', 3),
       (1, 'S04', 1, 'AM', '복도 통화', 30, false, NULL, '[2, 3]', 4),
       (1, 'S05', 1, 'AM', '팀장실 면담', 40, false, NULL, '[2, 3]', 5),
       (1, 'S06', 1, 'AM', '사무실 언쟁', 35, false, NULL, '[2, 3]', 6),
       (1, 'S07', 1, 'AM', '엘리베이터 침묵', 35, false, NULL, '[2, 3]', 7),
       (1, 'S08', 1, 'AM', '퇴근 준비', 35, false, NULL, '[2, 3]', 8),
       (1, 'S12', 1, 'PM', '한강 산책 대화', 90, true, NULL, '[1, 2]', 12),
       (1, 'S13', 1, 'PM', '강변 인서트', 30, true, NULL, '[1]', 13),
       (1, 'S14', 2, 'AM', '편집실 회의', 60, false, NULL, '[2, 3]', 14),
       (1, 'S15', 2, 'AM', '복도 재회', 60, false, NULL, '[3]', 15),
       (1, 'S18', 2, 'PM', '작업실 대화', 90, false, 2, '[2, 3]', 18),
       (1, 'S19', 2, 'PM', '작업실 인서트', 30, false, 2, '[2]', 19),
       (1, 'S16', 3, 'AM', '노무사 상담', 90, false, NULL, '[2, 5]', 16),
       (1, 'S17', 3, 'AM', '노무사 복도 통화', 30, false, NULL, '[5]', 17),
       (1, 'S21', 3, 'PM', '루프탑 소문', 90, true, 5, '[2, 4]', 21),
       (1, 'S22', 3, 'PM', '루프탑 야경 인서트', 30, true, 5, '[4]', 22)
ON CONFLICT DO NOTHING;

-- ===== 배우 날짜별 일정 (목데이터) =====
-- 1회차 날짜(D0) 기준 앞 28일 ~ 뒤 91일, 약 4개월치다. 날짜는 모두 D0에서 계산하고, 초기화가 1회차를 오늘로 옮기면
-- SEED 줄을 지우고 이 파일을 다시 돌린다(요일 규칙이 맞으려면 날짜를 밀지 말고 다시 만들어야 한다).
-- 배경 일정은 우리 촬영일 날짜를 피한다. 확정된 촬영일에는 소속사가 다른 일정을 잡지 않는다고 본다.
INSERT INTO actor_availability (actor_id, on_date, kind, start_time, end_time, reason_kind, memo, source)
WITH days AS (
    SELECT CAST(g AS date) AS d, CAST(g AS date) - s.shoot_date AS n, CAST(extract(isodow FROM g) AS integer) AS dow
    FROM shoot_days s, generate_series(s.shoot_date - 28, s.shoot_date + 91, interval '1 day') AS g
    WHERE s.id = 1
), rules (actor_id, d, kind, start_time, end_time, reason_kind, memo) AS (
    -- 배우 A(지우): 영화 「여름 손님」을 D0+21~+34의 화·수·목에 찍는다.
    SELECT 1, d, 'OFF', NULL, NULL, 'OTHER_PRODUCTION', '영화 「여름 손님」 촬영' FROM days
    WHERE n BETWEEN 21 AND 34 AND dow IN (2, 3, 4)
    -- 배우 B(도현): 연극 「봄밤」 연습은 D0+2까지 평일 저녁, 공연은 D0+3~+59의 금·토 저녁이다.
    UNION ALL SELECT 2, d, 'BUSY', '18:00', '22:00', 'OTHER_PRODUCTION', '연극 「봄밤」 연습' FROM days
    WHERE n <= 2 AND dow <= 5
    UNION ALL SELECT 2, d, 'BUSY', '18:30', '22:00', 'OTHER_PRODUCTION', '연극 「봄밤」 공연' FROM days
    WHERE n BETWEEN 3 AND 59 AND dow IN (5, 6)
    -- 배우 C(봉 대표): 예능 고정 출연 녹화가 격주 화요일에 있다.
    UNION ALL SELECT 3, d, 'BUSY', '09:00', '21:00', 'OTHER_PRODUCTION', '예능 녹화' FROM days
    WHERE dow = 2 AND (n + 28) / 7 % 2 = 0
    -- 배우 D(문태): 매주 일·월 낮에 카페 아르바이트를 한다.
    UNION ALL SELECT 4, d, 'BUSY', '10:00', '16:00', 'PERSONAL', '카페 아르바이트' FROM days
    WHERE dow IN (7, 1)
    -- 배우 E(구 노무사): 다른 드라마 「법대로」 고정 출연으로 매주 월·수는 촬영이 안 된다.
    UNION ALL SELECT 5, d, 'OFF', NULL, NULL, 'OTHER_PRODUCTION', '드라마 「법대로」 촬영' FROM days
    WHERE dow IN (1, 3)
    -- 날짜 하나짜리 일정은 D0 기준 날 수로 적는다.
    UNION ALL SELECT v.actor_id, days.d, v.kind, v.start_time, v.end_time, v.reason_kind, v.memo
    FROM days JOIN (VALUES (1, -12, 'BUSY', '07:00', '19:00', 'PROMOTION', '광고 촬영'),
                           (1, 9, 'BUSY', '07:00', '19:00', 'PROMOTION', '광고 촬영'),
                           (1, 37, 'BUSY', '07:00', '19:00', 'PROMOTION', '광고 촬영'),
                           (1, 63, 'BUSY', '07:00', '19:00', 'PROMOTION', '광고 촬영'),
                           (1, 16, 'BUSY', '13:00', '18:00', 'PROMOTION', '화보 촬영'),
                           (1, 52, 'BUSY', '13:00', '18:00', 'PROMOTION', '화보 촬영'),
                           (1, 44, 'OFF', NULL, NULL, 'TRAVEL', '해외 팬미팅'),
                           (1, 45, 'OFF', NULL, NULL, 'TRAVEL', '해외 팬미팅'),
                           (1, 46, 'OFF', NULL, NULL, 'TRAVEL', '해외 팬미팅'),
                           (1, 47, 'OFF', NULL, NULL, 'TRAVEL', '해외 팬미팅'),
                           (1, -5, 'BUSY', '10:00', '12:00', 'PERSONAL', '개인 일정'),
                           (1, 19, 'BUSY', '10:00', '12:00', 'PERSONAL', '개인 일정'),
                           (1, 71, 'BUSY', '10:00', '12:00', 'PERSONAL', '개인 일정'),
                           (1, 3, 'WINDOW', '13:00', '16:00', NULL, '소속사 회신: 오전 일정이 있어 오후만 가능'),
                           (2, 30, 'BUSY', '17:00', '21:00', 'PROMOTION', '브랜드 행사'),
                           (3, 50, 'BUSY', '16:00', '23:00', 'PROMOTION', '시상식'),
                           (3, 12, 'OFF', NULL, NULL, 'PERSONAL', '개인 일정'),
                           (3, 40, 'OFF', NULL, NULL, 'PERSONAL', '개인 일정'),
                           (4, 6, 'BUSY', '10:00', '13:00', 'OTHER_PRODUCTION', '오디션'),
                           (4, 20, 'BUSY', '10:00', '13:00', 'OTHER_PRODUCTION', '오디션'),
                           (4, 48, 'BUSY', '10:00', '13:00', 'OTHER_PRODUCTION', '오디션'),
                           (4, 75, 'BUSY', '10:00', '13:00', 'OTHER_PRODUCTION', '오디션'),
                           (5, 55, 'OFF', NULL, NULL, 'TRAVEL', '지방 공연'),
                           (5, 56, 'OFF', NULL, NULL, 'TRAVEL', '지방 공연'),
                           (5, 57, 'OFF', NULL, NULL, 'TRAVEL', '지방 공연'),
                           (5, 58, 'OFF', NULL, NULL, 'TRAVEL', '지방 공연'))
                AS v (actor_id, n, kind, start_time, end_time, reason_kind, memo) ON days.n = v.n
)
SELECT r.actor_id, r.d, r.kind, CAST(r.start_time AS time), CAST(r.end_time AS time), r.reason_kind, r.memo, 'SEED'
FROM rules r
WHERE NOT EXISTS (SELECT 1 FROM shoot_days s WHERE s.project_id = 1 AND s.shoot_date = r.d)
ON CONFLICT DO NOTHING;

-- 시연용으로 일부러 촬영일에 겹친 일정이다. 회차 날짜에 붙여 두어 회차 하나만 초기화해도 맞는 날에 남는다.
-- 1회차 A 12:00~13:00: 우천 때 12:30 시작 후보에 배우 일정 위반이 더 찍힌다(결과는 그대로 성수 14~16시).
-- 2회차 A 06:00~13:30: A가 1회차에 빠져 2회차 오후와 맞바꿀 때 13시 시작이 막혀 14시로 잡힌다.
-- 2회차 C 10:30~14:30: 콜시트 확정 뒤 들어온 회신이라 2회차 오후 확정안과 겹친다. 씬 순서(S19 → S18)를 바꾸면 풀린다.
INSERT INTO actor_availability (actor_id, on_date, kind, start_time, end_time, reason_kind, memo, source)
SELECT v.actor_id, s.shoot_date, 'BUSY', CAST(v.start_time AS time), CAST(v.end_time AS time), v.reason_kind, v.memo, 'SEED'
FROM shoot_days s
JOIN (VALUES (1, 1, '12:00', '13:00', 'PERSONAL', '병원 진료 [시연]'),
             (2, 1, '06:00', '13:30', 'PROMOTION', '광고 촬영 [시연]'),
             (2, 3, '10:30', '14:30', 'OTHER_PRODUCTION', '타 작품 인터뷰, 콜시트 확정 뒤 소속사 회신 [시연]'))
    AS v (shoot_day_id, actor_id, start_time, end_time, reason_kind, memo) ON s.id = v.shoot_day_id
ON CONFLICT DO NOTHING;
