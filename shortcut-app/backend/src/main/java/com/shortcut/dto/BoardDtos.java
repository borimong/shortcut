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

    public record SceneView(String code, String title, int durationMin, List<String> actors) {
    }

    public record WeatherView(String locationName, List<HourlyView> hourly, String summary) {
    }

    /** 시각별 시간당 강수량(mm)이다. */
    public record HourlyView(int hour, double precipMm) {
    }

    /** 블록마다 그 블록 촬영지의 날씨다. 화면은 지금 시각에 촬영 중인 블록의 날씨를 고른다. */
    public record BlockWeatherView(String blockCode, long locationId, String locationName, boolean indoor,
                                   List<HourlyView> hourly, String summary) {
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
