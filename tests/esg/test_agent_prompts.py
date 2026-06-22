"""Tests for ESG default agent prompts."""

from app.services.esg.agent_prompts import (
    PERSONA,
    WELCOME_TEXT,
    build_system_instruction,
)


def test_esg_welcome_text_uses_set_future_aikka_copy():
    assert WELCOME_TEXT["zh"]["title"] == "歡迎來到三立集團ESG永續展示區。"
    assert "AI 導覽員AIKKA" in WELCOME_TEXT["zh"]["description"]
    assert "共創台灣的美好永續" in WELCOME_TEXT["zh"]["description"]

    assert WELCOME_TEXT["en"]["title"] == "Welcome to SET FUTURE."
    assert "AI guide" in WELCOME_TEXT["en"]["description"]
    assert "30 years of SET's story in Taiwan" in WELCOME_TEXT["en"]["description"]


def test_esg_default_system_prompt_identifies_aikka_and_set_future():
    zh_instruction = build_system_instruction(PERSONA["zh"], "zh")
    en_instruction = build_system_instruction(PERSONA["en"], "en")

    assert "AIKKA" in zh_instruction
    assert "三立集團ESG永續展示區" in zh_instruction
    assert "共創台灣的美好永續" in zh_instruction

    assert "AIKKA" in en_instruction
    assert "SET FUTURE" in en_instruction
    assert "low-carbon living" in en_instruction
