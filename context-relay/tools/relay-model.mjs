#!/usr/bin/env node
// Executable model of Context Relay: workflow checking and blast-radius analysis.
// Zero dependencies. Node >= 18.
//
//   node tools/relay-model.mjs check              validate model, workflows, cycles, doc freshness
//   node tools/relay-model.mjs report <section>   print one generated markdown section
//   node tools/relay-model.mjs sync-docs          rewrite generated sections in docs/*.md

import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
export const ROOT = resolve(HERE, '..');
export const MODEL_PATH = join(ROOT, 'model', 'relay-model.json');
export const DOC_PATHS = [join(ROOT, 'docs', 'WORKFLOWS.md'), join(ROOT, 'docs', 'BLAST_RADIUS.md')];

export const loadModel = (path = MODEL_PATH) => JSON.parse(readFileSync(path, 'utf8'));

// ---------------------------------------------------------------- structure

const KINDS = ['change', 'runtime', 'trust'];
const THREATS = ['integrity', 'confidentiality'];

// A view is one propagation question over one edge kind. Trust edges are data flow;
// integrity asks where attacker content goes, confidentiality where secrets go.
export const VIEWS = {
  change: { kind: 'change', threat: null },
  runtime: { kind: 'runtime', threat: null },
  integrity: { kind: 'trust', threat: 'integrity' },
  confidentiality: { kind: 'trust', threat: 'confidentiality', sources: (m) => m.components.filter((c) => c.secretOrigin).map((c) => c.id) },
};
const TYPES = new Set(['Source', 'External', 'Pack', 'Text', 'Wrapped', 'Sink']);

export function edges(m) {
  return m.edges.map(([from, to, kind, controls = null, flag = null]) => ({
    from, to, kind, flag, baseline: flag === 'baseline',
    controls: controls === null ? [] : [].concat(controls),
  }));
}

export function validateModel(m) {
  const errs = [];
  const ids = new Set();
  for (const c of m.components) {
    if (ids.has(c.id)) errs.push(`duplicate component ${c.id}`);
    ids.add(c.id);
  }
  for (const e of edges(m)) {
    const tag = `edge ${e.from}->${e.to} (${e.kind})`;
    if (!ids.has(e.from)) errs.push(`${tag}: unknown source`);
    if (!ids.has(e.to)) errs.push(`${tag}: unknown target`);
    if (!KINDS.includes(e.kind)) errs.push(`${tag}: unknown kind`);
    for (const c of e.controls) if (!m.controls[c]) errs.push(`${tag}: unknown control ${c}`);
    if (e.flag !== null && e.flag !== 'baseline') errs.push(`${tag}: unknown flag ${e.flag}`);
  }
  for (const [id, c] of Object.entries(m.controls)) {
    if (c.strength !== 'full' && c.strength !== 'partial') errs.push(`control ${id}: strength must be full|partial`);
    for (const t of c.threats ?? []) if (!THREATS.includes(t)) errs.push(`control ${id}: unknown threat ${t}`);
  }
  for (const [op, p] of Object.entries(m.primitives)) {
    if (!TYPES.has(p.in) || !TYPES.has(p.out)) errs.push(`primitive ${op}: unknown type`);
    if (p.surfaces !== '*') for (const s of p.surfaces) if (!ids.has(s)) errs.push(`primitive ${op}: unknown surface ${s}`);
  }
  const steps = [];
  for (const r of [...m.entries, ...m.exits]) steps.push(...r.steps.map((s) => [r.id, s]));
  for (const w of [...m.workflows, ...m.antiWorkflows]) {
    const first = w.path[0];
    if (!w.start && !(typeof first === 'string' && routeById(m).get(first)?.start)) errs.push(`${w.id}: must begin with an entry route or declare start`);
    for (const item of w.path) {
      if (typeof item === 'object') steps.push([w.id, item]);
      else if (item !== 'gate' && !routeById(m).has(item)) errs.push(`${w.id}: unknown route ${item}`);
    }
  }
  steps.push(['gate', m.gate]);
  for (const [owner, s] of steps) {
    if (!m.primitives[s.op]) errs.push(`${owner}: unknown op ${s.op}`);
    if (!ids.has(s.at)) errs.push(`${owner}: unknown surface ${s.at}`);
    if (!m.actors.includes(s.by)) errs.push(`${owner}: unknown actor ${s.by}`);
    if (s.sink && !m.sinks[s.sink]) errs.push(`${owner}: unknown sink ${s.sink}`);
    if (s.fmt && !(s.fmt in m.formats)) errs.push(`${owner}: unknown format ${s.fmt}`);
    if ((s.op === 'inject' || s.op === 'emit') && !s.sink) errs.push(`${owner}: ${s.op} needs a sink`);
    if (s.op === 'render' && !s.fmt) errs.push(`${owner}: render needs a fmt`);
  }
  for (const f of m.failureModes) {
    if (!ids.has(f.at)) errs.push(`${f.id}: unknown component ${f.at}`);
    for (const c of f.controls) if (!m.controls[c]) errs.push(`${f.id}: unknown control ${c}`);
    for (const t of [f.inherent, f.residual]) {
      if (t.length !== 3 || t.some((x) => !Number.isInteger(x) || x < 1 || x > 5)) errs.push(`${f.id}: S/L/D must be integers 1..5`);
    }
  }
  for (const c of m.acceptedCycles) for (const n of c.nodes) if (!ids.has(n)) errs.push(`accepted cycle: unknown node ${n}`);
  return errs;
}

// Invariants that hold over the primitive set and components, independent of any workflow.
export function globalInvariants(m) {
  const errs = [];
  for (const [op, p] of Object.entries(m.primitives)) {
    if (p.effects.includes('network')) errs.push(`INV-NO-NET: ${op} declares a network effect`);
    if (p.effects.includes('exec')) {
      const humanOnly = Array.isArray(p.actors) && p.actors.length === 1 && p.actors[0] === 'human';
      const cliOnly = Array.isArray(p.surfaces) && p.surfaces.length === 1 && p.surfaces[0] === 'cli';
      if (!humanOnly || !cliOnly) errs.push(`INV-EXEC-HUMAN: ${op} executes commands but is not human-only on the CLI`);
    }
  }
  const byId = new Map(m.components.map((c) => [c.id, c]));
  const hookSurfaces = new Set();
  const collect = (s) => { if (s.by === 'hook') hookSurfaces.add(s.at); };
  for (const r of [...m.entries, ...m.exits]) r.steps.forEach(collect);
  for (const at of hookSurfaces) {
    if (byId.get(at)?.failPolicy !== 'open') errs.push(`INV-FAILOPEN: ${at} runs in a host hook without failPolicy "open"`);
  }
  return errs;
}

// ---------------------------------------------------------------- workflows

const routeCache = new WeakMap();
function routeById(m) {
  if (!routeCache.has(m)) routeCache.set(m, new Map([...m.entries, ...m.exits].map((r) => [r.id, r])));
  return routeCache.get(m);
}

// A workflow path is a list of route ids, the literal 'gate', and inline steps.
// An entry route (one with `start`) opens a new segment: the pack crossed a boundary.
export function expand(m, wf) {
  const segments = [];
  let cur = null;
  const open = (start) => { cur = { start, steps: [] }; segments.push(cur); };
  if (wf.start) open(wf.start);
  for (const item of wf.path) {
    if (item === 'gate') { cur.steps.push(m.gate); continue; }
    if (typeof item === 'object') { cur.steps.push(item); continue; }
    const r = routeById(m).get(item);
    if (r.start) open(r.start);
    cur.steps.push(...r.steps);
  }
  return segments;
}

export const effectiveTrust = (v) => (v.labels.has('approved') ? 'user' : v.origin);

// Abstract interpretation: the value carries a type, a label set and an origin.
// A step that violates any rule confers no labels, so a failed approval grants nothing.
export function checkWorkflow(m, wf) {
  const violations = [];
  expand(m, wf).forEach((seg, si) => {
    let v = { t: seg.start.t, origin: seg.start.trust ?? null, labels: new Set(), fmt: null };
    seg.steps.forEach((step, i) => {
      const where = `${si + 1}.${i + 1}:${step.op}@${step.at}/${step.by}`;
      const p = m.primitives[step.op];
      let ok = true;
      const fail = (rule, msg) => { ok = false; violations.push({ rule, where, msg }); };

      if (step.op === 'inject') {
        if (v.t !== 'Wrapped') fail('INV-WRAP', `inject needs Wrapped, got ${v.t}`);
      } else if (step.op === 'emit') {
        if (v.t !== 'Text' && v.t !== 'Wrapped') fail('INV-TYPE', `emit needs Text, got ${v.t}`);
      } else if (v.t !== p.in) {
        fail('INV-TYPE', `${step.op} needs ${p.in}, got ${v.t}`);
      }
      if (p.surfaces !== '*' && !p.surfaces.includes(step.at)) fail('INV-SURFACE', `${step.op} is not offered on ${step.at}`);
      if (p.actors !== '*' && !p.actors.includes(step.by)) fail('INV-ACTOR', `${step.op} cannot be performed by ${step.by}`);
      for (const l of p.requires ?? []) if (!v.labels.has(l)) fail('INV-REQ', `${step.op} requires ${l}`);
      if (step.op === 'capture' && wf.cyclic && !step.stripInjected) fail('INV-LOOP-ECHO', 'cyclic capture must strip previously injected regions');

      const trust = effectiveTrust(v);
      const serve = m.trust.serve?.[step.at];
      if (step.op === 'render' && serve && !serve.includes(trust)) fail('INV-SERVE', `${step.at} serves only ${serve.join('|')} packs, got ${trust}`);

      if (step.op === 'inject' || step.op === 'emit') {
        const sink = m.sinks[step.sink];
        if (step.op === 'inject' && sink.class !== 'context') fail('INV-SINK-CLASS', `inject into ${sink.class} sink ${step.sink}`);
        if (step.op === 'emit' && sink.class === 'context') fail('INV-SINK-CLASS', `context sink ${step.sink} must be reached through wrap+inject`);
        if (step.op === 'inject' && step.by === 'hook') {
          if (!m.trust.autoInject.includes(trust)) fail('INV-AUTO-TRUST', `auto-inject of a ${trust} pack`);
          if (!v.labels.has('sealed')) fail('INV-AUTO-SEALED', 'auto-inject of an unsealed pack');
        }
        if (sink.class === 'instruction' && !m.trust.instruction.includes(trust)) fail('INV-INSTR-TRUST', `${trust} pack into instruction sink ${step.sink}`);
        if (sink.requiresSealed && !v.labels.has('sealed')) fail('INV-SHARE-SEALED', `${step.sink} requires a sealed pack`);
        if (sink.capacityChars != null) {
          const max = m.formats[v.fmt]?.maxChars ?? null;
          const need = max === null ? Infinity : max + (v.t === 'Wrapped' ? m.wrapOverheadChars : 0);
          if (need > sink.capacityChars) fail('INV-BUDGET', `${v.fmt} render (${need} chars) exceeds ${step.sink} (${sink.capacityChars})`);
        }
      }

      const next = { t: p.out, origin: v.origin, labels: new Set(v.labels), fmt: v.fmt };
      if (p.origin) { next.origin = p.origin; next.labels = new Set(); }
      if (step.op === 'render') next.fmt = step.fmt;
      if (ok) for (const l of p.adds ?? []) next.labels.add(l);
      for (const l of p.removes ?? []) next.labels.delete(l);
      v = next;
    });
  });
  return { ok: violations.length === 0, violations, rules: [...new Set(violations.map((x) => x.rule))].sort() };
}

const GATEABLE = new Set(['INV-AUTO-TRUST', 'INV-INSTR-TRUST', 'INV-SERVE']);

// Every entry composed with every exit. A cell is 'direct' when it checks as is,
// 'gate' when only trust rules fail and inserting a human approval fixes it.
export function routeMatrix(m) {
  const cells = [];
  for (const e of m.entries) {
    for (const x of m.exits) {
      const direct = checkWorkflow(m, { path: [e.id, x.id] });
      let verdict = 'direct';
      let rules = [];
      if (!direct.ok) {
        rules = direct.rules;
        const gated = direct.rules.every((r) => GATEABLE.has(r)) && checkWorkflow(m, { path: [e.id, 'gate', x.id] }).ok;
        verdict = gated ? 'gate' : 'forbidden';
      }
      cells.push({ entry: e.id, exit: x.id, verdict, rules });
    }
  }
  return cells;
}

// ---------------------------------------------------------------- blast radius

// Exposure levels: 3 unmitigated, 2 damped (only partial controls on the best path), 1 contained.
export const LEVEL = { unmitigated: 3, damped: 2, contained: 1 };

function adjacency(m, kind, baseline) {
  const adj = new Map();
  for (const e of edges(m)) {
    if (e.kind !== kind || (e.baseline && !baseline)) continue;
    if (!adj.has(e.from)) adj.set(e.from, []);
    adj.get(e.from).push(e);
  }
  return adj;
}

// Controls without `threats` apply to every view; the others only to their threats.
const applies = (control, threat) => !control.threats || control.threats.includes(threat);

function edgeStrength(m, e, threat, disabled) {
  const live = e.controls.filter((c) => !disabled.has(c) && applies(m.controls[c], threat)).map((c) => m.controls[c].strength);
  return live.includes('full') ? 'full' : live.includes('partial') ? 'partial' : null;
}

export function propagate(m, source, view, { disabled = new Set(), baseline = false } = {}) {
  const { kind, threat } = VIEWS[view];
  const adj = adjacency(m, kind, baseline);
  const level = new Map([[source, LEVEL.unmitigated]]);
  const queue = [source];
  while (queue.length) {
    const u = queue.shift();
    const s = level.get(u);
    for (const e of adj.get(u) ?? []) {
      const strength = edgeStrength(m, e, threat, disabled);
      const ns = strength === 'full' ? LEVEL.contained : strength === 'partial' ? Math.min(s, LEVEL.damped) : s;
      if ((level.get(e.to) ?? 0) < ns) { level.set(e.to, ns); queue.push(e.to); }
    }
  }
  level.delete(source);
  const pick = (n) => [...level].filter(([, l]) => l === n).map(([id]) => id).sort();
  return { unmitigated: pick(3), damped: pick(2), contained: pick(1) };
}

export function radiusTable(m, view, opts = {}) {
  const { kind, sources: pick } = VIEWS[view];
  const sources = pick ? pick(m) : [...new Set(edges(m).filter((e) => e.kind === kind && (!e.baseline || opts.baseline)).map((e) => e.from))];
  return sources
    .map((id) => ({ id, ...propagate(m, id, view, opts) }))
    .filter((r) => r.unmitigated.length + r.damped.length + r.contained.length > 0)
    .sort((a, b) => b.unmitigated.length - a.unmitigated.length || b.damped.length - a.damped.length || a.id.localeCompare(b.id));
}

// Marginal value of a control: exposure pairs (source, node) that would become
// unmitigated if the control were removed, summed over all sources and kinds.
export function controlValue(m) {
  const used = new Set(edges(m).filter((e) => !e.baseline).flatMap((e) => e.controls));
  const unmitigatedPairs = (view, disabled) =>
    radiusTable(m, view, { disabled }).reduce((n, r) => n + r.unmitigated.length, 0);
  const base = Object.fromEntries(Object.keys(VIEWS).map((v) => [v, unmitigatedPairs(v, new Set())]));
  return [...used]
    .map((id) => {
      const off = new Set([id]);
      const byView = Object.fromEntries(
        Object.keys(VIEWS).map((v) => [v, unmitigatedPairs(v, off) - base[v]]).filter(([, n]) => n > 0),
      );
      return { id, strength: m.controls[id].strength, status: m.controls[id].status, byView, protected: Object.values(byView).reduce((a, b) => a + b, 0) };
    })
    .sort((a, b) => b.protected - a.protected || a.id.localeCompare(b.id));
}

// Elementary cycles of the trust graph through a data-layer node and an agent:
// the loops through which injected content can persist across sessions.
export function persistentCycles(m, { baseline = false } = {}) {
  const adj = adjacency(m, 'trust', baseline);
  const layer = new Map(m.components.map((c) => [c.id, c.layer]));
  const agent = new Set(m.components.filter((c) => c.agent).map((c) => c.id));
  const nodes = m.components.map((c) => c.id);
  const idx = new Map(nodes.map((n, i) => [n, i]));
  const found = [];
  for (const s of nodes) {
    const path = [];
    const onPath = new Set([s]);
    const dfs = (u) => {
      for (const e of adj.get(u) ?? []) {
        if (e.to === s) found.push([...path, e]);
        else if (idx.get(e.to) > idx.get(s) && !onPath.has(e.to)) {
          onPath.add(e.to); path.push(e); dfs(e.to); path.pop(); onPath.delete(e.to);
        }
      }
    };
    dfs(s);
  }
  const accepted = m.acceptedCycles.map((c) => ({ ...c, key: [...c.nodes].sort().join(',') }));
  return found
    .filter((cyc) => cyc.some((e) => layer.get(e.from) === 'data') && cyc.some((e) => agent.has(e.from)))
    .map((cyc) => {
      const nodesOn = cyc.map((e) => e.from);
      const controls = [...new Set(cyc.flatMap((e) => e.controls).filter((c) => applies(m.controls[c], 'integrity')))];
      const contained = cyc.some((e) => edgeStrength(m, e, 'integrity', new Set()) === 'full');
      const key = [...nodesOn].sort().join(',');
      const acc = accepted.find((a) => a.key === key) ?? null;
      return { nodes: nodesOn, controls, contained, accepted: acc?.decision ?? null, baseline: cyc.some((e) => e.baseline) };
    });
}

// ---------------------------------------------------------------- risks

export const rpn = ([s, l, d]) => s * l * d;

export function rankRisks(m) {
  return m.failureModes
    .map((f) => ({ ...f, inherentRpn: rpn(f.inherent), residualRpn: rpn(f.residual) }))
    .sort((a, b) => b.residualRpn - a.residualRpn || b.residual[0] - a.residual[0] || a.id.localeCompare(b.id));
}

// ---------------------------------------------------------------- full check

export function runChecks(m) {
  const problems = [...validateModel(m), ...globalInvariants(m)];
  if (problems.length) return problems; // later checks assume a well-formed model
  for (const w of m.workflows) {
    const r = checkWorkflow(m, w);
    for (const v of r.violations) problems.push(`${w.id} ${v.rule} at ${v.where}: ${v.msg}`);
  }
  for (const a of m.antiWorkflows) {
    const got = checkWorkflow(m, a).rules.join(',');
    const want = [...a.expect].sort().join(',');
    if (got !== want) problems.push(`${a.id} expected [${want}] got [${got}]`);
  }
  const cycles = persistentCycles(m);
  for (const c of cycles) {
    if (!c.contained && !c.accepted) problems.push(`G-TRUST-CYCLE: uncontained persistent loop ${c.nodes.join(' -> ')}`);
  }
  const live = new Set(cycles.filter((c) => !c.contained).map((c) => [...c.nodes].sort().join(',')));
  for (const a of m.acceptedCycles) {
    if (!live.has([...a.nodes].sort().join(','))) problems.push(`G-TRUST-CYCLE: accepted cycle ${a.nodes.join(' -> ')} is contained or absent; remove it`);
  }
  return problems;
}

// ---------------------------------------------------------------- markdown

const esc = (s) => String(s).replace(/\|/g, '\\|');
function table(headers, rows) {
  return [
    `| ${headers.map(esc).join(' | ')} |`,
    `|${headers.map(() => '---').join('|')}|`,
    ...rows.map((r) => `| ${r.map(esc).join(' | ')} |`),
  ].join('\n');
}
const list = (xs) => (xs.length ? xs.join(', ') : '—');
const pathText = (path) => path.map((p) => (typeof p === 'string' ? p : `${p.op}@${p.at}`)).join(' → ');

export const SECTIONS = {
  primitives(m) {
    const any = (x) => (x === '*' ? 'any' : x.join(', '));
    return table(
      ['Op', 'Type', 'Requires', 'Adds', 'Removes', 'Origin', 'Surfaces', 'Actors', 'Effects'],
      Object.entries(m.primitives).map(([op, p]) => [
        op, `${p.in} → ${p.out}`, list(p.requires ?? []), list(p.adds ?? []), list(p.removes ?? []),
        p.origin ?? '—', any(p.surfaces), any(p.actors), list(p.effects),
      ]),
    );
  },

  workflows(m) {
    return table(
      ['ID', 'Workflow', 'Composition', 'Scenarios', 'Verdict'],
      m.workflows.map((w) => {
        const r = checkWorkflow(m, w);
        return [w.id, w.name + (w.cyclic ? ' (cyclic)' : ''), pathText(w.path), list(w.scenarios ?? []), r.ok ? 'passes' : r.rules.join(', ')];
      }),
    );
  },

  anti(m) {
    return table(
      ['ID', 'Rejected composition', 'Path', 'Rules fired'],
      m.antiWorkflows.map((a) => [a.id, a.name, pathText(a.path), checkWorkflow(m, a).rules.join(', ')]),
    );
  },

  routes(m) {
    const cells = routeMatrix(m);
    const sym = { direct: 'ok', gate: 'gate', forbidden: 'no' };
    const rows = m.entries.map((e) => [
      `${e.id} ${e.name}`,
      ...m.exits.map((x) => sym[cells.find((c) => c.entry === e.id && c.exit === x.id).verdict]),
    ]);
    const n = (v) => cells.filter((c) => c.verdict === v).length;
    const why = [...new Set(cells.filter((c) => c.verdict === 'gate').flatMap((c) => c.rules))].sort();
    return [
      table(['Entry \\ Exit', ...m.exits.map((x) => x.id)], rows),
      '',
      table(['Exit', 'Name'], m.exits.map((x) => [x.id, x.name])),
      '',
      `${m.entries.length} entries + ${m.exits.length} exits = ${m.entries.length + m.exits.length} route definitions → ` +
        `${cells.length} compositions: ${n('direct')} direct, ${n('gate')} need a human approval (${why.join(', ')}), ${n('forbidden')} forbidden.`,
    ].join('\n');
  },

  'radius-integrity': (m) => radiusSection(m, 'integrity'),
  'radius-confidentiality': (m) => radiusSection(m, 'confidentiality'),
  'radius-runtime': (m) => radiusSection(m, 'runtime'),
  'radius-change': (m) => radiusSection(m, 'change'),

  controls(m) {
    return table(
      ['Control', 'Strength', 'Status', 'Pairs protected', 'By view', 'Mechanism'],
      controlValue(m).map((c) => [
        c.id, c.strength, c.status, c.protected,
        list(Object.entries(c.byView).map(([k, n]) => `${k} ${n}`)),
        m.controls[c.id].mechanism,
      ]),
    );
  },

  cycles(m) {
    const rows = (cs) => cs.map((c) => [
      [...c.nodes, c.nodes[0]].join(' → '),
      list(c.controls),
      c.contained ? 'contained' : c.accepted ? `accepted (${c.accepted})` : 'OPEN',
    ]);
    const delta = persistentCycles(m);
    const absolute = persistentCycles(m, { baseline: true }).filter((c) => c.baseline);
    return [
      '**Added by Context Relay (baseline edges excluded):**',
      '',
      table(['Loop', 'Controls on loop', 'Status'], rows(delta)),
      '',
      '**Present only because of host capabilities (baseline edges), shown for completeness:**',
      '',
      table(['Loop', 'Controls on loop', 'Status'], rows(absolute)),
    ].join('\n');
  },

  risks(m) {
    return table(
      ['Rank', 'ID', 'Failure mode', 'Kind', 'Inherent S·L·D', 'Residual S·L·D', 'RPN', 'Controls', 'Level'],
      rankRisks(m).map((f, i) => [
        i + 1, f.id, f.title, f.kind,
        `${f.inherent.join('·')} = ${f.inherentRpn}`, `${f.residual.join('·')} = ${f.residualRpn}`,
        f.residualRpn, f.controls.join(', '), `L${f.level}`,
      ]),
    );
  },

  backlog(m) {
    const partial = Object.entries(m.controls).filter(([, c]) => c.strength === 'partial');
    return table(
      ['Control', 'θ measured', 'θ target', 'Harness'],
      partial.map(([id, c]) => [id, c.theta ?? 'unmeasured', c.thetaTarget ?? 'to set', c.verify]),
    );
  },
};

// Impact column: the agents, egress points and host reached, with their exposure level.
// For confidentiality only egress counts: a secret that stays on the host is not exposed.
function radiusSection(m, view) {
  const counts = view === 'confidentiality' ? (c) => c.egress : (c) => c.agent || c.egress || c.layer === 'sink';
  const marked = new Set(m.components.filter(counts).map((c) => c.id));
  const name = { 3: 'unmitigated', 2: 'damped', 1: 'contained' };
  const rows = radiusTable(m, view).map((r) => {
    const impact = [[r.unmitigated, 3], [r.damped, 2], [r.contained, 1]]
      .flatMap(([ids, l]) => ids.filter((id) => marked.has(id)).map((id) => `${id} ${name[l]}`));
    return [r.id, r.unmitigated.length, r.damped.length, r.contained.length, list(r.unmitigated), list(impact)];
  });
  const label = view === 'confidentiality' ? 'Egress impact' : 'Agent / egress / host impact';
  return table(['Source', 'Unmitigated', 'Damped', 'Contained', 'Unmitigated reach', label], rows);
}

// ---------------------------------------------------------------- doc sync

const BLOCK = /<!-- relay-model:begin ([\w-]+) -->\n[\s\S]*?<!-- relay-model:end \1 -->/g;

export function syncText(m, text) {
  return text.replace(BLOCK, (_, name) => {
    if (!SECTIONS[name]) throw new Error(`unknown generated section ${name}`);
    return `<!-- relay-model:begin ${name} -->\n${SECTIONS[name](m)}\n<!-- relay-model:end ${name} -->`;
  });
}

export function staleDocs(m, paths = DOC_PATHS) {
  return paths.filter((p) => { const t = readFileSync(p, 'utf8'); return syncText(m, t) !== t; });
}

// ---------------------------------------------------------------- cli

function main([cmd, arg]) {
  const m = loadModel();
  if (cmd === 'check') {
    const problems = runChecks(m);
    if (!problems.length) for (const p of staleDocs(m)) problems.push(`stale generated section in ${p}; run sync-docs`);
    const cells = routeMatrix(m);
    console.log(`model: ${m.components.length} components, ${m.edges.length} edges, ${Object.keys(m.controls).length} controls, ` +
      `${m.workflows.length} workflows, ${m.antiWorkflows.length} anti-workflows, ${cells.length} route compositions`);
    for (const p of problems) console.log(`FAIL ${p}`);
    console.log(problems.length ? `${problems.length} problem(s)` : 'all checks pass');
    return problems.length ? 1 : 0;
  }
  if (cmd === 'report' && SECTIONS[arg]) { console.log(SECTIONS[arg](m)); return 0; }
  if (cmd === 'sync-docs') {
    for (const p of DOC_PATHS) writeFileSync(p, syncText(m, readFileSync(p, 'utf8')));
    return 0;
  }
  console.error(`usage: relay-model.mjs check | sync-docs | report <${Object.keys(SECTIONS).join('|')}>`);
  return 2;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exitCode = main(process.argv.slice(2));
}
