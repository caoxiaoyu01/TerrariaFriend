from typing import Any

from agent.decision.schema import DecisionInput
from agent.models.trigger import TriggerRequest


class ContextBuilder:
    def build(
        self,
        trigger: TriggerRequest,
        decision_input: DecisionInput,
        decision_reason: str,
    ) -> dict[str, Any]:
        # 只提供回答本次问题需要的信息
        context: dict[str, Any] = {
            "trigger_type": trigger.trigger_type.value,
            "priority": trigger.priority.value,
            "timestamp": trigger.timestamp.isoformat(),
            "vitals": decision_input.vitals.model_dump(mode="json"),
            "decision_reason": decision_reason,
        }
        if decision_input.user_query is not None:
            context["user_query"] = decision_input.user_query
        if decision_input.game_event is not None:
            context["game_event"] = decision_input.game_event.model_dump(mode="json")
        if decision_input.event_context is not None:
            context["event_context"] = decision_input.event_context.model_dump(
                mode="json",
                exclude_none=True,
            )
        if decision_input.periodic_summary is not None:
            context["periodic_summary"] = decision_input.periodic_summary.model_dump(
                mode="json",
                exclude_none=True,
            )
        return context
