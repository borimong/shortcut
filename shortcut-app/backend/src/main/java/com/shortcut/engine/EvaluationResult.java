package com.shortcut.engine;

import java.util.List;
import java.util.Map;

/**
 * 정규화한 가중치와 정렬된 전체 후보다.
 * 상위 몇 개를 자를지는 호출하는 쪽이 정한다.
 */
public record EvaluationResult(Map<String, Double> weights, List<CandidateResult> candidates) {
}
