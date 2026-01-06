# HTTP API 使用说明

## 概述

本机器人提供HTTP API接口，支持通过API提交115云下载任务。API监听端口23333，使用POST方法接收JSON格式的请求数据。

## 基本信息

- **监听端口**: 23333
- **请求方法**: POST
- **内容类型**: application/json
- **响应格式**: JSON

## 接口地址

```
POST http://your-server:23333/
```

如果使用反向代理，根据实际配置访问：
```
POST http://your-domain.com/your-path/
```

## 请求参数

### 单个任务提交

```json
{
  "user_id": "用户ID（字符串）",
  "url": "下载链接（磁力链或电驴链接）"
}
```

### 批量任务提交

```json
{
  "user_id": "用户ID（字符串）",
  "urls": [
    "下载链接1",
    "下载链接2",
    "下载链接3"
  ]
}
```

### 参数说明

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| user_id | string | 是 | Telegram用户ID，用于获取该用户的配置 |
| url | string | 否 | 单个下载链接（与urls二选一） |
| urls | array | 否 | 多个下载链接数组（与url二选一） |

**注意**: `url` 和 `urls` 参数必须提供其中一个。

## 响应格式

### 成功响应（全部成功）

```json
{
  "success": true,
  "message": "成功添加 3 个任务",
  "data": {
    "total": 3,
    "success": 3,
    "failed": 0,
    "tasks": [
      {
        "task_id": "info_hash值",
        "task_name": "任务名称",
        "task_size": 文件大小（字节）,
        "url": "原始下载链接"
      }
    ]
  }
}
```

### 成功响应（部分成功）

```json
{
  "success": true,
  "message": "部分成功: 2 个成功, 1 个失败",
  "data": {
    "total": 3,
    "success": 2,
    "failed": 1,
    "tasks": [
      {
        "task_id": "info_hash值",
        "task_name": "任务名称",
        "task_size": 文件大小（字节）,
        "url": "原始下载链接",
        "state": true,
        "error": null
      },
      {
        "task_id": "info_hash值",
        "task_name": "任务名称",
        "task_size": 0,
        "url": "原始下载链接",
        "state": false,
        "error": "错误信息"
      }
    ]
  }
}
```

### 失败响应

```json
{
  "success": false,
  "message": "错误描述信息"
}
```

## HTTP状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 请求成功 |
| 400 | 请求参数错误 |
| 500 | 服务器内部错误 |

## 错误信息说明

| 错误信息 | 原因 | 解决方法 |
|----------|------|----------|
| 缺少必要参数: user_id | 未提供user_id参数 | 确保请求中包含user_id |
| 缺少必要参数: url 或 urls | 未提供url或urls参数 | 确保请求中包含url或urls |
| 无效的JSON格式 | JSON格式错误 | 检查JSON格式是否正确 |
| 用户未配置 refresh_token | 用户未设置115的refresh_token | 通过Telegram bot设置refresh_token |
| 用户未设置下载文件夹 | 用户未设置下载文件夹 | 通过Telegram bot设置下载文件夹 |
| 刷新access_token失败 | refresh_token过期或无效 | 通过Telegram bot重新设置refresh_token |
| 服务器内部错误 | 服务器处理异常 | 查看服务器日志或联系管理员 |

## 使用示例

### cURL 示例

#### 单个任务

```bash
curl -X POST http://localhost:23333/ \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "123456789",
    "url": "magnet:?xt=urn:btih:08ada5a7a6183aae1e09d831df6748d566095a10&dn=Sintel"
  }'
```

#### 批量任务

```bash
curl -X POST http://localhost:23333/ \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "123456789",
    "urls": [
      "magnet:?xt=urn:btih:08ada5a7a6183aae1e09d831df6748d566095a10&dn=Sintel",
      "magnet:?xt=urn:btih:c9e15763f722f23e98a29decdfae341b98d53056&dn=Big+Buck+Bunny",
      "ed2k://|file|文件名|文件大小|文件哈希|/"
    ]
  }'
```

### Python 示例

```python
import requests
import json

def add_single_task(user_id, url):
    """提交单个任务"""
    response = requests.post(
        'http://localhost:23333/',
        json={
            'user_id': user_id,
            'url': url
        }
    )
    return response.json()

def add_batch_tasks(user_id, urls):
    """批量提交任务"""
    response = requests.post(
        'http://localhost:23333/',
        json={
            'user_id': user_id,
            'urls': urls
        }
    )
    return response.json()

# 使用示例
if __name__ == '__main__':
    # 单个任务
    result = add_single_task(
        '123456789',
        'magnet:?xt=urn:btih:08ada5a7a6183aae1e09d831df6748d566095a10&dn=Sintel'
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # 批量任务
    urls = [
        'magnet:?xt=urn:btih:08ada5a7a6183aae1e09d831df6748d566095a10&dn=Sintel',
        'magnet:?xt=urn:btih:c9e15763f722f23e98a29decdfae341b98d53056&dn=Big+Buck+Bunny'
    ]
    result = add_batch_tasks('123456789', urls)
    print(json.dumps(result, indent=2, ensure_ascii=False))
```

### JavaScript (Node.js) 示例

```javascript
const axios = require('axios');

async function addSingleTask(userId, url) {
    try {
        const response = await axios.post('http://localhost:23333/', {
            user_id: userId,
            url: url
        });
        return response.data;
    } catch (error) {
        console.error('请求失败:', error.response?.data || error.message);
        throw error;
    }
}

async function addBatchTasks(userId, urls) {
    try {
        const response = await axios.post('http://localhost:23333/', {
            user_id: userId,
            urls: urls
        });
        return response.data;
    } catch (error) {
        console.error('请求失败:', error.response?.data || error.message);
        throw error;
    }
}

// 使用示例
(async () => {
    // 单个任务
    const result1 = await addSingleTask(
        '123456789',
        'magnet:?xt=urn:btih:08ada5a7a6183aae1e09d831df6748d566095a10&dn=Sintel'
    );
    console.log(JSON.stringify(result1, null, 2));
    
    // 批量任务
    const urls = [
        'magnet:?xt=urn:btih:08ada5a7a6183aae1e09d831df6748d566095a10&dn=Sintel',
        'magnet:?xt=urn:btih:c9e15763f722f23e98a29decdfae341b98d53056&dn=Big+Buck+Bunny'
    ];
    const result2 = await addBatchTasks('123456789', urls);
    console.log(JSON.stringify(result2, null, 2));
})();
```

## 前置条件

使用API前，需要确保：

1. **用户已配置refresh_token**: 通过Telegram bot发送 `/set_refresh_token` 命令设置
2. **用户已设置下载文件夹**: 通过Telegram bot发送 `/set_download_folder` 命令设置
3. **机器人正在运行**: 确保Telegram bot和HTTP服务都已启动

## 支持的链接类型

- **磁力链接**: `magnet:?xt=urn:btih:...`
- **电驴链接**: `ed2k://|file|...`

## 注意事项

1. **用户ID**: 必须是Telegram用户ID，可以通过Telegram bot发送 `/start` 命令查看
2. **批量限制**: 建议单次提交不超过10个任务，避免请求超时
3. **任务状态**: 提交后可以通过Telegram bot的 `/task_status` 命令查看任务进度
4. **配额限制**: 115云下载有配额限制，可以通过 `/quota` 命令查看
5. **安全性**: 请确保API接口通过反向代理或其他方式保护，避免未授权访问

## 反向代理配置示例

### Nginx

```nginx
location /115bot/ {
    proxy_pass http://localhost:23333/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

### Caddy

```
reverse_proxy /115bot/* http://localhost:23333/
```

## 常见问题

**Q: 提示"用户未配置 refresh_token"？**  
A: 需要先通过Telegram bot设置refresh_token，发送 `/set_refresh_token` 命令。

**Q: 提示"用户未设置下载文件夹"？**  
A: 需要先通过Telegram bot设置下载文件夹，发送 `/set_download_folder` 命令。

**Q: 任务提交成功但无法下载？**  
A: 可能是配额不足或链接无效，可以通过 `/quota` 查看配额，或检查链接是否正确。

**Q: 如何查看任务下载进度？**  
A: 通过Telegram bot发送 `/task_status` 命令查看任务状态。

## 更新日志

- **2026-01-06**: 初始版本，支持单个和批量任务提交
