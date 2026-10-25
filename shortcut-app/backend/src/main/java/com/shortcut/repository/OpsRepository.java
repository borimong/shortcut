package com.shortcut.repository;

import com.shortcut.common.JsonColumns;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Time;
import java.time.LocalTime;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/**
 * 실행팀이 쓰는 가상 외부 서비스(장소 예약, 장비 렌탈, 촬영 허가, 차량, 연락, 장부)의 행을 읽고 쓴다.
 * 판단(가용 여부, 수수료, 금액)은 OpsService가 하고, 여기서는 SQL만 다룬다.
 */
@Repository
public class OpsRepository {

    private static final String RESERVATION_COLUMNS =
            "id, shoot_day_id, location_id, start_time, end_time, status, provider, task_id, cost_krw, cancel_fee_krw";

    private final JdbcClient jdbc;
    private final JsonColumns json;

    public OpsRepository(JdbcClient jdbc, JsonColumns json) {
        this.jdbc = jdbc;
        this.json = json;
    }

    // ---------------------------------------------------------------- 장소 예약

    public record ReservationRow(String id, long shootDayId, long locationId, LocalTime start, LocalTime end,
                                 String status, String provider, Long taskId, long costKrw, long cancelFeeKrw) {
    }

    public List<ReservationRow> findReservations(long shootDayId) {
        return jdbc.sql("SELECT " + RESERVATION_COLUMNS + " FROM reservations WHERE shoot_day_id = :id ORDER BY created_at, id")
                .param("id", shootDayId)
                .query(OpsRepository::mapReservation)
                .list();
    }

    public Optional<ReservationRow> findReservation(String id) {
        return jdbc.sql("SELECT " + RESERVATION_COLUMNS + " FROM reservations WHERE id = :id")
                .param("id", id)
                .query(OpsRepository::mapReservation)
                .optional();
    }

    public String nextReservationId() {
        return "R-" + jdbc.sql("SELECT nextval('ops_reservation_seq')").query(Long.class).single();
    }

    public void insertReservation(ReservationRow r) {
        jdbc.sql("""
                        INSERT INTO reservations (id, shoot_day_id, location_id, start_time, end_time, status, provider,
                                                  task_id, cost_krw, cancel_fee_krw)
                        VALUES (:id, :shootDayId, :locationId, :start, :end, :status, :provider, :taskId, :cost, :fee)
                        """)
                .param("id", r.id())
                .param("shootDayId", r.shootDayId())
                .param("locationId", r.locationId())
                .param("start", r.start())
                .param("end", r.end())
                .param("status", r.status())
                .param("provider", r.provider())
                .param("taskId", r.taskId())
                .param("cost", r.costKrw())
                .param("fee", r.cancelFeeKrw())
                .update();
    }

    public void updateReservation(String id, String status, Long taskId, long costKrw, long cancelFeeKrw) {
        jdbc.sql("""
                        UPDATE reservations SET status = :status, task_id = COALESCE(:taskId, task_id),
                               cost_krw = :cost, cancel_fee_krw = :fee
                        WHERE id = :id
                        """)
                .param("id", id)
                .param("status", status)
                .param("taskId", taskId)
                .param("cost", costKrw)
                .param("fee", cancelFeeKrw)
                .update();
    }

    // ---------------------------------------------------------------- 장비 렌탈

    public record RentalRow(String id, long shootDayId, Long taskId, List<Long> equipmentIds, LocalTime start,
                            LocalTime end, String status, long totalKrw, LocalTime deliveryAt, long cancelFeeKrw) {
    }

    public List<RentalRow> findRentals(long shootDayId) {
        return jdbc.sql("SELECT *, equipment_ids::text AS equipment_json FROM rental_bookings WHERE shoot_day_id = :id ORDER BY created_at, id")
                .param("id", shootDayId)
                .query(this::mapRental)
                .list();
    }

    public Optional<RentalRow> findRental(String id) {
        return jdbc.sql("SELECT *, equipment_ids::text AS equipment_json FROM rental_bookings WHERE id = :id")
                .param("id", id)
                .query(this::mapRental)
                .optional();
    }

    public String nextRentalId() {
        return "RB-" + jdbc.sql("SELECT nextval('ops_rental_seq')").query(Long.class).single();
    }

    public void insertRental(RentalRow r) {
        jdbc.sql("""
                        INSERT INTO rental_bookings (id, shoot_day_id, task_id, equipment_ids, start_time, end_time, status,
                                                     total_krw, delivery_at, cancel_fee_krw)
                        VALUES (:id, :shootDayId, :taskId, CAST(:equipment AS jsonb), :start, :end, :status, :total,
                                :deliveryAt, :fee)
                        """)
                .param("id", r.id())
                .param("shootDayId", r.shootDayId())
                .param("taskId", r.taskId())
                .param("equipment", json.write(r.equipmentIds()))
                .param("start", r.start())
                .param("end", r.end())
                .param("status", r.status())
                .param("total", r.totalKrw())
                .param("deliveryAt", r.deliveryAt())
                .param("fee", r.cancelFeeKrw())
                .update();
    }

    public void updateRentalStatus(String id, String status, long cancelFeeKrw) {
        jdbc.sql("UPDATE rental_bookings SET status = :status, cancel_fee_krw = :fee WHERE id = :id")
                .param("id", id)
                .param("status", status)
                .param("fee", cancelFeeKrw)
                .update();
    }

    // ---------------------------------------------------------------- 촬영 허가

    public record PermitRow(String id, long shootDayId, Long taskId, long locationId, LocalTime start, LocalTime end,
                            String kind, String status, long feeKrw, List<String> conditions, String denialReason) {
    }

    public List<PermitRow> findPermits(long shootDayId) {
        return jdbc.sql("SELECT *, conditions::text AS conditions_json FROM permits WHERE shoot_day_id = :id ORDER BY created_at, id")
                .param("id", shootDayId)
                .query(this::mapPermit)
                .list();
    }

    public Optional<PermitRow> findPermit(String id) {
        return jdbc.sql("SELECT *, conditions::text AS conditions_json FROM permits WHERE id = :id")
                .param("id", id)
                .query(this::mapPermit)
                .optional();
    }

    public String nextPermitId() {
        return "PM-" + jdbc.sql("SELECT nextval('ops_permit_seq')").query(Long.class).single();
    }

    public void insertPermit(PermitRow p) {
        jdbc.sql("""
                        INSERT INTO permits (id, shoot_day_id, task_id, location_id, start_time, end_time, kind, status,
                                             fee_krw, conditions, denial_reason)
                        VALUES (:id, :shootDayId, :taskId, :locationId, :start, :end, :kind, :status, :fee,
                                CAST(:conditions AS jsonb), :denial)
                        """)
                .param("id", p.id())
                .param("shootDayId", p.shootDayId())
                .param("taskId", p.taskId())
                .param("locationId", p.locationId())
                .param("start", p.start())
                .param("end", p.end())
                .param("kind", p.kind())
                .param("status", p.status())
                .param("fee", p.feeKrw())
                .param("conditions", json.write(p.conditions()))
                .param("denial", p.denialReason())
                .update();
    }

    // ---------------------------------------------------------------- 이동 수단

    public record TransportRow(String id, long shootDayId, Long taskId, long destLocationId, String vehicle, int count,
                               int headcount, LocalTime departAt, String pickup, String status, long costKrw,
                               long cancelFeeKrw) {
    }

    public List<TransportRow> findTransports(long shootDayId) {
        return jdbc.sql("SELECT * FROM transport_bookings WHERE shoot_day_id = :id ORDER BY created_at, id")
                .param("id", shootDayId)
                .query(OpsRepository::mapTransport)
                .list();
    }

    public Optional<TransportRow> findTransport(String id) {
        return jdbc.sql("SELECT * FROM transport_bookings WHERE id = :id")
                .param("id", id)
                .query(OpsRepository::mapTransport)
                .optional();
    }

    public String nextTransportId() {
        return "TB-" + jdbc.sql("SELECT nextval('ops_transport_seq')").query(Long.class).single();
    }

    public void insertTransport(TransportRow t) {
        jdbc.sql("""
                        INSERT INTO transport_bookings (id, shoot_day_id, task_id, dest_location_id, vehicle, vehicle_count,
                                                        headcount, depart_at, pickup, status, cost_krw, cancel_fee_krw)
                        VALUES (:id, :shootDayId, :taskId, :dest, :vehicle, :count, :headcount, :departAt, :pickup,
                                :status, :cost, :fee)
                        """)
                .param("id", t.id())
                .param("shootDayId", t.shootDayId())
                .param("taskId", t.taskId())
                .param("dest", t.destLocationId())
                .param("vehicle", t.vehicle())
                .param("count", t.count())
                .param("headcount", t.headcount())
                .param("departAt", t.departAt())
                .param("pickup", t.pickup())
                .param("status", t.status())
                .param("cost", t.costKrw())
                .param("fee", t.cancelFeeKrw())
                .update();
    }

    public void updateTransportStatus(String id, String status, long cancelFeeKrw) {
        jdbc.sql("UPDATE transport_bookings SET status = :status, cancel_fee_krw = :fee WHERE id = :id")
                .param("id", id)
                .param("status", status)
                .param("fee", cancelFeeKrw)
                .update();
    }

    // ---------------------------------------------------------------- 연락

    public record MessageRow(long id, long shootDayId, Long taskId, String recipientId, String recipientName,
                             String role, String channel, String text, String status, String reply) {
    }

    public Optional<MessageRow> findMessage(Long taskId, String recipientId, String text) {
        return jdbc.sql("""
                        SELECT * FROM outreach_messages
                        WHERE task_id IS NOT DISTINCT FROM CAST(:taskId AS bigint) AND recipient_id = :recipientId AND text = :text
                        ORDER BY id LIMIT 1
                        """)
                .param("taskId", taskId)
                .param("recipientId", recipientId)
                .param("text", text)
                .query(OpsRepository::mapMessage)
                .optional();
    }

    public long insertMessage(MessageRow m) {
        return jdbc.sql("""
                        INSERT INTO outreach_messages (shoot_day_id, task_id, recipient_id, recipient_name, role, channel,
                                                       text, status, reply)
                        VALUES (:shootDayId, :taskId, :recipientId, :name, :role, :channel, :text, :status, :reply)
                        RETURNING id
                        """)
                .param("shootDayId", m.shootDayId())
                .param("taskId", m.taskId())
                .param("recipientId", m.recipientId())
                .param("name", m.recipientName())
                .param("role", m.role())
                .param("channel", m.channel())
                .param("text", m.text())
                .param("status", m.status())
                .param("reply", m.reply())
                .query(Long.class)
                .single();
    }

    public List<MessageRow> findMessagesByTask(long taskId) {
        return jdbc.sql("SELECT * FROM outreach_messages WHERE task_id = :id ORDER BY id")
                .param("id", taskId)
                .query(OpsRepository::mapMessage)
                .list();
    }

    public List<MessageRow> findMessagesByShootDay(long shootDayId) {
        return jdbc.sql("SELECT * FROM outreach_messages WHERE shoot_day_id = :id ORDER BY id")
                .param("id", shootDayId)
                .query(OpsRepository::mapMessage)
                .list();
    }

    public void updateMessageReply(long id, String status, String reply) {
        jdbc.sql("UPDATE outreach_messages SET status = :status, reply = :reply WHERE id = :id")
                .param("id", id)
                .param("status", status)
                .param("reply", reply)
                .update();
    }

    // ---------------------------------------------------------------- 장부

    public record LedgerRow(long id, long shootDayId, Long taskId, String account, String memo, long amountKrw,
                            String refType, String refId) {
    }

    /**
     * 같은 작업이 같은 대상, 같은 계정을 다시 기록하면 새 행을 만들지 않고 적요와 금액만 고친다.
     */
    public LedgerRow upsertLedger(LedgerRow e) {
        return jdbc.sql("""
                        INSERT INTO ledger_entries (shoot_day_id, task_id, account, memo, amount_krw, ref_type, ref_id)
                        VALUES (:shootDayId, :taskId, :account, :memo, :amount, :refType, :refId)
                        ON CONFLICT (task_id, ref_type, ref_id, account)
                        DO UPDATE SET memo = EXCLUDED.memo, amount_krw = EXCLUDED.amount_krw
                        RETURNING *
                        """)
                .param("shootDayId", e.shootDayId())
                .param("taskId", e.taskId())
                .param("account", e.account())
                .param("memo", e.memo())
                .param("amount", e.amountKrw())
                .param("refType", e.refType())
                .param("refId", e.refId())
                .query(OpsRepository::mapLedger)
                .single();
    }

    public List<LedgerRow> findLedger(long shootDayId) {
        return jdbc.sql("SELECT * FROM ledger_entries WHERE shoot_day_id = :id ORDER BY id")
                .param("id", shootDayId)
                .query(OpsRepository::mapLedger)
                .list();
    }

    // ---------------------------------------------------------------- 매핑

    private static ReservationRow mapReservation(ResultSet rs, int row) throws SQLException {
        return new ReservationRow(rs.getString("id"), rs.getLong("shoot_day_id"), rs.getLong("location_id"),
                time(rs, "start_time"), time(rs, "end_time"), rs.getString("status"), rs.getString("provider"),
                rs.getObject("task_id", Long.class), rs.getLong("cost_krw"), rs.getLong("cancel_fee_krw"));
    }

    private RentalRow mapRental(ResultSet rs, int row) throws SQLException {
        return new RentalRow(rs.getString("id"), rs.getLong("shoot_day_id"), rs.getObject("task_id", Long.class),
                json.longs(rs.getString("equipment_json")), time(rs, "start_time"), time(rs, "end_time"),
                rs.getString("status"), rs.getLong("total_krw"), time(rs, "delivery_at"), rs.getLong("cancel_fee_krw"));
    }

    private PermitRow mapPermit(ResultSet rs, int row) throws SQLException {
        return new PermitRow(rs.getString("id"), rs.getLong("shoot_day_id"), rs.getObject("task_id", Long.class),
                rs.getLong("location_id"), time(rs, "start_time"), time(rs, "end_time"), rs.getString("kind"),
                rs.getString("status"), rs.getLong("fee_krw"), json.strings(rs.getString("conditions_json")),
                rs.getString("denial_reason"));
    }

    private static TransportRow mapTransport(ResultSet rs, int row) throws SQLException {
        return new TransportRow(rs.getString("id"), rs.getLong("shoot_day_id"), rs.getObject("task_id", Long.class),
                rs.getLong("dest_location_id"), rs.getString("vehicle"), rs.getInt("vehicle_count"),
                rs.getInt("headcount"), time(rs, "depart_at"), rs.getString("pickup"), rs.getString("status"),
                rs.getLong("cost_krw"), rs.getLong("cancel_fee_krw"));
    }

    private static MessageRow mapMessage(ResultSet rs, int row) throws SQLException {
        return new MessageRow(rs.getLong("id"), rs.getLong("shoot_day_id"), rs.getObject("task_id", Long.class),
                rs.getString("recipient_id"), rs.getString("recipient_name"), rs.getString("role"),
                rs.getString("channel"), rs.getString("text"), rs.getString("status"), rs.getString("reply"));
    }

    private static LedgerRow mapLedger(ResultSet rs, int row) throws SQLException {
        return new LedgerRow(rs.getLong("id"), rs.getLong("shoot_day_id"), rs.getObject("task_id", Long.class),
                rs.getString("account"), rs.getString("memo"), rs.getLong("amount_krw"), rs.getString("ref_type"),
                rs.getString("ref_id"));
    }

    private static LocalTime time(ResultSet rs, String column) throws SQLException {
        Time value = rs.getTime(column);
        return value == null ? null : value.toLocalTime();
    }
}
