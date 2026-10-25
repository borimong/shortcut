package com.shortcut.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.shortcut.config.ShortcutProperties;
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/**
 * Open-Meteo 예보 API로 지점별 시간당 강수량(mm)을 받는다. 무료 API는 키 없이 위경도를 그대로 넘긴다.
 * 여러 지점을 한 번에 물으면 지점 순서대로 배열이 오고, 한 지점만 물으면 객체 하나가 온다.
 */
@Component
public class OpenMeteoClient {

    public record Point(double latitude, double longitude) {
    }

    private final RestClient http;
    private final String apiKey;

    public OpenMeteoClient(ShortcutProperties properties) {
        ShortcutProperties.Weather weather = properties.weather();
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        // 4안 장소 등록 요청 안에서도 부르므로 API가 느리면 오래 기다리지 않고 마지막 예보를 쓴다.
        factory.setConnectTimeout(Duration.ofSeconds(3));
        factory.setReadTimeout(Duration.ofSeconds(5));
        this.http = RestClient.builder().baseUrl(weather.openMeteoUrl()).requestFactory(factory).build();
        this.apiKey = weather.apiKey();
    }

    /**
     * 지점마다 날짜와 시각(서울 시간)별 시간당 강수량을 돌려준다. 결과 순서는 points 순서와 같다.
     */
    public List<Map<LocalDate, Map<Integer, Double>>> hourlyPrecip(List<Point> points, LocalDate from, LocalDate to) {
        String latitudes = points.stream().map(p -> String.valueOf(p.latitude())).collect(Collectors.joining(","));
        String longitudes = points.stream().map(p -> String.valueOf(p.longitude())).collect(Collectors.joining(","));
        JsonNode body = http.get()
                .uri(b -> {
                    b.path("/v1/forecast")
                            .queryParam("latitude", latitudes)
                            .queryParam("longitude", longitudes)
                            .queryParam("hourly", "precipitation")
                            .queryParam("timezone", "Asia/Seoul")
                            .queryParam("start_date", from)
                            .queryParam("end_date", to);
                    if (apiKey != null && !apiKey.isBlank()) {
                        b.queryParam("apikey", apiKey);
                    }
                    return b.build();
                })
                .retrieve()
                .body(JsonNode.class);
        return parse(body, points.size());
    }

    static List<Map<LocalDate, Map<Integer, Double>>> parse(JsonNode body, int expected) {
        List<JsonNode> items = new ArrayList<>();
        if (body != null && body.isArray()) {
            body.forEach(items::add);
        } else if (body != null) {
            items.add(body);
        }
        if (items.size() != expected) {
            throw new IllegalStateException("Open-Meteo 응답 지점 수가 요청과 다릅니다: " + items.size() + "/" + expected);
        }
        return items.stream().map(OpenMeteoClient::parsePoint).toList();
    }

    private static Map<LocalDate, Map<Integer, Double>> parsePoint(JsonNode item) {
        JsonNode times = item.path("hourly").path("time");
        JsonNode values = item.path("hourly").path("precipitation");
        if (!times.isArray() || !values.isArray() || times.size() != values.size()) {
            throw new IllegalStateException("Open-Meteo 응답에 시간별 강수량이 없습니다.");
        }
        Map<LocalDate, Map<Integer, Double>> byDate = new TreeMap<>();
        for (int i = 0; i < times.size(); i++) {
            // 값이 빈 시각은 넣지 않는다. 저장할 때 그 시각은 마지막으로 받은 값이 남는다.
            if (values.get(i).isNull()) {
                continue;
            }
            LocalDateTime at = LocalDateTime.parse(times.get(i).asText());
            double mm = Math.round(values.get(i).asDouble() * 10) / 10.0;
            byDate.computeIfAbsent(at.toLocalDate(), d -> new TreeMap<>()).put(at.getHour(), mm);
        }
        return byDate;
    }
}
