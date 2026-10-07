const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

test('both COSE layouts reserve space for type labels', () => {
    const explorer = fs.readFileSync(path.join(__dirname, 'explorer.html'), 'utf8');
    const layouts = [...explorer.matchAll(/name:\s*'cose'([\s\S]*?)(?=\}\s*\)|\}\s*;)/g)];

    assert.equal(layouts.length, 2, 'the explorer should configure its initial and rebuilt COSE layouts');
    for (const [, options] of layouts) {
        assert.match(options, /nodeDimensionsIncludeLabels:\s*true/);
        assert.match(options, /idealEdgeLength:\s*140/);
    }
});

test('nodes use namespace fills with white text and kind-specific shapes', () => {
    const explorer = fs.readFileSync(path.join(__dirname, 'explorer.html'), 'utf8');

    assert.match(explorer, /selector: 'node',[\s\S]*?'background-color': 'data\(palette\)',[\s\S]*?'color': '#fff'/);

    for (const [kind, shape] of [
        ['class', 'rectangle'],
        ['interface', 'diamond'],
        ['struct', 'octagon'],
        ['enum', 'triangle']
    ]) {
        const match = explorer.match(new RegExp(`selector: 'node\\.${kind}',\\s*style: \\{([\\s\\S]*?)\\n\\s*\\}\\s*\\}`));
        assert.ok(match, `missing ${kind} node style`);
        assert.match(match[1], new RegExp(`'shape': '${shape}'`));
        assert.doesNotMatch(match[1], /background-color/);
    }
});

test('namespace labels preserve their full name while eliding leading segments on resize', () => {
    const explorer = fs.readFileSync(path.join(__dirname, 'explorer.html'), 'utf8');

    assert.match(explorer, /<script src="namespace-label\.js"><\/script>/);
    assert.match(explorer, /class="namespace-label" title="\$\{escapeHtml\(ns\.name\)\}" aria-label="\$\{escapeHtml\(ns\.name\)\}"/);
    assert.match(explorer, /class="namespace-name" data-full-namespace="\$\{escapeHtml\(ns\.name\)\}"/);
    assert.match(explorer, /\.namespace-name \{[\s\S]*?flex: 1 1 0;/);
    assert.match(explorer, /RoslynGraphNamespaceLabel\.elideFromLeft\(fullName/);
    assert.match(explorer, /scheduleNamespaceLabelElision\(\);/);
});

test('namespace palette picker is an accessible, arrowless color swatch', () => {
    const explorer = fs.readFileSync(path.join(__dirname, 'explorer.html'), 'utf8');

    assert.match(explorer, /<select class="palette-picker"[\s\S]*?style="--palette-color: \$\{palette\.color\}"[\s\S]*?aria-label="Color palette for \$\{escapeHtml\(ns\.name\)\}"/);
    assert.match(explorer, /\.palette-picker \{[\s\S]*?appearance: none;[\s\S]*?background: var\(--palette-color\);/);
    assert.match(explorer, /\.palette-picker:focus-visible \{[\s\S]*?outline: 2px solid/);
    assert.match(explorer, /\.palette-picker option \{[\s\S]*?color: #1e1e1e;/);
    assert.doesNotMatch(explorer, /palette-swatch|palette-select/);
    assert.match(explorer, /document\.querySelectorAll\('\.palette-picker'\)/);
});
