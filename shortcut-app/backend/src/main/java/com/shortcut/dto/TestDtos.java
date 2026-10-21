package com.shortcut.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.time.LocalDate;
import java.time.LocalTime;

public final class TestDtos {

    private TestDtos() {
    }

    /** date를 비우면 시연 촬영일 날짜로 넣는다. */
    public record AlertRequest(@NotBlank String region, @NotBlank String kind, @NotNull LocalTime startsAt,
                               @NotNull LocalTime endsAt, String message, LocalDate date) {
    }
}
