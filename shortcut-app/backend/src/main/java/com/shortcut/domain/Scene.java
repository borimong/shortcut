package com.shortcut.domain;

import java.util.List;
import java.util.Objects;

/**
 * 촬영 배정된 씬 하나와 그 대본 분해 값이다. 출연 배우는 등장 배역의 캐스팅에서 나온다.
 *
 * @param intExt 대본상 실내(INT) 또는 실외(EXT)
 * @param timeOfDay 대본상 낮(DAY) 또는 밤(NIGHT)
 * @param settingLocked 세트가 locationId에만 있어 다른 장소에서 찍을 수 없다
 * @param locationId 씬이 지정한 촬영 장소. 비어 있으면 블록 장소에서 찍는다
 */
public record Scene(
        String code,
        String blockCode,
        String title,
        int durationMin,
        String heading,
        String intExt,
        String timeOfDay,
        String setting,
        boolean settingLocked,
        Long locationId,
        List<SceneCharacter> characters,
        List<SceneRequirement> requirements) {

    public boolean exterior() {
        return "EXT".equals(intExt);
    }

    public boolean night() {
        return "NIGHT".equals(timeOfDay);
    }

    /** 화면과 MCP 응답이 예전부터 쓰던 이름이다. 이제 대본의 실외 여부를 그대로 돌려준다. */
    public boolean outdoorIntent() {
        return exterior();
    }

    /** 출연 배우 id다. 아직 캐스팅하지 않은 배역은 빠진다. */
    public List<Long> actorIds() {
        return characters.stream().map(SceneCharacter::actorId).filter(Objects::nonNull).distinct().toList();
    }
}
