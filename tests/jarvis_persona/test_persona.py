"""Jarvis Persona模块测试"""

from jarvis.jarvis_persona import (
    JarvisPersona,
    PersonaConfig,
    EvolutionStage,
    ASCII_ARTS,
    STAGE_DESCRIPTIONS,
    get_welcome_message,
    get_ascii_art,
    get_stage_description,
)


class TestEvolutionStage:
    """进化阶段枚举测试"""

    def test_all_stages_defined(self):
        """测试所有阶段都已定义"""
        stages = list(EvolutionStage)
        assert len(stages) == 6
        assert EvolutionStage.STAGE_0 in stages
        assert EvolutionStage.STAGE_5 in stages

    def test_stage_values(self):
        """测试阶段值"""
        assert EvolutionStage.STAGE_0.value == "stage_0"
        assert EvolutionStage.STAGE_3.value == "stage_3"


class TestASCIIArts:
    """ASCII艺术测试"""

    def test_all_stages_have_art(self):
        """测试所有阶段都有ASCII艺术"""
        for stage in EvolutionStage:
            assert stage in ASCII_ARTS
            assert len(ASCII_ARTS[stage]) > 0

    def test_art_contains_jarvis(self):
        """测试ASCII艺术包含JARVIS"""
        for stage in EvolutionStage:
            assert "J.A.R.V.I.S" in ASCII_ARTS[stage]


class TestStageDescriptions:
    """阶段描述测试"""

    def test_all_stages_have_description(self):
        """测试所有阶段都有描述"""
        for stage in EvolutionStage:
            assert stage in STAGE_DESCRIPTIONS
            desc = STAGE_DESCRIPTIONS[stage]
            assert "name" in desc
            assert "title" in desc
            assert "emoji" in desc
            assert "capabilities" in desc

    def test_stage3_description(self):
        """测试阶段3描述"""
        desc = STAGE_DESCRIPTIONS[EvolutionStage.STAGE_3]
        assert desc["name"] == "智能顾问"
        assert desc["title"] == "Smart Advisor"


class TestPersonaConfig:
    """人格配置测试"""

    def test_default_config(self):
        """测试默认配置"""
        config = PersonaConfig()
        assert config.name == "J.A.R.V.I.S"
        assert config.version == "3.0"
        assert config.current_stage == EvolutionStage.STAGE_3

    def test_custom_config(self):
        """测试自定义配置"""
        config = PersonaConfig(
            name="Custom", version="1.0", current_stage=EvolutionStage.STAGE_1
        )
        assert config.name == "Custom"
        assert config.version == "1.0"
        assert config.current_stage == EvolutionStage.STAGE_1


class TestJarvisPersona:
    """Jarvis人格类测试"""

    def test_default_persona(self):
        """测试默认人格"""
        persona = JarvisPersona()
        assert persona.name == "J.A.R.V.I.S"
        assert persona.current_stage == EvolutionStage.STAGE_3

    def test_custom_persona(self):
        """测试自定义人格"""
        config = PersonaConfig(current_stage=EvolutionStage.STAGE_1)
        persona = JarvisPersona(config)
        assert persona.current_stage == EvolutionStage.STAGE_1

    def test_set_stage(self):
        """测试设置阶段"""
        persona = JarvisPersona()
        persona.current_stage = EvolutionStage.STAGE_5
        assert persona.current_stage == EvolutionStage.STAGE_5

    def test_get_ascii_art(self):
        """测试获取ASCII艺术"""
        persona = JarvisPersona()
        art = persona.get_ascii_art()
        assert "J.A.R.V.I.S" in art
        assert "SMART ADVISOR" in art

    def test_get_ascii_art_specific_stage(self):
        """测试获取特定阶段ASCII艺术"""
        persona = JarvisPersona()
        art = persona.get_ascii_art(EvolutionStage.STAGE_0)
        assert "INITIALIZING" in art

    def test_get_stage_info(self):
        """测试获取阶段信息"""
        persona = JarvisPersona()
        info = persona.get_stage_info()
        assert info["name"] == "智能顾问"
        assert info["emoji"] == "🧠"

    def test_get_welcome_message(self):
        """测试获取欢迎消息"""
        persona = JarvisPersona()
        msg = persona.get_welcome_message()
        assert "J.A.R.V.I.S" in msg
        assert "智能顾问" in msg
        assert "您好" in msg

    def test_get_status_bar(self):
        """测试获取状态栏"""
        persona = JarvisPersona()
        bar = persona.get_status_bar()
        assert "🧠" in bar
        assert "J.A.R.V.I.S" in bar

    def test_get_evolution_progress(self):
        """测试获取进化进度"""
        persona = JarvisPersona()
        progress = persona.get_evolution_progress()
        assert "进化路线图" in progress
        assert "✅" in progress  # 已完成阶段
        assert "🔵" in progress  # 当前阶段
        assert "⬜" in progress  # 未来阶段


class TestConvenienceFunctions:
    """便捷函数测试"""

    def test_get_welcome_message_default(self):
        """测试默认欢迎消息"""
        msg = get_welcome_message()
        assert "J.A.R.V.I.S" in msg

    def test_get_welcome_message_specific_stage(self):
        """测试特定阶段欢迎消息"""
        msg = get_welcome_message(EvolutionStage.STAGE_0)
        assert "INITIALIZING" in msg

    def test_get_ascii_art_default(self):
        """测试默认ASCII艺术"""
        art = get_ascii_art()
        assert "J.A.R.V.I.S" in art

    def test_get_stage_description_default(self):
        """测试默认阶段描述"""
        desc = get_stage_description()
        assert desc["name"] == "智能顾问"

    def test_get_stage_description_specific(self):
        """测试特定阶段描述"""
        desc = get_stage_description(EvolutionStage.STAGE_5)
        assert desc["name"] == "数字孪生智能"
