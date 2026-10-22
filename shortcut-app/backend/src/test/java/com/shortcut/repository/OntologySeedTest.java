package com.shortcut.repository;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

/**
 * data.sql의 온톨로지 시드를 업무 시드(data.sql, 대본 시드, 씬 배정 시드)와 DB 없이 맞춰 본다.
 * 규칙은 기동 때 도는 OntologyRepository.findOrphanNodeIds와 같다. 노드 ID는 TYPE:업무 키이고,
 * 촬영일에 딸린 노드는 props의 shootDayId가 업무 행의 촬영일과 같아야 한다.
 */
class OntologySeedTest {

    private static final ObjectMapper JSON = new ObjectMapper();
    // 서버가 시드를 넣는 순서(application.yml의 data-locations)와 같게 이어 붙인다. 씬 배정은 data-schedule.sql에 있다.
    private static final String SEED = SeedRows.read("data.sql", "data-script.sql", "data-schedule.sql");

    @Test
    void 시드_노드는_모두_업무_시드_행을_가리킨다() throws Exception {
        Map<String, Long> business = businessKeys();
        for (Map<String, String> node : rows("ontology_nodes")) {
            String id = node.get("node_id");
            String type = node.get("type");
            assertThat(id).as("노드 ID의 타입").startsWith(type + ":");
            if (type.equals("STAFF") || type.equals("CONSTRAINT")) {
                continue;
            }
            assertThat(business).as("업무 행이 없는 노드 " + id).containsKey(id);
            Long shootDayId = business.get(id);
            if (shootDayId != null) {
                JsonNode props = JSON.readTree(node.get("props"));
                assertThat(props.path("shootDayId").asLong()).as(id + "의 촬영일").isEqualTo(shootDayId);
            }
        }
    }

    @Test
    void 시드_엣지의_양끝은_시드_노드다() {
        Set<String> nodes = rows("ontology_nodes").stream().map(n -> n.get("node_id")).collect(Collectors.toSet());
        for (Map<String, String> edge : rows("ontology_edges")) {
            assertThat(nodes).contains(edge.get("src"), edge.get("dst"));
        }
    }

    @Test
    void 촬영일마다_1_2_3안이_블록의_후보로_이어진다() {
        Set<String> candidates = rows("ontology_edges").stream()
                .filter(e -> e.get("relation").equals("후보"))
                .map(e -> e.get("src") + " → " + e.get("dst"))
                .collect(Collectors.toSet());
        List<Map<String, String>> options = rows("plan_options");
        assertThat(options).extracting(o -> o.get("shoot_day_id")).contains("1", "2", "3");
        for (Map<String, String> option : options) {
            String day = option.get("shoot_day_id");
            assertThat(candidates).contains("BLOCK:" + day + "-" + option.get("block_code") + " → PLAN:" + day + "-"
                    + option.get("option_no"));
        }
    }

    /**
     * 업무 시드 행에서 있어야 할 노드 ID와 그 행의 촬영일(촬영일에 딸리지 않으면 null)을 모은다.
     * 2회차 촬영일은 1회차 날짜에서 계산해 SELECT로 넣으므로, 촬영일은 외래키로 촬영일을 가리키는 블록 시드에서 모은다.
     */
    private static Map<String, Long> businessKeys() {
        Map<String, Long> keys = new HashMap<>();
        for (Map<String, String> b : rows("blocks")) {
            long day = Long.parseLong(b.get("shoot_day_id"));
            keys.put("SHOOT_DAY:" + day, day);
            keys.put("BLOCK:" + day + "-" + b.get("code"), day);
        }
        rows("scenes").forEach(s -> keys.put("SCENE:" + s.get("code"), Long.parseLong(s.get("shoot_day_id"))));
        rows("plan_options").forEach(o -> keys.put("PLAN:" + o.get("shoot_day_id") + "-" + o.get("option_no"),
                Long.parseLong(o.get("shoot_day_id"))));
        rows("reservations").forEach(r -> keys.put("RESERVATION:" + r.get("id"), Long.parseLong(r.get("shoot_day_id"))));
        rows("actors").forEach(a -> {
            keys.put("ACTOR:" + a.get("id"), null);
            keys.put("CONTRACT:" + a.get("contract_doc_id"), null);
        });
        rows("locations").forEach(l -> keys.put("LOCATION:" + l.get("id"), null));
        rows("equipment").forEach(e -> keys.put("EQUIPMENT:" + e.get("id"), null));
        rows("characters").forEach(c -> keys.put("CHARACTER:" + c.get("id"), null));
        return keys;
    }

    private static List<Map<String, String>> rows(String table) {
        return SeedRows.rows(SEED, table);
    }
}
