package com.shortcut.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.List;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * /internal/** 요청을 공유 토큰으로 인증한다.
 * 빈으로 등록하면 서블릿 필터로도 잡혀 모든 경로에 돌기 때문에 보안 체인 안에서만 생성한다.
 */
public class InternalTokenFilter extends OncePerRequestFilter {

    public static final String TOKEN_HEADER = "X-Internal-Token";
    public static final String ACTING_USER_HEADER = "X-Acting-User";
    private static final String DEFAULT_ACTOR = "agent";

    private final byte[] expected;

    public InternalTokenFilter(String internalToken) {
        if (internalToken == null || internalToken.isBlank()) {
            throw new IllegalStateException("INTERNAL_TOKEN이 비어 있습니다.");
        }
        this.expected = internalToken.getBytes(StandardCharsets.UTF_8);
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String given = request.getHeader(TOKEN_HEADER);
        // 문자열 비교는 앞 글자부터 일찍 끝나 응답 시간으로 토큰을 추측할 수 있어 고정 시간 비교를 쓴다.
        if (given != null && MessageDigest.isEqual(given.getBytes(StandardCharsets.UTF_8), expected)) {
            String actor = request.getHeader(ACTING_USER_HEADER);
            String principal = actor == null || actor.isBlank() ? DEFAULT_ACTOR : actor;
            SecurityContext context = SecurityContextHolder.createEmptyContext();
            context.setAuthentication(UsernamePasswordAuthenticationToken.authenticated(
                    principal, null, List.of(new SimpleGrantedAuthority("ROLE_INTERNAL"))));
            SecurityContextHolder.setContext(context);
        }
        chain.doFilter(request, response);
    }
}
