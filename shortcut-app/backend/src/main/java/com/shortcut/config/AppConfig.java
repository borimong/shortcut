package com.shortcut.config;

import com.fasterxml.jackson.datatype.jsr310.deser.LocalTimeDeserializer;
import com.fasterxml.jackson.datatype.jsr310.ser.LocalTimeSerializer;
import com.shortcut.engine.PlanEngine;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
public class AppConfig {

    private static final DateTimeFormatter HH_MM = DateTimeFormatter.ofPattern("HH:mm");

    // 엔진에 스프링 애너테이션을 붙이지 않으려고 여기서 빈으로 등록한다.
    @Bean
    PlanEngine planEngine() {
        return new PlanEngine();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    // 계약의 시간 형식이 "HH:mm"이라 Jackson 기본값인 초 단위 표기를 바꾼다.
    @Bean
    Jackson2ObjectMapperBuilderCustomizer hhmmTimeFormat() {
        return builder -> builder
                .serializerByType(LocalTime.class, new LocalTimeSerializer(HH_MM))
                .deserializerByType(LocalTime.class, new LocalTimeDeserializer(HH_MM));
    }
}
