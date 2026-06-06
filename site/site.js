// ── Copy-to-clipboard ────────────────────────────────────────────
document.querySelectorAll('.copy').forEach((btn) => {
  btn.addEventListener('click', () => {
    const text = btn.getAttribute('data-copy');
    const done = () => {
      btn.textContent = 'copied ✓';
      btn.classList.add('copied');
      setTimeout(() => { btn.textContent = 'copy'; btn.classList.remove('copied'); }, 1600);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, fallback);
    } else { fallback(); }
    function fallback() {
      const ta = document.createElement('textarea');
      ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); } catch (e) {}
      document.body.removeChild(ta); done();
    }
  });
});

// ── Coverage chip: cycle rich → sparse → gap ─────────────────────
const COV_ORDER = ['rich', 'sparse', 'gap'];
document.querySelectorAll('.cov').forEach((chip) => {
  chip.title = 'cycle coverage band';
  chip.addEventListener('click', () => {
    const cur = chip.getAttribute('data-cov');
    const next = COV_ORDER[(COV_ORDER.indexOf(cur) + 1) % COV_ORDER.length];
    chip.setAttribute('data-cov', next);
    chip.lastChild.textContent = ' coverage: ' + next;
  });
});

// ── Tier tabs (install page: free vs cloud) ──────────────────────
document.querySelectorAll('[data-tabs]').forEach((group) => {
  const tabs = group.querySelectorAll('.tab');
  const panes = group.querySelectorAll('.tier-pane');
  tabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      const target = tab.getAttribute('data-tab');
      tabs.forEach((t) => t.classList.toggle('active', t === tab));
      panes.forEach((p) => p.classList.toggle('active', p.getAttribute('data-pane') === target));
    });
  });
});
