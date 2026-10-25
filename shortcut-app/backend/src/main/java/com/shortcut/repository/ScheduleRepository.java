package com.shortcut.repository;

import com.shortcut.domain.AvailabilityEntry;
import com.shortcut.domain.SceneCharacter;
import com.shortcut.domain.ScheduledSlot;
import com.shortcut.domain.ScriptScene;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/**
 * 배우 날짜별 일정(actor_availability)과 대본 씬, 촬영 배정을 날짜 범위로 읽는다.
 * 한 촬영일 판정에 쓰는 값은 PlanDataService.load()가 이 저장소를 불러 엔진 입력에 싣는다.
 */
@Repository
public class ScheduleRepository {

    private final JdbcClient jdbc;

    public ScheduleRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public List<AvailabilityEntry> findAvailability(LocalDate from, LocalDate to) {
        return jdbc.sql("""
                        SELECT * FROM actor_availability
                        WHERE on_date BETWEEN :from AND :to
                        ORDER BY on_date, actor_id, start_time NULLS FIRST
                        """)
                .param("from", from)
                .param("to", to)
                .query((rs, n) -> new AvailabilityEntry(rs.getLong("actor_id"), rs.getObject("on_date", LocalDate.class),
                        rs.getString("kind"), PlanRepository.time(rs, "start_time"), PlanRepository.time(rs, "end_time"),
                        rs.getString("reason_kind"), rs.getString("memo"), rs.getString("source")))
                .list();
    }

    public Optional<LocalDate> findFirstShootDate(long projectId) {
        return jdbc.sql("SELECT min(shoot_date) FROM shoot_days WHERE project_id = :projectId")
                .param("projectId", projectId)
                .query(LocalDate.class)
                .optional();
    }

    /** 배우가 우리 촬영에 배정된 블록이다. 같은 블록의 씬은 한 줄로 묶는다. */
    public List<ScheduledSlot> findScheduledSlots(long projectId, LocalDate from, LocalDate to) {
        return jdbc.sql("""
                        SELECT c.actor_id, d.shoot_date, d.id AS shoot_day_id, b.code AS block_code, b.start_time,
                               b.end_time, string_agg(s.code, ', ' ORDER BY s.sort) AS scene_codes
                        FROM shoot_days d
                        JOIN blocks b ON b.shoot_day_id = d.id
                        JOIN scenes s ON s.shoot_day_id = d.id AND s.block_code = b.code
                        JOIN scene_characters sc ON sc.project_id = s.project_id AND sc.scene_code = s.code
                        JOIN characters c ON c.id = sc.character_id AND c.actor_id IS NOT NULL
                        WHERE d.project_id = :projectId AND d.shoot_date BETWEEN :from AND :to
                        GROUP BY c.actor_id, d.shoot_date, d.id, b.code, b.start_time, b.end_time
                        ORDER BY d.shoot_date, b.start_time, c.actor_id
                        """)
                .param("projectId", projectId)
                .param("from", from)
                .param("to", to)
                .query((rs, n) -> new ScheduledSlot(rs.getLong("actor_id"), rs.getObject("shoot_date", LocalDate.class),
                        rs.getLong("shoot_day_id"), rs.getString("block_code"), PlanRepository.time(rs, "start_time"),
                        PlanRepository.time(rs, "end_time"), rs.getString("scene_codes")))
                .list();
    }

    /** 대본 씬 전체와 등장 배역, 배정한 촬영일이다. */
    public List<ScriptScene> findScriptScenes(long projectId) {
        Map<String, List<SceneCharacter>> characters = new HashMap<>();
        jdbc.sql("""
                        SELECT sc.scene_code, c.id, c.name, c.actor_id
                        FROM scene_characters sc JOIN characters c ON c.id = sc.character_id
                        WHERE sc.project_id = :projectId
                        ORDER BY sc.scene_code, c.id
                        """)
                .param("projectId", projectId)
                .query((RowCallbackHandler) rs -> characters.computeIfAbsent(rs.getString("scene_code"), k -> new ArrayList<>())
                        .add(new SceneCharacter(rs.getLong("id"), rs.getString("name"), rs.getObject("actor_id", Long.class))));
        return jdbc.sql("""
                        SELECT ss.code, ss.heading, ss.int_ext, ss.time_of_day, ss.est_minutes,
                               COALESCE(array_agg(s.shoot_day_id ORDER BY s.shoot_day_id)
                                        FILTER (WHERE s.shoot_day_id IS NOT NULL), '{}') AS shoot_day_ids
                        FROM script_scenes ss
                        LEFT JOIN scenes s ON s.project_id = ss.project_id AND s.code = ss.code
                        WHERE ss.project_id = :projectId
                        GROUP BY ss.code, ss.heading, ss.int_ext, ss.time_of_day, ss.est_minutes
                        ORDER BY ss.code
                        """)
                .param("projectId", projectId)
                .query((rs, n) -> new ScriptScene(rs.getString("code"), rs.getString("heading"), rs.getString("int_ext"),
                        rs.getString("time_of_day"), rs.getObject("est_minutes", Integer.class),
                        List.copyOf(characters.getOrDefault(rs.getString("code"), List.of())),
                        List.of((Long[]) rs.getArray("shoot_day_ids").getArray())))
                .list();
    }

    /**
     * 데이터 정합성 문제를 사람이 읽을 문장으로 돌려준다. 기동 때 경고 로그로만 남긴다.
     * 대사 화자가 등장 배역에 없거나, 배정한 씬의 배역이 캐스팅되지 않았거나, 블록 씬 길이 합이 블록보다 길거나,
     * 같은 배우·날짜에 종일 불가와 가능 시간대가 함께 있거나, 대본 씬에 촬영 장소가 없거나,
     * 씬 배정에 적은 세트 장소가 대본 씬 촬영 장소와 다른 경우다.
     */
    public List<String> findIntegrityProblems() {
        return jdbc.sql("""
                        SELECT ss.code || ' 대본 씬에 촬영 장소가 정해지지 않았습니다' FROM script_scenes ss
                        WHERE ss.location_id IS NULL
                        UNION ALL
                        SELECT DISTINCT s.code || ' 배정 장소(' || s.location_id || ')가 대본 씬 촬영 장소('
                               || ss.location_id || ')와 다릅니다' FROM scenes s
                        JOIN script_scenes ss ON ss.project_id = s.project_id AND ss.code = s.code
                        WHERE s.location_id <> ss.location_id
                        UNION ALL
                        SELECT l.scene_code || ' 대사 화자(배역 ' || l.character_id || ')가 등장 배역에 없습니다' FROM script_lines l
                        WHERE l.kind = 'DIALOGUE' AND NOT EXISTS (
                            SELECT 1 FROM scene_characters sc
                            WHERE sc.project_id = l.project_id AND sc.scene_code = l.scene_code
                              AND sc.character_id = l.character_id)
                        UNION ALL
                        SELECT DISTINCT s.code || ' 배역 ' || c.name || '에 배우가 정해지지 않았습니다' FROM scenes s
                        JOIN scene_characters sc ON sc.project_id = s.project_id AND sc.scene_code = s.code
                        JOIN characters c ON c.id = sc.character_id
                        WHERE c.actor_id IS NULL
                        UNION ALL
                        SELECT b.shoot_day_id || '회차 ' || b.code || ' 블록 씬 길이 합(' || sum(s.duration_min)
                               || '분)이 블록(' || b.duration_min || '분)보다 깁니다' FROM blocks b
                        JOIN scenes s ON s.shoot_day_id = b.shoot_day_id AND s.block_code = b.code
                        GROUP BY b.shoot_day_id, b.code, b.duration_min
                        HAVING sum(s.duration_min) > b.duration_min
                        UNION ALL
                        SELECT DISTINCT '배우 ' || a.actor_id || ' ' || a.on_date || '에 종일 불가와 가능 시간대가 함께 있습니다'
                        FROM actor_availability a JOIN actor_availability w
                          ON w.actor_id = a.actor_id AND w.on_date = a.on_date AND w.kind = 'WINDOW'
                        WHERE a.kind = 'OFF'
                        """)
                .query(String.class)
                .list();
    }
}
