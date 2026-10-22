package com.shortcut.dto;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.util.List;

public final class BoardDtos {

    private BoardDtos() {
    }

    public record BoardResponse(ProjectView project, ShootDayView shootDay, CallsheetRef callsheet,
                                List<BlockView> blocks, JsonNode crewCallTimes, WeatherView weather,
                                List<ContactView> contacts, PendingProposalView pendingProposal,
                                List<BlockWeatherView> blockWeather, RainRuleView rainRule) {
    }

    public record ProjectView(long id, String name) {
    }

    /** dayNo는 같은 작품의 촬영일을 날짜순으로 셌을 때의 회차이고, totalDays는 전체 회차 수다. */
    public record ShootDayView(long id, LocalDate date, LocalTime callTime, int dataVersion, String notice,
                               int dayNo, int totalDays) {
    }

    public record CallsheetRef(int versionNo, OffsetDateTime createdAt) {
    }

    public record BlockView(String code, LocalTime start, LocalTime end, LocationView location,
                            List<EquipmentView> equipment, List<SceneView> scenes) {
    }

    public record LocationView(long id, String name, String address, boolean indoor, String region) {
    }

    public record EquipmentView(long id, String name, boolean available) {
    }

    /** characters는 "배역(배우)" 모양이다. intExt, timeOfDay는 대본의 실내/실외와 낮/밤이다. */
    public record SceneView(String code, String title, int durationMin, List<String> actors, String heading,
                            String intExt, String timeOfDay, List<String> characters) {
    }

    public record WeatherView(String locationName, List<HourlyView> hourly, String summary, ForecastView forecast) {
    }

    /**
     * 예보 출처와 갱신 시각이다.
     *
     * @param source LIVE(날씨 API 예보), SEED(시연용 시드 예보), NONE(실시간 예보를 쓰는데 이 장소 예보를 아직 못 받음)
     * @param updatedAt 날씨 API 예보를 마지막으로 받은 시각. LIVE일 때만 있다
     * @param stale 마지막 갱신이 오래되어 최근 갱신이 실패한 것으로 보이는지. 이때도 마지막으로 받은 값을 쓴다
     * @param manual 변경 입력으로 이 장소의 강수량을 덮어썼는지. 덮어쓴 시간대는 예보보다 입력값이 우선한다
     */
    public record ForecastView(String source, OffsetDateTime updatedAt, boolean stale, boolean manual) {
    }

    /** 시각별 시간당 강수량(mm)이다. */
    public record HourlyView(int hour, double precipMm) {
    }

    /** 블록마다 그 블록 촬영지의 날씨다. 화면은 지금 시각에 촬영 중인 블록의 날씨를 고른다. */
    public record BlockWeatherView(String blockCode, long locationId, String locationName, boolean indoor,
                                   List<HourlyView> hourly, String summary, ForecastView forecast) {
    }

    /** 관리자 설정의 강수 기준이다. 화면 강조 색과 엔진 판정이 같은 값을 쓴다. */
    public record RainRuleView(double blockMm, double warnMm) {
    }

    public record ContactView(String title, String name, String phone) {
    }

    public record PendingProposalView(long id, String versionNo, String status) {
    }

    public record CallsheetSummary(int versionNo, OffsetDateTime createdAt, Long proposalId) {
    }

    public record CallsheetContent(long shootDayId, int versionNo, Long proposalId, OffsetDateTime createdAt,
                                   LocalDate shootDate, LocalTime callTime, List<BlockView> blocks) {
    }

    public record HistoryItem(OffsetDateTime at, String kind, String text, String link) {
    }
}
