package com.shortcut.domain;

/**
 * 씬이 요구하는 장비, 소품, 의상, 보조출연, 특수 요구다.
 *
 * @param kind EQUIPMENT, PROP, COSTUME, EXTRAS, SPECIAL
 * @param equipmentId kind가 EQUIPMENT일 때만 있다
 * @param level MUST(없으면 못 찍음) 또는 WANT(있으면 좋음)
 */
public record SceneRequirement(String kind, Long equipmentId, String label, int qty, String level) {

    public boolean must() {
        return "MUST".equals(level);
    }
}
