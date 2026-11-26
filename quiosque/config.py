"""Configuração do quiosque: valores padrão, leitura, validação e gravação.

O arquivo config/config.json de cada quiosque só precisa ter o que for
diferente do padrão — o que faltar é completado com os valores abaixo.
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from .formato import MOMENTOS, VALENCIAS

# ---------------------------------------------------------------------------
# Pastas
# ---------------------------------------------------------------------------

def pasta_base() -> Path:
    """Pasta principal do sistema (onde ficam config/, dados/, assets/...).

    - Rodando pelo Python: a pasta acima de quiosque/.
    - Rodando pelo executável (PyInstaller): a pasta do .exe, ou a pasta acima
      dela se o .exe estiver dentro de bin/.
    - A variável de ambiente TERMOMETRO_BASE tem prioridade (usada nos testes).
    """
    if os.environ.get("TERMOMETRO_BASE"):
        return Path(os.environ["TERMOMETRO_BASE"]).resolve()
    if getattr(sys, "frozen", False):
        pasta_exe = Path(sys.executable).resolve().parent
        return pasta_exe.parent if pasta_exe.name.lower() == "bin" else pasta_exe
    return Path(__file__).resolve().parent.parent


def pasta_web() -> Path:
    """Pasta com o frontend (index.html, estilo.css, app.js).

    A variável TERMOMETRO_WEB tem prioridade (usada pelo app Android, que copia
    as telas para a memória interna do tablet).
    """
    if os.environ.get("TERMOMETRO_WEB"):
        return Path(os.environ["TERMOMETRO_WEB"]).resolve()
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "quiosque" / "web"
    return Path(__file__).resolve().parent / "web"


# ---------------------------------------------------------------------------
# Valores padrão
# ---------------------------------------------------------------------------

PADRAO: dict = {
    "_leia_me": (
        "Configuração deste quiosque. Cada computador tem a sua. "
        "Veja o README, seção 'Configuração do quiosque'. "
        "Depois de alterar, reinicie o quiosque ou salve pela área de administração."
    ),
    "kiosk_id": "Q01",
    "kiosk_local": "Portaria",
    "pin_admin": "2468",
    "porta": 8080,
    "logo": "assets/Eurostec-logo-azul.png",
    "logo_branco": "assets/Eurostec-logo-branco.png",
    "fundo_azul": "assets/BG_all_blue.jpg",
    "fuso_horario": "America/Sao_Paulo",
    "expediente": {
        "dias": ["segunda", "terça", "quarta", "quinta", "sexta"],
        "periodos": [
            {"inicio": "07:30", "fim": "11:50"},
            {"inicio": "13:00", "fim": "17:04"},
        ],
    },
    "feriados": [],
    "momentos": {
        "chegada": {
            "nome": "Chegada",
            "icone": "🌅",
            "inicio": "05:00",
            "fim": "10:00",
            "pergunta": "Como você está **chegando hoje?**",
            "perguntar_motivo": True,
        },
        "saida_almoco": {
            "nome": "Saída para o almoço",
            "icone": "🍽️",
            "inicio": "11:30",
            "fim": "12:20",
            "pergunta": "Como você está **saindo para o almoço?**",
            "perguntar_motivo": False,
        },
        "volta_almoco": {
            "nome": "Volta do almoço",
            "icone": "💼",
            "inicio": "12:20",
            "fim": "14:00",
            "pergunta": "Como você está **voltando do almoço?**",
            "perguntar_motivo": False,
        },
        "saida_final": {
            "nome": "Saída do dia",
            "icone": "🏠",
            "inicio": "16:30",
            "fim": "23:59",
            "pergunta": "Como você está **saindo hoje?**",
            "perguntar_motivo": True,
        },
    },
    "emocoes": [
        {"nome": "Feliz", "emoji": "😄", "cor": "#23863a", "cor_texto": "#ffffff",
         "pontuacao": 2, "valencia": "positiva", "acolhimento": False},
        {"nome": "Animado", "emoji": "🤩", "cor": "#5c9e0f", "cor_texto": "#ffffff",
         "pontuacao": 2, "valencia": "positiva", "acolhimento": False},
        {"nome": "Neutro", "emoji": "😐", "cor": "#6b7785", "cor_texto": "#ffffff",
         "pontuacao": 0, "valencia": "neutra", "acolhimento": False},
        {"nome": "Cansado", "emoji": "😩", "cor": "#7a5fb0", "cor_texto": "#ffffff",
         "pontuacao": -1, "valencia": "negativa", "acolhimento": False},
        {"nome": "Preocupado", "emoji": "😟", "cor": "#c98a00", "cor_texto": "#1f1f1f",
         "pontuacao": -1, "valencia": "negativa", "acolhimento": False},
        {"nome": "Triste", "emoji": "😢", "cor": "#2f62c4", "cor_texto": "#ffffff",
         "pontuacao": -2, "valencia": "negativa", "acolhimento": True},
        {"nome": "Bravo", "emoji": "😠", "cor": "#d9480f", "cor_texto": "#ffffff",
         "pontuacao": -2, "valencia": "negativa", "acolhimento": True},
        {"nome": "Furioso", "emoji": "😡", "cor": "#b02525", "cor_texto": "#ffffff",
         "pontuacao": -3, "valencia": "negativa", "acolhimento": True},
    ],
    "motivos": {
        "chegada": {
            "negativo": {
                "titulo": "O que mais **pesou?**",
                "opcoes": [
                    "Sono/cansaço",
                    "Trânsito/deslocamento",
                    "Família/vida pessoal",
                    "Saúde/dor",
                    "Preocupação com o trabalho",
                    "Financeiro",
                    "Prefiro não dizer",
                ],
            },
            "positivo": {
                "titulo": "O que mais **contribuiu?**",
                "opcoes": [
                    "Descansei bem",
                    "Vida pessoal/família",
                    "Animado com o dia de trabalho",
                    "Clima/dia bonito",
                    "Prefiro não dizer",
                ],
            },
        },
        "saida_final": {
            "negativo": {
                "titulo": "O que mais **pesou?**",
                "opcoes": [
                    "Volume/ritmo de trabalho",
                    "Relação com colegas",
                    "Liderança/cobrança",
                    "Falta de material/equipamento",
                    "Cliente/pressão externa",
                    "Cansaço físico",
                    "Situação de risco/segurança",
                    "Prefiro não dizer",
                ],
            },
            "positivo": {
                "titulo": "O que mais **contribuiu?**",
                "opcoes": [
                    "Dia produtivo",
                    "Equipe/colegas",
                    "Reconhecimento",
                    "Resolvi um problema",
                    "Prefiro não dizer",
                ],
            },
        },
    },
    "pergunta_do_dia": {
        "ativa": True,
        "momentos": ["saida_final"],
        "mostrar_para_neutro": True,
        "opcoes": ["Sim", "Mais ou menos", "Não"],
        "perguntas": [
            {"texto": "Conseguiu fazer suas pausas hoje?", "invertida": False},
            {"texto": "Você se sentiu seguro(a) no trabalho hoje?", "invertida": False},
            {"texto": "Você se sentiu respeitado(a) hoje?", "invertida": False},
            {"texto": "Teve as informações e ferramentas de que precisava?", "invertida": False},
            {"texto": "Sentiu-se sobrecarregado(a) hoje?", "invertida": True},
        ],
    },
    "textos": {
        "titulo": "Termômetro Emocional — **CIPA Eurostec.**",
        "texto_inicial": (
            "A CIPA quer entender como nossa equipe está se sentindo para cuidar "
            "melhor de todos. É **ANÔNIMO**: não registramos nome, foto nem crachá. "
            "É **RÁPIDO**: leva menos de 5 segundos. Contamos com a sua participação!"
        ),
        "botao_iniciar": "Toque para começar",
        "rodape": "Hoje {x} pessoas já participaram neste ponto.",
        "rodape_um": "Hoje 1 pessoa já participou neste ponto.",
        "rodape_zero": "Seja a primeira pessoa a participar hoje neste ponto!",
        "titulo_escolher_momento": "Em qual **momento do dia** você está?",
        "trocar_momento": "trocar momento",
        "pular": "Pular",
        "titulo_pergunta_do_dia": "Pergunta do dia",
        "agradecimento": "**Obrigado!** Hoje {x} pessoas já registraram como estão.",
        "agradecimento_um": "**Obrigado!** Hoje 1 pessoa já registrou como está.",
        "acolhimento": (
            "Obrigado por compartilhar. Se quiser conversar, "
            "a CIPA e o RH estão à disposição."
        ),
        "erro_registro": "Não foi possível registrar agora. Por favor, tente de novo.",
    },
    "tempos": {
        "inatividade_s": 3,
        "agradecimento_s": 1.5,
        "acolhimento_s": 4,
        "bloqueio_novo_registro_s": 2,
        "trava_entre_telas_s": 0.5,
        "toque_longo_admin_s": 3,
        "admin_inatividade_s": 120,
    },
    "clima": {
        "ativo": True,
        "latitude": -29.168,
        "longitude": -51.179,
        "intervalo_min": 15,
        "validade_max_min": 60,
    },
    "sincronizacao": {
        "url": "",
        "token": "",
        "atraso_envio_s": 8,
        "tamanho_lote": 50,
        "timeout_s": 30,
    },
}

DIAS_VALIDOS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]

# ---------------------------------------------------------------------------
# Leitura, mescla e gravação
# ---------------------------------------------------------------------------

def mesclar(padrao, usuario):
    """Mescla recursiva: dicionários são combinados; listas e valores substituem."""
    if isinstance(padrao, dict) and isinstance(usuario, dict):
        resultado = copy.deepcopy(padrao)
        for chave, valor in usuario.items():
            resultado[chave] = mesclar(padrao.get(chave), valor) if chave in padrao else copy.deepcopy(valor)
        return resultado
    return copy.deepcopy(usuario)


class ErroConfig(Exception):
    def __init__(self, erros: list[str]):
        super().__init__("; ".join(erros))
        self.erros = erros


def caminho_config(base: Path | None = None) -> Path:
    return (base or pasta_base()) / "config" / "config.json"


def carregar_config(caminho: Path) -> dict:
    """Lê o config.json (criando-o a partir do padrão se não existir)."""
    if not caminho.exists():
        salvar_config(caminho, PADRAO, fazer_backup=False)
        return copy.deepcopy(PADRAO)
    with open(caminho, "r", encoding="utf-8-sig") as arquivo:
        try:
            usuario = json.load(arquivo)
        except json.JSONDecodeError as erro:
            raise ErroConfig([
                f"O arquivo {caminho.name} tem um erro de digitação na linha {erro.lineno}, "
                f"coluna {erro.colno}: {erro.msg}. Confira vírgulas e aspas."
            ]) from erro
    config = mesclar(PADRAO, usuario)
    erros = validar_config(config)
    if erros:
        raise ErroConfig(erros)
    return config


def salvar_config(caminho: Path, config: dict, fazer_backup: bool = True) -> None:
    """Grava o config.json de forma segura, guardando uma cópia do anterior."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if fazer_backup and caminho.exists():
        pasta_backup = caminho.parent / "backups"
        pasta_backup.mkdir(exist_ok=True)
        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
        (pasta_backup / f"config_{carimbo}.json").write_bytes(caminho.read_bytes())
    conteudo = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    fd, temporario = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=str(caminho.parent))
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as arquivo:
        arquivo.write(conteudo)
    os.replace(temporario, caminho)


# ---------------------------------------------------------------------------
# Validação
# ---------------------------------------------------------------------------

RE_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
RE_COR = re.compile(r"^#[0-9a-fA-F]{6}$")
RE_KIOSK = re.compile(r"^[A-Za-z0-9_-]{1,20}$")
RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def minutos(hhmm: str) -> int:
    hora, minuto = hhmm.split(":")
    return int(hora) * 60 + int(minuto)


def minutos_fim(hhmm: str) -> int:
    """Fim de janela: "23:59" significa "até o fim do dia"."""
    return 24 * 60 if hhmm == "23:59" else minutos(hhmm)


def validar_config(config: dict) -> list[str]:
    """Devolve a lista de problemas encontrados (vazia = tudo certo)."""
    erros: list[str] = []

    def texto(valor, nome, vazio_ok=False):
        if not isinstance(valor, str) or (not vazio_ok and not valor.strip()):
            erros.append(f"'{nome}' precisa ser um texto{'' if vazio_ok else ' preenchido'}.")
            return False
        return True

    def numero(valor, nome, minimo=None, maximo=None):
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            erros.append(f"'{nome}' precisa ser um número.")
            return False
        if (minimo is not None and valor < minimo) or (maximo is not None and valor > maximo):
            erros.append(f"'{nome}' precisa estar entre {minimo} e {maximo}.")
            return False
        return True

    def booleano(valor, nome):
        if not isinstance(valor, bool):
            erros.append(f"'{nome}' precisa ser true (sim) ou false (não).")

    def hora(valor, nome):
        if not isinstance(valor, str) or not RE_HORA.match(valor):
            erros.append(f"'{nome}' precisa estar no formato HH:MM (ex.: 07:30).")
            return False
        return True

    # Identificação
    if not isinstance(config.get("kiosk_id"), str) or not RE_KIOSK.match(config.get("kiosk_id", "")):
        erros.append("'kiosk_id' deve ter de 1 a 20 caracteres: letras, números, '-' ou '_' (ex.: Q01).")
    texto(config.get("kiosk_local"), "kiosk_local")
    pin = config.get("pin_admin")
    if not isinstance(pin, str) or not pin.isdigit() or not 4 <= len(pin) <= 8:
        erros.append("'pin_admin' deve ter de 4 a 8 números, entre aspas (ex.: \"2468\").")
    numero(config.get("porta"), "porta", 1024, 65535)
    for chave in ("logo", "logo_branco", "fundo_azul"):
        texto(config.get(chave), chave)

    # Expediente e feriados
    expediente = config.get("expediente", {})
    dias = expediente.get("dias", [])
    if not isinstance(dias, list) or any(d not in DIAS_VALIDOS for d in dias):
        erros.append("'expediente.dias' deve ser uma lista com: " + ", ".join(DIAS_VALIDOS) + ".")
    for i, periodo in enumerate(expediente.get("periodos", [])):
        hora(periodo.get("inicio"), f"expediente.periodos[{i + 1}].inicio")
        hora(periodo.get("fim"), f"expediente.periodos[{i + 1}].fim")
    feriados = config.get("feriados", [])
    if not isinstance(feriados, list) or any(not isinstance(f, str) or not RE_DATA.match(f) for f in feriados):
        erros.append("'feriados' deve ser uma lista de datas no formato AAAA-MM-DD.")

    # Momentos
    momentos = config.get("momentos", {})
    janelas = []
    for mid in MOMENTOS:
        m = momentos.get(mid)
        if not isinstance(m, dict):
            erros.append(f"Falta o momento '{mid}' em 'momentos'.")
            continue
        texto(m.get("nome"), f"momentos.{mid}.nome")
        texto(m.get("pergunta"), f"momentos.{mid}.pergunta")
        booleano(m.get("perguntar_motivo"), f"momentos.{mid}.perguntar_motivo")
        ok_ini = hora(m.get("inicio"), f"momentos.{mid}.inicio")
        ok_fim = hora(m.get("fim"), f"momentos.{mid}.fim")
        if ok_ini and ok_fim:
            ini, fim = minutos(m["inicio"]), minutos_fim(m["fim"])
            if ini >= fim:
                erros.append(f"No momento '{mid}', o início ({m['inicio']}) deve ser antes do fim ({m['fim']}).")
            else:
                janelas.append((ini, fim, mid))
    janelas.sort()
    for (i1, f1, m1), (i2, f2, m2) in zip(janelas, janelas[1:]):
        if i2 < f1:
            erros.append(f"As janelas de '{m1}' e '{m2}' estão sobrepostas.")

    # Emoções
    emocoes = config.get("emocoes", [])
    if not isinstance(emocoes, list) or len(emocoes) < 2:
        erros.append("'emocoes' precisa ter pelo menos 2 emoções.")
        emocoes = []
    nomes = set()
    for i, e in enumerate(emocoes):
        rotulo = f"emocoes[{i + 1}]"
        if not isinstance(e, dict):
            erros.append(f"{rotulo} está em formato inválido.")
            continue
        if texto(e.get("nome"), f"{rotulo}.nome"):
            if e["nome"] in nomes:
                erros.append(f"A emoção '{e['nome']}' aparece duas vezes.")
            nomes.add(e["nome"])
        texto(e.get("emoji"), f"{rotulo}.emoji")
        for chave in ("cor", "cor_texto"):
            if not isinstance(e.get(chave), str) or not RE_COR.match(e.get(chave, "")):
                erros.append(f"'{rotulo}.{chave}' deve ser uma cor no formato #RRGGBB.")
        numero(e.get("pontuacao"), f"{rotulo}.pontuacao", -10, 10)
        if e.get("valencia") not in VALENCIAS:
            erros.append(f"'{rotulo}.valencia' deve ser: positiva, neutra ou negativa.")
        booleano(e.get("acolhimento"), f"{rotulo}.acolhimento")

    # Motivos
    for mid, grupos in (config.get("motivos") or {}).items():
        if mid not in MOMENTOS:
            erros.append(f"'motivos.{mid}' não é um momento válido.")
            continue
        for tipo in ("negativo", "positivo"):
            grupo = (grupos or {}).get(tipo)
            if grupo is None:
                continue
            texto(grupo.get("titulo"), f"motivos.{mid}.{tipo}.titulo")
            opcoes = grupo.get("opcoes")
            if not isinstance(opcoes, list) or not opcoes or any(not isinstance(o, str) or not o.strip() for o in opcoes):
                erros.append(f"'motivos.{mid}.{tipo}.opcoes' deve ser uma lista de textos.")

    # Pergunta do dia
    pdd = config.get("pergunta_do_dia", {})
    booleano(pdd.get("ativa"), "pergunta_do_dia.ativa")
    booleano(pdd.get("mostrar_para_neutro"), "pergunta_do_dia.mostrar_para_neutro")
    if not isinstance(pdd.get("momentos"), list) or any(m not in MOMENTOS for m in pdd.get("momentos", [])):
        erros.append("'pergunta_do_dia.momentos' deve listar momentos válidos (ex.: [\"saida_final\"]).")
    opcoes = pdd.get("opcoes")
    if not isinstance(opcoes, list) or len(opcoes) < 2 or any(not isinstance(o, str) for o in opcoes):
        erros.append("'pergunta_do_dia.opcoes' deve ter pelo menos 2 opções.")
    perguntas = pdd.get("perguntas")
    if not isinstance(perguntas, list) or not perguntas:
        erros.append("'pergunta_do_dia.perguntas' deve ter pelo menos 1 pergunta.")
    else:
        for i, p in enumerate(perguntas):
            if not isinstance(p, dict) or not isinstance(p.get("texto"), str) or not p["texto"].strip():
                erros.append(f"'pergunta_do_dia.perguntas[{i + 1}].texto' precisa ser preenchido.")

    # Textos
    for chave, valor in (config.get("textos") or {}).items():
        texto(valor, f"textos.{chave}", vazio_ok=True)

    # Tempos
    tempos = config.get("tempos", {})
    for chave in PADRAO["tempos"]:
        numero(tempos.get(chave), f"tempos.{chave}", 0, 3600)

    # Clima
    clima = config.get("clima", {})
    booleano(clima.get("ativo"), "clima.ativo")
    numero(clima.get("latitude"), "clima.latitude", -90, 90)
    numero(clima.get("longitude"), "clima.longitude", -180, 180)
    numero(clima.get("intervalo_min"), "clima.intervalo_min", 1, 1440)
    numero(clima.get("validade_max_min"), "clima.validade_max_min", 1, 1440)

    # Sincronização
    sinc = config.get("sincronizacao", {})
    url = sinc.get("url", "")
    if texto(url, "sincronizacao.url", vazio_ok=True) and url and not url.startswith("https://"):
        erros.append("'sincronizacao.url' deve começar com https:// (copie a URL do App da Web).")
    texto(sinc.get("token", ""), "sincronizacao.token", vazio_ok=True)
    if url and not sinc.get("token"):
        erros.append("Com a URL da planilha preenchida, o 'sincronizacao.token' também precisa ser preenchido.")
    numero(sinc.get("atraso_envio_s"), "sincronizacao.atraso_envio_s", 0, 3600)
    numero(sinc.get("tamanho_lote"), "sincronizacao.tamanho_lote", 1, 500)
    numero(sinc.get("timeout_s"), "sincronizacao.timeout_s", 1, 300)

    return erros


def emocao_por_nome(config: dict, nome: str) -> dict | None:
    for emocao in config["emocoes"]:
        if emocao["nome"] == nome:
            return emocao
    return None


def opcoes_motivo(config: dict, momento: str, valencia: str) -> dict | None:
    """Lista de motivos para um momento e valência (ou None se não houver)."""
    if not config["momentos"][momento].get("perguntar_motivo"):
        return None
    tipo = {"positiva": "positivo", "negativa": "negativo"}.get(valencia)
    if not tipo:
        return None
    grupo = (config.get("motivos") or {}).get(momento, {}).get(tipo)
    if not grupo or not grupo.get("opcoes"):
        return None
    return grupo
