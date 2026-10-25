package com.shortcut.domain;

import java.util.List;

/**
 * 대본 씬 하나와 촬영 배정 여부다. 아직 배정하지 않은 씬을 언제 찍을 수 있는지(배정 가능성) 볼 때 쓴다.
 *
 * @param estMinutes 배정 전 예상 촬영 분. 비어 있으면 60분으로 본다
 * @param assignedShootDayIds 이 씬을 배정한 촬영일. 비어 있으면 미배정이다
 */
public record ScriptScene(String code, String heading, String intExt, String timeOfDay, Integer estMinutes,
                          List<SceneCharacter> characters, List<Long> assignedShootDayIds) {

    public boolean exterior() {
        return "EXT".equals(intExt);
    }

    public boolean night() {
        return "NIGHT".equals(timeOfDay);
    }
}
