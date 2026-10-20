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
        return jdbc.sql("SELECT * FROM users WHERE role IN (:roles) ORDER BY id")
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

    public boolean exists(String username) {
        return jdbc.sql("SELECT count(*) FROM users WHERE username = :username")
                .param("username", username)
                .query(Long.class)
                .single() > 0;
    }

    private static UserAccount map(ResultSet rs, int row) throws SQLException {
        return new UserAccount(rs.getLong("id"), rs.getString("username"), rs.getString("password_hash"),
                rs.getString("name"), rs.getString("role"), rs.getString("dept"),
                rs.getString("title"), rs.getString("phone"));
    }
}
