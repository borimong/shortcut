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

    public record ImpactResponse(String root, List<OntologyNode> nodes, List<EdgeRef> edges) {
    }

    public record EdgeRef(String src, String relation, String dst) {
    }

    public record CreateEdgeRequest(@NotBlank @Size(max = 80) String src, @NotBlank @Size(max = 30) String relation,
                                    @NotBlank @Size(max = 80) String dst) {
    }
}
