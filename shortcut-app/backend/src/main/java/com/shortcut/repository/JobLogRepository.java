package com.shortcut.repository;

import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class JobLogRepository {

    private final JdbcClient jdbc;

    public JobLogRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(String queue, String messageId, int attempt, String status, String error) {
        jdbc.sql("""
                        INSERT INTO job_logs (queue, message_id, attempt, status, error)
                        VALUES (:queue, :messageId, :attempt, :status, :error)
                        """)
                .param("queue", queue)
                .param("messageId", messageId)
                .param("attempt", attempt)
                .param("status", status)
                .param("error", error)
                .update();
    }
}
