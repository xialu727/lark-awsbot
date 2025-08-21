#!/bin/bash

echo "开始部署飞书AWS工单机器人（无服务版本）..."

# 检查AWS SAM CLI是否安装
if ! command -v sam &> /dev/null; then
    echo "错误: AWS SAM CLI未安装。请先安装SAM CLI。"
    echo "macOS: brew tap aws/tap && brew install aws-sam-cli"
    echo "其他系统: 请参考 https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html"
    exit 1
fi

# 检查AWS CLI配置
if ! aws sts get-caller-identity &> /dev/null; then
    echo "错误: AWS CLI未正确配置。请运行 'aws configure' 配置您的AWS凭证。"
    exit 1
fi

# 创建events目录（如果不存在）
mkdir -p events

# 检查.env文件
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "未找到.env文件，将从.env.example创建..."
        cp .env.example .env
        echo "请编辑.env文件，填入您的配置信息。"
    else
        echo "创建.env文件..."
        cat > .env << EOF
FEISHU_APP_ID=cli_a1b2c3d4e5f6g7h8
FEISHU_APP_SECRET=abcdefghijklmnopqrstuvwxyz123456
AWS_ACCOUNT=123456789012
DYNAMODB_TABLE=aws-tickets
AWS_REGION=us-east-1
EOF
        echo "已创建.env文件，请编辑并填入您的配置信息。"
    fi
    exit 1
fi

# 加载环境变量
source <(grep -v '^#' .env | sed 's/^/export /')

# 构建SAM应用
echo "构建SAM应用..."
sam build

# 部署SAM应用
echo "部署SAM应用..."

# 检查是否需要引导式部署
if [ ! -f "samconfig.toml" ]; then
    echo "首次部署，启动引导式部署..."
    sam deploy --guided
else
    echo "使用现有配置部署..."
    sam deploy
fi

# 获取API Gateway URL
STACK_NAME=$(grep -A 1 "\[default.deploy\]" samconfig.toml | grep "stack_name" | cut -d'"' -f2)
if [ -z "$STACK_NAME" ]; then
    STACK_NAME="lark-aws-bot"
fi

API_URL=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --query "Stacks[0].Outputs[?OutputKey=='LarkBotApi'].OutputValue" --output text)

if [ -n "$API_URL" ]; then
    echo "\n部署完成！"
    echo "API Gateway URL: $API_URL"
    echo "\n请在飞书开发者平台配置以下URL:"
    echo "事件订阅URL: ${API_URL}webhook"
    echo "消息卡片URL: ${API_URL}card_action"
else
    echo "\n部署完成，但无法获取API Gateway URL。"
    echo "请在AWS CloudFormation控制台查看输出值。"
fi