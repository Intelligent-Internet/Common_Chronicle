import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from app.a2a.agent_executor import CommonChronicleAgentExecutor
from app.a2a.config import SERVER_HOST_START, SERVER_HOST_VIEW, SERVER_PORT


def build_app() -> A2AStarletteApplication:
    skills = [
        AgentSkill(
            id="timeline_generation",
            name="Timeline Generation",
            description="Generate comprehensive event timelines from viewpoints and research questions",
            tags=["timeline", "chronology", "events", "history"],
            examples=[
                "Generate a timeline for the development of artificial intelligence",
                "Create a chronological sequence of major events in World War II",
                "Build a timeline showing the evolution of renewable energy technologies",
            ],
        ),
    ]

    agent_card = AgentCard(
        name="Common Chronicle Timeline Generator",
        description="AI-powered timeline generation service that creates comprehensive event timelines from viewpoints and research questions",
        url=f"http://{SERVER_HOST_VIEW}:{SERVER_PORT}/",
        version="1.0.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=skills,
    )

    request_handler = DefaultRequestHandler(
        agent_executor=CommonChronicleAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    return A2AStarletteApplication(agent_card=agent_card, http_handler=request_handler)


def main():
    app = build_app()

    asgi_app = app.build()
    uvicorn.run(asgi_app, host=SERVER_HOST_START, port=SERVER_PORT, log_level="info")


if __name__ == "__main__":
    main()
