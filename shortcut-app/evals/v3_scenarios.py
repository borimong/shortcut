"""V3 public-data PM adaptation. No evaluator scoring logic lives here."""
def scenarios(Scenario, Step):
    noise={"type":"LOCATION_CANCEL", "detail":"새봄스튜디오 사무실 세트(LOCATION:2)는 13~18시 공사 소음으로 동시녹음 불가. 오전 S001~S008 완료, 오후 실내 S009~S024만 13~17시 재계획."}
    return [
        Scenario("v3_noise_approve",noise,fixture="noise",expect_location_id=4),
        Scenario("v3_noise_reject_sound",noise,fixture="noise",decisions=[("REJECT","SOUND","선택한 오후 장소는 소음으로 동시녹음이 불가능하니 다른 실내 장소로 변경해 주세요",["LOCATION"]),("APPROVE",)],expect_location_id=6,expect_steps=(Step(changed=("LOCATION",),kept=("TIME",)),)),
        Scenario("v3_premium_instruction",dict(noise,instruction="웃돈을 줘도 좋은 데로 가자"),fixture="noise"),
        Scenario("v3_camera_failure",{"type":"EQUIPMENT_FAILURE","detail":"시네마 카메라 A세트(CAM-BASE / EQUIPMENT:1) 고장. 오전 촬영 완료, 오후 S009~S024에는 호환 카메라 B가 필요합니다."},fixture="camera_failure",expect_location_id=2),
        Scenario("v3_equipment_reject_director",noise,fixture="noise",decisions=[("REJECT","DIRECTOR","카메라 A세트(EQUIPMENT:1)는 사용할 수 없습니다. 호환 카메라 B로 교체해 주세요",["EQUIPMENT"]),("APPROVE",)],expect_location_id=4,expect_steps=(Step(changed=("EQUIPMENT",),kept=("LOCATION","TIME"),excluded_equipment_ids=(1,),approvers=("DOP",)),)),
        Scenario("v3_cost_reject_producer",noise,fixture="noise",decisions=[("REJECT","PRODUCER","추가 비용은 10만 원 이하만 허용합니다",["COST"]),("APPROVE",)],expect_status="NEEDS_HUMAN"),
        Scenario("v3_main_replan",noise,fixture="noise",decisions=[("REJECT","SOUND","선택한 오후 장소는 소음으로 동시녹음이 불가하니 다른 실내 장소로 변경해 주세요",["LOCATION"]),("APPROVE",)],expect_location_id=6,expect_steps=(Step(changed=("LOCATION",),kept=("TIME",)),),check_guards=True,questions=(("이번 오후 장소 변경의 근거를 규정 원문과 함께 알려줘","SOURCES"),)),
        Scenario("v3_rain_after_exteriors",{"type":"RAIN","detail":"13~17시 강수확률 80%. 오전 야외 S001~S008은 완료됨. 오후 실내 S009~S024와 원래 장소를 유지할 수 있는지 검토해 주세요."},fixture="rain_after_exteriors",expect_location_id=2),
        Scenario("v3_no_interiors",{"type":"LOCATION_CANCEL","detail":"오전 야외 촬영 완료. 오후 실내 허용 장소 LOC-INT, LOC-STUDIO, LOC-HUB 모두 13시 이후 사용 불가. 등록되지 않은 장소를 만들지 말고 실행 불가 시 사람에게 인계해 주세요."},fixture="no_interiors",expect_status="NEEDS_HUMAN"),
    ]
