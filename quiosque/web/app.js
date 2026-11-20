/* Termômetro Emocional — CIPA Eurostec (telas do quiosque)
 *
 * Fluxo: início → (escolha do momento) → emoção [GRAVA] → (motivo) → (pergunta do dia) → obrigado → início
 * - Após 6 s sem toque em qualquer tela (menos a inicial), volta ao início.
 * - A emoção é gravada no 1º toque; os toques seguintes só completam o mesmo registro.
 * - Anti-duplo-toque: um NOVO registro só pode começar 2 s após o último toque gravado;
 *   ao trocar de tela há uma trava curta (0,5 s) para o mesmo toque não "cair" no botão seguinte.
 * Nenhum dado pessoal é coletado. Nada de câmera, nome, crachá ou texto livre.
 */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var TELAS_COM_TEMPO = ['tela-momento', 'tela-emocoes', 'tela-motivo', 'tela-pergunta'];
  var TELAS_ADMIN = ['tela-pin', 'tela-admin'];

  var estado = null;          // dados de /api/estado
  var assinaturaEstado = '';  // para saber quando redesenhar
  var telaAtual = null;
  var telaDesde = 0;
  var ultimoRegistro = 0;
  var timerTela = null;
  var fluxo = null;           // resposta em andamento
  var ocupado = false;        // gravando / iniciando
  var adminToken = null;
  var adminConfig = null;
  var timerAdmin = null;
  var timerStatusAdmin = null;

  // ------------------------------------------------------------------ utilidades
  function tempoMs(nome, padraoMs) {
    var t = estado && estado.tempos ? estado.tempos[nome] : undefined;
    return typeof t === 'number' ? t * 1000 : padraoMs;
  }
  function texto(nome) { return (estado && estado.textos && estado.textos[nome]) || ''; }
  function escapar(t) {
    return String(t).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  /* "**texto**" vira negrito: títulos em dois pesos (Regular + Bold), como pede o design system. */
  function negritoSimples(t) { return escapar(t).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>'); }
  function semMarcacao(t) { return String(t).replace(/\*\*/g, ''); }
  function momentoPorId(id) {
    for (var i = 0; i < estado.momentos.length; i++) if (estado.momentos[i].id === id) return estado.momentos[i];
    return null;
  }
  function novoId() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    var b = new Uint8Array(16);
    crypto.getRandomValues(b);
    b[6] = (b[6] & 0x0f) | 0x40; b[8] = (b[8] & 0x3f) | 0x80;
    var h = Array.prototype.map.call(b, function (x) { return (x + 0x100).toString(16).slice(1); }).join('');
    return h.slice(0, 8) + '-' + h.slice(8, 12) + '-' + h.slice(12, 16) + '-' + h.slice(16, 20) + '-' + h.slice(20);
  }
  function el(tag, classe, conteudo) {
    var e = document.createElement(tag);
    if (classe) e.className = classe;
    if (conteudo !== undefined) e.textContent = conteudo;
    return e;
  }

  function api(caminho, opcoes, limiteMs) {
    opcoes = opcoes || {};
    var ctrl = window.AbortController ? new AbortController() : null;
    var t = setTimeout(function () { if (ctrl) ctrl.abort(); }, limiteMs || 8000);
    var cabecalhos = { 'Content-Type': 'application/json' };
    if (adminToken) cabecalhos['X-Admin-Token'] = adminToken;
    return fetch(caminho, {
      method: opcoes.method || 'GET',
      body: opcoes.body,
      headers: cabecalhos,
      cache: 'no-store',
      signal: ctrl ? ctrl.signal : undefined
    }).then(function (resp) {
      return resp.json().catch(function () { return {}; }).then(function (dados) {
        if (!resp.ok || dados.ok === false) {
          var erro = new Error(dados.erro || dados.mensagem || ('Erro ' + resp.status));
          erro.status = resp.status; erro.dados = dados;
          throw erro;
        }
        return dados;
      });
    }).finally(function () { clearTimeout(t); });
  }
  function post(caminho, corpo, limiteMs) {
    return api(caminho, { method: 'POST', body: JSON.stringify(corpo || {}) }, limiteMs);
  }

  var timerAviso = null;
  function aviso(msg, ms) {
    var a = $('aviso');
    a.textContent = msg;
    a.classList.add('visivel');
    clearTimeout(timerAviso);
    timerAviso = setTimeout(function () { a.classList.remove('visivel'); }, ms || 3000);
  }

  // ------------------------------------------------------------------ telas
  function mostrar(id) {
    var anterior = telaAtual;
    document.querySelectorAll('.tela').forEach(function (t) { t.classList.toggle('ativa', t.id === id); });
    telaAtual = id;
    telaDesde = Date.now();
    clearTimeout(timerTela);
    $('canto-admin').hidden = TELAS_ADMIN.indexOf(id) >= 0;
    if (TELAS_COM_TEMPO.indexOf(id) >= 0) reiniciarContagem();
    if (TELAS_ADMIN.indexOf(anterior) >= 0 && TELAS_ADMIN.indexOf(id) < 0) encerrarAdmin();
    if (id === 'tela-inicio') { fluxo = null; ocupado = false; atualizarRodape(); }
  }

  function reiniciarContagem() {
    clearTimeout(timerTela);
    var ms = tempoMs('inatividade_s', 6000);
    timerTela = setTimeout(voltarInicio, ms);
    var barra = document.querySelector('#' + telaAtual + ' .barra-tempo span');
    if (barra) {
      barra.style.transition = 'none';
      barra.style.transform = 'scaleX(1)';
      void barra.offsetWidth; // reinicia a animação
      barra.style.transition = 'transform ' + ms + 'ms linear';
      barra.style.transform = 'scaleX(0)';
    }
  }

  function voltarInicio() { mostrar('tela-inicio'); }

  /* Anti-duplo-toque. novoRegistro=true para toques que começam um registro novo. */
  function travado(novoRegistro) {
    var agora = Date.now();
    if (agora - telaDesde < tempoMs('trava_entre_telas_s', 500)) return true;
    if (novoRegistro && agora - ultimoRegistro < tempoMs('bloqueio_novo_registro_s', 2000)) return true;
    return false;
  }

  // ------------------------------------------------------------------ desenho
  function desenharTudo() {
    document.title = semMarcacao(texto('titulo')) || document.title;
    $('inicio-titulo').innerHTML = negritoSimples(texto('titulo'));
    $('inicio-texto').innerHTML = negritoSimples(texto('texto_inicial'));
    $('botao-iniciar').textContent = texto('botao_iniciar');
    $('momento-titulo').innerHTML = negritoSimples(texto('titulo_escolher_momento'));
    $('botao-trocar-momento').textContent = texto('trocar_momento');
    $('motivo-pular').textContent = texto('pular');
    $('pergunta-pular').textContent = texto('pular');
    $('pergunta-selo').textContent = texto('titulo_pergunta_do_dia');

    var grade = $('emocoes-grade');
    grade.innerHTML = '';
    estado.emocoes.forEach(function (e) {
      var b = el('button', 'emocao');
      b.type = 'button';
      b.style.setProperty('--cor', e.cor);
      b.style.setProperty('--cor-texto', e.cor_texto);
      b.appendChild(el('span', 'emoji', e.emoji));
      b.appendChild(el('span', 'nome', e.nome));
      b.setAttribute('data-emocao', e.nome);
      b.addEventListener('click', function () { escolherEmocao(e, b); });
      grade.appendChild(b);
    });
    grade.style.gridTemplateColumns = 'repeat(' + Math.ceil(estado.emocoes.length / 2) + ', 1fr)';

    var momentos = $('momento-opcoes');
    momentos.innerHTML = '';
    estado.momentos.forEach(function (m) {
      var b = el('button', 'botao-momento');
      b.type = 'button';
      b.setAttribute('data-momento', m.id);
      if (m.icone) b.appendChild(el('span', 'icone', m.icone));
      b.appendChild(el('span', 'nome', m.nome));
      b.addEventListener('click', function () { escolherMomento(m.id); });
      momentos.appendChild(b);
    });
    atualizarRodape();
  }

  function atualizarRodape() {
    if (!estado) return;
    var x = estado.contagem_hoje || 0;
    $('inicio-rodape').textContent = x === 0 ? texto('rodape_zero')
      : x === 1 ? texto('rodape_um') : texto('rodape').replace('{x}', x);
  }

  function aplicarEstado(novo) {
    estado = novo;
    var assinatura = JSON.stringify([novo.textos, novo.emocoes, novo.momentos, novo.motivos, novo.pergunta_do_dia, novo.tempos]);
    if (assinatura !== assinaturaEstado) { assinaturaEstado = assinatura; desenharTudo(); }
    atualizarRodape();
    $('sem-servidor').hidden = true;
  }

  function carregarEstado(limiteMs) {
    return api('/api/estado', {}, limiteMs).then(aplicarEstado);
  }

  // ------------------------------------------------------------------ fluxo
  function iniciarFluxo() {
    if (telaAtual !== 'tela-inicio' || ocupado || travado(true)) return;
    ocupado = true;
    carregarEstado(1500).catch(function () {
      if (!estado) throw new Error('sem servidor');
    }).then(function () {
      fluxo = { id: novoId(), momento: null, automatico: false, emocao: null, etapas: [], contagem: 0 };
      if (estado.momento_atual) {
        definirMomento(estado.momento_atual, true);
        mostrar('tela-emocoes');
      } else {
        mostrar('tela-momento');
      }
    }).catch(function () {
      $('sem-servidor').hidden = false;
    }).finally(function () { ocupado = false; });
  }

  function definirMomento(id, automatico) {
    fluxo.momento = id;
    fluxo.automatico = automatico;
    $('emocoes-titulo').innerHTML = negritoSimples(momentoPorId(id).pergunta);
    var grade = $('emocoes-grade');
    grade.classList.remove('escolhendo');
    grade.querySelectorAll('.emocao').forEach(function (b) { b.classList.remove('escolhido'); b.disabled = false; });
  }

  function escolherMomento(id) {
    if (!fluxo || travado(false)) return;
    definirMomento(id, false);
    mostrar('tela-emocoes');
  }

  function trocarMomento() {
    if (!fluxo || ocupado || travado(false)) return;
    mostrar('tela-momento');
  }

  function criarResposta(corpo, tentativa) {
    return post('/api/respostas', corpo, 4000).catch(function (erro) {
      // Mesmo response_id: repetir é seguro, o servidor não duplica.
      if (tentativa < 2 && !(erro.status >= 400 && erro.status < 500)) {
        return new Promise(function (ok) { setTimeout(ok, 400); }).then(function () { return criarResposta(corpo, tentativa + 1); });
      }
      throw erro;
    });
  }

  function escolherEmocao(emocao, botao) {
    if (!fluxo || ocupado || travado(true)) return;
    ocupado = true;
    var grade = $('emocoes-grade');
    grade.classList.add('escolhendo');
    botao.classList.add('escolhido');
    grade.querySelectorAll('.emocao').forEach(function (b) { b.disabled = true; });
    criarResposta({
      response_id: fluxo.id,
      momento: fluxo.momento,
      momento_automatico: fluxo.automatico,
      emocao: emocao.nome
    }, 0).then(function (r) {
      ultimoRegistro = Date.now();
      fluxo.emocao = emocao;
      fluxo.contagem = r.contagem_hoje;
      if (estado) estado.contagem_hoje = r.contagem_hoje;
      fluxo.etapas = calcularEtapas();
      ocupado = false;
      avancar();
    }).catch(function () {
      ocupado = false;
      aviso(texto('erro_registro'), 3500);
      voltarInicio();
    });
  }

  function calcularEtapas() {
    var etapas = [];
    var valencia = fluxo.emocao.valencia;
    var motivos = (estado.motivos[fluxo.momento] || {})[valencia];
    if (valencia !== 'neutra' && motivos && motivos.opcoes && motivos.opcoes.length) etapas.push('motivo');
    var p = estado.pergunta_do_dia;
    if (p && p.momentos.indexOf(fluxo.momento) >= 0 && (valencia !== 'neutra' || p.mostrar_para_neutro)) etapas.push('pergunta');
    etapas.push('obrigado');
    return etapas;
  }

  function avancar() {
    var etapa = fluxo.etapas.shift();
    if (etapa === 'motivo') { desenharMotivo(); mostrar('tela-motivo'); }
    else if (etapa === 'pergunta') { desenharPergunta(); mostrar('tela-pergunta'); }
    else mostrarObrigado();
  }

  function desenharMotivo() {
    var grupo = estado.motivos[fluxo.momento][fluxo.emocao.valencia];
    var chip = $('motivo-emocao');
    chip.innerHTML = '';
    chip.style.setProperty('--cor', fluxo.emocao.cor);
    chip.style.setProperty('--cor-texto', fluxo.emocao.cor_texto);
    chip.appendChild(el('span', 'emoji', fluxo.emocao.emoji));
    chip.appendChild(el('span', '', fluxo.emocao.nome));
    $('motivo-titulo').innerHTML = negritoSimples(grupo.titulo);
    var caixa = $('motivo-opcoes');
    caixa.innerHTML = '';
    var n = grupo.opcoes.length;
    caixa.style.setProperty('--colunas', n <= 3 ? n : (n <= 6 ? 3 : 4));
    grupo.opcoes.forEach(function (opcao) {
      var b = el('button', 'opcao' + (/prefiro não dizer/i.test(opcao) ? ' secundaria' : ''), opcao);
      b.type = 'button';
      b.addEventListener('click', function () { completar({ motivo: opcao }, b); });
      caixa.appendChild(b);
    });
  }

  function desenharPergunta() {
    var p = estado.pergunta_do_dia;
    $('pergunta-texto').textContent = p.texto;
    var caixa = $('pergunta-opcoes');
    caixa.innerHTML = '';
    caixa.style.gridTemplateColumns = 'repeat(' + p.opcoes.length + ', 1fr)';
    p.opcoes.forEach(function (opcao) {
      var b = el('button', 'opcao', opcao);
      b.type = 'button';
      b.addEventListener('click', function () { completar({ resposta_pergunta_do_dia: opcao }, b); });
      caixa.appendChild(b);
    });
  }

  /* Toques 2 e 3: atualizam o MESMO registro (mesmo response_id). */
  function completar(campos, botao) {
    if (!fluxo || ocupado || travado(false)) return;
    ocupado = true;
    botao.classList.add('escolhido');
    post('/api/respostas/' + fluxo.id, campos, 4000).then(function (r) {
      ultimoRegistro = Date.now();
      fluxo.contagem = r.contagem_hoje;
    }).catch(function () {
      // A emoção já está gravada; seguimos sem travar a pessoa.
    }).finally(function () {
      ocupado = false;
      if (fluxo) avancar();
    });
  }

  function pular() {
    if (!fluxo || ocupado || travado(false)) return;
    avancar();
  }

  function mostrarObrigado() {
    var x = fluxo.contagem || (estado && estado.contagem_hoje) || 1;
    $('obrigado-texto').innerHTML = negritoSimples(x === 1 ? texto('agradecimento_um') : texto('agradecimento').replace('{x}', x));
    var acolher = !!(fluxo.emocao && fluxo.emocao.acolhimento);
    $('obrigado-acolhimento').textContent = acolher ? texto('acolhimento') : '';
    mostrar('tela-obrigado');
    timerTela = setTimeout(voltarInicio, acolher ? tempoMs('acolhimento_s', 4000) : tempoMs('agradecimento_s', 1500));
  }

  // ------------------------------------------------------------------ administração
  var pinDigitado = '';

  function abrirPin() {
    pinDigitado = '';
    desenharPin();
    $('pin-erro').textContent = '';
    mostrar('tela-pin');
    reiniciarTimerAdmin();
  }

  function desenharPin() {
    var pontos = $('pin-pontos');
    pontos.innerHTML = '';
    for (var i = 0; i < pinDigitado.length; i++) pontos.appendChild(el('span'));
  }

  function montarTecladoPin() {
    var teclado = $('pin-teclado');
    ['1', '2', '3', '4', '5', '6', '7', '8', '9', 'Apagar', '0', 'OK'].forEach(function (tecla) {
      var b = el('button', tecla === 'OK' ? 'ok' : (tecla === 'Apagar' ? 'acao' : ''), tecla);
      b.type = 'button';
      b.addEventListener('click', function () {
        if (tecla === 'Apagar') pinDigitado = pinDigitado.slice(0, -1);
        else if (tecla === 'OK') return entrarAdmin();
        else if (pinDigitado.length < 8) pinDigitado += tecla;
        $('pin-erro').textContent = '';
        desenharPin();
      });
      teclado.appendChild(b);
    });
  }

  function entrarAdmin() {
    if (!pinDigitado) return;
    post('/api/admin/login', { pin: pinDigitado }).then(function (r) {
      adminToken = r.token;
      mostrar('tela-admin');
      $('tela-admin').scrollTop = 0;
      carregarStatusAdmin();
      carregarConfigAdmin();
      clearInterval(timerStatusAdmin);
      timerStatusAdmin = setInterval(carregarStatusAdmin, 5000);
    }).catch(function (erro) {
      pinDigitado = '';
      desenharPin();
      $('pin-erro').textContent = erro.message || 'PIN incorreto.';
    });
  }

  function reiniciarTimerAdmin() {
    clearTimeout(timerAdmin);
    timerAdmin = setTimeout(voltarInicio, tempoMs('admin_inatividade_s', 120000));
  }

  function encerrarAdmin() {
    adminToken = null;
    clearTimeout(timerAdmin);
    clearInterval(timerStatusAdmin);
    carregarEstado().catch(function () {});
  }

  function selo(classe, t) { return '<span class="selo-status ' + classe + '">' + escapar(t) + '</span>'; }
  function linhaDados(dl, pares) {
    dl.innerHTML = pares.map(function (p) {
      return '<dt>' + escapar(p[0]) + '</dt><dd>' + (p[2] ? p[1] : escapar(p[1] === '' || p[1] == null ? '—' : p[1])) + '</dd>';
    }).join('');
  }

  function carregarStatusAdmin() {
    if (!adminToken) return;
    api('/api/admin/status').then(function (s) {
      $('admin-subtitulo').textContent = 'Quiosque ' + s.kiosk.id + ' — ' + s.kiosk.local + ' · ' + s.agora;
      var c = s.contagens_hoje;
      var html = '<div class="total"><b>' + c.total + '</b>Total</div>';
      estado.momentos.forEach(function (m) { html += '<div><b>' + (c[m.id] || 0) + '</b>' + escapar(m.nome) + '</div>'; });
      $('admin-contagens').innerHTML = html;
      var m = s.momento_atual ? momentoPorId(s.momento_atual) : null;
      $('admin-momento').textContent = 'Momento automático agora: ' + (m ? m.nome : 'nenhum (a pessoa escolhe o momento)');

      var sinc = s.sincronizacao;
      var situacao = !sinc.configurada ? selo('alerta', 'Não configurada')
        : sinc.ultimo_erro ? selo('erro', 'Com erro') : sinc.pendentes ? selo('alerta', 'Enviando') : selo('ok', 'Em dia');
      linhaDados($('admin-sinc'), [
        ['Situação', situacao, true],
        ['Pendentes', String(sinc.pendentes)],
        ['Enviados hoje', String(sinc.enviados_hoje)],
        ['Enviados (total)', String(sinc.enviados_total)],
        ['Último envio', sinc.ultimo_envio_ok],
        ['Último erro', sinc.ultimo_erro + (sinc.proxima_tentativa_em_s ? ' (nova tentativa em ' + sinc.proxima_tentativa_em_s + ' s)' : '')]
      ]);

      var cl = s.clima, v = cl.valores || {};
      linhaDados($('admin-clima'), [
        ['Situação', !cl.ativo ? selo('alerta', 'Desligado') : cl.valido ? selo('ok', 'Atualizado') : selo('erro', 'Sem dados recentes'), true],
        ['Atualizado em', cl.atualizado_em],
        ['Temperatura', v.temperatura_c !== undefined && v.temperatura_c !== '' ? v.temperatura_c + ' °C (sensação ' + v.sensacao_termica_c + ' °C)' : ''],
        ['Condição', v.condicao ? v.condicao + ' · ' + v.dia_ou_noite + ' · chuva ' + v.precipitacao_mm + ' mm' : ''],
        ['Último erro', cl.ultimo_erro]
      ]);

      var caixa = $('admin-pendrives');
      caixa.innerHTML = '';
      (s.pendrives || []).forEach(function (p) {
        var b = el('button', 'botao-admin principal', 'Exportar para ' + p.letra + ' (' + p.nome + ')');
        b.type = 'button';
        b.addEventListener('click', function () { exportar(p.letra); });
        caixa.appendChild(b);
      });
      if (!s.pendrives || !s.pendrives.length) caixa.appendChild(el('p', 'nota', s.windows ? 'Nenhum pendrive encontrado. Conecte um pendrive e aguarde alguns segundos.' : 'Detecção de pendrive disponível apenas no Windows.'));
      var local = el('button', 'botao-admin', 'Salvar na pasta "exportacoes" do quiosque');
      local.type = 'button';
      local.addEventListener('click', function () { exportar(null); });
      caixa.appendChild(local);
      $('admin-csv').innerHTML = escapar(s.csv.arquivos + ' arquivo(s) de respostas em ' + s.csv.pasta) +
        (s.csv.erro ? '<br>' + selo('erro', 'Atenção') + ' ' + escapar(s.csv.erro) : '');

      linhaDados($('admin-sistema'), [
        ['Versão', s.versao],
        ['Data e hora do PC', s.agora],
        ['Endereço', location.origin]
      ]);
    }).catch(tratarErroAdmin);
  }

  function tratarErroAdmin(erro) {
    if (erro && erro.status === 401) { aviso('Sessão expirada. Digite o PIN novamente.'); abrirPin(); }
  }

  function mensagem(id, t, ok) {
    var m = $(id);
    m.textContent = t;
    m.className = 'mensagem ' + (ok ? 'ok' : 'erro');
  }

  function acaoAdmin(acao, botao) {
    if (acao === 'reenviar_tudo' && !confirm('Reenviar todas as respostas deste quiosque para a planilha? (Não cria duplicatas.)')) return;
    botao.disabled = true;
    var alvo = acao === 'atualizar_clima' ? 'admin-clima-msg' : 'admin-sinc-msg';
    mensagem(alvo, 'Aguarde…', true);
    post('/api/admin/' + acao, {}, 120000).then(function (r) {
      var t = {
        testar_sincronizacao: r.mensagem,
        enviar_agora: r.resultado === 'nada' ? 'Não havia nada pendente.' : 'Pendentes enviados.',
        reenviar_tudo: r.quantidade + ' resposta(s) colocadas na fila de envio.',
        atualizar_clima: r.ok ? 'Clima atualizado.' : 'Não foi possível obter o clima (sem internet?).'
      }[acao];
      mensagem(alvo, t, acao !== 'atualizar_clima' || r.ok);
    }).catch(function (erro) {
      tratarErroAdmin(erro);
      mensagem(alvo, (erro.dados && (erro.dados.mensagem || erro.dados.erro)) || erro.message, false);
    }).finally(function () { botao.disabled = false; carregarStatusAdmin(); });
  }

  function exportar(destino) {
    mensagem('admin-exportar-msg', 'Copiando…', true);
    post('/api/admin/exportar', { destino: destino }, 60000).then(function (r) {
      mensagem('admin-exportar-msg', r.copiados + ' arquivo(s) copiado(s) para:\n' + r.pasta + (destino ? '\nAguarde 5 segundos antes de retirar o pendrive.' : ''), true);
    }).catch(function (erro) { tratarErroAdmin(erro); mensagem('admin-exportar-msg', erro.message, false); });
  }

  // Campos do formulário simples (o restante fica no editor avançado)
  function camposFormulario() {
    var secoes = [
      { titulo: 'Quiosque', campos: [
        { r: 'Código do quiosque (ex.: Q01)', c: 'kiosk_id' },
        { r: 'Local', c: 'kiosk_local' },
        { r: 'PIN da administração', c: 'pin_admin', modo: 'numeric' },
        { r: 'Logo azul (telas claras)', c: 'logo' },
        { r: 'Logo branco (telas azuis)', c: 'logo_branco' },
        { r: 'Fundo azul oficial', c: 'fundo_azul' }
      ] }
    ];
    secoes.push({ titulo: 'Momentos do dia (horário automático, segunda a sexta)', tabelaMomentos: true });
    secoes.push({ titulo: 'Pergunta do dia', campos: [
      { r: 'Pergunta do dia ligada', c: 'pergunta_do_dia.ativa', tipo: 'checkbox' },
      { r: 'Mostrar também para quem escolheu Neutro', c: 'pergunta_do_dia.mostrar_para_neutro', tipo: 'checkbox' }
    ] });
    secoes.push({ titulo: 'Clima (Open-Meteo)', campos: [
      { r: 'Clima ligado', c: 'clima.ativo', tipo: 'checkbox' },
      { r: 'Latitude', c: 'clima.latitude', tipo: 'number' },
      { r: 'Longitude', c: 'clima.longitude', tipo: 'number' }
    ] });
    secoes.push({ titulo: 'Planilha Google', campos: [
      { r: 'URL do App da Web (termina em /exec)', c: 'sincronizacao.url' },
      { r: 'Token secreto', c: 'sincronizacao.token' }
    ] });
    return secoes;
  }
  function lerCaminho(obj, caminho) { return caminho.split('.').reduce(function (o, k) { return o == null ? undefined : o[k]; }, obj); }
  function gravarCaminho(obj, caminho, valor) {
    var partes = caminho.split('.'), o = obj;
    for (var i = 0; i < partes.length - 1; i++) { if (o[partes[i]] == null) o[partes[i]] = {}; o = o[partes[i]]; }
    o[partes[partes.length - 1]] = valor;
  }

  function carregarConfigAdmin() {
    api('/api/admin/config').then(function (r) {
      adminConfig = r.config;
      var form = $('admin-form');
      form.innerHTML = '';
      function criarInput(campo) {
        var input = document.createElement('input');
        input.type = campo.tipo || 'text';
        input.setAttribute('data-caminho', campo.c);
        var valor = lerCaminho(adminConfig, campo.c);
        if (campo.tipo === 'checkbox') input.checked = !!valor;
        else input.value = valor == null ? '' : valor;
        if (campo.tipo === 'number') input.step = 'any';
        if (campo.modo) input.inputMode = campo.modo;
        if (campo.hora) { input.placeholder = 'HH:MM'; input.maxLength = 5; input.className = 'campo-hora'; }
        if (campo.r) input.setAttribute('aria-label', campo.r);
        return input;
      }
      camposFormulario().forEach(function (secao) {
        var fs = el('fieldset');
        fs.appendChild(el('legend', '', secao.titulo));
        if (secao.tabelaMomentos) {
          var tabela = el('div', 'tabela-momentos');
          ['Momento', 'Início', 'Fim', 'Perguntar o motivo'].forEach(function (t) { tabela.appendChild(el('div', 'cab', t)); });
          estado.momentos.forEach(function (m) {
            tabela.appendChild(el('div', 'nome-momento', m.nome));
            tabela.appendChild(criarInput({ r: m.nome + ' — início', c: 'momentos.' + m.id + '.inicio', hora: true }));
            tabela.appendChild(criarInput({ r: m.nome + ' — fim', c: 'momentos.' + m.id + '.fim', hora: true }));
            var lab = el('label', 'check-label');
            lab.appendChild(criarInput({ r: m.nome + ': perguntar o motivo', c: 'momentos.' + m.id + '.perguntar_motivo', tipo: 'checkbox' }));
            lab.appendChild(document.createTextNode('sim'));
            tabela.appendChild(lab);
          });
          fs.appendChild(tabela);
          fs.appendChild(el('p', 'nota', 'O início faz parte da janela e o fim não (ex.: 12:20 já é "Volta do almoço"). Fora das janelas, nos fins de semana e nos feriados, a pessoa escolhe o momento.'));
          form.appendChild(fs);
          return;
        }
        var grade = el('div', 'campos');
        secao.campos.forEach(function (campo) {
          var label = el('label', campo.tipo === 'checkbox' ? 'check-label' : '');
          var input = criarInput(campo);
          if (campo.tipo === 'checkbox') { label.appendChild(input); label.appendChild(document.createTextNode(campo.r)); }
          else { label.appendChild(document.createTextNode(campo.r)); label.appendChild(input); }
          grade.appendChild(label);
        });
        fs.appendChild(grade);
        form.appendChild(fs);
      });
      $('admin-json').value = JSON.stringify(adminConfig, null, 2);
    }).catch(tratarErroAdmin);
  }

  function salvarConfig(novo) {
    mensagem('admin-config-msg', 'Salvando…', true);
    post('/api/admin/config', { config: novo }).then(function () {
      mensagem('admin-config-msg', 'Configuração salva e aplicada.', true);
      carregarEstado().then(carregarConfigAdmin).catch(function () {});
      carregarStatusAdmin();
    }).catch(function (erro) {
      tratarErroAdmin(erro);
      var lista = (erro.dados && erro.dados.erros) || [erro.message];
      mensagem('admin-config-msg', 'Não foi salvo. Corrija:\n• ' + lista.join('\n• '), false);
    });
  }

  function salvarFormulario() {
    if (!adminConfig) return;
    var novo = JSON.parse(JSON.stringify(adminConfig));
    $('admin-form').querySelectorAll('input[data-caminho]').forEach(function (input) {
      var valor;
      if (input.type === 'checkbox') valor = input.checked;
      else if (input.type === 'number') valor = input.value === '' ? null : Number(input.value);
      else valor = input.value.trim();
      gravarCaminho(novo, input.getAttribute('data-caminho'), valor);
    });
    salvarConfig(novo);
  }

  function salvarJson() {
    var novo;
    try { novo = JSON.parse($('admin-json').value); }
    catch (e) { mensagem('admin-config-msg', 'O texto tem um erro de digitação (confira vírgulas, aspas e chaves): ' + e.message, false); return; }
    salvarConfig(novo);
  }

  function encerrarQuiosque() {
    if (!confirm('Fechar o quiosque e voltar para o Windows? Para abrir de novo, use "iniciar_quiosque.bat" ou reinicie o computador.')) return;
    post('/api/admin/encerrar', {}).finally(function () {
      adminToken = null;
      document.body.innerHTML = '<div class="sobreposicao"><div><h2>Quiosque encerrado.</h2><p>Se o navegador não fechar sozinho, pressione Alt+F4.</p></div></div>';
    });
  }

  // ------------------------------------------------------------------ canto escondido (toque longo)
  function configurarCanto() {
    var canto = $('canto-admin');
    var timer = null, disparou = false;
    canto.addEventListener('pointerdown', function (e) {
      e.preventDefault();
      disparou = false;
      try { canto.setPointerCapture(e.pointerId); } catch (x) { /* ok */ }
      clearTimeout(timer);
      timer = setTimeout(function () { disparou = true; abrirPin(); }, tempoMs('toque_longo_admin_s', 3000));
    });
    function cancelar() { clearTimeout(timer); }
    canto.addEventListener('pointerup', function () {
      cancelar();
      // Toque curto no canto da tela inicial também começa o fluxo.
      if (!disparou && telaAtual === 'tela-inicio') iniciarFluxo();
    });
    canto.addEventListener('pointercancel', cancelar);
    canto.addEventListener('lostpointercapture', cancelar);
  }

  // ------------------------------------------------------------------ proteções do quiosque
  function protegerQuiosque() {
    document.addEventListener('contextmenu', function (e) { if (telaAtual !== 'tela-admin') e.preventDefault(); });
    document.addEventListener('dragstart', function (e) { e.preventDefault(); });
    document.addEventListener('selectstart', function (e) {
      if (telaAtual !== 'tela-admin') e.preventDefault();
    });
    // Sem zoom com dois dedos / Ctrl+roda
    document.addEventListener('touchstart', function (e) { if (e.touches.length > 1) e.preventDefault(); }, { passive: false });
    document.addEventListener('gesturestart', function (e) { e.preventDefault(); });
    document.addEventListener('wheel', function (e) { if (e.ctrlKey) e.preventDefault(); }, { passive: false });
    // Qualquer toque reinicia a contagem de 6 s (e a de inatividade da administração).
    document.addEventListener('pointerdown', function () {
      if (TELAS_COM_TEMPO.indexOf(telaAtual) >= 0) reiniciarContagem();
      if (TELAS_ADMIN.indexOf(telaAtual) >= 0) reiniciarTimerAdmin();
      manterTelaLigada();
    }, true);
    document.addEventListener('keydown', function () { if (TELAS_ADMIN.indexOf(telaAtual) >= 0) reiniciarTimerAdmin(); }, true);
  }

  var travaTela = null;
  function manterTelaLigada() {
    if (travaTela || !('wakeLock' in navigator) || document.visibilityState !== 'visible') return;
    navigator.wakeLock.request('screen').then(function (t) {
      travaTela = t;
      t.addEventListener('release', function () { travaTela = null; });
    }).catch(function () { /* sem suporte ou sem permissão: o Windows cuida (README) */ });
  }

  /* Sem o arquivo oficial, o logo some: nunca é substituído por texto (regra da marca). */
  function verificarLogo() {
    document.querySelectorAll('img.logo').forEach(function (img) {
      function semLogo() { img.classList.add('sem-logo'); }
      img.addEventListener('error', semLogo);
      if (img.complete && img.naturalWidth === 0) semLogo();
    });
  }

  // ------------------------------------------------------------------ início
  function iniciar() {
    verificarLogo();
    protegerQuiosque();
    configurarCanto();
    montarTecladoPin();

    $('tela-inicio').addEventListener('click', iniciarFluxo);
    $('botao-trocar-momento').addEventListener('click', trocarMomento);
    $('motivo-pular').addEventListener('click', pular);
    $('pergunta-pular').addEventListener('click', pular);
    $('pin-cancelar').addEventListener('click', voltarInicio);
    $('admin-sair').addEventListener('click', voltarInicio);
    $('admin-salvar').addEventListener('click', salvarFormulario);
    $('admin-salvar-json').addEventListener('click', salvarJson);
    $('admin-restaurar-json').addEventListener('click', function () { $('admin-json').value = JSON.stringify(adminConfig, null, 2); });
    $('admin-recarregar').addEventListener('click', function () { location.reload(); });
    $('admin-encerrar').addEventListener('click', encerrarQuiosque);
    document.querySelectorAll('[data-acao]').forEach(function (b) {
      b.addEventListener('click', function () { acaoAdmin(b.getAttribute('data-acao'), b); });
    });
    document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'visible') manterTelaLigada(); });

    // Atualiza contagem e momento periodicamente enquanto está na tela inicial.
    setInterval(function () {
      if (telaAtual === 'tela-inicio') carregarEstado().catch(function () { $('sem-servidor').hidden = false; });
    }, 30000);

    function tentar() {
      carregarEstado().then(function () { mostrar('tela-inicio'); manterTelaLigada(); })
        .catch(function () { $('sem-servidor').hidden = false; setTimeout(tentar, 3000); });
    }
    tentar();
  }

  // Exposto só para os testes automáticos de tela.
  window.__termometro = {
    tela: function () { return telaAtual; },
    fluxo: function () { return fluxo; }
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
