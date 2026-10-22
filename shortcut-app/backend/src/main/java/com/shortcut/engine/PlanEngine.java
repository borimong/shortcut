package com.shortcut.engine;

import com.shortcut.domain.Actor;
import com.shortcut.domain.DisasterAlert;
import com.shortcut.domain.Equipment;
import com.shortcut.domain.Location;
import com.shortcut.domain.PlanOption;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Predicate;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/**
 * 오후 블록 후보를 만들고 하드 제약과 소프트 점수를 판정한다.
 * 업무 규칙이 여러 서비스로 흩어지면 Agent와 화면이 다른 답을 내므로 판정은 이 클래스 한 곳에서만 한다.
 */
public final class PlanEngine {

    public static final Map<String, Double> DEFAULT_WEIGHTS = defaultWeights();
    // 1/2/3안 밖에서 찾은 대체 장소는 4안으로 표시한다.
    public static final int ALTERNATIVE_OPTION_NO = 4;

    // 이동 시간은 목동 기준 거리 1km당 2분으로 어림한다.
    private static final double TRAVEL_MINUTES_PER_KM = 2.0;
    // 장소 도착 후 카메라와 조명을 세우는 데 30분이 든다고 본다.
    private static final int SETUP_MINUTES = 30;
    // 크루 근무는 블록 종료 뒤 철수 30분까지 센다.
    private static final int WRAP_MINUTES = 30;
    private static final double WEEKLY_LIMIT_HOURS = 52.0;
    private static final LocalTime NIGHT_LIMIT = LocalTime.of(22, 0);
    // 강수 기준은 관리자 설정이라 입력으로 받는다. 설정이 없을 때 쓰는 기본값은 시간당 5mm(촬영 불가)와 1mm(경고)다.
    public static final double DEFAULT_RAIN_BLOCK_MM = 5.0;
    public static final double DEFAULT_RAIN_WARN_MM = 1.0;
    // 50km를 넘으면 당일 이동으로는 모두 같은 부담이라 거리 점수는 0으로 둔다.
    private static final double DISTANCE_SCALE_KM = 50.0;
    // 점심 이후 시작하는 오후 블록이라 12시 종료를 만점, 20시 종료를 0점으로 본다.
    private static final double TIME_BASE_HOUR = 12.0;
    private static final double TIME_SPAN_HOURS = 8.0;
    private static final DateTimeFormatter HHMM = DateTimeFormatter.ofPattern("HHmm");
    private static final DateTimeFormatter HH_MM = DateTimeFormatter.ofPattern("HH:mm");

    public EvaluationResult evaluate(PlanInput input, Map<String, Double> requestedWeights,
                                     List<ExtraConstraint> extras) {
        List<ExtraConstraint> constraints = validated(extras);
        Map<String, Double> weights = normalizeWeights(requestedWeights);
        List<PlanOption> options = input.options().stream()
                .sorted(Comparator.comparingInt(PlanOption::optionNo))
                .toList();

        // 장소 후보는 1/2/3안의 장소에 4안 대체 장소를 더한다.
        // 장비와 시간대는 제작사가 검토한 1/2/3안 안에서만 섞어, 새 장소에서도 검증된 장비 구성과 시간표를 쓴다.
        List<long[]> locationChoices = new ArrayList<>();
        options.forEach(option -> locationChoices.add(new long[] {option.optionNo(), option.locationId()}));
        input.alternativeLocationIds().forEach(id -> locationChoices.add(new long[] {ALTERNATIVE_OPTION_NO, id}));

        List<CandidateResult> candidates = new ArrayList<>();
        for (long[] locationChoice : locationChoices) {
            for (PlanOption equipmentOption : options) {
                for (PlanOption timeOption : options) {
                    candidates.add(candidate(input, weights, constraints, (int) locationChoice[0], locationChoice[1],
                            equipmentOption, timeOption));
                }
            }
        }
        // 같은 점수일 때 실행마다 순서가 바뀌면 Agent 판단이 흔들리므로 해시로 순서를 고정한다.
        candidates.sort(Comparator.comparing(CandidateResult::feasible).reversed()
                .thenComparing(Comparator.comparingDouble(CandidateResult::totalScore).reversed())
                .thenComparing(CandidateResult::hash));
        return new EvaluationResult(rounded(weights), candidates);
    }

    public CheckResult check(PlanInput input, long locationId, List<Long> equipmentIds,
                             LocalTime start, LocalTime end, List<ExtraConstraint> extras) {
        List<ExtraConstraint> constraints = validated(extras);
        if (start == null || end == null || !start.isBefore(end)) {
            throw new PlanRuleException("INVALID_TIME", "시작 시각은 종료 시각보다 빨라야 합니다.");
        }
        Location location = input.locations().get(locationId);
        if (location == null) {
            throw new PlanRuleException("UNKNOWN_LOCATION", "없는 장소입니다: " + locationId);
        }
        List<Equipment> items = equipmentIds.stream().map(id -> {
            Equipment item = input.equipment().get(id);
            if (item == null) {
                throw new PlanRuleException("UNKNOWN_EQUIPMENT", "없는 장비입니다: " + id);
            }
            return item;
        }).toList();
        return check(input, location, items, start, end, constraints);
    }

    public static String hash(long locationId, List<Long> equipmentIds, LocalTime start, LocalTime end) {
        String equipment = equipmentIds.stream().sorted().map(String::valueOf).collect(Collectors.joining(","));
        return "L" + locationId + "-E" + equipment + "-T" + start.format(HHMM) + end.format(HHMM);
    }

    public static Map<String, Double> normalizeWeights(Map<String, Double> requested) {
        Map<String, Double> merged = new LinkedHashMap<>(DEFAULT_WEIGHTS);
        if (requested != null) {
            requested.forEach((key, value) -> {
                if (merged.containsKey(key) && value != null) {
                    merged.put(key, value);
                }
            });
        }
        double sum = 0;
        for (double value : merged.values()) {
            if (value < 0) {
                throw new PlanRuleException("INVALID_WEIGHTS", "가중치는 0 이상이어야 합니다.");
            }
            sum += value;
        }
        if (sum == 0) {
            throw new PlanRuleException("INVALID_WEIGHTS", "가중치 합이 0입니다.");
        }
        double total = sum;
        merged.replaceAll((key, value) -> value / total);
        return merged;
    }

    private CandidateResult candidate(PlanInput input, Map<String, Double> weights, List<ExtraConstraint> constraints,
                                      int locationOptionNo, long locationId, PlanOption equipmentOption,
                                      PlanOption timeOption) {
        Location location = input.locations().get(locationId);
        List<Equipment> items = equipmentOption.equipmentIds().stream()
                .sorted()
                .map(id -> input.equipment().get(id))
                .toList();
        LocalTime start = timeOption.start();
        LocalTime end = timeOption.end();
        CheckResult check = check(input, location, items, start, end, constraints);
        long cost = cost(location, items);

        Map<String, Double> soft = new LinkedHashMap<>();
        soft.put("location", round(location.fit()));
        soft.put("equipment", round(equipmentOption.equipmentFit()));
        // 촬영 불가 기준만큼 비가 오면 날씨 점수는 0이고, 비가 없으면 1이다.
        soft.put("weather", round(location.indoor() ? 1.0
                : 1.0 - Math.min(maxPrecip(input, location, start, end) / input.rainBlockMm(), 1.0)));
        soft.put("budget", round(Math.max(0.0, 1.0 - (double) cost / input.budgetCap())));
        soft.put("time", round(clamp(1.0 - (hours(end) - TIME_BASE_HOUR) / TIME_SPAN_HOURS)));
        soft.put("distance", round(1.0 - Math.min(location.distanceKm() / DISTANCE_SCALE_KM, 1.0)));
        double total = 0;
        for (Map.Entry<String, Double> entry : weights.entrySet()) {
            total += entry.getValue() * soft.get(entry.getKey());
        }

        return new CandidateResult(
                hash(location.id(), equipmentOption.equipmentIds(), start, end),
                locationOptionNo, location,
                equipmentOption.optionNo(), items,
                timeOption.optionNo(), start, end,
                check.feasible(), check.violations(), check.warnings(),
                soft, round(total), cost, cost - input.current().cost(), location.distanceKm());
    }

    private CheckResult check(PlanInput input, Location location, List<Equipment> items,
                              LocalTime start, LocalTime end, List<ExtraConstraint> constraints) {
        List<Finding> violations = new ArrayList<>();
        List<Finding> warnings = new ArrayList<>();
        int blockMinutes = minutes(end) - minutes(start);
        long cost = cost(location, items);

        for (long actorId : input.blockActorIds()) {
            checkActorDay(input, actorId, start, end, violations);
        }
        if (!location.available()) {
            violations.add(new Finding("LOCATION_CANCELLED", "SCHEDULE",
                    location.name() + "은(는) 변경 입력에서 취소되어 쓸 수 없습니다.", "SCHEDULE_LOCATION"));
        }
        if (start.isBefore(location.openFrom()) || end.isAfter(location.openTo())) {
            violations.add(new Finding("LOCATION_CLOSED", "SCHEDULE",
                    location.name() + " 이용 가능 시간(" + fmt(location.openFrom()) + "~" + fmt(location.openTo()) + ") 밖입니다.",
                    "SCHEDULE_LOCATION"));
        }
        double arrival = minutes(input.morningEnd()) + location.distanceKm() * TRAVEL_MINUTES_PER_KM + SETUP_MINUTES;
        if (arrival > minutes(start)) {
            violations.add(new Finding("TRAVEL_TOO_LONG", "SCHEDULE",
                    "오전 종료 후 이동과 세팅을 마치면 " + fmtMinutes(arrival) + "이라 " + fmt(start) + " 시작이 불가능합니다.",
                    "SCHEDULE_TRAVEL"));
        }
        for (Equipment item : items) {
            if (!item.available()) {
                violations.add(new Finding("EQUIPMENT_UNAVAILABLE", "SCHEDULE",
                        item.name() + "을(를) 사용할 수 없습니다.", "SCHEDULE_EQUIPMENT"));
            }
        }

        for (long actorId : input.blockActorIds()) {
            Actor actor = input.actors().get(actorId);
            if (actor.noNight() && end.isAfter(NIGHT_LIMIT)) {
                violations.add(new Finding("NIGHT_SHOOT", "CONTRACT",
                        actor.name() + " 계약상 22시 이후 촬영이 불가합니다.", "CONTRACT_NIGHT"));
            }
            double dailyHours = (input.actorOtherBlockMinutes().getOrDefault(actorId, 0) + blockMinutes) / 60.0;
            if (actor.maxDailyHours() != null && dailyHours > actor.maxDailyHours()) {
                violations.add(new Finding("DAILY_HOURS", "CONTRACT",
                        actor.name() + " 하루 촬영 " + dailyHours + "시간이 계약 최대 " + actor.maxDailyHours() + "시간을 넘습니다.",
                        "CONTRACT_DAILY_HOURS"));
            }
            if (actor.weeklyHoursUsed() + dailyHours > WEEKLY_LIMIT_HOURS) {
                violations.add(new Finding("WEEKLY_52H", "LAW",
                        actor.name() + " 주간 누적이 52시간을 넘습니다.", "LAW_52H"));
            }
        }
        double crewHours = (minutes(end) + WRAP_MINUTES - minutes(input.callTime())) / 60.0;
        if (input.crewWeeklyHoursUsed() + crewHours > WEEKLY_LIMIT_HOURS) {
            violations.add(new Finding("WEEKLY_52H", "LAW",
                    "크루 주간 누적이 " + (input.crewWeeklyHoursUsed() + crewHours) + "시간으로 52시간을 넘습니다.", "LAW_52H"));
        }
        if (!location.indoor() && outsidePermit(location, start, end)) {
            violations.add(new Finding("PERMIT_WINDOW", "LAW",
                    location.name() + " 촬영 허가 시간 밖입니다.", "LAW_PERMIT"));
        }

        checkScript(input, location, items, start, end, blockMinutes, violations, warnings);

        if (cost > input.budgetCap()) {
            violations.add(new Finding("BUDGET_EXCEEDED", "BUDGET",
                    "장소와 장비 비용 " + cost + "원이 블록 상한 " + input.budgetCap() + "원을 넘습니다.", "BUDGET_CAP"));
        }
        if (location.noFlyZone() && items.stream().anyMatch(Equipment::drone)) {
            violations.add(new Finding("DRONE_NO_FLY", "NO_FLY_ZONE",
                    location.name() + "은(는) 비행금지구역이라 드론을 쓸 수 없습니다.", "NO_FLY_ZONE"));
        }
        for (DisasterAlert alert : input.alerts()) {
            if (Regions.covers(alert.region(), location.region())
                    && overlaps(alert.startsAt(), alert.endsAt(), start, end)) {
                violations.add(new Finding("DISASTER_ALERT", "DISASTER",
                        location.region() + " " + alert.kind() + " 재난 문자(" + fmt(alert.startsAt()) + "~" + fmt(alert.endsAt()) + ")와 겹칩니다.",
                        "DISASTER_ALERT"));
            }
        }
        if (!location.indoor()) {
            double precip = maxPrecip(input, location, start, end);
            if (precip >= input.rainBlockMm()) {
                violations.add(new Finding("RAIN_HARD", "WEATHER",
                        location.name() + " 시간대 최대 강수량 시간당 " + mm(precip) + "mm로 기준 " + mm(input.rainBlockMm())
                                + "mm 이상이라 야외 촬영이 불가합니다.", "WEATHER_RAIN"));
            } else if (precip >= input.rainWarnMm()) {
                warnings.add(new Finding("RAIN_SOFT", "WEATHER",
                        location.name() + " 시간대 최대 강수량 시간당 " + mm(precip) + "mm로 우천 대비가 필요합니다.", "WEATHER_RAIN"));
            }
        }

        long extraCost = cost - input.current().cost();
        for (ExtraConstraint extra : constraints) {
            if ("MAX_EXTRA_COST".equals(extra.type())) {
                if (extraCost > extra.amount()) {
                    // 예산 초과와 같은 성격이라 BUDGET으로 분류하고 근거 키만 추가 제약으로 남긴다.
                    violations.add(new Finding("BUDGET_EXCEEDED", "BUDGET",
                            "추가 비용 " + extraCost + "원이 허용 " + extra.amount() + "원을 넘습니다. (" + extra.describe() + ")",
                            "EXTRA_MAX_EXTRA_COST"));
                }
            } else if (excludedBy(extra, input, location, items, start, end)) {
                violations.add(new Finding("EXCLUDED_BY_CONSTRAINT", "EXTRA",
                        "추가 제약으로 제외됩니다: " + extra.describe(), "EXTRA_" + extra.type()));
            }
        }
        return new CheckResult(List.copyOf(violations), List.copyOf(warnings));
    }

    /**
     * 배우의 그날 일정과 블록 시간을 맞춰 본다. 날짜별 일정(종일 불가, 가능 시간대, 다른 일정)에 변경 입력을 얹은 값이고,
     * 같은 촬영일의 다른 블록과 시간이 겹치는지도 본다(같은 배우가 두 곳에 있을 수 없다).
     */
    private static void checkActorDay(PlanInput input, long actorId, LocalTime start, LocalTime end,
                                      List<Finding> violations) {
        Actor actor = input.actors().get(actorId);
        ActorDay day = input.actorDay(actorId);
        if (day.off()) {
            String reason = day.offReason() == null ? "" : "(" + ActorDay.reasonLabel(day.offReason()) + ")";
            violations.add(new Finding("ACTOR_UNAVAILABLE", "SCHEDULE",
                    actor.name() + "은(는) 오늘 촬영에 참여할 수 없습니다" + reason + ".", "SCHEDULE_ACTOR"));
            return;
        }
        List<ActorDay.Busy> busy = day.overlapping(start, end);
        if (!busy.isEmpty()) {
            String slots = busy.stream()
                    .map(b -> fmt(b.from()) + "~" + fmt(b.to()) + " " + ActorDay.reasonLabel(b.reasonKind()))
                    .collect(Collectors.joining(", "));
            violations.add(new Finding("ACTOR_BUSY", "SCHEDULE",
                    actor.name() + " 일정(" + slots + ")과 겹칩니다.", "SCHEDULE_ACTOR"));
        } else if (!day.covers(start, end)) {
            String windows = day.windows().stream().map(w -> fmt(w.from()) + "~" + fmt(w.to()))
                    .collect(Collectors.joining(", "));
            violations.add(new Finding("ACTOR_UNAVAILABLE", "SCHEDULE",
                    actor.name() + " 가용 시간(" + windows + ") 밖입니다.", "SCHEDULE_ACTOR"));
        }
        for (BlockSlot other : input.otherBlocks()) {
            if (other.actorIds().contains(actorId) && overlaps(other.start(), other.end(), start, end)) {
                violations.add(new Finding("ACTOR_OVERLAP", "SCHEDULE",
                        actor.name() + "이(가) 같은 시간 " + other.code() + " 블록(" + fmt(other.start()) + "~"
                                + fmt(other.end()) + ")에도 나옵니다.", "SCHEDULE_OVERLAP"));
            }
        }
    }

    /**
     * 대본 씬 분해와 후보를 맞춰 본다. 물리적으로 못 찍는 것(지정 세트 밖, 필수 장비 없음, 배우 미정, 시간 부족,
     * 해가 진 뒤의 낮 야외 장면)은 위반이고, 연출이 받아들일 수도 있는 것(야외 장면을 실내에서, 선호 장비 없음)은 경고다.
     * 같은 규칙에 걸린 씬은 한 줄로 묶는다. Agent가 받는 평가 결과 길이에 한도가 있기 때문이다.
     */
    private static void checkScript(PlanInput input, Location location, List<Equipment> items, LocalTime start,
                                    LocalTime end, int blockMinutes, List<Finding> violations, List<Finding> warnings) {
        List<ScenePlan> scenes = input.blockScenes();
        if (scenes.isEmpty()) {
            return;
        }
        int sceneMinutes = scenes.stream().mapToInt(ScenePlan::durationMin).sum();
        if (sceneMinutes > blockMinutes) {
            violations.add(new Finding("BLOCK_OVERFLOW", "SCHEDULE",
                    "씬 길이 합 " + sceneMinutes + "분이 " + fmt(start) + "~" + fmt(end) + "(" + blockMinutes + "분)보다 깁니다.",
                    "SCHEDULE_BLOCK"));
        }
        Map<Long, String> lockedElsewhere = scenes.stream()
                .filter(s -> s.settingLocked() && s.locationId() != null && s.locationId() != location.id())
                .collect(Collectors.groupingBy(ScenePlan::locationId, LinkedHashMap::new,
                        Collectors.mapping(ScenePlan::code, Collectors.joining(", "))));
        lockedElsewhere.forEach((setId, codes) -> {
            Location set = input.locations().get(setId);
            violations.add(new Finding("SCRIPT_SETTING_LOCKED", "SCRIPT",
                    codes + "은(는) 세트가 " + (set == null ? "지정 장소" : set.name()) + "에만 있어 "
                            + location.name() + "에서 찍을 수 없습니다.", "SCRIPT_SETTING"));
        });
        List<String> uncast = scenes.stream().flatMap(s -> s.uncastCharacters().stream()).distinct().toList();
        if (!uncast.isEmpty()) {
            violations.add(new Finding("CHARACTER_UNCAST", "SCRIPT",
                    String.join(", ", uncast) + " 배역에 배우가 정해지지 않았습니다.", "SCRIPT_CAST"));
        }
        Set<Long> have = items.stream().map(Equipment::id).collect(Collectors.toSet());
        String mustMissing = equipmentNames(input, scenes.stream().flatMap(s -> s.mustEquipmentIds().stream()), have);
        if (!mustMissing.isEmpty()) {
            violations.add(new Finding("SCRIPT_EQUIPMENT_MISSING", "SCRIPT",
                    "대본상 필수 장비(" + mustMissing + ")가 장비 묶음에 없습니다.", "SCRIPT_EQUIPMENT"));
        }
        // 스튜디오 조명으로 낮밤을 만들 수 있으므로 해의 위치는 야외 장소에서 찍는 실외 장면만 본다.
        if (!location.indoor() && input.sunrise() != null && input.sunset() != null) {
            String dayOutside = codes(scenes, s -> s.exterior() && !s.night()
                    && (start.isBefore(input.sunrise()) || end.isAfter(input.sunset())));
            if (!dayOutside.isEmpty()) {
                violations.add(new Finding("SCRIPT_DAYLIGHT", "SCRIPT",
                        dayOutside + "은(는) 낮 야외 장면인데 일출~일몰(" + fmt(input.sunrise()) + "~" + fmt(input.sunset())
                                + ") 밖에 걸립니다.", "SCRIPT_TIME_OF_DAY"));
            }
            String nightBeforeDark = codes(scenes, s -> s.exterior() && s.night() && start.isBefore(input.sunset()));
            if (!nightBeforeDark.isEmpty()) {
                violations.add(new Finding("SCRIPT_DAYLIGHT", "SCRIPT",
                        nightBeforeDark + "은(는) 밤 야외 장면인데 일몰(" + fmt(input.sunset()) + ") 전에 시작합니다.",
                        "SCRIPT_TIME_OF_DAY"));
            }
        }
        String exteriorIndoor = codes(scenes, s -> s.exterior() && location.indoor());
        if (!exteriorIndoor.isEmpty()) {
            warnings.add(new Finding("SCRIPT_EXT_INDOOR", "SCRIPT",
                    exteriorIndoor + "은(는) 대본상 야외 장면인데 " + location.name() + "은(는) 실내입니다. 연출 확인이 필요합니다.",
                    "SCRIPT_SETTING"));
        }
        String interiorOutdoor = codes(scenes, s -> !s.exterior() && !location.indoor());
        if (!interiorOutdoor.isEmpty()) {
            warnings.add(new Finding("SCRIPT_INT_OUTDOOR", "SCRIPT",
                    interiorOutdoor + "은(는) 대본상 실내 장면인데 " + location.name() + "은(는) 야외입니다. 연출 확인이 필요합니다.",
                    "SCRIPT_SETTING"));
        }
        String wantMissing = equipmentNames(input, scenes.stream().flatMap(s -> s.wantEquipmentIds().stream()), have);
        if (!wantMissing.isEmpty()) {
            warnings.add(new Finding("SCRIPT_EQUIPMENT_WANTED", "SCRIPT",
                    "대본상 있으면 좋은 장비(" + wantMissing + ")가 장비 묶음에 없습니다.", "SCRIPT_EQUIPMENT"));
        }
    }

    private static String codes(List<ScenePlan> scenes, Predicate<ScenePlan> rule) {
        return scenes.stream().filter(rule).map(ScenePlan::code).collect(Collectors.joining(", "));
    }

    private static String equipmentNames(PlanInput input, Stream<Long> ids, Set<Long> have) {
        return ids.filter(id -> !have.contains(id)).distinct()
                .map(id -> input.equipment().containsKey(id) ? input.equipment().get(id).name() : "장비 " + id)
                .collect(Collectors.joining(", "));
    }

    private static boolean excludedBy(ExtraConstraint extra, PlanInput input, Location location, List<Equipment> items,
                                      LocalTime start, LocalTime end) {
        return switch (extra.type()) {
            case "EXCLUDE_LOCATION" -> extra.locationId() == location.id();
            case "EXCLUDE_LOCATION_TIME" -> extra.locationId() == location.id()
                    && overlaps(extra.from(), extra.to(), start, end);
            case "EXCLUDE_EQUIPMENT" -> items.stream().anyMatch(item -> item.id() == extra.equipmentId());
            case "REQUIRE_INDOOR" -> !location.indoor();
            // 대본의 실내/실외와 장소가 하나라도 어긋나면 뺀다. 감독이 "야외 장면은 야외에서"로 거절했을 때 쓴다.
            case "REQUIRE_SETTING_MATCH" -> input.blockScenes().stream().anyMatch(s -> s.exterior() == location.indoor());
            case "LATEST_END" -> end.isAfter(extra.time());
            case "EXCLUDE_TIME" -> overlaps(extra.from(), extra.to(), start, end);
            default -> false;
        };
    }

    private static boolean outsidePermit(Location location, LocalTime start, LocalTime end) {
        // 야외인데 허가 시간이 비어 있으면 허가 자체가 없다는 뜻이라 위반으로 본다.
        if (location.permitFrom() == null || location.permitTo() == null) {
            return true;
        }
        return start.isBefore(location.permitFrom()) || end.isAfter(location.permitTo());
    }

    /**
     * 시간대와 겹치는 정시 구간의 최대 시간당 강수량(mm)이다.
     * 12:30~14:30이면 12시, 13시, 14시 예보를 모두 본다.
     */
    public static double maxPrecip(Map<Integer, Double> hourly, LocalTime start, LocalTime end) {
        int lastHour = (minutes(end) - 1) / 60;
        double max = 0;
        for (int hour = start.getHour(); hour <= lastHour; hour++) {
            max = Math.max(max, hourly.getOrDefault(hour, 0.0));
        }
        return max;
    }

    private static double maxPrecip(PlanInput input, Location location, LocalTime start, LocalTime end) {
        return maxPrecip(input.precipByLocation().getOrDefault(location.id(), Map.of()), start, end);
    }

    public static String mm(double value) {
        return value == Math.rint(value) ? String.valueOf((long) value) : String.valueOf(Math.round(value * 10) / 10.0);
    }

    private static boolean overlaps(LocalTime aStart, LocalTime aEnd, LocalTime bStart, LocalTime bEnd) {
        return aStart.isBefore(bEnd) && bStart.isBefore(aEnd);
    }

    private static long cost(Location location, List<Equipment> items) {
        return location.cost() + items.stream().mapToLong(Equipment::cost).sum();
    }

    private static List<ExtraConstraint> validated(List<ExtraConstraint> extras) {
        List<ExtraConstraint> constraints = extras == null ? List.of() : extras;
        constraints.forEach(ExtraConstraint::validate);
        return constraints;
    }

    private static Map<String, Double> defaultWeights() {
        Map<String, Double> weights = new LinkedHashMap<>();
        weights.put("location", 0.25);
        weights.put("equipment", 0.15);
        weights.put("weather", 0.20);
        weights.put("budget", 0.15);
        weights.put("time", 0.10);
        weights.put("distance", 0.15);
        return Collections.unmodifiableMap(weights);
    }

    private static Map<String, Double> rounded(Map<String, Double> weights) {
        Map<String, Double> copy = new LinkedHashMap<>();
        weights.forEach((key, value) -> copy.put(key, round(value)));
        return copy;
    }

    private static int minutes(LocalTime time) {
        return time.toSecondOfDay() / 60;
    }

    private static double hours(LocalTime time) {
        return minutes(time) / 60.0;
    }

    private static double clamp(double value) {
        return Math.max(0.0, Math.min(1.0, value));
    }

    private static double round(double value) {
        return Math.round(value * 1000.0) / 1000.0;
    }

    private static String fmt(LocalTime time) {
        return time.format(HH_MM);
    }

    private static String fmtMinutes(double minutes) {
        int total = (int) Math.ceil(minutes);
        return String.format("%02d:%02d", total / 60, total % 60);
    }
}
