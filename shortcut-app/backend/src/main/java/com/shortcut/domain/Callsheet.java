package com.shortcut.domain;

import com.shortcut.engine.PlanSnapshot;
import java.time.OffsetDateTime;

/**
 * @param restoredFrom 앞 버전으로 되돌려 만든 버전이면 그 버전 번호다. 변경안으로 확정한 버전은 비어 있다
 * @param note 되돌린 사유
 */
public record Callsheet(
        long id,
        long shootDayId,
        int versionNo,
        Long proposalId,
        PlanSnapshot pm,
        OffsetDateTime createdAt,
        Integer restoredFrom,
        String note,
        String createdBy) {
}
