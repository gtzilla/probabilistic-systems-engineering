(function () {
  function escapeHtml(text) {
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function highlight(code) {
    var html = escapeHtml(code);
    html = html.replace(/(\/\/.*$)/gm, '<span class="tok-comment">$1</span>');
    html = html.replace(/("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|`(?:[^`\\]|\\.)*`)/g, '<span class="tok-string">$1</span>');
    html = html.replace(/\b(import|from|export|default|return|const|let|var|function|if|else|await|async|new|class|extends|try|catch|finally|throw)\b/g, '<span class="tok-keyword">$1</span>');
    html = html.replace(/\b(useState|useRef|useEffect|fetch|FormData)\b/g, '<span class="tok-builtin">$1</span>');
    html = html.replace(/\b([A-Z][A-Za-z0-9_]*)\b/g, '<span class="tok-type">$1</span>');
    html = html.replace(/\b(\d+(?:\.\d+)?)\b/g, '<span class="tok-number">$1</span>');
    return html;
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.pse-feature-block pre code').forEach(function (node) {
      var raw = node.textContent || '';
      node.innerHTML = highlight(raw);
    });
  });
})();
