package com.shortcut.repository;

import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.beans.factory.annotation.Value;
import java.time.LocalDate;
import org.springframework.stereotype.Repository;

/**
 * 시연 시나리오를 처음부터 다시 돌리려고 촬영일을 시드 상태로 되돌린다.
 * 시드 값은 data.sql에 한 번만 두고 여기서는 1안 행을 다시 읽어 복원한다.
 */
@Repository
public class ResetRepository {

    private static final String[] STATEMENTS = {
            "DELETE FROM approvals",
            "DELETE FROM proposals",
            "DELETE FROM ai_task_events",
            "DELETE FROM ai_tasks",
            "DELETE FROM change_events",
            "DELETE FROM notifications",
            "DELETE FROM disaster_alerts",
            "DELETE FROM outbox",
            "DELETE FROM ontology_edges WHERE created_by <> 'seed'",
            "DELETE FROM distribution_logs WHERE callsheet_version_id IN "
                    + "(SELECT id FROM callsheet_versions WHERE shoot_day_id = :id AND version_no > 1)",
            "DELETE FROM callsheet_versions WHERE shoot_day_id = :id AND version_no > 1",
            "DELETE FROM reservations WHERE shoot_day_id = :id AND provider <> 'OURPLACE'",
            "UPDATE reservations SET status = 'HELD' WHERE shoot_day_id = :id AND provider = 'OURPLACE'",
            """
            UPDATE blocks b SET location_id = o.location_id, equipment_ids = o.equipment_ids,
                   start_time = o.start_time, end_time = o.end_time
            FROM plan_options o
            WHERE b.shoot_day_id = :id AND b.code = 'PM'
              AND o.shoot_day_id = b.shoot_day_id AND o.block_code = 'PM' AND o.option_no = 1
            """,
            // 오후 블록을 1안으로 되돌린 뒤에 지워야 4안 장소를 가리키던 블록이 남지 않는다.
            "DELETE FROM shoot_day_alternatives WHERE shoot_day_id = :id",
            "DELETE FROM weather_forecasts WHERE location_id >= 100",
            "DELETE FROM reservations WHERE location_id >= 100",
            "DELETE FROM ontology_edges WHERE dst LIKE 'LOCATION:1__'",
            "DELETE FROM ontology_nodes WHERE node_id LIKE 'LOCATION:1__' OR node_id = 'PLAN:4'",
            "DELETE FROM locations WHERE id >= 100",
            "UPDATE shoot_days SET data_version = 1, shoot_date = CURRENT_DATE + 1 WHERE id = :id"
    };

    private final JdbcClient jdbc;
    private final String fixtureDate;

    public ResetRepository(JdbcClient jdbc, @Value("${shortcut.fixture-date:}") String fixtureDate) {
        this.jdbc = jdbc;
        this.fixtureDate = fixtureDate;
    }

    public void reset(long shootDayId) {
        for (String sql : STATEMENTS) {
            JdbcClient.StatementSpec spec = jdbc.sql(sql);
            if (sql.contains(":id")) {
                spec = spec.param("id", shootDayId);
            }
            spec.update();
        }
        if (!fixtureDate.isBlank()) {
            jdbc.sql("UPDATE actors a SET available_from=s.available_from, available_to=s.available_to, weekly_hours_used=s.weekly_hours_used FROM v3_actor_seed s WHERE a.id=s.id").update();
            jdbc.sql("UPDATE locations a SET open_from=s.open_from, open_to=s.open_to FROM v3_location_seed s WHERE a.id=s.id").update();
            jdbc.sql("UPDATE equipment a SET available=s.available FROM v3_equipment_seed s WHERE a.id=s.id").update();
            jdbc.sql("UPDATE weather_forecasts a SET precip_prob=s.precip_prob FROM v3_weather_seed s WHERE a.shoot_day_id=s.shoot_day_id AND a.location_id=s.location_id AND a.hour=s.hour").update();
            jdbc.sql("UPDATE shoot_days SET shoot_date = :date WHERE id = :id")
                    .param("date", LocalDate.parse(fixtureDate)).param("id", shootDayId).update();
        }
    }
}
