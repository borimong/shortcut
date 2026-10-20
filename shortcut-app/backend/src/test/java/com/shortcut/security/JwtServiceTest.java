package com.shortcut.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.shortcut.config.ShortcutProperties;
import com.shortcut.domain.UserAccount;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtException;

class JwtServiceTest {

    private static final String SECRET = "test-secret-that-is-at-least-32-bytes-long";
    private static final UserAccount AD1 = new UserAccount(4, "ad1", "hash", "윤하린", "AD1", "DIRECTING", "1조감독", null);

    @Test
    void 발급한_토큰을_같은_키로_검증하면_역할과_이름이_나온다() {
        String token = service(SECRET).issue(AD1);

        Jwt jwt = JwtService.decoder(SECRET).decode(token);

        assertThat(jwt.getSubject()).isEqualTo("ad1");
        assertThat(jwt.getClaimAsString("role")).isEqualTo("AD1");
        assertThat(jwt.getClaimAsString("name")).isEqualTo("윤하린");
        assertThat(jwt.getClaimAsString("dept")).isEqualTo("DIRECTING");
        assertThat(Duration.between(jwt.getIssuedAt(), jwt.getExpiresAt())).isEqualTo(Duration.ofHours(12));
        assertThat(jwt.getHeaders()).containsEntry("alg", "HS256");
    }

    @Test
    void 다른_키로_서명한_토큰은_거부한다() {
        String token = service("another-secret-that-is-also-32-bytes-long").issue(AD1);

        assertThatThrownBy(() -> JwtService.decoder(SECRET).decode(token)).isInstanceOf(JwtException.class);
    }

    @Test
    void 짧은_비밀키로는_만들지_않는다() {
        assertThatThrownBy(() -> service("too-short")).isInstanceOf(IllegalStateException.class);
    }

    private static JwtService service(String secret) {
        return new JwtService(new ShortcutProperties(new ShortcutProperties.Jwt(secret, Duration.ofHours(12)),
                "internal", new ShortcutProperties.Worker(false)));
    }
}
