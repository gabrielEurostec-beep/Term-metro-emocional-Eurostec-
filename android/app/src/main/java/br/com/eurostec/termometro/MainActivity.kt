package br.com.eurostec.termometro

import android.annotation.SuppressLint
import android.app.Activity
import android.app.ActivityManager
import android.graphics.Color
import android.graphics.Typeface
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.TextView
import com.chaquo.python.Python
import java.net.HttpURLConnection
import java.net.URL

/**
 * Tela do quiosque: mostra o Termômetro em tela cheia, sem barras do sistema.
 * O conteúdo vem do servidor local (ServicoQuiosque), em 127.0.0.1.
 */
class MainActivity : Activity() {

    private lateinit var telaWeb: WebView
    private lateinit var aviso: TextView
    private val handler = Handler(Looper.getMainLooper())
    private var fixarTelaJaTentado = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // O tablet não pode apagar a tela enquanto o quiosque está aberto.
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        aviso = TextView(this).apply {
            text = getString(R.string.iniciando)
            textSize = 22f
            gravity = Gravity.CENTER
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.parseColor("#0446A4"))
            setPadding(64, 64, 64, 64)
            typeface = Typeface.DEFAULT_BOLD
        }
        telaWeb = WebView(this).apply {
            visibility = View.GONE
            configurar()
        }
        setContentView(FrameLayout(this).apply {
            addView(telaWeb, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
            addView(aviso, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        })

        esconderBarras()
        pedirPermissaoDeNotificacao()
        ServicoQuiosque.iniciar(this)
        esperarServidorEAbrir()
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) esconderBarras()
    }

    override fun onResume() {
        super.onResume()
        fixarTela()
    }

    // Botão "voltar" não faz nada no quiosque (a administração sai pelo botão próprio).
    @Deprecated("Quiosque: o botão voltar é ignorado")
    override fun onBackPressed() {}

    @SuppressLint("SetJavaScriptEnabled")
    private fun WebView.configurar() {
        settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            cacheMode = WebSettings.LOAD_NO_CACHE
            setSupportZoom(false)
            builtInZoomControls = false
            displayZoomControls = false
            allowFileAccess = false
            allowContentAccess = false
        }
        addJavascriptInterface(PonteAndroid(this@MainActivity), "AndroidApp")
        isLongClickable = false
        setOnLongClickListener { true } // sem menu de cópia nem seleção de texto
        webChromeClient = WebChromeClient()
        webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                // Só o próprio quiosque: qualquer outro endereço é bloqueado.
                return !ehEnderecoDoQuiosque(request.url)
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame) {
                    voltarParaAviso()
                }
            }
        }
    }

    private fun ehEnderecoDoQuiosque(uri: Uri): Boolean =
        uri.host == "127.0.0.1" || uri.host == "localhost"

    /** Espera o servidor responder (em segundo plano) e só então mostra as telas. */
    private fun esperarServidorEAbrir() {
        Thread { aguardarEAbrir() }.start()
    }

    private fun aguardarEAbrir() {
        var tentativas = 0
        while (tentativas < 240) {
            val erro = Estado.erro
            if (erro != null) {
                mostrarErro(erro)
                return
            }
            if (servidorRespondendo()) {
                handler.post {
                    aviso.visibility = View.GONE
                    telaWeb.visibility = View.VISIBLE
                    telaWeb.loadUrl(Estado.ENDERECO + "/")
                }
                return
            }
            tentativas++
            Thread.sleep(500)
        }
        mostrarErro("Tempo esgotado ao iniciar o servidor.")
    }

    private fun voltarParaAviso() {
        handler.post {
            telaWeb.visibility = View.GONE
            aviso.visibility = View.VISIBLE
            aviso.text = getString(R.string.iniciando)
            esperarServidorEAbrir()
        }
    }

    private fun mostrarErro(detalhe: String) {
        handler.post {
            aviso.text = getString(R.string.erro_iniciar) + "\n\n" + detalhe
        }
    }

    private fun servidorRespondendo(): Boolean =
        try {
            val conexao = URL(Estado.ENDERECO + "/api/saude").openConnection() as HttpURLConnection
            conexao.connectTimeout = 1000
            conexao.readTimeout = 1000
            conexao.responseCode == 200
        } catch (e: Exception) {
            false
        }

    /**
     * Fixa a tela no aplicativo (modo quiosque do Android). Na primeira vez, o tablet pede
     * confirmação. Para bloqueio total sem confirmação, o tablet precisa ser gerenciado (MDM).
     */
    private fun fixarTela() {
        if (fixarTelaJaTentado) return
        fixarTelaJaTentado = true
        val gerenciador = getSystemService(ActivityManager::class.java)
        if (gerenciador.lockTaskModeState == ActivityManager.LOCK_TASK_MODE_NONE) {
            try {
                startLockTask()
            } catch (e: Exception) {
                // O usuário recusou a fixação: o quiosque continua funcionando sem ela.
            }
        }
    }

    private fun pedirPermissaoDeNotificacao() {
        if (Build.VERSION.SDK_INT >= 33) {
            requestPermissions(arrayOf("android.permission.POST_NOTIFICATIONS"), 1)
        }
    }

    @Suppress("DEPRECATION")
    private fun esconderBarras() {
        window.decorView.systemUiVisibility = (
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY or
                View.SYSTEM_UI_FLAG_FULLSCREEN or
                View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or
                View.SYSTEM_UI_FLAG_LAYOUT_STABLE or
                View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN or
                View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            )
    }

    /** Chamado pela administração ("Fechar o quiosque"): para o servidor e volta ao Android. */
    fun sairDoQuiosque() {
        try {
            stopLockTask()
        } catch (_: Exception) {
            // não estava fixada
        }
        ServicoQuiosque.parar(this)
        finishAndRemoveTask()
    }
}
