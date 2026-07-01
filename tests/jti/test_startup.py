from unittest.mock import Mock, patch

from app.services.jti import startup


def test_jti_startup_runs_core_and_background_tasks():
    prompt_manager = Mock()

    with (
        patch("app.services.jti.startup.jti_core_startup") as core_startup,
        patch("app.services.jti.startup.jti_background_startup") as background_startup,
    ):
        startup.jti_startup(prompt_manager)

    core_startup.assert_called_once_with(prompt_manager)
    background_startup.assert_called_once_with()


def test_jti_core_startup_does_not_seed_quiz_data():
    prompt_manager = Mock()

    with (
        patch("app.services.jti.startup._init_jti_default_prompt") as init_prompt,
        patch("app.services.jti.startup._migrate_jti_profile_storage") as migrate_profiles,
        patch("app.services.jti.startup._seed_quiz_data") as seed_quiz,
    ):
        startup.jti_core_startup(prompt_manager)

    init_prompt.assert_called_once_with(prompt_manager)
    migrate_profiles.assert_called_once_with(prompt_manager)
    seed_quiz.assert_not_called()


def test_jti_background_startup_seeds_quiz_data():
    with patch("app.services.jti.startup._seed_quiz_data") as seed_quiz:
        startup.jti_background_startup()

    seed_quiz.assert_called_once_with()
