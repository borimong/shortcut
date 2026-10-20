package com.shortcut.security;

import com.nimbusds.jose.jwk.source.ImmutableSecret;
import com.shortcut.config.ShortcutProperties;
import com.shortcut.domain.UserAccount;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.stereotype.Component;

@Component
public class JwtService {

    // HS256 키가 256비트보다 짧으면 무차별 대입에 약해 기동을 막는다.
    private static final int MIN_SECRET_BYTES = 32;

    private final JwtEncoder encoder;
    private final Duration ttl;

    public JwtService(ShortcutProperties properties) {
        this.encoder = new NimbusJwtEncoder(new ImmutableSecret<>(secretKey(properties.jwt().secret())));
        this.ttl = properties.jwt().ttl();
    }

    public String issue(UserAccount user) {
        Instant now = Instant.now();
        JwtClaimsSet claims = JwtClaimsSet.builder()
                .subject(user.username())
                .issuedAt(now)
                .expiresAt(now.plus(ttl))
                .claim("role", user.role())
                .claim("name", user.name())
                .claim("dept", user.dept())
                .build();
        JwsHeader header = JwsHeader.with(MacAlgorithm.HS256).build();
        return encoder.encode(JwtEncoderParameters.from(header, claims)).getTokenValue();
    }

    public static JwtDecoder decoder(String secret) {
        return NimbusJwtDecoder.withSecretKey(secretKey(secret)).macAlgorithm(MacAlgorithm.HS256).build();
    }

    static SecretKey secretKey(String secret) {
        byte[] bytes = secret == null ? new byte[0] : secret.getBytes(StandardCharsets.UTF_8);
        if (bytes.length < MIN_SECRET_BYTES) {
            throw new IllegalStateException("JWT_SECRET은 32바이트 이상이어야 합니다.");
        }
        return new SecretKeySpec(bytes, "HmacSHA256");
    }
}
