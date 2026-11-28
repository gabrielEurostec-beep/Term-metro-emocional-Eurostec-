/*
 * Teste de ponta a ponta das telas do quiosque (navegador real, toques simulados).
 *
 * Uso (para desenvolvedores): node tests/e2e/quiosque.e2e.js
 * Requer Node.js e o pacote "playwright" com o Chromium (mesmo motor do Edge).
 * Variáveis opcionais: PYTHON (interpretador), CAPTURAS (pasta para salvar prints).
 */
'use strict';

const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');

let chromium;
try { ({ chromium } = require('playwright')); } catch (e) {
  console.log('Playwright não instalado: teste de telas ignorado.');
  process.exit(0);
}

const RAIZ = path.resolve(__dirname, '..', '..');
const PYTHON = process.env.PYTHON || (fs.existsSync(path.join(RAIZ, '.venv', 'bin', 'python'))
  ? path.join(RAIZ, '.venv', 'bin', 'python') : 'python3');
const CAPTURAS = process.env.CAPTURAS || '';
const espera = (ms) => new Promise((ok) => setTimeout(ok, ms));
let porta = 18600;

function saude(p) {
  return new Promise((ok) => {
    const req = http.get({ host: '127.0.0.1', port: p, path: '/api/saude', timeout: 500 }, (r) => { r.resume(); ok(r.statusCode === 200); });
    req.on('error', () => ok(false));
    req.on('timeout', () => { req.destroy(); ok(false); });
  });
}

async function iniciarServidor(dataHora, configExtra, ambienteExtra = {}) {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'termometro-e2e-'));
  fs.mkdirSync(path.join(base, 'assets'));
  for (const nome of fs.readdirSync(path.join(RAIZ, 'assets'))) {
    fs.copyFileSync(path.join(RAIZ, 'assets', nome), path.join(base, 'assets', nome));
  }
  if (configExtra) {
    fs.mkdirSync(path.join(base, 'config'));
    fs.writeFileSync(path.join(base, 'config', 'config.json'), JSON.stringify(configExtra));
  }
  const p = ++porta;
  const proc = spawn(PYTHON, ['-m', 'quiosque', '--porta', String(p)], {
    cwd: RAIZ,
    env: { ...process.env, TERMOMETRO_BASE: base, TERMOMETRO_DATA_HORA_TESTE: dataHora, ...ambienteExtra },
    stdio: 'ignore'
  });
  for (let i = 0; i < 50 && !(await saude(p)); i++) await espera(100);
  return { base, url: `http://localhost:${p}`, parar: () => proc.kill() };
}

function lerCsv(base) {
  const pasta = path.join(base, 'dados');
  if (!fs.existsSync(pasta)) return [];
  const linhas = [];
  for (const nome of fs.readdirSync(pasta).filter((n) => n.endsWith('.csv'))) {
    const bruto = fs.readFileSync(path.join(pasta, nome));
    assert.equal(bruto.slice(0, 3).toString('hex'), 'efbbbf', 'CSV deve ter BOM UTF-8');
    const [cab, ...resto] = bruto.toString('utf8').replace(/^﻿/, '').split('\r\n').filter(Boolean);
    const colunas = cab.split(';');
    for (const l of resto) {
      const valores = l.split(';');
      linhas.push(Object.fromEntries(colunas.map((c, i) => [c, valores[i]])));
    }
  }
  return linhas;
}

async function tela(page) { return page.evaluate(() => window.__termometro.tela()); }
async function aguardarTela(page, id, timeout = 4000) {
  await page.waitForFunction((t) => window.__termometro && window.__termometro.tela() === t, id, { timeout });
  await espera(650); // tempo de reação de uma pessoa (passa a trava de 0,5 s)
}
async function capturar(page, nome) {
  if (!CAPTURAS) return;
  fs.mkdirSync(CAPTURAS, { recursive: true });
  await page.screenshot({ path: path.join(CAPTURAS, nome + '.png') });
}
async function tocarInicio(page) {
  // Toca numa área "vazia" da tela inicial (não no botão).
  await page.touchscreen.tap(200, 300);
}
async function tocar(page, seletor) { await page.locator(seletor).first().tap(); }

const resultados = [];
async function cenario(nome, fn) {
  const inicio = Date.now();
  try {
    await fn();
    resultados.push({ nome, ok: true });
    console.log(`  ✔ ${nome} (${((Date.now() - inicio) / 1000).toFixed(1)} s)`);
  } catch (erro) {
    resultados.push({ nome, ok: false });
    console.log(`  ✘ ${nome}\n    ${erro.stack.split('\n').slice(0, 4).join('\n    ')}`);
  }
}

(async () => {
  const navegador = await chromium.launch();
  // VIEWPORT=1280x800 roda o mesmo teste no tamanho de um tablet de 10 polegadas.
  const [largura, altura] = (process.env.VIEWPORT || '1920x1080').split('x').map(Number);
  const contexto = await navegador.newContext({ viewport: { width: largura, height: altura }, hasTouch: true, deviceScaleFactor: 1, locale: 'pt-BR', timezoneId: 'America/Sao_Paulo' });

  async function abrir(dataHora, configExtra) {
    const srv = await iniciarServidor(dataHora, configExtra);
    const page = await contexto.newPage();
    await page.goto(srv.url);
    await aguardarTela(page, 'tela-inicio');
    return { srv, page, fechar: async () => { await page.close(); srv.parar(); } };
  }

  console.log('Teste de telas do quiosque (Chromium, toque simulado)');

  await cenario('Chegada (quarta 07:45): toque em qualquer lugar, emoção grava NA HORA, motivo atualiza a mesma linha', async () => {
    const { srv, page, fechar } = await abrir('2026-11-18T07:45:00');
    await capturar(page, '01_inicio');
    assert.match(await page.textContent('#inicio-rodape'), /primeira pessoa/);
    await tocarInicio(page);
    await aguardarTela(page, 'tela-emocoes');
    assert.equal(await page.textContent('#emocoes-titulo'), 'Como você está chegando hoje?');
    assert.equal(await page.locator('#emocoes-grade .emocao').count(), 8);
    await capturar(page, '02_emocoes_chegada');
    await tocar(page, '[data-emocao="Cansado"]');
    await aguardarTela(page, 'tela-motivo');
    let csv = lerCsv(srv.base);
    assert.equal(csv.length, 1, 'gravou no 1º toque');
    assert.equal(csv[0].emocao, 'Cansado');
    assert.equal(csv[0].momento, 'chegada');
    assert.equal(csv[0].momento_automatico, 'sim');
    assert.equal(csv[0].motivo, '');
    assert.equal(csv[0].pontuacao, '-1');
    assert.equal(csv[0].valencia, 'negativa');
    assert.equal(csv[0].dia_semana, 'quarta');
    assert.equal(await page.textContent('#motivo-titulo'), 'O que mais pesou?');
    assert.equal(await page.locator('#motivo-opcoes .opcao').count(), 7);
    await capturar(page, '03_motivo_chegada_negativo');
    const id = csv[0].response_id;
    await tocar(page, '#motivo-opcoes .opcao >> text=Trânsito/deslocamento');
    await aguardarTela(page, 'tela-obrigado', 3000);
    csv = lerCsv(srv.base);
    assert.equal(csv.length, 1, 'continua 1 linha');
    assert.equal(csv[0].response_id, id, 'mesmo response_id');
    assert.equal(csv[0].motivo, 'Trânsito/deslocamento');
    assert.equal(await page.textContent('#obrigado-texto'), 'Obrigado! Hoje 1 pessoa já registrou como está.');
    assert.equal((await page.textContent('#obrigado-acolhimento')).trim(), '', 'Cansado não mostra acolhimento');
    await capturar(page, '04_obrigado');
    await page.waitForFunction(() => window.__termometro.tela() === 'tela-inicio', null, { timeout: 2500 });
    assert.match(await page.textContent('#inicio-rodape'), /Hoje 1 pessoa já participou/);
    await fechar();
  });

  await cenario('Anti-duplo-toque: novo registro bloqueado por 2 s; trava de 0,5 s entre telas', async () => {
    const { srv, page, fechar } = await abrir('2026-11-18T08:10:00');
    await tocarInicio(page);
    await page.waitForFunction(() => window.__termometro.tela() === 'tela-emocoes');
    // toque imediato (< 0,5 s) é ignorado
    await tocar(page, '[data-emocao="Neutro"]');
    await espera(200);
    assert.equal(lerCsv(srv.base).length, 0, 'toque logo após trocar de tela é ignorado');
    await espera(500);
    await tocar(page, '[data-emocao="Neutro"]');
    await page.waitForFunction(() => window.__termometro.tela() === 'tela-obrigado');
    // Neutro na chegada vai direto ao agradecimento
    await page.waitForFunction(() => window.__termometro.tela() === 'tela-inicio', null, { timeout: 2500 });
    const voltouEm = Date.now();
    await tocarInicio(page); // ainda dentro dos 2 s após o registro
    await espera(300);
    assert.equal(await tela(page), 'tela-inicio', 'bloqueado nos 2 s seguintes ao registro');
    await espera(Math.max(0, 2100 - (Date.now() - voltouEm) + 1600));
    await tocarInicio(page);
    await aguardarTela(page, 'tela-emocoes');
    assert.equal(lerCsv(srv.base).length, 1);
    await fechar();
  });

  await cenario('Inatividade: 3 s sem toque na tela de emoções volta ao início sem gravar nada', async () => {
    const { srv, page, fechar } = await abrir('2026-11-18T09:00:00');
    await tocarInicio(page);
    await aguardarTela(page, 'tela-emocoes');
    const desde = Date.now() - 650;
    await espera(1500);
    assert.equal(await tela(page), 'tela-emocoes', 'ainda na tela antes dos 3 s');
    await page.waitForFunction(() => window.__termometro.tela() === 'tela-inicio', null, { timeout: 3000 });
    const decorrido = Date.now() - desde;
    assert.ok(decorrido >= 2900 && decorrido <= 4200, `voltou em ${decorrido} ms (esperado ~3 s)`);
    assert.equal(lerCsv(srv.base).length, 0);
    await fechar();
  });

  await cenario('Motivo é opcional: 3 s parado no motivo volta ao início e a emoção continua gravada', async () => {
    const { srv, page, fechar } = await abrir('2026-11-18T07:50:00');
    await tocarInicio(page);
    await aguardarTela(page, 'tela-emocoes');
    await tocar(page, '[data-emocao="Feliz"]');
    await aguardarTela(page, 'tela-motivo');
    assert.equal(await page.textContent('#motivo-titulo'), 'O que mais contribuiu?');
    assert.equal(await page.locator('#motivo-opcoes .opcao').count(), 5);
    await capturar(page, '05_motivo_chegada_positivo');
    await page.waitForFunction(() => window.__termometro.tela() === 'tela-inicio', null, { timeout: 7000 });
    const csv = lerCsv(srv.base);
    assert.equal(csv.length, 1);
    assert.equal(csv[0].emocao, 'Feliz');
    assert.equal(csv[0].motivo, '');
    await fechar();
  });

  await cenario('Saída para o almoço (11:45): só a emoção, direto ao agradecimento', async () => {
    const { srv, page, fechar } = await abrir('2026-11-18T11:45:00');
    await tocarInicio(page);
    await aguardarTela(page, 'tela-emocoes');
    assert.equal(await page.textContent('#emocoes-titulo'), 'Como você está saindo para o almoço?');
    await tocar(page, '[data-emocao="Animado"]');
    await page.waitForFunction(() => window.__termometro.tela() === 'tela-obrigado');
    const csv = lerCsv(srv.base);
    assert.equal(csv[0].momento, 'saida_almoco');
    assert.equal(csv[0].pontuacao, '2');
    await fechar();
  });

  await cenario('Volta do almoço começa às 12:20 (limite da janela)', async () => {
    const { srv, page, fechar } = await abrir('2026-11-18T12:20:05');
    await tocarInicio(page);
    await aguardarTela(page, 'tela-emocoes');
    assert.equal(await page.textContent('#emocoes-titulo'), 'Como você está voltando do almoço?');
    await fechar();
  });

  await cenario('Saída do dia (17:00): Bravo → motivo → pergunta do dia → acolhimento', async () => {
    const { srv, page, fechar } = await abrir('2026-11-18T17:00:00');
    await tocarInicio(page);
    await aguardarTela(page, 'tela-emocoes');
    assert.equal(await page.textContent('#emocoes-titulo'), 'Como você está saindo hoje?');
    await capturar(page, '06_emocoes_saida');
    await tocar(page, '[data-emocao="Bravo"]');
    await aguardarTela(page, 'tela-motivo');
    assert.equal(await page.locator('#motivo-opcoes .opcao').count(), 8);
    await capturar(page, '07_motivo_saida_negativo');
    await tocar(page, '#motivo-opcoes .opcao >> text=Liderança/cobrança');
    await aguardarTela(page, 'tela-pergunta');
    const pergunta = await page.textContent('#pergunta-texto');
    assert.equal(await page.locator('#pergunta-opcoes .opcao').count(), 3);
    await capturar(page, '08_pergunta_do_dia');
    await tocar(page, '#pergunta-opcoes .opcao >> text=Mais ou menos');
    await aguardarTela(page, 'tela-obrigado', 3000);
    assert.match(await page.textContent('#obrigado-acolhimento'), /CIPA e o RH estão à disposição/);
    await capturar(page, '09_obrigado_acolhimento');
    const csv = lerCsv(srv.base);
    assert.equal(csv.length, 1);
    assert.equal(csv[0].motivo, 'Liderança/cobrança');
    assert.equal(csv[0].pergunta_do_dia, pergunta);
    assert.equal(csv[0].resposta_pergunta_do_dia, 'Mais ou menos');
    // acolhimento fica 4 s (mais que o agradecimento normal de 1,5 s)
    await espera(2000);
    assert.equal(await tela(page), 'tela-obrigado');
    await page.waitForFunction(() => window.__termometro.tela() === 'tela-inicio', null, { timeout: 3000 });
    await fechar();
  });

  await cenario('Saída do dia: Neutro pula o motivo mas vê a pergunta do dia (Pular funciona)', async () => {
    const { srv, page, fechar } = await abrir('2026-11-18T17:30:00');
    await tocarInicio(page);
    await aguardarTela(page, 'tela-emocoes');
    await tocar(page, '[data-emocao="Neutro"]');
    await aguardarTela(page, 'tela-pergunta');
    await tocar(page, '#pergunta-pular');
    await page.waitForFunction(() => window.__termometro.tela() === 'tela-obrigado');
    const csv = lerCsv(srv.base);
    assert.equal(csv[0].emocao, 'Neutro');
    assert.equal(csv[0].resposta_pergunta_do_dia, '');
    await fechar();
  });

  await cenario('Fora das janelas (quarta 15:00): escolha manual do momento, registrado como não automático', async () => {
    const { srv, page, fechar } = await abrir('2026-11-18T15:00:00');
    await tocarInicio(page);
    await aguardarTela(page, 'tela-momento');
    assert.equal(await page.locator('#momento-opcoes .botao-momento').count(), 4);
    await capturar(page, '10_escolha_momento');
    await tocar(page, '[data-momento="volta_almoco"]');
    await aguardarTela(page, 'tela-emocoes');
    assert.equal(await page.textContent('#emocoes-titulo'), 'Como você está voltando do almoço?');
    await tocar(page, '[data-emocao="Preocupado"]');
    await page.waitForFunction(() => window.__termometro.tela() === 'tela-obrigado');
    const csv = lerCsv(srv.base);
    assert.equal(csv[0].momento, 'volta_almoco');
    assert.equal(csv[0].momento_automatico, 'não');
    await fechar();
  });

  await cenario('Fim de semana (sábado 08:00): escolha manual do momento', async () => {
    const { page, fechar } = await abrir('2026-11-21T08:00:00');
    await tocarInicio(page);
    await aguardarTela(page, 'tela-momento');
    await fechar();
  });

  await cenario('Botão "trocar momento" dentro da janela automática', async () => {
    const { srv, page, fechar } = await abrir('2026-11-18T07:40:00');
    await tocarInicio(page);
    await aguardarTela(page, 'tela-emocoes');
    await tocar(page, '#botao-trocar-momento');
    await aguardarTela(page, 'tela-momento');
    await tocar(page, '[data-momento="saida_final"]');
    await aguardarTela(page, 'tela-emocoes');
    assert.equal(await page.textContent('#emocoes-titulo'), 'Como você está saindo hoje?');
    await tocar(page, '[data-emocao="Feliz"]');
    await aguardarTela(page, 'tela-motivo');
    const csv = lerCsv(srv.base);
    assert.equal(csv[0].momento, 'saida_final');
    assert.equal(csv[0].momento_automatico, 'não');
    await fechar();
  });

  await cenario('Agradecimento mostra só a contagem total (nunca a distribuição das emoções)', async () => {
    const { page, fechar } = await abrir('2026-11-18T11:50:00');
    for (const emocao of ['Feliz', 'Triste', 'Feliz']) {
      await tocarInicio(page);
      await aguardarTela(page, 'tela-emocoes');
      await tocar(page, `[data-emocao="${emocao}"]`);
      await page.waitForFunction(() => window.__termometro.tela() === 'tela-obrigado');
      const textoTela = await page.locator('#tela-obrigado').innerText();
      for (const nome of ['Feliz', 'Triste', '%']) assert.ok(!textoTela.includes(nome), `não mostra "${nome}"`);
      await page.waitForFunction(() => window.__termometro.tela() === 'tela-inicio', null, { timeout: 6000 });
      await espera(2100);
    }
    assert.match(await page.textContent('#inicio-rodape'), /Hoje 3 pessoas já participaram neste ponto/);
    await capturar(page, '11_inicio_com_contagem');
    await fechar();
  });

  await cenario('Administração: toque curto no canto inicia o fluxo; toque longo de 3 s + PIN abre o painel', async () => {
    const { page, fechar } = await abrir('2026-11-18T10:30:00');
    const cdp = await page.context().newCDPSession(page);
    const ponto = { x: largura - 40, y: 40 };
    // toque curto no canto → começa o fluxo normalmente
    await page.touchscreen.tap(ponto.x, ponto.y);
    await aguardarTela(page, 'tela-momento');
    await page.waitForFunction(() => window.__termometro.tela() === 'tela-inicio', null, { timeout: 7000 });
    await espera(600);
    // toque longo de 1 s não abre
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [ponto] });
    await espera(1000);
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await espera(300);
    assert.notEqual(await tela(page), 'tela-pin');
    await page.waitForFunction(() => window.__termometro.tela() === 'tela-inicio', null, { timeout: 7000 });
    await espera(600);
    // toque longo de 3 s abre o PIN
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [ponto] });
    await espera(3200);
    assert.equal(await tela(page), 'tela-pin');
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await espera(300);
    await capturar(page, '12_pin');
    for (const d of ['1', '1', '1', '1', 'OK']) await page.locator('#pin-teclado button', { hasText: new RegExp('^' + d + '$') }).tap();
    await page.waitForSelector('#pin-erro:has-text("PIN incorreto")');
    for (const d of ['2', '4', '6', '8', 'OK']) await page.locator('#pin-teclado button', { hasText: new RegExp('^' + d + '$') }).tap();
    await page.waitForFunction(() => window.__termometro.tela() === 'tela-admin');
    await page.waitForSelector('#admin-contagens .total');
    await page.waitForSelector('#admin-form input[data-caminho="kiosk_id"]');
    await espera(400);
    await capturar(page, '13_admin');
    // salvar configuração pelo formulário (muda o local)
    await page.fill('#admin-form input[data-caminho="kiosk_local"]', 'Recepção');
    await page.locator('#admin-salvar').tap();
    await page.waitForSelector('#admin-config-msg.ok');
    // configuração inválida é recusada com explicação
    await page.fill('#admin-form input[data-caminho="momentos.chegada.inicio"]', '11:00');
    await page.locator('#admin-salvar').tap();
    await page.waitForSelector('#admin-config-msg.erro');
    assert.match(await page.textContent('#admin-config-msg'), /início .* deve ser antes do fim|sobrepostas/);
    await page.locator('#admin-sair').tap();
    await aguardarTela(page, 'tela-inicio');
    await fechar();
  });

  await cenario('Setor: chegada mostra a tela de setor depois do motivo; Pular e escolha gravam certo', async () => {
    const { srv, page, fechar } = await abrir('2026-11-18T07:45:00', { setores: ['Administrativo', 'Assistência técnica', 'Comercial'] });
    await tocarInicio(page);
    await aguardarTela(page, 'tela-emocoes');
    await tocar(page, '[data-emocao="Cansado"]');
    await aguardarTela(page, 'tela-motivo');
    await tocar(page, '#motivo-opcoes .opcao >> text=Sono/cansaço');
    await aguardarTela(page, 'tela-setor');
    assert.equal(await page.locator('#setor-opcoes .opcao').count(), 3);
    await capturar(page, '14_setor');
    await tocar(page, '#setor-opcoes .opcao >> text=Comercial');
    await page.waitForFunction(() => window.__termometro.tela() === 'tela-obrigado');
    let csv = lerCsv(srv.base);
    assert.equal(csv[0].setor, 'Comercial');
    assert.equal(csv[0].setor_perguntado, 'sim');
    await fechar();
  });

  await cenario('Setor: pular grava a resposta sem setor', async () => {
    const { srv, page, fechar } = await abrir('2026-11-18T17:10:00', { setores: ['Produção', 'Qualidade', 'Segurança'] });
    await tocarInicio(page);
    await aguardarTela(page, 'tela-emocoes');
    await tocar(page, '[data-emocao="Feliz"]');
    await aguardarTela(page, 'tela-motivo');
    await tocar(page, '#motivo-pular');
    await aguardarTela(page, 'tela-pergunta');
    await tocar(page, '#pergunta-pular');
    await aguardarTela(page, 'tela-setor');
    await tocar(page, '#setor-pular');
    await page.waitForFunction(() => window.__termometro.tela() === 'tela-obrigado');
    const csv = lerCsv(srv.base);
    assert.equal(csv[0].setor, '');
    assert.equal(csv[0].setor_perguntado, 'sim');
    await fechar();
  });

  await cenario('Setor: almoço não mostra a tela de setor', async () => {
    const { page, fechar } = await abrir('2026-11-18T11:45:00', { setores: ['Produção'] });
    await tocarInicio(page);
    await aguardarTela(page, 'tela-emocoes');
    await tocar(page, '[data-emocao="Feliz"]');
    await page.waitForFunction(() => window.__termometro.tela() === 'tela-obrigado');
    await fechar();
  });

  await cenario('Administração: sessão expirada não apaga o PIN que a pessoa está digitando', async () => {
    const srv = await iniciarServidor('2026-11-18T10:30:00', null, { TERMOMETRO_SESSAO_ADMIN_S: '4' });
    const page = await contexto.newPage();
    await page.goto(srv.url);
    await aguardarTela(page, 'tela-inicio');
    const cdp = await page.context().newCDPSession(page);
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: largura - 40, y: 40 }] });
    await espera(3200);
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await page.waitForFunction(() => window.__termometro.tela() === 'tela-pin');
    for (const d of ['2', '4', '6', '8', 'OK']) await page.locator('#pin-teclado button', { hasText: new RegExp('^' + d + '$') }).tap();
    await page.waitForFunction(() => window.__termometro.tela() === 'tela-admin');
    // Tablet parado: a sessão de 4 s expira e a próxima consulta automática pede o PIN.
    await page.route('**/api/admin/**', (r) => r.abort());
    await espera(6000);
    await page.unroute('**/api/admin/**');
    await page.waitForFunction(() => window.__termometro.tela() === 'tela-pin', null, { timeout: 12000 });
    // A pessoa demora para digitar: a consulta automática não pode apagar os dígitos.
    await page.locator('#pin-teclado button', { hasText: /^2$/ }).tap();
    await page.locator('#pin-teclado button', { hasText: /^4$/ }).tap();
    await espera(6000);
    assert.equal(await page.locator('#pin-pontos span').count(), 2, 'os dígitos digitados continuam na tela');
    for (const d of ['6', '8', 'OK']) await page.locator('#pin-teclado button', { hasText: new RegExp('^' + d + '$') }).tap();
    await page.waitForFunction(() => window.__termometro.tela() === 'tela-admin', null, { timeout: 4000 });
    await page.close();
    srv.parar();
  });

  await cenario('Android: admin usa a ponte nativa (copiar para Download e fechar o app)', async () => {
    const srv = await iniciarServidor('2026-11-18T10:30:00');
    const page = await contexto.newPage();
    await page.addInitScript(() => {
      window.__chamadas = [];
      window.AndroidApp = {
        exportarParaDownloads: () => { window.__chamadas.push('exportar'); return JSON.stringify({ ok: true, copiados: 2, pasta: 'Download/TermometroEurostec' }); },
        sair: () => { window.__chamadas.push('sair'); },
        versao: () => '1.0.0'
      };
    });
    page.on('dialog', (d) => d.accept());
    await page.goto(srv.url);
    await aguardarTela(page, 'tela-inicio');
    // toque longo de 3 s no canto superior direito abre o PIN
    const cdp = await page.context().newCDPSession(page);
    const ponto = { x: largura - 40, y: 40 };
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [ponto] });
    await espera(3200);
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await page.waitForFunction(() => window.__termometro.tela() === 'tela-pin');
    for (const d of ['2', '4', '6', '8', 'OK']) await page.locator('#pin-teclado button', { hasText: new RegExp('^' + d + '$') }).tap();
    await page.waitForSelector('#admin-pendrives button');
    await page.locator('#admin-pendrives button', { hasText: 'Copiar respostas para a pasta Download' }).click();
    await page.waitForSelector('#admin-exportar-msg:has-text("2 arquivo(s) copiado(s)")');
    assert.match(await page.textContent('#admin-exportar-msg'), /Download\/TermometroEurostec/);
    await page.locator('#admin-encerrar').click();
    await espera(300);
    const chamadas = await page.evaluate(() => window.__chamadas);
    assert.deepEqual(chamadas, ['exportar', 'sair'], 'usou a ponte nativa, sem o caminho do Windows');
    await page.close();
    srv.parar();
  });

  await contexto.close();
  await navegador.close();
  const falhas = resultados.filter((r) => !r.ok).length;
  console.log(`\n${resultados.length - falhas} de ${resultados.length} cenários passaram.`);
  process.exit(falhas ? 1 : 0);
})();
