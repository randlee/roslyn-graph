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
