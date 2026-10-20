package com.shortcut.domain;

import java.time.OffsetDateTime;

public record OntologyEdge(
        long id,
        String src,
        String relation,
        String dst,
        String createdBy,
        OffsetDateTime createdAt) {
}
