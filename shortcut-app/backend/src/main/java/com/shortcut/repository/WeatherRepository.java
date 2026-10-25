package com.shortcut.repository;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/**
 * 날씨 API 예보(weather_forecasts의 LIVE 행)를 받을 대상과 저장이다. 시드 예보(SEED 행)는 건드리지 않는다.
 */
@Repository
public class WeatherRepository {

    /** 예보를 받을 촬영일과 장소다. 4안 장소는 그 장소를 등록한 촬영일에만 받는다. */
    public record Target(long shootDayId, LocalDate shootDate, long locationId, String locationName,
                         double latitude, double longitude) {
    }

    public record Key(long shootDayId, long locationId) {
    }

    private final JdbcClient jdbc;

    public WeatherRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    /** 촬영일이 from~to 사이이고 위경도가 있는 장소다. */
    public List<Target> targets(LocalDate from, LocalDate to) {
        return jdbc.sql("""
                        SELECT d.id AS shoot_day_id, d.shoot_date, l.id AS location_id, l.name, l.latitude, l.longitude
                        FROM shoot_days d
                        JOIN locations l ON l.latitude IS NOT NULL AND l.longitude IS NOT NULL
                         AND (l.id < :base OR EXISTS (SELECT 1 FROM shoot_day_alternatives a
                                                      WHERE a.shoot_day_id = d.id AND a.location_id = l.id))
                        WHERE d.shoot_date BETWEEN :from AND :to
                        ORDER BY l.id, d.shoot_date
                        """)
                .param("base", PlanRepository.ALTERNATIVE_LOCATION_ID_BASE)
                .param("from", from)
                .param("to", to)
                .query((rs, n) -> new Target(rs.getLong("shoot_day_id"), rs.getObject("shoot_date", LocalDate.class),
                        rs.getLong("location_id"), rs.getString("name"), rs.getDouble("latitude"),
                        rs.getDouble("longitude")))
                .list();
    }

    /** LIVE 예보가 한 시각이라도 있는 촬영일과 장소다. */
    public Set<Key> liveKeys() {
        Set<Key> keys = new HashSet<>();
        jdbc.sql("SELECT DISTINCT shoot_day_id, location_id FROM weather_forecasts WHERE source = 'LIVE'")
                .query((RowCallbackHandler) rs -> keys.add(new Key(rs.getLong("shoot_day_id"), rs.getLong("location_id"))));
        return keys;
    }

    /** 받은 시각만 덮어쓴다. 받지 못한 시각의 행은 마지막으로 받은 값이 그대로 남는다. */
    public void saveLive(long shootDayId, long locationId, Map<Integer, Double> hourly, OffsetDateTime fetchedAt) {
        hourly.forEach((hour, mm) -> jdbc.sql("""
                        INSERT INTO weather_forecasts (shoot_day_id, location_id, hour, precip_mm, source, fetched_at)
                        VALUES (:shootDayId, :locationId, :hour, :mm, 'LIVE', :fetchedAt)
                        ON CONFLICT (shoot_day_id, location_id, hour, source)
                        DO UPDATE SET precip_mm = EXCLUDED.precip_mm, fetched_at = EXCLUDED.fetched_at
                        """)
                .param("shootDayId", shootDayId)
                .param("locationId", locationId)
                .param("hour", hour)
                .param("mm", mm)
                .param("fetchedAt", fetchedAt)
                .update());
    }
}
