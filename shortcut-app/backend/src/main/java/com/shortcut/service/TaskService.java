package com.shortcut.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.shortcut.common.AfterCommit;
import com.shortcut.common.ApiException;
import com.shortcut.common.JsonColumns;
import com.shortcut.domain.AiTask;
import com.shortcut.domain.ChangeEvent;
import com.shortcut.domain.Proposal;
import com.shortcut.domain.TaskEvent;
import com.shortcut.dto.TaskDtos.AskRequest;
import com.shortcut.dto.TaskDtos.InternalTaskView;
import com.shortcut.dto.TaskDtos.TaskCreated;
import com.shortcut.dto.TaskDtos.TaskEventRequest;
import com.shortcut.dto.TaskDtos.TaskView;
import com.shortcut.repository.ProposalRepository;
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
            "NODE", "TOOL_START", "TOOL_END", "TOKEN", "APPROVAL_REQUIRED", "DONE", "FAILED", "NEEDS_HUMAN");
    // 내 작업 목록은 최근 작업만 보면 충분해 화면 한 쪽 분량으로 자른다.
    private static final int LIST_LIMIT = 50;

    private final TaskRepository tasks;
    private final ProposalRepository proposals;
    private final PlanDataService planData;
    private final OutboxService outbox;
    private final SseHub hub;
    private final JsonColumns json;

    public TaskService(TaskRepository tasks, ProposalRepository proposals, PlanDataService planData,
                       OutboxService outbox, SseHub hub, JsonColumns json) {
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
                task.shootDayId());
    }

    /**
     * 이벤트 저장과 작업 상태 전이를 한 트랜잭션으로 묶고, 화면 전달은 커밋 뒤에 한다.
     */
    @Transactional
    public void appendEvent(long id, TaskEventRequest request) {
        if (!EVENT_TYPES.contains(request.type())) {
            throw ApiException.badRequest("UNKNOWN_EVENT_TYPE", "알 수 없는 이벤트 유형입니다: " + request.type());
        }
        find(id);
        JsonNode payload = request.payload() == null ? JsonNodeFactory.instance.objectNode() : request.payload();
        TaskEvent saved = tasks.insertTaskEvent(id, request.type(), json.write(payload));
        switch (request.type()) {
            case "NODE" -> tasks.markRunning(id);
            case "APPROVAL_REQUIRED" -> tasks.markWaitingApproval(id, longOrNull(payload, "proposalId"));
            case "DONE" -> tasks.markFinished(id, "DONE", textOrNull(payload, "answer"),
                    payload.hasNonNull("sources") ? json.write(payload.get("sources")) : null,
                    textOrNull(payload, "traceUrl"), longOrNull(payload, "proposalId"));
            case "FAILED" -> tasks.markFinished(id, "FAILED", null, null, textOrNull(payload, "traceUrl"), null);
            case "NEEDS_HUMAN" -> {
                // NEEDS_HUMAN은 answer 대신 reason을 보내는 경우가 많아 사람이 읽을 문장으로 reason을 쓴다.
                String answer = payload.hasNonNull("answer") ? textOrNull(payload, "answer") : textOrNull(payload, "reason");
                tasks.markFinished(id, "NEEDS_HUMAN", answer, null, textOrNull(payload, "traceUrl"), null);
            }
            default -> {
            }
        }
        AfterCommit.run(() -> hub.publishTask(saved));
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
