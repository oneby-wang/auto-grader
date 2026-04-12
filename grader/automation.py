"""
自动化操作模块 - 核心的自动化流程控制
"""

import os
import time

try:
    import pyautogui
    # 设置 pyautogui 安全模式，防止意外操作
    pyautogui.FAILSAFE = True  # 鼠标移到左上角会抛出异常停止程序
    pyautogui.PAUSE = 0.1  # 每个操作后的默认延迟
except ImportError:
    pyautogui = None

from .config_loader import GraderConfig, QuestionConfig
from .screenshot import take_screenshot_safe
from .scorer import (
    ScorerFactory, BaseScorer, ScoreResult,
    score_image_with_retry, validate_score,
    set_default_scorer
)


class AutomationError(Exception):
    """自动化操作错误异常"""
    pass


class AutoGrader:
    """自动化评分器主类"""

    def __init__(self, config: GraderConfig):
        self.config = config
        self.results = []  # 存储每页的评分结果

        if pyautogui is None:
            raise AutomationError("未安装 pyautogui，请运行: pip install pyautogui")

        # 获取屏幕尺寸用于验证坐标
        self.screen_width, self.screen_height = pyautogui.size()
        print(f"屏幕分辨率: {self.screen_width}x{self.screen_height}")

        # 初始化评分器
        self.scorer = self._init_scorer()

    def _init_scorer(self) -> BaseScorer:
        """
        根据配置初始化评分器

        Returns:
            BaseScorer 实例
        """
        provider = self.config.model_provider
        model_config = self.config.get_scorer_config()

        print(f"使用评分模型: {provider}")
        if provider == "dashscope":
            print("提示: 请确保已设置 DASHSCOPE_API_KEY 环境变量")

        try:
            scorer = ScorerFactory.create_scorer(provider, model_config)
            # 设置为默认评分器，以便兼容旧接口
            set_default_scorer(scorer)
            return scorer
        except Exception as e:
            print(f"警告: 初始化评分器失败: {e}")
            print("回退到模拟评分器")
            fallback_scorer = ScorerFactory.create_scorer("mock")
            set_default_scorer(fallback_scorer)
            return fallback_scorer

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

        # 清除已有内容 (Ctrl+A 全选，然后 Delete 删除)
        pyautogui.hotkey('ctrl', 'a')
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

    def _score_screenshot(self, screenshot_path: str, question: QuestionConfig) -> ScoreResult:
        """对截图进行评分"""
        print(f"  调用评分模型...")
        print(f"  题目: {question.name}")
        print(f"  满分值: {question.max_score}")
        if question.correct_answer:
            print(f"  正确答案: {question.correct_answer}")
        print(f"  使用配置的评分提示词")

        try:
            result = self.scorer.score(
                image_path=screenshot_path,
                question_name=question.name,
                correct_answer=question.correct_answer,
                max_score=question.max_score,
                prompt_template=question.prompt
            )
            result = validate_score(result, max_score=question.max_score)
            print(f"  获得评分: {result.score}")
            return result
        except Exception as e:
            print(f"  评分出错: {e}")
            # 使用带重试的兼容接口
            result = score_image_with_retry(
                screenshot_path,
                question_name=question.name,
                correct_answer=question.correct_answer,
                max_score=question.max_score,
                prompt_template=question.prompt
            )
            return result

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
            "success": False,
            "error": None
        }

        try:
            # 1. 截图
            screenshot_path = self._take_screenshot_for_question(question, page_index)
            result["screenshot"] = screenshot_path

            # 2. 评分（调用模型）
            score_result = self._score_screenshot(screenshot_path, question)
            result["score"] = score_result.score
            result["recognized_text"] = score_result.recognized_text

            # 3. 输入评分
            self._input_score(question, score_result.score)

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
        print(f"  模型提供商: {self.config.model_provider}")
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

        print(f"\n总页面数: {total}")
        print(f"成功: {success}")
        print(f"失败: {failed}")

        if total > 0:
            print(f"\n详细结果:")
            for r in self.results:
                status = "✓" if r["success"] else "✗"
                score_info = f" 评分: {r['score']}" if r["score"] is not None else ""
                correct_info = f" 答案: {r['correct_answer']}" if r.get("correct_answer") else ""
                error_info = f" 错误: {r['error']}" if r["error"] else ""
                q_index = r.get('question_index', '?')
                print(f"  {status} 第 {r['page']} 页 第 {q_index} 题 ({r['question']}){correct_info}{score_info}{error_info}")

        # 保存结果到文件
        self._save_results()

    def _save_results(self) -> None:
        """将结果保存到 JSON 文件"""
        import json
        from datetime import datetime

        results_file = os.path.join(
            self.config.screenshot_dir,
            f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

        output = {
            "timestamp": datetime.now().isoformat(),
            "config": self.config.config_path,
            "model_provider": self.config.model_provider,
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
