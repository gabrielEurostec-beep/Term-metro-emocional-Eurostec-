"""Resumo em texto simples com os principais achados do período."""
from __future__ import annotations

import math

from quiosque.formato import MOMENTOS
from relatorio.analise import INSUFICIENTE, Resultado
from relatorio.formatacao import data_br, decimal, inteiro, nome_dia, nome_momento, percentual

DIAS_UTEIS = ["segunda", "terça", "quarta", "quinta", "sexta"]
NOME_DIA_LONGO = {
    "segunda": "segunda-feira", "terça": "terça-feira", "quarta": "quarta-feira",
    "quinta": "quinta-feira", "sexta": "sexta-feira", "sábado": "sábado", "domingo": "domingo",
}
DESCRICAO_VARIACAO = {
    "Manhã": "de manhã (da chegada à saída para o almoço)",
    "Almoço": "no almoço (da saída à volta do almoço)",
    "Tarde": "à tarde (da volta do almoço à saída do dia)",
}


def _valido(x) -> bool:
    return x is not None and x != INSUFICIENTE and not (isinstance(x, float) and math.isnan(x))


def _indice(x) -> str:
    return decimal(x, 2, sinal=True)


def _minusculo(texto: str) -> str:
    return texto[:1].lower() + texto[1:]


def gerar_resumo(r: Resultado) -> list[str]:
    """Lista de frases curtas, em português simples."""
    minimo = r.minimo
    k = r.kpis
    cfg = r.config
    frases: list[str] = []

    # 1. Período e volume
    frases.append(
        f"Período analisado: {data_br(r.inicio)} a {data_br(r.fim)}. Foram {inteiro(k['total'])} "
        f"respostas em {k['pontos']} ponto(s) de coleta, com coleta em {k['dias_uteis_coleta']} dia(s) útil(eis)."
    )

    # 2. Participação
    part = r.brutos["participacao"]
    if k["dias_uteis_coleta"] and _valido(part["taxa_geral"]) and part["n_util"] >= minimo:
        por_momento = {m: v for m, v in part["por_momento"].items() if v["n"] >= minimo}
        frase = (f"Participação média: {percentual(part['taxa_geral'])} do público esperado "
                 f"({cfg.get('publico_esperado_por_quiosque', 40)} pessoas por ponto de coleta, em cada momento).")
        if len(por_momento) >= 2:
            maior = max(por_momento, key=lambda m: por_momento[m]["taxa"])
            menor = min(por_momento, key=lambda m: por_momento[m]["taxa"])
            frase += (f" A maior adesão foi na {_minusculo(nome_momento(maior))} "
                      f"({percentual(por_momento[maior]['taxa'])}) e a menor na "
                      f"{_minusculo(nome_momento(menor))} ({percentual(por_momento[menor]['taxa'])}).")
        frases.append(frase)

        semanal = [(rot, v) for rot, v in part["semanal"] if v is not None]
        if len(semanal) >= 2:
            (rot_ini, v_ini), (rot_fim, v_fim) = semanal[0], semanal[-1]
            diferenca = v_fim - v_ini
            if diferenca <= -0.05:
                frases.append(
                    f"Atenção: a adesão está caindo. Passou de {percentual(v_ini)} na semana de {rot_ini} "
                    f"para {percentual(v_fim)} na semana de {rot_fim}. Vale reforçar a divulgação."
                )
            elif diferenca >= 0.05:
                frases.append(
                    f"A adesão está subindo: passou de {percentual(v_ini)} na semana de {rot_ini} "
                    f"para {percentual(v_fim)} na semana de {rot_fim}."
                )
            else:
                frases.append(
                    f"A adesão ficou estável ao longo das semanas (entre {percentual(min(v_ini, v_fim))} "
                    f"e {percentual(max(v_ini, v_fim))})."
                )

    # 3. Humor geral
    if k["total"] >= minimo:
        frase = f"Índice de humor geral: {_indice(k['indice_geral'])} (escala de −3 a +2)."
        partes = []
        if isinstance(k["pct_positivas"], float):
            partes.append(f"{percentual(k['pct_positivas'])} das respostas foram emoções positivas")
        if isinstance(k["pct_negativas"], float):
            partes.append(f"{percentual(k['pct_negativas'])} negativas")
        if partes:
            frase += " " + " e ".join(partes) + "."
        frases.append(frase)

    # 4. Melhor e pior momento
    humor = {m: v for m, v in r.brutos["humor_momento"].items() if m in MOMENTOS and v["n"] >= minimo}
    if len(humor) >= 2:
        melhor = max(humor, key=lambda m: humor[m]["media"])
        pior = min(humor, key=lambda m: humor[m]["media"])
        frases.append(
            f"O humor é melhor na {_minusculo(nome_momento(melhor))} ({_indice(humor[melhor]['media'])}) "
            f"e pior na {_minusculo(nome_momento(pior))} ({_indice(humor[pior]['media'])})."
        )

    # 5. Maior queda ao longo do dia
    variacoes = {n: v for n, v in r.brutos["variacoes"].items() if n in DESCRICAO_VARIACAO and v["dias"] > 0}
    if variacoes:
        pior_var = min(variacoes, key=lambda n: variacoes[n]["media"])
        valor = variacoes[pior_var]["media"]
        if valor < -0.10:
            frases.append(
                f"A maior queda de humor acontece {DESCRICAO_VARIACAO[pior_var]}: {_indice(valor)} em média "
                f"(base: {variacoes[pior_var]['dias']} dia(s) por ponto de coleta)."
            )
        else:
            frases.append("Não houve queda relevante de humor entre os momentos do dia.")
    dia_inteiro = r.brutos["variacoes"].get("Dia inteiro", {})
    if dia_inteiro.get("dias"):
        v = dia_inteiro["media"]
        if v < -0.10:
            frases.append(f"Em média, as pessoas saem pior do que chegaram ({_indice(v)} entre a chegada e a saída do dia).")
        elif v > 0.10:
            frases.append(f"Em média, as pessoas saem melhor do que chegaram ({_indice(v)} entre a chegada e a saída do dia).")
        else:
            frases.append(f"Em média, as pessoas saem com humor parecido ao da chegada ({_indice(v)}).")

    # 6. Dia da semana
    tabela = r.tabelas["humor_dia_momento"].dados
    por_dia = {}
    for _, linha in tabela.iterrows():
        dia = next((d for d in DIAS_UTEIS if nome_dia(d) == linha["Dia da semana"]), None)
        if dia and _valido(linha["Todos os momentos"]):
            por_dia[dia] = float(linha["Todos os momentos"])
    if len(por_dia) >= 2:
        melhor = max(por_dia, key=por_dia.get)
        pior = min(por_dia, key=por_dia.get)
        frases.append(
            f"Entre os dias úteis, {NOME_DIA_LONGO[pior]} tem o pior humor ({_indice(por_dia[pior])}) "
            f"e {NOME_DIA_LONGO[melhor]} o melhor ({_indice(por_dia[melhor])})."
        )

    # 7. Clima
    clima = r.graficos["clima_condicao"]
    valores = dict(zip(clima["rotulos"], clima["valores"]))
    if valores.get("Sol") is not None and valores.get("Chuva") is not None:
        diferenca = valores["Chuva"] - valores["Sol"]
        if diferenca <= -0.10:
            frases.append(
                f"O tempo parece influenciar: com chuva, o índice médio foi {_indice(valores['Chuva'])}, "
                f"contra {_indice(valores['Sol'])} com sol."
            )
        else:
            frases.append(
                f"Não se viu diferença relevante de humor entre dias de chuva ({_indice(valores['Chuva'])}) "
                f"e de sol ({_indice(valores['Sol'])})."
            )

    # 8. Motivos
    for momento, rotulo in (("chegada", "Na chegada"), ("saida_final", "Na saída do dia")):
        item = r.brutos["motivos"].get((momento, "negativa"))
        if item and item["valido"] and item["itens"]:
            principal = item["itens"][0]
            if principal["motivo"] == "Prefiro não dizer" and len(item["itens"]) > 1:
                principal = item["itens"][1]
            frases.append(
                f"{rotulo}, quem estava mal apontou principalmente “{principal['motivo']}” "
                f"({percentual(principal['pct'])} dos motivos informados)."
            )

    # 9. Pergunta do dia
    # Só cita percentuais que representam pelo menos `minimo` pessoas.
    perguntas = [p for p in r.graficos["pergunta_dia"] if p["valida"] and p["favoravel"][1] is not None]
    if perguntas:
        pior = min(perguntas, key=lambda p: p["favoravel"][1])
        frases.append(
            f"Pergunta do dia com resultado mais baixo: “{pior['pergunta']}” — "
            f"{percentual(pior['favoravel'][1])} de respostas favoráveis."
        )
        for p in perguntas:
            if p["invertida"] and p is not pior and p["desfavoravel"][1] is not None:
                frases.append(
                    f"“{p['pergunta']}”: {percentual(p['desfavoravel'][1])} responderam “Sim”."
                )

    frases.append(
        f"Para proteger o anonimato, qualquer recorte com menos de {minimo} respostas aparece como "
        f"“dados insuficientes”, e categorias com 1 a {minimo - 1} respostas aparecem como “<{minimo}”, sem percentual."
    )
    return frases
