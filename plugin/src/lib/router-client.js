const axios = require('axios');

class RouterClient {
  constructor(endpoint) {
    this.endpoint = endpoint || 'http://localhost:18889';
    this.client = axios.create({
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json'
      }
    });
  }

  async route(message) {
    try {
      const response = await this.client.post(`${this.endpoint}/route`, {
        content: message.content,
        prefix: message.prefix,
        user_id: message.userId,
        chat_id: message.chatId,
        metadata: {
          originalContent: message.originalContent,
          pluginVersion: '0.1.0'
        }
      });

      return response.data;
    } catch (error) {
      if (error.response) {
        throw new Error(`Router error: ${error.response.status} - ${error.response.data?.detail || error.message}`);
      }
      throw new Error(`Router connection failed: ${error.message}`);
    }
  }

  async healthCheck() {
    try {
      const response = await this.client.get(`${this.endpoint}/health`);
      return response.data;
    } catch (error) {
      return { status: 'unreachable', error: error.message };
    }
  }

  async getStatus() {
    try {
      const response = await this.client.get(`${this.endpoint}/status`);
      return response.data;
    } catch (error) {
      return { status: 'error', error: error.message };
    }
  }
}

module.exports = { RouterClient };
