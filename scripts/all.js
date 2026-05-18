// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

(function () {
  function msGetSelected(wrapId) {
    const boxes = [...document.querySelectorAll(`#${wrapId} .ms-panel input`)];
    const checked = boxes.filter(b => b.checked).map(b => b.value);
    return checked.length === boxes.length ? null : new Set(checked);
  }

  function msUpdateLabel(wrapId) {
    const boxes = [...document.querySelectorAll(`#${wrapId} .ms-panel input`)];
    const checked = boxes.filter(b => b.checked);
    const label = document.querySelector(`#${wrapId} .ms-label`);
    if (!label) return;
    if (checked.length === 0 || checked.length === boxes.length) label.textContent = 'All';
    else if (checked.length === 1) label.textContent = checked[0].value;
    else label.textContent = `${checked.length} selected`;
  }

  function applyFilters() {
    const sf  = msGetSelected('ms-status');
    const suf = msGetSelected('ms-suite');
    let vi = 0, total = 0, passed = 0, failed = 0, skipped = 0;

    document.querySelectorAll('#suite-table .suite-row').forEach(row => {
      const exp = document.getElementById(row.dataset.expand);
      const suiteOk = !suf || suf.has(row.dataset.suite);

      let visible = 0;
      if (exp) {
        exp.querySelectorAll('.expand-body > .tc-detail, .expand-body > div.tc-row').forEach(el => {
          const s = el.dataset.status;
          const ok = !sf || sf.has(s);
          el.hidden = !ok;
          if (ok) visible++;
        });
      }

      const show = suiteOk && (!sf || visible > 0);
      row.hidden = !show;
      if (!show) {
        if (exp) exp.hidden = true;
        row.classList.remove('open');
      } else {
        row.classList.toggle('even', vi % 2 === 0);
        row.classList.toggle('odd',  vi % 2 !== 0);
        vi++;
        if (exp) {
          exp.querySelectorAll('.expand-body > .tc-detail, .expand-body > div.tc-row').forEach(el => {
            if (el.hidden) return;
            const s = el.dataset.status;
            if (s === 'passed') passed++;
            else if (s === 'failed') failed++;
            else if (s === 'skipped') skipped++;
            total++;
          });
        }
      }
    });

    document.getElementById('stat-total').textContent   = total;
    document.getElementById('stat-passed').textContent  = passed;
    document.getElementById('stat-failed').textContent  = failed;
    document.getElementById('stat-skipped').textContent = skipped;
  }

  document.addEventListener('DOMContentLoaded', function () {
    applyFilters();

    ['ms-status', 'ms-suite'].forEach(id => {
      const wrap = document.getElementById(id);
      if (!wrap) return;
      const btn   = wrap.querySelector('.ms-btn');
      const panel = wrap.querySelector('.ms-panel');
      btn.addEventListener('click', e => {
        e.stopPropagation();
        const isOpen = !panel.hidden;
        document.querySelectorAll('.ms-panel').forEach(p => p.hidden = true);
        document.querySelectorAll('.ms-wrap').forEach(w => w.classList.remove('open'));
        if (!isOpen) { panel.hidden = false; wrap.classList.add('open'); }
      });
      panel.addEventListener('click', e => e.stopPropagation());
      wrap.querySelectorAll('.ms-action-btn').forEach(ab => {
        ab.addEventListener('click', () => {
          const all = ab.dataset.action === 'all';
          wrap.querySelectorAll('input[type=checkbox]').forEach(cb => cb.checked = all);
          msUpdateLabel(id); applyFilters();
        });
      });
      wrap.querySelectorAll('input[type=checkbox]').forEach(cb => {
        cb.addEventListener('change', () => { msUpdateLabel(id); applyFilters(); });
      });
    });

    document.addEventListener('click', () => {
      document.querySelectorAll('.ms-panel').forEach(p => p.hidden = true);
      document.querySelectorAll('.ms-wrap').forEach(w => w.classList.remove('open'));
    });

    document.querySelector('#suite-table tbody').addEventListener('click', e => {
      const row = e.target.closest('.suite-row');
      if (!row) return;
      const exp = document.getElementById(row.dataset.expand);
      if (!exp) return;
      exp.hidden = !exp.hidden;
      row.classList.toggle('open');
    });
  });
})();
