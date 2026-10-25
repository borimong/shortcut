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
                task.traceId(), null));
    }

    @Transactional(propagation = Propagation.MANDATORY)
    public void agentResume(AiTask task, long proposalId, Resume resume) {
        enqueue(RabbitTopology.AGENT_TASKS, new AgentTaskMessage(task.id(), task.kind(), "RESUME", task.threadId(),
                task.shootDayId(), task.eventId(), proposalId, null, resume, task.requestedBy(), task.traceId(), null));
    }

    /**
     * 사용자가 고른 생각 하나를 고쳐 달라는 요청을 Agent에 넘긴다. 승인 재개와 같은 큐를 쓰고 action만 REVISE다.
     */
    @Transactional(propagation = Propagation.MANDATORY)
    public void agentRevise(AiTask task, Revise revise) {
        enqueue(RabbitTopology.AGENT_TASKS, new AgentTaskMessage(task.id(), task.kind(), "REVISE", task.threadId(),
                task.shootDayId(), task.eventId(), null, null, null, task.requestedBy(), task.traceId(), revise));
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
                                   String requestedBy, String traceId, Revise revise) {
    }

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record Resume(String decision, String role, String reason, List<String> issues) {
    }

    /**
     * @param eventId 고르게 한 THOUGHT 이벤트 id
     * @param step 그 생각을 낸 노드가 실행될 때의 단계 번호. 계획 단계는 이 값으로 되돌아갈 체크포인트를 찾는다
     * @param node 그 생각을 낸 노드 이름
     * @param agent 그 생각을 낸 Agent 이름(planner, supervisor, venue 등)
     * @param phase plan 또는 exec
     * @param comment 사용자가 적은 수정 요청
     */
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record Revise(long eventId, Integer step, String node, String agent, String phase, String comment) {
    }

    public record CallsheetJob(long callsheetVersionId, long shootDayId, int versionNo, String traceId) {
    }
}
