package com.shortcut.engine;

import com.shortcut.domain.Actor;
import com.shortcut.domain.SceneCharacter;
import com.shortcut.domain.ScriptScene;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.NavigableMap;
import java.util.Objects;

/**
 * 아직 촬영 배정하지 않은 대본 씬을 배우 날짜별 일정 안에서 찍을 수 있는 날이 있는지 본다(대본 ↔ 일정 교차검증).
 * 회차를 잡기 전에 "이 밤 장면은 배우 계약상 어느 날에도 못 찍는다"를 알려 주려는 것이다.
 * 판정은 순수 함수로 두어 촬영판 점검과 Agent 질의응답이 같은 결과를 쓴다.
 */
public final class Placeability {

    // 예상 분이 없는 씬은 한 시간으로 본다.
    public static final int DEFAULT_MINUTES = 60;
    // 실내 장면은 조명으로 낮밤을 만들 수 있어 하루 촬영 시간대 전체를 본다.
    private static final LocalTime INTERIOR_FROM = LocalTime.of(6, 0);
    private static final LocalTime DAY_END = LocalTime.of(23, 59);
    // 야간 촬영이 안 되는 배우는 22시까지만 센다(엔진의 NIGHT_SHOOT 기준과 같다).
    private static final LocalTime NIGHT_LIMIT = LocalTime.of(22, 0);
    private static final DateTimeFormatter HH_MM = DateTimeFormatter.ofPattern("HH:mm");

    private Placeability() {
    }

    /** 씬 하나의 결과다. 찍을 수 있으면 firstDate가 있고, 없으면 reason이 이유다. */
    public record Result(String code, String heading, List<Long> actorIds, int minutes, LocalDate firstDate,
                         String reason) {

        public boolean placeable() {
            return firstDate != null;
        }
    }

    /**
     * @param days 날짜마다 배우별 그날 일정. 우리 촬영에 이미 배정된 시간은 다른 일정(busy)으로 얹어 둔다
     */
    public static List<Result> check(List<ScriptScene> scenes, Map<Long, Actor> actors,
                                     NavigableMap<LocalDate, Map<Long, ActorDay>> days, LocalTime sunrise,
                                     LocalTime sunset) {
        List<Result> results = new ArrayList<>();
        for (ScriptScene scene : scenes) {
            if (!scene.assignedShootDayIds().isEmpty()) {
                continue;
            }
            results.add(check(scene, actors, days, sunrise, sunset));
        }
        return results;
    }

    private static Result check(ScriptScene scene, Map<Long, Actor> actors,
                                NavigableMap<LocalDate, Map<Long, ActorDay>> days, LocalTime sunrise, LocalTime sunset) {
        int minutes = scene.estMinutes() == null ? DEFAULT_MINUTES : scene.estMinutes();
        List<Long> actorIds = scene.characters().stream().map(SceneCharacter::actorId).filter(Objects::nonNull)
                .distinct().toList();
        List<String> uncast = scene.characters().stream().filter(c -> c.actorId() == null)
                .map(SceneCharacter::name).toList();
        if (!uncast.isEmpty()) {
            return new Result(scene.code(), scene.heading(), actorIds, minutes, null,
                    String.join(", ", uncast) + " 배역에 배우가 정해지지 않았습니다.");
        }
        LocalTime from = !scene.exterior() ? INTERIOR_FROM : scene.night() ? sunset : sunrise;
        LocalTime to = scene.exterior() && !scene.night() ? sunset : DAY_END;
        for (Map.Entry<LocalDate, Map<Long, ActorDay>> day : days.entrySet()) {
            if (longestRun(free(actorIds, actors, day.getValue(), from, to)) >= minutes) {
                return new Result(scene.code(), scene.heading(), actorIds, minutes, day.getKey(), null);
            }
        }
        // 함께 비는 날이 없으면 혼자서도 시간을 못 내는 배우를 이유로 든다. 그런 배우가 없으면 일정이 엇갈리는 것이다.
        String label = (scene.exterior() ? (scene.night() ? "밤 야외" : "낮 야외") : "실내") + " 장면 " + minutes + "분";
        for (long actorId : actorIds) {
            boolean anyDay = days.values().stream()
                    .anyMatch(d -> longestRun(free(List.of(actorId), actors, d, from, to)) >= minutes);
            if (!anyDay) {
                Actor actor = actors.get(actorId);
                return new Result(scene.code(), scene.heading(), actorIds, minutes, null,
                        actor.name() + "은(는) 기간 안에 " + label + "을 낼 수 있는 날이 없습니다(계약 가능 시간 "
                                + actor.availableFrom().format(HH_MM) + "~" + actor.availableTo().format(HH_MM) + ").");
            }
        }
        return new Result(scene.code(), scene.heading(), actorIds, minutes, null,
                "등장 배우가 기간 안에 함께 " + label + "을 낼 수 있는 날이 없습니다.");
    }

    /** 분 단위로 모든 배우가 비는지 표시한다. 날짜별 일정이 없는 배우는 계약 기본 시간으로 본다. */
    private static boolean[] free(List<Long> actorIds, Map<Long, Actor> actors, Map<Long, ActorDay> day,
                                  LocalTime from, LocalTime to) {
        boolean[] free = new boolean[24 * 60];
        for (int m = minute(from); m < minute(to); m++) {
            free[m] = true;
        }
        for (long actorId : actorIds) {
            Actor actor = actors.get(actorId);
            ActorDay actorDay = day.getOrDefault(actorId, ActorDay.of(actor));
            boolean[] mine = new boolean[24 * 60];
            if (!actorDay.off()) {
                for (ActorDay.Window w : actorDay.windows()) {
                    for (int m = minute(w.from()); m < minute(w.to()); m++) {
                        mine[m] = true;
                    }
                }
                for (ActorDay.Busy b : actorDay.busy()) {
                    for (int m = minute(b.from()); m < minute(b.to()); m++) {
                        mine[m] = false;
                    }
                }
            }
            int limit = actor.noNight() ? minute(NIGHT_LIMIT) : free.length;
            for (int m = 0; m < free.length; m++) {
                free[m] &= mine[m] && m < limit;
            }
        }
        return free;
    }

    private static int longestRun(boolean[] free) {
        int best = 0;
        int run = 0;
        for (boolean f : free) {
            run = f ? run + 1 : 0;
            best = Math.max(best, run);
        }
        return best;
    }

    private static int minute(LocalTime time) {
        return time.getHour() * 60 + time.getMinute();
    }
}
