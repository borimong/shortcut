package com.shortcut.engine;

import java.time.LocalTime;
import java.util.List;

/**
 * 한 블록의 장소, 장비, 시간대, 비용 묶음이다.
 * 현재 확정 콜시트와 후보안을 같은 모양으로 비교하려고 둔다.
 */
public record PlanSnapshot(long locationId, List<Long> equipmentIds, LocalTime start, LocalTime end, long cost) {

    public PlanSnapshot {
        equipmentIds = equipmentIds.stream().sorted().toList();
    }

    public boolean sameEquipment(PlanSnapshot other) {
        return equipmentIds.equals(other.equipmentIds);
    }

    public boolean sameTime(PlanSnapshot other) {
        return start.equals(other.start) && end.equals(other.end);
    }
}
