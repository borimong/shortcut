package com.shortcut.repository;

import com.shortcut.domain.Notification;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.List;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class NotificationRepository {

    private static final String SELECT = """
            SELECT n.*, u.username FROM notifications n JOIN users u ON u.id = n.user_id
            """;

    private final JdbcClient jdbc;

    public NotificationRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public void insertForUsers(List<Long> userIds, String kind, String title, String body, String link) {
        if (userIds.isEmpty()) {
            return;
        }
        jdbc.sql("""
                        INSERT INTO notifications (user_id, kind, title, body, link)
                        SELECT id, :kind, :title, :body, :link FROM users WHERE id IN (:ids)
                        """)
                .param("ids", userIds)
                .param("kind", kind)
                .param("title", title)
                .param("body", body)
                .param("link", link)
                .update();
    }

    public void insertForAll(String kind, String title, String body, String link) {
        jdbc.sql("""
                        INSERT INTO notifications (user_id, kind, title, body, link)
                        SELECT id, :kind, :title, :body, :link FROM users WHERE active
                        """)
                .param("kind", kind)
                .param("title", title)
                .param("body", body)
                .param("link", link)
                .update();
    }

    public List<Notification> findForUser(String username, int limit) {
        return jdbc.sql(SELECT + " WHERE u.username = :username ORDER BY n.id DESC LIMIT :limit")
                .param("username", username)
                .param("limit", limit)
                .query(NotificationRepository::map)
                .list();
    }

    public long countUnread(String username) {
        return jdbc.sql("""
                        SELECT count(*) FROM notifications n JOIN users u ON u.id = n.user_id
                        WHERE u.username = :username AND NOT n.read
                        """)
                .param("username", username)
                .query(Long.class)
                .single();
    }

    public int markRead(long id, String username) {
        return jdbc.sql("""
                        UPDATE notifications SET read = true
                        WHERE id = :id AND user_id = (SELECT id FROM users WHERE username = :username)
                        """)
                .param("id", id)
                .param("username", username)
                .update();
    }

    public void markAllRead(String username) {
        jdbc.sql("""
                        UPDATE notifications SET read = true
                        WHERE NOT read AND user_id = (SELECT id FROM users WHERE username = :username)
                        """)
                .param("username", username)
                .update();
    }

    public List<Notification> findAfter(long afterId, int limit) {
        return jdbc.sql(SELECT + " WHERE n.id > :afterId ORDER BY n.id LIMIT :limit")
                .param("afterId", afterId)
                .param("limit", limit)
                .query(NotificationRepository::map)
                .list();
    }

    public long maxId() {
        return jdbc.sql("SELECT COALESCE(max(id), 0) FROM notifications").query(Long.class).single();
    }

    private static Notification map(ResultSet rs, int row) throws SQLException {
        return new Notification(rs.getLong("id"), rs.getString("username"), rs.getString("kind"), rs.getString("title"),
                rs.getString("body"), rs.getString("link"), rs.getBoolean("read"),
                rs.getObject("created_at", OffsetDateTime.class));
    }
}
