package com.shortcut.service;

import static org.assertj.core.api.Assertions.assertThat;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.shortcut.domain.*;
import com.shortcut.engine.*;
import java.nio.file.Path;
import java.time.LocalTime;
import java.util.*;
import org.junit.jupiter.api.Test;

/** Read the generated public fixture, rather than duplicating legacy seed values. */
class V3FixtureTest {
    private final V3PlanBoundary boundary = new V3PlanBoundary();
    private static LocalTime time(String value) { return LocalTime.parse(value); }
    private static LocalTime t(JsonNode n, String field) { return time(n.get(field).asText()); }
    private static List<Long> ids(JsonNode array) {
        var ids=new ArrayList<Long>(); array.forEach(n -> ids.add(n.asLong())); return ids;
    }
    private PlanInput input(String fixture) throws Exception {
        JsonNode data=new ObjectMapper().readTree(Path.of("../fixtures/v3/app_snapshot.json").toFile());
        Map<Long,Actor> actors=new LinkedHashMap<>();
        for (var n:data.get("actors")) {
            long id=n.get("id").asLong();
            actors.put(id,new Actor(id,n.get("name").asText(),t(n,"available_from"),t(n,"available_to"),n.get("weekly_hours_used").asDouble(),n.get("contract_doc_id").asText(),n.get("no_night").asBoolean(),n.get("max_daily_hours").asDouble(),n.get("manager_phone").asText()));
        }
        Map<Long,Location> locations=new LinkedHashMap<>();
        for (var n:data.get("locations")) {
            long id=n.get("id").asLong();
            var end=t(n,"open_to");
            if ((fixture.equals("noise") && id==2) || (fixture.equals("no_interiors") && Set.of(2L,4L,6L).contains(id))) end=time("12:00");
            locations.put(id,new Location(id,n.get("name").asText(),n.get("address").asText(),n.get("indoor").asBoolean(),n.get("region").asText(),t(n,"open_from"),end,t(n,"permit_from"),t(n,"permit_to"),n.get("cost").asLong(),false,n.get("fit").asDouble(),n.get("distance_km").asDouble(),n.get("note").asText()));
        }
        Map<Long,Equipment> equipment=new LinkedHashMap<>();
        for (var n:data.get("equipment")) {
            long id=n.get("id").asLong();
            equipment.put(id,new Equipment(id,n.get("name").asText(),n.get("available").asBoolean() && !(fixture.equals("camera_failure") && id==1),false,n.get("cost").asLong()));
        }
        List<PlanOption> options=new ArrayList<>();
        for(var n:data.get("plan_options")) options.add(new PlanOption(n.get("option_no").asInt(),n.get("location_id").asLong(),ids(n.get("equipment_ids")),n.get("equipment_fit").asDouble(),t(n,"start_time"),t(n,"end_time")));
        return new PlanInput(time("08:00"),time("11:00"),600000,28,
            new PlanSnapshot(2,List.of(1L,4L,7L,10L,12L),time("13:00"),time("17:00"),0),
            List.of(1L,2L,3L,4L,5L),Map.of(1L,120,2L,120,3L,120),actors,locations,equipment,options,Map.of(),List.of(),List.of());
    }
    private List<CandidateResult> feasible(String fixture,List<ExtraConstraint> extras) throws Exception {
        return new PlanEngine().evaluate(input(fixture),null,extras).candidates().stream()
            .filter(CandidateResult::feasible)
            .filter(c -> boundary.check(c.location().id(),c.equipment().stream().map(Equipment::id).toList(),c.start(),c.end()).isEmpty()).toList();
    }
    @Test void originalAndNoiseHaveExpectedPlaces() throws Exception {
        assertThat(feasible("baseline",List.of()).getFirst().location().id()).isEqualTo(2);
        assertThat(feasible("noise",List.of()).getFirst().location().id()).isEqualTo(4);
        var reject = new ExtraConstraint("EXCLUDE_LOCATION",4L,null,null,null,null,null,"소음","SOUND");
        assertThat(feasible("noise",List.of(reject)).getFirst().location().id()).isEqualTo(6);
    }
    @Test void cameraFailureAndRejectionUseActualCompatibleCamera() throws Exception {
        var failed=feasible("camera_failure",List.of()).getFirst();
        assertThat(failed.location().id()).isEqualTo(2);
        assertThat(failed.equipment().stream().map(Equipment::id)).contains(2L).doesNotContain(1L);
        var reject=new ExtraConstraint("EXCLUDE_EQUIPMENT",null,1L,null,null,null,null,"고장","DIRECTOR");
        var replaced=feasible("noise",List.of(reject)).getFirst();
        assertThat(replaced.location().id()).isEqualTo(4);
        assertThat(replaced.equipment().stream().map(Equipment::id)).contains(2L).doesNotContain(1L);
    }
    @Test void insufficientBudgetAndNoVenueHaveNoCandidate() throws Exception {
        var cap=new ExtraConstraint("MAX_EXTRA_COST",null,null,null,null,100000L,null,"10만원","PRODUCER");
        assertThat(feasible("noise",List.of(cap))).isEmpty();
        assertThat(feasible("no_interiors",List.of())).isEmpty();
    }
    @Test void boundaryRejectsUnpermittedVenueMissingGroupsAndTimeShift() {
        var gear=List.of(1L,4L,7L,10L,12L);
        assertThat(boundary.check(2,gear,time("13:00"),time("17:00"))).isEmpty();
        assertThat(boundary.check(8,gear,time("13:00"),time("17:00"))).isNotEmpty();
        assertThat(boundary.check(2,List.of(1L,4L,9L,10L,12L),time("13:00"),time("17:00"))).isNotEmpty();
        assertThat(boundary.check(2,gear,time("13:30"),time("17:30"))).isNotEmpty();
    }
}
