package com.shortcut.repository;

import com.shortcut.common.JsonColumns;
import com.shortcut.domain.AiTask;
import com.shortcut.domain.ChangeEvent;
import com.shortcut.domain.TaskEvent;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class TaskRepository {

    private final JdbcClient jdbc;
    private final JsonColumns json;

    public TaskRepository(JdbcClient jdbc, JsonColumns json) {
        this.jdbc = jdbc;
        this.json = json;
    }

    /**
     * 같은 변동을 두 번 눌러도 이벤트가 하나만 생기도록 dedup_key 유니크 제약에 맡긴다.
     * 비어 있으면 이미 있는 이벤트라는 뜻이다.
     */
    public Optional<Long> insertEventIfAbsent(long shootDayId, String type, String detail, String instruction,
                                              int dataVersion, String dedupKey, String requestedBy) {
        return jdbc.sql("""
                        INSERT INTO change_events (shoot_day_id, type, detail, instruction, data_version, dedup_key, requested_by)
                        VALUES (:shootDayId, :type, :detail, :instruction, :dataVersion, :dedupKey, :requestedBy)
                        ON CONFLICT (dedup_key) DO NOTHING
                        RETURNING id
                        """)
                .param("shootDayId", shootDayId)
                .param("type", type)
                .param("detail", detail)
                .param("instruction", instruction)
                .param("dataVersion", dataVersion)
                .param("dedupKey", dedupKey)
                .param("requestedBy", requestedBy)
                .query(Long.class)
                .optional();
    }

    public void updateEventChanges(long eventId, String changesJson) {
        jdbc.sql("UPDATE change_events SET changes = CAST(:changes AS jsonb) WHERE id = :id")
                .param("changes", changesJson)
                .param("id", eventId)
                .update();
    }

    /** 변경 입력에서 반영한 구조화된 변경의 한 줄 요약 목록이다. Agent에게 그대로 넘긴다. */
    public List<String> findEventChangeSummaries(long eventId) {
        return jdbc.sql("SELECT c ->> 'summary' FROM change_events, jsonb_array_elements(changes) c WHERE id = :id")
                .param("id", eventId)
                .query(String.class)
                .list();
    }

    public Optional<ChangeEvent> findEventByDedupKey(String dedupKey) {
        return jdbc.sql("SELECT * FROM change_events WHERE dedup_key = :key")
                .param("key", dedupKey)
                .query(TaskRepository::mapEvent)
                .optional();
    }

    public Optional<ChangeEvent> findEvent(long id) {
        return jdbc.sql("SELECT * FROM change_events WHERE id = :id")
                .param("id", id)
                .query(TaskRepository::mapEvent)
                .optional();
    }

    public List<ChangeEvent> findEvents(long shootDayId) {
        return jdbc.sql("SELECT * FROM change_events WHERE shoot_day_id = :id ORDER BY id")
                .param("id", shootDayId)
                .query(TaskRepository::mapEvent)
                .list();
    }

    public long insertTask(String kind, String question, Long eventId, Long proposalId, long shootDayId,
                           String requestedBy, String traceId, String threadPrefix) {
        long id = jdbc.sql("""
                        INSERT INTO ai_tasks (kind, status, question, event_id, proposal_id, shoot_day_id, requested_by, trace_id)
                        VALUES (:kind, 'QUEUED', :question, :eventId, :proposalId, :shootDayId, :requestedBy, :traceId)
                        RETURNING id
                        """)
                .param("kind", kind)
                .param("question", question)
                .param("eventId", eventId)
                .param("proposalId", proposalId)
                .param("shootDayId", shootDayId)
                .param("requestedBy", requestedBy)
                .param("traceId", traceId)
                .query(Long.class)
                .single();
        long threadKey = eventId != null ? eventId : id;
        jdbc.sql("UPDATE ai_tasks SET thread_id = :threadId WHERE id = :id")
                .param("threadId", threadPrefix + threadKey)
                .param("id", id)
                .update();
        return id;
    }

    public Optional<AiTask> findTask(long id) {
        return jdbc.sql("SELECT *, sources::text AS sources_json FROM ai_tasks WHERE id = :id")
                .param("id", id)
                .query(this::mapTask)
                .optional();
    }

    public Optional<AiTask> findTaskByEvent(long eventId) {
        return jdbc.sql("SELECT *, sources::text AS sources_json FROM ai_tasks WHERE event_id = :id ORDER BY id LIMIT 1")
                .param("id", eventId)
                .query(this::mapTask)
                .optional();
    }

    public List<AiTask> findTasks(String requestedBy, int limit) {
        String where = requestedBy == null ? "" : " WHERE requested_by = :requestedBy";
        JdbcClient.StatementSpec spec = jdbc.sql(
                        "SELECT *, sources::text AS sources_json FROM ai_tasks" + where + " ORDER BY id DESC LIMIT :limit")
                .param("limit", limit);
        if (requestedBy != null) {
            spec = spec.param("requestedBy", requestedBy);
        }
        return spec.query(this::mapTask).list();
    }

    public void markRunning(long id) {
        jdbc.sql("""
                        UPDATE ai_tasks SET status = 'RUNNING', updated_at = now()
                        WHERE id = :id AND status IN ('QUEUED', 'WAITING_APPROVAL')
                        """)
                .param("id", id)
                .update();
    }

    /**
     * 수정 요청을 받은 작업을 다시 실행 중으로 돌린다. 승인 대기, 완료, 사람 확인 상태에서만 바뀐다.
     */
    public int markRevising(long id) {
        return jdbc.sql("""
                        UPDATE ai_tasks SET status = 'RUNNING', updated_at = now()
                        WHERE id = :id AND status IN ('WAITING_APPROVAL', 'DONE', 'NEEDS_HUMAN')
                        """)
                .param("id", id)
                .update();
    }

    public Optional<TaskEvent> findTaskEvent(long taskId, long eventId) {
        return jdbc.sql("SELECT *, payload::text AS payload_json FROM ai_task_events WHERE task_id = :taskId AND id = :id")
                .param("taskId", taskId)
                .param("id", eventId)
                .query(TaskRepository::mapTaskEvent)
                .optional();
    }

    public void markWaitingApproval(long id, Long proposalId) {
        jdbc.sql("""
                        UPDATE ai_tasks SET status = 'WAITING_APPROVAL', proposal_id = COALESCE(:proposalId, proposal_id),
                               updated_at = now()
                        WHERE id = :id AND status <> 'CANCELLED'
                        """)
                .param("id", id)
                .param("proposalId", proposalId)
                .update();
    }

    public void markFinished(long id, String status, String answer, String sourcesJson, String traceUrl, Long proposalId) {
        jdbc.sql("""
                        UPDATE ai_tasks SET status = :status,
                               answer = COALESCE(:answer, answer),
                               sources = COALESCE(CAST(:sources AS jsonb), sources),
                               trace_url = COALESCE(:traceUrl, trace_url),
                               proposal_id = COALESCE(:proposalId, proposal_id),
                               updated_at = now()
                        WHERE id = :id AND status <> 'CANCELLED'
                        """)
                .param("id", id)
                .param("status", status)
                .param("answer", answer)
                .param("sources", sourcesJson)
                .param("traceUrl", traceUrl)
                .param("proposalId", proposalId)
                .update();
    }

    public TaskEvent insertTaskEvent(long taskId, String type, String payloadJson) {
        return jdbc.sql("""
                        INSERT INTO ai_task_events (task_id, type, payload)
                        VALUES (:taskId, :type, CAST(:payload AS jsonb))
                        RETURNING *, payload::text AS payload_json
                        """)
                .param("taskId", taskId)
                .param("type", type)
                .param("payload", payloadJson)
                .query(TaskRepository::mapTaskEvent)
                .single();
    }

    public List<TaskEvent> findTaskEventsAfter(long taskId, long afterId) {
        return jdbc.sql("""
                        SELECT *, payload::text AS payload_json FROM ai_task_events
                        WHERE task_id = :taskId AND id > :afterId ORDER BY id
                        """)
                .param("taskId", taskId)
                .param("afterId", afterId)
                .query(TaskRepository::mapTaskEvent)
                .list();
    }

    private AiTask mapTask(ResultSet rs, int row) throws SQLException {
        return new AiTask(rs.getLong("id"), rs.getString("kind"), rs.getString("status"), rs.getString("question"),
                rs.getString("answer"), json.tree(rs.getString("sources_json")), rs.getObject("event_id", Long.class),
                rs.getObject("proposal_id", Long.class), rs.getString("trace_url"), rs.getString("thread_id"),
                rs.getString("trace_id"), rs.getLong("shoot_day_id"), rs.getString("requested_by"),
                rs.getObject("created_at", OffsetDateTime.class), rs.getObject("updated_at", OffsetDateTime.class));
    }

    private static ChangeEvent mapEvent(ResultSet rs, int row) throws SQLException {
        return new ChangeEvent(rs.getLong("id"), rs.getLong("shoot_day_id"), rs.getString("type"), rs.getString("detail"),
                rs.getString("instruction"), rs.getInt("data_version"), rs.getString("requested_by"),
                rs.getObject("created_at", OffsetDateTime.class));
    }

    private static TaskEvent mapTaskEvent(ResultSet rs, int row) throws SQLException {
        return new TaskEvent(rs.getLong("id"), rs.getLong("task_id"), rs.getString("type"),
                rs.getString("payload_json"), rs.getObject("created_at", OffsetDateTime.class));
    }
}
