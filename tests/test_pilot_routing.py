from oth.core.pilot import PilotPlanner


def test_explicit_production_code_routes_to_engineering():
    plan = PilotPlanner().plan(
        "Continue working on the production code for the OTH engineering execution subsystem."
    )
    assert plan.tasks[0].capability == "engineering"
    assert plan.tasks[0].action == "execute"
    assert plan.tasks[0].priority == 95


def test_explicit_repository_bugfix_routes_to_engineering():
    plan = PilotPlanner().plan("Fix the repository bug in the task execution kernel.")
    assert plan.tasks[0].capability == "engineering"


def test_research_about_python_does_not_route_to_engineering():
    plan = PilotPlanner().plan("Research Python libraries for market research automation.")
    assert plan.tasks[0].capability == "scout"


def test_video_creation_stays_media():
    plan = PilotPlanner().plan("Create a video for the campaign launch.")
    assert plan.tasks[0].capability == "media-production"
    assert plan.tasks[0].action == "plan"


def test_general_reasoning_stays_reasoning():
    plan = PilotPlanner().plan("Explain why the engineering execution subsystem needs evidence.")
    assert plan.tasks[0].capability == "reasoning"
