package com.shortcut.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.JsonNode;
import com.shortcut.dto.BoardDtos.EquipmentView;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.util.List;

public final class ProposalDtos {

    private ProposalDtos() {
    }

    public record CreateProposalRequest(@NotNull Long taskId, Long eventId, @NotNull Long shootDayId,
                                        @NotNull @Min(1) Integer loopNo, @NotNull @Valid ProposalCandidate candidate,
                                        Double score, JsonNode scoreBreakdown, JsonNode weights, String explanation,
                                        JsonNode checklist, JsonNode evidence, JsonNode unresolved,
                                        @NotNull Integer dataVersion, JsonNode review) {
    }

    public record ProposalCandidate(@NotNull Long locationId, @NotNull List<Long> equipmentIds,
                                    @NotNull LocalTime start, @NotNull LocalTime end, JsonNode source) {
    }

    public record ProposalCreated(long proposalId, String versionNo, List<String> requiredApprovers, String status) {
    }

    public record ProposalView(long id, long taskId, Long eventId, String versionNo, int loopNo, String status,
                               OffsetDateTime createdAt, int dataVersion, PlanSide original, PlanSide proposed,
                               long extraCost, double distanceDeltaKm, double score, JsonNode scoreBreakdown,
                               JsonNode weights, String explanation, JsonNode checklist, JsonNode evidence,
                               JsonNode unresolved, JsonNode review, List<ApprovalView> approvals, int approvedCount,
                               int requiredCount) {
    }

    public record PlanSide(ProposalLocation location, List<EquipmentView> equipment, LocalTime start, LocalTime end,
                           long cost, @JsonInclude(JsonInclude.Include.NON_NULL) JsonNode source) {
    }

    public record ProposalLocation(long id, String name, boolean indoor) {
    }

    public record ApprovalView(String role, String title, String scope, String status, String userName,
                               String reason, List<String> issues, OffsetDateTime decidedAt) {
    }

    public record ProposalSummary(long id, long taskId, String versionNo, int loopNo, String status,
                                  OffsetDateTime createdAt, ProposalLocation location, LocalTime start,
                                  LocalTime end, double score, int approvedCount, int requiredCount) {
    }

    /**
     * @param issues 거절할 때 문제로 고른 요소(LOCATION, TIME, EQUIPMENT, COST, OTHER). Agent가 이 요소만 바꿔 다시 계획한다.
     */
    public record ApprovalRequest(@NotNull Long proposalId, @NotNull @Pattern(regexp = "APPROVE|REJECT") String decision,
                                  @Size(max = 500) String reason,
                                  List<@Pattern(regexp = "LOCATION|TIME|EQUIPMENT|COST|OTHER") String> issues) {
    }

    public record ApprovalResult(long proposalId, String status, List<ApprovalView> approvals) {
    }

    public record CommitRequest(@NotNull Integer dataVersion) {
    }

    public record CommitResult(int callsheetVersionNo, String reservationStatus, boolean distributed) {
    }
}
