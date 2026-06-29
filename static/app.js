/**
 * app.js — Application controller.
 *
 * Bridges the view (index.html) and business logic (gateway.js, prompt.js).
 * Manages state, sends prompt to Gateway, handles real-time task status via WebSocket.
 */

const GATEWAY_HTTP = 'http://127.0.0.1:18789';

class App {
  constructor() {
    this.gateway = new GatewayChat();
    this.selectedCostume = null;
    this.isPrinting = false;
    this.taskId = null;
    this.taskWs = null;

    /** View callbacks */
    this.onConnectionChange = null;  // (state)
    this.onChatUrl = null;          // (url)  — load Gateway chat iframe
    this.onSystemLog = null;        // (message)
    this.onCostumeSelect = null;    // (costume)
    this.onTaskStateChange = null;  // (state) — real-time task state updates
    this.onTaskComplete = null;     // (state) — task done
    this.onTaskFailed = null;       // (state) — task failed
  }

  async init() {
    try {
      await this.gateway.connect();
      this._notify(this.onSystemLog, '已连接到 OpenClaw Gateway');
    } catch (e) {
      this._notify(this.onSystemLog, '无法连接到 OpenClaw Gateway: ' + e.message);
    }
  }

  selectCostume(id) {
    this.selectedCostume = COSTUMES.find(c => c.id === id);
    this._notify(this.onCostumeSelect, this.selectedCostume);
  }

  /**
   * Connect to task WebSocket for real-time status push.
   */
  connectTaskWebSocket(taskId) {
    if (this.taskWs) {
      this.taskWs.close();
      this.taskWs = null;
    }

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    this.taskWs = new WebSocket(`${protocol}//${location.host}/ws/task/${taskId}`);

    this.taskWs.onmessage = (event) => {
      try {
        const state = JSON.parse(event.data);
        this._handleTaskState(state);
      } catch (e) { /* ignore parse errors */ }
    };

    this.taskWs.onclose = () => { this.taskWs = null; };
    this.taskWs.onerror = () => { this.taskWs = null; };
  }

  /**
   * Handle real-time task state updates from WebSocket.
   */
  _handleTaskState(state) {
    this._notify(this.onTaskStateChange, state);

    if (state.status === 'done') {
      this._notify(this.onTaskComplete, state);
      if (this.taskWs) { this.taskWs.close(); this.taskWs = null; }
    } else if (state.status === 'failed') {
      this._notify(this.onTaskFailed, state);
      if (this.taskWs) { this.taskWs.close(); this.taskWs = null; }
    }
  }

  async startPrint() {
    if (!this.selectedCostume || !this.gateway.connected || this.isPrinting) return;

    this.isPrinting = true;

    try {
      const genRes = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ip_id: this.selectedCostume.id }),
      });
      const { task_id } = await genRes.json();
      this.taskId = task_id;

      // Connect WebSocket for real-time status push
      this.connectTaskWebSocket(task_id);

      // Load Gateway chat UI in iframe
      const sessionParam = encodeURIComponent('agent:main:' + this.gateway.sessionKey);
      const chatUrl = `${GATEWAY_HTTP}/chat?session=${sessionParam}`;
      this._notify(this.onChatUrl, chatUrl);

      // Send prompt to Gateway
      const prompt = buildPrompt(this.selectedCostume, task_id);
      await this.gateway.sendMessage(prompt);
      this._notify(this.onSystemLog, '任务已发送，实时状态推送已连接');
    } catch (e) {
      this._notify(this.onSystemLog, '发送失败: ' + e.message);
      this.isPrinting = false;
    }
  }

  /**
   * Clean up WebSocket connection.
   */
  disconnect() {
    if (this.taskWs) {
      this.taskWs.close();
      this.taskWs = null;
    }
  }

  _notify(fn, ...args) {
    if (typeof fn === 'function') fn(...args);
  }
}
