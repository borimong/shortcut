package com.shortcut.service;

import com.shortcut.domain.Actor;
import com.shortcut.domain.Block;
import com.shortcut.domain.DataOverride;
import com.shortcut.domain.Equipment;
import com.shortcut.domain.Location;
import com.shortcut.domain.Role;
import com.shortcut.domain.Scene;
import com.shortcut.dto.ResourceDtos.ActiveOverride;
import com.shortcut.dto.ResourceDtos.ResourceBoard;
import com.shortcut.dto.ResourceDtos.ResourceItem;
import com.shortcut.repository.OverrideRepository;
import com.shortcut.repository.PlanRepository;
import com.shortcut.security.CurrentUser;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ResourceService {

    private final PlanDataService planData;
    private final OverrideRepository overrides;

    public ResourceService(PlanDataService planData, OverrideRepository overrides) {
        this.planData = planData;
        this.overrides = overrides;
    }

    /**
     * 장비, 장소, 배우마다 지금 상태와 그 상태를 만든 기록, 확정된 오후 블록에서 쓰이는 곳을 묶는다.
     * 상태는 덮어쓰기를 얹은 촬영 데이터(PlanData)에서 읽으므로 엔진과 Agent가 보는 것과 같다.
     */
    @Transactional(readOnly = true)
    public ResourceBoard board(CurrentUser user, Long requestedShootDayId) {
        long shootDayId = PlanDataService.orDefault(requestedShootDayId);
        PlanData data = planData.load(shootDayId);
        List<DataOverride> active = overrides.find(shootDayId);
        Block pm = data.changingBlock();
        Set<Long> pmActors = data.scenesOf(PlanData.CHANGING_BLOCK).stream()
                .map(Scene::actorIds)
                .flatMap(List::stream)
                .collect(Collectors.toSet());

        List<ResourceItem> equipment = data.equipment().values().stream()
                .map(e -> equipmentItem(e, latest(active, "EQUIPMENT_UNAVAILABLE", e.id()), pm, shootDayId))
                .toList();
        // 4안 탐색으로 등록한 외부 장소는 패널에서 고치지 않는다.
        List<ResourceItem> locations = data.locations().values().stream()
                .filter(l -> l.id() < PlanRepository.ALTERNATIVE_LOCATION_ID_BASE)
                .map(l -> locationItem(l, latest(active, "LOCATION_UNAVAILABLE", l.id()), pm, shootDayId))
                .toList();
        List<ResourceItem> actors = data.actors().values().stream()
                .map(a -> actorItem(a, latest(active, "ACTOR_WINDOW", a.id()), pmActors, shootDayId))
                .toList();
        return new ResourceBoard(shootDayId, data.shootDay().shootDate(), data.shootDay().dataVersion(),
                Role.CHANGERS.contains(user.role()), equipment, locations, actors);
    }

    private static ResourceItem equipmentItem(Equipment e, Optional<DataOverride> o, Block pm, long shootDayId) {
        String status = o.map(found -> "REPAIR".equals(found.payload().path("status").asText()) ? "REPAIR" : "BROKEN")
                .orElse("OK");
        String usage = pm.equipmentIds().contains(e.id()) ? "오후 블록 사용 중" : null;
        return new ResourceItem(e.id(), e.name(), status, usage, null, null, o.map(x -> view(x, shootDayId)).orElse(null));
    }

    private static ResourceItem locationItem(Location l, Optional<DataOverride> o, Block pm, long shootDayId) {
        String usage = pm.locationId() != null && pm.locationId() == l.id() ? "오후 블록 촬영지" : null;
        return new ResourceItem(l.id(), l.name(), o.isPresent() ? "CANCELLED" : "OK", usage, null, null,
                o.map(x -> view(x, shootDayId)).orElse(null));
    }

    private static ResourceItem actorItem(Actor a, Optional<DataOverride> o, Set<Long> pmActors, long shootDayId) {
        // 불참은 가용 시작과 끝을 같은 시각으로 저장한다(EventService.ABSENT).
        String status = o.map(x -> a.availableFrom().equals(a.availableTo()) ? "ABSENT" : "LIMITED").orElse("OK");
        String usage = pmActors.contains(a.id()) ? "오후 블록 출연" : null;
        return new ResourceItem(a.id(), a.name(), status, usage, a.availableFrom(), a.availableTo(),
                o.map(x -> view(x, shootDayId)).orElse(null));
    }

    /** 같은 대상에 기록이 여러 개면 나중 것이 이긴다. PlanDataService도 순서대로 얹으므로 같은 결과다. */
    private static Optional<DataOverride> latest(List<DataOverride> active, String kind, long targetId) {
        return active.stream()
                .filter(o -> kind.equals(o.kind()) && o.targetId() != null && o.targetId() == targetId)
                .reduce((first, second) -> second);
    }

    private static ActiveOverride view(DataOverride o, long shootDayId) {
        return new ActiveOverride(o.id(), o.untilDate(), o.memo(), o.createdBy(), o.createdAt(), o.eventId(),
                o.shootDayId() != shootDayId);
    }
}
