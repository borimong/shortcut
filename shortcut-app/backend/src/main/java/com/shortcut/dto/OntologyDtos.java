package com.shortcut.dto;

import com.shortcut.domain.OntologyNode;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.List;

public final class OntologyDtos {

    private OntologyDtos() {
    }

    public record NodeDetail(OntologyNode node, List<Neighbor> neighbors) {
    }

    public record Neighbor(String relation, String direction, OntologyNode node) {
    }

    /**
     * Agent는 도구 결과를 4000자에서 자르므로 관계를 노드보다 먼저 둔다. 잘려도 먼 노드의 속성만 빠진다.
     */
    public record ImpactResponse(String root, List<EdgeRef> edges, List<OntologyNode> nodes) {
    }

    public record EdgeRef(String src, String relation, String dst) {
    }

    public record CreateEdgeRequest(@NotBlank @Size(max = 80) String src, @NotBlank @Size(max = 30) String relation,
                                    @NotBlank @Size(max = 80) String dst) {
    }
}
