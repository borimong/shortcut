package com.shortcut.web.internal;

import com.shortcut.common.ApiException;
import java.util.Map;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

/** V3 public-fixture setup only. Existing internal-token security applies. */
@RestController
@Profile("v3 & api")
@RequestMapping("/internal/test/v3")
public class V3TestController {
    private final JdbcClient jdbc;
    public V3TestController(JdbcClient jdbc) { this.jdbc = jdbc; }

    @GetMapping("/info")
    public Map<String, Object> info() {
        return Map.of("dataset", "V3", "scope", "PM_ADAPTER_NOT_FULL_V3_EVALUATION",
                "date", "2026-10-23", "scenes", jdbc.sql("SELECT count(*) FROM scenes").query(Long.class).single());
    }

    @PostMapping("/case")
    @Transactional
    public Map<String, String> prepare(@RequestBody Map<String, String> body) {
        String name = body.getOrDefault("name", "baseline");
        if (!java.util.Set.of("baseline", "noise", "camera_failure", "no_interiors", "rain_after_exteriors").contains(name)) {
            throw ApiException.badRequest("UNKNOWN_V3_CASE", "등록되지 않은 V3 시연 조건입니다.");
        }
        // Called after reset, before submitting a task. Restore ALL mutable injected fields.
        jdbc.sql("UPDATE actors a SET available_from=s.available_from, available_to=s.available_to, weekly_hours_used=s.weekly_hours_used FROM v3_actor_seed s WHERE a.id=s.id").update();
        jdbc.sql("UPDATE locations a SET open_from=s.open_from, open_to=s.open_to FROM v3_location_seed s WHERE a.id=s.id").update();
        jdbc.sql("UPDATE equipment a SET available=s.available FROM v3_equipment_seed s WHERE a.id=s.id").update();
        jdbc.sql("UPDATE weather_forecasts a SET precip_prob=s.precip_prob FROM v3_weather_seed s WHERE a.shoot_day_id=s.shoot_day_id AND a.location_id=s.location_id AND a.hour=s.hour").update();
        if (name.equals("noise")) jdbc.sql("UPDATE locations SET open_to='12:00' WHERE id=2").update();
        if (name.equals("camera_failure")) jdbc.sql("UPDATE equipment SET available=false WHERE id=1").update();
        if (name.equals("no_interiors")) jdbc.sql("UPDATE locations SET open_to='12:00' WHERE id IN (2,4,6)").update();
        if (name.equals("rain_after_exteriors")) jdbc.sql("UPDATE weather_forecasts SET precip_prob=80 WHERE hour>=13").update();
        jdbc.sql("UPDATE shoot_days SET data_version=data_version+1 WHERE id=1").update();
        return Map.of("case", name, "scope", "PM_ADAPTER_NOT_FULL_V3_EVALUATION");
    }
}
