package com.shortcut.web;

import com.shortcut.dto.AdminDtos.AdminRequest;
import com.shortcut.dto.AdminDtos.ApproverRulesRequest;
import com.shortcut.dto.AdminDtos.ApproverRulesView;
import com.shortcut.dto.AdminDtos.MemberView;
import com.shortcut.dto.AdminDtos.RainCheckResult;
import com.shortcut.dto.AdminDtos.SettingsRequest;
import com.shortcut.dto.AdminDtos.SettingsView;
import com.shortcut.dto.AdminDtos.WeatherRefreshResult;
import com.shortcut.service.AdminService;
import com.shortcut.service.RainAlertService;
import com.shortcut.service.WeatherForecastService;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.context.annotation.Profile;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 관리자 페이지 API다. 모든 요청은 AdminService가 관리자 여부를 DB에서 확인한 뒤 처리한다.
 */
@RestController
@Profile("api")
@RequestMapping("/api/admin")
public class AdminController {

    private final AdminService admin;
    private final RainAlertService rainAlerts;
    private final WeatherForecastService forecasts;

    public AdminController(AdminService admin, RainAlertService rainAlerts, WeatherForecastService forecasts) {
        this.admin = admin;
        this.rainAlerts = rainAlerts;
        this.forecasts = forecasts;
    }

    @GetMapping("/settings")
    public SettingsView settings(@AuthenticationPrincipal Jwt jwt) {
        return admin.settings(jwt.getSubject());
    }

    @PutMapping("/settings")
    public SettingsView updateSettings(@AuthenticationPrincipal Jwt jwt, @Valid @RequestBody SettingsRequest request) {
        return admin.updateSettings(jwt.getSubject(), request);
    }

    @GetMapping("/approver-rules")
    public ApproverRulesView approverRules(@AuthenticationPrincipal Jwt jwt) {
        return admin.approverRules(jwt.getSubject());
    }

    @PutMapping("/approver-rules")
    public ApproverRulesView updateApproverRules(@AuthenticationPrincipal Jwt jwt,
                                                 @Valid @RequestBody ApproverRulesRequest request) {
        return admin.updateApproverRules(jwt.getSubject(), request.rules());
    }

    @GetMapping("/members")
    public List<MemberView> members(@AuthenticationPrincipal Jwt jwt) {
        return admin.members(jwt.getSubject());
    }

    @PutMapping("/members/{id}/admin")
    public MemberView setAdmin(@AuthenticationPrincipal Jwt jwt, @PathVariable long id,
                               @Valid @RequestBody AdminRequest request) {
        return admin.setAdmin(jwt.getSubject(), id, request.admin());
    }

    @DeleteMapping("/members/{id}")
    public MemberView withdraw(@AuthenticationPrincipal Jwt jwt, @PathVariable long id) {
        return admin.withdraw(jwt.getSubject(), id);
    }

    /** 다음 정기 확인(1분 간격)을 기다리지 않고 지금 우천 알림 조건을 확인한다. */
    @PostMapping("/rain-alerts/check")
    public RainCheckResult checkRain(@AuthenticationPrincipal Jwt jwt) {
        admin.requireAdmin(jwt.getSubject());
        return rainAlerts.checkNow();
    }

    /** 다음 정기 갱신(1시간 간격)을 기다리지 않고 지금 날씨 API 예보를 받는다. */
    @PostMapping("/weather/refresh")
    public WeatherRefreshResult refreshWeather(@AuthenticationPrincipal Jwt jwt) {
        admin.requireAdmin(jwt.getSubject());
        return forecasts.refreshNow();
    }
}
