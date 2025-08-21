#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具模块
提供配置管理、异常处理、日志记录、重试机制等通用功能
"""

import json
import logging
import os
import time
import traceback
from functools import wraps
from typing import Any, Callable, Dict, Optional, Union


# ==================== 配置管理 ====================

class Config:
    """配置管理类"""
    
    def __init__(self):
        """初始化配置"""
        self._load_config()
    
    def _load_config(self):
        """加载配置项"""
        # 飞书配置
        self.FEISHU_APP_ID = os.environ.get('FEISHU_APP_ID')
        self.FEISHU_APP_SECRET = os.environ.get('FEISHU_APP_SECRET')
        self.FEISHU_API_BASE_URL = 'https://open.feishu.cn/open-apis'
        
        # AWS配置
        self.AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
        self.DYNAMODB_TABLE = os.environ.get('DYNAMODB_TABLE', 'aws-tickets')
        
        # 应用配置
        self.DEBUG = os.environ.get('DEBUG', 'false').lower() == 'true'
        self.LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
        
        # 工单配置
        self.MAX_HISTORY_RECORDS = int(os.environ.get('MAX_HISTORY_RECORDS', '10'))
        self.DEFAULT_TICKET_STATUS = 'pending'
        
        # 群聊配置
        self.CHAT_NAME_PREFIX = 'AWS工单-'
        self.CHAT_DESCRIPTION_TEMPLATE = 'AWS工单讨论群\n标题: {title}\n服务: {service}\n严重性: {severity}'
    
    def get_feishu_config(self) -> dict:
        """获取飞书配置"""
        return {
            'app_id': self.FEISHU_APP_ID,
            'app_secret': self.FEISHU_APP_SECRET,
            'api_base_url': self.FEISHU_API_BASE_URL
        }
    
    def get_aws_config(self) -> dict:
        """获取AWS配置"""
        return {
            'region': self.AWS_REGION,
            'dynamodb_table': self.DYNAMODB_TABLE
        }


# 全局配置实例
config = Config()


def get_config() -> Config:
    """获取配置实例"""
    return config


# ==================== 异常类定义 ====================


class TicketError(Exception):
    """工单相关异常基类"""
    pass


class FeishuAPIError(TicketError):
    """飞书API异常"""
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class AWSServiceError(TicketError):
    """AWS服务异常"""
    def __init__(self, message: str, service_name: Optional[str] = None, error_code: Optional[str] = None):
        super().__init__(message)
        self.service_name = service_name
        self.error_code = error_code


class ValidationError(TicketError):
    """数据验证异常"""
    pass


class ConfigurationError(TicketError):
    """配置异常"""
    pass


class Logger:
    """日志管理类"""
    
    def __init__(self, name: str = __name__):
        """初始化日志器
        
        Args:
            name: 日志器名称
        """
        self.logger = logging.getLogger(name)
        self._setup_logger()
    
    def _setup_logger(self):
        """设置日志器"""
        config = get_config()
        
        # 设置日志级别
        level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
        self.logger.setLevel(level)
        
        # 避免重复添加handler
        if not self.logger.handlers:
            # 创建控制台处理器
            handler = logging.StreamHandler()
            handler.setLevel(level)
            
            # 设置日志格式
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            
            self.logger.addHandler(handler)
    
    def info(self, message: str, **kwargs):
        """记录信息日志"""
        self._log_with_context('info', message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """记录警告日志"""
        self._log_with_context('warning', message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """记录错误日志"""
        self._log_with_context('error', message, **kwargs)
    
    def debug(self, message: str, **kwargs):
        """记录调试日志"""
        self._log_with_context('debug', message, **kwargs)
    
    def _log_with_context(self, level: str, message: str, **kwargs):
        """带上下文的日志记录
        
        Args:
            level: 日志级别
            message: 日志消息
            **kwargs: 额外的上下文信息
        """
        # 添加上下文信息
        if kwargs:
            context = json.dumps(kwargs, ensure_ascii=False, default=str)
            message = f"{message} | Context: {context}"
        
        getattr(self.logger, level)(message)


# 全局日志器实例
logger = Logger('ticket_bot')


def get_logger(name: str = None) -> Logger:
    """获取日志器实例
    
    Args:
        name: 日志器名称
        
    Returns:
        Logger: 日志器实例
    """
    if name:
        return Logger(name)
    return logger


def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0, 
          exceptions: tuple = (Exception,)):
    """重试装饰器
    
    Args:
        max_attempts: 最大重试次数
        delay: 初始延迟时间（秒）
        backoff: 延迟时间倍数
        exceptions: 需要重试的异常类型
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_attempts - 1:
                        # 最后一次尝试失败，抛出异常
                        logger.error(
                            f"函数 {func.__name__} 重试 {max_attempts} 次后仍然失败",
                            error=str(e),
                            traceback=traceback.format_exc()
                        )
                        raise e
                    
                    logger.warning(
                        f"函数 {func.__name__} 第 {attempt + 1} 次尝试失败，{current_delay}秒后重试",
                        error=str(e)
                    )
                    
                    time.sleep(current_delay)
                    current_delay *= backoff
            
            # 理论上不会到达这里
            raise last_exception
        
        return wrapper
    return decorator


def safe_json_loads(json_str: str, default: Any = None) -> Any:
    """安全的JSON解析
    
    Args:
        json_str: JSON字符串
        default: 解析失败时的默认值
        
    Returns:
        Any: 解析结果或默认值
    """
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger = get_logger('utils')
        logger.warning(f"JSON解析失败: {str(e)}", json_str=json_str)
        return default


def safe_json_dumps(obj: Any, default: str = '{}') -> str:
    """安全的JSON序列化
    
    Args:
        obj: 要序列化的对象
        default: 序列化失败时的默认值
        
    Returns:
        str: JSON字符串或默认值
    """
    try:
        return json.dumps(obj, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        logger = get_logger('utils')
        logger.warning(f"JSON序列化失败: {str(e)}", obj=obj)
        return default


def handle_exception(func: Callable) -> Callable:
    """异常处理装饰器
    
    Args:
        func: 被装饰的函数
        
    Returns:
        Callable: 装饰后的函数
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except TicketError as e:
            # 业务异常，记录并重新抛出
            logger.error(
                f"业务异常在函数 {func.__name__} 中发生",
                error=str(e),
                error_type=type(e).__name__
            )
            raise
        except Exception as e:
            # 未预期的异常，记录详细信息
            logger.error(
                f"未预期异常在函数 {func.__name__} 中发生",
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc()
            )
            # 转换为业务异常
            raise TicketError(f"函数 {func.__name__} 执行失败: {str(e)}") from e
    
    return wrapper


def validate_required_fields(data: dict, required_fields: list, 
                           error_message: str = "缺少必需字段") -> None:
    """验证必需字段
    
    Args:
        data: 要验证的数据字典
        required_fields: 必需字段列表
        error_message: 错误消息
        
    Raises:
        ValidationError: 当缺少必需字段时
    """
    missing_fields = []
    
    for field in required_fields:
        # 检查字段是否存在且不为空
        if field not in data or data[field] is None or data[field] == '':
            missing_fields.append(field)
    
    if missing_fields:
        raise ValidationError(f"{error_message}: {', '.join(missing_fields)}")


def format_timestamp(timestamp: Union[int, float, str], 
                    format_str: str = '%Y-%m-%d %H:%M:%S') -> str:
    """格式化时间戳
    
    Args:
        timestamp: 时间戳
        format_str: 格式字符串
        
    Returns:
        str: 格式化后的时间字符串
    """
    try:
        if isinstance(timestamp, str):
            timestamp = float(timestamp)
        
        import datetime
        dt = datetime.datetime.fromtimestamp(timestamp)
        return dt.strftime(format_str)
    except (ValueError, TypeError, OSError) as e:
        logger.warning(f"时间戳格式化失败: {str(e)}", timestamp=timestamp)
        return '未知时间'


def create_response(success: bool = True, message: str = '', 
                   data: Any = None, error_code: str = None) -> dict:
    """创建标准响应格式
    
    Args:
        success: 是否成功
        message: 响应消息
        data: 响应数据
        error_code: 错误代码
        
    Returns:
        dict: 标准响应字典
    """
    response = {
        'success': success,
        'message': message,
        'timestamp': int(time.time())
    }
    
    if data is not None:
        response['data'] = data
    
    if error_code:
        response['error_code'] = error_code
    
    return response