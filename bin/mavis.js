#!/usr/bin/env node
'use strict';

/**
 * mavis skill - the local skill-evolve CLI surface.
 *
 * The native skill-evolve RPCs live on the DesktopService contract. The mcode
 * CLI app-server exposes that contract over the "desktopService/transport"
 * method, which speaks RuntimeTransport frames:
 *
 *   request  { type:"request", id, method, url, headers, body }
 *   response { type:"response-start", id, seq, status, headers }
 *            { type:"stream-chunk",  id, seq, payload:{encoding,data} }
 *            { type:"stream-done" | "stream-error" }
 *
 * Body bindings: a POST carries { "body_json": "<the json as a string>" }.
 * The payload arrives base64 encoded and the response is { "result_json": "<json>" }.
 *
 * Every command falls back to writing the native store directly
 * (<dataDir>/local-runtime/skill-evolve.json) when the transport is unavailable,
 * so reporting a signal always works even with the runtime down.
 */

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');

const DATA_DIR = process.env.MAVIS_DATA_DIR || path.join(os.homedir(), '.minimax');
const STORE = path.join(DATA_DIR, 'local-runtime', 'skill-evolve.json');
const BASE = '/minimax-desktop/api/v1/skill-evolve';

const ISSUE_KINDS = ['missing-skill', 'missing-step', 'bad-default', 'wrong-trigger', 'manual-trigger'];
const AUTO_ATTRIBUTION = new Set(['missing-step', 'bad-default', 'wrong-trigger']);

// ---------------------------------------------------------------- transport

function findMcode() {
  if (process.env.MCODE_BIN) return process.env.MCODE_BIN;
  const name = process.platform === 'win32' ? 'mcode.cmd' : 'mcode';
  const dirs = (process.env.PATH || '').split(path.delimiter).filter(Boolean);
  for (const d of dirs) {
    const p = path.join(d, name);
    try { if (fs.existsSync(p)) return p; } catch { /* ignore */ }
  }
  return name;
}

class Transport {
  constructor() {
    this.proc = null;
    this.buf = '';
    this.pending = new Map();
    this.seq = 0;
  }

  async start() {
    const cmd = findMcode();
    this.proc = spawn(cmd, ['app-server', '--stdio'], {
      stdio: ['pipe', 'pipe', 'pipe'],
      shell: process.platform === 'win32',
    });
    this.proc.stdout.setEncoding('utf-8');
    this.proc.stdout.on('data', (chunk) => this.onData(chunk));
    this.proc.stderr.resume();

    const initId = this.nextId();
    const initPromise = this.waitFor(initId);
    this.send({
      jsonrpc: '2.0',
      id: initId,
      method: 'initialize',
      params: {
        protocolVersion: 1,
        clientInfo: { name: 'mavis-skill', version: '0.7.6' },
        capabilities: { desktopService: { transportProtocolVersion: 2 } },
      },
    });
    await initPromise;
    this.send({ jsonrpc: '2.0', method: 'initialized', params: {} });
    return this;
  }

  nextId() { this.seq += 1; return this.seq; }

  send(obj) {
    this.proc.stdin.write(JSON.stringify(obj) + '\n');
  }

  onData(chunk) {
    this.buf += chunk;
    let idx;
    while ((idx = this.buf.indexOf('\n')) >= 0) {
      const line = this.buf.slice(0, idx).trim();
      this.buf = this.buf.slice(idx + 1);
      if (line) this.onLine(line);
    }
  }

  onLine(line) {
    let msg;
    try { msg = JSON.parse(line); } catch { return; }

    if (msg.method === 'desktopService/transport' && msg.params && msg.params.frame) {
      const frame = msg.params.frame;
      const entry = this.pending.get(frame.id);
      if (!entry) return;
      if (frame.type === 'response-start') {
        entry.status = frame.status;
      } else if (frame.type === 'stream-chunk') {
        const p = frame.payload || {};
        const raw = p.encoding === 'base64' ? Buffer.from(p.data || '', 'base64').toString('utf-8') : (p.data || '');
        entry.text += raw;
      } else if (frame.type === 'stream-error') {
        const err = frame.error || frame.message || 'stream error';
        this.pending.delete(frame.id);
        entry.reject(new Error(typeof err === 'string' ? err : JSON.stringify(err)));
      } else if (frame.type === 'stream-done') {
        this.pending.delete(frame.id);
        entry.resolve({ text: entry.text, status: entry.status });
      }
      return;
    }

    if (msg.id !== undefined && this.pending.has(msg.id)) {
      const entry = this.pending.get(msg.id);
      this.pending.delete(msg.id);
      if (msg.error) { entry.reject(new Error(msg.error.message || 'rpc error')); return; }
      entry.resolve({ result: msg.result, text: '', status: null });
    }
  }

  waitFor(id) {
    return new Promise((resolve, reject) => {
      const entry = { resolve, reject, text: '', status: null, error: null };
      this.pending.set(id, entry);
      const timer = setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id);
          reject(new Error('app-server request timed out'));
        }
      }, 20000);
      if (typeof timer.unref === 'function') timer.unref();
      entry.resolve = (value) => { clearTimeout(timer); resolve(value); };
      entry.reject = (err) => { clearTimeout(timer); reject(err); };
    });
  }

  async call(method, url, body) {
    const id = 'rq-' + Math.random().toString(36).slice(2, 10);
    const entryPromise = this.waitFor(id);
    const frame = {
      type: 'request',
      id,
      method,
      url,
      headers: { 'content-type': 'application/json' },
    };
    if (body !== undefined) frame.body = JSON.stringify(body);
    this.send({ jsonrpc: '2.0', id: this.nextId() + 1000, method: 'desktopService/transport', params: { frame } });
    const entry = await entryPromise;
    if (entry.status && entry.status >= 400) {
      throw new Error('HTTP ' + entry.status + ': ' + entry.text.slice(0, 300));
    }
    const parsed = JSON.parse(entry.text || '{}');
    if (parsed.result_json) {
      try { return JSON.parse(parsed.result_json); } catch { return parsed; }
    }
    return parsed;
  }

  stop() {
    try { this.proc.kill(); } catch { /* ignore */ }
  }
}

let transport = null;

async function nativeCall(method, url, body) {
  if (!transport) {
    transport = new Transport();
    await transport.start();
  }
  return transport.call(method, url, body);
}

// ------------------------------------------------------------- store fallback

function readStore() {
  try {
    const raw = JSON.parse(fs.readFileSync(STORE, 'utf-8'));
    return {
      signals: Array.isArray(raw.signals) ? raw.signals : [],
      proposals: Array.isArray(raw.proposals) ? raw.proposals : [],
      history: Array.isArray(raw.history) ? raw.history : [],
    };
  } catch {
    return { signals: [], proposals: [], history: [] };
  }
}

function writeStore(state) {
  fs.mkdirSync(path.dirname(STORE), { recursive: true });
  fs.writeFileSync(STORE, JSON.stringify(state, null, 2), 'utf-8');
}

function newId(prefix) {
  return prefix + '_' + require('crypto').randomBytes(6).toString('hex');
}

// -------------------------------------------------------------------- cli

function parseArgs(argv) {
  const opts = { _: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a.startsWith('--')) {
      const eq = a.indexOf('=');
      if (eq > -1) {
        opts[a.slice(2, eq)] = a.slice(eq + 1);
      } else {
        const next = argv[i + 1];
        if (next !== undefined && !next.startsWith('--')) { opts[a.slice(2)] = next; i += 1; }
        else opts[a.slice(2)] = true;
      }
    } else opts._.push(a);
  }
  return opts;
}

function out(t) { process.stdout.write(t + '\n'); }
function fail(msg, code) { process.stderr.write('mavis: ' + msg + '\n'); process.exit(code === undefined ? 1 : code); }

function requireOption(opts, name, flag) {
  const v = opts[name];
  if (v === undefined || v === true || v === '') fail('missing required option ' + (flag || '--' + name));
  return String(v);
}

function issueKind(opts, fallback) {
  const raw = opts['issue-kind'] || opts.issueKind;
  if (raw === undefined || raw === true) return fallback;
  const kind = String(raw);
  if (!ISSUE_KINDS.includes(kind)) fail('unknown issue-kind "' + kind + '". Expected one of: ' + ISSUE_KINDS.join(', '));
  return kind;
}

function evidenceOf(opts) {
  const v = opts.evidence || opts['evidence-excerpt'] || opts.evidenceExcerpt;
  if (v === undefined || v === true || String(v).trim() === '') fail('missing required option --evidence "<excerpt>"');
  return String(v);
}

function signalBody(opts, fallbackKind) {
  const kind = issueKind(opts, fallbackKind);
  const body = {
    channel: opts.channel ? String(opts.channel) : 'active',
    issueKind: kind,
    evidenceExcerpt: evidenceOf(opts),
  };
  if (opts['skill-ref']) body.skillRef = String(opts['skill-ref']);
  if (opts.rationale) body.rationale = String(opts.rationale);
  if (opts['session-id']) body.sessionId = String(opts['session-id']);
  if (opts['agent-name']) body.agentName = String(opts['agent-name']);
  if (!body.attribution && AUTO_ATTRIBUTION.has(kind)) body.attribution = 'skill_issue';
  return body;
}

async function reportSignal(opts) {
  const body = signalBody(opts, 'manual-trigger');
  try {
    const res = await nativeCall('POST', BASE + '/signal', { body_json: JSON.stringify(body) });
    out('signal_id=' + (res.signalId || (res.signal && res.signal.signalId) || ''));
    out('status=' + ((res.signal && res.signal.verdict) || 'pending'));
    out('transport=native');
    return 0;
  } catch (err) {
    const state = readStore();
    const now = Date.now();
    const signal = { id: newId('sig'), kind: 'signal', status: 'pending', createdAt: now, updatedAt: now, body };
    state.signals.unshift(signal);
    state.history.unshift({ type: 'signal.created', id: signal.id, at: now });
    writeStore(state);
    out('signal_id=' + signal.id);
    out('status=pending');
    out('transport=store-fallback (' + err.message + ')');
    return 0;
  }
}

async function reportProposal(opts) {
  const name = opts['suggested-name'] || opts.name;
  if (name === undefined || name === true || String(name).trim() === '') fail('missing required option --suggested-name "<name>"');
  const excerpts = [];
  const ev = opts.evidence || opts['evidence-excerpt'];
  if (ev !== undefined && ev !== true) excerpts.push(String(ev));
  const body = {
    suggestedName: String(name),
    suggestedScope: opts['suggested-scope'] ? String(opts['suggested-scope']) : 'agent-self',
    summary: opts.summary ? String(opts.summary) : '',
    rationale: opts.rationale ? String(opts.rationale) : '',
    evidenceExcerpts: excerpts,
  };
  if (opts['target-agent-name']) body.targetAgentName = String(opts['target-agent-name']);
  if (opts.sketch) body.sketch = String(opts.sketch);
  try {
    const res = await nativeCall('POST', BASE + '/proposal', { body_json: JSON.stringify(body) });
    out('proposal_id=' + (res.proposalId || (res.proposal && res.proposal.proposalId) || ''));
    out('status=' + ((res.proposal && res.proposal.verdict) || 'pending'));
    out('transport=native');
    return 0;
  } catch (err) {
    const state = readStore();
    const now = Date.now();
    const proposal = { id: newId('pro'), kind: 'proposal', status: 'pending', createdAt: now, updatedAt: now, body };
    state.proposals.unshift(proposal);
    state.history.unshift({ type: 'proposal.created', id: proposal.id, at: now });
    writeStore(state);
    out('proposal_id=' + proposal.id);
    out('status=pending');
    out('transport=store-fallback (' + err.message + ')');
    return 0;
  }
}

async function cancelSignal(opts) {
  const id = requireOption(opts, 'signal-id');
  try {
    const res = await nativeCall('POST', BASE + '/signal/cancel', {
      signal_id: id,
      reason: opts.reason ? String(opts.reason) : 'dismissed by user',
    });
    out('signal_id=' + id);
    out('status=' + ((res.signal && res.signal.verdict) || res.status || 'dismissed'));
    out('transport=native');
    return 0;
  } catch (err) {
    const state = readStore();
    const signal = state.signals.find((s) => s.id === id);
    if (!signal) fail('signal ' + id + ' not found', 2);
    signal.status = 'dismissed';
    signal.updatedAt = Date.now();
    signal.body = Object.assign({}, signal.body, { cancelReason: opts.reason ? String(opts.reason) : 'dismissed by user' });
    writeStore(state);
    out('signal_id=' + id);
    out('status=dismissed');
    out('transport=store-fallback');
    return 0;
  }
}

async function cancelProposal(opts) {
  const id = requireOption(opts, 'proposal-id');
  try {
    const res = await nativeCall('POST', BASE + '/proposal/cancel', {
      proposal_id: id,
      reason: opts.reason ? String(opts.reason) : 'dismissed by user',
    });
    out('proposal_id=' + id);
    out('status=' + ((res.proposal && res.proposal.verdict) || res.status || 'dismissed'));
    out('transport=native');
    return 0;
  } catch (err) {
    const state = readStore();
    const proposal = state.proposals.find((p) => p.id === id);
    if (!proposal) fail('proposal ' + id + ' not found', 2);
    proposal.status = 'dismissed';
    proposal.updatedAt = Date.now();
    proposal.body = Object.assign({}, proposal.body, { cancelReason: opts.reason ? String(opts.reason) : 'dismissed by user' });
    writeStore(state);
    out('proposal_id=' + id);
    out('status=dismissed');
    out('transport=store-fallback');
    return 0;
  }
}

async function markActed(opts) {
  const id = requireOption(opts, 'proposal-id');
  try {
    await nativeCall('POST', BASE + '/proposal/mark-acted', {
      proposal_id: id,
      skill_ref: opts['skill-ref'] ? String(opts['skill-ref']) : undefined,
    });
    out('proposal_id=' + id);
    out('status=acted');
    out('transport=native');
    return 0;
  } catch (err) {
    const state = readStore();
    const proposal = state.proposals.find((p) => p.id === id);
    if (!proposal) fail('proposal ' + id + ' not found', 2);
    proposal.status = 'acted';
    proposal.updatedAt = Date.now();
    writeStore(state);
    out('proposal_id=' + id);
    out('status=acted');
    out('transport=store-fallback');
    return 0;
  }
}

async function listSignals(opts) {
  try {
    const res = await nativeCall('GET', BASE + '/signals');
    const items = res.signals || res.items || [];
    out('signals=' + items.length);
    for (const s of items) {
      out('  ' + s.signalId + '  ' + (s.verdict || 'pending') + '  ' + (s.issueKind || 'unknown') + '  ' + ((s.target && s.target.skillRef) || '-'));
    }
    out('transport=native');
    return 0;
  } catch (err) {
    const state = readStore();
    const wanted = opts.status ? String(opts.status) : null;
    const rows = state.signals.filter((s) => (wanted ? s.status === wanted : true));
    out('signals=' + rows.length);
    for (const s of rows) out('  ' + s.id + '  ' + s.status + '  ' + (s.body.issueKind || 'unknown') + '  ' + (s.body.skillRef || '-'));
    out('transport=store-fallback');
    return 0;
  }
}

async function listProposals(opts) {
  try {
    const res = await nativeCall('GET', BASE + '/proposals');
    const items = res.proposals || res.items || [];
    out('proposals=' + items.length);
    for (const p of items) out('  ' + p.proposalId + '  ' + (p.verdict || 'pending') + '  ' + (p.suggestedName || 'unnamed'));
    out('transport=native');
    return 0;
  } catch (err) {
    const state = readStore();
    const wanted = opts.status ? String(opts.status) : null;
    const rows = state.proposals.filter((p) => (wanted ? p.status === wanted : true));
    out('proposals=' + rows.length);
    for (const p of rows) out('  ' + p.id + '  ' + p.status + '  ' + (p.body.suggestedName || 'unnamed'));
    out('transport=store-fallback');
    return 0;
  }
}

async function history() {
  try {
    const res = await nativeCall('GET', BASE + '/history');
    const items = res.history || res.items || [];
    out('history=' + items.length);
    for (const h of items.slice(0, 50)) out('  ' + (h.at || '') + '  ' + h.type + '  ' + (h.id || ''));
    out('transport=native');
    return 0;
  } catch (err) {
    const state = readStore();
    out('history=' + state.history.length);
    for (const h of state.history.slice(0, 50)) out('  ' + (h.at || '') + '  ' + h.type + '  ' + (h.id || ''));
    out('transport=store-fallback');
    return 0;
  }
}

async function usage() {
  out('store=' + STORE);
  try {
    const res = await nativeCall('GET', BASE + '/usage');
    out('usage=' + JSON.stringify(res.usage || res));
    out('transport=native');
    return 0;
  } catch (err) {
    const state = readStore();
    out('signals=' + state.signals.length);
    out('proposals=' + state.proposals.length);
    out('transport=store-fallback');
    return 0;
  }
}

async function catalog() {
  const url = '/minimax-desktop/api/v1/runtime/skills?agentName=mavis';
  try {
    const res = await nativeCall('GET', url);
    const list = res.skills || res.data || res;
    const arr = Array.isArray(list) ? list : (list.skills || []);
    out('catalog=' + arr.length);
    for (const s of arr) {
      const name = (s && typeof s === 'object') ? (s.name || s.slug || JSON.stringify(s)) : s;
      out('  ' + name);
    }
    return 0;
  } catch (err) {
    out('catalog=error ' + (err && err.message ? err.message : String(err)));
    return 1;
  }
}

async function main() {
  const argv = process.argv.slice(2);
  if (argv.length === 0) fail('usage: mavis skill <signal|proposal|evolve> <command> [options]');
  const opts = parseArgs(argv);
  const group = opts._[0];
  const action = opts._[1];

  if (group === 'skill' && action === 'signal') {
    if (opts._[2] === 'report') return reportSignal(opts);
    if (opts._[2] === 'cancel') return cancelSignal(opts);
    if (opts._[2] === 'list') return listSignals(opts);
    fail('usage: mavis skill signal <report|cancel|list>');
  }
  if (group === 'skill' && action === 'proposal') {
    if (opts._[2] === 'report') return reportProposal(opts);
    if (opts._[2] === 'cancel') return cancelProposal(opts);
    if (opts._[2] === 'mark-acted') return markActed(opts);
    if (opts._[2] === 'list') return listProposals(opts);
    fail('usage: mavis skill proposal <report|cancel|mark-acted|list>');
  }
  if (group === 'skill' && action === 'evolve') {
    if (opts._[2] === 'history') return history();
    if (opts._[2] === 'usage') return usage();
    fail('usage: mavis skill evolve <history|usage>');
  }
  if (group === 'skill' && action === 'usage') return usage();
  if (group === 'skill' && action === 'catalog') return catalog();
  fail('unknown command: mavis ' + argv.join(' '));
}

main()
  .then((code) => { if (transport) transport.stop(); process.exit(code || 0); })
  .catch((err) => {
    if (transport) transport.stop();
    process.stderr.write('mavis: ' + (err && err.message ? err.message : String(err)) + '\n');
    process.exit(1);
  });
