class PrefixDetector {
  constructor(prefixes) {
    this.prefixes = prefixes || {
      'hm:': 'hm',
      'gpt:': 'gpt',
      'cherry:': 'cherry',
      'wb:': 'wb',
      'both:': 'both',
      'all:': 'all',
      'oc:': 'oc'
    };
  }

  detect(content) {
    if (!content || typeof content !== 'string') {
      return { hasPrefix: false, prefix: null, cleanContent: content };
    }

    const trimmed = content.trim();
    
    for (const [prefixStr, prefixKey] of Object.entries(this.prefixes)) {
      if (trimmed.toLowerCase().startsWith(prefixStr.toLowerCase())) {
        return {
          hasPrefix: true,
          prefix: prefixKey,
          cleanContent: trimmed.slice(prefixStr.length).trim()
        };
      }
    }

    return { hasPrefix: false, prefix: null, cleanContent: trimmed };
  }

  addPrefix(prefixStr, prefixKey) {
    this.prefixes[prefixStr] = prefixKey;
  }

  removePrefix(prefixStr) {
    delete this.prefixes[prefixStr];
  }

  listPrefixes() {
    return { ...this.prefixes };
  }
}

module.exports = { PrefixDetector };
