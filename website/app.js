'use strict';

(() => {
  const prompts = { practice: '', correction: '', tasks: [] };
  const fields = {
    practice: document.getElementById('practice-prompt'),
    correction: document.getElementById('correction-prompt'),
    task: document.getElementById('task-prompt'),
  };
  const taskDescriptions = {
    daily: { title: '今日の順番を決める', description: '対応できる時間と用事を伝えて、まず一つを決めます。不明な締切や担当は、相談事項として分けます。' },
    email: { title: 'メールの用件を拾う', description: '依頼・質問・締切を一つずつ取り出し、原文と照らし合わせます。添付や日時がわからないときは、そのまま不明と伝えます。' },
    writing: { title: '伝わる文章に整える', description: '受け取った依頼と下書きを見比べ、意味を変えずに自然な日本語へ。日付や約束が勝手に変わっていないか、最後に自分でも確かめます。' },
    handoff: { title: '不在前に引き継ぐ', description: '不在中の期限と、ほかの人が待っている用事を整理。担当候補と、実際に引き受けた人を分けて、連絡文を用意します。' },
  };
  const tabs = Array.from(document.querySelectorAll('[data-task]'));
  const copyButtons = Array.from(document.querySelectorAll('[data-copy]'));
  let activeTask = 'daily';
  let loaded = false;

  function selectTask(id, focus) {
    if (!taskDescriptions[id]) return;
    activeTask = id;
    tabs.forEach(tab => {
      const selected = tab.dataset.task === id;
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
      if (selected && focus) tab.focus();
    });
    document.getElementById('task-panel').setAttribute('aria-labelledby', `tab-${id}`);
    document.getElementById('task-title').textContent = taskDescriptions[id].title;
    document.getElementById('task-description').textContent = taskDescriptions[id].description;
    if (loaded) fields.task.value = prompts.tasks.find(task => task.id === id).prompt;
    fields.task.scrollTop = 0;
    const status = document.getElementById('task-status');
    status.textContent = '';
    status.classList.remove('is-error');
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => selectTask(tab.dataset.task, false));
    tab.addEventListener('keydown', event => {
      let next = null;
      if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (index + 1) % tabs.length;
      if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (index + tabs.length - 1) % tabs.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = tabs.length - 1;
      if (next !== null) {
        event.preventDefault();
        selectTask(tabs[next].dataset.task, true);
      }
    });
  });

  function manualCopy(kind, status) {
    const field = fields[kind];
    const details = document.getElementById(`${kind}-details`);
    if (details) details.open = true;
    field.focus();
    field.select();
    field.setSelectionRange(0, field.value.length);
    field.scrollIntoView({ behavior: 'auto', block: 'center' });
    status.classList.add('is-error');
    status.textContent = '自動コピーができませんでした。表示した文を選択しています。パソコンはCtrl+C（Macは⌘+C）、スマートフォンは選択した文を長押しして「コピー」を選んでください。';
    // Keep the fallback instructions next to the selected text, including when
    // the copy action started at the top of the page.
    if (kind === 'practice' && status.id !== 'practice-status') {
      const nearbyStatus = document.getElementById('practice-status');
      nearbyStatus.textContent = status.textContent;
      nearbyStatus.classList.add('is-error');
    }
  }

  copyButtons.forEach(button => {
    button.addEventListener('click', async () => {
      if (!loaded) return;
      const kind = button.dataset.copy;
      const status = document.getElementById(button.dataset.status);
      const text = fields[kind].value;
      status.textContent = '';
      status.classList.remove('is-error');
      button.disabled = true;
      try {
        if (!navigator.clipboard || !window.isSecureContext) throw new Error('Clipboard unavailable');
        await navigator.clipboard.writeText(text);
        status.textContent = kind === 'correction'
          ? 'コピーしました。練習したのと同じChatGPTのチャットに貼り付けて、送信してください。'
          : kind === 'task'
            ? 'コピーしました。ChatGPTに貼り付けて、空欄を埋めてから送信してください。'
            : 'コピーしました。次にChatGPTを開き、新しいチャットに貼り付けて送信してください。';
      } catch (_) {
        manualCopy(kind, status);
      } finally {
        button.disabled = false;
      }
    });
  });

  const checks = Array.from(document.querySelectorAll('input[name="send-check"]'));
  // Avoid a browser restoring old checked state as proof of a new review.
  function resetChecks() {
    checks.forEach(check => { check.checked = false; });
    document.getElementById('check-count').textContent = '0 / 5';
    document.getElementById('check-result').textContent = '確認できない項目があれば、下書きに戻しましょう。';
  }
  resetChecks();
  window.addEventListener('pageshow', resetChecks);
  checks.forEach(check => check.addEventListener('change', () => {
    const count = checks.filter(item => item.checked).length;
    document.getElementById('check-count').textContent = `${count} / 5`;
    document.getElementById('check-result').textContent = count === checks.length
      ? '5項目を自分で確認しました。最後に、実際のメール画面の宛先・本文・添付も見直してください。'
      : '確認できない項目があれば、下書きに戻しましょう。';
  }));

  async function loadPrompts() {
    const loadStatus = document.getElementById('load-status');
    try {
      const response = await fetch('./prompts.json');
      if (!response.ok) throw new Error('Prompt request failed');
      const data = await response.json();
      if (typeof data.practice !== 'string' || !data.practice.trim()
        || typeof data.correction !== 'string' || !data.correction.trim()
        || !Array.isArray(data.tasks)
        || !Object.keys(taskDescriptions).every(id => data.tasks.some(task => task.id === id && typeof task.prompt === 'string' && task.prompt.trim()))) {
        throw new Error('Prompt data incomplete');
      }
      prompts.practice = data.practice;
      prompts.correction = data.correction;
      prompts.tasks = data.tasks;
      fields.practice.value = prompts.practice;
      fields.correction.value = prompts.correction;
      loaded = true;
      selectTask(activeTask, false);
      copyButtons.forEach(button => { button.disabled = false; });
      loadStatus.textContent = '';
    } catch (_) {
      const message = '教材を読み込めませんでした。インターネット接続を確認して、このページを再読み込みしてください。';
      loadStatus.textContent = message;
      loadStatus.classList.add('load-error');
      Object.values(fields).forEach(field => { field.value = message; });
      const heroStatus = document.getElementById('hero-status');
      heroStatus.textContent = message;
      heroStatus.classList.add('is-error');
      copyButtons.forEach(button => { button.disabled = true; });
    }
  }

  loadPrompts();
})();
