package com.shortcut.engine;

import static com.shortcut.engine.SeedPlan.t;
import static org.assertj.core.api.Assertions.assertThat;

import com.shortcut.domain.Actor;
import com.shortcut.domain.SceneCharacter;
import com.shortcut.domain.ScriptScene;
import java.time.LocalDate;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import org.junit.jupiter.api.Test;

class PlaceabilityTest {

    private static final LocalDate DAY1 = LocalDate.of(2026, 10, 22);
    private static final Map<Long, Actor> ACTORS = Map.of(
            1L, new Actor(1, "배우 A", t("09:00"), t("16:00"), 44, "contract-actor-a-v3", true, 10.0, null),
            2L, new Actor(2, "배우 B", t("07:00"), t("22:00"), 38, "contract-actor-b-v1", false, null, null),
            3L, new Actor(3, "배우 C", t("06:30"), t("20:00"), 30, "contract-actor-c-v2", false, null, null));
    private static final SceneCharacter JIWOO = new SceneCharacter(1, "봉지우", 1L);
    private static final SceneCharacter DOHYUN = new SceneCharacter(2, "강도현", 2L);
    private static final SceneCharacter BONG = new SceneCharacter(3, "봉재필", 3L);

    @Test
    void 계약상_낮에만_되는_배우가_나오는_밤_야외_장면은_어느_날에도_못_찍는다() {
        ScriptScene alley = new ScriptScene("S09", "S#09. 지우네 집 앞 골목 (밤, 실외)", "EXT", "NIGHT", 30,
                List.of(JIWOO, DOHYUN), List.of());

        Placeability.Result result = Placeability.check(List.of(alley), ACTORS, days(7, Map.of()), t("06:50"), t("17:40"))
                .getFirst();

        assertThat(result.placeable()).isFalse();
        assertThat(result.reason()).contains("배우 A", "밤 야외 장면 30분", "09:00~16:00");
    }

    @Test
    void 함께_비는_첫_날을_찾고_배정한_씬은_보지_않는다() {
        ScriptScene door = new ScriptScene("S20", "S#20. 작업실 문 앞 (낮, 실내)", "INT", "DAY", 30,
                List.of(JIWOO, DOHYUN, BONG), List.of());
        ScriptScene assigned = new ScriptScene("S12", "S#12. 한강 공원 산책로 (낮, 실외)", "EXT", "DAY", null,
                List.of(JIWOO, DOHYUN), List.of(1L));
        // 첫날은 배우 C가 종일 다른 작품을 찍는다.
        Map<LocalDate, Map<Long, ActorDay>> busy = Map.of(DAY1,
                Map.of(3L, new ActorDay(3, true, "OTHER_PRODUCTION", List.of(), List.of())));

        List<Placeability.Result> results = Placeability.check(List.of(door, assigned), ACTORS, days(7, busy),
                t("06:50"), t("17:40"));

        assertThat(results).hasSize(1);
        assertThat(results.getFirst().placeable()).isTrue();
        assertThat(results.getFirst().firstDate()).isEqualTo(DAY1.plusDays(1));
    }

    @Test
    void 캐스팅_전_배역이_있으면_배정할_수_없다() {
        ScriptScene cafe = new ScriptScene("S10", "S#10. 문태의 카페 (낮, 실내)", "INT", "DAY", 30,
                List.of(DOHYUN, new SceneCharacter(4, "문태", null)), List.of());

        Placeability.Result result = Placeability.check(List.of(cafe), ACTORS, days(7, Map.of()), t("06:50"), t("17:40"))
                .getFirst();

        assertThat(result.placeable()).isFalse();
        assertThat(result.reason()).contains("문태 배역에 배우가 정해지지 않았습니다");
    }

    /** 날짜마다 배우별 하루를 만든다. 따로 준 날은 그 값을, 나머지는 계약 기본 시간을 쓴다. */
    private static TreeMap<LocalDate, Map<Long, ActorDay>> days(int count, Map<LocalDate, Map<Long, ActorDay>> overrides) {
        TreeMap<LocalDate, Map<Long, ActorDay>> days = new TreeMap<>();
        for (int i = 0; i < count; i++) {
            LocalDate date = DAY1.plusDays(i);
            Map<Long, ActorDay> byActor = new HashMap<>();
            ACTORS.values().forEach(a -> byActor.put(a.id(), ActorDay.of(a)));
            byActor.putAll(overrides.getOrDefault(date, Map.of()));
            days.put(date, byActor);
        }
        return days;
    }
}
