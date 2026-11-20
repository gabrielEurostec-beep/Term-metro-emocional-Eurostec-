"""Gera o relatório quinzenal do Termômetro Emocional.

Uso:
    python -m relatorio [--entrada PASTA] [--saida PASTA]
                        [--inicio AAAA-MM-DD] [--fim AAAA-MM-DD] [--nao-abrir]

Sem argumentos, usa as pastas de config/relatorio.json
(padrão: entrada_relatorio/ e relatorios/).
"""
from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from datetime import date
from pathlib import Path


def _preparar_console() -> None:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def _garantir_caminho_projeto() -> None:
    raiz = Path(__file__).resolve().parent.parent
    if str(raiz) not in sys.path:
        sys.path.insert(0, str(raiz))


def _abrir(caminho: Path) -> None:
    try:
        if os.name == "nt":
            os.startfile(str(caminho))  # type: ignore[attr-defined]
        else:
            webbrowser.open(caminho.resolve().as_uri())
    except Exception:  # noqa: BLE001 - abrir o navegador é só uma conveniência
        print("  (Não consegui abrir o navegador automaticamente. Abra o arquivo acima com duplo clique.)")


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m relatorio",
        description="Gera o relatório do Termômetro Emocional (HTML + Excel).",
    )
    parser.add_argument("--entrada", help="pasta com os CSVs (padrão: pasta_entrada de config/relatorio.json)")
    parser.add_argument("--saida", help="pasta onde salvar o relatório (padrão: pasta_saida)")
    parser.add_argument("--inicio", help="primeiro dia do período, AAAA-MM-DD (padrão: todos os dados)")
    parser.add_argument("--fim", help="último dia do período, AAAA-MM-DD (padrão: todos os dados)")
    parser.add_argument("--nao-abrir", action="store_true", help="não abrir o relatório no navegador ao terminar")
    parser.add_argument("--config", help="caminho de outro arquivo de configuração (opcional)")
    return parser


def main(argv: list[str] | None = None) -> int:
    _preparar_console()
    _garantir_caminho_projeto()
    from relatorio.configuracao import carregar_config, raiz_projeto, resolver_pasta

    args = criar_parser().parse_args(argv)
    raiz = raiz_projeto()

    print("=" * 64)
    print(" Termômetro Emocional — CIPA Eurostec | Relatório")
    print("=" * 64)

    try:
        config = carregar_config(raiz, Path(args.config) if args.config else None)
    except ValueError as erro:
        print(f"\nERRO: {erro}")
        return 2

    entrada = resolver_pasta(args.entrada or config["pasta_entrada"], raiz)
    saida = resolver_pasta(args.saida or config["pasta_saida"], raiz)

    try:
        from relatorio.leitura import ler_data_argumento
        inicio = ler_data_argumento(args.inicio)
        fim = ler_data_argumento(args.fim)
    except ValueError as erro:
        print(f"\nERRO: {erro}")
        return 2
    except ImportError as erro:
        print(f"\nERRO: faltam bibliotecas do relatório ({erro}). Rode o instalar.bat (opção do PC da CIPA).")
        return 3

    if not entrada.exists():
        entrada.mkdir(parents=True, exist_ok=True)
        print(f"\nA pasta de entrada não existia e foi criada agora:\n  {entrada}")
        print("Copie para ela os arquivos CSV dos quiosques (ou o CSV baixado da planilha) e rode de novo.")
        return 1

    try:
        from relatorio.analise import analisar
        from relatorio.excel import gerar_excel
        from relatorio.html import gerar_html
        from relatorio.leitura import carregar_pasta, filtrar_periodo
        from relatorio.resumo import gerar_resumo
    except ImportError as erro:
        print(f"\nERRO: faltam bibliotecas do relatório ({erro}). Rode o instalar.bat (opção do PC da CIPA).")
        return 3

    print(f"\nLendo os arquivos CSV de:\n  {entrada}")
    leitura = carregar_pasta(entrada, config.get("ordem_emocoes"))
    for caminho, motivo in leitura.arquivos_ignorados:
        print(f"  Aviso: arquivo ignorado ({motivo}): {caminho.name}")
    if not leitura.arquivos_lidos:
        print("\nNenhum arquivo CSV do Termômetro foi encontrado nessa pasta.")
        print("Copie para ela os CSVs dos quiosques (pasta 'dados') ou o CSV baixado da planilha e rode de novo.")
        return 1
    print(f"  {len(leitura.arquivos_lidos)} arquivo(s), {leitura.linhas_lidas} linha(s) lidas.")
    if leitura.duplicadas_removidas:
        print(f"  {leitura.duplicadas_removidas} resposta(s) repetida(s) foram consolidadas (mesmo response_id).")
    for aviso in leitura.avisos:
        print(f"  Aviso: {aviso}")

    df = filtrar_periodo(leitura.dados, inicio, fim)
    if df.empty:
        print("\nNão há respostas no período escolhido. Confira as datas de início e fim.")
        return 1
    print(f"  {len(df)} resposta(s) no período de {min(df['data']).strftime('%d/%m/%Y')} "
          f"a {max(df['data']).strftime('%d/%m/%Y')}.")

    print("\nCalculando os indicadores...")
    resultado = analisar(df, config)
    resumo = gerar_resumo(resultado)
    info = {
        "arquivos_lidos": leitura.arquivos_lidos,
        "arquivos_ignorados": leitura.arquivos_ignorados,
        "linhas_lidas": leitura.linhas_lidas,
        "duplicadas_removidas": leitura.duplicadas_removidas,
        "avisos": leitura.avisos,
    }

    hoje = date.today().isoformat()
    caminho_html = gerar_html(resultado, resumo, saida / f"relatorio_{hoje}.html", info, raiz)
    caminho_xlsx = gerar_excel(resultado, resumo, saida / f"relatorio_{hoje}.xlsx", info)

    print("\nRelatório pronto!")
    print(f"  Página (abra no navegador): {caminho_html}")
    print(f"  Planilha (Excel):           {caminho_xlsx}")
    if caminho_xlsx.name != f"relatorio_{hoje}.xlsx":
        print("  (O Excel anterior estava aberto, por isso o novo foi salvo com outro nome.)")

    if not args.nao_abrir and config.get("abrir_ao_terminar", True):
        _abrir(caminho_html)
    return 0


if __name__ == "__main__":
    sys.exit(main())
