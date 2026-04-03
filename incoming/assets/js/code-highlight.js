(function () {
  function escapeHtml(text) {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  var KEYWORDS = new Set(['import', 'from', 'export', 'default', 'return', 'const', 'let', 'var', 'function', 'if', 'else', 'await', 'async', 'new', 'class', 'extends', 'try', 'catch', 'finally', 'throw', 'null', 'true', 'false']);
  var BUILTINS = new Set(['useState', 'useRef', 'useEffect', 'fetch', 'FormData', 'Promise', 'Array', 'Object', 'JSON', 'console']);

  function readWhile(code, start, matcher) {
    var idx = start;
    while (idx < code.length && matcher(code[idx], idx)) {
      idx += 1;
    }
    return idx;
  }

  function readString(code, start) {
    var quote = code[start];
    var idx = start + 1;
    while (idx < code.length) {
      var ch = code[idx];
      if (ch === '\\') {
        idx += 2;
        continue;
      }
      idx += 1;
      if (ch === quote) {
        break;
      }
    }
    return idx;
  }

  function tokenClass(token) {
    if (KEYWORDS.has(token)) {
      return 'tok-keyword';
    }
    if (BUILTINS.has(token)) {
      return 'tok-builtin';
    }
    if (/^[A-Z][A-Za-z0-9_]*$/.test(token)) {
      return 'tok-type';
    }
    return '';
  }

  function wrapToken(cls, value) {
    if (!cls) {
      return escapeHtml(value);
    }
    return '<span class="' + cls + '">' + escapeHtml(value) + '</span>';
  }

  function highlight(code) {
    var out = [];
    var idx = 0;

    while (idx < code.length) {
      var ch = code[idx];
      var next = idx + 1 < code.length ? code[idx + 1] : '';

      if (ch === '/' && next === '/') {
        var commentEnd = readWhile(code, idx, function (current) {
          return current !== '\n';
        });
        out.push('<span class="tok-comment">' + escapeHtml(code.slice(idx, commentEnd)) + '</span>');
        idx = commentEnd;
        continue;
      }

      if (ch === '"' || ch === '\'' || ch === '`') {
        var stringEnd = readString(code, idx);
        out.push('<span class="tok-string">' + escapeHtml(code.slice(idx, stringEnd)) + '</span>');
        idx = stringEnd;
        continue;
      }

      if (/[0-9]/.test(ch)) {
        var numberEnd = readWhile(code, idx, function (current) {
          return /[0-9.]/.test(current);
        });
        out.push('<span class="tok-number">' + escapeHtml(code.slice(idx, numberEnd)) + '</span>');
        idx = numberEnd;
        continue;
      }

      if (/[A-Za-z_$]/.test(ch)) {
        var identEnd = readWhile(code, idx, function (current) {
          return /[A-Za-z0-9_$]/.test(current);
        });
        var ident = code.slice(idx, identEnd);
        out.push(wrapToken(tokenClass(ident), ident));
        idx = identEnd;
        continue;
      }

      out.push(escapeHtml(ch));
      idx += 1;
    }

    return out.join('');
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.pse-doc-shell pre code, .nei-article pre code').forEach(function (node) {
      var raw = node.textContent || '';
      if (!raw.trim()) {
        return;
      }
      node.innerHTML = highlight(raw);
    });
  });
})();
