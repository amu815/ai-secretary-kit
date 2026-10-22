'use strict';

(() => {
  // Keep a manual path as the default. Only a user-activated desktop link
  // attempts to open the installed app; no timer or web-chat fallback runs.
  const userAgent = navigator.userAgent || '';
  const isTabletMac = /Macintosh/i.test(userAgent) && navigator.maxTouchPoints > 1;
  const isMobile = /Android|iPhone|iPad|iPod|Mobile|Tablet/i.test(userAgent)
    || isTabletMac || navigator.userAgentData?.mobile === true;
  const isDesktop = !isMobile && /Macintosh|Windows NT|Linux|X11/i.test(userAgent);
  if (isDesktop) {
    document.querySelectorAll('[data-open-app]').forEach(link => {
      link.setAttribute('href', 'codex://threads/new');
      link.querySelector('[data-app-label]').textContent = 'ChatGPTアプリを開く';
    });
  }

  // Anchor links reveal the relevant help even when it is folded away.
  function revealDetails(target) {
    if (!target) return;
    let node = target;
    while (node) {
      if (node.tagName === 'DETAILS') node.open = true;
      node = node.parentElement;
    }
    if (target.id === 'practice') document.getElementById('practice-lab').open = true;
  }
  function revealHash() {
    if (window.location.hash) revealDetails(document.getElementById(window.location.hash.slice(1)));
  }
  document.querySelectorAll('a[href^="#"]').forEach(link => {
    link.addEventListener('click', () => {
      const href = link.getAttribute('href');
      if (href.startsWith('#')) revealDetails(document.getElementById(href.slice(1)));
    });
  });
  window.addEventListener('hashchange', revealHash);
  revealHash();

  const prompts = { onboarding: '', practice: '', correction: '', tasks: [], starterReplies: [] };
  const fields = {
    onboarding: document.getElementById('onboarding-prompt'),
    practice: document.getElementById('practice-prompt'),
    correction: document.getElementById('correction-prompt'),
    task: document.getElementById('task-prompt'),
    reply: document.getElementById('reply-prompt'),
  };
  const taskDescriptions = {
    daily: { title: '今日の順番を決める', description: '用事の一覧や思い出せる1件を渡すと、まず今日の優先順位表を作ります。固定のIDを使い、同じ会話で完了のチェックを増やしていきます。', next: '文をそのまま送信 → 用事を渡す → 表の「今の一件」を進める → 同じ会話へ「Aが終わった」。' },
    email: { title: 'メールの用件を拾う', description: '文をそのまま送ると、どのメールをどう渡すか、AIが一つずつ案内します。依頼・質問・締切を取り出して、原文と見比べます。', next: 'そのあと、確認したいメールを1件コピーするか、必要な部分の画像をChatGPTへ渡します。' },
    writing: { title: '伝わる文章に整える', description: '文をそのまま送ると、直したい文章や相手との関係を、AIが一つずつ聞きます。最初から説明を全部そろえる必要はありません。', next: '下書きがあれば、AIに聞かれたときに貼り付けます。まだ書けていなければ、そのまま伝えてください。' },
    handoff: { title: '不在前に引き継ぐ', description: '文をそのまま送ると、不在の日や残っている用事を、AIが一つずつ聞きます。担当が決まっていなくても始められます。', next: 'やりかけの仕事の一覧やメモがあれば渡します。ない場合は、思い出せる1件を短い言葉で伝えます。' },
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
    document.getElementById('task-next').textContent = taskDescriptions[id].next;
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
    revealDetails(field);
    field.focus();
    field.select();
    field.setSelectionRange(0, field.value.length);
    field.scrollIntoView({ behavior: 'auto', block: 'center' });
    status.classList.add('is-error');
    status.textContent = '自動コピーができませんでした。表示した文を選択しています。パソコンはCtrl+C（Macは⌘+C）、スマートフォンは選択した文を長押しして「コピー」を選んでください。';
    // Keep the fallback instructions next to the selected text, including when
    // the copy action started at the top of the page.
    if (kind === 'onboarding' && status.id !== 'onboarding-status') {
      const nearbyStatus = document.getElementById('onboarding-status');
      nearbyStatus.textContent = status.textContent;
      nearbyStatus.classList.add('is-error');
    }
  }

  copyButtons.forEach(button => {
    button.addEventListener('click', async () => {
      if (!loaded) return;
      const kind = button.dataset.copy;
      const status = document.getElementById(button.dataset.status);
      if (kind === 'reply') {
        const reply = prompts.starterReplies.find(item => item.id === button.dataset.reply);
        fields.reply.value = reply.text;
        document.getElementById('reply-label').textContent = `「${reply.label}」の返事`;
      }
      const text = fields[kind].value;
      status.textContent = '';
      status.classList.remove('is-error');
      button.disabled = true;
      try {
        if (!navigator.clipboard || !window.isSecureContext) throw new Error('Clipboard unavailable');
        await navigator.clipboard.writeText(text);
        if (kind === 'reply' || kind === 'correction') {
          status.textContent = 'コピーしました。ChatGPTアプリで、今使っている同じ会話に貼り付けて送信してください。';
        } else if (kind === 'practice') {
          status.textContent = 'コピーしました。ChatGPTアプリのWorkで新しい会話へそのまま送信し、回答を下の3つのポイントで確かめてください。';
        } else {
          status.textContent = 'コピーしました。ChatGPTアプリのWorkで、6 Sol・Mediumを確認してからそのまま貼り付けて送信してください。AIの次の案内に、一つずつ答えれば大丈夫です。';
        }
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

  // This fictional interaction stays on this page. No task data is stored
  // or sent to ChatGPT, and completed rows keep their original fixed IDs.
  const demoChecks = Array.from(document.querySelectorAll('input[name="demo-task"]'));
  const demoReset = document.getElementById('demo-reset');
  function updateDemo() {
    const done = demoChecks.filter(check => check.checked).length;
    document.getElementById('demo-count').textContent = `${done} / ${demoChecks.length}`;
    const progress = document.getElementById('demo-progress');
    progress.value = done;
    progress.textContent = `${done} / ${demoChecks.length}`;
    demoChecks.forEach(check => {
      const row = check.closest('[data-demo-row]');
      row.classList.toggle('is-complete', check.checked);
      row.querySelector('[data-demo-state]').textContent = check.checked ? '完了' : '未完了';
    });
    const next = demoChecks.find(check => !check.checked);
    document.getElementById('demo-summary').textContent = next
      ? `${done} / ${demoChecks.length}件完了。見本の次の一件：${next.value}「${next.dataset.taskName}」。`
      : `${done} / ${demoChecks.length}件完了。見本の3件が終わりました。完了した行も、表に残っています。`;
  }
  function resetDemo() {
    demoChecks.forEach(check => { check.checked = false; });
    updateDemo();
  }
  demoChecks.forEach(check => {
    check.disabled = false;
    check.addEventListener('change', updateDemo);
  });
  demoReset.disabled = false;
  demoReset.addEventListener('click', resetDemo);
  window.addEventListener('pageshow', resetDemo);
  resetDemo();

  async function loadPrompts() {
    const loadStatus = document.getElementById('load-status');
    try {
      const response = await fetch('./prompts.json?v=20261022-model');
      if (!response.ok) throw new Error('Prompt request failed');
      const data = await response.json();
      if (typeof data.onboarding !== 'string' || !data.onboarding.trim()
        || typeof data.practice !== 'string' || !data.practice.trim()
        || typeof data.correction !== 'string' || !data.correction.trim()
        || !Array.isArray(data.tasks)
        || !Array.isArray(data.starterReplies)
        || !['help', 'unsure', 'done', 'board'].every(id => data.starterReplies.some(reply => reply.id === id
          && typeof reply.label === 'string' && reply.label.trim()
          && typeof reply.text === 'string' && reply.text.trim()))
        || !Object.keys(taskDescriptions).every(id => data.tasks.some(task => task.id === id && typeof task.prompt === 'string' && task.prompt.trim()))) {
        throw new Error('Prompt data incomplete');
      }
      prompts.onboarding = data.onboarding;
      prompts.practice = data.practice;
      prompts.correction = data.correction;
      prompts.tasks = data.tasks;
      prompts.starterReplies = data.starterReplies;
      fields.onboarding.value = prompts.onboarding;
      fields.practice.value = prompts.practice;
      fields.correction.value = prompts.correction;
      fields.reply.value = prompts.starterReplies.find(reply => reply.id === 'help').text;
      document.querySelectorAll('[data-reply]').forEach(button => {
        const reply = prompts.starterReplies.find(item => item.id === button.dataset.reply);
        button.textContent = reply.label;
        button.setAttribute('aria-label', `「${reply.label}」の返事をコピー`);
      });
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
