package com.shortcut.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyCollection;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.mock;

import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.shortcut.common.ApiException;
import com.shortcut.domain.OntologyEdge;
import com.shortcut.domain.OntologyNode;
import com.shortcut.dto.OntologyDtos.EdgeRef;
import com.shortcut.dto.OntologyDtos.ImpactResponse;
import com.shortcut.repository.OntologyRepository;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class OntologyServiceTest {

    // 시드의 오후 블록 둘레만 옮겼다. 씬 → 블록 → 촬영일, 블록 → 장소·장비·후보안.
    private static final List<OntologyEdge> EDGES = List.of(
            edge(1, "SCENE:S12", "출연", "ACTOR:1"),
            edge(2, "SCENE:S12", "촬영지", "LOCATION:1"),
            edge(3, "SHOOT_DAY:1", "포함", "BLOCK:1-PM"),
            edge(4, "SHOOT_DAY:1", "포함", "BLOCK:1-AM"),
            edge(5, "BLOCK:1-PM", "포함", "SCENE:S12"),
            edge(6, "BLOCK:1-PM", "포함", "SCENE:S13"),
            edge(7, "BLOCK:1-PM", "촬영지", "LOCATION:1"),
            edge(8, "BLOCK:1-PM", "사용", "EQUIPMENT:1"),
            edge(9, "BLOCK:1-PM", "후보", "PLAN:2"),
            edge(10, "PLAN:2", "사용", "EQUIPMENT:4"),
            edge(11, "BLOCK:1-AM", "촬영지", "LOCATION:4"));

    private final OntologyRepository repository = mock(OntologyRepository.class);
    private OntologyService ontology;

    @BeforeEach
    void setUp() {
        given(repository.findNode(anyString())).willAnswer(call -> Optional.of(node(call.getArgument(0))));
        given(repository.findEdgesTouching(anyCollection())).willAnswer(call -> {
            Collection<String> ids = call.getArgument(0);
            return EDGES.stream().filter(e -> ids.contains(e.src()) || ids.contains(e.dst())).toList();
        });
        // DB처럼 노드 ID 순서로 돌려줘도 서비스가 찾은 순서로 다시 세우는지 본다.
        given(repository.findNodes(anyCollection())).willAnswer(call -> {
            Collection<String> ids = call.getArgument(0);
            return ids.stream().sorted().map(OntologyServiceTest::node).toList();
        });
        ontology = new OntologyService(repository);
    }

    @Test
    void 씬에서_깊이_2면_블록을_거쳐_촬영일과_후보안까지_닿는다() {
        ImpactResponse impact = ontology.impact("SCENE:S12", 2);

        assertThat(ids(impact)).contains("BLOCK:1-PM", "SHOOT_DAY:1", "SCENE:S13", "EQUIPMENT:1", "PLAN:2")
                .doesNotContain("BLOCK:1-AM", "EQUIPMENT:4");
        assertThat(impact.edges()).contains(new EdgeRef("SHOOT_DAY:1", "포함", "BLOCK:1-PM"),
                new EdgeRef("BLOCK:1-PM", "후보", "PLAN:2"));
    }

    @Test
    void 깊이_1이면_바로_이웃한_블록까지만_나온다() {
        ImpactResponse impact = ontology.impact("SCENE:S12", 1);

        assertThat(ids(impact)).containsExactly("SCENE:S12", "ACTOR:1", "LOCATION:1", "BLOCK:1-PM");
    }

    @Test
    void 노드는_가까운_순서로_나와_잘려도_먼_노드부터_빠진다() {
        List<String> ids = ids(ontology.impact("SCENE:S12", 3));

        assertThat(ids.get(0)).isEqualTo("SCENE:S12");
        assertThat(ids.indexOf("BLOCK:1-PM")).isLessThan(ids.indexOf("SHOOT_DAY:1"));
        assertThat(ids.indexOf("SHOOT_DAY:1")).isLessThan(ids.indexOf("BLOCK:1-AM"));
        assertThat(ids).doesNotContain("LOCATION:4");
    }

    @Test
    void 깊이가_3을_넘으면_400이다() {
        assertThatThrownBy(() -> ontology.impact("SCENE:S12", 4))
                .isInstanceOf(ApiException.class)
                .extracting(e -> ((ApiException) e).code()).isEqualTo("INVALID_DEPTH");
    }

    private static List<String> ids(ImpactResponse impact) {
        return impact.nodes().stream().map(OntologyNode::nodeId).toList();
    }

    private static OntologyNode node(String id) {
        return new OntologyNode(id, id.substring(0, id.indexOf(':')), id, JsonNodeFactory.instance.objectNode());
    }

    private static OntologyEdge edge(long id, String src, String relation, String dst) {
        return new OntologyEdge(id, src, relation, dst, "seed", null);
    }
}
