package com.shortcut.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.shortcut.security.InternalTokenFilter;
import com.shortcut.security.JwtService;
import jakarta.servlet.DispatcherType;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Map;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

/**
 * worker는 웹 서버가 없어 보안 체인을 만들 수 없으므로 서블릿 앱일 때만 올린다.
 */
@Configuration
@EnableWebSecurity
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
public class SecurityConfig {

    private final ShortcutProperties properties;
    private final ObjectMapper objectMapper;

    public SecurityConfig(ShortcutProperties properties, ObjectMapper objectMapper) {
        this.properties = properties;
        this.objectMapper = objectMapper;
    }

    /**
     * 내부 API는 서비스 간 호출이라 사용자 JWT 대신 공유 토큰만 본다.
     * 공개 체인보다 먼저 매칭되어야 JWT 검사를 타지 않는다.
     */
    @Bean
    @Order(1)
    SecurityFilterChain internalChain(HttpSecurity http) throws Exception {
        return http.securityMatcher("/internal/**")
                .csrf(csrf -> csrf.disable())
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .addFilterBefore(new InternalTokenFilter(properties.internalToken()), AuthorizationFilter.class)
                .authorizeHttpRequests(auth -> auth.anyRequest().hasRole("INTERNAL"))
                .exceptionHandling(e -> e.authenticationEntryPoint((request, response, ex) ->
                        writeError(response, HttpServletResponse.SC_UNAUTHORIZED, "INVALID_INTERNAL_TOKEN", "내부 토큰이 없거나 틀립니다.")))
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain publicChain(HttpSecurity http) throws Exception {
        return http
                .csrf(csrf -> csrf.disable())
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        // SSE 응답의 비동기 재진입과 오류 페이지는 이미 인가를 통과한 요청이라 다시 막지 않는다.
                        .dispatcherTypeMatchers(DispatcherType.ASYNC, DispatcherType.ERROR).permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/auth/login").permitAll()
                        .requestMatchers("/actuator/health", "/actuator/health/**").permitAll()
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth -> oauth
                        .bearerTokenResolver(bearerTokenResolver())
                        .jwt(jwt -> jwt.jwtAuthenticationConverter(roleConverter()))
                        .authenticationEntryPoint((request, response, ex) ->
                                writeError(response, HttpServletResponse.SC_UNAUTHORIZED, "UNAUTHORIZED", "로그인이 필요합니다.")))
                .exceptionHandling(e -> e
                        .authenticationEntryPoint((request, response, ex) ->
                                writeError(response, HttpServletResponse.SC_UNAUTHORIZED, "UNAUTHORIZED", "로그인이 필요합니다."))
                        .accessDeniedHandler((request, response, ex) ->
                                writeError(response, HttpServletResponse.SC_FORBIDDEN, "FORBIDDEN", "권한이 없습니다.")))
                .build();
    }

    @Bean
    JwtDecoder jwtDecoder() {
        return JwtService.decoder(properties.jwt().secret());
    }

    /**
     * EventSource는 헤더를 못 붙여 SSE 경로만 쿼리 토큰을 받는다.
     * 다른 경로까지 열면 토큰이 접근 로그와 브라우저 기록에 남기 쉬워 범위를 좁힌다.
     */
    private static BearerTokenResolver bearerTokenResolver() {
        DefaultBearerTokenResolver headerOnly = new DefaultBearerTokenResolver();
        DefaultBearerTokenResolver withQuery = new DefaultBearerTokenResolver();
        withQuery.setAllowUriQueryParameter(true);
        return request -> {
            String path = request.getRequestURI();
            boolean stream = "GET".equals(request.getMethod())
                    && (path.equals("/api/notifications/stream") || path.matches("/api/ai/tasks/[^/]+/stream"));
            return stream ? withQuery.resolve(request) : headerOnly.resolve(request);
        };
    }

    private static JwtAuthenticationConverter roleConverter() {
        JwtGrantedAuthoritiesConverter authorities = new JwtGrantedAuthoritiesConverter();
        authorities.setAuthoritiesClaimName("role");
        authorities.setAuthorityPrefix("ROLE_");
        JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(authorities);
        return converter;
    }

    private void writeError(HttpServletResponse response, int status, String code, String message) throws IOException {
        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding("UTF-8");
        objectMapper.writeValue(response.getOutputStream(), Map.of("code", code, "message", message));
    }
}
