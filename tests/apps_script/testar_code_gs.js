/*
 * Testa o apps_script/Code.gs com uma planilha simulada (sem precisar do Google).
 * Uso: node tests/apps_script/testar_code_gs.js   (sai com código 0 se tudo passar)
 */
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ARQUIVO = path.resolve(__dirname, '..', '..', 'apps_script', 'Code.gs');

// ------------------------------------------------------------ planilha simulada
function criarAba(nome) {
  const dados = []; // linhas (arrays)
  const aba = {
    nome, dados, congeladas: 0, formatos: {},
    getLastRow: () => dados.length,
    getLastColumn: () => Math.max(0, ...dados.map((l) => l.length)),
    getMaxRows: () => 1000,
    setFrozenRows: (n) => { aba.congeladas = n; },
    autoResizeColumns: () => aba,
    getRange: (linha, coluna, nLinhas = 1, nColunas = 1) => {
      const faixa = {
        getValues: () => {
          const r = [];
          for (let i = 0; i < nLinhas; i++) {
            const l = dados[linha - 1 + i] || [];
            r.push(Array.from({ length: nColunas }, (_, j) => (l[coluna - 1 + j] === undefined ? '' : l[coluna - 1 + j])));
          }
          return r;
        },
        setValues: (valores) => {
          assert.equal(valores.length, nLinhas, 'quantidade de linhas do setValues');
          valores.forEach((v, i) => {
            assert.equal(v.length, nColunas, 'quantidade de colunas do setValues');
            while (dados.length < linha + i) dados.push([]);
            const alvo = dados[linha - 1 + i];
            v.forEach((x, j) => { alvo[coluna - 1 + j] = x; });
          });
          return faixa;
        },
        setNumberFormat: (f) => { aba.formatos[coluna] = f; return faixa; },
        setFontWeight: () => faixa,
        setBackground: () => faixa,
        setFontColor: () => faixa
      };
      return faixa;
    }
  };
  return aba;
}

function novoAmbiente(token) {
  const abas = {};
  const planilha = {
    getName: () => 'Termômetro Emocional (teste)',
    getSheetByName: (n) => abas[n] || null,
    insertSheet: (n) => (abas[n] = criarAba(n))
  };
  let travas = 0;
  const contexto = {
    SpreadsheetApp: { getActiveSpreadsheet: () => planilha },
    LockService: { getScriptLock: () => ({ waitLock: () => { travas++; }, releaseLock: () => {} }) },
    ContentService: {
      MimeType: { JSON: 'application/json' },
      createTextOutput: (texto) => ({ texto, setMimeType() { return this; }, getContent() { return texto; } })
    }
  };
  vm.createContext(contexto);
  let fonte = fs.readFileSync(ARQUIVO, 'utf8');
  if (token !== undefined) fonte = fonte.replace(/const TOKEN = '.*?';/, `const TOKEN = '${token}';`);
  vm.runInContext(fonte + '\n;globalThis.__api = { doPost, doGet, configurarPlanilha };', contexto);
  const api = contexto.__api;
  return {
    abas,
    travas: () => travas,
    post: (corpo) => JSON.parse(api.doPost({ postData: { contents: JSON.stringify(corpo) } }).getContent()),
    postBruto: (texto) => JSON.parse(api.doPost({ postData: { contents: texto } }).getContent()),
    get: () => api.doGet().getContent(),
    configurar: () => api.configurarPlanilha()
  };
}

function linha(id, extra = {}) {
  return {
    response_id: id, kiosk_id: 'Q01', kiosk_local: 'Portaria', timestamp: '2026-11-18T07:45:00-03:00',
    data: '2026-11-18', dia_semana: 'quarta', hora: '07:45:00', momento: 'chegada', momento_automatico: 'sim',
    emocao: 'Cansado', valencia: 'negativa', pontuacao: -1, motivo: '', pergunta_do_dia: '',
    resposta_pergunta_do_dia: '', temperatura_c: 16.4, sensacao_termica_c: 15.1, precipitacao_mm: 0,
    codigo_tempo: 3, condicao: 'nublado', dia_ou_noite: 'dia', versao_app: '1.0.0', ...extra
  };
}

const ID1 = '11111111-1111-4111-8111-111111111111';
const ID2 = '22222222-2222-4222-8222-222222222222';
const ID3 = '33333333-3333-4333-8333-333333333333';

const testes = {
  'sem trocar o TOKEN padrão, recusa tudo'() {
    const amb = novoAmbiente();
    const r = amb.post({ token: 'TROQUE-ESTE-TOKEN', acao: 'ping' });
    assert.equal(r.ok, false);
    assert.match(r.erro, /Troque o TOKEN/);
  },
  'token errado é recusado e nada é gravado'() {
    const amb = novoAmbiente('segredo');
    const r = amb.post({ token: 'outro', acao: 'gravar', linhas: [linha(ID1)] });
    assert.equal(r.ok, false);
    assert.equal(Object.keys(amb.abas).length, 0);
  },
  'ping devolve o nome da planilha'() {
    const amb = novoAmbiente('segredo');
    const r = amb.post({ token: 'segredo', acao: 'ping' });
    assert.deepEqual(r, { ok: true, planilha: 'Termômetro Emocional (teste)' });
  },
  'grava com cabeçalho, aba congelada e colunas de texto'() {
    const amb = novoAmbiente('segredo');
    const r = amb.post({ token: 'segredo', acao: 'gravar', linhas: [linha(ID1), linha(ID2)] });
    assert.equal(r.ok, true);
    assert.equal(r.inseridas, 2);
    const aba = amb.abas.Respostas;
    assert.equal(aba.dados.length, 3);
    assert.equal(aba.dados[0][0], 'response_id');
    assert.equal(aba.dados[0].length, 24);
    assert.equal(aba.congeladas, 1);
    assert.equal(aba.formatos[1], '@');
    assert.equal(aba.dados[1][11], -1, 'pontuação como número');
    assert.equal(aba.dados[1][17], 16.4, 'temperatura como número');
    assert.ok(amb.travas() >= 1, 'usa trava contra gravações simultâneas');
  },
  'reenvio e atualização SUBSTITUEM a linha (sem duplicar)'() {
    const amb = novoAmbiente('segredo');
    amb.post({ token: 'segredo', acao: 'gravar', linhas: [linha(ID1), linha(ID2)] });
    const r = amb.post({ token: 'segredo', acao: 'gravar', linhas: [linha(ID1, { motivo: 'Trânsito/deslocamento' }), linha(ID3)] });
    assert.equal(r.atualizadas, 1);
    assert.equal(r.inseridas, 1);
    const aba = amb.abas.Respostas;
    assert.equal(aba.dados.length, 4, 'cabeçalho + 3 respostas');
    const ids = aba.dados.slice(1).map((l) => l[0]);
    assert.equal(new Set(ids).size, 3);
    assert.equal(aba.dados[1][12], 'Trânsito/deslocamento');
    // reenviar tudo de novo não muda nada
    amb.post({ token: 'segredo', acao: 'gravar', linhas: [linha(ID1, { motivo: 'Trânsito/deslocamento' }), linha(ID2), linha(ID3)] });
    assert.equal(aba.dados.length, 4);
  },
  'mesmo id duas vezes no mesmo envio fica uma linha só (a mais recente)'() {
    const amb = novoAmbiente('segredo');
    amb.post({ token: 'segredo', acao: 'gravar', linhas: [linha(ID1), linha(ID1, { motivo: 'Financeiro' })] });
    const aba = amb.abas.Respostas;
    assert.equal(aba.dados.length, 2);
    assert.equal(aba.dados[1][12], 'Financeiro');
  },
  'id em maiúsculas é tratado como o mesmo registro'() {
    const amb = novoAmbiente('segredo');
    amb.post({ token: 'segredo', acao: 'gravar', linhas: [linha(ID1)] });
    amb.post({ token: 'segredo', acao: 'gravar', linhas: [linha(ID1.toUpperCase(), { motivo: 'Financeiro' })] });
    assert.equal(amb.abas.Respostas.dados.length, 2);
  },
  'ignora linhas sem response_id válido e neutraliza fórmulas'() {
    const amb = novoAmbiente('segredo');
    const r = amb.post({ token: 'segredo', acao: 'gravar', linhas: [{ response_id: 'x' }, linha(ID1, { kiosk_local: '=IMPORTXML("http://x")' })] });
    assert.equal(r.ignoradas, 1);
    assert.equal(amb.abas.Respostas.dados[1][2], '\'=IMPORTXML("http://x")');
  },
  'JSON inválido não derruba o script; abrir a URL no navegador mostra que funciona'() {
    const amb = novoAmbiente('segredo');
    const r = amb.postBruto('isto não é json');
    assert.equal(r.ok, false);
    assert.match(amb.get(), /funcionando/);
  },
  'planilha antiga (sem colunas de setor) ganha as colunas no fim e recebe os dados certos'() {
    const amb = novoAmbiente('segredo');
    const antigas = ['response_id', 'kiosk_id', 'kiosk_local', 'timestamp', 'data', 'dia_semana', 'hora',
      'momento', 'momento_automatico', 'emocao', 'valencia', 'pontuacao', 'motivo', 'pergunta_do_dia',
      'resposta_pergunta_do_dia', 'temperatura_c', 'sensacao_termica_c', 'precipitacao_mm', 'codigo_tempo',
      'condicao', 'dia_ou_noite', 'versao_app'];
    amb.abas.Respostas = criarAba('Respostas');
    amb.abas.Respostas.dados.push(antigas.slice());
    amb.post({ token: 'segredo', acao: 'gravar', linhas: [linha(ID1, { setor: 'Comercial', setor_perguntado: 'sim' })] });
    const aba = amb.abas.Respostas;
    const cabecalho = aba.dados[0];
    assert.equal(cabecalho.length, 24, 'duas colunas novas acrescentadas');
    assert.equal(cabecalho[22], 'setor');
    assert.equal(cabecalho[23], 'setor_perguntado');
    assert.equal(aba.dados[1][cabecalho.indexOf('setor')], 'Comercial');
    assert.equal(aba.dados[1][cabecalho.indexOf('emocao')], 'Cansado');
  },
  'configurarPlanilha cria a aba'() {
    const amb = novoAmbiente('segredo');
    assert.match(amb.configurar(), /pronta/);
    assert.equal(amb.abas.Respostas.dados.length, 1);
  }
};

let falhas = 0;
for (const [nome, fn] of Object.entries(testes)) {
  try { fn(); console.log('  ✔ ' + nome); } catch (e) { falhas++; console.log('  ✘ ' + nome + '\n    ' + e.message); }
}
console.log(`\nCode.gs: ${Object.keys(testes).length - falhas} de ${Object.keys(testes).length} testes passaram.`);
process.exit(falhas ? 1 : 0);
