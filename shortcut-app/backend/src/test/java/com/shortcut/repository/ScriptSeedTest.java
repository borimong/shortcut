package com.shortcut.repository;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

/**
 * 대본 시드(data-script.sql)와 제작부 시드(data-schedule.sql), 기본 시드(data.sql)를 DB 없이 맞춰 본다.
 * 촬영 배정한 씬은 대본에 있어야 하고, 등장 배역의 캐스팅이 예전 출연 배우 열과 같아야 하며,
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
    void 등장_배역의_캐스팅이_씬의_출연_배우와_같다() {
        // data-schedule.sql의 캐스팅은 배역 id와 배우 id가 같다(UPDATE ... VALUES (1, 1), (2, 2) ...).
        Map<String, Set<Long>> cast = new HashMap<>();
        for (Map<String, String> row : SeedRows.rows(SEED, "scene_characters")) {
            cast.computeIfAbsent(row.get("scene_code"), k -> new TreeSet<>()).add(Long.parseLong(row.get("character_id")));
        }
        for (Map<String, String> scene : SeedRows.rows(SEED, "scenes")) {
            Set<Long> actors = new TreeSet<>(parseIds(scene.get("actor_ids")));
            assertThat(cast.get(scene.get("code"))).as(scene.get("code") + "의 등장 배역").isEqualTo(actors);
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
    void 야외_의도_열이_대본의_실외와_같다() {
        Map<String, String> intExt = SeedRows.rows(SEED, "script_scenes").stream()
                .collect(Collectors.toMap(s -> s.get("code"), s -> s.get("int_ext")));
        for (Map<String, String> scene : SeedRows.rows(SEED, "scenes")) {
            assertThat(Boolean.parseBoolean(scene.get("outdoor_intent"))).as(scene.get("code"))
                    .isEqualTo("EXT".equals(intExt.get(scene.get("code"))));
        }
    }

    @Test
    void 시연용으로_겹친_배우_일정은_세_건이다() {
        assertThat(SEED.split("\\[시연]", -1)).hasSize(4);
    }

    private static List<Long> parseIds(String json) {
        String inner = json.replace("[", "").replace("]", "").strip();
        return inner.isEmpty() ? List.of() : Arrays.stream(inner.split(",")).map(String::strip)
                .map(Long::parseLong).toList();
    }
}
