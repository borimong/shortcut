package com.shortcut.repository;

import java.util.List;
import javax.sql.DataSource;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
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
            // Agent가 만든 엣지 가운데 다른 촬영일 노드에만 닿는 것(그 촬영일의 4안 등)은 남긴다.
            // 이 촬영일 노드에 닿거나 어느 촬영일에도 딸리지 않은 노드끼리 이은 엣지는 지운다.
            """
            DELETE FROM ontology_edges e
            WHERE e.created_by <> 'seed'
              AND (EXISTS (SELECT 1 FROM ontology_nodes n
                           WHERE n.node_id IN (e.src, e.dst) AND n.props ->> 'shootDayId' = CAST(:id AS text))
                   OR NOT EXISTS (SELECT 1 FROM ontology_nodes n
                                  WHERE n.node_id IN (e.src, e.dst) AND n.props ->> 'shootDayId' IS NOT NULL))
            """,
            "DELETE FROM distribution_logs WHERE callsheet_version_id IN "
                    + "(SELECT id FROM callsheet_versions WHERE shoot_day_id = :id AND version_no > 1)",
            "DELETE FROM callsheet_versions WHERE shoot_day_id = :id AND version_no > 1",
            "DELETE FROM reservations WHERE shoot_day_id = :id AND provider <> 'OURPLACE'",
            // 실행팀이 시드 예약을 확정하거나 취소했어도 시드 상태(가예약, 금액과 수수료 없음)로 되돌린다.
            """
            UPDATE reservations SET status = 'HELD', task_id = NULL, cost_krw = 0, cancel_fee_krw = 0
            WHERE shoot_day_id = :id AND provider = 'OURPLACE'
            """,
            // 실행팀이 남긴 렌탈, 허가, 차량, 연락, 장부 기록을 지운다.
            "DELETE FROM ledger_entries WHERE shoot_day_id = :id",
            "DELETE FROM outreach_messages WHERE shoot_day_id = :id",
            "DELETE FROM transport_bookings WHERE shoot_day_id = :id",
            "DELETE FROM permits WHERE shoot_day_id = :id",
            "DELETE FROM rental_bookings WHERE shoot_day_id = :id",
            """
            UPDATE blocks b SET location_id = o.location_id, equipment_ids = o.equipment_ids,
                   start_time = o.start_time, end_time = o.end_time
            FROM plan_options o
            WHERE b.shoot_day_id = :id AND b.code = 'PM'
              AND o.shoot_day_id = b.shoot_day_id AND o.block_code = 'PM' AND o.option_no = 1
            """,
            // 확정으로 바뀐 오후 블록 씬 순서를 콜시트 v1 스냅숏 순서로 되돌린다. 블록이 쓰던 sort 값을 작은 것부터 다시 나눠 준다.
            """
            WITH wanted AS (
                SELECT e.value ->> 'code' AS code, e.ordinality AS n
                FROM callsheet_versions cv CROSS JOIN jsonb_array_elements(cv.scenes) WITH ORDINALITY AS e
                WHERE cv.shoot_day_id = :id AND cv.version_no = 1
            ), slots AS (
                SELECT sort, row_number() OVER (ORDER BY sort) AS n
                FROM scenes WHERE shoot_day_id = :id AND block_code = 'PM'
            )
            UPDATE scenes s SET sort = slots.sort
            FROM wanted JOIN slots ON slots.n = wanted.n
            WHERE s.shoot_day_id = :id AND s.block_code = 'PM' AND s.code = wanted.code
            """,
            // 오후 블록을 1안으로 되돌린 뒤에 지워야 4안 장소를 가리키던 블록이 남지 않는다.
            "DELETE FROM shoot_day_alternatives WHERE shoot_day_id = :id",
            "DELETE FROM weather_forecasts WHERE shoot_day_id = :id AND location_id >= 100",
            "DELETE FROM reservations WHERE shoot_day_id = :id AND location_id >= 100",
            // 같은 대체 장소를 다른 촬영일도 4안으로 등록했으면 그 촬영일 행이 아직 가리키므로 장소 행을 남긴다.
            """
            DELETE FROM locations l
            WHERE l.id >= 100 AND l.id NOT IN (
                SELECT location_id FROM shoot_day_alternatives
                UNION SELECT location_id FROM weather_forecasts
                UNION SELECT location_id FROM reservations
                UNION SELECT location_id FROM plan_options
                UNION SELECT pm_location_id FROM callsheet_versions
                UNION SELECT location_id FROM blocks WHERE location_id IS NOT NULL
                UNION SELECT location_id FROM scenes WHERE location_id IS NOT NULL)
            """,
            // 이 촬영일 노드에 닿는 Agent 엣지는 위에서 지웠으므로 이 촬영일의 4안 노드를 지울 수 있다.
            "DELETE FROM ontology_nodes WHERE node_id = 'PLAN:' || :id || '-4'",
            // 업무 행이 사라진 대체 장소 노드를 지운다. 다른 촬영일 노드에서 이어진 엣지가 아직 있으면 외래키에 걸리므로 남긴다.
            """
            DELETE FROM ontology_nodes n
            WHERE n.type = 'LOCATION' AND NOT EXISTS (SELECT 1 FROM locations l WHERE n.node_id = 'LOCATION:' || l.id)
              AND NOT EXISTS (SELECT 1 FROM ontology_edges e WHERE n.node_id IN (e.src, e.dst))
            """,
            // 변경 입력이 남긴 장비 고장, 배우 불참, 장소 취소, 강수량 덮어쓰기와 우천 알림 기록을 지운다.
            "DELETE FROM shoot_day_overrides WHERE shoot_day_id = :id",
            "DELETE FROM rain_alerts_sent WHERE shoot_day_id = :id",
            // 아래에서 촬영일 날짜가 바뀌면 전에 받은 날씨 API 예보는 다른 날짜의 예보다. 지우면 다음 정기 확인(1분 간격)에서 새 날짜로 받는다.
            """
            DELETE FROM weather_forecasts w USING shoot_days d
            WHERE w.source = 'LIVE' AND w.shoot_day_id = d.id
              AND d.project_id = (SELECT project_id FROM shoot_days WHERE id = :id)
              AND d.shoot_date <> CURRENT_DATE + CAST(d.id - (SELECT min(f.id) FROM shoot_days f
                                                              WHERE f.project_id = d.project_id) AS integer)
            """,
            "UPDATE shoot_days SET data_version = 1 WHERE id = :id",
            // 씬 진행 표시가 시계 기준이라 같은 작품의 첫 촬영일(시연 촬영일)은 항상 오늘로 두고, n회차는 오늘 + (n - 1)일에 둔다.
            // 촬영판은 계속 오늘인 시연 촬영일을 고르고, 적용 기간이 있는 자원 상태가 다음 촬영일에도 걸리는지 이어서 확인할 수 있다.
            // 2회차를 초기화해도 날짜는 첫 촬영일 기준이라 회차끼리 날짜가 겹치지 않는다.
            """
            UPDATE shoot_days d SET shoot_date = CURRENT_DATE + CAST(d.id - (SELECT min(f.id) FROM shoot_days f
                                                                             WHERE f.project_id = d.project_id) AS integer)
            WHERE d.project_id = (SELECT project_id FROM shoot_days WHERE id = :id)
            """
    };

    // 배우 날짜별 일정 목데이터(SEED 줄)를 만드는 시드 파일이다. 서버가 켜질 때도 같은 파일이 돈다.
    private static final String SCHEDULE_SEED = "data-schedule.sql";

    private final JdbcClient jdbc;
    private final DataSource dataSource;

    public ResetRepository(JdbcClient jdbc, DataSource dataSource) {
        this.jdbc = jdbc;
        this.dataSource = dataSource;
    }

    /**
     * 이 촬영일이 속한 작품의 모든 촬영일을 시드 상태로 되돌린다. 촬영일 하나만 되돌리면 다른 회차에 넣은 변경
     * (장소 취소, 장비 고장, 배우 다른 일정)과 확정이 남아, 같은 시나리오를 다시 돌릴 때 변경이 두 벌로 쌓인다.
     * 위 문장은 촬영일마다 돌려도 결과가 같게 짜여 있어(작품 전체를 보는 문장 포함) 촬영일 순서대로 한 번씩 돈다.
     */
    public void reset(long shootDayId) {
        List<Long> days = jdbc.sql("""
                        SELECT id FROM shoot_days
                        WHERE project_id = (SELECT project_id FROM shoot_days WHERE id = :id)
                        ORDER BY id
                        """)
                .param("id", shootDayId)
                .query(Long.class)
                .list();
        for (long day : days) {
            for (String sql : STATEMENTS) {
                JdbcClient.StatementSpec spec = jdbc.sql(sql);
                if (sql.contains(":id")) {
                    spec = spec.param("id", day);
                }
                spec.update();
            }
        }
        // 배우 일정 목데이터는 1회차 날짜에서 계산한다. 위에서 촬영일 날짜가 바뀌었을 수 있으니 SEED 줄을 지우고 다시 만든다.
        // 날짜를 같은 날 수만큼 밀면 "금·토 공연" 같은 요일 규칙이 어긋나서 밀지 않는다. 소속사 회신과 직접 입력은 남긴다.
        // 같은 트랜잭션의 연결을 쓰므로 초기화가 실패하면 함께 되돌아간다.
        jdbc.sql("DELETE FROM actor_availability WHERE source = 'SEED'").update();
        new ResourceDatabasePopulator(new ClassPathResource(SCHEDULE_SEED)).execute(dataSource);
    }
}
