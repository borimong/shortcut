package com.shortcut.domain;

public record UserAccount(
        long id,
        String username,
        String passwordHash,
        String name,
        String role,
        String dept,
        String title,
        String phone) {
}
