package com.shortcut.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class OpenMeteoClientTest {

    private static final ObjectMapper JSON = new ObjectMapper();

    @Test
    void 한_지점_응답을_날짜와_시각별_강수량으로_나눈다() throws Exception {
        JsonNode body = JSON.readTree("""
                {"hourly": {"time": ["2026-10-22T12:00", "2026-10-22T13:00", "2026-10-23T13:00"],
                            "precipitation": [0.04, 8.26, null]}}
                """);

        List<Map<LocalDate, Map<Integer, Double>>> parsed = OpenMeteoClient.parse(body, 1);

        // 소수 한 자리로 반올림하고, 값이 빈 시각은 빼서 저장할 때 마지막 값이 남게 한다.
        assertThat(parsed.get(0)).containsOnlyKeys(LocalDate.of(2026, 10, 22));
        assertThat(parsed.get(0).get(LocalDate.of(2026, 10, 22))).containsExactly(Map.entry(12, 0.0), Map.entry(13, 8.3));
    }

    @Test
    void 여러_지점_응답은_요청_순서대로_돌려준다() throws Exception {
        JsonNode body = JSON.readTree("""
                [{"hourly": {"time": ["2026-10-22T13:00"], "precipitation": [8.0]}},
                 {"hourly": {"time": ["2026-10-22T13:00"], "precipitation": [0.0]}}]
                """);

        List<Map<LocalDate, Map<Integer, Double>>> parsed = OpenMeteoClient.parse(body, 2);

        assertThat(parsed).extracting(p -> p.get(LocalDate.of(2026, 10, 22)).get(13)).containsExactly(8.0, 0.0);
    }

    @Test
    void 지점_수가_다르거나_시간별_값이_없으면_실패로_본다() throws Exception {
        JsonNode one = JSON.readTree("{\"hourly\": {\"time\": [], \"precipitation\": []}}");
        JsonNode error = JSON.readTree("{\"error\": true, \"reason\": \"Latitude must be in range\"}");

        assertThatThrownBy(() -> OpenMeteoClient.parse(one, 2)).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> OpenMeteoClient.parse(error, 1)).isInstanceOf(IllegalStateException.class);
    }
}
