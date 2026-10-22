package com.shortcut.engine;

import java.util.List;

/**
 * 엔진이 대본 규칙을 판정할 때 보는 씬 하나의 분해 값이다.
 * DB와 대본 파일을 모르는 상태로 테스트하려고 필요한 값만 담는다.
 *
 * @param exterior 대본상 실외(EXT) 장면이다
 * @param night 대본상 밤 장면이다
 * @param settingLocked 세트가 locationId에만 있어 다른 장소에서 찍을 수 없다
 * @param locationId 씬이 지정한 촬영 장소. 비어 있으면 블록 장소에서 찍는다
 * @param uncastCharacters 등장하지만 아직 배우가 정해지지 않은 배역 이름
 * @param mustEquipmentIds 대본상 없으면 찍을 수 없는 장비
 * @param wantEquipmentIds 있으면 좋은 장비
 */
public record ScenePlan(
        String code,
        int durationMin,
        boolean exterior,
        boolean night,
        boolean settingLocked,
        Long locationId,
        List<String> uncastCharacters,
        List<Long> mustEquipmentIds,
        List<Long> wantEquipmentIds) {
}
