package com.shortcut.repository;

import com.shortcut.common.JsonColumns;
import com.shortcut.domain.OntologyEdge;
import com.shortcut.domain.OntologyNode;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class OntologyRepository {

    private final JdbcClient jdbc;
    private final JsonColumns json;

    public OntologyRepository(JdbcClient jdbc, JsonColumns json) {
        this.jdbc = jdbc;
        this.json = json;
    }

    public Optional<OntologyNode> findNode(String nodeId) {
        return jdbc.sql("SELECT *, props::text AS props_json FROM ontology_nodes WHERE node_id = :id")
                .param("id", nodeId)
                .query(this::mapNode)
                .optional();
    }

    public List<OntologyNode> findNodes(Collection<String> nodeIds) {
        if (nodeIds.isEmpty()) {
            return List.of();
        }
        return jdbc.sql("SELECT *, props::text AS props_json FROM ontology_nodes WHERE node_id IN (:ids) ORDER BY node_id")
                .param("ids", nodeIds)
                .query(this::mapNode)
                .list();
    }

    public List<OntologyEdge> findEdgesTouching(Collection<String> nodeIds) {
        if (nodeIds.isEmpty()) {
            return List.of();
        }
        return jdbc.sql("SELECT * FROM ontology_edges WHERE src IN (:ids) OR dst IN (:ids) ORDER BY id")
                .param("ids", nodeIds)
                .query(OntologyRepository::mapEdge)
                .list();
    }

    /**
     * 노드 ID 규칙(TYPE:업무 키)으로 업무 테이블에서 있어야 할 노드 ID를 만들어 보고, 맞는 행이 없는 노드를 돌려준다.
     * 촬영일에 딸린 행은 노드 props의 shootDayId도 같아야 한다. 영향 조회가 그 값으로 촬영일을 가르기 때문이다.
     * 매니저(STAFF)와 계약 제약(CONSTRAINT)은 업무 테이블이 없어 타입만 본다.
     */
    public List<String> findOrphanNodeIds() {
        return jdbc.sql("""
                        WITH business (node_id, shoot_day_id) AS (
                            SELECT 'SHOOT_DAY:' || id, id FROM shoot_days
                            UNION ALL SELECT 'BLOCK:' || shoot_day_id || '-' || code, shoot_day_id FROM blocks
                            UNION ALL SELECT 'SCENE:' || code, shoot_day_id FROM scenes
                            UNION ALL SELECT 'PLAN:' || shoot_day_id || '-' || option_no, shoot_day_id FROM plan_options
                            UNION ALL SELECT 'PLAN:' || shoot_day_id || '-4', shoot_day_id FROM shoot_day_alternatives
                            UNION ALL SELECT 'RESERVATION:' || id, shoot_day_id FROM reservations
                            UNION ALL SELECT 'ACTOR:' || id, NULL FROM actors
                            UNION ALL SELECT 'CONTRACT:' || contract_doc_id, NULL FROM actors
                            UNION ALL SELECT 'LOCATION:' || id, NULL FROM locations
                            UNION ALL SELECT 'EQUIPMENT:' || id, NULL FROM equipment
                            UNION ALL SELECT 'CHARACTER:' || id, NULL FROM characters
                        )
                        SELECT n.node_id FROM ontology_nodes n
                        WHERE split_part(n.node_id, ':', 1) <> n.type
                           OR (n.type NOT IN ('STAFF', 'CONSTRAINT')
                               AND NOT EXISTS (SELECT 1 FROM business b
                                               WHERE b.node_id = n.node_id
                                                 AND (b.shoot_day_id IS NULL
                                                      OR CAST(b.shoot_day_id AS text) = n.props ->> 'shootDayId')))
                        ORDER BY n.node_id
                        """)
                .query(String.class)
                .list();
    }

    /**
     * 이미 있는 관계면 비어 있는 값을 돌려 호출한 쪽이 409로 답하게 한다.
     */
    public Optional<OntologyEdge> insertEdge(String src, String relation, String dst, String createdBy) {
        return jdbc.sql("""
                        INSERT INTO ontology_edges (src, relation, dst, created_by)
                        VALUES (:src, :relation, :dst, :createdBy)
                        ON CONFLICT (src, relation, dst) DO NOTHING
                        RETURNING *
                        """)
                .param("src", src)
                .param("relation", relation)
                .param("dst", dst)
                .param("createdBy", createdBy)
                .query(OntologyRepository::mapEdge)
                .optional();
    }

    private OntologyNode mapNode(ResultSet rs, int row) throws SQLException {
        return new OntologyNode(rs.getString("node_id"), rs.getString("type"), rs.getString("label"),
                json.tree(rs.getString("props_json")));
    }

    private static OntologyEdge mapEdge(ResultSet rs, int row) throws SQLException {
        return new OntologyEdge(rs.getLong("id"), rs.getString("src"), rs.getString("relation"), rs.getString("dst"),
                rs.getString("created_by"), rs.getObject("created_at", OffsetDateTime.class));
    }
}
