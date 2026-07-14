"""Safety prompt contracts shared by every user-facing agent service."""

import pytest

from app.services.esg.agent_prompts import (
    PERSONA as ESG_PERSONA,
    build_system_instruction as build_esg_system_instruction,
)
from app.services.general.agent_prompts import (
    PERSONA as GENERAL_PERSONA,
    build_system_instruction as build_general_system_instruction,
)
from app.services.hciot.agent_prompts import (
    PERSONA as HCIOT_PERSONA,
    build_system_instruction as build_hciot_system_instruction,
)
from app.services.jti.agent_prompts import (
    PERSONA as JTI_PERSONA,
    build_system_instruction as build_jti_system_instruction,
)

SERVICES = (
    ("esg", build_esg_system_instruction, ESG_PERSONA),
    ("general", build_general_system_instruction, GENERAL_PERSONA),
    ("hciot", build_hciot_system_instruction, HCIOT_PERSONA),
    ("jti", build_jti_system_instruction, JTI_PERSONA),
)

CUSTOM_RULE_SECTIONS = {
    "role_scope": "自訂角色",
    "scope_limits": "自訂範圍",
    "response_style": "自訂風格",
    "knowledge_rules": "自訂知識庫規則",
}


def assert_uses_strict_shared_safety(instruction: str) -> None:
    assert "「我是」是正常自我介紹" in instruction
    assert "害怕、難過、焦慮、壓力大、疲憊或心情不好" in instruction
    assert "避免使用「請一定」「務必」" in instruction
    assert "1925" in instruction
    assert "1995" in instruction


@pytest.mark.parametrize(
    ("_name", "builder", "persona"),
    SERVICES,
    ids=[service[0] for service in SERVICES],
)
def test_default_prompts_use_strict_shared_safety(_name, builder, persona):
    instruction = builder(persona["zh"], "zh")

    assert_uses_strict_shared_safety(instruction)


@pytest.mark.parametrize(
    ("_name", "builder", "persona"),
    SERVICES,
    ids=[service[0] for service in SERVICES],
)
def test_custom_prompts_use_strict_shared_safety(_name, builder, persona):
    instruction = builder(persona["zh"], "zh", CUSTOM_RULE_SECTIONS)

    assert "自訂風格" in instruction
    assert_uses_strict_shared_safety(instruction)
