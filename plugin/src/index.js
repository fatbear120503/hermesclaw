const express = require('express');
const axios = require('axios');
const { PrefixDetector } = require('./lib/prefix-detector');
const { RouterClient } = require('./lib/router-client');
const config = require('./config/default');

class HermesClawPlugin {
  constructor(options = {}) {
    this.config = { ...config, ...options };
    this.prefixDetector = new PrefixDetector(this.config.prefixes);
    this.routerClient = new RouterClient(this.config.routerEndpoint);
    this.app = express();
    this.setupMiddleware();
    this.setupRoutes();
  }

  setupMiddleware() {
    this.app.use(express.json());
  }

  setupRoutes() {
    // Main message handler
    this.app.post('/message', async (req, res) => {
      try {
        const { content, userId, chatId } = req.body;
        
        // Detect prefix
        const detection = this.prefixDetector.detect(content);
        
        if (!detection.hasPrefix || detection.prefix === 'oc') {
          // No prefix or oc: prefix - let OpenClaw handle it directly
          return res.json({
            handled: false,
            reason: 'No routing prefix detected',
            originalContent: content
          });
        }

        // Has routing prefix - forward to Router
        const response = await this.routerClient.route({
          content: detection.cleanContent,
          prefix: detection.prefix,
          userId,
          chatId,
          originalContent: content
        });

        return res.json({
          handled: true,
          agent: detection.prefix,
          response: response
        });
      } catch (error) {
        console.error('Plugin error:', error);
        return res.status(500).json({
          error: 'Internal plugin error',
          message: error.message
        });
      }
    });

    // Health check
    this.app.get('/health', (req, res) => {
      res.json({ status: 'ok', plugin: 'hermesclaw', version: '0.1.0' });
    });

    // Config endpoint
    this.app.get('/config', (req, res) => {
      res.json({
        prefixes: this.config.prefixes,
        routerEndpoint: this.config.routerEndpoint,
        version: '0.1.0'
      });
    });
  }

  start() {
    const port = this.config.port || 3001;
    this.app.listen(port, () => {
      console.log(`HermesClaw Plugin running on port ${port}`);
      console.log(`Router endpoint: ${this.config.routerEndpoint}`);
      console.log(`Supported prefixes: ${Object.keys(this.config.prefixes).join(', ')}`);
    });
  }
}

module.exports = { HermesClawPlugin };
