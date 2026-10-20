package com.shortcut.engine;

import java.util.List;

public record CheckResult(List<Finding> violations, List<Finding> warnings) {

    public boolean feasible() {
        return violations.isEmpty();
    }
}
