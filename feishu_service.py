#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书API服务模块
封装所有飞书相关的API调用
使用lark-oapi SDK替代原生REST API调用
"""

import json
import time
from typing import Dict, List, Optional, Union

import lark_oapi as lark
from lark_oapi.api.im.v1 import *
from lark_oapi.api.auth.v3 import *

from utils import (
    get_config,
    FeishuAPIError, 
    get_logger, 
    handle_exception, 
    retry, 
    safe_json_loads,
    validate_required_fields
)


class FeishuService:
    """飞书API服务类"""
    
    def __init__(self):
        """初始化飞书服务"""
        self.config = get_config()
        self.logger = get_logger('feishu_service')
        self._access_token = None
        self._token_expires_at = 0
        
        # 验证配置
        feishu_config = self.config.get_feishu_config()
        validate_required_fields(
            feishu_config, 
            ['app_id', 'app_secret'], 
            "飞书配置不完整"
        )
        
        # 初始化lark客户端
        self._client = lark.Client.builder() \
            .app_id(feishu_config['app_id']) \
            .app_secret(feishu_config['app_secret']) \
            .log_level(lark.LogLevel.INFO) \
            .build()
    
    @handle_exception
    @retry(max_attempts=3, delay=1.0, exceptions=(Exception,))
    def get_access_token(self) -> str:
        """获取飞书访问令牌
        
        Returns:
            str: 访问令牌
            
        Raises:
            FeishuAPIError: 获取令牌失败时
        """
        # 检查令牌是否仍然有效
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token
        
        self.logger.info("获取飞书访问令牌")
        
        try:
            # 使用lark-oapi SDK获取访问令牌
            request = InternalTenantAccessTokenRequest.builder().build()
            response = self._client.auth.v3.tenant_access_token.internal(request)
            
            if not response.success():
                error_msg = f"获取访问令牌失败: {response.msg}"
                self.logger.error(error_msg, response_data=response.raw)
                raise FeishuAPIError(error_msg, response.code, response.raw)
            
            self._access_token = response.data.tenant_access_token
            # 设置令牌过期时间（提前5分钟刷新）
            expires_in = response.data.expire or 7200
            self._token_expires_at = time.time() + expires_in - 300
            
            self.logger.info("成功获取飞书访问令牌")
            return self._access_token
            
        except Exception as e:
            error_msg = f"请求飞书API失败: {str(e)}"
            self.logger.error(error_msg)
            # 处理lark-oapi SDK异常
            if hasattr(e, 'code') and hasattr(e, 'msg'):
                raise FeishuAPIError(f"获取访问令牌失败: {e.msg}", status_code=getattr(e, 'code', None)) from e
            else:
                raise FeishuAPIError(error_msg) from e
    
    @handle_exception
    @retry(max_attempts=2, delay=1.0, exceptions=(Exception,))
    def send_message(self, chat_id: str, msg_type: str, content: Dict) -> Dict:
        """发送飞书消息
        
        Args:
            chat_id: 聊天ID
            msg_type: 消息类型 (text, interactive等)
            content: 消息内容
            
        Returns:
            Dict: API响应结果
            
        Raises:
            FeishuAPIError: 发送消息失败时
        """
        validate_required_fields(
            {'chat_id': chat_id, 'msg_type': msg_type, 'content': content},
            ['chat_id', 'msg_type', 'content'],
            "发送消息参数不完整"
        )
        
        self.logger.info("发送飞书消息", chat_id=chat_id, msg_type=msg_type)
        
        try:
            # 使用lark-oapi SDK发送消息
            request = CreateMessageRequest.builder() \
                .receive_id_type("chat_id") \
                .request_body(CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type(msg_type)
                    .content(json.dumps(content, ensure_ascii=False))
                    .build()) \
                .build()
            
            response = self._client.im.v1.message.create(request)
            
            if not response.success():
                error_msg = f"发送消息失败: {response.msg}"
                self.logger.error(error_msg, response_data=response.raw)
                raise FeishuAPIError(error_msg, response.code, response.raw)
            
            self.logger.info("成功发送飞书消息", message_id=response.data.message_id)
            
            # 返回兼容原格式的响应
            return {
                "code": 0,
                "msg": "success",
                "data": {
                    "message_id": response.data.message_id
                }
            }
            
        except Exception as e:
            error_msg = f"发送飞书消息请求失败: {str(e)}"
            self.logger.error(error_msg)
            # 处理lark-oapi SDK异常
            if hasattr(e, 'code') and hasattr(e, 'msg'):
                raise FeishuAPIError(f"发送消息失败: {e.msg}", status_code=getattr(e, 'code', None)) from e
            else:
                raise FeishuAPIError(error_msg) from e
    
    @handle_exception
    @retry(max_attempts=2, delay=1.0, exceptions=(Exception,))
    def create_chat(self, chat_name: str, description: str = '', 
                   owner_id: str = '', user_list: List[str] = None) -> Optional[str]:
        """创建飞书群聊
        
        Args:
            chat_name: 群聊名称
            description: 群聊描述
            owner_id: 群主ID
            user_list: 用户ID列表
            
        Returns:
            Optional[str]: 群聊ID，创建失败返回None
            
        Raises:
            FeishuAPIError: 创建群聊失败时
        """
        validate_required_fields(
            {'chat_name': chat_name},
            ['chat_name'],
            "创建群聊参数不完整"
        )
        
        self.logger.info("创建飞书群聊", chat_name=chat_name, owner_id=owner_id)
        
        try:
            # 使用lark-oapi SDK创建群聊
            request_body = CreateChatRequestBody.builder() \
                .name(chat_name) \
                .description(description) \
                .chat_mode("group") \
                .chat_type("private") \
                .join_message_visibility("all_members") \
                .leave_message_visibility("all_members") \
                .membership_approval("no_approval_required")
            
            # 设置群主
            if owner_id:
                request_body.owner_id(owner_id)
            
            # 添加初始成员
            if user_list:
                request_body.user_id_list(user_list)
            
            request = CreateChatRequest.builder() \
                .request_body(request_body.build()) \
                .build()
            
            response = self._client.im.v1.chat.create(request)
            
            if not response.success():
                error_msg = f"创建群聊失败: {response.msg}"
                self.logger.error(error_msg, response_data=response.raw)
                raise FeishuAPIError(error_msg, response.code, response.raw)
            
            chat_id = response.data.chat_id
            if chat_id:
                self.logger.info("成功创建飞书群聊", chat_id=chat_id, chat_name=chat_name)
                return chat_id
            else:
                error_msg = "创建群聊成功但未返回群聊ID"
                self.logger.error(error_msg, response_data=response.raw)
                raise FeishuAPIError(error_msg, response.code, response.raw)
                
        except Exception as e:
            error_msg = f"创建群聊请求失败: {str(e)}"
            self.logger.error(error_msg)
            # 处理lark-oapi SDK异常
            if hasattr(e, 'code') and hasattr(e, 'msg'):
                raise FeishuAPIError(f"创建群聊失败: {e.msg}", status_code=getattr(e, 'code', None)) from e
            else:
                raise FeishuAPIError(error_msg) from e
    
    def create_ticket_card(self, title: str) -> Dict:
        """创建工单卡片
        
        Args:
            title: 工单标题
            
        Returns:
            Dict: 卡片配置
        """
        validate_required_fields(
            {'title': title},
            ['title'],
            "创建工单卡片参数不完整"
        )
        
        self.logger.info("创建工单卡片", title=title)
        
        card = {
            "config": {
                "wide_screen_mode": True
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "content": f"**🎫 创建AWS工单**\n\n📝 标题: {title}",
                        "tag": "lark_md"
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "content": "**请选择服务类型:**",
                        "tag": "lark_md"
                    }
                },
                {
                    "tag": "select_static",
                    "placeholder": {
                        "content": "选择AWS服务",
                        "tag": "plain_text"
                    },
                    "options": self._get_service_options(),
                    "value": {
                        "service": ""
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "content": "**请选择严重性级别:**",
                        "tag": "lark_md"
                    }
                },
                {
                    "tag": "select_static",
                    "placeholder": {
                        "content": "选择严重性级别",
                        "tag": "plain_text"
                    },
                    "options": self._get_severity_options(),
                    "value": {
                        "severity": ""
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "content": "提交工单",
                                "tag": "plain_text"
                            },
                            "type": "primary",
                            "value": json.dumps({
                                "action": "submit_ticket",
                                "title": title
                            })
                        }
                    ]
                }
            ],
            "header": {
                "template": "blue",
                "title": {
                    "content": "AWS工单系统",
                    "tag": "plain_text"
                }
            }
        }
        
        return card
    
    def _get_service_options(self) -> List[Dict]:
        """获取服务选项
        
        Returns:
            List[Dict]: 服务选项列表
        """
        return [
            {
                "text": {
                    "content": "Amazon EC2",
                    "tag": "plain_text"
                },
                "value": "amazon-elastic-compute-cloud-linux"
            },
            {
                "text": {
                    "content": "Amazon S3",
                    "tag": "plain_text"
                },
                "value": "amazon-simple-storage-service"
            },
            {
                "text": {
                    "content": "Amazon RDS",
                    "tag": "plain_text"
                },
                "value": "amazon-relational-database-service"
            },
            {
                "text": {
                    "content": "AWS Lambda",
                    "tag": "plain_text"
                },
                "value": "aws-lambda"
            },
            {
                "text": {
                    "content": "Amazon VPC",
                    "tag": "plain_text"
                },
                "value": "amazon-virtual-private-cloud"
            }
        ]
    
    def _get_severity_options(self) -> List[Dict]:
        """获取严重性选项
        
        Returns:
            List[Dict]: 严重性选项列表
        """
        return [
            {
                "text": {
                    "content": "🔴 紧急 (Critical)",
                    "tag": "plain_text"
                },
                "value": "critical"
            },
            {
                "text": {
                    "content": "🟠 高 (High)",
                    "tag": "plain_text"
                },
                "value": "high"
            },
            {
                "text": {
                    "content": "🟡 中 (Normal)",
                    "tag": "plain_text"
                },
                "value": "normal"
            },
            {
                "text": {
                    "content": "🟢 低 (Low)",
                    "tag": "plain_text"
                },
                "value": "low"
            }
        ]


# 全局飞书服务实例
_feishu_service = None


def get_feishu_service() -> FeishuService:
    """获取飞书服务实例
    
    Returns:
        FeishuService: 飞书服务实例
    """
    global _feishu_service
    if _feishu_service is None:
        _feishu_service = FeishuService()
    return _feishu_service