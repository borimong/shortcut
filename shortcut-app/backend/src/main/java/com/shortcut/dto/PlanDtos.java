package com.shortcut.dto;

import com.shortcut.domain.Equipment;
import com.shortcut.dto.BoardDtos.EquipmentView;
import com.shortcut.dto.BoardDtos.ForecastView;
import com.shortcut.dto.BoardDtos.HourlyView;
import com.shortcut.engine.ExtraConstraint;
import com.shortcut.engine.Finding;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import jakarta.validation.constraints.NotEmpty;
import java.time.LocalDate;
import java.time.LocalTime;
import java.util.List;
import java.util.Map;

public final class PlanDtos {

    private PlanDtos() {
    }

    public record EvaluateRequest(@NotNull Long shootDayId, Map<String, Double> weights,
                                  List<ExtraConstraint> extraConstraints, List<String> excludeHashes) {
    }

    public record EvaluateResponse(int dataVersion, Map<String, Double> weights, long feasibleCount,
                                   List<CandidateView> candidates) {
    }

    public record CandidateView(String hash, CandidateLocation location, CandidateEquipment equipment,
                                CandidateTime time, boolean feasible, List<Finding> violations, List<Finding> warnings,
                                Map<String, Double> softScores, double totalScore, long cost, long extraCost,
                                double distanceKm) {
    }

    public record CandidateLocation(int optionNo, long id, String name, boolean indoor) {
    }

    public record CandidateEquipment(int optionNo, List<EquipmentView> items) {
    }

    public record CandidateTime(int optionNo, LocalTime start, LocalTime end) {
    }

    public record RegisterAlternativesRequest(@NotEmpty @Size(max = 3) List<Long> externalLocationIds,
                                              List<String> keywords) {
    }

    public record AlternativeLocationView(long locationId, long externalId, String name, boolean indoor, String region,
                                          double distanceKm, long cost, double fit, List<String> matchedKeywords) {
    }

    public record ValidateRequest(@NotNull Long shootDayId, @NotNull @Valid CandidateInput candidate,
                                  List<ExtraConstraint> extraConstraints, @NotNull Integer dataVersion) {
    }

    public record CandidateInput(@NotNull Long locationId, @NotNull List<Long> equipmentIds,
                                 @NotNull LocalTime start, @NotNull LocalTime end) {
    }

    public record ValidateResponse(boolean valid, boolean stale, int dataVersion, List<Finding> violations,
                                   List<Finding> warnings) {
    }

    public record PlanSetResponse(long shootDayId, int dataVersion, PlanBlock block, PlanCurrent current,
                                  List<PlanOptionView> options) {
    }

    public record PlanBlock(String code, int durationMin, List<PlanScene> scenes, List<Long> actorIds) {
    }

    public record PlanScene(String code, String title, int durationMin, List<Long> actorIds, boolean outdoorIntent) {
    }

    public record PlanCurrent(PlanLocation location, List<EquipmentView> equipment, LocalTime start, LocalTime end,
                              long cost) {
    }

    public record PlanLocation(long id, String name, boolean indoor, String region, long cost, double distanceKm,
                               double fit) {
    }

    public record PlanOptionView(int optionNo, PlanLocation location, List<EquipmentView> equipment,
                                 double equipmentFit, LocalTime start, LocalTime end) {
    }

    public record AvailabilityResponse(List<ActorAvailability> actors, List<LocationAvailability> locations,
                                       List<Equipment> equipment, double crewWeeklyHoursUsed) {
    }

    public record ActorAvailability(long id, String name, LocalTime availableFrom, LocalTime availableTo,
                                    double weeklyHoursUsed, String contractDocId, boolean noNight,
                                    Double maxDailyHours) {
    }

    public record LocationAvailability(long id, String name, boolean indoor, String region, LocalTime openFrom,
                                       LocalTime openTo, LocalTime permitFrom, LocalTime permitTo,
                                       boolean noFlyZone, String note, boolean available) {
    }

    /** weatherSource는 관리자 설정의 예보 선택(SEED 또는 LIVE)이다. 장소마다 실제로 쓴 예보는 forecast에 있다. */
    public record WeatherResponse(LocalDate date, List<LocationWeather> locations, double rainBlockMm, double rainWarnMm,
                                  String weatherSource) {
    }

    public record LocationWeather(long locationId, String name, boolean indoor, List<HourlyView> hourly,
                                  ForecastView forecast) {
    }

    public record ExternalLocationView(long id, String name, boolean indoor, String region, double distanceKm,
                                       long cost, List<String> keywords, String source) {
    }
}
