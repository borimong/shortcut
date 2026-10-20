package com.shortcut.repository;

import com.shortcut.domain.OutboxMessage;
import java.util.List;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class OutboxRepository {

    private final JdbcClient jdbc;

    public OutboxRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(String routingKey, String payloadJson) {
        jdbc.sql("INSERT INTO outbox (routing_key, payload, status) VALUES (:routingKey, CAST(:payload AS jsonb), 'NEW')")
                .param("routingKey", routingKey)
                .param("payload", payloadJson)
                .update();
    }

    /**
     * api를 여러 개 띄워도 같은 행을 두 번 발행하지 않도록 잠긴 행은 건너뛴다.
     */
    public List<OutboxMessage> lockNewBatch(int limit) {
        return jdbc.sql("""
                        SELECT id, routing_key, payload::text AS payload_json FROM outbox
                        WHERE status = 'NEW' ORDER BY id LIMIT :limit FOR UPDATE SKIP LOCKED
                        """)
                .param("limit", limit)
                .query((rs, n) -> new OutboxMessage(rs.getLong("id"), rs.getString("routing_key"),
                        rs.getString("payload_json")))
                .list();
    }

    public void markSent(long id) {
        jdbc.sql("UPDATE outbox SET status = 'SENT', sent_at = now() WHERE id = :id").param("id", id).update();
    }

    public void markFailed(long id, String error) {
        jdbc.sql("UPDATE outbox SET attempts = attempts + 1, last_error = :error WHERE id = :id")
                .param("id", id)
                .param("error", error)
                .update();
    }
}
