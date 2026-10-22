package com.shortcut.engine;

import java.time.LocalTime;
import java.util.List;

/**
 * 한 블록의 장소, 장비, 시간대, 비용, 씬 시각표 묶음이다.
 * 현재 확정 콜시트와 후보안을 같은 모양으로 비교하려고 둔다.
 * scenes가 비어 있으면 씬 순서를 모르는 옛 기록이다.
 */
public record PlanSnapshot(long locationId, List<Long> equipmentIds, LocalTime start, LocalTime end, long cost,
                           List<SceneSlot> scenes) {

    public PlanSnapshot {
        equipmentIds = equipmentIds.stream().sorted().toList();
        scenes = scenes == null ? List.of() : List.copyOf(scenes);
    }

    public PlanSnapshot(long locationId, List<Long> equipmentIds, LocalTime start, LocalTime end, long cost) {
        this(locationId, equipmentIds, start, end, cost, List.of());
    }

    public boolean sameEquipment(PlanSnapshot other) {
        return equipmentIds.equals(other.equipmentIds);
    }

    public boolean sameTime(PlanSnapshot other) {
        return start.equals(other.start) && end.equals(other.end);
    }

    /** 씬 순서가 같은지 본다. 한쪽이라도 순서를 모르면(옛 기록) 같다고 본다. */
    public boolean sameSceneOrder(PlanSnapshot other) {
        return scenes.isEmpty() || other.scenes.isEmpty()
                || SceneSlot.codes(scenes).equals(SceneSlot.codes(other.scenes));
    }
}
