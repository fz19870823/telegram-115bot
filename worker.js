// 全局存储会话数据（允许）
const sessions = new Map();
const SESSION_TIMEOUT = 10 * 60 * 1000; // 10分钟过期
const CLIENT_ID = "100000001"; // 替换为实际115应用ID

export default {
  async fetch(request, env) {
    // 每次请求时清理过期会话
    const now = Date.now();
    for (const [uid, session] of sessions.entries()) {
      if (now - session.timestamp > SESSION_TIMEOUT) {
        sessions.delete(uid);
      }
    }

    const url = new URL(request.url);
    const path = url.pathname;
    
    if (path === '/' || path === '/index.html') {
      return new Response(getIndexHTML(), {
        headers: { 
          'Content-Type': 'text/html; charset=utf-8',
          'Cache-Control': 'no-cache',
          'Cross-Origin-Opener-Policy': 'same-origin',
          'Cross-Origin-Embedder-Policy': 'require-corp'
        }
      });
    }
    
    if (path === '/auth/init') {
      return handleAuthInit(request);
    } else if (path === '/auth/poll') {
      return handleAuthPoll(request);
    } else if (path === '/auth/token') {
      return handleTokenExchange(request);
    }
    
    return new Response('Not Found', { status: 404 });
  }
};

// 生成随机字符串
function generateRandomString(length) {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~';
  let result = '';
  for (let i = 0; i < length; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

// 生成PKCE code challenge
async function generateCodeChallenge(codeVerifier) {
  const encoder = new TextEncoder();
  const data = encoder.encode(codeVerifier);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  const hashBase64 = btoa(String.fromCharCode(...hashArray))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
  return hashBase64;
}

async function handleAuthInit(request) {
  try {
    const codeVerifier = generateRandomString(64);
    const codeChallenge = await generateCodeChallenge(codeVerifier);
    
    const response = await fetch('https://passportapi.115.com/open/authDeviceCode', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        client_id: CLIENT_ID,
        code_challenge: codeChallenge,
        code_challenge_method: 'sha256'
      })
    });
    
    const data = await response.json();
    
    if (!data.data?.qrcode) {
      throw new Error(data.error || '未获取到二维码数据');
    }
    
    sessions.set(data.data.uid, {
      codeVerifier,
      timestamp: Date.now()
    });
    
    return new Response(JSON.stringify({
      uid: data.data.uid,
      qrcode: data.data.qrcode,
      time: data.data.time,
      sign: data.data.sign
    }), {
      headers: { 'Content-Type': 'application/json' }
    });
    
  } catch (error) {
    return new Response(JSON.stringify({ 
      error: '获取二维码失败',
      details: error.message 
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

async function handleAuthPoll(request) {
  const url = new URL(request.url);
  const uid = url.searchParams.get('uid');
  const time = url.searchParams.get('time');
  const sign = url.searchParams.get('sign');
  
  if (!uid || !time || !sign) {
    return new Response(JSON.stringify({ error: '缺少必要参数' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' }
    });
  }
  
  try {
    const response = await fetch(`https://qrcodeapi.115.com/get/status/?uid=${uid}&time=${time}&sign=${sign}`);
    const data = await response.json();
    return new Response(JSON.stringify(data), {
      headers: { 'Content-Type': 'application/json' }
    });
  } catch (error) {
    return new Response(JSON.stringify({ error: '轮询失败' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

async function handleTokenExchange(request) {
  try {
    const { uid } = await request.json();
    if (!uid) throw new Error('缺少uid参数');
    
    const session = sessions.get(uid);
    if (!session) throw new Error('会话已过期');
    
    const response = await fetch('https://passportapi.115.com/open/deviceCodeToToken', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        uid,
        code_verifier: session.codeVerifier
      })
    });
    
    const data = await response.json();
    
    if (data.error) throw new Error(data.error);
    
    sessions.delete(uid);

    // 修改：直接更新当前页面的 DOM 元素
    return new Response(JSON.stringify({
      access_token: data.data.access_token,
      refresh_token: data.data.refresh_token
    }), {
      headers: { 'Content-Type': 'application/json' }
    });
    
  } catch (error) {
    return new Response(JSON.stringify({ 
      error: '获取Token失败',
      details: error.message 
    }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

function getIndexHTML() {
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>115网盘扫码登录</title>
  <style>
    body {
      font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
      max-width: 600px;
      margin: 0 auto;
      padding: 20px;
      text-align: center;
      background-color: #f5f5f5;
    }
    #qrcode-container {
      width: 200px;
      height: 200px;
      margin: 20px auto;
      padding: 10px;
      background: white;
      border-radius: 8px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    }
    #qrcode-canvas {
      display: block;
      margin: 0 auto;
    }
    #status {
      margin: 20px 0;
      padding: 12px;
      border-radius: 6px;
      font-size: 16px;
    }
    .loading {
      color: #666;
      background: #f0f0f0;
    }
    .success {
      color: #07c160;
      background: #e6f7ee;
    }
    .error {
      color: #ee0a24;
      background: #fde6e6;
    }
    /* 新增样式：用于显示令牌 */
    .token-container {
      margin: 20px 0;
      padding: 12px;
      border-radius: 6px;
      background: white;
      box-shadow: 0 2px 10px rgba(0,0,0,0.1);
      display: none; /* 默认隐藏 */
    }
    .token-input {
      width: 100%;
      padding: 10px;
      margin-bottom: 10px;
      border: 1px solid #ddd;
      border-radius: 4px;
    }
    .copy-button {
      padding: 8px 16px;
      background: #007bff;
      color: white;
      border: none;
      border-radius: 4px;
      cursor: pointer;
    }
    .copy-button:hover {
      background: #0056b3;
    }
  </style>
</head>
<body>
  <h1>115网盘登录</h1>
  <div id="qrcode-container">
    <canvas id="qrcode-canvas"></canvas>
  </div>
  <div id="status" class="loading">请使用115客户端扫描二维码</div>

  <!-- 新增：用于显示令牌的容器 -->
  <div id="token-container" class="token-container">
    <h3>Access Token</h3>
    <input type="text" class="token-input" id="access-token" readonly>
    <button class="copy-button" onclick="copyToClipboard('access-token')">复制 Access Token</button>
    
    <h3>Refresh Token</h3>
    <input type="text" class="token-input" id="refresh-token" readonly>
    <button class="copy-button" onclick="copyToClipboard('refresh-token')">复制 Refresh Token</button>
  </div>

  <!-- 动态加载 qrcode.min.js -->
  <script>
    (async () => {
      try {
        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/qrcode@1.5.1/build/qrcode.min.js';
        document.head.appendChild(script);
        await new Promise((resolve) => {
          script.onload = resolve;
        });
      } catch (error) {
        console.error('加载 qrcode.min.js 失败:', error);
        document.getElementById('status').className = 'error';
        document.getElementById('status').textContent = '二维码库加载失败，请刷新页面';
      }
    })();
  </script>
  
  <script>
    document.addEventListener('DOMContentLoaded', function() {
      const qrcodeCanvas = document.getElementById('qrcode-canvas');
      const statusElement = document.getElementById('status');
      const tokenContainer = document.getElementById('token-container'); // 新增：令牌容器
      const accessTokenInput = document.getElementById('access-token'); // 新增：Access Token 输入框
      const refreshTokenInput = document.getElementById('refresh-token'); // 新增：Refresh Token 输入框
      let uid = null;
      
      // 修改 renderQRCode 函数以兼容最新版本的 qrcode.js
      function renderQRCode(url) {
        return new Promise((resolve, reject) => {
          QRCode.toCanvas(qrcodeCanvas, url, {
            width: 180,
            margin: 1,
            color: {
              dark: '#000000',
              light: '#ffffff'
            }
          }).then(() => {
            resolve();
          }).catch((error) => {
            console.error('二维码生成失败:', error);
            statusElement.className = 'error';
            statusElement.textContent = '二维码生成失败，请刷新页面';
            reject(error);
          });
        });
      }

      async function initAuth() {
        try {
          statusElement.className = 'loading';
          statusElement.textContent = '正在获取二维码...';
          
          const response = await fetch('/auth/init', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            }
          });
          
          const data = await response.json();
          
          if (data.error) throw new Error(data.error || '初始化失败');
          
          await renderQRCode(data.qrcode);
          uid = data.uid;
          statusElement.textContent = '请使用115客户端扫描二维码';
          
          pollStatus(data.uid, data.time, data.sign);
          
        } catch (error) {
          console.error('初始化错误:', error);
          statusElement.className = 'error';
          statusElement.textContent = '初始化失败: ' + error.message;
        }
      }

      async function pollStatus(uid, time, sign) {
        try {
          const response = await fetch(\`/auth/poll?uid=\${encodeURIComponent(uid)}&time=\${time}&sign=\${sign}\`);
          const data = await response.json();
          
          if (data.error) throw new Error(data.error);
          
          if (data.state === 0) {
            statusElement.className = 'error';
            statusElement.textContent = '二维码已失效，请刷新页面重试';
            return;
          }
          
          if (data.data?.status === 1) {
            statusElement.className = 'loading';
            statusElement.textContent = '扫码成功，请在客户端确认登录';
          } else if (data.data?.status === 2) {
            statusElement.className = 'loading';
            statusElement.textContent = '登录成功，正在获取令牌...';
            await getToken(uid);
            return;
          }
          
          setTimeout(() => pollStatus(uid, time, sign), 2000);
          
        } catch (error) {
          console.error('轮询错误:', error);
          statusElement.className = 'error';
          statusElement.textContent = '轮询失败: ' + error.message;
        }
      }

      async function getToken(uid) {
        try {
          const response = await fetch('/auth/token', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({ uid })
          });
          
          const data = await response.json();
          
          if (data.error) throw new Error(data.error);
          
          statusElement.className = 'success';
          statusElement.textContent = '登录成功！';
          
          // 新增：更新令牌容器的内容
          tokenContainer.style.display = 'block'; // 显示令牌容器
          accessTokenInput.value = data.access_token;
          refreshTokenInput.value = data.refresh_token;
          
          // 实际应用中这里应该安全地存储token
          // 例如通过postMessage发送给父窗口或存储在安全的地方
          
        } catch (error) {
          console.error('获取令牌失败:', error);
          statusElement.className = 'error';
          statusElement.textContent = '获取令牌失败: ' + error.message;
        }
      }

      // 启动初始化
      initAuth();
    });
  </script>
</body>
</html>`;
}
