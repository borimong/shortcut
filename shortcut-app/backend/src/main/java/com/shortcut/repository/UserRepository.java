package com.shortcut.repository;

import com.shortcut.domain.UserAccount;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class UserRepository {

    private final JdbcClient jdbc;

    public UserRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<UserAccount> findByUsername(String username) {
        return jdbc.sql("SELECT * FROM users WHERE username = :username")
                .param("username", username)
                .query(UserRepository::map)
                .optional();
    }

    public List<UserAccount> findAll() {
        return jdbc.sql("SELECT * FROM users ORDER BY id").query(UserRepository::map).list();
    }

    public List<UserAccount> findByRoles(List<String> roles) {
        if (roles.isEmpty()) {
            return List.of();
        }
        return jdbc.sql("SELECT * FROM users WHERE role IN (:roles) AND active ORDER BY id")
                .param("roles", roles)
                .query(UserRepository::map)
                .list();
    }

    public void insertIfAbsent(String username, String passwordHash, String name, String role,
                               String dept, String title, String phone) {
        jdbc.sql("""
                        INSERT INTO users (username, password_hash, name, role, dept, title, phone)
                        VALUES (:username, :hash, :name, :role, :dept, :title, :phone)
                        ON CONFLICT (username) DO NOTHING
                        """)
                .param("username", username)
                .param("hash", passwordHash)
                .param("name", name)
                .param("role", role)
                .param("dept", dept)
                .param("title", title)
                .param("phone", phone)
                .update();
    }

    public void setAdmin(long id, boolean admin) {
        jdbc.sql("UPDATE users SET is_admin = :admin WHERE id = :id").param("admin", admin).param("id", id).update();
    }

    /**
     * 탈퇴는 행을 지우지 않고 비활성으로만 바꾼다. 승인 기록과 알림이 사용자 행을 참조하기 때문이다.
     */
    public void deactivate(long id) {
        jdbc.sql("UPDATE users SET active = false, is_admin = false WHERE id = :id").param("id", id).update();
    }

    public Optional<UserAccount> findById(long id) {
        return jdbc.sql("SELECT * FROM users WHERE id = :id").param("id", id).query(UserRepository::map).optional();
    }

    public long countActiveAdmins() {
        return jdbc.sql("SELECT count(*) FROM users WHERE is_admin AND active").query(Long.class).single();
    }

    /**
     * 관리자가 한 명도 없을 때만 시드 관리자에게 권한을 준다. 관리자가 직접 해제한 권한을 재시작 때 되돌리지 않는다.
     */
    public void grantAdminsIfNone(List<String> usernames) {
        jdbc.sql("""
                        UPDATE users SET is_admin = true
                        WHERE username IN (:usernames) AND active
                          AND NOT EXISTS (SELECT 1 FROM users WHERE is_admin)
                        """)
                .param("usernames", usernames)
                .update();
    }

    public boolean exists(String username) {
        return jdbc.sql("SELECT count(*) FROM users WHERE username = :username")
                .param("username", username)
                .query(Long.class)
                .single() > 0;
    }

    private static UserAccount map(ResultSet rs, int row) throws SQLException {
        return new UserAccount(rs.getLong("id"), rs.getString("username"), rs.getString("password_hash"),
                rs.getString("name"), rs.getString("role"), rs.getString("dept"),
                rs.getString("title"), rs.getString("phone"), rs.getBoolean("is_admin"), rs.getBoolean("active"));
    }
}
