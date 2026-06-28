from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoleSpec:
    intent: str
    role: str
    output_type: str
    behavior: str
    completion_rules: tuple[str, ...]


ROLE_SPECS = {
    "content_creation": RoleSpec(
        intent="content_creation",
        role="Content Director",
        output_type="complete_content_asset",
        behavior="Produce contenuti completi, pronti da pubblicare, senza teoria inutile.",
        completion_rules=(
            "LinkedIn post: Hook, Body, CTA, optional hashtags.",
            "Carousel: Title, slide-by-slide structure, CTA.",
            "TikTok/video: Hook, Script, Visual direction, CTA.",
            "Never return only a hook unless the user explicitly asks only for hooks.",
        ),
    ),
    "strategy": RoleSpec(
        intent="strategy",
        role="Strategy Advisor",
        output_type="strategic_recommendation",
        behavior="Dà direzione chiara, opzioni, tradeoff e raccomandazione pratica.",
        completion_rules=("Explain the strategic choice.", "Give concrete next moves.", "Avoid generic summaries."),
    ),
    "business_analysis": RoleSpec(
        intent="business_analysis",
        role="Research Analyst",
        output_type="analysis",
        behavior="Analizza dati, ipotesi, rischi e implicazioni operative.",
        completion_rules=("Separate facts from assumptions.", "End with a conclusion.", "Do not invent data."),
    ),
    "task_management": RoleSpec(
        intent="task_management",
        role="Operations Manager",
        output_type="task_dashboard",
        behavior="Trasforma obiettivi e richieste in priorità eseguibili.",
        completion_rules=("Prioritize tasks.", "Keep actions concise.", "Connect work to active goals when possible."),
    ),
    "goal_review": RoleSpec(
        intent="goal_review",
        role="CEO/Manager Agent",
        output_type="goal_dashboard",
        behavior="Legge obiettivi, stato, priorità e prossime decisioni.",
        completion_rules=("Show progress.", "Clarify priorities.", "Suggest next actions."),
    ),
    "decision_support": RoleSpec(
        intent="decision_support",
        role="Executive Advisor",
        output_type="decision_support",
        behavior="Aiuta Michele a decidere con criteri, tradeoff e raccomandazione.",
        completion_rules=("State the recommended choice.", "Explain why.", "Define the smallest useful test."),
    ),
    "conversation": RoleSpec(
        intent="conversation",
        role="Senior Consultant",
        output_type="conversation",
        behavior="Risponde in modo naturale, professionale e diretto.",
        completion_rules=("Be concise.", "Ask at most one clarification question only if necessary."),
    ),
}


class RoleRouter:
    def detect_intent(self, text: str) -> str:
        normalized = text.lower()
        if any(term in normalized for term in ("decidere", "decisione", "scelta", "scegliere", "conviene", "cosa faresti")):
            return "decision_support"
        if any(term in normalized for term in ("obiettivo", "obiettivi", "goal", "progresso obiettivo")):
            return "goal_review"
        if any(term in normalized for term in ("task", "priorità", "priorita", "cosa devo fare", "cosa dovrei fare", "briefing", "review")):
            return "task_management"
        if any(term in normalized for term in ("analizza", "analisi", "ricerca", "research", "mercato", "competitor", "benchmark", "confronta")):
            return "business_analysis"
        content_terms = ("linkedin", "instagram", "tiktok", "carousel", "carosello", "newsletter", "video", "script", "post", "caption", "contenuto", "contenuti")
        content_actions = ("crea", "scrivi", "fammi", "prepara", "genera", "dammi", "proponi", "sviluppa")
        if any(term in normalized for term in content_terms) and any(action in normalized for action in content_actions):
            return "content_creation"
        if any(term in normalized for term in ("strategia", "business", "monetizzazione", "funnel", "posizionamento", "crescita", "growth", "audience", "personal brand")):
            return "strategy"
        return "conversation"

    def spec_for_text(self, text: str) -> RoleSpec:
        return self.spec_for_intent(self.detect_intent(text))

    def spec_for_intent(self, intent: str) -> RoleSpec:
        return ROLE_SPECS.get(intent, ROLE_SPECS["conversation"])

    def context_for_prompt(self, spec: RoleSpec) -> str:
        rules = "\n".join(f"- {rule}" for rule in spec.completion_rules)
        return (
            "ROLE ROUTING\n"
            f"Intent: {spec.intent}\n"
            f"Role: {spec.role}\n"
            f"Output type: {spec.output_type}\n"
            f"Behavior: {spec.behavior}\n"
            f"Completion rules:\n{rules}"
        )
