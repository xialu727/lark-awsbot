#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AWS服务模块
封装所有AWS相关的服务调用
"""

import time
from typing import Dict, List, Optional, Any

import boto3
from botocore.exceptions import ClientError, BotoCoreError

from utils import (
    get_config,
    AWSServiceError,
    get_logger,
    handle_exception,
    retry,
    validate_required_fields,
    format_timestamp
)


class AWSService:
    """AWS服务类"""
    
    def __init__(self):
        """初始化AWS服务"""
        self.config = get_config()
        self.logger = get_logger('aws_service')
        self._clients = {}
        
        # 验证配置
        aws_config = self.config.get_aws_config()
        validate_required_fields(
            aws_config,
            ['region', 'dynamodb_table'],
            "AWS配置不完整"
        )
    
    def _get_client(self, service_name: str):
        """获取AWS客户端
        
        Args:
            service_name: AWS服务名称
            
        Returns:
            AWS客户端实例
        """
        if service_name not in self._clients:
            try:
                aws_config = self.config.get_aws_config()
                self._clients[service_name] = boto3.client(
                    service_name,
                    region_name=aws_config['region']
                )
                self.logger.info(f"创建AWS {service_name} 客户端", region=aws_config['region'])
            except Exception as e:
                error_msg = f"创建AWS {service_name} 客户端失败: {str(e)}"
                self.logger.error(error_msg)
                raise AWSServiceError(error_msg, service_name) from e
        
        return self._clients[service_name]
    
    @property
    def dynamodb(self):
        """获取DynamoDB客户端"""
        return self._get_client('dynamodb')
    
    @property
    def support(self):
        """获取Support客户端"""
        return self._get_client('support')


class DynamoDBService(AWSService):
    """DynamoDB服务类"""
    
    @handle_exception
    @retry(max_attempts=3, delay=1.0, exceptions=(ClientError, BotoCoreError))
    def save_ticket(self, ticket_id: str, user_id: str, title: str, 
                   service: str, severity: str, chat_id: str = None, 
                   status: str = None) -> Dict[str, Any]:
        """保存工单到DynamoDB
        
        Args:
            ticket_id: 工单ID
            user_id: 用户ID
            title: 工单标题
            service: 服务类型
            severity: 严重性
            chat_id: 群聊ID
            status: 工单状态
            
        Returns:
            Dict[str, Any]: 保存的工单数据
            
        Raises:
            AWSServiceError: 保存失败时
        """
        validate_required_fields(
            {
                'ticket_id': ticket_id,
                'user_id': user_id,
                'title': title,
                'service': service,
                'severity': severity
            },
            ['ticket_id', 'user_id', 'title', 'service', 'severity'],
            "保存工单参数不完整"
        )
        
        self.logger.info("保存工单到DynamoDB", ticket_id=ticket_id, user_id=user_id)
        
        aws_config = self.config.get_aws_config()
        table_name = aws_config['dynamodb_table']
        
        # 构建工单数据
        ticket_data = {
            'ticket_id': ticket_id,
            'user_id': user_id,
            'title': title,
            'service': service,
            'severity': severity,
            'status': status or self.config.DEFAULT_TICKET_STATUS,
            'created_at': int(time.time()),
            'updated_at': int(time.time())
        }
        
        if chat_id:
            ticket_data['chat_id'] = chat_id
        
        # 转换为DynamoDB格式
        dynamodb_item = self._convert_to_dynamodb_item(ticket_data)
        
        try:
            response = self.dynamodb.put_item(
                TableName=table_name,
                Item=dynamodb_item
            )
            
            self.logger.info("成功保存工单", ticket_id=ticket_id)
            return ticket_data
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_msg = f"保存工单到DynamoDB失败: {e.response['Error']['Message']}"
            self.logger.error(error_msg, error_code=error_code, ticket_id=ticket_id)
            raise AWSServiceError(error_msg, 'dynamodb', error_code) from e
        except Exception as e:
            error_msg = f"保存工单失败: {str(e)}"
            self.logger.error(error_msg, ticket_id=ticket_id)
            raise AWSServiceError(error_msg, 'dynamodb') from e
    
    @handle_exception
    @retry(max_attempts=3, delay=1.0, exceptions=(ClientError, BotoCoreError))
    def get_user_tickets(self, user_id: str, limit: int = None) -> List[Dict[str, Any]]:
        """获取用户的历史工单
        
        Args:
            user_id: 用户ID
            limit: 返回记录数限制
            
        Returns:
            List[Dict[str, Any]]: 工单列表
            
        Raises:
            AWSServiceError: 查询失败时
        """
        validate_required_fields(
            {'user_id': user_id},
            ['user_id'],
            "查询用户工单参数不完整"
        )
        
        self.logger.info("查询用户历史工单", user_id=user_id, limit=limit)
        
        aws_config = self.config.get_aws_config()
        table_name = aws_config['dynamodb_table']
        
        # 设置查询限制
        query_limit = limit or self.config.MAX_HISTORY_RECORDS
        
        try:
            # 使用scan操作查询用户工单
            scan_params = {
                'TableName': table_name,
                'FilterExpression': 'user_id = :user_id',
                'ExpressionAttributeValues': {
                    ':user_id': {'S': user_id}
                },
                'Limit': query_limit
            }
            
            response = self.dynamodb.scan(**scan_params)
            items = response.get('Items', [])
            
            # 转换DynamoDB格式为普通字典
            tickets = []
            for item in items:
                ticket = self._convert_from_dynamodb_item(item)
                tickets.append(ticket)
            
            # 按创建时间倒序排列
            tickets.sort(key=lambda x: x.get('created_at', 0), reverse=True)
            
            self.logger.info(f"查询到 {len(tickets)} 条历史工单", user_id=user_id)
            return tickets
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_msg = f"查询用户工单失败: {e.response['Error']['Message']}"
            self.logger.error(error_msg, error_code=error_code, user_id=user_id)
            raise AWSServiceError(error_msg, 'dynamodb', error_code) from e
        except Exception as e:
            error_msg = f"查询用户工单失败: {str(e)}"
            self.logger.error(error_msg, user_id=user_id)
            raise AWSServiceError(error_msg, 'dynamodb') from e
    
    @handle_exception
    @retry(max_attempts=3, delay=1.0, exceptions=(ClientError, BotoCoreError))
    def update_ticket_status(self, ticket_id: str, status: str, 
                           aws_case_id: str = None) -> bool:
        """更新工单状态
        
        Args:
            ticket_id: 工单ID
            status: 新状态
            aws_case_id: AWS工单ID
            
        Returns:
            bool: 更新是否成功
            
        Raises:
            AWSServiceError: 更新失败时
        """
        validate_required_fields(
            {'ticket_id': ticket_id, 'status': status},
            ['ticket_id', 'status'],
            "更新工单状态参数不完整"
        )
        
        self.logger.info("更新工单状态", ticket_id=ticket_id, status=status)
        
        aws_config = self.config.get_aws_config()
        table_name = aws_config['dynamodb_table']
        
        try:
            # 构建更新表达式
            update_expression = "SET #status = :status, updated_at = :updated_at"
            expression_attribute_names = {'#status': 'status'}
            expression_attribute_values = {
                ':status': {'S': status},
                ':updated_at': {'N': str(int(time.time()))}
            }
            
            if aws_case_id:
                update_expression += ", aws_case_id = :aws_case_id"
                expression_attribute_values[':aws_case_id'] = {'S': aws_case_id}
            
            response = self.dynamodb.update_item(
                TableName=table_name,
                Key={'ticket_id': {'S': ticket_id}},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_attribute_names,
                ExpressionAttributeValues=expression_attribute_values
            )
            
            self.logger.info("成功更新工单状态", ticket_id=ticket_id, status=status)
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_msg = f"更新工单状态失败: {e.response['Error']['Message']}"
            self.logger.error(error_msg, error_code=error_code, ticket_id=ticket_id)
            raise AWSServiceError(error_msg, 'dynamodb', error_code) from e
        except Exception as e:
            error_msg = f"更新工单状态失败: {str(e)}"
            self.logger.error(error_msg, ticket_id=ticket_id)
            raise AWSServiceError(error_msg, 'dynamodb') from e
    
    def _convert_to_dynamodb_item(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """转换数据为DynamoDB格式
        
        Args:
            data: 原始数据
            
        Returns:
            Dict[str, Any]: DynamoDB格式数据
        """
        item = {}
        for key, value in data.items():
            if isinstance(value, str):
                item[key] = {'S': value}
            elif isinstance(value, (int, float)):
                item[key] = {'N': str(value)}
            elif isinstance(value, bool):
                item[key] = {'BOOL': value}
            elif value is None:
                item[key] = {'NULL': True}
            else:
                # 其他类型转为字符串
                item[key] = {'S': str(value)}
        return item
    
    def _convert_from_dynamodb_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """从DynamoDB格式转换数据
        
        Args:
            item: DynamoDB格式数据
            
        Returns:
            Dict[str, Any]: 普通字典数据
        """
        data = {}
        for key, value in item.items():
            if 'S' in value:
                data[key] = value['S']
            elif 'N' in value:
                # 尝试转换为整数，失败则保持为字符串
                try:
                    data[key] = int(value['N'])
                except ValueError:
                    try:
                        data[key] = float(value['N'])
                    except ValueError:
                        data[key] = value['N']
            elif 'BOOL' in value:
                data[key] = value['BOOL']
            elif 'NULL' in value:
                data[key] = None
            else:
                data[key] = str(value)
        return data


class SupportService(AWSService):
    """AWS Support服务类"""
    
    @handle_exception
    @retry(max_attempts=2, delay=2.0, exceptions=(ClientError, BotoCoreError))
    def create_support_case(self, title: str, service: str, severity: str, 
                          content: str, language: str = 'zh') -> str:
        """创建AWS Support工单
        
        Args:
            title: 工单标题
            service: 服务代码
            severity: 严重性级别
            content: 工单内容
            language: 语言代码
            
        Returns:
            str: AWS工单ID
            
        Raises:
            AWSServiceError: 创建失败时
        """
        validate_required_fields(
            {
                'title': title,
                'service': service,
                'severity': severity,
                'content': content
            },
            ['title', 'service', 'severity', 'content'],
            "创建AWS工单参数不完整"
        )
        
        self.logger.info("创建AWS Support工单", title=title, service=service, severity=severity)
        
        try:
            response = self.support.create_case(
                subject=title,
                serviceCode=service,
                severityCode=severity,
                categoryCode='general-guidance',
                communicationBody=content,
                language=language,
                issueType='customer-service'
            )
            
            case_id = response['caseId']
            self.logger.info("成功创建AWS Support工单", case_id=case_id, title=title)
            return case_id
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_msg = f"创建AWS Support工单失败: {e.response['Error']['Message']}"
            self.logger.error(error_msg, error_code=error_code, title=title)
            raise AWSServiceError(error_msg, 'support', error_code) from e
        except Exception as e:
            error_msg = f"创建AWS Support工单失败: {str(e)}"
            self.logger.error(error_msg, title=title)
            raise AWSServiceError(error_msg, 'support') from e


# 全局服务实例
_dynamodb_service = None
_support_service = None


def get_dynamodb_service() -> DynamoDBService:
    """获取DynamoDB服务实例
    
    Returns:
        DynamoDBService: DynamoDB服务实例
    """
    global _dynamodb_service
    if _dynamodb_service is None:
        _dynamodb_service = DynamoDBService()
    return _dynamodb_service


def get_support_service() -> SupportService:
    """获取Support服务实例
    
    Returns:
        SupportService: Support服务实例
    """
    global _support_service
    if _support_service is None:
        _support_service = SupportService()
    return _support_service