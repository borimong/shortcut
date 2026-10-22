package com.shortcut.dto;

import com.shortcut.domain.Equipment;
import com.shortcut.domain.SceneCharacter;
import com.shortcut.domain.SceneRequirement;
import com.shortcut.dto.BoardDtos.EquipmentView;
import com.shortcut.dto.BoardDtos.ForecastView;
import com.shortcut.dto.BoardDtos.HourlyView;
import com.shortcut.dto.ScheduleDtos.BusyView;
import com.shortcut.dto.ScheduleDtos.WindowView;
import com.shortcut.engine.ExtraConstraint;
import com.shortcut.engine.Finding;
import com.shortcut.engine.SceneSlot;
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

    /**
     * sceneOrder는 이 후보로 찍을 오후 블록 씬 시각표다. 지금 순서로 배우 일정이나 해에 막히면 엔진이 순서를 바꾸고
     * sceneOrderChanged가 true가 된다. 그 순서를 validate와 변경안에 그대로 넘긴다.
     */
    public record CandidateView(String hash, CandidateLocation location, CandidateEquipment equipment,
                                CandidateTime time, boolean feasible, List<Finding> violations, List<Finding> warnings,
                                Map<String, Double> softScores, double totalScore, long cost, long extraCost,
                                double distanceKm, List<SceneSlot> sceneOrder, boolean sceneOrderChanged) {
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

    /** sceneOrder는 오후 블록 씬 코드 순서다. 비우면 엔진이 후보 평가 때와 같은 방법으로 고른다. */
    public record CandidateInput(@NotNull Long locationId, @NotNull List<Long> equipmentIds,
                                 @NotNull LocalTime start, @NotNull LocalTime end, List<String> sceneOrder) {
    }

    /** sceneOrder는 판정에 쓴 씬 시각표다. */
    public record ValidateResponse(boolean valid, boolean stale, int dataVersion, List<Finding> violations,
                                   List<Finding> warnings, List<SceneSlot> sceneOrder, boolean sceneOrderChanged) {
    }

    public record PlanSetResponse(long shootDayId, int dataVersion, PlanBlock block, PlanCurrent current,
                                  List<PlanOptionView> options) {
    }

    /** sunrise, sunset은 낮/밤 대본 규칙에 쓰는 그날의 일출과 일몰이다. */
    public record PlanBlock(String code, int durationMin, List<PlanScene> scenes, List<Long> actorIds,
                            LocalTime sunrise, LocalTime sunset) {
    }

    /**
     * 씬과 대본 분해 값이다. outdoorIntent는 예전 이름이고 intExt가 EXT인지와 같다.
     * characters의 actorId가 비어 있으면 캐스팅 전 배역이고, requirements의 level은 MUST(필수) 또는 WANT(선호)다.
     */
    public record PlanScene(String code, String title, int durationMin, List<Long> actorIds, boolean outdoorIntent,
                            String heading, String intExt, String timeOfDay, String setting, boolean settingLocked,
                            Long locationId, List<SceneCharacter> characters, List<SceneRequirement> requirements) {
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

    /**
     * availableFrom~To는 계약 기본 시간(변경 입력의 가용 시간 반영)이다. 그날 실제로 쓰는 값은 off, windows, busy다.
     * busy에는 개인 사정 대신 사유 종류만 담는다.
     */
    public record ActorAvailability(long id, String name, LocalTime availableFrom, LocalTime availableTo,
                                    double weeklyHoursUsed, String contractDocId, boolean noNight,
                                    Double maxDailyHours, boolean off, String offReason, List<WindowView> windows,
                                    List<BusyView> busy) {
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
