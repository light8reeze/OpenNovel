from __future__ import annotations

from langgraph.graph import END, StateGraph
from pydantic import ValidationError

from app.config import load_settings
from app.graph.state import IntentGraphState, NarrativeGraphState
from app.prompts.intent_builder import build_intent_prompts
from app.prompts.narrative_builder import build_narrative_prompts
from app.schemas.common import Action, ActionType
from app.schemas.intent import IntentValidationRequest, IntentValidationResponse
from app.schemas.narrative import NarrativeRequest, NarrativeResponse
from app.services.fallback_renderer import render_opening, render_turn
from app.services.llm_client import LlmError, build_llm_client

SETTINGS = load_settings()
LLM_CLIENT = build_llm_client(SETTINGS)


def _heuristic_intent_response(request: IntentValidationRequest) -> IntentValidationResponse:
    normalized = request.player_input.strip().lower()
    action_type = ActionType.INVESTIGATE
    target = None
    confidence = 0.55
    flags: list[str] = ["heuristic_intent_fallback"]

    if any(token in normalized for token in ("창고", "warehouse")):
        action_type = ActionType.MOVE
        target = "warehouse"
        confidence = 0.92
    elif any(token in normalized for token in ("골목", "alley")):
        action_type = ActionType.MOVE
        target = "alley"
        confidence = 0.92
    elif any(token in normalized for token in ("여관", "tavern", "inn")):
        action_type = ActionType.MOVE
        target = "tavern"
        confidence = 0.92
    elif any(token in normalized for token in ("광장", "square")):
        action_type = ActionType.MOVE
        target = "village_square"
        confidence = 0.88
    elif any(token in normalized for token in ("아리아", "aria", "대화", "talk")):
        action_type = ActionType.TALK
        target = "aria"
        confidence = 0.94
    elif any(token in normalized for token in ("휴식", "rest")):
        action_type = ActionType.REST
        confidence = 0.86
    elif any(token in normalized for token in ("횃불", "torch")):
        action_type = ActionType.USE_ITEM
        target = "torch"
        confidence = 0.84
    elif any(token in normalized for token in ("도망", "flee")):
        action_type = ActionType.FLEE
        confidence = 0.83

    return IntentValidationResponse(
        action=Action(action_type=action_type, target=target, raw_input=request.player_input),
        confidence=confidence,
        validation_flags=flags,
        source="heuristic",
    )


def _build_intent_prompt(state: IntentGraphState) -> IntentGraphState:
    system_prompt, user_prompt = build_intent_prompts(state["request"])
    state["system_prompt"] = system_prompt
    state["user_prompt"] = user_prompt
    return state


def _generate_intent_candidate(state: IntentGraphState) -> IntentGraphState:
    try:
        result = LLM_CLIENT.generate_json(
            schema_name="intent_validation",
            schema_model=IntentValidationResponse,
            system_prompt=state["system_prompt"],
            user_prompt=state["user_prompt"],
        )
        state["raw_result"] = result.payload
        state["response"] = IntentValidationResponse.model_validate(
            {**result.payload, "source": result.provider}
        )
    except (LlmError, ValidationError) as error:
        state["error"] = str(error)
    return state


def _fallback_intent(state: IntentGraphState) -> IntentGraphState:
    if "response" not in state:
        response = _heuristic_intent_response(state["request"])
        if "error" in state:
            response.validation_flags.append(f"llm_error:{state['error']}")
        state["response"] = response
    return state


def _validate_action(state: IntentGraphState) -> IntentGraphState:
    request = state["request"]
    response = state["response"]

    if response.action.action_type not in request.allowed_actions:
        response.action.action_type = ActionType.INVESTIGATE
        response.action.target = None
        response.validation_flags.append("action_not_allowed")
        response.confidence = min(response.confidence, 0.25)

    if response.action.target and response.action.target not in request.scene_context.visible_targets:
        response.action.target = None
        response.validation_flags.append("target_not_visible")
        response.confidence = min(response.confidence, 0.25)

    state["response"] = response
    return state


def _build_narrative_prompt(state: NarrativeGraphState) -> NarrativeGraphState:
    system_prompt, user_prompt = build_narrative_prompts(state["kind"], state["request"])
    state["system_prompt"] = system_prompt
    state["user_prompt"] = user_prompt
    return state


def _generate_narrative_candidate(state: NarrativeGraphState) -> NarrativeGraphState:
    try:
        result = LLM_CLIENT.generate_json(
            schema_name=f"{state['kind']}_narrative",
            schema_model=NarrativeResponse,
            system_prompt=state["system_prompt"],
            user_prompt=state["user_prompt"],
        )
        state["raw_result"] = result.payload
        state["response"] = NarrativeResponse.model_validate(
            {
                **result.payload,
                "source": result.provider,
                "used_fallback": False,
            }
        )
    except (LlmError, ValidationError) as error:
        state["error"] = str(error)
    return state


def _fallback_narrative(state: NarrativeGraphState) -> NarrativeGraphState:
    if "response" not in state:
        request = state["request"]
        response = render_opening(request) if state["kind"] == "opening" else render_turn(request)
        if "error" in state:
            response.safety_flags.append(f"llm_error:{state['error']}")
        state["response"] = response
    return state


def _validate_narrative(state: NarrativeGraphState) -> NarrativeGraphState:
    request = state["request"]
    response = state["response"]
    response.choices = [choice for choice in response.choices if choice in request.allowed_choices][:4]
    if len(response.choices) < 2 or not response.narrative.strip():
        response = render_opening(request) if state["kind"] == "opening" else render_turn(request)
        response.safety_flags.append("invalid_narrative_output")
    state["response"] = response
    return state


def _compile_intent_graph():
    graph = StateGraph(IntentGraphState)
    graph.add_node("build_intent_prompt", _build_intent_prompt)
    graph.add_node("generate_intent_candidate", _generate_intent_candidate)
    graph.add_node("fallback_intent", _fallback_intent)
    graph.add_node("validate_action", _validate_action)
    graph.set_entry_point("build_intent_prompt")
    graph.add_edge("build_intent_prompt", "generate_intent_candidate")
    graph.add_edge("generate_intent_candidate", "fallback_intent")
    graph.add_edge("fallback_intent", "validate_action")
    graph.add_edge("validate_action", END)
    return graph.compile()


def _compile_narrative_graph():
    graph = StateGraph(NarrativeGraphState)
    graph.add_node("build_narrative_prompt", _build_narrative_prompt)
    graph.add_node("generate_narrative_candidate", _generate_narrative_candidate)
    graph.add_node("fallback_narrative", _fallback_narrative)
    graph.add_node("validate_narrative", _validate_narrative)
    graph.set_entry_point("build_narrative_prompt")
    graph.add_edge("build_narrative_prompt", "generate_narrative_candidate")
    graph.add_edge("generate_narrative_candidate", "fallback_narrative")
    graph.add_edge("fallback_narrative", "validate_narrative")
    graph.add_edge("validate_narrative", END)
    return graph.compile()


INTENT_GRAPH = _compile_intent_graph()
NARRATIVE_GRAPH = _compile_narrative_graph()


def validate_intent_workflow(request: IntentValidationRequest) -> IntentValidationResponse:
    result = INTENT_GRAPH.invoke({"request": request})
    return result["response"]


def narrative_workflow(kind: str, request: NarrativeRequest) -> NarrativeResponse:
    result = NARRATIVE_GRAPH.invoke({"kind": kind, "request": request})
    return result["response"]
