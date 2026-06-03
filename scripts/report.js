// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

(function () {
  const STATUS_ORDER = { untested: 0, skipped: 1, failed: 2, passed: 3 };
  let sortCol = null, sortDir = 1;

  function cmp(a, b) {
    if (typeof a === 'number' && typeof b === 'number') return a - b;
    return String(a).localeCompare(String(b));
  }

  function cellValue(row, col) {
    switch (col) {
      case 'status':  return STATUS_ORDER[row.dataset.status] ?? 99;
      case 'fid':     return row.dataset.fid || '';
      case 'desc':    return row.cells[2].textContent.trim();
      case 'release': return row.dataset.release || '';
      case 'failed':  return +row.dataset.failed;
      case 'passed':  return +row.dataset.passed;
      case 'skipped': return +row.dataset.skipped;
      default:        return '';
    }
  }

  function reorder(rows) {
    const tbody = document.querySelector('#feature-table tbody');
    rows.forEach((row, i) => {
      row.classList.toggle('even', i % 2 === 0);
      row.classList.toggle('odd',  i % 2 !== 0);
      tbody.appendChild(row);
      const exp = document.getElementById(row.dataset.expand);
      if (exp) tbody.appendChild(exp);
    });
    document.querySelectorAll('#feature-table thead th').forEach(th => {
      th.classList.remove('sort-asc', 'sort-desc');
      if (sortCol && th.dataset.col === sortCol)
        th.classList.add(sortDir === 1 ? 'sort-asc' : 'sort-desc');
    });
  }

  function updateStats() {
    const seen = new Set();
    let passed = 0, failed = 0;
    document.querySelectorAll('#feature-table .feature-row').forEach(row => {
      if (row.hidden) return;
      const exp = document.getElementById(row.dataset.expand);
      if (!exp) return;
      exp.querySelectorAll('.tc-row').forEach(tcRow => {
        const nameEl = tcRow.querySelector('.tc-name');
        if (!nameEl) return;
        const id = nameEl.textContent.trim();
        if (seen.has(id)) return;
        seen.add(id);
        const badge = tcRow.querySelector('.badge');
        if (!badge) return;
        const status = [...badge.classList].find(c => c !== 'badge');
        if (status === 'passed') passed++;
        else if (status === 'failed' || status === 'skipped') failed++;
      });
    });
    document.getElementById('stat-total').textContent   = failed + passed;
    document.getElementById('stat-passed').textContent  = passed;
    document.getElementById('stat-failed').textContent  = failed;
  }

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
    const sf = msGetSelected('ms-status');
    const rf = msGetSelected('ms-release');
    const tf = msGetSelected('ms-type');
    const scf = msGetSelected('ms-scope');
    let vi = 0;
    document.querySelectorAll('#feature-table .feature-row').forEach(row => {
      const ok = (!sf || sf.has(row.dataset.status))
               && (!rf || rf.has(row.dataset.release))
               && (!tf || tf.has(row.dataset.type))
               && (!scf || scf.has(row.dataset.scope));
      row.hidden = !ok;
      const exp = document.getElementById(row.dataset.expand);
      if (!ok) {
        if (exp) exp.hidden = true;
        row.classList.remove('open');
      } else {
        row.classList.toggle('even', vi % 2 === 0);
        row.classList.toggle('odd',  vi % 2 !== 0);
        vi++;
      }
    });
    updateStats();
  }

  document.addEventListener('DOMContentLoaded', function () {
    const tbody = document.querySelector('#feature-table tbody');
    if (!tbody) return;

    const getRows = () => [...tbody.querySelectorAll('.feature-row')];

    reorder(getRows());
    ['ms-status', 'ms-scope', 'ms-type', 'ms-release'].forEach(id => msUpdateLabel(id));
    applyFilters();

    document.querySelectorAll('#feature-table thead th[data-col]').forEach(th => {
      th.addEventListener('click', () => {
        const col = th.dataset.col;
        if (sortCol === col) sortDir *= -1;
        else { sortCol = col; sortDir = 1; }
        reorder(getRows().sort((a, b) => cmp(cellValue(a, col), cellValue(b, col)) * sortDir));
      });
    });

    ['ms-status', 'ms-release', 'ms-type', 'ms-scope'].forEach(id => {
      const wrap = document.getElementById(id);
      if (!wrap) return;
      const btn = wrap.querySelector('.ms-btn');
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

    tbody.addEventListener('click', e => {
      const row = e.target.closest('.feature-row');
      if (!row) return;
      const exp = document.getElementById(row.dataset.expand);
      if (!exp) return;
      exp.hidden = !exp.hidden;
      row.classList.toggle('open');
    });
  });
})();
