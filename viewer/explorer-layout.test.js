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

test('panel toggles are compact directional controls with accessible names', () => {
    const explorer = fs.readFileSync(path.join(__dirname, 'explorer.html'), 'utf8');

    assert.match(explorer, /class="icon-btn panel-toggle" id="sidebar-toggle"[\s\S]*?aria-label="Hide sidebar"[\s\S]*?>◀<\/button>/);
    assert.match(explorer, /class="icon-btn panel-toggle" id="details-toggle"[\s\S]*?aria-label="Hide details"[\s\S]*?>▶<\/button>/);
    assert.match(explorer, /sidebarToggle\.setAttribute\('aria-label', sidebarLabel\)/);
    assert.match(explorer, /detailsToggle\.setAttribute\('aria-label', detailsLabel\)/);
});

test('copying a graph uses a compact clipboard action', () => {
    const explorer = fs.readFileSync(path.join(__dirname, 'explorer.html'), 'utf8');

    assert.match(explorer, /<button class="icon-btn graph-action-btn" id="copy-graph-btn" disabled[\s\S]*?aria-label="Copy graph selection for Claude"[\s\S]*?>📋<\/button>/);
    assert.doesNotMatch(explorer, /📋 Copy for Claude/);
});

test('graph export actions are grouped after loading and use icon-only controls', () => {
    const explorer = fs.readFileSync(path.join(__dirname, 'explorer.html'), 'utf8');

    assert.match(explorer, /<div class="menu-button">[\s\S]*?<\/div>\s*<div class="graph-actions" aria-label="Graph actions">[\s\S]*?id="copy-graph-btn"[\s\S]*?<button class="icon-btn graph-action-btn" id="download-graph-btn" disabled[\s\S]*?aria-label="Download graph selection as JSON"[\s\S]*?>⬇<\/button>[\s\S]*?<\/div>/);
    assert.match(explorer, /\.graph-actions \{[\s\S]*?border-left: 1px solid #555;/);
    assert.doesNotMatch(explorer, />⬇ JSON<\/button>/);
});

test('the type copy action is a compact control in the detail heading', () => {
    const explorer = fs.readFileSync(path.join(__dirname, 'explorer.html'), 'utf8');

    assert.match(explorer, /<div class="details-title-row">[\s\S]*?<h2>\$\{kindIcon\} \$\{type\.name\}<\/h2>[\s\S]*?<button class="icon-btn copy-type-btn" onclick="copySelection\('type'\)"[\s\S]*?aria-label="Copy this type for Claude"[\s\S]*?>📋<\/button>[\s\S]*?<\/div>/);
    assert.match(explorer, /\.details-title-row \{[\s\S]*?display: flex;[\s\S]*?border-bottom: 2px solid #007acc;/);
    assert.doesNotMatch(explorer, /📋 Copy this type/);
});
