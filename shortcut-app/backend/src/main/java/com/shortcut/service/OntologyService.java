package com.shortcut.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.shortcut.common.ApiException;
import com.shortcut.domain.OntologyEdge;
import com.shortcut.domain.OntologyNode;
import com.shortcut.dto.OntologyDtos.CreateEdgeRequest;
import com.shortcut.dto.OntologyDtos.EdgeRef;
import com.shortcut.dto.OntologyDtos.ImpactResponse;
import com.shortcut.dto.OntologyDtos.Neighbor;
import com.shortcut.dto.OntologyDtos.NodeDetail;
import com.shortcut.repository.OntologyRepository;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OntologyService {

    // 3단계를 넘으면 촬영일 전체가 다 걸려 나와 영향 범위로서 의미가 없어진다.
    private static final int MAX_DEPTH = 3;

    private final OntologyRepository ontology;

    public OntologyService(OntologyRepository ontology) {
        this.ontology = ontology;
    }

    @Transactional(readOnly = true)
    public NodeDetail node(String nodeId) {
        OntologyNode node = find(nodeId);
        List<OntologyEdge> edges = ontology.findEdgesTouching(List.of(nodeId));
        Set<String> otherIds = new LinkedHashSet<>();
        edges.forEach(e -> otherIds.add(e.src().equals(nodeId) ? e.dst() : e.src()));
        Map<String, OntologyNode> others = new LinkedHashMap<>();
        ontology.findNodes(otherIds).forEach(n -> others.put(n.nodeId(), n));
        List<Neighbor> neighbors = edges.stream()
                .map(e -> e.src().equals(nodeId)
                        ? new Neighbor(e.relation(), "OUT", others.get(e.dst()))
                        : new Neighbor(e.relation(), "IN", others.get(e.src())))
                .toList();
        return new NodeDetail(node, neighbors);
    }

    /**
     * 관계 방향과 상관없이 따라가야 "배우 A가 빠지면 어떤 씬이 영향받나"와 "이 씬에 누가 걸리나"를 함께 답할 수 있다.
     * 배우와 장비는 촬영일을 넘어 공유되므로, shootDayId를 주면 props의 shootDayId가 다른 노드(다른 촬영일의 블록, 씬, 안,
     * 예약)는 결과에 넣지도 더 따라가지도 않는다. 촬영일 표시가 없는 배우, 장소, 장비는 그대로 따라간다.
     */
    @Transactional(readOnly = true)
    public ImpactResponse impact(String nodeId, int depth, Long shootDayId) {
        if (depth < 1 || depth > MAX_DEPTH) {
            throw ApiException.badRequest("INVALID_DEPTH", "depth는 1에서 3 사이여야 합니다.");
        }
        // 찾은 순서(가까운 노드 먼저)를 지켜야 결과가 잘릴 때 변경 지점에서 먼 노드부터 빠진다.
        Map<String, OntologyNode> visited = new LinkedHashMap<>();
        visited.put(nodeId, find(nodeId));
        Set<String> otherDays = new HashSet<>();
        Map<Long, OntologyEdge> edges = new LinkedHashMap<>();
        Set<String> frontier = Set.of(nodeId);
        for (int level = 0; level < depth && !frontier.isEmpty(); level++) {
            List<OntologyEdge> touching = ontology.findEdgesTouching(frontier);
            Set<String> discovered = new LinkedHashSet<>();
            for (OntologyEdge edge : touching) {
                for (String end : List.of(edge.src(), edge.dst())) {
                    if (!visited.containsKey(end) && !otherDays.contains(end)) {
                        discovered.add(end);
                    }
                }
            }
            Map<String, OntologyNode> fetched = new HashMap<>();
            ontology.findNodes(discovered).forEach(n -> fetched.put(n.nodeId(), n));
            Set<String> next = new LinkedHashSet<>();
            for (String id : discovered) {
                OntologyNode node = fetched.get(id);
                if (node == null) {
                    continue;
                }
                if (isOtherDay(node, shootDayId)) {
                    otherDays.add(id);
                } else {
                    visited.put(id, node);
                    next.add(id);
                }
            }
            for (OntologyEdge edge : touching) {
                if (!otherDays.contains(edge.src()) && !otherDays.contains(edge.dst())) {
                    edges.putIfAbsent(edge.id(), edge);
                }
            }
            frontier = next;
        }
        List<EdgeRef> edgeRefs = edges.values().stream()
                .map(e -> new EdgeRef(e.src(), e.relation(), e.dst()))
                .toList();
        return new ImpactResponse(nodeId, edgeRefs, List.copyOf(visited.values()));
    }

    private static boolean isOtherDay(OntologyNode node, Long shootDayId) {
        JsonNode day = node.props().path("shootDayId");
        return shootDayId != null && !day.isMissingNode() && day.asLong() != shootDayId;
    }

    @Transactional
    public OntologyEdge addEdge(CreateEdgeRequest request, String createdBy) {
        find(request.src());
        find(request.dst());
        return ontology.insertEdge(request.src(), request.relation(), request.dst(), createdBy)
                .orElseThrow(() -> ApiException.conflict("EDGE_EXISTS", "이미 있는 관계입니다."));
    }

    private OntologyNode find(String nodeId) {
        return ontology.findNode(nodeId)
                .orElseThrow(() -> ApiException.notFound("NODE_NOT_FOUND", "노드가 없습니다: " + nodeId));
    }
}
