"""Gera dados FICTÍCIOS para testar o relatório do Termômetro Emocional.

Simula 2 quinzenas (4 semanas corridas), 2 pontos de coleta (Q01 e Q02) e
cerca de 150 pessoas, nos 4 momentos do dia, gravando os CSVs exatamente no
formato dos quiosques (um arquivo por quiosque por dia).

Os quiosques Q01 e Q02 têm tela de setor: na chegada e na saída do dia,
~80% informam o setor (setor_perguntado = 'sim').

Uso:
    python ferramentas/gerar_dados_ficticios.py [--saida dados_ficticios]
        [--fim AAAA-MM-DD] [--semente 42] [--com-planilha]

--com-planilha também grava planilha_exportada.csv imitando o CSV baixado
da Planilha Google (separador ",", decimais com ponto, data 20/11/2026,
sem BOM), com parte das MESMAS respostas — algumas com o motivo
preenchido — para testar a deduplicação do relatório.
"""
from __future__ import annotations

import argparse
import csv
import math
import random
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from quiosque.formato import COLUNAS, DIAS_SEMANA, VERSAO_APP, escrever_csv, nome_arquivo_dia  # noqa: E402

EMOCOES = [
    ("Feliz", 2, "positiva"),
    ("Animado", 2, "positiva"),
    ("Neutro", 0, "neutra"),
    ("Cansado", -1, "negativa"),
    ("Preocupado", -1, "negativa"),
    ("Triste", -2, "negativa"),
    ("Bravo", -2, "negativa"),
    ("Furioso", -3, "negativa"),
]
PONTOS = {nome: p for nome, p, _ in EMOCOES}
VALENCIA = {nome: v for nome, _, v in EMOCOES}

MOTIVOS = {
    ("chegada", "negativa"): [
        "Sono/cansaço", "Trânsito/deslocamento", "Família/vida pessoal", "Saúde/dor",
        "Preocupação com o trabalho", "Financeiro", "Prefiro não dizer",
    ],
    ("chegada", "positiva"): [
        "Descansei bem", "Vida pessoal/família", "Animado com o dia de trabalho",
        "Clima/dia bonito", "Prefiro não dizer",
    ],
    ("saida_final", "negativa"): [
        "Volume/ritmo de trabalho", "Relação com colegas", "Liderança/cobrança",
        "Falta de material/equipamento", "Cliente/pressão externa", "Cansaço físico",
        "Situação de risco/segurança", "Prefiro não dizer",
    ],
    ("saida_final", "positiva"): [
        "Dia produtivo", "Equipe/colegas", "Reconhecimento", "Resolvi um problema", "Prefiro não dizer",
    ],
}
PERGUNTAS = [
    ("Conseguiu fazer suas pausas hoje?", False, 0.62),
    ("Você se sentiu seguro(a) no trabalho hoje?", False, 0.82),
    ("Você se sentiu respeitado(a) hoje?", False, 0.78),
    ("Teve as informações e ferramentas de que precisava?", False, 0.66),
    ("Sentiu-se sobrecarregado(a) hoje?", True, 0.60),  # 0.60 = chance de "Não" (favorável)
]
QUIOSQUES = [
    ("Q01", "Pavilhão 1", 80, 0.00),
    ("Q02", "Pavilhão 6", 70, -0.20),
]
MOMENTOS = ["chegada", "saida_almoco", "volta_almoco", "saida_final"]
PARTICIPACAO_BASE = {"chegada": 0.80, "saida_almoco": 0.42, "volta_almoco": 0.36, "saida_final": 0.70}
ADESAO_SEMANA = [1.00, 0.94, 0.88, 0.82]  # adesão caindo ao longo das semanas
HORARIO = {  # (média em minutos, desvio)
    "chegada": (7 * 60 + 20, 7),
    "saida_almoco": (11 * 60 + 55, 4),
    "volta_almoco": (12 * 60 + 56, 4),
    "saida_final": (17 * 60 + 10, 6),
}
JANELAS = {
    "chegada": (5 * 60, 10 * 60),
    "saida_almoco": (11 * 60 + 30, 12 * 60 + 20),
    "volta_almoco": (12 * 60 + 20, 14 * 60),
    "saida_final": (16 * 60 + 30, 24 * 60),
}
EFEITO_DIA = {0: -0.35, 1: -0.10, 2: 0.0, 3: 0.10, 4: 0.40, 5: 0.20, 6: 0.20}
EFEITO_MOMENTO = {"chegada": 0.0, "saida_almoco": 0.25, "volta_almoco": 0.05, "saida_final": -0.25}
FERIADOS_FIXOS = {(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25)}
# Telas de setor: a lista de cada quiosque (vazia = tela desligada, como no quiosque/config.py).
SETORES = {
    "Q01": ["Administrativo", "Assistência técnica", "Comercial"],
    "Q02": ["Produção", "Qualidade", "Segurança"],
}
MOMENTOS_COM_SETOR = ("chegada", "saida_final")
PULA_SETOR = 0.20  # ~80% informam o setor
EFEITO_SETOR = {"Comercial": 0.15, "Administrativo": 0.05, "Assistência técnica": -0.05,
                "Produção": -0.10, "Qualidade": 0.0, "Segurança": -0.20}
SETORES_RAROS_FDS = ("Segurança", "Qualidade")
SEMANAS_FDS_RAROS = (1, 3)  # índices das semanas em que esses setores quase não aparecem nos fins de semana


def condicao_do_codigo(codigo: int) -> str:
    """Mesma regra do quiosque (quiosque/clima.py)."""
    if codigo in (0, 1):
        return "sol"
    if codigo in (2, 3, 45, 48):
        return "nublado"
    if 51 <= codigo <= 67 or 80 <= codigo <= 82 or 95 <= codigo <= 99:
        return "chuva"
    return "outro"


class Simulador:
    def __init__(self, semente: int):
        self.rng = random.Random(semente)
        # RNG separado para os setores: não muda a sequência dos demais sorteios.
        self.rng_setor = random.Random(semente + 1000)

    # ----------------------------------------------------------------- clima
    def clima_do_dia(self, d: date) -> dict:
        rng = self.rng
        tipo = rng.choices(["sol", "nublado", "chuva"], [0.42, 0.30, 0.28])[0]
        tmin = rng.gauss(13.5, 2.6) - (1.5 if tipo == "chuva" else 0)
        amplitude = max(4.0, rng.gauss(10.5, 2.5) - (4 if tipo == "chuva" else 0))
        if rng.random() < 0.08:  # dia quente fora do comum
            tmin, amplitude = tmin + 4, amplitude + 4
        return {"tipo": tipo, "tmin": tmin, "tmax": tmin + amplitude,
                "offline": {}, "neblina": tipo == "nublado" and rng.random() < 0.5}

    def clima_na_hora(self, dia: dict, minutos: int) -> dict:
        rng = self.rng
        h = minutos / 60
        if h <= 6:
            temp = dia["tmin"]
        elif h <= 15:
            temp = dia["tmin"] + (dia["tmax"] - dia["tmin"]) * math.sin((h - 6) / 9 * math.pi / 2)
        else:
            temp = dia["tmax"] - (dia["tmax"] - dia["tmin"]) * 0.55 * min(1, (h - 15) / 9)
        temp += rng.gauss(0, 0.4)
        precip = 0.0
        if dia["tipo"] == "sol":
            codigo = rng.choice([0, 0, 1])
        elif dia["tipo"] == "nublado":
            codigo = 45 if dia["neblina"] and h < 9 else rng.choice([2, 3, 3])
        else:
            if rng.random() < 0.7:
                codigo = rng.choice([61, 63, 80, 53, 61])
                precip = round(rng.uniform(0.1, 3.5), 1)
            else:
                codigo = 3
        sensacao = temp - rng.uniform(0.5, 2.5) if temp < 20 else temp + rng.uniform(-0.5, 1.5)
        return {
            "temperatura_c": round(temp, 1),
            "sensacao_termica_c": round(sensacao, 1),
            "precipitacao_mm": precip,
            "codigo_tempo": codigo,
            "condicao": condicao_do_codigo(codigo),
            "dia_ou_noite": "dia" if 6 <= h < 20 else "noite",
        }

    # ---------------------------------------------------------------- humor
    def escolher_emocao(self, latente: float, momento: str, dia_semana: int) -> str:
        pesos = []
        for nome, pontos, _ in EMOCOES:
            peso = math.exp(-((pontos - latente) ** 2) / (2 * 0.9 ** 2))
            fator = {"Feliz": 1.2, "Neutro": 1.3, "Furioso": 0.35, "Bravo": 0.6, "Triste": 0.7}.get(nome, 1.0)
            if nome == "Animado":
                fator = 0.7 if momento == "chegada" else 1.0
                if dia_semana == 4 and momento == "saida_final":
                    fator = 1.6
            if nome == "Cansado":
                fator = {"saida_final": 1.8, "volta_almoco": 1.3}.get(momento, 1.0)
                if momento == "chegada" and dia_semana == 0:
                    fator = 1.5
            if nome == "Preocupado" and momento == "chegada":
                fator = 1.3
            pesos.append(peso * fator)
        return self.rng.choices([e[0] for e in EMOCOES], pesos)[0]

    def escolher_motivo(self, momento, valencia, emocao, dia_semana, clima, kiosk) -> str:
        opcoes = MOTIVOS[(momento, valencia)]
        pesos = {o: 1.0 for o in opcoes}
        chuva = clima.get("condicao") == "chuva"
        if (momento, valencia) == ("chegada", "negativa"):
            pesos.update({"Sono/cansaço": 3 + (2 if emocao == "Cansado" else 0) + (1 if dia_semana == 0 else 0),
                          "Trânsito/deslocamento": 2 + (2 if chuva else 0),
                          "Família/vida pessoal": 1.5 + (1 if emocao == "Triste" else 0),
                          "Preocupação com o trabalho": 1.5 + (1.5 if emocao == "Preocupado" else 0),
                          "Financeiro": 1 + (0.8 if emocao == "Preocupado" else 0),
                          "Prefiro não dizer": 1 + (0.8 if emocao in ("Bravo", "Furioso") else 0)})
        elif (momento, valencia) == ("chegada", "positiva"):
            pesos.update({"Descansei bem": 3, "Vida pessoal/família": 2,
                          "Animado com o dia de trabalho": 1.5 + (1.5 if emocao == "Animado" else 0),
                          "Clima/dia bonito": 1 + (2.5 if clima.get("condicao") == "sol" else 0),
                          "Prefiro não dizer": 0.7})
        elif (momento, valencia) == ("saida_final", "negativa"):
            pesos.update({"Volume/ritmo de trabalho": 3 + (1 if dia_semana in (1, 2, 3) else 0),
                          "Relação com colegas": 1 + (1 if emocao in ("Bravo", "Furioso") else 0),
                          "Liderança/cobrança": 1.3 + (1.2 if emocao in ("Bravo", "Furioso") else 0),
                          "Falta de material/equipamento": 1 + (0.8 if kiosk == "Q02" else 0),
                          "Cliente/pressão externa": 1.2,
                          "Cansaço físico": 2 + (2.5 if emocao == "Cansado" else 0) + (1 if kiosk == "Q02" else 0),
                          "Situação de risco/segurança": 0.4 + (0.6 if kiosk == "Q02" else 0),
                          "Prefiro não dizer": 1})
        else:
            pesos.update({"Dia produtivo": 3, "Equipe/colegas": 2 + (1 if dia_semana == 4 else 0),
                          "Reconhecimento": 0.8, "Resolvi um problema": 1.5, "Prefiro não dizer": 0.5})
        return self.rng.choices(opcoes, [pesos[o] for o in opcoes])[0]

    def responder_pergunta(self, d: date, latente: float):
        texto, invertida, base = PERGUNTAS[d.toordinal() % len(PERGUNTAS)]
        logit = math.log(base / (1 - base)) + 0.6 * (latente - 0.3)
        p_fav = 1 / (1 + math.exp(-logit))
        p_meio = (1 - p_fav) * 0.45
        sorteio = self.rng.random()
        favoravel, desfavoravel = ("Não", "Sim") if invertida else ("Sim", "Não")
        if sorteio < p_fav:
            return texto, favoravel
        if sorteio < p_fav + p_meio:
            return texto, "Mais ou menos"
        return texto, desfavoravel

    # --------------------------------------------------------------- setor
    def setor_da_resposta(self, kiosk, momento, d, semana, setor_pessoa) -> tuple[str, str]:
        """Devolve (setor_perguntado, setor). A tela só aparece em chegada e saída do dia."""
        if kiosk not in SETORES or momento not in MOMENTOS_COM_SETOR:
            return "não", ""
        if self.rng_setor.random() < PULA_SETOR:
            return "sim", ""
        if setor_pessoa is not None:  # em dia útil, cada pessoa tem o próprio setor
            return "sim", setor_pessoa
        setores = SETORES[kiosk]  # fim de semana: quem aparece é sorteado
        pesos = [0.12 if eh_folga(d) and nome in SETORES_RAROS_FDS and semana in SEMANAS_FDS_RAROS
                 else 1.0 for nome in setores]
        return "sim", self.rng_setor.choices(setores, pesos)[0]

    # ------------------------------------------------------------- horários
    def horario(self, momento: str, d: date) -> tuple[int, bool]:
        """Devolve (minutos, momento_automatico)."""
        rng = self.rng
        sorteio = rng.random()
        if momento == "chegada" and sorteio < 0.04:  # chegou atrasado (fora da janela)
            return int(min(11 * 60 + 25, max(10 * 60 + 2, rng.gauss(10 * 60 + 40, 18)))), False
        if momento == "saida_final" and sorteio < 0.05:  # saiu mais cedo
            return int(min(16 * 60 + 28, max(14 * 60 + 5, rng.gauss(15 * 60 + 45, 20)))), False
        media, desvio = HORARIO[momento]
        inicio, fim = JANELAS[momento]
        minutos = int(min(fim - 1, max(inicio, rng.gauss(media, desvio))))
        automatico = rng.random() >= 0.02  # 2% tocam em "trocar momento"
        return minutos, automatico

    # ------------------------------------------------------------- resposta
    def montar(self, kiosk, local, d, momento, minutos, automatico, emocao, clima, motivo="",
               pergunta="", resposta="", setor="", setor_perguntado="não") -> dict:
        segundos = self.rng.randint(0, 59)
        hora = f"{minutos // 60:02d}:{minutos % 60:02d}:{segundos:02d}"
        linha = {
            "response_id": str(uuid.UUID(int=self.rng.getrandbits(128), version=4)),
            "kiosk_id": kiosk,
            "kiosk_local": local,
            "timestamp": f"{d.isoformat()}T{hora}-03:00",
            "data": d.isoformat(),
            "dia_semana": DIAS_SEMANA[d.weekday()],
            "hora": hora,
            "momento": momento,
            "momento_automatico": "sim" if automatico else "não",
            "emocao": emocao,
            "valencia": VALENCIA[emocao],
            "pontuacao": PONTOS[emocao],
            "motivo": motivo,
            "pergunta_do_dia": pergunta,
            "resposta_pergunta_do_dia": resposta,
            "setor": setor,
            "setor_perguntado": setor_perguntado,
            "versao_app": VERSAO_APP,
        }
        for chave in ("temperatura_c", "sensacao_termica_c", "precipitacao_mm", "codigo_tempo",
                      "condicao", "dia_ou_noite"):
            linha[chave] = clima.get(chave, "")
        return linha


def eh_folga(d: date) -> bool:
    return d.weekday() >= 5 or (d.month, d.day) in FERIADOS_FIXOS


def gerar(fim: date, semente: int = 42) -> list[dict]:
    sim = Simulador(semente)
    rng = sim.rng
    inicio = fim - timedelta(days=27)
    pessoas = {}
    for kiosk, _, populacao, _ in QUIOSQUES:
        pessoas[kiosk] = [
            {"base": rng.gauss(0.4, 0.5), "engajamento": rng.uniform(0.55, 1.15)}
            for _ in range(populacao)
        ]
        for pessoa in pessoas[kiosk]:  # setor fixo de cada pessoa (sorteio à parte)
            pessoa["setor"] = sim.rng_setor.choice(SETORES[kiosk]) if kiosk in SETORES else None
    linhas = []
    d = inicio
    while d <= fim:
        clima_dia = sim.clima_do_dia(d)
        semana = min(3, (d - inicio).days // 7)
        for kiosk, local, _, efeito_kiosk in QUIOSQUES:
            offline_manha = rng.random() < 0.06  # quiosque sem internet pela manhã
            ruido_dia = rng.gauss(0, 0.15)

            def clima_para(minutos):
                if (offline_manha and minutos < 12 * 60) or rng.random() < 0.02:
                    return {}
                return sim.clima_na_hora(clima_dia, minutos)

            if eh_folga(d):  # fim de semana/feriado: poucas respostas, momento escolhido à mão
                for _ in range(rng.choice([0, 1, 1, 2, 3, 4] if d.weekday() == 5 else [0, 0, 1, 2])):
                    momento = rng.choice(MOMENTOS)
                    minutos = int(min(23 * 60, max(6 * 60, rng.gauss(HORARIO[momento][0], 30))))
                    clima = clima_para(minutos)
                    latente = rng.gauss(0.5, 0.9)
                    emocao = sim.escolher_emocao(latente, momento, d.weekday())
                    perguntado, setor = sim.setor_da_resposta(kiosk, momento, d, semana, None)
                    linhas.append(sim.montar(kiosk, local, d, momento, minutos, False, emocao, clima,
                                             setor=setor, setor_perguntado=perguntado))
                continue

            for pessoa in pessoas[kiosk]:
                if rng.random() > 0.88:  # ausente (folga, férias, outro turno)
                    continue
                humor_pessoa_dia = pessoa["base"] + rng.gauss(0, 0.35)
                for momento in MOMENTOS:
                    p = PARTICIPACAO_BASE[momento] * ADESAO_SEMANA[semana] * pessoa["engajamento"]
                    if rng.random() > min(0.97, p):
                        continue
                    minutos, automatico = sim.horario(momento, d)
                    clima = clima_para(minutos)
                    latente = (humor_pessoa_dia + EFEITO_DIA[d.weekday()] + EFEITO_MOMENTO[momento]
                               + efeito_kiosk + EFEITO_SETOR.get(pessoa["setor"], 0.0)
                               + ruido_dia + rng.gauss(0, 0.8))
                    if momento == "saida_final" and d.weekday() == 4:
                        latente += 0.5
                    condicao = clima.get("condicao")
                    latente += {"chuva": -0.30, "nublado": -0.05, "sol": 0.15}.get(condicao, 0)
                    if clima and clima["temperatura_c"] < 12:
                        latente -= 0.15
                    emocao = sim.escolher_emocao(latente, momento, d.weekday())
                    valencia = VALENCIA[emocao]
                    motivo = pergunta = resposta = ""
                    if momento in ("chegada", "saida_final") and valencia != "neutra" and rng.random() < 0.72:
                        motivo = sim.escolher_motivo(momento, valencia, emocao, d.weekday(), clima, kiosk)
                    if momento == "saida_final" and rng.random() < 0.78:
                        pergunta, resposta = sim.responder_pergunta(d, latente)
                    perguntado, setor = sim.setor_da_resposta(kiosk, momento, d, semana, pessoa["setor"])
                    linhas.append(sim.montar(kiosk, local, d, momento, minutos, automatico, emocao,
                                             clima, motivo, pergunta, resposta,
                                             setor=setor, setor_perguntado=perguntado))
        d += timedelta(days=1)
    linhas.sort(key=lambda l: (l["kiosk_id"], l["data"], l["hora"]))
    return linhas


def gravar_quiosques(linhas: list[dict], saida: Path) -> int:
    grupos: dict[tuple[str, str], list[dict]] = {}
    for linha in linhas:
        grupos.setdefault((linha["kiosk_id"], linha["data"]), []).append(linha)
    for (kiosk, data), grupo in grupos.items():
        escrever_csv(saida / kiosk / nome_arquivo_dia(kiosk, data), grupo)
    return len(grupos)


def gravar_planilha(linhas: list[dict], saida: Path, semente: int) -> int:
    """Imita o CSV baixado da Planilha Google (com parte das mesmas respostas)."""
    rng = random.Random(semente + 1)
    amostra = [dict(l) for l in linhas if rng.random() < 0.6]
    completadas = 0
    for linha in amostra:
        contexto = (linha["momento"], linha["valencia"])
        if completadas < 25 and not linha["motivo"] and contexto in MOTIVOS:
            linha["motivo"] = rng.choice(MOTIVOS[contexto])
            completadas += 1
    caminho = saida / "planilha_exportada.csv"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo, delimiter=",", lineterminator="\r\n")
        escritor.writerow(COLUNAS)
        for linha in amostra:
            valores = []
            for coluna in COLUNAS:
                valor = linha.get(coluna, "")
                if coluna == "data":
                    a, m, dd = valor.split("-")
                    valor = f"{dd}/{m}/{a}"
                valores.append("" if valor is None else str(valor))
            escritor.writerow(valores)
    return len(amostra)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Gera dados fictícios do Termômetro Emocional.")
    parser.add_argument("--saida", default="dados_ficticios", help="pasta de saída (padrão: dados_ficticios)")
    parser.add_argument("--fim", default=None, help="último dia, AAAA-MM-DD (padrão: hoje)")
    parser.add_argument("--semente", type=int, default=42, help="semente aleatória (padrão: 42)")
    parser.add_argument("--com-planilha", action="store_true",
                        help="grava também planilha_exportada.csv (teste de deduplicação)")
    args = parser.parse_args(argv)

    fim = date.fromisoformat(args.fim) if args.fim else date.today()
    saida = Path(args.saida)
    if not saida.is_absolute():
        saida = Path.cwd() / saida
    linhas = gerar(fim, args.semente)
    arquivos = gravar_quiosques(linhas, saida)
    print(f"Dados fictícios gerados: {len(linhas)} respostas em {arquivos} arquivos.")
    print(f"Período: {(fim - timedelta(days=27)).strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}")
    for kiosk, local, _, _ in QUIOSQUES:
        n = sum(1 for l in linhas if l["kiosk_id"] == kiosk)
        print(f"  {kiosk} ({local}): {n} respostas")
    if args.com_planilha:
        n = gravar_planilha(linhas, saida, args.semente)
        print(f"  planilha_exportada.csv: {n} respostas repetidas (teste de deduplicação)")
    print(f"Pasta: {saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
