"""
评分模块 - 多模态大模型评分接口（预留）

此模块预留了调用多模态大模型的接口，后续接入实际的模型 API。
"""

import os
import random
from typing import Optional


class ScorerError(Exception):
    """评分错误异常"""
    pass


def score_image(image_path: str) -> str:
    """
    调用多模态大模型对截图进行评分

    TODO: 接入实际的多模态大模型 API
    当前返回模拟评分用于测试

    Args:
        image_path: 截图文件路径

    Returns:
        评分结果字符串（如 "90"、"A"、"优秀" 等）

    Raises:
        ScorerError: 评分失败时抛出
    """
    if not os.path.exists(image_path):
        raise ScorerError(f"截图文件不存在: {image_path}")

    # TODO: 在这里接入实际的多模态大模型 API
    # 示例实现思路:
    #
    # 1. OpenAI GPT-4 Vision 方式:
    #    import openai
    #    with open(image_path, "rb") as f:
    #        response = openai.chat.completions.create(
    #            model="gpt-4-vision-preview",
    #            messages=[{
    #                "role": "user",
    #                "content": [
    #                    {"type": "text", "text": "请为这道题评分，只返回数字分数(0-100)"},
    #                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
    #                ]
    #            }]
    #        )
    #    return response.choices[0].message.content.strip()
    #
    # 2. Claude 方式:
    #    import anthropic
    #    client = anthropic.Anthropic()
    #    with open(image_path, "rb") as f:
    #        response = client.messages.create(
    #            model="claude-3-opus-20240229",
    #            max_tokens=100,
    #            messages=[{
    #                "role": "user",
    #                "content": [
    #                    {"type": "text", "text": "请为这道题评分，只返回数字分数(0-100)"},
    #                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64_image}}
    #                ]
    #            }]
    #        )
    #    return response.content[0].text.strip()
    #
    # 3. 本地模型方式:
    #    from transformers import pipeline
    #    scorer = pipeline("image-to-text", model="your-model")
    #    result = scorer(image_path)
    #    return parse_score(result)

    # 当前返回模拟评分（60-100之间随机）
    # 实际使用时删除以下代码，替换为真实模型调用
    mock_score = random.randint(60, 100)
    return str(mock_score)


def score_image_with_retry(
    image_path: str,
    max_retries: int = 3,
    default_score: str = "80"
) -> str:
    """
    带重试机制的评分函数

    Args:
        image_path: 截图文件路径
        max_retries: 最大重试次数
        default_score: 评分失败时的默认分数

    Returns:
        评分结果字符串
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            score = score_image(image_path)
            return score
        except ScorerError as e:
            last_error = e
            if attempt < max_retries - 1:
                import time
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
    import re
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
