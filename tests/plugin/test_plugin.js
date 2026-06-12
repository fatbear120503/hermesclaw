const { PrefixDetector } = require('../../plugin/src/lib/prefix-detector');
const { RouterClient } = require('../../plugin/src/lib/router-client');

describe('PrefixDetector', () => {
  let detector;

  beforeEach(() => {
    detector = new PrefixDetector();
  });

  test('detects hm: prefix', () => {
    const result = detector.detect('hm: hello world');
    expect(result.hasPrefix).toBe(true);
    expect(result.prefix).toBe('hm');
    expect(result.cleanContent).toBe('hello world');
  });

  test('detects gpt: prefix', () => {
    const result = detector.detect('gpt: what is AI');
    expect(result.hasPrefix).toBe(true);
    expect(result.prefix).toBe('gpt');
  });

  test('detects cherry: prefix', () => {
    const result = detector.detect('cherry: analyze this');
    expect(result.hasPrefix).toBe(true);
    expect(result.prefix).toBe('cherry');
    expect(result.cleanContent).toBe('analyze this');
  });

  test('detects wb: prefix', () => {
    const result = detector.detect('wb: help me');
    expect(result.hasPrefix).toBe(true);
    expect(result.prefix).toBe('wb');
    expect(result.cleanContent).toBe('help me');
  });

  test('detects both: prefix', () => {
    const result = detector.detect('both: complex question');
    expect(result.hasPrefix).toBe(true);
    expect(result.prefix).toBe('both');
  });

  test('handles no prefix', () => {
    const result = detector.detect('hello world');
    expect(result.hasPrefix).toBe(false);
    expect(result.prefix).toBeNull();
    expect(result.cleanContent).toBe('hello world');
  });

  test('handles empty string', () => {
    const result = detector.detect('');
    expect(result.hasPrefix).toBe(false);
  });

  test('handles null', () => {
    const result = detector.detect(null);
    expect(result.hasPrefix).toBe(false);
  });

  test('is case insensitive', () => {
    const result = detector.detect('HM: uppercase');
    expect(result.hasPrefix).toBe(true);
    expect(result.prefix).toBe('hm');
  });

  test('adds custom prefix', () => {
    detector.addPrefix('custom:', 'custom');
    const result = detector.detect('custom: test');
    expect(result.hasPrefix).toBe(true);
    expect(result.prefix).toBe('custom');
  });

  test('removes prefix', () => {
    detector.removePrefix('oc:');
    const result = detector.detect('oc: test');
    expect(result.hasPrefix).toBe(false);
  });
});

describe('RouterClient', () => {
  let client;

  beforeEach(() => {
    client = new RouterClient('http://localhost:18889');
  });

  test('healthCheck returns status', async () => {
    const result = await client.healthCheck();
    expect(result).toHaveProperty('status');
  });

  test('getStatus returns status object', async () => {
    const result = await client.getStatus();
    expect(result).toHaveProperty('status');
  });
});
