package com.shortcut.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.time.LocalTime;

public final class TestDtos {

    private TestDtos() {
    }

    public record AlertRequest(@NotBlank String region, @NotBlank String kind, @NotNull LocalTime startsAt,
                               @NotNull LocalTime endsAt, String message) {
    }
}
