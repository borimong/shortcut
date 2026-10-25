package com.shortcut.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties("shortcut")
public record ShortcutProperties(Jwt jwt, String internalToken, Worker worker, Weather weather) {

    public record Jwt(String secret, Duration ttl) {
    }

    public record Worker(boolean failFirstAttempt) {
    }

    /**
     * @param openMeteoUrl 날씨 API 주소. 무료 API는 키가 없고, 상용 주소(customer-api)를 쓸 때만 apiKey를 .env로 넘긴다
     * @param fetchEnabled false면 날씨 API를 부르지 않는다. 인터넷이 없는 곳에서 띄울 때 끈다
     */
    public record Weather(String openMeteoUrl, String apiKey, boolean fetchEnabled) {
    }
}
