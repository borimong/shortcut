package com.shortcut.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.shortcut.common.AfterCommit;
import com.shortcut.common.ApiException;
import com.shortcut.common.JsonColumns;
import com.shortcut.domain.AiTask;
import com.shortcut.domain.ChangeEvent;
import com.shortcut.domain.Proposal;
import com.shortcut.domain.ProposalStatus;
import com.shortcut.domain.TaskEvent;
import com.shortcut.domain.TaskStatus;
import com.shortcut.dto.TaskDtos.AskRequest;
import com.shortcut.dto.TaskDtos.InternalTaskView;
import com.shortcut.dto.TaskDtos.RevisionAccepted;
import com.shortcut.dto.TaskDtos.RevisionRequest;
import com.shortcut.dto.TaskDtos.TaskCreated;
import com.shortcut.dto.TaskDtos.TaskEventRequest;
import com.shortcut.dto.TaskDtos.TaskView;
import com.shortcut.repository.ProposalRepository;
import com.shortcut.repository.SettingsRepository;
import com.shortcut.repository.TaskRepository;
import com.shortcut.security.CurrentUser;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@Service
public class TaskService {

    private static final Set<String> EVENT_TYPES = Set.of(
            "NODE", "TOOL_START", "TOOL_END", "TOKEN", "APPROVAL_REQUIRED", "DONE", "FAILED", "NEEDS_HUMAN",
            "AGENT", "THOUGHT", "REVISION");
    public static final String PLAN_PHASE = "plan";
    public static final String EXEC_PHASE = "exec";
    // 내 작업 목록은 최근 작업만 보면 충분해 화면 한 쪽 분량으로 자른다.
    private static final int LIST_LIMIT = 50;

    private final TaskRepository tasks;
    private final ProposalRepository proposals;
    private final PlanDataService planData;
    private final OutboxService outbox;
    private final SseHub hub;
    private final JsonColumns json;
    private final SettingsRepository settings;

    public TaskService(TaskRepository tasks, ProposalRepository proposals, PlanDataService planData,
                       OutboxService outbox, SseHub hub, JsonColumns json, SettingsRepository settings) {
        this.settings = settings;
        this.tasks = tasks;
        this.proposals = proposals;
        this.planData = planData;
        this.outbox = outbox;
        this.hub = hub;
        this.json = json;
    }

    @Transactional
    public TaskCreated ask(CurrentUser user, AskRequest request) {
        long shootDayId;
        if (request.proposalId() != null) {
            Proposal proposal = proposals.find(request.proposalId())
                    .orElseThrow(() -> ApiException.notFound("PROPOSAL_NOT_FOUND", "변경안이 없습니다: " + request.proposalId()));
            shootDayId = proposal.shootDayId();
        } else {
            shootDayId = planData.boardShootDayId();
        }
        long id = tasks.insertTask("ASK", request.question().strip(), null, request.proposalId(), shootDayId,
                user.username(), UUID.randomUUID().toString(), "ask-");
        outbox.agentStart(find(id));
        return new TaskCreated(id);
    }

    @Transactional(readOnly = true)
    public TaskView get(long id) {
        return TaskView.of(find(id));
    }

    @Transactional(readOnly = true)
    public List<TaskView> list(CurrentUser user, boolean mine) {
        return tasks.findTasks(mine ? user.username() : null, LIST_LIMIT).stream().map(TaskView::of).toList();
    }

    @Transactional(readOnly = true)
    public InternalTaskView internalGet(long id) {
        AiTask task = find(id);
        ChangeEvent event = task.eventId() == null ? null : tasks.findEvent(task.eventId()).orElse(null);
        return new InternalTaskView(TaskView.of(task), task.requestedBy(),
                event == null ? null : event.instruction(),
                event == null ? null : event.type(),
                event == null ? null : event.detail(),
                task.shootDayId(),
                event == null ? List.of() : tasks.findEventChangeSummaries(event.id()),
                settings.settings().maxLoops());
    }

    /**
     * 이벤트 저장과 작업 상태 전이를 한 트랜잭션으로 묶고, 화면 전달은 커밋 뒤에 한다.
     */
    @Transactional
    public void appendEvent(long id, TaskEventRequest request) {
        if (!EVENT_TYPES.contains(request.type())) {
            throw ApiException.badRequest("UNKNOWN_EVENT_TYPE", "알 수 없는 이벤트 유형입니다: " + request.type());
        }
        // 중단한 작업에는 진행 이벤트를 더 받지 않는다. Agent는 이 응답을 보고 그래프를 멈춘다.
        if ("CANCELLED".equals(find(id).status())) {
            throw ApiException.conflict("TASK_CANCELLED", "중단한 작업입니다: " + id);
        }
        JsonNode payload = request.payload() == null ? JsonNodeFactory.instance.objectNode() : request.payload();
        TaskEvent saved = tasks.insertTaskEvent(id, request.type(), json.write(payload));
        switch (request.type()) {
            case "NODE" -> tasks.markRunning(id);
            case "APPROVAL_REQUIRED" -> tasks.markWaitingApproval(id, longOrNull(payload, "proposalId"));
            case "DONE" -> tasks.markFinished(id, TaskStatus.DONE, textOrNull(payload, "answer"),
                    payload.hasNonNull("sources") ? json.write(payload.get("sources")) : null,
                    textOrNull(payload, "traceUrl"), longOrNull(payload, "proposalId"));
            case "FAILED" -> tasks.markFinished(id, TaskStatus.FAILED, null, null, textOrNull(payload, "traceUrl"), null);
            case "NEEDS_HUMAN" -> {
                // NEEDS_HUMAN은 answer 대신 reason을 보내는 경우가 많아 사람이 읽을 문장으로 reason을 쓴다.
                String answer = payload.hasNonNull("answer") ? textOrNull(payload, "answer") : textOrNull(payload, "reason");
                tasks.markFinished(id, TaskStatus.NEEDS_HUMAN, answer, null, textOrNull(payload, "traceUrl"), null);
            }
            default -> {
            }
        }
        AfterCommit.run(() -> hub.publishTask(saved));
    }

    /**
     * 사용자가 생각 기록 하나를 골라 고쳐 달라고 한다. 그래프가 멈춰 있는 지점에서만 받는다.
     * 계획 단계 생각은 승인 대기 중에만 받고 대기 변경안을 닫는다. Agent가 그 생각 직전 체크포인트에서 다시 계획한다.
     * 실행 단계 생각은 작업이 끝난 뒤(완료, 사람 확인)에만 받는다. 실행팀이 그 Agent와 뒤 단계 Agent만 다시 보낸다.
     * 변경안 닫기, 수정 요청 기록, 상태 전이, Agent 메시지를 한 트랜잭션으로 묶어 하나만 반영되는 일이 없게 한다.
     */
    @Transactional
    public RevisionAccepted revise(CurrentUser user, long id, RevisionRequest request) {
        AiTask task = find(id);
        TaskEvent target = tasks.findTaskEvent(id, request.eventId())
                .orElseThrow(() -> ApiException.badRequest("REVISION_TARGET_INVALID", "이 작업의 생각 기록이 아닙니다: " + request.eventId()));
        if (!"THOUGHT".equals(target.type())) {
            throw ApiException.badRequest("REVISION_TARGET_INVALID", "생각 기록(THOUGHT)만 수정 요청할 수 있습니다.");
        }
        JsonNode thought = json.tree(target.payloadJson());
        if (thought == null || !thought.path("revisable").asBoolean(false)) {
            throw ApiException.badRequest("REVISION_TARGET_INVALID", "수정 요청을 받지 않는 생각입니다.");
        }
        String phase = thought.path("phase").asText(PLAN_PHASE);
        if (PLAN_PHASE.equals(phase)) {
            if (!TaskStatus.WAITING_APPROVAL.equals(task.status())) {
                throw ApiException.conflict("REVISION_NOT_ALLOWED", "계획 단계 생각은 승인 대기 중에만 고칠 수 있습니다. 현재 상태: " + task.status());
            }
            // 고친 계획으로 새 변경안을 다시 올리므로, 지금 기다리는 변경안은 승인 화면에서 내린다.
            if (task.proposalId() != null) {
                proposals.find(task.proposalId())
                        .filter(p -> ProposalStatus.PENDING.equals(p.status()))
                        .ifPresent(p -> {
                            proposals.updateStatus(p.id(), ProposalStatus.CANCELLED);
                            proposals.cancelPending(p.id());
                        });
            }
        } else if (EXEC_PHASE.equals(phase)) {
            if (!TaskStatus.DONE.equals(task.status()) && !TaskStatus.NEEDS_HUMAN.equals(task.status())) {
                throw ApiException.conflict("REVISION_NOT_ALLOWED", "실행 단계 생각은 작업이 끝난 뒤에만 고칠 수 있습니다. 현재 상태: " + task.status());
            }
        } else {
            throw ApiException.badRequest("REVISION_TARGET_INVALID", "알 수 없는 단계입니다: " + phase);
        }
        Integer step = thought.hasNonNull("step") && thought.get("step").canConvertToInt() ? thought.get("step").asInt() : null;
        String node = textOrNull(thought, "node");
        String agent = textOrNull(thought, "agent");
        String comment = request.comment().strip();
        ObjectNode revision = JsonNodeFactory.instance.objectNode();
        revision.put("eventId", target.id());
        if (step != null) {
            revision.put("step", step);
        }
        revision.put("node", node);
        revision.put("agent", agent);
        revision.put("phase", phase);
        revision.put("comment", comment);
        revision.put("requestedBy", user.username());
        TaskEvent saved = tasks.insertTaskEvent(id, "REVISION", json.write(revision));
        tasks.markRevising(id);
        outbox.agentRevise(task, new OutboxService.Revise(target.id(), step, node, agent, phase, comment));
        AfterCommit.run(() -> hub.publishTask(saved));
        return new RevisionAccepted(id, phase);
    }

    public SseEmitter stream(long id, Long lastEventId) {
        find(id);
        return hub.openTask(id, lastEventId == null ? 0 : lastEventId,
                after -> tasks.findTaskEventsAfter(id, after),
                () -> tasks.findTask(id).map(AiTask::finished).orElse(true));
    }

    private AiTask find(long id) {
        return tasks.findTask(id).orElseThrow(() -> ApiException.notFound("TASK_NOT_FOUND", "작업이 없습니다: " + id));
    }

    private static String textOrNull(JsonNode node, String field) {
        return node.hasNonNull(field) ? node.get(field).asText() : null;
    }

    private static Long longOrNull(JsonNode node, String field) {
        return node.hasNonNull(field) && node.get(field).canConvertToLong() ? node.get(field).asLong() : null;
    }
}
