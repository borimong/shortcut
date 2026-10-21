package com.shortcut.repository;

import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/**
 * 시연 시나리오를 처음부터 다시 돌리려고 촬영일을 시드 상태로 되돌린다.
 * 시드 값은 data.sql에 한 번만 두고 여기서는 1안 행을 다시 읽어 복원한다.
 * 지우는 순서는 외래키에 맞춰 두었다. 변경안을 먼저 지우면 작업과 콜시트의 변경안 칸은 SET NULL로 비고,
 * 4안 장소를 지우면 그 장소의 우천 알림 기록은 CASCADE로 함께 지워진다(schema.sql 정리 구역).
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
            // Agent가 만든 엣지는 위에서 모두 지웠으므로 이 촬영일의 4안 노드와 업무 행이 사라진 대체 장소 노드만 남는다.
            "DELETE FROM ontology_nodes WHERE node_id = 'PLAN:' || :id || '-4'",
            "DELETE FROM locations WHERE id >= 100",
            """
            DELETE FROM ontology_nodes n
            WHERE n.type = 'LOCATION' AND NOT EXISTS (SELECT 1 FROM locations l WHERE n.node_id = 'LOCATION:' || l.id)
            """,
            // 변경 입력이 남긴 장비 고장, 배우 불참, 장소 취소, 강수량 덮어쓰기와 우천 알림 기록을 지운다.
            "DELETE FROM shoot_day_overrides WHERE shoot_day_id = :id",
            "DELETE FROM rain_alerts_sent WHERE shoot_day_id = :id",
            // 씬 진행 표시가 시계 기준이라 시연 촬영일은 항상 오늘로 둔다.
            "UPDATE shoot_days SET data_version = 1, shoot_date = CURRENT_DATE WHERE id = :id",
            // 같은 작품의 다음 촬영일(시드 2회차)은 그다음 날부터 하루씩 둔다. 촬영판은 계속 오늘인 시연 촬영일을 고르고,
            // 적용 기간이 있는 자원 상태가 다음 촬영일에도 걸리는지 이어서 확인할 수 있다.
            """
            UPDATE shoot_days SET shoot_date = CURRENT_DATE + CAST(id - :id AS integer)
            WHERE id > :id AND project_id = (SELECT project_id FROM shoot_days WHERE id = :id)
            """
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
