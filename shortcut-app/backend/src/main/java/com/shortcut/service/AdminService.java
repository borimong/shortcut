package com.shortcut.service;

import com.shortcut.common.ApiException;
import com.shortcut.domain.AppSettings;
import com.shortcut.domain.UserAccount;
import com.shortcut.dto.AdminDtos.ApproverRulesView;
import com.shortcut.dto.AdminDtos.MemberView;
import com.shortcut.dto.AdminDtos.RoleOption;
import com.shortcut.dto.AdminDtos.SettingsRequest;
import com.shortcut.dto.AdminDtos.SettingsView;
import com.shortcut.engine.ApproverRule;
import com.shortcut.repository.SettingsRepository;
import com.shortcut.repository.UserRepository;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 관리자 페이지의 운영 설정, 필수 승인자 규칙, 구성원 관리다.
 * 관리자 여부는 토큰이 아니라 매번 DB에서 확인한다. 관리자 권한을 바로 회수할 수 있어야 하기 때문이다.
 */
@Service
public class AdminService {

    // 승인자로 지정할 수 있는 역할이다. 열람 전용 연출부원은 넣지 않는다.
    private static final List<RoleOption> ROLES = List.of(
            new RoleOption("PRODUCER", "제작 PD"),
            new RoleOption("PRODUCTION_MANAGER", "제작실장"),
            new RoleOption("DIRECTOR", "연출 PD (연출감독)"),
            new RoleOption("AD1", "1조감독"),
            new RoleOption("AD2", "2조감독"),
            new RoleOption("DOP", "촬영감독"),
            new RoleOption("SOUND", "동시녹음팀장"));

    private final UserRepository users;
    private final SettingsRepository settings;

    public AdminService(UserRepository users, SettingsRepository settings) {
        this.users = users;
        this.settings = settings;
    }

    public UserAccount requireAdmin(String username) {
        return users.findByUsername(username)
                .filter(u -> u.active() && u.admin())
                .orElseThrow(() -> ApiException.forbidden("관리자만 쓸 수 있습니다."));
    }

    @Transactional(readOnly = true)
    public SettingsView settings(String username) {
        requireAdmin(username);
        return SettingsView.of(settings.settings());
    }

    @Transactional
    public SettingsView updateSettings(String username, SettingsRequest request) {
        requireAdmin(username);
        if (request.rainWarnMm() > request.rainBlockMm()) {
            throw ApiException.badRequest("INVALID_RAIN_RULE", "경고 강수량은 촬영 불가 강수량보다 클 수 없습니다.");
        }
        String weatherSource = request.weatherSource() == null
                ? settings.settings().weatherSource() : request.weatherSource();
        settings.updateSettings(new AppSettings(request.maxLoops(), request.rainBlockMm(), request.rainWarnMm(),
                request.rainAlertLeadHours(), weatherSource, null, null), username);
        return SettingsView.of(settings.settings());
    }

    @Transactional(readOnly = true)
    public ApproverRulesView approverRules(String username) {
        requireAdmin(username);
        return new ApproverRulesView(settings.approverRules(), ROLES);
    }

    /**
     * 모든 변경안에는 최소 한 명의 승인자가 있어야 하므로 항상(ALWAYS) 규칙은 비울 수 없다.
     */
    @Transactional
    public ApproverRulesView updateApproverRules(String username, Map<String, List<String>> requested) {
        requireAdmin(username);
        List<String> allowed = ROLES.stream().map(RoleOption::role).toList();
        Map<String, List<String>> rules = new LinkedHashMap<>();
        for (String kind : ApproverRule.CHANGE_KINDS) {
            List<String> roles = List.copyOf(new LinkedHashSet<>(requested.getOrDefault(kind, List.of())));
            roles.stream().filter(r -> !allowed.contains(r)).findFirst().ifPresent(r -> {
                throw ApiException.badRequest("UNKNOWN_ROLE", "지정할 수 없는 역할입니다: " + r);
            });
            rules.put(kind, roles);
        }
        if (rules.get("ALWAYS").isEmpty()) {
            throw ApiException.badRequest("ALWAYS_REQUIRED", "모든 변경안에 승인할 사람(항상)을 한 명 이상 골라야 합니다.");
        }
        settings.replaceApproverRules(rules);
        return new ApproverRulesView(settings.approverRules(), ROLES);
    }

    @Transactional(readOnly = true)
    public List<MemberView> members(String username) {
        requireAdmin(username);
        return users.findAll().stream().map(MemberView::of).toList();
    }

    @Transactional
    public MemberView setAdmin(String username, long id, boolean admin) {
        UserAccount me = requireAdmin(username);
        UserAccount target = users.findById(id).filter(UserAccount::active)
                .orElseThrow(() -> ApiException.notFound("USER_NOT_FOUND", "구성원이 없습니다: " + id));
        if (!admin && target.admin() && users.countActiveAdmins() <= 1) {
            throw ApiException.badRequest("LAST_ADMIN", "마지막 관리자의 권한은 해제할 수 없습니다.");
        }
        if (!admin && target.id() == me.id()) {
            throw ApiException.badRequest("SELF_ADMIN", "자기 자신의 관리자 권한은 해제할 수 없습니다.");
        }
        users.setAdmin(id, admin);
        return MemberView.of(users.findById(id).orElseThrow());
    }

    /**
     * 탈퇴는 계정을 비활성으로 바꾼다. 로그인, 연락처, 알림 대상에서 빠지고 승인 기록은 남는다.
     */
    @Transactional
    public MemberView withdraw(String username, long id) {
        UserAccount me = requireAdmin(username);
        UserAccount target = users.findById(id)
                .orElseThrow(() -> ApiException.notFound("USER_NOT_FOUND", "구성원이 없습니다: " + id));
        if (target.id() == me.id()) {
            throw ApiException.badRequest("SELF_WITHDRAW", "자기 자신은 탈퇴 처리할 수 없습니다.");
        }
        if (target.admin() && users.countActiveAdmins() <= 1) {
            throw ApiException.badRequest("LAST_ADMIN", "마지막 관리자는 탈퇴 처리할 수 없습니다.");
        }
        users.deactivate(id);
        return MemberView.of(users.findById(id).orElseThrow());
    }
}
