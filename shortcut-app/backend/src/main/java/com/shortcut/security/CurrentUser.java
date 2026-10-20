package com.shortcut.security;

import org.springframework.security.oauth2.jwt.Jwt;

/**
 * 토큰 claim만으로 권한을 판단하려고 DB 조회 없이 만든다.
 */
public record CurrentUser(String username, String role, String name, String dept) {

    public static CurrentUser from(Jwt jwt) {
        return new CurrentUser(jwt.getSubject(), jwt.getClaimAsString("role"),
                jwt.getClaimAsString("name"), jwt.getClaimAsString("dept"));
    }
}
