package com.shortcut.engine;

import java.text.NumberFormat;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * 현재 확정안과 후보안의 차이로 필수 승인자를 정한다.
 * 승인 화면과 Agent가 같은 순서를 보도록 규칙 순서대로 넣고 중복은 첫 위치만 남긴다.
 */
public final class ApproverRule {

    private ApproverRule() {
    }

    public static List<String> requiredApprovers(PlanSnapshot current, PlanSnapshot candidate) {
        Set<String> roles = new LinkedHashSet<>();
        roles.add("DIRECTOR");
        if (current.locationId() != candidate.locationId()) {
            roles.add("AD1");
            roles.add("SOUND");
        }
        if (!current.sameEquipment(candidate)) {
            roles.add("DOP");
        }
        if (!current.sameTime(candidate)) {
            roles.add("AD1");
            roles.add("AD2");
        }
        if (candidate.cost() - current.cost() > 0) {
            roles.add("PRODUCER");
        }
        return List.copyOf(roles);
    }

    public static String scope(String role, long extraCost) {
        return switch (role) {
            case "DIRECTOR" -> "전체 계획, 장소";
            case "AD1" -> "촬영 순서, 시간";
            case "AD2" -> "동선, 이동";
            case "SOUND" -> "장소 소음";
            case "DOP" -> "장비 변경";
            case "PRODUCER" -> "추가 비용 " + NumberFormat.getIntegerInstance(Locale.KOREA).format(extraCost) + "원";
            default -> "";
        };
    }
}
