package com.shortcut.repository;

import static com.shortcut.repository.PlanRepository.time;

import com.fasterxml.jackson.databind.JsonNode;
import com.shortcut.common.JsonColumns;
import com.shortcut.domain.Approval;
import com.shortcut.domain.Proposal;
import com.shortcut.engine.PlanSnapshot;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class ProposalRepository {

    private static final String SELECT = """
            SELECT *, orig_equipment_ids::text AS orig_equipment_json, equipment_ids::text AS equipment_json,
                   source::text AS source_json, score_breakdown::text AS breakdown_json, weights::text AS weights_json,
                   checklist::text AS checklist_json, evidence::text AS evidence_json, unresolved::text AS unresolved_json,
                   review::text AS review_json
            FROM proposals
            """;

    private final JdbcClient jdbc;
    private final JsonColumns json;

    public ProposalRepository(JdbcClient jdbc, JsonColumns json) {
        this.jdbc = jdbc;
        this.json = json;
    }

    public long insert(NewProposal p) {
        return jdbc.sql("""
                        INSERT INTO proposals (task_id, event_id, shoot_day_id, loop_no, version_no, status, data_version,
                            orig_location_id, orig_equipment_ids, orig_start, orig_end, orig_cost,
                            location_id, equipment_ids, start_time, end_time, cost,
                            source, score, score_breakdown, weights, explanation, checklist, evidence, unresolved, review)
                        VALUES (:taskId, :eventId, :shootDayId, :loopNo, :versionNo, 'PENDING', :dataVersion,
                            :origLocation, CAST(:origEquipment AS jsonb), :origStart, :origEnd, :origCost,
                            :location, CAST(:equipment AS jsonb), :start, :end, :cost,
                            CAST(:source AS jsonb), :score, CAST(:breakdown AS jsonb), CAST(:weights AS jsonb), :explanation,
                            CAST(:checklist AS jsonb), CAST(:evidence AS jsonb), CAST(:unresolved AS jsonb), CAST(:review AS jsonb))
                        RETURNING id
                        """)
                .param("taskId", p.taskId())
                .param("eventId", p.eventId())
                .param("shootDayId", p.shootDayId())
                .param("loopNo", p.loopNo())
                .param("versionNo", p.versionNo())
                .param("dataVersion", p.dataVersion())
                .param("origLocation", p.original().locationId())
                .param("origEquipment", json.write(p.original().equipmentIds()))
                .param("origStart", p.original().start())
                .param("origEnd", p.original().end())
                .param("origCost", p.original().cost())
                .param("location", p.proposed().locationId())
                .param("equipment", json.write(p.proposed().equipmentIds()))
                .param("start", p.proposed().start())
                .param("end", p.proposed().end())
                .param("cost", p.proposed().cost())
                .param("source", json.write(p.source()))
                .param("score", p.score())
                .param("breakdown", json.write(p.scoreBreakdown()))
                .param("weights", json.write(p.weights()))
                .param("explanation", p.explanation())
                .param("checklist", json.write(p.checklist()))
                .param("evidence", json.write(p.evidence()))
                .param("unresolved", json.write(p.unresolved()))
                .param("review", json.write(p.review()))
                .query(Long.class)
                .single();
    }

    public record NewProposal(long taskId, Long eventId, long shootDayId, int loopNo, int versionNo, int dataVersion,
                              PlanSnapshot original, PlanSnapshot proposed, JsonNode source, double score,
                              JsonNode scoreBreakdown, JsonNode weights, String explanation, JsonNode checklist,
                              JsonNode evidence, JsonNode unresolved, JsonNode review) {
    }

    public Optional<Proposal> find(long id) {
        return jdbc.sql(SELECT + " WHERE id = :id").param("id", id).query(this::map).optional();
    }

    /**
     * 두 승인자가 동시에 마지막 승인을 눌러도 상태 전이가 한 번만 일어나도록 행을 잠근다.
     */
    public Optional<Proposal> findForUpdate(long id) {
        return jdbc.sql(SELECT + " WHERE id = :id FOR UPDATE").param("id", id).query(this::map).optional();
    }

    public List<Proposal> findByShootDay(long shootDayId) {
        return jdbc.sql(SELECT + " WHERE shoot_day_id = :id ORDER BY id DESC")
                .param("id", shootDayId)
                .query(this::map)
                .list();
    }

    public Optional<Proposal> findOpen(long shootDayId) {
        return jdbc.sql(SELECT + " WHERE shoot_day_id = :id AND status IN ('PENDING', 'APPROVED') ORDER BY id DESC LIMIT 1")
                .param("id", shootDayId)
                .query(this::map)
                .optional();
    }

    public void updateStatus(long id, String status) {
        jdbc.sql("UPDATE proposals SET status = :status, updated_at = now() WHERE id = :id")
                .param("id", id)
                .param("status", status)
                .update();
    }

    public void insertApproval(long proposalId, int seq, String role) {
        jdbc.sql("INSERT INTO approvals (proposal_id, seq, role, status) VALUES (:proposalId, :seq, :role, 'PENDING')")
                .param("proposalId", proposalId)
                .param("seq", seq)
                .param("role", role)
                .update();
    }

    public List<Approval> findApprovals(long proposalId) {
        return jdbc.sql("SELECT * FROM approvals WHERE proposal_id = :id ORDER BY seq")
                .param("id", proposalId)
                .query(this::mapApproval)
                .list();
    }

    public int decide(long proposalId, String role, String status, String userName, String reason, List<String> issues) {
        return jdbc.sql("""
                        UPDATE approvals SET status = :status, user_name = :userName, reason = :reason,
                               issues = CAST(:issues AS jsonb), decided_at = now()
                        WHERE proposal_id = :proposalId AND role = :role AND status = 'PENDING'
                        """)
                .param("proposalId", proposalId)
                .param("role", role)
                .param("status", status)
                .param("userName", userName)
                .param("reason", reason)
                .param("issues", json.write(issues))
                .update();
    }

    public void cancelPending(long proposalId) {
        jdbc.sql("UPDATE approvals SET status = 'CANCELLED' WHERE proposal_id = :id AND status = 'PENDING'")
                .param("id", proposalId)
                .update();
    }

    public List<DecidedApproval> findDecided(long shootDayId) {
        return jdbc.sql("""
                        SELECT a.*, p.version_no FROM approvals a JOIN proposals p ON p.id = a.proposal_id
                        WHERE p.shoot_day_id = :id AND a.status IN ('APPROVED', 'REJECTED')
                        ORDER BY a.decided_at
                        """)
                .param("id", shootDayId)
                .query((rs, n) -> new DecidedApproval(mapApproval(rs, n), rs.getInt("version_no")))
                .list();
    }

    public record DecidedApproval(Approval approval, int versionNo) {
    }

    private Proposal map(ResultSet rs, int row) throws SQLException {
        PlanSnapshot original = new PlanSnapshot(rs.getLong("orig_location_id"), json.longs(rs.getString("orig_equipment_json")),
                time(rs, "orig_start"), time(rs, "orig_end"), rs.getLong("orig_cost"));
        PlanSnapshot proposed = new PlanSnapshot(rs.getLong("location_id"), json.longs(rs.getString("equipment_json")),
                time(rs, "start_time"), time(rs, "end_time"), rs.getLong("cost"));
        return new Proposal(rs.getLong("id"), rs.getLong("task_id"), rs.getObject("event_id", Long.class),
                rs.getLong("shoot_day_id"), rs.getInt("loop_no"), rs.getInt("version_no"), rs.getString("status"),
                rs.getInt("data_version"), original, proposed, json.tree(rs.getString("source_json")),
                rs.getDouble("score"), json.tree(rs.getString("breakdown_json")), json.tree(rs.getString("weights_json")),
                rs.getString("explanation"), json.tree(rs.getString("checklist_json")),
                json.tree(rs.getString("evidence_json")), json.tree(rs.getString("unresolved_json")),
                json.tree(rs.getString("review_json")),
                rs.getObject("created_at", OffsetDateTime.class), rs.getObject("updated_at", OffsetDateTime.class));
    }

    private Approval mapApproval(ResultSet rs, int row) throws SQLException {
        return new Approval(rs.getLong("id"), rs.getLong("proposal_id"), rs.getInt("seq"), rs.getString("role"),
                rs.getString("status"), rs.getString("user_name"), rs.getString("reason"),
                json.strings(rs.getString("issues")), rs.getObject("decided_at", OffsetDateTime.class));
    }
}
