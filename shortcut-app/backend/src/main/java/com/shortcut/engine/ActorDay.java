package com.shortcut.engine;

import com.shortcut.domain.Actor;
import com.shortcut.domain.AvailabilityEntry;
import java.time.LocalTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 배우 한 명의 그날 일정이다. 날짜별 기본 일정(actor_availability)에 변경 입력을 얹은 결과다.
 *
 * @param off 종일 촬영할 수 없다
 * @param offReason 종일 불가 사유 종류(OTHER_PRODUCTION 등). 변경 입력의 불참이면 null이다
 * @param windows 그날 가능한 시간대. 여러 개일 수 있다
 * @param busy 가능한 시간대 안에서 빼야 하는 다른 일정
 */
public record ActorDay(long actorId, boolean off, String offReason, List<Window> windows, List<Busy> busy) {

    // 배우 일정 사유는 개인 사정을 옮기지 않으려고 종류만 보여 준다. OUR_SHOOT은 우리 촬영에 이미 배정된 시간이다.
    private static final Map<String, String> REASON_LABELS = Map.of(
            "OTHER_PRODUCTION", "타 작품", "PROMOTION", "광고·행사", "PERSONAL", "개인 일정", "TRAVEL", "이동·해외 일정",
            "OUR_SHOOT", "우리 촬영");

    public static String reasonLabel(String reasonKind) {
        return REASON_LABELS.getOrDefault(reasonKind, "다른 일정");
    }

    public record Window(LocalTime from, LocalTime to) {
    }

    /** 다른 일정이다. Agent와 화면에는 개인 사정 대신 사유 종류만 보인다. */
    public record Busy(LocalTime from, LocalTime to, String reasonKind) {
    }

    /** 날짜별 일정이 없을 때는 계약 기본 시간 하나를 쓴다. 변경 입력의 불참은 가용 시작과 끝이 같게 저장된다. */
    public static ActorDay of(Actor actor) {
        if (actor.availableFrom().equals(actor.availableTo())) {
            return new ActorDay(actor.id(), true, null, List.of(), List.of());
        }
        return new ActorDay(actor.id(), false, null, List.of(new Window(actor.availableFrom(), actor.availableTo())),
                List.of());
    }

    /**
     * 그날의 날짜별 기본 일정으로 하루를 만든다. OFF가 있으면 종일 불가, WINDOW가 있으면 그 창들이 가능 시간이고
     * 없으면 계약 기본 시간(actors.available_from~to)이다. BUSY는 가능 시간에서 뺄 다른 일정이다.
     */
    public static ActorDay of(Actor actor, List<AvailabilityEntry> entries) {
        AvailabilityEntry off = entries.stream().filter(e -> "OFF".equals(e.kind())).findFirst().orElse(null);
        if (off != null) {
            return new ActorDay(actor.id(), true, off.reasonKind(), List.of(), List.of());
        }
        List<Window> windows = new ArrayList<>();
        List<Busy> busy = new ArrayList<>();
        for (AvailabilityEntry e : entries) {
            if ("WINDOW".equals(e.kind())) {
                windows.add(new Window(e.start(), e.end()));
            } else if ("BUSY".equals(e.kind())) {
                busy.add(new Busy(e.start(), e.end(), e.reasonKind()));
            }
        }
        if (windows.isEmpty()) {
            windows.add(new Window(actor.availableFrom(), actor.availableTo()));
        }
        return new ActorDay(actor.id(), false, null, List.copyOf(windows), List.copyOf(busy));
    }

    /**
     * 변경 입력의 가용 시간 덮어쓰기다. 현장에서 들어온 최신 정보라 기본 일정의 종일 불가보다 앞서고,
     * 그날 가능 시간을 이 창 하나로 바꾸되 다른 일정은 남긴다. 시작과 끝이 같으면 불참이다.
     */
    public ActorDay withWindow(LocalTime from, LocalTime to) {
        if (from.equals(to)) {
            return new ActorDay(actorId, true, null, List.of(), List.of());
        }
        return new ActorDay(actorId, false, null, List.of(new Window(from, to)), busy);
    }

    /** 변경 입력으로 들어온 다른 일정을 더한다. */
    public ActorDay withBusy(Busy extra) {
        List<Busy> all = new ArrayList<>(busy);
        all.add(extra);
        return new ActorDay(actorId, off, offReason, windows, List.copyOf(all));
    }

    /** start~end 내내 현장에 있을 수 있는지 본다. 가능한 시간대 하나 안에 들고 다른 일정과 겹치지 않아야 한다. */
    public boolean covers(LocalTime start, LocalTime end) {
        return !off && windows.stream().anyMatch(w -> !start.isBefore(w.from()) && !end.isAfter(w.to()))
                && overlapping(start, end).isEmpty();
    }

    public List<Busy> overlapping(LocalTime start, LocalTime end) {
        return busy.stream().filter(b -> b.from().isBefore(end) && start.isBefore(b.to())).toList();
    }
}
