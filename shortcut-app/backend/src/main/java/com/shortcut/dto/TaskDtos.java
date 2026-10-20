package com.shortcut.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonUnwrapped;
import com.fasterxml.jackson.databind.JsonNode;
import com.shortcut.domain.AiTask;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.time.OffsetDateTime;

public final class TaskDtos {

    private TaskDtos() {
    }

    public record EventRequest(
            @NotNull @Pattern(regexp = "RAIN|ACTOR_SCHEDULE|LOCATION_CANCEL|EQUIPMENT_FAILURE|DISASTER") String type,
            @NotBlank @Size(max = 500) String detail,
            @Size(max = 500) String instruction,
            Long shootDayId) {
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
                                   String eventType, String eventDetail, long shootDayId) {
    }

    public record TaskEventRequest(@NotBlank String type, JsonNode payload) {
    }
}
