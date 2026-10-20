package com.shortcut.dto;

import com.shortcut.domain.UserAccount;
import jakarta.validation.constraints.NotBlank;

public final class AuthDtos {

    private AuthDtos() {
    }

    public record LoginRequest(@NotBlank String username, @NotBlank String password) {
    }

    public record LoginResponse(String accessToken, UserView user) {
    }

    public record UserView(long id, String username, String name, String role, String dept, String title) {

        public static UserView of(UserAccount user) {
            return new UserView(user.id(), user.username(), user.name(), user.role(), user.dept(), user.title());
        }
    }
}
