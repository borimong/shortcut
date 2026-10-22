package com.shortcut.repository;

import static com.shortcut.repository.PlanRepository.time;

import com.shortcut.common.JsonColumns;
import com.shortcut.domain.Callsheet;
import com.shortcut.engine.PlanSnapshot;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class CallsheetRepository {

    private final JdbcClient jdbc;
    private final JsonColumns json;

    public CallsheetRepository(JdbcClient jdbc, JsonColumns json) {
        this.jdbc = jdbc;
        this.json = json;
    }

    public List<Callsheet> findAll(long shootDayId) {
        return jdbc.sql(select() + " WHERE shoot_day_id = :id ORDER BY version_no DESC")
                .param("id", shootDayId)
                .query(this::map)
                .list();
    }

    public Optional<Callsheet> find(long shootDayId, int versionNo) {
        return jdbc.sql(select() + " WHERE shoot_day_id = :id AND version_no = :versionNo")
                .param("id", shootDayId)
                .param("versionNo", versionNo)
                .query(this::map)
                .optional();
    }

    public Optional<Callsheet> findLatest(long shootDayId) {
        return jdbc.sql(select() + " WHERE shoot_day_id = :id ORDER BY version_no DESC LIMIT 1")
                .param("id", shootDayId)
                .query(this::map)
                .optional();
    }

    public Callsheet insert(long shootDayId, int versionNo, long proposalId, PlanSnapshot pm) {
        long id = jdbc.sql("""
                        INSERT INTO callsheet_versions
                            (shoot_day_id, version_no, proposal_id, pm_location_id, pm_equipment_ids, pm_start, pm_end, pm_cost,
                             scenes)
                        VALUES (:id, :versionNo, :proposalId, :location, CAST(:equipment AS jsonb), :start, :end, :cost,
                                CAST(:scenes AS jsonb))
                        RETURNING id
                        """)
                .param("id", shootDayId)
                .param("versionNo", versionNo)
                .param("proposalId", proposalId)
                .param("location", pm.locationId())
                .param("equipment", json.write(pm.equipmentIds()))
                .param("start", pm.start())
                .param("end", pm.end())
                .param("cost", pm.cost())
                .param("scenes", json.write(pm.scenes()))
                .query(Long.class)
                .single();
        return jdbc.sql(select() + " WHERE id = :id").param("id", id).query(this::map).single();
    }

    public boolean hasHeldReservation(long shootDayId, long locationId) {
        return jdbc.sql("""
                        SELECT count(*) FROM reservations
                        WHERE shoot_day_id = :id AND location_id = :location AND status = 'HELD'
                        """)
                .param("id", shootDayId)
                .param("location", locationId)
                .query(Long.class)
                .single() > 0;
    }

    public void insertManualReservation(String id, long shootDayId, long locationId, LocalTime start, LocalTime end) {
        jdbc.sql("""
                        INSERT INTO reservations (id, shoot_day_id, location_id, start_time, end_time, status, provider)
                        VALUES (:id, :shootDayId, :location, :start, :end, 'MANUAL_PENDING', 'MANUAL')
                        ON CONFLICT (id) DO NOTHING
                        """)
                .param("id", id)
                .param("shootDayId", shootDayId)
                .param("location", locationId)
                .param("start", start)
                .param("end", end)
                .update();
    }

    /**
     * 같은 배포 메시지가 다시 와도 수신자별 기록이 하나만 남도록 유니크 키에 맡긴다.
     */
    public int insertDistribution(long callsheetVersionId, long userId) {
        return jdbc.sql("""
                        INSERT INTO distribution_logs (callsheet_version_id, user_id, channel, status)
                        VALUES (:versionId, :userId, 'WEB', 'SENT')
                        ON CONFLICT (callsheet_version_id, user_id, channel) DO NOTHING
                        """)
                .param("versionId", callsheetVersionId)
                .param("userId", userId)
                .update();
    }

    public List<DistributionSummary> findDistributions(long shootDayId) {
        return jdbc.sql("""
                        SELECT cv.version_no, min(d.created_at) AS at, count(*) AS recipients
                        FROM distribution_logs d JOIN callsheet_versions cv ON cv.id = d.callsheet_version_id
                        WHERE cv.shoot_day_id = :id
                        GROUP BY cv.version_no ORDER BY cv.version_no
                        """)
                .param("id", shootDayId)
                .query((rs, n) -> new DistributionSummary(rs.getInt("version_no"),
                        rs.getObject("at", OffsetDateTime.class), rs.getInt("recipients")))
                .list();
    }

    public record DistributionSummary(int versionNo, OffsetDateTime at, int recipients) {
    }

    private static String select() {
        return "SELECT *, pm_equipment_ids::text AS equipment_json, scenes::text AS scenes_json FROM callsheet_versions";
    }

    private Callsheet map(ResultSet rs, int row) throws SQLException {
        PlanSnapshot pm = new PlanSnapshot(rs.getLong("pm_location_id"), json.longs(rs.getString("equipment_json")),
                time(rs, "pm_start"), time(rs, "pm_end"), rs.getLong("pm_cost"), json.sceneSlots(rs.getString("scenes_json")));
        return new Callsheet(rs.getLong("id"), rs.getLong("shoot_day_id"), rs.getInt("version_no"),
                rs.getObject("proposal_id", Long.class), pm, rs.getObject("created_at", OffsetDateTime.class));
    }
}
