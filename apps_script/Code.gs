/**
 * Termômetro Emocional — CIPA Eurostec
 * Web App que recebe as respostas dos quiosques e grava na aba "Respostas"
 * desta Planilha Google.
 *
 * PASSO A PASSO COMPLETO: README.md, seção "Planilha Google central".
 * Resumo:
 *   1. Troque o TOKEN abaixo por uma senha longa (use a MESMA no config.json
 *      de cada quiosque, campo "sincronizacao.token").
 *   2. Salve e execute a função "configurarPlanilha" uma vez (autorize o acesso).
 *   3. Implantar > Nova implantação > Tipo "App da Web" >
 *      Executar como: "Eu" > Quem pode acessar: "Qualquer pessoa".
 *   4. Copie a URL que termina em /exec para o config.json dos quiosques.
 *
 * Regras:
 *   - Sem o token correto, nada é gravado.
 *   - Cada resposta tem um response_id único. Se a mesma resposta chegar de
 *     novo (reenvio ou atualização com o motivo), a linha existente é
 *     SUBSTITUÍDA — nunca duplicada.
 */

const TOKEN = 'TROQUE-ESTE-TOKEN';

const NOME_ABA = 'Respostas';
const COLUNAS = [
  'response_id', 'kiosk_id', 'kiosk_local', 'timestamp', 'data', 'dia_semana', 'hora',
  'momento', 'momento_automatico', 'emocao', 'valencia', 'pontuacao', 'motivo',
  'pergunta_do_dia', 'resposta_pergunta_do_dia', 'setor', 'setor_perguntado',
  'temperatura_c', 'sensacao_termica_c',
  'precipitacao_mm', 'codigo_tempo', 'condicao', 'dia_ou_noite', 'versao_app'
];
// Colunas guardadas como texto puro (a planilha não converte em data/número).
const COLUNAS_TEXTO = ['response_id', 'kiosk_id', 'timestamp', 'data', 'hora', 'versao_app'];
const RE_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Recebe os envios dos quiosques. */
function doPost(e) {
  try {
    var corpo = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    if (!TOKEN || TOKEN === 'TROQUE-ESTE-TOKEN') {
      return responder({ ok: false, erro: 'Troque o TOKEN no início do Code.gs e publique uma nova versão do App da Web.' });
    }
    if (corpo.token !== TOKEN) {
      return responder({ ok: false, erro: 'token inválido (confira o token no config.json do quiosque)' });
    }
    if (corpo.acao === 'ping') {
      return responder({ ok: true, planilha: SpreadsheetApp.getActiveSpreadsheet().getName() });
    }
    if (corpo.acao === 'gravar') {
      return responder(gravarLinhas(corpo.linhas));
    }
    return responder({ ok: false, erro: 'ação desconhecida' });
  } catch (erro) {
    return responder({ ok: false, erro: String((erro && erro.message) || erro) });
  }
}

/** Abrir a URL no navegador mostra esta mensagem (serve para testar a publicação). */
function doGet() {
  return ContentService.createTextOutput(
    'Termômetro Emocional — CIPA Eurostec: o App da Web está funcionando. Os quiosques enviam os dados por POST.'
  );
}

/** Execute UMA VEZ pelo editor (botão Executar) para criar a aba e autorizar o script. */
function configurarPlanilha() {
  var aba = obterAba();
  aba.autoResizeColumns(1, COLUNAS.length);
  return 'Aba "' + NOME_ABA + '" pronta.';
}

function gravarLinhas(linhas) {
  if (!Array.isArray(linhas)) return { ok: false, erro: 'lista de linhas inválida' };
  var validas = linhas.filter(function (l) {
    return l && typeof l.response_id === 'string' && RE_ID.test(l.response_id);
  });

  var trava = LockService.getScriptLock();
  trava.waitLock(30000); // vários quiosques ao mesmo tempo: um de cada vez
  try {
    var aba = obterAba();
    // As colunas seguem o cabeçalho REAL da planilha (por nome), então uma planilha
    // antiga, com colunas a menos, continua funcionando.
    var cabecalho = aba.getRange(1, 1, 1, aba.getLastColumn()).getValues()[0].map(String);
    var ultima = aba.getLastRow();
    var linhaDoId = {};
    if (ultima > 1) {
      var ids = aba.getRange(2, 1, ultima - 1, 1).getValues();
      for (var i = 0; i < ids.length; i++) linhaDoId[String(ids[i][0]).toLowerCase()] = i + 2;
    }

    var novas = [];
    var posicaoNova = {};
    var atualizadas = 0;
    validas.forEach(function (l) {
      var id = l.response_id.toLowerCase();
      l.response_id = id;
      var valores = cabecalho.map(function (c) { return valorCelula(l[c]); });
      if (linhaDoId[id]) {
        aba.getRange(linhaDoId[id], 1, 1, cabecalho.length).setValues([valores]);
        atualizadas++;
      } else if (posicaoNova[id] !== undefined) {
        novas[posicaoNova[id]] = valores; // mesmo id duas vezes no mesmo envio: fica a última
      } else {
        posicaoNova[id] = novas.length;
        novas.push(valores);
      }
    });
    if (novas.length) {
      aba.getRange(ultima + 1, 1, novas.length, cabecalho.length).setValues(novas);
    }
    return {
      ok: true,
      recebidas: linhas.length,
      inseridas: novas.length,
      atualizadas: atualizadas,
      ignoradas: linhas.length - validas.length
    };
  } finally {
    trava.releaseLock();
  }
}

function valorCelula(valor) {
  if (valor === null || valor === undefined) return '';
  if (typeof valor === 'number' || typeof valor === 'boolean') return valor;
  var texto = String(valor);
  // Evita que um texto seja interpretado como fórmula.
  if (/^[=+@]/.test(texto)) return "'" + texto;
  return texto;
}

function obterAba() {
  var planilha = SpreadsheetApp.getActiveSpreadsheet();
  var aba = planilha.getSheetByName(NOME_ABA);
  if (!aba) aba = planilha.insertSheet(NOME_ABA);
  if (aba.getLastRow() === 0) {
    aba.getRange(1, 1, 1, COLUNAS.length).setValues([COLUNAS])
      .setFontWeight('bold').setBackground('#0446a4').setFontColor('#ffffff');
    aba.setFrozenRows(1);
    COLUNAS_TEXTO.forEach(function (c) {
      aba.getRange(1, COLUNAS.indexOf(c) + 1, aba.getMaxRows(), 1).setNumberFormat('@');
    });
  } else {
    // Planilha criada antes de uma versão: acrescenta no FIM as colunas que faltam.
    var atual = aba.getRange(1, 1, 1, aba.getLastColumn()).getValues()[0].map(String);
    var faltando = COLUNAS.filter(function (c) { return atual.indexOf(c) < 0; });
    if (faltando.length) {
      aba.getRange(1, atual.length + 1, 1, faltando.length).setValues([faltando])
        .setFontWeight('bold').setBackground('#0446a4').setFontColor('#ffffff');
    }
  }
  return aba;
}

function responder(objeto) {
  return ContentService.createTextOutput(JSON.stringify(objeto))
    .setMimeType(ContentService.MimeType.JSON);
}
