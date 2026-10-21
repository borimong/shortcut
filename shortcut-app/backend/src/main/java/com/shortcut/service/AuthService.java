package com.shortcut.service;

import com.shortcut.common.ApiException;
import com.shortcut.domain.UserAccount;
import com.shortcut.dto.AuthDtos.LoginResponse;
import com.shortcut.dto.AuthDtos.UserView;
import com.shortcut.repository.UserRepository;
import com.shortcut.security.JwtService;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
public class AuthService {

    private final UserRepository users;
    private final PasswordEncoder passwordEncoder;
    private final JwtService jwtService;

    public AuthService(UserRepository users, PasswordEncoder passwordEncoder, JwtService jwtService) {
        this.users = users;
        this.passwordEncoder = passwordEncoder;
        this.jwtService = jwtService;
    }

    /**
     * 아이디가 없을 때와 비밀번호가 틀릴 때 같은 응답을 줘 계정 존재 여부가 드러나지 않게 한다.
     */
    public LoginResponse login(String username, String password) {
        UserAccount user = users.findByUsername(username)
                .filter(u -> u.active() && passwordEncoder.matches(password, u.passwordHash()))
                .orElseThrow(() -> new ApiException(HttpStatus.UNAUTHORIZED, "INVALID_CREDENTIALS",
                        "아이디 또는 비밀번호가 올바르지 않습니다."));
        return new LoginResponse(jwtService.issue(user), UserView.of(user));
    }

    public UserView me(String username) {
        // 탈퇴한 계정은 남은 토큰으로도 쓰지 못하게 화면이 로그아웃하도록 401을 준다.
        return users.findByUsername(username)
                .filter(UserAccount::active)
                .map(UserView::of)
                .orElseThrow(() -> new ApiException(HttpStatus.UNAUTHORIZED, "USER_INACTIVE", "탈퇴했거나 없는 계정입니다."));
    }
}
