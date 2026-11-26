package br.com.eurostec.termometro

import android.content.ContentValues
import android.content.Context
import android.os.Environment
import android.provider.MediaStore
import org.json.JSONObject
import java.io.File

/**
 * Arquivos do quiosque no tablet.
 *
 * - Telas e logos (web/ e assets/) vêm empacotados no APK e são copiados a cada abertura,
 *   para ficarem sempre iguais à versão do aplicativo.
 * - config/, dados/ (CSVs) e estado/ ficam na memória interna do app e NUNCA são apagados
 *   por esta cópia. Atualizar o aplicativo preserva as respostas.
 */
object Arquivos {
    private const val PASTA_BASE = "termometro"
    private const val PASTA_DOWNLOAD = "TermometroEurostec"

    fun pastaBase(context: Context): File = File(context.filesDir, PASTA_BASE)

    fun prepararArquivos(context: Context) {
        val base = pastaBase(context)
        copiarDoApk(context, "termometro/web", File(base, "web"))
        copiarDoApk(context, "termometro/assets", File(base, "assets"))
    }

    private fun copiarDoApk(context: Context, origem: String, destino: File) {
        val gerenciador = context.assets
        val itens = gerenciador.list(origem) ?: emptyArray()
        if (itens.isEmpty()) {
            destino.parentFile?.mkdirs()
            gerenciador.open(origem).use { entrada ->
                destino.outputStream().use { saida -> entrada.copyTo(saida) }
            }
            return
        }
        destino.mkdirs()
        for (nome in itens) {
            copiarDoApk(context, "$origem/$nome", File(destino, nome))
        }
    }

    /**
     * Copia os CSVs de respostas para Download/TermometroEurostec, onde o app "Arquivos"
     * encontra. Devolve um JSON: {ok, copiados, pasta} ou {ok: false, erro}.
     */
    fun exportarCsvParaDownloads(context: Context): JSONObject {
        val csvs = File(pastaBase(context), "dados")
            .listFiles { f -> f.name.startsWith("respostas_") && f.name.endsWith(".csv") }
            ?.toList()
            ?: emptyList()
        if (csvs.isEmpty()) {
            return JSONObject().put("ok", false).put("erro", "Ainda não há respostas gravadas neste tablet.")
        }
        for (csv in csvs) {
            gravarEmDownloads(context, csv)
        }
        return JSONObject()
            .put("ok", true)
            .put("copiados", csvs.size)
            .put("pasta", "Download/$PASTA_DOWNLOAD")
    }

    private fun gravarEmDownloads(context: Context, arquivo: File) {
        val resolver = context.contentResolver
        val pasta = "${Environment.DIRECTORY_DOWNLOADS}/$PASTA_DOWNLOAD/"

        // Substitui a cópia anterior do mesmo arquivo (evita "respostas (1).csv").
        resolver.delete(
            MediaStore.Downloads.EXTERNAL_CONTENT_URI,
            "${MediaStore.MediaColumns.DISPLAY_NAME} = ? AND ${MediaStore.MediaColumns.RELATIVE_PATH} = ?",
            arrayOf(arquivo.name, pasta)
        )

        val valores = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, arquivo.name)
            put(MediaStore.MediaColumns.MIME_TYPE, "text/csv")
            put(MediaStore.MediaColumns.RELATIVE_PATH, pasta)
            put(MediaStore.MediaColumns.IS_PENDING, 1)
        }
        val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, valores)
            ?: throw IllegalStateException("Não foi possível criar ${arquivo.name} em Download.")
        resolver.openOutputStream(uri)?.use { saida ->
            arquivo.inputStream().use { entrada -> entrada.copyTo(saida) }
        } ?: throw IllegalStateException("Não foi possível gravar ${arquivo.name}.")

        valores.clear()
        valores.put(MediaStore.MediaColumns.IS_PENDING, 0)
        resolver.update(uri, valores, null, null)
    }
}
