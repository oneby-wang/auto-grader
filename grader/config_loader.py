"""
配置加载模块 - 读取和验证 JSON 配置文件
"""

import json
import os
from typing import List, Dict, Any, Tuple, Optional


class ConfigError(Exception):
    """配置错误异常"""
    pass


class QuestionConfig:
    """单个题目的配置"""

    def __init__(self, data: Dict[str, Any], index: int):
        self.index = index
        self.name = data.get("name", f"题目{index + 1}")
        self.correct_answer = data.get("correct_answer")
        self.screenshot_area = self._parse_screenshot_area(data.get("screenshot_area"))
        self.input_box = self._parse_coordinate(data.get("input_box"), "input_box")
        self.next_button = self._parse_coordinate(data.get("next_button"), "next_button")

    def _parse_screenshot_area(self, area) -> Tuple[int, int, int, int]:
        """解析截图区域坐标 [x1, y1, x2, y2] -> (x, y, width, height)"""
        if not area or not isinstance(area, (list, tuple)) or len(area) != 4:
            raise ConfigError(f"题目 '{self.name}' 的 screenshot_area 必须是包含4个元素的列表 [x1, y1, x2, y2]")

        try:
            x1, y1, x2, y2 = map(int, area)
        except (ValueError, TypeError):
            raise ConfigError(f"题目 '{self.name}' 的 screenshot_area 坐标必须是整数")

        if x1 < 0 or y1 < 0 or x2 < 0 or y2 < 0:
            raise ConfigError(f"题目 '{self.name}' 的 screenshot_area 坐标不能为负数")

        if x2 <= x1 or y2 <= y1:
            raise ConfigError(f"题目 '{self.name}' 的 screenshot_area 右下角坐标必须大于左上角坐标")

        # 转换为 pyautogui 格式: (x, y, width, height)
        return (x1, y1, x2 - x1, y2 - y1)

    def _parse_coordinate(self, coord, name: str) -> Tuple[int, int]:
        """解析坐标 [x, y]"""
        if not coord or not isinstance(coord, (list, tuple)) or len(coord) != 2:
            raise ConfigError(f"题目 '{self.name}' 的 {name} 必须是包含2个元素的列表 [x, y]")

        try:
            x, y = map(int, coord)
        except (ValueError, TypeError):
            raise ConfigError(f"题目 '{self.name}' 的 {name} 坐标必须是整数")

        if x < 0 or y < 0:
            raise ConfigError(f"题目 '{self.name}' 的 {name} 坐标不能为负数")

        return (x, y)

    def __repr__(self):
        return f"QuestionConfig({self.name}, correct={self.correct_answer}, screenshot={self.screenshot_area}, input={self.input_box}, next={self.next_button})"


class GraderConfig:
    """评分器整体配置"""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.data = self._load_json()

        self.total_pages = self._parse_total_pages()
        self.delay_between_pages = self._parse_delay()
        self.delay_before_screenshot = self.data.get("delay_before_screenshot", 0.5)
        self.screenshot_dir = self._parse_screenshot_dir()
        self.questions = self._parse_questions()
        self.model_provider = self._parse_model_provider()
        self.model_config = self._parse_model_config()

    def _load_json(self) -> Dict[str, Any]:
        """加载 JSON 文件"""
        if not os.path.exists(self.config_path):
            raise ConfigError(f"配置文件不存在: {self.config_path}")

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigError(f"配置文件 JSON 格式错误: {e}")
        except Exception as e:
            raise ConfigError(f"读取配置文件失败: {e}")

    def _parse_total_pages(self) -> int:
        """解析总页面数"""
        total = self.data.get("total_pages")
        if total is None:
            raise ConfigError("配置文件中缺少 'total_pages' 字段")

        try:
            total = int(total)
        except (ValueError, TypeError):
            raise ConfigError("'total_pages' 必须是整数")

        if total <= 0:
            raise ConfigError("'total_pages' 必须大于 0")

        return total

    def _parse_delay(self) -> float:
        """解析页面间延迟"""
        delay = self.data.get("delay_between_pages", 2.0)
        try:
            delay = float(delay)
        except (ValueError, TypeError):
            raise ConfigError("'delay_between_pages' 必须是数字")

        if delay < 0:
            raise ConfigError("'delay_between_pages' 不能为负数")

        return delay

    def _parse_screenshot_dir(self) -> str:
        """解析截图保存目录"""
        dir_path = self.data.get("screenshot_dir", "screenshots")

        # 如果是相对路径，相对于配置文件所在目录
        if not os.path.isabs(dir_path):
            base_dir = os.path.dirname(os.path.abspath(self.config_path))
            dir_path = os.path.join(base_dir, dir_path)

        # 确保目录存在
        os.makedirs(dir_path, exist_ok=True)

        return dir_path

    def _parse_questions(self) -> List[QuestionConfig]:
        """解析题目配置列表"""
        questions_data = self.data.get("questions")
        if not questions_data:
            raise ConfigError("配置文件中缺少 'questions' 字段或为空列表")

        if not isinstance(questions_data, list):
            raise ConfigError("'questions' 必须是列表")

        if len(questions_data) == 0:
            raise ConfigError("'questions' 列表不能为空")

        questions = []
        for i, q_data in enumerate(questions_data):
            if not isinstance(q_data, dict):
                raise ConfigError(f"questions[{i}] 必须是对象")
            questions.append(QuestionConfig(q_data, i))

        return questions

    def _parse_model_provider(self) -> str:
        """解析模型提供商配置"""
        provider = self.data.get("model_provider", "mock")

        if not isinstance(provider, str):
            raise ConfigError("'model_provider' 必须是字符串")

        return provider.lower()

    def _parse_model_config(self) -> Dict[str, Any]:
        """解析模型配置"""
        model_config = self.data.get("model_config", {})

        if not isinstance(model_config, dict):
            raise ConfigError("'model_config' 必须是对象")

        return model_config

    def get_question_for_page(self, page_index: int) -> QuestionConfig:
        """
        根据页面索引获取对应的题目配置
        如果题目数量少于页面数，则循环使用题目配置
        """
        question_index = page_index % len(self.questions)
        return self.questions[question_index]

    def get_scorer_config(self) -> Dict[str, Any]:
        """
        获取当前模型提供商的配置

        Returns:
            模型配置字典
        """
        return self.model_config.get(self.model_provider, {})

    def validate(self) -> bool:
        """验证配置是否完整有效"""
        if self.total_pages <= 0:
            return False
        if len(self.questions) == 0:
            return False
        return True

    def __repr__(self):
        return f"GraderConfig(pages={self.total_pages}, questions={len(self.questions)}, provider={self.model_provider}, dir={self.screenshot_dir})"
