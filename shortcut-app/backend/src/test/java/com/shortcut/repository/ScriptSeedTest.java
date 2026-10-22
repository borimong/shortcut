package com.shortcut.repository;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

/**
 * 대본 시드(data-script.sql)와 제작부 시드(data-schedule.sql), 기본 시드(data.sql)를 DB 없이 맞춰 본다.
 * 촬영 배정한 씬은 대본에 있고 등장 배역이 모두 캐스팅되어 있어야 하며,
 * 블록 씬 길이 합이 블록 길이와 같아야 한다. 배우 일정 목데이터의 시연용 겹친 날도 확인한다.
 */
class ScriptSeedTest {

    private static final String SEED = SeedRows.read("data.sql", "data-script.sql", "data-schedule.sql");

    @Test
    void 촬영_배정한_씬은_모두_대본에_있다() {
        Set<String> script = SeedRows.rows(SEED, "script_scenes").stream().map(s -> s.get("code"))
                .collect(Collectors.toSet());
        assertThat(script).hasSize(23);
        assertThat(SeedRows.rows(SEED, "scenes")).extracting(s -> s.get("code")).allSatisfy(code ->
                assertThat(script).contains(code));
    }

    @Test
    void 촬영_배정한_씬은_등장_배역이_있고_모두_캐스팅되어_있다() {
        // 출연 배우는 등장 배역의 캐스팅에서 읽는다. data-schedule.sql은 배역 1~5를 배우 1~5에 캐스팅한다.
        Set<Long> castCharacters = Set.of(1L, 2L, 3L, 4L, 5L);
        assertThat(SEED).contains("FROM (VALUES (1, 1), (2, 2), (3, 3), (4, 4), (5, 5)) AS v (character_id, actor_id)");
        Map<String, Set<Long>> characters = new HashMap<>();
        for (Map<String, String> row : SeedRows.rows(SEED, "scene_characters")) {
            characters.computeIfAbsent(row.get("scene_code"), k -> new TreeSet<>())
                    .add(Long.parseLong(row.get("character_id")));
        }
        for (Map<String, String> scene : SeedRows.rows(SEED, "scenes")) {
            assertThat(characters.get(scene.get("code"))).as(scene.get("code") + "의 등장 배역").isNotEmpty()
                    .allSatisfy(id -> assertThat(castCharacters).contains(id));
        }
    }

    @Test
    void 블록_씬_길이_합이_블록_길이와_같다() {
        Map<String, Integer> sums = new HashMap<>();
        for (Map<String, String> scene : SeedRows.rows(SEED, "scenes")) {
            sums.merge(scene.get("shoot_day_id") + "-" + scene.get("block_code"),
                    Integer.parseInt(scene.get("duration_min")), Integer::sum);
        }
        for (Map<String, String> block : SeedRows.rows(SEED, "blocks")) {
            String key = block.get("shoot_day_id") + "-" + block.get("code");
            assertThat(sums.get(key)).as(key + " 블록 씬 길이 합").isEqualTo(Integer.parseInt(block.get("duration_min")));
        }
    }

    @Test
    void 시연용으로_겹친_배우_일정은_세_건이다() {
        assertThat(SEED.split("\\[시연]", -1)).hasSize(4);
    }
}
