package com.shortcut.web.internal;

import com.shortcut.domain.OntologyEdge;
import com.shortcut.dto.OntologyDtos.CreateEdgeRequest;
import com.shortcut.dto.OntologyDtos.ImpactResponse;
import com.shortcut.dto.OntologyDtos.NodeDetail;
import com.shortcut.service.OntologyService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal/ontology")
public class InternalOntologyController {

    private final OntologyService ontology;

    public InternalOntologyController(OntologyService ontology) {
        this.ontology = ontology;
    }

    @GetMapping("/nodes/{nodeId}")
    public NodeDetail node(@PathVariable String nodeId) {
        return ontology.node(nodeId);
    }

    @GetMapping("/impact")
    public ImpactResponse impact(@RequestParam String nodeId, @RequestParam(defaultValue = "2") int depth) {
        return ontology.impact(nodeId, depth);
    }

    /**
     * 누가 관계를 추가했는지 남기려고 X-Acting-User(없으면 agent)를 created_by로 쓴다.
     */
    @PostMapping("/edges")
    @ResponseStatus(HttpStatus.CREATED)
    public OntologyEdge addEdge(Authentication caller, @Valid @RequestBody CreateEdgeRequest request) {
        return ontology.addEdge(request, caller.getName());
    }
}
