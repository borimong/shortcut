package com.shortcut.repository;

import com.shortcut.common.JsonColumns;
import com.shortcut.domain.DataOverride;
import java.util.List;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/**
 * 변경 입력이 남긴 촬영일 데이터 덮어쓰기와 우천 알림 발송 기록을 다룬다.
 */
@Repository
public class OverrideRepository {

    private final JdbcClient jdbc;
    private final JsonColumns json;

    public OverrideRepository(JdbcClient jdbc, JsonColumns json) {
        this.jdbc = jdbc;
        this.json = json;
    }

    public void insert(long shootDayId, long eventId, String kind, Long targetId, Object payload) {
        jdbc.sql("""
                        INSERT INTO shoot_day_overrides (shoot_day_id, event_id, kind, target_id, payload)
                        VALUES (:shootDayId, :eventId, :kind, :targetId, CAST(:payload AS jsonb))
                        """)
                .param("shootDayId", shootDayId)
                .param("eventId", eventId)
                .param("kind", kind)
                .param("targetId", targetId)
                .param("payload", json.write(payload))
                .update();
    }

    public List<DataOverride> find(long shootDayId) {
        return jdbc.sql("SELECT * FROM shoot_day_overrides WHERE shoot_day_id = :id ORDER BY id")
                .param("id", shootDayId)
                .query((rs, n) -> new DataOverride(rs.getLong("id"), rs.getLong("shoot_day_id"),
                        rs.getObject("event_id", Long.class), rs.getString("kind"),
                        rs.getObject("target_id", Long.class), json.tree(rs.getString("payload"))))
                .list();
    }

    /**
     * 같은 장소와 시각의 우천 알림을 처음 기록할 때만 true를 돌려준다.
     */
    public boolean markRainAlertSent(long shootDayId, long locationId, int hour) {
        return jdbc.sql("""
                        INSERT INTO rain_alerts_sent (shoot_day_id, location_id, hour)
                        VALUES (:shootDayId, :locationId, :hour)
                        ON CONFLICT DO NOTHING
                        """)
                .param("shootDayId", shootDayId)
                .param("locationId", locationId)
                .param("hour", hour)
                .update() > 0;
    }
}
