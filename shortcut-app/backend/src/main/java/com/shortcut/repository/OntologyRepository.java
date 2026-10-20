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
