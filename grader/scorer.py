"""
评分模块 - 多模态大模型评分接口

支持多种大模型提供商：
- 阿里百炼 (DashScope)
- 模拟评分 (Mock，用于测试)

可通过 config.json 配置切换模型提供商。
"""

import base64
import os
import random
import re
import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class ScorerError(Exception):
    """评分错误异常"""
    pass


class BaseScorer(ABC):
    """
    评分器抽象基类

    所有具体评分器实现都需要继承此类，实现 score 方法。
    """

    @abstractmethod
    def score(self, image_path: str, question_name: str, correct_answer: Optional[str]) -> str:
        """
        对截图进行评分

        Args:
            image_path: 截图文件路径
            question_name: 题目名称
            correct_answer: 正确答案（可选）

        Returns:
            评分结果字符串（如 "90"）

        Raises:
            ScorerError: 评分失败时抛出
        """
        pass

    def _encode_image(self, image_path: str) -> str:
        """
        将图片文件转为 base64 编码

        Args:
            image_path: 图片文件路径

        Returns:
            base64 编码的字符串

        Raises:
            ScorerError: 文件不存在或读取失败时抛出
        """
        if not os.path.exists(image_path):
            raise ScorerError(f"截图文件不存在: {image_path}")

        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode("utf-8")
        except Exception as e:
            raise ScorerError(f"读取图片文件失败: {e}")

    def _build_prompt(self, question_name: str, correct_answer: Optional[str]) -> str:
        """
        构建评分提示词

        Args:
            question_name: 题目名称
            correct_answer: 正确答案

        Returns:
            完整的提示词字符串
        """
        prompt = f"""你是一位专业的教师，需要对学生的答题情况进行评分。

题目类型: {question_name}
"""
        if correct_answer:
            prompt += f"正确答案: {correct_answer}\n"

        prompt += """
请查看图片中的学生答案，根据以下标准评分：
- 如果学生答案与正确答案一致：满分 100 分
- 如果部分正确：酌情给分（60-99 分）
- 如果完全错误：0-59 分

请只返回一个数字分数（0-100），不要有任何其他文字说明。"""

        return prompt


class DashScopeScorer(BaseScorer):
    """
    阿里百炼评分器实现

    使用 OpenAI 兼容接口调用阿里百炼的 qwen3-vl-plus 模型。
    需要在环境变量中设置 DASHSCOPE_API_KEY。
    """

    DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    DEFAULT_MODEL = "qwen3-vl-plus"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化阿里百炼评分器

        Args:
            config: 模型配置字典，可包含 model、enable_thinking、thinking_budget 等
        """
        self.config = config or {}
        self.api_key = os.getenv("DASHSCOPE_API_KEY")

        if not self.api_key:
            raise ScorerError(
                "未设置 DASHSCOPE_API_KEY 环境变量，"
                "请运行: export DASHSCOPE_API_KEY=your_api_key"
            )

        # 导入 openai 库
        try:
            from openai import OpenAI
            self.OpenAI = OpenAI
        except ImportError:
            raise ScorerError(
                "未安装 openai 包，请运行: pip install openai"
            )

        # 初始化客户端
        self.client = self.OpenAI(
            api_key=self.api_key,
            base_url=self.config.get("base_url", self.DEFAULT_BASE_URL)
        )

        self.model = self.config.get("model", self.DEFAULT_MODEL)
        self.enable_thinking = self.config.get("enable_thinking", False)
        self.thinking_budget = self.config.get("thinking_budget", 81920)

    def score(self, image_path: str, question_name: str, correct_answer: Optional[str]) -> str:
        """
        调用阿里百炼模型对截图进行评分

        Args:
            image_path: 截图文件路径
            question_name: 题目名称
            correct_answer: 正确答案
        Returns:
            评分结果字符串
        """
        # 编码图片
        base64_image = self._encode_image(image_path)

        # 构建提示词
        prompt = self._build_prompt(question_name, correct_answer)

        # 构建请求参数
        messages = [{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{base64_image}"
                    }
                },
                {"type": "text", "text": prompt}
            ]
        }]

        # 构建 extra_body 参数
        extra_body = {}
        if self.enable_thinking:
            extra_body["enable_thinking"] = True
            extra_body["thinking_budget"] = self.thinking_budget

        try:
            # 发起请求（非流式，简化处理）
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=False,
                extra_body=extra_body if extra_body else None
            )

            # 提取评分结果
            result = completion.choices[0].message.content.strip()

            # 从结果中提取数字
            numbers = re.findall(r'\d+', result)
            if numbers:
                return numbers[0]

            # 如果没有提取到数字，返回原结果
            return result

        except Exception as e:
            raise ScorerError(f"阿里百炼 API 调用失败: {e}")


class MockScorer(BaseScorer):
    """
    模拟评分器（用于测试）

    返回随机分数，不调用真实 API。
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.min_score = self.config.get("min_score", 60)
        self.max_score = self.config.get("max_score", 100)

    def score(self, image_path: str, question_name: str, correct_answer: Optional[str]) -> str:
        """返回随机评分"""
        if not os.path.exists(image_path):
            raise ScorerError(f"截图文件不存在: {image_path}")

        mock_score = random.randint(self.min_score, self.max_score)
        return str(mock_score)


class ScorerFactory:
    """
    评分器工厂类

    根据配置创建对应的评分器实例。
    """

    _scorers = {
        "dashscope": DashScopeScorer,
        "mock": MockScorer,
    }

    @classmethod
    def create_scorer(cls, provider: str = "mock", config: Optional[Dict[str, Any]] = None) -> BaseScorer:
        """
        创建评分器实例

        Args:
            provider: 模型提供商名称 (dashscope, mock)
            config: 模型配置字典

        Returns:
            BaseScorer 实例

        Raises:
            ScorerError: 不支持的提供商时抛出
        """
        provider = provider.lower()

        if provider not in cls._scorers:
            raise ScorerError(
                f"不支持的模型提供商: {provider}. "
                f"支持的提供商: {', '.join(cls._scorers.keys())}"
            )

        scorer_class = cls._scorers[provider]
        return scorer_class(config)

    @classmethod
    def register_scorer(cls, name: str, scorer_class: type):
        """
        注册新的评分器实现（用于扩展）

        Args:
            name: 提供商名称
            scorer_class: 继承自 BaseScorer 的类
        """
        if not issubclass(scorer_class, BaseScorer):
            raise ValueError("评分器类必须继承自 BaseScorer")
        cls._scorers[name.lower()] = scorer_class


# 全局评分器实例（用于保持向后兼容的函数接口）
_default_scorer: Optional[BaseScorer] = None


def set_default_scorer(scorer: BaseScorer) -> None:
    """设置默认评分器实例"""
    global _default_scorer
    _default_scorer = scorer


def score_image(image_path: str, question_name: str = "题目", correct_answer: Optional[str] = None) -> str:
    """
    对截图进行评分（兼容旧接口）

    如果未设置默认评分器，则使用 MockScorer。

    Args:
        image_path: 截图文件路径
        question_name: 题目名称
        correct_answer: 正确答案

    Returns:
        评分结果字符串
    """
    global _default_scorer

    if _default_scorer is None:
        _default_scorer = MockScorer()

    return _default_scorer.score(image_path, question_name, correct_answer)


def score_image_with_retry(
    image_path: str,
    question_name: str = "题目",
    correct_answer: Optional[str] = None,
    max_retries: int = 3,
    default_score: str = "80"
) -> str:
    """
    带重试机制的评分函数（兼容旧接口）

    Args:
        image_path: 截图文件路径
        question_name: 题目名称
        correct_answer: 正确答案
        max_retries: 最大重试次数
        default_score: 评分失败时的默认分数

    Returns:
        评分结果字符串
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            score = score_image(image_path, question_name, correct_answer)
            return score
        except ScorerError as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(1 * (attempt + 1))  # 指数退避
            continue

    # 所有重试都失败，返回默认分数并记录错误
    print(f"警告: 评分失败 ({last_error})，使用默认分数: {default_score}")
    return default_score


def validate_score(score: str, min_score: int = 0, max_score: int = 100) -> str:
    """
    验证并格式化评分结果

    Args:
        score: 原始评分字符串
        min_score: 最小有效分数
        max_score: 最大有效分数

    Returns:
        验证后的评分字符串
    """
    # 尝试提取数字
    numbers = re.findall(r'\d+', score)

    if numbers:
        try:
            num_score = int(numbers[0])
            # 限制在有效范围内
            num_score = max(min_score, min(max_score, num_score))
            return str(num_score)
        except ValueError:
            pass

    # 如果不是数字，直接返回原字符串（可能是等级制如 A/B/C）
    return score.strip()
