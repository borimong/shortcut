package com.shortcut.config;

import com.shortcut.repository.ScheduleRepository;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

/**
 * 대본, 촬영 배정, 배우 날짜별 일정이 서로 맞는지 기동할 때 한 번 본다. 판정을 막지는 않고 경고로만 남긴다.
 * 대사 화자와 등장 배역, 캐스팅, 블록 씬 길이, 같은 날의 종일 불가와 가능 시간대가 대상이다.
 */
@Component
@Profile("api")
public class ScheduleIntegrityCheck implements CommandLineRunner {

    private static final Logger log = LoggerFactory.getLogger(ScheduleIntegrityCheck.class);

    private final ScheduleRepository schedules;

    public ScheduleIntegrityCheck(ScheduleRepository schedules) {
        this.schedules = schedules;
    }

    @Override
    public void run(String... args) {
        List<String> problems = schedules.findIntegrityProblems();
        if (problems.isEmpty()) {
            log.info("대본·일정 정합성 검사: 문제가 없습니다.");
        } else {
            log.warn("대본·일정 정합성 검사: 문제 {}개 {}", problems.size(), problems);
        }
    }
}
