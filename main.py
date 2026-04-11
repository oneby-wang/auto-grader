#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyAutoGUI 自动化评分脚本

使用方法:
    python main.py [--config CONFIG_PATH] [--pages TOTAL_PAGES]

参数:
    --config, -c    配置文件路径 (默认: config.json)
    --pages, -p     覆盖配置中的总页面数

示例:
    python main.py
    python main.py --config my_config.json
    python main.py --pages 20

功能:
    1. 根据配置文件循环处理多个页面
    2. 每个页面截取指定区域截图
    3. 调用多模态大模型进行评分（预留接口）
    4. 在指定输入框输入评分
    5. 点击下一题/提交按钮
"""

import sys
import os

# 确保可以导入 grader 包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from grader.config_loader import GraderConfig, ConfigError
from grader.automation import AutoGrader, AutomationError


def main():
    """主函数"""
    import argparse

    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description='PyAutoGUI 自动化评分脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
注意事项:
  - 运行前请确保已正确配置 config.json 文件
  - 确保目标应用窗口已打开且可见
  - 运行过程中将鼠标移到屏幕左上角可紧急停止
  - 运行过程中请勿操作鼠标和键盘
        '''
    )

    parser.add_argument(
        '-c', '--config',
        default='config.json',
        help='配置文件路径 (默认: config.json)'
    )

    parser.add_argument(
        '-p', '--pages',
        type=int,
        default=None,
        help='覆盖配置中的总页面数'
    )

    parser.add_argument(
        '--version',
        action='version',
        version='%(prog)s 1.0.0'
    )

    args = parser.parse_args()

    # 检查配置文件路径
    config_path = args.config
    if not os.path.isabs(config_path):
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), config_path)

    try:
        # 加载配置
        print(f"加载配置文件: {config_path}")
        config = GraderConfig(config_path)

        # 如果命令行指定了页面数，覆盖配置
        if args.pages is not None:
            if args.pages <= 0:
                print("错误: 页面数必须大于 0")
                sys.exit(1)
            config.total_pages = args.pages
            print(f"命令行覆盖: 总页面数 = {args.pages}")

        # 验证配置
        if not config.validate():
            print("错误: 配置验证失败")
            sys.exit(1)

        print(f"配置加载成功: {config}")

        # 运行评分器
        grader = AutoGrader(config)
        grader.run()

    except ConfigError as e:
        print(f"配置错误: {e}")
        sys.exit(1)

    except AutomationError as e:
        print(f"自动化错误: {e}")
        sys.exit(1)

    except KeyboardInterrupt:
        print("\n用户中断执行")
        sys.exit(0)

    except Exception as e:
        print(f"未知错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
