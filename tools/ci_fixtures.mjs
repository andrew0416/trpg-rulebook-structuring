#!/usr/bin/env node
// Built-in AES-256-GCM only; key material never appears in arguments or output.
import assert from 'node:assert/strict';
import { createCipheriv, createDecipheriv, randomBytes } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';

const HEADER = Buffer.from('PTKFX001', 'ascii');
const IV_BYTES = 12;
const TAG_BYTES = 16;

function parseKey(value) {
  if (typeof value !== 'string' || !/^[0-9a-fA-F]{64}$/.test(value)) {
    throw new Error('PTK_FIXTURE_KEY must contain exactly 64 hexadecimal characters.');
  }
  return Buffer.from(value, 'hex');
}

function encrypt(plaintext, key) {
  const iv = randomBytes(IV_BYTES);
  const cipher = createCipheriv('aes-256-gcm', key, iv, { authTagLength: TAG_BYTES });
  cipher.setAAD(HEADER);
  const ciphertext = Buffer.concat([cipher.update(plaintext), cipher.final()]);
  return Buffer.concat([HEADER, iv, cipher.getAuthTag(), ciphertext]);
}

function decrypt(bundle, key) {
  const headerEnd = HEADER.length;
  const ivEnd = headerEnd + IV_BYTES;
  const tagEnd = ivEnd + TAG_BYTES;
  if (bundle.length < tagEnd || !bundle.subarray(0, headerEnd).equals(HEADER)) {
    throw new Error('Unsupported or truncated fixture bundle.');
  }
  const decipher = createDecipheriv(
    'aes-256-gcm', key, bundle.subarray(headerEnd, ivEnd),
    { authTagLength: TAG_BYTES },
  );
  decipher.setAAD(HEADER);
  decipher.setAuthTag(bundle.subarray(ivEnd, tagEnd));
  // Nothing is written until final() authenticates the complete plaintext.
  return Buffer.concat([decipher.update(bundle.subarray(tagEnd)), decipher.final()]);
}

function selfCheck() {
  const key = randomBytes(32);
  const plaintext = Buffer.from('fixture\r\n\u0000\uffff', 'utf8');
  const bundle = encrypt(plaintext, key);
  assert.deepEqual(decrypt(bundle, key), plaintext);
  assert.notDeepEqual(encrypt(plaintext, key), bundle);
  for (const index of [0, HEADER.length, HEADER.length + IV_BYTES, bundle.length - 1]) {
    const tampered = Buffer.from(bundle);
    tampered[index] ^= 1;
    assert.throws(() => decrypt(tampered, key));
  }
  assert.throws(() => decrypt(bundle.subarray(0, 35), key));
  assert.throws(() => decrypt(bundle, randomBytes(32)));
  for (const value of [undefined, '', 'a'.repeat(63), 'g'.repeat(64), ' '.repeat(64)]) {
    assert.throws(() => parseKey(value));
  }
  assert.deepEqual(parseKey(key.toString('hex')), key);
  console.log('Fixture crypto self-check passed; no private inputs used.');
}

try {
  const [mode, input, output, ...extra] = process.argv.slice(2);
  if (mode === '--self-check' && input === undefined) {
    selfCheck();
  } else {
    if (!['encrypt', 'decrypt'].includes(mode) || !input || !output || extra.length) {
      throw new Error('Usage: ci_fixtures.mjs encrypt|decrypt INPUT OUTPUT');
    }
    const key = parseKey(process.env.PTK_FIXTURE_KEY);
    delete process.env.PTK_FIXTURE_KEY;
    const data = readFileSync(input);
    const result = mode === 'encrypt' ? encrypt(data, key) : decrypt(data, key);
    writeFileSync(output, result, { flag: 'wx', mode: 0o600 });
    key.fill(0);
    console.log(mode === 'encrypt' ? 'Fixture bundle encrypted.' : 'Fixture bundle authenticated and decrypted.');
  }
} catch {
  // Do not print crypto exceptions, arguments, plaintext, or environment values.
  console.error('Fixture operation failed: check mode, key format, bundle authentication, and file paths.');
  process.exitCode = 1;
}