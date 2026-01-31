"""PreferenceLearner测试模块"""

from jarvis.jarvis_digital_twin.user_profile.preference_learner import (
    CodeStyleDetail,
    CodeStylePreference,
    InteractionData,
    InteractionStyleDetail,
    InteractionStylePreference,
    PreferenceConfidence,
    PreferenceLearner,
    TechStackPreference,
    UserPreference,
)


class TestPreferenceConfidence:
    """PreferenceConfidence数据类测试"""

    def test_default_values(self) -> None:
        """测试默认值"""
        conf = PreferenceConfidence()
        assert conf.value == 0.5
        assert conf.sample_count == 0
        assert conf.last_updated == ""

    def test_update_positive(self) -> None:
        """测试正向更新"""
        conf = PreferenceConfidence(value=0.5)
        conf.update(positive=True)
        assert conf.value == 0.6
        assert conf.sample_count == 1
        assert conf.last_updated != ""

    def test_update_negative(self) -> None:
        """测试负向更新"""
        conf = PreferenceConfidence(value=0.5)
        conf.update(positive=False)
        assert conf.value == 0.4
        assert conf.sample_count == 1

    def test_update_with_weight(self) -> None:
        """测试带权重的更新"""
        conf = PreferenceConfidence(value=0.5)
        conf.update(positive=True, weight=2.0)
        assert conf.value == 0.7

    def test_update_bounds(self) -> None:
        """测试边界值"""
        conf = PreferenceConfidence(value=0.95)
        conf.update(positive=True)
        assert conf.value == 1.0

        conf2 = PreferenceConfidence(value=0.05)
        conf2.update(positive=False)
        assert conf2.value == 0.0


class TestCodeStyleDetail:
    """CodeStyleDetail数据类测试"""

    def test_default_values(self) -> None:
        """测试默认值"""
        style = CodeStyleDetail()
        assert style.preferred_style == CodeStylePreference.MIXED
        assert style.indentation == "spaces"
        assert style.indent_size == 4
        assert style.max_line_length == 88
        assert style.prefer_type_hints is True
        assert style.prefer_docstrings is True
        assert style.naming_convention == "snake_case"

    def test_custom_values(self) -> None:
        """测试自定义值"""
        style = CodeStyleDetail(
            preferred_style=CodeStylePreference.FUNCTIONAL,
            indent_size=2,
            prefer_type_hints=False,
        )
        assert style.preferred_style == CodeStylePreference.FUNCTIONAL
        assert style.indent_size == 2
        assert style.prefer_type_hints is False


class TestTechStackPreference:
    """TechStackPreference数据类测试"""

    def test_default_values(self) -> None:
        """测试默认值"""
        tech = TechStackPreference()
        assert tech.preferred_languages == []
        assert tech.preferred_frameworks == []
        assert tech.preferred_tools == []
        assert tech.avoided_technologies == []

    def test_custom_values(self) -> None:
        """测试自定义值"""
        tech = TechStackPreference(
            preferred_languages=["python", "rust"],
            preferred_frameworks=["fastapi"],
        )
        assert "python" in tech.preferred_languages
        assert "fastapi" in tech.preferred_frameworks


class TestInteractionStyleDetail:
    """InteractionStyleDetail数据类测试"""

    def test_default_values(self) -> None:
        """测试默认值"""
        style = InteractionStyleDetail()
        assert style.preferred_style == InteractionStylePreference.FRIENDLY
        assert style.verbosity_level == 0.5
        assert style.prefer_examples is True
        assert style.prefer_explanations is True
        assert style.response_language == "zh"


class TestUserPreference:
    """UserPreference数据类测试"""

    def test_default_values(self) -> None:
        """测试默认值"""
        pref = UserPreference()
        assert pref.user_id == "default"
        assert isinstance(pref.code_style, CodeStyleDetail)
        assert isinstance(pref.tech_stack, TechStackPreference)
        assert isinstance(pref.interaction_style, InteractionStyleDetail)
        assert pref.created_at != ""
        assert pref.updated_at != ""

    def test_to_dict(self) -> None:
        """测试转换为字典"""
        pref = UserPreference(user_id="test_user")
        data = pref.to_dict()
        assert data["user_id"] == "test_user"
        assert "code_style" in data
        assert "tech_stack" in data
        assert "interaction_style" in data

    def test_from_dict(self) -> None:
        """测试从字典创建"""
        data = {
            "user_id": "test_user",
            "code_style": {
                "preferred_style": "functional",
                "indent_size": 2,
            },
            "tech_stack": {
                "preferred_languages": ["python"],
            },
            "interaction_style": {
                "preferred_style": "technical",
            },
        }
        pref = UserPreference.from_dict(data)
        assert pref.user_id == "test_user"
        assert pref.code_style.preferred_style == CodeStylePreference.FUNCTIONAL
        assert "python" in pref.tech_stack.preferred_languages
        assert (
            pref.interaction_style.preferred_style
            == InteractionStylePreference.TECHNICAL
        )

    def test_from_dict_invalid_enum(self) -> None:
        """测试从字典创建时处理无效枚举"""
        data = {
            "code_style": {"preferred_style": "invalid"},
            "interaction_style": {"preferred_style": "invalid"},
        }
        pref = UserPreference.from_dict(data)
        assert pref.code_style.preferred_style == CodeStylePreference.MIXED
        assert (
            pref.interaction_style.preferred_style
            == InteractionStylePreference.FRIENDLY
        )


class TestInteractionData:
    """InteractionData数据类测试"""

    def test_default_values(self) -> None:
        """测试默认值"""
        data = InteractionData()
        assert data.content == ""
        assert data.interaction_type == ""
        assert data.tags == []
        assert data.metadata == {}
        assert data.timestamp != ""

    def test_custom_values(self) -> None:
        """测试自定义值"""
        data = InteractionData(
            content="test content",
            interaction_type="command",
            tags=["test", "code"],
        )
        assert data.content == "test content"
        assert data.interaction_type == "command"
        assert "test" in data.tags


class TestPreferenceLearner:
    """PreferenceLearner类测试"""

    def test_init_default(self) -> None:
        """测试默认初始化"""
        learner = PreferenceLearner()
        assert learner.user_id == "default"
        assert isinstance(learner.preference, UserPreference)

    def test_init_custom_user_id(self) -> None:
        """测试自定义用户ID初始化"""
        learner = PreferenceLearner(user_id="test_user")
        assert learner.user_id == "test_user"
        assert learner.preference.user_id == "test_user"

    def test_learn_code_style_concise(self) -> None:
        """测试学习简洁代码风格"""
        learner = PreferenceLearner()
        interaction = InteractionData(content="请用简洁的方式实现")
        learner.learn_from_interaction(interaction)
        assert (
            learner.preference.code_style.preferred_style == CodeStylePreference.CONCISE
        )

    def test_learn_code_style_functional(self) -> None:
        """测试学习函数式代码风格"""
        learner = PreferenceLearner()
        interaction = InteractionData(content="使用functional方式和lambda")
        learner.learn_from_interaction(interaction)
        assert (
            learner.preference.code_style.preferred_style
            == CodeStylePreference.FUNCTIONAL
        )

    def test_learn_type_hints_preference(self) -> None:
        """测试学习类型注解偏好"""
        learner = PreferenceLearner()
        interaction = InteractionData(content="请添加type hint")
        learner.learn_from_interaction(interaction)
        assert learner.preference.code_style.prefer_type_hints is True

    def test_learn_tech_stack_language(self) -> None:
        """测试学习语言偏好"""
        learner = PreferenceLearner()
        interaction = InteractionData(content="使用python实现", tags=["rust"])
        learner.learn_from_interaction(interaction)
        assert "python" in learner.preference.tech_stack.preferred_languages
        assert "rust" in learner.preference.tech_stack.preferred_languages

    def test_learn_tech_stack_framework(self) -> None:
        """测试学习框架偏好"""
        learner = PreferenceLearner()
        interaction = InteractionData(content="用fastapi创建API")
        learner.learn_from_interaction(interaction)
        assert "fastapi" in learner.preference.tech_stack.preferred_frameworks

    def test_learn_tech_stack_tool(self) -> None:
        """测试学习工具偏好"""
        learner = PreferenceLearner()
        interaction = InteractionData(content="使用pytest测试")
        learner.learn_from_interaction(interaction)
        assert "pytest" in learner.preference.tech_stack.preferred_tools

    def test_learn_interaction_style_formal(self) -> None:
        """测试学习正式交互风格"""
        learner = PreferenceLearner()
        interaction = InteractionData(content="请用正式专业的方式回答")
        learner.learn_from_interaction(interaction)
        assert (
            learner.preference.interaction_style.preferred_style
            == InteractionStylePreference.FORMAL
        )

    def test_learn_verbosity_detailed(self) -> None:
        """测试学习详细程度偏好"""
        learner = PreferenceLearner()
        initial_level = learner.preference.interaction_style.verbosity_level
        interaction = InteractionData(content="请详细解释")
        learner.learn_from_interaction(interaction)
        assert learner.preference.interaction_style.verbosity_level > initial_level

    def test_learn_example_preference(self) -> None:
        """测试学习示例偏好"""
        learner = PreferenceLearner()
        interaction = InteractionData(content="请给我一个例子")
        learner.learn_from_interaction(interaction)
        assert learner.preference.interaction_style.prefer_examples is True

    def test_get_code_style_preference(self) -> None:
        """测试获取代码风格偏好"""
        learner = PreferenceLearner()
        style = learner.get_code_style_preference()
        assert isinstance(style, CodeStyleDetail)

    def test_get_tech_preference(self) -> None:
        """测试获取技术栈偏好"""
        learner = PreferenceLearner()
        tech = learner.get_tech_preference()
        assert isinstance(tech, TechStackPreference)

    def test_get_interaction_style_preference(self) -> None:
        """测试获取交互风格偏好"""
        learner = PreferenceLearner()
        style = learner.get_interaction_style_preference()
        assert isinstance(style, InteractionStyleDetail)

    def test_update_preference_code_style(self) -> None:
        """测试更新代码风格偏好"""
        learner = PreferenceLearner()
        result = learner.update_preference("code_style", "indent_size", 2)
        assert result is True
        assert learner.preference.code_style.indent_size == 2

    def test_update_preference_custom(self) -> None:
        """测试更新自定义偏好"""
        learner = PreferenceLearner()
        result = learner.update_preference("custom", "theme", "dark")
        assert result is True
        assert learner.preference.custom_preferences["theme"] == "dark"

    def test_update_preference_invalid(self) -> None:
        """测试更新无效偏好"""
        learner = PreferenceLearner()
        result = learner.update_preference("code_style", "invalid_key", "value")
        assert result is False

    def test_get_preference_confidence(self) -> None:
        """测试获取偏好置信度"""
        learner = PreferenceLearner()
        conf = learner.get_preference_confidence("code_style")
        assert 0.0 <= conf <= 1.0

    def test_get_overall_confidence(self) -> None:
        """测试获取整体置信度"""
        learner = PreferenceLearner()
        conf = learner.get_overall_confidence()
        assert 0.0 <= conf <= 1.0

    def test_reset_preference_all(self) -> None:
        """测试重置所有偏好"""
        learner = PreferenceLearner()
        learner.preference.code_style.indent_size = 2
        learner.reset_preference()
        assert learner.preference.code_style.indent_size == 4

    def test_reset_preference_specific(self) -> None:
        """测试重置特定偏好"""
        learner = PreferenceLearner()
        learner.preference.code_style.indent_size = 2
        learner.preference.tech_stack.preferred_languages.append("python")
        learner.reset_preference("code_style")
        assert learner.preference.code_style.indent_size == 4
        assert "python" in learner.preference.tech_stack.preferred_languages

    def test_export_import_preference(self) -> None:
        """测试导出和导入偏好"""
        learner = PreferenceLearner(user_id="test")
        learner.preference.code_style.indent_size = 2
        data = learner.export_preference()

        learner2 = PreferenceLearner(user_id="test")
        learner2.import_preference(data)
        assert learner2.preference.code_style.indent_size == 2

    def test_interaction_history_count(self) -> None:
        """测试交互历史计数"""
        learner = PreferenceLearner()
        assert learner.get_interaction_history_count() == 0
        learner.learn_from_interaction(InteractionData(content="test"))
        assert learner.get_interaction_history_count() == 1

    def test_clear_interaction_history(self) -> None:
        """测试清除交互历史"""
        learner = PreferenceLearner()
        learner.learn_from_interaction(InteractionData(content="test"))
        learner.clear_interaction_history()
        assert learner.get_interaction_history_count() == 0
