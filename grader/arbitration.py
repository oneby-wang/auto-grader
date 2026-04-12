"""
仲裁模块 - 多模型评分结果仲裁与异常检测
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from .scorer import ScoreResult


@dataclass
class ArbitrationResult:
    """仲裁结果"""
    is_consistent: bool  # 是否一致（无异常）
    final_score: float  # 根据策略计算的最终分数
    avg_score: float  # 平均分
    max_score: float  # 最高分数
    min_score: float  # 最低分数
    max_diff: float  # 最大分差
    strategy: str  # 使用的仲裁策略
    threshold: float  # 异常检测阈值
    anomalies: List[str]  # 异常模型列表
    model_results: Dict[str, ScoreResult]  # 各模型原始结果


class ScoreArbitrator:
    """评分仲裁器 - 处理多模型评分结果的仲裁"""

    def __init__(self, threshold: float, strategy: str = "avg"):
        """
        初始化仲裁器

        Args:
            threshold: 异常检测阈值（分数差超过此值视为异常）
            strategy: 仲裁策略，可选 "max"、"min"、"avg"
        """
        self.threshold = threshold
        self.strategy = strategy

        if strategy not in ("max", "min", "avg"):
            raise ValueError(f"不支持的仲裁策略: {strategy}，必须是 'max'、'min' 或 'avg'")

    def arbitrate(self, results: Dict[str, ScoreResult]) -> ArbitrationResult:
        """
        仲裁多个模型的评分结果

        Args:
            results: {model_provider: ScoreResult}

        Returns:
            ArbitrationResult 包含仲裁结果和异常检测信息
        """
        if not results:
            raise ValueError("评分结果不能为空")

        # 提取所有分数
        scores = {provider: result.score for provider, result in results.items()}

        # 计算统计值
        score_values = list(scores.values())
        avg_score = sum(score_values) / len(score_values)
        max_score = max(score_values)
        min_score = min(score_values)
        max_diff = max_score - min_score

        # 检测异常（分差超过阈值的模型）
        anomalies = []
        for provider, score in scores.items():
            # 计算该模型与其他模型的平均分差
            other_scores = [s for p, s in scores.items() if p != provider]
            if other_scores:
                avg_other = sum(other_scores) / len(other_scores)
                if abs(score - avg_other) > self.threshold:
                    anomalies.append(provider)

        # 判断是否一致（无异常）
        is_consistent = len(anomalies) == 0 and max_diff <= self.threshold

        # 根据策略计算最终分数
        if self.strategy == "max":
            final_score = max_score
        elif self.strategy == "min":
            final_score = min_score
        else:  # avg
            final_score = avg_score

        return ArbitrationResult(
            is_consistent=is_consistent,
            final_score=final_score,
            avg_score=avg_score,
            max_score=max_score,
            min_score=min_score,
            max_diff=max_diff,
            strategy=self.strategy,
            threshold=self.threshold,
            anomalies=anomalies,
            model_results=results
        )

    def __repr__(self):
        return f"ScoreArbitrator(threshold={self.threshold}, strategy={self.strategy})"
