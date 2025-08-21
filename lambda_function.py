#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AWS Lambda function for Feishu bot integration
重构版本 - 使用模块化架构
"""

import json
from typing import Dict, Any

from utils import get_config, get_logger, handle_exception, safe_json_loads, create_response
from ticket_handler import get_ticket_handler

# AWS客户端初始化已移至 aws_service.py 模块

# 飞书API相关功能已移至 feishu_service.py 模块

# 工单相关功能已移至 ticket_handler.py 模块

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda主处理函数 - 重构版本
    使用模块化架构处理飞书机器人请求
    """
    logger = get_logger(__name__)
    config = get_config()
    
    try:
        # 解析请求
        path = event.get('path', '')
        http_method = event.get('httpMethod', '')
        body = safe_json_loads(event.get('body', '{}'))
        
        logger.info(f"收到请求: {http_method} {path}")
        
        # 获取工单处理器
        ticket_handler = get_ticket_handler()
        
        # 处理飞书webhook请求
        if path == '/webhook' and http_method == 'POST':
            # 处理飞书验证请求
            if 'challenge' in body:
                logger.info("处理飞书验证请求")
                return create_response(200, {"challenge": body["challenge"]})
            
            # 处理飞书事件
            return ticket_handler.handle_feishu_event(body)
        
        # 处理卡片交互
        elif path == '/card_action' and http_method == 'POST':
            return ticket_handler.handle_card_action(body)
        
        # 默认返回404
        return create_response(404, {"error": "Not Found"})
        
    except Exception as e:
        logger.error(f"处理请求异常: {str(e)}")
        return create_response(500, {"error": f"服务器内部错误: {str(e)}"})

# 本地测试用
if __name__ == "__main__":
    # 模拟API Gateway事件
    test_event = {
        'path': '/webhook',
        'httpMethod': 'POST',
        'body': json.dumps({
            'challenge': 'test_challenge'
        })
    }
    
    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2, ensure_ascii=False))