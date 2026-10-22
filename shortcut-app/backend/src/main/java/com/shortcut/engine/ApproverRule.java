package com.shortcut.engine;

import java.text.NumberFormat;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * 현재 확정안과 후보안의 차이로 필수 승인자를 정한다.
 * 승인 화면과 Agent가 같은 순서를 보도록 규칙 순서대로 넣고 중복은 첫 위치만 남긴다.
 */
public final class ApproverRule {

    /** 변경 종류와 확인 순서다. 관리자 페이지의 승인자 표도 이 순서로 보인다. */
    public static final List<String> CHANGE_KINDS = List.of("ALWAYS", "LOCATION", "EQUIPMENT", "TIME", "SCENE", "COST");

    /** 관리자가 규칙을 바꾸기 전의 기본값이다. data.sql의 approver_rules 시드와 같다. */
    public static final Map<String, List<String>> DEFAULT_RULES = defaultRules();

    // 같은 종류 안에서는 승인 화면에 부서 순서(제작부, 연출부, 기술부서)로 보이게 정렬한다.
    private static final List<String> ROLE_ORDER = List.of("PRODUCER", "PRODUCTION_MANAGER", "DIRECTOR", "AD1", "AD2",
            "DOP", "SOUND", "CREW");

    private ApproverRule() {
    }

    public static List<String> requiredApprovers(PlanSnapshot current, PlanSnapshot candidate) {
        return requiredApprovers(current, candidate, DEFAULT_RULES);
    }

    /**
     * 바뀐 요소에 해당하는 규칙의 역할을 모은다. 항상(ALWAYS) 규칙이 비어도 최소 한 명은 승인하게 연출감독을 넣는다.
     */
    public static List<String> requiredApprovers(PlanSnapshot current, PlanSnapshot candidate,
                                                 Map<String, List<String>> rules) {
        Set<String> roles = new LinkedHashSet<>();
        addSorted(roles, rules.get("ALWAYS"));
        if (current.locationId() != candidate.locationId()) {
            addSorted(roles, rules.get("LOCATION"));
        }
        if (!current.sameEquipment(candidate)) {
            addSorted(roles, rules.get("EQUIPMENT"));
        }
        if (!current.sameTime(candidate)) {
            addSorted(roles, rules.get("TIME"));
        }
        // 씬 순서가 바뀌면 배우 콜타임과 현장 동선이 바뀌므로 조감독들이 확인한다.
        if (!current.sameSceneOrder(candidate)) {
            addSorted(roles, rules.get("SCENE"));
        }
        if (candidate.cost() - current.cost() > 0) {
            addSorted(roles, rules.get("COST"));
        }
        if (roles.isEmpty()) {
            roles.add("DIRECTOR");
        }
        return List.copyOf(roles);
    }

    private static void addSorted(Set<String> roles, List<String> add) {
        if (add == null) {
            return;
        }
        add.stream()
                .sorted(Comparator.comparingInt(role -> ROLE_ORDER.indexOf(role) < 0 ? ROLE_ORDER.size() : ROLE_ORDER.indexOf(role)))
                .forEach(roles::add);
    }

    private static Map<String, List<String>> defaultRules() {
        Map<String, List<String>> rules = new LinkedHashMap<>();
        rules.put("ALWAYS", List.of("DIRECTOR"));
        rules.put("LOCATION", List.of("AD1", "SOUND"));
        rules.put("EQUIPMENT", List.of("DOP"));
        rules.put("TIME", List.of("AD1", "AD2"));
        rules.put("SCENE", List.of("AD1", "AD2"));
        rules.put("COST", List.of("PRODUCER"));
        return Collections.unmodifiableMap(rules);
    }

    public static String scope(String role, long extraCost) {
        return switch (role) {
            case "DIRECTOR" -> "전체 계획, 장소";
            case "AD1" -> "촬영 순서, 시간";
            case "AD2" -> "동선, 이동";
            case "SOUND" -> "장소 소음";
            case "DOP" -> "장비 변경";
            case "PRODUCER" -> "추가 비용 " + NumberFormat.getIntegerInstance(Locale.KOREA).format(extraCost) + "원";
            case "PRODUCTION_MANAGER" -> "제작 일정, 현장 운영";
            case "CREW" -> "현장 확인";
            default -> "";
        };
    }
}
