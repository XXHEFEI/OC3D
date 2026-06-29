/**
 * gateway.js — GatewayChat: WebSocket communication with OpenClaw Gateway.
 *
 * Handles connect handshake, RPC calls, event routing, and session management.
 * Pure business logic — no DOM dependencies.
 */

const AUTH_TOKEN = 'e967ae3cf75190019f45e871a2def5a48c5ef0a4baf2266a';
const CLIENT_ID = 'openclaw-control-ui';

class GatewayChat {
  constructor() {
    this.ws = null;
    this.sessionKey = null;
    this.reqId = 0;
    this.pending = new Map();
    this.connected = false;
    this._eventCallbacks = [];
  }

  /** Register an event callback. Returns this for chaining. */
  onEvent(fn) {
    this._eventCallbacks.push(fn);
    return this;
  }

  _emit(evt, payload) {
    this._eventCallbacks.forEach(fn => {
      try { fn(evt, payload); } catch (e) { /* ignore */ }
    });
  }

  async connect() {
    const wsUrl = `ws://${location.host}/ws/gateway`;
    this.ws = new WebSocket(wsUrl);

    this.ws.onerror = () => this._emit('connection', { state: 'error' });
    this.ws.onclose = () => {
      this.connected = false;
      this._emit('connection', { state: 'off' });
    };

    return new Promise((resolve, reject) => {
      this.ws.onopen = async () => {
        try {
          const challenge = await this._waitForEvent('connect.challenge');
          if (!challenge) throw new Error('No challenge received');

          await this._rpc('connect', {
            minProtocol: 3, maxProtocol: 4,
            client: { id: CLIENT_ID, version: '1.0.0', platform: 'windows', mode: 'webchat' },
            role: 'operator', scopes: ['operator.read', 'operator.write'],
            caps: [], commands: [], permissions: {},
            auth: { token: AUTH_TOKEN },
            locale: 'zh-CN', userAgent: 'ip-print-web/1.0',
          });

          await this._rpc('sessions.subscribe', {});

          this.sessionKey = 'ip-print-' + Date.now().toString(36);
          await this._rpc('sessions.create', {
            key: this.sessionKey, agentId: 'main', label: this.sessionKey,
          });

          this.connected = true;
          this._emit('connection', { state: 'on' });
          resolve();
        } catch (e) {
          reject(e);
        }
      };

      this.ws.onmessage = (e) => this._handleMessage(e.data);
    });
  }

  _waitForEvent(eventName, timeout = 10000) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`Timeout waiting for ${eventName}`)), timeout);
      const wrapper = (evt, payload) => {
        if (evt === eventName) {
          clearTimeout(timer);
          // Remove wrapper from callbacks
          const idx = this._eventCallbacks.indexOf(wrapper);
          if (idx >= 0) this._eventCallbacks.splice(idx, 1);
          resolve(payload);
        }
      };
      this._eventCallbacks.push(wrapper);
    });
  }

  _rpc(method, params, timeout = 30000) {
    const id = String(++this.reqId);
    this.ws.send(JSON.stringify({ type: 'req', id, method, params }));
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`RPC timeout: ${method}`));
      }, timeout);
      this.pending.set(id, { resolve, reject, timer });
    });
  }

  _handleMessage(raw) {
    try {
      const frame = JSON.parse(raw);
      if (frame.type === 'res') {
        const p = this.pending.get(frame.id);
        if (p) {
          clearTimeout(p.timer);
          this.pending.delete(frame.id);
          if (frame.ok) p.resolve(frame);
          else p.reject(new Error(frame.error?.message || 'RPC error'));
        }
      } else if (frame.type === 'event') {
        this._emit(frame.event, frame.payload || {});
      }
    } catch (e) { /* ignore parse errors */ }
  }

  async sendMessage(text) {
    if (!this.connected || !this.sessionKey) throw new Error('Not connected');
    return this._rpc('chat.send', {
      sessionKey: this.sessionKey,
      message: text,
      thinking: 'medium',
      idempotencyKey: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
    });
  }

  close() {
    if (this.ws) this.ws.close();
    this.connected = false;
    this._emit('connection', { state: 'off' });
  }
}
