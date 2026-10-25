package com.shortcut.repository;

import com.shortcut.domain.AppSettings;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/**
 * 관리자가 바꾸는 운영 설정과 필수 승인자 규칙을 읽고 쓴다.
 */
@Repository
public class SettingsRepository {

    private final JdbcClient jdbc;

    public SettingsRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public AppSettings settings() {
        return jdbc.sql("SELECT * FROM app_settings WHERE id = 1")
                .query(SettingsRepository::map)
                .optional()
                .orElse(AppSettings.DEFAULT);
    }

    public void updateSettings(AppSettings settings, String updatedBy) {
        jdbc.sql("""
                        INSERT INTO app_settings (id, max_loops, rain_block_mm, rain_warn_mm, rain_alert_lead_hours,
                                                  mock_venue_conflict, mock_permit_denied, updated_by, updated_at)
                        VALUES (1, :maxLoops, :blockMm, :warnMm, :leadHours, :venueConflict, :permitDenied, :by, now())
                        ON CONFLICT (id) DO UPDATE SET max_loops = EXCLUDED.max_loops, rain_block_mm = EXCLUDED.rain_block_mm,
                            rain_warn_mm = EXCLUDED.rain_warn_mm, rain_alert_lead_hours = EXCLUDED.rain_alert_lead_hours,
                            mock_venue_conflict = EXCLUDED.mock_venue_conflict,
                            mock_permit_denied = EXCLUDED.mock_permit_denied,
                            updated_by = EXCLUDED.updated_by, updated_at = now()
                        """)
                .param("maxLoops", settings.maxLoops())
                .param("blockMm", settings.rainBlockMm())
                .param("warnMm", settings.rainWarnMm())
                .param("leadHours", settings.rainAlertLeadHours())
                .param("venueConflict", settings.mockVenueConflict())
                .param("permitDenied", settings.mockPermitDenied())
                .param("by", updatedBy)
                .update();
    }

    /**
     * 변경 종류별 필수 승인자 역할이다. 키 순서는 ALWAYS, LOCATION, EQUIPMENT, TIME, COST로 고정한다.
     */
    public Map<String, List<String>> approverRules() {
        Map<String, List<String>> rules = new LinkedHashMap<>();
        for (String kind : List.of("ALWAYS", "LOCATION", "EQUIPMENT", "TIME", "COST")) {
            rules.put(kind, jdbc.sql("SELECT role FROM approver_rules WHERE change_kind = :kind ORDER BY role")
                    .param("kind", kind)
                    .query(String.class)
                    .list());
        }
        return rules;
    }

    public void replaceApproverRules(Map<String, List<String>> rules) {
        jdbc.sql("DELETE FROM approver_rules").update();
        rules.forEach((kind, roles) -> roles.forEach(role -> jdbc.sql(
                        "INSERT INTO approver_rules (change_kind, role) VALUES (:kind, :role) ON CONFLICT DO NOTHING")
                .param("kind", kind)
                .param("role", role)
                .update()));
    }

    private static AppSettings map(ResultSet rs, int row) throws SQLException {
        return new AppSettings(rs.getInt("max_loops"), rs.getDouble("rain_block_mm"), rs.getDouble("rain_warn_mm"),
                rs.getInt("rain_alert_lead_hours"), rs.getBoolean("mock_venue_conflict"),
                rs.getBoolean("mock_permit_denied"), rs.getString("updated_by"),
                rs.getObject("updated_at", OffsetDateTime.class));
    }
}
