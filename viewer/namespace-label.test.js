const test = require('node:test');
const assert = require('node:assert/strict');
const { candidates, elideFromLeft } = require('./namespace-label.js');

test('namespace label candidates progressively remove leading segments', () => {
    assert.deepEqual(candidates('Radiant.ComponentModel.Severity'), [
        'Radiant.ComponentModel.Severity',
        'ComponentModel.Severity',
        'Severity'
    ]);
});

test('namespace labels retain the longest suffix that fits', () => {
    const name = 'Radiant.ComponentModel.Severity';
    assert.equal(elideFromLeft(name, candidate => candidate.length <= 32), name);
    assert.equal(elideFromLeft(name, candidate => candidate.length <= 24), 'ComponentModel.Severity');
    assert.equal(elideFromLeft(name, candidate => candidate.length <= 10), 'Severity');
});

test('namespace labels retain their only segment when none fit', () => {
    assert.equal(elideFromLeft('Radiant.ComponentModel.Severity', () => false), 'Severity');
});
