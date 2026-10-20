package com.shortcut.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * outbox 릴레이, 알림 전달, heartbeat는 api 프로세스에서만 돈다.
 * worker까지 돌리면 같은 outbox 행을 두 프로세스가 다투므로 프로필로 막는다.
 */
@Configuration
@Profile("api")
@EnableScheduling
public class SchedulingConfig {
}
