"""
自动化操作模块 - 核心的自动化流程控制
"""

import os
import platform
import time

try:
    import pyautogui
    # 设置 pyautogui 安全模式，防止意外操作
    pyautogui.FAILSAFE = True  # 鼠标移到左上角会抛出异常停止程序
    pyautogui.PAUSE = 0.1  # 每个操作后的默认延迟
except ImportError:
    pyautogui = None

from typing import Dict, List
from .config_loader import GraderConfig, QuestionConfig
from .screenshot import take_screenshot_safe
from .scorer import (
    ScorerFactory, BaseScorer, ScoreResult,
    score_image_with_retry, validate_score,
    set_default_scorer
)
from .arbitration import ScoreArbitrator


class AutomationError(Exception):
    """自动化操作错误异常"""
    pass


class AutoGrader:
    """自动化评分器主类"""

    def __init__(self, config: GraderConfig):
        self.config = config
        self.results: List[Dict] = []  # 存储每道题的评分结果
        self.results_by_model: Dict[str, List[Dict]] = {}  # 按模型存储结果
        self.arbitration_results: List[Dict] = []  # 仲裁结果

        if pyautogui is None:
            raise AutomationError("未安装 pyautogui，请运行: pip install pyautogui")

        # 获取屏幕尺寸用于验证坐标
        self.screen_width, self.screen_height = pyautogui.size()
        print(f"屏幕分辨率: {self.screen_width}x{self.screen_height}")

        # 初始化评分器（支持多模型）
        self.scorers: Dict[str, BaseScorer] = self._init_scorers()

    def _init_scorers(self) -> Dict[str, BaseScorer]:
        """
        根据配置初始化多个评分器

        Returns:
            {provider: BaseScorer} 字典
        """
        scorers = {}

        for provider in self.config.model_providers:
            model_config = self.config.get_scorer_config(provider)

            print(f"初始化评分模型: {provider}")
            if provider == "dashscope":
                print("  提示: 请确保已设置 DASHSCOPE_API_KEY 环境变量")
            elif provider == "volcengine":
                print("  提示: 请确保已设置 VOLCENGINE_API_KEY 环境变量")

            try:
                scorer = ScorerFactory.create_scorer(provider, model_config)
                scorers[provider] = scorer
                # 设置第一个为默认评分器，以便兼容旧接口
                if len(scorers) == 1:
                    set_default_scorer(scorer)
            except Exception as e:
                print(f"  警告: 初始化评分器 {provider} 失败: {e}")
                if provider == "mock":
                    raise  # mock 评分器不应该失败

        if not scorers:
            print("所有评分器初始化失败，使用模拟评分器")
            fallback_scorer = ScorerFactory.create_scorer("mock")
            scorers["mock"] = fallback_scorer
            set_default_scorer(fallback_scorer)

        return scorers

    def _validate_coordinate(self, x: int, y: int, name: str) -> None:
        """验证坐标是否在屏幕范围内"""
        if x < 0 or x >= self.screen_width:
            raise AutomationError(f"坐标 {name} x={x} 超出屏幕范围 (0-{self.screen_width})")
        if y < 0 or y >= self.screen_height:
            raise AutomationError(f"坐标 {name} y={y} 超出屏幕范围 (0-{self.screen_height})")

    def _click_at(self, x: int, y: int, description: str = "") -> None:
        """在指定坐标点击"""
        self._validate_coordinate(x, y, description or "点击位置")
        print(f"  点击 {description}: ({x}, {y})")
        pyautogui.click(x, y)
        time.sleep(0.2)  # 点击后短暂等待

    def _input_text(self, x: int, y: int, text: str, description: str = "输入框") -> None:
        """在指定输入框输入文本"""
        # 先点击输入框
        self._click_at(x, y, description)

        # 清除已有内容 (Mac 用 Command+A，其他用 Ctrl+A 全选，然后 Delete 删除)
        select_key = 'command' if platform.system() == 'Darwin' else 'ctrl'
        pyautogui.hotkey(select_key, 'a')
        pyautogui.press('delete')

        # 输入文本
        print(f"  输入: '{text}'")
        pyautogui.typewrite(str(text), interval=0.01)
        time.sleep(0.2)

    def _take_screenshot_for_question(
        self,
        question: QuestionConfig,
        page_index: int
    ) -> str:
        """为题目的指定区域截图"""
        print(f"  截图区域: {question.screenshot_area}")

        # 等待页面稳定
        time.sleep(self.config.delay_before_screenshot)

        screenshot_path = take_screenshot_safe(
            region=question.screenshot_area,
            save_dir=self.config.screenshot_dir,
            page_index=page_index,
            question_name=question.name
        )

        print(f"  截图保存: {screenshot_path}")
        return screenshot_path

    def _score_screenshot_multi(self, screenshot_path: str, question: QuestionConfig) -> Dict[str, ScoreResult]:
        """
        使用多个模型对截图进行评分

        Args:
            screenshot_path: 截图文件路径
            question: 题目配置

        Returns:
            {provider: ScoreResult} 各模型的评分结果
        """
        print(f"  调用评分模型...")
        print(f"  题目: {question.name}")
        print(f"  满分值: {question.max_score}")
        if question.correct_answer:
            print(f"  正确答案: {question.correct_answer}")

        results = {}

        for provider, scorer in self.scorers.items():
            print(f"  使用模型 [{provider}] 评分...")
            score_start = time.time()
            try:
                result = scorer.score(
                    image_path=screenshot_path,
                    question_name=question.name,
                    correct_answer=question.correct_answer,
                    max_score=question.max_score,
                    prompt_template=question.prompt
                )
                result = validate_score(result, max_score=question.max_score)
                print(f"    [{provider}] 评分: {result.score} (耗时: {time.time() - score_start:.2f}s)")
                results[provider] = result
            except Exception as e:
                print(f"    [{provider}] 评分出错: {e}")
                # 使用带重试的兼容接口
                result = score_image_with_retry(
                    screenshot_path,
                    question_name=question.name,
                    correct_answer=question.correct_answer,
                    max_score=question.max_score,
                    prompt_template=question.prompt
                )
                print(f"    [{provider}] 评分完成: {result.score} (耗时: {time.time() - score_start:.2f}s)")
                results[provider] = result

        return results

    def _input_score(self, question: QuestionConfig, score: float) -> None:
        """在指定输入框输入评分"""
        x, y = question.input_box
        self._input_text(x, y, str(score), f"'{question.name}' 评分输入框")

    def process_question(
        self,
        page_index: int,
        question_index: int,
        question: QuestionConfig
    ) -> dict:
        """
        处理单道题目

        Args:
            page_index: 当前页索引（从0开始）
            question_index: 当前题目索引（该页内的第几题，从0开始）
            question: 题目配置

        Returns:
            处理结果字典
        """
        print(f"\n  处理第 {question_index + 1}/{len(self.config.questions)} 题: {question.name}")

        result = {
            "page": page_index + 1,
            "question_index": question_index + 1,
            "question": question.name,
            "correct_answer": question.correct_answer,
            "screenshot": None,
            "score": None,
            "recognized_text": None,
            "model_scores": {},
            "arbitration": None,
            "success": False,
            "error": None
        }

        try:
            # 1. 截图
            screenshot_path = self._take_screenshot_for_question(question, page_index)
            result["screenshot"] = screenshot_path

            # 2. 评分（调用所有模型）
            model_results = self._score_screenshot_multi(screenshot_path, question)

            # 记录各模型评分
            for provider, score_result in model_results.items():
                result["model_scores"][provider] = {
                    "score": score_result.score,
                    "recognized_text": score_result.recognized_text
                }

            # 3. 仲裁（多模型时）
            is_multi_model = len(self.scorers) > 1
            if is_multi_model and question.arbitration:
                arbitrator = ScoreArbitrator(
                    threshold=question.arbitration.score_diff_threshold,
                    strategy=question.arbitration.strategy
                )
                arb_result = arbitrator.arbitrate(model_results)

                result["arbitration"] = {
                    "is_consistent": arb_result.is_consistent,
                    "final_score": arb_result.final_score,
                    "avg_score": arb_result.avg_score,
                    "max_score": arb_result.max_score,
                    "min_score": arb_result.min_score,
                    "max_diff": arb_result.max_diff,
                    "strategy": arb_result.strategy,
                    "threshold": arb_result.threshold,
                    "anomalies": arb_result.anomalies
                }

                final_score = arb_result.final_score
                print(f"  仲裁结果: 最终分数={final_score}, 策略={arb_result.strategy}, 一致性={arb_result.is_consistent}")
            else:
                # 单模型时直接使用该模型的分数
                first_result = list(model_results.values())[0]
                final_score = first_result.score
                result["recognized_text"] = first_result.recognized_text

            result["score"] = final_score

            # 4. 输入评分
            self._input_score(question, final_score)

            result["success"] = True
            print(f"  ✓ 第 {question_index + 1} 题处理完成")

        except Exception as e:
            result["error"] = str(e)
            print(f"  ✗ 第 {question_index + 1} 题处理失败: {e}")
            raise

        return result

    def run(self) -> None:
        """运行完整的自动化流程"""
        print("\n" + "="*60)
        print("PyAutoGUI 自动化评分脚本")
        print("="*60)
        print(f"\n配置信息:")
        print(f"  总页面数: {self.config.total_pages}")
        print(f"  每页题目数: {len(self.config.questions)}")
        print(f"  下一页按钮: {self.config.next_button}")
        print(f"  模型提供商: {', '.join(self.config.model_providers)}")
        print(f"  页面间延迟: {self.config.delay_between_pages}秒")
        print(f"  截图保存目录: {self.config.screenshot_dir}")

        # 打印题目信息
        print(f"\n题目配置:")
        for q in self.config.questions:
            correct = f" (答案: {q.correct_answer})" if q.correct_answer else ""
            print(f"  - {q.name}{correct}")

        print(f"\n注意事项:")
        print("  - 请将鼠标移到屏幕左上角可紧急停止程序")
        print("  - 确保目标应用窗口已打开且可见")
        print("  - 不要在运行过程中操作鼠标和键盘")
        print("\n5秒后开始执行...")

        # 倒计时，给用户时间准备
        for i in range(5, 0, -1):
            print(f"  {i}...")
            time.sleep(1)

        print("\n开始执行!")

       # 外层循环：遍历每一页
        for page_index in range(self.config.total_pages):

            print(f"\n{'='*50}")
            print(f"处理第 {page_index + 1}/{self.config.total_pages} 页")
            print(f"{'='*50}")

            # 内层循环：遍历该页的每道题目
            for question_index, question in enumerate(self.config.questions):
                try:
                    result = self.process_question(
                        page_index=page_index,
                        question_index=question_index,
                       question=question
                    )
                    self.results.append(result)

                except Exception as e:
                    # 记录失败结果
                    self.results.append({
                        "page": page_index + 1,
                        "question_index": question_index + 1,
                        "question": question.name,
                        "correct_answer": question.correct_answer,
                        "screenshot": None,
                        "score": None,
                        "recognized_text": None,
                        "success": False,
                        "error": str(e)
                    })

                    print(f"\n错误: 处理第 {page_index + 1} 页第 {question_index + 1} 题时发生异常")
                    print(f"异常信息: {e}")

                    # 询问是否继续
                    response = input("是否继续处理下一题? (y/n): ").strip().lower()
                    if response not in ('y', 'yes', '是'):
                        print("用户取消，停止执行")
                        return  # 完全退出

            # 点击下一页按钮（最后一页不需要）
            if page_index < self.config.total_pages - 1:
                self._click_at(
                    self.config.next_button[0],
                    self.config.next_button[1],
                    "下一页按钮"
                )

            print(f"  等待 {self.config.delay_between_pages} 秒加载下一页...")
            time.sleep(self.config.delay_between_pages)

        # 输出统计结果
        self._print_summary()

    def _print_summary(self) -> None:
        """打印执行摘要"""
        print("\n" + "="*60)
        print("执行完成摘要")
        print("="*60)

        total = len(self.results)
        success = sum(1 for r in self.results if r["success"])
        failed = total - success

        print(f"\n总题目数: {total}")
        print(f"成功: {success}")
        print(f"失败: {failed}")

        # 多模型时显示对比表
        is_multi_model = len(self.scorers) > 1
        if is_multi_model and total > 0:
            print(f"\n各模型评分对比:")
            print(f"{'页':<4} {'题':<4} {'名称':<10}", end="")
            for provider in self.scorers.keys():
                print(f" {provider:<12}", end="")
            print(f" {'最终分':<8} {'差异':<8} {'状态'}")
            print("-" * 80)

            for r in self.results:
                if not r["success"]:
                    continue
                print(f"{r['page']:<4} {r['question_index']:<4} {r['question']:<10}", end="")
                for provider in self.scorers.keys():
                    model_score = r.get("model_scores", {}).get(provider, {}).get("score", "N/A")
                    print(f" {str(model_score):<12}", end="")
                arb = r.get("arbitration")
                if arb:
                    print(f" {arb['final_score']:<8.1f} {arb['max_diff']:<8.1f} {'一致' if arb['is_consistent'] else '异常'}")
                else:
                    print(f" {r.get('score', 'N/A'):<8} {'N/A':<8} {'-'}")

            # 显示异常题目
            anomalies = [r for r in self.results if r.get("arbitration") and not r["arbitration"]["is_consistent"]]
            if anomalies:
                print(f"\n⚠️  需要人工介入的题目（分差超过阈值）:")
                for r in anomalies:
                    arb = r["arbitration"]
                    print(f"  第 {r['page']} 页 第 {r['question_index']} 题 ({r['question']}): "
                          f"分差={arb['max_diff']:.1f}, 异常模型={', '.join(arb['anomalies'])}")

        # 保存结果到文件
        self._save_results()

    def _save_results(self) -> None:
        """将结果保存到 JSON 文件（每个模型单独保存）"""
        import json
        from datetime import datetime

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        is_multi_model = len(self.scorers) > 1

        if is_multi_model:
            # 多模型时，每个模型单独保存
            for provider in self.scorers.keys():
                results_file = os.path.join(
                    self.config.screenshot_dir,
                    f"results_{provider}_{timestamp}.json"
                )

                # 提取该模型的结果
                model_results = []
                for r in self.results:
                    model_result = {
                        "page": r["page"],
                        "question_index": r["question_index"],
                        "question": r["question"],
                        "correct_answer": r["correct_answer"],
                        "screenshot": r["screenshot"],
                        "score": r.get("model_scores", {}).get(provider, {}).get("score"),
                        "recognized_text": r.get("model_scores", {}).get(provider, {}).get("recognized_text"),
                        "success": r["success"],
                        "error": r["error"]
                    }
                    model_results.append(model_result)

                output = {
                    "timestamp": datetime.now().isoformat(),
                    "config": self.config.config_path,
                    "model_provider": provider,
                    "total_pages": self.config.total_pages,
                    "questions_per_page": len(self.config.questions),
                    "total_questions": len(model_results),
                    "results": model_results
                }

                with open(results_file, 'w', encoding='utf-8') as f:
                    json.dump(output, f, ensure_ascii=False, indent=2)

                print(f"\n[{provider}] 结果已保存: {results_file}")

            # 保存仲裁结果
            arbitration_file = os.path.join(
                self.config.screenshot_dir,
                f"results_arbitration_{timestamp}.json"
            )

            arbitration_output = {
                "timestamp": datetime.now().isoformat(),
                "config": self.config.config_path,
                "model_providers": list(self.scorers.keys()),
                "total_pages": self.config.total_pages,
                "questions_per_page": len(self.config.questions),
                "total_questions": len(self.results),
                "results": self.results
            }

            with open(arbitration_file, 'w', encoding='utf-8') as f:
                json.dump(arbitration_output, f, ensure_ascii=False, indent=2)

            print(f"[arbitration] 结果已保存: {arbitration_file}")
        else:
            # 单模型时，直接保存
            provider = list(self.scorers.keys())[0]
            results_file = os.path.join(
                self.config.screenshot_dir,
                f"results_{provider}_{timestamp}.json"
            )

            output = {
                "timestamp": datetime.now().isoformat(),
                "config": self.config.config_path,
                "model_provider": provider,
                "total_pages": self.config.total_pages,
                "questions_per_page": len(self.config.questions),
                "total_questions": len(self.results),
                "results": self.results
            }

            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(output, f, ensure_ascii=False, indent=2)

            print(f"\n详细结果已保存: {results_file}")


def run_grader(config_path: str) -> None:
    """
    运行评分器的便捷函数

    Args:
        config_path: 配置文件路径
    """
    # 加载配置
    config = GraderConfig(config_path)

    # 创建并运行评分器
    grader = AutoGrader(config)
    grader.run()
