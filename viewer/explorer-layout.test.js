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

test('node kinds use saturated fills with white text for readable labels', () => {
    const explorer = fs.readFileSync(path.join(__dirname, 'explorer.html'), 'utf8');

    assert.match(explorer, /selector: 'node',[\s\S]*?'background-color': '#006f77',[\s\S]*?'color': '#fff'/);
    assert.match(explorer, /selector: 'node\.class',[\s\S]*?'background-color': '#0078d4'/);
    assert.match(explorer, /selector: 'node\.interface',[\s\S]*?'background-color': '#6f42c1'/);
    assert.match(explorer, /selector: 'node\.struct',[\s\S]*?'background-color': '#007c91'/);
    assert.match(explorer, /selector: 'node\.enum',[\s\S]*?'background-color': '#9a6700'/);
});
