package com.shortcut.repository;

import org.springframework.jdbc.core.simple.JdbcClient;
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
            // 변경 입력이 남긴 장비 고장, 배우 불참, 장소 취소, 강수량 덮어쓰기와 우천 알림 기록을 지운다.
            "DELETE FROM shoot_day_overrides WHERE shoot_day_id = :id",
            "DELETE FROM rain_alerts_sent WHERE shoot_day_id = :id",
            // 씬 진행 표시가 시계 기준이라 시연 촬영일은 항상 오늘로 둔다.
            "UPDATE shoot_days SET data_version = 1, shoot_date = CURRENT_DATE WHERE id = :id"
    };

    private final JdbcClient jdbc;

    public ResetRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public void reset(long shootDayId) {
        for (String sql : STATEMENTS) {
            JdbcClient.StatementSpec spec = jdbc.sql(sql);
            if (sql.contains(":id")) {
                spec = spec.param("id", shootDayId);
            }
            spec.update();
        }
    }
}
