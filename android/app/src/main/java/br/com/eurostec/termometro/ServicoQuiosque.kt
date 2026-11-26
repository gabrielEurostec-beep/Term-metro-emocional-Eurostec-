package br.com.eurostec.termometro

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import com.chaquo.python.Python
import java.io.File

/**
 * Mantém o servidor do quiosque rodando, mesmo que a tela esteja fechada.
 * O servidor é o mesmo do quiosque Windows (quiosque/servidor.py), chamado pelo Chaquopy.
 */
class ServicoQuiosque : Service() {

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        criarCanal()
        val notificacao = montarNotificacao()
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(ID_NOTIFICACAO, notificacao, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(ID_NOTIFICACAO, notificacao)
        }
        if (!Estado.servidorIniciado) {
            Thread { subirServidor() }.start()
        }
        return START_STICKY
    }

    private fun subirServidor() {
        try {
            Arquivos.prepararArquivos(this)
            val base = Arquivos.pastaBase(this)
            val web = File(base, "web")
            Python.getInstance()
                .getModule("quiosque.android_app")
                .callAttr("iniciar", base.absolutePath, web.absolutePath, Estado.PORTA)
            Estado.erro = null
            Estado.servidorIniciado = true
        } catch (e: Exception) {
            Estado.erro = e.message ?: e.toString()
        }
    }

    override fun onDestroy() {
        try {
            Python.getInstance().getModule("quiosque.android_app").callAttr("parar")
        } catch (_: Exception) {
            // o aplicativo já está fechando
        }
        Estado.servidorIniciado = false
        super.onDestroy()
    }

    private fun criarCanal() {
        val gerenciador = getSystemService(NotificationManager::class.java)
        if (gerenciador.getNotificationChannel(CANAL) == null) {
            gerenciador.createNotificationChannel(
                NotificationChannel(CANAL, "Termômetro Emocional", NotificationManager.IMPORTANCE_LOW)
            )
        }
    }

    private fun montarNotificacao(): Notification =
        Notification.Builder(this, CANAL)
            .setContentTitle("Termômetro Emocional")
            .setContentText("Quiosque em funcionamento")
            .setSmallIcon(R.drawable.ic_notificacao)
            .setOngoing(true)
            .build()

    companion object {
        private const val CANAL = "quiosque"
        private const val ID_NOTIFICACAO = 1

        fun iniciar(context: Context) {
            context.startForegroundService(Intent(context, ServicoQuiosque::class.java))
        }

        fun parar(context: Context) {
            context.stopService(Intent(context, ServicoQuiosque::class.java))
        }
    }
}
