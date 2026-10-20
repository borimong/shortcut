package com.shortcut.engine;

/**
 * 엔진 입력 자체가 잘못된 경우에 던진다.
 * 웹 계층은 이 예외를 400으로 바꾼다.
 */
public class PlanRuleException extends RuntimeException {

    private final String code;

    public PlanRuleException(String code, String message) {
        super(message);
        this.code = code;
    }

    public String code() {
        return code;
    }
}
