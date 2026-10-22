package com.shortcut.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.shortcut.common.AfterCommit;
import com.shortcut.common.ApiException;
import com.shortcut.domain.AiTask;
import com.shortcut.domain.Approval;
import com.shortcut.domain.Callsheet;
import com.shortcut.domain.Location;
import com.shortcut.domain.Proposal;
import com.shortcut.domain.UserAccount;
import com.shortcut.dto.NotificationDtos.ApprovalUpdated;
import com.shortcut.dto.ProposalDtos.ApprovalRequest;
import com.shortcut.dto.ProposalDtos.ApprovalResult;
import com.shortcut.dto.ProposalDtos.ApprovalView;
import com.shortcut.dto.ProposalDtos.CommitResult;
import com.shortcut.dto.ProposalDtos.CreateProposalRequest;
import com.shortcut.dto.ProposalDtos.PlanSide;
import com.shortcut.dto.ProposalDtos.ProposalCandidate;
import com.shortcut.dto.ProposalDtos.ProposalCreated;
import com.shortcut.dto.ProposalDtos.ProposalLocation;
import com.shortcut.dto.ProposalDtos.ProposalScene;
import com.shortcut.dto.ProposalDtos.ProposalSummary;
import com.shortcut.dto.ProposalDtos.ProposalView;
import com.shortcut.engine.ApproverRule;
import com.shortcut.engine.CheckResult;
import com.shortcut.engine.PlanEngine;
import com.shortcut.engine.PlanSnapshot;
import com.shortcut.engine.SceneSlot;
import com.shortcut.repository.CallsheetRepository;
import com.shortcut.repository.PlanRepository;
import com.shortcut.repository.ProposalRepository;
import com.shortcut.repository.SettingsRepository;
import com.shortcut.repository.ProposalRepository.NewProposal;
import com.shortcut.repository.TaskRepository;
import com.shortcut.repository.UserRepository;
import com.shortcut.security.CurrentUser;
import java.time.format.DateTimeFormatter;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 변경안 생성, 승인 흐름, 확정 반영을 맡는다.
 * 상태 전이와 outbox 기록은 모두 같은 트랜잭션에서 일어나 Agent가 받는 RESUME과 DB 상태가 어긋나지 않는다.
 */
@Service
public class ProposalService {

    private static final String PENDING = "PENDING";
    private static final String APPROVED = "APPROVED";
    private static final String REJECTED = "REJECTED";
    private static final String STALE = "STALE";
    private static final DateTimeFormatter HH_MM = DateTimeFormatter.ofPattern("HH:mm");
    private static final int MIN_REASON_LENGTH = 5;


    private final ProposalRepository proposals;
    private final TaskRepository tasks;
    private final PlanRepository plans;
    private final CallsheetRepository callsheets;
    private final UserRepository users;
    private final PlanDataService planData;
    private final PlanService planService;
    private final NotificationService notifications;
    private final OutboxService outbox;
    private final SseHub hub;
    private final ObjectMapper mapper;
    private final SettingsRepository settings;

    public ProposalService(ProposalRepository proposals, TaskRepository tasks, PlanRepository plans,
                           CallsheetRepository callsheets, UserRepository users, PlanDataService planData,
                           PlanService planService, NotificationService notifications, OutboxService outbox,
                           SseHub hub, ObjectMapper mapper, SettingsRepository settings) {
        this.settings = settings;
        this.proposals = proposals;
        this.tasks = tasks;
        this.plans = plans;
        this.callsheets = callsheets;
        this.users = users;
        this.planData = planData;
        this.planService = planService;
        this.notifications = notifications;
        this.outbox = outbox;
        this.hub = hub;
        this.mapper = mapper;
    }

    /**
     * Agent가 고른 후보라도 서버가 엔진으로 다시 검증한다.
     * LLM이 위반을 놓치거나 데이터가 바뀐 뒤 올린 안이 승인 단계로 넘어가면 안 되기 때문이다.
     */
    @Transactional
    public ProposalCreated create(CreateProposalRequest request) {
        AiTask task = tasks.findTask(request.taskId())
                .orElseThrow(() -> ApiException.notFound("TASK_NOT_FOUND", "작업이 없습니다: " + request.taskId()));
        if ("CANCELLED".equals(task.status())) {
            throw ApiException.conflict("TASK_CANCELLED", "중단한 재계획이라 변경안을 올릴 수 없습니다.");
        }
        long shootDayId = request.shootDayId();
        int current = plans.lockDataVersion(shootDayId)
                .orElseThrow(() -> ApiException.notFound("SHOOT_DAY_NOT_FOUND", "촬영일이 없습니다: " + shootDayId));
        if (request.dataVersion() != current) {
            throw ApiException.conflict("VERSION_CONFLICT", "촬영 데이터가 바뀌었습니다. 현재 버전 " + current);
        }
        PlanData data = planData.load(shootDayId);
        ProposalCandidate candidate = request.candidate();
        CheckResult check = planService.check(data, candidate.locationId(), candidate.equipmentIds(),
                candidate.start(), candidate.end(), List.of(), candidate.sceneOrder());
        if (!check.feasible()) {
            throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "PLAN_INVALID", "하드 제약을 위반한 후보입니다.",
                    Map.of("violations", check.violations()));
        }

        PlanSnapshot original = data.current();
        // 씬 순서는 엔진이 판정에 쓴 순서다. Agent가 순서를 비워 보내도 평가 때와 같은 순서가 남는다.
        PlanSnapshot proposed = data.snapshot(candidate.locationId(), candidate.equipmentIds(),
                candidate.start(), candidate.end(), check.sceneOrder());
        // 필수 승인자는 관리자 페이지에서 바꾼 규칙을 따른다.
        List<String> roles = ApproverRule.requiredApprovers(original, proposed, settings.approverRules());
        // 위에서 촬영일 행을 잠갔으므로 동시에 만든 변경안끼리 번호가 겹치지 않는다.
        int versionNo = proposals.nextVersionNo(shootDayId);
        Long eventId = request.eventId() != null ? request.eventId() : task.eventId();
        double score = request.score() == null ? 0.0 : request.score();
        long id = proposals.insert(new NewProposal(task.id(), eventId, shootDayId, request.loopNo(), versionNo, current,
                original, proposed, orEmptyObject(candidate.source()), score, orEmptyObject(request.scoreBreakdown()),
                request.weights() == null ? mapper.valueToTree(PlanEngine.DEFAULT_WEIGHTS) : request.weights(),
                request.explanation(), orEmptyArray(request.checklist()), orEmptyArray(request.evidence()),
                orEmptyArray(request.unresolved()), request.review()));
        for (int i = 0; i < roles.size(); i++) {
            proposals.insertApproval(id, i + 1, roles.get(i));
        }

        String label = "v" + versionNo;
        String link = "/proposals/" + id;
        String summary = summary(data, original, proposed);
        long extraCost = proposed.cost() - original.cost();
        for (String role : roles) {
            notifications.notifyRoles(List.of(role), NotificationService.APPROVAL_REQUEST,
                    "변경안 " + label + " 승인 요청", ApproverRule.scope(role, extraCost) + " 검토가 필요합니다. " + summary, link);
        }
        notifications.notifyAll(NotificationService.CHANGE_NOTICE, "변경안 " + label + " 승인 진행 중", summary, link);
        return new ProposalCreated(id, label, roles, PENDING);
    }

    @Transactional(readOnly = true)
    public ProposalView view(long id) {
        Proposal p = find(id);
        PlanData data = planData.load(p.shootDayId());
        List<Approval> approvals = proposals.findApprovals(id);
        long extraCost = p.proposed().cost() - p.original().cost();
        double distanceDelta = data.locations().get(p.proposed().locationId()).distanceKm()
                - data.locations().get(p.original().locationId()).distanceKm();
        return new ProposalView(p.id(), p.taskId(), p.shootDayId(), p.eventId(), p.versionLabel(), p.loopNo(), p.status(), p.createdAt(),
                p.dataVersion(), side(data, p.original(), null), side(data, p.proposed(), p.source()), extraCost,
                distanceDelta, p.score(), p.scoreBreakdown(), p.weights(), p.explanation(), p.checklist(),
                p.evidence(), p.unresolved(), p.review(), approvalViews(approvals, extraCost), approvedCount(approvals),
                approvals.size(), !p.original().sameSceneOrder(p.proposed()));
    }

    @Transactional(readOnly = true)
    public List<ProposalSummary> list(long shootDayId) {
        PlanData data = planData.load(shootDayId);
        return proposals.findByShootDay(shootDayId).stream().map(p -> {
            List<Approval> approvals = proposals.findApprovals(p.id());
            Location location = data.locations().get(p.proposed().locationId());
            return new ProposalSummary(p.id(), p.taskId(), p.versionLabel(), p.loopNo(), p.status(), p.createdAt(),
                    new ProposalLocation(location.id(), location.name(), location.indoor()),
                    p.proposed().start(), p.proposed().end(), p.score(), approvedCount(approvals), approvals.size());
        }).toList();
    }

    /**
     * 판정 순서는 존재, 상태, 역할, 사유, 데이터 최신성 순이다.
     * 권한 없는 사용자의 요청이 STALE 전이 같은 부수 효과를 일으키지 않게 하려는 순서다.
     */
    @Transactional
    public ApprovalResult decide(CurrentUser user, long taskId, ApprovalRequest request) {
        Proposal p = proposals.findForUpdate(request.proposalId())
                .filter(found -> found.taskId() == taskId)
                .orElseThrow(() -> ApiException.notFound("PROPOSAL_NOT_FOUND", "이 작업의 변경안이 아닙니다: " + request.proposalId()));
        if (!PENDING.equals(p.status())) {
            throw ApiException.conflict("PROPOSAL_NOT_PENDING", "이미 처리된 변경안입니다: " + p.status());
        }
        List<Approval> before = proposals.findApprovals(p.id());
        boolean myTurn = before.stream().anyMatch(a -> a.role().equals(user.role()) && PENDING.equals(a.status()));
        if (!myTurn) {
            throw ApiException.forbidden("이 변경안에서 승인 대기 중인 역할이 아닙니다.");
        }
        boolean reject = "REJECT".equals(request.decision());
        String reason = request.reason() == null ? null : request.reason().strip();
        if (reject && (reason == null || reason.isEmpty())) {
            throw ApiException.badRequest("REASON_REQUIRED", "거절 사유를 입력해야 합니다.");
        }
        // "ㅇ" 같은 사유로는 Agent가 무엇을 고칠지 알 수 없어 지나치게 넓게 제외하므로 최소 길이와 문제 요소를 받는다.
        if (reject && reason.length() < MIN_REASON_LENGTH) {
            throw ApiException.badRequest("REASON_TOO_SHORT", "거절 사유를 " + MIN_REASON_LENGTH + "자 이상 구체적으로 입력해야 합니다.");
        }
        List<String> issues = request.issues() == null ? List.of() : List.copyOf(new LinkedHashSet<>(request.issues()));
        if (reject && issues.isEmpty()) {
            throw ApiException.badRequest("ISSUES_REQUIRED", "무엇이 문제인지(장소, 시간대, 장비, 비용, 기타) 하나 이상 골라야 합니다.");
        }

        AiTask task = tasks.findTask(p.taskId()).orElseThrow();
        int currentVersion = plans.findShootDay(p.shootDayId()).orElseThrow().dataVersion();
        String label = p.versionLabel();
        String title;
        String body;
        String status;
        if (currentVersion != p.dataVersion()) {
            proposals.updateStatus(p.id(), STALE);
            proposals.cancelPending(p.id());
            outbox.agentResume(task, p.id(), new OutboxService.Resume(STALE, null, null, List.of()));
            status = STALE;
            title = "변경안 " + label + " 무효";
            body = "승인 대기 중 촬영 데이터가 바뀌어 다시 계획합니다.";
        } else if (reject) {
            proposals.decide(p.id(), user.role(), REJECTED, user.username(), user.name(), reason, issues);
            proposals.updateStatus(p.id(), REJECTED);
            proposals.cancelPending(p.id());
            outbox.agentResume(task, p.id(), new OutboxService.Resume(REJECTED, user.role(), reason, issues));
            status = REJECTED;
            title = "변경안 " + label + " 거절";
            body = user.name() + ": " + reason;
        } else {
            proposals.decide(p.id(), user.role(), APPROVED, user.username(), user.name(), null, List.of());
            boolean all = proposals.findApprovals(p.id()).stream().allMatch(a -> APPROVED.equals(a.status()));
            if (all) {
                proposals.updateStatus(p.id(), APPROVED);
                outbox.agentResume(task, p.id(), new OutboxService.Resume(APPROVED, null, null, List.of()));
            }
            status = all ? APPROVED : PENDING;
            title = all ? "변경안 " + label + " 전원 승인" : "변경안 " + label + " 승인 진행";
            body = user.name() + " 승인";
        }

        List<Approval> after = proposals.findApprovals(p.id());
        Set<String> related = new LinkedHashSet<>();
        related.add(task.requestedBy());
        users.findByRoles(after.stream().map(Approval::role).toList()).forEach(u -> related.add(u.username()));
        notifications.notifyUsernames(related, NotificationService.DECISION, title, body, "/proposals/" + p.id());

        ApprovalUpdated update = new ApprovalUpdated(p.id(), approvedCount(after), after.size(), status);
        AfterCommit.run(() -> hub.broadcast("APPROVAL_UPDATED", update));
        long extraCost = p.proposed().cost() - p.original().cost();
        return new ApprovalResult(p.id(), status, approvalViews(after, extraCost));
    }

    /**
     * 촬영판 갱신, 버전 증가, 콜시트 버전, 예약, 배포 작업, 알림을 한 트랜잭션으로 확정한다.
     * 촬영일 행을 잠가 두 변경안이 동시에 확정되며 버전이 꼬이는 일을 막는다.
     */
    @Transactional
    public CommitResult commit(long id, int dataVersion) {
        Proposal p = proposals.findForUpdate(id)
                .orElseThrow(() -> ApiException.notFound("PROPOSAL_NOT_FOUND", "변경안이 없습니다: " + id));
        if (!APPROVED.equals(p.status())) {
            throw ApiException.conflict("NOT_APPROVED", "승인 완료된 변경안이 아닙니다: " + p.status());
        }
        long shootDayId = p.shootDayId();
        int current = plans.lockDataVersion(shootDayId).orElseThrow();
        if (dataVersion != current || p.dataVersion() != current) {
            throw ApiException.conflict("VERSION_CONFLICT", "촬영 데이터가 바뀌었습니다. 현재 버전 " + current);
        }
        PlanData data = planData.load(shootDayId);
        PlanSnapshot proposed = p.proposed();
        plans.updateBlock(shootDayId, PlanData.CHANGING_BLOCK, proposed);
        // 씬 순서는 촬영판(scenes.sort)과 새 콜시트 스냅숏에 함께 남는다. 옛 콜시트 버전은 자기 스냅숏의 순서를 그대로 보인다.
        if (!proposed.scenes().isEmpty()) {
            plans.updateSceneOrder(shootDayId, PlanData.CHANGING_BLOCK, SceneSlot.codes(proposed.scenes()));
        }
        plans.bumpDataVersion(shootDayId);
        // "변경안 v4 확정"이 "콜시트 v4"가 되도록 변경안 번호를 그대로 쓴다. 거절된 안의 번호는 콜시트에서 건너뛴다.
        int versionNo = p.versionNo();
        Callsheet callsheet = callsheets.insert(shootDayId, versionNo, p.id(), proposed);
        proposals.updateStatus(id, "COMMITTED");

        String reservationStatus;
        if (callsheets.hasHeldReservation(shootDayId, proposed.locationId())) {
            reservationStatus = "HELD";
        } else {
            // 외부 예약 연동이 없는 장소는 제작부 담당자가 직접 잡아야 하므로 처리 대기로 남긴다.
            callsheets.insertManualReservation("M-" + p.id(), shootDayId, proposed.locationId(),
                    proposed.start(), proposed.end());
            reservationStatus = "MANUAL_PENDING";
        }

        AiTask task = tasks.findTask(p.taskId()).orElseThrow();
        outbox.callsheetJob(callsheet.id(), shootDayId, versionNo, task.traceId());
        notifications.notifyAll(NotificationService.CHANGE_NOTICE, "확정 콜시트 v" + versionNo + " 배포",
                summary(data, p.original(), proposed), "/");
        return new CommitResult(versionNo, reservationStatus, false);
    }

    private Proposal find(long id) {
        return proposals.find(id).orElseThrow(() -> ApiException.notFound("PROPOSAL_NOT_FOUND", "변경안이 없습니다: " + id));
    }

    private List<ApprovalView> approvalViews(List<Approval> approvals, long extraCost) {
        Map<String, UserAccount> holders = new LinkedHashMap<>();
        users.findByRoles(approvals.stream().map(Approval::role).toList())
                .forEach(u -> holders.putIfAbsent(u.role(), u));
        return approvals.stream().map(a -> {
            UserAccount holder = holders.get(a.role());
            String title = holder == null ? a.role() : holder.title();
            String userName = a.userName() != null ? a.userName() : holder == null ? null : holder.name();
            return new ApprovalView(a.role(), title, ApproverRule.scope(a.role(), extraCost), a.status(), userName,
                    a.reason(), a.issues(), a.decidedAt());
        }).toList();
    }

    private static int approvedCount(List<Approval> approvals) {
        return (int) approvals.stream().filter(a -> APPROVED.equals(a.status())).count();
    }

    private static PlanSide side(PlanData data, PlanSnapshot plan, JsonNode source) {
        Location location = data.locations().get(plan.locationId());
        Map<String, String> titles = new LinkedHashMap<>();
        data.scenes().forEach(scene -> titles.put(scene.code(), scene.title()));
        List<ProposalScene> scenes = plan.scenes().stream()
                .map(s -> new ProposalScene(s.code(), titles.get(s.code()), s.start(), s.end())).toList();
        return new PlanSide(new ProposalLocation(location.id(), location.name(), location.indoor()),
                ShootDayQueryService.equipment(data, plan.equipmentIds()), plan.start(), plan.end(), plan.cost(),
                source, scenes);
    }

    /** 알림 한 줄 요약이다. 씬 순서가 바뀌면 새 순서를 붙인다. */
    private static String summary(PlanData data, PlanSnapshot original, PlanSnapshot plan) {
        String summary = "오후 블록: " + data.locations().get(plan.locationId()).name() + " "
                + plan.start().format(HH_MM) + "~" + plan.end().format(HH_MM);
        if (!original.sameSceneOrder(plan)) {
            summary += ", 씬 순서 " + String.join(" → ", SceneSlot.codes(plan.scenes()));
        }
        return summary;
    }

    private static JsonNode orEmptyObject(JsonNode node) {
        return node == null || node.isNull() ? JsonNodeFactory.instance.objectNode() : node;
    }

    private static JsonNode orEmptyArray(JsonNode node) {
        return node == null || node.isNull() ? JsonNodeFactory.instance.arrayNode() : node;
    }
}
