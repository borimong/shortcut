package com.shortcut.repository;

import com.shortcut.common.JsonColumns;
import com.shortcut.domain.DataOverride;
import java.time.LocalDate;
import java.time.OffsetDateTime;
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
        insert(shootDayId, eventId, kind, targetId, payload, null, null, null);
    }

    /**
     * 시작일은 등록한 촬영일의 날짜다. untilDate가 있으면 그날까지 다른 촬영일에도 적용된다.
     */
    public void insert(long shootDayId, long eventId, String kind, Long targetId, Object payload,
                       LocalDate untilDate, String memo, String createdBy) {
        jdbc.sql("""
                        INSERT INTO shoot_day_overrides (shoot_day_id, event_id, kind, target_id, payload,
                                                         starts_on, until_date, memo, created_by)
                        VALUES (:shootDayId, :eventId, :kind, :targetId, CAST(:payload AS jsonb),
                                (SELECT shoot_date FROM shoot_days WHERE id = :shootDayId), :untilDate, :memo, :createdBy)
                        """)
                .param("shootDayId", shootDayId)
                .param("eventId", eventId)
                .param("kind", kind)
                .param("targetId", targetId)
                .param("payload", json.write(payload))
                .param("untilDate", untilDate)
                .param("memo", memo)
                .param("createdBy", createdBy)
                .update();
    }

    /**
     * 이 촬영일에 적용되는 덮어쓰기다. 되돌린 것은 빼고, 다른 촬영일에 등록했어도 기간 안이면 넣는다.
     */
    public List<DataOverride> find(long shootDayId) {
        return jdbc.sql("""
                        SELECT o.* FROM shoot_day_overrides o, shoot_days d
                        WHERE d.id = :id AND o.cleared_at IS NULL
                          AND (o.shoot_day_id = d.id
                               OR (o.until_date IS NOT NULL AND d.shoot_date BETWEEN o.starts_on AND o.until_date))
                        ORDER BY o.id
                        """)
                .param("id", shootDayId)
                .query((rs, n) -> new DataOverride(rs.getLong("id"), rs.getLong("shoot_day_id"),
                        rs.getObject("event_id", Long.class), rs.getString("kind"),
                        rs.getObject("target_id", Long.class), json.tree(rs.getString("payload")),
                        rs.getObject("starts_on", LocalDate.class), rs.getObject("until_date", LocalDate.class),
                        rs.getString("memo"), rs.getString("created_by"),
                        rs.getObject("created_at", OffsetDateTime.class)))
                .list();
    }

    /**
     * 덮어쓰기를 되돌린다. 이미 되돌린 행이면 false다.
     */
    public boolean clear(long id, String username) {
        return jdbc.sql("UPDATE shoot_day_overrides SET cleared_at = now(), cleared_by = :username WHERE id = :id AND cleared_at IS NULL")
                .param("id", id)
                .param("username", username)
                .update() > 0;
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
