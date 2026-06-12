module.exports = {
  // Plugin server port
  port: 3001,
  
  // Router endpoint
  routerEndpoint: 'http://localhost:18889',
  
  // Supported prefixes
  prefixes: {
    'hm:': 'hm',        // Hermes Agent
    'gpt:': 'gpt',      // GPT Agent
    'cherry:': 'cherry', // Cherry Agent (Agnes-2.0-Flash)
    'wb:': 'wb',        // WorkBuddy Agent (Qwen/Qwen3-8B)
    'both:': 'both',    // Aggregate: OpenClaw + Hermes
    'all:': 'all',      // Aggregate: All agents
    'oc:': 'oc'         // OpenClaw (handled locally)
  },
  
  // OpenClaw Gateway
  openclawGateway: 'http://localhost:18789',
  
  // Logging
  logLevel: 'info',
  
  // Retry settings
  maxRetries: 3,
  retryDelay: 1000
};
