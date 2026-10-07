// Chooses namespace suffixes for narrow UI labels without hiding the most-specific segment.
(function (root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) {
        module.exports = api;
    }
    root.RoslynGraphNamespaceLabel = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
    function candidates(namespaceName) {
        const segments = String(namespaceName || '').split('.').filter(Boolean);
        if (segments.length === 0) return [''];
        return segments.map((_, index) => segments.slice(index).join('.'));
    }

    // `fits` receives each candidate, longest first. The final segment is always returned
    // so the browser can apply its ordinary overflow behavior only as a last resort.
    function elideFromLeft(namespaceName, fits) {
        const options = candidates(namespaceName);
        return options.find(candidate => fits(candidate)) || options[options.length - 1];
    }

    return { candidates, elideFromLeft };
});
