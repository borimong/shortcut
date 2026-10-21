"""실제 실패의 재발 방지: 5개 장비 중 한 개 거절, 비용만 변경, 출처 연결."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.graph.rejection import explicit_budget, resolve_targets, RejectionTargetError
from app.graph.schemas import RejectionTargets
from app.graph.qa import build_qa_graph, valid_citations
from app.harness.model import ModelGateway
from app.harness.limits import new_counter
from tests.fakes import FakeModel, make_context, _hit


def candidate():
    return {"equipment": {"items": [{"id": 1, "name": "시네마 카메라 A세트"}, {"id": 4, "name": "LED 조명"}, {"id": 7, "name": "음향"}, {"id": 10, "name": "그립"}, {"id": 12, "name": "전원"}]}, "extraCost": 180000}


def test_explicit_camera_excludes_only_camera_not_all_five():
    ctx=SimpleNamespace(model=SimpleNamespace(structured=AsyncMock(side_effect=AssertionError("불필요한 모델 호출"))))
    result=asyncio.run(resolve_targets(ctx,["EQUIPMENT"],"카메라 A(EQUIPMENT:1) 고장이니 교체",candidate()))
    assert [c.equipment_id for c in result.constraints]==[1]
    assert [c.type for c in result.constraints]==["EXCLUDE_EQUIPMENT"]


@pytest.mark.parametrize("text,amount",[("추가 비용은 10만 원 이하",100000),("추가비 최대 129,000원",129000),("상한 1.5만원",15000)])
def test_budget_units_are_won_and_never_exclude_equipment(text,amount):
    assert explicit_budget(text)==amount
    result=asyncio.run(resolve_targets(None,["COST"],text,candidate()))
    assert len(result.constraints)==1
    assert result.constraints[0].type=="MAX_EXTRA_COST" and result.constraints[0].amount==amount


def test_extraction_outside_selected_issue_is_ignored_and_unknown_equipment_is_refused():
    model=SimpleNamespace(structured=AsyncMock(return_value=RejectionTargets(equipment_ids=[1,4,7,10,12],max_extra_cost=99999,summary="추출")))
    result=asyncio.run(resolve_targets(SimpleNamespace(model=model),["COST"],"더 싸게 해 주세요",candidate()))
    assert [c.type for c in result.constraints]==["MAX_EXTRA_COST"]
    model.structured.return_value=RejectionTargets(equipment_ids=[999],summary="알 수 없음")
    with pytest.raises(RejectionTargetError):
        asyncio.run(resolve_targets(SimpleNamespace(model=model),["EQUIPMENT"],"장비가 문제",candidate()))


class NoToolModel(FakeModel):
    async def chat(self,ctx,messages,tools=None):
        return AIMessage(content="끝")


def test_qa_preloads_verified_proposal_even_when_model_calls_no_tools():
    ctx,_,clients,_=make_context(model=NoToolModel())
    hit=_hit("WEATHER")
    clients["business"]._get_proposal=lambda args: {"id": args["proposal_id"],"evidence":[{"id":hit["chunk_id"],"docId":hit["doc_id"],"title":hit["title"],"text":hit["text"]}]}
    graph=build_qa_graph().compile(checkpointer=InMemorySaver())
    result=asyncio.run(graph.ainvoke({"task_id":1,"proposal_id":10,"question":"이번 변경의 근거는?","loop_counter":new_counter()},{"configurable":{"thread_id":"qa-preload"}},context=ctx))
    assert hit["chunk_id"] in result["evidence"]
    assert valid_citations(result["answer"],result["evidence"])


def test_qa_searches_when_model_skips_tools_and_rejects_invented_citations():
    ctx,_,clients,_=make_context(model=NoToolModel())
    graph=build_qa_graph().compile(checkpointer=InMemorySaver())
    result=asyncio.run(graph.ainvoke({"task_id":1,"question":"규정 근거는?","loop_counter":new_counter()},{"configurable":{"thread_id":"qa-fallback"}},context=ctx))
    assert result["evidence"]
    assert clients["rag"].calls
    assert not valid_citations("허위 [fake#1]",result["evidence"])


def test_structured_response_gets_validation_feedback_once_and_usage_is_counted():
    raw=AIMessage(content="",tool_calls=[{"name":"X","args":{"constraints":[1,2,3,4,5]},"id":"a"}])
    bound=SimpleNamespace(ainvoke=AsyncMock(side_effect=[{"raw":raw,"parsing_error":ValueError("maximum 3 items"),"parsed":None},{"raw":raw,"parsing_error":None,"parsed":"fixed"}]))
    model=SimpleNamespace(with_structured_output=lambda *args,**kwargs:bound)
    ctx=SimpleNamespace(counter=new_counter())
    from app.graph.schemas import RejectionPlan
    result=asyncio.run(ModelGateway(model,None).structured(ctx,[],RejectionPlan))
    assert result=="fixed" and ctx.counter["retries"]==1 and ctx.counter["llm_calls"]==2
    assert "maximum 3" in str(bound.ainvoke.call_args.args[0][-1].content)


def test_persistent_structure_error_has_a_bounded_repair():
    raw=AIMessage(content="")
    bound=SimpleNamespace(ainvoke=AsyncMock(return_value={"raw":raw,"parsing_error":ValueError("bad"),"parsed":None}))
    model=SimpleNamespace(with_structured_output=lambda *args,**kwargs:bound)
    ctx=SimpleNamespace(counter=new_counter())
    from app.graph.schemas import RejectionPlan
    with pytest.raises(ValueError,match="수정 1회"):
        asyncio.run(ModelGateway(model,None).structured(ctx,[],RejectionPlan))
    assert bound.ainvoke.await_count==2
