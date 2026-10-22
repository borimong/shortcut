package com.shortcut.domain;

import java.time.OffsetDateTime;
import java.util.Map;
import java.util.Set;

/**
 * 촬영일 예보가 어디서 왔는지다. 화면이 시드 예보, 실시간 예보와 갱신 시각, 현장 입력을 구분해 보여 줄 때 쓴다.
 *
 * @param liveFetchedAt 장소별로 날씨 API 예보를 마지막으로 받은 시각이다. 실시간 예보를 쓰는데 시각이 없는 장소는 시드 예보를 대신 쓴다
 * @param manualLocations 변경 입력으로 강수량을 덮어쓴 장소다. 덮어쓴 시간대는 예보보다 입력값을 쓴다
 */
public record ForecastInfo(Map<Long, OffsetDateTime> liveFetchedAt, Set<Long> manualLocations) {

    public static final ForecastInfo NONE = new ForecastInfo(Map.of(), Set.of());
}
