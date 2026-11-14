/*
 * Mobile touch-target regression for the TEL99 terminal.
 *
 * The terminal sets a 44px minimum touch height for its primary controls
 * (navigation, widget jump, widget list, sidebar toggle...). The chart
 * timeframe selector and the RSI/MACD switch were the exception at 30px/26px,
 * which is below both the app's own standard and the 44px/48px platform
 * guidelines. This test resolves the real CSS cascade for `min-height` on
 * those controls so a later rule cannot silently shrink them again.
 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const css = fs.readFileSync(path.join(__dirname, '..', 'site', 'terminal', 'terminal.css'), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');

// Parse the stylesheet into {media, selector, declarations, order} rules,
// keeping source order (later rules win ties on equal specificity).
function parseRules(text) {
  const rules = [];
  let order = 0;
  const walk = (chunk, media) => {
    let i = 0;
    while (i < chunk.length) {
      const open = chunk.indexOf('{', i);
      if (open === -1) break;
      const head = chunk.slice(i, open).trim();
      let depth = 1;
      let end = open + 1;
      while (end < chunk.length && depth) {
        if (chunk[end] === '{') depth++;
        else if (chunk[end] === '}') depth--;
        end++;
      }
      const body = chunk.slice(open + 1, end - 1);
      if (head.startsWith('@media')) walk(body, media.concat(head.slice(6).trim()));
      else if (!head.startsWith('@')) {
        for (const selector of head.split(',')) rules.push({ media, selector: selector.trim(), body, order: order++ });
      }
      i = end;
    }
  };
  walk(text, []);
  return rules;
}

function mediaMatches(media, width) {
  for (const condition of media) {
    const max = /\(max-width:\s*(\d+)px\)/.exec(condition);
    const min = /\(min-width:\s*(\d+)px\)/.exec(condition);
    if (max && width > Number(max[1])) return false;
    if (min && width < Number(min[1])) return false;
  }
  return true;
}

function specificity(selector) {
  const ids = (selector.match(/#[\w-]+/g) || []).length;
  const classes = (selector.match(/\.[\w-]+/g) || []).length + (selector.match(/\[/g) || []).length;
  const elements = (selector.match(/(?<![\w.#-])[a-zA-Z][\w-]*/g) || []).length;
  return [ids, classes, elements];
}

function resolvedValue(rules, selector, property, width) {
  let winner = null;
  for (const rule of rules) {
    if (rule.selector !== selector || !mediaMatches(rule.media, width)) continue;
    const match = new RegExp('(?:^|;)\\s*' + property + '\\s*:\\s*([^;]+)').exec(rule.body);
    if (!match) continue;
    const candidate = { spec: specificity(selector), order: rule.order, value: match[1].trim() };
    if (!winner || candidate.spec.join(',') > winner.spec.join(',') ||
        (candidate.spec.join(',') === winner.spec.join(',') && candidate.order >= winner.order)) {
      winner = candidate;
    }
  }
  return winner ? winner.value : null;
}

const px = (value) => (value ? Number(/^(\d+(?:\.\d+)?)px$/.exec(value)?.[1]) : NaN);

const rules = parseRules(css);
const TIMEFRAME = '.segmented button';
const MOMENTUM = '.osc-head .segmented button';

test('mobile: the chart timeframe selector keeps a 44px touch target', () => {
  for (const width of [320, 360, 390, 414, 700]) {
    const height = px(resolvedValue(rules, TIMEFRAME, 'min-height', width));
    assert.ok(height >= 44, `timeframe selector min-height at ${width}px was ${height}px, expected >= 44px`);
  }
});

test('mobile: the RSI/MACD switch keeps a 44px touch target', () => {
  for (const width of [320, 360, 390, 414, 700]) {
    const height = px(resolvedValue(rules, MOMENTUM, 'min-height', width));
    assert.ok(height >= 44, `momentum switch min-height at ${width}px was ${height}px, expected >= 44px`);
  }
});

test('the fix stays scoped to mobile and leaves the desktop density untouched', () => {
  for (const width of [701, 900, 1200]) {
    assert.equal(resolvedValue(rules, TIMEFRAME, 'min-height', width), '30px', `desktop timeframe height changed at ${width}px`);
    assert.equal(resolvedValue(rules, MOMENTUM, 'min-height', width), '26px', `desktop momentum height changed at ${width}px`);
  }
});
