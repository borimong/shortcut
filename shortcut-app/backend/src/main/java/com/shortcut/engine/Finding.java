package com.shortcut.engine;

/**
 * 하드 제약 위반과 경고를 같은 모양으로 담는다.
 * Agent가 ruleRef로 규정 근거를 찾아가므로 코드와 근거 키를 함께 둔다.
 */
public record Finding(String code, String constraint, String message, String ruleRef) {
}
