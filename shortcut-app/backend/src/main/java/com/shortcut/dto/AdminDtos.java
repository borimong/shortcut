package com.shortcut.dto;

import com.shortcut.domain.AppSettings;
import com.shortcut.domain.UserAccount;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;

public final class AdminDtos {

    private AdminDtos() {
    }

    public record SettingsView(int maxLoops, double rainBlockMm, double rainWarnMm, int rainAlertLeadHours,
                               String weatherSource, String updatedBy, OffsetDateTime updatedAt) {

        public static SettingsView of(AppSettings s) {
            return new SettingsView(s.maxLoops(), s.rainBlockMm(), s.rainWarnMm(), s.rainAlertLeadHours(),
                    s.weatherSource(), s.updatedBy(), s.updatedAt());
        }
    }

    /** weatherSource를 비워 보내면 지금 값을 그대로 둔다. 예보 선택이 생기기 전 화면이 보낸 요청도 받으려는 것이다. */
    public record SettingsRequest(
            @NotNull @Min(1) @Max(10) Integer maxLoops,
            @NotNull @DecimalMin("0.1") @DecimalMax("100") Double rainBlockMm,
            @NotNull @DecimalMin("0") @DecimalMax("100") Double rainWarnMm,
            @NotNull @Min(0) @Max(48) Integer rainAlertLeadHours,
            @Pattern(regexp = "SEED|LIVE") String weatherSource) {
    }

    /**
     * 날씨 API 예보를 한 번 받은 결과다.
     *
     * @param updated 예보를 받아 저장한 (촬영일, 장소) 수. 같은 장소도 촬영일마다 따로 센다
     * @param failed 받지 못한 장소 이름. 이 장소들은 마지막으로 받은 예보를 그대로 쓴다
     * @param dataVersionBumped 촬영 불가 기준을 넘나드는 변화가 있어 data_version을 올린 촬영일 수
     */
    public record WeatherRefreshResult(int updated, List<String> failed, int dataVersionBumped) {
    }

    /**
     * @param rules 변경 종류(ALWAYS, LOCATION, EQUIPMENT, TIME, COST)별 필수 승인 역할
     * @param roles 고를 수 있는 역할과 화면 이름
     */
    public record ApproverRulesView(Map<String, List<String>> rules, List<RoleOption> roles) {
    }

    public record RoleOption(String role, String title) {
    }

    public record ApproverRulesRequest(@NotNull Map<String, List<String>> rules) {
    }

    public record MemberView(long id, String username, String name, String role, String title, String phone,
                             boolean admin, boolean active) {

        public static MemberView of(UserAccount u) {
            return new MemberView(u.id(), u.username(), u.name(), u.role(), u.title(), u.phone(), u.admin(), u.active());
        }
    }

    public record AdminRequest(@NotNull Boolean admin) {
    }

    public record RainCheckResult(int sent, List<String> alerts) {
    }
}
