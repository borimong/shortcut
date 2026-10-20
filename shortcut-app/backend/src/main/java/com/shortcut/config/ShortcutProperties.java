package com.shortcut.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties("shortcut")
public record ShortcutProperties(Jwt jwt, String internalToken, Worker worker) {

    public record Jwt(String secret, Duration ttl) {
    }

    public record Worker(boolean failFirstAttempt) {
    }
}
