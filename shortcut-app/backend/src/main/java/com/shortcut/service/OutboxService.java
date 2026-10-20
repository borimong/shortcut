package com.shortcut.service;

import java.util.List;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.shortcut.common.JsonColumns;
import com.shortcut.config.RabbitTopology;
import com.shortcut.domain.AiTask;
import com.shortcut.repository.OutboxRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * 큐로 나갈 메시지를 업무 데이터와 같은 트랜잭션에 outbox 행으로 남긴다.
 * 커밋 전에 바로 발행하면 롤백된 작업이 Agent에 전달될 수 있어 발행은 릴레이가 따로 한다.
 */
@Service
public class OutboxService {

    private final OutboxRepository outbox;
    private final JsonColumns json;

    public OutboxService(OutboxRepository outbox, JsonColumns json) {
        this.outbox = outbox;
        this.json = json;
    }

    @Transactional(propagation = Propagation.MANDATORY)
    public void agentStart(AiTask task) {
        enqueue(RabbitTopology.AGENT_TASKS, new AgentTaskMessage(task.id(), task.kind(), "START", task.threadId(),
                task.shootDayId(), task.eventId(), task.proposalId(), task.question(), null, task.requestedBy(),
                task.traceId()));
    }

    @Transactional(propagation = Propagation.MANDATORY)
    public void agentResume(AiTask task, long proposalId, Resume resume) {
        enqueue(RabbitTopology.AGENT_TASKS, new AgentTaskMessage(task.id(), task.kind(), "RESUME", task.threadId(),
                task.shootDayId(), task.eventId(), proposalId, null, resume, task.requestedBy(), task.traceId()));
    }

    @Transactional(propagation = Propagation.MANDATORY)
    public void callsheetJob(long callsheetVersionId, long shootDayId, int versionNo, String traceId) {
        enqueue(RabbitTopology.JOBS_CALLSHEET, new CallsheetJob(callsheetVersionId, shootDayId, versionNo, traceId));
    }

    private void enqueue(String routingKey, Object message) {
        outbox.insert(routingKey, json.write(message));
    }

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record AgentTaskMessage(long taskId, String kind, String action, String threadId, long shootDayId,
                                   Long eventId, Long proposalId, String question, Resume resume,
                                   String requestedBy, String traceId) {
    }

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record Resume(String decision, String role, String reason, List<String> issues) {
    }

    public record CallsheetJob(long callsheetVersionId, long shootDayId, int versionNo, String traceId) {
    }
}
