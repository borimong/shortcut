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
                                List<ContactView> contacts, PendingProposalView pendingProposal) {
    }

    public record ProjectView(long id, String name) {
    }

    public record ShootDayView(long id, LocalDate date, LocalTime callTime, int dataVersion, String notice) {
    }

    public record CallsheetRef(int versionNo, OffsetDateTime createdAt) {
    }

    public record BlockView(String code, LocalTime start, LocalTime end, LocationView location,
                            List<EquipmentView> equipment, List<SceneView> scenes) {
    }

    public record LocationView(long id, String name, String address, boolean indoor, String region) {
    }

    public record EquipmentView(long id, String name) {
    }

    public record SceneView(String code, String title, int durationMin, List<String> actors) {
    }

    public record WeatherView(String locationName, List<HourlyView> hourly, String summary) {
    }

    public record HourlyView(int hour, int precipProb) {
    }

    public record ContactView(String title, String name, String phoneMasked) {
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
