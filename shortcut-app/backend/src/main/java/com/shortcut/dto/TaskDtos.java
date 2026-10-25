package com.shortcut.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonUnwrapped;
import com.fasterxml.jackson.databind.JsonNode;
import com.shortcut.domain.AiTask;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.util.List;

public final class TaskDtos {

    private TaskDtos() {
    }

    public record EventRequest(
            @NotNull @Pattern(regexp = "RAIN|ACTOR_SCHEDULE|LOCATION_CANCEL|EQUIPMENT_FAILURE|DISASTER|OTHER") String type,
            @NotBlank @Size(max = 500) String detail,
            @Size(max = 500) String instruction,
            Long shootDayId,
            @Valid @Size(max = 10) List<ChangeItem> changes) {
    }

    /**
     * 변경 입력에서 고른 구조화된 변경 한 건이다. 문장(detail)과 달리 엔진이 바로 읽는 업무 데이터로 반영된다.
     *
     * @param kind EQUIPMENT_UNAVAILABLE, ACTOR_ABSENT, ACTOR_WINDOW, LOCATION_UNAVAILABLE, RAIN_FORECAST, DISASTER_ALERT
     * @param targetId 장비, 배우, 장소 id
     * @param from 배우 가용 시작 또는 재난 문자 시작 시각(HH:mm)
     * @param to 배우 가용 끝 또는 재난 문자 끝 시각(HH:mm)
     * @param fromHour 비가 시작되는 시각(0~23)
     * @param toHour 비가 그치는 시각(0~23, 포함)
     * @param mm 시간당 강수량(mm)
     * @param region 재난 문자 지역(예: 서울 영등포구)
     * @param alertKind 재난 문자 종류(예: 호우 경보)
     */
    public record ChangeItem(
            @NotNull @Pattern(regexp = "EQUIPMENT_UNAVAILABLE|ACTOR_ABSENT|ACTOR_WINDOW|LOCATION_UNAVAILABLE|RAIN_FORECAST|DISASTER_ALERT") String kind,
            Long targetId,
            LocalTime from,
            LocalTime to,
            Integer fromHour,
            Integer toHour,
            Double mm,
            @Size(max = 40) String region,
            @Size(max = 40) String alertKind) {
    }

    public record EventOptions(long pmLocationId, List<OptionLocation> locations, List<OptionEquipment> equipment,
                               List<OptionActor> actors, List<String> regions) {
    }

    public record OptionLocation(long id, String name, String region, boolean indoor, boolean available) {
    }

    public record OptionEquipment(long id, String name, boolean available) {
    }

    public record OptionActor(long id, String name, LocalTime availableFrom, LocalTime availableTo) {
    }

    public record EventResponse(long eventId, long taskId, @JsonInclude(JsonInclude.Include.NON_NULL) Boolean duplicate) {
    }

    public record AskRequest(@NotBlank @Size(max = 1000) String question, Long proposalId) {
    }

    public record TaskCreated(long taskId) {
    }

    public record TaskView(long id, String kind, String status, String question, String answer, JsonNode sources,
                           Long eventId, Long proposalId, String traceUrl, OffsetDateTime createdAt,
                           OffsetDateTime updatedAt) {

        public static TaskView of(AiTask task) {
            return new TaskView(task.id(), task.kind(), task.status(), task.question(), task.answer(), task.sources(),
                    task.eventId(), task.proposalId(), task.traceUrl(), task.createdAt(), task.updatedAt());
        }
    }

    public record InternalTaskView(@JsonUnwrapped TaskView task, String requestedBy, String instruction,
                                   String eventType, String eventDetail, long shootDayId,
                                   List<String> eventChanges, int maxLoops) {
    }

    public record TaskEventRequest(@NotBlank String type, JsonNode payload) {
    }

    /**
     * 생각 기록(THOUGHT 이벤트) 하나를 골라 고쳐 달라는 요청이다.
     *
     * @param eventId 이 작업의 THOUGHT 이벤트 id
     * @param comment 고쳐 달라는 내용 한 줄
     */
    public record RevisionRequest(@NotNull Long eventId, @NotBlank @Size(max = 300) String comment) {
    }

    /**
     * @param phase plan이면 체크포인트에서 다시 계획하고, exec이면 실행팀이 해당 Agent만 다시 보낸다
     */
    public record RevisionAccepted(long taskId, String phase) {
    }
}
