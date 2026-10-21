package com.shortcut.repository;

import com.shortcut.common.JsonColumns;
import com.shortcut.domain.Actor;
import com.shortcut.domain.Block;
import com.shortcut.domain.DisasterAlert;
import com.shortcut.domain.Equipment;
import com.shortcut.domain.ExternalLocation;
import com.shortcut.domain.Location;
import com.shortcut.domain.PlanOption;
import com.shortcut.domain.Scene;
import com.shortcut.domain.ShootDay;
import com.shortcut.domain.WeatherHour;
import com.shortcut.engine.PlanSnapshot;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;
import java.time.LocalTime;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class PlanRepository {

    // 카탈로그 장소를 촬영일 장소로 등록할 때 쓰는 id 시작값이다. 시드 장소(1~4)와 겹치지 않게 100부터 쓴다.
    public static final long ALTERNATIVE_LOCATION_ID_BASE = 100;
    // 아워플레이스 대관 시간은 카탈로그에 없어 일반적인 대관 시간인 08:00~22:00으로 본다.
    private static final LocalTime ALTERNATIVE_OPEN_FROM = LocalTime.of(8, 0);
    private static final LocalTime ALTERNATIVE_OPEN_TO = LocalTime.of(22, 0);

    private final JdbcClient jdbc;
    private final JsonColumns json;

    public PlanRepository(JdbcClient jdbc, JsonColumns json) {
        this.jdbc = jdbc;
        this.json = json;
    }

    public Optional<ShootDay> findShootDay(long id) {
        return jdbc.sql("""
                        SELECT sd.*, sd.crew_calls::text AS crew_calls_json, p.name AS project_name,
                               p.block_budget_cap, p.crew_weekly_hours_used
                        FROM shoot_days sd JOIN projects p ON p.id = sd.project_id
                        WHERE sd.id = :id
                        """)
                .param("id", id)
                .query((rs, n) -> new ShootDay(rs.getLong("id"), rs.getLong("project_id"), rs.getString("project_name"),
                        rs.getObject("shoot_date", LocalDate.class), time(rs, "call_time"), rs.getInt("data_version"),
                        rs.getString("notice"), rs.getString("crew_calls_json"), rs.getLong("block_budget_cap"),
                        rs.getDouble("crew_weekly_hours_used")))
                .optional();
    }

    /**
     * 오늘 이후 가장 가까운 촬영일을 고르고 없으면 가장 최근 촬영일을 쓴다.
     * 시드 날짜가 지나도 촬영판이 비지 않게 하려는 선택이다.
     */
    public Optional<Long> findBoardShootDayId() {
        return jdbc.sql("""
                        SELECT id FROM shoot_days
                        ORDER BY (shoot_date < CURRENT_DATE), abs(shoot_date - CURRENT_DATE), id
                        LIMIT 1
                        """)
                .query(Long.class)
                .optional();
    }

    public Optional<Integer> lockDataVersion(long shootDayId) {
        return jdbc.sql("SELECT data_version FROM shoot_days WHERE id = :id FOR UPDATE")
                .param("id", shootDayId)
                .query(Integer.class)
                .optional();
    }

    public int bumpDataVersion(long shootDayId) {
        return jdbc.sql("UPDATE shoot_days SET data_version = data_version + 1 WHERE id = :id RETURNING data_version")
                .param("id", shootDayId)
                .query(Integer.class)
                .single();
    }

    public List<Block> findBlocks(long shootDayId) {
        return jdbc.sql("SELECT *, equipment_ids::text AS equipment_json FROM blocks WHERE shoot_day_id = :id ORDER BY start_time")
                .param("id", shootDayId)
                .query((rs, n) -> new Block(rs.getString("code"), time(rs, "start_time"), time(rs, "end_time"),
                        rs.getInt("duration_min"), rs.getObject("location_id", Long.class),
                        json.longs(rs.getString("equipment_json"))))
                .list();
    }

    public void updateBlock(long shootDayId, String code, PlanSnapshot plan) {
        jdbc.sql("""
                        UPDATE blocks SET location_id = :location, equipment_ids = CAST(:equipment AS jsonb),
                               start_time = :start, end_time = :end
                        WHERE shoot_day_id = :id AND code = :code
                        """)
                .param("location", plan.locationId())
                .param("equipment", json.write(plan.equipmentIds()))
                .param("start", plan.start())
                .param("end", plan.end())
                .param("id", shootDayId)
                .param("code", code)
                .update();
    }

    public List<Scene> findScenes(long shootDayId) {
        return jdbc.sql("SELECT *, actor_ids::text AS actor_json FROM scenes WHERE shoot_day_id = :id ORDER BY sort")
                .param("id", shootDayId)
                .query((rs, n) -> new Scene(rs.getString("code"), rs.getString("block_code"), rs.getString("title"),
                        rs.getInt("duration_min"), rs.getBoolean("outdoor_intent"), json.longs(rs.getString("actor_json"))))
                .list();
    }

    // 배우, 장소, 장비는 원본 시드 행이다. 변경 입력과 자원 현황의 고장, 취소, 불참은 shoot_day_overrides에만 있으므로
    // 서비스는 아래 세 메서드를 직접 부르지 말고 PlanDataService.load()로 덮어쓰기까지 얹은 상태를 읽는다.
    public List<Actor> findActors() {
        return jdbc.sql("SELECT * FROM actors ORDER BY id")
                .query((rs, n) -> new Actor(rs.getLong("id"), rs.getString("name"), time(rs, "available_from"),
                        time(rs, "available_to"), rs.getDouble("weekly_hours_used"), rs.getString("contract_doc_id"),
                        rs.getBoolean("no_night"), nullableDouble(rs, "max_daily_hours"), rs.getString("manager_phone")))
                .list();
    }

    public List<Location> findLocations() {
        return jdbc.sql("SELECT * FROM locations ORDER BY id")
                .query((rs, n) -> new Location(rs.getLong("id"), rs.getString("name"), rs.getString("address"),
                        rs.getBoolean("indoor"), rs.getString("region"), time(rs, "open_from"), time(rs, "open_to"),
                        time(rs, "permit_from"), time(rs, "permit_to"), rs.getLong("cost"), rs.getBoolean("no_fly_zone"),
                        rs.getDouble("fit"), rs.getDouble("distance_km"), rs.getString("note"), true))
                .list();
    }

    public List<Equipment> findEquipment() {
        return jdbc.sql("SELECT * FROM equipment ORDER BY id")
                .query((rs, n) -> new Equipment(rs.getLong("id"), rs.getString("name"), rs.getBoolean("available"),
                        rs.getBoolean("drone"), rs.getLong("cost")))
                .list();
    }

    public List<PlanOption> findPlanOptions(long shootDayId, String blockCode) {
        return jdbc.sql("""
                        SELECT *, equipment_ids::text AS equipment_json FROM plan_options
                        WHERE shoot_day_id = :id AND block_code = :code ORDER BY option_no
                        """)
                .param("id", shootDayId)
                .param("code", blockCode)
                .query((rs, n) -> new PlanOption(rs.getInt("option_no"), rs.getLong("location_id"),
                        json.longs(rs.getString("equipment_json")), rs.getDouble("equipment_fit"),
                        time(rs, "start_time"), time(rs, "end_time")))
                .list();
    }

    public List<WeatherHour> findWeather(long shootDayId) {
        return jdbc.sql("SELECT * FROM weather_forecasts WHERE shoot_day_id = :id ORDER BY location_id, hour")
                .param("id", shootDayId)
                .query((rs, n) -> new WeatherHour(rs.getLong("location_id"), rs.getInt("hour"), rs.getDouble("precip_mm")))
                .list();
    }

    /** 그 날짜에 발령된 재난 문자다. 다른 날 문자가 이 촬영일 판정에 섞이지 않게 촬영일 날짜로 거른다. */
    public List<DisasterAlert> findAlerts(LocalDate date) {
        return jdbc.sql("SELECT * FROM disaster_alerts WHERE alert_date = :date ORDER BY id")
                .param("date", date)
                .query(PlanRepository::mapAlert)
                .list();
    }

    public DisasterAlert insertAlert(LocalDate date, String region, String kind, LocalTime startsAt, LocalTime endsAt,
                                     String message) {
        return jdbc.sql("""
                        INSERT INTO disaster_alerts (alert_date, region, kind, starts_at, ends_at, message)
                        VALUES (:date, :region, :kind, :startsAt, :endsAt, :message) RETURNING *
                        """)
                .param("date", date)
                .param("region", region)
                .param("kind", kind)
                .param("startsAt", startsAt)
                .param("endsAt", endsAt)
                .param("message", message)
                .query(PlanRepository::mapAlert)
                .single();
    }

    public void deleteAlerts() {
        jdbc.sql("DELETE FROM disaster_alerts").update();
    }

    public List<Long> findAlternativeLocationIds(long shootDayId) {
        return jdbc.sql("SELECT location_id FROM shoot_day_alternatives WHERE shoot_day_id = :id ORDER BY location_id")
                .param("id", shootDayId)
                .query(Long.class)
                .list();
    }

    /**
     * 카탈로그 장소를 촬영일의 4안 장소로 등록한다.
     * 엔진은 locations 표의 장소만 판정하므로 같은 규칙으로 검사받도록 장소, 날씨, 온톨로지에 함께 넣는다.
     */
    public void registerAlternative(long shootDayId, long locationId, ExternalLocation external, double fit,
                                    List<String> keywords) {
        jdbc.sql("""
                        INSERT INTO locations (id, name, address, indoor, region, open_from, open_to, permit_from, permit_to,
                                               cost, no_fly_zone, fit, distance_km, note)
                        VALUES (:id, :name, :region, :indoor, :region, :openFrom, :openTo, :permitFrom, :permitTo,
                                :cost, false, :fit, :distance, '아워플레이스 대체 장소, 예약은 담당자 확정 필요')
                        ON CONFLICT (id) DO UPDATE SET fit = EXCLUDED.fit
                        """)
                .param("id", locationId)
                .param("name", external.name())
                .param("region", external.region())
                .param("indoor", external.indoor())
                .param("openFrom", ALTERNATIVE_OPEN_FROM)
                .param("openTo", ALTERNATIVE_OPEN_TO)
                // 대관 장소의 야외 공간은 대관 시간 안에서 촬영이 허용된다고 보고 허가 시간을 대관 시간과 같게 둔다.
                .param("permitFrom", external.indoor() ? null : ALTERNATIVE_OPEN_FROM)
                .param("permitTo", external.indoor() ? null : ALTERNATIVE_OPEN_TO)
                .param("cost", external.cost())
                .param("fit", fit)
                .param("distance", external.distanceKm())
                .update();
        // 대체 장소는 지점별 예보가 없으므로 같은 날 야외 장소 가운데 가장 많은 강수량을 그대로 써서 보수적으로 판정한다.
        jdbc.sql("""
                        INSERT INTO weather_forecasts (shoot_day_id, location_id, hour, precip_mm)
                        SELECT w.shoot_day_id, :locationId, w.hour, max(w.precip_mm)
                        FROM weather_forecasts w JOIN locations l ON l.id = w.location_id
                        WHERE w.shoot_day_id = :shootDayId AND NOT l.indoor AND l.id < :base
                        GROUP BY w.shoot_day_id, w.hour
                        ON CONFLICT DO NOTHING
                        """)
                .param("locationId", locationId)
                .param("shootDayId", shootDayId)
                .param("base", ALTERNATIVE_LOCATION_ID_BASE)
                .update();
        jdbc.sql("""
                        INSERT INTO shoot_day_alternatives (shoot_day_id, location_id, external_id, keywords)
                        VALUES (:shootDayId, :locationId, :externalId, CAST(:keywords AS jsonb))
                        ON CONFLICT DO NOTHING
                        """)
                .param("shootDayId", shootDayId)
                .param("locationId", locationId)
                .param("externalId", external.id())
                .param("keywords", json.write(keywords))
                .update();
        // 4안 노드는 촬영일마다 따로 둔다(PLAN:<촬영일>-4). 대체 장소 노드는 장소 ID가 같으면 촬영일끼리 함께 쓴다.
        String plan = "PLAN:" + shootDayId + "-4";
        jdbc.sql("""
                        INSERT INTO ontology_nodes (node_id, type, label, props)
                        VALUES (:plan, 'PLAN', '4안 (대체 장소)', CAST(:planProps AS jsonb)),
                               (:node, 'LOCATION', :name, CAST(:props AS jsonb))
                        ON CONFLICT DO NOTHING
                        """)
                .param("plan", plan)
                .param("planProps", json.write(java.util.Map.of("shootDayId", shootDayId, "optionNo", 4)))
                .param("node", "LOCATION:" + locationId)
                .param("name", external.name())
                .param("props", json.write(java.util.Map.of("source", "OURPLACE_MOCK", "region", external.region())))
                .update();
        jdbc.sql("""
                        INSERT INTO ontology_edges (src, relation, dst, created_by)
                        VALUES (:plan, '포함', :node, 'agent')
                        ON CONFLICT DO NOTHING
                        """)
                .param("plan", plan)
                .param("node", "LOCATION:" + locationId)
                .update();
        // 4안도 오후 블록의 후보로 이어 블록에서 영향을 볼 때 함께 나오게 한다. 블록 노드가 없는 촬영일이면 건너뛴다.
        jdbc.sql("""
                        INSERT INTO ontology_edges (src, relation, dst, created_by)
                        SELECT node_id, '후보', :plan, 'agent' FROM ontology_nodes WHERE node_id = :block
                        ON CONFLICT DO NOTHING
                        """)
                .param("plan", plan)
                .param("block", "BLOCK:" + shootDayId + "-PM")
                .update();
    }

    public List<ExternalLocation> findExternalLocations() {
        return jdbc.sql("SELECT *, keywords::text AS keyword_json FROM external_locations ORDER BY distance_km, id")
                .query((rs, n) -> new ExternalLocation(rs.getLong("id"), rs.getString("name"), rs.getBoolean("indoor"),
                        rs.getString("region"), rs.getDouble("distance_km"), rs.getLong("cost"),
                        json.strings(rs.getString("keyword_json"))))
                .list();
    }

    private static DisasterAlert mapAlert(ResultSet rs, int row) throws SQLException {
        return new DisasterAlert(rs.getLong("id"), rs.getObject("alert_date", LocalDate.class), rs.getString("region"),
                rs.getString("kind"), time(rs, "starts_at"), time(rs, "ends_at"), rs.getString("message"));
    }

    static LocalTime time(ResultSet rs, String column) throws SQLException {
        return rs.getObject(column, LocalTime.class);
    }

    private static Double nullableDouble(ResultSet rs, String column) throws SQLException {
        double value = rs.getDouble(column);
        return rs.wasNull() ? null : value;
    }
}
