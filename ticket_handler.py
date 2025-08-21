#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工单处理模块
处理工单的完整生命周期，整合飞书和AWS服务
"""

import json
import time
from typing import Dict, List, Optional, Any

from utils import (
    get_config,
    get_logger,
    handle_exception,
    safe_json_loads,
    validate_required_fields,
    format_timestamp,
    create_response,
    ValidationError,
    TicketError
)
from feishu_service import get_feishu_service
from aws_service import get_dynamodb_service, get_support_service


class TicketHandler:
    """工单处理器"""
    
    def __init__(self):
        """初始化工单处理器"""
        self.config = get_config()
        self.logger = get_logger('ticket_handler')
        self.feishu_service = get_feishu_service()
        self.dynamodb_service = get_dynamodb_service()
        self.support_service = get_support_service()
    
    @handle_exception
    def handle_create_ticket_command(self, chat_id: str, title: str) -> Dict[str, Any]:
        """处理创建工单命令
        
        Args:
            chat_id: 聊天ID
            title: 工单标题
            
        Returns:
            Dict[str, Any]: 处理结果
        """
        validate_required_fields(
            {'chat_id': chat_id, 'title': title},
            ['chat_id', 'title'],
            "创建工单参数不完整"
        )
        
        self.logger.info("处理创建工单命令", chat_id=chat_id, title=title)
        
        try:
            # 创建工单卡片
            card = self.feishu_service.create_ticket_card(title)
            
            # 发送卡片消息
            result = self.feishu_service.send_message(
                chat_id=chat_id,
                msg_type='interactive',
                content={'card': card}
            )
            
            if result.get('code') == 0:
                self.logger.info("成功发送工单创建卡片", chat_id=chat_id, title=title)
                return create_response(True, "工单创建卡片已发送")
            else:
                error_msg = f"发送工单卡片失败: {result.get('msg', '未知错误')}"
                self.logger.error(error_msg, result=result)
                return create_response(False, error_msg)
                
        except Exception as e:
            error_msg = f"处理创建工单命令失败: {str(e)}"
            self.logger.error(error_msg, chat_id=chat_id, title=title)
            return create_response(False, error_msg)
    
    @handle_exception
    def handle_card_action(self, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理卡片交互
        
        Args:
            action_data: 卡片交互数据
            
        Returns:
            Dict[str, Any]: 处理结果
        """
        self.logger.info("处理卡片交互", action_data=action_data)
        
        try:
            # 解析action数据
            action = action_data.get('action', {})
            
            # 解析action value
            action_value = self._parse_action_value(action.get('value', {}))
            action_type = action_value.get('action')
            
            if action_type == 'submit_ticket':
                return self._handle_submit_ticket(action_data, action_value)
            else:
                error_msg = f"未知的操作类型: {action_type}"
                self.logger.warning(error_msg, action_type=action_type)
                return create_response(False, error_msg)
                
        except Exception as e:
            error_msg = f"处理卡片交互失败: {str(e)}"
            self.logger.error(error_msg, action_data=action_data)
            return create_response(False, error_msg)
    
    @handle_exception
    def handle_history_command(self, chat_id: str, user_id: str) -> Dict[str, Any]:
        """处理历史工单查询命令
        
        Args:
            chat_id: 聊天ID
            user_id: 用户ID
            
        Returns:
            Dict[str, Any]: 处理结果
        """
        validate_required_fields(
            {'chat_id': chat_id, 'user_id': user_id},
            ['chat_id', 'user_id'],
            "查询历史工单参数不完整"
        )
        
        self.logger.info("处理历史工单查询", chat_id=chat_id, user_id=user_id)
        
        try:
            # 查询用户历史工单
            tickets = self.dynamodb_service.get_user_tickets(user_id)
            
            if not tickets:
                message = "暂无历史工单记录"
                self.feishu_service.send_message(
                    chat_id=chat_id,
                    msg_type='text',
                    content={'text': message}
                )
                return create_response(True, message)
            
            # 构建历史工单消息
            history_text = self._build_history_message(tickets)
            
            # 发送历史工单消息
            self.feishu_service.send_message(
                chat_id=chat_id,
                msg_type='text',
                content={'text': history_text}
            )
            
            self.logger.info(f"成功发送历史工单信息，共 {len(tickets)} 条记录", user_id=user_id)
            return create_response(True, f"已发送 {len(tickets)} 条历史工单记录")
            
        except Exception as e:
            error_msg = f"查询历史工单失败: {str(e)}"
            self.logger.error(error_msg, user_id=user_id)
            
            # 发送错误消息给用户
            self.feishu_service.send_message(
                chat_id=chat_id,
                msg_type='text',
                content={'text': error_msg}
            )
            
            return create_response(False, error_msg)
    
    @handle_exception
    def handle_content_command(self, chat_id: str, user_id: str, content: str) -> Dict[str, Any]:
        """处理工单内容添加命令
        
        Args:
            chat_id: 聊天ID
            user_id: 用户ID
            content: 工单内容
            
        Returns:
            Dict[str, Any]: 处理结果
        """
        validate_required_fields(
            {'chat_id': chat_id, 'user_id': user_id, 'content': content},
            ['chat_id', 'user_id', 'content'],
            "添加工单内容参数不完整"
        )
        
        self.logger.info("处理工单内容添加", chat_id=chat_id, user_id=user_id)
        
        try:
            # 简化版本：直接创建AWS工单
            # 在实际应用中，应该先查找对应的工单记录
            case_id = self.support_service.create_support_case(
                title="示例工单标题",
                service="amazon-elastic-compute-cloud-linux",
                severity="low",
                content=content
            )
            
            success_msg = f"工单已创建，AWS工单ID: {case_id}"
            
            # 发送成功消息
            self.feishu_service.send_message(
                chat_id=chat_id,
                msg_type='text',
                content={'text': success_msg}
            )
            
            self.logger.info("成功创建AWS工单", case_id=case_id, user_id=user_id)
            return create_response(True, success_msg)
            
        except Exception as e:
            error_msg = f"创建AWS工单失败: {str(e)}"
            self.logger.error(error_msg, user_id=user_id)
            
            # 发送错误消息给用户
            self.feishu_service.send_message(
                chat_id=chat_id,
                msg_type='text',
                content={'text': error_msg}
            )
            
            return create_response(False, error_msg)
    
    @handle_exception
    def handle_help_command(self, chat_id: str) -> Dict[str, Any]:
        """处理帮助命令
        
        Args:
            chat_id: 聊天ID
            
        Returns:
            Dict[str, Any]: 处理结果
        """
        self.logger.info("处理帮助命令", chat_id=chat_id)
        
        help_text = (
            "🤖 **AWS工单机器人帮助**\n\n"
            "**支持的命令:**\n"
            "• `开工单 [标题]` - 创建新工单\n"
            "• `内容 [详情]` - 添加工单详情\n"
            "• `历史` - 查看历史工单\n"
            "• `帮助` - 显示帮助信息\n\n"
            "**使用示例:**\n"
            "• 开工单 EC2实例无法启动\n"
            "• 内容 我的EC2实例在启动时出现错误...\n\n"
            "**功能特点:**\n"
            "• 自动创建讨论群聊\n"
            "• 支持多种AWS服务\n"
            "• 历史工单查询\n"
            "• 实时状态更新"
        )
        
        try:
            self.feishu_service.send_message(
                chat_id=chat_id,
                msg_type='text',
                content={'text': help_text}
            )
            
            self.logger.info("成功发送帮助信息", chat_id=chat_id)
            return create_response(True, "帮助信息已发送")
            
        except Exception as e:
            error_msg = f"发送帮助信息失败: {str(e)}"
            self.logger.error(error_msg, chat_id=chat_id)
            return create_response(False, error_msg)
    
    @handle_exception
    def handle_feishu_event(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """处理飞书事件
        
        Args:
            body: 飞书事件数据
            
        Returns:
            Dict[str, Any]: 处理结果
        """
        self.logger.info("处理飞书事件", body=body)
        
        try:
            # 解析飞书事件格式
            chat_id, text, user_id = self._parse_feishu_event(body)
            
            if not chat_id or not text or not user_id:
                self.logger.warning("飞书事件解析失败或缺少必要信息")
                return create_response(200, {"success": True, "message": "事件已接收但无需处理"})
            
            # 处理不同的命令
            if text.startswith('开工单'):
                title = text[3:].strip()
                if title:
                    return self.handle_create_ticket_command(chat_id, title)
                else:
                    self.feishu_service.send_message(
                        chat_id=chat_id,
                        msg_type='text',
                        content={'text': "请提供工单标题，例如：开工单 EC2实例无法启动"}
                    )
                    return create_response(200, {"success": True})
            
            elif text.startswith('内容'):
                content = text[2:].strip()
                if content:
                    return self.handle_content_command(chat_id, user_id, content)
                else:
                    self.feishu_service.send_message(
                        chat_id=chat_id,
                        msg_type='text',
                        content={'text': "请提供工单内容，例如：内容 我的EC2实例无法启动，错误信息为..."}
                    )
                    return create_response(200, {"success": True})
            
            elif text.strip() == '帮助':
                return self.handle_help_command(chat_id)
            
            elif text.strip() == '历史':
                return self.handle_history_command(chat_id, user_id)
            
            # 默认返回成功
            return create_response(200, {"success": True})
            
        except Exception as e:
            error_msg = f"处理飞书事件失败: {str(e)}"
            self.logger.error(error_msg, body=body)
            return create_response(500, {"error": error_msg})
    
    def _parse_feishu_event(self, body: Dict[str, Any]) -> tuple:
        """解析飞书事件
        
        Args:
            body: 飞书事件数据
            
        Returns:
            tuple: (chat_id, text, user_id)
        """
        chat_id = ''
        text = ''
        user_id = ''
        
        try:
            # 处理2.0版本API格式
            if 'header' in body and 'event' in body:
                self.logger.info("检测到飞书API 2.0格式")
                event_data = body['event']
                event_type = event_data.get('type', '')
                
                if event_type == 'message':
                    message = event_data.get('message', {})
                    chat_id = message.get('chat_id', '')
                    content = safe_json_loads(message.get('content', '{}'))
                    text = content.get('text', '')
                    user_id = event_data.get('sender', {}).get('sender_id', {}).get('user_id', '')
            
            # 处理1.0版本API格式
            elif 'type' in body and body.get('type') == 'message':
                self.logger.info("检测到飞书API 1.0格式")
                message = body.get('message', {})
                chat_id = message.get('chat_id', '')
                content = safe_json_loads(message.get('content', '{}'))
                text = content.get('text', '')
                user_id = body.get('sender_id', {}).get('user_id', '')
            
            self.logger.info(f"解析飞书事件: chat_id={chat_id}, text={text}, user_id={user_id}")
            
        except Exception as e:
            self.logger.error(f"解析飞书事件失败: {str(e)}", body=body)
        
        return chat_id, text, user_id
    
    def _handle_submit_ticket(self, action_data: Dict[str, Any], 
                            action_value: Dict[str, Any]) -> Dict[str, Any]:
        """处理提交工单操作
        
        Args:
            action_data: 卡片交互数据
            action_value: 解析后的操作值
            
        Returns:
            Dict[str, Any]: 处理结果
        """
        try:
            # 获取表单数据
            title = action_value.get('title', '')
            user_id = action_data.get('user_id', '')
            
            # 解析服务和严重性选项
            service, severity = self._parse_form_options(action_data)
            
            # 验证必需字段
            if not all([title, service, severity, user_id]):
                missing_fields = []
                if not title: missing_fields.append('标题')
                if not service: missing_fields.append('服务类型')
                if not severity: missing_fields.append('严重性')
                if not user_id: missing_fields.append('用户ID')
                
                error_msg = f"请完善以下信息: {', '.join(missing_fields)}"
                self.logger.warning(error_msg, action_data=action_data)
                return create_response(False, error_msg)
            
            # 生成工单ID
            ticket_id = f"TICKET-{int(time.time())}"
            
            # 创建工单群聊
            chat_config = self.config.get_chat_config()
            chat_name = f"{chat_config['name_prefix']}{ticket_id}"
            chat_description = chat_config['description_template'].format(
                title=title,
                service=service,
                severity=severity
            )
            
            chat_id = self.feishu_service.create_chat(
                chat_name=chat_name,
                description=chat_description,
                owner_id=user_id,
                user_list=[user_id]
            )
            
            # 保存工单信息
            ticket_data = self.dynamodb_service.save_ticket(
                ticket_id=ticket_id,
                user_id=user_id,
                title=title,
                service=service,
                severity=severity,
                chat_id=chat_id
            )
            
            # 在群聊中发送工单信息
            if chat_id:
                chat_msg = (
                    f"🎫 **AWS工单已创建**\n\n"
                    f"📋 **工单ID:** {ticket_id}\n"
                    f"📝 **标题:** {title}\n"
                    f"🔧 **服务:** {service}\n"
                    f"⚠️ **严重性:** {severity}\n\n"
                    f"请在此群中讨论工单相关问题。"
                )
                
                self.feishu_service.send_message(
                    chat_id=chat_id,
                    msg_type='text',
                    content={'text': chat_msg}
                )
                
                success_msg = (
                    f"✅ **工单创建成功**\n\n"
                    f"📋 工单ID: {ticket_id}\n"
                    f"📝 标题: {title}\n"
                    f"🔧 服务: {service}\n"
                    f"⚠️ 严重性: {severity}\n"
                    f"💬 讨论群聊: {chat_name}\n\n"
                    f"请使用 `内容 [详细描述]` 命令添加工单详细信息。"
                )
            else:
                success_msg = (
                    f"✅ **工单创建成功**\n\n"
                    f"📋 工单ID: {ticket_id}\n"
                    f"📝 标题: {title}\n"
                    f"🔧 服务: {service}\n"
                    f"⚠️ 严重性: {severity}\n"
                    f"⚠️ 创建群聊失败，请联系管理员\n\n"
                    f"请使用 `内容 [详细描述]` 命令添加工单详细信息。"
                )
            
            self.logger.info("成功创建工单", ticket_id=ticket_id, user_id=user_id, chat_id=chat_id)
            return create_response(True, success_msg, {'ticket_id': ticket_id, 'chat_id': chat_id})
            
        except Exception as e:
            error_msg = f"创建工单失败: {str(e)}"
            self.logger.error(error_msg, action_data=action_data)
            return create_response(False, error_msg)
    
    def _parse_action_value(self, value: Any) -> Dict[str, Any]:
        """解析action value
        
        Args:
            value: action value
            
        Returns:
            Dict[str, Any]: 解析后的值
        """
        if isinstance(value, str):
            return safe_json_loads(value, {})
        elif isinstance(value, dict):
            return value
        else:
            return {}
    
    def _parse_form_options(self, action_data: Dict[str, Any]) -> tuple:
        """解析表单选项
        
        Args:
            action_data: 卡片交互数据
            
        Returns:
            tuple: (service, severity)
        """
        service = ''
        severity = ''
        
        # 兼容不同版本的选项格式
        options = action_data.get('action', {}).get('option', {})
        
        if isinstance(options, list):
            for option in options:
                if 'service' in option:
                    service = option.get('value', '')
                elif 'severity' in option:
                    severity = option.get('value', '')
        elif isinstance(options, dict):
            # 处理2.0版本API的选项格式
            for key, value in options.items():
                if 'service' in key:
                    service = value
                elif 'severity' in key:
                    severity = value
        
        return service, severity
    
    def _build_history_message(self, tickets: List[Dict[str, Any]]) -> str:
        """构建历史工单消息
        
        Args:
            tickets: 工单列表
            
        Returns:
            str: 格式化的历史工单消息
        """
        history_text = "📋 **历史工单记录:**\n\n"
        
        for ticket in tickets:
            ticket_id = ticket.get('ticket_id', '')
            title = ticket.get('title', '')
            service = ticket.get('service', '')
            severity = ticket.get('severity', '')
            status = ticket.get('status', 'unknown')
            created_at = ticket.get('created_at', '')
            chat_id = ticket.get('chat_id', '')
            
            # 格式化创建时间
            created_time = format_timestamp(created_at, '%Y-%m-%d %H:%M')
            
            history_text += f"🎫 **{ticket_id}**\n"
            history_text += f"📝 标题: {title}\n"
            history_text += f"🔧 服务: {service}\n"
            history_text += f"⚠️ 严重性: {severity}\n"
            history_text += f"📊 状态: {status}\n"
            history_text += f"📅 创建时间: {created_time}\n"
            
            # 显示群聊信息
            if chat_id:
                history_text += f"💬 讨论群聊: AWS工单-{ticket_id}\n"
            else:
                history_text += f"💬 讨论群聊: 未创建\n"
            
            history_text += "\n" + "-" * 30 + "\n\n"
        
        return history_text


# 全局工单处理器实例
_ticket_handler = None


def get_ticket_handler() -> TicketHandler:
    """获取工单处理器实例
    
    Returns:
        TicketHandler: 工单处理器实例
    """
    global _ticket_handler
    if _ticket_handler is None:
        _ticket_handler = TicketHandler()
    return _ticket_handler