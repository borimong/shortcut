package com.shortcut.engine;

import java.util.List;

/**
 * @param sceneOrder 판정에 쓴 블록 씬 시각표
 * @param sceneOrderChanged 지금 확정 순서와 씬 순서가 다르다
 */
public record CheckResult(List<Finding> violations, List<Finding> warnings, List<SceneSlot> sceneOrder,
                          boolean sceneOrderChanged) {

    public boolean feasible() {
        return violations.isEmpty();
    }
}
