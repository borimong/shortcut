package com.shortcut.dto;

import com.shortcut.domain.AppSettings;
import com.shortcut.domain.UserAccount;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;

public final class AdminDtos {

    private AdminDtos() {
    }

    public record SettingsView(int maxLoops, double rainBlockMm, double rainWarnMm, int rainAlertLeadHours,
                               boolean mockVenueConflict, boolean mockPermitDenied,
                               String updatedBy, OffsetDateTime updatedAt) {

        public static SettingsView of(AppSettings s) {
            return new SettingsView(s.maxLoops(), s.rainBlockMm(), s.rainWarnMm(), s.rainAlertLeadHours(),
                    s.mockVenueConflict(), s.mockPermitDenied(), s.updatedBy(), s.updatedAt());
        }
    }

    public record SettingsRequest(
            @NotNull @Min(1) @Max(10) Integer maxLoops,
            @NotNull @DecimalMin("0.1") @DecimalMax("100") Double rainBlockMm,
            @NotNull @DecimalMin("0") @DecimalMax("100") Double rainWarnMm,
            @NotNull @Min(0) @Max(48) Integer rainAlertLeadHours,
            Boolean mockVenueConflict,
            Boolean mockPermitDenied) {
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
