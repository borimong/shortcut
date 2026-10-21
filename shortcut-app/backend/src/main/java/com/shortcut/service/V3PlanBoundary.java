package com.shortcut.service;

import com.shortcut.engine.Finding;
import java.time.LocalTime;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

/** Prevent the PM projection from accepting resources/times outside its declared V3 subset. */
@Component
@Profile("v3")
public class V3PlanBoundary {
    public List<Finding> check(long locationId, List<Long> equipment, LocalTime start, LocalTime end) {
        List<Finding> findings = new ArrayList<>();
        if (!Set.of(2L,4L,6L).contains(locationId)) {
            findings.add(new Finding("V3_INTERIOR_SCOPE", "SCHEDULE", "오후 실내 씬의 허용 장소가 아닙니다.", "PLAN_RULES"));
        }
        if (!LocalTime.of(13,0).equals(start) || !LocalTime.of(17,0).equals(end)) {
            findings.add(new Finding("V3_FIXED_PM_WINDOW", "SCHEDULE", "이 어댑터는 점심 이후 13~17시의 240분을 유지합니다.", "PLAN_RULES"));
        }
        Set<Long> supplied = new HashSet<>(equipment);
        List<Set<Long>> groups=List.of(Set.of(1L,2L),Set.of(4L,5L),Set.of(7L,8L),Set.of(10L,11L),Set.of(12L,13L));
        if (equipment.size()!=5 || supplied.size()!=5 || groups.stream().anyMatch(g -> supplied.stream().filter(g::contains).count()!=1)) {
            findings.add(new Finding("V3_EQUIPMENT_GROUPS", "SCHEDULE", "호환되는 카메라·조명·3채널 음향·그립·전원 각 1개가 필요합니다.", "PLAN_RULES"));
        }
        return findings;
    }
}
