"""
截图模块 - 区域截图功能
"""

import os
import time
from datetime import datetime
from typing import Tuple

try:
    import pyautogui
except ImportError:
    pyautogui = None


class ScreenshotError(Exception):
    """截图错误异常"""
    pass


def take_screenshot(
    region: Tuple[int, int, int, int],
    save_dir: str,
    filename: str = None
) -> str:
    """
    截取指定区域的屏幕截图

    Args:
        region: 截图区域 (x, y, width, height)
        save_dir: 截图保存目录
        filename: 自定义文件名，默认为时间戳

    Returns:
        保存的截图文件路径

    Raises:
        ScreenshotError: 截图失败时抛出
    """
    if pyautogui is None:
        raise ScreenshotError("未安装 pyautogui，请运行: pip install pyautogui")

    # 确保保存目录存在
    os.makedirs(save_dir, exist_ok=True)

    # 生成文件名
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.png"

    # 确保文件名有正确的扩展名
    if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
        filename += ".png"

    save_path = os.path.join(save_dir, filename)

    try:
        # 截取指定区域
        # pyautogui.screenshot 的 region 参数: (left, top, width, height)
        screenshot = pyautogui.screenshot(region=region)
        screenshot.save(save_path)

        # 验证文件是否成功保存
        if not os.path.exists(save_path):
            raise ScreenshotError(f"截图保存失败: {save_path}")

        return save_path

    except Exception as e:
        raise ScreenshotError(f"截图失败: {e}")


def take_screenshot_safe(
    region: Tuple[int, int, int, int],
    save_dir: str,
    page_index: int,
    question_name: str
) -> str:
    """
    安全的截图函数，带错误处理和日志

    Args:
        region: 截图区域 (x, y, width, height)
        save_dir: 截图保存目录
        page_index: 当前页面索引
        question_name: 题目名称

    Returns:
        保存的截图文件路径
    """
    # 生成带序号的文件名
    timestamp = datetime.now().strftime("%H%M%S")
    safe_name = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in question_name)
    filename = f"page_{page_index + 1:03d}_{safe_name}_{timestamp}.png"

    return take_screenshot(region, save_dir, filename)
