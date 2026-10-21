package com.shortcut.repository;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;

/**
 * data.sql의 온톨로지 시드를 같은 파일의 업무 시드와 DB 없이 맞춰 본다.
 * 규칙은 기동 때 도는 OntologyRepository.findOrphanNodeIds와 같다. 노드 ID는 TYPE:업무 키이고,
 * 촬영일에 딸린 노드는 props의 shootDayId가 업무 행의 촬영일과 같아야 한다.
 */
class OntologySeedTest {

    private static final ObjectMapper JSON = new ObjectMapper();
    private static final String SEED = read("data.sql");

    @Test
    void 시드_노드는_모두_업무_시드_행을_가리킨다() throws IOException {
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
        assertThat(options).extracting(o -> o.get("shoot_day_id")).contains("1", "2");
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
        return keys;
    }

    /**
     * INSERT INTO table (열, ...) VALUES (...), (...) 형식의 시드 행을 열 이름 → 값으로 읽는다. 따옴표 값은 벗긴다.
     */
    private static List<Map<String, String>> rows(String table) {
        List<Map<String, String>> rows = new ArrayList<>();
        Matcher insert = Pattern.compile("INSERT INTO " + table + " \\(([^)]*)\\)\\s*VALUES").matcher(SEED);
        while (insert.find()) {
            String[] columns = insert.group(1).split(",");
            for (List<String> tuple : tuples(insert.end())) {
                Map<String, String> row = new HashMap<>();
                for (int i = 0; i < columns.length; i++) {
                    row.put(columns[i].strip(), tuple.get(i));
                }
                rows.add(row);
            }
        }
        return rows;
    }

    /**
     * VALUES 뒤의 괄호 묶음을 값 목록으로 나눈다. 따옴표 안의 쉼표와 괄호는 값의 일부이고, 주석은 건너뛴다.
     * 괄호 밖에서 쉼표와 공백이 아닌 글자(ON CONFLICT, 세미콜론)가 나오면 VALUES가 끝난 것이다.
     */
    private static List<List<String>> tuples(int from) {
        List<List<String>> tuples = new ArrayList<>();
        List<String> values = new ArrayList<>();
        StringBuilder value = new StringBuilder();
        boolean quoted = false;
        int depth = 0;
        for (int i = from; i < SEED.length(); i++) {
            char c = SEED.charAt(i);
            if (c == '\'') {
                quoted = !quoted;
                value.append(c);
            } else if (quoted) {
                value.append(c);
            } else if (c == '-' && SEED.startsWith("--", i)) {
                int lineEnd = SEED.indexOf('\n', i);
                i = lineEnd < 0 ? SEED.length() : lineEnd;
            } else if (c == '(') {
                if (depth++ > 0) {
                    value.append(c);
                }
            } else if (c == ')') {
                if (--depth > 0) {
                    value.append(c);
                } else {
                    values.add(literal(value));
                    tuples.add(values);
                    values = new ArrayList<>();
                }
            } else if (depth == 1 && c == ',') {
                values.add(literal(value));
            } else if (depth > 0) {
                value.append(c);
            } else if (c != ',' && !Character.isWhitespace(c)) {
                break;
            }
        }
        return tuples;
    }

    private static String literal(StringBuilder raw) {
        String value = raw.toString().strip();
        raw.setLength(0);
        return value.startsWith("'") && value.endsWith("'")
                ? value.substring(1, value.length() - 1).replace("''", "'")
                : value;
    }

    private static String read(String path) {
        try {
            return new ClassPathResource(path).getContentAsString(StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
