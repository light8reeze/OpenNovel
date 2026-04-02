from __future__ import annotations

from pydantic import ValidationError

from app.config import RoleModelSettings
from app.prompts.world_builder import build_world_builder_prompts
from app.schemas.multi_agent import WorldBlueprint, WorldBuildRequest, WorldBuildResponse, WorldLocation, WorldNpc
from app.schemas.story_setup import StorySetup
from app.services.file_logger import log_llm_error
from app.services.llm_client import BaseLlmClient, LlmError


class WorldBuilderAgent:
    def __init__(self, settings: RoleModelSettings, llm_client: BaseLlmClient):
        self.settings = settings
        self.llm_client = llm_client

    def build(self, story_setup: StorySetup) -> WorldBuildResponse:
        request = WorldBuildRequest(story_setup=story_setup)
        system_prompt, user_prompt = build_world_builder_prompts(request)
        try:
            result = self.llm_client.generate_json(
                schema_name="world_blueprint",
                schema_model=WorldBlueprint,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            payload = self._repair_payload(result.payload, story_setup)
            blueprint = WorldBlueprint.model_validate(payload)
            return WorldBuildResponse(
                blueprint=self._normalize_blueprint(blueprint, story_setup),
                source=f"{result.provider}_llm",
                provider=result.provider,
                model=result.model,
                used_fallback=False,
                token_usage=result.token_usage,
            )
        except (LlmError, ValidationError) as error:
            log_llm_error(
                role="world_builder",
                provider=self.settings.provider,
                model=self.settings.model,
                stage="fallback",
                error=str(error),
                extra={"story_setup_id": story_setup.id},
            )
            return WorldBuildResponse(
                blueprint=self._fallback_blueprint(story_setup),
                source="world_builder_fallback",
                provider=self.settings.provider,
                model=self.settings.model,
                used_fallback=True,
            )

    def _repair_payload(self, payload: object, story_setup: StorySetup) -> object:
        if not isinstance(payload, dict):
            return payload
        required = {"id", "title", "world_summary", "tone", "core_conflict", "player_goal", "opening_hook"}
        if required.issubset(payload.keys()):
            return payload
        template = payload.get("blueprint_template")
        if isinstance(template, dict):
            repaired = dict(template)
            repaired["id"] = story_setup.id
            repaired["title"] = story_setup.title
            repaired["world_summary"] = story_setup.world_summary
            repaired["tone"] = story_setup.tone
            repaired["core_conflict"] = repaired.get("core_conflict") or story_setup.player_goal
            repaired["player_goal"] = story_setup.player_goal
            repaired["opening_hook"] = story_setup.opening_hook
            return repaired
        nested_setup = payload.get("story_setup")
        if isinstance(nested_setup, dict):
            fallback = self._fallback_blueprint(story_setup).model_dump(mode="json")
            fallback["core_conflict"] = nested_setup.get("player_goal") or story_setup.player_goal
            return fallback
        return payload

    def _normalize_blueprint(self, blueprint: WorldBlueprint, story_setup: StorySetup) -> WorldBlueprint:
        locations = self._normalize_locations(blueprint, story_setup)
        starting_location_id = self._normalize_starting_location(
            blueprint.starting_location_id,
            locations,
        )
        npcs = self._normalize_npcs(blueprint, locations, story_setup)
        return WorldBlueprint(
            id=blueprint.id.strip() or story_setup.id,
            title=blueprint.title.strip() or story_setup.title,
            world_summary=blueprint.world_summary.strip() or story_setup.world_summary,
            tone=blueprint.tone.strip() or story_setup.tone,
            core_conflict=blueprint.core_conflict.strip() or story_setup.player_goal,
            player_goal=blueprint.player_goal.strip() or story_setup.player_goal,
            opening_hook=blueprint.opening_hook.strip() or story_setup.opening_hook,
            starting_location_id=starting_location_id,
            locations=locations,
            npcs=npcs,
            notable_locations=[location.label for location in locations],
            important_npcs=[npc.label for npc in npcs],
            hidden_truths=[item.strip() for item in blueprint.hidden_truths if item.strip()][:5],
        )

    def _fallback_blueprint(self, story_setup: StorySetup) -> WorldBlueprint:
        location_labels, npc_label = self._fallback_seed(story_setup)
        locations = self._build_linear_locations(location_labels)
        npcs = [
            WorldNpc(
                id=self._slugify_label(npc_label),
                label=npc_label,
                home_location_id=locations[0].id,
                role="guide",
                interaction_hint=f"{npc_label}은(는) 현재 상황을 설명하거나 경고를 전할 수 있다.",
            )
        ]
        return WorldBlueprint(
            id=story_setup.id,
            title=story_setup.title,
            world_summary=story_setup.world_summary,
            tone=story_setup.tone,
            core_conflict=f"{story_setup.player_goal} 과정에서 세계의 숨겨진 진실이 드러난다.",
            player_goal=story_setup.player_goal,
            opening_hook=story_setup.opening_hook,
            starting_location_id=locations[0].id,
            locations=locations,
            npcs=npcs,
            notable_locations=[location.label for location in locations],
            important_npcs=[npc.label for npc in npcs],
            hidden_truths=["이 장소는 겉보기보다 오래된 봉인과 계약 위에 세워져 있다."],
        )

    def _normalize_starting_location(self, value: str, locations: list[WorldLocation]) -> str:
        normalized = value.strip().lower()
        by_id = {location.id: location.id for location in locations}
        by_label = {location.label.strip().lower(): location.id for location in locations}
        return by_id.get(normalized) or by_label.get(normalized) or locations[0].id

    def _normalize_locations(self, blueprint: WorldBlueprint, story_setup: StorySetup) -> list[WorldLocation]:
        locations: list[WorldLocation] = []
        for index, location in enumerate(blueprint.locations[:5]):
            label = location.label.strip()
            if not label:
                continue
            location_id = location.id.strip() or f"location_{index + 1}"
            connections = [conn.strip() for conn in location.connections if conn.strip()]
            locations.append(
                WorldLocation(
                    id=location_id,
                    label=label,
                    kind=location.kind.strip() or "location",
                    connections=connections,
                    danger_level=max(1, min(5, location.danger_level)),
                    investigation_hooks=[item.strip() for item in location.investigation_hooks if item.strip()][:3],
                )
            )
        if not locations:
            labels = [item.strip() for item in blueprint.notable_locations if item.strip()]
            if not labels:
                labels, _ = self._fallback_seed(story_setup)
            locations = self._build_linear_locations(labels)
        if all(not location.connections for location in locations):
            locations = self._build_linear_locations([location.label for location in locations], locations)
        return locations

    def _normalize_npcs(
        self,
        blueprint: WorldBlueprint,
        locations: list[WorldLocation],
        story_setup: StorySetup,
    ) -> list[WorldNpc]:
        valid_location_ids = {location.id for location in locations}
        npcs: list[WorldNpc] = []
        for index, npc in enumerate(blueprint.npcs[:5]):
            label = npc.label.strip()
            if not label:
                continue
            npc_id = npc.id.strip() or f"npc_{index + 1}"
            home = npc.home_location_id.strip()
            if home not in valid_location_ids:
                home = locations[0].id
            npcs.append(
                WorldNpc(
                    id=npc_id,
                    label=label,
                    home_location_id=home,
                    role=npc.role.strip(),
                    interaction_hint=npc.interaction_hint.strip(),
                )
            )
        if not npcs:
            labels, npc_label = self._fallback_seed(story_setup)
            return [
                WorldNpc(
                    id=self._slugify_label(npc_label),
                    label=npc_label,
                    home_location_id=locations[0].id,
                    role="guide",
                    interaction_hint=f"{npc_label}은(는) 현재 상황을 설명하거나 경고를 전할 수 있다.",
                )
            ]
        return npcs

    def _build_linear_locations(
        self,
        labels: list[str],
        seed_locations: list[WorldLocation] | None = None,
    ) -> list[WorldLocation]:
        cleaned = [label.strip() for label in labels if label.strip()][:5]
        if len(cleaned) < 3:
            cleaned = [*cleaned, "중심 구역", "깊은 구역", "핵심 장소"][:4]
        locations: list[WorldLocation] = []
        for index, label in enumerate(cleaned):
            existing = seed_locations[index] if seed_locations and index < len(seed_locations) else None
            location_id = existing.id if existing else self._slugify_label(label, prefix=f"loc_{index + 1}")
            connections: list[str] = []
            if index > 0:
                prev_id = locations[index - 1].id
                connections.append(prev_id)
            if index < len(cleaned) - 1:
                next_id = (
                    seed_locations[index + 1].id
                    if seed_locations and index + 1 < len(seed_locations)
                    else self._slugify_label(cleaned[index + 1], prefix=f"loc_{index + 2}")
                )
                connections.append(next_id)
            locations.append(
                WorldLocation(
                    id=location_id,
                    label=label,
                    kind=existing.kind if existing else "location",
                    connections=connections,
                    danger_level=existing.danger_level if existing else min(5, index + 1),
                    investigation_hooks=existing.investigation_hooks if existing else [f"{label}에서 수상한 흔적을 발견할 수 있다."],
                )
            )
        return locations

    def _fallback_seed(self, story_setup: StorySetup) -> tuple[list[str], str]:
        setup_id = story_setup.id.lower()
        if "city" in setup_id:
            return ["젖은 부두", "안개 골목", "밀수 창고", "종탑 광장"], "항구 경비"
        if "temple" in setup_id or "shrine" in setup_id:
            return ["낡은 대웅전", "승방 회랑", "지하 법당", "봉인된 내전"], "노승"
        if "frontier" in setup_id:
            return ["변경 초소", "먼지 협곡", "버려진 급수탑", "깨어난 망루"], "정찰병"
        if "royal" in setup_id or "palace" in setup_id or "court" in setup_id:
            return ["침전 앞 회랑", "비밀 서고", "어전 통로", "봉인된 내실"], "상궁"
        if "manor" in setup_id or "estate" in setup_id:
            return ["현관 홀", "초상화 복도", "봉인된 서재", "지하 예배실"], "집사"
        return ["폐허 입구", "무너진 회랑", "함정 석실", "깊은 성소"], "관리인"

    def _slugify_label(self, value: str, prefix: str = "node") -> str:
        slug = "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")
        slug = "_".join(filter(None, slug.split("_")))
        return slug or prefix
