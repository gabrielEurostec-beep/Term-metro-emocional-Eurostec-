package br.com.eurostec.termometro

import android.webkit.JavascriptInterface
import org.json.JSONObject

/**
 * Funções do tablet chamadas pelas telas (window.AndroidApp no app.js).
 * Só o que não dá para fazer pelo navegador: copiar para Download e fechar o aplicativo.
 */
class PonteAndroid(private val tela: MainActivity) {

    @JavascriptInterface
    fun exportarParaDownloads(): String =
        try {
            Arquivos.exportarCsvParaDownloads(tela).toString()
        } catch (e: Exception) {
            JSONObject()
                .put("ok", false)
                .put("erro", "Não foi possível copiar os arquivos: ${e.message ?: "erro desconhecido"}")
                .toString()
        }

    @JavascriptInterface
    fun sair() {
        tela.runOnUiThread { tela.sairDoQuiosque() }
    }

    @JavascriptInterface
    fun versao(): String = BuildConfig.VERSION_NAME
}
