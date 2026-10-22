package com.shortcut.domain;

import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * 제작사 역할이다. DB, JWT, API에는 이름(PRODUCER 등)을 문자열로 그대로 쓰고, 이름에 딸린 표시 이름, 부서,
 * 승인 담당 범위, 권한은 이 한 곳에서 읽는다.
 * 선언 순서가 부서 순서(제작부, 연출부, 기술부서)이고 승인 화면과 관리자 페이지가 이 순서로 보인다.
 */
public enum Role {

    PRODUCER("제작 PD", "PRODUCTION", "추가 비용"),
    PRODUCTION_MANAGER("제작실장", "PRODUCTION", "제작 일정, 현장 운영"),
    DIRECTOR("연출 PD (연출감독)", "DIRECTING", "전체 계획, 장소"),
    AD1("1조감독", "DIRECTING", "촬영 순서, 시간"),
    AD2("2조감독", "DIRECTING", "동선, 이동"),
    DOP("촬영감독", "TECH", "장비 변경"),
    SOUND("동시녹음팀장", "TECH", "장소 소음"),
    CREW("연출부원", "DIRECTING", "현장 확인");

    /** 콜시트를 바꿀 수 있는 역할이다. 제작 조직에서 제작 PD가 제작실장보다 위다. */
    public static final Set<String> CHANGERS = names(PRODUCER, DIRECTOR);
    /** 촬영판 연락처에 보이는 역할이다. 현장에서 바로 연락할 제작부와 연출부 책임자다. */
    public static final Set<String> CONTACTS = names(PRODUCER, PRODUCTION_MANAGER, DIRECTOR, AD1, AD2);
    /** 승인자로 지정할 수 있는 역할이다. 열람 전용 연출부원은 넣지 않는다. */
    public static final List<Role> APPROVER_CANDIDATES = Arrays.stream(values()).filter(r -> r != CREW).toList();

    private final String label;
    private final String dept;
    private final String scope;

    Role(String label, String dept, String scope) {
        this.label = label;
        this.dept = dept;
        this.scope = scope;
    }

    public String label() {
        return label;
    }

    public String dept() {
        return dept;
    }

    /** 승인 카드에 보이는 담당 범위다. 제작 PD는 금액을 붙여 쓴다(ApproverRule.scope). */
    public String scope() {
        return scope;
    }

    public static Optional<Role> find(String name) {
        return Arrays.stream(values()).filter(r -> r.name().equals(name)).findFirst();
    }

    /** 정렬용 순서다. 모르는 역할은 맨 뒤로 보낸다. */
    public static int order(String name) {
        return find(name).map(Enum::ordinal).orElse(values().length);
    }

    private static Set<String> names(Role... roles) {
        return Arrays.stream(roles).map(Enum::name).collect(Collectors.toUnmodifiableSet());
    }
}
