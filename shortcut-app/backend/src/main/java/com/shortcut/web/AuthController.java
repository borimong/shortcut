package com.shortcut.web;

import com.shortcut.dto.AuthDtos.LoginRequest;
import com.shortcut.dto.AuthDtos.LoginResponse;
import com.shortcut.dto.AuthDtos.UserView;
import com.shortcut.service.AuthService;
import jakarta.validation.Valid;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class AuthController {

    private final AuthService auth;

    public AuthController(AuthService auth) {
        this.auth = auth;
    }

    @PostMapping("/auth/login")
    public LoginResponse login(@Valid @RequestBody LoginRequest request) {
        return auth.login(request.username(), request.password());
    }

    @GetMapping("/me")
    public UserView me(@AuthenticationPrincipal Jwt jwt) {
        return auth.me(jwt.getSubject());
    }
}
