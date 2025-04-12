#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import time
import threading
import importlib.util
import asyncio
import logging

# 配置日志
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("启动器")

def run_script_in_thread(script_name):
    """在线程中运行Python脚本"""
    logger.info(f"正在加载 {script_name}...")
    try:
        # 动态导入Python模块
        spec = importlib.util.spec_from_file_location(script_name.replace('.py', ''), script_name)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # 创建一个新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # 运行main函数
        logger.info(f"正在启动 {script_name}...")
        loop.run_until_complete(module.main())
        
    except Exception as e:
        logger.error(f"运行 {script_name} 时出错: {e}")
        import traceback
        logger.error(traceback.format_exc())

def main():
    print("\n" + "="*50)
    logger.info("Telegram 消息转发工具启动器")
    print("="*50 + "\n")
    
    # 检查.env文件是否存在
    if not os.path.exists('.env'):
        logger.error("未找到.env配置文件！请先创建.env文件并设置必要的配置项。")
        return
    
    # 创建线程
    threads = []
    
    # 启动频道转发器线程
    channel_thread = threading.Thread(
        target=run_script_in_thread, 
        args=('advanced_forwarder.py',),
        name="频道转发器线程"
    )
    channel_thread.daemon = True  # 设置为守护线程，主线程结束时会自动终止
    threads.append(channel_thread)
    
    # 启动群组聊天模拟器线程
    group_thread = threading.Thread(
        target=run_script_in_thread, 
        args=('group_chat_simulator.py',),
        name="群组聊天模拟器线程"
    )
    group_thread.daemon = True  # 设置为守护线程，主线程结束时会自动终止
    threads.append(group_thread)
    
    # 依次启动线程，加点延迟避免冲突
    logger.info("正在启动所有服务...")
    channel_thread.start()
    time.sleep(2)  # 等待频道转发器初始化
    group_thread.start()
    
    logger.info("所有服务已启动！")
    print("\n" + "="*50)
    logger.info("提示: 按Ctrl+C可以停止所有服务")
    print("="*50 + "\n")
    
    try:
        # 等待所有线程结束(实际上不会结束除非程序被中断)
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        logger.info("收到停止信号，正在关闭所有服务...")
        # 线程设置为守护线程，主线程结束时会自动终止
        logger.info("所有服务已停止")

if __name__ == "__main__":
    main() 